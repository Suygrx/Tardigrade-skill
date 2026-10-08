"""Home page endpoints: /api/installed, /api/uninstall + install tracking."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tardigrade_skill import adapt_llm

REPO = Path(__file__).resolve().parents[1]


def _client() -> TestClient:
    from server.app import create_app

    return TestClient(create_app())


@pytest.fixture()
def isolated_store(tmp_path: Path, monkeypatch):
    adapt_llm.reset_store()
    monkeypatch.setattr(adapt_llm, "HOME_DIR", tmp_path / "tgd")
    monkeypatch.setattr(adapt_llm, "ADAPTERS_DIR", tmp_path / "tgd" / "adapters")
    monkeypatch.setattr(adapt_llm, "DB_PATH", tmp_path / "tgd" / "desktop.db")
    # isolate dispatch targets too: tests must never write into the real
    # ~/.codex/skills etc., and /api/installed's external-scan must see only
    # what the test itself installed
    import tardigrade_skill.dispatcher as dispatcher

    monkeypatch.setattr(
        dispatcher,
        "target_dir",
        lambda agent, project: tmp_path / "agents" / agent / ("project" if project else "global"),
    )
    yield


def test_install_records_and_home_lists(monkeypatch, tmp_path: Path, isolated_store) -> None:
    c = _client()
    r = c.post("/api/install", json={"source": str(REPO / "demo" / "skills" / "pdf-helper"), "agent": "claude-code"})
    assert r.json()["results"][0]["ok"] is True

    home = c.get("/api/installed").json()
    claude = next(p for p in home["platforms"] if p["agent"] == "claude-code")
    assert len(claude["skills"]) == 1
    rec = claude["skills"][0]
    assert rec["skill"] == "pdf-helper"
    assert rec["present"] is True  # dest exists on disk
    # other platforms have zero installs
    codex = next(p for p in home["platforms"] if p["agent"] == "codex")
    assert codex["skills"] == []


def test_uninstall_removes_dir_and_record(monkeypatch, tmp_path: Path, isolated_store) -> None:
    c = _client()
    c.post("/api/install", json={"source": str(REPO / "demo" / "skills" / "pdf-helper"), "agent": "claude-code"})
    dest = Path(next(p for p in c.get("/api/installed").json()["platforms"] if p["agent"] == "claude-code")["skills"][0]["dest"])
    assert dest.is_dir()

    r = c.post("/api/uninstall", json={"skill": "pdf-helper", "agent": "claude-code"})
    assert r.json()["ok"] is True
    assert not dest.exists()
    assert c.get("/api/installed").json()["platforms"][0]["skills"] == []

    # second uninstall -> 404 (no managed record)
    assert c.post("/api/uninstall", json={"skill": "pdf-helper", "agent": "claude-code"}).status_code == 404


def test_uninstall_refuses_outside_managed_root(monkeypatch, tmp_path: Path, isolated_store) -> None:
    adapt_llm.record_install("evil", "claude-code", Path("C:/Windows/System32/evil"), source="x")
    r = _client().post("/api/uninstall", json={"skill": "evil", "agent": "claude-code"})
    assert r.json()["ok"] is False
    assert "refusing" in r.json()["message"]


def test_apply_also_records(monkeypatch, tmp_path: Path, isolated_store) -> None:
    c = _client()
    r = c.post("/api/apply", json={"root": str(REPO / "demo" / "skills"), "agent": "codex", "skills": ["log-cleaner"]})
    assert r.json()["results"][0]["ok"] is True  # full* tier is one-click applicable
    codex = next(p for p in c.get("/api/installed").json()["platforms"] if p["agent"] == "codex")
    assert [s["skill"] for s in codex["skills"]] == ["log-cleaner"]


def test_installed_reports_detected(monkeypatch, tmp_path: Path, isolated_store) -> None:
    """Platforms report detected=True only when their config dir exists (cc-switch pill)."""
    from tardigrade_skill.dispatcher import DETECT_DIRS

    monkeypatch.setitem(DETECT_DIRS, "codex", str(tmp_path / "codex-home"))
    monkeypatch.setitem(DETECT_DIRS, "claude-code", str(tmp_path / "claude-home"))
    (tmp_path / "codex-home").mkdir()
    c = _client()
    platforms = {p["agent"]: p["detected"] for p in c.get("/api/installed").json()["platforms"]}
    assert platforms["codex"] is True
    assert platforms["claude-code"] is False
    assert len(platforms) >= 18


def test_import_local_skill(tmp_path: Path, isolated_store) -> None:
    from types import SimpleNamespace

    import sys

    app_module = sys.modules["server.app"]

    c = _client()
    src = REPO / "demo" / "skills" / "pdf-helper"

    r = c.post("/api/import", json={"path": str(src), "agent": "codex"})
    assert r.status_code == 200 and r.json()["ok"] is True
    # new semantics: import archives into the skill library (no direct platform install)
    assert r.json()["dir"] and Path(r.json()["dir"]).is_dir()
    assert r.json()["skill"] == "pdf-helper"
    lib = c.get("/api/library").json()
    assert any(s["name"] == "pdf-helper" for s in lib["skills"])

    # no SKILL.md -> rejected
    empty = tmp_path / "not-a-skill"
    empty.mkdir()
    assert c.post("/api/import", json={"path": str(empty), "agent": "codex"}).status_code == 400

    # CRITICAL audit finding -> blocked
    def bad_audit(_):
        return SimpleNamespace(findings=[SimpleNamespace(severity="CRITICAL", message="x")], summary=lambda: "")

    monkey = __import__("pytest").MonkeyPatch()
    monkey.setattr(app_module, "run_audit", bad_audit)
    try:
        r = c.post("/api/import", json={"path": str(src), "agent": "codex"})
        assert r.status_code == 400 and "拦截" in r.json()["detail"]
    finally:
        monkey.undo()
