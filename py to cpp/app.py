from flask import Flask, jsonify, render_template, request
from transpiler.ast_analyzer import analyze_ast
from transpiler.ast_generator import generate_ast
from transpiler.code_generator import generate_cpp
from transpiler.cpp_runner import compile_cpp_source, run_compiled_binary
from transpiler.errors import TranspilerError
from transpiler.intermediate_code import build_ir_bundle

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/convert", methods=["POST"])
def convert():
    data = request.get_json(silent=True) or {}
    source_code = data.get("code", "")
    optimize = bool(data.get("optimize", True))

    ast_result = generate_ast(source_code)
    if not ast_result.get("success"):
        return jsonify({
            "success": False,
            "error": ast_result.get("error", "Syntax Error"),
            "diagnostic": ast_result.get("diagnostic"),
        }), 400

    tree = ast_result["tree"]
    source_lines = ast_result.get("source_lines", [])

    try:
        analysis = analyze_ast(tree, source_lines=source_lines)
        ir_module, ir_text = build_ir_bundle(
            tree,
            source_lines=source_lines,
            optimize=optimize,
        )
        cpp_code = generate_cpp(
            tree,
            intermediate_code=ir_text,
            ir_module=ir_module,
            source_lines=source_lines,
        )

        return jsonify({
            "success": True,
            "ast": ast_result["ast"],
            "ast_tree": ast_result.get("ast_tree"),
            "analysis": analysis,
            "intermediate_code": ir_text,
            "cpp": cpp_code,
            "message": "Transpiled to C++17 successfully!",
        })

    except TranspilerError as err:
        return jsonify({
            "success": False,
            "error": err.diagnostic.format(),
            "diagnostic": err.diagnostic.to_dict(),
        }), 400

    except Exception as exc:
        return jsonify({
            "success": False,
            "error": f"Unexpected Compiler Error: {exc}",
        }), 500


@app.route("/compile", methods=["POST"])
def compile_cpp():
    data = request.get_json(silent=True) or {}
    cpp_code = data.get("cpp_code", "")
    standard = data.get("standard", "c++17")
    if standard not in ("c++17", "c++20"):
        standard = "c++17"

    result = compile_cpp_source(cpp_code, standard=standard)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@app.route("/run", methods=["POST"])
def run_cpp():
    data = request.get_json(silent=True) or {}
    stdin_data = data.get("stdin", "")
    cpp_code = data.get("cpp_code")

    # Optionally re-compile if C++ editor content was provided
    if cpp_code is not None and cpp_code.strip():
        comp = compile_cpp_source(cpp_code)
        if not comp.get("success"):
            return jsonify({
                "success": False,
                "error": comp.get("error", "Compilation failed."),
                "stdout": "",
                "stderr": comp.get("compiler_output", ""),
            }), 400

    result = run_compiled_binary(stdin_data=stdin_data)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


if __name__ == "__main__":
    app.run(debug=True)