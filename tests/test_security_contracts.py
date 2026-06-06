import pathlib
import pytest
from flask import Flask
from flask_jwt_extended import create_access_token, JWTManager
from middleware.rbac_matrix import setup_rbac_matrix
from utils.idempotency import require_idempotency
from utils.permission_validator import PermissionValidator, permission_validator
from routes.v1.auth_route import auth_bp
from extensions import jwt


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
    assert (
        "POST /mahasangraha/api/v1/projects/<project_id>/forms/<form_id>/publish"
        in matrix
    )


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
        "POST", "/mahasangraha/api/v1/projects/proj-123/forms/form-456/publish"
    )
    assert perm1 == "form:publish"

    # Match EXACT responses route
    perm2 = pv.match_route_permission(
        "GET", "/mahasangraha/api/v1/projects/proj-123/forms/form-456/responses"
    )
    assert perm2 == "response:view"

    # Match EXACT export route with wildcards in format
    perm3 = pv.match_route_permission(
        "GET", "/mahasangraha/api/v1/projects/proj-123/forms/form-456/export/csv"
    )
    assert perm3 == "response:export"

    # Unprotected route should return None
    perm4 = pv.match_route_permission("GET", "/mahasangraha/api/v1/health")
    assert perm4 is None


def test_rbac_matrix_middleware_enforcement():
    """Verify that the RBAC matrix middleware blocks/allows requests correctly."""
    test_app = Flask("test_rbac_app")
    test_app.config["JWT_SECRET_KEY"] = "super-secret"
    test_app.config["JWT_ALGORITHM"] = "HS256"
    JWTManager(test_app)

    setup_rbac_matrix(test_app)

    # Add a mock endpoint to test middleware intercept
    @test_app.route(
        "/mahasangraha/api/v1/projects/<project_id>/forms/<form_id>/publish",
        methods=["POST"],
    )
    def publish_mock(project_id, form_id):
        return {"status": "success"}, 200

    client = test_app.test_client()

    # Case 1: Unauthenticated request should get 401
    res1 = client.post("/mahasangraha/api/v1/projects/p1/forms/f1/publish")
    assert res1.status_code == 401
    assert res1.json["success"] is False
    assert "Authentication required" in res1.json["error"]["message"]

    with test_app.app_context():
        # Case 2: User role has insufficient permissions (should get 403)
        user_token = create_access_token(
            identity="test-user",
            additional_claims={"roles": ["user"], "organization_id": "org1"},
        )

        # Case 3: Admin role has sufficient permissions (should get 200)
        admin_token = create_access_token(
            identity="test-admin",
            additional_claims={"roles": ["admin"], "organization_id": "org1"},
        )

        # Case 4: Superadmin role has wildcard bypass (should get 200)
        super_token = create_access_token(
            identity="test-super",
            additional_claims={"roles": ["superadmin"], "organization_id": "org1"},
        )

    # Run client requests with headers
    res2 = client.post(
        "/mahasangraha/api/v1/projects/p1/forms/f1/publish",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert res2.status_code == 403
    assert "Insufficient permissions" in res2.json["error"]["message"]

    res3 = client.post(
        "/mahasangraha/api/v1/projects/p1/forms/f1/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res3.status_code == 200
    assert res3.json["status"] == "success"

    res4 = client.post(
        "/mahasangraha/api/v1/projects/p1/forms/f1/publish",
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert res4.status_code == 200
    assert res4.json["status"] == "success"


@pytest.fixture
def auth_contract_app():
    app = Flask("auth_contract_app")
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="super-secret",
        JWT_ALGORITHM="HS256",
        JWT_TOKEN_LOCATION=["headers", "cookies"],
        JWT_COOKIE_CSRF_PROTECT=True,
        JWT_ACCESS_CSRF_HEADER_NAME="X-CSRF-TOKEN-ACCESS",
        JWT_REFRESH_CSRF_HEADER_NAME="X-CSRF-TOKEN-REFRESH",
    )
    jwt.init_app(app)
    app.register_blueprint(auth_bp, url_prefix="/mahasangraha/api/v1/auth")
    return app


def test_auth_transport_matrix_accepts_bearer_and_cookie(auth_contract_app, db_connection):
    client = auth_contract_app.test_client()

    with auth_contract_app.app_context():
        bearer_token = create_access_token(
            identity="user-1",
            additional_claims={"roles": ["admin"], "organization_id": "org-1"},
        )
        cookie_token = create_access_token(
            identity="user-2",
            additional_claims={"roles": ["admin"], "organization_id": "org-1"},
        )

    bearer_response = client.post(
        "/mahasangraha/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {bearer_token}"},
    )
    assert bearer_response.status_code == 200
    assert bearer_response.json["success"] is True

    from flask_jwt_extended import set_access_cookies

    with auth_contract_app.test_request_context():
        response = auth_contract_app.response_class()
        set_access_cookies(response, cookie_token)

    access_cookie = None
    csrf_cookie = None
    for set_cookie in response.headers.getlist("Set-Cookie"):
        key, value = set_cookie.split(";", 1)[0].split("=", 1)
        if key == "access_token_cookie":
            access_cookie = value
        if key == "csrf_access_token":
            csrf_cookie = value

    assert access_cookie
    assert csrf_cookie
    client.set_cookie("access_token_cookie", access_cookie)
    client.set_cookie("csrf_access_token", csrf_cookie)
    cookie_response = client.post(
        "/mahasangraha/api/v1/auth/logout",
        headers={"X-CSRF-TOKEN-ACCESS": csrf_cookie},
    )
    assert cookie_response.status_code == 200
    assert cookie_response.json["success"] is True


def test_cookie_auth_write_routes_require_csrf_header(auth_contract_app, db_connection):
    client = auth_contract_app.test_client()

    with auth_contract_app.app_context():
        access_token = create_access_token(
            identity="user-3",
            additional_claims={"roles": ["admin"], "organization_id": "org-1"},
        )

    response = auth_contract_app.response_class()
    from flask_jwt_extended import set_access_cookies

    with auth_contract_app.test_request_context():
        set_access_cookies(response, access_token)
    csrf_cookie = None
    for set_cookie in response.headers.getlist("Set-Cookie"):
        key, value = set_cookie.split(";", 1)[0].split("=", 1)
        if key == "csrf_access_token":
            csrf_cookie = value

    assert csrf_cookie

    access_cookie = None
    for set_cookie in response.headers.getlist("Set-Cookie"):
        key, value = set_cookie.split(";", 1)[0].split("=", 1)
        if key == "access_token_cookie":
            access_cookie = value
    assert access_cookie
    client.set_cookie("access_token_cookie", access_cookie)

    blocked = client.post(
        "/mahasangraha/api/v1/auth/logout",
    )
    assert blocked.status_code in {401, 403}
    assert "msg" in blocked.json or "error" in blocked.json

    client.set_cookie("csrf_access_token", csrf_cookie)
    allowed = client.post(
        "/mahasangraha/api/v1/auth/logout",
        headers={
            "X-CSRF-TOKEN-ACCESS": csrf_cookie,
        },
    )
    assert allowed.status_code == 200
    assert allowed.json["success"] is True
