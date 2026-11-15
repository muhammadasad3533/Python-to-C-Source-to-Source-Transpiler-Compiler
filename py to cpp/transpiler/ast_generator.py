import ast
from typing import Any
from transpiler.errors import TranspilerError


def _ast_to_interactive_dict(node: ast.AST) -> dict[str, Any]:
    """Convert a Python AST node into a JSON-serializable tree for interactive UI rendering."""
    node_type = type(node).__name__
    label = node_type

    if isinstance(node, ast.FunctionDef):
        args = [a.arg for a in node.args.args]
        label = f"FunctionDef: {node.name}({', '.join(args)})"
    elif isinstance(node, ast.ClassDef):
        bases = [ast.unparse(b) for b in node.bases]
        base_str = f"({', '.join(bases)})" if bases else ""
        label = f"ClassDef: {node.name}{base_str}"
    elif isinstance(node, ast.Name):
        label = f"Name: {node.id} ({type(node.ctx).__name__})"
    elif isinstance(node, ast.Constant):
        label = f"Constant: {repr(node.value)} ({type(node.value).__name__})"
    elif isinstance(node, ast.Call):
        func_name = ast.unparse(node.func)
        label = f"Call: {func_name}()"
    elif isinstance(node, ast.BinOp):
        label = f"BinOp: {type(node.op).__name__}"
    elif isinstance(node, ast.UnaryOp):
        label = f"UnaryOp: {type(node.op).__name__}"
    elif isinstance(node, ast.BoolOp):
        label = f"BoolOp: {type(node.op).__name__}"
    elif isinstance(node, ast.Compare):
        ops = ", ".join(type(op).__name__ for op in node.ops)
        label = f"Compare: {ops}"
    elif isinstance(node, ast.AugAssign):
        label = f"AugAssign: {type(node.op).__name__}="
    elif isinstance(node, ast.Import):
        names = ", ".join(alias.name for alias in node.names)
        label = f"Import: {names}"
    elif isinstance(node, ast.ImportFrom):
        names = ", ".join(alias.name for alias in node.names)
        label = f"ImportFrom: {node.module} -> {names}"

    children = []
    for field_name, value in ast.iter_fields(node):
        if isinstance(value, ast.AST):
            child = _ast_to_interactive_dict(value)
            child["field"] = field_name
            children.append(child)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, ast.AST):
                    child = _ast_to_interactive_dict(item)
                    child["field"] = field_name
                    children.append(child)

    return {
        "type": node_type,
        "label": label,
        "line": getattr(node, "lineno", None),
        "col": getattr(node, "col_offset", None),
        "children": children,
    }


def generate_ast(source_code: str) -> dict[str, Any]:
    """Generate Abstract Syntax Tree from Python source code with rich diagnostics."""
    if not source_code or not source_code.strip():
        err = TranspilerError(
            category="Syntax Error",
            line=1,
            feature="Empty Input",
            expression="",
            reason="No Python source code was provided.",
            suggestion="Enter valid Python 3 statements or load an example program.",
        )
        return {
            "success": False,
            "error": err.diagnostic.format(),
            "diagnostic": err.diagnostic.to_dict(),
        }

    source_lines = source_code.splitlines()

    try:
        tree = ast.parse(source_code)
        ast_output = ast.dump(tree, indent=4, include_attributes=False)
        ast_tree = _ast_to_interactive_dict(tree)

        return {
            "success": True,
            "ast": ast_output,
            "ast_tree": ast_tree,
            "tree": tree,
            "source_lines": source_lines,
        }

    except SyntaxError as error:
        bad_line = ""
        if error.lineno and 1 <= error.lineno <= len(source_lines):
            bad_line = source_lines[error.lineno - 1]
            if error.offset and error.offset > 0:
                pointer = " " * (error.offset - 1) + "^"
                bad_line = f"{bad_line}\n        {pointer}"

        err = TranspilerError(
            category="Syntax Error",
            line=error.lineno,
            feature="Python Syntax",
            expression=error.text.strip() if error.text else "",
            reason=error.msg or "Invalid Python syntax.",
            suggestion="Check indentation, missing colons (:), or unmatched parentheses/brackets.",
            source_line=bad_line or None,
        )
        return {
            "success": False,
            "error": err.diagnostic.format(),
            "diagnostic": err.diagnostic.to_dict(),
        }