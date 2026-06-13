from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict
from typing import List, Dict, Any, Tuple, Optional, Literal
from logger.unified_logger import (
    app_logger,
    error_logger,
    audit_logger,
    get_logger,
    log_performance,
)
from services.base import BaseService, PaginatedResult, TSchema, TUpdateSchema
from utils.exceptions import NotFoundError, ValidationError, ConflictError
from models import Form, FormResponse, DynamicViewDefinition
from schemas.response import FormResponseSchema, DynamicViewDefinitionSchema
from schemas.base import InboundPayloadSchema

logger = get_logger(__name__)



class FormResponseCreateSchema(FormResponseSchema, InboundPayloadSchema):
    idempotency_key: Optional[str] = None


class FormResponseUpdateSchema(BaseModel, InboundPayloadSchema):
    model_config = ConfigDict(extra="ignore")

    project: Optional[str] = None
    form: Optional[str] = None
    form_version: Optional[str] = None
    version: Optional[str] = None
    organization_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    submitted_by: Optional[str] = None
    submitted_at: Optional[datetime] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    status: Optional[Literal["submitted", "processed", "error", "archived"]] = None
    review_status: Optional[Literal["pending", "approved", "rejected"]] = None
    meta_data: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None



class FormResponseService(BaseService):
    def __init__(self):
        super().__init__(model=FormResponse, schema=FormResponseSchema)

    def _collect_section_analytics(self, sections):
        events = []

        def walk(nodes):
            for node in nodes or []:
                metadata = {}
                if isinstance(node, dict):
                    metadata = dict(node.get("metadata") or node.get("meta_data") or {})
                    section_id = node.get("id")
                    title = node.get("title")
                    children = node.get("sections") or []
                else:
                    metadata = dict(getattr(node, "metadata", {}) or {})
                    section_id = getattr(node, "id", None)
                    title = getattr(node, "title", None)
                    children = getattr(node, "sections", []) or []

                analytics_event = (
                    metadata.get("analyticsEvent")
                    or metadata.get("analytics_event")
                    or ""
                ).strip()
                if analytics_event or any(
                    metadata.get(flag) is True
                    for flag in ("trackView", "trackCompletion", "trackDwellTime")
                ):
                    events.append(
                        {
                            "section_id": str(section_id) if section_id is not None else None,
                            "title": title,
                            "event_name": analytics_event or None,
                            "track_view": metadata.get("trackView", metadata.get("track_view", True)),
                            "track_completion": metadata.get(
                                "trackCompletion", metadata.get("track_completion", True)
                            ),
                            "track_dwell_time": metadata.get(
                                "trackDwellTime", metadata.get("track_dwell_time", False)
                            ),
                        }
                    )
                walk(children)

        walk(sections)
        return events

    def get_decrypted_response(
        self, response_id: str, organization_id: str
    ) -> Dict[str, Any]:
        """
        Fetches a single response, decrypts its sensitive fields, and caches the result in Redis.
        Uses batch decryption for efficiency.
        """
        app_logger.info(
            f"Entering get_decrypted_response for Response ID {response_id}"
        )
        try:
            from services.redis_service import redis_service
            from config.settings import settings
            from utils.encryption import batch_decrypt_values

            cache_key = f"decrypted_response:{organization_id}:{response_id}"

            if settings.CACHE_ENABLED:
                cached = redis_service.cache.get(cache_key)
                if cached:
                    app_logger.info(f"Cache hit for decrypted response: {response_id}")
                    return cached

            # Fetch from DB
            response = self.model.objects(
                id=response_id, organization_id=organization_id, is_deleted=False
            ).first()
            if not response:
                app_logger.warning(f"Response {response_id} not found")
                raise NotFoundError("Response not found")

            # Batch Decrypt
            full_data = response.data.copy()
            if response.encrypted_data:
                fields = list(response.encrypted_data.keys())
                values = list(response.encrypted_data.values())
                decrypted_values = batch_decrypt_values(values)
                for i, field in enumerate(fields):
                    full_data[field] = decrypted_values[i]

            # Build full result
            result = self._to_schema(response).model_dump()
            result["data"] = full_data

            if settings.CACHE_ENABLED:
                redis_service.cache.set(
                    cache_key, result, ttl=settings.RESPONSE_CACHE_TTL
                )

            audit_logger.info(
                f"AUDIT: Decrypted response accessed: {response_id} by org {organization_id}"
            )
            app_logger.info(
                f"Successfully completed get_decrypted_response for {response_id}"
            )
            return result
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(
                    f"Error in get_decrypted_response for {response_id}: {str(e)}",
                    exc_info=True,
                )
            raise

    def update(
        self, doc_id: str, update_schema: TUpdateSchema, organization_id: str = None
    ) -> TSchema:
        """Override update to invalidate decrypted response cache."""
        app_logger.info(f"Entering FormResponseService.update for ID {doc_id}")
        try:
            from services.redis_service import redis_service
            from config.settings import settings

            # Invalidate analytics cache before updating
            response_doc = self.model.objects(id=doc_id).first()
            if response_doc and hasattr(response_doc, "_data") and "form" in response_doc._data:
                form_ref = response_doc._data.get("form")
                if form_ref:
                    form_id = str(form_ref.id) if hasattr(form_ref, "id") else str(form_ref)
                    try:
                        from services.analytics_cache import analytics_cache
                        analytics_cache.invalidate_form(form_id)
                    except Exception as cache_err:
                        app_logger.warning(f"Failed to invalidate analytics cache on update: {cache_err}")

            result = super().update(doc_id, update_schema, organization_id)

            if settings.CACHE_ENABLED:
                keys_to_delete = [f"decrypted_response:{doc_id}"]
                if organization_id:
                    keys_to_delete.append(
                        f"decrypted_response:{organization_id}:{doc_id}"
                    )
                redis_service.cache.delete(*keys_to_delete)

            audit_logger.info(f"AUDIT: FormResponse updated with ID {doc_id}")
            app_logger.info(
                f"Successfully completed FormResponseService.update for ID {doc_id}"
            )
            return result
        except Exception as e:
            error_logger.error(
                f"Error in FormResponseService.update for ID {doc_id}: {str(e)}",
                exc_info=True,
            )
            raise

    def delete(
        self, doc_id: str, organization_id: str = None, hard_delete: bool = False
    ) -> None:
        """Override delete to invalidate decrypted response cache."""
        app_logger.info(f"Entering FormResponseService.delete for ID {doc_id}")
        try:
            from services.redis_service import redis_service
            from config.settings import settings

            # Invalidate analytics cache before deleting
            response_doc = self.model.objects(id=doc_id).first()
            if response_doc and hasattr(response_doc, "_data") and "form" in response_doc._data:
                form_ref = response_doc._data.get("form")
                if form_ref:
                    form_id = str(form_ref.id) if hasattr(form_ref, "id") else str(form_ref)
                    try:
                        from services.analytics_cache import analytics_cache
                        analytics_cache.invalidate_form(form_id)
                    except Exception as cache_err:
                        app_logger.warning(f"Failed to invalidate analytics cache on delete: {cache_err}")

            super().delete(doc_id, organization_id, hard_delete)

            if hard_delete and response_doc and organization_id:
                try:
                    from services.tombstone_service import TombstoneService

                    TombstoneService().record_delete(
                        organization_id=organization_id,
                        entity_type="responses",
                        entity_id=str(doc_id),
                    )
                except Exception as tombstone_err:
                    app_logger.warning(
                        f"Failed to record response tombstone for {doc_id}: {tombstone_err}"
                    )

            if organization_id:
                from services.tenant_service import TenantService
                TenantService().recalculate_usage(organization_id)


            if settings.CACHE_ENABLED:
                keys_to_delete = [f"decrypted_response:{doc_id}"]
                if organization_id:
                    keys_to_delete.append(
                        f"decrypted_response:{organization_id}:{doc_id}"
                    )
                redis_service.cache.delete(*keys_to_delete)

            audit_logger.info(f"AUDIT: FormResponse deleted with ID {doc_id}")
            app_logger.info(
                f"Successfully completed FormResponseService.delete for ID {doc_id}"
            )
        except Exception as e:
            error_logger.error(
                f"Error in FormResponseService.delete for ID {doc_id}: {str(e)}",
                exc_info=True,
            )
            raise

    def validate_payload(
        self, form_id: str, payload_data: Dict[str, Any], organization_id: str = None
    ) -> Tuple[bool, Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
        """
        Dynamically cross-checks an incoming submission against the strict Option, Logic,
        and Validation rule sets using the unified FormValidationService.
        """
        app_logger.info(f"Entering validate_payload for Form ID {form_id}")
        from services.form_validation_service import FormValidationService

        # This service handles everything: version resolution, conditions, calculations, etc.
        is_valid, cleaned_data, errors, calculated_values = (
            FormValidationService.validate_submission(
                form_id=form_id, payload=payload_data, organization_id=organization_id
            )
        )

        if not is_valid:
            app_logger.warning(
                f"Payload validation failed for Form {form_id}: {errors}"
            )
            raise ValidationError(f"Payload validation failed", details=errors)

        return is_valid, cleaned_data, errors, calculated_values

    def create_submission(self, data: FormResponseCreateSchema) -> FormResponseSchema:
        """Securely ingest a form submission executing payload validation first, wrapping with Idempotency."""
        app_logger.info(f"Entering create_submission for Form ID {data.form}")
        try:
            from services.tenant_service import TenantService
            TenantService().check_submission_quota(data.organization_id)

            idempotency_key = data.idempotency_key or data.data.get("idempotency_key")

            if idempotency_key:
                data.idempotency_key = idempotency_key
                if "idempotency_key" in data.data:
                    data.data = dict(data.data)
                    data.data.pop("idempotency_key", None)

                import uuid
                form_uuid = uuid.UUID(data.form) if isinstance(data.form, str) else data.form
                existing = FormResponse.objects(
                    __raw__={
                        "form": str(form_uuid),
                        "organization_id": data.organization_id,
                        "idempotency_key": idempotency_key,
                        "is_deleted": False,
                    }
                ).first()
                if existing:
                    existing_hash = (existing.meta_data or {}).get(
                        "idempotency_request_hash"
                    )
                    incoming_hash = (data.meta_data or {}).get(
                        "idempotency_request_hash"
                    )
                    if (
                        existing_hash
                        and incoming_hash
                        and existing_hash != incoming_hash
                    ):
                        raise ConflictError(
                            "Idempotency-Key was reused with a different request body"
                        )
                    app_logger.info(
                        f"Idempotent submission trapped: form {data.form} key {idempotency_key}"
                    )
                    return self._to_schema(existing)

            # --- Size Guard ---
            import json

            payload_size = len(json.dumps(data.data))
            if payload_size > 5 * 1024 * 1024:  # 5MB limit
                raise ValidationError(
                    f"Payload too large: {payload_size} bytes (max 5MB)"
                )

            # 1. Unified Validation (includes conditions, calculations, type checks)
            is_valid, cleaned_data, errors, calculated_values = self.validate_payload(
                form_id=str(data.form),
                payload_data=data.data,
                organization_id=data.organization_id,
            )

            # Update data with cleaned values.
            # If validator cannot map fields (e.g., missing variable_name in draft forms),
            # preserve original payload instead of writing an empty dict.
            data.data = cleaned_data if cleaned_data else (data.data or {})
            if calculated_values:
                if not data.meta_data:
                    data.meta_data = {}
                data.meta_data["calculated_values"] = calculated_values

            app_logger.info(
                f"Incoming submission for form {data.form} from organization {data.organization_id}"
            )

            # 2. Fetch Active Version and Snapshot for the response record
            form_doc = Form.objects(
                id=data.form, organization_id=data.organization_id, is_deleted=False
            ).first()
            if form_doc:
                raw_active_version = form_doc._data.get("active_version")
                active_version_id = getattr(
                    raw_active_version, "id", raw_active_version
                )
                if active_version_id:
                    from models.Form import Version, FormVersion

                    version_doc = Version.objects(id=active_version_id).first()
                    if version_doc:
                        data.version = version_doc.version_string
                        commit_id = getattr(
                            form_doc, "active_publish_commit_id", None
                        ) or getattr(form_doc, "head_commit_id", None)
                        if commit_id is not None:
                            data.commit_id = str(commit_id)

                    fv = None
                    if version_doc:
                        fv = FormVersion.objects(
                            form=form_doc.id, version=version_doc
                        ).first()
                        if not fv:
                            fv = FormVersion.objects(
                                form=form_doc.id, version__id=version_doc.id
                            ).first()
                    if not fv:
                        fv = (
                            FormVersion.objects(form=form_doc.id, status="published")
                            .order_by("-created_at")
                            .first()
                        )
                    if fv:
                        data.form_version = str(fv.id)

            # Create the response document
            try:
                response = self.create(data)
                TenantService().recalculate_usage(data.organization_id)

            except ConflictError:
                if idempotency_key:
                    import uuid
                    form_uuid = uuid.UUID(data.form) if isinstance(data.form, str) else data.form
                    existing = FormResponse.objects(
                        __raw__={
                            "form": str(form_uuid),
                            "organization_id": data.organization_id,
                            "idempotency_key": idempotency_key,
                            "is_deleted": False,
                        }
                    ).first()
                    if existing:
                        existing_hash = (existing.meta_data or {}).get(
                            "idempotency_request_hash"
                        )
                        incoming_hash = (data.meta_data or {}).get(
                            "idempotency_request_hash"
                        )
                        if (
                            existing_hash
                            and incoming_hash
                            and existing_hash != incoming_hash
                        ):
                            raise
                        return self._to_schema(existing)
                raise

            # Trigger background tasks
            try:
                from tasks.ai_tasks import (
                    async_index_response_vector,
                    async_classify_response_tags,
                )

                async_index_response_vector.delay(
                    str(response.id), data.organization_id
                )
                async_classify_response_tags.delay(
                    str(response.id), data.organization_id
                )
            except Exception as e:
                error_logger.warning(f"Failed to enqueue background tasks: {e}")

            # Publish Domain Event to decouple notification and webhook routing
            try:
                from services import event_bus

                section_analytics = []
                try:
                    form_for_analytics = Form.objects(
                        id=data.form, organization_id=data.organization_id, is_deleted=False
                    ).first()
                    if form_for_analytics is not None:
                        sections = getattr(form_for_analytics, "sections", []) or []
                        if not sections:
                            active_version = getattr(form_for_analytics, "_data", {}).get(
                                "active_version"
                            )
                            versions = getattr(form_for_analytics, "versions", []) or []
                            if active_version and versions:
                                for version in versions:
                                    if str(getattr(version, "version", "")) == str(
                                        active_version
                                    ):
                                        sections = getattr(version, "sections", []) or []
                                        break
                        section_analytics = self._collect_section_analytics(sections)
                except Exception as analytics_err:
                    error_logger.warning(
                        f"Failed to collect section analytics metadata: {analytics_err}"
                    )

                event_bus.publish(
                    "form.submitted",
                    {
                        "form_id": str(data.form),
                        "response_id": str(response.id),
                        "organization_id": data.organization_id,
                        "data": data.data,
                        "analytics": {"section_events": section_analytics},
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as e:
                error_logger.error(
                    f"Failed to publish domain event for response {response.id}: {str(e)}",
                    exc_info=True,
                )

            # Invalidate analytics cache
            try:
                from services.analytics_cache import analytics_cache
                analytics_cache.invalidate_form(str(data.form))
            except Exception as cache_err:
                error_logger.warning(
                    f"Failed to invalidate analytics cache on create: {cache_err}"
                )

            audit_logger.info(
                f"AUDIT: Form submission created for Form {data.form}, Response ID {response.id}"
            )
            app_logger.info(
                f"Successfully completed create_submission for Form ID {data.form}"
            )
            return response
        except Exception as e:
            error_logger.error(
                f"Error in create_submission for Form {data.form}: {str(e)}",
                exc_info=True,
            )
            raise

    def list_by_form(
        self,
        form_id: str,
        organization_id: str,
        page: int = 1,
        page_size: int = 50,
        project_id: str = None,
    ) -> PaginatedResult:
        """Pull highly paginated subsets of heavy analytics collections scoped to standard Tenant boundaries."""
        app_logger.info(
            f"Pulling paginated responses for form {form_id} org {organization_id}"
        )
        from uuid import UUID
        from models import Form, Project

        try:
            form_lookup_id = UUID(form_id)
        except Exception:
            form_lookup_id = form_id

        form_doc = Form.objects(
            id=form_lookup_id, organization_id=organization_id, is_deleted=False
        ).first()
        if not form_doc:
            logger.info(f"Form {form_id} not found")
            return PaginatedResult(
                items=[],
                total=0,
                page=page,
                page_size=page_size,
                has_next=False,
                success=True,
            )
        app_logger.debug(
            f"Resolved form for response listing: form_id={form_id}, resolved_form_id={form_doc.id}, org={organization_id}"
        )
        filters = {
            "form": form_doc.id,
            "organization_id": organization_id,
            "is_deleted": False,
        }
        if project_id:
            try:
                project_lookup_id = UUID(str(project_id))
            except Exception:
                project_lookup_id = project_id

            project_doc = Project.objects(
                id=project_lookup_id,
                organization_id=organization_id,
                is_deleted=False,
            ).first()
            if project_doc:
                filters["project"] = project_doc.id
            else:
                app_logger.warning(
                    f"Project {project_id} not found for response listing in org {organization_id}"
                )
                return PaginatedResult(
                    items=[],
                    total=0,
                    page=page,
                    page_size=page_size,
                    has_next=False,
                    success=True,
                )

        return self.list_paginated(
            page=page,
            page_size=page_size,
            **filters,
        )

    def list_by_project(
        self, project_id: str, organization_id: str, page: int = 1, page_size: int = 50
    ) -> PaginatedResult:
        """Deep analytics subset for root enterprise Projects."""
        return self.list_paginated(
            page=page,
            page_size=page_size,
            project=project_id,
            organization_id=organization_id,
            is_deleted=False,
        )


class DynamicViewDefinitionCreateSchema(
    DynamicViewDefinitionSchema, InboundPayloadSchema
):
    pass


class DynamicViewDefinitionUpdateSchema(
    DynamicViewDefinitionSchema, InboundPayloadSchema
):
    pass


class DynamicViewService(BaseService):
    def __init__(self):
        super().__init__(
            model=DynamicViewDefinition, schema=DynamicViewDefinitionSchema
        )

    @log_performance
    def execute_materialized_view(self, view_id: str) -> List[Dict[str, Any]]:
        """
        Executes the stored aggregate pipeline (db.createView / aggregate)
        producing the raw analytics table for frontend Charting components to render.
        """
        view_def = self.model.objects(id=view_id, is_deleted=False).first()
        if not view_def:
            raise NotFoundError(f"View definition {view_id} missing or deleted")

        try:
            # Connect the literal raw collection engine (FormResponse) to dynamic pipeline
            pipeline = view_def.pipeline
            # This pushes computation down to the MongoDB core entirely
            cursor = FormResponse.objects.aggregate(*pipeline)
            return list(cursor)
        except Exception as e:
            error_logger.error(
                f"MongoDB Aggregation Framework crashed on view {view_id}: {str(e)}",
                exc_info=True,
            )
            raise ValidationError("Pipeline execution failed", details=str(e))
