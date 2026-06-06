"""
services/oidc_service.py
Service handling external OIDC/OAuth2 login flows, claims verification, and user mappings.
"""

import base64
import datetime
import hashlib
import hmac
import json
import uuid
from urllib.parse import quote_plus

from config.settings import settings
from logger.unified_logger import app_logger, audit_logger
from models.OidcUserMapping import OidcUserMapping
from models.User import User
from services.base import BaseService
from utils.exceptions import ValidationError


class OidcService(BaseService):
    def __init__(self):
        super().__init__(model=OidcUserMapping, schema=None)

    def _canonical_claim_payload(self, claims: dict) -> str:
        normalized = {
            key: value
            for key, value in claims.items()
            if key not in {"claims_signature", "signature", "signature_kid"}
        }
        return json.dumps(normalized, sort_keys=True, separators=(",", ":"))

    def _verify_claim_signature(self, claims: dict, provider: str) -> None:
        signature = claims.get("claims_signature") or claims.get("signature")
        if not signature:
            return

        secret = getattr(settings, "OIDC_SHARED_SECRET", None) or settings.JWT_SECRET_KEY
        digest = hmac.new(
            secret.encode("utf-8"),
            self._canonical_claim_payload(claims).encode("utf-8"),
            hashlib.sha256,
        ).digest()
        expected_signature = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

        if not hmac.compare_digest(expected_signature, signature):
            raise ValidationError(
                f"Invalid OIDC claim signature for provider {provider}."
            )

    def _extract_email_domain(self, email: str) -> str:
        if "@" not in email:
            raise ValidationError("Invalid OIDC email claim: missing domain.")
        return email.rsplit("@", 1)[-1].lower()

    def _resolve_trusted_domain(self, organization_id: str, provider: str) -> str | None:
        mapping = (
            OidcUserMapping.objects(organization_id=organization_id, provider=provider)
            .order_by("-id")
            .first()
        )
        if not mapping or not getattr(mapping, "email", None):
            return None
        return self._extract_email_domain(mapping.email)

    def _validate_domain_binding(
        self, organization_id: str, provider: str, claims: dict, email: str
    ) -> None:
        email_domain = self._extract_email_domain(email)
        hinted_domain = (
            claims.get("hd")
            or claims.get("email_domain")
            or claims.get("domain")
            or claims.get("tenant_domain")
        )
        if hinted_domain and hinted_domain.lower() != email_domain:
            raise ValidationError("OIDC domain hint does not match the email domain.")

        claimed_org = claims.get("organization_id") or claims.get("org_id")
        if claimed_org and claimed_org != organization_id:
            raise ValidationError(
                "OIDC tenant claim does not match the target organization."
            )

        trusted_domain = self._resolve_trusted_domain(organization_id, provider)
        if trusted_domain and trusted_domain != email_domain:
            raise ValidationError(
                f"OIDC domain mismatch for organization {organization_id}: "
                f"expected {trusted_domain}, received {email_domain}."
            )

    def get_oidc_auth_url(self, organization_id: str, provider: str) -> str:
        """
        Generates the target OIDC authorization URL for the client redirection.
        """
        client_id = f"ridp-{organization_id}-client"
        redirect_uri = "http://localhost:8051/mahasangraha/api/v1/auth/oidc/callback"
        state = f"{organization_id}:{provider}:{uuid.uuid4().hex}"

        auth_url = (
            f"https://auth.{provider}.com/oauth/authorize?client_id={quote_plus(client_id)}"
            f"&response_type=code&scope=openid+email+profile&redirect_uri={quote_plus(redirect_uri)}"
            f"&state={quote_plus(state)}"
        )

        app_logger.info(
            f"Generated OIDC Auth URL for org {organization_id}, provider {provider}"
        )
        return auth_url

    def handle_oidc_callback(self, organization_id: str, provider: str, code: str, mock_claims: dict = None) -> User:
        """
        Exchanges code for claims, resolves the OIDC user mapping,
        and provisions a new user under the tenant context if it doesn't exist.
        """
        if not code:
            raise ValidationError("OIDC authorization code is missing.")

        if mock_claims is None:
            mock_claims = {
                "sub": f"ext-{provider}-{hash(code)}",
                "email": f"user-{hash(code)}@tenant.com",
                "preferred_username": f"user_{hash(code)}",
                "roles": ["user"],
            }

        self._verify_claim_signature(mock_claims, provider)

        subject_id = mock_claims.get("sub")
        email = mock_claims.get("email")
        username = mock_claims.get("preferred_username") or email
        roles = mock_claims.get("roles") or ["user"]

        if not subject_id or not email:
            raise ValidationError("Invalid OIDC claim data: sub and email are required.")

        self._validate_domain_binding(organization_id, provider, mock_claims, email)

        mapping = OidcUserMapping.objects(provider=provider, subject_id=subject_id).first()

        if mapping:
            user = User.objects(id=mapping.user_id).first()
            if not user:
                user = self._provision_user(organization_id, username, email, roles)
                mapping.user_id = user.id
                mapping.claims = mock_claims
                mapping.email = email
                mapping.organization_id = organization_id
                mapping.save()
        else:
            user = User.objects(email=email).first()
            if not user:
                user = self._provision_user(organization_id, username, email, roles)
            elif getattr(user, "organization_id", organization_id) != organization_id:
                raise ValidationError(
                    "OIDC email is already bound to a different organization."
                )

            mapping = OidcUserMapping(
                organization_id=organization_id,
                provider=provider,
                subject_id=subject_id,
                user_id=user.id,
                email=email,
                claims=mock_claims,
            )
            mapping.save()

        user.last_login = datetime.datetime.now(datetime.timezone.utc)
        user.save()

        audit_logger.info(
            f"AUDIT: OIDC login completed for user {user.id} ({email}) via provider {provider}"
        )
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
            is_email_verified=True,
        )
        user.save()
        app_logger.info(f"Provisioned new user {user.id} from OIDC details")
        return user
