"""tardigrade-skill desktop launcher.

Lifecycle: start uvicorn on a free localhost port first, then open the pywebview
window pointed at it; when the window closes, shut the server down gracefully.
If pywebview is unavailable, fall back to the default browser (dev mode).

Environment overrides (CI / headless smoke tests):
- TARDIGRADE_PORT      fixed port instead of a random free one
- TARDIGRADE_HEADLESS  "1" = serve only, never open a window/browser
"""

from __future__ import annotations

import os
import socket
import threading
import webbrowser
from pathlib import Path

import uvicorn

from server.app import create_app


def _free_port() -> int:
    override = os.environ.get("TARDIGRADE_PORT")
    if override:
        return int(override)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ensure_stdio() -> None:
    """PyInstaller --windowed builds have no console: sys.stdout/stderr are
    None, and uvicorn's ColourizedFormatter calls .isatty() on them during
    logging setup -> ValueError. Point them at the null device first."""
    import sys

    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115


def main() -> None:
    _ensure_stdio()
    port = _free_port()
    app = create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # signals belong to the main thread
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}"
    _wait_ready(url)

    if os.environ.get("TARDIGRADE_HEADLESS") == "1":
        print(f"Tardigrade Skill serving (headless) at {url}", flush=True)
        try:
            thread.join()
        except KeyboardInterrupt:
            pass
    else:
        try:
            import webview  # pywebview

            # background_color 必须与页面深色底一致：默认白底会在大面积重绘时露白（闪烁）
            webview.create_window(
                "Tardigrade Skill", url, width=1180, height=760, min_size=(960, 640),
                background_color="#1d1d20",
            )
            webview.start()
        except ImportError:
            print(f"pywebview not installed — dev fallback: opening {url} in your browser. Ctrl+C to quit.")
            webbrowser.open(url)
            try:
                thread.join()
            except KeyboardInterrupt:
                pass

    server.should_exit = True
    thread.join(timeout=5)


def _wait_ready(url: str, timeout: float = 10.0) -> None:
    import time
    from urllib.request import urlopen

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(f"{url}/api/health", timeout=1) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f"server did not become ready at {url}")


if __name__ == "__main__":
    main()
