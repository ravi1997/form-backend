from pydantic import BaseModel, Field
from typing import Optional


class LoginRequest(BaseModel):
    identifier: Optional[str] = Field(None, description="Username, email, or employee ID (for password login)")
    password: Optional[str] = Field(None, min_length=8, description="Password (for password login)")
    mobile: Optional[str] = Field(None, max_length=15, description="Mobile number (for OTP login)")
    otp: Optional[str] = Field(None, min_length=4, max_length=6, description="OTP (for OTP login)")


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
