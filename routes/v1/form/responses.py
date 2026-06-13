from . import form_bp
from flasgger import swag_from
from flask import request, jsonify, current_app
from flask import g
from flask_jwt_extended import jwt_required, get_jwt_identity
from routes.v1.form import form_bp
from services.response_service import FormResponseService, FormResponseCreateSchema
from routes.v1.form.helper import get_current_user, has_form_permission
from models.Form import Form, FormVersion, Project
from models.Response import FormResponse
from mongoengine import DoesNotExist
from bson.dbref import DBRef
from logger.unified_logger import app_logger, error_logger, audit_logger
from datetime import datetime, timezone
from bson import json_util
from bson.binary import Binary, UuidRepresentation

from utils.response_helper import success_response, error_response

response_service = FormResponseService()


@form_bp.route("/<form_id>/responses", methods=["POST"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {"200": {"description": "Success"}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True},
            {
                "name": "body",
                "in": "body",
                "schema": {"$ref": "#/definitions/FormResponseCreateSchema"},
            },
        ],
    }
)
@jwt_required()
def submit_response(form_id):
    """
    Authenticated form submission.
    """
    app_logger.info(f"Entering submit_response for form_id: {form_id}")
    current_user = get_current_user()
    data = request.get_json()

    try:
        from uuid import UUID

        try:
            form_uuid = UUID(form_id)
        except ValueError:
            app_logger.warning(f"Invalid form ID format: {form_id}")
            return error_response(message="Invalid form ID format", status_code=400)

        form = Form.objects.get(
            id=form_uuid,
            organization_id=current_user.organization_id,
            is_deleted=False,
        )

        # 1. Permission Check
        if not has_form_permission(current_user, form, "submit"):
            app_logger.warning(
                f"User {current_user.id} does not have permission to submit to form {form_id}"
            )
            return error_response(
                message="You do not have permission to submit to this form",
                status_code=403,
            )

        # 2. Lifecycle Check
        now = datetime.now(timezone.utc)
        if form.expires_at and form.expires_at.replace(tzinfo=timezone.utc) < now:
            app_logger.warning(
                f"Submission rejected: Form {form_id} expired at {form.expires_at}"
            )
            return error_response(message="This form has expired", status_code=400)

        if form.publish_at and form.publish_at.replace(tzinfo=timezone.utc) > now:
            app_logger.warning(
                f"Submission rejected: Form {form_id} is scheduled for {form.publish_at}"
            )
            return error_response(
                message="This form is not yet available", status_code=400
            )

        # 3. Validation & Service Call
        submission_data = {
            "form": str(form.id),
            "organization_id": current_user.organization_id,
            "data": data.get("data", {}),
            "submitted_by": str(current_user.id),
            "ip_address": request.remote_addr,
            "user_agent": request.user_agent.string,
        }

        form_project = form._data.get("project")
        if isinstance(form_project, DBRef):
            submission_data["project"] = str(form_project.id)
        elif hasattr(form_project, "id"):
            submission_data["project"] = str(form_project.id)
        elif form_project:
            submission_data["project"] = str(form_project)

        create_schema = FormResponseCreateSchema(**submission_data)
        response = response_service.create_submission(create_schema)

        audit_logger.info(
            f"User {current_user.id} submitted response {response.id} to form {form_id}",
            extra={
                "user_id": str(current_user.id),
                "form_id": form_id,
                "response_id": str(response.id),
                "organization_id": current_user.organization_id,
                "action": "submit_response",
            },
        )

        app_logger.info(
            f"Exiting submit_response for form_id: {form_id}, response_id: {response.id}"
        )
        return success_response(
            data={"response_id": str(response.id)},
            message="Response submitted successfully",
            status_code=201,
        )

    except DoesNotExist:
        error_logger.error(f"Form {form_id} not found: {form_id}", exc_info=True)
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(
            f"Error submitting response to form {form_id}: {str(e)}", exc_info=True
        )
        return error_response(message="Failed to submit response", status_code=400)


