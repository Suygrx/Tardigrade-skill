"""Server M3 endpoints: /api/llm/config, /api/llm/test, /api/search, /api/install."""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from tardigrade_skill import discover, llm

from .test_adapt_llm import _skill_with_blocks, CURSOR_LIKE  # noqa: F401 (fixtures reuse helpers)

REPO = Path(__file__).resolve().parents[1]


def _client() -> TestClient:
    from server.app import create_app

    return TestClient(create_app())


def test_llm_config_saves_and_probes(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "models.toml"
    monkeypatch.setattr(llm, "CONFIG_PATH", target)

    def fake_get(url, **kw):
        return httpx.Response(200, json={"data": [{"id": "mock-model"}]}, request=httpx.Request("GET", url))

    monkeypatch.setattr(llm.httpx, "get", fake_get)
    c = _client()
    r = c.post("/api/llm/config", json={"base_url": "https://mock.example/v1/", "api_key": "sk-x", "model": "mock-model"})
    assert r.status_code == 200
    body = r.json()
    assert body["saved"] is True and body["ok"] is True and body["exact_match"] is True
    assert target.is_file()  # written to the user's config path

    # missing fields -> 400
    r2 = c.post("/api/llm/config", json={"base_url": "", "api_key": "k", "model": "m"})
    assert r2.status_code == 400


def test_install_happy_and_gated(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(llm, "CONFIG_PATH", tmp_path / "unused.toml")
    c = _client()

    # pdf-helper from demo is designed full on claude-code
    r = c.post("/api/install", json={"source": str(REPO / "demo" / "skills" / "pdf-helper"), "agent": "claude-code"})
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["ok"] is True
    assert Path(body["results"][0]["dest"]).is_dir()

    # broken-skill: spec-invalid -> rejected with reason
    r2 = c.post("/api/install", json={"source": str(REPO / "demo" / "skills" / "broken-skill"), "agent": "claude-code"})
    assert r2.json()["results"][0]["ok"] is False

    # unknown agent -> 400
    r3 = c.post("/api/install", json={"source": str(REPO / "demo" / "skills" / "pdf-helper"), "agent": "nope"})
    assert r3.status_code == 400


def test_search_endpoint_uses_core(monkeypatch) -> None:
    called = {}

    def fake_search(query, limit=5, use_cache=True):
        called.update(query=query, limit=limit)
        return {"results": [], "rate_limited": False, "degraded": False, "message": "", "cached": False}

    monkeypatch.setattr(discover, "search_skills", fake_search)
    c = _client()
    r = c.post("/api/search", json={"query": "pdf", "limit": 99})
    assert r.status_code == 200
    assert called == {"query": "pdf", "limit": 10}  # limit clamped to 10
