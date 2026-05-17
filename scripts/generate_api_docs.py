"""Generate lightweight Markdown API reference files.

The generator intentionally uses only the Python standard library so it can run
in CI before optional documentation tooling is installed.
"""

from __future__ import annotations

import argparse
import inspect
import pkgutil
import sys
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
API_DIR = REPO_ROOT / "docs" / "api"

MODULE_TITLES = {
    "dsafelogger": "Public API",
    "dsafelogger.mp": "Multiprocess API",
    "dsafelogger._async": "Async Logging",
    "dsafelogger._cli": "CLI Tool",
    "dsafelogger._color": "Color Console",
    "dsafelogger._constants": "Constants",
    "dsafelogger._context": "Context Management",
    "dsafelogger._env_parser": "Environment Variable Parser",
    "dsafelogger._formatter": "Formatters",
    "dsafelogger._handler": "File Handler",
    "dsafelogger._ini_loader": "INI / Dict Loader",
    "dsafelogger._integrity": "Integrity Verification",
    "dsafelogger._levels": "Custom Log Levels",
    "dsafelogger._logger": "DSafeLogger Class",
    "dsafelogger._mp_attach": "Multiprocess Client Transport",
    "dsafelogger._mp_control": "Multiprocess Control Plane",
    "dsafelogger._mp_protocol": "Multiprocess Protocol",
    "dsafelogger._mp_queue": "Multiprocess Queue Tracking",
    "dsafelogger._mp_runtime": "Multiprocess Writer Runtime",
    "dsafelogger._pipeline": "Configuration Pipeline",
    "dsafelogger._purge": "Purge / Archive Workers",
    "dsafelogger._routing": "Routing Strategies",
    "dsafelogger._sink": "Sink Configuration",
    "dsafelogger._transport": "Transport Configuration",
    "dsafelogger._validator": "Path Validator",
    "dsafelogger._writer_formatter": "Writer Formatter Utilities",
}


def _module_names() -> list[str]:
    package_dir = SRC_ROOT / "dsafelogger"
    names = ["dsafelogger", "dsafelogger.mp"]
    for module_info in sorted(pkgutil.iter_modules([str(package_dir)]), key=lambda item: item.name):
        if module_info.name == "mp":
            continue
        names.append(f"dsafelogger.{module_info.name}")
    return names


def _doc_summary(obj: Any) -> str:
    doc = inspect.getdoc(obj) or ""
    return doc.strip()


def _signature(obj: Any) -> str:
    try:
        return str(inspect.signature(obj))
    except (TypeError, ValueError):
        return "(...)"


def _is_constant(name: str, value: Any) -> bool:
    if name.startswith("_") or not name.isupper():
        return False
    return isinstance(value, (str, int, float, bool, tuple, frozenset, type(None)))


def _format_value(value: Any) -> str:
    if isinstance(value, frozenset):
        text = "frozenset({" + ", ".join(repr(item) for item in sorted(value, key=repr)) + "})"
    else:
        text = repr(value)
    if len(text) > 80:
        text = text[:77] + "..."
    return text.replace("|", "\\|")


def _module_members(module: ModuleType) -> tuple[list[tuple[str, Any]], list[tuple[str, Any]], list[tuple[str, Any]]]:
    functions: list[tuple[str, Any]] = []
    classes: list[tuple[str, Any]] = []
    constants: list[tuple[str, Any]] = []
    exported = set(getattr(module, "__all__", ())) if module.__name__ in {"dsafelogger", "dsafelogger.mp"} else None
    for name, value in sorted(vars(module).items()):
        if exported is not None and name not in exported:
            continue
        if inspect.isfunction(value) and value.__module__ == module.__name__:
            functions.append((name, value))
        elif inspect.isclass(value) and value.__module__ == module.__name__:
            classes.append((name, value))
        elif _is_constant(name, value):
            constants.append((name, value))
    return functions, classes, constants


