"""
routes/v1/oauth_route.py
OAuth 2.0 routes for public API access.
"""

from flask import Blueprint, request, jsonify, redirect, url_for
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.security import require_roles
from utils.response_helper import success_response, error_response
from services.oauth_service import oauth_service
from logger.unified_logger import app_logger, error_logger, audit_logger

oauth_bp = Blueprint("oauth_bp", __name__)


@oauth_bp.route("/authorize", methods=["GET"])
@swag_from({
    "tags": ["OAuth"],
    "parameters": [
        {"name": "response_type", "in": "query", "type": "string", "required": True},
        {"name": "client_id", "in": "query", "type": "string", "required": True},
        {"name": "redirect_uri", "in": "query", "type": "string", "required": False},
        {"name": "scope", "in": "query", "type": "string", "required": False},
        {"name": "state", "in": "query", "type": "string", "required": False},
        {"name": "code_challenge", "in": "query", "type": "string", "required": False},
        {"name": "code_challenge_method", "in": "query", "type": "string", "required": False}
    ],
    "responses": {"302": {"description": "Redirect to authorization page or error"}}
})
def authorize():
    """OAuth 2.0 authorization endpoint."""
    try:
        # Parse request parameters
        response_type = request.args.get('response_type')
        client_id = request.args.get('client_id')
        redirect_uri = request.args.get('redirect_uri')
        scope = request.args.get('scope', 'read')
        state = request.args.get('state')
        code_challenge = request.args.get('code_challenge')
        code_challenge_method = request.args.get('code_challenge_method')
        
        # Validate parameters
        if response_type != 'code':
            return error_response("Response type must be 'code'", status_code=400)
        
        if not client_id:
            return error_response("Client ID is required", status_code=400)
        
        # Get OAuth client
        try:
            client = oauth_service.get_oauth_client(client_id)
        except Exception as e:
            return error_response(str(e), status_code=401)
        
        # Validate redirect URI
        if redirect_uri and redirect_uri not in client.redirect_uris:
            return error_response("Invalid redirect URI", status_code=400)
        
        # For now, we'll simulate the authorization flow
        # In a real implementation, this would show a login/consent page
        # For demo purposes, we'll auto-authorize
        
        # Get current user (this would normally come from session)
        # For now, we'll use a placeholder
        user_id = request.args.get('user_id', 'placeholder_user_id')
        
        # Create authorization code
        auth_code = oauth_service.create_authorization_code(
            client_id=client_id,
            user_id=user_id,
            redirect_uri=redirect_uri,
            scopes=scope.split() if scope else ['read'],
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method
        )
        
        # Redirect back to client with authorization code
        redirect_url = redirect_uri or client.redirect_uris[0]
        separator = '&' if '?' in redirect_url else '?'
        
        redirect_params = f"code={auth_code.code}"
        if state:
            redirect_params += f"&state={state}"
        
        return redirect(f"{redirect_url}{separator}{redirect_params}")
        
    except Exception as e:
        error_logger.error(f"OAuth authorization error: {e}", exc_info=True)
        return error_response(str(e), status_code=400)


@oauth_bp.route("/token", methods=["POST"])
@swag_from({
    "tags": ["OAuth"],
    "parameters": [
        {"name": "grant_type", "in": "formData", "type": "string", "required": True},
        {"name": "code", "in": "formData", "type": "string", "required": False},
        {"name": "refresh_token", "in": "formData", "type": "string", "required": False},
        {"name": "client_id", "in": "formData", "type": "string", "required": True},
        {"name": "client_secret", "in": "formData", "type": "string", "required": True},
        {"name": "redirect_uri", "in": "formData", "type": "string", "required": False},
        {"name": "code_verifier", "in": "formData", "type": "string", "required": False}
    ],
    "responses": {"200": {"description": "Access token"}}
})
def token():
    """OAuth 2.0 token endpoint."""
    try:
        # Parse form data
        grant_type = request.form.get('grant_type')
        client_id = request.form.get('client_id')
        client_secret = request.form.get('client_secret')
        
        if not grant_type:
            return error_response("Grant type is required", status_code=400)
        
        if not client_id or not client_secret:
            return error_response("Client ID and secret are required", status_code=400)
        
        if grant_type == 'authorization_code':
            # Authorization Code Grant
            code = request.form.get('code')
            redirect_uri = request.form.get('redirect_uri')
            code_verifier = request.form.get('code_verifier')
            
            if not code:
                return error_response("Authorization code is required", status_code=400)
            
            # Exchange code for token
            token_response = oauth_service.exchange_code_for_token(
                code=code,
                client_id=client_id,
                client_secret=client_secret,
                code_verifier=code_verifier
            )
            
            return jsonify(token_response)
            
        elif grant_type == 'refresh_token':
            # Refresh Token Grant
            refresh_token = request.form.get('refresh_token')
            
            if not refresh_token:
                return error_response("Refresh token is required", status_code=400)
            
            # Refresh access token
            token_response = oauth_service.refresh_access_token(
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret
            )
            
            return jsonify(token_response)
            
        else:
            return error_response(f"Unsupported grant type: {grant_type}", status_code=400)
            
    except Exception as e:
        error_logger.error(f"OAuth token error: {e}", exc_info=True)
        return error_response(str(e), status_code=400)


