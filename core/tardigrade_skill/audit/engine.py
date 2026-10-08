"""Static security gate: audit findings and severity model."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SEVERITY_ORDER = {"LOW": 0, "HIGH": 1, "CRITICAL": 2}

TEXT_EXTENSIONS = {".md", ".txt", ".py", ".sh", ".js", ".ts", ".json", ".yaml", ".yml", ".toml"}


@dataclass
class Finding:
    rule_id: str
    severity: str  # LOW | HIGH | CRITICAL
    file: str
    line: int | None
    message: str

    def __str__(self) -> str:
        loc = f"{self.file}:{self.line}" if self.line else self.file
        return f"[{self.severity}] {loc} ({self.rule_id}) {self.message}"


@dataclass
class AuditReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(f.severity == "CRITICAL" for f in self.findings)

    def summary(self) -> str:
        counts = {s: sum(1 for f in self.findings if f.severity == s) for s in ("CRITICAL", "HIGH", "LOW")}
        verdict = "BLOCKED" if self.blocked else "PASS"
        return (
            f"audit: {verdict} | CRITICAL={counts['CRITICAL']} HIGH={counts['HIGH']} LOW={counts['LOW']} "
            f"({len(self.findings)} findings)"
        )


def iter_text_files(skill_dir: Path):
    """Yield text files inside the skill directory (SKILL.md plus everything else)."""
    for p in sorted(Path(skill_dir).rglob("*")):
        if p.is_file() and p.suffix.lower() in TEXT_EXTENSIONS:
            yield p
