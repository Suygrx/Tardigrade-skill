"""tardigrade-skill desktop server: thin FastAPI layer over the core engine.

No business logic lives here — every endpoint delegates to tardigrade_skill core
modules (spec / audit / ir / profiles / adapt / installer / dispatcher / lockfile).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tardigrade_skill import adapt_llm
from tardigrade_skill import discover
from tardigrade_skill import llm as llm_module
from tardigrade_skill.adapt import judge_skill
from tardigrade_skill.audit import run_audit
from tardigrade_skill.dispatcher import DispatchError, dispatch
from tardigrade_skill.installer import find_skill_dirs as scan_skill_dirs
from tardigrade_skill.installer import resolve_source, SourceError
from tardigrade_skill.ir import SkillIR, build_ir
from tardigrade_skill.lockfile import LockFile, build_entry
from tardigrade_skill.profiles import default_profiles_dir, load_profiles
from tardigrade_skill.spec import SpecError, validate_skill

from .version import __version__


# Request bodies live at module level: FastAPI resolves type hints against module
# globals, and function-local models break under `from __future__ import annotations`.
class RootsBody(BaseModel):
    roots: list[str] | None = None


class AuditBody(BaseModel):
    path: str


class ApplyBody(BaseModel):
    root: str
    agent: str
    skills: list[str]


class SettingsBody(BaseModel):
    roots: list[str]


class AdaptBody(BaseModel):
    skill: str
    agent: str


class AdaptationIdBody(BaseModel):
    id: str


class LlmConfigBody(BaseModel):
    base_url: str
    api_key: str
    model: str


class SearchBody(BaseModel):
    query: str
    limit: int = 5


class InstallBody(BaseModel):
    source: str
    agent: str


class UninstallBody(BaseModel):
    skill: str
    agent: str


def _find_demo_roots() -> list[Path]:
    import sys

    if getattr(sys, "frozen", False):  # bundled app: no demo dir, roots come from settings
        return []
    repo = Path(__file__).resolve().parents[1]
    demo = repo / "demo" / "skills"
    return [demo] if demo.is_dir() else []


def _static_dir() -> Path:
    import sys

    if getattr(sys, "frozen", False):  # PyInstaller: bundled as <_MEIPASS>/static
        return Path(getattr(sys, "_MEIPASS")) / "static"
    return Path(__file__).resolve().parents[1] / "desktop" / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="Tardigrade-skill desktop", version=__version__)
    profiles = load_profiles(default_profiles_dir())
    state = {"roots": [str(p) for p in _find_demo_roots()], "lock_root": Path(__file__).resolve().parents[1]}

    # ------------------------------------------------------------- helpers

    def _scan_skills(roots: list[str]) -> list[Path]:
        dirs: list[Path] = []
        for root in roots:
            dirs.extend(scan_skill_dirs(Path(root)))
        seen: set[str] = set()
        unique: list[Path] = []
        for d in dirs:
            key = str(d.resolve())
            if key not in seen:
                seen.add(key)
                unique.append(d)
        return sorted(unique, key=lambda p: p.name)

    def _roots_or_400(roots: list[str] | None) -> list[str]:
        rs = [str(Path(r)) for r in (roots if roots else state["roots"])]
        if not rs:
            raise HTTPException(400, "no skill roots configured")
        return rs

    # ------------------------------------------------------------- meta

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/api/targets")
    def targets() -> dict:
        return {
            "targets": [
                {
                    "id": p.id,
                    "name": p.name,
                    "discovery": p.discovery,
                    "capabilities": {k: v.model_dump() for k, v in p.capabilities.items()},
                    "script_runtime": p.script_runtime,
                    "notes": p.notes,
                }
                for p in profiles.values()
            ]
        }

    # ------------------------------------------------------------- skills

    @app.post("/api/skills")
    def skills(body: RootsBody) -> dict:
        rs = _roots_or_400(body.roots)
        out = []
        for d in _scan_skills(rs):
            problems = validate_skill(d)
            item = {"name": d.name, "dir": str(d), "valid": not problems, "problems": problems}
            if not problems:
                try:
                    ir: SkillIR = build_ir(d)
                    item.update(
                        {
                            "description": ir.description,
                            "requires": ir.requires,
                            "evidence": ir.evidence,
                            "tools": [{"tool": t.tool, "pattern": t.pattern} for t in ir.allowed_tools],
                            "blocks": len(ir.blocks),
                            "scripts": ir.scripts,
                            "body_chars": ir.body_chars,
                        }
                    )
                except SpecError:
                    pass
            out.append(item)
        return {"skills": out, "roots": rs}

    @app.post("/api/audit")
    def audit(body: AuditBody) -> dict:
        path = Path(body.path)
        if not path.is_dir():
            raise HTTPException(400, f"not a directory: {path}")
        report = run_audit(path)
        return {
            "summary": report.summary(),
            "blocked": report.blocked,
            "findings": [
                {"rule_id": f.rule_id, "severity": f.severity, "file": f.file, "line": f.line, "message": f.message}
                for f in report.findings
            ],
        }

    # ------------------------------------------------------------- matrix

    @app.post("/api/matrix")
    def matrix(body: RootsBody) -> dict:
        rs = _roots_or_400(body.roots)
        rows = []
        for d in _scan_skills(rs):
            cells = [judge_skill(d, p).to_dict() for p in profiles.values()]
            problems = validate_skill(d)
            rows.append({"skill": d.name, "dir": str(d), "valid": not problems, "cells": cells})
        return {
            "platforms": [{"id": p.id, "name": p.name} for p in profiles.values()],
            "rows": rows,
            "roots": rs,
        }

    # ------------------------------------------------------------- apply (one click)

    @app.post("/api/apply")
    def apply(body: ApplyBody) -> dict:
        if body.agent not in profiles:
            raise HTTPException(400, f"unknown agent '{body.agent}'")
        profile = profiles[body.agent]
        results = []
        skill_dirs = {d.name: d for d in _scan_skills([body.root])}
        lock = LockFile.load(state["lock_root"])
        for name in body.skills:
            d = skill_dirs.get(name)
            if d is None:
                results.append({"skill": name, "ok": False, "message": "not found in roots"})
                continue
            problems = validate_skill(d)
            if problems:
                results.append({"skill": name, "ok": False, "message": problems[0]})
                continue
            report = run_audit(d)
            if report.blocked:
                results.append({"skill": name, "ok": False, "message": f"blocked by audit gate: {report.summary()}"})
                continue
            judgment = judge_skill(d, profile)
            if judgment.tier not in {"full", "full*"}:
                results.append(
                    {"skill": name, "ok": False, "message": f"tier is '{judgment.tier}', not one-click applicable"}
                )
                continue
            try:
                dest = dispatch(d, body.agent)
            except DispatchError as e:
                results.append({"skill": name, "ok": False, "message": str(e)})
                continue
            adapt_llm.record_install(name, body.agent, dest, source=f"apply:{d}")
            lock.record(build_entry(name, f"apply:{d}", d))
            results.append({"skill": name, "ok": True, "tier": judgment.tier, "dest": str(dest)})
        lock_path = lock.save(state["lock_root"])
        return {"results": results, "lockfile": str(lock_path)}

    # ------------------------------------------------------------- settings

    @app.get("/api/settings")
    def get_settings() -> dict:
        return {"roots": state["roots"]}

    @app.post("/api/settings")
    def set_settings(body: SettingsBody) -> dict:
        state["roots"] = body.roots
        return {"roots": state["roots"]}

    # ------------------------------------------------------------- L2 adaptation (BYOK)

    @app.get("/api/llm-status")
    def llm_status() -> dict:
        cfg = llm_module.load_model_config()
        return {"configured": cfg is not None, **(cfg.public_view() if cfg else {})}

    @app.post("/api/adapt")
    def adapt(body: AdaptBody) -> dict:
        if body.agent not in profiles:
            raise HTTPException(400, f"unknown agent '{body.agent}'")
        skill_dirs = {d.name: d for d in _scan_skills(_roots_or_400(None))}
        d = skill_dirs.get(body.skill)
        if d is None:
            raise HTTPException(404, f"skill '{body.skill}' not found in roots")
        judgment = judge_skill(d, profiles[body.agent])
        if judgment.tier != "adapted":
            raise HTTPException(400, f"tier is '{judgment.tier}', only 'adapted' cells run the LLM engine")
        result = adapt_llm.adapt_skill(d, profiles[body.agent])
        result["judgment"] = judgment.to_dict()
        return result

    @app.get("/api/adaptations")
    def adaptations(status: str | None = None) -> dict:
        return {"adaptations": adapt_llm.list_adaptations(status)}

    @app.post("/api/adaptations/confirm")
    def adaptations_confirm(body: AdaptationIdBody) -> dict:
        return adapt_llm.confirm_adaptation(body.id, dispatch_fn=dispatch)

    @app.post("/api/adaptations/reject")
    def adaptations_reject(body: AdaptationIdBody) -> dict:
        return adapt_llm.reject_adaptation(body.id)

    # ------------------------------------------------------------- LLM config (user-provided, auto-probed)

    @app.post("/api/llm/config")
    def llm_config(body: LlmConfigBody) -> dict:
        """Save the user-provided endpoint/key/model, then auto-probe it."""
        if not (body.base_url.strip() and body.api_key.strip() and body.model.strip()):
            raise HTTPException(400, "base_url, api_key and model are all required")
        cfg_path = llm_module.save_model_config(body.base_url, body.api_key, body.model)
        cfg = llm_module.load_model_config(cfg_path)
        probe = llm_module.test_connection(cfg)
        return {"saved": True, "path": str(cfg_path), **probe}

    @app.post("/api/llm/test")
    def llm_test() -> dict:
        cfg = llm_module.load_model_config()
        if cfg is None:
            raise HTTPException(400, "no model configured yet")
        return llm_module.test_connection(cfg)

    # ------------------------------------------------------------- discovery (search = audit)

    @app.post("/api/search")
    def search(body: SearchBody) -> dict:
        return discover.search_skills(body.query, limit=max(1, min(body.limit, 10)))

    # ------------------------------------------------------------- home: installed per platform

    @app.get("/api/installed")
    def installed() -> dict:
        """Per-platform listing of skills installed via Tardigrade (CC Switch home).

        `detected` = the platform's config dir exists on this machine, so the
        UI can show only platforms the user actually has (cc-switch behavior).
        """
        from tardigrade_skill.dispatcher import detect_platforms

        detected = detect_platforms()
        all_installs = adapt_llm.list_installs()
        out = []
        for p in profiles.values():
            items = []
            for rec in all_installs:
                if rec["agent"] != p.id:
                    continue
                dest = Path(rec["dest"])
                present = dest.is_dir()
                items.append({**rec, "present": present})
            out.append({"agent": p.id, "name": p.name, "discovery": p.discovery, "detected": detected.get(p.id, False), "skills": items})
        return {"platforms": out}

    @app.post("/api/uninstall")
    def uninstall(body: UninstallBody) -> dict:
        """Remove a managed install. Only dirs under the agent's own skills root are touched."""
        from tardigrade_skill.dispatcher import target_dir

        dest = adapt_llm.drop_install(body.skill, body.agent)
        if dest is None:
            raise HTTPException(404, f"no managed install for {body.skill} -> {body.agent}")
        dest_path = Path(dest)
        try:
            root = target_dir(body.agent, project=False)
            inside = str(dest_path.resolve()).startswith(str(root.expanduser().resolve()))
        except Exception:
            inside = False
        if not inside:
            return {"ok": False, "message": f"refusing: {dest} is not under the managed skills root"}
        import shutil

        if dest_path.is_dir():
            shutil.rmtree(dest_path)
        return {"ok": True, "removed": str(dest_path)}

    @app.post("/api/install")
    def install(body: InstallBody) -> dict:
        """Full audited install pipeline for remote/local sources (discovery -> platform)."""
        if body.agent not in profiles:
            raise HTTPException(400, f"unknown agent '{body.agent}'")
        import tempfile

        with tempfile.TemporaryDirectory(prefix="tardigrade-install-") as tmp:
            workdir = Path(tmp)
            try:
                root, source_desc, resolved_sha = resolve_source(body.source, workdir)
            except SourceError as e:
                raise HTTPException(400, f"source error: {e}")
            skill_dirs = scan_skill_dirs(root)
            if not skill_dirs:
                raise HTTPException(400, "no skill directories found (no SKILL.md within 2 levels)")
            profile = profiles[body.agent]
            lock = LockFile.load(state["lock_root"])
            results = []
            for d in skill_dirs:
                problems = validate_skill(d)
                if problems:
                    results.append({"skill": d.name, "ok": False, "message": problems[0]})
                    continue
                report = run_audit(d)
                if report.blocked:
                    results.append(
                        {"skill": d.name, "ok": False, "message": f"blocked by audit gate: {report.summary()}", "audit": report.summary()}
                    )
                    continue
                judgment = judge_skill(d, profile)
                if judgment.tier not in {"full", "full*"}:
                    results.append(
                        {"skill": d.name, "ok": False, "message": f"tier is '{judgment.tier}'; run the L2 adaptation flow for this platform"}
                    )
                    continue
                try:
                    dest = dispatch(d, body.agent)
                except DispatchError as e:
                    results.append({"skill": d.name, "ok": False, "message": str(e)})
                    continue
                adapt_llm.record_install(d.name, body.agent, dest, source=source_desc)
                lock.record(build_entry(d.name, source_desc, d, resolved_sha=resolved_sha))
                results.append({"skill": d.name, "ok": True, "tier": judgment.tier, "dest": str(dest)})
            lock_path = lock.save(state["lock_root"])
            return {"results": results, "lockfile": str(lock_path)}

    # ------------------------------------------------------------- static frontend

    static_dir = _static_dir()
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


app = create_app()
