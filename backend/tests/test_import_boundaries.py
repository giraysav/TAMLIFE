"""import-linter sozlesmesini ast ile ikinci kez dogrular (forbidden ve independence)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
CONFIG = ROOT / ".importlinter"


def _contracts() -> list[tuple[str, dict[str, list[str]]]]:
    blocks = CONFIG.read_text(encoding="utf-8-sig").split("[importlinter:contract:")[1:]
    found: list[tuple[str, dict[str, list[str]]]] = []
    for block in blocks:
        body = block.split("]", 1)[1]
        lists: dict[str, list[str]] = {}
        current: str | None = None
        for line in body.splitlines():
            if not line.strip():
                continue
            if line.startswith((" ", "\t")) and current:
                lists[current].append(line.strip())
            elif "=" in line:
                key, value = (part.strip() for part in line.split("=", 1))
                current = key if value == "" else None
                lists[key] = [] if value == "" else [value]
        found.append((lists["type"][0], lists))
    return found


def _imported(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(APP.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _under(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def test_no_forbidden_imports() -> None:
    violations: list[str] = []
    for kind, c in _contracts():
        for path in APP.rglob("*.py"):
            name = _module_name(path)
            if kind == "forbidden":
                if not any(_under(name, s) for s in c["source_modules"]):
                    continue
                banned = c["forbidden_modules"]
                violations += [f"{name} -> {i}" for i in _imported(path) if any(_under(i, b) for b in banned)]
            elif kind == "independence":
                own = next((m for m in c["modules"] if _under(name, m)), None)
                if own is None:
                    continue
                others = [m for m in c["modules"] if m != own]
                violations += [f"{name} -> {i}" for i in _imported(path) if any(_under(i, o) for o in others)]
    assert violations == []


def test_pyproject_matches_importlinter_modules() -> None:
    py = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for line in CONFIG.read_text(encoding="utf-8-sig").splitlines():
        item = line.strip()
        if item.startswith("app."):
            assert f'"{item}"' in py
