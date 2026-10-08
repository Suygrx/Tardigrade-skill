# skill-lock

Package manager for **Agent Skills** (the [agentskills.io](https://agentskills.io) format):
reproducible installs, a content-hash lockfile, and a pre-install security gate.

## Why

The spec defines the *format* of a skill — nothing about versions, distribution,
integrity, or safety. Existing Python tools (max 3 stars) only copy files. The
2026 ecosystem audit [Snyk ToxicSkills](https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub)
found 36.8% of scanned skills carry at least one security flaw.

`skill-lock` fills the package-manager gap:

- **install** — one pipeline: `resolve → validate → audit → lock → dispatch`
- **lockfile** — `skills.lock` pins source + rev + per-file SHA-256; reproducible and tamper-checkable
- **audit gate** — static, zero-API checks: invisible Unicode smuggling, prompt-injection
  patterns, dangerous Python/shell APIs in `scripts/`, credential paths, path traversal
- **multi-agent dispatch** — one skill, installed to Claude Code / Codex / Gemini CLI / Cursor / OpenCode

The audit gate is a *known-pattern gate* (the role `pip audit` plays for packages), not an
LLM-level malicious-skill classifier — deep semantic detection is out of scope by design.

## Install

```bash
uv tool install skill-lock     # or: pipx install skill-lock
```

## Usage

```bash
skill-lock validate ./my-skill            # spec conformance
skill-lock audit ./my-skill               # security gate report
skill-lock install ./my-skill --to claude-code --project
skill-lock install https://github.com/owner/repo --to codex   # git, pinned by resolved SHA
skill-lock list                            # what's in skills.lock
skill-lock check my-skill .claude/skills/my-skill   # verify against lockfile hashes
skill-lock targets                         # supported agents and directories
```

Install is blocked (exit 2) on CRITICAL findings unless `--allow-risk` is given
(the findings are still reported and recorded in the lockfile flow).

## Status

Alpha (v0.1). Supported sources: local dirs, `.zip`, git URLs (shallow clone).
Roadmap: `update/outdated`, SARIF reports, signing/provenance, MCP server mode.
