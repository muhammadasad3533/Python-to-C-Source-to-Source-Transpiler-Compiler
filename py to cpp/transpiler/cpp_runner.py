import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any


BUILD_DIR = Path(__file__).resolve().parent.parent / "build_output"
MAX_OUTPUT_CHARS = 65536


def ensure_build_dir() -> Path:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    return BUILD_DIR


def get_binary_path(build_dir: Path) -> Path:
    exe_name = "output.exe" if platform.system() == "Windows" else "output"
    return build_dir / exe_name


def compile_cpp_source(
    cpp_code: str,
    standard: str = "c++17",
    timeout: int = 10,
) -> dict[str, Any]:
    """Save C++ source to output.cpp and compile safely using g++ without shell=True."""
    if not cpp_code or not cpp_code.strip():
        return {
            "success": False,
            "error": "No C++ source code provided to compile.",
            "compiler_output": "",
        }

    gpp_path = shutil.which("g++")
    if gpp_path is None:
        return {
            "success": False,
            "error": (
                "G++ compiler ('g++') was not found in your system PATH.\n"
                "Install MinGW-w64 (Windows), build-essential (Linux), or Xcode Command Line Tools (macOS), "
                "then restart the server."
            ),
            "compiler_output": "",
        }

    build_dir = ensure_build_dir()
    source_path = build_dir / "output.cpp"
    binary_path = get_binary_path(build_dir)

    if binary_path.exists():
        try:
            binary_path.unlink()
        except OSError:
            pass

    source_path.write_text(cpp_code, encoding="utf-8")

    cmd = [
        gpp_path,
        f"-std={standard}",
        "-O2",
        "-Wall",
        "-Wextra",
        str(source_path),
        "-o",
        str(binary_path),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            cwd=str(build_dir),
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Compilation timed out after {timeout} seconds.",
            "compiler_output": "",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": f"Failed to invoke g++: {exc}",
            "compiler_output": "",
        }

    stderr = (proc.stderr or "").strip()
    stdout = (proc.stdout or "").strip()
    combined_output = "\n".join(part for part in (stdout, stderr) if part)

    if proc.returncode != 0 or not binary_path.exists():
        return {
            "success": False,
            "error": f"C++ Compilation Error (exit code {proc.returncode}):\n{combined_output}",
            "compiler_output": combined_output,
        }

    return {
        "success": True,
        "message": f"Compiled successfully with {standard.upper()} ({binary_path.name}).",
        "compiler_output": combined_output or "0 errors, 0 warnings.",
        "source_file": str(source_path),
        "binary_file": str(binary_path),
    }


def run_compiled_binary(
    stdin_data: str = "",
    timeout: int = 5,
) -> dict[str, Any]:
    """Execute the previously compiled C++ binary with safe timeouts and output caps."""
    build_dir = ensure_build_dir()
    binary_path = get_binary_path(build_dir)

    if not binary_path.exists():
        return {
            "success": False,
            "error": "No compiled executable found. Click 'Compile C++' first.",
            "stdout": "",
            "stderr": "",
        }

    try:
        proc = subprocess.run(
            [str(binary_path)],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            cwd=str(build_dir),
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Execution Error: Program timed out after {timeout} seconds (possible infinite loop).",
            "stdout": "",
            "stderr": "",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": f"Execution Error: {exc}",
            "stdout": "",
            "stderr": "",
        }

    out = proc.stdout or ""
    err = proc.stderr or ""
    if len(out) > MAX_OUTPUT_CHARS:
        out = out[:MAX_OUTPUT_CHARS] + "\n... [Output truncated at 64 KB]"
    if len(err) > MAX_OUTPUT_CHARS:
        err = err[:MAX_OUTPUT_CHARS] + "\n... [Stderr truncated at 64 KB]"

    return {
        "success": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": out,
        "stderr": err,
        "error": f"Runtime Error (exit code {proc.returncode}):\n{err}" if proc.returncode != 0 else "",
    }