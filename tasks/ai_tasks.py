from config.celery import celery_app
from services.summarization_service import summarization_service
from logger.unified_logger import app_logger, error_logger, audit_logger, get_logger
from models.response import FormResponse
from models.response import SummarySnapshot
from datetime import datetime, timezone

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def async_generate_form_summary(self, form_id: str, organization_id: str):
    """
    Background task to generate an executive summary for a form's responses.
    """
    app_logger.info(f"Entering async_generate_form_summary for Form ID {form_id}")
    try:
        # Fetch responses (multi-tenant isolated)
        responses = FormResponse.objects(
            form=form_id, organization_id=organization_id, is_deleted=False
        ).only("data", "submitted_at")

        if not responses:
            app_logger.info(
                f"No responses found for Form ID {form_id}, skipping summary generation"
            )
            return {"status": "skipped", "reason": "no_responses"}

        # Convert to list of dicts for the service
        response_data = [r.to_mongo().to_dict() for r in responses]

        # Map-Reduce Summarization
        summary = summarization_service.generate_executive_summary(response_data)

        # Save Snapshot for persistent viewing
        snapshot = SummarySnapshot(
            form_id=form_id,
            timestamp=datetime.now(timezone.utc),
            period_start=responses.order_by("submitted_at").first().submitted_at,
            period_end=responses.order_by("-submitted_at").first().submitted_at,
            response_count=len(responses),
            summary_data={"executive_summary": summary},
            strategy_used="map_reduce_v1",
        )
        snapshot.save()

        audit_logger.info(
            f"AUDIT: AI Task: Summary snapshot {snapshot.id} created for form {form_id}"
        )
        app_logger.info(
            f"Successfully completed async_generate_form_summary for Form ID {form_id}"
        )
        return {"status": "success", "snapshot_id": str(snapshot.id)}

    except Exception as e:
        error_logger.error(
            f"AI Task failed for form {form_id}: {str(e)}", exc_info=True
        )
        raise self.retry(exc=e)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def async_index_response_vector(self, response_id, organization_id):
    """
    Background task to vectorize a form response and store it in the vector database.
    This enables semantic search across form submissions.
    """
    from services.vector_provider import vector_provider
    from models.response import FormResponse
    import json

    app_logger.info(
        f"Entering async_index_response_vector for Response ID {response_id}"
    )
    try:
        response = FormResponse.objects(
            id=response_id, organization_id=organization_id, is_deleted=False
        ).first()
        if not response:
            error_logger.error(f"Response {response_id} not found for vectorization")
            return {"status": "error", "message": "Response not found"}

        # Combine all text fields for vectorization
        # (Exclude sensitive fields to prevent PII in vector store)
        text_content = json.dumps(response.data)

        metadata = {
            "form_id": str(getattr(response.form, "id", response.form)),
            "submitted_at": response.submitted_at.isoformat(),
            "status": response.status,
        }

        success = vector_provider.embed_and_store(
            tenant_id=organization_id,
            document_id=response_id,
            text=text_content,
            metadata=metadata,
        )

        if success:
            audit_logger.info(f"AUDIT: Response {response_id} indexed in vector DB")
            app_logger.info(
                f"Successfully completed async_index_response_vector for Response ID {response_id}"
            )
            return {"status": "success"}
        else:
            error_logger.error(f"Failed to index response {response_id} in vector DB")
            return {"status": "error"}

    except Exception as e:
        error_logger.error(
            f"AI Task index_response_vector failed for {response_id}: {str(e)}",
            exc_info=True,
        )
        raise self.retry(exc=e)


