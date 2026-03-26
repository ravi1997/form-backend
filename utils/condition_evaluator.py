"""
utils/condition_evaluator.py
A pure-Python engine for evaluating complex form logic conditions server-side.
Supports nested groups, type coercion, and multiple source/comparison types.
"""
import re
import logging
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

class ConditionEvaluator:
    def __init__(self, data: Dict[str, Any], context: Optional[Dict[str, Any]] = None):
        """
        data: The submitted form payload (keys = variable_names, values = submitted values).
        context: Optional extra context with url_params, user_info dict.
        """
        self.data = data or {}
        self.context = context or {}

    def evaluate(self, condition: Any) -> bool:
        """
        Evaluates a Condition embedded document against the data.
        Returns True if the condition is satisfied, False otherwise.
        """
        if not condition:
            return True
            
        try:
            cond_type = getattr(condition, "type", "simple")
            if cond_type == "group":
                return self._evaluate_group(condition)
            else:
                return self._evaluate_simple(condition)
        except Exception as e:
            logger.debug(f"Condition evaluation failed: {e}")
            return False

    def _evaluate_simple(self, condition: Any) -> bool:
        """Evaluates a single simple condition."""
        source_type = getattr(condition, "source_type", "field")
        source_id = getattr(condition, "source_id", None)
        operator = getattr(condition, "operator", "equals")
        
        if not source_id:
            return False
            
        source_val = self._get_source_value(source_type, source_id)
        comparison_val = self._get_comparison_value(condition)
        
        return self._apply_operator(source_val, operator, comparison_val)

    def _evaluate_group(self, condition: Any) -> bool:
        """Evaluates a group of conditions with logical operator."""
        logical_op = getattr(condition, "logical_operator", "AND")
        sub_conditions = getattr(condition, "conditions", [])
        
        if not sub_conditions:
            return True
            
        results = [self.evaluate(c) for c in sub_conditions]
        
        if logical_op == "AND":
            return all(results)
        elif logical_op == "OR":
            return any(results)
        elif logical_op == "NOT":
            # NOT expects exactly one condition, but we handle multiple as NOT AND
            return not all(results) if len(results) > 1 else not results[0]
        elif logical_op == "NOR":
            return not any(results)
        elif logical_op == "NAND":
            return not all(results)
            
        return False

    def _get_source_value(self, source_type: str, source_id: str) -> Any:
        """Resolves the left-hand side value from data or context."""
        if source_type in ("field", "hidden_field", "calculated_value"):
            return self.data.get(source_id)
        elif source_type == "url_param":
            return self.context.get("url_params", {}).get(source_id)
        elif source_type == "user_info":
            return self.context.get("user_info", {}).get(source_id)
        return None

    def _get_comparison_value(self, condition: Any) -> Any:
        """Resolves the right-hand side comparison value."""
        comp_type = getattr(condition, "comparison_type", "constant")
        comp_val_dict = getattr(condition, "comparison_value", {})
        
        if not isinstance(comp_val_dict, dict):
            return comp_val_dict

        operator = getattr(condition, "operator", "")
        if operator == "between":
            try:
                return {
                    "min": float(comp_val_dict.get("min", 0)),
                    "max": float(comp_val_dict.get("max", 0))
                }
            except (ValueError, TypeError):
                return {"min": 0, "max": 0}

        # Handle constant or field-based comparison
        val = comp_val_dict.get("value") if "value" in comp_val_dict else comp_val_dict
        
        if comp_type == "field":
            return self.data.get(str(val))
        elif comp_type == "url_param":
            return self.context.get("url_params", {}).get(str(val))
        elif comp_type == "user_info":
            return self.context.get("user_info", {}).get(str(val))
            
        return val

    def _apply_operator(self, source_val: Any, operator: str, comparison_val: Any) -> bool:
        """Applies the operator. Handles type coercion."""
        try:
            # 1. Handle Emptiness Operators
            if operator == "is_empty":
                return source_val in (None, "", [], {})
            if operator == "is_not_empty":
                return source_val not in (None, "", [], {})
            
            # 2. Handle Equality
            if operator == "equals":
                return str(source_val) == str(comparison_val)
            if operator == "not_equals":
                return str(source_val) != str(comparison_val)
                
            # 3. Handle Numeric Comparisons
            if operator in ("greater_than", "less_than", "greater_than_equals", "less_than_equals", "between"):
                s_float = float(source_val)
                if operator == "between":
                    return comparison_val["min"] <= s_float <= comparison_val["max"]
                
                c_float = float(comparison_val)
                if operator == "greater_than": return s_float > c_float
                if operator == "less_than": return s_float < c_float
                if operator == "greater_than_equals": return s_float >= c_float
                if operator == "less_than_equals": return s_float <= c_float

            # 4. Handle String Operators
            s_str = str(source_val).lower()
            c_str = str(comparison_val).lower()
            
            if operator == "contains": return c_str in s_str
            if operator == "not_contains": return c_str not in s_str
            if operator == "starts_with": return s_str.startswith(c_str)
            if operator == "ends_with": return s_str.endswith(c_str)
            
            # 5. Handle List Operators
            if operator == "in_list":
                if isinstance(comparison_val, list):
                    return source_val in comparison_val
                return str(source_val) in str(comparison_val).split(",")
            
            if operator == "not_in_list":
                if isinstance(comparison_val, list):
                    return source_val not in comparison_val
                return str(source_val) not in str(comparison_val).split(",")

            # 6. Handle Regex
            if operator == "matches_regex":
                return bool(re.search(str(comparison_val), str(source_val)))
                
            # 7. Handle Checked (Boolean)
            if operator == "is_checked":
                return bool(source_val) is True

        except (ValueError, TypeError, KeyError):
            return False
            
        return False
