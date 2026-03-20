from . import form_bp
from flasgger import swag_from
import json
import re


def sanitize_uuid_for_eval(uuid_str):
    """
    Replaces dashes in UUID with underscores and adds a prefix to make it a valid identifier.
    Example: 123-456 -> v_123_456
    """
    return f"v_{uuid_str.replace('-', '_')}"


def prepare_eval_context(entries):
    """
    Creates a context dictionary where keys are sanitized UUIDs.
    Also keeps original keys just in case (as strings).
    """
    context = {}
    if entries:
        for entry in entries:
            for k, v in entry.items():
                # Add sanitized version
                safe_key = sanitize_uuid_for_eval(str(k))
                context[safe_key] = v
                # Add original version (quoted for string comparison if needed, though less likely for variable lookup)
                context[str(k)] = v
    return context


import ast
import operator as op

# Safe operators for AST evaluation
SAFE_OPERATORS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.BitXor: op.xor,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
    ast.Not: op.not_,
    ast.Eq: op.eq,
    ast.NotEq: op.ne,
    ast.Lt: op.lt,
    ast.LtE: op.le,
    ast.Gt: op.gt,
    ast.GtE: op.ge,
    ast.In: lambda x, y: x in y,
    ast.NotIn: lambda x, y: x not in y,
    ast.Is: lambda x, y: x is y,
    ast.IsNot: lambda x, y: x is not y,
}


def safe_eval(expr, context):
    """
    Safely evaluate an expression string using the given context.
    Uses AST parsing to avoid security risks of eval().
    """
    try:
        # Parse the expression into an AST
        tree = ast.parse(expr, mode="eval")
        return _eval_node(tree.body, context)
    except Exception as e:
        # Log the error if needed, but return False/Error as per use case
        # For condition evaluation, if it fails, it's usually False
        raise ValueError(f"Safe eval failed: {e}")


def _eval_node(node, context):
    if isinstance(node, ast.Constant):  # Python 3.8+
        return node.value
    elif isinstance(node, ast.Name):
        # Resolve variable from context
        return context.get(node.id)
    elif isinstance(node, ast.BinOp):
        left = _eval_node(node.left, context)
        right = _eval_node(node.right, context)
        return SAFE_OPERATORS[type(node.op)](left, right)
    elif isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, context)
        return SAFE_OPERATORS[type(node.op)](operand)
    elif isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for value in node.values:
                if not _eval_node(value, context):
                    return False
            return True
        elif isinstance(node.op, ast.Or):
            for value in node.values:
                if _eval_node(value, context):
                    return True
            return False
    elif isinstance(node, ast.Compare):
        left = _eval_node(node.left, context)
        for operation, comparator in zip(node.ops, node.comparators):
            right = _eval_node(comparator, context)
            if not SAFE_OPERATORS[type(operation)](left, right):
                return False
            left = right
        return True
    elif isinstance(node, ast.List):
        return [_eval_node(elt, context) for elt in node.elts]

    raise ValueError(f"Unsupported expression node: {type(node)}")


def evaluate_condition(condition, context, logger=None):
    """
    Evaluates a condition string against the context using safe_eval.
    Sanitizes UUIDs in the condition string to match sanitized context keys.
    """
    if not condition:
        return False

    try:
        # Regex to find UUID patterns
        uuid_pattern = r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"

        def replace_uuid(match):
            return sanitize_uuid_for_eval(match.group(0))

        safe_condition = re.sub(uuid_pattern, replace_uuid, condition)

        if logger and safe_condition != condition:
            logger.debug(f"Sanitized condition: {condition} -> {safe_condition}")

        return safe_eval(safe_condition, context)
    except Exception as err:
        if logger:
            logger.warning(f"Eval failed: {condition}, error={err}")
        return False


