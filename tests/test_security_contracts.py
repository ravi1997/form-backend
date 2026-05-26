from utils.idempotency import require_idempotency
import pathlib
from utils.permission_validator import PermissionValidator, permission_validator
from flask import Flask
from middleware.rbac_matrix import setup_rbac_matrix
from flask_jwt_extended import create_access_token, JWTManager


def test_retryable_mutation_requires_idempotency_key(app):
    @require_idempotency()
    def mutation():
        raise AssertionError("mutation must not execute without idempotency key")

    with app.test_request_context("/resource", method="POST", json={"x": 1}):
        response, status = mutation()

    assert status == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_permission_matrix_declares_critical_routes():
    matrix = pathlib.Path("config/permissions.yaml").read_text()

    assert "form:publish" in matrix
    assert "response:export" in matrix
    assert "POST /form/api/v1/projects/<project_id>/forms/<form_id>/publish" in matrix


def test_permission_validator_singleton():
    """Verify that PermissionValidator works as a singleton."""
    pv1 = PermissionValidator()
    pv2 = PermissionValidator()
    assert pv1 is pv2
    assert permission_validator is pv1


def test_permission_validator_inheritance_and_wildcard():
    """Verify role inheritance and wildcard behavior in PermissionValidator."""
    pv = PermissionValidator()
    
    # Superadmin should have wildcard and therefore any permission
    assert pv.has_permission(["superadmin"], "random:permission")
    assert pv.has_permission(["superadmin"], "form:publish")
    
    # Admin should inherit from manager and user
    admin_perms = pv.get_user_permissions(["admin"])
    assert "form:publish" in admin_perms
    assert "form:create" in admin_perms
    assert "form:view" in admin_perms
    
    # User should only have basic permissions
    user_perms = pv.get_user_permissions(["user"])
    assert "form:view" in user_perms
    assert "form:publish" not in user_perms
    
    # Manager should inherit from user and have its own permissions
    manager_perms = pv.get_user_permissions(["manager"])
    assert "form:view" in manager_perms
    assert "form:create" in manager_perms
    assert "form:publish" in manager_perms


def test_route_pattern_matching():
    """Verify that Flask-style path parameters are matched correctly."""
    pv = PermissionValidator()
    
    # Match EXACT publish route
    perm1 = pv.match_route_permission(
        "POST", "/form/api/v1/projects/proj-123/forms/form-456/publish"
    )
    assert perm1 == "form:publish"
    
    # Match EXACT responses route
    perm2 = pv.match_route_permission(
        "GET", "/form/api/v1/projects/proj-123/forms/form-456/responses"
    )
    assert perm2 == "response:view"

    # Match EXACT export route with wildcards in format
    perm3 = pv.match_route_permission(
        "GET", "/form/api/v1/projects/proj-123/forms/form-456/export/csv"
    )
    assert perm3 == "response:export"

    # Unprotected route should return None
    perm4 = pv.match_route_permission("GET", "/form/api/v1/health")
    assert perm4 is None


def test_rbac_matrix_middleware_enforcement():
    """Verify that the RBAC matrix middleware blocks/allows requests correctly."""
    test_app = Flask("test_rbac_app")
    test_app.config["JWT_SECRET_KEY"] = "super-secret"
    test_app.config["JWT_ALGORITHM"] = "HS256"
    JWTManager(test_app)
    
    setup_rbac_matrix(test_app)

    # Add a mock endpoint to test middleware intercept
    @test_app.route("/form/api/v1/projects/<project_id>/forms/<form_id>/publish", methods=["POST"])
    def publish_mock(project_id, form_id):
        return {"status": "success"}, 200

    client = test_app.test_client()

    # Case 1: Unauthenticated request should get 401
    res1 = client.post("/form/api/v1/projects/p1/forms/f1/publish")
    assert res1.status_code == 401
    assert res1.json["success"] is False
    assert "Authentication required" in res1.json["error"]["message"]

    with test_app.app_context():
        # Case 2: User role has insufficient permissions (should get 403)
        user_token = create_access_token(
            identity="test-user",
            additional_claims={"roles": ["user"], "organization_id": "org1"}
        )
        
        # Case 3: Admin role has sufficient permissions (should get 200)
        admin_token = create_access_token(
            identity="test-admin",
            additional_claims={"roles": ["admin"], "organization_id": "org1"}
        )

        # Case 4: Superadmin role has wildcard bypass (should get 200)
        super_token = create_access_token(
            identity="test-super",
            additional_claims={"roles": ["superadmin"], "organization_id": "org1"}
        )

    # Run client requests with headers
    res2 = client.post(
        "/form/api/v1/projects/p1/forms/f1/publish",
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert res2.status_code == 403
    assert "Insufficient permissions" in res2.json["error"]["message"]

    res3 = client.post(
        "/form/api/v1/projects/p1/forms/f1/publish",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res3.status_code == 200
    assert res3.json["status"] == "success"

    res4 = client.post(
        "/form/api/v1/projects/p1/forms/f1/publish",
        headers={"Authorization": f"Bearer {super_token}"}
    )
    assert res4.status_code == 200
    assert res4.json["status"] == "success"

