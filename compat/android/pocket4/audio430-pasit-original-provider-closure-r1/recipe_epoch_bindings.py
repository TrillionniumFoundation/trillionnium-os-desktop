"""Inspect literal ROOT-relative recipe/tool bindings before sealing a request.

This is the portable form of the production preparation check. It is a static
binding check; it does not execute, adopt or qualify any build or recovery job.
"""
import ast


def recipe_bindings(source, expected_recipe, expected_tools):
    if type(source) is not str or type(expected_recipe) is not str or type(expected_tools) is not str:
        raise TypeError("source and exact relative bindings must be strings")
    if not expected_recipe.startswith("recipe-") or "/" in expected_recipe:
        raise ValueError("one explicit recipe directory")
    if not expected_tools.startswith("tools/") or len(expected_tools.split("/")) != 2:
        raise ValueError("one explicit tools directory")
    if expected_tools.split("/")[1] in ("", ".", ".."):
        raise ValueError("tools directory cannot traverse")
    allowed = {expected_recipe, expected_tools, expected_tools + "/droidloom-update"}
    rows = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Div)
            and isinstance(node.left, ast.Name)
            and node.left.id == "ROOT"
            and isinstance(node.right, ast.Constant)
            and isinstance(node.right.value, str)
        ):
            path = node.right.value
            if path.startswith("recipe-") or path.startswith("tools/"):
                rows.append({"line": node.lineno, "path": path})
    if not rows:
        raise ValueError("normal/recovery recipe bindings must be explicit")
    return {"observed": rows, "invalid": [row for row in rows if row["path"] not in allowed]}


def require_recipe_bindings(source, expected_recipe, expected_tools):
    result = recipe_bindings(source, expected_recipe, expected_tools)
    if result["invalid"]:
        raise ValueError("stale normal/recovery recipe or tool binding")
    return result
