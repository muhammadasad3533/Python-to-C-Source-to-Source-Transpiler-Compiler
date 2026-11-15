# Py2Cpp — Python-to-C++17 Source-to-Source Transpiler

**Design and Development of a Python-to-C++ Source-to-Source Transpiler with Abstract Syntax Tree (AST) and Intermediate Code Generation.**

Py2Cpp automatically parses Python 3 programs into an Abstract Syntax Tree, performs scope-aware static type inference, lowers the program into a typed Intermediate Representation (IR) with optional compile-time optimizations, emits readable C++17 source code, and compiles/executes the binary via `g++`.

---

## System Architecture & Compiler Pipeline

```text
Python 3 Source Code
        │
        ▼
┌────────────────────────────┐
│  AST Generator & Analyzer  │  (transpiler/ast_generator.py, ast_analyzer.py)
└────────────────────────────┘
        │
        ▼
┌────────────────────────────┐
│ Symbol Table & Type Engine │  (transpiler/symbol_table.py, type_inference.py)
└────────────────────────────┘
        │
        ▼
┌────────────────────────────┐
│ Typed IR & IR Optimizer    │  (transpiler/intermediate_code.py)
└────────────────────────────┘
        │
        ▼
┌────────────────────────────┐
│   C++17 Code Generator     │  (transpiler/code_generator.py)
└────────────────────────────┘
        │
        ▼
┌────────────────────────────┐
│  G++ Compiler & Sandbox    │  (transpiler/cpp_runner.py)
└────────────────────────────┘
        │
        ▼
   Executable Output