from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from orna_atlas.app.modules.users.schemas import UserRead


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserRead


class OAuthProvidersResponse(BaseModel):
    providers: list[Literal["google", "apple", "facebook"]]


class LogoutResponse(BaseModel):
    status: str = "logged_out"
