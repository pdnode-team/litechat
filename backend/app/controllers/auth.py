from typing import Optional
from litestar import Controller, get, post, Request
from litestar.exceptions import NotAuthorizedException, ValidationException, PermissionDeniedException
from sqlalchemy import select, or_, func
from app.db.session import async_session_factory
from app.models.auth_token import PURPOSE_EMAIL_VERIFICATION, PURPOSE_PASSWORD_RESET
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SetupAdminRequest,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
)
from app.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.services.email_service import (
    send_email_verification_email,
    send_password_reset_email,
)
from app.services.token_service import consume_token, issue_token

# Compared against when the submitted identifier matches no user, purely to keep
# the failure path's timing consistent with the success path.
_DUMMY_PASSWORD_HASH = hash_password("litechat-timing-equalizer")

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

            # Fire-and-forget confirmation link; registration is not blocked on it.
            verification_token = await issue_token(session, new_user.id, PURPOSE_EMAIL_VERIFICATION)
            await send_email_verification_email(new_user.email, verification_token)

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
            # Always run a bcrypt comparison, even for an unknown user, so the
            # response time does not reveal whether the account exists.
            if user is None:
                verify_password(data.password, _DUMMY_PASSWORD_HASH)
                raise NotAuthorizedException("Invalid credentials provided.")
            if not verify_password(data.password, user.hashed_password):
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

    @post("/forgot-password", status_code=202)
    async def forgot_password(self, data: ForgotPasswordRequest) -> dict:
        """Request a password-reset link.

        Always reports success so the endpoint cannot be used to discover which
        email addresses have accounts.
        """
        async with async_session_factory() as session:
            user = (
                await session.execute(select(User).where(User.email == data.email.strip().lower()))
            ).scalar_one_or_none()

            if user and user.is_active:
                raw_token = await issue_token(session, user.id, PURPOSE_PASSWORD_RESET)
                await send_password_reset_email(user.email, raw_token)

        return {"detail": "If that address has an account, a reset link has been sent."}

    @post("/reset-password")
    async def reset_password(self, data: ResetPasswordRequest) -> dict:
        async with async_session_factory() as session:
            token = await consume_token(session, data.token, PURPOSE_PASSWORD_RESET)
            if token is None:
                raise ValidationException("This reset link is invalid or has expired.")

            user = await session.get(User, token.user_id)
            if not user or not user.is_active:
                raise ValidationException("This reset link is invalid or has expired.")

            user.hashed_password = hash_password(data.new_password)
            await session.commit()

        return {"detail": "Password updated. You can now sign in."}

    @post("/verify-email")
    async def verify_email(self, data: VerifyEmailRequest) -> dict:
        async with async_session_factory() as session:
            token = await consume_token(session, data.token, PURPOSE_EMAIL_VERIFICATION)
            if token is None:
                raise ValidationException("This verification link is invalid or has expired.")

            user = await session.get(User, token.user_id)
            if not user:
                raise ValidationException("This verification link is invalid or has expired.")

            user.email_verified = True
            await session.commit()

        return {"detail": "Email address confirmed."}

    @post("/resend-verification")
    async def resend_verification(self, request: Request) -> dict:
        user = await get_current_user_from_request(request)
        if not user:
            raise NotAuthorizedException("Authentication required.")
        if user.email_verified:
            return {"detail": "Your email address is already confirmed."}

        async with async_session_factory() as session:
            raw_token = await issue_token(session, user.id, PURPOSE_EMAIL_VERIFICATION)
        await send_email_verification_email(user.email, raw_token)

        return {"detail": "Verification email sent."}

    @post("/change-password")
    async def change_password(self, request: Request, data: ChangePasswordRequest) -> dict:
        user = await get_current_user_from_request(request)
        if not user:
            raise NotAuthorizedException("Authentication required.")

        if not verify_password(data.current_password, user.hashed_password):
            raise ValidationException("Your current password is incorrect.")

        async with async_session_factory() as session:
            db_user = await session.get(User, user.id)
            if not db_user:
                raise NotAuthorizedException("Authentication required.")
            db_user.hashed_password = hash_password(data.new_password)
            await session.commit()

        return {"detail": "Password changed."}
