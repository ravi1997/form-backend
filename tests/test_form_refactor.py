import pytest
from unittest.mock import MagicMock, patch
from services.form_validation_service import FormValidationService
from models.Form import Form, FormVersion

def test_unified_validation_simple():
    # Mock Form and FormVersion
    mock_form = MagicMock()
    mock_form.id = "form1"
    mock_form.active_version_id = "v1"
    mock_form.organization_id = "org1"
    
    mock_version = MagicMock()
    mock_version.id = "v1"
    mock_version.snapshot = {
        "sections": [{
            "title": "General",
            "questions": [{
                "label": "Name",
                "field_type": "input",
                "variable_name": "name",
                "validation": {"is_required": True}
            }]
        }]
    }
    
    with patch("models.Form.objects") as mock_form_objs, \
         patch("models.FormVersion.objects") as mock_version_objs:
        
        mock_form_objs.return_value.first.return_value = mock_form
        mock_version_objs.return_value.first.return_value = mock_version
        
        # Validate - Missing required field
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1",
            payload={},
            organization_id="org1"
        )
        assert not valid
        assert any(e["field"] == "name" for e in errors)
        
        # Validate - Success
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1",
            payload={"name": "John"},
            organization_id="org1"
        )
        assert valid
        assert cleaned["name"] == "John"

def test_calculated_fields():
    mock_form = MagicMock(id="form1", active_version_id="v1", organization_id="org1")
    mock_version = MagicMock(id="v1")
    mock_version.snapshot = {
        "sections": [{
            "questions": [
                {"variable_name": "price", "field_type": "number"},
                {"variable_name": "qty", "field_type": "number"},
                {"variable_name": "total", "field_type": "number", "logic": {"calculated_value": "price * qty"}}
            ]
        }]
    }
    
    with patch("models.Form.objects") as mock_form_objs, \
         patch("models.FormVersion.objects") as mock_version_objs:
        
        mock_form_objs.return_value.first.return_value = mock_form
        mock_version_objs.return_value.first.return_value = mock_version
        
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1",
            payload={"price": 10, "qty": 5},
            organization_id="org1"
        )
        
        assert valid
        assert calc["total"] == 50
        assert cleaned["total"] == 50

def test_cascading_selects():
    mock_form = MagicMock(id="form1", active_version_id="v1", organization_id="org1")
    mock_version = MagicMock(id="v1")
    mock_version.snapshot = {
        "sections": [{
            "questions": [
                {
                    "variable_name": "country", 
                    "field_type": "select",
                    "options": [
                        {"option_value": "India"},
                        {"option_value": "USA"}
                    ]
                },
                {
                    "variable_name": "city",
                    "field_type": "select",
                    "logic": {"parent_variable_name": "country"},
                    "options": [
                        {"option_value": "Mumbai", "parent_option_value": "India"},
                        {"option_value": "NY", "parent_option_value": "USA"}
                    ]
                }
            ]
        }]
    }
    
    with patch("models.Form.objects") as mock_form_objs, \
         patch("models.FormVersion.objects") as mock_version_objs:
        
        mock_form_objs.return_value.first.return_value = mock_form
        mock_version_objs.return_value.first.return_value = mock_version
        
        # Invalid: Mumbai for USA
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1",
            payload={"country": "USA", "city": "Mumbai"},
            organization_id="org1"
        )
        assert not valid
        assert any(e["field"] == "city" for e in errors)
        
        # Valid: Mumbai for India
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1",
            payload={"country": "India", "city": "Mumbai"},
            organization_id="org1"
        )
        assert valid
        assert cleaned["city"] == "Mumbai"
