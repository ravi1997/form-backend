from . import form_bp
from flasgger import swag_from
import json
import re
from logger.unified_logger import app_logger, error_logger, audit_logger
from flask import request, jsonify, current_app
from flask_jwt_extended import jwt_required
from services.form_validation_service import FormValidationService

def validate_form_submission(form, submitted_data, logger=None, is_draft=False, organization_id=None):
    """
    Validates submitted data against form structure and rules using the canonical service.
    Returns (validation_errors, cleaned_data).
    """
    is_valid, cleaned_data, errors, calculated_values = FormValidationService.validate_submission(
        form_id=str(form.id),
        payload=submitted_data,
        organization_id=organization_id or getattr(form, "organization_id", None)
    )
    
    # Map to the format expected by legacy route callers
    mapped_errors = []
    for err in errors:
        mapped_errors.append({
            "id": err.get("field"),
            "error": err.get("error")
        })
        
    return mapped_errors, cleaned_data


@form_bp.route("/conditions/evaluate", methods=["POST"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
@jwt_required()
def evaluate_conditions_endpoint():
    """
    Evaluate conditional logic for dynamic form behavior.
    """
    app_logger.info("Entering evaluate_conditions_endpoint")
    try:
        data = request.get_json()
        form_id = data.get("form_id")
        conditions = data.get("conditions", [])  # List of condition strings or objects
        responses = data.get("responses", {})

        if not form_id:
            return jsonify({"error": "form_id is required"}), 400

        from utils.condition_evaluator import ConditionEvaluator
        evaluator = ConditionEvaluator(responses)

        results = {}
        for cond in conditions:
            if isinstance(cond, str):
                # Evaluate as expression
                results[cond] = evaluator.safe_eval(cond)
            elif isinstance(cond, dict):
                # Evaluate as structured Condition
                results[json.dumps(cond)] = evaluator.evaluate(cond)

        app_logger.info(f"Exiting evaluate_conditions_endpoint: {len(results)} conditions evaluated")
        return success_response(data={"results": results})

    except Exception as e:
        error_logger.error(f"Condition evaluation error in endpoint: {str(e)}")
        return error_response(message=str(e), status_code=400)
