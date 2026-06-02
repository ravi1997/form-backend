"""
services/oidc_service.py
Service handling external OIDC/OAuth2 login flows, claims verification, and user mappings.
"""

import uuid
from logger.unified_logger import app_logger, audit_logger
from services.base import BaseService
from models.OidcUserMapping import OidcUserMapping
from models.User import User
from utils.exceptions import ValidationError

class OidcService(BaseService):
    def __init__(self):
        super().__init__(model=OidcUserMapping, schema=None)

    def get_oidc_auth_url(self, organization_id: str, provider: str) -> str:
        """
        Generates the target OIDC authorization URL for the client redirection.
        """
        client_id = f"ridp-{organization_id}-client"
        redirect_uri = "http://localhost:8051/mahasangraha/api/v1/auth/oidc/callback"
        state = f"{organization_id}:{provider}:{uuid.uuid4().hex}"
        
        # Simulated OIDC auth endpoint url
        auth_url = f"https://auth.{provider}.com/oauth/authorize?client_id={client_id}&response_type=code&scope=openid+email+profile&redirect_uri={redirect_uri}&state={state}"
        
        app_logger.info(f"Generated OIDC Auth URL for org {organization_id}, provider {provider}")
        return auth_url

    def handle_oidc_callback(self, organization_id: str, provider: str, code: str, mock_claims: dict = None) -> User:
        """
        Exchanges code for claims, resolves the OIDC user mapping,
        and provisions a new user under the tenant context if it doesn't exist.
        """
        if not code:
            raise ValidationError("OIDC authorization code is missing.")

        # Simulate claim payload if not provided
        if mock_claims is None:
            mock_claims = {
                "sub": f"ext-{provider}-{hash(code)}",
                "email": f"user-{hash(code)}@tenant.com",
                "preferred_username": f"user_{hash(code)}",
                "roles": ["user"],
            }

        subject_id = mock_claims.get("sub")
        email = mock_claims.get("email")
        username = mock_claims.get("preferred_username") or email
        roles = mock_claims.get("roles") or ["user"]

        if not subject_id or not email:
            raise ValidationError("Invalid OIDC claim data: sub and email are required.")

        # 1. Resolve user mapping
        mapping = OidcUserMapping.objects(
            provider=provider,
            subject_id=subject_id
        ).first()

        if mapping:
            # Check user exists
            user = User.objects(id=mapping.user_id).first()
            if not user:
                # User deleted but mapping remained, re-provision
                user = self._provision_user(organization_id, username, email, roles)
                mapping.user_id = user.id
                mapping.claims = mock_claims
                mapping.save()
        else:
            # Check if user already exists with this email in the system
            user = User.objects(email=email).first()
            if not user:
                # Provision new user
                user = self._provision_user(organization_id, username, email, roles)

            # Create mapping
            mapping = OidcUserMapping(
                organization_id=organization_id,
                provider=provider,
                subject_id=subject_id,
                user_id=user.id,
                email=email,
                claims=mock_claims
            )
            mapping.save()

        # Update last login info
        import datetime
        user.last_login = datetime.datetime.now(datetime.timezone.utc)
        user.save()

        audit_logger.info(f"AUDIT: OIDC login completed for user {user.id} ({email}) via provider {provider}")
        return user

    def _provision_user(self, organization_id: str, username: str, email: str, roles: list) -> User:
        """Provisions a new tenant user dynamically from OIDC claims."""
        user = User(
            organization_id=organization_id,
            username=username,
            email=email,
            roles=roles,
            user_type="general",
            is_active=True,
            is_email_verified=True
        )
        user.save()
        app_logger.info(f"Provisioned new user {user.id} from OIDC details")
        return user
