from . import form_bp
from flasgger import swag_from
from datetime import datetime, timezone
from routes.v1.form.helper import get_current_user
from routes.v1.form import form_bp
from flask import current_app, request, jsonify
from flask_jwt_extended import jwt_required
from mongoengine import DoesNotExist
from models import Form, FormResponse
from utils.exceptions import NotFoundError, ValidationError, ForbiddenError, ServiceError
from utils.response_helper import success_response, error_response
import json


# -------------------- Public Anonymous Submission --------------------
@form_bp.route("/<form_id>/public-submit", methods=["POST"])
@swag_from({
    "tags": [
        "Form"
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
            "required": true
        }
    ]
})
def submit_public_response(form_id):
    data = request.get_json()
    try:
        form = Form.objects.get(id=form_id)

        # Check if form is published
        if form.status != "published":
            current_app.logger.warning(
                f"Attempted public submission to non-published form {form_id} (status: {form.status})"
            )
            raise ForbiddenError(f"Form is {form.status}, not accepting submissions")

        # Check if form has expired
        if form.expires_at and datetime.now(timezone.utc) > form.expires_at.replace(
            tzinfo=timezone.utc
        ):
            current_app.logger.warning(
                f"Attempted public submission to expired form {form_id} (expired at: {form.expires_at})"
            )
            raise ForbiddenError("Form has expired")

        # Check if form is scheduled for future
        now = datetime.now(timezone.utc)
        if form.publish_at and now < form.publish_at.replace(tzinfo=timezone.utc):
            current_app.logger.warning(
                f"Attempted public submission to future scheduled form {form_id} (publish at: {form.publish_at})"
            )
            raise ForbiddenError("Form is not yet available")

        if not form.is_public:
            raise ForbiddenError("Form is not public")

        from routes.v1.form.validation import validate_form_submission

        submitted_data = data.get("data", {})
        validation_errors, cleaned_data = validate_form_submission(
            form, submitted_data, current_app.logger
        )

        if validation_errors:
            current_app.logger.warning(f"Public validation failed: {validation_errors}")
            return error_response(message="Validation failed", details=validation_errors, status_code=422)

        response = FormResponse(
            form=form.id,
            submitted_by="anonymous",
            data=cleaned_data,
            submitted_at=datetime.now(timezone.utc),
        )
        response.save()

        # Fire notification triggers if available
        try:
            from services.notification_service import NotificationService

            triggers = getattr(form, "triggers", []) or []
            if triggers:
                NotificationService.execute_triggers(
                    [t.to_mongo().to_dict() for t in triggers],
                    {"form_id": str(form.id), "response_id": str(response.id)},
                )
        except Exception as notif_err:
            current_app.logger.warning(f"Notification trigger error: {notif_err}")

        return success_response(
            data={"response_id": str(response.id)},
            message="Response submitted anonymously",
            status_code=201
        )
    except DoesNotExist:
        raise NotFoundError("Form not found")
    except (ValidationError, ForbiddenError) as e:
        raise
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@form_bp.route("/<string:form_id>/history", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
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
            "required": true
        }
    ]
})
@jwt_required()
def form_submission_history(form_id):
    current_user = get_current_user()
    try:
        question_id = request.args.get("question_id")
        primary_value = request.args.get("primary_value")
        auth = request.headers.get("Authorization")
        if not auth:
            token = request.cookies.get("access_token_cookie")
            if token:
                auth = f"Bearer {token}"

        if not question_id or not primary_value:
            return (
                jsonify(
                    {"error": "Missing 'question_id' or 'primary_value' parameter"}
                ),
                400,
            )

        current_app.logger.info(
            f"User {current_user.username} is requesting submission history for form {form_id}, question {question_id} with value '{primary_value}'"
        )

        # Construct the search payload
        search_payload = {
            "data": {
                question_id: {"value": primary_value, "type": "string", "fuzzy": True}
            },
            "limit": 100,
            "sort_by": "submitted_at",
            "sort_order": "asc",
            "include": {"questions": [], "sections": []},
        }

        # Forward the JWT token
        headers = {
            "Authorization": auth,
        }

        url = f"/form/api/v1/form/{form_id}/responses/search"
        current_app.logger.debug(
            f"Internal search URL: {url}, Payload: {search_payload}, Headers: {headers}"
        )
        # Call the internal search route using requests
        response = current_app.test_client().post(
            url,
            data=json.dumps(search_payload),
            content_type="application/json",
            headers=headers,
        )

        if response.status_code == 200:
            full_data = response.get_json().get("responses", [])
            result = [
                {"_id": r["_id"], "submitted_at": r["submitted_at"]} for r in full_data
            ]
            return jsonify({"data": result}), 200
        else:
            current_app.logger.error(
                f"Search call failed for form {form_id}, question {question_id} with value '{primary_value}': {response.text}"
            )
            return (
                jsonify(
                    {"error": "Search call failed", "details": response.get_json()}
                ),
                response.status_code,
            )

    except Exception as e:
        current_app.logger.error(
            f"Error fetching form submission history: {str(e)}", exc_info=True
        )
        return jsonify({"error": "Internal server error"}), 500


