from flask import Blueprint, render_template, request
from flasgger import swag_from
from routes.v1.form.helper import apply_translations
from models import Form
from mongoengine import DoesNotExist
from logger.unified_logger import app_logger, error_logger

view_bp = Blueprint("view_bp", __name__)


# -------------------- index --------------------
@view_bp.route("/", methods=["GET"])
@swag_from({
    "tags": [
        "View"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
def index():
    app_logger.info("View Index accessed")
    try:
        return render_template("login.html")
    except Exception as e:
        error_logger.error(f"Error rendering login template: {str(e)}")
        return "Login page not found", 404


@view_bp.route("/<form_id>", methods=["GET"])
@swag_from({
    "tags": [
        "View"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
def view_form(form_id):
    app_logger.info(f"Viewing form {form_id}")
    try:
        form = Form.objects.get(id=form_id)
        lang = request.args.get("lang")
        form_dict = form.to_mongo().to_dict()
        if "_id" in form_dict:
            form_dict["id"] = str(form_dict.pop("_id"))
        if lang:
            app_logger.info(f"Applying translations for language: {lang} on form {form_id}")
            form_dict = apply_translations(form_dict, lang)
        return render_template("view.html", form=form_dict)
    except DoesNotExist:
        app_logger.warning(f"Form view failed: ID {form_id} not found")
        return "Form not found", 404
    except Exception as e:
        error_logger.error(f"Error viewing form {form_id}: {str(e)}")
        return "Internal server error", 500

