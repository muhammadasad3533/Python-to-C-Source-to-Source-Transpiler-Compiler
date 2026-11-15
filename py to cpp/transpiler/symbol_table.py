from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class CppType:
    """Represents a resolved C++ type."""
    base: str  # "int", "double", "bool", "std::string", "void", "std::vector", "std::tuple", "std::unordered_map", "std::unordered_set", "unknown", or ClassName
    params: tuple["CppType", ...] = ()
    is_class: bool = False

    def to_cpp(self) -> str:
        if self.base == "unknown":
            return "auto"
        if self.base == "std::vector":
            elem = self.params[0].to_cpp() if self.params else "int"
            return f"std::vector<{elem}>"
        if self.base == "std::unordered_set":
            elem = self.params[0].to_cpp() if self.params else "int"
            return f"std::unordered_set<{elem}>"
        if self.base == "std::unordered_map":
            k = self.params[0].to_cpp() if len(self.params) >= 1 else "std::string"
            v = self.params[1].to_cpp() if len(self.params) >= 2 else "int"
            return f"std::unordered_map<{k}, {v}>"
        if self.base == "std::tuple":
            if not self.params:
                return "std::tuple<>"
            inner = ", ".join(p.to_cpp() for p in self.params)
            return f"std::tuple<{inner}>"
        return self.base

    def is_numeric(self) -> bool:
        return self.base in ("int", "double", "bool")

    def is_known(self) -> bool:
        if self.base == "unknown":
            return False
        return all(p.is_known() for p in self.params)


# Common primitive singletons
INT_TYPE = CppType("int")
DOUBLE_TYPE = CppType("double")
BOOL_TYPE = CppType("bool")
STR_TYPE = CppType("std::string")
VOID_TYPE = CppType("void")
UNKNOWN_TYPE = CppType("unknown")


def unify_types(t1: CppType, t2: CppType) -> Optional[CppType]:
    """Unify two C++ types if compatible (e.g., int + double -> double)."""
    if t1 == t2:
        return t1
    if t1 == UNKNOWN_TYPE:
        return t2
    if t2 == UNKNOWN_TYPE:
        return t1
    if {t1.base, t2.base} <= {"int", "double"}:
        return DOUBLE_TYPE
    if {t1.base, t2.base} <= {"int", "bool"}:
        return INT_TYPE
    if t1.base == t2.base and len(t1.params) == len(t2.params):
        unified_params = []
        for p1, p2 in zip(t1.params, t2.params):
            u = unify_types(p1, p2)
            if u is None:
                return None
            unified_params.append(u)
        return CppType(t1.base, tuple(unified_params), t1.is_class)
    return None


@dataclass
class VariableSymbol:
    name: str
    cpp_type: CppType
    line: Optional[int] = None
    is_param: bool = False
    is_global_ref: bool = False
    is_nonlocal_ref: bool = False


@dataclass
class FunctionSymbol:
    name: str
    params: list[tuple[str, CppType]] = field(default_factory=list)
    defaults: dict[str, str] = field(default_factory=dict)
    return_type: CppType = UNKNOWN_TYPE
    line: Optional[int] = None
    is_method: bool = False
    owner_class: Optional[str] = None
    has_vararg: bool = False
    has_kwarg: bool = False


@dataclass
class ClassSymbol:
    name: str
    bases: list[str] = field(default_factory=list)
    fields: dict[str, CppType] = field(default_factory=dict)
    class_attributes: dict[str, CppType] = field(default_factory=dict)
    methods: dict[str, FunctionSymbol] = field(default_factory=dict)
    line: Optional[int] = None


class Scope:
    def __init__(self, name: str, kind: str, parent: Optional["Scope"] = None):
        self.name = name
        self.kind = kind  # "global", "class", "function", "block"
        self.parent = parent
        self.variables: dict[str, VariableSymbol] = {}
        self.functions: dict[str, FunctionSymbol] = {}
        self.classes: dict[str, ClassSymbol] = {}
        self.globals_declared: set[str] = set()
        self.nonlocals_declared: set[str] = set()

    def define_var(self, symbol: VariableSymbol) -> None:
        self.variables[symbol.name] = symbol

    def lookup_var(self, name: str) -> Optional[VariableSymbol]:
        if name in self.variables:
            return self.variables[name]
        if self.parent is not None:
            return self.parent.lookup_var(name)
        return None

    def lookup_var_local(self, name: str) -> Optional[VariableSymbol]:
        return self.variables.get(name)

    def define_func(self, func: FunctionSymbol) -> None:
        self.functions[func.name] = func

    def lookup_func(self, name: str) -> Optional[FunctionSymbol]:
        if name in self.functions:
            return self.functions[name]
        if self.parent is not None:
            return self.parent.lookup_func(name)
        return None

    def define_class(self, cls: ClassSymbol) -> None:
        self.classes[cls.name] = cls

    def lookup_class(self, name: str) -> Optional[ClassSymbol]:
        if name in self.classes:
            return self.classes[name]
        if self.parent is not None:
            return self.parent.lookup_class(name)
        return None


class SymbolTable:
    def __init__(self):
        self.global_scope = Scope("global", "global")
        self.current_scope = self.global_scope
        self.function_scopes: dict[str, Scope] = {}
        self.imported_modules: set[str] = set()
        self.imported_symbols: dict[str, str] = {}  # alias -> full.name

    def enter_scope(self, name: str, kind: str) -> Scope:
        scope = Scope(name=name, kind=kind, parent=self.current_scope)
        self.current_scope = scope
        if kind == "function":
            self.function_scopes[name] = scope
        return scope

    def exit_scope(self) -> None:
        if self.current_scope.parent is not None:
            self.current_scope = self.current_scope.parent