def validate_form_submission(form, submitted_data, logger, is_draft=False):
    """
    Validates submitted data against form structure and rules.
    Returns (validation_errors, cleaned_data).
    cleaned_data contains only visible and valid fields.
    If is_draft=True, skips required checks and minimum limits.
    """
    validation_errors = []
    cleaned_data = {}

    # Get the latest version
    if not form.versions:
        return [{"error": "Form has no versions defined"}], {}

    active_v = getattr(form, "active_version_id", None)
    if active_v:
        latest_version = next(
            (v for v in form.versions if v.version == active_v), form.versions[-1]
        )
    else:
        latest_version = form.versions[-1]

    for section in latest_version.sections:
        sid = str(section.id)
        section_data = submitted_data.get(sid)

        logger.info(
            f"Processing section: {sid}, repeatable={section.is_repeatable_section}"
        )

        if section.is_repeatable_section:
            if section_data is None:
                if section.repeat_min and section.repeat_min > 0 and not is_draft:
                    msg = f"At least {section.repeat_min} entries required"
                    validation_errors.append({"section_id": sid, "error": msg})
                # If optional and missing, cleaned_data[sid] can be skipped or []
                continue

            if not isinstance(section_data, list):
                msg = "Expected a list of entries for repeatable section"
                validation_errors.append({"section_id": sid, "error": msg})
                logger.warning(f"{sid}: {msg}")
                continue

            if (
                section.repeat_min
                and len(section_data) < section.repeat_min
                and not is_draft
            ):
                msg = f"At least {section.repeat_min} entries required"
                validation_errors.append({"section_id": sid, "error": msg})
                logger.warning(f"{sid}: {msg}")

            if section.repeat_max and len(section_data) > section.repeat_max:
                msg = f"No more than {section.repeat_max} entries allowed"
                validation_errors.append({"section_id": sid, "error": msg})
                logger.warning(f"{sid}: {msg}")

            entries = section_data
            cleaned_section_entries = []
        else:
            if section_data is None:
                entries = [{}]
            elif not isinstance(section_data, dict):
                logger.warning(
                    f"{sid}: Non-dict data in non-repeatable section, skipping."
                )
                continue
            else:
                entries = [section_data]
            cleaned_section_entries = []  # Will hold 1 entry

        for entry in entries:
            # Context for visibility/required conditions
            # Use only current entry context as per original logic
            context = prepare_eval_context([entry])

            cleaned_entry = {}

            for question in section.questions:
                qid = str(question.id)
                val = entry.get(qid) if entry else None
                logger.debug(f"Checking question {qid}, label={question.label}")

                # 1. Evaluate visibility
                is_visible = True
                if question.visibility_condition:
                    is_visible = evaluate_condition(
                        question.visibility_condition, context, logger
                    )
                    logger.debug(f"Visibility of {qid}: {is_visible}")

                if not is_visible:
                    # Skip validation AND do not add to cleaned_entry
                    continue

                # 2. Evaluate Conditional Required
                is_required = question.is_required
                if (
                    not is_required
                    and hasattr(question, "required_condition")
                    and question.required_condition
                ):
                    is_required = evaluate_condition(
                        question.required_condition, context, logger
                    )
                    if is_required:
                        logger.debug(
                            f"Field {qid} is mandatory due to condition: {question.required_condition}"
                        )

                # Checkbox normalization
                if (
                    question.field_type == "checkbox"
                    and val is not None
                    and not isinstance(val, list)
                ):
                    val = [val] if val else []

                # Handle repeatable questions
                if question.is_repeatable_question:
                    if not isinstance(val, list) and val is not None:
                        msg = "Expected list of answers for repeatable question"
                        validation_errors.append({"id": qid, "error": msg})
                        logger.warning(f"{qid}: {msg}")
                        # Don't add to cleaned_entry if invalid structure
                        continue

                    if is_required and (val is None or len(val) == 0):
                        if not is_draft:
                            msg = "Required field missing"
                            validation_errors.append({"id": qid, "error": msg})
                            logger.warning(f"{qid}: {msg}")
                        continue

                    if val:
                        if (
                            question.repeat_min
                            and len(val) < question.repeat_min
                            and not is_draft
                        ):
                            msg = f"At least {question.repeat_min} entries required"
                            validation_errors.append({"id": qid, "error": msg})
                            logger.warning(f"{qid}: {msg}")
                        if question.repeat_max and len(val) > question.repeat_max:
                            msg = f"No more than {question.repeat_max} entries allowed"
                            validation_errors.append({"id": qid, "error": msg})
                            logger.warning(f"{qid}: {msg}")

                    answers_to_check = val if val else []
                    cleaned_entry[qid] = val  # Add raw value, or normalized?
                else:
                    answers_to_check = [val]
                    cleaned_entry[qid] = val

                for ans in answers_to_check:
                    if is_required and (ans is None or ans == ""):
                        if not is_draft:
                            msg = "Required field missing"
                            validation_errors.append({"id": qid, "error": msg})
                            logger.warning(f"{qid}: {msg}")
                        continue

                    if ans in (None, ""):
                        continue

                    # Type checks
                    if question.field_type == "checkbox" and not isinstance(ans, list):
                        msg = "Expected a list for checkbox"
                        validation_errors.append({"id": qid, "error": msg})
                        logger.warning(f"{qid}: {msg}")
                    elif question.field_type in ("text", "textarea") and not isinstance(
                        ans, str
                    ):
                        msg = "Expected a string for text/textarea"
                        validation_errors.append({"id": qid, "error": msg})
                        logger.warning(f"{qid}: {msg}")
                    elif question.field_type == "radio":
                        if not isinstance(ans, str):
                            msg = "Expected a string for radio"
                            validation_errors.append({"id": qid, "error": msg})
                            logger.warning(f"{qid}: {msg}")
                        elif val not in [opt.option_value for opt in question.options]:
                            msg = "Invalid option selected"
                            validation_errors.append({"id": qid, "error": msg})
                            logger.warning(f"{qid}: {msg}")
                    elif question.field_type == "file_upload":
                        if isinstance(ans, dict) and "filepath" in ans:
                            pass
                        elif isinstance(ans, list):
                            for file_info in ans:
                                if (
                                    not isinstance(file_info, dict)
                                    or "filepath" not in file_info
                                ):
                                    msg = "Invalid file upload"
                                    validation_errors.append({"id": qid, "error": msg})
                                    logger.warning(f"{qid}: {msg}")
                        else:
                            msg = "Expected file upload for file_upload field type"
                            validation_errors.append({"id": qid, "error": msg})
                            logger.warning(f"{qid}: {msg}")
                    elif question.field_type == "slider":
                        try:
                            val_num = float(ans)
                            meta = question.meta_data or {}
                            min_val = meta.get("min")
                            max_val = meta.get("max")
                            if min_val is not None and val_num < min_val:
                                validation_errors.append(
                                    {
                                        "id": qid,
                                        "error": f"Value must be at least {min_val}",
                                    }
                                )
                            if max_val is not None and val_num > max_val:
                                validation_errors.append(
                                    {
                                        "id": qid,
                                        "error": f"Value must be at most {max_val}",
                                    }
                                )
                        except (ValueError, TypeError):
                            validation_errors.append(
                                {"id": qid, "error": "Invalid numeric value for slider"}
                            )

                    # Custom validation rules
                    if question.validation_rules and not is_draft:
                        try:
                            rules = json.loads(question.validation_rules)
                            if isinstance(ans, str):
                                if (
                                    "min_length" in rules
                                    and len(ans) < rules["min_length"]
                                ):
                                    msg = f"Minimum length is {rules['min_length']}"
                                    validation_errors.append({"id": qid, "error": msg})
                                if (
                                    "max_length" in rules
                                    and len(ans) > rules["max_length"]
                                ):
                                    msg = f"Maximum length is {rules['max_length']}"
                                    validation_errors.append({"id": qid, "error": msg})
                                # Added Regex validation
                                if "regex" in rules:
                                    pattern = rules["regex"]
                                    if not re.fullmatch(pattern, ans):
                                        msg = rules.get(
                                            "regex_error_message",
                                            f"Does not match required pattern: {pattern}",
                                        )
                                        validation_errors.append(
                                            {"id": qid, "error": msg}
                                        )
                            # Added Number range validation
                            elif question.field_type in ("number", "slider"):
                                try:
                                    num_val = float(ans)
                                    if (
                                        "min_value" in rules
                                        and num_val < rules["min_value"]
                                    ):
                                        msg = f"Value must be at least {rules['min_value']}"
                                        validation_errors.append(
                                            {"id": qid, "error": msg}
                                        )
                                    if (
                                        "max_value" in rules
                                        and num_val > rules["max_value"]
                                    ):
                                        msg = f"Value must be at most {rules['max_value']}"
                                        validation_errors.append(
                                            {"id": qid, "error": msg}
                                        )
                                except (ValueError, TypeError):
                                    msg = "Invalid numeric value"
                                    validation_errors.append({"id": qid, "error": msg})
                            if question.field_type == "checkbox" and isinstance(
                                ans, list
                            ):
                                if (
                                    "min_selections" in rules
                                    and len(ans) < rules["min_selections"]
                                ):
                                    msg = f"Select at least {rules['min_selections']} options"
                                    validation_errors.append({"id": qid, "error": msg})
                                if (
                                    "max_selections" in rules
                                    and len(ans) > rules["max_selections"]
                                ):
                                    msg = f"Select no more than {rules['max_selections']} options"
                                    validation_errors.append({"id": qid, "error": msg})
                        except json.JSONDecodeError:  # More specific exception handling
                            msg = "Invalid JSON format for validation_rules"
                            validation_errors.append({"id": qid, "error": msg})
                            logger.error(f"{qid}: {msg}")
                        except re.error as re_err:  # Handle invalid regex patterns
                            msg = f"Invalid regex pattern: {re_err}"
                            validation_errors.append({"id": qid, "error": msg})
                            logger.error(f"{qid}: {msg}")
                        except Exception as ve:
                            msg = f"Error processing validation rules: {str(ve)}"
                            validation_errors.append({"id": qid, "error": msg})
                            logger.error(f"{qid}: {msg}")

            cleaned_section_entries.append(cleaned_entry)

        # Assign cleaned entries to section in cleaned_data
        if section.is_repeatable_section:
            if cleaned_section_entries:
                cleaned_data[sid] = cleaned_section_entries
        else:
            if cleaned_section_entries:
                cleaned_data[sid] = cleaned_section_entries[0]

    # --- Phase 7: Global Custom Validation ---
    if (
        hasattr(latest_version, "custom_validations")
        and latest_version.custom_validations
        and not is_draft
    ):
        # Build Global Context
        # Flatten all non-repeatable fields from cleaned_data
        global_context_entries = []
        for sid, s_data in cleaned_data.items():
            if isinstance(s_data, dict):
                global_context_entries.append(s_data)

        # We can pass multiple dictionaries to prepare_eval_context logic
        # but my function takes a list of entries and merges them.
        # Wait, prepare_eval_context merges keys from ALL entries in the list?
        # Let's check prepare_eval_context definition.
        # "creates a context... keys are sanitized UUIDs... for entry in entries.. for k,v in entry.items()... context[k]=v"
        # Yes, it overwrites if duplicates exist, but otherwise merges. This is what we want.

        global_context = prepare_eval_context(global_context_entries)

        for rule in latest_version.custom_validations:
            expr = rule.get("expression")
            err_msg = rule.get("error_message", "Validation failed")

            if expr:
                try:
                    is_valid = evaluate_condition(expr, global_context, logger)
                    # We assume expression MUST be True.
                    if not is_valid:
                        validation_errors.append({"global": True, "error": err_msg})
                        logger.warning(f"Global validation failed: {expr}")
                except Exception as e:
                    logger.error(f"Error evaluating global rule {expr}: {e}")
                    # Decide if error in rule should block submission? Yes.
                    validation_errors.append(
                        {"global": True, "error": f"Rule error: {err_msg}"}
                    )

    return validation_errors, cleaned_data


