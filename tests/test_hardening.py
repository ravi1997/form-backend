import pytest
from unittest.mock import MagicMock, patch
from services.form_validation_service import FormValidationService
from models.Form import Form, FormVersion

def test_cross_tenant_denial():
    mock_form = MagicMock(id="form1", organization_id="org1")
    
    with patch("models.Form.objects") as mock_form_objs, \
         patch("models.FormVersion.objects") as mock_version_objs:
        mock_form_objs.return_value.first.return_value = mock_form
        mock_version_objs.return_value.first.return_value = None
        
        # Access with wrong org
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1",
            payload={},
            organization_id="org2" # Wrong org
        )
        assert not valid
        assert len(errors) > 0

def test_repeatable_section_validation():
    mock_form = MagicMock(id="form1", active_version_id="v1", organization_id="org1")
    mock_version = MagicMock(id="v1")
    mock_version.snapshot = {
        "sections": [{
            "variable_name": "members",
            "logic": {"is_repeatable": True, "repeat_min": 2},
            "questions": [{
                "variable_name": "name",
                "field_type": "input",
                "validation": {"is_required": True}
            }]
        }]
    }
    
    with patch("models.Form.objects") as mock_form_objs, \
         patch("models.FormVersion.objects") as mock_version_objs:
        
        mock_form_objs.return_value.first.return_value = mock_form
        mock_version_objs.return_value.first.return_value = mock_version
        
        # Fail: only 1 entry
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1",
            payload={"members": [{"name": "John"}]},
            organization_id="org1"
        )
        assert not valid
        assert any("Minimum 2 entries required" in str(e) for e in errors)
        
        # Success: 2 entries
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1",
            payload={"members": [{"name": "John"}, {"name": "Jane"}]},
            organization_id="org1"
        )
        assert valid
        assert len(cleaned["members"]) == 2

def test_complex_calculation_order():
    mock_form = MagicMock(id="form1", active_version_id="v1", organization_id="org1")
    mock_version = MagicMock(id="v1")
    # C depends on B, B depends on A
    mock_version.snapshot = {
        "sections": [{
            "questions": [
                {"variable_name": "C", "field_type": "number", "logic": {"calculated_value": "B + 1"}},
                {"variable_name": "A", "field_type": "number"},
                {"variable_name": "B", "field_type": "number", "logic": {"calculated_value": "A * 2"}}
            ]
        }]
    }
    
    with patch("models.Form.objects") as mock_form_objs, \
         patch("models.FormVersion.objects") as mock_version_objs:
        
        mock_form_objs.return_value.first.return_value = mock_form
        mock_version_objs.return_value.first.return_value = mock_version
        
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1",
            payload={"A": 10},
            organization_id="org1"
        )
        
        assert valid
        assert calc["B"] == 20
        assert calc["C"] == 21

def test_circular_dependency_detection():
    mock_form = MagicMock(id="form1", active_version_id="v1", organization_id="org1")
    mock_version = MagicMock(id="v1")
    # A depends on B, B depends on A
    mock_version.snapshot = {
        "sections": [{
            "questions": [
                {"variable_name": "A", "field_type": "number", "logic": {"calculated_value": "B + 1"}},
                {"variable_name": "B", "field_type": "number", "logic": {"calculated_value": "A + 1"}}
            ]
        }]
    }
    
    with patch("models.Form.objects") as mock_form_objs, \
         patch("models.FormVersion.objects") as mock_version_objs:
        
        mock_form_objs.return_value.first.return_value = mock_form
        mock_version_objs.return_value.first.return_value = mock_version
        
        with pytest.raises(ValueError) as excinfo:
            FormValidationService.validate_submission(
                form_id="form1",
                payload={"A": 1},
                organization_id="org1"
            )
        assert "Circular calculated field dependency" in str(excinfo.value)

def test_option_level_visibility():
    mock_form = MagicMock(id="form1", active_version_id="v1", organization_id="org1")
    mock_version = MagicMock(id="v1")
    mock_version.snapshot = {
        "sections": [{
            "questions": [
                {"variable_name": "role", "field_type": "input"},
                {
                    "variable_name": "access", 
                    "field_type": "select",
                    "options": [
                        {"option_value": "admin", "visibility_condition": {"source_id": "role", "operator": "equals", "comparison_value": "boss"}},
                        {"option_value": "user"}
                    ]
                }
            ]
        }]
    }
    
    with patch("models.Form.objects") as mock_form_objs, \
         patch("models.FormVersion.objects") as mock_version_objs:
        
        mock_form_objs.return_value.first.return_value = mock_form
        mock_version_objs.return_value.first.return_value = mock_version
        
        # Fail: 'admin' selected but role is not 'boss'
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1",
            payload={"role": "employee", "access": "admin"},
            organization_id="org1"
        )
        assert not valid
        assert any("hidden by conditions" in str(e) for e in errors)
        
        # Success: 'admin' selected and role is 'boss'
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1",
            payload={"role": "boss", "access": "admin"},
            organization_id="org1"
        )
        assert valid
