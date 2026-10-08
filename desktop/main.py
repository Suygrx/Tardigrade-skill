"""skill-lock desktop launcher.

Lifecycle: start uvicorn on a free localhost port first, then open the pywebview
window pointed at it; when the window closes, shut the server down gracefully.
If pywebview is unavailable, fall back to the default browser (dev mode).
"""

from __future__ import annotations

import socket
import threading
import webbrowser
from pathlib import Path

import uvicorn

from server.app import create_app


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    port = _free_port()
    app = create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # signals belong to the main thread
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}"
    _wait_ready(url)

    try:
        import webview  # pywebview

        webview.create_window("skill-lock", url, width=1180, height=760, min_size=(960, 640))
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
