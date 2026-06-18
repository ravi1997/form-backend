import pytest
from flask_jwt_extended import create_access_token
from models.Organization import Organization
from models.TenantSettings import TenantSettings
from models.user import User
from services.org_service import OrgService
from schemas.org import OrgCreateSchema
from utils.exceptions import ValidationError, NotFoundError

@pytest.fixture
def org_service():
    Organization.objects.delete()
    TenantSettings.objects.delete()
    return OrgService()

def test_create_org(db_connection, org_service):
    schema = OrgCreateSchema(
        organization_id="spacex",
        name="Space Exploration Technologies Corp.",
        display_name="SpaceX",
        contact_email="elon@spacex.com",
        description="Mars mission provider",
        metadata={"priority": "high"}
    )
    
    res = org_service.create_org(schema)
    assert res.organization_id == "spacex"
    assert res.name == "Space Exploration Technologies Corp."
    assert res.status == "active"
    
    # Verify DB state
    org = Organization.objects(organization_id="spacex").first()
    assert org is not None
    assert org.name == "Space Exploration Technologies Corp."
    
    # Verify TenantSettings auto-creation
    settings = TenantSettings.objects(organization_id="spacex").first()
    assert settings is not None
    assert settings.max_forms == 100

def test_create_org_duplicate(db_connection, org_service):
    schema = OrgCreateSchema(
        organization_id="spacex",
        name="SpaceX",
        display_name="SpaceX"
    )
    org_service.create_org(schema)
    
    with pytest.raises(ValidationError):
        org_service.create_org(schema)

def test_update_status(db_connection, org_service):
    schema = OrgCreateSchema(
        organization_id="spacex",
        name="SpaceX",
        display_name="SpaceX"
    )
    org_service.create_org(schema)
    
    res = org_service.update_status("spacex", "suspended")
    assert res.status == "suspended"
    
    # Verify TenantSettings is_active state
    settings = TenantSettings.objects(organization_id="spacex").first()
    assert settings.is_active is False
    
    res = org_service.update_status("spacex", "active")
    assert res.status == "active"
    
    settings = TenantSettings.objects(organization_id="spacex").first()
    assert settings.is_active is True

def test_assign_admin(db_connection, org_service):
    import uuid
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        username="spacexadmin",
        email="admin@spacex.com",
        roles=["user"],
        organization_id="spacex"
    )
    user.save()
    
    schema = OrgCreateSchema(
        organization_id="spacex",
        name="SpaceX",
        display_name="SpaceX"
    )
    org_service.create_org(schema)
    
    res = org_service.assign_admin("spacex", user_id)
    assert res.admin_user_id == user_id
    
    # Verify role promotion
    user_updated = User.objects(id=user_id).first()
    assert "admin" in user_updated.roles

def test_org_management_routes(db_connection):
    from app import create_app
    from unittest.mock import patch
    with patch("mongoengine.connect") as mock_connect:
        flask_app = create_app()
        client = flask_app.test_client()

        # 1. Superadmin Token
        with flask_app.app_context():
            superadmin_token = create_access_token(
                identity="sa_user",
                additional_claims={"roles": ["superadmin"], "organization_id": "system"}
            )
            user_token = create_access_token(
                identity="norm_user",
                additional_claims={"roles": ["user"], "organization_id": "spacex"}
            )

        headers_sa = {"Authorization": f"Bearer {superadmin_token}"}
        headers_user = {"Authorization": f"Bearer {user_token}"}

        # 2. Try POST with standard user (Forbidden)
        payload = {
            "organization_id": "nasa",
            "name": "National Aeronautics and Space Admin",
            "display_name": "NASA"
        }
        resp = client.post("/mahasangraha/api/v1/admin/orgs/", json=payload, headers=headers_user)
        assert resp.status_code == 403

        # 3. Create Org as Superadmin
        resp = client.post("/mahasangraha/api/v1/admin/orgs/", json=payload, headers=headers_sa)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["organization_id"] == "nasa"

        # 4. List Orgs as Superadmin
        resp = client.get("/mahasangraha/api/v1/admin/orgs/", headers=headers_sa)
        assert resp.status_code == 200
        assert len(resp.get_json()["data"]) >= 1

        # 5. Suspend Org
        resp = client.put("/mahasangraha/api/v1/admin/orgs/nasa/status", json={"status": "suspended"}, headers=headers_sa)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "suspended"

        # 6. Test middleware suspension block for standard user of suspended org
        with flask_app.app_context():
            suspended_user_token = create_access_token(
                identity="nasa_user",
                additional_claims={"roles": ["user"], "organization_id": "nasa"}
            )
        headers_nasa = {"Authorization": f"Bearer {suspended_user_token}"}
        
        # Attempting to call a protected route (e.g. GET /mahasangraha/api/v1/projects) should trigger RBAC and 403 because org is suspended.
        resp = client.get("/mahasangraha/api/v1/projects", headers=headers_nasa)
        assert resp.status_code == 403
        assert "suspended" in resp.get_json()["error"]["message"].lower()


