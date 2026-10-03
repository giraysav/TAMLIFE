"""import-linter ile ayni yasak listeyi ast ile tarar."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
CONFIG = ROOT / ".importlinter"


def _contracts() -> list[tuple[set[str], set[str]]]:
    text = CONFIG.read_text(encoding="utf-8")
    blocks = text.split("[importlinter:contract:")[1:]
    found: list[tuple[set[str], set[str]]] = []
    for block in blocks:
        body = block.split("]", 1)[1]
        lists: dict[str, list[str]] = {}
        current: str | None = None
        for line in body.splitlines():
            if not line.strip():
                continue
            if line.startswith((" ", "\t")) and current:
                lists[current].append(line.strip())
                continue
            if "=" in line:
                key, value = (part.strip() for part in line.split("=", 1))
                if value == "":
                    current = key
                    lists[key] = []
                else:
                    current = None
        found.append((set(lists["source_modules"]), set(lists["forbidden_modules"])))
    return found


def _imported(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _module_name(path: Path) -> str:
    rel = path.relative_to(APP.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def test_no_forbidden_imports() -> None:
    violations: list[str] = []
    for sources, forbidden in _contracts():
        for path in APP.rglob("*.py"):
            name = _module_name(path)
            if not any(name == src or name.startswith(src + ".") for src in sources):
                continue
            for imported in _imported(path):
                if any(imported == ban or imported.startswith(ban + ".") for ban in forbidden):
                    violations.append(f"{name} -> {imported}")
    assert violations == []


def test_pyproject_matches_importlinter_modules() -> None:
    py = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    ini = CONFIG.read_text(encoding="utf-8")
    for line in ini.splitlines():
        item = line.strip()
        if item.startswith("app."):
            assert f"\"{item}\"" in py
