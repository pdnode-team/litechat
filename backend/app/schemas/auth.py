import re
from datetime import datetime, timezone
from typing import Optional
from pydantic import ConfigDict, BaseModel, EmailStr, Field, field_validator

def validate_password_strength(v: str) -> str:
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if not re.search(r"[A-Za-z]", v) or not re.search(r"[0-9]", v):
        raise ValueError("Password must contain both letters and digits.")
    if len(v.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes.")
    return v

class LoginRequest(BaseModel):
    username_or_email: str
    password: str

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    full_name: str = Field(min_length=2, max_length=60)
    password: str

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return validate_password_strength(v)

class SetupAdminRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    full_name: str = Field(min_length=2, max_length=60)
    password: str

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return validate_password_strength(v)

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return validate_password_strength(v)

class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10)

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return validate_password_strength(v)

class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: str
    role: str
    avatar_url: Optional[str] = None
    is_active: bool
    email_verified: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    user: UserResponse

