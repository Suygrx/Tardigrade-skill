"""Audit package: static security gate for Agent Skills."""

from __future__ import annotations

from pathlib import Path

from .engine import AuditReport, Finding
from .rules_code import scan_scripts
from .rules_text import scan_text_file


def run_audit(skill_dir: Path) -> AuditReport:
    """Run all static rules against a skill directory."""
    report = AuditReport()
    skill_dir = Path(skill_dir)
    for p in sorted(skill_dir.rglob("*")):
        if p.is_file():
            report.findings.extend(scan_text_file(p))
    report.findings.extend(scan_scripts(skill_dir))
    return report
