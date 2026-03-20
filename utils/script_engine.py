"""
utils/script_engine.py
Safe expression evaluator for lightweight workflow conditions.
"""

from __future__ import annotations

import ast
from typing import Any, Dict


_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Subscript,
    ast.Index,
    ast.Dict,
    ast.List,
    ast.Tuple,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
)


def _assert_safe_ast(node: ast.AST) -> None:
    for child in ast.walk(node):
        if not isinstance(child, _ALLOWED_NODES):
            raise ValueError(f"Unsupported expression node: {type(child).__name__}")


def execute_safe_script(
    script: str, input_data: Dict[str, Any] | None = None, additional_globals: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """
    Evaluates script payloads of the form `result = <expression>` safely.
    Returns {"result": <bool or value>} and never executes statements.
    """
    statement = (script or "").strip()
    if not statement:
        return {"result": False}

    prefix = "result ="
    if statement.startswith(prefix):
        expression = statement[len(prefix):].strip()
    else:
        expression = statement

    if not expression:
        return {"result": False}

    context = {}
    if input_data:
        context["input_data"] = input_data
    if additional_globals:
        context.update(additional_globals)

    try:
        parsed = ast.parse(expression, mode="eval")
        _assert_safe_ast(parsed)
        compiled = compile(parsed, "<safe_condition>", "eval")
        value = eval(compiled, {"__builtins__": {}}, context)
        return {"result": value}
    except Exception:
        return {"result": False}
