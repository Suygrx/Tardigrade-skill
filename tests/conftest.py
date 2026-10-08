"""Fixture helpers: build sample skill directories on disk."""

from __future__ import annotations

from pathlib import Path

VALID_SKILL_MD = """---
name: sample-skill
description: A benign sample skill used in tests. Use when testing skill-lock.
license: MIT
metadata:
  author: test-org
  version: "1.0"
---

# Sample skill

Do the thing, step by step:

1. Read the input file.
2. Transform it.
3. Write the output next to the input.

Run the helper:

    scripts/helper.py
"""


def make_skill(root: Path, name: str = "sample-skill", skill_md: str = VALID_SKILL_MD, files: dict[str, str] | None = None) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(skill_md, encoding="utf-8")
    (d / "scripts").mkdir(exist_ok=True)
    (d / "scripts" / "helper.py").write_text("print('hello')\n", encoding="utf-8")
    for rel, content in (files or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return d
