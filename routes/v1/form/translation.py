from . import form_bp
from flasgger import swag_from
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from models import Form
from models.TranslationJob import TranslationJob
from routes.v1.form.helper import get_current_user, has_form_permission
from services.ai_service import AIService
from datetime import datetime, timezone

translation_bp = Blueprint("translation", __name__)


from utils.response_helper import success_response, error_response, BaseSerializer

@translation_bp.route("", methods=["GET"])
@swag_from({
    "tags": [
        "Translation"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
def get_translations():
    app_logger.info("Entering get_translations")
    form_id = request.args.get("form_id")
    language = request.args.get("language")

    if not form_id:
        app_logger.warning("Missing form_id in get_translations")
        return error_response(message="Missing form_id", status_code=400)

    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)
        if not has_form_permission(current_user, form, "view"):
            app_logger.warning(f"Unauthorized access attempt to translations for form {form_id} by user {current_user.id}")
            return error_response(message="Unauthorized", status_code=403)

        if not form.versions:
            app_logger.info(f"Form {form_id} has no versions, returning empty translations")
            return success_response(data={"language": language, "translations": {}})

        latest_version = form.versions[-1]
        translations = latest_version.translations or {}

        app_logger.info(f"Exiting get_translations for form_id: {form_id}")
        if language:
            return success_response(data={
                "language": language,
                "translations": translations.get(language, {}),
            })

        return success_response(data=translations)
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Error in get_translations for form {form_id}: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@translation_bp.route("", methods=["POST"])
@swag_from({
    "tags": [
        "Translation"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
def save_translations():
    app_logger.info("Entering save_translations")
    data = request.get_json()
    form_id = data.get("form_id")
    language = data.get("language")
    translations = data.get("translations")

    if not form_id or not language or translations is None:
        app_logger.warning("Missing required fields in save_translations")
        return error_response(message="Missing form_id, language, or translations", status_code=400)

    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)
        if not has_form_permission(current_user, form, "edit"):
            app_logger.warning(f"Unauthorized attempt to save translations for form {form_id} by user {current_user.id}")
            return error_response(message="Unauthorized", status_code=403)

        if not form.versions:
            app_logger.warning(f"Attempt to save translations for form {form_id} which has no versions")
            return error_response(message="Form has no versions", status_code=400)

        latest_version = form.versions[-1]
        if not latest_version.translations:
            latest_version.translations = {}

        latest_version.translations[language] = translations
        form.save()

        audit_logger.info(f"User {current_user.id} saved translations for form {form_id} and language {language}", extra={
            "user_id": str(current_user.id),
            "form_id": form_id,
            "language": language,
            "action": "save_translations"
        })

        app_logger.info(f"Exiting save_translations for form_id: {form_id}")
        return success_response(message="Translations saved successfully")
    except DoesNotExist:
        return error_response(message="Form not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Error in save_translations for form {form_id}: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@translation_bp.route("/languages", methods=["GET"])
@swag_from({
    "tags": [
        "Translation"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
def list_languages():
    app_logger.info("Entering list_languages")
    languages = [
        {"code": "en", "name": "English", "native_name": "English"},
        {"code": "es", "name": "Spanish", "native_name": "Español"},
        {"code": "fr", "name": "French", "native_name": "Français"},
        {"code": "de", "name": "German", "native_name": "Deutsch"},
        {"code": "it", "name": "Italian", "native_name": "Italiano"},
        {"code": "pt", "name": "Portuguese", "native_name": "Português"},
        {"code": "ru", "name": "Russian", "native_name": "Русский"},
        {"code": "zh", "name": "Chinese", "native_name": "中文"},
        {"code": "ja", "name": "Japanese", "native_name": "日本語"},
        {"code": "ko", "name": "Korean", "native_name": "한국어"},
        {"code": "hi", "name": "Hindi", "native_name": "हिन्दी"},
        {"code": "ar", "name": "Arabic", "native_name": "العربية"},
    ]
    app_logger.info("Exiting list_languages")
    return success_response(data=languages)


@translation_bp.route("/preview", methods=["POST"])
@swag_from({
    "tags": [
        "Translation"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
def preview_translation():
    app_logger.info("Entering preview_translation")
    data = request.get_json()
    text = data.get("text")
    source_lang = data.get("source_language", "en")
    target_lang = data.get("target_language")

    if not text or not target_lang:
        app_logger.warning("Missing text or target_language in preview_translation")
        return error_response(message="Missing text or target_language", status_code=400)

    try:
        translated = AIService.translate_text(text, source_lang, target_lang)
        app_logger.info("Exiting preview_translation")
        return success_response(data={"translated_text": translated})
    except Exception as e:
        error_logger.error(f"Error in preview_translation: {str(e)}", exc_info=True)
        return error_response(message="Translation preview failed", status_code=500)


@translation_bp.route("/jobs", methods=["GET", "POST"])
@swag_from({
    "tags": [
        "Translation"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
def handle_jobs():
    if request.method == "GET":
        app_logger.info("Entering handle_jobs (GET)")
        form_id = request.args.get("form_id")
        if not form_id:
            app_logger.warning("Missing form_id in handle_jobs (GET)")
            return error_response(message="Missing form_id", status_code=400)

        try:
            current_user = get_current_user()
            jobs = TranslationJob.objects(form_id=form_id).order_by("-created_at")
            app_logger.info(f"Exiting handle_jobs (GET) for form_id: {form_id}")
            return success_response(data=[BaseSerializer.clean_dict(job.to_mongo().to_dict()) for job in jobs])
        except Exception as e:
            error_logger.error(f"Error in handle_jobs (GET) for form {form_id}: {str(e)}", exc_info=True)
            return error_response(message="Failed to fetch jobs", status_code=500)

    # POST - Start a new job
    app_logger.info("Entering handle_jobs (POST)")
    data = request.get_json()
    form_id = data.get("form_id")
    source_lang = data.get("source_language", "en")
    target_languages = data.get("target_languages", [])
    total_fields = data.get("total_fields", 0)

    if not form_id or not target_languages:
        app_logger.warning("Missing required fields in handle_jobs (POST)")
        return error_response(message="Missing form_id or target_languages", status_code=400)

    current_user = get_current_user()
    try:
        form = Form.objects.get(id=form_id, organization_id=current_user.organization_id)
        if not has_form_permission(current_user, form, "edit"):
            app_logger.warning(f"Unauthorized attempt to start translation job for form {form_id} by user {current_user.id}")
            return error_response(message="Unauthorized", status_code=403)

        job = TranslationJob(
            form_id=form_id,
            source_language=source_lang,
            target_languages=target_languages,
            total_fields=total_fields,
            created_by=str(current_user.id),
            status="pending",
        )
        job.save()

        audit_logger.info(f"User {current_user.id} started translation job {job.id} for form {form_id}", extra={
            "user_id": str(current_user.id),
            "form_id": form_id,
            "job_id": str(job.id),
            "target_languages": target_languages,
            "action": "start_translation_job"
        })

        # Start background processing
        from tasks.form_tasks import async_process_translation_job
        async_process_translation_job.delay(str(job.id))

        app_logger.info(f"Exiting handle_jobs (POST) for form_id: {form_id}, job_id: {job.id}")
        return success_response(
            data={"job_id": str(job.id)},
            message="Translation job started",
            status_code=201
        )

    except Exception as e:
        error_logger.error(f"Error starting translation job for form {form_id}: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@translation_bp.route("/jobs/<job_id>", methods=["GET"])
@swag_from({
    "tags": [
        "Translation"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "job_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def get_job_status(job_id):
    app_logger.info(f"Entering get_job_status for job_id: {job_id}")
    try:
        job = TranslationJob.objects.get(id=job_id)
        app_logger.info(f"Exiting get_job_status for job_id: {job_id}")
        return success_response(data=BaseSerializer.clean_dict(job.to_mongo().to_dict()))
    except Exception as e:
        app_logger.warning(f"Translation job not found: {job_id}")
        return error_response(message="Job not found", status_code=404)


@translation_bp.route("/jobs/<job_id>/cancel", methods=["PATCH"])
@swag_from({
    "tags": [
        "Translation"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "job_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def cancel_job(job_id):
    app_logger.info(f"Entering cancel_job for job_id: {job_id}")
    try:
        current_user = get_current_user()
        job = TranslationJob.objects.get(id=job_id)
        if job.status in ["pending", "in_progress"]:
            job.status = "cancelled"
            job.save()
            
            audit_logger.info(f"User {current_user.id} cancelled translation job {job_id}", extra={
                "user_id": str(current_user.id),
                "job_id": job_id,
                "action": "cancel_translation_job"
            })
            
            app_logger.info(f"Exiting cancel_job for job_id: {job_id}")
            return success_response(message="Job cancelled")
        
        app_logger.warning(f"Cannot cancel job {job_id} in {job.status} state")
        return error_response(message=f"Cannot cancel job in {job.status} state", status_code=400)
    except Exception as e:
        app_logger.warning(f"Translation job not found for cancellation: {job_id}")
        return error_response(message="Job not found", status_code=404)


@translation_bp.route("/jobs/<job_id>", methods=["DELETE"])
@swag_from({
    "tags": [
        "Translation"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "job_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def delete_job(job_id):
    app_logger.info(f"Entering delete_job for job_id: {job_id}")
    try:
        current_user = get_current_user()
        job = TranslationJob.objects.get(id=job_id)
        job.delete()
        
        audit_logger.info(f"User {current_user.id} deleted translation job {job_id}", extra={
            "user_id": str(current_user.id),
            "job_id": job_id,
            "action": "delete_translation_job"
        })
        
        app_logger.info(f"Exiting delete_job for job_id: {job_id}")
        return success_response(message="Job deleted")
    except Exception as e:
        app_logger.warning(f"Translation job not found for deletion: {job_id}")
        return error_response(message="Job not found", status_code=404)


@translation_bp.route("/jobs/<job_id>/content", methods=["GET"])
@swag_from({
    "tags": [
        "Translation"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "job_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def get_translated_content(job_id):
    app_logger.info(f"Entering get_translated_content for job_id: {job_id}")
    try:
        job = TranslationJob.objects.get(id=job_id)
        if job.status != "completed":
            app_logger.warning(f"Attempt to fetch content for incomplete job {job_id} (status: {job.status})")
            return error_response(message="Job not completed yet", status_code=400)

        app_logger.info(f"Exiting get_translated_content for job_id: {job_id}")
        return success_response(data={"form_id": str(job.form_id), "results": job.results})
    except Exception as e:
        app_logger.warning(f"Translation job not found: {job_id}")
        return error_response(message="Job not found", status_code=404)


