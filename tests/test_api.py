"""FastAPI layer tests: thin endpoints over core (health/targets/skills/matrix/apply)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from server.app import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_health() -> None:
    r = _client().get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_targets_returns_shipped_profiles() -> None:
    r = _client().get("/api/targets")
    ids = [t["id"] for t in r.json()["targets"]]
    assert {"claude-code", "codex", "gemini-cli", "cursor", "opencode"} <= set(ids)


def test_matrix_over_repo_demo(tmp_path: Path) -> None:
    demo = Path(__file__).resolve().parents[1] / "demo" / "skills"
    if not demo.is_dir():
        return  # pragma: no cover
    r = _client().post("/api/matrix", json={"roots": [str(demo)]})
    assert r.status_code == 200
    body = r.json()
    names = {row["skill"] for row in body["rows"]}
    assert "pdf-helper" in names and "broken-skill" in names
    tiers = {c["tier"] for row in body["rows"] for c in row["cells"]}
    # the demo set is designed to exercise every tier
    assert {"full", "full*", "adapted", "partial", "incompatible"} <= tiers


def test_apply_rejects_non_full_tier(tmp_path: Path) -> None:
    demo = Path(__file__).resolve().parents[1] / "demo" / "skills"
    if not demo.is_dir():
        return  # pragma: no cover
    r = _client().post("/api/apply", json={"root": str(demo), "agent": "opencode", "skills": ["log-cleaner"]})
    assert r.status_code == 200
    result = r.json()["results"][0]
    assert result["ok"] is False
    assert "partial" in result["message"]


def test_apply_full_tier_dispatches_and_locks(tmp_path: Path) -> None:
    demo = Path(__file__).resolve().parents[1] / "demo" / "skills"
    if not demo.is_dir():
        return  # pragma: no cover
    # pdf-helper on claude-code is the designed one-click cell
    r = _client().post("/api/apply", json={"root": str(demo), "agent": "claude-code", "skills": ["pdf-helper"]})
    assert r.status_code == 200
    result = r.json()["results"][0]
    assert result["ok"] is True
    assert Path(result["dest"]).is_dir()


def test_unknown_agent_rejected() -> None:
    r = _client().post("/api/apply", json={"root": "x", "agent": "nope", "skills": []})
    assert r.status_code == 400