from routes.v1.form import form_bp
from flask import request, jsonify, current_app
from flask_jwt_extended import jwt_required


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
    try:
        data = request.get_json()
        form_id = data.get("form_id")
        conditions = data.get("conditions", [])  # List of condition strings or objects
        responses = data.get("responses", {})

        if not form_id:
            return jsonify({"error": "form_id is required"}), 400

        # Prepare context from responses
        # Assuming responses keys might need sanitization if they are UUIDs
        context = prepare_eval_context([responses])

        # Determine strictness?
        logger = current_app.logger

        # If the input provides specific conditions to test (e.g. "age > 18")
        # useful for testing logic
        results = {}
        for cond in conditions:
            # Check if cond is a dict (like {"field_id": "...", "condition": "..."}) or string
            if isinstance(cond, str):
                results[cond] = evaluate_condition(cond, context, logger)
            elif isinstance(cond, dict) and "condition" in cond:
                c_str = cond["condition"]
                res = evaluate_condition(c_str, context, logger)
                results[c_str] = res

        # Also, we might want to evaluate ALL form logic?
        # The frontend often sends the current responses and expects to know
        # which fields should be visible/required based on the Form definition.
        # But this endpoint payload "conditions": List suggests we just evaluate specific expressions.
        # Or does it mean "Evaluate field conditions"?
        # Let's support both or just return the results of the requested conditions.

        return (
            jsonify(
                {"results": results, "context_keys": list(context.keys())}
            ),  # Debug info
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Condition evaluation error: {str(e)}")
        return jsonify({"error": str(e)}), 400
