import asyncio
import sys
import argparse
from sqlalchemy import select
from app.db.session import async_session_factory, init_db
from app.models.user import User
from app.services.auth_service import hash_password
from app.schemas.auth import validate_password_strength

async def create_admin(email: str, username: str, full_name: str, password: str):
    await init_db()
    validate_password_strength(password)
    async with async_session_factory() as session:
        stmt = select(User).where((User.email == email.lower()) | (User.username == username.lower()))
        res = await session.execute(stmt)
        if res.scalar_one_or_none():
            print(f"Error: User with email '{email}' or username '{username}' already exists.")
            sys.exit(1)

        admin = User(
            email=email.strip().lower(),
            username=username.strip().lower(),
            full_name=full_name.strip(),
            hashed_password=hash_password(password),
            role="admin",
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        print(f"Successfully created Administrator account: @{admin.username} ({admin.email}) [ID: {admin.id}]")

def main():
    parser = argparse.ArgumentParser(description="Create a LiteChat administrator account")
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument("--username", required=True, help="Admin username")
    parser.add_argument("--full-name", required=True, help="Admin full name")
    parser.add_argument("--password", required=True, help="Admin password (min 8 chars, letters and digits)")
    args = parser.parse_args()

    asyncio.run(create_admin(args.email, args.username, args.full_name, args.password))

if __name__ == "__main__":
    main()
