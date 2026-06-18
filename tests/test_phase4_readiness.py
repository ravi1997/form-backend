import pytest
import uuid
from datetime import datetime, timedelta, timezone
from utils.exceptions import ValidationError
from models.user import User
from models.form import Form, Project
from models.response import FormResponse
from models.TenantSettings import TenantSettings
from models.LegalHold import LegalHold
from models.OidcUserMapping import OidcUserMapping
from services.compliance_service import ComplianceService
from services.tenant_service import TenantService
from services.oidc_service import OidcService
from services.form_service import FormService
from services.response_service import FormResponseService
from tasks.compliance_tasks import execute_tenant_retention_policy


def test_oidc_user_mapping(app, db_connection):
    with app.app_context():
        org_id = "org-oidc-test"
        provider = "google"
        code = "mock-auth-code-123"
        mock_claims = {
            "sub": "google-sub-123456",
            "email": "oidc-user@oidctest.com",
            "preferred_username": "oidc_tester",
            "roles": ["user", "manager"]
        }

        service = OidcService()
        
        # 1. First time callback - should provision user and mapping
        user = service.handle_oidc_callback(org_id, provider, code, mock_claims)
        assert user is not None
        assert user.email == "oidc-user@oidctest.com"
        assert user.username == "oidc_tester"
        assert "manager" in user.roles

        mapping = OidcUserMapping.objects(provider=provider, subject_id="google-sub-123456").first()
        assert mapping is not None
        assert mapping.user_id == user.id
        assert mapping.email == "oidc-user@oidctest.com"

        # 2. Second time callback - should return existing user without re-creating
        user_again = service.handle_oidc_callback(org_id, provider, code, mock_claims)
        assert user_again.id == user.id

        # Verify query count
        assert User.objects(email="oidc-user@oidctest.com").count() == 1


def test_legal_holds(app, db_connection):
    with app.app_context():
        org_id = "org-hold-test"
        
        # Setup form
        form_id = str(uuid.uuid4())
        form = Form(
            id=form_id,
            title="Hold Test Form",
            slug="hold-test-form",
            organization_id=org_id,
            created_by="tester",
            status="published"
        ).save()

        # Setup response
        resp_id = str(uuid.uuid4())
        response = FormResponse(
            id=resp_id,
            organization_id=org_id,
            form=form_id,
            data={"field1": "value1"},
            submitted_by="tester",
            idempotency_key=str(uuid.uuid4())
        ).save()

        compliance = ComplianceService()
        form_service = FormService()
        response_service = FormResponseService()

        # 1. No holds - Deletion should work
        # Let's verify deleting a response works without hold
        resp2_id = str(uuid.uuid4())
        resp2 = FormResponse(
            id=resp2_id,
            organization_id=org_id,
            form=form_id,
            data={"field1": "value2"},
            submitted_by="tester",
            idempotency_key=str(uuid.uuid4())
        ).save()
        response_service.delete(resp2_id, org_id, hard_delete=True)
        assert FormResponse.objects(id=resp2_id).count() == 0

        # 2. Apply hold on Response
        compliance.apply_legal_hold(org_id, "response", resp_id, "Investigation", "compliance_officer")
        assert compliance.is_held("response", resp_id) is True

        # Try to delete response -> Should raise ValidationError
        with pytest.raises(ValidationError, match="Resource has an active legal hold and cannot be deleted."):
            response_service.delete(resp_id, org_id)

        # 3. Apply hold on Form
        compliance.apply_legal_hold(org_id, "form", form_id, "Investigation", "compliance_officer")
        assert compliance.is_held("form", form_id) is True

        # Try to delete form -> Should raise ValidationError
        with pytest.raises(ValidationError, match="Resource has an active legal hold and cannot be deleted."):
            form_service.delete(form_id, org_id)

        # Create another response under the same form.
        # Since the form is held, trying to delete this response should also fail!
        resp3_id = str(uuid.uuid4())
        resp3 = FormResponse(
            id=resp3_id,
            organization_id=org_id,
            form=form_id,
            data={"field1": "value3"},
            submitted_by="tester",
            idempotency_key=str(uuid.uuid4())
        ).save()

        with pytest.raises(ValidationError, match="Resource has an active legal hold on its parent form and cannot be deleted."):
            response_service.delete(resp3_id, org_id)

        # 4. Release holds and verify deletion is unblocked
        compliance.release_legal_hold(org_id, "response", resp_id, "compliance_officer")
        compliance.release_legal_hold(org_id, "form", form_id, "compliance_officer")
        
        assert compliance.is_held("response", resp_id) is False
        assert compliance.is_held("form", form_id) is False

        # Should delete response successfully now
        response_service.delete(resp_id, org_id, hard_delete=True)
        assert FormResponse.objects(id=resp_id).count() == 0


