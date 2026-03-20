from datetime import datetime, timezone
from typing import List, Dict, Any
from logger import get_logger, access_logger, error_logger, log_performance
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
        from services.redis_service import redis_service
        from config.settings import settings
        from utils.encryption import batch_decrypt_values
        
        cache_key = f"decrypted_response:{response_id}"
        
        if settings.CACHE_ENABLED:
            cached = redis_service.cache.get(cache_key)
            if cached:
                return cached
        
        # Fetch from DB
        response = self.model.objects(id=response_id, organization_id=organization_id, is_deleted=False).first()
        if not response:
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
            
        return result

    def update(self, doc_id: str, update_schema: TUpdateSchema, organization_id: str = None) -> TSchema:
        """Override update to invalidate decrypted response cache."""
        from services.redis_service import redis_service
        from config.settings import settings
        
        result = super().update(doc_id, update_schema, organization_id)
        
        if settings.CACHE_ENABLED:
            redis_service.cache.delete(f"decrypted_response:{doc_id}")
            
        return result

    def delete(self, doc_id: str, organization_id: str = None, hard_delete: bool = False) -> None:
        """Override delete to invalidate decrypted response cache."""
        from services.redis_service import redis_service
        from config.settings import settings
        
        super().delete(doc_id, organization_id, hard_delete)
        
        if settings.CACHE_ENABLED:
            redis_service.cache.delete(f"decrypted_response:{doc_id}")

    def validate_payload(self, form_id: str, payload_data: Dict[str, Any]) -> bool:
        """
        Dynamically cross-checks an incoming submission against the strict Option, Logic,
        and Validation rule sets using a cached Pydantic model.
        """
        from models.Form import Form, FormVersion
        from utils.schema_generator import generate_form_model

        form = Form.objects(id=form_id, is_deleted=False).first()
        if not form:
            raise NotFoundError("Master Form architecture not found for validation")

        if form.status != "published":
            access_logger.warning(f"Submission rejected: Form {form_id} is not live.")
            raise ValidationError("Form is inactive or archived")

        # 1. Fetch the active FormVersion
        if not form.active_version:
             raise ValidationError("No active version found for this form")
             
        version_doc = FormVersion.objects(form=form.id, version=form.active_version).first()
        if not version_doc:
             raise ValidationError("Active form version definition not found")

        # 2. Generate/Fetch Cached Pydantic Model
        try:
            DynamicModel = generate_form_model(str(version_doc.id), version_doc.sections)
            # 3. Validate
            DynamicModel(**payload_data)
        except Exception as ve:
            logger.debug(f"Payload validation failed: {str(ve)}")
            raise ValidationError(f"Payload validation failed: {str(ve)}")
        
        return True

    def create_submission(self, data: FormResponseCreateSchema) -> FormResponseSchema:
        """Securely ingest a form submission executing payload validation first, wrapping with Idempotency."""
        # --- Idempotency Check ---
        idempotency_key = data.data.get("idempotency_key")
        if idempotency_key:
            existing = FormResponse.objects(form=data.form, data__idempotency_key=idempotency_key).first()
            if existing:
                access_logger.info(f"Idempotent submission trapped: form {data.form} key {idempotency_key}")
                return self._to_schema(existing)
        
        self.validate_payload(data.form, data.data)
        access_logger.info(
            f"Incoming submission for form {data.form} from organization {data.organization_id}"
        )

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

        return response

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
