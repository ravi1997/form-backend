from typing import Any, Dict, List, Optional, Tuple, Set
from models.Form import Form, FormVersion, Section, Question
from utils.condition_evaluator import ConditionEvaluator
from logger.unified_logger import app_logger, error_logger
import re

class FormValidationService:
    @staticmethod
    def validate_submission(
        form_id: str, 
        payload: Dict[str, Any], 
        version_id: Optional[str] = None,
        organization_id: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
        """
        Canonical validation engine for form submissions.
        Returns: (is_valid, cleaned_data, errors, calculated_values)
        """
        app_logger.info(f"Validating submission for form {form_id}")
        
        # 1. Resolve Form and Version (Scoped by organization_id)
        # Use __raw__ or explicit filter if needed, but BaseDocument handles it if current_user is set.
        # Here we use explicit filter for background tasks safety.
        from models.Form import Form, FormVersion
        
        form = Form.objects(id=form_id, organization_id=organization_id, is_deleted=False).first()
        if not form:
            return False, {}, [{"error": "Form not found"}], {}
            
        if not version_id:
            version_id = form.active_version_id
            
        if not version_id:
            return False, {}, [{"error": "No active version for this form"}], {}
            
        version_doc = FormVersion.objects(id=version_id, form=form.id, organization_id=organization_id).first()
        if not version_doc:
            return False, {}, [{"error": "Form version not found"}], {}

        # 2. Get Snapshot or Reconstruct from Legacy Sections
        sections_data = version_doc.resolved_snapshot.get("sections", [])

        # 3. Initialize Evaluator
        evaluator = ConditionEvaluator(payload)
        
        cleaned_data = {}
        errors = []
        calculated_values = {}
        visible_fields = set()

        # 4. Resolve Calculation Order (Topological Sort)
        all_questions = []
        def flatten_questions(secs):
            for s in secs:
                all_questions.extend(s.get("questions", []))
                if s.get("sections"):
                    flatten_questions(s["sections"])
        flatten_questions(sections_data)
        
        try:
            calc_order = FormValidationService._get_evaluation_order(all_questions)
        except ValueError as e:
            return False, {}, [{"error": str(e)}], {}

        # 5. Process Sections Recursively (First Pass: Visibility and Clean Data)
        FormValidationService._process_sections(
            sections_data, 
            payload, 
            evaluator, 
            cleaned_data, 
            errors, 
            calculated_values,
            visible_fields,
            calc_order
        )

        # 6. Global Calculation Pass (Second Pass: Topological Order)
        # Evaluate all calculated fields that are visible and have expressions
        # This allows cross-section calculation dependencies
        visible_calc_fields = {q.get("variable_name"): q for q in all_questions if q.get("variable_name") in visible_fields and q.get("logic", {}).get("calculated_value")}
        
        for var_name in calc_order:
            if var_name in visible_calc_fields:
                q = visible_calc_fields[var_name]
                calc_expr = q.get("logic", {}).get("calculated_value")
                # Safe execution with error wrapping (Phase 6)
                calc_result = evaluator.safe_eval(calc_expr, wrap_errors=True)
                if isinstance(calc_result, tuple):
                    res, err = calc_result
                    if err:
                        errors.append({"field": var_name, "error": f"Calculation error: {err}"})
                        continue
                    calc_val = res
                else:
                    calc_val = calc_result

                if calc_val is not None:
                    calculated_values[var_name] = calc_val
                    # Update both payload (for evaluator) and cleaned_data (for output)
                    payload[var_name] = calc_val
                    cleaned_data[var_name] = calc_val

        is_valid = len(errors) == 0
        return is_valid, cleaned_data, errors, calculated_values

    @staticmethod
    def _get_evaluation_order(questions: List[Dict[str, Any]]) -> List[str]:
        """Performs topological sort on questions based on calculated_value dependencies."""
        graph = {}
        all_var_names = {q.get("variable_name") for q in questions if q.get("variable_name")}
        
        for q in questions:
            var_name = q.get("variable_name")
            if not var_name: continue
            
            logic = q.get("logic", {})
            calc_expr = logic.get("calculated_value")
            
            dependencies = []
            if calc_expr:
                deps = ConditionEvaluator.get_dependencies(calc_expr)
                # Filter to only include other fields in the form
                dependencies = [d for d in deps if d in all_var_names and d != var_name]
            
            graph[var_name] = dependencies

        # Topological Sort
        ordered = []
        visited = set()
        temp_stack = set()

        def visit(node):
            if node in temp_stack:
                raise ValueError(f"Circular calculated field dependency detected involving: {node}")
            if node not in visited:
                temp_stack.add(node)
                for dep in graph.get(node, []):
                    visit(dep)
                temp_stack.remove(node)
                visited.add(node)
                ordered.append(node)

        for node in graph:
            if node not in visited:
                visit(node)
        
        return ordered

    @staticmethod
    def _process_sections(
        sections: List[Dict[str, Any]], 
        payload: Dict[str, Any],
        evaluator: ConditionEvaluator,
        cleaned_data: Dict[str, Any],
        errors: List[Dict[str, Any]],
        calculated_values: Dict[str, Any],
        visible_fields: Set[str],
        calc_order: List[str],
        parent_path: str = ""
    ):
        for section in sections:
            # 1. Section Visibility Check
            logic = section.get("logic", {})
            visibility_cond = logic.get("visibility_condition")
            if visibility_cond and not evaluator.evaluate(visibility_cond):
                continue
                
            # 2. Handle Repeatable Sections
            if logic.get("is_repeatable"):
                sid = section.get("id") or str(section.get("_id"))
                var_name = section.get("variable_name") or sid # Repeatable sections should have variable names
                
                section_payload = payload.get(var_name, [])
                if not isinstance(section_payload, list):
                    errors.append({"field": var_name, "error": "Expected a list for repeatable section"})
                    continue
                
                # min/max check
                r_min = logic.get("repeat_min", 0)
                r_max = logic.get("repeat_max")
                if len(section_payload) < r_min:
                    errors.append({"field": var_name, "error": f"Minimum {r_min} entries required"})
                if r_max and len(section_payload) > r_max:
                    errors.append({"field": var_name, "error": f"Maximum {r_max} entries allowed"})

                cleaned_repeats = []
                for i, entry in enumerate(section_payload):
                    entry_cleaned = {}
                    # Create a sub-evaluator for this repeat entry context
                    # Current limitation: can't easily reference other repeat entries without global context
                    entry_evaluator = ConditionEvaluator(entry, context={"global": payload, "index": i})
                    
                    FormValidationService._process_section_content(
                        section, entry, entry_evaluator, entry_cleaned, errors, 
                        calculated_values, visible_fields, calc_order, 
                        parent_path=f"{var_name}[{i}]."
                    )
                    cleaned_repeats.append(entry_cleaned)
                
                cleaned_data[var_name] = cleaned_repeats
            else:
                # Normal Section
                FormValidationService._process_section_content(
                    section, payload, evaluator, cleaned_data, errors, 
                    calculated_values, visible_fields, calc_order,
                    parent_path=parent_path
                )

    @staticmethod
    def _process_section_content(
        section: Dict[str, Any],
        payload: Dict[str, Any],
        evaluator: ConditionEvaluator,
        cleaned_data: Dict[str, Any],
        errors: List[Dict[str, Any]],
        calculated_values: Dict[str, Any],
        visible_fields: Set[str],
        calc_order: List[str],
        parent_path: str = ""
    ):
        # Process Questions
        for question in section.get("questions", []):
            FormValidationService._process_question(
                question, payload, evaluator, cleaned_data, errors, 
                calculated_values, visible_fields, calc_order, parent_path
            )
        
        # Recurse sub-sections
        if section.get("sections"):
            FormValidationService._process_sections(
                section["sections"], payload, evaluator, cleaned_data, errors, 
                calculated_values, visible_fields, calc_order,
                parent_path=parent_path
            )

    @staticmethod
    def _process_question(
        question: Dict[str, Any],
        payload: Dict[str, Any],
        evaluator: ConditionEvaluator,
        cleaned_data: Dict[str, Any],
        errors: List[Dict[str, Any]],
        calculated_values: Dict[str, Any],
        visible_fields: Set[str],
        calc_order: List[str],
        parent_path: str = ""
    ):
        var_name = question.get("variable_name")
        if not var_name:
            return

        # 1. Question Visibility Check
        logic = question.get("logic", {})
        visibility_cond = logic.get("visibility_condition")
        is_visible = True
        if visibility_cond:
            is_visible = evaluator.evaluate(visibility_cond)
            
        if not is_visible:
            return
            
        visible_fields.add(var_name)
        val = payload.get(var_name)
        
        # (Calculation removed here, moved to global pass in validate_submission)

        # 3. Validation Rules
        v_rules = question.get("validation", {})
        
        # Required Check (including conditional required)
        is_required = v_rules.get("is_required", False)
        req_conds = v_rules.get("required_conditions", [])
        if not is_required and req_conds:
            op = v_rules.get("logical_operator", "AND")
            results = [evaluator.evaluate(c) for c in req_conds]
            is_required = all(results) if op == "AND" else any(results)

        full_field_path = f"{parent_path}{var_name}"

        if is_required and val in (None, "", [], {}):
            errors.append({"field": full_field_path, "error": v_rules.get("error_message") or "Field is required"})
            return

        if val in (None, "", [], {}):
            cleaned_data[var_name] = val
            return

        # 4. Type & Constraint Checks
        field_type = question.get("field_type")
        
        # String length
        if field_type in ("input", "textarea", "email"):
            if not isinstance(val, str):
                errors.append({"field": full_field_path, "error": "Invalid data type"})
            else:
                min_l = v_rules.get("min_length")
                max_l = v_rules.get("max_length")
                if min_l and len(val) < min_l:
                    errors.append({"field": full_field_path, "error": f"Minimum length is {min_l}"})
                if max_l and len(val) > max_l:
                    errors.append({"field": full_field_path, "error": f"Maximum length is {max_l}"})
                    
        # Numeric Range
        if field_type in ("number", "price", "age", "slider"):
            try:
                f_val = float(val)
                min_v = v_rules.get("min_value")
                max_v = v_rules.get("max_value")
                if min_v is not None and f_val < float(min_v):
                    errors.append({"field": full_field_path, "error": f"Minimum value is {min_v}"})
                if max_v is not None and f_val > float(max_v):
                    errors.append({"field": full_field_path, "error": f"Maximum value is {max_v}"})
            except (ValueError, TypeError):
                errors.append({"field": full_field_path, "error": "Invalid numeric value"})

        # Options validation (including cascading selects AND option-level visibility)
        options = question.get("options", [])
        if options and field_type in ("select", "radio", "dropdown", "multi_select", "checkboxes"):
            parent_var = logic.get("parent_variable_name")
            parent_val = payload.get(parent_var) if parent_var else None
            
            allowed_options = []
            for opt in options:
                # 1. Cascading check
                if opt.get("parent_option_value") and str(opt.get("parent_option_value")) != str(parent_val):
                    continue
                
                # 2. Option-level visibility check
                opt_vis_cond = opt.get("visibility_condition")
                if opt_vis_cond and not evaluator.evaluate(opt_vis_cond):
                    continue
                    
                allowed_options.append(opt)
            
            allowed_values = [str(opt.get("option_value")) for opt in allowed_options]
            
            if field_type in ("multi_select", "checkboxes"):
                if isinstance(val, list):
                    for v in val:
                        if str(v) not in allowed_values:
                            errors.append({"field": full_field_path, "error": f"Invalid option selected: {v}"})
            else:
                if str(val) not in allowed_values:
                    errors.append({"field": full_field_path, "error": "Invalid option selected or option is hidden by conditions"})

        cleaned_data[var_name] = val

    @staticmethod
    def _document_to_dict(doc):
        """Simple helper to convert mongoengine doc to dict including nested structures."""
        if hasattr(doc, "to_mongo"):
            return doc.to_mongo().to_dict()
        return doc