@oauth_bp.route("/revoke", methods=["POST"])
@swag_from({
    "tags": ["OAuth"],
    "parameters": [
        {"name": "token", "in": "formData", "type": "string", "required": True},
        {"name": "token_type_hint", "in": "formData", "type": "string", "required": False}
    ],
    "responses": {"200": {"description": "Token revoked"}}
})
def revoke():
    """OAuth 2.0 token revocation endpoint."""
    try:
        token = request.form.get('token')
        token_type = request.form.get('token_type_hint', 'access_token')
        
        if not token:
            return error_response("Token is required", status_code=400)
        
        # Revoke token
        success = oauth_service.revoke_token(token, token_type)
        
        if success:
            return jsonify({"status": "success"})
        else:
            return error_response("Token not found", status_code=404)
            
    except Exception as e:
        error_logger.error(f"OAuth revoke error: {e}", exc_info=True)
        return error_response(str(e), status_code=400)


@oauth_bp.route("/introspect", methods=["POST"])
@swag_from({
    "tags": ["OAuth"],
    "parameters": [
        {"name": "token", "in": "formData", "type": "string", "required": True},
        {"name": "token_type_hint", "in": "formData", "type": "string", "required": False}
    ],
    "responses": {"200": {"description": "Token information"}}
})
def introspect():
    """OAuth 2.0 token introspection endpoint."""
    try:
        token = request.form.get('token')
        token_type = request.form.get('token_type_hint', 'access_token')
        
        if not token:
            return error_response("Token is required", status_code=400)
        
        # Validate token
        token_info = oauth_service.validate_access_token(token)
        
        if token_info:
            token_info['active'] = True
            return jsonify(token_info)
        else:
            return jsonify({"active": False})
            
    except Exception as e:
        error_logger.error(f"OAuth introspect error: {e}", exc_info=True)
        return error_response(str(e), status_code=400)


@oauth_bp.route("/jwks", methods=["GET"])
@swag_from({
    "tags": ["OAuth"],
    "responses": {"200": {"description": "JSON Web Key Set"}}
})
def jwks():
    """JSON Web Key Set endpoint for OpenID Connect."""
    # For now, return empty JWKS
    # In a real implementation, this would return the public keys
    return jsonify({"keys": []})


