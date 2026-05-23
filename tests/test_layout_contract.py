from schemas.form import FormSchema
from services.section_service import SectionService


def test_form_schema_accepts_ui_type_and_sections_without_overwriting_section_layout():
    form = FormSchema(
        title="Layout Contract",
        slug="layout-contract",
        organization_id="org-1",
        created_by="user-1",
        ui_type="grid-cols-3",
        sections=[
            {
                "title": "Personal",
                "layout": "accordion",
                "grid_columns": 2,
                "questions": [],
            }
        ],
    )

    assert form.ui_type == "grid-cols-3"
    assert form.sections[0].layout == "accordion"


def test_section_layout_does_not_require_form_ui_type():
    section = SectionService.normalize_section_tree(
        {"title": "Internal Grid", "layout": "grid", "gridColumns": 3}
    )

    assert section["layout"] == "grid"
    assert section["grid_columns"] == 3
    assert "ui_type" not in section


def test_legacy_ui_layout_type_maps_to_section_layout_and_is_mirrored():
    section = SectionService.normalize_section_tree(
        {"title": "Legacy", "ui": {"layout_type": "tabbed"}}
    )

    assert section["layout"] == "tabbed"
    assert section["ui"]["layout_type"] == "tabbed"


def test_nested_sub_section_layouts_are_preserved_recursively():
    section = SectionService.normalize_section_tree(
        {
            "title": "Parent",
            "layout": "cards",
            "sections": [
                {
                    "title": "Child",
                    "ui": {"layoutType": "wizard"},
                    "gridColumns": 2,
                    "style": {"background": "#fff"},
                    "logic": {"visibility": "always"},
                    "questions": [{"label": "Name", "field_type": "input"}],
                }
            ],
        }
    )

    child = section["sections"][0]
    assert section["layout"] == "cards"
    assert child["layout"] == "wizard"
    assert child["ui"]["layout_type"] == "wizard"
    assert child["grid_columns"] == 2
    assert child["style"] == {"background": "#fff"}
    assert child["logic"] == {"visibility": "always"}
    assert child["questions"][0]["label"] == "Name"
