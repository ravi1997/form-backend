from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from mongoengine.queryset.visitor import Q
from logger.unified_logger import (
    app_logger,
    error_logger,
    audit_logger,
    get_logger,
    log_performance,
)
from logger.sla import enforce_sla
from services.base import BaseService
from services.access_control_service import AccessControlService
from utils.exceptions import ConflictError, NotFoundError, StateTransitionError
from utils.response_helper import FormSerializer
from models import Form, Project, Version, FormVersion, Section, QuickResponse
from schemas.form import (
    AdvancedSettingsSchema,
    DataExportSettingsSchema,
    FormSchema,
    ProjectSchema,
    QuickResponseSchema,
    SubmissionSettingsSchema,
)
from schemas.base import InboundPayloadSchema
from services.section_service import SectionService

logger = get_logger(__name__)


class FormCreateSchema(FormSchema, InboundPayloadSchema):
    pass


class FormUpdateSchema(FormSchema, InboundPayloadSchema):
    pass


from services.event_bus import event_bus


class FormService(BaseService):
    def __init__(self):
        super().__init__(model=Form, schema=FormSchema)

    @staticmethod
    def _normalize_slug(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        slug = str(value).strip().lower()
        return slug or None

    @staticmethod
    def _normalize_locale(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip().replace("_", "-")
        if not text:
            return None
        parts = [part for part in text.split("-") if part]
        if not parts:
            return None
        language = parts[0].lower()
        if len(parts) == 1:
            return language
        region = parts[1].upper() if len(parts[1]) == 2 else parts[1].lower()
        rest = [part.lower() for part in parts[2:]]
        return "-".join([language, region, *rest]) if rest else "-".join(
            [language, region]
        )

    @staticmethod
    def _snapshot_quick_response(quick_response: Any) -> Dict[str, Any]:
        if hasattr(quick_response, "to_mongo"):
            data = quick_response.to_mongo().to_dict()
        elif hasattr(quick_response, "model_dump"):
            data = quick_response.model_dump(exclude_none=True)
        elif isinstance(quick_response, dict):
            data = dict(quick_response)
        else:
            data = {}
        if "_id" in data:
            data["id"] = str(data.pop("_id"))
        return data

    def _validate_advanced_settings_uniqueness(
        self,
        organization_id: str,
        *,
        form_id: Optional[str],
        slug: Optional[str],
        internal_code: Optional[str],
    ) -> None:
        if slug:
            slug_query = Form.objects(
                organization_id=organization_id,
                is_deleted=False,
            ).filter(Q(slug=slug) | Q(slug_history=slug))
            if form_id:
                slug_query = slug_query.filter(id__ne=form_id)
            if slug_query.first():
                raise ConflictError(
                    "Slug is already in use or reserved by another form."
                )

        if internal_code:
            code_query = Form.objects(
                organization_id=organization_id,
                is_deleted=False,
                advanced_settings__internal_code=internal_code,
            )
            if form_id:
                code_query = code_query.filter(id__ne=form_id)
            if code_query.first():
                raise ConflictError(
                    "Internal code is already in use by another form."
                )

    def _prepare_advanced_settings_payload(
        self,
        *,
        organization_id: str,
        form_id: Optional[str],
        existing_advanced_settings: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        resolved_slug: Optional[str] = None,
        resolved_locale_default: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = dict(existing_advanced_settings or {})
        incoming = dict(payload or {})

        payload_model = AdvancedSettingsSchema.model_validate(incoming)
        normalized_payload = payload_model.model_dump(exclude_unset=True, exclude_none=True)

        merged = dict(existing)
        merged.update(normalized_payload)

        slug = self._normalize_slug(
            resolved_slug or merged.get("slug") or existing.get("slug")
        )
        locale_default = self._normalize_locale(
            resolved_locale_default
            or merged.get("locale_default")
            or existing.get("locale_default")
            or "en"
        )

        if slug:
            merged["slug"] = slug
        if locale_default:
            merged["locale_default"] = locale_default

        fallback_language = self._normalize_locale(
            merged.get("fallback_language") or locale_default or "en"
        )
        if fallback_language:
            merged["fallback_language"] = fallback_language

        merged["api_identifiers"] = dict(merged.get("api_identifiers") or {})
        merged["experimental_flags"] = dict(merged.get("experimental_flags") or {})

        self._validate_advanced_settings_uniqueness(
            organization_id,
            form_id=form_id,
            slug=slug,
            internal_code=merged.get("internal_code"),
        )
        return merged

    def _apply_advanced_settings_to_form(
        self,
        form_doc: Form,
        *,
        organization_id: str,
        payload: Optional[Dict[str, Any]],
        resolved_slug: Optional[str] = None,
        resolved_locale_default: Optional[str] = None,
    ) -> Dict[str, Any]:
        advanced_settings = self._prepare_advanced_settings_payload(
            organization_id=organization_id,
            form_id=str(getattr(form_doc, "id", "")) or None,
            existing_advanced_settings=getattr(form_doc, "advanced_settings", None),
            payload=payload,
            resolved_slug=resolved_slug,
            resolved_locale_default=resolved_locale_default,
        )

        previous_slug = getattr(form_doc, "slug", None)
        current_slug = advanced_settings.get("slug") or previous_slug
        current_locale = advanced_settings.get("locale_default") or getattr(
            form_doc, "default_language", None
        )

        if previous_slug and current_slug and previous_slug != current_slug:
            slug_history = list(getattr(form_doc, "slug_history", []) or [])
            if previous_slug not in slug_history:
                slug_history.append(previous_slug)
            form_doc.slug_history = slug_history

        if current_slug:
            form_doc.slug = current_slug
        if current_locale:
            form_doc.default_language = current_locale
        form_doc.advanced_settings = advanced_settings
        return advanced_settings

    def delete(
        self, doc_id: str, organization_id: str = None, hard_delete: bool = False
    ) -> None:
        super().delete(doc_id, organization_id, hard_delete)
        if hard_delete and organization_id:
            try:
                from services.tombstone_service import TombstoneService

                TombstoneService().record_delete(
                    organization_id=organization_id,
                    entity_type="forms",
                    entity_id=str(doc_id),
                )
            except Exception as tombstone_err:
                app_logger.warning(
                    f"Failed to record form tombstone for {doc_id}: {tombstone_err}"
                )
        if organization_id:
            from services.tenant_service import TenantService
            TenantService().recalculate_usage(organization_id)


    def sync_form_canvas(
        self, form_id: str, organization_id: str, canvas_data: Dict[str, Any]
    ) -> Form:
        """Replace the form's canvas from the builder payload.

        The frontend intentionally sends both:
        - top-level `sections` for direct canvas sync
        - `versions[0].sections` for the snapshot/version contract

        This method treats them as the same canonical canvas and persists all
        relevant metadata on the form document so the builder does not drift
        into two incompatible representations.
        """
        form_doc = self.model.objects(
            id=form_id, organization_id=organization_id, is_deleted=False
        ).first()
        if not form_doc:
            raise NotFoundError("Form not found for canvas sync")

        def _coerce_text(value: Any) -> Optional[str]:
            if value is None:
                return None
            if isinstance(value, str):
                text = value.strip()
                return text if text else None
            if isinstance(value, dict):
                for key in ("en", "default", "value", "text"):
                    candidate = value.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        return candidate.strip()
                for candidate in value.values():
                    if isinstance(candidate, str) and candidate.strip():
                        return candidate.strip()
                return None
            return str(value)

        def _normalize_option(option_payload: Dict[str, Any]) -> Dict[str, Any]:
            option = dict(option_payload or {})
            option.pop("id", None)
            option.pop("_id", None)
            option["option_label"] = (
                _coerce_text(option.pop("option_label", option.pop("label", None)))
                or ""
            )
            option["option_value"] = (
                _coerce_text(option.pop("option_value", option.pop("value", None)))
                or option["option_label"]
            )
            if "description" in option:
                option["description"] = _coerce_text(option["description"])
            visibility_condition = option.get("visibility_condition")
            if isinstance(visibility_condition, str) or visibility_condition is None:
                option["visibility_condition"] = None
            return option

        def _normalize_question(question_payload: Dict[str, Any]) -> Dict[str, Any]:
            question = dict(question_payload or {})
            question.pop("id", None)
            question.pop("_id", None)
            question["label"] = (
                _coerce_text(question.get("label")) or "Untitled Question"
            )
            if "help_text" in question:
                question["help_text"] = _coerce_text(question.get("help_text"))
            if "default_value" in question:
                default_value = question.get("default_value")
                if isinstance(default_value, dict):
                    question["default_value"] = _coerce_text(default_value)
                elif default_value is None:
                    question["default_value"] = None
                else:
                    question["default_value"] = str(default_value)

            if "options" in question and isinstance(question["options"], list):
                question["options"] = [
                    _normalize_option(opt)
                    for opt in question["options"]
                    if isinstance(opt, dict)
                ]

            for key in ("metadata", "metaData"):
                if key in question:
                    val = question.pop(key)
                    if val is not None and "meta_data" not in question:
                        question["meta_data"] = val
            if "meta_data" in question and question["meta_data"] is None:
                question["meta_data"] = {}

            # Drop frontend-only text objects from fields that are strict strings.
            for key in (
                "placeholder",
                "validation_regex",
                "custom_error_message",
                "input_mask",
            ):
                if key in question and not isinstance(question[key], str):
                    question[key] = _coerce_text(question[key])
            return question

        def _normalize_section_payload(
            section_payload: Dict[str, Any],
        ) -> Dict[str, Any]:
            payload = SectionService.normalize_section_tree(dict(section_payload or {}))
            nested_payloads = payload.pop("sections", []) or []
            payload.pop("id", None)
            payload.pop("_id", None)
            payload["title"] = _coerce_text(payload.get("title")) or "Untitled Section"
            if "description" in payload:
                payload["description"] = _coerce_text(payload.get("description"))
            if "help_text" in payload:
                payload["help_text"] = _coerce_text(payload.get("help_text"))
            if "questions" in payload and isinstance(payload["questions"], list):
                payload["questions"] = [
                    _normalize_question(q)
                    for q in payload["questions"]
                    if isinstance(q, dict)
                ]
            if (
                "response_templates" in payload
                and payload["response_templates"] is None
            ):
                payload["response_templates"] = []
            if "tags" in payload and payload["tags"] is None:
                payload["tags"] = []
            for key in ("metadata", "metaData"):
                if key in payload:
                    val = payload.pop(key)
                    if val is not None and "meta_data" not in payload:
                        payload["meta_data"] = val
            if "meta_data" in payload and payload["meta_data"] is None:
                payload["meta_data"] = {}
            payload["sections"] = nested_payloads
            return payload

        def _has_sections_payload(payload: Dict[str, Any]) -> bool:
            if not isinstance(payload, dict):
                return False
            if "sections" in payload:
                return True
            versions = payload.get("versions", []) if isinstance(payload, dict) else []
            if not versions:
                return False
            first_version = versions[0] if isinstance(versions[0], dict) else {}
            return "sections" in first_version

        def _extract_sections(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
            sections = payload.get("sections", []) if isinstance(payload, dict) else []
            if sections:
                return sections
            versions = payload.get("versions", []) if isinstance(payload, dict) else []
            if not versions:
                return []
            first_version = versions[0] if isinstance(versions[0], dict) else {}
            return (
                first_version.get("sections", [])
                if isinstance(first_version, dict)
                else []
            )

        sections_payload_present = _has_sections_payload(canvas_data)
        sections_data = (
            _extract_sections(canvas_data) if sections_payload_present else []
        )
        normalized_sections = []

        def build_section(section_payload: Dict[str, Any]):
            payload = _normalize_section_payload(section_payload)
            nested_payloads = payload.pop("sections", []) or []
            payload["organization_id"] = organization_id
            section_doc = Section(**payload)
            section_doc.organization_id = organization_id
            section_doc.save()
            child_refs = []
            for child_payload in nested_payloads:
                child_refs.append(build_section(child_payload))
            if child_refs:
                section_doc.sections = child_refs
                section_doc.save()
            return section_doc

        for section_payload in sections_data:
            normalized_sections.append(build_section(section_payload))

        if sections_payload_present:
            form_doc.sections = normalized_sections
        if "title" in canvas_data:
            form_doc.title = canvas_data["title"]
        if "status" in canvas_data:
            form_doc.status = canvas_data["status"]
        if "ui_type" in canvas_data:
            form_doc.ui_type = canvas_data["ui_type"]
        if "description" in canvas_data:
            form_doc.description = canvas_data["description"]
        if "help_text" in canvas_data:
            form_doc.help_text = canvas_data["help_text"]
        if "style" in canvas_data:
            form_doc.style = canvas_data["style"]
        workflows = canvas_data.get("workflows")
        if workflows is None and isinstance(canvas_data.get("metadata"), dict):
            workflows = canvas_data["metadata"].get("workflowSettings")
        if workflows is not None:
            form_doc.workflows = workflows
        if isinstance(canvas_data.get("metadata"), dict):
            form_doc.metadata = {
                **(getattr(form_doc, "metadata", {}) or {}),
                **canvas_data["metadata"],
            }
        access_policy = canvas_data.get(
            "access_policy", canvas_data.get("accessPolicy")
        )
        if access_policy is not None:
            form_doc.access_policy = access_policy
        advanced_settings = canvas_data.get(
            "advanced_settings", canvas_data.get("advancedSettings")
        )
        if (
            advanced_settings is not None
            or "slug" in canvas_data
            or "default_language" in canvas_data
        ):
            resolved_slug = (
                (advanced_settings or {}).get("slug")
                if isinstance(advanced_settings, dict)
                else None
            ) or canvas_data.get("slug") or getattr(form_doc, "slug", None)
            resolved_locale_default = (
                (advanced_settings or {}).get("locale_default")
                if isinstance(advanced_settings, dict)
                else None
            ) or (
                (advanced_settings or {}).get("localeDefault")
                if isinstance(advanced_settings, dict)
                else None
            ) or canvas_data.get("default_language") or getattr(
                form_doc, "default_language", None
            )
            self._apply_advanced_settings_to_form(
                form_doc,
                organization_id=organization_id,
                payload=advanced_settings if isinstance(advanced_settings, dict) else None,
                resolved_slug=resolved_slug,
                resolved_locale_default=resolved_locale_default,
            )
        submission_settings = canvas_data.get(
            "submission_settings", canvas_data.get("submissionSettings")
        )
        if submission_settings is not None:
            form_doc.submission_settings = (
                SubmissionSettingsSchema.model_validate(submission_settings)
                .model_dump(exclude_unset=True, exclude_none=True)
            )
        quick_responses = canvas_data.get(
            "quick_responses", canvas_data.get("quickResponses")
        )
        if quick_responses is not None:
            form_doc.quick_responses = [
                QuickResponse(
                    **QuickResponseSchema.model_validate(
                        item.model_dump(exclude_none=True)
                        if hasattr(item, "model_dump")
                        else item
                    ).model_dump(exclude_none=True)
                )
                for item in (quick_responses or [])
                if item is not None
            ]
        data_export_settings = canvas_data.get(
            "data_export_settings", canvas_data.get("dataExportSettings")
        )
        if data_export_settings is not None:
            form_doc.data_export_settings = (
                DataExportSettingsSchema.model_validate(data_export_settings)
                .model_dump(exclude_none=True)
            )
        if "active_version" in canvas_data:
            active_version_value = canvas_data["active_version"]
            version_doc = None
            if active_version_value:
                active_version_str = str(active_version_value)
                version_doc = Version.objects(
                    form=form_doc,
                    id=active_version_str,
                ).first()
                if not version_doc and isinstance(active_version_value, str):
                    parts = active_version_value.split(".")
                    if len(parts) == 3 and all(part.isdigit() for part in parts):
                        version_doc = Version.objects(
                            form=form_doc,
                            major=int(parts[0]),
                            minor=int(parts[1]),
                            patch=int(parts[2]),
                        ).first()
            if version_doc:
                form_doc.active_version = version_doc
        form_doc.save()
        self.sync_draft_version(form_id, organization_id)
        audit_logger.info(f"AUDIT: Form canvas synced for form {form_id}")
        return form_doc

    def _stamp_sections_with_version(
        self, form_doc: Form, version_doc: Version, form_version: FormVersion
    ) -> None:
        """Persist version references on all direct and nested sections."""

        def stamp(section_ref):
            section_id = getattr(section_ref, "id", section_ref)
            section_doc = Section.objects(
                id=section_id,
                organization_id=form_doc.organization_id,
                is_deleted=False,
            ).first()
            if not section_doc:
                return
            section_doc.version = version_doc
            section_doc.save()
            for nested_ref in section_doc.sections or []:
                stamp(nested_ref)

        for section_ref in form_doc.sections or []:
            stamp(section_ref)

    def _build_draft_snapshot(self, form_doc: Form) -> Dict[str, Any]:
        """Build a normalized snapshot from the current form structure."""
        sections_data = []
        for section_ref in form_doc.sections or []:
            sections_data.append(self._snapshot_section(section_ref))
        snapshot = {
            "sections": sections_data,
            "translations": form_doc.translations or {},
        }
        workflows = getattr(form_doc, "workflows", None)
        if workflows is not None:
            snapshot["workflows"] = workflows
        submission_settings = getattr(form_doc, "submission_settings", None)
        if submission_settings is not None:
            snapshot["submission_settings"] = submission_settings
        data_export_settings = getattr(form_doc, "data_export_settings", None)
        if data_export_settings is not None:
            snapshot["data_export_settings"] = data_export_settings
        quick_responses = getattr(form_doc, "quick_responses", None)
        if quick_responses is not None:
            snapshot["quick_responses"] = [
                self._snapshot_quick_response(item) for item in quick_responses
            ]
        advanced_settings = getattr(form_doc, "advanced_settings", None)
        if advanced_settings is not None:
            snapshot["advanced_settings"] = advanced_settings
        return snapshot

    def sync_draft_version(self, form_id: str, organization_id: str) -> FormVersion:
        """
        Ensure a draft Version + FormVersion snapshot exists for the current form state.
        This gives forms/sections version metadata immediately after create/update.
        """
        app_logger.info(f"Entering sync_draft_version for Form ID {form_id}")
        form_doc = self.model.objects(
            id=form_id, organization_id=organization_id, is_deleted=False
        ).first()
        if not form_doc:
            raise NotFoundError("Form not found for draft version sync")

        existing_version = form_doc._data.get("active_version")
        version_doc = None
        if existing_version:
            version_id = getattr(existing_version, "id", existing_version)
            version_doc = Version.objects(id=version_id).first()

        if not version_doc:
            version_doc = Version(form=form_doc, major=0, minor=1, patch=0)
            version_doc.save()
            form_doc.active_version = version_doc

        snapshot_data = self._build_draft_snapshot(form_doc)
        import json
        import zlib
        from models.Form import SnapshotStore

        snapshot_json = json.dumps(snapshot_data, default=str)
        compressed_data = zlib.compress(snapshot_json.encode("utf-8"))
        store = SnapshotStore(
            organization_id=form_doc.organization_id,
            compressed_data=compressed_data,
            is_compressed=True,
            size_bytes=len(snapshot_json),
        )
        store.save()

        form_version = FormVersion.objects(
            form=form_doc.id, version=version_doc
        ).first()
        if not form_version:
            form_version = FormVersion(
                form=form_doc,
                version=version_doc,
                status="draft",
                snapshot_ref=store,
                translations=form_doc.translations or {},
            )
        else:
            form_version.snapshot_ref = store
            form_version.translations = form_doc.translations or {}
            form_version.status = "draft"

        if hasattr(form_version, "access_policy") and hasattr(
            form_doc, "access_policy"
        ):
            try:
                form_version.access_policy = form_doc.access_policy
            except Exception:
                # Older schemas may not expose access_policy on FormVersion.
                pass
        if hasattr(form_version, "submission_settings") and hasattr(
            form_doc, "submission_settings"
        ):
            try:
                form_version.submission_settings = form_doc.submission_settings
            except Exception:
                # Older schemas may not expose submission_settings on FormVersion.
                pass
        if hasattr(form_version, "data_export_settings") and hasattr(
            form_doc, "data_export_settings"
        ):
            try:
                form_version.data_export_settings = form_doc.data_export_settings
            except Exception:
                # Older schemas may not expose data_export_settings on FormVersion.
                pass
        if hasattr(form_version, "quick_responses") and hasattr(
            form_doc, "quick_responses"
        ):
            try:
                form_version.quick_responses = form_doc.quick_responses
            except Exception:
                # Older schemas may not expose quick_responses on FormVersion.
                pass
        if hasattr(form_version, "advanced_settings") and hasattr(
            form_doc, "advanced_settings"
        ):
            try:
                form_version.advanced_settings = form_doc.advanced_settings
            except Exception:
                # Older schemas may not expose advanced_settings on FormVersion.
                pass

        form_version.save()
        form_doc.save()
        self._stamp_sections_with_version(form_doc, version_doc, form_version)
        app_logger.info(
            f"Successfully completed sync_draft_version for Form ID {form_id}"
        )
        return form_version

    @enforce_sla(max_ms=100)
    def create(self, create_schema: FormCreateSchema) -> FormSchema:
        app_logger.info(
            f"Entering FormService.create with title: {create_schema.title}"
        )
        try:
            if create_schema.organization_id:
                from services.tenant_service import TenantService
                tenant_service = TenantService()
                tenant_service.check_form_quota(create_schema.organization_id)

            data = create_schema.model_dump(exclude_unset=True, exclude={"sections"})
            if data.get("data_export_settings") is not None:
                data["data_export_settings"] = (
                    DataExportSettingsSchema.model_validate(
                        data["data_export_settings"]
                    ).model_dump(exclude_none=True)
                )
            quick_responses = data.get("quick_responses")
            if quick_responses is not None:
                data["quick_responses"] = [
                    QuickResponse(
                        **QuickResponseSchema.model_validate(
                            item.model_dump(exclude_none=True)
                            if hasattr(item, "model_dump")
                            else item
                        ).model_dump(exclude_none=True)
                    )
                    for item in (quick_responses or [])
                    if item is not None
                ]
            advanced_settings = self._prepare_advanced_settings_payload(
                organization_id=create_schema.organization_id,
                form_id=None,
                existing_advanced_settings=None,
                payload=data.get("advanced_settings"),
                resolved_slug=data.get("slug"),
                resolved_locale_default=data.get("default_language"),
            )
            data["advanced_settings"] = advanced_settings
            data["slug"] = advanced_settings.get("slug") or data.get("slug")
            data["default_language"] = (
                advanced_settings.get("locale_default")
                or data.get("default_language")
                or "en"
            )
            form_doc = self.model(**data)
            form_doc.save()

            if form_doc.organization_id:
                tenant_service.recalculate_usage(form_doc.organization_id)

            self.sync_draft_version(str(form_doc.id), form_doc.organization_id)

            form = self._to_schema(form_doc)
            event_bus.publish("form.indexed", form.model_dump())
            audit_logger.info(
                f"AUDIT: Form created with ID {form.id} and title {form.title}"
            )
            app_logger.info(
                f"Successfully completed FormService.create for ID {form.id}"
            )
            return form
        except Exception as e:
            error_logger.error(f"Error in FormService.create: {str(e)}", exc_info=True)
            raise

    def update(
        self,
        form_id: str,
        update_schema: FormUpdateSchema,
        organization_id: Optional[str] = None,
    ) -> FormSchema:
        app_logger.info(f"Entering FormService.update for Form ID {form_id}")
        try:
            current_form = self.model.objects(
                id=form_id,
                organization_id=organization_id,
                is_deleted=False,
            ).first()
            if not current_form:
                raise NotFoundError("Form not found for update")

            old_slug = getattr(current_form, "slug", None)
            current_advanced_settings = getattr(current_form, "advanced_settings", None)
            payload_advanced_settings = getattr(update_schema, "advanced_settings", None)
            if payload_advanced_settings is not None or getattr(update_schema, "slug", None):
                advanced_settings = self._prepare_advanced_settings_payload(
                    organization_id=organization_id or current_form.organization_id,
                    form_id=str(current_form.id),
                    existing_advanced_settings=current_advanced_settings,
                    payload=(
                        payload_advanced_settings.model_dump(exclude_unset=True, exclude_none=True)
                        if hasattr(payload_advanced_settings, "model_dump")
                        else payload_advanced_settings
                    ),
                    resolved_slug=getattr(update_schema, "slug", None) or old_slug,
                    resolved_locale_default=getattr(update_schema, "default_language", None)
                    or getattr(current_form, "default_language", None),
                )
                update_schema.advanced_settings = advanced_settings
                update_schema.slug = advanced_settings.get("slug") or old_slug
                update_schema.default_language = advanced_settings.get(
                    "locale_default"
                ) or getattr(current_form, "default_language", None)
            payload_data_export_settings = getattr(update_schema, "data_export_settings", None)
            if payload_data_export_settings is not None:
                update_schema.data_export_settings = (
                    DataExportSettingsSchema.model_validate(
                        payload_data_export_settings.model_dump(
                            exclude_none=True
                        )
                        if hasattr(payload_data_export_settings, "model_dump")
                        else payload_data_export_settings
                    ).model_dump(exclude_none=True)
                )

            form = super().update(
                form_id, update_schema, organization_id=organization_id
            )
            updated_advanced_settings = getattr(update_schema, "advanced_settings", None)
            new_slug = getattr(update_schema, "slug", None)
            if old_slug and new_slug and old_slug != new_slug:
                history = list(getattr(current_form, "slug_history", []) or [])
                if old_slug not in history:
                    history.append(old_slug)
                self.model.objects(
                    id=form_id, organization_id=organization_id
                ).update_one(set__slug_history=history)
                if updated_advanced_settings is not None:
                    current_form.slug_history = history
            event_bus.publish("form.indexed", form.model_dump())
            audit_logger.info(f"AUDIT: Form updated with ID {form_id}")
            app_logger.info(
                f"Successfully completed FormService.update for ID {form_id}"
            )
            return form
        except Exception as e:
            error_logger.error(
                f"Error in FormService.update for ID {form_id}: {str(e)}", exc_info=True
            )
            raise

    @enforce_sla(max_ms=50)
    def get_by_slug(self, slug: str, organization_id: str) -> FormSchema:
        """Fetch form securely bounded by tenant slug."""
        app_logger.info(f"Entering get_by_slug: {slug} for org {organization_id}")
        try:
            form_doc = (
                self.model.objects(
                    organization_id=organization_id,
                    is_deleted=False,
                )
                .filter(Q(slug=slug) | Q(slug_history=slug))
                .first()
            )

            if not form_doc:
                app_logger.debug(f"Form '{slug}' not found in org {organization_id}")
                raise NotFoundError(f"Form '{slug}' not found")

            app_logger.info(f"Successfully completed get_by_slug for: {slug}")
            return self._to_schema(form_doc)
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(
                    f"Error in get_by_slug for {slug}: {str(e)}", exc_info=True
                )
            raise

    def _snapshot_section(self, section: Section) -> Dict[str, Any]:
        """Deep snapshots a section and its sub-sections/questions into a dictionary."""
        if hasattr(section, "to_mongo"):
            data = section.to_mongo().to_dict()
        else:
            # Handle DBRef/raw reference values from legacy forms.
            section_doc = Section.objects(
                id=getattr(section, "id", section),
                is_deleted=False,
            ).first()
            if not section_doc:
                raise NotFoundError("Section not found while snapshotting form")
            data = section_doc.to_mongo().to_dict()
        if "_id" in data:
            data["id"] = str(data.pop("_id"))

        # Snapshot sub-sections recursively
        nested_sections = []
        for nested in getattr(section, "sections", []) or []:
            nested_sections.append(self._snapshot_section(nested))
        if nested_sections:
            data["sections"] = nested_sections

        # Snapshot questions (Questions are embedded, so to_mongo handles them,
        # but we ensure IDs are strings)
        for q in data.get("questions", []):
            if "_id" in q:
                q["id"] = str(q.pop("_id"))

        return data

    @log_performance
    def publish_form(
        self,
        form_id: str,
        organization_id: Optional[str] = None,
        major_bump: bool = False,
        minor_bump: bool = True,
    ) -> Dict[str, Any]:
        """
        Calculates Semantic Versioning and locks in an immutable snapshot
        (FormVersion) so active live forms are safe from structural breakage.
        """
        app_logger.info(f"Entering publish_form for Form ID {form_id}")
        filters = {"id": form_id, "is_deleted": False}
        if organization_id:
            filters["organization_id"] = organization_id

        form_doc = self.model.objects(**filters).first()
        if not form_doc:
            app_logger.warning(f"Form {form_id} not found for publishing")
            raise NotFoundError("Form not found for publishing")

        if not form_doc.sections:
            raise StateTransitionError("Cannot publish a form with no sections")

        try:
            # Semantic Version logic
            current_version = None
            if form_doc.active_version_id:
                current_version = Version.objects(id=form_doc.active_version_id).first()
            major, minor, patch = 1, 0, 0
            if current_version:
                major = (
                    current_version.major + 1 if major_bump else current_version.major
                )
                minor = (
                    current_version.minor + 1
                    if (minor_bump and not major_bump)
                    else (0 if major_bump else current_version.minor)
                )
                patch = (
                    current_version.patch + 1 if not (major_bump or minor_bump) else 0
                )

            # 1. Create the semantic map
            new_version = Version(form=form_doc, major=major, minor=minor, patch=patch)
            new_version.save()

            # 2. Extract an immutable snapshot, deep cloning sections as they exist right now
            snapshot_data = {
                "sections": [self._snapshot_section(s) for s in form_doc.sections],
                "translations": form_doc.translations or {},
            }
            if getattr(form_doc, "workflows", None) is not None:
                snapshot_data["workflows"] = form_doc.workflows
            quick_responses = getattr(form_doc, "quick_responses", None)
            if quick_responses is not None:
                snapshot_data["quick_responses"] = [
                    self._snapshot_quick_response(item) for item in quick_responses
                ]

            # --- Snapshot Hardening (Phase 4) ---
            from models.Form import SnapshotStore
            import zlib
            import json

            snapshot_json = json.dumps(snapshot_data, default=str)
            size_bytes = len(snapshot_json)

            # Compress snapshot for storage efficiency
            compressed_data = zlib.compress(snapshot_json.encode("utf-8"))

            if size_bytes > 10 * 1024 * 1024:  # 10MB limit
                app_logger.warning(f"Oversized snapshot detected: {size_bytes} bytes")

            store = SnapshotStore(
                organization_id=form_doc.organization_id,
                compressed_data=compressed_data,
                is_compressed=True,
                size_bytes=size_bytes,
            )
            store.save()

            snapshot = FormVersion(
                form=form_doc,
                version=new_version,
                status="published",
                snapshot_ref=store,
                translations=form_doc.translations or {},  # Keep for compatibility
                quick_responses=list(getattr(form_doc, "quick_responses", []) or []),
            )
            snapshot.save()
            self._stamp_sections_with_version(form_doc, new_version, snapshot)

            # 3. Update active form
            form_doc.status = "published"
            form_doc.publish_at = datetime.now(timezone.utc)
            form_doc.active_version = new_version
            form_doc.save()

            audit_logger.info(
                f"AUDIT: Published '{form_doc.title}' at version v{major}.{minor}.{patch}"
            )
            app_logger.info(f"Successfully completed publish_form for ID {form_id}")

            result = self._to_schema(form_doc).model_dump()
            result["version_metadata"] = {
                "version_string": new_version.version_string,
                "major": major,
                "minor": minor,
                "patch": patch,
                "form_version_id": str(snapshot.id),
            }
            return result

        except Exception as e:
            error_logger.error(
                f"Failed to publish form {form_id}: {str(e)}", exc_info=True
            )
            raise StateTransitionError(
                "Publish sequence failed",
                details={"error": str(e)},
            )


class ProjectCreateSchema(ProjectSchema, InboundPayloadSchema):
    pass


class ProjectUpdateSchema(ProjectSchema, InboundPayloadSchema):
    pass


class ProjectService(BaseService):
    def __init__(self):
        super().__init__(model=Project, schema=ProjectSchema)

    def create_project_with_form(
        self,
        project_data: Dict[str, Any],
        form_data: Dict[str, Any],
        organization_id: str,
    ) -> Dict[str, Any]:
        app_logger.info("Entering create_project_with_form")
        project_data = dict(project_data or {})
        form_data = dict(form_data or {})
        project_data["organization_id"] = organization_id
        form_data["organization_id"] = organization_id
        project_schema = ProjectCreateSchema(**project_data)
        project = super().create(project_schema)
        form_data["project"] = str(project.id)
        form_schema = FormCreateSchema(**form_data)
        form = FormService().create(form_schema)
        project_doc = Project.objects(
            id=project.id, organization_id=organization_id, is_deleted=False
        ).first()
        form_doc = Form.objects(
            id=form.id, organization_id=organization_id, is_deleted=False
        ).first()
        if project_doc and form_doc:
            project_doc.forms.append(form_doc)
            project_doc.save()
        return {"project": project, "form": form}

    def create_form_in_project(
        self,
        project_id: str,
        form_data: Dict[str, Any],
        organization_id: str,
        user: Optional[Any] = None,
    ) -> FormSchema:
        app_logger.info(f"Entering create_form_in_project for project {project_id}")
        project = Project.objects(
            id=project_id, organization_id=organization_id, is_deleted=False
        ).first()
        if not project:
            raise NotFoundError("Project not found")
        if user and not AccessControlService.check_project_permission(
            user, project, "edit"
        ):
            raise PermissionError("Unauthorized to manage this project")
        form_data = dict(form_data or {})
        form_data["organization_id"] = organization_id
        form_data["project"] = str(project.id)
        form_schema = FormCreateSchema(**form_data)
        form = FormService().create(form_schema)
        project_form = Form.objects(
            id=form.id, organization_id=organization_id, is_deleted=False
        ).first()
        project.forms.append(project_form)
        project.save()
        return form

    def list_forms_in_project(
        self,
        project_id: str,
        organization_id: Optional[str] = None,
    ) -> List[FormSchema]:
        """Deep queries safely resolved linked active forms in a project tree."""
        app_logger.info(f"Entering list_forms_in_project for Project ID {project_id}")
        try:
            filters = {"id": project_id, "is_deleted": False}
            if organization_id:
                filters["organization_id"] = organization_id

            project_doc = self.model.objects(**filters).first()
            if not project_doc:
                app_logger.warning(f"Project {project_id} not found")
                raise NotFoundError("Project not found")

            app_logger.info(f"Project {project_id} found")
            app_logger.info(f"Project forms: {project_doc.forms}")
            # Extract safely avoiding dereferencing destroyed models.
            # Treat `Form.project` as the canonical link and merge any legacy
            # `project.forms` references so stale project arrays do not hide
            # valid forms from the dashboard.
            forms = []
            seen_form_ids = set()

            def _append_form(form_doc):
                if not form_doc:
                    return
                form_id = getattr(form_doc, "id", None)
                if not form_id:
                    return
                form_id_str = str(form_id)
                if form_id_str in seen_form_ids:
                    return
                seen_form_ids.add(form_id_str)
                forms.append(form_doc)

            direct_forms = Form.objects(
                project=project_doc.id,
                is_deleted=False,
                **({"organization_id": organization_id} if organization_id else {}),
            )
            for direct_form in direct_forms:
                _append_form(direct_form)

            for form_ref in project_doc.forms or []:
                try:
                    app_logger.info(f"Form reference {form_ref}")

                    form_id = getattr(form_ref, "id", None)
                    if form_id is None:
                        form_id = form_ref if isinstance(form_ref, str) else None
                    if not form_id:
                        app_logger.warning(f"Form reference {form_ref} is invalid")
                        continue

                    form = Form.objects(
                        id=form_id,
                        is_deleted=False,
                        **(
                            {"organization_id": organization_id}
                            if organization_id
                            else {}
                        ),
                    ).first()
                    if not form:
                        app_logger.warning(f"Form {form_id} not found")
                        continue
                    app_logger.info(f"Form {form_id} found")
                    _append_form(form)
                except Exception as e:
                    app_logger.warning(
                        f"Error in list_forms_in_project for Project ID {project_id}: {str(e)}"
                    )
                    continue

            app_logger.info(
                f"Successfully completed list_forms_in_project for Project ID {project_id} with total forms {len(forms)}"
            )
            return [FormSerializer.serialize(form.to_dict()) for form in forms]
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(
                    f"Error in list_forms_in_project for Project ID {project_id}: {str(e)}",
                    exc_info=True,
                )
            raise
