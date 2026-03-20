"""
services/user_service.py
Handles user authentication, OTP generation/validation, and profile management.
"""

import secrets
from datetime import datetime, timezone
from logger import get_logger, audit_logger
from services.base import BaseService
from utils.exceptions import UnauthorizedError
from models import User
from mongoengine import Q
from schemas.user import UserSchema, UserCreateSchema, UserUpdateSchema
from services.redis_service import redis_service

logger = get_logger(__name__)


class UserService(BaseService):
    def __init__(self):
        super().__init__(model=User, schema=UserSchema)

    def create(self, create_schema: UserCreateSchema) -> UserSchema:
        """
        Custom create method to handle password hashing specifically for User model.
        """
        data = create_schema.model_dump(exclude_unset=True)
        password = data.pop("password")
        
        # Ensure organization_id is present if required by business logic
        user_doc = User(**data)
        user_doc.set_password(password)
        user_doc.save()
        
        logger.info(f"Created User with ID {user_doc.id} in org {user_doc.organization_id}")
        return self._to_schema(user_doc)

    def update(self, doc_id: str, update_schema: UserUpdateSchema, organization_id: str = None) -> UserSchema:
        """
        Custom update method to handle password updates with org scoping.
        """
        data = update_schema.model_dump(exclude_unset=True)
        password = data.pop("password", None)
        
        filters = {'id': doc_id}
        if organization_id:
            filters['organization_id'] = organization_id
            
        user_doc = User.objects(**filters).get()
        
        # Update other fields
        for field, value in data.items():
            setattr(user_doc, field, value)
            
        if password:
            user_doc.set_password(password)
            
        user_doc.save()
        return self._to_schema(user_doc)

    def authenticate_employee(self, identifier: str, password: str) -> UserSchema:
        """
        Authentication with security hardening.
        Account locking, failed attempt tracking, and password expiration
        are all handled by the User model methods.
        """
        audit_logger.info(f"Authentication attempt for identifier: {identifier}")
        user_doc = User.authenticate(identifier, password)

        if not user_doc:
            # User.authenticate already increments failed attempts / locks if needed
            logger.warning(f"Authentication failure for identifier: {identifier}")
            raise UnauthorizedError("Invalid credentials or account is locked")

        return self._to_schema(user_doc)

    def request_otp(self, identifier: str) -> bool:
        """
        Generates and stores a cryptographically-secure 6-digit OTP for a user.
        Returns True regardless of whether the user exists to prevent
        user-enumeration attacks.
        """
        user = User.objects(
            Q(is_deleted=False) & 
            Q(is_active=True) & (
                Q(mobile=identifier) | 
                Q(username=identifier) | 
                Q(email=identifier)
            )
        ).first()

        # Always return True to prevent user enumeration attacks
        if not user:
            return True

        if user.is_locked():
            raise UnauthorizedError("Account is locked. Please contact support.")

        # Strict rate limiting on OTP resends
        if user.otp_resend_count >= 5:
            user.lock_account(duration_hours=1)
            raise UnauthorizedError("Too many OTP requests. Account locked for 1 hour.")

        # FIX: Use secrets module (cryptographically secure) for OTP generation
        otp = str(secrets.randbelow(900000) + 100000)  # Always exactly 6 digits
        
        # FIX: Move OTP storage to Redis with 5-minute TTL
        otp_key = f"otp:{user.id}"
        redis_service.cache.set(otp_key, otp, ttl=300)
        
        user.otp_resend_count += 1
        user.save()

        audit_logger.info(f"OTP generated for user {user.id}")
        return True

    def verify_otp_login(self, identifier: str, otp_code: str) -> UserSchema:
        """
        Validates the OTP, clears it after successful use to prevent replay
        attacks, and resets failed-login counters.
        """
        user = User.objects(
            Q(is_deleted=False) & 
            Q(is_active=True) & (
                Q(mobile=identifier) | 
                Q(username=identifier) | 
                Q(email=identifier)
            )
        ).first()

        if not user or user.is_locked():
            raise UnauthorizedError("Invalid request or account locked")

        otp_key = f"otp:{user.id}"
        cached_otp = redis_service.cache.get(otp_key)

        if not cached_otp or cached_otp != otp_code:
            user.increment_failed_logins(max_attempts=3)  # Stricter for OTP
            raise UnauthorizedError("Invalid or expired OTP code")

        # FIX: Clear OTP from Redis immediately after use to prevent replay attacks
        redis_service.cache.delete(otp_key)
        
        user.otp_resend_count = 0
        user.reset_failed_logins()
        user.last_login = datetime.now(timezone.utc)
        user.save()

        audit_logger.info(f"User {user.id} authenticated via OTP")
        return self._to_schema(user)
