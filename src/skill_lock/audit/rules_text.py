"""Text-level rules: invisible Unicode smuggling, prompt injection, hidden instructions.

Applied to every text file in the skill (SKILL.md, references/, scripts/, ...).
"""

from __future__ import annotations

import re
from pathlib import Path

from .engine import Finding

# Zero-width / bidi / tag characters that allow hiding instructions in plain sight.
INVISIBLE_CHARS = {
    0x200B: "ZERO WIDTH SPACE",
    0x200C: "ZERO WIDTH NON-JOINER",
    0x200D: "ZERO WIDTH JOINER",
    0x200E: "LEFT-TO-RIGHT MARK",
    0x200F: "RIGHT-TO-LEFT MARK",
    0x202A: "LEFT-TO-RIGHT EMBEDDING",
    0x202B: "RIGHT-TO-LEFT EMBEDDING",
    0x202C: "POP DIRECTIONAL FORMATTING",
    0x202D: "LEFT-TO-RIGHT OVERRIDE",
    0x202E: "RIGHT-TO-LEFT OVERRIDE",
    0x2060: "WORD JOINER",
    0x2061: "FUNCTION APPLICATION",
    0x2062: "INVISIBLE TIMES",
    0x2063: "INVISIBLE SEPARATOR",
    0x2064: "INVISIBLE PLUS",
    0x2066: "LEFT-TO-RIGHT ISOLATE",
    0x2067: "RIGHT-TO-LEFT ISOLATE",
    0x2068: "FIRST STRONG ISOLATE",
    0x2069: "POP DIRECTIONAL ISOLATE",
    0xFEFF: "ZERO WIDTH NO-BREAK SPACE (BOM)",
    0x00AD: "SOFT HYPHEN",
    0x180E: "MONGOLIAN VOWEL SEPARATOR",
}

# (compiled regex, severity, rule_id, message)
INJECTION_PATTERNS: list[tuple[re.Pattern[str], str, str, str]] = [
    (
        re.compile(r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?)", re.I),
        "CRITICAL",
        "injection/override",
        "instruction override attempt ('ignore previous instructions')",
    ),
    (
        re.compile(r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|rules?|guidance)", re.I),
        "CRITICAL",
        "injection/override",
        "instruction override attempt ('disregard previous rules')",
    ),
    (
        re.compile(r"do\s+not\s+(tell|inform|reveal|show)\s+(it\s+to\s+)?(the\s+)?user", re.I),
        "CRITICAL",
        "injection/concealment",
        "concealment instruction ('do not tell the user')",
    ),
    (
        re.compile(r"(note|message|instruction|reminder)s?\s+to\s+(the\s+)?(agent|assistant|model|ai)\s*:", re.I),
        "HIGH",
        "injection/agent-note",
        "hidden 'note to the agent' section",
    ),
    (
        re.compile(r"<\s*/?\s*(system|assistant)\s*>|\bsystem\s*prompt\s*:", re.I),
        "CRITICAL",
        "injection/role-impersonation",
        "system/assistant role impersonation markup",
    ),
    (
        re.compile(r"you\s+are\s+now\s+(a|an|the)\s+", re.I),
        "HIGH",
        "injection/persona-hijack",
        "persona hijack pattern ('you are now a ...')",
    ),
    (
        re.compile(r"exfiltrat(?:e|ing|ion)|send\s+(?:the\s+)?(?:api[_ ]?key|credentials?|tokens?|ssh\s+keys?)\s+(?:to|via)", re.I),
        "CRITICAL",
        "exfiltration/intent",
        "credential exfiltration intent",
    ),
    (
        re.compile(r"\b(?:curl|wget)\b[^|;\n]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b", re.I),
        "CRITICAL",
        "execution/remote-script",
        "remote script piped into shell",
    ),
    (
        re.compile(r"[A-Za-z0-9+/]{80,}={0,2}"),
        "HIGH",
        "obfuscation/base64-blob",
        "large base64-like blob (possible obfuscated payload)",
    ),
    (
        re.compile(r"\.env\b|~?/?\.ssh/id_(?:rsa|ed25519)|\.aws/credentials", re.I),
        "HIGH",
        "credentials/reference",
        "references credential files (.env / .ssh / .aws)",
    ),
]


def scan_text_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return findings
    lines = text.splitlines()

    for i, line in enumerate(lines, start=1):
        for cp, label in INVISIBLE_CHARS.items():
            if chr(cp) in line:
                findings.append(
                    Finding(
                        rule_id="hidden/unicode-smuggling",
                        severity="CRITICAL",
                        file=str(path),
                        line=i,
                        message=f"invisible Unicode character U+{cp:04X} ({label})",
                    )
                )
                break  # one report per line is enough

    for i, line in enumerate(lines, start=1):
        for pattern, severity, rule_id, message in INJECTION_PATTERNS:
            if pattern.search(line):
                findings.append(
                    Finding(rule_id=rule_id, severity=severity, file=str(path), line=i, message=message)
                )
    return findings
