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
    (tmp_path / "codex-home" / "config.json").write_text("{}", encoding="utf-8")  # 非空才算安装
    (tmp_path / "claude-home").mkdir()  # 空壳目录 -> 未安装
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


def test_library_delete_and_open_url(tmp_path: Path, isolated_store) -> None:
    c = _client()
    c.post("/api/settings", json={"roots": [], "download_dir": str(tmp_path / "lib")})

    r = c.post("/api/import", json={"path": str(REPO / "demo" / "skills" / "pdf-helper")})
    assert r.status_code == 200
    assert any(s["name"] == "pdf-helper" for s in c.get("/api/library").json()["skills"])

    # delete refuses paths outside the library
    assert c.post("/api/library/delete", json={"name": "../../etc"}).status_code == 400
    assert c.post("/api/library/delete", json={"name": "nope"}).json()["ok"] is False

    r = c.post("/api/library/delete", json={"name": "pdf-helper"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert not any(s["name"] == "pdf-helper" for s in c.get("/api/library").json()["skills"])

    # open-url only allows http/https
    assert c.post("/api/open-url", json={"url": "file:///C:/Windows"}).status_code == 400


def test_uninstall_unmanaged_skill(tmp_path: Path, isolated_store, monkeypatch) -> None:
    """非托管（本机已有）skill 也能统一管理卸载：按平台根目录定位删除。"""
    import shutil as _shutil

    import tardigrade_skill.dispatcher as dispatcher
    from tardigrade_skill.dispatcher import target_dir

    c = _client()
    monkeypatch.setattr(
        dispatcher, "target_dir",
        lambda agent, project: tmp_path / "agents" / agent / ("project" if project else "global"),
    )
    fake_root = tmp_path / "agents" / "codex" / "global"
    src = REPO / "demo" / "skills" / "pdf-helper"
    dest = fake_root / "pdf-helper"
    _shutil.copytree(src, dest)
    assert dest.is_dir()
    installed_rows = [i for p in c.get("/api/installed").json()["platforms"] for i in p["skills"] if i["skill"] == "pdf-helper"]
    assert len(installed_rows) == 1 and installed_rows[0]["managed"] is False  # 无安装记录 -> 非托管

    r = c.post("/api/uninstall", json={"skill": "pdf-helper", "agent": "codex"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert not dest.exists()

    # 平台根外的路径拒绝（越权守卫）
    outside = tmp_path / "outside"
    _shutil.copytree(src, outside)
    r2 = c.post("/api/uninstall", json={"skill": "outside", "agent": "codex"})
    assert r2.status_code == 404
    assert outside.exists()


def test_detect_platforms_requires_nonempty_dir(monkeypatch, tmp_path: Path) -> None:
    """空壳配置目录（卸载残留/误创建）不应判定为已安装。"""
    import tardigrade_skill.dispatcher as dispatcher

    real = tmp_path / "real"
    empty = tmp_path / "empty"
    real.mkdir()
    (real / "settings.json").write_text("{}", encoding="utf-8")
    empty.mkdir()
    monkeypatch.setattr(dispatcher, "DETECT_DIRS", {"codex": str(real), "kilo": str(empty), "trae": str(tmp_path / "missing")})
    out = dispatcher.detect_platforms()
    assert out == {"codex": True, "kilo": False, "trae": False}


def test_adapt_batch_buckets(tmp_path: Path, isolated_store) -> None:
    """批量适配分桶：full 直接安装，adapted 进待确认（mock LLM），其余跳过。"""
    from types import SimpleNamespace
    import sys

    c = _client()  # 先触发 server.app 导入
    app_module = sys.modules["server.app"]
    c.post("/api/settings", json={"roots": [str(REPO / "demo" / "skills")], "download_dir": str(tmp_path / "lib")})

    def fake_judge(skill_dir, profile):
        return SimpleNamespace(
            agent=profile.id, skill=Path(skill_dir).name,
            tier="full" if profile.id == "codex" else ("partial" if profile.id == "droid" else "adapted"),
            reasons=[], gaps=["auto-trigger"] if profile.id != "codex" else [], caveats=[],
            resident_tokens=10, to_dict=lambda: {},
        )

    orig_judge = app_module.judge_skill
    orig_adapt = app_module.adapt_llm.adapt_skill
    app_module.judge_skill = fake_judge
    app_module.adapt_llm.adapt_skill = lambda skill_dir, profile, config=None, language="zh": {
        "status": "pending", "id": "fake123", "recheck": "full", "message": ""
    }
    try:
        r = c.post("/api/adapt-batch", json={"skill": "pdf-helper", "agents": ["codex", "workbuddy", "droid"]})
        assert r.status_code == 200
        data = r.json()
        by_agent = {x["agent"]: x for x in data["results"]}
        assert by_agent["codex"]["action"] == "installed"          # full 桶：直接安装
        assert by_agent["workbuddy"]["action"] == "pending"        # adapted 桶：进待确认
        assert by_agent["droid"]["action"] == "skipped"            # 无脚本运行时：跳过
        assert data["summary"]["installed"] == 1 and data["summary"]["pending"] == 1
        assert Path(by_agent["codex"]["dest"]).is_dir()
    finally:
        app_module.judge_skill = orig_judge
        app_module.adapt_llm.adapt_skill = orig_adapt
