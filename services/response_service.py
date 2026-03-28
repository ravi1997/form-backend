from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple
from logger.unified_logger import app_logger, error_logger, audit_logger, get_logger, log_performance
from services.base import BaseService, PaginatedResult, TSchema, TUpdateSchema
from utils.exceptions import NotFoundError, ValidationError
from models import Form, FormResponse, DynamicViewDefinition
from schemas.response import FormResponseSchema, DynamicViewDefinitionSchema
from schemas.base import InboundPayloadSchema

logger = get_logger(__name__)


class FormResponseCreateSchema(FormResponseSchema, InboundPayloadSchema):
    pass


class FormResponseUpdateSchema(FormResponseSchema, InboundPayloadSchema):
    pass


class FormResponseService(BaseService):
    def __init__(self):
        super().__init__(model=FormResponse, schema=FormResponseSchema)

    def get_decrypted_response(self, response_id: str, organization_id: str) -> Dict[str, Any]:
        """
        Fetches a single response, decrypts its sensitive fields, and caches the result in Redis.
        Uses batch decryption for efficiency.
        """
        app_logger.info(f"Entering get_decrypted_response for Response ID {response_id}")
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
            response = self.model.objects(id=response_id, organization_id=organization_id, is_deleted=False).first()
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
            result['data'] = full_data
            
            if settings.CACHE_ENABLED:
                redis_service.cache.set(cache_key, result, ttl=settings.RESPONSE_CACHE_TTL)
            
            audit_logger.info(f"AUDIT: Decrypted response accessed: {response_id} by org {organization_id}")
            app_logger.info(f"Successfully completed get_decrypted_response for {response_id}")
            return result
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(f"Error in get_decrypted_response for {response_id}: {str(e)}", exc_info=True)
            raise

    def update(self, doc_id: str, update_schema: TUpdateSchema, organization_id: str = None) -> TSchema:
        """Override update to invalidate decrypted response cache."""
        app_logger.info(f"Entering FormResponseService.update for ID {doc_id}")
        try:
            from services.redis_service import redis_service
            from config.settings import settings
            
            result = super().update(doc_id, update_schema, organization_id)
            
            if settings.CACHE_ENABLED:
                keys_to_delete = [f"decrypted_response:{doc_id}"]
                if organization_id:
                    keys_to_delete.append(f"decrypted_response:{organization_id}:{doc_id}")
                redis_service.cache.delete(*keys_to_delete)
            
            audit_logger.info(f"AUDIT: FormResponse updated with ID {doc_id}")
            app_logger.info(f"Successfully completed FormResponseService.update for ID {doc_id}")
            return result
        except Exception as e:
            error_logger.error(f"Error in FormResponseService.update for ID {doc_id}: {str(e)}", exc_info=True)
            raise

    def delete(self, doc_id: str, organization_id: str = None, hard_delete: bool = False) -> None:
        """Override delete to invalidate decrypted response cache."""
        app_logger.info(f"Entering FormResponseService.delete for ID {doc_id}")
        try:
            from services.redis_service import redis_service
            from config.settings import settings
            
            super().delete(doc_id, organization_id, hard_delete)
            
            if settings.CACHE_ENABLED:
                keys_to_delete = [f"decrypted_response:{doc_id}"]
                if organization_id:
                    keys_to_delete.append(f"decrypted_response:{organization_id}:{doc_id}")
                redis_service.cache.delete(*keys_to_delete)
            
            audit_logger.info(f"AUDIT: FormResponse deleted with ID {doc_id}")
            app_logger.info(f"Successfully completed FormResponseService.delete for ID {doc_id}")
        except Exception as e:
            error_logger.error(f"Error in FormResponseService.delete for ID {doc_id}: {str(e)}", exc_info=True)
            raise

    def validate_payload(self, form_id: str, payload_data: Dict[str, Any], organization_id: str = None) -> Tuple[bool, Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
        """
        Dynamically cross-checks an incoming submission against the strict Option, Logic,
        and Validation rule sets using the unified FormValidationService.
        """
        app_logger.info(f"Entering validate_payload for Form ID {form_id}")
        from services.form_validation_service import FormValidationService
        
        # This service handles everything: version resolution, conditions, calculations, etc.
        is_valid, cleaned_data, errors, calculated_values = FormValidationService.validate_submission(
            form_id=form_id,
            payload=payload_data,
            organization_id=organization_id
        )
        
        if not is_valid:
            app_logger.warning(f"Payload validation failed for Form {form_id}: {errors}")
            raise ValidationError(f"Payload validation failed", details=errors)
            
        return is_valid, cleaned_data, errors, calculated_values

    def create_submission(self, data: FormResponseCreateSchema) -> FormResponseSchema:
        """Securely ingest a form submission executing payload validation first, wrapping with Idempotency."""
        app_logger.info(f"Entering create_submission for Form ID {data.form}")
        try:
            # --- Size Guard ---
            import json
            payload_size = len(json.dumps(data.data))
            if payload_size > 5 * 1024 * 1024: # 5MB limit
                raise ValidationError(f"Payload too large: {payload_size} bytes (max 5MB)")

            # --- Idempotency Check ---
            idempotency_key = data.data.get("idempotency_key")
            if idempotency_key:
                existing = FormResponse.objects(form=data.form, data__idempotency_key=idempotency_key).first()
                if existing:
                    app_logger.info(f"Idempotent submission trapped: form {data.form} key {idempotency_key}")
                    return self._to_schema(existing)
            
            # 1. Unified Validation (includes conditions, calculations, type checks)
            is_valid, cleaned_data, errors, calculated_values = self.validate_payload(
                form_id=str(data.form), 
                payload_data=data.data, 
                organization_id=data.organization_id
            )
            
            # Update data with cleaned and calculated values
            data.data = cleaned_data
            if calculated_values:
                if "meta_data" not in data.__dict__:
                    data.meta_data = {}
                data.meta_data["calculated_values"] = calculated_values

            app_logger.info(
                f"Incoming submission for form {data.form} from organization {data.organization_id}"
            )

            # 2. Fetch Active Version and Snapshot for the response record
            form_doc = Form.objects(id=data.form).first()
            if form_doc and form_doc.active_version:
                data.version = form_doc.active_version.version_string
                # Resolve FormVersion for snapshot reference
                from models.Form import FormVersion
                fv = FormVersion.objects(form=form_doc.id, version=form_doc.active_version.id).first()
                if fv:
                    data.form_version = str(fv.id)

            # Create the response document
            response = self.create(data)

            # Trigger background tasks
            try:
                from tasks.ai_tasks import async_index_response_vector
                async_index_response_vector.delay(str(response.id), data.organization_id)
            except Exception as e:
                error_logger.warning(f"Failed to enqueue vector indexing: {e}")

            # Publish Domain Event to decouple notification and webhook routing
            try:
                from services import event_bus
                event_bus.publish("form.submitted", {
                    "form_id": str(data.form),
                    "response_id": str(response.id),
                    "organization_id": data.organization_id,
                    "data": data.data,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            except Exception as e:
                error_logger.error(
                    f"Failed to publish domain event for response {response.id}: {str(e)}",
                    exc_info=True,
                )

            audit_logger.info(f"AUDIT: Form submission created for Form {data.form}, Response ID {response.id}")
            app_logger.info(f"Successfully completed create_submission for Form ID {data.form}")
            return response
        except Exception as e:
            error_logger.error(f"Error in create_submission for Form {data.form}: {str(e)}", exc_info=True)
            raise

    def list_by_form(
        self, form_id: str, organization_id: str, page: int = 1, page_size: int = 50
    ) -> PaginatedResult:
        """Pull highly paginated subsets of heavy analytics collections scoped to standard Tenant boundaries."""
        logger.debug(
            f"Pulling paginated responses for form {form_id} org {organization_id}"
        )
        return self.list_paginated(
            page=page,
            page_size=page_size,
            form=form_id,
            organization_id=organization_id,
            is_deleted=False,
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