@form_bp.route("/<form_id>/responses", methods=["GET"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {"200": {"description": "Success"}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
def list_responses(form_id):
    """
    List responses for a specific form (paginated).
    """
    app_logger.info(f"Entering list_responses for form_id: {form_id}")
    current_user = get_current_user()
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)

    try:
        from uuid import UUID

        try:
            project_uuid = (
                UUID(str(g.project_id)) if getattr(g, "project_id", None) else None
            )
        except ValueError:
            app_logger.warning(
                f"Invalid project ID format: {getattr(g, 'project_id', None)}"
            )
            return error_response(message="Invalid project ID format", status_code=400)

        project_doc = None
        if project_uuid:
            project_doc = Project.objects.get(
                id=project_uuid,
                organization_id=current_user.organization_id,
                is_deleted=False,
            )

        try:
            form_uuid = UUID(str(form_id))
        except ValueError:
            app_logger.warning(f"Invalid form ID format: {form_id}")
            return error_response(message="Invalid form ID format", status_code=400)

        form = None
        if project_doc:
            for form_ref in project_doc.forms or []:
                ref_id = getattr(form_ref, "id", form_ref)
                if str(ref_id) == str(form_uuid):
                    form = Form.objects.get(
                        id=ref_id,
                        organization_id=current_user.organization_id,
                        is_deleted=False,
                    )
                    break
        if not form:
            form = Form.objects.get(
                id=form_uuid,
                organization_id=current_user.organization_id,
                is_deleted=False,
            )

        if not form:
            app_logger.warning(f"Form not found: {form_id}")
            return error_response(
                message=f"Form not found : {form_id}", status_code=404
            )

        if not has_form_permission(current_user, form, "view_responses"):
            app_logger.warning(
                f"User {current_user.id} does not have permission to view responses for form {form_id}"
            )
            return error_response(
                message="You do not have permission to view responses for this form",
                status_code=403,
            )

        app_logger.info(f"Form id : {form.id} org id : {current_user.organization_id}")

        target_form_binary = Binary.from_uuid(
            UUID(form_id),
            uuid_representation=UuidRepresentation.PYTHON_LEGACY,
        )

        query = FormResponse.objects(
            __raw__={
                "organization_id": current_user.organization_id,
                "is_deleted": False,
                "form": target_form_binary,
            }
        )
        app_logger.info("Pass 1")
        total = query.count()
        items = (
            query.order_by("-created_at").skip((page - 1) * page_size).limit(page_size)
        )
        payload = [response_service._to_schema(item).model_dump() for item in items]
        app_logger.info("Pass 2")

        result = {
            "items": payload,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": (page * page_size) < total,
            "success": True,
        }

        app_logger.info(
            f"Exiting list_responses for form_id: {form_id}, count: {len(payload)}"
        )
        return success_response(data=result)

    except DoesNotExist as e:
        app_logger.warning(
            f"Form {form_id} not found: {form_id} {str(e)}", exc_info=True
        )
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        app_logger.warning(
            f"Error listing responses for form {form_id}: {str(e)}", exc_info=True
        )
        return error_response(message="Failed to list responses", status_code=400)


@form_bp.route("/<form_id>/responses/sync", methods=["POST"])
@jwt_required()
def sync_responses(form_id):
    """
    Sync offline submissions.
    Supports conflict resolution ('server_wins' or 'client_wins').
    """
    app_logger.info(f"Entering sync_responses for form_id: {form_id}")
    current_user = get_current_user()
    payload_data = request.get_json() or {}
    submissions = payload_data.get("submissions", [])
    conflict_resolution = payload_data.get("conflict_resolution", "server_wins")
    last_synced_at_raw = (
        request.args.get("last_synced_at") or payload_data.get("last_synced_at")
    )
    tombstone_entity_types = payload_data.get("tombstone_entity_types")

    if not isinstance(submissions, list):
        return error_response(message="Submissions must be a list", status_code=400)

    try:
        from uuid import UUID
        try:
            form_uuid = UUID(form_id)
        except ValueError:
            return error_response(message="Invalid form ID format", status_code=400)

        form = Form.objects.get(
            id=form_uuid,
            organization_id=current_user.organization_id,
            is_deleted=False,
        )

        if not has_form_permission(current_user, form, "submit"):
            return error_response(
                message="You do not have permission to submit to this form",
                status_code=403,
            )

        tombstones = []
        if last_synced_at_raw:
            try:
                if isinstance(last_synced_at_raw, str):
                    normalized_last_synced_at = last_synced_at_raw.replace("Z", "+00:00")
                    last_synced_at = datetime.fromisoformat(normalized_last_synced_at)
                else:
                    last_synced_at = last_synced_at_raw
                from services.tombstone_service import TombstoneService

                tombstone_service = TombstoneService()
                tombstones = tombstone_service.list_since(
                    organization_id=current_user.organization_id,
                    since=last_synced_at,
                    entity_types=tombstone_entity_types
                    if isinstance(tombstone_entity_types, list)
                    else None,
                )
            except ValueError:
                return error_response(
                    message="Invalid last_synced_at format", status_code=400
                )

        results = []
        for sub in submissions:
            sub_data = sub.get("data", {})
            idempotency_key = sub.get("idempotency_key") or sub_data.get("idempotency_key")
            
            if not idempotency_key:
                results.append({
                    "status": "failed",
                    "error": "idempotency_key is required for offline sync to prevent duplicates"
                })
                continue

            existing = FormResponse.objects(
                __raw__={
                    "form": str(form.id),
                    "organization_id": current_user.organization_id,
                    "idempotency_key": idempotency_key,
                    "is_deleted": False,
                }
            ).first()

            if existing:
                if conflict_resolution == "client_wins":
                    try:
                        is_valid, cleaned_data, errors, calculated_values = response_service.validate_payload(
                            form_id=str(form.id),
                            payload_data=sub_data,
                            organization_id=current_user.organization_id
                        )
                        existing.data = cleaned_data or sub_data
                        if calculated_values:
                            if not existing.meta_data:
                                existing.meta_data = {}
                            existing.meta_data["calculated_values"] = calculated_values
                        existing.updated_at = datetime.now(timezone.utc)
                        existing.save()
                        
                        from services.redis_service import redis_service
                        from config.settings import settings
                        if settings.CACHE_ENABLED:
                            redis_service.cache.delete(
                                f"decrypted_response:{existing.id}",
                                f"decrypted_response:{current_user.organization_id}:{existing.id}"
                            )

                        # Invalidate analytics cache
                        try:
                            from services.analytics_cache import analytics_cache
                            analytics_cache.invalidate_form(str(form.id))
                        except Exception as cache_err:
                            app_logger.warning(f"Failed to invalidate analytics cache in sync: {cache_err}")

                        results.append({
                            "idempotency_key": idempotency_key,
                            "status": "conflict_resolved_client",
                            "response_id": str(existing.id)
                        })
                        audit_logger.info(f"AUDIT: Offline sync updated response {existing.id} (client_wins)")
                    except Exception as val_err:
                        results.append({
                            "idempotency_key": idempotency_key,
                            "status": "validation_failed",
                            "error": str(val_err)
                        })
                else:
                    results.append({
                        "idempotency_key": idempotency_key,
                        "status": "conflict_resolved_server",
                        "response_id": str(existing.id)
                    })
            else:
                submission_data = {
                    "form": str(form.id),
                    "organization_id": current_user.organization_id,
                    "data": sub_data,
                    "submitted_by": str(current_user.id),
                    "ip_address": request.remote_addr,
                    "user_agent": request.user_agent.string,
                    "idempotency_key": idempotency_key,
                }
                
                form_project = form._data.get("project")
                if isinstance(form_project, DBRef):
                    submission_data["project"] = str(form_project.id)
                elif hasattr(form_project, "id"):
                    submission_data["project"] = str(form_project.id)
                elif form_project:
                    submission_data["project"] = str(form_project)

                try:
                    create_schema = FormResponseCreateSchema(**submission_data)
                    new_resp = response_service.create_submission(create_schema)
                    results.append({
                        "idempotency_key": idempotency_key,
                        "status": "created",
                        "response_id": str(new_resp.id)
                    })
                except Exception as e:
                    results.append({
                        "idempotency_key": idempotency_key,
                        "status": "failed",
                        "error": str(e)
                    })

        response_payload = {"results": results}
        if last_synced_at_raw:
            response_payload["tombstones"] = tombstones
        return success_response(data=response_payload)

    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Error syncing responses: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)
