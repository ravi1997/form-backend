"""
services/auth_service.py
Purely responsible for JWT Token lifecycle management using flask-jwt-extended.
Integrates with Redis/MongoDB for revocation.
"""

from datetime import timedelta
from typing import Dict, Any, Optional

from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_jti
)
from config.settings import settings
from logger import get_logger, audit_logger
from services.base import BaseService
from models.User import User
from models.TokenBlocklist import TokenBlocklist
from models.SystemSettings import SystemSettings
from schemas.auth import TokenResponse
from services.redis_service import redis_service

logger = get_logger(__name__)


class AuthService(BaseService):
    def __init__(self):
        # We don't really have a single model for this service, but BaseService requires one
        super().__init__(model=TokenBlocklist, schema=None)

    def _get_auth_params(self) -> Dict[str, Any]:
        """
        Fetches auth parameters from SystemSettings in DB, 
        falling back to config/settings.py.
        """
        try:
            db_settings = SystemSettings.get_or_create_default()
            return {
                "access_mins": db_settings.jwt_access_token_expires_minutes,
                "refresh_days": db_settings.jwt_refresh_token_expires_days
            }
        except Exception as e:
            logger.warning(f"Using settings fallback: {e}")
            return {
                "access_mins": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
                "refresh_days": settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
            }

    def generate_tokens(self, user: User) -> TokenResponse:
        """
        Generates access and refresh tokens for a user using flask-jwt-extended.
        Includes roles in the access token.
        """
        params = self._get_auth_params()

        access_expires = timedelta(minutes=params["access_mins"])
        refresh_expires = timedelta(days=params["refresh_days"])

        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={"roles": getattr(user, "roles", [])},
            expires_delta=access_expires
        )

        refresh_token = create_refresh_token(
            identity=str(user.id),
            expires_delta=refresh_expires
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=params["access_mins"] * 60,
        )

    def revoke_token(self, token: str) -> None:
        """
        Revokes a JWT token by its JTI. 
        Calculates TTL based on the token's 'exp' claim.
        """
        try:
            decoded = decode_token(token)
            jti = decoded["jti"]
            exp_timestamp = decoded["exp"]
            
            # Persist revocation to both Redis (fast) and MongoDB (audit)
            from datetime import datetime, timezone
            expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
            
            # Add to Redis
            ttl = int(exp_timestamp - datetime.now(timezone.utc).timestamp())
            if ttl > 0:
                redis_service.cache.set(f"revoked_token:{jti}", "1", ttl=ttl)

            # Add to MongoDB
            if not TokenBlocklist.objects(jti=jti).first():
                TokenBlocklist(jti=jti, expires_at=expires_at).save()
                audit_logger.info(f"Token revoked: {jti}")
                
        except Exception as e:
            logger.error(f"Failed to revoke token: {e}")

    def is_token_revoked(self, jti: str) -> bool:
        """Checks if a JTI exists in the blocklist (Redis first, then DB)."""
        # 1. Check Redis
        if redis_service.cache.get(f"revoked_token:{jti}"):
            return True

        # 2. Fallback to DB
        return TokenBlocklist.objects(jti=jti).first() is not None

    def revoke_all_user_sessions(self, user_id: str) -> None:
        """
        Sets the last_token_revocation_at timestamp for a user, 
        effectively invalidating all existing tokens.
        """
        user = User.objects(id=user_id).first()
        if user:
            from datetime import datetime, timezone
            user.last_token_revocation_at = datetime.now(timezone.utc)
            user.save()
            audit_logger.info(f"All sessions revoked for user: {user_id}")

    def check_global_revocation(self, user_id: str, iat_timestamp: int) -> bool:
        """
        Checks if a token was issued before the user's last global revocation event.
        """
        user = User.objects(id=user_id).only("last_token_revocation_at").first()
        if not user or not user.last_token_revocation_at:
            return False
        
        from datetime import datetime, timezone
        token_iat = datetime.fromtimestamp(iat_timestamp, tz=timezone.utc)
        return token_iat < user.last_token_revocation_at
