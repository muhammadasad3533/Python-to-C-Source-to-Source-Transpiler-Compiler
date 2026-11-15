import ast
from dataclasses import dataclass, field
from typing import Any, Optional
from transpiler.errors import TranspilerError, get_source_line
from transpiler.symbol_table import (
    BOOL_TYPE,
    DOUBLE_TYPE,
    INT_TYPE,
    STR_TYPE,
    UNKNOWN_TYPE,
    VOID_TYPE,
    CppType,
    Scope,
    SymbolTable,
    VariableSymbol,
)
from transpiler.type_inference import TypeInferenceEngine


# ============================================================
# Structured Typed IR Nodes
# ============================================================

@dataclass
class IRExpr:
    cpp_type: CppType = UNKNOWN_TYPE
    line: Optional[int] = None


@dataclass
class IRConst(IRExpr):
    value: Any = None


@dataclass
class IRVar(IRExpr):
    name: str = ""


@dataclass
class IRBinOp(IRExpr):
    op: str = ""
    left: IRExpr = field(default_factory=IRExpr)
    right: IRExpr = field(default_factory=IRExpr)


@dataclass
class IRUnaryOp(IRExpr):
    op: str = ""
    operand: IRExpr = field(default_factory=IRExpr)


@dataclass
class IRBoolOp(IRExpr):
    op: str = ""
    values: list[IRExpr] = field(default_factory=list)


@dataclass
class IRCompare(IRExpr):
    left: IRExpr = field(default_factory=IRExpr)
    ops: list[str] = field(default_factory=list)
    comparators: list[IRExpr] = field(default_factory=list)


@dataclass
class IRTernary(IRExpr):
    test: IRExpr = field(default_factory=IRExpr)
    body: IRExpr = field(default_factory=IRExpr)
    orelse: IRExpr = field(default_factory=IRExpr)


@dataclass
class IRCall(IRExpr):
    func_name: str = ""
    args: list[IRExpr] = field(default_factory=list)
    kwargs: dict[str, IRExpr] = field(default_factory=dict)


@dataclass
class IRMethodCall(IRExpr):
    obj: IRExpr = field(default_factory=IRExpr)
    method: str = ""
    args: list[IRExpr] = field(default_factory=list)


@dataclass
class IRAttribute(IRExpr):
    obj: IRExpr = field(default_factory=IRExpr)
    attr: str = ""


@dataclass
class IRIndex(IRExpr):
    obj: IRExpr = field(default_factory=IRExpr)
    index: IRExpr = field(default_factory=IRExpr)


@dataclass
class IRSlice(IRExpr):
    obj: IRExpr = field(default_factory=IRExpr)
    lower: Optional[IRExpr] = None
    upper: Optional[IRExpr] = None
    step: Optional[IRExpr] = None


@dataclass
class IRCollection(IRExpr):
    kind: str = "list"
    elements: list[IRExpr] = field(default_factory=list)


@dataclass
class IRDict(IRExpr):
    keys: list[IRExpr] = field(default_factory=list)
    values: list[IRExpr] = field(default_factory=list)


@dataclass
class IRFString(IRExpr):
    parts: list[IRExpr] = field(default_factory=list)


@dataclass
class IRLambda(IRExpr):
    params: list[tuple[str, CppType]] = field(default_factory=list)
    body: IRExpr = field(default_factory=IRExpr)


@dataclass
class IRListComp(IRExpr):
    elt: IRExpr = field(default_factory=IRExpr)
    target: str = ""
    target_type: CppType = INT_TYPE
    iter_expr: IRExpr = field(default_factory=IRExpr)
    ifs: list[IRExpr] = field(default_factory=list)


@dataclass
class IRDictComp(IRExpr):
    key: IRExpr = field(default_factory=IRExpr)
    value: IRExpr = field(default_factory=IRExpr)
    target: str = ""
    target_type: CppType = INT_TYPE
    iter_expr: IRExpr = field(default_factory=IRExpr)
    ifs: list[IRExpr] = field(default_factory=list)


# ============================================================
# IR Statements
# ============================================================

@dataclass
class IRStmt:
    line: Optional[int] = None


@dataclass
class IRAssign(IRStmt):
    target: Any = None
    value: IRExpr = field(default_factory=IRExpr)
    is_declaration: bool = False
    var_type: CppType = UNKNOWN_TYPE


@dataclass
class IRAugAssign(IRStmt):
    target: Any = None
    op: str = ""
    value: IRExpr = field(default_factory=IRExpr)


@dataclass
class IRExprStmt(IRStmt):
    expr: IRExpr = field(default_factory=IRExpr)


@dataclass
class IRPrint(IRStmt):
    args: list[IRExpr] = field(default_factory=list)
    sep: str = " "
    end: str = "\n"


@dataclass
class IRIf(IRStmt):
    test: IRExpr = field(default_factory=IRExpr)
    body: list[IRStmt] = field(default_factory=list)
    orelse: list[IRStmt] = field(default_factory=list)


@dataclass
class IRWhile(IRStmt):
    test: IRExpr = field(default_factory=IRExpr)
    body: list[IRStmt] = field(default_factory=list)


@dataclass
class IRForRange(IRStmt):
    var_name: str = ""
    start: IRExpr = field(default_factory=IRExpr)
    stop: IRExpr = field(default_factory=IRExpr)
    step: IRExpr = field(default_factory=IRExpr)
    declare_var: bool = True


@dataclass
class IRForRangeBlock(IRForRange):
    body: list[IRStmt] = field(default_factory=list)


@dataclass
class IRForEach(IRStmt):
    targets: list[str] = field(default_factory=list)
    target_type: CppType = UNKNOWN_TYPE
    iterable: IRExpr = field(default_factory=IRExpr)
    body: list[IRStmt] = field(default_factory=list)
    declare_var: bool = True


@dataclass
class IRReturn(IRStmt):
    value: Optional[IRExpr] = None


@dataclass
class IRBreak(IRStmt):
    pass


@dataclass
class IRContinue(IRStmt):
    pass


@dataclass
class IRPass(IRStmt):
    pass


