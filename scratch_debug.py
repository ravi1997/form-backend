from app import create_app
from models.User import User
from models.Form import Form, Project
from models.Dashboard import Dashboard, DashboardWidget
from services.dashboard_service import DashboardService
import uuid

app = create_app()
with app.app_context():
    # Setup project and form
    project_id = str(uuid.uuid4())
    form_id = str(uuid.uuid4())

    project = Project(
        id=project_id,
        title="Phase 3 Project",
        organization_id="org-phase3",
    ).save()

    form = Form(
        id=form_id,
        title="Phase 3 Form",
        slug="phase3-form",
        organization_id="org-phase3",
        created_by="some-user",
        project=project,
        status="published",
    ).save()

    dashboard_id = uuid.uuid4()
    dashboard = Dashboard(
        id=dashboard_id,
        title="Phase 3 Dashboard",
        slug="phase3-dashboard",
        organization_id="org-phase3",
        created_by="some-user",
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

    # Retrieve from DB
    fetched = Dashboard.objects(slug="phase3-dashboard").first()
    print("Fetched from DB widgets form_ref class:", fetched.widgets[0].form_ref.__class__.__name__)
    
    doc_dict = fetched.to_dict()
    print("fetched.to_dict():", doc_dict)
    
    from services.base import BaseService
    svc = DashboardService()
    try:
        schema = svc._to_schema(fetched)
        print("Schema output widgets:", [w.model_dump() for w in schema.widgets])
    except Exception as e:
        print("Error in _to_schema:", e)
