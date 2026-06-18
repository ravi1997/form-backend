from flask import Blueprint, request
from flask_jwt_extended import get_jwt, get_jwt_identity

from models.base import Role
from models.identity import User
from services.api_key_service import ApiKeyService
from utils.response_helper import error_response, success_response
from utils.security import require_roles

api_key_bp = Blueprint("api_keys", __name__)


@api_key_bp.route("/", methods=["GET"])
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def list_api_keys():
    claims = get_jwt()
    organization_id = claims.get("org_id") or claims.get("organization_id")
    if not organization_id:
        return error_response("Organization ID not found in token context", 400)
    records = ApiKeyService.list_api_keys(organization_id)
    return success_response(
        data=[
            {
                "id": str(record.id),
                "name": record.name,
                "key_prefix": record.key_prefix,
                "scopes": record.scopes,
                "is_active": record.is_active,
                "expires_at": record.expires_at.isoformat() if record.expires_at else None,
                "last_used_at": record.last_used_at.isoformat() if record.last_used_at else None,
            }
            for record in records
        ]
    )


@api_key_bp.route("/", methods=["POST"])
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def create_api_key():
    claims = get_jwt()
    organization_id = claims.get("org_id") or claims.get("organization_id")
    user_id = get_jwt_identity()
    if not organization_id or not user_id:
        return error_response("Organization ID not found in token context", 400)
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return error_response("name is required", 400)
    user = User.objects(id=user_id).first()
    if user is None:
        return error_response("User not found", 404)
    result = ApiKeyService.create_api_key(
        organization_id=organization_id,
        name=name,
        created_by=user,
        scopes=data.get("scopes") or [],
    )
    return success_response(
        data={
            "id": str(result.record.id),
            "raw_key": result.raw_key,
            "key_prefix": result.prefix,
        },
        status_code=201,
    )
