"""SkillIR extraction tests (doc §20: dual-channel capability inference)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tardigrade_skill.ir import build_ir
from tardigrade_skill.spec import SpecError

from .conftest import VALID_SKILL_MD

NETWORK_SKILL_MD = """---
name: net-skill
description: Download release assets from an API endpoint over HTTP.
allowed-tools: "WebFetch, Bash(git *)"
---

# Net skill

Download the release from https://example.com and store it locally.

    scripts/grab.py
"""


def _write(root: Path, name: str, skill_md: str, scripts: dict[str, str] | None = None) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(skill_md, encoding="utf-8")
    for rel, content in (scripts or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return d


def test_ir_benign_requires_nothing(tmp_path: Path) -> None:
    d = _write(tmp_path, "sample-skill", VALID_SKILL_MD)
    ir = build_ir(d)
    assert ir.name == "sample-skill"
    assert ir.requires == {"shell": False, "network": False, "fs_write": False}
    assert ir.blocks == []  # body has no markdown headings -> no instruction blocks
    assert ir.body_chars > 0


def test_ir_network_from_ast_and_text(tmp_path: Path) -> None:
    d = _write(
        tmp_path,
        "net-skill",
        NETWORK_SKILL_MD,
        {"scripts/grab.py": "import requests\nresp = requests.get('https://x.example')\n"},
    )
    ir = build_ir(d)
    assert ir.requires["network"] is True
    assert any(e.startswith("ast:grab.py") for e in ir.evidence["network"])
    assert any(e.startswith("text:SKILL.md") for e in ir.evidence["network"])
    assert [(t.tool, t.pattern) for t in ir.allowed_tools] == [("WebFetch", "WebFetch"), ("Bash", "Bash(git *)")]


def test_ir_shell_and_fs_from_ast(tmp_path: Path) -> None:
    d = _write(
        tmp_path,
        "sample-skill",
        VALID_SKILL_MD,
        {"scripts/do.py": "import subprocess, os\nsubprocess.run(['ls'])\nos.makedirs('out')\n"},
    )
    ir = build_ir(d)
    assert ir.requires["shell"] is True
    assert ir.requires["fs_write"] is True
    assert any("subprocess" in e for e in ir.evidence["shell"])


def test_ir_blocks_locate_scripts(tmp_path: Path) -> None:
    body = VALID_SKILL_MD + "\n## Extra\n\nUse scripts/helper.py now.\n"
    d = _write(tmp_path, "sample-skill", body)
    ir = build_ir(d)
    extra = [b for b in ir.blocks if b.heading == "Extra"]
    assert extra and "scripts/helper.py" in extra[0].scripts
    assert extra[0].end >= extra[0].start


def test_ir_invalid_spec_raises(tmp_path: Path) -> None:
    d = _write(tmp_path, "wrong-dir", VALID_SKILL_MD)  # name mismatch
    with pytest.raises(SpecError):
        build_ir(d)
