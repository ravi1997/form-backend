from . import form_bp
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from models import Form
from models.TranslationJob import TranslationJob
from routes.v1.form.helper import get_current_user, has_form_permission
from services.ai_service import AIService
from datetime import datetime, timezone
import threading

translation_bp = Blueprint("translation", __name__)


@translation_bp.route("", methods=["GET"])
@jwt_required()
def get_translations():
    form_id = request.args.get("form_id")
    language = request.args.get("language")

    if not form_id:
        return jsonify({"error": "Missing form_id"}), 400

    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)
        if not has_form_permission(current_user, form, "view"):
            return jsonify({"error": "Unauthorized"}), 403

        if not form.versions:
            return jsonify({"language": language, "translations": {}}), 200

        latest_version = form.versions[-1]
        translations = latest_version.translations or {}

        if language:
            return (
                jsonify(
                    {
                        "language": language,
                        "translations": translations.get(language, {}),
                    }
                ),
                200,
            )

        return jsonify(translations), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@translation_bp.route("", methods=["POST"])
@jwt_required()
def save_translations():
    data = request.get_json()
    form_id = data.get("form_id")
    language = data.get("language")
    translations = data.get("translations")

    if not form_id or not language or translations is None:
        return jsonify({"error": "Missing form_id, language, or translations"}), 400

    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)
        if not has_form_permission(current_user, form, "edit"):
            return jsonify({"error": "Unauthorized"}), 403

        if not form.versions:
            return jsonify({"error": "Form has no versions"}), 400

        latest_version = form.versions[-1]
        if not latest_version.translations:
            latest_version.translations = {}

        latest_version.translations[language] = translations
        form.save()

        return jsonify({"message": "Translations saved successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@translation_bp.route("/languages", methods=["GET"])
@jwt_required()
def list_languages():
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
    return jsonify(languages), 200


@translation_bp.route("/preview", methods=["POST"])
@jwt_required()
def preview_translation():
    data = request.get_json()
    text = data.get("text")
    source_lang = data.get("source_language", "en")
    target_lang = data.get("target_language")

    if not text or not target_lang:
        return jsonify({"error": "Missing text or target_language"}), 400

    translated = AIService.translate_text(text, source_lang, target_lang)
    return jsonify({"translated_text": translated}), 200


@translation_bp.route("/jobs", methods=["GET", "POST"])
@jwt_required()
def handle_jobs():
    if request.method == "GET":
        form_id = request.args.get("form_id")
        if not form_id:
            return jsonify({"error": "Missing form_id"}), 400

        jobs = TranslationJob.objects(form_id=form_id).order_by("-created_at")
        return jsonify([job.to_dict() for job in jobs]), 200

    # POST - Start a new job
    data = request.get_json()
    form_id = data.get("form_id")
    source_lang = data.get("source_language", "en")
    target_languages = data.get("target_languages", [])
    total_fields = data.get("total_fields", 0)

    if not form_id or not target_languages:
        return jsonify({"error": "Missing form_id or target_languages"}), 400

    current_user = get_current_user()
    try:
        form = Form.objects.get(id=form_id)
        if not has_form_permission(current_user, form, "edit"):
            return jsonify({"error": "Unauthorized"}), 403

        job = TranslationJob(
            form_id=form_id,
            source_language=source_lang,
            target_languages=target_languages,
            total_fields=total_fields,
            created_by=str(current_user.id),
            status="pending",
        )
        job.save()

        # Start background processing
        thread = threading.Thread(
            target=process_translation_job,
            args=(job.id, current_app._get_current_object()),
        )
        thread.start()

        return jsonify({"message": "Translation job started", "job_id": job.id}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@translation_bp.route("/jobs/<job_id>", methods=["GET"])
@jwt_required()
def get_job_status(job_id):
    try:
        job = TranslationJob.objects.get(id=job_id)
        return jsonify(job.to_dict()), 200
    except Exception:
        return jsonify({"error": "Job not found"}), 404


@translation_bp.route("/jobs/<job_id>/cancel", methods=["PATCH"])
@jwt_required()
def cancel_job(job_id):
    try:
        job = TranslationJob.objects.get(id=job_id)
        if job.status in ["pending", "in_progress"]:
            job.status = "cancelled"
            job.save()
            return jsonify({"message": "Job cancelled"}), 200
        return jsonify({"error": f"Cannot cancel job in {job.status} state"}), 400
    except Exception:
        return jsonify({"error": "Job not found"}), 404


@translation_bp.route("/jobs/<job_id>", methods=["DELETE"])
@jwt_required()
def delete_job(job_id):
    try:
        job = TranslationJob.objects.get(id=job_id)
        job.delete()
        return jsonify({"message": "Job deleted"}), 200
    except Exception:
        return jsonify({"error": "Job not found"}), 404


@translation_bp.route("/jobs/<job_id>/content", methods=["GET"])
@jwt_required()
def get_translated_content(job_id):
    try:
        job = TranslationJob.objects.get(id=job_id)
        if job.status != "completed":
            return jsonify({"error": "Job not completed yet"}), 400

        return jsonify({"form_id": job.form_id, "results": job.results}), 200
    except Exception:
        return jsonify({"error": "Job not found"}), 404


# Helper for background processing
def process_translation_job(job_id, app):
    with app.app_context():
        try:
            job = TranslationJob.objects.get(id=job_id)
            if job.status == "cancelled":
                return

            job.status = "inProgress"
            job.started_at = datetime.now(timezone.utc)
            job.save()

            form = Form.objects.get(id=job.form_id)
            if not form.versions:
                raise Exception("Form has no versions")

            latest_version = form.versions[-1]

            # Extract translatable items
            translatable_items = {
                "title": form.title,
                "description": form.description or "",
            }

            for section in latest_version.sections:
                translatable_items[f"section_{section.id}_title"] = section.title
                if section.description:
                    translatable_items[f"section_{section.id}_desc"] = (
                        section.description
                    )

                for question in section.questions:
                    translatable_items[f"question_{question.id}_label"] = question.label
                    if question.help_text:
                        translatable_items[f"question_{question.id}_help"] = (
                            question.help_text
                        )
                    if question.placeholder:
                        translatable_items[f"question_{question.id}_place"] = (
                            question.placeholder
                        )

                    for option in question.options:
                        translatable_items[f"option_{option.id}_label"] = (
                            option.option_label
                        )

            results = {}
            total_langs = len(job.target_languages)

            for i, lang in enumerate(job.target_languages):
                if job.reload().status == "cancelled":
                    break

                try:
                    translated_dict = AIService.translate_bulk(
                        translatable_items, job.source_language, lang
                    )

                    # Update form with translations
                    if not latest_version.translations:
                        latest_version.translations = {}

                    latest_version.translations[lang] = translated_dict
                    form.save()

                    results[lang] = {
                        "success": True,
                        "success_count": len(translated_dict),
                        "failure_count": 0,
                    }

                    job.completed_fields += 1  # In this case it's languages
                except Exception as e:
                    results[lang] = {
                        "success": False,
                        "success_count": 0,
                        "failure_count": 1,
                        "error_message": str(e),
                    }
                    job.failed_fields += 1

                job.progress = int(((i + 1) / total_langs) * 100)
                job.save()

            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.results = results
            job.save()

        except Exception as e:
            try:
                job = TranslationJob.objects.get(id=job_id)
                job.status = "failed"
                job.error_message = str(e)
                job.save()
            except Exception:
                pass
            app.logger.error(f"Error processing translation job {job_id}: {str(e)}")