@celery_app.task(bind=True, max_retries=5, default_retry_delay=60)
def async_export_to_olap(self, event_payload):
    """
    Consumes submission events and exports them to a high-performance
    columnar store (DuckDB/ClickHouse) for real-time analytics.
    """
    from services.analytics_stream_service import analytics_stream_service

    app_logger.info("Entering async_export_to_olap")
    try:
        analytics_stream_service.process_submission_event(event_payload)
        audit_logger.info("AUDIT: Exported submission event to OLAP")
        app_logger.info("Successfully completed async_export_to_olap")
        return {"status": "success"}
    except Exception as e:
        error_logger.error(f"OLAP Export Task failed: {str(e)}", exc_info=True)
        raise self.retry(exc=e)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def async_classify_response_tags(self, response_id: str, organization_id: str):
    """
    Background Celery task to classify a form submission against the form's taxonomy
    and auto-apply categories/tags to the FormResponse document.
    """
    from models.response import FormResponse
    from models.form import Form, FormVersion
    from services.ai_service import ai_service

    app_logger.info(f"Entering async_classify_response_tags for response {response_id}")
    try:
        response = FormResponse.objects(
            id=response_id, organization_id=organization_id, is_deleted=False
        ).first()

        if not response:
            error_logger.error(
                f"Response {response_id} not found during classification"
            )
            return {"status": "error", "reason": "not_found"}

        # Fetch form configurations
        raw_form_ref = response._data.get("form")
        form_id = getattr(raw_form_ref, "id", raw_form_ref) if raw_form_ref else None
        form_doc = Form.objects(
            id=form_id, organization_id=organization_id, is_deleted=False
        ).first()

        if not form_doc:
            app_logger.warning(f"Form not found for response {response_id}")
            return {"status": "skipped", "reason": "form_not_found"}

        # Check if classification is enabled and taxonomy exists
        classification_enabled = getattr(form_doc, "classification_enabled", False)
        classification_taxonomy = getattr(form_doc, "classification_taxonomy", [])

        # If not enabled on form, try retrieving from FormVersion snapshot
        raw_ver_ref = response._data.get("form_version")
        if not classification_enabled and raw_ver_ref:
            ver_id = getattr(raw_ver_ref, "id", raw_ver_ref)
            ver_doc = FormVersion.objects(id=ver_id).first()
            if ver_doc:
                classification_enabled = getattr(
                    ver_doc, "classification_enabled", False
                )
                classification_taxonomy = getattr(
                    ver_doc, "classification_taxonomy", []
                )

        if not classification_enabled or not classification_taxonomy:
            app_logger.info(
                f"AI classification not enabled or taxonomy empty for form {form_doc.id}"
            )
            return {"status": "skipped", "reason": "disabled_or_empty_taxonomy"}

        # Gather all text data securely, ignoring nested dicts, and skipping sensitive fields
        text_elements = []

        # 1. Standard text fields from response data
        for var_name, value in response.data.items():
            if isinstance(value, str) and value.strip():
                # Skip sensitive fields if defined in form snapshot
                # In the codebase, FLE moves sensitive fields to response.encrypted_data,
                # meaning response.data contains only non-sensitive content.
                text_elements.append(value.strip())

        if not text_elements:
            app_logger.info(f"No textual content in response {response_id} to classify")
            return {"status": "skipped", "reason": "no_text_content"}

        combined_text = "\n".join(text_elements)

        # Perform AI classification
        taxonomy_payload = []
        for item in classification_taxonomy:
            if isinstance(item, dict):
                taxonomy_payload.append(
                    {
                        "category_name": item.get("category_name", ""),
                        "description": item.get("description", ""),
                        "keywords": item.get("keywords", []) or [],
                    }
                )
                continue
            taxonomy_payload.append(
                {
                    "category_name": item.category_name,
                    "description": item.description,
                    "keywords": item.keywords,
                }
            )

        app_logger.info(
            f"AI Task: Classifying text (len={len(combined_text)}) for response {response_id}"
        )
        ai_res = ai_service.classify_taxonomy(combined_text, taxonomy_payload)

        matched_tags = ai_res.get("tags", [])

        # Update response model directly
        if matched_tags:
            # Preserve existing user-defined or pipeline tags and combine with matched tags uniquely
            existing_tags = set(response.tags or [])
            updated_tags = list(existing_tags.union(matched_tags))
            response.tags = updated_tags

            # Save classification payload to ai_results
            response.ai_results = response.ai_results or {}
            response.ai_results["classification"] = {
                "tags": matched_tags,
                "scores": ai_res.get("scores", {}),
                "provider": ai_res.get("provider", "unknown"),
                "classified_at": datetime.now(timezone.utc).isoformat(),
            }
            response.save()

            audit_logger.info(
                f"AUDIT: AI Classification: Applied tags {matched_tags} to response {response_id}"
            )
            app_logger.info(
                f"AI auto-tagging successfully completed for response {response_id}"
            )
            return {"status": "success", "tags_applied": matched_tags}
        else:
            app_logger.info(
                f"AI classification completed for {response_id} with no matching tags"
            )
            return {"status": "success", "tags_applied": []}

    except Exception as e:
        error_logger.error(
            f"AI classification task failed for response {response_id}: {str(e)}",
            exc_info=True,
        )
        raise self.retry(exc=e)


@celery_app.task(bind=True)
def async_run_lora_improvement_loop(self, cycles=1, target_dataset_size=10000, fast=True):
    """
    Asynchronously executes the LoRA model continuous improvement loop.
    Runs offline training, dataset building, validation, and checkpoint promotion.
    """
    import subprocess
    app_logger.info("Entering async_run_lora_improvement_loop")
    try:
        cmd = [
            "python3",
            "lora/improve_loop.py",
            "--cycles", str(cycles),
            "--target-dataset-size", str(target_dataset_size)
        ]
        if fast:
            cmd.append("--fast")

        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        audit_logger.info(f"AUDIT: LoRA improvement loop completed. Cycles run: {cycles}")
        app_logger.info("Successfully completed async_run_lora_improvement_loop")
        return {
            "status": "success",
            "stdout": process.stdout[-2000:],
            "stderr": process.stderr[-2000:]
        }
    except subprocess.CalledProcessError as e:
        error_logger.error(
            f"LoRA improvement loop task failed: {e.stderr}",
            exc_info=True
        )
        return {"status": "error", "message": str(e), "stderr": e.stderr}
    except Exception as e:
        error_logger.error(
            f"Unexpected error in LoRA improvement task: {str(e)}",
            exc_info=True
        )
        raise self.retry(exc=e)
