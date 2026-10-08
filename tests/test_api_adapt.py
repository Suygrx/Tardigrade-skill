"""Server L2 endpoints: /api/adapt, /api/adaptations, /api/llm-status (mock LLM)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from tardigrade_skill import adapt_llm
from tardigrade_skill.ir import build_ir
from tardigrade_skill.llm import ModelConfig

from .conftest import VALID_SKILL_MD
from .test_adapt_llm import _good_response, _mock_llm, _skill_with_blocks, CURSOR_LIKE

CFG = ModelConfig(base_url="https://mock.example/v1", api_key="sk-test", model="mock-model")


def _patch_env(monkeypatch, tmp_path: Path) -> None:
    """Point the adaptation store at tmp and force the model config."""
    adapt_llm.reset_store()
    monkeypatch.setattr(adapt_llm, "HOME_DIR", tmp_path / "tgd")
    monkeypatch.setattr(adapt_llm, "ADAPTERS_DIR", tmp_path / "tgd" / "adapters")
    monkeypatch.setattr(adapt_llm, "DB_PATH", tmp_path / "tgd" / "desktop.db")
    monkeypatch.setattr(adapt_llm.llm, "load_model_config", lambda: CFG)


def test_llm_status_unconfigured(monkeypatch) -> None:
    monkeypatch.setattr(adapt_llm.llm, "load_model_config", lambda: None)
    c = TestClient(__import__("server.app", fromlist=["create_app"]).create_app())
    body = c.get("/api/llm-status").json()
    assert body["configured"] is False


def test_adapt_endpoint_full_flow(monkeypatch, tmp_path: Path) -> None:
    _patch_env(monkeypatch, tmp_path)
    d = _skill_with_blocks(tmp_path)
    ir = build_ir(d)
    _mock_llm(monkeypatch, [_good_response(ir)])

    c = TestClient(__import__("server.app", fromlist=["create_app"]).create_app())
    c.post("/api/settings", json={"roots": [str(tmp_path)]})

    # adapted cell exists on cursor (resident-rules)
    matrix = c.post("/api/matrix", json={"roots": [str(tmp_path)]}).json()
    cell = next(cell for row in matrix["rows"] if row["skill"] == "sample-skill" for cell in row["cells"] if cell["agent"] == "cursor")
    assert cell["tier"] == "adapted"

    r = c.post("/api/adapt", json={"skill": "sample-skill", "agent": "cursor"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending"
    assert body["judgment"]["tier"] == "adapted"

    listing = c.get("/api/adaptations").json()["adaptations"]
    assert len(listing) == 1

    ok = c.post("/api/adaptations/confirm", json={"id": body["id"]}).json()
    assert ok["ok"] is True


def test_adapt_endpoint_rejects_non_adapted_tier(monkeypatch, tmp_path: Path) -> None:
    _patch_env(monkeypatch, tmp_path)
    _skill_with_blocks(tmp_path)  # claude-code judges it full -> adapt must refuse
    c = TestClient(__import__("server.app", fromlist=["create_app"]).create_app())
    c.post("/api/settings", json={"roots": [str(tmp_path)]})
    r = c.post("/api/adapt", json={"skill": "sample-skill", "agent": "claude-code"})
    assert r.status_code == 400
    assert "full" in r.json()["detail"]
