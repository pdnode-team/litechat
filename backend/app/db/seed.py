import os
import logging
from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.user import User
from app.services.auth_service import hash_password

logger = logging.getLogger("litechat.seed")

async def seed_initial_data() -> None:
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")
    if admin_email and admin_password:
        async with async_session_factory() as session:
            stmt = select(User).where(User.email == admin_email.strip().lower())
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if not existing:
                username = os.getenv("ADMIN_USERNAME", "admin").strip().lower()
                full_name = os.getenv("ADMIN_NAME", "System Administrator").strip()
                admin = User(
                    email=admin_email.strip().lower(),
                    username=username,
                    full_name=full_name,
                    hashed_password=hash_password(admin_password),
                    role="admin",
                    is_active=True,
                )
                session.add(admin)
                await session.commit()
                logger.info("Seeded initial administrator account from environment: %s", admin.email)

