"""Platform Profile: declarative capability card per target agent (doc §16/§22).

Adding a platform = adding one YAML file, zero code. Capabilities carry optional
caveats; a supported-but-caveated capability yields the `full*` verdict (usable,
but execution needs confirmation) — misjudging as safe is worse than under-promising.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class Capability(BaseModel):
    supported: bool = True
    caveat: str | None = None


class PlatformProfile(BaseModel):
    id: str
    name: str
    discovery: str = "native-skills"  # native-skills | resident-rules | none
    frontmatter_fields: list[str] = Field(default_factory=lambda: ["name", "description", "license", "compatibility", "metadata", "allowed-tools"])
    capabilities: dict[str, Capability] = Field(
        default_factory=lambda: {k: Capability() for k in ("shell", "network", "fs_write")}
    )
    script_runtime: str | None = "python"  # None = platform cannot execute scripts
    notes: str = ""

    @property
    def supports_skills(self) -> bool:
        return self.discovery == "native-skills"


def load_profiles(profiles_dir: Path) -> dict[str, PlatformProfile]:
    """Load every *.yaml in the directory. Returns id -> profile."""
    profiles: dict[str, PlatformProfile] = {}
    profiles_dir = Path(profiles_dir)
    if not profiles_dir.is_dir():
        return profiles
    for p in sorted(profiles_dir.glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        profile = PlatformProfile.model_validate(data)
        profiles[profile.id] = profile
    return profiles


def default_profiles_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "profiles"
