"""
AegisCX Authentication Routes
=============================
Endpoints:
  POST /auth/register  - Create a new user account
  POST /auth/login     - Authenticate and receive tokens
  POST /auth/refresh   - Refresh access token
  POST /auth/logout    - Invalidate session client-side
  GET  /auth/me        - Get the current user profile
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.models.models import Company, User

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    company_name: Optional[str] = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, value: str) -> str:
        if not any(char.isdigit() for char in value):
            raise ValueError("Password must contain at least one digit")
        if not any(char.isalpha() for char in value):
            raise ValueError("Password must contain at least one letter")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    company_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


async def _ensure_user_workspace(
    db: AsyncSession,
    *,
    user: User,
    preferred_company_name: Optional[str] = None,
) -> None:
    """
    Ensure every real account belongs to a company workspace.

    Several dashboard and upload paths are multi-tenant by design, so a missing
    company_id creates confusing downstream behavior. We normalize that here
    for both new registrations and older local users created before this rule.
    """
    if user.company_id:
        return

    workspace_name = (
        (preferred_company_name or "").strip()
        or f"{user.name.strip()}'s Workspace"
    )
    company = Company(
        name=workspace_name,
        industry="customer intelligence",
        subscription_tier="free",
        is_active=True,
    )
    db.add(company)
    await db.flush()

    user.company_id = company.id
    user.role = "admin"


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Create a new user account and assign it to a workspace immediately so the
    dashboard, uploads, and analytics all work on the first sign-in.
    """
    existing_user = await db.execute(select(User).where(User.email == body.email))
    if existing_user.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address already registered",
        )

    user = User(
        email=body.email.strip().lower(),
        name=body.name.strip(),
        password_hash=hash_password(body.password),
        role="admin",
    )
    db.add(user)
    await db.flush()

    await _ensure_user_workspace(
        db,
        user=user,
        preferred_company_name=body.company_name,
    )

    await db.commit()
    await db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user.id, user.role, user.company_id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Authenticate with email and password.
    """
    result = await db.execute(
        select(User).where(User.email == body.email.strip().lower())
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been deactivated",
        )

    await _ensure_user_workspace(db, user=user)

    # Smoothly migrate older local password hashes after a successful login so
    # future sign-ins stay stable on this environment.
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)

    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    return TokenResponse(
        access_token=create_access_token(user.id, user.role, user.company_id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """
    Exchange a valid refresh token for a new access token.
    """
    payload = decode_token(body.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    await _ensure_user_workspace(db, user=user)
    await db.commit()

    return TokenResponse(
        access_token=create_access_token(user.id, user.role, user.company_id),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the profile of the currently authenticated user.
    """
    result = await db.execute(
        select(User).where(User.id == current_user["user_id"])
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
