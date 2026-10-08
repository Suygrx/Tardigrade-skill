"""Deterministic tier judgment: skill × platform -> full / adapted / partial / incompatible.

M1 scope: L0/L1 deterministic rules only. The `adapted` tier marks "a degradable
gap exists; LLM adaptation (L2, BYOK) can produce an installable variant — pending
until M2 lands". Output is transparent: every cell carries reasons, gaps, caveats
and (for resident-rules degradation) a resident token cost estimate (doc §21).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .ir import SkillIR, build_ir
from .profiles import PlatformProfile
from .spec import SpecError

TIERS = ("full", "adapted", "partial", "incompatible")


@dataclass
class Judgment:
    agent: str
    skill: str
    tier: str  # full | full* | adapted | partial | incompatible
    reasons: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)  # capabilities the platform lacks
    caveats: list[str] = field(default_factory=list)  # supported-but-confirm items
    resident_tokens: int | None = None  # rough cost when degraded to resident rules

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "skill": self.skill,
            "tier": self.tier,
            "reasons": self.reasons,
            "gaps": self.gaps,
            "caveats": self.caveats,
            "resident_tokens": self.resident_tokens,
        }


def _judge(ir: SkillIR, profile: PlatformProfile) -> Judgment:
    reasons: list[str] = []
    gaps: list[str] = []
    caveats: list[str] = []

    for cap, needed in ir.requires.items():
        if not needed:
            continue
        cap_obj = profile.capabilities.get(cap)
        if cap_obj is None or not cap_obj.supported:
            gaps.append(cap)
        elif cap_obj.caveat:
            caveats.append(f"{cap}: {cap_obj.caveat}")

    script_gap = bool(ir.scripts) and profile.script_runtime is None

    # 1. no skill mechanism at all -> degrade to resident rules (needs LLM rewrite + HITL)
    if profile.discovery == "none":
        return Judgment(
            agent=profile.id,
            skill=ir.name,
            tier="adapted",
            reasons=["platform has no skill mechanism; degrade to resident rules"],
            gaps=gaps or ["skill-mechanism"],
            caveats=caveats,
            resident_tokens=ir.body_chars // 4,
        )

    # 2. scripts cannot run on this platform -> manual steps, not auto-adaptable
    if script_gap:
        reasons.append(f"platform cannot execute scripts ({len(ir.scripts)} script files); manual run required")
        return Judgment(
            agent=profile.id,
            skill=ir.name,
            tier="partial",
            reasons=reasons,
            gaps=gaps + [f"script-runtime:{profile.script_runtime or 'none'}"],
            caveats=caveats,
        )

    # 3. resident-rules discovery (e.g. rules-only platforms): degradable via LLM rewrite
    if profile.discovery == "resident-rules":
        return Judgment(
            agent=profile.id,
            skill=ir.name,
            tier="adapted",
            reasons=["no automatic skill triggering; description would become resident rules"],
            gaps=["auto-trigger"],
            caveats=caveats,
            resident_tokens=ir.body_chars // 4,
        )

    # 4. native skills: capability gaps decide
    if gaps:
        reasons.append(f"capability gap(s) not carried natively: {', '.join(gaps)}; LLM adaptation can rewrite around them")
        return Judgment(
            agent=profile.id,
            skill=ir.name,
            tier="adapted",
            reasons=reasons,
            gaps=gaps,
            caveats=caveats,
        )

    if caveats:
        reasons.append("all required capabilities supported; execution needs confirmation on this platform")
        return Judgment(agent=profile.id, skill=ir.name, tier="full*", reasons=reasons, caveats=caveats)

    reasons.append("all required capabilities supported natively")
    return Judgment(agent=profile.id, skill=ir.name, tier="full", reasons=reasons)


def judge_skill(skill_dir: Path, profile: PlatformProfile) -> Judgment:
    """Judge one skill directory against one platform profile."""
    try:
        ir = build_ir(skill_dir)
    except SpecError as e:
        return Judgment(agent=profile.id, skill=Path(skill_dir).name, tier="incompatible", reasons=[f"spec violation: {e}"])
    return _judge(ir, profile)
