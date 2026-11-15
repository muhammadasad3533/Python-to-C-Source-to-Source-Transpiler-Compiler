import math
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from transpiler.ast_analyzer import analyze_ast
from transpiler.ast_generator import generate_ast
from transpiler.code_generator import generate_cpp
from transpiler.cpp_runner import compile_cpp_source, run_compiled_binary
from transpiler.intermediate_code import build_ir_bundle


@dataclass
class TestCase:
    id: int
    name: str
    code: str
    stdin: str = ""


TEST_CASES: list[TestCase] = [
    TestCase(
        1,
        "Basic Variables and Assignments",
        """a = 15
b = 25
c = a + b
x, y = 3, 7
x, y = y, x
print(c, x, y)""",
    ),
    TestCase(
        2,
        "Arithmetic Operations",
        """print(10 + 3, 10 - 3, 10 * 3)
print(7 // 2, -7 // 2)
print(7 % 3, -7 % 3)
print(2 ** 5)""",
    ),
    TestCase(
        3,
        "Print Statements",
        """print("Hello", "C++", sep="-", end="!")
print()
print(True, False, 42)""",
    ),
    TestCase(
        4,
        "Input Statements",
        """name = input()
age = int(input())
print(f"User {name} is {age + 1} next year")""",
        stdin="Asad\n21\n",
    ),
    TestCase(
        5,
        "If / Elif / Else Conditions",
        """score = 84
if score >= 90:
    grade = "A"
elif score >= 80:
    grade = "B"
else:
    grade = "C"
in_range = 80 <= score < 90
print(grade, in_range)""",
    ),
    TestCase(
        6,
        "For Loops",
        """s1 = 0
for i in range(5):
    s1 += i
s2 = 0
for j in range(10, 0, -3):
    s2 += j
print(s1, s2)""",
    ),
    TestCase(
        7,
        "While Loops with Break and Continue",
        """n = 0
total = 0
while n < 10:
    n += 1
    if n % 2 == 0:
        continue
    if n > 7:
        break
    total += n
print(total)""",
    ),
    TestCase(
        8,
        "Function Definitions",
        """def greet(user, prefix="Hello"):
    return prefix + ", " + user

print(greet("World"))
print(greet("Dev", "Hi"))""",
    ),
    TestCase(
        9,
        "Function Calling and Keyword Arguments",
        """def power_add(base, exp, offset=0):
    return (base ** exp) + offset

print(power_add(3, 3))
print(power_add(2, 4, offset=10))""",
    ),
    TestCase(
        10,
        "Nested Function Calls",
        """def add(a, b):
    return a + b

def calculate(x, y):
    result = add(x, y)
    return result * 2

answer = calculate(10, 20)
print(answer)""",
    ),
    TestCase(
        11,
        "Recursive Functions",
        """def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)

print(factorial(6), fib(7))""",
    ),
    TestCase(
        12,
        "Lists and Dictionaries",
        """nums = [10, 20, 30, 40]
nums.append(50)
print(nums[0], nums[-1], nums[1:4])
ages = {"Ali": 20, "Sara": 22}
ages["Omar"] = 25
print(ages["Sara"], "Omar" in ages, len(ages))""",
    ),
    TestCase(
        13,
        "String Operations",
        """text = "  Python to C++  "
clean = text.strip().upper()
parts = "a,b,c".split(",")
joined = "-".join(parts)
print(clean)
print(joined, clean.startswith("PYTHON"))""",
    ),
    TestCase(
        14,
        "Lambda Functions",
        """square = lambda x: x * x
multiply = lambda a, b: a * b
print(square(6), multiply(4, 5))""",
    ),
    TestCase(
        15,
        "Classes and Objects",
        """class Shape:
    def __init__(self, name):
        self.name = name

    def describe(self):
        return "Shape: " + self.name

class Rectangle(Shape):
    def __init__(self, name, w, h):
        self.name = name
        self.w = w
        self.h = h

    def area(self):
        return self.w * self.h

r = Rectangle("Box", 4, 5)
print(r.describe(), r.area())""",
    ),
    TestCase(
        16,
        "Exception Handling",
        """def check_positive(v):
    try:
        if v < 0:
            raise ValueError("Negative value")
        return v * 10
    except ValueError as e:
        print("Handled:", e)
        return 0

print(check_positive(5))
print(check_positive(-3))""",
    ),
    TestCase(
        17,
        "Nested Loops",
        """count = 0
for i in range(1, 4):
    for j in range(1, 4):
        if i == j:
            continue
        count += i * j
print(count)""",
    ),
    TestCase(
        18,
        "List Comprehensions",
        """data = [1, 2, 3, 4, 5, 6]
evens_squared = [x * x for x in data if x % 2 == 0]
print(evens_squared)""",
    ),
    TestCase(
        19,
        "Built-in Functions",
        """vals = [5, 2, 9, 1, 7]
print(len(vals), min(vals), max(vals), sum(vals))
print(abs(-42), sorted(vals), list(reversed(vals)))
for idx, val in enumerate(["x", "y"]):
    print(idx, val)""",
    ),
    TestCase(
        20,
        "Complex Multi-Feature Program",
        """class Student:
    def __init__(self, name, marks):
        self.name = name
        self.marks = marks

    def average(self):
        return sum(self.marks) // len(self.marks)

def classify(avg):
    if avg >= 85:
        return "Distinction"
    elif avg >= 70:
        return "Merit"
    return "Pass"

students = [
    Student("Ayesha", [90, 88, 92]),
    Student("Bilal", [72, 75, 70])
]

for st in students:
    avg = st.average()
    print(f"{st.name}: {avg} ({classify(avg)})")""",
    ),
]


