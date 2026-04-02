"""
User Management Routes (Self-Service and Administrative)
Uses UserService for all user-related business logic.
"""

import logging
from flask import Blueprint, request, jsonify
from flasgger import swag_from
from flask_jwt_extended import (
    jwt_required, 
    current_user,
    get_jwt_identity
)
from services.user_service import UserService
from utils.exceptions import UnauthorizedError, NotFoundError, ValidationError
from utils.security import require_roles
from utils.response_helper import success_response, error_response
from extensions import limiter
from schemas.user import UserOut, UserCreateSchema, UserUpdateSchema
from logger.unified_logger import app_logger, error_logger, audit_logger

user_bp = Blueprint("user_bp", __name__)
user_service = UserService()


# ─── Self-Service (Authenticated User) ─────────────────────────────────────────


@user_bp.route("/profile", methods=["GET"])
@user_bp.route("/status", methods=["GET"])
@swag_from({
    "tags": [
        "User"
    ],
    "responses": {
        "200": {
            "description": "Return the currently authenticated user's profile.",
            "schema": {
                "$ref": "#/definitions/UserOut"
            }
        }
    }
})
@jwt_required()
def get_profile():
    """Return the currently authenticated user's profile."""
    app_logger.info(f"User {current_user.id} fetching profile")
    user_data = UserOut.model_validate(current_user.to_dict()).model_dump()
    return success_response(data={"user": user_data})


@user_bp.route("/change-password", methods=["POST"])
@swag_from({
    "tags": [
        "User"
    ],
    "responses": {
        "200": {
            "description": "Securely change the current user's password.",
            "schema": {
                "$ref": "#/definitions/UserOut"
            }
        }
    }
})
@jwt_required()
@limiter.limit("3 per hour")
def change_password():
    """Securely change the current user's password."""
    app_logger.info(f"User {current_user.id} requesting password change")
    data = request.json or {}
    current_pw = data.get("current_password", "")
    new_pw = data.get("new_password", "")

    if not current_user.check_password(current_pw):
        app_logger.warning(f"Password change failed for user {current_user.id}: Incorrect current password")
        raise ValidationError("Current password incorrect")

    try:
        current_user.set_password(new_pw)
        current_user.save()
        audit_logger.info(f"Password changed successfully for user {current_user.id}")
        return success_response(message="Password changed successfully")
    except Exception as e:
        error_logger.error(f"Error changing password for user {current_user.id}: {str(e)}")
        raise


# ─── Administrative CRUD (Roles: admin, superadmin) ─────────────────────────────


@user_bp.route("/users", methods=["GET"])
@swag_from({
    "tags": [
        "User"
    ],
    "responses": {
        "200": {
            "description": "List all registered users. Admin only.",
            "schema": {
                "$ref": "#/definitions/UserOut"
            }
        }
    }
})
@require_roles("admin", "superadmin")
def list_users():
    """List all registered users. Admin only."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} listing users")
    try:
        users = user_service.list_paginated(
            page=int(request.args.get("page", 1)),
            page_size=int(request.args.get("page_size", 20))
        )
        return success_response(data=users.model_dump())
    except Exception as e:
        error_logger.error(f"Error listing users by admin {admin_id}: {str(e)}")
        return error_response(message="Failed to list users", status_code=500)


@user_bp.route("/users/<user_id>", methods=["GET"])
@swag_from({
    "tags": [
        "User"
    ],
    "responses": {
        "200": {
            "description": "Fetch details of a specific user. Admin only.",
            "schema": {
                "$ref": "#/definitions/UserOut"
            }
        }
    },
    "parameters": [
        {
            "name": "user_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@require_roles("admin", "superadmin")
def get_user_by_id(user_id):
    """Fetch details of a specific user. Admin only."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} fetching user {user_id}")
    try:
        user = user_service.get_by_id(user_id)
        return success_response(data=UserOut.model_validate(user.model_dump()).model_dump())
    except NotFoundError:
        app_logger.warning(f"Admin {admin_id} requested non-existent user {user_id}")
        raise
    except Exception as e:
        error_logger.error(f"Error fetching user {user_id} by admin {admin_id}: {str(e)}")
        return error_response(message="Failed to fetch user", status_code=500)