# -------------------- Workflow Next Action Check --------------------
@form_bp.route("/<form_id>/next-action", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
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
            "required": true
        }
    ]
})
@jwt_required()
def check_next_action(form_id):
    """
    Check if any active workflows should be triggered for this form.
    This endpoint is used by the frontend to determine the next action after form submission.

    Query Parameters:
    - response_id (optional): Check workflows for a specific response

    Returns:
    - workflow_action object if a workflow is triggered
    - null if no workflow is triggered
    """
    current_app.logger.info(f"--- Check Next Action for form_id: {form_id} ---")
    try:
        from models.Workflow import FormWorkflow

        try:
            from utils.script_engine import execute_safe_script
        except ImportError:

            def execute_safe_script(script, input_data=None, additional_globals=None):
                ctx = dict(additional_globals or {})
                try:
                    exec(compile(script, "<string>", "exec"), ctx)
                except Exception:
                    pass
                return {"result": ctx.get("result", False)}

        # Verify form exists
        form = Form.objects(id=form_id).first()
        if not form:
            current_app.logger.warning(
                f"Check Next Action failed: Form {form_id} not found"
            )
            return jsonify({"error": "Form not found"}), 404

        # Get response_id from query params if provided
        response_id = request.args.get("response_id")

        if response_id:
            # Check workflows for a specific response
            response = FormResponse.objects(id=response_id, form=form.id).first()
            if not response:
                current_app.logger.warning(
                    f"Check Next Action failed: Response {response_id} not found"
                )
                return jsonify({"error": "Response not found"}), 404

            submitted_data = response.data
        else:
            # No specific response - return available workflows for this form
            workflows = FormWorkflow.objects(
                trigger_form_id=str(form.id), is_active=True
            )

            workflow_list = []
            for wf in workflows:
                workflow_list.append(
                    {
                        "id": str(wf.id),
                        "name": wf.name,
                        "description": wf.description,
                        "condition": wf.trigger_condition,
                    }
                )

            return (
                jsonify(
                    {
                        "form_id": str(form.id),
                        "workflows": workflow_list,
                        "count": len(workflow_list),
                    }
                ),
                200,
            )

        # Evaluate workflows for the specific response
        workflows = FormWorkflow.objects(trigger_form_id=str(form.id), is_active=True)

        # Flatten response data for easier access in condition evaluation
        flat_answers = {}
        for sid, s_val in submitted_data.items():
            if isinstance(s_val, dict):
                flat_answers.update(s_val)

        for wf in workflows:
            try:
                # Evaluate condition
                condition = wf.trigger_condition
                if not condition or condition.strip() == "":
                    condition = "True"

                if condition != "True":
                    # Wrap condition to result
                    script = f"result = {condition}"
                    context = {"answers": flat_answers, "data": flat_answers}

                    res = execute_safe_script(
                        script, input_data=flat_answers, additional_globals=context
                    )

                    if res.get("result"):
                        # Match found
                        actions_payload = []
                        for act in wf.actions:
                            action_data = {
                                "type": act.type,
                                "target_form_id": act.target_form_id,
                                "data_mapping": act.data_mapping,
                                "assign_to_user_field": act.assign_to_user_field,
                            }
                            actions_payload.append(action_data)

                        workflow_action = {
                            "workflow_id": str(wf.id),
                            "workflow_name": wf.name,
                            "actions": actions_payload,
                            "matched_condition": condition,
                        }

                        current_app.logger.info(
                            f"Workflow {wf.id} triggered for response {response_id}"
                        )
                        return (
                            jsonify(
                                {
                                    "form_id": str(form.id),
                                    "response_id": response_id,
                                    "workflow_action": workflow_action,
                                }
                            ),
                            200,
                        )
                else:
                    # Condition is True (always trigger)
                    actions_payload = []
                    for act in wf.actions:
                        action_data = {
                            "type": act.type,
                            "target_form_id": act.target_form_id,
                            "data_mapping": act.data_mapping,
                            "assign_to_user_field": act.assign_to_user_field,
                        }
                        actions_payload.append(action_data)

                    workflow_action = {
                        "workflow_id": str(wf.id),
                        "workflow_name": wf.name,
                        "actions": actions_payload,
                        "matched_condition": "True (always)",
                    }

                    current_app.logger.info(
                        f"Workflow {wf.id} triggered (always) for response {response_id}"
                    )
                    return (
                        jsonify(
                            {
                                "form_id": str(form.id),
                                "response_id": response_id,
                                "workflow_action": workflow_action,
                            }
                        ),
                        200,
                    )

            except Exception as e:
                current_app.logger.warning(f"Error evaluating workflow {wf.id}: {e}")
                continue

        # No workflow triggered
        current_app.logger.info(
            f"No workflows triggered for form {form_id}, response {response_id}"
        )
        return (
            jsonify(
                {
                    "form_id": str(form.id),
                    "response_id": response_id,
                    "workflow_action": None,
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Error checking next action: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 400
