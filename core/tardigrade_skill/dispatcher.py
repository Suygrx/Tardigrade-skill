"""Dispatch installed skills to agent target directories (copy mode by default)."""

from __future__ import annotations

import shutil
from pathlib import Path

# agent id -> (global target dir, project-local target dir)
TARGETS: dict[str, tuple[str, str]] = {
    "claude-code": ("~/.claude/skills", ".claude/skills"),
    "codex": ("~/.codex/skills", ".codex/skills"),
    "gemini-cli": ("~/.gemini/skills", ".gemini/skills"),
    "cursor": ("~/.cursor/skills", ".cursor/skills"),
    "opencode": ("~/.config/opencode/skills", ".opencode/skills"),
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
