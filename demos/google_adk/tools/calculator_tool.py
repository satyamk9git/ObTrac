"""
Calculator and unit converter tools for Google ADK agents.
"""

import ast
import math
import operator
from google.adk.tools import ToolContext
from obtrac_sdk import trace

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.USub: operator.neg,
    ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv,
}
_FUNCS = {
    "sqrt": math.sqrt, "abs": abs, "round": round,
    "log": math.log, "log2": math.log2, "log10": math.log10,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "ceil": math.ceil, "floor": math.floor,
}

def _safe_eval(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp):
        op = _OPS.get(type(node.op))
        if not op:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op(_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _OPS.get(type(node.op))
        if not op:
            raise ValueError(f"Unsupported unary op")
        return op(_safe_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn = _FUNCS.get(node.func.id)
        if fn:
            return fn(*[_safe_eval(a) for a in node.args])
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


@trace(name="calculator", span_type="tool_call")
def calculator(expression: str, tool_context: ToolContext) -> dict:
    """
    Evaluate a mathematical expression safely.

    Args:
        expression: Math expression e.g. "15% of 4500", "sqrt(144) + 2**8"
        tool_context: Injected by ADK — carries session info auto-detected by ObTrac.

    Returns:
        dict with 'result' and 'expression' keys.
    """
    try:
        expr = (expression
                .replace("^", "**")
                .replace("×", "*")
                .replace("÷", "/")
                .replace(",", ""))

        # Handle "X% of Y" shorthand
        if "% of" in expr.lower():
            parts = expr.lower().replace("% of", "*0.01*").split("*0.01*")
            if len(parts) == 2:
                expr = f"{parts[0].strip()} * 0.01 * {parts[1].strip()}"

        tree = ast.parse(expr, mode="eval")
        result = _safe_eval(tree.body)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return {"expression": expression, "result": result, "status": "success"}
    except Exception as e:
        return {"expression": expression, "error": str(e), "status": "error"}


_UNIT_CONVERSIONS = {
    ("km", "miles"): lambda x: round(x * 0.621371, 4),
    ("miles", "km"): lambda x: round(x * 1.60934, 4),
    ("kg", "lbs"): lambda x: round(x * 2.20462, 4),
    ("lbs", "kg"): lambda x: round(x / 2.20462, 4),
    ("celsius", "fahrenheit"): lambda x: round(x * 9/5 + 32, 2),
    ("fahrenheit", "celsius"): lambda x: round((x - 32) * 5/9, 2),
    ("usd", "inr"): lambda x: round(x * 83.5, 2),
    ("inr", "usd"): lambda x: round(x / 83.5, 4),
    ("meters", "feet"): lambda x: round(x * 3.28084, 4),
    ("feet", "meters"): lambda x: round(x / 3.28084, 4),
    ("gb", "mb"): lambda x: round(x * 1024, 2),
    ("mb", "gb"): lambda x: round(x / 1024, 6),
}


@trace(name="unit_converter", span_type="tool_call")
def unit_converter(value: float, from_unit: str, to_unit: str, tool_context: ToolContext) -> dict:
    """
    Convert between common units of measurement.

    Args:
        value: Numeric value to convert.
        from_unit: Source unit (km, miles, kg, lbs, celsius, fahrenheit, usd, inr, meters, feet).
        to_unit: Target unit.
        tool_context: Injected by ADK.

    Returns:
        dict with 'result', 'from', 'to' keys.
    """
    key = (from_unit.lower(), to_unit.lower())
    fn = _UNIT_CONVERSIONS.get(key)
    if not fn:
        available = [f"{f} → {t}" for f, t in _UNIT_CONVERSIONS]
        return {
            "status": "error",
            "error": f"No conversion for '{from_unit}' → '{to_unit}'",
            "available": available,
        }
    result = fn(value)
    return {
        "status": "success",
        "value": value,
        "from_unit": from_unit,
        "to_unit": to_unit,
        "result": result,
        "formatted": f"{value} {from_unit} = {result} {to_unit}",
    }