@dataclass
class IRTryHandler:
    exc_type: Optional[str]
    var_name: Optional[str]
    body: list[IRStmt]


@dataclass
class IRTry(IRStmt):
    body: list[IRStmt] = field(default_factory=list)
    handlers: list[IRTryHandler] = field(default_factory=list)
    orelse: list[IRStmt] = field(default_factory=list)
    finalbody: list[IRStmt] = field(default_factory=list)


@dataclass
class IRRaise(IRStmt):
    exc_type: str = "RuntimeError"
    message: Optional[IRExpr] = None


@dataclass
class IRFunction(IRStmt):
    name: str = ""
    params: list[tuple[str, CppType, Optional[IRExpr]]] = field(default_factory=list)
    return_type: CppType = VOID_TYPE
    local_vars: list[tuple[str, CppType]] = field(default_factory=list)
    body: list[IRStmt] = field(default_factory=list)
    is_method: bool = False
    is_constructor: bool = False
    is_virtual: bool = False
    is_override: bool = False


@dataclass
class IRClass(IRStmt):
    name: str = ""
    bases: list[str] = field(default_factory=list)
    fields: list[tuple[str, CppType]] = field(default_factory=list)
    class_attrs: list[tuple[str, CppType, IRExpr]] = field(default_factory=list)
    methods: list[IRFunction] = field(default_factory=list)


@dataclass
class IRModule:
    classes: list[IRClass] = field(default_factory=list)
    functions: list[IRFunction] = field(default_factory=list)
    global_vars: list[tuple[str, CppType]] = field(default_factory=list)
    main_body: list[IRStmt] = field(default_factory=list)
    symtab: Optional[SymbolTable] = None


# ============================================================
# IR Optimizer (Constant Folding, Algebraic Simplification, DCE)
# ============================================================

class IROptimizer:
    def optimize(self, module: IRModule) -> IRModule:
        for cls in module.classes:
            for method in cls.methods:
                method.body = self._optimize_block(method.body)
        for fn in module.functions:
            fn.body = self._optimize_block(fn.body)
        module.main_body = self._optimize_block(module.main_body)
        return module

    def _optimize_block(self, stmts: list[IRStmt]) -> list[IRStmt]:
        optimized: list[IRStmt] = []
        for stmt in stmts:
            opt_stmt = self._optimize_stmt(stmt)
            if opt_stmt is None:
                continue
            if isinstance(opt_stmt, list):
                optimized.extend(opt_stmt)
            else:
                optimized.append(opt_stmt)
            if isinstance(opt_stmt, (IRReturn, IRBreak, IRContinue, IRRaise)):
                break
        return optimized

    def _optimize_stmt(self, stmt: IRStmt) -> Any:
        if isinstance(stmt, IRAssign):
            stmt.value = self._optimize_expr(stmt.value)
            return stmt
        if isinstance(stmt, IRAugAssign):
            stmt.value = self._optimize_expr(stmt.value)
            return stmt
        if isinstance(stmt, IRExprStmt):
            stmt.expr = self._optimize_expr(stmt.expr)
            return stmt
        if isinstance(stmt, IRPrint):
            stmt.args = [self._optimize_expr(a) for a in stmt.args]
            return stmt
        if isinstance(stmt, IRReturn):
            if stmt.value is not None:
                stmt.value = self._optimize_expr(stmt.value)
            return stmt
        if isinstance(stmt, IRIf):
            stmt.test = self._optimize_expr(stmt.test)
            stmt.body = self._optimize_block(stmt.body)
            stmt.orelse = self._optimize_block(stmt.orelse)
            if isinstance(stmt.test, IRConst) and isinstance(stmt.test.value, bool):
                return stmt.body if stmt.test.value else stmt.orelse
            return stmt
        if isinstance(stmt, IRWhile):
            stmt.test = self._optimize_expr(stmt.test)
            stmt.body = self._optimize_block(stmt.body)
            if isinstance(stmt.test, IRConst) and stmt.test.value is False:
                return None
            return stmt
        if isinstance(stmt, IRForRangeBlock):
            stmt.start = self._optimize_expr(stmt.start)
            stmt.stop = self._optimize_expr(stmt.stop)
            stmt.step = self._optimize_expr(stmt.step)
            stmt.body = self._optimize_block(stmt.body)
            return stmt
        if isinstance(stmt, IRForEach):
            stmt.iterable = self._optimize_expr(stmt.iterable)
            stmt.body = self._optimize_block(stmt.body)
            return stmt
        if isinstance(stmt, IRTry):
            stmt.body = self._optimize_block(stmt.body)
            for h in stmt.handlers:
                h.body = self._optimize_block(h.body)
            stmt.orelse = self._optimize_block(stmt.orelse)
            stmt.finalbody = self._optimize_block(stmt.finalbody)
            return stmt
        return stmt

    def _optimize_expr(self, expr: IRExpr) -> IRExpr:
        if isinstance(expr, IRUnaryOp):
            expr.operand = self._optimize_expr(expr.operand)
            if isinstance(expr.operand, IRConst):
                val = expr.operand.value
                if expr.op == "-" and isinstance(val, (int, float)) and not isinstance(val, bool):
                    return IRConst(cpp_type=expr.cpp_type, line=expr.line, value=-val)
                if expr.op == "+" and isinstance(val, (int, float)) and not isinstance(val, bool):
                    return IRConst(cpp_type=expr.cpp_type, line=expr.line, value=+val)
                if expr.op == "not" and isinstance(val, bool):
                    return IRConst(cpp_type=BOOL_TYPE, line=expr.line, value=not val)
            if expr.op == "not" and isinstance(expr.operand, IRUnaryOp) and expr.operand.op == "not":
                return expr.operand.operand
            return expr

        if isinstance(expr, IRBinOp):
            expr.left = self._optimize_expr(expr.left)
            expr.right = self._optimize_expr(expr.right)

            if isinstance(expr.left, IRConst) and isinstance(expr.right, IRConst):
                lv, rv = expr.left.value, expr.right.value
                if (
                    isinstance(lv, (int, float))
                    and isinstance(rv, (int, float))
                    and not isinstance(lv, bool)
                    and not isinstance(rv, bool)
                ):
                    try:
                        folded = None
                        if expr.op == "+":
                            folded = lv + rv
                        elif expr.op == "-":
                            folded = lv - rv
                        elif expr.op == "*":
                            folded = lv * rv
                        elif expr.op == "/" and rv != 0:
                            folded = lv / rv
                        elif expr.op == "//" and rv != 0:
                            folded = lv // rv
                        elif expr.op == "%" and rv != 0:
                            folded = lv % rv
                        elif expr.op == "**" and abs(rv) <= 32:
                            folded = lv ** rv
                        if folded is not None:
                            return IRConst(cpp_type=expr.cpp_type, line=expr.line, value=folded)
                    except Exception:
                        pass

            if isinstance(expr.right, IRConst) and isinstance(expr.right.value, (int, float)) and not isinstance(expr.right.value, bool):
                if expr.op in ("+", "-") and expr.right.value == 0:
                    return expr.left
                if expr.op == "*" and expr.right.value == 1:
                    return expr.left
                if expr.op == "*" and expr.right.value == 0 and expr.left.cpp_type == INT_TYPE:
                    return IRConst(cpp_type=INT_TYPE, line=expr.line, value=0)
                if expr.op == "**" and expr.right.value == 1:
                    return expr.left

            if isinstance(expr.left, IRConst) and isinstance(expr.left.value, (int, float)) and not isinstance(expr.left.value, bool):
                if expr.op == "+" and expr.left.value == 0:
                    return expr.right
                if expr.op == "*" and expr.left.value == 1:
                    return expr.right

            return expr

        if isinstance(expr, IRBoolOp):
            expr.values = [self._optimize_expr(v) for v in expr.values]
            return expr

        if isinstance(expr, IRCompare):
            expr.left = self._optimize_expr(expr.left)
            expr.comparators = [self._optimize_expr(c) for c in expr.comparators]
            return expr

        if isinstance(expr, IRCall):
            expr.args = [self._optimize_expr(a) for a in expr.args]
            return expr

        return expr


