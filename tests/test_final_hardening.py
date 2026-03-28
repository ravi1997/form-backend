import pytest
from unittest.mock import MagicMock, patch
from services.form_validation_service import FormValidationService
from models.Form import Form, FormVersion, SnapshotStore
from flask import Flask
from routes.v1.form.export import stream_form_csv

def test_aggregate_repeat_calculations():
    # Setup a form with a repeat section and a sum calculation
    mock_form = MagicMock(id="form1", active_version_id="v1", organization_id="org1")
    mock_version = MagicMock(id="v1")
    
    # members is repeatable, has 'age' field
    # total_age = sum(members.age)
    mock_version.snapshot = {
        "sections": [{
            "variable_name": "members",
            "logic": {"is_repeatable": True},
            "questions": [{"variable_name": "age", "field_type": "number"}]
        }, {
            "questions": [{
                "variable_name": "total_age",
                "field_type": "number",
                "logic": {"calculated_value": "sum(members.age)"}
            }]
        }]
    }
    
    # Mock property
    type(mock_version).resolved_snapshot = mock_version.snapshot

    with patch("models.Form.objects") as mock_form_objs, \
         patch("models.FormVersion.objects") as mock_version_objs:
        
        mock_form_objs.return_value.first.return_value = mock_form
        mock_version_objs.return_value.first.return_value = mock_version
        
        payload = {
            "members": [{"age": 10}, {"age": 20}, {"age": 5}]
        }
        
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1",
            payload=payload,
            organization_id="org1"
        )
        
        assert valid
        assert calc["total_age"] == 35
        assert cleaned["total_age"] == 35

def test_circular_dependency_parsing():
    # A -> B, B -> A
    questions = [
        {"variable_name": "A", "logic": {"calculated_value": "B + 1"}},
        {"variable_name": "B", "logic": {"calculated_value": "A + 1"}}
    ]
    
    with pytest.raises(ValueError) as excinfo:
        FormValidationService._get_evaluation_order(questions)
    assert "Circular calculated field dependency" in str(excinfo.value)

def test_missing_dependency_graceful_handling():
    # total = a + b, but b is missing from payload and not a calculated field
    mock_form = MagicMock(id="form1", active_version_id="v1", organization_id="org1")
    mock_version = MagicMock(id="v1")
    mock_version.snapshot = {
        "sections": [{
            "questions": [
                {"variable_name": "a", "field_type": "number"},
                {"variable_name": "total", "field_type": "number", "logic": {"calculated_value": "a + b"}}
            ]
        }]
    }
    type(mock_version).resolved_snapshot = mock_version.snapshot

    with patch("models.Form.objects") as mock_form_objs, \
         patch("models.FormVersion.objects") as mock_version_objs:
        
        mock_form_objs.return_value.first.return_value = mock_form
        mock_version_objs.return_value.first.return_value = mock_version
        
        # 'b' is missing
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1",
            payload={"a": 10},
            organization_id="org1"
        )
        
        # Calculation should fail but not crash validation
        assert not valid
        assert any("Calculation error" in str(e) for e in errors)

def test_streaming_export_generator():
    mock_form = MagicMock(id="form1", title="Test Form")
    mock_form.active_version = None
    
    mock_response = MagicMock()
    mock_response.id = "r1"
    mock_response.submitted_by = "user1"
    mock_response.submitted_at = None
    mock_response.status = "submitted"
    mock_response.data = {"field1": "val1"}
    
    responses = [mock_response]
    
    gen = stream_form_csv(mock_form, responses)
    header = next(gen)
    assert "response_id" in header
    assert "data (raw)" in header
    
    row = next(gen)
    assert "r1" in row
    assert "val1" in row

def test_global_tenant_isolation_queryset():
    from models.Form import Form
    from flask import Flask
    from mongoengine import connect, disconnect
    from mongoengine.queryset.visitor import Q
    
    app = Flask(__name__)
    mock_user = MagicMock()
    mock_user.organization_id = "org_A"
    mock_user.roles = ["user"]
    
    with app.app_context():
        with patch("models.base.current_user", mock_user), \
             patch("models.base.has_request_context", return_value=True), \
             patch("mongoengine.Document._get_collection") as mock_get_coll:
            
            # Setup mock collection to avoid connection
            mock_coll = MagicMock()
            mock_get_coll.return_value = mock_coll
            
            # We need a QuerySet instance
            from models.base import TenantIsolatedSoftDeleteQuerySet
            qs = TenantIsolatedSoftDeleteQuerySet(Form, mock_coll)
            
            # Call the QuerySet with a filter
            # qs(organization_id="org_B") should trigger the __call__ logic
            new_qs = qs(organization_id="org_B")
            
            # Check if organization_id was overwritten in the internal query
            # In MongoEngine, filters are stored in _query_obj
            query_dict = new_qs._query
            assert query_dict["organization_id"] == "org_A"
