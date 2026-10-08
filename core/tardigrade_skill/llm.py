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
