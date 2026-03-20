"""
Authentication Routes
Uses AuthService and UserService for all business logic.
"""

import logging
from flask import Blueprint, current_app, request, jsonify
from flask_jwt_extended import (
    jwt_required,
    get_jwt,
    set_access_cookies,
    unset_jwt_cookies,
    get_jwt_identity,
)
from services.auth_service import AuthService
from services.user_service import UserService
from utils.exceptions import UnauthorizedError, ValidationError
from utils.response_helper import success_response, error_response
from extensions import limiter
from schemas.auth import TokenResponse
from schemas.user import UserOut
from flasgger import swag_from

auth_bp = Blueprint("auth_bp", __name__)
auth_service = AuthService()
user_service = UserService()
logger = logging.getLogger(__name__)


# -------------------- REGISTER --------------------


@auth_bp.route("/register", methods=["POST"])
@swag_from({
    "tags": ["Auth"],
    "summary": "Register a new user",
    "description": "Registers a new user and returns user details.",
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {"$ref": "#/definitions/UserCreateSchema"}
        }
    ],
    "responses": {
        "201": {
            "description": "User created successfully",
            "schema": {"$ref": "#/definitions/UserOut"}
        },
        "400": {"description": "Validation error or user already exists"}
    }
})
@limiter.limit("5 per minute")
def register():
    """Register a new user account."""
    data = request.get_json(silent=True) or {}
    try:
        from schemas.user import UserCreateSchema
        schema = UserCreateSchema(**data)
        user = user_service.create(schema)
        current_app.logger.info(
            f"New user registered: {user.username or user.email}"
        )
        return success_response(
            data={"user": UserOut.model_validate(user.model_dump()).model_dump()},
            message="User registered successfully",
            status_code=201
        )
    except Exception as e:
        current_app.logger.warning(f"Registration failed: {e}")
        return error_response(message=str(e), status_code=400)


# -------------------- LOGIN --------------------


@auth_bp.route("/login", methods=["POST"])
@swag_from({
    "tags": ["Auth"],
    "summary": "User Login",
    "description": "Authenticate via password or OTP and issue JWT tokens.",
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {"$ref": "#/definitions/LoginRequest"}
        }
    ],
    "responses": {
        "200": {
            "description": "Login successful",
            "schema": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "access_token": {"type": "string"},
                            "refresh_token": {"type": "string"},
                            "user": {"$ref": "#/definitions/UserOut"}
                        }
                    }
                }
            }
        },
        "401": {"description": "Invalid credentials"}
    }
})
@limiter.limit("5 per minute")
def login():
    """Authenticate via password or OTP and issue JWT tokens."""
    data = request.get_json(force=True, silent=True) or {}
    password = data.get("password")
    mobile = data.get("mobile")
    otp = data.get("otp")

    try:
        if password:
            # Password login
            identifier = (
                data.get("email")
                or data.get("username")
                or data.get("employee_id")
                or data.get("identifier")
            )
            if not identifier:
                raise ValidationError("Missing identifier")
            user_schema = user_service.authenticate_employee(identifier, password)

        elif mobile and otp:
            # OTP login
            user_schema = user_service.verify_otp_login(str(mobile).strip(), otp)

        else:
            raise ValidationError("Missing credentials: provide (identifier + password) or (mobile + otp)")

        # Issue tokens via AuthService
        from models.User import User
        user_doc = User.objects(id=user_schema.id).first()
        token_data = auth_service.generate_tokens(user_doc)

        data = {
            "access_token": token_data.access_token, 
            "refresh_token": token_data.refresh_token, 
            "user": UserOut.model_validate(user_schema.model_dump()).model_dump()
        }
        resp = success_response(data=data, message="Login successful")
        
        # Set HttpOnly cookies for better security
        set_access_cookies(resp, token_data.access_token)
        current_app.logger.info(f"Login successful for user id={user_doc.id}")
        return resp
    except (UnauthorizedError, ValidationError) as e:
        raise
    except Exception:
        current_app.logger.exception("Login workflow error")
        return error_response(message="Authentication failed", status_code=500)


