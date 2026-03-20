"""
utils/jwt_handlers.py
Registers JWT callbacks for the application.
"""
from extensions import jwt

def register_jwt_handlers(app):
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload: dict) -> bool:
        jti = jwt_payload["jti"]
        user_id = jwt_payload["sub"]
        iat = jwt_payload["iat"]
        
        from services.auth_service import AuthService
        auth_service = AuthService()
        
        # 1. Check Global Revocation (last_token_revocation_at)
        if auth_service.check_global_revocation(user_id, iat):
            return True
            
        # 2. Check Specific JTI Revocation
        return auth_service.is_token_revoked(jti)

    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        identity = jwt_data["sub"]
        from models.User import User
        return User.objects(id=identity).first()
