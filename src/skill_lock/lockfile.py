"""skills.lock: reproducible install state with content hashes (rug-pull detection)."""

from __future__ import annotations

import hashlib
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

LOCK_FILE_NAME = "skills.lock"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class LockEntry:
    name: str
    source: str
    rev: str = ""
    resolved_sha: str = ""
    installed_at: str = ""
    files: dict[str, str] = field(default_factory=dict)  # relative path -> sha256

    def to_toml(self) -> str:
        # files must be an inline table: a [skills.files] sub-table would always
        # attach to the LAST [[skills]] entry and break with multiple skills.
        files_items = ", ".join(f'"{rel}" = "{digest}"' for rel, digest in sorted(self.files.items()))
        files_inline = "{ " + files_items + " }" if self.files else "{}"
        lines = [
            "[[skills]]",
            f'name = "{self.name}"',
            f'source = "{self.source}"',
            f'rev = "{self.rev}"',
            f'resolved_sha = "{self.resolved_sha}"',
            f'installed_at = "{self.installed_at}"',
            f"files = {files_inline}",
        ]
        return "\n".join(lines) + "\n"


class LockFile:
    def __init__(self) -> None:
        self.entries: dict[str, LockEntry] = {}

    @classmethod
    def load(cls, root: Path) -> "LockFile":
        lock_path = Path(root) / LOCK_FILE_NAME
        lock = cls()
        if not lock_path.is_file():
            return lock
        data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
        for entry in data.get("skills", []):
            files = entry.pop("files", {})
            lock.entries[entry["name"]] = LockEntry(files=files, **entry)
        return lock

    def save(self, root: Path) -> Path:
        lock_path = Path(root) / LOCK_FILE_NAME
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        blocks = [entry.to_toml() for entry in self.entries.values()]
        header = (
            "# skills.lock - managed by skill-lock. Do not edit manually.\n"
            "# Reproducible install state: source pin + content hashes.\n\n"
        )
        lock_path.write_text(header + "\n".join(blocks), encoding="utf-8")
        return lock_path

    def record(self, entry: LockEntry) -> None:
        self.entries[entry.name] = entry

    def check(self, skill_install_dir: Path, name: str) -> list[str]:
        """Compare on-disk file hashes against the lock entry. Returns tamper list."""
        entry = self.entries.get(name)
        if entry is None:
            return [f"{name}: not found in lockfile"]
        tampered: list[str] = []
        base = Path(skill_install_dir)
        for rel, digest in sorted(entry.files.items()):
            p = base / rel
            if not p.is_file():
                tampered.append(f"{rel}: MISSING (locked sha256={digest[:12]})")
            elif sha256_file(p) != digest:
                tampered.append(f"{rel}: MODIFIED (locked sha256={digest[:12]})")
        return tampered


def build_entry(name: str, source: str, skill_dir: Path, rev: str = "", resolved_sha: str = "") -> LockEntry:
    files = {
        str(p.relative_to(skill_dir)).replace("\\", "/"): sha256_file(p)
        for p in sorted(Path(skill_dir).rglob("*"))
        if p.is_file()
    }
    return LockEntry(
        name=name,
        source=source,
        rev=rev,
        resolved_sha=resolved_sha,
        installed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        files=files,
    )