def _module_filename(module_name: str) -> str:
    return module_name.replace("._", "__").replace(".", "__") + ".md"


def _render_module(module_name: str) -> str:
    module = import_module(module_name)
    title = MODULE_TITLES.get(module_name, module_name)
    lines = [f"# {title}", "", f"**Module**: `{module_name}`", ""]

    module_doc = _doc_summary(module)
    if module_doc:
        lines.extend([module_doc, ""])

    functions, classes, constants = _module_members(module)

    if functions:
        lines.extend(["## Functions", ""])
        for name, function in functions:
            lines.extend([f"### `{name}{_signature(function)}`", ""])
            doc = _doc_summary(function)
            if doc:
                lines.extend([doc, ""])

    if classes:
        lines.extend(["## Classes", ""])
        for name, cls in classes:
            lines.extend([f"### `{name}{_signature(cls)}`", ""])
            doc = _doc_summary(cls)
            if doc:
                lines.extend([doc, ""])
            methods = [
                (method_name, method)
                for method_name, method in sorted(vars(cls).items())
                if not method_name.startswith("_") and inspect.isfunction(method)
            ]
            if methods:
                lines.extend(["Public methods:", ""])
                for method_name, method in methods:
                    lines.extend([f"- `{method_name}{_signature(method)}`"])
                lines.append("")

    if constants:
        lines.extend(["## Constants", "", "| Name | Type | Value |", "|---|---|---|"])
        for name, value in constants:
            lines.append(f"| `{name}` | `{type(value).__name__}` | `{_format_value(value)}` |")
        lines.append("")

    if not (functions or classes or constants):
        lines.extend(["No public functions, classes, or constants are exported by this module.", ""])

    return "\n".join(lines).rstrip() + "\n"


def _render_index(module_names: list[str]) -> str:
    lines = [
        "# API Reference",
        "",
        "Generated API reference for D-SafeLogger.",
        "",
        "Run `uv run python scripts/generate_api_docs.py --check` to verify it is up to date.",
        "",
        "Most users should start with `dsafelogger` and `dsafelogger.mp`. Modules whose names start with `_` are documented for transparency and maintainers, but they are not the stable public API surface.",
        "",
    ]
    for module_name in module_names:
        title = MODULE_TITLES.get(module_name, module_name)
        lines.append(f"- [{title}]({_module_filename(module_name)}) - `{module_name}`")
    return "\n".join(lines).rstrip() + "\n"


def _generated_files() -> dict[Path, str]:
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    module_names = _module_names()
    files = {API_DIR / "index.md": _render_index(module_names)}
    for module_name in module_names:
        files[API_DIR / _module_filename(module_name)] = _render_module(module_name)
    return files


def _existing_generated_files() -> set[Path]:
    if not API_DIR.exists():
        return set()
    return {path for path in API_DIR.iterdir() if path.is_file() and path.suffix in {".md", ".txt"}}


def check() -> int:
    files = _generated_files()
    expected_paths = set(files)
    stale_paths = _existing_generated_files() - expected_paths
    changed_paths = [path for path, content in files.items() if not path.exists() or path.read_text(encoding="utf-8") != content]
    if stale_paths or changed_paths:
        for path in sorted(changed_paths):
            print(f"out of date: {path.relative_to(REPO_ROOT)}")
        for path in sorted(stale_paths):
            print(f"stale: {path.relative_to(REPO_ROOT)}")
        return 1
    print("API docs are up to date")
    return 0


def write() -> int:
    files = _generated_files()
    API_DIR.mkdir(parents=True, exist_ok=True)
    for path in _existing_generated_files() - set(files):
        path.unlink()
    for path, content in files.items():
        path.write_text(content, encoding="utf-8", newline="\n")
    print(f"Generated {len(files)} API reference files in {API_DIR.relative_to(REPO_ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if generated docs are not up to date")
    args = parser.parse_args()
    return check() if args.check else write()


if __name__ == "__main__":
    raise SystemExit(main())
