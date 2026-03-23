from pydantic import Field, validator
from typing import Optional, List, Literal
from datetime import datetime
from .base import SoftDeleteBaseSchema, InboundPayloadSchema


class UserSchema(SoftDeleteBaseSchema):
    username: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, pattern=r"^\S+@\S+\.\S+$")
    employee_id: Optional[str] = Field(None, max_length=30)
    mobile: Optional[str] = Field(None, max_length=15)
    department: Optional[str] = None
    organization_id: Optional[str] = None

    user_type: Literal["employee", "general"]

    is_active: bool = True
    is_admin: bool = False
    is_email_verified: bool = False

    roles: List[
        Literal[
            "superadmin",
            "admin",
            "user",
            "creator",
            "approver",
            "editor",
            "publisher",
            "deo",
            "manager",
            "general",
        ]
    ] = Field(default_factory=list)

    failed_login_attempts: int = 0
    otp_resend_count: int = 0
    lock_until: Optional[datetime] = None
    last_login: Optional[datetime] = None


class UserCreateSchema(UserSchema, InboundPayloadSchema):
    password: str = Field(..., min_length=8)


class UserUpdateSchema(UserSchema, InboundPayloadSchema):
    password: Optional[str] = Field(None, min_length=8)


class UserOut(UserSchema):
    """
    Schema for public API responses. 
    Excludes internal security counters.
    """
    id: str
    
    class Config:
        # Exclude internal bookkeeping fields from output
        exclude = {
            "failed_login_attempts",
            "otp_resend_count",
            "lock_until",
            "is_deleted",
            "deleted_at"
        }
