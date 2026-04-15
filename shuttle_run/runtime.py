from __future__ import annotations

import ast
import inspect
import json
import re
from functools import lru_cache
from pathlib import Path
import importlib

PRIMARY_FUNCTION = 'shuttle_run'
SOURCES = {'6-9': 'ages_6-9/shuttle_run/shuttle_run.py', '10-13': 'ages_10-13/shuttle_run/shuttle_run.py', '14-18': 'ages_14-18/shuttle_run/shuttle_run.py'}

_LINE_FILTER = re.compile(r"^\s*(!?pip\s+install|get_ipython\()")


def _ensure_mediapipe_compat() -> None:
    try:
        mp = importlib.import_module("mediapipe")
    except Exception:
        return

    if hasattr(mp, "solutions"):
        return

    try:
        solutions = importlib.import_module("mediapipe.python.solutions")
    except Exception:
        return

    setattr(mp, "solutions", solutions)


def _read_code(source_file: Path) -> str:
    if source_file.suffix.lower() == ".ipynb":
        data = json.loads(source_file.read_text(encoding="utf-8"))
        code = "\n".join(
            "".join(cell.get("source", []))
            for cell in data.get("cells", [])
            if cell.get("cell_type") == "code"
        )
    else:
        code = source_file.read_text(encoding="utf-8", errors="ignore")
    return "\n".join(line for line in code.splitlines() if not _LINE_FILTER.match(line))


def _resolve_source_file(preferred_file: Path) -> Path:
    if preferred_file.exists():
        return preferred_file
    notebook_fallback = preferred_file.with_suffix(".ipynb")
    if notebook_fallback.exists():
        return notebook_fallback
    raise FileNotFoundError(f"Source file not found: {preferred_file} (or {notebook_fallback})")


def _safe_module_ast(code: str) -> ast.Module:
    def _is_safe_assignment_value(value: ast.AST | None) -> bool:
        if not isinstance(value, ast.Call):
            return True
        func = value.func
        if isinstance(func, ast.Name):
            return func.id in {"Pose", "DrawingSpec"}
        if isinstance(func, ast.Attribute):
            return func.attr in {"Pose", "DrawingSpec"}
        return False

    tree = ast.parse(code)
    keep = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            keep.append(node)
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            value = getattr(node, "value", None)
            if not _is_safe_assignment_value(value):
                continue
            keep.append(node)
            continue
        if isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant):
            if isinstance(node.value.value, str):
                keep.append(node)
    return ast.Module(body=keep, type_ignores=[])


@lru_cache(maxsize=16)
def _load_namespace(age_group: str) -> dict:
    if age_group not in SOURCES:
        raise ValueError(f"Unsupported age group '{age_group}' for this activity.")

    root = Path(__file__).resolve().parents[1]
    source_file = _resolve_source_file(root / SOURCES[age_group])

    try:
        code = _read_code(source_file)
        module_ast = _safe_module_ast(code)
        _ensure_mediapipe_compat()
        namespace: dict = {}
        exec(compile(module_ast, str(source_file), "exec"), namespace, namespace)
        return namespace
    except Exception:
        notebook_fallback = source_file.with_suffix(".ipynb")
        if source_file.suffix.lower() == ".py" and notebook_fallback.exists():
            code = _read_code(notebook_fallback)
            module_ast = _safe_module_ast(code)
            _ensure_mediapipe_compat()
            namespace = {}
            exec(compile(module_ast, str(notebook_fallback), "exec"), namespace, namespace)
            return namespace
        raise


def get_activity_function(age_group: str, function_name: str):
    namespace = _load_namespace(age_group)
    fn = namespace.get(function_name)
    if not callable(fn):
        raise ValueError(f"Function '{function_name}' not found for age group '{age_group}'.")
    return fn


def run_primary(
    age_group: str,
    candidate_id: str,
    candidate_name: str,
    video_path: str,
    age: int | None = None,
    gender: str | None = None,
    data_print: str = "N",
    jumped_length: float | None = None,
):
    fn = get_activity_function(age_group, PRIMARY_FUNCTION)
    sig = inspect.signature(fn)

    value_pool = {
        "ID": candidate_id,
        "id": candidate_id,
        "name": candidate_name,
        "Name": candidate_name,
        "path": video_path,
        "video_path": video_path,
        "data_print": data_print,
        "age": age,
        "gender": gender,
        "jumped_length": jumped_length,
    }

    kwargs = {}
    for param_name, param in sig.parameters.items():
        if param_name in value_pool and value_pool[param_name] is not None:
            kwargs[param_name] = value_pool[param_name]
        elif param.default is inspect._empty:
            raise ValueError(
                f"Missing required parameter '{param_name}' for function '{PRIMARY_FUNCTION}'"
            )

    return fn(**kwargs)


def run_common(
    age_group: str,
    candidate_id: str,
    candidate_name: str,
    video_path: str,
    age: int | None = None,
    gender: str | None = None,
    jumped_length: float | None = None,
):
    return run_primary(
        age_group=age_group,
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        video_path=video_path,
        age=age,
        gender=gender,
        data_print="N",
    )


def run_shuttle_run(
    age_group: str,
    candidate_id: str,
    candidate_name: str,
    video_path: str,
    age: int | None = None,
    gender: str | None = None,
    jumped_length: float | None = None,
):
    return run_common(
        age_group=age_group,
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        video_path=video_path,
        age=age,
        gender=gender,
    )