def test_retention_policy_scrub(app, db_connection):
    with app.app_context():
        org_id = "org-retention-test"
        
        # Setup tenant settings
        tenant_settings = TenantSettings.get_or_create(org_id)
        tenant_settings.retention_days = 30
        tenant_settings.save()

        form_id = str(uuid.uuid4())
        form = Form(
            id=form_id,
            title="Retention Form",
            slug="retention-form",
            organization_id=org_id,
            created_by="tester",
            status="published"
        ).save()

        # 1. Expired response (35 days old)
        expired_id = str(uuid.uuid4())
        expired_resp = FormResponse(
            id=expired_id,
            organization_id=org_id,
            form=form_id,
            data={"info": "expired"},
            submitted_by="tester",
            submitted_at=datetime.now(timezone.utc) - timedelta(days=35),
            idempotency_key=str(uuid.uuid4())
        ).save()

        # 2. Active response (5 days old)
        active_id = str(uuid.uuid4())
        active_resp = FormResponse(
            id=active_id,
            organization_id=org_id,
            form=form_id,
            data={"info": "active"},
            submitted_by="tester",
            submitted_at=datetime.now(timezone.utc) - timedelta(days=5),
            idempotency_key=str(uuid.uuid4())
        ).save()

        # 3. Expired but held response (40 days old, but under legal hold)
        held_expired_id = str(uuid.uuid4())
        held_expired_resp = FormResponse(
            id=held_expired_id,
            organization_id=org_id,
            form=form_id,
            data={"info": "held_expired"},
            submitted_by="tester",
            submitted_at=datetime.now(timezone.utc) - timedelta(days=40),
            idempotency_key=str(uuid.uuid4())
        ).save()

        compliance = ComplianceService()
        compliance.apply_legal_hold(org_id, "response", held_expired_id, "Prune Block Test", "system")

        # Recalculate usage
        TenantService().recalculate_usage(org_id)
        assert TenantSettings.get_or_create(org_id).usage_submissions_count == 3

        # Run Celery retention scrubbing task synchronously
        result = execute_tenant_retention_policy(org_id)
        assert result["pruned_count"] == 1
        assert result["held_count"] == 1
        assert expired_id in result["pruned_ids"]

        # Check DB states
        assert FormResponse.objects(id=expired_id).count() == 0
        assert FormResponse.objects(id=active_id).count() == 1
        assert FormResponse.objects(id=held_expired_id).count() == 1

        # Verify updated usage count
        assert TenantSettings.get_or_create(org_id).usage_submissions_count == 2


def test_tenant_quotas(app, db_connection):
    with app.app_context():
        org_id = "org-quota-test"
        
        # Limit to max 2 forms, max 2 submissions
        tenant_settings = TenantSettings.get_or_create(org_id)
        tenant_settings.max_forms = 2
        tenant_settings.max_submissions = 2
        tenant_settings.save()

        tenant_service = TenantService()

        # 1. Verify Form Quotas
        # Create Form 1 -> success
        Form(id=str(uuid.uuid4()), title="F1", slug="f1", organization_id=org_id, created_by="tester").save()
        tenant_service.check_form_quota(org_id)  # should not raise
        
        # Create Form 2 -> success
        Form(id=str(uuid.uuid4()), title="F2", slug="f2", organization_id=org_id, created_by="tester").save()
        
        # Check quota -> should raise ValidationError since we have 2/2 forms
        with pytest.raises(ValidationError, match="Form limit quota exceeded"):
            tenant_service.check_form_quota(org_id)

        # 2. Verify Submission Quotas
        form = Form.objects(organization_id=org_id).first()
        form_id = str(form.id)
        
        # Submission 1 -> success
        FormResponse(id=str(uuid.uuid4()), organization_id=org_id, form=form_id, data={"x": 1}, submitted_by="tester", idempotency_key=str(uuid.uuid4())).save()
        tenant_service.check_submission_quota(org_id)  # should not raise

        # Submission 2 -> success
        FormResponse(id=str(uuid.uuid4()), organization_id=org_id, form=form_id, data={"x": 2}, submitted_by="tester", idempotency_key=str(uuid.uuid4())).save()

        # Check quota -> should raise ValidationError since we have 2/2 submissions
        with pytest.raises(ValidationError, match="Submissions limit quota exceeded"):
            tenant_service.check_submission_quota(org_id)