@oauth_bp.route("/.well-known/oauth-authorization-server", methods=["GET"])
@swag_from({
    "tags": ["OAuth"],
    "responses": {"200": {"description": "OAuth authorization server metadata"}}
})
def oauth_metadata():
    """OAuth 2.0 authorization server metadata."""
    base_url = request.url_root.rstrip('/')
    
    metadata = {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/mahasangraha/api/v1/oauth/authorize",
        "token_endpoint": f"{base_url}/mahasangraha/api/v1/oauth/token",
        "revocation_endpoint": f"{base_url}/mahasangraha/api/v1/oauth/revoke",
        "introspection_endpoint": f"{base_url}/mahasangraha/api/v1/oauth/introspect",
        "jwks_uri": f"{base_url}/mahasangraha/api/v1/oauth/jwks",
        "scopes_supported": ["read", "write", "admin"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "code_challenge_methods_supported": ["plain", "S256"],
        "subject_types_supported": ["public"]
    }
    
    return jsonify(metadata)


# API Key Management Routes
@oauth_bp.route("/api-keys", methods=["POST"])
@swag_from({
    "tags": ["API Keys"],
    "responses": {"201": {"description": "API key created"}}
})
@jwt_required()
@require_roles("admin")
def create_api_key():
    """Create a new API key."""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request data is required", status_code=400)
        
        # Get user's organization
        from services.auth_service import auth_service
        user_orgs = auth_service.get_user_organizations(user_id)
        if not user_orgs:
            return error_response("User not associated with any organization", status_code=400)
        
        data['organization_id'] = str(user_orgs[0].id)
        data['user_id'] = user_id
        
        api_key_data = oauth_service.create_enhanced_api_key(**data)
        
        return success_response(
            data=api_key_data,
            message="API key created successfully",
            status_code=201
        )
        
    except Exception as e:
        error_logger.error(f"API key creation error: {e}", exc_info=True)
        return error_response(str(e), status_code=400)


@oauth_bp.route("/api-keys", methods=["GET"])
@swag_from({
    "tags": ["API Keys"],
    "responses": {"200": {"description": "List of API keys"}}
})
@jwt_required()
@require_roles("admin")
def list_api_keys():
    """List API keys for the current organization."""
    try:
        user_id = get_jwt_identity()
        
        # Get user's organization
        from services.auth_service import auth_service
        user_orgs = auth_service.get_user_organizations(user_id)
        if not user_orgs:
            return error_response("User not associated with any organization", status_code=400)
        
        from models.oauth import EnhancedApiKey
        api_keys = EnhancedApiKey.objects(
            organization_id=str(user_orgs[0].id),
            is_deleted=False
        ).order_by('-created_at')
        
        api_keys_data = []
        for api_key in api_keys:
            api_keys_data.append({
                "id": str(api_key.id),
                "name": api_key.name,
                "description": api_key.description,
                "key_prefix": api_key.key_prefix,
                "scopes": [scope.to_dict() for scope in api_key.scopes],
                "rate_limit": api_key.rate_limit.to_dict() if api_key.rate_limit else None,
                "is_active": api_key.is_active,
                "usage_count": api_key.usage_count,
                "last_used_at": api_key.last_used_at.isoformat() if api_key.last_used_at else None,
                "created_at": api_key.created_at.isoformat(),
                "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None
            })
        
        return success_response(data=api_keys_data)
        
    except Exception as e:
        error_logger.error(f"API key listing error: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@oauth_bp.route("/api-keys/<key_id>", methods=["DELETE"])
@swag_from({
    "tags": ["API Keys"],
    "parameters": [
        {"name": "key_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {"200": {"description": "API key revoked"}}
})
@jwt_required()
@require_roles("admin")
def revoke_api_key(key_id):
    """Revoke an API key."""
    try:
        user_id = get_jwt_identity()
        
        # Get API key
        from models.oauth import EnhancedApiKey
        api_key = EnhancedApiKey.objects(
            id=key_id,
            is_deleted=False
        ).first()
        
        if not api_key:
            return error_response("API key not found", status_code=404)
        
        # Check user has permission
        from services.auth_service import auth_service
        user_orgs = auth_service.get_user_organizations(user_id)
        if not user_orgs or str(api_key.organization_id) != str(user_orgs[0].id):
            return error_response("Permission denied", status_code=403)
        
        # Revoke API key
        api_key.is_active = False
        api_key.revoked_at = datetime.utcnow()
        api_key.revoked_by = user_id
        api_key.save()
        
        audit_logger.info(f"API key revoked: {api_key.name} by user {user_id}")
        
        return success_response(message="API key revoked successfully")
        
    except Exception as e:
        error_logger.error(f"API key revocation error: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@oauth_bp.route("/api-keys/<key_id>/usage", methods=["GET"])
@swag_from({
    "tags": ["API Keys"],
    "parameters": [
        {"name": "key_id", "in": "path", "type": "string", "required": True},
        {"name": "days", "in": "query", "type": "integer", "required": False}
    ],
    "responses": {"200": {"description": "API key usage statistics"}}
})
@jwt_required()
@require_roles("admin")
def get_api_key_usage(key_id):
    """Get API key usage statistics."""
    try:
        user_id = get_jwt_identity()
        days = int(request.args.get('days', 7))
        
        # Get API key
        from models.oauth import EnhancedApiKey
        api_key = EnhancedApiKey.objects(
            id=key_id,
            is_deleted=False
        ).first()
        
        if not api_key:
            return error_response("API key not found", status_code=404)
        
        # Check user has permission
        from services.auth_service import auth_service
        user_orgs = auth_service.get_user_organizations(user_id)
        if not user_orgs or str(api_key.organization_id) != str(user_orgs[0].id):
            return error_response("Permission denied", status_code=403)
        
        # Get usage logs
        from datetime import datetime, timedelta
        from models.oauth import ApiKeyUsageLog
        
        start_date = datetime.utcnow() - timedelta(days=days)
        usage_logs = ApiKeyUsageLog.objects(
            api_key_id=api_key,
            timestamp__gte=start_date
        ).order_by('-timestamp')
        
        # Calculate statistics
        total_requests = usage_logs.count()
        successful_requests = usage_logs(status_code__lt=400).count()
        error_requests = total_requests - successful_requests
        
        avg_response_time = 0
        if usage_logs:
            response_times = [log.response_time_ms for log in usage_logs if log.response_time_ms]
            if response_times:
                avg_response_time = sum(response_times) / len(response_times)
        
        # Group by endpoint
        endpoint_stats = {}
        for log in usage_logs:
            endpoint = log.endpoint
            if endpoint not in endpoint_stats:
                endpoint_stats[endpoint] = {
                    "count": 0,
                    "success": 0,
                    "errors": 0,
                    "avg_response_time": 0
                }
            
            endpoint_stats[endpoint]["count"] += 1
            if log.status_code and log.status_code < 400:
                endpoint_stats[endpoint]["success"] += 1
            else:
                endpoint_stats[endpoint]["errors"] += 1
        
        # Calculate averages for each endpoint
        for endpoint, stats in endpoint_stats.items():
            endpoint_logs = usage_logs(endpoint=endpoint, response_time_ms__ne=None)
            response_times = [log.response_time_ms for log in endpoint_logs if log.response_time_ms]
            if response_times:
                stats["avg_response_time"] = sum(response_times) / len(response_times)
        
        return success_response(data={
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "error_requests": error_requests,
            "success_rate": (successful_requests / total_requests * 100) if total_requests > 0 else 0,
            "avg_response_time": round(avg_response_time, 2),
            "endpoint_stats": endpoint_stats,
            "period_days": days
        })
        
    except Exception as e:
        error_logger.error(f"API key usage error: {e}", exc_info=True)
        return error_response(str(e), status_code=500)