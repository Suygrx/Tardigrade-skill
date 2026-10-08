# tardigrade-skill

Desktop manager + adaptation engine for **Agent Skills** (the [agentskills.io](https://agentskills.io) format).

One screen tells you, for every skill × every target platform, whether it can be
used as-is, needs adaptation, needs manual steps, or is genuinely incompatible —
then applies it in one click. The goal is not 100% compatibility; it is
**transparent compatibility**.

## Why

The spec defines the *format* of a skill — nothing about versions, distribution,
integrity, safety, or cross-platform adaptation. Existing Python tools (max 3 stars)
only copy files. The 2026 ecosystem audit
[Snyk ToxicSkills](https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub)
found 36.8% of scanned skills carry at least one security flaw.

`tardigrade-skill` fills the gap:

- **install** — one audited pipeline: `resolve → validate → audit → lock → dispatch`
- **adapt** — SkillIR + Platform Profiles (N+M, not N×M): deterministic rule layer
  (L0/L1) for `full`/`partial`/`incompatible`, BYOK LLM layer (L2) for `adapted`,
  with changelog accounting and human confirmation before anything lands
- **lockfile** — `skills.lock` pins source + rev + per-file SHA-256; reproducible and tamper-checkable
- **audit gate** — static, zero-API checks: invisible Unicode smuggling, prompt-injection
  patterns, dangerous Python/shell APIs in `scripts/`, credential paths, path traversal
- **multi-agent dispatch** — one skill, installed to Claude Code / Codex / Gemini CLI / Cursor / OpenCode

The audit gate is a *known-pattern gate* (the role `pip audit` plays for packages), not an
LLM-level malicious-skill classifier — deep semantic detection is out of scope by design.

## Layout (monorepo)

```
core/       engine package (spec · audit · installer · lockfile · dispatcher · ir · profiles)
server/     FastAPI app — thin REST layer over core
desktop/    pywebview shell + frontend SPA (adaptation matrix)
profiles/   platform profiles (add a platform = add a YAML card, zero code)
tests/      pytest suite
```

## Install

```bash
uv tool install tardigrade-skill     # or: pipx install tardigrade-skill
```

## Development

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # Windows
set PYTHONPATH=core;server
.venv/Scripts/python -m pytest
.venv/Scripts/python desktop/main.py     # desktop app (falls back to browser)
```

## CLI usage

```bash
tardigrade-skill validate ./my-skill            # spec conformance
tardigrade-skill audit ./my-skill               # security gate report
tardigrade-skill install ./my-skill --to claude-code --project
tardigrade-skill install https://github.com/owner/repo --to codex   # git, pinned by resolved SHA
tardigrade-skill list                            # what's in skills.lock
tardigrade-skill check my-skill .claude/skills/my-skill   # verify against lockfile hashes
tardigrade-skill targets                         # supported agents and directories
```

Install is blocked (exit 2) on CRITICAL findings unless `--allow-risk` is given
(the findings are still reported and recorded in the lockfile flow).

## Status

Alpha (v0.2-dev). Tier 1 MVP done and verified. Now building the desktop
adaptation matrix (M1: deterministic tiers, then M2: BYOK LLM adaptation + HITL).
Roadmap: `update/outdated`, SARIF reports, signing/provenance, MCP server mode.
