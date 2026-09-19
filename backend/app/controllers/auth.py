from typing import Optional
from litestar import Controller, get, post, Request
from litestar.exceptions import NotAuthorizedException, ValidationException, PermissionDeniedException
from sqlalchemy import select, or_, func
from app.db.session import async_session_factory
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    SetupAdminRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)

async def get_current_user_from_request(request: Request) -> Optional[User]:
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1]
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        # A malformed 'sub' claim is an authentication failure, never a 500.
        return None
    async with async_session_factory() as session:
        user = await session.get(User, user_id)
        if user and not user.is_active:
            return None
        return user

class AuthController(Controller):
    path = "/api/auth"

    @get("/bootstrap-status")
    async def bootstrap_status(self) -> dict:
        """Public probe so the UI can tell a fresh install apart from an initialised one.

        Reveals only whether the user table is empty, which the setup-admin endpoint
        already discloses through its locked/unlocked response.
        """
        async with async_session_factory() as session:
            count_res = await session.execute(select(func.count(User.id)))
            return {"needs_setup": count_res.scalar_one() == 0}

    @post("/register")
    async def register(self, data: RegisterRequest) -> TokenResponse:
        async with async_session_factory() as session:
            # Check duplicate
            stmt = select(User).where(or_(User.email == data.email, User.username == data.username))
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                raise ValidationException("Username or Email is already registered.")

            # All public registrations are strictly assigned the 'customer' role
            new_user = User(
                email=data.email.strip().lower(),
                username=data.username.strip().lower(),
                full_name=data.full_name.strip(),
                hashed_password=hash_password(data.password),
                role="customer",
                avatar_url=None,
                is_active=True,
            )
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)

            token = create_access_token({
                "sub": str(new_user.id),
                "role": new_user.role,
                "name": new_user.full_name,
            })
            return TokenResponse(
                access_token=token,
                user=UserResponse.model_validate(new_user),
            )

    @post("/setup-admin")
    async def setup_admin(self, data: SetupAdminRequest) -> TokenResponse:
        """One-time bootstrap endpoint for creating the initial root administrator if system has 0 users."""
        async with async_session_factory() as session:
            count_res = await session.execute(select(func.count(User.id)))
            if count_res.scalar_one() > 0:
                raise PermissionDeniedException("System already has active accounts. Administrator setup is locked.")

            admin_user = User(
                email=data.email.strip().lower(),
                username=data.username.strip().lower(),
                full_name=data.full_name.strip(),
                hashed_password=hash_password(data.password),
                role="admin",
                avatar_url=None,
                is_active=True,
            )
            session.add(admin_user)
            await session.commit()
            await session.refresh(admin_user)

            token = create_access_token({
                "sub": str(admin_user.id),
                "role": admin_user.role,
                "name": admin_user.full_name,
            })
            return TokenResponse(
                access_token=token,
                user=UserResponse.model_validate(admin_user),
            )

    @post("/login")
    async def login(self, data: LoginRequest) -> TokenResponse:
        async with async_session_factory() as session:
            identifier = data.username_or_email.strip().lower()
            stmt = select(User).where(
                or_(User.email == identifier, User.username == identifier)
            )
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if not user or not verify_password(data.password, user.hashed_password):
                raise NotAuthorizedException("Invalid credentials provided.")

            if not user.is_active:
                raise NotAuthorizedException("Account is disabled. Please contact an administrator.")

            token = create_access_token({
                "sub": str(user.id),
                "role": user.role,
                "name": user.full_name,
            })
            return TokenResponse(
                access_token=token,
                user=UserResponse.model_validate(user),
            )

    @get("/me")
    async def get_current_user(self, request: Request) -> UserResponse:
        user = await get_current_user_from_request(request)
        if not user:
            raise NotAuthorizedException("Authentication required.")
        return UserResponse.model_validate(user)
