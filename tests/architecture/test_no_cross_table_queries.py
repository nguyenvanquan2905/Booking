"""Architecture test scanning SQL strings to forbid cross-table queries (owner: C)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "booking_agent"

MODULE_TABLE_PREFIXES: dict[str, tuple[str, ...]] = {
    "booking": ("booking_",),
    "agent": ("agent_",),
    "browser_control": ("bc_",),
    "sandbox": ("sandbox_",),
    "profile": ("profile_",),
    "artifact": ("artifact_",),
    "telemetry": ("telemetry_",),
}

_SQL_KEYWORD_RE = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP)\b", re.I)
_SQL_TABLE_REF_RE = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE(?:\s+IF\s+(?:NOT\s+)?EXISTS)?)\s+([a-zA-Z0-9_]+)",
    re.I,
)
_DOMAIN_PREFIXES = ("booking_", "agent_", "bc_", "sandbox_", "profile_", "artifact_", "telemetry_")


def _iter_sql_strings(py_file: Path) -> list[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    sql_strings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            if _SQL_KEYWORD_RE.search(text) and _SQL_TABLE_REF_RE.search(text):
                sql_strings.append(text)
    return sql_strings


def test_no_cross_table_queries() -> None:
    """Every module may only query SQLite tables carrying its own prefix."""
    violations: list[str] = []

    for py_file in sorted(SRC_ROOT.rglob("*.py")):
        rel = py_file.relative_to(SRC_ROOT)
        if rel == Path("shared/schema.py"):
            continue

        module_name = rel.parts[0] if len(rel.parts) > 1 else ""
        allowed_prefixes = MODULE_TABLE_PREFIXES.get(module_name, ())

        for sql_text in _iter_sql_strings(py_file):
            referenced_tables = set(_SQL_TABLE_REF_RE.findall(sql_text))
            for table in sorted(referenced_tables):
                table_lower = table.lower()
                if not table_lower.startswith(_DOMAIN_PREFIXES):
                    continue
                if not any(table_lower.startswith(prefix) for prefix in allowed_prefixes):
                    violations.append(
                        f"{rel}: module '{module_name or 'root'}' queries foreign table '{table}'"
                    )

    assert not violations, "Cross-table SQL violations:\n" + "\n".join(violations)
