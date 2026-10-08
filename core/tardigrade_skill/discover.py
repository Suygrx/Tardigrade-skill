"""Discovery: search = audit (doc §24).

Sources, merged and deduped by repo:
- GitHub topic aggregation (claude-skill / agent-skills / cursor-rules),
  ranked by stars
- skills.sh (Vercel's open skills directory) install-telemetry search,
  which maps skill entries back to their GitHub repos

Each top result is shallow-fetched (zipball) and run through the static
audit gate on the spot. Results carry an audit badge:
pass / findings(HIGH=n, LOW=m) / blocked(CRITICAL=n) / skipped.

Quota exhaustion or offline -> degrade to un-audited listing with a hint to run
`audit` manually. Results are cached for 24h as a JSON file.
"""

from __future__ import annotations

import json
import tempfile
import time
import zipfile
from pathlib import Path

import httpx

from .audit import run_audit
from .installer import find_skill_dirs

SEARCH_TOPICS = ("claude-skill", "agent-skills", "cursor-rules")
SKILLS_SH_SEARCH_URL = "https://skills.sh/api/search"
CACHE_PATH = Path("~/.tardigrade/search-cache.json").expanduser()
CACHE_TTL = 24 * 3600
HTTP_TIMEOUT = httpx.Timeout(30.0)
MAX_ZIP_BYTES = 64 * 1024 * 1024  # skip repos whose zipball exceeds ~64MB
AUDIT_WORKERS = 5


def _gh_get(url: str, params: dict | None = None) -> httpx.Response:
    return httpx.get(
        url,
        params=params,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "tardigrade-skill"},
        timeout=HTTP_TIMEOUT,
    )


def _badge_for(findings: list) -> dict:
    counts = {s: sum(1 for f in findings if f.severity == s) for s in ("CRITICAL", "HIGH", "LOW")}
    if counts["CRITICAL"]:
        return {"badge": "blocked", "detail": f"CRITICAL={counts['CRITICAL']}", "blocked": True}
    if counts["HIGH"] or counts["LOW"]:
        return {"badge": "findings", "detail": f"HIGH={counts['HIGH']} LOW={counts['LOW']}", "blocked": False}
    return {"badge": "pass", "detail": "no findings", "blocked": False}


def audit_remote_repo(full_name: str, workdir: Path) -> dict:
    """Shallow-fetch one repo's zipball and audit every skill inside it."""
    zip_path = workdir / "repo.zip"
    dest = workdir / "repo"
    try:
        with httpx.stream(
            "GET",
            f"https://codeload.github.com/{full_name}/zip/HEAD",
            timeout=httpx.Timeout(60.0),
            follow_redirects=True,
        ) as resp:
            if resp.status_code != 200:
                return {"badge": "skipped", "detail": f"fetch HTTP {resp.status_code}", "skills": []}
            with open(zip_path, "wb") as f:
                received = 0
                for chunk in resp.iter_bytes(65536):
                    received += len(chunk)
                    if received > MAX_ZIP_BYTES:
                        return {"badge": "skipped", "detail": "repo zipball too large (>64MB)", "skills": []}
                    f.write(chunk)
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():  # same traversal guard as the installer
                target = dest / info.filename
                if not str(target.resolve()).startswith(str(dest.resolve())):
                    return {"badge": "skipped", "detail": "zip path traversal", "skills": []}
            zf.extractall(dest)
        skills_out = []
        aggregated = []
        for skill_dir in find_skill_dirs(dest):
            report = run_audit(skill_dir)
            aggregated.extend(report.findings)
            skills_out.append(
                {
                    "name": skill_dir.name,
                    "summary": report.summary(),
                    **_badge_for(report.findings),
                }
            )
        if not skills_out:
            return {"badge": "skipped", "detail": "no SKILL.md found", "skills": []}
        return {**_badge_for(aggregated), "skills": skills_out}
    except (httpx.HTTPError, zipfile.BadZipFile, OSError) as e:
        return {"badge": "skipped", "detail": str(e)[:120], "skills": []}
    finally:
        zip_path.unlink(missing_ok=True)


