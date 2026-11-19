"""Architecture tests enforcing module boundaries and package __init__.py presence (owner: C)."""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "booking_agent"

ALLOWED_CROSS_MODULE_SUBMODULES = frozenset({"port", "service", "models", "schema"})
SHARED_KERNEL_MODULE = "shared"
COMPOSITION_ROOT_FILES = frozenset({"main.py", "__init__.py"})


def _get_module_name(py_file: Path) -> str | None:
    rel = py_file.relative_to(SRC_ROOT)
    if len(rel.parts) == 1:
        return None
    return rel.parts[0]


def _is_submodule_on_disk(dotted_path: str) -> bool:
    parts = dotted_path.split(".")[1:]
    candidate = SRC_ROOT.joinpath(*parts)
    return candidate.is_dir() or candidate.with_suffix(".py").is_file()


def _extract_imported_modules(py_file: Path) -> list[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            targets.append(node.module)
            for alias in node.names:
                candidate = f"{node.module}.{alias.name}"
                if candidate.startswith("booking_agent.") and _is_submodule_on_disk(candidate):
                    targets.append(candidate)
    return targets


def test_every_module_has_init() -> None:
    """Every directory under src/booking_agent/ must contain __init__.py."""
    missing: list[str] = []
    for directory in SRC_ROOT.rglob("*"):
        if not directory.is_dir() or directory.name == "__pycache__":
            continue
        if not (directory / "__init__.py").is_file():
            missing.append(str(directory.relative_to(SRC_ROOT)))
    assert not missing, f"Directories missing __init__.py: {missing}"


def test_module_boundaries() -> None:
    """Disallow cross-module internal imports outside shared kernel, ports, and public facades."""
    violations: list[str] = []

    for py_file in sorted(SRC_ROOT.rglob("*.py")):
        rel = py_file.relative_to(SRC_ROOT)
        if len(rel.parts) == 1 and rel.name in COMPOSITION_ROOT_FILES:
            continue

        owner_mod = _get_module_name(py_file)
        if owner_mod is None:
            continue

        for target in _extract_imported_modules(py_file):
            if not target.startswith("booking_agent."):
                continue
            parts = target.split(".")
            if len(parts) < 2:
                continue
            target_mod = parts[1]

            if target_mod == owner_mod or target_mod == SHARED_KERNEL_MODULE:
                continue

            if len(parts) == 2:
                continue

            sub = parts[2]
            if sub in ALLOWED_CROSS_MODULE_SUBMODULES:
                if target_mod == "telemetry" and sub != "schema":
                    violations.append(f"{rel}: forbidden telemetry import '{target}'")
                continue

            violations.append(
                f"{rel}: forbidden cross-module internal import '{target}' "
                f"(owner '{owner_mod}' -> '{target_mod}.{sub}')"
            )

    assert not violations, "Module boundary violations:\n" + "\n".join(violations)
