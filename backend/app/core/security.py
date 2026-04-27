"""
AegisCX Authentication Core
===========================
Provides:
  - Password hashing and verification
  - JWT access token creation and verification
  - Refresh token management
  - FastAPI security dependency helpers

The local Windows environment has been intermittently unstable with passlib's
automatic bcrypt backend checks, so new passwords use a deterministic
PBKDF2-SHA256 format implemented with the Python standard library. Legacy
bcrypt hashes are still accepted so older local users continue to work.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db

settings = get_settings()

# Keep passlib only as a compatibility helper for legacy hashes that are not
# in the new PBKDF2 format.
_legacy_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)
_PBKDF2_PREFIX = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 390_000

# LOGINLESS MODE: auto_error=False means missing or bad tokens do not
# automatically reject the request before development fallbacks can run.
_http_bearer = HTTPBearer(auto_error=False)


def _encode_b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_b64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def _hash_password_pbkdf2(plain_password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        plain_password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
    )
    return (
        f"{_PBKDF2_PREFIX}${_PBKDF2_ITERATIONS}$"
        f"{_encode_b64(salt)}${_encode_b64(digest)}"
    )


def _verify_password_pbkdf2(plain_password: str, hashed_password: str) -> bool:
    try:
        _, rounds, encoded_salt, encoded_digest = hashed_password.split("$", 3)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            _decode_b64(encoded_salt),
            int(rounds),
        )
        return hmac.compare_digest(_encode_b64(digest), encoded_digest)
    except Exception:
        return False


def password_needs_rehash(hashed_password: str) -> bool:
    """
    Return True when a stored password should be rewritten into the current
    stable PBKDF2 format.
    """
    if not hashed_password:
        return True
    return not hashed_password.startswith(f"{_PBKDF2_PREFIX}$")


def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password using the stable PBKDF2-SHA256 format.
    """
    return _hash_password_pbkdf2(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against the stored password hash.
    """
    if not hashed_password:
        return False

    if hashed_password.startswith(f"{_PBKDF2_PREFIX}$"):
        return _verify_password_pbkdf2(plain_password, hashed_password)

    if hashed_password.startswith("$2"):
        try:
            import bcrypt

            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except Exception:
            return False

    try:
        return _legacy_pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def create_access_token(user_id: str, role: str, company_id: Optional[str] = None) -> str:
    """
    Create a signed JWT access token.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "role": role,
        "company_id": str(company_id) if company_id else None,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_refresh_token(user_id: str) -> str:
    """
    Create a long-lived refresh token.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        if payload.get("sub") is None:
            raise credentials_exception
        return payload
    except JWTError:
        raise credentials_exception


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_http_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Validate a bearer token and return the current user context.

    In development, a missing token falls back to a deterministic local admin
    so the dashboard remains usable even before a manual signup flow is tested.
    """
    if not credentials or not credentials.credentials:
        if settings.environment == "development":
            return {
                "user_id": "00000000-0000-0000-0000-000000000000",
                "role": "admin",
                "company_id": "00000000-0000-0000-0000-000000000000",
                "is_mock": True,
            }

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type: access token required",
        )

    return {
        "user_id": payload["sub"],
        "role": payload.get("role"),
        "company_id": payload.get("company_id"),
    }


def require_role(*roles: str):
    """
    Role-based access control dependency factory.
    """

    async def role_checker(
        current_user: dict = Depends(get_current_user),
    ) -> dict:
        if current_user["role"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {list(roles)}",
            )
        return current_user

    return role_checker
