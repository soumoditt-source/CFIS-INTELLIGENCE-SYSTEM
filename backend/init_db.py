"""
AegisCX Database Initializer
==============================
Bootstraps the database schema.
Run this before starting the platform for the first time.
"""

import asyncio
import sys
import os

# CRITICAL: always run from the backend directory so .env and ./data/ paths resolve correctly
_script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(_script_dir)
# Add backend dir to sys.path for imports
sys.path.insert(0, _script_dir)

from app.core.database import init_db, check_db_health, DATABASE_URL
from app.core.config import get_settings

settings = get_settings()

async def seed_data():
    """Seed the database with a default company and admin user for local dev."""
    from app.core.database import AsyncSessionLocal
    from app.models.models import User, Company
    from sqlalchemy import select

    MOCK_ID = "00000000-0000-0000-0000-000000000000"
    
    async with AsyncSessionLocal() as db:
        # Check if company exists
        result = await db.execute(select(Company).where(Company.id == MOCK_ID))
        company = result.scalar_one_or_none()
        
        if not company:
            print(f"Seeding default company: {MOCK_ID}")
            company = Company(
                id=MOCK_ID,
                name="AegisCX Development",
                industry="Technology",
                subscription_tier="enterprise"
            )
            db.add(company)
            await db.flush()

        # Check if user exists
        result = await db.execute(select(User).where(User.id == MOCK_ID))
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"Seeding default admin user: {MOCK_ID}")
            user = User(
                id=MOCK_ID,
                email="admin@aegiscx.local",
                name="Aegis Admin",
                password_hash="BYPASS", # Not used in dev bypass mode
                role="admin",
                company_id=MOCK_ID,
                is_active=True
            )
            db.add(user)
        
        await db.commit()
        print("SUCCESS: Seeding complete.")

async def main():
    print(f"--- AegisCX Database Initializer ---")
    print(f"Target: {DATABASE_URL}")
    
    # Check health first
    is_up = await check_db_health()
    if not is_up and "postgresql" in DATABASE_URL:
        print("ERROR: PostgreSQL is not reachable. Ensure the database is running.")
        sys.exit(1)
        
    print("Initializing tables...")
    try:
        await init_db()
        print("SUCCESS: Database initialized successfully.")
        
        # Seed default data
        await seed_data()
        
    except Exception as e:
        print(f"FAILED: Error during initialization: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
