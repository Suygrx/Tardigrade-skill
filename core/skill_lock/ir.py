"""SkillIR: a small intermediate representation of a skill, extracted statically.

Design (doc §20): three granularities —
  A. capability booleans  requires{shell, network, fs_write}  (AST + body-text dual
     channel; conflicts union'd with recorded evidence sources)
  B. structured tool calls  tools[{tool, pattern}]  (from frontmatter allowed-tools,
     for L1 mechanical mapping)
  C. instruction blocks  blocks[{id, heading, start, end, scripts}]  (for L2
     targeted rewriting and changelog accounting)

No full semantic tree — deliberately out of scope.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from .audit.rules_code import NETWORK_MODULES
from .spec import load_skill

# ---------------------------------------------------------------- text channel

SHELL_HINTS = re.compile(
    r"\b(?:terminal|shell|bash|zsh|powershell|command[ -]line|cli)\b"
    r"|\bcurl\b|\bwget\b|\bpip install\b|\bnpm\b|\bgit clone\b|\bpython\b",
    re.I,
)
NETWORK_HINTS = re.compile(
    r"\b(?:download|upload|https?://|webhook|fetch|internet|online)\b"
    r"|\bcurl\b|\bwget\b|\brequests\b|\bhttpx\b|\burllib\b|\bsocket\b",
    re.I,
)
FS_WRITE_HINTS = re.compile(
    r"\b(?:write|save|create|edit|modify|delete|move|rename)\b[^.\n]{0,24}"
    r"\b(?:files?|director(?:y|ies)|folders?|documents?|notes?|logs?)\b",
    re.I,
)

SCRIPT_REF_RE = re.compile(r"scripts/[\w\-./]+", re.I)


# ---------------------------------------------------------------- AST channel


def _ast_capabilities(py_file: Path) -> dict[str, list[str]]:
    """Infer capability needs from one Python file. Returns cap -> evidence list."""
    caps: dict[str, list[str]] = {"shell": [], "network": [], "fs_write": []}
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return caps

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    rel = py_file.name
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = [a.name for a in node.names]
            if any(n.split(".")[0] in {"subprocess", "os"} for n in names) or mod.startswith(("subprocess", "os")):
                caps["shell"].append(f"ast:{rel}:{getattr(node, 'lineno', 0)} import {mod or names}")
            if any(n in NETWORK_MODULES or n.split(".")[0] in {"requests", "httpx", "socket"} for n in names) or mod.startswith(
                ("requests", "httpx", "urllib", "socket")
            ):
                caps["network"].append(f"ast:{rel}:{getattr(node, 'lineno', 0)} import {mod or names}")
        elif isinstance(node, ast.Call):
            src = ast.unparse(node) if hasattr(ast, "unparse") else ""
            if re.search(r"\b(subprocess|os\.system|os\.popen)\b", src):
                caps["shell"].append(f"ast:{rel}:{getattr(node, 'lineno', 0)} call {src[:60]}")
            if re.search(r"\bopen\s*\(.['wba]|write_text|write_bytes|shutil\.|os\.makedirs|mkdir", src):
                caps["fs_write"].append(f"ast:{rel}:{getattr(node, 'lineno', 0)} call {src[:60]}")
    # network modules imported but maybe only used as names
    for mod in imported:
        if mod in NETWORK_MODULES or mod.split(".")[0] in {"requests", "httpx", "socket"}:
            caps["network"].append(f"ast:{rel}:0 import {mod}")
    return caps


# ---------------------------------------------------------------- IR model


@dataclass
class ToolUse:
    tool: str
    pattern: str  # raw spec text, e.g. "Bash(git *)" or "WebFetch"


@dataclass
class Block:
    id: str  # e.g. "b1"
    heading: str
    start: int  # 1-based line in SKILL.md body
    end: int
    scripts: list[str] = field(default_factory=list)


@dataclass
class SkillIR:
    name: str
    description: str
    allowed_tools: list[ToolUse]
    requires: dict[str, bool]  # shell / network / fs_write
    evidence: dict[str, list[str]]  # cap -> evidence strings (ast: / text: sources)
    blocks: list[Block]
    scripts: list[str]  # relative paths of script files present
    body_chars: int

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "allowed_tools": [{"tool": t.tool, "pattern": t.pattern} for t in self.allowed_tools],
            "requires": self.requires,
            "evidence": self.evidence,
            "blocks": [
                {"id": b.id, "heading": b.heading, "start": b.start, "end": b.end, "scripts": b.scripts}
                for b in self.blocks
            ],
            "scripts": self.scripts,
            "body_chars": self.body_chars,
        }


def _parse_blocks(body: str) -> list[Block]:
    lines = body.splitlines()
    blocks: list[Block] = []
    current: Block | None = None
    for i, line in enumerate(lines, start=1):
        m = re.match(r"^(#{2,3})\s+(.*)$", line)
        if m:
            if current:
                current.end = i - 1
                blocks.append(current)
            current = Block(id=f"b{len(blocks) + 1}", heading=m.group(2).strip(), start=i, end=i)
        elif current:
            current.end = i
            current.scripts.extend(m2.group(0) for m2 in SCRIPT_REF_RE.finditer(line) if m2.group(0) not in current.scripts)
    if current:
        blocks.append(current)
    return [b for b in blocks if b.heading or b.scripts]


def build_ir(skill_dir: Path) -> SkillIR:
    """Extract the SkillIR from a skill directory. Raises SpecError on invalid SKILL.md."""
    skill_dir = Path(skill_dir)
    meta, body, _ = load_skill(skill_dir)  # SpecError propagates

    evidence: dict[str, list[str]] = {"shell": [], "network": [], "fs_write": []}

    # channel 1: AST over scripts/
    for py in sorted(skill_dir.rglob("*.py")):
        caps = _ast_capabilities(py)
        for cap, evs in caps.items():
            evidence[cap].extend(evs)

    # channel 2: body text keywords
    for cap, rx in (("shell", SHELL_HINTS), ("network", NETWORK_HINTS), ("fs_write", FS_WRITE_HINTS)):
        for i, line in enumerate(body.splitlines(), start=1):
            if rx.search(line):
                evidence[cap].append(f"text:SKILL.md:{i}")

    requires = {cap: bool(evs) for cap, evs in evidence.items()}

    tools: list[ToolUse] = []
    if meta.allowed_tools:
        for raw in meta.allowed_tools.split(","):
            raw = raw.strip()
            if raw:
                tools.append(ToolUse(tool=raw.split("(")[0].strip(), pattern=raw))

    scripts = sorted(str(p.relative_to(skill_dir)).replace("\\", "/") for p in skill_dir.rglob("*") if p.is_file() and p.suffix in {".py", ".sh", ".bash", ".zsh"})

    return SkillIR(
        name=meta.name,
        description=meta.description,
        allowed_tools=tools,
        requires=requires,
        evidence=evidence,
        blocks=_parse_blocks(body),
        scripts=scripts,
        body_chars=len(body),
    )
