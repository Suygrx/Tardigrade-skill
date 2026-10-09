"""BYOK model client: OpenAI-compatible chat completions.

Config lives at ~/.tardigrade/models.toml (user-managed, never bundled):

    [default]
    base_url = "https://api.openai.com/v1"   # any OpenAI-compatible endpoint
    api_key  = "sk-..."
    model    = "gpt-4o-mini"

Security posture (doc §14): the key only ever goes into the LLM request — it is
never written to lockfiles, adaptation metadata, or the UI.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

CONFIG_PATH = Path("~/.tardigrade/models.toml").expanduser()
TIMEOUT = httpx.Timeout(120.0)
PROMPT_VERSION = "l2-adapt-v1"


@dataclass
class ModelConfig:
    base_url: str
    api_key: str
    model: str

    def public_view(self) -> dict[str, str]:
        """UI-safe view: never includes the api key."""
        return {"base_url": self.base_url, "model": self.model}


def load_model_config(path: Path | None = None) -> ModelConfig | None:
    cfg_path = Path(path) if path else CONFIG_PATH
    if not cfg_path.is_file():
        return None
    try:
        data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return None
    section = data.get("default") or next(iter(data.values()), None)
    if not isinstance(section, dict):
        return None
    base_url, api_key, model = section.get("base_url"), section.get("api_key"), section.get("model")
    if not (base_url and api_key and model):
        return None
    return ModelConfig(base_url=str(base_url).rstrip("/"), api_key=str(api_key), model=str(model))


def save_model_config(base_url: str, api_key: str, model: str, path: Path | None = None) -> Path:
    """Persist the user-provided config. The user may use ANY OpenAI-compatible
    endpoint; the values are stored verbatim and probed by test_connection()."""
    cfg_path = Path(path) if path else CONFIG_PATH
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    # json.dumps yields TOML-compatible basic-string escaping (backslashes, quotes)
    esc = lambda s: json.dumps(str(s))
    cfg_path.write_text(
        "# ~/.tardigrade/models.toml - managed by Tardigrade Skill settings UI\n"
        "[default]\n"
        f"base_url = {esc(base_url.strip().rstrip('/'))}\n"
        f"api_key = {esc(api_key.strip())}\n"
        f"model = {esc(model.strip())}\n",
        encoding="utf-8",
    )
    return cfg_path


def test_connection(config: ModelConfig) -> dict:
    """Probe the endpoint. Auto-detection: GET {base_url}/models (free, no tokens).

    - endpoint reachable AND /models implemented -> ok=True with detected model ids
    - reachable but /models missing (some gateways) -> ok=True, detected=None
    - unreachable / auth rejected -> ok=False with reason
    """
    try:
        resp = httpx.get(
            f"{config.base_url}/models",
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=httpx.Timeout(20.0),
        )
    except httpx.HTTPError as e:
        return {"ok": False, "message": f"endpoint unreachable: {e}"}
    if resp.status_code in (401, 403):
        return {"ok": False, "message": f"auth rejected (HTTP {resp.status_code}); check the api key"}
    if resp.status_code != 200:
        # gateway reachable, no /models route: accept without a model list
        return {"ok": True, "detected": None, "message": f"endpoint reachable (HTTP {resp.status_code}); /models not available, model name taken as-is"}
    try:
        ids = [m.get("id") for m in resp.json().get("data", []) if m.get("id")]
    except ValueError:
        return {"ok": True, "detected": None, "message": "endpoint reachable; /models response unrecognized"}
    exact = config.model in ids
    fuzzy = [i for i in ids if config.model.lower() in i.lower() or i.lower() in config.model.lower()]
    msg = f"detected {len(ids)} models" if ids else "endpoint reachable; /models returned no entries"
    if ids and not exact and fuzzy:
        msg += f"; closest to '{config.model}': {fuzzy[:3]}"
    elif ids and not exact:
        msg += f"; '{config.model}' not listed (endpoint may still accept it)"
    return {"ok": True, "detected": ids, "exact_match": exact, "message": msg}


def chat(config: ModelConfig, system_prompt: str, user_prompt: str) -> str:
    """One chat completion. Returns assistant text; raises RuntimeError on failure."""
    try:
        resp = httpx.post(
            f"{config.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {config.api_key}"},
            json={
                "model": config.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0,
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError(f"LLM request failed: {e}") from e
    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"unexpected LLM response shape: {e}") from e


def extract_json(text: str) -> dict[str, Any] | None:
    """Parse the first JSON object in a response (tolerates code fences)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                import json

                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None