# ============================================================
# AST -> Typed IR Lowering
# ============================================================

class IRBuilder:
    def __init__(self, tree: ast.Module, source_lines: Optional[list[str]] = None):
        self.tree = tree
        self.source_lines = source_lines or []
        self.type_engine = TypeInferenceEngine(tree, source_lines=self.source_lines)
        self.symtab = self.type_engine.analyze()
        self.declared_in_scope: list[set[str]] = [set()]

    def _error(self, node: ast.AST, feature: str, reason: str, suggestion: str) -> None:
        line = getattr(node, "lineno", None)
        try:
            expr = ast.unparse(node)
        except Exception:
            expr = type(node).__name__
        raise TranspilerError(
            line=line,
            feature=feature,
            expression=expr,
            reason=reason,
            suggestion=suggestion,
            source_line=get_source_line(self.source_lines, line),
        )

    def _expr_type(self, node: ast.AST, scope: Scope) -> CppType:
        cached = self.type_engine.node_types.get(id(node))
        if cached and cached != UNKNOWN_TYPE:
            return cached
        return self.type_engine.infer_expr(node, scope)

    def build(self) -> IRModule:
        module = IRModule(symtab=self.symtab)
        global_scope = self.symtab.global_scope

        for vname, vsym in sorted(global_scope.variables.items()):
            module.global_vars.append((vname, vsym.cpp_type))
            self.declared_in_scope[0].add(vname)

        for stmt in self.tree.body:
            if isinstance(stmt, ast.ClassDef):
                module.classes.append(self._lower_class(stmt, global_scope))
            elif isinstance(stmt, ast.FunctionDef):
                module.functions.append(self._lower_function(stmt, global_scope))
            elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
                continue
            else:
                lowered = self._lower_stmt(stmt, global_scope)
                module.main_body.extend(lowered)

        return module

    def _lower_class(self, node: ast.ClassDef, global_scope: Scope) -> IRClass:
        cls_sym = global_scope.lookup_class(node.name)
        assert cls_sym is not None

        inherited_fields: set[str] = set()
        for base_name in cls_sym.bases:
            base_cls = global_scope.lookup_class(base_name)
            if base_cls:
                inherited_fields.update(base_cls.fields.keys())

        fields = [(fname, ftype) for fname, ftype in cls_sym.fields.items() if fname not in inherited_fields]
        class_attrs: list[tuple[str, CppType, IRExpr]] = []
        methods: list[IRFunction] = []

        for item in node.body:
            if isinstance(item, ast.Assign):
                for t in item.targets:
                    if isinstance(t, ast.Name) and t.id in cls_sym.class_attributes:
                        val_ir = self._lower_expr(item.value, global_scope)
                        class_attrs.append((t.id, cls_sym.class_attributes[t.id], val_ir))
            elif isinstance(item, ast.FunctionDef):
                fn_sym = cls_sym.methods[item.name]
                m_scope = self.symtab.function_scopes.get(f"{node.name}.{item.name}", global_scope)
                ir_fn = self._lower_function(item, m_scope, fn_sym=fn_sym, cls_sym=cls_sym)
                methods.append(ir_fn)

        return IRClass(
            line=node.lineno,
            name=node.name,
            bases=cls_sym.bases,
            fields=fields,
            class_attrs=class_attrs,
            methods=methods,
        )

    def _lower_function(
        self,
        node: ast.FunctionDef,
        parent_scope: Scope,
        fn_sym=None,
        cls_sym=None,
    ) -> IRFunction:
        if fn_sym is None:
            fn_sym = parent_scope.lookup_func(node.name)
        assert fn_sym is not None

        fn_scope = self.symtab.function_scopes.get(
            f"{cls_sym.name}.{node.name}" if cls_sym else node.name,
            parent_scope,
        )

        args = node.args.args
        defaults = node.args.defaults
        default_offset = len(args) - len(defaults)
        default_ir_map: dict[str, IRExpr] = {}
        for idx, arg in enumerate(args):
            if idx >= default_offset:
                default_ir_map[arg.arg] = self._lower_expr(defaults[idx - default_offset], parent_scope)

        params_with_defaults = [
            (pname, ptype, default_ir_map.get(pname))
            for pname, ptype in fn_sym.params
        ]

        param_names = {p[0] for p in fn_sym.params} | {"self"}
        local_vars: list[tuple[str, CppType]] = []
        scope_declared = set(param_names) | fn_scope.globals_declared

        for vname, vsym in sorted(fn_scope.variables.items()):
            if vname not in param_names and vname not in fn_scope.globals_declared:
                local_vars.append((vname, vsym.cpp_type))
                scope_declared.add(vname)

        self.declared_in_scope.append(scope_declared)
        body_stmts: list[IRStmt] = []
        for stmt in node.body:
            body_stmts.extend(self._lower_stmt(stmt, fn_scope))
        self.declared_in_scope.pop()

        is_override = False
        if cls_sym and cls_sym.bases and node.name != "__init__":
            for bname in cls_sym.bases:
                bcls = self.symtab.global_scope.lookup_class(bname)
                if bcls and node.name in bcls.methods:
                    is_override = True
                    break

        return IRFunction(
            line=node.lineno,
            name=node.name,
            params=params_with_defaults,
            return_type=fn_sym.return_type,
            local_vars=local_vars,
            body=body_stmts,
            is_method=cls_sym is not None,
            is_constructor=(cls_sym is not None and node.name == "__init__"),
            is_virtual=(cls_sym is not None and node.name != "__init__"),
            is_override=is_override,
        )

    def _lower_stmt(self, node: ast.AST, scope: Scope) -> list[IRStmt]:
        if isinstance(node, (ast.Global, ast.Nonlocal, ast.Import, ast.ImportFrom)):
            return []

        if isinstance(node, ast.Pass):
            return [IRPass(line=node.lineno)]

        if isinstance(node, ast.Break):
            return [IRBreak(line=node.lineno)]

        if isinstance(node, ast.Continue):
            return [IRContinue(line=node.lineno)]

        if isinstance(node, ast.Return):
            val = self._lower_expr(node.value, scope) if node.value is not None else None
            return [IRReturn(line=node.lineno, value=val)]

        if isinstance(node, ast.Assign):
            val_ir = self._lower_expr(node.value, scope)
            stmts: list[IRStmt] = []
            for target in node.targets:
                stmts.extend(self._lower_assignment_target(target, val_ir, node.lineno, scope))
            return stmts

        if isinstance(node, ast.AnnAssign):
            if node.value is None:
                return []
            val_ir = self._lower_expr(node.value, scope)
            return self._lower_assignment_target(node.target, val_ir, node.lineno, scope)

        if isinstance(node, ast.AugAssign):
            op_map = {
                ast.Add: "+",
                ast.Sub: "-",
                ast.Mult: "*",
                ast.Div: "/",
                ast.FloorDiv: "//",
                ast.Mod: "%",
                ast.Pow: "**",
                ast.BitAnd: "&",
                ast.BitOr: "|",
                ast.BitXor: "^",
                ast.LShift: "<<",
                ast.RShift: ">>",
            }
            op = op_map.get(type(node.op))
            if op is None:
                self._error(node, "Augmented Assignment", f"Unsupported operator {type(node.op).__name__}", "Use standard assignment.")
            val_ir = self._lower_expr(node.value, scope)
            if isinstance(node.target, ast.Name):
                return [IRAugAssign(line=node.lineno, target=node.target.id, op=op, value=val_ir)]
            if isinstance(node.target, ast.Attribute):
                attr_ir = IRAttribute(
                    cpp_type=self._expr_type(node.target, scope),
                    line=node.lineno,
                    obj=self._lower_expr(node.target.value, scope),
                    attr=node.target.attr,
                )
                return [IRAugAssign(line=node.lineno, target=attr_ir, op=op, value=val_ir)]
            if isinstance(node.target, ast.Subscript):
                idx_ir = self._lower_subscript(node.target, scope)
                return [IRAugAssign(line=node.lineno, target=idx_ir, op=op, value=val_ir)]

        if isinstance(node, ast.Expr):
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == "print":
                call = node.value
                args_ir = [self._lower_expr(a, scope) for a in call.args]
                sep = " "
                end = "\n"
                for kw in call.keywords:
                    if kw.arg == "sep" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        sep = kw.value.value
                    elif kw.arg == "end" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        end = kw.value.value
                return [IRPrint(line=node.lineno, args=args_ir, sep=sep, end=end)]
            return [IRExprStmt(line=node.lineno, expr=self._lower_expr(node.value, scope))]

        if isinstance(node, ast.If):
            test_ir = self._lower_expr(node.test, scope)
            body_ir: list[IRStmt] = []
            for s in node.body:
                body_ir.extend(self._lower_stmt(s, scope))
            else_ir: list[IRStmt] = []
            for s in node.orelse:
                else_ir.extend(self._lower_stmt(s, scope))
            return [IRIf(line=node.lineno, test=test_ir, body=body_ir, orelse=else_ir)]

        if isinstance(node, ast.While):
            test_ir = self._lower_expr(node.test, scope)
            body_ir = []
            for s in node.body:
                body_ir.extend(self._lower_stmt(s, scope))
            return [IRWhile(line=node.lineno, test=test_ir, body=body_ir)]

        if isinstance(node, ast.For):
            body_ir = []
            for s in node.body:
                body_ir.extend(self._lower_stmt(s, scope))

            if (
                isinstance(node.target, ast.Name)
                and isinstance(node.iter, ast.Call)
                and isinstance(node.iter.func, ast.Name)
                and node.iter.func.id == "range"
                and not node.iter.keywords
            ):
                r_args = node.iter.args
                if len(r_args) == 1:
                    start = IRConst(cpp_type=INT_TYPE, line=node.lineno, value=0)
                    stop = self._lower_expr(r_args[0], scope)
                    step = IRConst(cpp_type=INT_TYPE, line=node.lineno, value=1)
                elif len(r_args) == 2:
                    start = self._lower_expr(r_args[0], scope)
                    stop = self._lower_expr(r_args[1], scope)
                    step = IRConst(cpp_type=INT_TYPE, line=node.lineno, value=1)
                elif len(r_args) == 3:
                    start = self._lower_expr(r_args[0], scope)
                    stop = self._lower_expr(r_args[1], scope)
                    step = self._lower_expr(r_args[2], scope)
                else:
                    self._error(node, "range() Call", "range() expects 1 to 3 arguments.", "Pass range(stop), range(start, stop), or range(start, stop, step).")

                return [
                    IRForRangeBlock(
                        line=node.lineno,
                        var_name=node.target.id,
                        start=start,
                        stop=stop,
                        step=step,
                        body=body_ir,
                    )
                ]

            iter_ir = self._lower_expr(node.iter, scope)
            if isinstance(node.target, ast.Name):
                targets = [node.target.id]
            elif isinstance(node.target, (ast.Tuple, ast.List)) and all(isinstance(e, ast.Name) for e in node.target.elts):
                targets = [e.id for e in node.target.elts]  # type: ignore
            else:
                self._error(node, "For Loop Target", "Unsupported loop target pattern.", "Use a simple variable or tuple of variable names.")

            return [
                IRForEach(
                    line=node.lineno,
                    targets=targets,
                    iterable=iter_ir,
                    body=body_ir,
                )
            ]

        if isinstance(node, ast.Try):
            try_body = []
            for s in node.body:
                try_body.extend(self._lower_stmt(s, scope))
            handlers: list[IRTryHandler] = []
            for h in node.handlers:
                exc_name = ast.unparse(h.type) if h.type is not None else "Exception"
                h_body = []
                for s in h.body:
                    h_body.extend(self._lower_stmt(s, scope))
                handlers.append(IRTryHandler(exc_type=exc_name, var_name=h.name, body=h_body))
            else_body = []
            for s in node.orelse:
                else_body.extend(self._lower_stmt(s, scope))
            final_body = []
            for s in node.finalbody:
                final_body.extend(self._lower_stmt(s, scope))
            return [
                IRTry(
                    line=node.lineno,
                    body=try_body,
                    handlers=handlers,
                    orelse=else_body,
                    finalbody=final_body,
                )
            ]

        if isinstance(node, ast.Raise):
            if node.exc is None:
                return [IRRaise(line=node.lineno, exc_type="RuntimeError", message=None)]
            if isinstance(node.exc, ast.Call) and isinstance(node.exc.func, ast.Name):
                msg_ir = self._lower_expr(node.exc.args[0], scope) if node.exc.args else None
                return [IRRaise(line=node.lineno, exc_type=node.exc.func.id, message=msg_ir)]
            if isinstance(node.exc, ast.Name):
                return [IRRaise(line=node.lineno, exc_type=node.exc.id, message=None)]
            self._error(node, "Raise Statement", "Unsupported exception expression in raise.", "Use 'raise ValueError(\"message\")' or 'raise RuntimeError(\"message\")'.")

        self._error(
            node,
            f"Statement ({type(node).__name__})",
            f"Statement type '{type(node).__name__}' is not supported yet.",
            "Rewrite using supported control flow, functions, classes, or assignments.",
        )
        return []

    def _lower_assignment_target(self, target: ast.AST, val_ir: IRExpr, line: int, scope: Scope) -> list[IRStmt]:
        if isinstance(target, ast.Name):
            sym = scope.lookup_var(target.id)
            vtype = sym.cpp_type if sym else val_ir.cpp_type
            return [IRAssign(line=line, target=target.id, value=val_ir, var_type=vtype)]

        if isinstance(target, ast.Attribute):
            attr_ir = IRAttribute(
                cpp_type=self._expr_type(target, scope),
                line=line,
                obj=self._lower_expr(target.value, scope),
                attr=target.attr,
            )
            return [IRAssign(line=line, target=attr_ir, value=val_ir)]

        if isinstance(target, ast.Subscript):
            sub_ir = self._lower_subscript(target, scope)
            return [IRAssign(line=line, target=sub_ir, value=val_ir)]

        if isinstance(target, (ast.Tuple, ast.List)):
            if all(isinstance(elt, ast.Name) for elt in target.elts):
                names = [elt.id for elt in target.elts]  # type: ignore
                return [IRAssign(line=line, target=names, value=val_ir)]

        self._error(target, "Assignment Target", "Complex destructuring target is not supported.", "Assign to simple variables, attributes, indexed elements, or flat tuples.")
        return []

    def _lower_subscript(self, node: ast.Subscript, scope: Scope) -> IRExpr:
        obj_ir = self._lower_expr(node.value, scope)
        res_type = self._expr_type(node, scope)
        if isinstance(node.slice, ast.Slice):
            lower = self._lower_expr(node.slice.lower, scope) if node.slice.lower else None
            upper = self._lower_expr(node.slice.upper, scope) if node.slice.upper else None
            step = self._lower_expr(node.slice.step, scope) if node.slice.step else None
            return IRSlice(cpp_type=res_type, line=node.lineno, obj=obj_ir, lower=lower, upper=upper, step=step)
        idx_ir = self._lower_expr(node.slice, scope)
        return IRIndex(cpp_type=res_type, line=node.lineno, obj=obj_ir, index=idx_ir)

    def _lower_expr(self, node: ast.AST, scope: Scope) -> IRExpr:
        res_type = self._expr_type(node, scope)
        line = getattr(node, "lineno", None)

        if isinstance(node, ast.Constant):
            return IRConst(cpp_type=res_type, line=line, value=node.value)

        if isinstance(node, ast.Name):
            sym = scope.lookup_var(node.id)
            if (
                sym is None
                and scope.lookup_class(node.id) is None
                and scope.lookup_func(node.id) is None
                and node.id not in self.symtab.imported_modules
                and node.id not in self.symtab.imported_symbols
            ):
                self._error(
                    node,
                    "Variable Reference",
                    f"Variable '{node.id}' is referenced before assignment in scope '{scope.name}'.",
                    f"Define '{node.id}' before using it, or pass it as a function parameter.",
                )
            return IRVar(cpp_type=res_type, line=line, name=node.id)

        if isinstance(node, ast.JoinedStr):
            parts: list[IRExpr] = []
            for v in node.values:
                if isinstance(v, ast.Constant):
                    parts.append(IRConst(cpp_type=STR_TYPE, line=line, value=str(v.value)))
                elif isinstance(v, ast.FormattedValue):
                    parts.append(self._lower_expr(v.value, scope))
            return IRFString(cpp_type=STR_TYPE, line=line, parts=parts)

        if isinstance(node, ast.BinOp):
            op_map = {
                ast.Add: "+",
                ast.Sub: "-",
                ast.Mult: "*",
                ast.Div: "/",
                ast.FloorDiv: "//",
                ast.Mod: "%",
                ast.Pow: "**",
                ast.BitAnd: "&",
                ast.BitOr: "|",
                ast.BitXor: "^",
                ast.LShift: "<<",
                ast.RShift: ">>",
            }
            op = op_map.get(type(node.op))
            if op is None:
                self._error(node, "Binary Operator", f"Operator '{type(node.op).__name__}' is not supported.", "Use standard arithmetic or bitwise operators.")
            return IRBinOp(
                cpp_type=res_type,
                line=line,
                op=op,
                left=self._lower_expr(node.left, scope),
                right=self._lower_expr(node.right, scope),
            )

        if isinstance(node, ast.UnaryOp):
            op_map = {
                ast.USub: "-",
                ast.UAdd: "+",
                ast.Not: "not",
                ast.Invert: "~",
            }
            op = op_map.get(type(node.op))
            if op is None:
                self._error(node, "Unary Operator", f"Unary operator '{type(node.op).__name__}' is not supported.", "Use '-', '+', 'not', or '~'.")
            return IRUnaryOp(
                cpp_type=res_type,
                line=line,
                op=op,
                operand=self._lower_expr(node.operand, scope),
            )

        if isinstance(node, ast.BoolOp):
            op = "and" if isinstance(node.op, ast.And) else "or"
            return IRBoolOp(
                cpp_type=BOOL_TYPE,
                line=line,
                op=op,
                values=[self._lower_expr(v, scope) for v in node.values],
            )

        if isinstance(node, ast.Compare):
            op_map = {
                ast.Eq: "==",
                ast.NotEq: "!=",
                ast.Lt: "<",
                ast.LtE: "<=",
                ast.Gt: ">",
                ast.GtE: ">=",
                ast.In: "in",
                ast.NotIn: "not in",
                ast.Is: "is",
                ast.IsNot: "is not",
            }
            ops: list[str] = []
            for op_node in node.ops:
                op_str = op_map.get(type(op_node))
                if op_str is None:
                    self._error(node, "Comparison Operator", f"Unsupported comparison '{type(op_node).__name__}'.", "Use ==, !=, <, <=, >, >=, in, not in, is, or is not.")
                ops.append(op_str)
            return IRCompare(
                cpp_type=BOOL_TYPE,
                line=line,
                left=self._lower_expr(node.left, scope),
                ops=ops,
                comparators=[self._lower_expr(c, scope) for c in node.comparators],
            )

        if isinstance(node, ast.IfExp):
            return IRTernary(
                cpp_type=res_type,
                line=line,
                test=self._lower_expr(node.test, scope),
                body=self._lower_expr(node.body, scope),
                orelse=self._lower_expr(node.orelse, scope),
            )

        if isinstance(node, ast.List):
            return IRCollection(
                cpp_type=res_type,
                line=line,
                kind="list",
                elements=[self._lower_expr(e, scope) for e in node.elts],
            )

        if isinstance(node, ast.Tuple):
            return IRCollection(
                cpp_type=res_type,
                line=line,
                kind="tuple",
                elements=[self._lower_expr(e, scope) for e in node.elts],
            )

        if isinstance(node, ast.Set):
            return IRCollection(
                cpp_type=res_type,
                line=line,
                kind="set",
                elements=[self._lower_expr(e, scope) for e in node.elts],
            )

        if isinstance(node, ast.Dict):
            keys = [self._lower_expr(k, scope) for k in node.keys if k is not None]
            vals = [self._lower_expr(v, scope) for v in node.values]
            return IRDict(cpp_type=res_type, line=line, keys=keys, values=vals)

        if isinstance(node, ast.Subscript):
            return self._lower_subscript(node, scope)

        if isinstance(node, ast.Attribute):
            return IRAttribute(
                cpp_type=res_type,
                line=line,
                obj=self._lower_expr(node.value, scope),
                attr=node.attr,
            )

        if isinstance(node, ast.Lambda):
            params = [(arg.arg, INT_TYPE) for arg in node.args.args]
            lam_scope = Scope("lambda", "function", parent=scope)
            for pname, ptype in params:
                lam_scope.define_var(VariableSymbol(pname, ptype, line, is_param=True))
            body_ir = self._lower_expr(node.body, lam_scope)
            return IRLambda(cpp_type=res_type, line=line, params=params, body=body_ir)

        if isinstance(node, ast.ListComp):
            if len(node.generators) != 1 or not isinstance(node.generators[0].target, ast.Name):
                self._error(node, "List Comprehension", "Only single-generator list comprehensions with a simple target variable are supported.", "Rewrite nested comprehensions as explicit 'for' loops.")
            gen = node.generators[0]
            comp_scope = Scope("listcomp", "block", parent=scope)
            iter_ir = self._lower_expr(gen.iter, scope)
            t_type = res_type.params[0] if res_type.params else INT_TYPE
            comp_scope.define_var(VariableSymbol(gen.target.id, t_type, line))  # type: ignore
            elt_ir = self._lower_expr(node.elt, comp_scope)
            ifs_ir = [self._lower_expr(cond, comp_scope) for cond in gen.ifs]
            return IRListComp(
                cpp_type=res_type,
                line=line,
                elt=elt_ir,
                target=gen.target.id,  # type: ignore
                target_type=t_type,
                iter_expr=iter_ir,
                ifs=ifs_ir,
            )

        if isinstance(node, ast.DictComp):
            if len(node.generators) != 1 or not isinstance(node.generators[0].target, ast.Name):
                self._error(node, "Dict Comprehension", "Only single-generator dict comprehensions with a simple target variable are supported.", "Rewrite nested comprehensions as explicit 'for' loops.")
            gen = node.generators[0]
            comp_scope = Scope("dictcomp", "block", parent=scope)
            iter_ir = self._lower_expr(gen.iter, scope)
            comp_scope.define_var(VariableSymbol(gen.target.id, INT_TYPE, line))  # type: ignore
            key_ir = self._lower_expr(node.key, comp_scope)
            val_ir = self._lower_expr(node.value, comp_scope)
            ifs_ir = [self._lower_expr(cond, comp_scope) for cond in gen.ifs]
            return IRDictComp(
                cpp_type=res_type,
                line=line,
                key=key_ir,
                value=val_ir,
                target=gen.target.id,  # type: ignore
                target_type=INT_TYPE,
                iter_expr=iter_ir,
                ifs=ifs_ir,
            )

        if isinstance(node, ast.Call):
            args_ir = [self._lower_expr(a, scope) for a in node.args]
            kwargs_ir = {kw.arg: self._lower_expr(kw.value, scope) for kw in node.keywords if kw.arg}

            if isinstance(node.func, ast.Name):
                fname = node.func.id
                fn_sym = scope.lookup_func(fname)
                if fn_sym and kwargs_ir:
                    ordered_args = list(args_ir)
                    for idx in range(len(ordered_args), len(fn_sym.params)):
                        pname, _ = fn_sym.params[idx]
                        if pname in kwargs_ir:
                            ordered_args.append(kwargs_ir[pname])
                    args_ir = ordered_args
                    kwargs_ir = {}

                return IRCall(
                    cpp_type=res_type,
                    line=line,
                    func_name=fname,
                    args=args_ir,
                    kwargs=kwargs_ir,
                )

            if isinstance(node.func, ast.Attribute):
                obj_ir = self._lower_expr(node.func.value, scope)
                return IRMethodCall(
                    cpp_type=res_type,
                    line=line,
                    obj=obj_ir,
                    method=node.func.attr,
                    args=args_ir,
                )

            self._error(node, "Function Call", "Indirect dynamic callable expressions are not supported.", "Call functions or methods directly by name.")

        self._error(
            node,
            f"Expression ({type(node).__name__})",
            f"Expression '{type(node).__name__}' cannot be translated.",
            "Simplify the expression using supported Python constructs.",
        )
        return IRConst(cpp_type=INT_TYPE, value=0)