@user_bp.route("/users", methods=["POST"])
@swag_from({
    "tags": [
        "User"
    ],
    "responses": {
        "200": {
            "description": "Provision a new user account. Admin only.",
            "schema": {
                "$ref": "#/definitions/UserOut"
            }
        }
    },
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "schema": {
                "$ref": "#/definitions/UserUpdateSchema"
            }
        }
    ]
})
@require_roles("admin", "superadmin")
def create_user():
    """Provision a new user account. Admin only."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} creating new user")
    data = request.json or {}
    try:
        schema = UserCreateSchema(**data)
        user = user_service.create(schema)
        audit_logger.info(f"User {user.id} created by admin {admin_id}")
        return success_response(
            data={"user": UserOut.model_validate(user.model_dump()).model_dump()},
            message="User created",
            status_code=201
        )
    except Exception as e:
        error_logger.warning(f"Admin user creation failed (Admin: {admin_id}): {str(e)}")
        return error_response(message=str(e), status_code=400)


@user_bp.route("/users/<user_id>", methods=["PUT"])
@swag_from({
    "tags": [
        "User"
    ],
    "responses": {
        "200": {
            "description": "Update user attributes. Admin only.",
            "schema": {
                "$ref": "#/definitions/UserOut"
            }
        }
    },
    "parameters": [
        {
            "name": "user_id",
            "in": "path",
            "type": "string",
            "required": True
        },
        {
            "name": "body",
            "in": "body",
            "schema": {
                "$ref": "#/definitions/UserUpdateSchema"
            }
        }
    ]
})
@require_roles("admin", "superadmin")
def update_user_by_id(user_id):
    """Update user attributes. Admin only."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} updating user {user_id}")
    data = request.json or {}
    try:
        schema = UserUpdateSchema(**data)
        user = user_service.update(user_id, schema)
        audit_logger.info(f"User {user_id} updated by admin {admin_id}")
        return success_response(data=UserOut.model_validate(user.model_dump()).model_dump())
    except Exception as e:
        error_logger.error(f"User update failed for {user_id} (Admin: {admin_id}): {str(e)}")
        return error_response(message=str(e), status_code=400)


