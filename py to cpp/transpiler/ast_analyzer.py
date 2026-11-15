import ast
from typing import Any, Optional
from transpiler.errors import TranspilerError, get_source_line


# AST nodes explicitly rejected with helpful diagnostics
UNSUPPORTED_NODES: dict[type, tuple[str, str, str]] = {
    ast.AsyncFunctionDef: (
        "Async Function Definition",
        "Asynchronous coroutines (async def) have no direct 1:1 C++17 equivalent.",
        "Convert the function to a synchronous 'def' function.",
    ),
    ast.Await: (
        "Await Expression",
        "Asynchronous 'await' expressions are not supported.",
        "Use synchronous function calls instead.",
    ),
    ast.AsyncFor: (
        "Async For Loop",
        "Asynchronous 'async for' loops are not supported.",
        "Use a standard synchronous 'for' loop.",
    ),
    ast.AsyncWith: (
        "Async With Statement",
        "Asynchronous context managers ('async with') are not supported.",
        "Use synchronous resource handling.",
    ),
    ast.Yield: (
        "Generator Yield",
        "Python generator coroutines ('yield') require state-machine transformation.",
        "Build and return a list instead of yielding values.",
    ),
    ast.YieldFrom: (
        "Generator Yield From",
        "Python 'yield from' delegation is not supported.",
        "Iterate over the sub-iterable and append items to a list.",
    ),
}


