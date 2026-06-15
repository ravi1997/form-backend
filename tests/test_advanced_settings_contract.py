import pytest
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from models.Form import Form
from routes.v1.form.form import import_form
from routes.v1.forms_misc_route import check_slug
from routes.v1.view_route import view_form
from schemas.form import FormSchema
from services.form_service import FormService


def test_form_schema_accepts_advanced_settings_and_syncs_top_level_fields():
    form = FormSchema(
        title="Advanced Contract",
        slug="legacy-slug",
        organization_id="org-1",
        created_by="user-1",
        advanced_settings={
            "slug": "ADVANCED-SLUG",
            "localeDefault": "fr_FR",
            "fallbackLanguage": "fr",
            "internalCode": "ADV_1",
            "apiIdentifiers": {"webhook": "WH-1"},
            "experimentalFlags": {"beta": True},
        },
    )

    assert form.slug == "advanced-slug"
    assert form.default_language == "fr-FR"
    assert form.advanced_settings.slug == "advanced-slug"
    assert form.advanced_settings.locale_default == "fr-FR"
    assert form.advanced_settings.fallback_language == "fr"
    assert form.advanced_settings.internal_code == "ADV_1"
    assert form.advanced_settings.api_identifiers == {"webhook": "WH-1"}
    assert form.advanced_settings.experimental_flags == {"beta": True}


def test_advanced_settings_rejects_invalid_slug():
    with pytest.raises(ValidationError):
        FormSchema(
            title="Invalid Advanced Contract",
            slug="invalid-advanced-contract",
            organization_id="org-1",
            created_by="user-1",
            advanced_settings={"slug": "bad slug!"},
        )


def test_sync_form_canvas_persists_advanced_settings_without_clearing_sections():
    service = FormService()
    mock_form = MagicMock()
    mock_form.id = "form-1"
    mock_form.organization_id = "org-1"
    mock_form.slug = "legacy-slug"
    mock_form.default_language = "en"
    mock_form.sections = ["existing-section"]
    mock_form.slug_history = []
    mock_form.advanced_settings = {"slug": "legacy-slug"}
    mock_form.save = MagicMock()

    mock_query = MagicMock()
    mock_query.first.return_value = mock_form

    with patch.object(
        FormService, "_validate_advanced_settings_uniqueness", return_value=None
    ), patch("services.form_service.Form.objects", return_value=mock_query), patch(
        "services.form_service.FormService.sync_draft_version"
    ) as sync_draft_version:
        sync_draft_version.return_value = MagicMock()

        updated = service.sync_form_canvas(
            "form-1",
            "org-1",
            {
                "advancedSettings": {
                    "slug": "new-slug",
                    "localeDefault": "fr-fr",
                    "internalCode": "ADV-2",
                    "apiIdentifiers": {"webhook": "WH-2"},
                    "experimentalFlags": {"beta": True},
                }
            },
        )

    assert updated is mock_form
    assert mock_form.sections == ["existing-section"]
    assert mock_form.slug == "new-slug"
    assert mock_form.default_language == "fr-FR"
    assert mock_form.advanced_settings["slug"] == "new-slug"
    assert mock_form.advanced_settings["locale_default"] == "fr-FR"
    assert mock_form.advanced_settings["internal_code"] == "ADV-2"
    assert mock_form.slug_history == ["legacy-slug"]
    mock_form.save.assert_called()
    sync_draft_version.assert_called_once_with("form-1", "org-1")