@user_bp.route("/users/<user_id>", methods=["DELETE"])
@swag_from({
    "tags": [
        "User"
    ],
    "responses": {
        "200": {
            "description": "Soft-delete a user account. Superadmin only."
        }
    },
    "parameters": [
        {
            "name": "user_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@require_roles("superadmin") # Only superadmin can delete
def delete_user_by_id(user_id):
    """Soft-delete a user account. Superadmin only."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Superadmin {admin_id} deactivating user {user_id}")
    try:
        user_service.delete(user_id)
        audit_logger.info(f"User {user_id} deactivated by superadmin {admin_id}")
        return success_response(message="User account deactivated")
    except Exception as e:
        error_logger.error(f"User deactivation failed for {user_id} (Superadmin: {admin_id}): {str(e)}")
        raise


@user_bp.route("/users/<user_id>/roles", methods=["PUT"])
@swag_from({
    "tags": [
        "User"
    ],
    "responses": {
        "200": {
            "description": "Update user roles. Admin only.",
            "schema": {
                "$ref": "#/definitions/UserOut"
            }
        }
    },
    "parameters": [
        {
            "name": "user_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@require_roles("admin", "superadmin")
def update_user_roles(user_id):
    """Update user roles. Admin only."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} updating roles for user {user_id}")
    data = request.json or {}
    roles = data.get("roles")
    if roles is None:
        return error_response(message="Roles are required", status_code=400)
    
    try:
        from models.User import User
        user = User.objects(id=user_id).first()
        if not user:
            app_logger.warning(f"Admin {admin_id} attempted to update roles for non-existent user {user_id}")
            raise NotFoundError("User not found")
        
        old_roles = user.roles
        user.roles = roles
        # If 'admin' or 'superadmin' is in roles, also set is_admin=True
        if any(r in roles for r in ["admin", "superadmin"]):
            user.is_admin = True
        
        user.save()
        audit_logger.info(f"Roles for user {user_id} updated from {old_roles} to {roles} by admin {admin_id}")
        return success_response(data=UserOut.model_validate(user.to_dict()).model_dump(), message="Roles updated", success=True)
    except Exception as e:
        error_logger.error(f"Role update failed for {user_id} (Admin: {admin_id}): {str(e)}")
        return error_response(message=str(e), status_code=400)


# ─── Account Security Management ───────────────────────────────────────────────


@user_bp.route("/users/<user_id>/lock", methods=["POST"])
@swag_from({
    "tags": [
        "User"
    ],
    "responses": {
        "200": {
            "description": "Manually lock a user account. Admin only."
        }
    },
    "parameters": [
        {
            "name": "user_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@require_roles("admin", "superadmin")
def lock_user_account(user_id):
    """Manually lock a user account. Admin only."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} locking user account {user_id}")
    try:
        from models.User import User
        user = User.objects(id=user_id).first()
        if not user:
            app_logger.warning(f"Admin {admin_id} attempted to lock non-existent user {user_id}")
            raise NotFoundError("User not found")
        user.lock_account()
        audit_logger.info(f"User {user_id} account manually locked by admin {admin_id}")
        return success_response(message=f"User {user_id} account locked")
    except Exception as e:
        error_logger.error(f"Account lock failed for {user_id} (Admin: {admin_id}): {str(e)}")
        raise


@user_bp.route("/users/<user_id>/unlock", methods=["POST"])
@swag_from({
    "tags": [
        "User"
    ],
    "responses": {
        "200": {
            "description": "Manually unlock a user account. Admin only."
        }
    },
    "parameters": [
        {
            "name": "user_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@require_roles("admin", "superadmin")
def unlock_user_account(user_id):
    """Manually unlock a user account. Admin only."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} unlocking user account {user_id}")
    try:
        from models.User import User
        user = User.objects(id=user_id).first()
        if not user:
            app_logger.warning(f"Admin {admin_id} attempted to unlock non-existent user {user_id}")
            raise NotFoundError("User not found")
        user.unlock_account()
        audit_logger.info(f"User {user_id} account manually unlocked by admin {admin_id}")
        return success_response(message=f"User {user_id} account unlocked")
    except Exception as e:
        error_logger.error(f"Account unlock failed for {user_id} (Admin: {admin_id}): {str(e)}")
        raise


@user_bp.route("/security/lock-status/<user_id>", methods=["GET"])
@swag_from({
    "tags": [
        "User"
    ],
    "responses": {
        "200": {
            "description": "Get account lock status for a specific user. Admin only.",
            "schema": {
                "type": "object",
                "properties": {
                    "is_locked": {"type": "boolean"},
                    "lock_until": {"type": "string", "format": "date-time"},
                    "failed_login_attempts": {"type": "integer"}
                }
            }
        }
    },
    "parameters": [
        {
            "name": "user_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@require_roles("admin", "superadmin")
def get_lock_status(user_id):
    """Get account lock status for a specific user. Admin only."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} fetching lock status for user {user_id}")
    try:
        from models.User import User
        user = User.objects(id=user_id).first()
        if not user:
            raise NotFoundError("User not found")
        
        return success_response(data={
            "is_locked": user.is_locked(),
            "lock_until": user.lock_until.isoformat() if user.lock_until else None,
            "failed_login_attempts": user.failed_login_attempts
        })
    except Exception as e:
        error_logger.error(f"Error fetching lock status for {user_id}: {str(e)}")
        raise

