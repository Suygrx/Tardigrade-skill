"""Rotate and clean log files (shell + filesystem demo)."""

import os
import subprocess
from pathlib import Path


def plan(root: Path) -> list[Path]:
    return [p for p in root.glob("*.log") if p.stat().st_size > 1_000_000]


def rotate(path: Path) -> None:
    os.makedirs(path.parent / "archive", exist_ok=True)
    subprocess.run(["gzip", "-k", str(path)], check=True)  # noqa: S603, S607


if __name__ == "__main__":
    print("\n".join(str(p) for p in plan(Path.cwd())))
