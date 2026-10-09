"""tardigrade-skill desktop server: thin FastAPI layer over the core engine.

No business logic lives here — every endpoint delegates to tardigrade_skill core
modules (spec / audit / ir / profiles / adapt / installer / dispatcher / lockfile).
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tardigrade_skill import adapt_llm
from tardigrade_skill import discover
from tardigrade_skill import llm as llm_module
from tardigrade_skill.adapt import judge_skill
from tardigrade_skill.audit import run_audit
from tardigrade_skill.dispatcher import DispatchError, TARGETS, dispatch, target_dir
from tardigrade_skill.installer import find_skill_dirs as scan_skill_dirs
from tardigrade_skill.installer import resolve_source, SourceError


# Request bodies must live at module level: app.py uses `from __future__ import
# annotations`, and FastAPI resolves string annotations against module globals —
# a nested class would make the body param degrade to a query param (422).
class UninstallBody(BaseModel):
    skill: str
    agent: str


class ImportBody(BaseModel):
    path: str
    agent: str = ""  # legacy field; import now archives into the library, not a platform

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
    download_dir: str | None = None
    language: str | None = None  # zh | en


class AdaptBody(BaseModel):
    skill: str
    agent: str
    dir: str | None = None  # library/任意允许目录下的 skill 源目录（管理页开关触发适配时使用）


class AdaptBatchBody(BaseModel):
    skill: str
    dir: str | None = None
    agents: list[str] | None = None  # 缺省 = 本机检测到的全部平台


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


class DownloadBody(BaseModel):
    source: str


class ToggleBody(BaseModel):
    dir: str
    agent: str


class LibraryDeleteBody(BaseModel):
    name: str


class OpenUrlBody(BaseModel):
    url: str


class SkillDetailBody(BaseModel):
    path: str


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
    # 默认落到当前用户的下载目录（需求指定），设置页可改
    default_download_dir = str(Path("~/Downloads/Tardigrade-skills").expanduser())
    state = {
        "roots": [str(p) for p in _find_demo_roots()],
        "lock_root": Path(__file__).resolve().parents[1],
        "download_dir": default_download_dir,  # 市场/导入的 skill 落库目录（设置可改）
        "language": "zh",  # UI 与 LLM 适配产物的说明语言（zh | en）
    }

    def _library_meta_path() -> Path:
        return Path(state["download_dir"]) / ".library-meta.json"

    def _load_library_meta() -> dict:
        try:
            return json.loads(_library_meta_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_library_meta(meta: dict) -> None:
        try:
            Path(state["download_dir"]).mkdir(parents=True, exist_ok=True)
            _library_meta_path().write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

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
        return {"roots": state["roots"], "download_dir": state["download_dir"], "language": state["language"]}

    @app.post("/api/settings")
    def set_settings(body: SettingsBody) -> dict:
        state["roots"] = body.roots
        if body.download_dir:
            state["download_dir"] = body.download_dir
        if body.language in {"zh", "en"}:
            state["language"] = body.language
        return {"roots": state["roots"], "download_dir": state["download_dir"], "language": state["language"]}

    # ------------------------------------------------------------- L2 adaptation (BYOK)

    @app.get("/api/llm-status")
    def llm_status() -> dict:
        cfg = llm_module.load_model_config()
        if cfg is None:
            return {"configured": False}
        masked = cfg.api_key[:3] + "****" + cfg.api_key[-4:] if len(cfg.api_key) > 7 else "****"
        return {"configured": True, **cfg.public_view(), "api_key_masked": masked}

    @app.post("/api/adapt")
    def adapt(body: AdaptBody) -> dict:
        if body.agent not in profiles:
            raise HTTPException(400, f"unknown agent '{body.agent}'")
        if body.dir:
            d = Path(body.dir).expanduser()
            if not (d / "SKILL.md").is_file():
                raise HTTPException(400, "该目录没有 SKILL.md，不是有效的 skill")
        else:
            scan_roots = [r for r in [*state["roots"], state["download_dir"]] if Path(r).is_dir()]
            skill_dirs = {dd.name: dd for dd in _scan_skills(scan_roots)}
            d = skill_dirs.get(body.skill)
            if d is None:
                raise HTTPException(404, f"skill '{body.skill}' not found in roots or library")
        judgment = judge_skill(d, profiles[body.agent])
        if judgment.tier != "adapted":
            raise HTTPException(400, f"tier is '{judgment.tier}', only 'adapted' cells run the LLM engine")
        result = adapt_llm.adapt_skill(d, profiles[body.agent], language=state["language"])
        result["judgment"] = judgment.to_dict()
        return result

    @app.post("/api/adapt-batch")
    def adapt_batch(body: AdaptBatchBody) -> dict:
        """单 skill × 多平台批量适配（方案 C 分桶）。

        full/full* → 直接 dispatch 安装（与开关语义一致，0 token）；
        adapted    → 每平台 1 次 L2 调用，产物进待确认；
        其余       → 跳过并给出原因。
        """
        from concurrent.futures import ThreadPoolExecutor

        from tardigrade_skill.dispatcher import DispatchError, detect_platforms, dispatch

        if body.dir:
            d = Path(body.dir).expanduser()
            if not (d / "SKILL.md").is_file():
                raise HTTPException(400, "该目录没有 SKILL.md，不是有效的 skill")
        else:
            scan_roots = [r for r in [*state["roots"], state["download_dir"]] if Path(r).is_dir()]
            skill_dirs = {dd.name: dd for dd in _scan_skills(scan_roots)}
            d = skill_dirs.get(body.skill)
            if d is None:
                raise HTTPException(404, f"skill '{body.skill}' not found in roots or library")

        targets = body.agents or [a for a, ok in detect_platforms().items() if ok]
        targets = [a for a in targets if a in profiles]
        if not targets:
            raise HTTPException(400, "没有可适配的目标平台")

        def one(agent: str) -> dict:
            profile = profiles[agent]
            try:
                judgment = judge_skill(d, profile)
            except Exception as e:
                return {"agent": agent, "action": "error", "message": str(e)}
            if judgment.tier in {"full", "full*"}:
                try:
                    dest = dispatch(d, agent)
                    adapt_llm.record_install(d.name, agent, dest, source=f"adapt-batch:{d}")
                    return {"agent": agent, "tier": judgment.tier, "action": "installed", "dest": str(dest)}
                except DispatchError as e:
                    return {"agent": agent, "tier": judgment.tier, "action": "error", "message": str(e)}
            if judgment.tier == "adapted":
                r = adapt_llm.adapt_skill(d, profile, language=state["language"])
                return {"agent": agent, "tier": judgment.tier, "action": r.get("status", "failed"),
                        "id": r.get("id"), "recheck": r.get("recheck"), "message": r.get("message")}
            return {"agent": agent, "tier": judgment.tier, "action": "skipped", "reasons": judgment.reasons}

        with ThreadPoolExecutor(max_workers=4) as ex:
            results = list(ex.map(one, targets))
        summary = {}
        for r in results:
            summary[r["action"]] = summary.get(r["action"], 0) + 1
        return {"ok": True, "skill": d.name, "results": results, "summary": summary}

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
        """Save the user-provided endpoint/key/model, then auto-probe it.

        api_key 为空表示沿用已保存的 key（表单回填时密钥不打码回显，留空即保持不变）。
        """
        if not (body.base_url.strip() and body.model.strip()):
            raise HTTPException(400, "base_url and model are required")
        api_key = body.api_key.strip()
        if not api_key:
            existing = llm_module.load_model_config()
            if existing is None:
                raise HTTPException(400, "api_key is required on first setup")
            api_key = existing.api_key
        cfg_path = llm_module.save_model_config(body.base_url, api_key, body.model)
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
        """Per-platform listing of skills (CC Switch home).

        Each platform merges two sources:
        - managed: installs recorded by Tardigrade (uninstallable)
        - external: SKILL.md dirs already present in the platform's own
          skills directory, installed outside Tardigrade (shown, not
          uninstallable — we don't touch what we didn't install)
        `detected` = the platform's config dir exists on this machine.
        """
        from tardigrade_skill.dispatcher import detect_platforms, target_dir

        detected = detect_platforms()
        all_installs = adapt_llm.list_installs()
        out = []
        for p in profiles.values():
            items = []
            managed_dests: set[str] = set()
            for rec in all_installs:
                if rec["agent"] != p.id:
                    continue
                dest = Path(rec["dest"])
                present = dest.is_dir()
                if present:
                    managed_dests.add(str(dest.resolve()).lower())
                items.append({**rec, "present": present, "managed": True})
            # scan the platform's own skills dir for skills installed outside Tardigrade
            try:
                base = target_dir(p.id, project=False)
            except DispatchError:
                base = None
            if base and base.is_dir():
                for child in sorted(base.iterdir()):
                    if not child.is_dir() or not (child / "SKILL.md").is_file():
                        continue
                    if str(child.resolve()).lower() in managed_dests:
                        continue
                    items.append(
                        {
                            "skill": child.name,
                            "agent": p.id,
                            "dest": str(child),
                            "source": "",
                            "installed_at": None,
                            "present": True,
                            "managed": False,
                        }
                    )
            out.append({"agent": p.id, "name": p.name, "discovery": p.discovery, "detected": detected.get(p.id, False), "skills": items})
        return {"platforms": out}

    def _audit_badge(report) -> dict:
        counts = {s: sum(1 for f in report.findings if f.severity == s) for s in ("CRITICAL", "HIGH", "LOW")}
        if counts["CRITICAL"]:
            return {"badge": "blocked", "detail": f"CRITICAL={counts['CRITICAL']}"}
        if counts["HIGH"] or counts["LOW"]:
            return {"badge": "findings", "detail": f"HIGH={counts['HIGH']} LOW={counts['LOW']}"}
        return {"badge": "pass", "detail": "no findings"}

    def _copy_into_library(src: Path, source: str) -> dict:
        """Copy a validated skill dir into the download library. Returns row."""
        lib = Path(state["download_dir"])
        lib.mkdir(parents=True, exist_ok=True)
        dest = lib / src.name
        if dest.resolve() == src.resolve():
            raise HTTPException(400, "该目录已在下载库中")
        if dest.exists():
            shutil.rmtree(dest)  # 重新导入 = 覆盖我们管理的库副本
        shutil.copytree(src, dest)
        meta = _load_library_meta()
        meta[src.name] = {"source": source, "added_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        _save_library_meta(meta)
        return {"skill": src.name, "dir": str(dest), "source": source}

    @app.post("/api/import")
    def import_local(body: ImportBody) -> dict:
        """Import a local skill directory into the library (audit gate -> copy)."""
        src = Path(body.path).expanduser()
        if not src.is_dir():
            raise HTTPException(404, f"目录不存在：{src}")
        if not (src / "SKILL.md").is_file():
            raise HTTPException(400, "该目录没有 SKILL.md，不是有效的 skill")
        report = run_audit(src)
        badge_out = _audit_badge(report)
        if badge_out["badge"] == "blocked":
            raise HTTPException(400, f"安全审计拦截（{badge_out['detail']}），已拒绝导入")
        row = _copy_into_library(src, source=f"local:{src}")
        return {"ok": True, **row, "audit": badge_out}

    @app.post("/api/download")
    def download(body: DownloadBody) -> dict:
        """Market install: resolve a remote source into the download library (audit gate)."""
        import tempfile

        with tempfile.TemporaryDirectory(prefix="tardigrade-download-") as tmp:
            workdir = Path(tmp)
            try:
                root, source_desc, _resolved_sha = resolve_source(body.source, workdir)
            except SourceError as e:
                raise HTTPException(400, f"source error: {e}")
            skill_dirs = scan_skill_dirs(root)
            if not skill_dirs:
                raise HTTPException(400, "no skill directories found (no SKILL.md within 2 levels)")
            results = []
            for d in skill_dirs:
                report = run_audit(d)
                badge_out = _audit_badge(report)
                if badge_out["badge"] == "blocked":
                    results.append({"skill": d.name, "ok": False, "audit": badge_out})
                    continue
                row = _copy_into_library(d, source=f"market:{body.source}")
                results.append({"skill": d.name, "ok": True, "dir": row["dir"], "audit": badge_out})
        return {"ok": True, "source": body.source, "results": results}

    @app.get("/api/library")
    def library() -> dict:
        """Local skill library (downloaded + imported) with parsed descriptions."""
        lib = Path(state["download_dir"])
        meta = _load_library_meta()
        skills = []
        if lib.is_dir():
            for d in _scan_skills([str(lib)]):
                item = {"name": d.name, "dir": str(d), "source": meta.get(d.name, {}).get("source", "local")}
                problems = validate_skill(d)
                item["valid"] = not problems
                if not problems:
                    try:
                        ir: SkillIR = build_ir(d)
                        item["description"] = ir.description
                    except SpecError:
                        item["description"] = ""
                else:
                    item["description"] = problems[0]
                skills.append(item)
        return {"dir": str(lib), "skills": skills}

    @app.post("/api/library/delete")
    def library_delete(body: LibraryDeleteBody) -> dict:
        """从本地 Skill 库删除一个 skill（仅允许删 download_dir 内的目录）。"""
        lib = Path(state["download_dir"]).expanduser().resolve()
        target = (lib / body.name).resolve()
        if lib not in target.parents or target == lib:
            raise HTTPException(400, "只能删除本地 Skill 库内的目录")
        if not target.is_dir():
            return {"ok": False, "message": f"目录不存在：{target}"}
        shutil.rmtree(target)
        meta = _load_library_meta()
        if body.name in meta:
            meta.pop(body.name)
            _save_library_meta(meta)
        return {"ok": True, "removed": str(target)}

    @app.post("/api/open-url")
    def open_url(body: OpenUrlBody) -> dict:
        """用系统默认浏览器打开外部链接（exe 的 webview 里没有可用的 window.open）。"""
        import webbrowser

        if not body.url.startswith(("http://", "https://")):
            raise HTTPException(400, "只允许 http/https 链接")
        webbrowser.open(body.url)
        return {"ok": True}

    @app.post("/api/toggle")
    def toggle(body: ToggleBody) -> dict:
        """管理页平台开关：适配则安装（写入记录），不适配则返回判定供前端弹窗。"""
        if body.agent not in profiles:
            raise HTTPException(400, f"unknown agent '{body.agent}'")
        src = Path(body.dir).expanduser()
        if not (src / "SKILL.md").is_file():
            raise HTTPException(400, "该目录没有 SKILL.md，不是有效的 skill")
        profile = profiles[body.agent]
        judgment = judge_skill(src, profile)
        if judgment.tier not in {"full", "full*"}:
            return {"ok": False, "tier": judgment.tier, **judgment.to_dict()}
        problems = validate_skill(src)
        if problems:
            return {"ok": False, "tier": "invalid", "reasons": problems}
        report = run_audit(src)
        if report.blocked:
            return {"ok": False, "tier": "blocked", "reasons": [report.summary()]}
        try:
            dest = dispatch(src, body.agent)
        except DispatchError as e:
            raise HTTPException(400, str(e))
        adapt_llm.record_install(src.name, body.agent, dest, source=f"toggle:{src}")
        return {"ok": True, "tier": judgment.tier, "dest": str(dest)}

    @app.post("/api/skill-detail")
    def skill_detail(body: SkillDetailBody) -> dict:
        """读取一个 skill 的 SKILL.md 原文。路径必须位于允许的目录内。"""
        path = Path(body.path).expanduser().resolve()
        allowed_bases = [Path(state["download_dir"]).expanduser().resolve()]
        for agent in TARGETS:
            try:
                allowed_bases.append(target_dir(agent, project=False).resolve())
                allowed_bases.append(target_dir(agent, project=True).resolve())
            except DispatchError:
                continue
        for root in state["roots"]:
            allowed_bases.append(Path(root).expanduser().resolve())
        if not any(str(path).startswith(str(base)) for base in allowed_bases):
            raise HTTPException(403, "路径不在允许的目录内")
        md = path / "SKILL.md"
        if not md.is_file():
            raise HTTPException(404, "该目录没有 SKILL.md")
        try:
            content = md.read_text(encoding="utf-8")
        except OSError as e:
            raise HTTPException(400, f"读取失败：{e}")
        return {"name": path.name, "path": str(path), "content": content}

    @app.post("/api/uninstall")
    def uninstall(body: UninstallBody) -> dict:
        """Remove a skill from a platform (managed or not). Only dirs under the agent's own skills root are touched."""
        from tardigrade_skill.dispatcher import target_dir

        dest = adapt_llm.drop_install(body.skill, body.agent)
        if dest is None:
            # 非托管（本机已有）skill：统一管理 —— 在平台 skills 根目录下按名定位后删除
            try:
                root = target_dir(body.agent, project=False).expanduser().resolve()
            except Exception as e:
                raise HTTPException(400, f"cannot resolve skills root for '{body.agent}': {e}")
            candidate = (root / body.skill).resolve()
            if root not in candidate.parents or not (candidate / "SKILL.md").is_file():
                raise HTTPException(404, f"'{body.skill}' not found under {root} (or not a valid skill dir)")
            dest = str(candidate)
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
