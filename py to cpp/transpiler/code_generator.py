import ast
import json
from typing import Optional
from transpiler.errors import TranspilerError
from transpiler.intermediate_code import (
    IRAssign,
    IRAttribute,
    IRAugAssign,
    IRBinOp,
    IRBoolOp,
    IRBreak,
    IRCall,
    IRClass,
    IRCollection,
    IRCompare,
    IRConst,
    IRContinue,
    IRDict,
    IRDictComp,
    IRExpr,
    IRExprStmt,
    IRForEach,
    IRForRangeBlock,
    IRFString,
    IRFunction,
    IRIf,
    IRIndex,
    IRLambda,
    IRListComp,
    IRMethodCall,
    IRModule,
    IRPass,
    IRPrint,
    IRRaise,
    IRReturn,
    IRSlice,
    IRStmt,
    IRTernary,
    IRTry,
    IRUnaryOp,
    IRWhile,
    IRVar,
    build_ir_bundle,
)
from transpiler.symbol_table import (
    BOOL_TYPE,
    DOUBLE_TYPE,
    INT_TYPE,
    STR_TYPE,
    VOID_TYPE,
    CppType,
)


CPP_RUNTIME_HELPERS = r"""
// ============================================================
// Python-Compatible C++17 Runtime Helpers
// ============================================================
namespace py_rt {

inline int py_mod(int a, int b) {
    if (b == 0) throw std::runtime_error("ZeroDivisionError: integer division or modulo by zero");
    int r = a % b;
    return (r != 0 && ((r < 0) != (b < 0))) ? r + b : r;
}

inline double py_mod(double a, double b) {
    if (b == 0.0) throw std::runtime_error("ZeroDivisionError: float modulo");
    double r = std::fmod(a, b);
    return (r != 0.0 && ((r < 0.0) != (b < 0.0))) ? r + b : r;
}

inline int py_floordiv(int a, int b) {
    if (b == 0) throw std::runtime_error("ZeroDivisionError: integer division or modulo by zero");
    int q = a / b;
    int r = a % b;
    return (r != 0 && ((r < 0) != (b < 0))) ? q - 1 : q;
}

inline double py_floordiv(double a, double b) {
    if (b == 0.0) throw std::runtime_error("ZeroDivisionError: float floor division by zero");
    return std::floor(a / b);
}

template <typename T>
inline T& py_index(std::vector<T>& vec, int idx) {
    int n = static_cast<int>(vec.size());
    int real_idx = idx < 0 ? n + idx : idx;
    if (real_idx < 0 || real_idx >= n) {
        throw std::out_of_range("IndexError: list index out of range");
    }
    return vec[real_idx];
}

template <typename T>
inline const T& py_index(const std::vector<T>& vec, int idx) {
    int n = static_cast<int>(vec.size());
    int real_idx = idx < 0 ? n + idx : idx;
    if (real_idx < 0 || real_idx >= n) {
        throw std::out_of_range("IndexError: list index out of range");
    }
    return vec[real_idx];
}

inline std::string py_index(const std::string& s, int idx) {
    int n = static_cast<int>(s.size());
    int real_idx = idx < 0 ? n + idx : idx;
    if (real_idx < 0 || real_idx >= n) {
        throw std::out_of_range("IndexError: string index out of range");
    }
    return std::string(1, s[real_idx]);
}

template <typename T>
inline std::vector<T> py_slice(const std::vector<T>& vec, int start, int stop, int step, bool has_start, bool has_stop) {
    if (step == 0) throw std::invalid_argument("ValueError: slice step cannot be zero");
    int n = static_cast<int>(vec.size());
    int s = has_start ? (start < 0 ? std::max(0, n + start) : std::min(n, start)) : (step > 0 ? 0 : n - 1);
    int e = has_stop ? (stop < 0 ? std::max(-1, n + stop) : std::min(n, stop)) : (step > 0 ? n : -1);
    std::vector<T> out;
    if (step > 0) {
        for (int i = s; i < e; i += step) out.push_back(vec[i]);
    } else {
        for (int i = s; i > e; i += step) out.push_back(vec[i]);
    }
    return out;
}

inline std::string py_slice(const std::string& str, int start, int stop, int step, bool has_start, bool has_stop) {
    if (step == 0) throw std::invalid_argument("ValueError: slice step cannot be zero");
    int n = static_cast<int>(str.size());
    int s = has_start ? (start < 0 ? std::max(0, n + start) : std::min(n, start)) : (step > 0 ? 0 : n - 1);
    int e = has_stop ? (stop < 0 ? std::max(-1, n + stop) : std::min(n, stop)) : (step > 0 ? n : -1);
    std::string out;
    if (step > 0) {
        for (int i = s; i < e; i += step) out.push_back(str[i]);
    } else {
        for (int i = s; i > e; i += step) out.push_back(str[i]);
    }
    return out;
}

inline std::string str_repeat(const std::string& s, int times) {
    std::string out;
    if (times <= 0) return out;
    out.reserve(s.size() * times);
    for (int i = 0; i < times; ++i) out += s;
    return out;
}

inline std::string str_upper(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return std::toupper(c); });
    return s;
}

inline std::string str_lower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return std::tolower(c); });
    return s;
}

inline std::string str_strip(const std::string& s) {
    size_t start = s.find_first_not_of(" \t\n\r");
    if (start == std::string::npos) return "";
    size_t end = s.find_last_not_of(" \t\n\r");
    return s.substr(start, end - start + 1);
}

inline std::string str_replace(std::string s, const std::string& from, const std::string& to) {
    if (from.empty()) return s;
    size_t pos = 0;
    while ((pos = s.find(from, pos)) != std::string::npos) {
        s.replace(pos, from.length(), to);
        pos += to.length();
    }
    return s;
}

inline std::vector<std::string> str_split(const std::string& s, const std::string& sep = "") {
    std::vector<std::string> res;
    if (sep.empty()) {
        std::istringstream iss(s);
        std::string token;
        while (iss >> token) res.push_back(token);
        return res;
    }
    size_t start = 0, end;
    while ((end = s.find(sep, start)) != std::string::npos) {
        res.push_back(s.substr(start, end - start));
        start = end + sep.length();
    }
    res.push_back(s.substr(start));
    return res;
}

inline std::string str_join(const std::string& sep, const std::vector<std::string>& items) {
    std::string out;
    for (size_t i = 0; i < items.size(); ++i) {
        if (i > 0) out += sep;
        out += items[i];
    }
    return out;
}

inline std::string py_input(const std::string& prompt = "") {
    if (!prompt.empty()) {
        std::cout << prompt;
        std::cout.flush();
    }
    std::string line;
    std::getline(std::cin, line);
    return line;
}

template <typename T>
inline bool py_in(const T& item, const std::vector<T>& vec) {
    return std::find(vec.begin(), vec.end(), item) != vec.end();
}

template <typename T>
inline bool py_in(const T& item, const std::unordered_set<T>& st) {
    return st.find(item) != st.end();
}

template <typename K, typename V>
inline bool py_in(const K& key, const std::unordered_map<K, V>& mp) {
    return mp.find(key) != mp.end();
}

inline bool py_in(const std::string& sub, const std::string& s) {
    return s.find(sub) != std::string::npos;
}

template <typename T>
inline std::vector<T> py_sorted(std::vector<T> vec, bool reverse = false) {
    if (reverse) {
        std::sort(vec.begin(), vec.end(), std::greater<T>());
    } else {
        std::sort(vec.begin(), vec.end());
    }
    return vec;
}

template <typename T>
inline std::vector<T> py_reversed(std::vector<T> vec) {
    std::reverse(vec.begin(), vec.end());
    return vec;
}

template <typename T>
inline T py_sum(const std::vector<T>& vec) {
    return std::accumulate(vec.begin(), vec.end(), T{});
}

template <typename T>
inline std::vector<std::tuple<int, T>> py_enumerate(const std::vector<T>& vec, int start = 0) {
    std::vector<std::tuple<int, T>> out;
    out.reserve(vec.size());
    for (size_t i = 0; i < vec.size(); ++i) {
        out.emplace_back(start + static_cast<int>(i), vec[i]);
    }
    return out;
}

template <typename A, typename B>
inline std::vector<std::tuple<A, B>> py_zip(const std::vector<A>& a, const std::vector<B>& b) {
    size_t n = std::min(a.size(), b.size());
    std::vector<std::tuple<A, B>> out;
    out.reserve(n);
    for (size_t i = 0; i < n; ++i) {
        out.emplace_back(a[i], b[i]);
    }
    return out;
}

inline std::string to_py_str(const std::string& v) { return v; }
inline std::string to_py_str(const char* v) { return std::string(v); }
inline std::string to_py_str(bool v) { return v ? "True" : "False"; }
inline std::string to_py_str(int v) { return std::to_string(v); }
inline std::string to_py_str(long long v) { return std::to_string(v); }
inline std::string to_py_str(double v) {
    std::ostringstream oss;
    oss << v;
    std::string s = oss.str();
    if (s.find('.') == std::string::npos && s.find('e') == std::string::npos) {
        s += ".0";
    }
    return s;
}

template <typename T>
inline std::ostream& operator<<(std::ostream& os, const std::vector<T>& vec) {
    os << "[";
    for (size_t i = 0; i < vec.size(); ++i) {
        if (i > 0) os << ", ";
        if constexpr (std::is_same_v<T, std::string>) {
            os << "'" << vec[i] << "'";
        } else {
            os << vec[i];
        }
    }
    os << "]";
    return os;
}

template <typename K, typename V>
inline std::ostream& operator<<(std::ostream& os, const std::unordered_map<K, V>& mp) {
    os << "{";
    bool first = true;
    for (const auto& [k, v] : mp) {
        if (!first) os << ", ";
        first = false;
        if constexpr (std::is_same_v<K, std::string>) os << "'" << k << "'";
        else os << k;
        os << ": ";
        if constexpr (std::is_same_v<V, std::string>) os << "'" << v << "'";
        else os << v;
    }
    os << "}";
    return os;
}

} // namespace py_rt
"""


