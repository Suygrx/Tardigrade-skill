"""Discovery: search = audit (doc §24).

GitHub topic aggregation (claude-skill / agent-skills / cursor-rules) ranked by
stars, then each top result is shallow-fetched (zipball) and run through the
static audit gate on the spot. Results carry an audit badge:
pass / findings(HIGH=n, LOW=m) / blocked(CRITICAL=n) / skipped.

Quota exhaustion or offline -> degrade to un-audited listing with a hint to run
`audit` manually. Results are cached for 24h as a JSON file.
"""

from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

import httpx

from .audit import run_audit
from .installer import find_skill_dirs

SEARCH_TOPICS = ("claude-skill", "agent-skills", "cursor-rules")
CACHE_PATH = Path("~/.tardigrade/search-cache.json").expanduser()
CACHE_TTL = 24 * 3600
HTTP_TIMEOUT = httpx.Timeout(30.0)


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
                for chunk in resp.iter_bytes(65536):
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
                },
            )

    ranked = sorted(repos.values(), key=lambda r: -r["stars"])[:limit]

    results = []
    offline = False
    if ranked:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="tardigrade-search-") as tmp:
            workdir = Path(tmp)
            for repo in ranked:
                audit = audit_remote_repo(repo["full_name"], workdir)
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
