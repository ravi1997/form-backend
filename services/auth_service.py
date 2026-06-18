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
    get_jti,
)
from config.settings import settings
from logger.unified_logger import app_logger, error_logger, audit_logger, get_logger
from services.base import BaseService
from models.user import User
from models.auth import TokenBlocklist
from models.system import SystemSettings
from schemas.auth import TokenResponse
from schemas.user import UserOut
from services.redis_service import redis_service
from utils.exceptions import UnauthorizedError

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
        app_logger.info("Entering _get_auth_params")
        try:
            db_settings = SystemSettings.get_or_create_default()
            app_logger.info("Successfully completed _get_auth_params")
            return {
                "access_mins": db_settings.jwt_access_token_expires_minutes,
                "refresh_days": db_settings.jwt_refresh_token_expires_days,
            }
        except Exception as e:
            app_logger.warning(f"Using settings fallback: {e}")
            return {
                "access_mins": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
                "refresh_days": settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
            }

    def generate_tokens(self, user: User) -> TokenResponse:
        """
        Generates access and refresh tokens for a user using flask-jwt-extended.
        Keeps the documented claim contract for access tokens.
        """
        app_logger.info(f"Entering generate_tokens for User ID {user.id}")
        try:
            params = self._get_auth_params()

            access_expires = timedelta(minutes=params["access_mins"])
            refresh_expires = timedelta(days=params["refresh_days"])

            user_roles = list(getattr(user, "roles", []) or [])
            if getattr(user, "is_admin", False) and "admin" not in user_roles:
                user_roles.append("admin")
            if getattr(user, "is_admin", False) and "superadmin" in user_roles:
                system_role = "super_admin"
            elif getattr(user, "is_admin", False):
                system_role = "admin"
            else:
                system_role = "user"

            org_claims: list[dict[str, Any]] = []
            organization_id = getattr(user, "organization_id", None)
            if organization_id:
                role = getattr(user, "role", None) or getattr(user, "org_role", None)
                org_claims.append(
                    {
                        "org_id": str(organization_id),
                        "role": role or (user_roles[0] if user_roles else "org_viewer"),
                        "status": "active",
                    }
                )

            access_token = create_access_token(
                identity=str(user.id),
                additional_claims={
                    "roles": user_roles,
                    "role": user_roles[0] if user_roles else system_role,
                    "org_id": str(organization_id) if organization_id else None,
                    "system_role": system_role,
                    "orgs": org_claims,
                    "email": getattr(user, "email", None),
                },
                expires_delta=access_expires,
            )

            refresh_token = create_refresh_token(
                identity=str(user.id), expires_delta=refresh_expires
            )

            audit_logger.info(f"AUDIT: Generated tokens for User ID {user.id}")
            app_logger.info(
                f"Successfully completed generate_tokens for User ID {user.id}"
            )
            return TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=params["access_mins"] * 60,
            )
        except Exception as e:
            error_logger.error(
                f"Error in generate_tokens for User ID {user.id}: {str(e)}",
                exc_info=True,
            )
            raise

    def create_token(
        self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Backward-compatible helper used by tests and internal callers.
        """
        app_logger.info(f"Entering create_token for identity: {data.get('sub')}")
        try:
            identity = data.get("sub")
            if not identity:
                raise UnauthorizedError("Missing subject for token creation")
            claims = {k: v for k, v in data.items() if k != "sub"}
            token = create_access_token(
                identity=identity, additional_claims=claims, expires_delta=expires_delta
            )
            app_logger.info(
                f"Successfully completed create_token for identity: {identity}"
            )
            return token
        except Exception as e:
            if not isinstance(e, UnauthorizedError):
                error_logger.error(f"Error in create_token: {str(e)}", exc_info=True)
            raise

    def validate_token(self, token: str):
        app_logger.info("Entering validate_token")
        try:
            payload = decode_token(token)
            if self.check_global_revocation(
                payload["sub"], payload["iat"]
            ) or self.is_token_revoked(payload["jti"]):
                app_logger.warning(
                    f"Token validation failed (revoked) for JTI: {payload.get('jti')}"
                )
                raise UnauthorizedError("Token has been revoked")

            from schemas.auth import TokenPayload

            app_logger.info("Successfully completed validate_token")
            return TokenPayload.model_validate(payload)
        except Exception as e:
            if e.__class__.__name__ == "ExpiredSignatureError":
                raise UnauthorizedError("Token has expired")
            if not isinstance(e, UnauthorizedError):
                error_logger.error(f"Error in validate_token: {str(e)}", exc_info=True)
            raise

    def authenticate_user(self, identifier: str, password: str) -> User:
        app_logger.info(f"Entering authenticate_user for identifier: {identifier}")
        try:
            user = User.authenticate(identifier, password)
            if not user:
                app_logger.warning(f"Authentication failed for {identifier}")
                raise UnauthorizedError("Invalid credentials")

            audit_logger.info(f"AUDIT: User {user.id} authenticated")
            app_logger.info(
                f"Successfully completed authenticate_user for {identifier}"
            )
            return user
        except Exception as e:
            if not isinstance(e, UnauthorizedError):
                error_logger.error(
                    f"Error in authenticate_user: {str(e)}", exc_info=True
                )
            raise

    def _resolve_user_from_token(self, token: str) -> User:
        """
        Resolve a user from a verification or invite token.

        Supports either a JWT token issued by the system or a token that was
        embedded in the invite/verification link and later stored as a claim.
        """
        app_logger.info("Entering _resolve_user_from_token")
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
            email = payload.get("email") or payload.get("invitee_email")

            user = None
            if user_id:
                user = User.objects(id=user_id).first()
            if not user and email:
                user = User.objects(email=email).first()

            if not user:
                raise UnauthorizedError("Invalid or expired token")

            app_logger.info(
                f"Successfully completed _resolve_user_from_token for user id={user.id}"
            )
            return user
        except UnauthorizedError:
            raise
        except Exception as e:
            error_logger.error(
                f"Error resolving user from token: {str(e)}", exc_info=True
            )
            raise UnauthorizedError("Invalid or expired token")

    def verify_email(self, token: str) -> User:
        """
        Marks a user's email as verified using a verification token.
        """
        app_logger.info("Entering verify_email")
        user = self._resolve_user_from_token(token)
        if not getattr(user, "email", None):
            raise UnauthorizedError("User does not have an email address")

        if not user.is_email_verified:
            user.is_email_verified = True
            user.save()
            audit_logger.info(f"AUDIT: Email verified for user id={user.id}")

        app_logger.info(f"Successfully completed verify_email for user id={user.id}")
        return user

    def accept_invite(self, token: str, password: Optional[str] = None) -> User:
        """
        Accepts an invite token, verifies the invited user, and optionally sets a password.
        """
        app_logger.info("Entering accept_invite")
        user = self._resolve_user_from_token(token)

        if password:
            user.set_password(password)

        user.is_active = True
        user.is_email_verified = True
        user.save()
        audit_logger.info(f"AUDIT: Invite accepted for user id={user.id}")
        app_logger.info(f"Successfully completed accept_invite for user id={user.id}")
        return user

    def revoke_token(self, token: str) -> None:
        """
        Revokes a JWT token by its JTI.
        Calculates TTL based on the token's 'exp' claim.
        """
        app_logger.info("Entering revoke_token")
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
                audit_logger.info(f"AUDIT: Token revoked: {jti}")

            app_logger.info(f"Successfully completed revoke_token for JTI: {jti}")

        except Exception as e:
            error_logger.error(f"Failed to revoke token: {e}", exc_info=True)
            raise

    def revoke_token_payload(self, payload: Dict[str, Any]) -> None:
        """
        Revoke a token when its decoded JWT payload is already available.
        """
        app_logger.info(f"Entering revoke_token_payload for JTI: {payload.get('jti')}")
        try:
            from datetime import datetime, timezone

            jti = payload["jti"]
            exp_timestamp = payload["exp"]
            expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
            ttl = int(exp_timestamp - datetime.now(timezone.utc).timestamp())
            if ttl > 0:
                redis_service.cache.set(f"revoked_token:{jti}", "1", ttl=ttl)
            if not TokenBlocklist.objects(jti=jti).first():
                TokenBlocklist(jti=jti, expires_at=expires_at).save()
                audit_logger.info(f"AUDIT: Token payload revoked: {jti}")

            app_logger.info(
                f"Successfully completed revoke_token_payload for JTI: {jti}"
            )
        except Exception as e:
            error_logger.error(
                f"Failed to revoke decoded token payload: {e}", exc_info=True
            )
            raise

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
        app_logger.info(f"Entering revoke_all_user_sessions for User ID {user_id}")
        try:
            user = User.objects(id=user_id).first()
            if user:
                from datetime import datetime, timezone

                user.last_token_revocation_at = datetime.now(timezone.utc)
                user.save()
                audit_logger.info(f"AUDIT: All sessions revoked for user: {user_id}")
                app_logger.info(
                    f"Successfully completed revoke_all_user_sessions for User ID {user_id}"
                )
        except Exception as e:
            error_logger.error(
                f"Failed to revoke all sessions for User ID {user_id}: {e}",
                exc_info=True,
            )

    def check_global_revocation(self, user_id: str, iat_timestamp: int) -> bool:
        """
        Checks if a token was issued before the user's last global revocation event.
        """
        try:
            user = User.objects(id=user_id).only("last_token_revocation_at").first()
        except Exception as exc:
            if exc.__class__.__name__ == "ConnectionFailure":
                app_logger.warning(
                    "Skipping global token revocation check: database unavailable"
                )
                return False
            raise
        if not user or not user.last_token_revocation_at:
            return False

        from datetime import datetime, timezone

        token_iat = datetime.fromtimestamp(iat_timestamp, tz=timezone.utc)
        return token_iat < user.last_token_revocation_at
