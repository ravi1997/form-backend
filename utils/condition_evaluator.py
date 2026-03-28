"""
utils/condition_evaluator.py
A pure-Python engine for evaluating complex form logic conditions server-side.
Supports nested groups, type coercion, and multiple source/comparison types.
"""
import re
import logging
from typing import Any, Dict, List, Optional, Union, Set

logger = logging.getLogger(__name__)

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

class ConditionEvaluator:
    def __init__(self, data: Dict[str, Any], context: Optional[Dict[str, Any]] = None):
        """
        data: The submitted form payload (keys = variable_names, values = submitted values).
        context: Optional extra context with url_params, user_info dict.
        """
        self.data = data or {}
        self.context = context or {}

    def safe_eval(self, expr: str, wrap_errors: bool = False) -> Any:
        """
        Safely evaluate an expression string using the given context (data).
        Uses AST parsing to avoid security risks of eval().
        If wrap_errors is True, returns (result, error_msg) tuple.
        """
        if not expr:
            return (None, None) if wrap_errors else None
        try:
            tree = ast.parse(expr, mode="eval")
            result = self._eval_node(tree.body)
            return (result, None) if wrap_errors else result
        except Exception as e:
            msg = str(e)
            logger.debug(f"Safe eval failed for expression '{expr}': {msg}")
            if wrap_errors:
                return (None, msg)
            return None

    @staticmethod
    def get_dependencies(expr: str) -> Set[str]:
        """Parses an expression and returns a set of all variable dependencies."""
        if not expr:
            return set()
        try:
            tree = ast.parse(expr, mode="eval")
            deps = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    deps.add(node.id)
                elif isinstance(node, ast.Call):
                    # Exclude function names from dependencies
                    if isinstance(node.func, ast.Name):
                        # Optionally we could track function dependencies if they were dynamic
                        pass
            return deps
        except Exception:
            return set()

    def _eval_node(self, node: Any) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            # Resolve variable from data or context
            return self.data.get(node.id) or self.context.get(node.id)
        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            return SAFE_OPERATORS[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            return SAFE_OPERATORS[type(node.op)](operand)
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for value in node.values:
                    if not self._eval_node(value):
                        return False
                return True
            elif isinstance(node.op, ast.Or):
                for value in node.values:
                    if self._eval_node(value):
                        return True
                return False
        elif isinstance(node, ast.Compare):
            left = self._eval_node(node.left)
            for operation, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator)
                if not SAFE_OPERATORS[type(operation)](left, right):
                    return False
                left = right
            return True
        elif isinstance(node, ast.List):
            return [self._eval_node(elt) for elt in node.elts]
        elif isinstance(node, ast.Call):
            # Support basic functions like len(), sum(), max(), min()
            func_name = node.func.id if isinstance(node.func, ast.Name) else None
            if func_name == "len":
                arg = self._eval_node(node.args[0])
                return len(arg) if arg is not None else 0
            
            if func_name in ("repeat_sum", "sum"):
                arg = self._eval_node(node.args[0])
                if isinstance(arg, list):
                    # Handle both list of numbers and list of dicts
                    vals = [v for v in arg if isinstance(v, (int, float))]
                    if not vals and all(isinstance(v, dict) for v in arg):
                        # sum(members, 'age') ? or sum(members.age)
                        # If sum(members) where members is list of dicts, it won't work unless we have a field
                        pass
                    return sum(vals) if vals else 0
                return 0

            if func_name in ("repeat_max", "max"):
                arg = self._eval_node(node.args[0])
                if isinstance(arg, list):
                    vals = [v for v in arg if isinstance(v, (int, float))]
                    return max(vals) if vals else 0
                return 0

            if func_name in ("repeat_min", "min"):
                arg = self._eval_node(node.args[0])
                if isinstance(arg, list):
                    vals = [v for v in arg if isinstance(v, (int, float))]
                    return min(vals) if vals else 0
                return 0

            raise ValueError(f"Unsupported function call: {func_name}")

        elif isinstance(node, ast.Attribute):
            # Support members.age where members is a list of dicts
            value = self._eval_node(node.value)
            if isinstance(value, list):
                # Return a list of the attributes from each item
                return [i.get(node.attr) for i in value if isinstance(i, dict)]
            if isinstance(value, dict):
                return value.get(node.attr)
            return None

        elif isinstance(node, ast.Subscript):
            value = self._eval_node(node.value)
            index = self._eval_node(node.slice)
            try:
                return value[index]
            except (IndexError, KeyError, TypeError):
                return None

        raise ValueError(f"Unsupported expression node: {type(node)}")

    def _get_val(self, obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def evaluate(self, condition: Any) -> bool:
        """
        Evaluates a Condition embedded document against the data.
        Returns True if the condition is satisfied, False otherwise.
        """
        if not condition:
            return True
            
        try:
            cond_type = self._get_val(condition, "type", "simple")
            if cond_type == "group":
                return self._evaluate_group(condition)
            else:
                return self._evaluate_simple(condition)
        except Exception as e:
            logger.debug(f"Condition evaluation failed: {e}")
            return False

    def _evaluate_simple(self, condition: Any) -> bool:
        """Evaluates a single simple condition."""
        source_type = self._get_val(condition, "source_type", "field")
        source_id = self._get_val(condition, "source_id", None)
        operator = self._get_val(condition, "operator", "equals")
        
        if not source_id:
            return False
            
        source_val = self._get_source_value(source_type, source_id)
        comparison_val = self._get_comparison_value(condition)
        
        return self._apply_operator(source_val, operator, comparison_val)

    def _evaluate_group(self, condition: Any) -> bool:
        """Evaluates a group of conditions with logical operator."""
        logical_op = self._get_val(condition, "logical_operator", "AND")
        sub_conditions = self._get_val(condition, "conditions", [])
        
        if not sub_conditions:
            return True
            
        results = [self.evaluate(c) for c in sub_conditions]
        
        if logical_op == "AND":
            return all(results)
        elif logical_op == "OR":
            return any(results)
        elif logical_op == "NOT":
            # NOT expects exactly one condition, but we handle multiple as NOT AND
            return not all(results) if len(results) > 1 else not (results[0] if results else False)
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
        comp_type = self._get_val(condition, "comparison_type", "constant")
        comp_val_dict = self._get_val(condition, "comparison_value", {})
        
        if not isinstance(comp_val_dict, dict):
            return comp_val_dict

        operator = self._get_val(condition, "operator", "")
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
