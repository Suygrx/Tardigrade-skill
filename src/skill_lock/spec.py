"""SKILL.md parsing and validation against the Agent Skills spec (agentskills.io)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NAME_MAX = 64
DESC_MAX = 1024
COMPAT_MAX = 500

ALLOWED_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}


class SpecError(Exception):
    """Raised when a SKILL.md cannot be parsed or violates the spec."""


class SkillMeta(BaseModel):
    """Frontmatter schema per https://agentskills.io/specification."""

    name: str
    description: str
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] | None = None
    allowed_tools: str | None = Field(default=None, alias="allowed-tools")

    model_config = {"populate_by_name": True}

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        if not 1 <= len(v) <= NAME_MAX:
            raise ValueError(f"name must be 1-{NAME_MAX} characters, got {len(v)}")
        if not NAME_RE.match(v):
            raise ValueError(
                "name may only contain lowercase letters, digits and single hyphens "
                "(no leading/trailing/consecutive hyphens)"
            )
        return v

    @field_validator("description")
    @classmethod
    def _check_description(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must be non-empty")
        if len(v) > DESC_MAX:
            raise ValueError(f"description must be at most {DESC_MAX} characters, got {len(v)}")
        return v

    @field_validator("compatibility")
    @classmethod
    def _check_compat(cls, v: str | None) -> str | None:
        if v is not None and len(v) > COMPAT_MAX:
            raise ValueError(f"compatibility must be at most {COMPAT_MAX} characters, got {len(v)}")
        return v

    @field_validator("metadata")
    @classmethod
    def _check_metadata(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        if v is not None:
            for k, val in v.items():
                if not isinstance(k, str) or not isinstance(val, str):
                    raise ValueError("metadata must map string keys to string values")
        return v


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split SKILL.md content into (frontmatter_dict, markdown_body)."""
    if not text.startswith("---"):
        raise SpecError("SKILL.md must start with a YAML frontmatter block (---)")
    end = text.find("\n---", 3)
    if end == -1:
        raise SpecError("frontmatter block is not closed (missing ---)")
    fm_text = text[3:end].strip("\n")
    body = text[end + 4 :]
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        raise SpecError(f"invalid YAML frontmatter: {e}") from e
    if not isinstance(fm, dict):
        raise SpecError("frontmatter must be a YAML mapping")
    return fm, body


def load_skill(skill_dir: Path) -> tuple[SkillMeta, str, list[str]]:
    """Load and validate a skill directory.

    Returns (meta, body, warnings). Raises SpecError on hard violations.
    """
    skill_dir = Path(skill_dir)
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise SpecError(f"missing SKILL.md in {skill_dir}")
    fm, body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))

    warnings: list[str] = []
    unknown = set(fm) - ALLOWED_FIELDS
    if unknown:
        warnings.append(f"unexpected frontmatter fields: {', '.join(sorted(unknown))}")

    try:
        meta = SkillMeta.model_validate(fm)
    except Exception as e:  # pydantic.ValidationError
        details = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())
        raise SpecError(details) from e

    if meta.name != skill_dir.name:
        raise SpecError(f"name '{meta.name}' must match the parent directory name '{skill_dir.name}'")

    return meta, body, warnings


def validate_skill(skill_dir: Path) -> list[str]:
    """Validate a skill directory, returning a list of problems (empty = valid)."""
    problems: list[str] = []
    skill_dir = Path(skill_dir)
    if not skill_dir.is_dir():
        return [f"not a directory: {skill_dir}"]
    try:
        _, _, warns = load_skill(skill_dir)
        problems.extend(warns)
    except SpecError as e:
        problems.append(str(e))
    return problems