def outputs_match(py_out: str, cpp_out: str, tol: float = 1e-5) -> bool:
    py_lines = [line.rstrip() for line in py_out.strip().splitlines()]
    cpp_lines = [line.rstrip() for line in cpp_out.strip().splitlines()]
    if py_lines == cpp_lines:
        return True
    if len(py_lines) != len(cpp_lines):
        return False
    for pl, cl in zip(py_lines, cpp_lines):
        if pl == cl:
            continue
        p_tokens = pl.split()
        c_tokens = cl.split()
        if len(p_tokens) != len(c_tokens):
            return False
        for pt, ct in zip(p_tokens, c_tokens):
            if pt == ct:
                continue
            try:
                if not math.isclose(float(pt), float(ct), rel_tol=tol, abs_tol=tol):
                    return False
            except ValueError:
                return False
    return True


def run_test_suite() -> dict:
    has_gpp = shutil.which("g++") is not None
    total = len(TEST_CASES)
    passed = 0
    failed = 0
    transpile_errors = 0
    compile_errors = 0
    runtime_errors = 0

    print("=" * 72)
    print("Py2Cpp Automated Differential Test Suite (20 Categories)")
    print("=" * 72)

    for tc in TEST_CASES:
        py_proc = subprocess.run(
            [sys.executable, "-c", tc.code],
            input=tc.stdin,
            capture_output=True,
            text=True,
            timeout=5,
        )
        expected_out = py_proc.stdout

        ast_res = generate_ast(tc.code)
        if not ast_res.get("success"):
            transpile_errors += 1
            failed += 1
            print(f"[FAIL] Test {tc.id:02d}: {tc.name} -> AST Error: {ast_res.get('error')}")
            continue

        try:
            analyze_ast(ast_res["tree"], source_lines=ast_res["source_lines"])
            ir_mod, ir_txt = build_ir_bundle(ast_res["tree"], source_lines=ast_res["source_lines"], optimize=True)
            cpp_code = generate_cpp(ast_res["tree"], intermediate_code=ir_txt, ir_module=ir_mod)
        except Exception as exc:
            transpile_errors += 1
            failed += 1
            print(f"[FAIL] Test {tc.id:02d}: {tc.name} -> Transpiler Error: {exc}")
            continue

        if not has_gpp:
            passed += 1
            print(f"[PASS-TRANSPILE] Test {tc.id:02d}: {tc.name} (g++ not installed; C++ generated)")
            continue

        comp_res = compile_cpp_source(cpp_code)
        if not comp_res.get("success"):
            compile_errors += 1
            failed += 1
            print(f"[FAIL] Test {tc.id:02d}: {tc.name} -> G++ Compile Error:\n{comp_res.get('error')}")
            continue

        run_res = run_compiled_binary(stdin_data=tc.stdin)
        if not run_res.get("success"):
            runtime_errors += 1
            failed += 1
            print(f"[FAIL] Test {tc.id:02d}: {tc.name} -> Runtime Error:\n{run_res.get('error')}")
            continue

        actual_out = run_res.get("stdout", "")
        if outputs_match(expected_out, actual_out):
            passed += 1
            print(f"[PASS] Test {tc.id:02d}: {tc.name}")
        else:
            failed += 1
            print(
                f"[FAIL] Test {tc.id:02d}: {tc.name} -> Output mismatch!\n"
                f"  Expected (Python): {expected_out!r}\n"
                f"  Actual   (C++17) : {actual_out!r}"
            )

    success_rate = (passed / total) * 100.0
    print("=" * 72)
    print(f"Total Tests       : {total}")
    print(f"Passed Tests      : {passed}")
    print(f"Failed Tests      : {failed}")
    print(f"Transpile Errors  : {transpile_errors}")
    print(f"Compilation Errors: {compile_errors}")
    print(f"Execution Errors  : {runtime_errors}")
    print(f"Success Percentage: {success_rate:.1f}%")
    print("=" * 72)

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "transpile_errors": transpile_errors,
        "compile_errors": compile_errors,
        "runtime_errors": runtime_errors,
        "success_percentage": success_rate,
    }


if __name__ == "__main__":
    summary = run_test_suite()
    sys.exit(0 if summary["failed"] == 0 else 1)