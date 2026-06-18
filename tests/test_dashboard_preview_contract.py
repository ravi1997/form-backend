import uuid

from flask_jwt_extended import create_access_token

from models.dashboard import Dashboard, DashboardWidget
from models.user import User
from routes.v1.dashboard_route import dashboard_bp


def test_dashboard_canvas_include_data_returns_resolved_widgets(app, db_connection, mocker):
    try:
        app.register_blueprint(
            dashboard_bp, url_prefix="/mahasangraha/api/v1/dashboards"
        )
    except AssertionError:
        pass

    with app.app_context():
        user = User(
            id=uuid.uuid4(),
            username="dash_preview",
            email="dash-preview@test.com",
            user_type="employee",
            is_active=True,
            roles=["admin"],
            organization_id="org-preview",
        )
        user.save()

        token = create_access_token(
            identity=str(user.id),
            additional_claims={
                "roles": ["admin"],
                "organization_id": "org-preview",
                "org_id": "org-preview",
            },
        )
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        client = app.test_client()

        dashboard = Dashboard(
            id=uuid.uuid4(),
            title="Preview Dashboard",
            slug="preview-dashboard",
            organization_id="org-preview",
            created_by=str(user.id),
            widgets=[
                DashboardWidget(
                    title="Score Widget",
                    type="kpi_card",
                )
            ],
        ).save()

        mocker.patch(
            "routes.v1.dashboard_route.resolve_widget_data",
            return_value={
                "id": str(dashboard.widgets[0].id),
                "title": "Score Widget",
                "type": "kpi_card",
                "data": {"value": 42},
            },
        )

        resp = client.get(
            f"/mahasangraha/api/v1/dashboards/{dashboard.id}/canvas?include_data=1",
            headers=headers,
        )
        assert resp.status_code == 200

        payload = resp.get_json()["data"]
        assert payload["widgets"][0]["data"]["value"] == 42
        assert payload["widgets"][0]["title"] == "Score Widget"

        resp = client.get(
            f"/mahasangraha/api/v1/dashboards/{dashboard.slug}",
            headers=headers,
        )
        assert resp.status_code == 200
        slug_payload = resp.get_json()["data"]
        assert slug_payload["widgets"][0]["data"]["value"] == 42