class CppCodeGenerator:
    def __init__(self, tree: ast.Module, ir_module: Optional[IRModule] = None, source_lines: Optional[list[str]] = None):
        self.tree = tree
        self.source_lines = source_lines or []
        if ir_module is None:
            ir_module, _ = build_ir_bundle(tree, source_lines=self.source_lines, optimize=True)
        self.ir_module = ir_module
        self.temp_counter = 0
        self.active_class: Optional[str] = None
        self.declared_vars_stack: list[set[str]] = [set()]

    def _new_temp(self, prefix: str = "_tmp") -> str:
        self.temp_counter += 1
        return f"{prefix}{self.temp_counter}"

    def generate(self) -> str:
        lines: list[str] = [
            "#include <iostream>",
            "#include <string>",
            "#include <vector>",
            "#include <tuple>",
            "#include <unordered_map>",
            "#include <unordered_set>",
            "#include <algorithm>",
            "#include <numeric>",
            "#include <cmath>",
            "#include <cctype>",
            "#include <sstream>",
            "#include <stdexcept>",
            "#include <functional>",
            "#include <type_traits>",
            "",
            CPP_RUNTIME_HELPERS.strip(),
            "",
            "using py_rt::operator<<;",
            "",
        ]

        # 1. Class definitions (must precede global variables that use class types)
        for cls in self.ir_module.classes:
            lines.extend(self._emit_class(cls))
            lines.append("")

        # 2. Global variable declarations (skip generic lambda variables; they are declared with 'auto')
        if self.ir_module.global_vars:
            lines.append("// Global Variables")
            for vname, vtype in self.ir_module.global_vars:
                if vtype.base == "std::function":
                    continue
                lines.append(f"{vtype.to_cpp()} {vname};")
                self.declared_vars_stack[0].add(vname)
            lines.append("")

        # 3. Function prototypes (forward declarations for mutual/self recursion)
        if self.ir_module.functions:
            lines.append("// Function Prototypes")
            for fn in self.ir_module.functions:
                lines.append(self._emit_function_signature(fn, include_defaults=True) + ";")
            lines.append("")

        # 4. Function definitions
        for fn in self.ir_module.functions:
            lines.extend(self._emit_function(fn))
            lines.append("")

        # 5. Main entry point
        lines.append("int main() {")
        lines.append("    std::cout << std::boolalpha;")
        for stmt in self.ir_module.main_body:
            lines.extend(self._emit_stmt(stmt, indent="    "))
        lines.append("    return 0;")
        lines.append("}")

        return "\n".join(lines)

    # ============================================================
    # Classes & Functions
    # ============================================================

    def _emit_class(self, cls: IRClass) -> list[str]:
        base_clause = ""
        if cls.bases:
            base_clause = " : " + ", ".join(f"public {b}" for b in cls.bases)

        out = [f"class {cls.name}{base_clause} {{", "public:"]
        for fname, ftype in cls.fields:
            out.append(f"    {ftype.to_cpp()} {fname};")
        for aname, atype, aval in cls.class_attrs:
            out.append(f"    static inline {atype.to_cpp()} {aname} = {self._emit_expr(aval)};")
        if cls.fields or cls.class_attrs:
            out.append("")

        has_zero_arg_ctor = any(
            m.is_constructor and len(m.params) == 0 for m in cls.methods
        )
        if not has_zero_arg_ctor:
            out.append(f"    {cls.name}() = default;")
            out.append("")

        self.active_class = cls.name
        for method in cls.methods:
            out.extend(self._emit_function(method, indent="    ", class_name=cls.name))
            out.append("")
        self.active_class = None

        out.append("};")
        return out

    def _emit_function_signature(
        self,
        fn: IRFunction,
        include_defaults: bool = False,
        class_name: Optional[str] = None,
    ) -> str:
        params_str_list: list[str] = []
        for pname, ptype, default_expr in fn.params:
            p_decl = f"{ptype.to_cpp()} {pname}"
            if include_defaults and default_expr is not None:
                p_decl += f" = {self._emit_expr(default_expr)}"
            params_str_list.append(p_decl)
        params_str = ", ".join(params_str_list)

        if fn.is_constructor and class_name:
            return f"{class_name}({params_str})"

        prefix = "virtual " if (fn.is_virtual and not fn.is_override) else ""
        suffix = " override" if fn.is_override else ""
        return f"{prefix}{fn.return_type.to_cpp()} {fn.name}({params_str}){suffix}"

    def _emit_function(
        self,
        fn: IRFunction,
        indent: str = "",
        class_name: Optional[str] = None,
    ) -> list[str]:
        sig = self._emit_function_signature(fn, include_defaults=fn.is_method, class_name=class_name)
        out = [f"{indent}{sig} {{"]

        declared = {p[0] for p in fn.params} | {"self"}
        for vname, vtype in fn.local_vars:
            if vtype.base == "std::function":
                continue
            out.append(f"{indent}    {vtype.to_cpp()} {vname};")
            declared.add(vname)
        if fn.local_vars:
            out.append("")

        self.declared_vars_stack.append(declared)
        for stmt in fn.body:
            out.extend(self._emit_stmt(stmt, indent=indent + "    "))
        self.declared_vars_stack.pop()

        out.append(f"{indent}}}")
        return out

    # ============================================================
    # Statements
    # ============================================================

    def _emit_stmt(self, stmt: IRStmt, indent: str) -> list[str]:
        if isinstance(stmt, IRPass):
            return [f"{indent}// pass"]

        if isinstance(stmt, IRBreak):
            return [f"{indent}break;"]

        if isinstance(stmt, IRContinue):
            return [f"{indent}continue;"]

        if isinstance(stmt, IRReturn):
            if stmt.value is None:
                return [f"{indent}return;"]
            return [f"{indent}return {self._emit_expr(stmt.value)};"]

        if isinstance(stmt, IRExprStmt):
            return [f"{indent}{self._emit_expr(stmt.expr)};"]

        if isinstance(stmt, IRPrint):
            if not stmt.args:
                return [f"{indent}std::cout << {json.dumps(stmt.end)};"]
            parts: list[str] = []
            for idx, arg in enumerate(stmt.args):
                if idx > 0 and stmt.sep:
                    parts.append(json.dumps(stmt.sep))
                if arg.cpp_type in (DOUBLE_TYPE, BOOL_TYPE):
                    parts.append(f"py_rt::to_py_str({self._emit_expr(arg)})")
                else:
                    parts.append(self._emit_expr(arg))
            parts.append(json.dumps(stmt.end))
            return [f"{indent}std::cout << {' << '.join(parts)};"]

        if isinstance(stmt, IRAssign):
            rhs = self._emit_expr(stmt.value)
            if isinstance(stmt.target, list):
                tmp = self._new_temp("_unpack")
                out = [f"{indent}auto {tmp} = {rhs};"]
                for idx, name in enumerate(stmt.target):
                    out.append(f"{indent}{name} = std::get<{idx}>({tmp});")
                return out
            if isinstance(stmt.target, IRExpr):
                lhs = self._emit_expr(stmt.target)
                return [f"{indent}{lhs} = {rhs};"]
            if isinstance(stmt.value, IRLambda) and stmt.target not in self.declared_vars_stack[-1]:
                self.declared_vars_stack[-1].add(stmt.target)
                return [f"{indent}auto {stmt.target} = {rhs};"]
            return [f"{indent}{stmt.target} = {rhs};"]

        if isinstance(stmt, IRAugAssign):
            lhs = self._emit_expr(stmt.target) if isinstance(stmt.target, IRExpr) else str(stmt.target)
            rhs = self._emit_expr(stmt.value)
            if stmt.op == "//":
                return [f"{indent}{lhs} = py_rt::py_floordiv({lhs}, {rhs});"]
            if stmt.op == "%":
                return [f"{indent}{lhs} = py_rt::py_mod({lhs}, {rhs});"]
            if stmt.op == "**":
                return [f"{indent}{lhs} = std::pow({lhs}, {rhs});"]
            return [f"{indent}{lhs} {stmt.op}= {rhs};"]

        if isinstance(stmt, IRIf):
            cond = self._emit_cond(stmt.test)
            out = [f"{indent}if ({cond}) {{"]
            for s in stmt.body:
                out.extend(self._emit_stmt(s, indent + "    "))
            if stmt.orelse:
                if len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], IRIf):
                    elif_lines = self._emit_stmt(stmt.orelse[0], indent)
                    elif_lines[0] = f"{indent}}} else {elif_lines[0].lstrip()}"
                    out.extend(elif_lines)
                    return out
                out.append(f"{indent}}} else {{")
                for s in stmt.orelse:
                    out.extend(self._emit_stmt(s, indent + "    "))
            out.append(f"{indent}}}")
            return out

        if isinstance(stmt, IRWhile):
            cond = self._emit_cond(stmt.test)
            out = [f"{indent}while ({cond}) {{"]
            for s in stmt.body:
                out.extend(self._emit_stmt(s, indent + "    "))
            out.append(f"{indent}}}")
            return out

        if isinstance(stmt, IRForRangeBlock):
            start = self._emit_expr(stmt.start)
            stop = self._emit_expr(stmt.stop)
            step = self._emit_expr(stmt.step)
            var = stmt.var_name

            if isinstance(stmt.step, IRConst) and isinstance(stmt.step.value, int):
                if stmt.step.value > 0:
                    cond = f"{var} < {stop}"
                    inc = f"++{var}" if stmt.step.value == 1 else f"{var} += {stmt.step.value}"
                elif stmt.step.value < 0:
                    cond = f"{var} > {stop}"
                    inc = f"--{var}" if stmt.step.value == -1 else f"{var} += {stmt.step.value}"
                else:
                    raise TranspilerError(
                        line=stmt.line,
                        feature="range() Step",
                        expression="range(..., 0)",
                        reason="range() step argument must not be zero.",
                        suggestion="Provide a non-zero integer step.",
                    )
            else:
                step_tmp = self._new_temp("_step")
                out = [
                    f"{indent}{{",
                    f"{indent}    int {step_tmp} = {step};",
                    f"{indent}    if ({step_tmp} == 0) throw std::invalid_argument(\"ValueError: range() arg 3 must not be zero\");",
                    f"{indent}    for (int {var} = {start}; ({step_tmp} > 0) ? ({var} < {stop}) : ({var} > {stop}); {var} += {step_tmp}) {{",
                ]
                for s in stmt.body:
                    out.extend(self._emit_stmt(s, indent + "        "))
                out.append(f"{indent}    }}")
                out.append(f"{indent}}}")
                return out

            out = [f"{indent}for (int {var} = {start}; {cond}; {inc}) {{"]
            for s in stmt.body:
                out.extend(self._emit_stmt(s, indent + "    "))
            out.append(f"{indent}}}")
            return out

        if isinstance(stmt, IRForEach):
            it_expr = self._emit_expr(stmt.iterable)
            if len(stmt.targets) == 1:
                t = stmt.targets[0]
                if stmt.iterable.cpp_type == STR_TYPE:
                    tmp_c = self._new_temp("_ch")
                    out = [
                        f"{indent}for (char {tmp_c} : {it_expr}) {{",
                        f"{indent}    {t} = std::string(1, {tmp_c});",
                    ]
                else:
                    tmp_el = self._new_temp("_item")
                    out = [
                        f"{indent}for (const auto& {tmp_el} : {it_expr}) {{",
                        f"{indent}    {t} = {tmp_el};",
                    ]
            else:
                bindings = ", ".join(f"_b_{t}" for t in stmt.targets)
                out = [f"{indent}for (const auto& [{bindings}] : {it_expr}) {{"]
                for t in stmt.targets:
                    out.append(f"{indent}    {t} = _b_{t};")

            for s in stmt.body:
                out.extend(self._emit_stmt(s, indent + "    "))
            out.append(f"{indent}}}")
            return out

        if isinstance(stmt, IRTry):
            out = [f"{indent}try {{"]
            for s in stmt.body:
                out.extend(self._emit_stmt(s, indent + "    "))
            for s in stmt.orelse:
                out.extend(self._emit_stmt(s, indent + "    "))

            if stmt.handlers:
                for idx, h in enumerate(stmt.handlers):
                    cpp_exc = self._map_exception_type(h.exc_type)
                    catch_var = f"_exc_{idx}"
                    out.append(f"{indent}}} catch (const {cpp_exc}& {catch_var}) {{")
                    if h.var_name:
                        out.append(f"{indent}    {h.var_name} = std::string({catch_var}.what());")
                    for s in h.body:
                        out.extend(self._emit_stmt(s, indent + "    "))
            else:
                out.append(f"{indent}}} catch (const std::exception&) {{")
            out.append(f"{indent}}}")

            if stmt.finalbody:
                out.append(f"{indent}// finally block")
                for s in stmt.finalbody:
                    out.extend(self._emit_stmt(s, indent))
            return out

        if isinstance(stmt, IRRaise):
            cpp_exc = self._map_exception_type(stmt.exc_type)
            msg = self._emit_expr(stmt.message) if stmt.message else json.dumps(stmt.exc_type)
            return [f"{indent}throw {cpp_exc}({msg});"]

        return []

    def _map_exception_type(self, py_exc: Optional[str]) -> str:
        mapping = {
            "ValueError": "std::invalid_argument",
            "TypeError": "std::invalid_argument",
            "IndexError": "std::out_of_range",
            "KeyError": "std::out_of_range",
            "ZeroDivisionError": "std::runtime_error",
            "RuntimeError": "std::runtime_error",
            "Exception": "std::exception",
            "BaseException": "std::exception",
        }
        return mapping.get(py_exc or "Exception", "std::exception")

    # ============================================================
    # Expressions
    # ============================================================

    def _emit_cond(self, expr: IRExpr) -> str:
        code = self._emit_expr(expr)
        if expr.cpp_type == STR_TYPE:
            return f"!({code}).empty()"
        if expr.cpp_type.base in ("std::vector", "std::unordered_map", "std::unordered_set"):
            return f"!({code}).empty()"
        return code

    def _emit_expr(self, expr: IRExpr) -> str:
        if isinstance(expr, IRConst):
            if isinstance(expr.value, bool):
                return "true" if expr.value else "false"
            if isinstance(expr.value, str):
                return f"std::string({json.dumps(expr.value, ensure_ascii=False)})"
            if expr.value is None:
                return "nullptr"
            return repr(expr.value)

        if isinstance(expr, IRVar):
            if expr.name == "self" and self.active_class:
                return "(*this)"
            return expr.name

        if isinstance(expr, IRAttribute):
            if isinstance(expr.obj, IRVar) and expr.obj.name == "self" and self.active_class:
                return f"this->{expr.attr}"
            if isinstance(expr.obj, IRVar) and expr.obj.name == "math":
                math_consts = {"pi": "M_PI", "e": "M_E", "tau": "(2.0 * M_PI)", "inf": "INFINITY", "nan": "NAN"}
                if expr.attr in math_consts:
                    return math_consts[expr.attr]
            return f"{self._emit_expr(expr.obj)}.{expr.attr}"

        if isinstance(expr, IRFString):
            if not expr.parts:
                return 'std::string("")'
            pieces = [f"py_rt::to_py_str({self._emit_expr(p)})" for p in expr.parts]
            return "(" + " + ".join(pieces) + ")"

        if isinstance(expr, IRUnaryOp):
            operand = self._emit_expr(expr.operand)
            if expr.op == "not":
                return f"(!({self._emit_cond(expr.operand)}))"
            return f"({expr.op}{operand})"

        if isinstance(expr, IRBinOp):
            left = self._emit_expr(expr.left)
            right = self._emit_expr(expr.right)

            if expr.op == "*":
                if expr.left.cpp_type == STR_TYPE and expr.right.cpp_type == INT_TYPE:
                    return f"py_rt::str_repeat({left}, {right})"
                if expr.left.cpp_type == INT_TYPE and expr.right.cpp_type == STR_TYPE:
                    return f"py_rt::str_repeat({right}, {left})"

            if expr.op == "**":
                if expr.cpp_type == INT_TYPE:
                    return f"static_cast<int>(std::llround(std::pow({left}, {right})))"
                return f"std::pow(static_cast<double>({left}), static_cast<double>({right}))"

            if expr.op == "//":
                return f"py_rt::py_floordiv({left}, {right})"

            if expr.op == "%":
                return f"py_rt::py_mod({left}, {right})"

            if expr.op == "/":
                return f"(static_cast<double>({left}) / ({right}))"

            return f"({left} {expr.op} {right})"

        if isinstance(expr, IRBoolOp):
            cpp_op = "&&" if expr.op == "and" else "||"
            parts = [f"({self._emit_cond(v)})" for v in expr.values]
            return "(" + f" {cpp_op} ".join(parts) + ")"

        if isinstance(expr, IRCompare):
            cur_expr = expr.left
            cur_code = self._emit_expr(cur_expr)
            clauses: list[str] = []

            for op, comp in zip(expr.ops, expr.comparators):
                comp_code = self._emit_expr(comp)
                if op == "in":
                    clauses.append(f"py_rt::py_in({cur_code}, {comp_code})")
                elif op == "not in":
                    clauses.append(f"(!py_rt::py_in({cur_code}, {comp_code}))")
                elif op == "is":
                    clauses.append(f"({cur_code} == {comp_code})")
                elif op == "is not":
                    clauses.append(f"({cur_code} != {comp_code})")
                else:
                    clauses.append(f"({cur_code} {op} {comp_code})")
                cur_expr = comp
                cur_code = comp_code

            return " && ".join(clauses) if len(clauses) > 1 else clauses[0]

        if isinstance(expr, IRTernary):
            return f"(({self._emit_cond(expr.test)}) ? ({self._emit_expr(expr.body)}) : ({self._emit_expr(expr.orelse)}))"

        if isinstance(expr, IRCollection):
            elems = ", ".join(self._emit_expr(e) for e in expr.elements)
            if expr.kind == "tuple":
                return f"std::make_tuple({elems})"
            return f"{expr.cpp_type.to_cpp()}{{{elems}}}"

        if isinstance(expr, IRDict):
            pairs = ", ".join(
                f"{{{self._emit_expr(k)}, {self._emit_expr(v)}}}"
                for k, v in zip(expr.keys, expr.values)
            )
            return f"{expr.cpp_type.to_cpp()}{{{pairs}}}"

        if isinstance(expr, IRIndex):
            obj = self._emit_expr(expr.obj)
            idx = self._emit_expr(expr.index)
            if expr.obj.cpp_type.base == "std::unordered_map":
                return f"{obj}[{idx}]"
            if expr.obj.cpp_type.base == "std::tuple" and isinstance(expr.index, IRConst) and isinstance(expr.index.value, int):
                return f"std::get<{expr.index.value}>({obj})"
            return f"py_rt::py_index({obj}, {idx})"

        if isinstance(expr, IRSlice):
            obj = self._emit_expr(expr.obj)
            has_start = "true" if expr.lower is not None else "false"
            has_stop = "true" if expr.upper is not None else "false"
            start = self._emit_expr(expr.lower) if expr.lower is not None else "0"
            stop = self._emit_expr(expr.upper) if expr.upper is not None else "0"
            step = self._emit_expr(expr.step) if expr.step is not None else "1"
            return f"py_rt::py_slice({obj}, {start}, {stop}, {step}, {has_start}, {has_stop})"

        if isinstance(expr, IRLambda):
            params = ", ".join(f"auto {p}" for p, _ in expr.params)
            body = self._emit_expr(expr.body)
            return f"[&]({params}) {{ return {body}; }}"

        if isinstance(expr, IRListComp):
            vec_type = expr.cpp_type.to_cpp()
            it = self._emit_expr(expr.iter_expr)
            elt = self._emit_expr(expr.elt)
            conds = " && ".join(f"({self._emit_cond(c)})" for c in expr.ifs)
            push = f"if ({conds}) _res.push_back({elt});" if conds else f"_res.push_back({elt});"
            return (
                f"[&]() {{ {vec_type} _res; "
                f"for (const auto& {expr.target} : {it}) {{ {push} }} "
                f"return _res; }}()"
            )

        if isinstance(expr, IRDictComp):
            map_type = expr.cpp_type.to_cpp()
            it = self._emit_expr(expr.iter_expr)
            k = self._emit_expr(expr.key)
            v = self._emit_expr(expr.value)
            conds = " && ".join(f"({self._emit_cond(c)})" for c in expr.ifs)
            ins = f"if ({conds}) _res[{k}] = {v};" if conds else f"_res[{k}] = {v};"
            return (
                f"[&]() {{ {map_type} _res; "
                f"for (const auto& {expr.target} : {it}) {{ {ins} }} "
                f"return _res; }}()"
            )

        if isinstance(expr, IRCall):
            return self._emit_call(expr)

        if isinstance(expr, IRMethodCall):
            return self._emit_method_call(expr)

        return "0"

    def _emit_call(self, expr: IRCall) -> str:
        fn = expr.func_name
        args = [self._emit_expr(a) for a in expr.args]

        if fn == "input":
            prompt = args[0] if args else '""'
            return f"py_rt::py_input({prompt})"

        if fn == "int":
            if not args:
                return "0"
            if expr.args[0].cpp_type == STR_TYPE:
                base = f", {args[1]}" if len(args) > 1 else ""
                return f"std::stoi({args[0]}{base})"
            return f"static_cast<int>({args[0]})"

        if fn == "float":
            if not args:
                return "0.0"
            if expr.args[0].cpp_type == STR_TYPE:
                return f"std::stod({args[0]})"
            return f"static_cast<double>({args[0]})"

        if fn == "str":
            if not args:
                return 'std::string("")'
            return f"py_rt::to_py_str({args[0]})"

        if fn == "bool":
            if not args:
                return "false"
            return f"static_cast<bool>({self._emit_cond(expr.args[0])})"

        if fn == "len":
            return f"static_cast<int>(({args[0]}).size())"

        if fn == "abs":
            return f"std::abs({args[0]})"

        if fn == "max":
            if len(args) == 1:
                return f"(*std::max_element(({args[0]}).begin(), ({args[0]}).end()))"
            return f"std::max({{{', '.join(args)}}})"

        if fn == "min":
            if len(args) == 1:
                return f"(*std::min_element(({args[0]}).begin(), ({args[0]}).end()))"
            return f"std::min({{{', '.join(args)}}})"

        if fn == "sum":
            return f"py_rt::py_sum({args[0]})"

        if fn == "round":
            if len(args) == 1:
                return f"static_cast<int>(std::llround({args[0]}))"
            factor = f"std::pow(10.0, {args[1]})"
            return f"(std::round(({args[0]}) * {factor}) / {factor})"

        if fn == "sorted":
            rev = "true" if ("reverse" in expr.kwargs and isinstance(expr.kwargs["reverse"], IRConst) and expr.kwargs["reverse"].value) else "false"
            return f"py_rt::py_sorted({args[0]}, {rev})"

        if fn == "reversed":
            return f"py_rt::py_reversed({args[0]})"

        if fn == "enumerate":
            start = args[1] if len(args) > 1 else "0"
            return f"py_rt::py_enumerate({args[0]}, {start})"

        if fn == "zip":
            return f"py_rt::py_zip({args[0]}, {args[1]})"

        if fn == "type":
            t_name = expr.args[0].cpp_type.to_cpp() if expr.args else "void"
            return f"std::string(\"<class '{t_name}'>\")"

        if fn == "isinstance":
            if len(expr.args) >= 2 and isinstance(expr.args[1], IRVar):
                target_name = expr.args[1].name
                py_to_cpp = {"int": "int", "float": "double", "str": "std::string", "bool": "bool", "list": "std::vector"}
                expected = py_to_cpp.get(target_name, target_name)
                actual = expr.args[0].cpp_type.base
                return "true" if actual == expected else "false"
            return "false"

        if fn == "list":
            if not args:
                return "std::vector<int>{}"
            if expr.args[0].cpp_type.base == "std::vector":
                return args[0]
            return f"[&]() {{ auto _seq = {args[0]}; return std::vector(_seq.begin(), _seq.end()); }}()"

        if fn == "set":
            if not args:
                return "std::unordered_set<int>{}"
            return f"[&]() {{ auto _seq = {args[0]}; return std::unordered_set(_seq.begin(), _seq.end()); }}()"

        return f"{fn}({', '.join(args)})"

    def _emit_method_call(self, expr: IRMethodCall) -> str:
        obj_code = self._emit_expr(expr.obj)
        args = [self._emit_expr(a) for a in expr.args]
        m = expr.method

        if isinstance(expr.obj, IRVar) and expr.obj.name == "math":
            if m == "factorial":
                return f"static_cast<int>(std::tgamma(({args[0]}) + 1))"
            if m == "gcd":
                return f"std::gcd({args[0]}, {args[1]})"
            if m in ("floor", "ceil"):
                return f"static_cast<int>(std::{m}({args[0]}))"
            return f"std::{m}({', '.join(args)})"

        if expr.obj.cpp_type == STR_TYPE:
            if m == "upper":
                return f"py_rt::str_upper({obj_code})"
            if m == "lower":
                return f"py_rt::str_lower({obj_code})"
            if m == "strip":
                return f"py_rt::str_strip({obj_code})"
            if m == "replace":
                return f"py_rt::str_replace({obj_code}, {args[0]}, {args[1]})"
            if m == "split":
                sep = args[0] if args else '""'
                return f"py_rt::str_split({obj_code}, {sep})"
            if m == "join":
                return f"py_rt::str_join({obj_code}, {args[0]})"
            if m == "find":
                return f"static_cast<int>(({obj_code}).find({args[0]}))"
            if m == "startswith":
                return f"(({obj_code}).rfind({args[0]}, 0) == 0)"
            if m == "endswith":
                return f"(({obj_code}).size() >= ({args[0]}).size() && ({obj_code}).compare(({obj_code}).size() - ({args[0]}).size(), ({args[0]}).size(), {args[0]}) == 0)"

        if expr.obj.cpp_type.base == "std::vector":
            if m == "append":
                return f"{obj_code}.push_back({args[0]})"
            if m == "pop":
                if not args:
                    return f"[&]() {{ auto _v = {obj_code}.back(); {obj_code}.pop_back(); return _v; }}()"
                return f"[&]() {{ auto _v = {obj_code}[{args[0]}]; {obj_code}.erase({obj_code}.begin() + {args[0]}); return _v; }}()"
            if m == "insert":
                return f"{obj_code}.insert({obj_code}.begin() + {args[0]}, {args[1]})"
            if m == "clear":
                return f"{obj_code}.clear()"
            if m == "sort":
                return f"std::sort({obj_code}.begin(), {obj_code}.end())"
            if m == "reverse":
                return f"std::reverse({obj_code}.begin(), {obj_code}.end())"
            if m == "count":
                return f"static_cast<int>(std::count({obj_code}.begin(), {obj_code}.end(), {args[0]}))"

        if expr.obj.cpp_type.base == "std::unordered_set":
            if m == "add":
                return f"{obj_code}.insert({args[0]})"
            if m == "remove":
                return f"{obj_code}.erase({args[0]})"
            if m == "clear":
                return f"{obj_code}.clear()"

        if expr.obj.cpp_type.base == "std::unordered_map":
            if m == "get":
                default = args[1] if len(args) > 1 else "{}"
                return f"(({obj_code}).count({args[0]}) ? ({obj_code}).at({args[0]}) : {default})"
            if m == "clear":
                return f"{obj_code}.clear()"

        if isinstance(expr.obj, IRVar) and expr.obj.name == "self" and self.active_class:
            return f"this->{m}({', '.join(args)})"

        return f"{obj_code}.{m}({', '.join(args)})"


def generate_cpp(
    tree: ast.Module,
    intermediate_code: Optional[str] = None,
    ir_module: Optional[IRModule] = None,
    source_lines: Optional[list[str]] = None,
) -> str:
    generator = CppCodeGenerator(tree, ir_module=ir_module, source_lines=source_lines)
    return generator.generate()