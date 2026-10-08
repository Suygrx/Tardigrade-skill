"""Dispatch installed skills to agent target directories (copy mode by default)."""

from __future__ import annotations

import shutil
from pathlib import Path

# agent id -> (global target dir, project-local target dir)
# Dirs follow the cross-agent skills standard popularized by the skills CLI
# (vercel-labs/skills): every mainstream desktop agent exposes a SKILL.md
# directory; the global dir doubles as the install-detection signal.
TARGETS: dict[str, tuple[str, str]] = {
    "claude-code": ("~/.claude/skills", ".claude/skills"),
    "codex": ("~/.codex/skills", ".codex/skills"),
    "gemini-cli": ("~/.gemini/skills", ".gemini/skills"),
    "cursor": ("~/.cursor/skills", ".cursor/skills"),
    "opencode": ("~/.config/opencode/skills", ".opencode/skills"),
    "github-copilot": ("~/.copilot/skills", ".github/skills"),
    "windsurf": ("~/.codeium/windsurf/skills", ".windsurf/skills"),
    "qwen-code": ("~/.qwen/skills", ".qwen/skills"),
    "iflow-cli": ("~/.iflow/skills", ".iflow/skills"),
    "crush": ("~/.config/crush/skills", ".crush/skills"),
    "goose": ("~/.config/goose/skills", ".goose/skills"),
    "droid": ("~/.factory/skills", ".factory/skills"),
    "amp": ("~/.config/agents/skills", ".agents/skills"),
    "cline": ("~/.agents/skills", ".agents/skills"),
    "roo": ("~/.roo/skills", ".roo/skills"),
    "kilo": ("~/.kilo/skills", ".kilo/skills"),
    "trae": ("~/.trae/skills", ".trae/skills"),
    "trae-cn": ("~/.trae-cn/skills", ".trae-cn/skills"),
    "workbuddy": ("~/.workbuddy/skills", ".workbuddy/skills"),
}

# agent id -> config dir whose existence means "this platform is installed"
# (mirrors the detectInstalled() checks in vercel-labs/skills src/agents.ts)
DETECT_DIRS: dict[str, str] = {
    "claude-code": "~/.claude",
    "codex": "~/.codex",
    "gemini-cli": "~/.gemini",
    "cursor": "~/.cursor",
    "opencode": "~/.config/opencode",
    "github-copilot": "~/.copilot",
    "windsurf": "~/.codeium/windsurf",
    "qwen-code": "~/.qwen",
    "iflow-cli": "~/.iflow",
    "crush": "~/.config/crush",
    "goose": "~/.config/goose",
    "droid": "~/.factory",
    "amp": "~/.config/amp",
    "cline": "~/.cline",
    "roo": "~/.roo",
    "kilo": "~/.kilo",
    "trae": "~/.trae",
    "trae-cn": "~/.trae-cn",
    "workbuddy": "~/.workbuddy",
}


class DispatchError(Exception):
    pass


def target_dir(agent: str, project: bool) -> Path:
    if agent not in TARGETS:
        known = ", ".join(sorted(TARGETS))
        raise DispatchError(f"unknown agent '{agent}' (supported: {known})")
    raw = TARGETS[agent][1 if project else 0]
    return Path(raw).expanduser()


def dispatch(skill_dir: Path, agent: str, project: bool = False, dest_override: Path | None = None) -> Path:
    """Copy a skill directory into the agent's skills directory. Returns destination."""
    dest_base = Path(dest_override).expanduser() if dest_override else target_dir(agent, project)
    dest = dest_base / Path(skill_dir).name
    if dest.exists():
        shutil.rmtree(dest)  # managed directory: replace our own previous install
    dest_base.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill_dir, dest)
    return dest


def detect_platforms() -> dict[str, bool]:
    """Which agent platforms are present on this machine (config dir exists)."""
    out: dict[str, bool] = {}
    for agent, raw in DETECT_DIRS.items():
        try:
            out[agent] = Path(raw).expanduser().is_dir()
        except OSError:  # pragma: no cover - bad home expansion
            out[agent] = False
    return out
