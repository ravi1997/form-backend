"""
User Management Routes (Self-Service and Administrative)
Uses UserService for all user-related business logic.
"""

import logging
from flask import Blueprint, request, jsonify
from flasgger import swag_from
from flask_jwt_extended import (
    jwt_required, 
    current_user
)
from services.user_service import UserService
from utils.exceptions import UnauthorizedError, NotFoundError, ValidationError
from utils.security import require_roles
from utils.response_helper import success_response, error_response
from extensions import limiter
from schemas.user import UserOut, UserCreateSchema, UserUpdateSchema

user_bp = Blueprint("user_bp", __name__)
user_service = UserService()
logger = logging.getLogger(__name__)


# ─── Self-Service (Authenticated User) ─────────────────────────────────────────


@user_bp.route("/profile", methods=["GET"])
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
    return success_response(data=UserOut.model_validate(current_user.to_dict()).model_dump())


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
    data = request.json or {}
    current_pw = data.get("current_password", "")
    new_pw = data.get("new_password", "")

    if not current_user.check_password(current_pw):
        raise ValidationError("Current password incorrect")

    current_user.set_password(new_pw)
    current_user.save()
    logger.info(f"Password changed for user {current_user.id}")
    return success_response(message="Password changed successfully")


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
    users = user_service.list_paginated(
        page=int(request.args.get("page", 1)),
        page_size=int(request.args.get("page_size", 20))
    )
    return success_response(data=users.model_dump())


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
            "required": true
        }
    ]
})
@require_roles("admin", "superadmin")
def get_user_by_id(user_id):
    """Fetch details of a specific user. Admin only."""
    user = user_service.get_by_id(user_id)
    return success_response(data=UserOut.model_validate(user.model_dump()).model_dump())


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
    data = request.json or {}
    try:
        schema = UserCreateSchema(**data)
        user = user_service.create(schema)
        return success_response(
            data={"user": UserOut.model_validate(user.model_dump()).model_dump()},
            message="User created",
            status_code=201
        )
    except Exception as e:
        logger.warning(f"Admin user creation failed: {e}")
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
            "required": true
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
    data = request.json or {}
    try:
        schema = UserUpdateSchema(**data)
        user = user_service.update(user_id, schema)
        return success_response(data=UserOut.model_validate(user.model_dump()).model_dump())
    except Exception as e:
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
            "required": true
        }
    ]
})
@require_roles("superadmin") # Only superadmin can delete
def delete_user_by_id(user_id):
    """Soft-delete a user account. Superadmin only."""
    user_service.delete(user_id)
    return success_response(message="User account deactivated")


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
            "required": true
        }
    ]
})
@require_roles("admin", "superadmin")
def lock_user_account(user_id):
    """Manually lock a user account. Admin only."""
    from models.User import User
    user = User.objects(id=user_id).first()
    if not user:
        raise NotFoundError("User not found")
    user.lock_account()
    return success_response(message=f"User {user_id} account locked")


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
            "required": true
        }
    ]
})
@require_roles("admin", "superadmin")
def unlock_user_account(user_id):
    """Manually unlock a user account. Admin only."""
    from models.User import User
    user = User.objects(id=user_id).first()
    if not user:
        raise NotFoundError("User not found")
    user.unlock_account()
    return success_response(message=f"User {user_id} account unlocked")
