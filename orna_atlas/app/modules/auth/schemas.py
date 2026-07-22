from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from orna_atlas.app.modules.users.schemas import UserRead


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class MagicLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    return_to: str | None = Field(default=None, max_length=512)


class MagicLinkAccepted(BaseModel):
    accepted: bool = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserRead


class OAuthProvidersResponse(BaseModel):
    providers: list[Literal["google", "apple", "facebook"]]


class LogoutResponse(BaseModel):
    status: str = "logged_out"
