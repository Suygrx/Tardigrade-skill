"""L2 adaptation pipeline tests (mock LLM — no network).

Covers doc §12/§23 contract: fencing, canary leak rejection, JSON extraction,
deterministic changelog coverage check with exactly one retry, fixation reuse,
and the HITL confirm gate (spec + audit before dispatch).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tardigrade_skill import adapt_llm
from tardigrade_skill.adapt_llm import (
    _coverage_ok,
    adapt_skill,
    confirm_adaptation,
    list_adaptations,
    reject_adaptation,
    source_hash,
)
from tardigrade_skill.fencing import CANARY_PREFIX, fence_content
from tardigrade_skill.ir import build_ir
from tardigrade_skill.llm import ModelConfig, extract_json
from tardigrade_skill.profiles import PlatformProfile

from .conftest import VALID_SKILL_MD

CURSOR_LIKE = PlatformProfile.model_validate(
    {
        "id": "cursor",
        "name": "Cursor",
        "discovery": "resident-rules",
        "capabilities": {
            "shell": {"supported": True, "caveat": "approval"},
            "network": {"supported": True},
            "fs_write": {"supported": True},
        },
        "script_runtime": "python",
    }
)

CFG = ModelConfig(base_url="https://mock.example/v1", api_key="sk-test", model="mock-model")


def _skill_with_blocks(root: Path) -> Path:
    body = VALID_SKILL_MD + "\n## Extra section\n\nUse scripts/helper.py when needed.\n"
    d = root / "sample-skill"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(body, encoding="utf-8")
    (d / "scripts").mkdir()
    (d / "scripts" / "helper.py").write_text("print('hi')\n", encoding="utf-8")
    return d


def _mock_llm(monkeypatch, responses: list[str]) -> list[dict]:
    """Replace llm.chat; record the prompts it receives."""
    calls: list[dict] = []

    def fake_chat(config, system_prompt, user_prompt):
        calls.append({"system": system_prompt, "user": user_prompt})
        return responses[min(len(calls) - 1, len(responses) - 1)]

    monkeypatch.setattr(adapt_llm.llm, "chat", fake_chat)
    return calls


def _good_response(ir) -> str:
    changelog = [{"block": b.id, "action": "kept", "reason": "compatible", "lost": "", "replacement": ""} for b in ir.blocks]
    return json.dumps({"adapted_skill_md": VALID_SKILL_MD, "changelog": changelog, "notes": "ok"})


# ------------------------------------------------------------------ fencing

def test_fence_nonce_wraps_content() -> None:
    fenced, nonce = fence_content("hello world")
    assert nonce in fenced and "hello world" in fenced
    assert fenced.count(nonce) == 2  # open + close marker only


def test_canary_check() -> None:
    assert adapt_llm.check_canary("clean output", CANARY_PREFIX + "abc")
    assert not adapt_llm.check_canary(f"leak {CANARY_PREFIX}abc", CANARY_PREFIX + "abc")


# ------------------------------------------------------------------ json / coverage

def test_extract_json_tolerates_fences() -> None:
    text = "```json\n{\"a\": 1, \"nested\": {\"b\": 2}}\n```"
    assert extract_json(text) == {"a": 1, "nested": {"b": 2}}


def test_coverage_ok_flags_missing_and_extra(tmp_path: Path) -> None:
    ir = build_ir(_skill_with_blocks(tmp_path))  # one heading -> single block b1
    problems = _coverage_ok([{"block": "b9", "action": "kept"}], ir)
    assert any("missing block: b1" in p for p in problems)
    assert any("unknown block: b9" in p for p in problems)


# ------------------------------------------------------------------ pipeline

def test_adapt_success_and_fixation_reuse(tmp_path: Path, monkeypatch) -> None:
    adapt_llm.reset_store()
    d = _skill_with_blocks(tmp_path)
    ir = build_ir(d)
    calls = _mock_llm(monkeypatch, [_good_response(ir)])

    r1 = adapt_skill(d, CURSOR_LIKE, CFG)
    assert r1["status"] == "pending"
    assert r1["reused"] is False
    assert {c["block"] for c in r1["changelog"]} == {b.id for b in ir.blocks}
    assert len(calls) == 1
    # fenced content + canary reached the prompt exactly once each
    assert "fence=" in calls[0]["user"]
    assert CANARY_PREFIX in calls[0]["system"]

    # same source + agent -> reuse, no second LLM call
    r2 = adapt_skill(d, CURSOR_LIKE, CFG)
    assert r2["reused"] is True and len(calls) == 1

    products = list_adaptations("pending")
    assert len(products) == 1
    assert (Path(products[0]["dir"]) / "SKILL.md").is_file()
    assert (Path(products[0]["dir"]) / "scripts" / "helper.py").is_file()


def test_adapt_contract_breach_retries_once_then_partial(tmp_path: Path, monkeypatch) -> None:
    adapt_llm.reset_store()
    d = _skill_with_blocks(tmp_path)
    # changelog references an unknown block -> missing b1 -> breach twice (initial + one retry) -> partial
    bad = json.dumps(
        {"adapted_skill_md": VALID_SKILL_MD, "changelog": [{"block": "b9", "action": "kept"}], "notes": ""}
    )
    calls = _mock_llm(monkeypatch, [bad, bad])
    r = adapt_skill(d, CURSOR_LIKE, CFG)
    assert r["status"] == "partial"
    assert "missing block" in r["message"]
    assert len(calls) == 2
    assert list_adaptations() == []


def test_adapt_canary_leak_rejected(tmp_path: Path, monkeypatch) -> None:
    adapt_llm.reset_store()
    d = _skill_with_blocks(tmp_path)
    leaky = [json.dumps({"adapted_skill_md": VALID_SKILL_MD, "changelog": [], "notes": ""})]

    def fake_chat(config, system_prompt, user_prompt):
        canary = system_prompt.split(CANARY_PREFIX)[1].split()[0]
        return CANARY_PREFIX + canary  # model "leaks" the canary

    monkeypatch.setattr(adapt_llm.llm, "chat", fake_chat)
    monkeypatch.setattr(adapt_llm.llm, "extract_json", lambda t: extract_json(leaky[0]))
    r = adapt_skill(d, CURSOR_LIKE, CFG)
    assert r["status"] == "failed"
    assert "canary" in r["message"]


def test_adapt_without_model_config(tmp_path: Path, monkeypatch) -> None:
    adapt_llm.reset_store()
    monkeypatch.setattr(adapt_llm.llm, "load_model_config", lambda: None)
    r = adapt_skill(_skill_with_blocks(tmp_path), CURSOR_LIKE, None)
    assert r["status"] == "no-model"


# ------------------------------------------------------------------ HITL

def test_confirm_runs_audit_gate_then_dispatches(tmp_path: Path, monkeypatch) -> None:
    adapt_llm.reset_store()
    d = _skill_with_blocks(tmp_path)
    ir = build_ir(d)
    _mock_llm(monkeypatch, [_good_response(ir)])
    r = adapt_skill(d, CURSOR_LIKE, CFG)
    assert r["status"] == "pending"

    dispatched: list[tuple[str, str]] = []

    def fake_dispatch(product: Path, agent: str) -> Path:
        dispatched.append((str(product), agent))
        return Path("/fake/dest") / product.name

    out = confirm_adaptation(r["id"], dispatch_fn=fake_dispatch)
    assert out["ok"] is True
    assert dispatched and dispatched[0][1] == "cursor"
    assert list_adaptations()[0]["status"] == "confirmed"

    # double confirm rejected
    assert confirm_adaptation(r["id"], dispatch_fn=fake_dispatch)["ok"] is False


def test_reject_flow(tmp_path: Path, monkeypatch) -> None:
    adapt_llm.reset_store()
    d = _skill_with_blocks(tmp_path)
    ir = build_ir(d)
    _mock_llm(monkeypatch, [_good_response(ir)])
    r = adapt_skill(d, CURSOR_LIKE, CFG)
    assert reject_adaptation(r["id"])["ok"] is True
    assert list_adaptations()[0]["status"] == "rejected"
    # rejected product can be re-adapted (no reuse)
    r2 = adapt_skill(d, CURSOR_LIKE, CFG)
    assert r2["status"] == "pending" and r2["id"] != r["id"]


def test_source_hash_stable_and_sensitive(tmp_path: Path) -> None:
    d1 = _skill_with_blocks(tmp_path)
    h1 = source_hash(d1)
    assert h1 == source_hash(d1)
    (d1 / "scripts" / "helper.py").write_text("print('changed')\n", encoding="utf-8")
    assert h1 != source_hash(d1)


# ------------------------------------------------------------------ mechanical / multi-file / recheck

def test_mechanical_frontmatter_trims_whitelist(tmp_path: Path) -> None:
    strict = PlatformProfile.model_validate({"id": "strict", "name": "Strict", "frontmatter_fields": ["name", "description"]})
    md = VALID_SKILL_MD  # has license + metadata beyond the whitelist
    new_text, dropped = adapt_llm.mechanical_frontmatter(md, strict)
    assert dropped == ["license", "metadata"]
    assert "license" not in new_text.split("---")[1]
    assert "name: sample-skill" in new_text
    # 平台支持全部字段时不做任何改动
    same, dropped2 = adapt_llm.mechanical_frontmatter(md, CURSOR_LIKE)
    assert dropped2 == [] and same == md


def test_adapt_prompt_contains_supporting_files_and_judgment(tmp_path: Path, monkeypatch) -> None:
    adapt_llm.reset_store()
    d = _skill_with_blocks(tmp_path)
    ir = build_ir(d)
    calls = _mock_llm(monkeypatch, [_good_response(ir)])
    r = adapt_skill(d, CURSOR_LIKE, CFG)
    assert r["status"] == "pending"
    user = calls[0]["user"]
    # scripts 内容作为围栏数据进入 prompt
    assert "UNTRUSTED SUPPORTING FILES" in user
    assert "print('hi')" in user
    # 判定层的真实 gaps/caveats 进入 prompt（resident-rules 平台 -> auto-trigger gap）
    assert "auto-trigger" in user


def test_adapt_skips_non_adapted_tier(tmp_path: Path, monkeypatch) -> None:
    adapt_llm.reset_store()
    d = _skill_with_blocks(tmp_path)
    calls = _mock_llm(monkeypatch, [])
    capable = PlatformProfile.model_validate(
        {
            "id": "capable",
            "name": "Capable",
            "discovery": "native-skills",
            "capabilities": {"shell": {"supported": True}, "network": {"supported": True}, "fs_write": {"supported": True}},
            "script_runtime": "python",
        }
    )
    r = adapt_skill(d, capable, CFG)
    assert r["status"] == "not-adapted" and r["tier"] == "full"
    assert calls == []  # 0 token
