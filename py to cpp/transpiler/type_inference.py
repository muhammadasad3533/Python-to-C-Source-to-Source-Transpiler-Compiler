import ast
from typing import Optional
from transpiler.errors import TranspilerError, get_source_line
from transpiler.symbol_table import (
    BOOL_TYPE,
    DOUBLE_TYPE,
    INT_TYPE,
    STR_TYPE,
    UNKNOWN_TYPE,
    VOID_TYPE,
    ClassSymbol,
    CppType,
    FunctionSymbol,
    Scope,
    SymbolTable,
    VariableSymbol,
    unify_types,
)


def list_of(elem: CppType) -> CppType:
    return CppType("std::vector", [elem])


def set_of(elem: CppType) -> CppType:
    return CppType("std::unordered_set", [elem])


def dict_of(key: CppType, val: CppType) -> CppType:
    return CppType("std::unordered_map", [key, val])


def tuple_of(elems: list[CppType]) -> CppType:
    return CppType("std::tuple", elems)


class TypeInferenceEngine:
    def __init__(self, tree: ast.Module, source_lines: Optional[list[str]] = None):
        self.tree = tree
        self.source_lines = source_lines or []
        self.symtab = SymbolTable()
        self.node_types: dict[int, CppType] = {}

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

    def resolve_annotation(self, ann: Optional[ast.AST]) -> CppType:
        if ann is None:
            return UNKNOWN_TYPE
        if isinstance(ann, ast.Constant):
            if ann.value is None:
                return VOID_TYPE
            if isinstance(ann.value, str):
                return CppType(ann.value)
        if isinstance(ann, ast.Name):
            mapping = {
                "int": INT_TYPE,
                "float": DOUBLE_TYPE,
                "str": STR_TYPE,
                "bool": BOOL_TYPE,
                "None": VOID_TYPE,
                "list": list_of(INT_TYPE),
                "dict": dict_of(STR_TYPE, INT_TYPE),
                "set": set_of(INT_TYPE),
                "tuple": tuple_of([INT_TYPE]),
            }
            if ann.id in mapping:
                return mapping[ann.id]
            if self.symtab.global_scope.lookup_class(ann.id):
                return CppType(ann.id)
            return CppType(ann.id)
        if isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name):
            container = ann.value.id
            if container == "list":
                return list_of(self.resolve_annotation(ann.slice))
            if container == "set":
                return set_of(self.resolve_annotation(ann.slice))
            if container == "dict" and isinstance(ann.slice, ast.Tuple) and len(ann.slice.elts) == 2:
                k_t = self.resolve_annotation(ann.slice.elts[0])
                v_t = self.resolve_annotation(ann.slice.elts[1])
                return dict_of(k_t, v_t)
            if container == "tuple":
                if isinstance(ann.slice, ast.Tuple):
                    return tuple_of([self.resolve_annotation(e) for e in ann.slice.elts])
                return tuple_of([self.resolve_annotation(ann.slice)])
        return UNKNOWN_TYPE

    def analyze(self) -> SymbolTable:
        global_scope = self.symtab.global_scope

        # Pass 1: Register imports, classes, and top-level function skeletons
        for stmt in self.tree.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    self.symtab.imported_modules.add(alias.asname or alias.name)
            elif isinstance(stmt, ast.ImportFrom):
                if stmt.module:
                    for alias in stmt.names:
                        self.symtab.imported_symbols[alias.asname or alias.name] = stmt.module
            elif isinstance(stmt, ast.ClassDef):
                bases = [b.id for b in stmt.bases if isinstance(b, ast.Name)]
                cls_sym = ClassSymbol(name=stmt.name, bases=bases, line=stmt.lineno)
                global_scope.define_class(cls_sym)
                self._register_class_skeleton(stmt, cls_sym)
            elif isinstance(stmt, ast.FunctionDef):
                fn_sym = self._create_func_symbol(stmt)
                global_scope.define_func(fn_sym)

        # Pass 2: Infer global variables and propagate call-site argument types into functions & constructors
        self._infer_block(self.tree.body, global_scope)

        # Pass 3: Re-infer class methods and functions with propagated parameter & inheritance field types
        for _ in range(3):
            self._sync_inherited_fields()
            for stmt in self.tree.body:
                if isinstance(stmt, ast.ClassDef):
                    cls_sym = global_scope.lookup_class(stmt.name)
                    if cls_sym:
                        self._infer_class_bodies(stmt, cls_sym)
                elif isinstance(stmt, ast.FunctionDef):
                    fn_sym = global_scope.lookup_func(stmt.name)
                    if fn_sym:
                        self._infer_function_body(stmt, fn_sym, global_scope)
            self._sync_inherited_fields()
            self._infer_block(self.tree.body, global_scope)

        # Finalize any remaining UNKNOWN types to sensible C++ defaults
        self._finalize_scope(global_scope)
        for fn_scope in self.symtab.function_scopes.values():
            self._finalize_scope(fn_scope)
        for cls_sym in global_scope.classes.values():
            for fname, ftype in list(cls_sym.fields.items()):
                if ftype == UNKNOWN_TYPE:
                    cls_sym.fields[fname] = INT_TYPE
            for fn_sym in cls_sym.methods.values():
                self._finalize_func(fn_sym)
        for fn_sym in global_scope.functions.values():
            self._finalize_func(fn_sym)

        return self.symtab

    def _sync_inherited_fields(self) -> None:
        """Synchronize field types between base classes and derived classes."""
        global_scope = self.symtab.global_scope
        for cls_sym in global_scope.classes.values():
            for bname in cls_sym.bases:
                bcls = global_scope.lookup_class(bname)
                if not bcls:
                    continue
                for fname, ftype in list(cls_sym.fields.items()):
                    if fname in bcls.fields:
                        btype = bcls.fields[fname]
                        merged = unify_types(btype, ftype)
                        if merged != UNKNOWN_TYPE:
                            bcls.fields[fname] = merged
                            cls_sym.fields[fname] = merged

    def _finalize_scope(self, scope: Scope) -> None:
        for vsym in scope.variables.values():
            if vsym.cpp_type == UNKNOWN_TYPE:
                vsym.cpp_type = INT_TYPE

    def _finalize_func(self, fn_sym: FunctionSymbol) -> None:
        fn_sym.params = [
            (pname, INT_TYPE if ptype == UNKNOWN_TYPE else ptype)
            for pname, ptype in fn_sym.params
        ]
        if fn_sym.return_type == UNKNOWN_TYPE:
            fn_sym.return_type = VOID_TYPE

    def _create_func_symbol(self, node: ast.FunctionDef, is_method: bool = False) -> FunctionSymbol:
        args = node.args.args
        defaults = node.args.defaults
        default_offset = len(args) - len(defaults)

        params: list[tuple[str, CppType]] = []

        for idx, arg in enumerate(args):
            if is_method and idx == 0 and arg.arg == "self":
                continue
            ann_type = self.resolve_annotation(arg.annotation)
            if idx >= default_offset:
                def_node = defaults[idx - default_offset]
                if ann_type == UNKNOWN_TYPE:
                    ann_type = self._quick_const_type(def_node)
            params.append((arg.arg, ann_type))

        ret_type = self.resolve_annotation(node.returns)
        return FunctionSymbol(
            name=node.name,
            params=params,
            return_type=ret_type,
            line=node.lineno,
            is_method=is_method,
        )

    def _quick_const_type(self, node: ast.AST) -> CppType:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return BOOL_TYPE
            if isinstance(node.value, int):
                return INT_TYPE
            if isinstance(node.value, float):
                return DOUBLE_TYPE
            if isinstance(node.value, str):
                return STR_TYPE
        return UNKNOWN_TYPE

    def _register_class_skeleton(self, node: ast.ClassDef, cls_sym: ClassSymbol) -> None:
        global_scope = self.symtab.global_scope
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                fn_sym = self._create_func_symbol(item, is_method=True)
                cls_sym.methods[item.name] = fn_sym
                m_scope = Scope(f"{cls_sym.name}.{item.name}", "function", parent=global_scope)
                m_scope.define_var(VariableSymbol("self", CppType(cls_sym.name), item.lineno, is_param=True))
                for pname, ptype in fn_sym.params:
                    m_scope.define_var(VariableSymbol(pname, ptype, item.lineno, is_param=True))
                self.symtab.function_scopes[f"{cls_sym.name}.{item.name}"] = m_scope

                # Pre-register all self.<attr> assignments in __init__ so fields always exist
                if item.name == "__init__":
                    for sub in ast.walk(item):
                        if isinstance(sub, ast.Assign):
                            for tgt in sub.targets:
                                if (
                                    isinstance(tgt, ast.Attribute)
                                    and isinstance(tgt.value, ast.Name)
                                    and tgt.value.id == "self"
                                ):
                                    if tgt.attr not in cls_sym.fields:
                                        cls_sym.fields[tgt.attr] = UNKNOWN_TYPE
            elif isinstance(item, ast.Assign):
                for tgt in item.targets:
                    if isinstance(tgt, ast.Name):
                        cls_sym.class_attributes[tgt.id] = self.infer_expr(item.value, global_scope)

    def _infer_class_bodies(self, node: ast.ClassDef, cls_sym: ClassSymbol) -> None:
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                fn_sym = cls_sym.methods[item.name]
                m_scope = self.symtab.function_scopes[f"{cls_sym.name}.{item.name}"]

                # If self.<attr> = <param> and <attr> already has a known field type, back-propagate to <param>
                for sub in item.body:
                    if (
                        isinstance(sub, ast.Assign)
                        and len(sub.targets) == 1
                        and isinstance(sub.targets[0], ast.Attribute)
                        and isinstance(sub.targets[0].value, ast.Name)
                        and sub.targets[0].value.id == "self"
                        and isinstance(sub.value, ast.Name)
                    ):
                        attr_name = sub.targets[0].attr
                        param_name = sub.value.id
                        field_t = cls_sym.fields.get(attr_name, UNKNOWN_TYPE)
                        if field_t != UNKNOWN_TYPE:
                            for idx, (pname, ptype) in enumerate(fn_sym.params):
                                if pname == param_name and ptype == UNKNOWN_TYPE:
                                    fn_sym.params[idx] = (pname, field_t)

                for pname, ptype in fn_sym.params:
                    if pname in m_scope.variables and ptype != UNKNOWN_TYPE:
                        m_scope.variables[pname].cpp_type = ptype
                self._infer_block(item.body, m_scope, active_func=fn_sym, active_class=cls_sym)

    def _infer_function_body(self, node: ast.FunctionDef, fn_sym: FunctionSymbol, parent_scope: Scope) -> None:
        fn_scope = self.symtab.function_scopes.get(fn_sym.name)
        if fn_scope is None:
            fn_scope = Scope(fn_sym.name, "function", parent=parent_scope)
            self.symtab.function_scopes[fn_sym.name] = fn_scope

        for pname, ptype in fn_sym.params:
            if pname in fn_scope.variables:
                if ptype != UNKNOWN_TYPE:
                    fn_scope.variables[pname].cpp_type = ptype
            else:
                fn_scope.define_var(VariableSymbol(pname, ptype, node.lineno, is_param=True))

        self._infer_block(node.body, fn_scope, active_func=fn_sym)

    def _infer_block(
        self,
        stmts: list[ast.AST],
        scope: Scope,
        active_func: Optional[FunctionSymbol] = None,
        active_class: Optional[ClassSymbol] = None,
    ) -> None:
        for stmt in stmts:
            self._infer_stmt(stmt, scope, active_func=active_func, active_class=active_class)

    def _infer_stmt(
        self,
        stmt: ast.AST,
        scope: Scope,
        active_func: Optional[FunctionSymbol] = None,
        active_class: Optional[ClassSymbol] = None,
    ) -> None:
        if isinstance(stmt, ast.Global):
            for name in stmt.names:
                scope.globals_declared.add(name)
            return

        if isinstance(stmt, ast.Assign):
            val_type = self.infer_expr(stmt.value, scope)
            for target in stmt.targets:
                self._assign_target(target, val_type, stmt.lineno, scope, active_class=active_class)
            return

        if isinstance(stmt, ast.AnnAssign):
            ann_type = self.resolve_annotation(stmt.annotation)
            val_type = self.infer_expr(stmt.value, scope) if stmt.value is not None else ann_type
            final_type = ann_type if ann_type != UNKNOWN_TYPE else val_type
            self._assign_target(stmt.target, final_type, stmt.lineno, scope, active_class=active_class)
            return

        if isinstance(stmt, ast.AugAssign):
            val_type = self.infer_expr(stmt.value, scope)
            if isinstance(stmt.target, ast.Name):
                existing = scope.lookup_var(stmt.target.id)
                cur = existing.cpp_type if existing else UNKNOWN_TYPE
                merged = DOUBLE_TYPE if isinstance(stmt.op, ast.Div) else unify_types(cur, val_type)
                self._assign_target(stmt.target, merged, stmt.lineno, scope, active_class=active_class)
            else:
                self.infer_expr(stmt.target, scope)
            return

        if isinstance(stmt, ast.Expr):
            self.infer_expr(stmt.value, scope)
            return

        if isinstance(stmt, ast.Return):
            if active_func is not None:
                if stmt.value is None:
                    active_func.return_type = unify_types(active_func.return_type, VOID_TYPE)
                else:
                    r_type = self.infer_expr(stmt.value, scope)
                    if r_type != UNKNOWN_TYPE:
                        active_func.return_type = unify_types(active_func.return_type, r_type)
            return

        if isinstance(stmt, ast.If):
            self.infer_expr(stmt.test, scope)
            self._infer_block(stmt.body, scope, active_func=active_func, active_class=active_class)
            self._infer_block(stmt.orelse, scope, active_func=active_func, active_class=active_class)
            return

        if isinstance(stmt, ast.While):
            self.infer_expr(stmt.test, scope)
            self._infer_block(stmt.body, scope, active_func=active_func, active_class=active_class)
            return

        if isinstance(stmt, ast.For):
            iter_type = self.infer_expr(stmt.iter, scope)
            elem_type = self._iterable_element_type(stmt.iter, iter_type)
            self._assign_target(stmt.target, elem_type, stmt.lineno, scope, active_class=active_class)
            self._infer_block(stmt.body, scope, active_func=active_func, active_class=active_class)
            return

        if isinstance(stmt, ast.Try):
            self._infer_block(stmt.body, scope, active_func=active_func, active_class=active_class)
            for h in stmt.handlers:
                if h.name:
                    self._assign_target(ast.Name(id=h.name, ctx=ast.Store()), STR_TYPE, h.lineno, scope)
                self._infer_block(h.body, scope, active_func=active_func, active_class=active_class)
            self._infer_block(stmt.orelse, scope, active_func=active_func, active_class=active_class)
            self._infer_block(stmt.finalbody, scope, active_func=active_func, active_class=active_class)
            return

        if isinstance(stmt, ast.Raise):
            if stmt.exc is not None:
                self.infer_expr(stmt.exc, scope)
            return

    def _iterable_element_type(self, iter_node: ast.AST, iter_type: CppType) -> CppType:
        if (
            isinstance(iter_node, ast.Call)
            and isinstance(iter_node.func, ast.Name)
            and iter_node.func.id == "range"
        ):
            return INT_TYPE
        if iter_type == STR_TYPE:
            return STR_TYPE
        if iter_type.base in ("std::vector", "std::unordered_set") and iter_type.params:
            return iter_type.params[0]
        if iter_type.base == "std::unordered_map" and iter_type.params:
            return iter_type.params[0]
        if iter_type.base == "std::tuple" and iter_type.params:
            return iter_type.params[0]
        return INT_TYPE

    def _assign_target(
        self,
        target: ast.AST,
        val_type: CppType,
        line: int,
        scope: Scope,
        active_class: Optional[ClassSymbol] = None,
    ) -> None:
        if isinstance(target, ast.Name):
            target_scope = self.symtab.global_scope if target.id in scope.globals_declared else scope
            existing = target_scope.variables.get(target.id)
            if existing is not None:
                if val_type != UNKNOWN_TYPE:
                    existing.cpp_type = unify_types(existing.cpp_type, val_type)
            else:
                target_scope.define_var(VariableSymbol(target.id, val_type, line))
            return

        if isinstance(target, ast.Attribute):
            if isinstance(target.value, ast.Name) and target.value.id == "self" and active_class is not None:
                existing_f = active_class.fields.get(target.attr, UNKNOWN_TYPE)
                if val_type != UNKNOWN_TYPE:
                    merged_f = unify_types(existing_f, val_type)
                    active_class.fields[target.attr] = merged_f
                    for bname in active_class.bases:
                        bcls = self.symtab.global_scope.lookup_class(bname)
                        if bcls and target.attr in bcls.fields:
                            bcls.fields[target.attr] = unify_types(bcls.fields[target.attr], merged_f)
                elif target.attr not in active_class.fields:
                    active_class.fields[target.attr] = UNKNOWN_TYPE
            return

        if isinstance(target, (ast.Tuple, ast.List)):
            if val_type.base == "std::tuple" and len(val_type.params) == len(target.elts):
                for elt, sub_t in zip(target.elts, val_type.params):
                    self._assign_target(elt, sub_t, line, scope, active_class=active_class)
            else:
                for elt in target.elts:
                    self._assign_target(elt, INT_TYPE, line, scope, active_class=active_class)
            return

        if isinstance(target, ast.Subscript):
            self.infer_expr(target, scope)

    def infer_expr(self, node: Optional[ast.AST], scope: Scope) -> CppType:
        if node is None:
            return VOID_TYPE

        inferred = self._compute_expr_type(node, scope)
        self.node_types[id(node)] = inferred
        return inferred

    def _compute_expr_type(self, node: ast.AST, scope: Scope) -> CppType:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return BOOL_TYPE
            if isinstance(node.value, int):
                return INT_TYPE
            if isinstance(node.value, float):
                return DOUBLE_TYPE
            if isinstance(node.value, str):
                return STR_TYPE
            if node.value is None:
                return VOID_TYPE
            return UNKNOWN_TYPE

        if isinstance(node, ast.Name):
            if node.id in ("True", "False"):
                return BOOL_TYPE
            if node.id == "None":
                return VOID_TYPE
            sym = scope.lookup_var(node.id)
            if sym is not None:
                return sym.cpp_type
            cls = scope.lookup_class(node.id)
            if cls is not None:
                return CppType(cls.name)
            return UNKNOWN_TYPE

        if isinstance(node, ast.JoinedStr):
            for v in node.values:
                if isinstance(v, ast.FormattedValue):
                    self.infer_expr(v.value, scope)
            return STR_TYPE

        if isinstance(node, ast.UnaryOp):
            op_t = self.infer_expr(node.operand, scope)
            if isinstance(node.op, ast.Not):
                return BOOL_TYPE
            return op_t if op_t != UNKNOWN_TYPE else INT_TYPE

        if isinstance(node, ast.BoolOp):
            for v in node.values:
                self.infer_expr(v, scope)
            return BOOL_TYPE

        if isinstance(node, ast.Compare):
            self.infer_expr(node.left, scope)
            for c in node.comparators:
                self.infer_expr(c, scope)
            return BOOL_TYPE

        if isinstance(node, ast.IfExp):
            self.infer_expr(node.test, scope)
            t1 = self.infer_expr(node.body, scope)
            t2 = self.infer_expr(node.orelse, scope)
            return unify_types(t1, t2)

        if isinstance(node, ast.BinOp):
            lt = self.infer_expr(node.left, scope)
            rt = self.infer_expr(node.right, scope)
            if isinstance(node.op, ast.Div):
                return DOUBLE_TYPE
            if isinstance(node.op, ast.Add) and (lt == STR_TYPE or rt == STR_TYPE):
                return STR_TYPE
            if isinstance(node.op, ast.Mult) and (lt == STR_TYPE or rt == STR_TYPE):
                return STR_TYPE
            if isinstance(node.op, ast.Pow):
                if lt == DOUBLE_TYPE or rt == DOUBLE_TYPE:
                    return DOUBLE_TYPE
                if isinstance(node.right, ast.Constant) and isinstance(node.right.value, int) and node.right.value < 0:
                    return DOUBLE_TYPE
                return INT_TYPE
            if lt == DOUBLE_TYPE or rt == DOUBLE_TYPE:
                return DOUBLE_TYPE
            if lt != UNKNOWN_TYPE:
                return lt
            if rt != UNKNOWN_TYPE:
                return rt
            return INT_TYPE

        if isinstance(node, ast.List):
            if not node.elts:
                return list_of(INT_TYPE)
            elem_t = UNKNOWN_TYPE
            for e in node.elts:
                elem_t = unify_types(elem_t, self.infer_expr(e, scope))
            return list_of(elem_t if elem_t != UNKNOWN_TYPE else INT_TYPE)

        if isinstance(node, ast.Tuple):
            if not node.elts:
                return tuple_of([INT_TYPE])
            return tuple_of([self.infer_expr(e, scope) for e in node.elts])

        if isinstance(node, ast.Set):
            if not node.elts:
                return set_of(INT_TYPE)
            elem_t = UNKNOWN_TYPE
            for e in node.elts:
                elem_t = unify_types(elem_t, self.infer_expr(e, scope))
            return set_of(elem_t if elem_t != UNKNOWN_TYPE else INT_TYPE)

        if isinstance(node, ast.Dict):
            if not node.keys:
                return dict_of(STR_TYPE, INT_TYPE)
            kt = UNKNOWN_TYPE
            vt = UNKNOWN_TYPE
            for k, v in zip(node.keys, node.values):
                if k is not None:
                    kt = unify_types(kt, self.infer_expr(k, scope))
                vt = unify_types(vt, self.infer_expr(v, scope))
            return dict_of(
                kt if kt != UNKNOWN_TYPE else STR_TYPE,
                vt if vt != UNKNOWN_TYPE else INT_TYPE,
            )

        if isinstance(node, ast.ListComp):
            gen = node.generators[0]
            it_t = self.infer_expr(gen.iter, scope)
            el_t = self._iterable_element_type(gen.iter, it_t)
            comp_scope = Scope("listcomp", "block", parent=scope)
            if isinstance(gen.target, ast.Name):
                comp_scope.define_var(VariableSymbol(gen.target.id, el_t, node.lineno))
            for cond in gen.ifs:
                self.infer_expr(cond, comp_scope)
            res_el = self.infer_expr(node.elt, comp_scope)
            return list_of(res_el if res_el != UNKNOWN_TYPE else INT_TYPE)

        if isinstance(node, ast.DictComp):
            gen = node.generators[0]
            it_t = self.infer_expr(gen.iter, scope)
            el_t = self._iterable_element_type(gen.iter, it_t)
            comp_scope = Scope("dictcomp", "block", parent=scope)
            if isinstance(gen.target, ast.Name):
                comp_scope.define_var(VariableSymbol(gen.target.id, el_t, node.lineno))
            for cond in gen.ifs:
                self.infer_expr(cond, comp_scope)
            kt = self.infer_expr(node.key, comp_scope)
            vt = self.infer_expr(node.value, comp_scope)
            return dict_of(kt if kt != UNKNOWN_TYPE else STR_TYPE, vt if vt != UNKNOWN_TYPE else INT_TYPE)

        if isinstance(node, ast.Subscript):
            val_t = self.infer_expr(node.value, scope)
            if isinstance(node.slice, ast.Slice):
                if node.slice.lower:
                    self.infer_expr(node.slice.lower, scope)
                if node.slice.upper:
                    self.infer_expr(node.slice.upper, scope)
                if node.slice.step:
                    self.infer_expr(node.slice.step, scope)
                return val_t
            self.infer_expr(node.slice, scope)
            if val_t == STR_TYPE:
                return STR_TYPE
            if val_t.base == "std::vector" and val_t.params:
                return val_t.params[0]
            if val_t.base == "std::unordered_map" and len(val_t.params) == 2:
                return val_t.params[1]
            if val_t.base == "std::tuple" and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int):
                idx = node.slice.value
                if 0 <= idx < len(val_t.params):
                    return val_t.params[idx]
            return INT_TYPE

        if isinstance(node, ast.Attribute):
            obj_t = self.infer_expr(node.value, scope)
            if isinstance(node.value, ast.Name) and node.value.id == "math":
                return DOUBLE_TYPE
            cls_sym = self.symtab.global_scope.lookup_class(obj_t.base)
            if cls_sym:
                if node.attr in cls_sym.fields:
                    return cls_sym.fields[node.attr]
                if node.attr in cls_sym.class_attributes:
                    return cls_sym.class_attributes[node.attr]
                for bname in cls_sym.bases:
                    bcls = self.symtab.global_scope.lookup_class(bname)
                    if bcls and node.attr in bcls.fields:
                        return bcls.fields[node.attr]
            return UNKNOWN_TYPE

        if isinstance(node, ast.Lambda):
            param_types = [INT_TYPE for _ in node.args.args]
            lam_scope = Scope("lambda", "function", parent=scope)
            for arg in node.args.args:
                lam_scope.define_var(VariableSymbol(arg.arg, INT_TYPE, node.lineno, is_param=True))
            ret_t = self.infer_expr(node.body, lam_scope)
            if ret_t == UNKNOWN_TYPE:
                ret_t = INT_TYPE
            return CppType("std::function", [CppType(f"{ret_t.to_cpp()}({', '.join(p.to_cpp() for p in param_types)})")])

        if isinstance(node, ast.Call):
            arg_types = [self.infer_expr(a, scope) for a in node.args]
            kw_types = {kw.arg: self.infer_expr(kw.value, scope) for kw in node.keywords if kw.arg}

            if isinstance(node.func, ast.Name):
                fname = node.func.id
                if fname == "input":
                    return STR_TYPE
                if fname == "int":
                    return INT_TYPE
                if fname == "float":
                    return DOUBLE_TYPE
                if fname == "str":
                    return STR_TYPE
                if fname == "bool":
                    return BOOL_TYPE
                if fname == "len":
                    return INT_TYPE
                if fname == "abs":
                    return arg_types[0] if arg_types and arg_types[0] != UNKNOWN_TYPE else INT_TYPE
                if fname in ("max", "min", "sum"):
                    if len(arg_types) == 1 and arg_types[0].base == "std::vector" and arg_types[0].params:
                        return arg_types[0].params[0]
                    if arg_types:
                        res = UNKNOWN_TYPE
                        for at in arg_types:
                            res = unify_types(res, at)
                        return res if res != UNKNOWN_TYPE else INT_TYPE
                    return INT_TYPE
                if fname == "round":
                    return DOUBLE_TYPE if len(arg_types) >= 2 else INT_TYPE
                if fname in ("sorted", "reversed", "list"):
                    if arg_types and arg_types[0].base == "std::vector":
                        return arg_types[0]
                    if arg_types and arg_types[0] == STR_TYPE:
                        return list_of(STR_TYPE)
                    return list_of(INT_TYPE)
                if fname == "set":
                    if arg_types and arg_types[0].params:
                        return set_of(arg_types[0].params[0])
                    return set_of(INT_TYPE)
                if fname == "enumerate":
                    el = arg_types[0].params[0] if (arg_types and arg_types[0].params) else INT_TYPE
                    return list_of(tuple_of([INT_TYPE, el]))
                if fname == "zip":
                    t1 = arg_types[0].params[0] if (len(arg_types) > 0 and arg_types[0].params) else INT_TYPE
                    t2 = arg_types[1].params[0] if (len(arg_types) > 1 and arg_types[1].params) else INT_TYPE
                    return list_of(tuple_of([t1, t2]))
                if fname in ("type", "isinstance"):
                    return STR_TYPE if fname == "type" else BOOL_TYPE
                if fname == "print":
                    return VOID_TYPE

                # Class constructor call -> propagate argument types to __init__
                cls_sym = scope.lookup_class(fname)
                if cls_sym is not None:
                    if "__init__" in cls_sym.methods:
                        init_sym = cls_sym.methods["__init__"]
                        init_scope = self.symtab.function_scopes.get(f"{fname}.__init__")
                        for idx, at in enumerate(arg_types):
                            if idx < len(init_sym.params) and at != UNKNOWN_TYPE:
                                pname, ptype = init_sym.params[idx]
                                merged_p = unify_types(ptype, at)
                                init_sym.params[idx] = (pname, merged_p)
                                if init_scope and pname in init_scope.variables:
                                    init_scope.variables[pname].cpp_type = merged_p
                    return CppType(cls_sym.name)

                # User-defined function call -> propagate argument types
                fn_sym = scope.lookup_func(fname)
                if fn_sym is not None:
                    for idx, at in enumerate(arg_types):
                        if idx < len(fn_sym.params) and at != UNKNOWN_TYPE:
                            pname, ptype = fn_sym.params[idx]
                            fn_sym.params[idx] = (pname, unify_types(ptype, at))
                    for kw_name, kw_t in kw_types.items():
                        for idx, (pname, ptype) in enumerate(fn_sym.params):
                            if pname == kw_name and kw_t != UNKNOWN_TYPE:
                                fn_sym.params[idx] = (pname, unify_types(ptype, kw_t))
                    return fn_sym.return_type

            if isinstance(node.func, ast.Attribute):
                obj_t = self.infer_expr(node.func.value, scope)
                method = node.func.attr

                if isinstance(node.func.value, ast.Name) and node.func.value.id == "math":
                    if method in ("factorial", "gcd", "floor", "ceil"):
                        return INT_TYPE
                    return DOUBLE_TYPE

                if obj_t == STR_TYPE:
                    if method in ("upper", "lower", "strip", "replace", "join"):
                        return STR_TYPE
                    if method == "split":
                        return list_of(STR_TYPE)
                    if method in ("find", "count"):
                        return INT_TYPE
                    if method in ("startswith", "endswith", "isdigit", "isalpha"):
                        return BOOL_TYPE

                if obj_t.base == "std::vector":
                    if method in ("append", "insert", "clear", "sort", "reverse"):
                        return VOID_TYPE
                    if method == "pop":
                        return obj_t.params[0] if obj_t.params else INT_TYPE
                    if method == "count":
                        return INT_TYPE

                cls_sym = self.symtab.global_scope.lookup_class(obj_t.base)
                if cls_sym:
                    m_sym = cls_sym.methods.get(method)
                    if m_sym is None:
                        for bname in cls_sym.bases:
                            bcls = self.symtab.global_scope.lookup_class(bname)
                            if bcls and method in bcls.methods:
                                m_sym = bcls.methods[method]
                                break
                    if m_sym:
                        return m_sym.return_type

        return UNKNOWN_TYPE