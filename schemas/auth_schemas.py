"""
schemas/auth_schemas.py
Authentication and authorization request/response schemas.
"""

from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    """User role enumeration."""
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    USER = "user"
    CREATOR = "creator"
    APPROVER = "approver"
    EDITOR = "editor"
    PUBLISHER = "publisher"
    DEO = "deo"
    MANAGER = "manager"
    GENERAL = "general"


class UserLoginRequest(BaseModel):
    """User login request schema."""
    identifier: str = Field(..., description="Username, email, or employee ID")
    password: str = Field(..., min_length=8, description="User password")
    remember_me: bool = Field(default=False, description="Remember me token")


class UserLoginResponse(BaseModel):
    """User login response schema."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")
    user: dict = Field(..., description="User information")


class UserRegisterRequest(BaseModel):
    """User registration request schema."""
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(..., min_length=8, description="Password")
    full_name: str = Field(..., min_length=2, max_length=100, description="Full name")
    roles: List[UserRole] = Field(default=[UserRole.USER], description="User roles")


class UserRegisterResponse(BaseModel):
    """User registration response schema."""
    id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    email: str = Field(..., description="Email address")
    full_name: str = Field(..., description="Full name")
    roles: List[UserRole] = Field(..., description="User roles")
    is_active: bool = Field(default=True, description="Account status")
    created_at: datetime = Field(..., description="Creation timestamp")


class RefreshTokenRequest(BaseModel):
    """Refresh token request schema."""
    refresh_token: str = Field(..., description="Refresh token")


class ApiKeyCreateRequest(BaseModel):
    """API key creation request schema."""
    name: str = Field(..., min_length=1, max_length=100, description="API key name")
    scopes: List[str] = Field(default=[], description="API key scopes")
    expires_at: Optional[datetime] = Field(None, description="Expiration date")


class ApiKeyResponse(BaseModel):
    """API key response schema."""
    id: str = Field(..., description="API key ID")
    name: str = Field(..., description="API key name")
    key_prefix: str = Field(..., description="API key prefix")
    scopes: List[str] = Field(..., description="API key scopes")
    is_active: bool = Field(..., description="API key status")
    created_at: datetime = Field(..., description="Creation timestamp")
    expires_at: Optional[datetime] = Field(None, description="Expiration date")
    last_used_at: Optional[datetime] = Field(None, description="Last used timestamp")