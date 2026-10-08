"""Root launcher for the frozen desktop app (PyInstaller entry point).

In dev, prefer `python desktop/main.py`. This root-level entry exists because
PyInstaller reliably resolves imports relative to the entry script's directory
(repo root -> `server/` and `core/` on sys.path via pathex).
"""
import sys

sys.path.insert(0, "core")
sys.path.insert(0, "server")

from desktop.main import main  # noqa: E402

if __name__ == "__main__":
    main()
