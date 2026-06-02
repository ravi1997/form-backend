import pytest
import uuid
import json
from datetime import datetime, timezone
from flask_jwt_extended import create_access_token
from bson.binary import Binary, UuidRepresentation
from models.User import User
from models.Form import Form, Project
from models.Response import FormResponse
from models.Dashboard import Dashboard, DashboardWidget
from models.Workflow import ApprovalWorkflow, WorkflowStep
from models.WorkflowInstance import WorkflowInstance
from services.analytics_cache import analytics_cache
from workers.event_listener import handle_form_submitted
from routes.v1.form.responses import form_bp
from routes.v1.dashboard_route import dashboard_bp
from routes.v1.workflow_route import workflow_bp

def test_phase3_completion(app, db_connection):
    # Register blueprints if not registered
    try:
        app.register_blueprint(
            form_bp, url_prefix="/mahasangraha/api/v1/projects/<project_id>/forms"
        )
        app.register_blueprint(
            dashboard_bp, url_prefix="/mahasangraha/api/v1/dashboards"
        )
        app.register_blueprint(
            workflow_bp, url_prefix="/mahasangraha/api/v1/workflows"
        )
    except AssertionError:
        pass

    with app.app_context():
        # 1. SETUP USER AND AUTH HEADERS
        user = User(
            id=uuid.uuid4(),
            username="phase3_tester",
            email="phase3@test.com",
            user_type="employee",
            is_active=True,
            roles=["admin"],
            organization_id="org-phase3",
        )
        user.save()

        token = create_access_token(
            identity=str(user.id),
            additional_claims={"roles": ["admin"], "organization_id": "org-phase3", "org_id": "org-phase3"},
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        client = app.test_client()

        # 2. SETUP PROJECT AND FORM
        project_id = uuid.uuid4()
        form_id = uuid.uuid4()

        project = Project(
            id=project_id,
            title="Phase 3 Project",
            slug="phase3-project",
            organization_id="org-phase3",
            created_by=str(user.id),
        ).save()

        form = Form(
            id=form_id,
            title="Phase 3 Form",
            slug="phase3-form",
            organization_id="org-phase3",
            created_by=str(user.id),
            project=project,
            status="published",
        ).save()

        # --- TEST 1: FORM ENGINE OFFLINE SYNC ---
        # Sync three responses (two new, one invalid)
        sync_payload = {
            "conflict_resolution": "server_wins",
            "submissions": [
                {
                    "idempotency_key": "sync-key-1",
                    "data": {"status": "completed", "score": 85}
                },
                {
                    "idempotency_key": "sync-key-2",
                    "data": {"status": "pending", "score": 90}
                },
                {
                    # Missing idempotency key
                    "data": {"status": "draft"}
                }
            ]
        }

        sync_url = f"/mahasangraha/api/v1/projects/{project_id}/forms/{form_id}/responses/sync"
        resp = client.post(sync_url, headers=headers, data=json.dumps(sync_payload))
        assert resp.status_code == 200
        res_data = resp.get_json()["data"]["results"]
        assert len(res_data) == 3
        assert res_data[0]["status"] == "created"
        assert res_data[1]["status"] == "created"
        assert res_data[2]["status"] == "failed"

        response_id_1 = res_data[0]["response_id"]

        # Conflict resolution test: server_wins vs client_wins
        conflict_payload_server = {
            "conflict_resolution": "server_wins",
            "submissions": [
                {
                    "idempotency_key": "sync-key-1",
                    "data": {"status": "completed", "score": 99}  # Modified score
                }
            ]
        }
        resp = client.post(sync_url, headers=headers, data=json.dumps(conflict_payload_server))
        res_data_server = resp.get_json()["data"]["results"]
        assert res_data_server[0]["status"] == "conflict_resolved_server"
        
        # Verify db wasn't updated
        db_resp = FormResponse.objects.get(id=response_id_1)
        assert db_resp.data["score"] == 85

        conflict_payload_client = {
            "conflict_resolution": "client_wins",
            "submissions": [
                {
                    "idempotency_key": "sync-key-1",
                    "data": {"status": "completed", "score": 100}  # Modified score
                }
            ]
        }
        resp = client.post(sync_url, headers=headers, data=json.dumps(conflict_payload_client))
        res_data_client = resp.get_json()["data"]["results"]
        assert res_data_client[0]["status"] == "conflict_resolved_client"

        # Verify db WAS updated
        db_resp = FormResponse.objects.get(id=response_id_1)
        assert db_resp.data["score"] == 100

        # --- TEST 2: ANALYSIS ENGINE CACHING ---
        # Set a cache key and verify invalidation
        cache_key = analytics_cache._generate_cache_key(str(form_id), "summary", None, "org-phase3")
        analytics_cache.set(str(form_id), "summary", {"cached_metric": 42}, None, 300, "org-phase3")
        assert analytics_cache.redis_client.get(cache_key) is not None

        # Modifying response should invalidate cache
        db_resp.data["score"] = 95
        from services.response_service import FormResponseService, FormResponseUpdateSchema
        response_service = FormResponseService()
        response_service.update(str(db_resp.id), FormResponseUpdateSchema(data=db_resp.data), "org-phase3")

        # Cache should be invalidated now
        assert analytics_cache.redis_client.get(cache_key) is None

        # --- TEST 3: DASHBOARD ENGINE (Filtering, Sharing, Exporting) ---
        dashboard_id = uuid.uuid4()
        # Create dashboard with a widget targeting the form
        dashboard = Dashboard(
            id=dashboard_id,
            title="Phase 3 Dashboard",
            slug="phase3-dashboard",
            organization_id="org-phase3",
            created_by=str(user.id),
            widgets=[
                DashboardWidget(
                    title="Score Widget",
                    type="counter",
                    form_ref=form,
                    group_by_field="status",
                    filters={"status": "completed"}
                )
            ]
        ).save()

        # Dynamic filter: filter completed status (returns count=2 for score=100 & score=90)
        # Verify get dashboard with dynamic filter
        dashboard_url = "/mahasangraha/api/v1/dashboards/phase3-dashboard"
        resp = client.get(f"{dashboard_url}?filter_status=completed", headers=headers)
        assert resp.status_code == 200
        dash_data = resp.get_json()["data"]
        # The Score Widget value should count only completed responses
        assert dash_data["widgets"][0]["data"] >= 1

        # Share dashboard endpoint
        share_url = f"/mahasangraha/api/v1/dashboards/{dashboard_id}/share"
        resp = client.post(share_url, headers=headers)
        assert resp.status_code == 200
        share_token = resp.get_json()["data"]["share_token"]
        assert share_token is not None

        # Public share endpoint (NO AUTH HEADERS!)
        shared_view_url = f"/mahasangraha/api/v1/dashboards/shared/{share_token}"
        resp = client.get(shared_view_url)
        assert resp.status_code == 200
        shared_dash = resp.get_json()["data"]
        assert shared_dash["title"] == "Phase 3 Dashboard"

        # Export dashboard endpoints
        export_url = f"/mahasangraha/api/v1/dashboards/{dashboard_id}/export"
        resp = client.get(f"{export_url}?format=json", headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["title"] == "Phase 3 Dashboard"

        resp = client.get(f"{export_url}?format=csv", headers=headers)
        assert resp.status_code == 200
        assert "Dashboard Title,Phase 3 Dashboard" in resp.get_data(as_text=True)

        # --- TEST 4: WORKFLOW ENGINE AUTO-TRIGGER ---
        # Create an active workflow definition for the form
        workflow_def = ApprovalWorkflow(
            name="Submit Approval Workflow",
            organization_id="org-phase3",
            trigger_form_id=str(form_id),
            status="active",
            steps=[
                WorkflowStep(
                    step_name="Manager Review",
                    order=1,
                    approvers=[str(user.id)],
                    min_approvals_required=1
                )
            ],
            created_by=str(user.id)
        ).save()

        # Simulate form.submitted event
        event_payload = {
            "form_id": str(form_id),
            "response_id": str(db_resp.id),
            "organization_id": "org-phase3",
            "data": db_resp.data
        }
        handle_form_submitted(event_payload)

        # Check that a WorkflowInstance was automatically created
        wf_instance = WorkflowInstance.objects(
            resource_type="form_response",
            resource_id=str(db_resp.id),
            organization_id="org-phase3",
            is_deleted=False
        ).first()

        assert wf_instance is not None
        assert wf_instance.workflow_definition.id == workflow_def.id
        assert wf_instance.status == "pending"
