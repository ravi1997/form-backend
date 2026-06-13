from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.template_service import FormBlueprintService


class _Query(list):
    pass


@patch("services.template_service.FormBlueprint")
def test_list_official_blueprints_uses_model_query(mock_model):
    blueprint = SimpleNamespace(id="bp-1", name="General Intake", is_official=True)
    mock_model.objects.return_value = _Query([blueprint])

    service = FormBlueprintService()
    service._to_schema = lambda document: {"id": document.id, "name": document.name}
    items = service.list_official_blueprints()

    assert items == [{"id": "bp-1", "name": "General Intake"}]


@patch("services.template_service.FormBlueprint")
@patch("services.template_service.Form")
def test_instantiate_blueprint_creates_form(mock_form, mock_blueprint_model):
    blueprint = SimpleNamespace(
        id="bp-1",
        name="Patient Intake",
        sections=["section-1"],
    )
    mock_blueprint_model.objects.return_value.first.return_value = blueprint
    created_form = MagicMock()
    created_form.id = "form-1"
    mock_form.return_value = created_form

    service = FormBlueprintService()
    result = service.instantiate_blueprint("bp-1", "org-1", "user-1")

    assert result == created_form
    mock_form.assert_called_once()
    created_form.save.assert_called_once()