def _skills_sh_search(query: str) -> dict[str, dict]:
    """skills.sh (Vercel) open skills directory — install-telemetry search.

    Entries are per-skill ({source: "owner/repo", name, installs}); they are
    aggregated back to repos. Best-effort: any failure -> {} and the search
    silently degrades to GitHub-topic-only.
    """
    try:
        resp = httpx.get(
            SKILLS_SH_SEARCH_URL,
            params={"q": query},
            headers={"User-Agent": "tardigrade-skill"},
            timeout=HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            return {}
        entries = resp.json().get("skills") or []
    except (httpx.HTTPError, ValueError):
        return {}
    repos: dict[str, dict] = {}
    for e in entries:
        full_name = e.get("source")
        if not full_name or "/" not in full_name:
            continue
        rec = repos.setdefault(
            full_name,
            {
                "full_name": full_name,
                "html_url": f"https://github.com/{full_name}",
                "installs": 0,
                "sh_skills": [],
            },
        )
        rec["installs"] += int(e.get("installs") or 0)
        if e.get("name") and len(rec["sh_skills"]) < 3:
            rec["sh_skills"].append(e["name"])
    return repos


def _gh_repo_meta(full_name: str) -> dict:
    """Best-effort GitHub repo metadata for skills.sh-only results."""
    try:
        resp = _gh_get(f"https://api.github.com/repos/{full_name}")
        if resp.status_code == 200:
            item = resp.json()
            return {
                "stars": item.get("stargazers_count", 0),
                "description": (item.get("description") or "")[:160],
            }
    except httpx.HTTPError:
        pass
    return {"stars": 0, "description": ""}


def search_skills(query: str, limit: int = 5, use_cache: bool = True) -> dict:
    """Search by keyword across the skill topics; audit the top `limit` repos."""
    query = query.strip()
    if not query:
        return {"results": [], "cached": False, "rate_limited": False, "message": "empty query"}

    if use_cache and CACHE_PATH.is_file():
        try:
            cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            entry = cache.get(query.lower())
            if entry and time.time() - entry["ts"] < CACHE_TTL:
                return {**entry["payload"], "cached": True}
        except (json.JSONDecodeError, OSError, KeyError):
            pass

    repos: dict[str, dict] = {}
    rate_limited = False
    for topic in SEARCH_TOPICS:
        try:
            resp = _gh_get(
                "https://api.github.com/search/repositories",
                params={"q": f"{query} topic:{topic}", "sort": "stars", "per_page": 10},
            )
        except httpx.HTTPError:
            rate_limited = True
            continue
        if resp.status_code in (403, 429):
            rate_limited = True
            continue
        if resp.status_code != 200:
            continue
        for item in resp.json().get("items", []):
            repos.setdefault(
                item["full_name"],
                {
                    "full_name": item["full_name"],
                    "html_url": item["html_url"],
                    "stars": item.get("stargazers_count", 0),
                    "description": (item.get("description") or "")[:160],
                    "installs": 0,
                    "sh_skills": [],
                },
            )

    # 第二数据源：skills.sh 安装量遥测（Vercel 开放 skills 目录）
    for full_name, rec in _skills_sh_search(query).items():
        if full_name in repos:
            repos[full_name]["installs"] = rec["installs"]
            repos[full_name]["sh_skills"] = rec["sh_skills"]
        else:
            meta = _gh_repo_meta(full_name)
            repos[full_name] = {**rec, **meta}

    # 排序：安装量是"真实在用"的信号，权重高于星标
    ranked = sorted(repos.values(), key=lambda r: -(r.get("stars", 0) + 2 * r.get("installs", 0)))[:limit]

    results = []
    offline = False
    if ranked:
        from concurrent.futures import ThreadPoolExecutor

        with tempfile.TemporaryDirectory(prefix="tardigrade-search-") as tmp:
            workdir = Path(tmp)
            # parallel audits: each repo gets its own subdir (zip fetches don't race);
            # total wall time ~= slowest repo instead of the sum of all five
            with ThreadPoolExecutor(max_workers=min(AUDIT_WORKERS, len(ranked))) as ex:
                audits = list(
                    ex.map(
                        lambda pair: audit_remote_repo(pair[1]["full_name"], workdir / str(pair[0])),
                        enumerate(ranked),
                    )
                )
            for repo, audit in zip(ranked, audits):
                if audit["badge"] == "skipped" and "fetch HTTP" in audit.get("detail", ""):
                    offline = True
                results.append({**repo, "audit": audit})

    payload = {
        "results": results,
        "rate_limited": rate_limited,
        "degraded": rate_limited or offline,
        "message": (
            "GitHub 配额受限或网络不可用：结果未分级，请安装前手动运行 audit"
            if (rate_limited or offline)
            else ""
        ),
    }
    if not rate_limited and not offline:
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            cache = {}
            if CACHE_PATH.is_file():
                try:
                    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    cache = {}
            cache[query.lower()] = {"ts": time.time(), "payload": payload}
            CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
        except OSError:
            pass
    return {**payload, "cached": False}
