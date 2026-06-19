"""
services/oauth_service.py
OAuth 2.0 service for public API access.
"""

import hashlib
import secrets
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse

from logger.unified_logger import app_logger, error_logger, audit_logger
from services.base import BaseService
from models.oauth import (
    OAuthClient, OAuthAuthorizationCode, OAuthAccessToken, 
    OAuthRefreshToken, EnhancedApiKey, ApiKeyUsageLog,
    PublicApiEndpoint, PublicApiDocumentation
)
from utils.exceptions import ValidationError, NotFoundError, AuthenticationError


class OAuthService(BaseService):
    """OAuth 2.0 service for managing public API access."""

    def __init__(self):
        super().__init__(model=OAuthClient, schema=None)

    def create_oauth_client(self, **kwargs) -> OAuthClient:
        """Create a new OAuth 2.0 client."""
        required_fields = ['client_name', 'organization_id', 'user_id', 'redirect_uris']
        for field in required_fields:
            if not kwargs.get(field):
                raise ValidationError(f"{field} is required")

        # Validate redirect URIs
        for uri in kwargs['redirect_uris']:
            self._validate_redirect_uri(uri)

        # Generate client credentials
        client_id = self._generate_client_id()
        client_secret = self._generate_client_secret()

        client = OAuthClient(
            client_id=client_id,
            client_secret=self._hash_secret(client_secret),
            client_name=kwargs['client_name'],
            client_type=kwargs.get('client_type', 'confidential'),
            redirect_uris=kwargs['redirect_uris'],
            scopes=kwargs.get('scopes', ['read']),
            grant_types=kwargs.get('grant_types', ['authorization_code']),
            response_types=kwargs.get('response_types', ['code']),
            organization_id=kwargs['organization_id'],
            user_id=kwargs['user_id'],
            is_active=kwargs.get('is_active', True),
            is_trusted=kwargs.get('is_trusted', False),
            website=kwargs.get('website'),
            description=kwargs.get('description'),
            logo_url=kwargs.get('logo_url'),
            terms_of_service_url=kwargs.get('terms_of_service_url'),
            privacy_policy_url=kwargs.get('privacy_policy_url'),
            contact_email=kwargs.get('contact_email'),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        client.save()
        
        audit_logger.info(f"OAuth client created: {client.client_name} ({client.client_id})")
        
        # Return client with plaintext secret (only shown once)
        client_data = client.to_dict()
        client_data['client_secret'] = client_secret
        return client_data

    def get_oauth_client(self, client_id: str) -> OAuthClient:
        """Get OAuth client by client ID."""
        client = OAuthClient.objects(client_id=client_id, is_deleted=False).first()
        if not client:
            raise NotFoundError(f"OAuth client not found: {client_id}")
        return client

    def authenticate_client(self, client_id: str, client_secret: str) -> OAuthClient:
        """Authenticate OAuth client."""
        client = self.get_oauth_client(client_id)
        
        if not self._verify_secret(client_secret, client.client_secret):
            raise AuthenticationError("Invalid client credentials")
        
        if not client.is_active:
            raise AuthenticationError("Client is not active")
        
        return client

    def create_authorization_code(self, client_id: str, user_id: str, **kwargs) -> OAuthAuthorizationCode:
        """Create OAuth authorization code."""
        # Validate client
        client = self.get_oauth_client(client_id)
        
        # Validate redirect URI
        redirect_uri = kwargs.get('redirect_uri')
        if redirect_uri and redirect_uri not in client.redirect_uris:
            raise ValidationError("Invalid redirect URI")

        # Generate authorization code
        code = self._generate_authorization_code()
        
        auth_code = OAuthAuthorizationCode(
            code=code,
            client_id=client_id,
            user_id=user_id,
            redirect_uri=redirect_uri,
            scopes=kwargs.get('scopes', client.scopes),
            state=kwargs.get('state'),
            code_challenge=kwargs.get('code_challenge'),
            code_challenge_method=kwargs.get('code_challenge_method'),
            nonce=kwargs.get('nonce'),
            expires_at=datetime.utcnow() + timedelta(minutes=10),  # 10 minutes expiry
            created_at=datetime.utcnow()
        )
        auth_code.save()
        
        return auth_code

    def get_authorization_code(self, code: str) -> OAuthAuthorizationCode:
        """Get authorization code."""
        auth_code = OAuthAuthorizationCode.objects(
            code=code, 
            expires_at__gt=datetime.utcnow()
        ).first()
        if not auth_code:
            raise ValidationError("Invalid or expired authorization code")
        return auth_code

    def exchange_code_for_token(self, code: str, client_id: str, client_secret: str, **kwargs) -> Dict[str, Any]:
        """Exchange authorization code for access token."""
        # Get and validate authorization code
        auth_code = self.get_authorization_code(code)
        
        # Validate client
        client = self.authenticate_client(client_id, client_secret)
        
        # Validate client matches
        if auth_code.client_id != client_id:
            raise ValidationError("Authorization code does not match client")
        
        # Validate PKCE if present
        if auth_code.code_challenge:
            code_verifier = kwargs.get('code_verifier')
            if not code_verifier:
                raise ValidationError("Code verifier required for PKCE")
            
            if not self._verify_pkce_challenge(code_verifier, auth_code):
                raise ValidationError("Invalid PKCE code verifier")
        
        # Delete the authorization code (single use)
        auth_code.delete()
        
        # Create access and refresh tokens
        access_token = self._generate_access_token()
        refresh_token = self._generate_refresh_token()
        
        # Get user's organization
        user_org = self._get_user_organization(auth_code.user_id)
        
        # Create access token record
        access_token_record = OAuthAccessToken(
            access_token=self._hash_token(access_token),
            refresh_token=self._hash_token(refresh_token),
            token_type="Bearer",
            expires_in=3600,  # 1 hour
            scopes=auth_code.scopes,
            client_id=client_id,
            user_id=auth_code.user_id,
            organization_id=user_org,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        access_token_record.save()
        
        # Create refresh token record
        refresh_token_record = OAuthRefreshToken(
            refresh_token=self._hash_token(refresh_token),
            access_token=access_token_record.access_token,
            client_id=client_id,
            user_id=auth_code.user_id,
            organization_id=user_org,
            scopes=auth_code.scopes,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=30)  # 30 days
        )
        refresh_token_record.save()
        
        audit_logger.info(f"OAuth token issued for client {client_id}")
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": " ".join(auth_code.scopes)
        }

    def refresh_access_token(self, refresh_token: str, client_id: str, client_secret: str) -> Dict[str, Any]:
        """Refresh access token using refresh token."""
        # Validate client
        client = self.authenticate_client(client_id, client_secret)
        
        # Get refresh token
        refresh_token_record = OAuthRefreshToken.objects(
            refresh_token=self._hash_token(refresh_token),
            is_revoked=False,
            expires_at__gt=datetime.utcnow()
        ).first()
        if not refresh_token_record:
            raise AuthenticationError("Invalid or expired refresh token")
        
        # Validate client matches
        if refresh_token_record.client_id != client_id:
            raise AuthenticationError("Refresh token does not match client")
        
        # Revoke old refresh token
        refresh_token_record.is_revoked = True
        refresh_token_record.save()
        
        # Generate new tokens
        new_access_token = self._generate_access_token()
        new_refresh_token = self._generate_refresh_token()
        
        # Create new access token
        access_token_record = OAuthAccessToken(
            access_token=self._hash_token(new_access_token),
            refresh_token=self._hash_token(new_refresh_token),
            token_type="Bearer",
            expires_in=3600,
            scopes=refresh_token_record.scopes,
            client_id=client_id,
            user_id=refresh_token_record.user_id,
            organization_id=refresh_token_record.organization_id,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        access_token_record.save()
        
        # Create new refresh token
        new_refresh_token_record = OAuthRefreshToken(
            refresh_token=self._hash_token(new_refresh_token),
            access_token=access_token_record.access_token,
            client_id=client_id,
            user_id=refresh_token_record.user_id,
            organization_id=refresh_token_record.organization_id,
            scopes=refresh_token_record.scopes,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
        new_refresh_token_record.save()
        
        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": " ".join(refresh_token_record.scopes)
        }

    def revoke_token(self, token: str, token_type: str = "access_token") -> bool:
        """Revoke OAuth token."""
        if token_type == "access_token":
            token_record = OAuthAccessToken.objects(
                access_token=self._hash_token(token),
                is_revoked=False
            ).first()
        elif token_type == "refresh_token":
            token_record = OAuthRefreshToken.objects(
                refresh_token=self._hash_token(token),
                is_revoked=False
            ).first()
        else:
            raise ValidationError("Invalid token type")
        
        if not token_record:
            return False
        
        token_record.is_revoked = True
        token_record.save()
        
        audit_logger.info(f"OAuth {token_type} revoked")
        return True

    def validate_access_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Validate access token and return token info."""
        token_record = OAuthAccessToken.objects(
            access_token=self._hash_token(access_token),
            is_revoked=False,
            expires_at__gt=datetime.utcnow()
        ).first()
        
        if not token_record:
            return None
        
        # Update last used timestamp
        token_record.last_used_at = datetime.utcnow()
        token_record.save()
        
        return {
            "client_id": token_record.client_id,
            "user_id": str(token_record.user_id),
            "organization_id": token_record.organization_id,
            "scopes": token_record.scopes,
            "expires_at": token_record.expires_at.isoformat()
        }

    def create_enhanced_api_key(self, **kwargs) -> Dict[str, Any]:
        """Create an enhanced API key with scopes and rate limits."""
        required_fields = ['name', 'organization_id', 'user_id']
        for field in required_fields:
            if not kwargs.get(field):
                raise ValidationError(f"{field} is required")

        # Generate API key
        raw_key = self._generate_api_key()
        key_prefix = raw_key[:8]
        key_hash = self._hash_secret(raw_key)
        
        # Create API key record
        api_key = EnhancedApiKey(
            key_prefix=key_prefix,
            key_hash=key_hash,
            name=kwargs['name'],
            description=kwargs.get('description'),
            organization_id=kwargs['organization_id'],
            user_id=kwargs['user_id'],
            scopes=kwargs.get('scopes', []),
            rate_limit=kwargs.get('rate_limit'),
            is_active=kwargs.get('is_active', True),
            expires_at=kwargs.get('expires_at'),
            ip_whitelist=kwargs.get('ip_whitelist', []),
            allowed_origins=kwargs.get('allowed_origins', []),
            webhooks=kwargs.get('webhooks', []),
            created_by=kwargs['user_id'],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        api_key.save()
        
        audit_logger.info(f"API key created: {api_key.name} ({api_key.key_prefix})")
        
        # Return API key with plaintext secret (only shown once)
        api_key_data = api_key.to_dict()
        api_key_data['api_key'] = raw_key
        return api_key_data

    def get_api_key(self, key_prefix: str, organization_id: str) -> EnhancedApiKey:
        """Get API key by prefix."""
        api_key = EnhancedApiKey.objects(
            key_prefix=key_prefix,
            organization_id=organization_id,
            is_deleted=False,
            is_active=True
        ).first()
        if not api_key:
            raise NotFoundError(f"API key not found: {key_prefix}")
        return api_key

    def authenticate_api_key(self, api_key: str) -> Optional[EnhancedApiKey]:
        """Authenticate API key."""
        key_prefix = api_key[:8]
        key_hash = self._hash_secret(api_key)
        
        api_key_record = EnhancedApiKey.objects(
            key_prefix=key_prefix,
            key_hash=key_hash,
            is_deleted=False,
            is_active=True
        ).first()
        
        if not api_key_record:
            return None
        
        # Check expiry
        if api_key_record.expires_at and api_key_record.expires_at < datetime.utcnow():
            return None
        
        return api_key_record

    def log_api_key_usage(self, api_key: EnhancedApiKey, **kwargs) -> ApiKeyUsageLog:
        """Log API key usage."""
        usage_log = ApiKeyUsageLog(
            api_key_id=api_key,
            organization_id=api_key.organization_id,
            user_id=api_key.user_id,
            endpoint=kwargs.get('endpoint'),
            method=kwargs.get('method'),
            status_code=kwargs.get('status_code'),
            response_time_ms=kwargs.get('response_time_ms'),
            request_size_bytes=kwargs.get('request_size_bytes'),
            response_size_bytes=kwargs.get('response_size_bytes'),
            ip_address=kwargs.get('ip_address'),
            user_agent=kwargs.get('user_agent'),
            timestamp=datetime.utcnow(),
            rate_limited=kwargs.get('rate_limited', False),
            error_message=kwargs.get('error_message')
        )
        usage_log.save()
        
        # Update usage counts
        api_key.usage_count += 1
        api_key.usage_last_hour += 1
        api_key.usage_last_day += 1
        api_key.last_used_at = datetime.utcnow()
        api_key.save()
        
        return usage_log

    def check_rate_limit(self, api_key: EnhancedApiKey) -> Tuple[bool, Dict[str, Any]]:
        """Check if API key is within rate limits."""
        rate_limit = api_key.rate_limit
        
        if not rate_limit:
            return True, {"message": "No rate limit configured"}
        
        # Check hourly limit
        if rate_limit.requests_per_hour and api_key.usage_last_hour >= rate_limit.requests_per_hour:
            return False, {
                "message": "Hourly rate limit exceeded",
                "limit": rate_limit.requests_per_hour,
                "current": api_key.usage_last_hour,
                "window": "hour"
            }
        
        # Check daily limit
        if rate_limit.requests_per_day and api_key.usage_last_day >= rate_limit.requests_per_day:
            return False, {
                "message": "Daily rate limit exceeded",
                "limit": rate_limit.requests_per_day,
                "current": api_key.usage_last_day,
                "window": "day"
            }
        
        return True, {"message": "Within rate limits"}

    def reset_usage_counts(self, organization_id: str):
        """Reset hourly usage counts for an organization."""
        from datetime import datetime, timedelta
        
        # Reset hourly counts
        EnhancedApiKey.objects(
            organization_id=organization_id
        ).update(set__usage_last_hour=0)
        
        # Reset daily counts if it's a new day
        # This would typically be called by a scheduled task
        pass

    def _generate_client_id(self) -> str:
        """Generate OAuth client ID."""
        return f"fbp_client_{secrets.token_urlsafe(16)}"

    def _generate_client_secret(self) -> str:
        """Generate OAuth client secret."""
        return secrets.token_urlsafe(32)

    def _generate_authorization_code(self) -> str:
        """Generate authorization code."""
        return secrets.token_urlsafe(32)

    def _generate_access_token(self) -> str:
        """Generate access token."""
        return f"fbp_at_{secrets.token_urlsafe(32)}"

    def _generate_refresh_token(self) -> str:
        """Generate refresh token."""
        return f"fbp_rt_{secrets.token_urlsafe(32)}"

    def _generate_api_key(self) -> str:
        """Generate API key."""
        return f"fbp_{secrets.token_urlsafe(32)}"

    def _hash_secret(self, secret: str) -> str:
        """Hash secret using SHA-256."""
        return hashlib.sha256(secret.encode('utf-8')).hexdigest()

    def _hash_token(self, token: str) -> str:
        """Hash token using SHA-256."""
        return self._hash_secret(token)

    def _verify_secret(self, secret: str, hash_value: str) -> bool:
        """Verify secret against hash."""
        return self._hash_secret(secret) == hash_value

    def _validate_redirect_uri(self, uri: str):
        """Validate redirect URI."""
        parsed = urlparse(uri)
        if not parsed.scheme or not parsed.netloc:
            raise ValidationError("Invalid redirect URI")
        if parsed.scheme not in ['http', 'https']:
            raise ValidationError("Redirect URI must use HTTP or HTTPS")

    def _verify_pkce_challenge(self, code_verifier: str, auth_code: OAuthAuthorizationCode) -> bool:
        """Verify PKCE code challenge."""
        import hashlib
        import base64
        
        if auth_code.code_challenge_method == 'plain':
            return code_verifier == auth_code.code_challenge
        elif auth_code.code_challenge_method == 'S256':
            challenge = base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode('utf-8')).digest()
            ).decode('utf-8').rstrip('=')
            return challenge == auth_code.code_challenge
        return False

    def _get_user_organization(self, user_id) -> str:
        """Get user's organization ID."""
        from models.identity import OrgMembership
        
        membership = OrgMembership.objects(
            user_id=user_id,
            status='active'
        ).first()
        
        if not membership:
            raise ValidationError("User is not a member of any organization")
        
        return str(membership.org_id)


oauth_service = OAuthService()