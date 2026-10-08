"""Source resolution: local dirs, zip archives, git repos (shallow)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


class SourceError(Exception):
    pass


def find_skill_dirs(root: Path) -> list[Path]:
    """Locate skill directories under a source root (dirs containing SKILL.md, 2 levels deep)."""
    root = Path(root)
    if (root / "SKILL.md").is_file():
        return [root]
    found: list[Path] = []
    for child in sorted(root.iterdir()):
        if child.is_dir():
            if (child / "SKILL.md").is_file():
                found.append(child)
            else:  # one more level (e.g. skills/<category>/<skill>)
                for grandchild in sorted(child.iterdir()):
                    if grandchild.is_dir() and (grandchild / "SKILL.md").is_file():
                        found.append(grandchild)
    return found


def resolve_source(source: str, workdir: Path) -> tuple[Path, str, str]:
    """Materialize a source into a local directory.

    Returns (root_dir, source_description, resolved_sha).
    Raises SourceError on unsupported or broken sources.
    """
    src = str(source)
    if src.startswith(("http://", "https://", "git@")) or src.endswith(".git"):
        return _resolve_git(src, workdir)
    p = Path(src)
    if p.is_dir():
        return p, f"local:{p.as_posix()}", ""
    if p.is_file() and p.suffix.lower() == ".zip":
        return _resolve_zip(p, workdir)
    raise SourceError(f"unsupported source: {src} (expected local dir, .zip, or git URL)")


def _resolve_zip(p: Path, workdir: Path) -> tuple[Path, str, str]:
    dest = workdir / "zip"
    with zipfile.ZipFile(p) as zf:
        # basic zip-bomb / traversal guard
        for info in zf.infolist():
            target = dest / info.filename
            if not str(target.resolve()).startswith(str(dest.resolve())):
                raise SourceError(f"zip contains path traversal: {info.filename}")
            if info.file_size > 50 * 1024 * 1024:
                raise SourceError(f"zip entry too large (>50MB): {info.filename}")
        zf.extractall(dest)
    return dest, f"zip:{p.as_posix()}", ""


def _resolve_git(url: str, workdir: Path) -> tuple[Path, str, str]:
    dest = workdir / "git"
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest)],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as e:
        raise SourceError(f"git clone failed: {e.stderr.decode(errors='replace')[:300]}") from e
    resolved = subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    # keep lockfile self-contained: drop the .git dir after recording the sha
    shutil.rmtree(dest / ".git", ignore_errors=True)
    return dest, f"git:{url}", resolved
