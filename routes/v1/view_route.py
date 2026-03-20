from flask import Blueprint, render_template, request
from flasgger import swag_from
from routes.v1.form.helper import apply_translations
from models import Form
from mongoengine import DoesNotExist
import logging

view_bp = Blueprint("view_bp", __name__)
logger = logging.getLogger(__name__)


# -------------------- index --------------------
@view_bp.route("/", methods=["GET"])
@swag_from({
    "tags": ["View"],
    "responses": {
        "200": {"description": "Success"}
    }
})
def index():
    logger.info("--- View Index branch started ---")
    try:
        return render_template("login.html")
    except Exception:
        logger.error("Login template not found")
        return "Login page not found", 404


@view_bp.route("/<form_id>", methods=["GET"])
@swag_from({
    "tags": ["View"],
    "responses": {
        "200": {"description": "Success"}
    }
})
def view_form(form_id):
    logger.info(f"--- View Form branch started for id: {form_id} ---")
    try:
        form = Form.objects.get(id=form_id)
        lang = request.args.get("lang")
        form_dict = form.to_mongo().to_dict()
        if "_id" in form_dict:
            form_dict["id"] = str(form_dict.pop("_id"))
        if lang:
            logger.info(f"Applying translations for language: {lang}")
            form_dict = apply_translations(form_dict, lang)
        return render_template("view.html", form=form_dict)
    except DoesNotExist:
        logger.warning(f"View Form failed: ID {form_id} not found")
        return "Form not found", 404