# ============================================================
# Human-Readable TAC Formatter (for UI Tab & Inspection)
# ============================================================

class TACFormatter:
    def __init__(self):
        self.lines: list[str] = []
        self.temp_count = 0
        self.label_count = 0

    def new_temp(self) -> str:
        self.temp_count += 1
        return f"t{self.temp_count}"

    def new_label(self) -> str:
        self.label_count += 1
        return f"L{self.label_count}"

    def format_module(self, module: IRModule) -> str:
        self.lines = []
        self.temp_count = 0
        self.label_count = 0

        for cls in module.classes:
            bases = f"({', '.join(cls.bases)})" if cls.bases else ""
            self.lines.append(f"CLASS {cls.name}{bases}:")
            for fname, ftype in cls.fields:
                self.lines.append(f"  FIELD {fname}: {ftype.to_cpp()}")
            for m in cls.methods:
                self._format_function(m, indent="  ")
            self.lines.append(f"END CLASS {cls.name}")
            self.lines.append("")

        for fn in module.functions:
            self._format_function(fn, indent="")
            self.lines.append("")

        if module.main_body:
            self.lines.append("FUNC main() -> int:")
            for stmt in module.main_body:
                self._format_stmt(stmt, indent="  ")
            self.lines.append("END FUNC main")

        return "\n".join(self.lines).strip()

    def _format_function(self, fn: IRFunction, indent: str) -> None:
        params = ", ".join(f"{p}: {t.to_cpp()}" for p, t, _ in fn.params)
        self.lines.append(f"{indent}FUNC {fn.name}({params}) -> {fn.return_type.to_cpp()}:")
        for stmt in fn.body:
            self._format_stmt(stmt, indent=indent + "  ")
        self.lines.append(f"{indent}END FUNC {fn.name}")

    def _format_expr(self, expr: IRExpr, indent: str) -> str:
        if isinstance(expr, IRConst):
            return repr(expr.value)
        if isinstance(expr, IRVar):
            return expr.name
        if isinstance(expr, IRBinOp):
            l = self._format_expr(expr.left, indent)
            r = self._format_expr(expr.right, indent)
            t = self.new_temp()
            self.lines.append(f"{indent}{t} = {l} {expr.op} {r}")
            return t
        if isinstance(expr, IRUnaryOp):
            o = self._format_expr(expr.operand, indent)
            t = self.new_temp()
            self.lines.append(f"{indent}{t} = {expr.op} {o}")
            return t
        if isinstance(expr, IRBoolOp):
            vals = [self._format_expr(v, indent) for v in expr.values]
            t = self.new_temp()
            self.lines.append(f"{indent}{t} = {f' {expr.op} '.join(vals)}")
            return t
        if isinstance(expr, IRCompare):
            cur = self._format_expr(expr.left, indent)
            parts = []
            for op, comp in zip(expr.ops, expr.comparators):
                nxt = self._format_expr(comp, indent)
                parts.append(f"{cur} {op} {nxt}")
                cur = nxt
            t = self.new_temp()
            self.lines.append(f"{indent}{t} = {' and '.join(parts)}")
            return t
        if isinstance(expr, IRCall):
            args = ", ".join(self._format_expr(a, indent) for a in expr.args)
            t = self.new_temp()
            self.lines.append(f"{indent}{t} = CALL {expr.func_name}({args})")
            return t
        if isinstance(expr, IRMethodCall):
            obj = self._format_expr(expr.obj, indent)
            args = ", ".join(self._format_expr(a, indent) for a in expr.args)
            t = self.new_temp()
            self.lines.append(f"{indent}{t} = CALL {obj}.{expr.method}({args})")
            return t
        if isinstance(expr, IRAttribute):
            obj = self._format_expr(expr.obj, indent)
            return f"{obj}.{expr.attr}"
        if isinstance(expr, IRIndex):
            obj = self._format_expr(expr.obj, indent)
            idx = self._format_expr(expr.index, indent)
            return f"{obj}[{idx}]"
        if isinstance(expr, IRCollection):
            elts = ", ".join(self._format_expr(e, indent) for e in expr.elements)
            t = self.new_temp()
            self.lines.append(f"{indent}{t} = {expr.kind.upper()}[{elts}]")
            return t
        if isinstance(expr, IRDict):
            pairs = ", ".join(
                f"{self._format_expr(k, indent)}: {self._format_expr(v, indent)}"
                for k, v in zip(expr.keys, expr.values)
            )
            t = self.new_temp()
            self.lines.append(f"{indent}{t} = DICT{{{pairs}}}")
            return t
        if isinstance(expr, IRFString):
            parts = " + ".join(self._format_expr(p, indent) for p in expr.parts)
            t = self.new_temp()
            self.lines.append(f"{indent}{t} = FSTR({parts})")
            return t
        return "<expr>"

    def _format_stmt(self, stmt: IRStmt, indent: str) -> None:
        if isinstance(stmt, IRAssign):
            rhs = self._format_expr(stmt.value, indent)
            if isinstance(stmt.target, list):
                lhs = ", ".join(stmt.target)
            elif isinstance(stmt.target, IRExpr):
                lhs = self._format_expr(stmt.target, indent)
            else:
                lhs = str(stmt.target)
            self.lines.append(f"{indent}{lhs} = {rhs}")
        elif isinstance(stmt, IRAugAssign):
            rhs = self._format_expr(stmt.value, indent)
            lhs = self._format_expr(stmt.target, indent) if isinstance(stmt.target, IRExpr) else str(stmt.target)
            self.lines.append(f"{indent}{lhs} = {lhs} {stmt.op} {rhs}")
        elif isinstance(stmt, IRExprStmt):
            self._format_expr(stmt.expr, indent)
        elif isinstance(stmt, IRPrint):
            args = ", ".join(self._format_expr(a, indent) for a in stmt.args)
            self.lines.append(f"{indent}PRINT {args}")
        elif isinstance(stmt, IRReturn):
            if stmt.value is not None:
                val = self._format_expr(stmt.value, indent)
                self.lines.append(f"{indent}RETURN {val}")
            else:
                self.lines.append(f"{indent}RETURN")
        elif isinstance(stmt, IRBreak):
            self.lines.append(f"{indent}BREAK")
        elif isinstance(stmt, IRContinue):
            self.lines.append(f"{indent}CONTINUE")
        elif isinstance(stmt, IRPass):
            self.lines.append(f"{indent}NOP")
        elif isinstance(stmt, IRIf):
            cond = self._format_expr(stmt.test, indent)
            else_lbl = self.new_label()
            end_lbl = self.new_label()
            self.lines.append(f"{indent}ifFalse {cond} goto {else_lbl}")
            for s in stmt.body:
                self._format_stmt(s, indent)
            self.lines.append(f"{indent}goto {end_lbl}")
            self.lines.append(f"{indent}{else_lbl}:")
            for s in stmt.orelse:
                self._format_stmt(s, indent)
            self.lines.append(f"{indent}{end_lbl}:")
        elif isinstance(stmt, IRWhile):
            start_lbl = self.new_label()
            end_lbl = self.new_label()
            self.lines.append(f"{indent}{start_lbl}:")
            cond = self._format_expr(stmt.test, indent)
            self.lines.append(f"{indent}ifFalse {cond} goto {end_lbl}")
            for s in stmt.body:
                self._format_stmt(s, indent)
            self.lines.append(f"{indent}goto {start_lbl}")
            self.lines.append(f"{indent}{end_lbl}:")
        elif isinstance(stmt, IRForRangeBlock):
            start = self._format_expr(stmt.start, indent)
            stop = self._format_expr(stmt.stop, indent)
            step = self._format_expr(stmt.step, indent)
            self.lines.append(f"{indent}FOR {stmt.var_name} IN RANGE({start}, {stop}, {step}):")
            for s in stmt.body:
                self._format_stmt(s, indent + "  ")
            self.lines.append(f"{indent}END FOR")
        elif isinstance(stmt, IRForEach):
            it = self._format_expr(stmt.iterable, indent)
            t_str = ", ".join(stmt.targets)
            self.lines.append(f"{indent}FOREACH {t_str} IN {it}:")
            for s in stmt.body:
                self._format_stmt(s, indent + "  ")
            self.lines.append(f"{indent}END FOREACH")
        elif isinstance(stmt, IRTry):
            self.lines.append(f"{indent}TRY:")
            for s in stmt.body:
                self._format_stmt(s, indent + "  ")
            for h in stmt.handlers:
                self.lines.append(f"{indent}EXCEPT {h.exc_type}:")
                for s in h.body:
                    self._format_stmt(s, indent + "  ")
            self.lines.append(f"{indent}END TRY")
        elif isinstance(stmt, IRRaise):
            msg = self._format_expr(stmt.message, indent) if stmt.message else '""'
            self.lines.append(f"{indent}RAISE {stmt.exc_type}({msg})")


def build_ir_bundle(
    tree: ast.Module,
    source_lines: Optional[list[str]] = None,
    optimize: bool = True,
) -> tuple[IRModule, str]:
    builder = IRBuilder(tree, source_lines=source_lines)
    ir_module = builder.build()
    if optimize:
        ir_module = IROptimizer().optimize(ir_module)
    tac_text = TACFormatter().format_module(ir_module)
    return ir_module, tac_text


def generate_ir(
    tree: ast.Module,
    source_lines: Optional[list[str]] = None,
    optimize: bool = True,
) -> str:
    _, tac_text = build_ir_bundle(tree, source_lines=source_lines, optimize=optimize)
    return tac_text