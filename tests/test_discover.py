"""M3 tests: LLM config save/probe (doc: user fills url+key+model, auto-detect)
and search=audit discovery with cache + rate-limit degradation."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from tardigrade_skill import discover, llm
from tardigrade_skill.llm import ModelConfig, load_model_config, save_model_config
from tardigrade_skill.llm import test_connection as probe_connection  # renamed: pytest would collect test_*

CFG = ModelConfig(base_url="https://mock.example/v1", api_key="sk-test", model="mock-model")


# ------------------------------------------------------------------ config save/probe

def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    p = save_model_config("https://api.example.com/v1/", "sk-abc", "gpt-4o-mini", path=tmp_path / "models.toml")
    cfg = load_model_config(p)
    assert cfg is not None
    assert cfg.base_url == "https://api.example.com/v1"  # trailing slash stripped
    assert cfg.api_key == "sk-abc"
    assert cfg.model == "gpt-4o-mini"
    assert "sk-abc" in p.read_text(encoding="utf-8")  # key lives only in the user's local file


def test_probe_models_listed_with_exact_match(monkeypatch) -> None:
    cfg = ModelConfig(base_url="https://mock.example/v1", api_key="sk-test", model="gpt-4o-mini")
    def fake_get(url, **kw):
        assert url.endswith("/models")
        return httpx.Response(200, json={"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4o"}]}, request=httpx.Request("GET", url))

    monkeypatch.setattr(llm.httpx, "get", fake_get)
    cfg = ModelConfig(base_url="https://mock.example/v1", api_key="sk-test", model="gpt-4o-mini")
    r = probe_connection(cfg)
    assert r["ok"] is True and r["exact_match"] is True
    assert set(r["detected"]) == {"gpt-4o-mini", "gpt-4o"}


def test_probe_closest_match_hint(monkeypatch) -> None:
    def fake_get(url, **kw):
        return httpx.Response(200, json={"data": [{"id": "deepseek-chat-v3"}, {"id": "other"}]}, request=httpx.Request("GET", url))

    monkeypatch.setattr(llm.httpx, "get", fake_get)
    r = probe_connection(ModelConfig(base_url="https://x/v1", api_key="k", model="deepseek-chat"))
    assert r["ok"] is True and r["exact_match"] is False
    assert "closest" in r["message"]


def test_probe_auth_rejected_and_unreachable(monkeypatch) -> None:
    monkeypatch.setattr(llm.httpx, "get", lambda url, **kw: httpx.Response(401, json={}, request=httpx.Request("GET", url)))
    assert probe_connection(CFG)["ok"] is False

    def boom(url, **kw):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(llm.httpx, "get", boom)
    r = probe_connection(CFG)
    assert r["ok"] is False and "unreachable" in r["message"]


def test_probe_gateway_without_models(monkeypatch) -> None:
    monkeypatch.setattr(llm.httpx, "get", lambda url, **kw: httpx.Response(404, request=httpx.Request("GET", url)))
    r = probe_connection(CFG)
    assert r["ok"] is True and r["detected"] is None


# ------------------------------------------------------------------ discover

def _fake_gh_search(monkeypatch, repos_by_topic: dict[str, list[dict]]) -> None:
    def fake_get(url, params=None, **kw):
        topic = params["q"].split("topic:")[1]
        items = repos_by_topic.get(topic, [])
        return httpx.Response(200, json={"items": items}, request=httpx.Request("GET", url))

    monkeypatch.setattr(discover, "_gh_get", fake_get)


def test_search_merges_topics_ranks_by_stars_and_audits(tmp_path: Path, monkeypatch) -> None:
    discover.CACHE_PATH = tmp_path / "cache.json"  # isolate cache
    _fake_gh_search(
        monkeypatch,
        {
            "claude-skill": [{"full_name": "a/one", "html_url": "https://github.com/a/one", "stargazers_count": 5, "description": "d1"}],
            "agent-skills": [
                {"full_name": "b/two", "html_url": "https://github.com/b/two", "stargazers_count": 99, "description": "d2"},
                {"full_name": "a/one", "html_url": "https://github.com/a/one", "stargazers_count": 5, "description": "d1"},
            ],
        },
    )
    monkeypatch.setattr(discover, "audit_remote_repo", lambda name, wd: {"badge": "pass", "detail": "no findings", "skills": [{"name": "x", "badge": "pass", "detail": "", "summary": "audit: PASS"}]})

    r = discover.search_skills("pdf", limit=2, use_cache=False)
    assert [x["full_name"] for x in r["results"]] == ["b/two", "a/one"]  # deduped, star-ranked
    assert all(x["audit"]["badge"] == "pass" for x in r["results"])
    assert r["degraded"] is False


def test_search_cache_hit_skips_network(tmp_path: Path, monkeypatch) -> None:
    discover.CACHE_PATH = tmp_path / "cache.json"
    cache = {"pdf": {"ts": __import__("time").time(), "payload": {"results": [{"full_name": "cached/repo"}], "rate_limited": False, "degraded": False, "message": ""}}}
    discover.CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")

    def forbidden(url, params=None, **kw):
        raise AssertionError("network must not be hit on cache hit")

    monkeypatch.setattr(discover, "_gh_get", forbidden)
    r = discover.search_skills("pdf", use_cache=True)
    assert r["cached"] is True and r["results"][0]["full_name"] == "cached/repo"


def test_search_rate_limit_degrades_to_unaudited(tmp_path: Path, monkeypatch) -> None:
    discover.CACHE_PATH = tmp_path / "cache.json"

    def forbidden(url, params=None, **kw):
        return httpx.Response(403, json={}, request=httpx.Request("GET", url))

    monkeypatch.setattr(discover, "_gh_get", forbidden)
    r = discover.search_skills("pdf", use_cache=False)
    assert r["rate_limited"] is True and r["degraded"] is True
    assert "手动" in r["message"]
    assert discover.CACHE_PATH.exists() is False  # degraded results must not poison the cache


def test_badge_mapping() -> None:
    class F:
        def __init__(self, s):
            self.severity = s

    assert discover._badge_for([])["badge"] == "pass"
    assert discover._badge_for([F("HIGH"), F("LOW")])["badge"] == "findings"
    b = discover._badge_for([F("CRITICAL")])
    assert b["badge"] == "blocked" and b["blocked"] is True
