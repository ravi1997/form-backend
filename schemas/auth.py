from pydantic import BaseModel, Field
from typing import Optional


class LoginRequest(BaseModel):
    identifier: str = Field(..., description="Username, email, or employee ID")
    password: str = Field(..., min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    sub: str  # user_id
    jti: str
    exp: int
    iat: int
    roles: list[str] = []
