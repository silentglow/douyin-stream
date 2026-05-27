from __future__ import annotations

from pathlib import Path


def test_playwright_removed_from_dependencies() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")

    assert "playwright" not in pyproject.lower()
    assert "playwright" not in requirements.lower()


def test_no_playwright_imports_in_src() -> None:
    root = Path(__file__).resolve().parents[1]
    src_root = root / "src" / "media_tools"

    offenders: list[str] = []
    for path in src_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        if "from playwright" in lowered or "import playwright" in lowered:
            offenders.append(str(path))

    assert offenders == []

