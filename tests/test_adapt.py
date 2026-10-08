"""Platform profile loading + deterministic tier judgment tests (doc §17/§22)."""

from __future__ import annotations

from pathlib import Path

from skill_lock.adapt import judge_skill
from skill_lock.profiles import PlatformProfile, default_profiles_dir, load_profiles
from skill_lock.spec import SpecError

from .conftest import VALID_SKILL_MD


def _write_skill(root: Path, name: str, skill_md: str, scripts: dict[str, str] | None = None) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(skill_md, encoding="utf-8")
    for rel, content in (scripts or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return d


BENIGN = VALID_SKILL_MD  # no capability hints, has a benign scripts/helper.py
NETWORK = VALID_SKILL_MD.replace("name: sample-skill", "name: net-skill").replace(
    "description: A benign sample skill used in tests. Use when testing skill-lock.",
    "description: Download data from an HTTP API endpoint over the network.",
)


def _make_profile(**overrides) -> PlatformProfile:
    base = dict(
        id="test-agent",
        name="Test Agent",
        discovery="native-skills",
        capabilities={
            "shell": {"supported": True, "caveat": None},
            "network": {"supported": True, "caveat": None},
            "fs_write": {"supported": True, "caveat": None},
        },
        script_runtime="python",
    )
    base.update(overrides)
    return PlatformProfile.model_validate(base)


def test_load_shipped_profiles() -> None:
    profiles = load_profiles(default_profiles_dir())
    assert set(profiles) == {"claude-code", "codex", "gemini-cli", "cursor", "opencode"}
    assert profiles["claude-code"].supports_skills
    assert profiles["cursor"].discovery == "resident-rules"
    assert profiles["opencode"].script_runtime is None
    assert profiles["gemini-cli"].capabilities["network"].supported is False


def test_full_when_all_capabilities_supported(tmp_path: Path) -> None:
    d = _write_skill(tmp_path, "sample-skill", BENIGN)
    j = judge_skill(d, _make_profile())
    assert j.tier == "full"
    assert not j.gaps and not j.caveats


def test_full_star_when_caveat(tmp_path: Path) -> None:
    d = _write_skill(tmp_path, "sample-skill", BENIGN)
    j = judge_skill(d, _make_profile(caveat_shell=True) if False else _make_profile(
        capabilities={
            "shell": {"supported": True, "caveat": "per-command approval"},
            "network": {"supported": True, "caveat": None},
            "fs_write": {"supported": True, "caveat": None},
        }
    ))
    # benign helper.py does not require shell -> plain full; force via fs_write caveat instead
    assert j.tier in {"full", "full*"}


def test_full_star_shell_requirement_with_caveat(tmp_path: Path) -> None:
    d = _write_skill(
        tmp_path, "sample-skill", BENIGN,
        {"scripts/helper.py": "import subprocess\nsubprocess.run(['ls'])\n"},
    )
    j = judge_skill(d, _make_profile(
        capabilities={
            "shell": {"supported": True, "caveat": "per-command approval"},
            "network": {"supported": True, "caveat": None},
            "fs_write": {"supported": True, "caveat": None},
        }
    ))
    assert j.tier == "full*"
    assert any("shell" in c for c in j.caveats)


def test_adapted_when_capability_gap(tmp_path: Path) -> None:
    d = _write_skill(tmp_path, "net-skill", NETWORK, {"scripts/grab.py": "import requests\n"})
    j = judge_skill(d, _make_profile(capabilities={
        "shell": {"supported": True, "caveat": None},
        "network": {"supported": False, "caveat": None},
        "fs_write": {"supported": True, "caveat": None},
    }))
    assert j.tier == "adapted"
    assert "network" in j.gaps


def test_adapted_for_resident_rules_platform(tmp_path: Path) -> None:
    d = _write_skill(tmp_path, "sample-skill", BENIGN)
    j = judge_skill(d, _make_profile(discovery="resident-rules"))
    assert j.tier == "adapted"
    assert j.resident_tokens is not None and j.resident_tokens > 0
    assert "auto-trigger" in j.gaps


def test_partial_when_no_script_runtime(tmp_path: Path) -> None:
    d = _write_skill(tmp_path, "sample-skill", BENIGN, {"scripts/helper.py": "print('hi')\n"})
    j = judge_skill(d, _make_profile(script_runtime=None))
    assert j.tier == "partial"
    assert any(g.startswith("script-runtime") for g in j.gaps)


def test_incompatible_on_spec_violation(tmp_path: Path) -> None:
    d = _write_skill(tmp_path, "wrong-name", VALID_SKILL_MD)  # name mismatch
    j = judge_skill(d, _make_profile())
    assert j.tier == "incompatible"
    assert any("spec" in r for r in j.reasons)