# -------------------- OTP REQUEST --------------------


@auth_bp.route("/request-otp", methods=["POST"])
@swag_from({
    "tags": ["Auth"],
    "summary": "Request OTP",
    "description": "Generate and send an OTP to the given mobile/email.",
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "properties": {
                    "mobile": {"type": "string"},
                    "email": {"type": "string"}
                }
            }
        }
    ],
    "responses": {
        "200": {"description": "OTP sent successfully"},
        "400": {"description": "Missing identifier"}
    }
})
@limiter.limit("3 per minute")
def request_otp():
    """Generate and send an OTP to the given mobile/email."""
    data = request.get_json(silent=True) or {}
    identifier = data.get("mobile") or data.get("email")
    if not identifier:
        return error_response(message="mobile or email required", status_code=400)
    try:
        user_service.request_otp(str(identifier).strip())
        return success_response(message="OTP sent successfully")
    except UnauthorizedError as e:
        return error_response(message=str(e), status_code=403)
    except Exception:
        return error_response(message="OTP generation failed", status_code=500)


# -------------------- TOKEN REFRESH --------------------


@auth_bp.route("/refresh", methods=["POST"])
@swag_from({
    "tags": ["Auth"],
    "summary": "Refresh Access Token",
    "description": "Generates a new access token using a valid refresh token.",
    "security": [{"Bearer": []}],
    "responses": {
        "200": {
            "description": "Token refreshed",
            "schema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string"},
                    "refresh_token": {"type": "string"},
                    "success": {"type": "boolean"}
                }
            }
        },
        "401": {"description": "Invalid or expired refresh token"}
    }
})
@jwt_required(refresh=True)
def refresh():
    """Issue a new access token using a valid refresh token."""
    try:
        from models.User import User
        current_user_id = get_jwt_identity()
        user = User.objects(id=current_user_id, is_active=True, is_deleted=False).first()
        if not user:
            return jsonify(message="User not found or suspended"), 404

        token_data = auth_service.generate_tokens(user)
        
        resp = jsonify(
            access_token=token_data.access_token, 
            refresh_token=token_data.refresh_token, # Rotate refresh token too
            success=True
        )
        set_access_cookies(resp, token_data.access_token)
        return resp, 200
    except Exception as e:
        return jsonify(message="Token refresh failed", error=str(e)), 401


# -------------------- LOGOUT --------------------


@auth_bp.route("/logout", methods=["POST"])
@swag_from({
    "tags": ["Auth"],
    "summary": "User Logout",
    "description": "Revokes the user's access and refresh tokens.",
    "security": [{"Bearer": []}],
    "responses": {
        "200": {"description": "Logout successful"}
    }
})
@jwt_required()
def logout():
    """Revoke the current JWT session."""
    try:
        # Revoke the access token
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            auth_service.revoke_token(token)

        resp = success_response(message="Successfully logged out")
        unset_jwt_cookies(resp)
        return resp
    except Exception:
        return error_response(message="Logout failed", status_code=500)


@auth_bp.route("/revoke-all", methods=["POST"])
@swag_from({
    "tags": ["Auth"],
    "summary": "Revoke All Sessions",
    "description": "Revokes all active JWT sessions for the authenticated user.",
    "security": [{"Bearer": []}],
    "responses": {
        "200": {"description": "All sessions revoked successfully"}
    }
})
@jwt_required()
def revoke_all():
    """Revoke all active sessions for the authenticated user."""
    try:
        user_id = get_jwt_identity()
        auth_service.revoke_all_user_sessions(user_id)
        
        resp = success_response(message="All sessions revoked successfully")
        unset_jwt_cookies(resp)
        return resp
    except Exception as e:
        logger.error(f"Global revocation failed: {e}")
        return error_response(message="Failed to revoke all sessions", status_code=500)