def test_import_form_uses_advanced_settings_slug_and_locale(db_connection, app):
    mock_user = MagicMock(id="user-1", organization_id="org-1")

    with app.test_request_context(
        "/mahasangraha/api/v1/forms/import",
        method="POST",
        json={
            "title": "Imported Advanced Form",
            "advancedSettings": {
                "slug": "imported-advanced",
                "localeDefault": "fr-fr",
                "fallbackLanguage": "fr",
                "internalCode": "ADV-3",
                "apiIdentifiers": {"webhook": "WH-3"},
                "experimentalFlags": {"beta": True},
            },
        },
    ), patch("flask_jwt_extended.view_decorators.verify_jwt_in_request"), patch(
        "utils.security_helpers.verify_jwt_in_request"
    ), patch(
        "routes.v1.form.form.get_current_user", return_value=mock_user
    ):
        response, status = import_form()

    assert status == 201
    saved_form = Form.objects(slug="imported-advanced").first()
    assert saved_form is not None
    assert saved_form.default_language == "fr-FR"
    assert saved_form.advanced_settings["slug"] == "imported-advanced"
    assert saved_form.advanced_settings["locale_default"] == "fr-FR"
    assert saved_form.advanced_settings["fallback_language"] == "fr"
    assert saved_form.advanced_settings["internal_code"] == "ADV-3"
    assert saved_form.advanced_settings["api_identifiers"] == {"webhook": "WH-3"}
    assert saved_form.advanced_settings["experimental_flags"] == {"beta": True}


def test_check_slug_treats_slug_history_as_reserved(db_connection, app):
    Form(
        title="Advanced Lookup",
        slug="current-slug",
        slug_history=["retired-slug"],
        organization_id="org-1",
        created_by="user-1",
    ).save()

    with app.test_request_context(
        "/mahasangraha/api/v1/forms/slug-available?slug=retired-slug",
        method="GET",
    ), patch("flask_jwt_extended.view_decorators.verify_jwt_in_request"), patch(
        "utils.security_helpers.verify_jwt_in_request"
    ):
        response, status = check_slug()

    assert status == 200
    assert response.get_json()["data"]["available"] is False


def test_check_slug_allows_the_current_form_slug_when_editing(db_connection, app):
    form = Form(
        title="Advanced Lookup",
        slug="current-slug",
        slug_history=["retired-slug"],
        organization_id="org-1",
        created_by="user-1",
    ).save()

    with app.test_request_context(
        f"/mahasangraha/api/v1/forms/slug-available?slug=current-slug&form_id={form.id}",
        method="GET",
    ), patch("flask_jwt_extended.view_decorators.verify_jwt_in_request"), patch(
        "utils.security_helpers.verify_jwt_in_request"
    ):
        response, status = check_slug()

    assert status == 200
    assert response.get_json()["data"]["available"] is True


def test_view_form_uses_fallback_translation_when_requested_language_missing(app):
    mock_form = MagicMock()
    mock_form.id = "form-1"
    mock_form.organization_id = "org-1"
    mock_form.is_public = True
    mock_form.status = "published"
    mock_form.publish_at = None
    mock_form.expires_at = None
    mock_form.to_mongo.return_value.to_dict.return_value = {
        "_id": "form-1",
        "title": "Base Title",
        "description": "Base Description",
        "help_text": "Base Help",
        "is_public": True,
        "status": "published",
        "default_language": "en-US",
        "supported_languages": ["en-US", "fr"],
        "translations": {
            "fr": {"title": "Titre FR"},
            "en": {"title": "Title EN"},
        },
        "advanced_settings": {
            "locale_default": "fr-FR",
            "fallback_language": "fr",
        },
    }

    def render_template_side_effect(template_name, **kwargs):
        return kwargs["form"]

    def apply_translations_side_effect(form_dict, lang):
        translated = dict(form_dict)
        translated["title"] = f"translated-{lang}"
        return translated

    mock_objects = MagicMock()
    mock_objects.get.return_value = mock_form

    with app.test_request_context("/mahasangraha/api/v1/view/form-1?lang=fr-CA"):
        with patch("routes.v1.view_route.Form.objects", new=mock_objects), patch(
            "routes.v1.view_route.render_template",
            side_effect=render_template_side_effect,
        ), patch(
            "routes.v1.view_route.apply_translations",
            side_effect=apply_translations_side_effect,
        ) as apply_translations_mock:
            rendered = view_form("form-1")

    assert rendered["title"] == "translated-fr"
    apply_translations_mock.assert_called_once()
    assert apply_translations_mock.call_args.args[1] == "fr"