class ASTAnalyzer(ast.NodeVisitor):
    def __init__(self, source_lines: Optional[list[str]] = None):
        self.source_lines = source_lines or []
        self.variables: set[str] = set()
        self.constants: list[Any] = []
        self.operators: set[str] = set()
        self.functions_called: set[str] = set()
        self.functions_defined: list[dict[str, Any]] = []
        self.classes_defined: list[dict[str, Any]] = []
        self.imports: list[str] = []
        self.data_structures: set[str] = set()
        self.statements: dict[str, int] = {}
        self.detected_features: set[str] = set()

    def _fail(self, node: ast.AST, feature: str, reason: str, suggestion: str) -> None:
        line = getattr(node, "lineno", None)
        try:
            expr = ast.unparse(node)
        except Exception:
            expr = type(node).__name__
        raise TranspilerError(
            feature=feature,
            reason=reason,
            suggestion=suggestion,
            line=line,
            expression=expr,
            source_line=get_source_line(self.source_lines, line),
        )

    def generic_visit(self, node: ast.AST) -> None:
        node_type = type(node)
        if node_type in UNSUPPORTED_NODES:
            feature, reason, suggestion = UNSUPPORTED_NODES[node_type]
            self._fail(node, feature, reason, suggestion)
        super().generic_visit(node)

    def count_statement(self, name: str) -> None:
        self.statements[name] = self.statements.get(name, 0) + 1

    # Identifiers & Constants
    def visit_Name(self, node: ast.Name) -> None:
        self.variables.add(node.id)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        self.constants.append(node.value)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        self.detected_features.add("F-Strings")
        self.generic_visit(node)

    # Operators
    def visit_BinOp(self, node: ast.BinOp) -> None:
        self.operators.add(type(node.op).__name__)
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        self.operators.add(type(node.op).__name__)
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.operators.add(type(node.op).__name__)
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        for operator in node.ops:
            self.operators.add(type(operator).__name__)
        if len(node.ops) > 1:
            self.detected_features.add("Chained Comparisons")
        self.generic_visit(node)

    # Assignments
    def visit_Assign(self, node: ast.Assign) -> None:
        self.count_statement("Assignment")
        if len(node.targets) > 1 or any(isinstance(t, (ast.Tuple, ast.List)) for t in node.targets):
            self.detected_features.add("Multiple / Unpacking Assignment")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.count_statement("Annotated Assignment")
        self.detected_features.add("Type Annotations")
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.count_statement("Augmented Assignment")
        self.operators.add(type(node.op).__name__)
        self.generic_visit(node)

    # Functions & Lambdas
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.count_statement("Function Definition")
        self.detected_features.add("Functions")
        self.functions_defined.append(
            {
                "name": node.name,
                "params": [arg.arg for arg in node.args.args],
                "has_vararg": node.args.vararg is not None,
                "has_kwarg": node.args.kwarg is not None,
                "line": node.lineno,
            }
        )
        # Visit defaults, decorators, and body without adding param names to global variables
        for default in node.args.defaults:
            self.visit(default)
        for stmt in node.body:
            self.visit(stmt)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.count_statement("Lambda Expression")
        self.detected_features.add("Lambda Functions")
        self.visit(node.body)

    def visit_Return(self, node: ast.Return) -> None:
        self.count_statement("Return")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            self.functions_called.add(node.func.id)
        else:
            self.functions_called.add(ast.unparse(node.func))
            if isinstance(node.func, ast.Attribute):
                self.visit(node.func.value)

        for argument in node.args:
            self.visit(argument)
        for keyword in node.keywords:
            self.visit(keyword.value)

    # Control Flow
    def visit_If(self, node: ast.If) -> None:
        self.count_statement("If / Elif")
        self.detected_features.add("Conditionals")
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.count_statement("For Loop")
        self.detected_features.add("For Loops")
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.count_statement("While Loop")
        self.detected_features.add("While Loops")
        self.generic_visit(node)

    def visit_Break(self, node: ast.Break) -> None:
        self.count_statement("Break")
        self.generic_visit(node)

    def visit_Continue(self, node: ast.Continue) -> None:
        self.count_statement("Continue")
        self.generic_visit(node)

    def visit_Pass(self, node: ast.Pass) -> None:
        self.count_statement("Pass")

    # Data Structures & Comprehensions
    def visit_List(self, node: ast.List) -> None:
        self.data_structures.add("List (std::vector)")
        self.generic_visit(node)

    def visit_Tuple(self, node: ast.Tuple) -> None:
        self.data_structures.add("Tuple (std::tuple)")
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        self.data_structures.add("Dict (std::unordered_map)")
        self.generic_visit(node)

    def visit_Set(self, node: ast.Set) -> None:
        self.data_structures.add("Set (std::unordered_set)")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self.detected_features.add("Indexing / Slicing")
        self.generic_visit(node)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self.count_statement("List Comprehension")
        self.detected_features.add("List Comprehensions")
        self.generic_visit(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self.count_statement("Dict Comprehension")
        self.detected_features.add("Dict Comprehensions")
        self.generic_visit(node)

    # Object-Oriented Programming
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.count_statement("Class Definition")
        self.detected_features.add("Object-Oriented Programming")
        bases = [ast.unparse(b) for b in node.bases]
        methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
        self.classes_defined.append(
            {
                "name": node.name,
                "bases": bases,
                "methods": methods,
                "line": node.lineno,
            }
        )
        for stmt in node.body:
            self.visit(stmt)

    # Exceptions
    def visit_Try(self, node: ast.Try) -> None:
        self.count_statement("Try / Except")
        self.detected_features.add("Exception Handling")
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        self.count_statement("Raise")
        self.detected_features.add("Exception Handling")
        self.generic_visit(node)

    # Scope & Imports
    def visit_Global(self, node: ast.Global) -> None:
        self.count_statement("Global Declaration")
        self.detected_features.add("Global Scope")

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.count_statement("Nonlocal Declaration")
        self.detected_features.add("Nonlocal Scope")

    def visit_Import(self, node: ast.Import) -> None:
        self.count_statement("Import")
        for alias in node.names:
            self.imports.append(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.count_statement("ImportFrom")
        mod = node.module or ""
        for alias in node.names:
            self.imports.append(f"{mod}.{alias.name}")

    def visit_Expr(self, node: ast.Expr) -> None:
        self.count_statement("Expression")
        self.generic_visit(node)


def analyze_ast(tree: ast.AST, source_lines: Optional[list[str]] = None) -> dict[str, Any]:
    analyzer = ASTAnalyzer(source_lines=source_lines)
    analyzer.visit(tree)

    return {
        "variables": sorted(analyzer.variables),
        "constants": analyzer.constants,
        "operators": sorted(analyzer.operators),
        "functions": sorted(analyzer.functions_called),
        "defined_functions": analyzer.functions_defined,
        "defined_classes": analyzer.classes_defined,
        "imports": analyzer.imports,
        "data_structures": sorted(analyzer.data_structures),
        "detected_features": sorted(analyzer.detected_features),
        "statements": analyzer.statements,
        "total_variables": len(analyzer.variables),
        "total_constants": len(analyzer.constants),
        "total_operators": len(analyzer.operators),
        "total_functions": len(analyzer.functions_called),
    }