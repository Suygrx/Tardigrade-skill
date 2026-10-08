"""Code-level rules for scripts/: AST checks for Python, regex checks for shell."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from .engine import Finding

# attribute chains treated as dangerous callables: module.function
DANGEROUS_CALLS: dict[str, tuple[str, str]] = {
    "os.system": ("CRITICAL", "code/shell-exec"),
    "os.popen": ("CRITICAL", "code/shell-exec"),
    "os.execv": ("CRITICAL", "code/exec-replace"),
    "subprocess.run": ("HIGH", "code/subprocess"),
    "subprocess.call": ("HIGH", "code/subprocess"),
    "subprocess.Popen": ("HIGH", "code/subprocess"),
    "subprocess.check_output": ("HIGH", "code/subprocess"),
    "eval": ("CRITICAL", "code/dynamic-eval"),
    "exec": ("CRITICAL", "code/dynamic-eval"),
    "pickle.loads": ("HIGH", "code/unsafe-deserialize"),
    "yaml.load": ("HIGH", "code/unsafe-deserialize"),
}

SENSITIVE_ENV_RE = re.compile(r"(token|secret|api_?key|passwd|password|credential)", re.I)
SENSITIVE_PATHS_RE = re.compile(
    r"\.ssh/|/\.ssh\b|id_rsa|id_ed25519|\.aws|\.gnupg|\.env\b|cookies\.sqlite|Login Data",
    re.I,
)
NETWORK_MODULES = {"requests", "httpx", "urllib.request", "socket"}
TRAVERSAL_RE = re.compile(r"(?:\.\./){2,}")


def _call_name(node: ast.Call) -> str | None:
    parts: list[str] = []
    obj = node.func
    while isinstance(obj, ast.Attribute):
        parts.append(obj.attr)
        obj = obj.value
    if isinstance(obj, ast.Name):
        parts.append(obj.id)
        return ".".join(reversed(parts))
    if isinstance(obj, ast.Name) is False and parts:
        return parts[-1]  # bare builtin like eval/exec reached via attr-less node
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _has_shell_true(node: ast.Call) -> bool:
    for kw in node.keywords:
        if kw.arg == "shell":
            return True
    return False


def scan_python_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return findings

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name is None:
            continue
        hit = DANGEROUS_CALLS.get(name)
        if hit is None and name in {"system", "popen", "run", "call", "Popen", "check_output"}:
            # os.system imported as `from os import system`
            hit = ("HIGH", "code/shell-exec-or-subprocess")
        if hit:
            severity, rule_id = hit
            msg = f"call to {name}()"
            if name.startswith("subprocess") and _has_shell_true(node):
                severity, msg = "CRITICAL", f"call to {name}(shell=True)"
            findings.append(
                Finding(rule_id=rule_id, severity=severity, file=str(path), line=node.lineno, message=msg)
            )

        # os.environ access to sensitive keys
        if isinstance(node.func, ast.Subscript) or name == "os.environ.get":
            pass
    # separate pass: subscript/get on os.environ with sensitive names
    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            target = node.value
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"get", "getenv"}:
            target = node.func.value
        if target is not None:
            base = ""
            if isinstance(target, ast.Attribute):
                base = target.attr
            elif isinstance(target, ast.Name):
                base = target.id
            if base in {"environ", "getenv", "os"}:
                src = ast.unparse(node) if hasattr(ast, "unparse") else ""
                if SENSITIVE_ENV_RE.search(src):
                    findings.append(
                        Finding(
                            rule_id="code/credential-env",
                            severity="HIGH",
                            file=str(path),
                            line=getattr(node, "lineno", 0),
                            message=f"reads sensitive environment variable: {src[:80]}",
                        )
                    )

    # string constants: sensitive paths and traversal
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if SENSITIVE_PATHS_RE.search(node.value):
                findings.append(
                    Finding(
                        rule_id="code/credential-path",
                        severity="HIGH",
                        file=str(path),
                        line=node.lineno,
                        message=f"references sensitive path: {node.value[:60]}",
                    )
                )
            if TRAVERSAL_RE.search(node.value):
                findings.append(
                    Finding(
                        rule_id="code/path-traversal",
                        severity="HIGH",
                        file=str(path),
                        line=node.lineno,
                        message="path traversal pattern ('../../') in string literal",
                    )
                )
    return findings


SHELL_PATTERNS: list[tuple[re.Pattern[str], str, str, str]] = [
    (re.compile(r"\b(?:curl|wget)\b[^|;\n]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b", re.I), "CRITICAL", "execution/remote-script", "remote script piped into shell"),
    (re.compile(r"\bbase64\s+(-d|--decode)\b", re.I), "HIGH", "obfuscation/base64-decode", "base64 decoding in shell script"),
    (re.compile(r"\brm\s+-rf\s+[/~]", re.I), "CRITICAL", "code/destructive-rm", "destructive 'rm -rf /' or '~'"),
    (re.compile(r"\beval\b"), "HIGH", "code/dynamic-eval", "use of eval in shell script"),
    (re.compile(r"\b(?:cat|less|more)\b.*id_rsa|scp\b.*id_rsa", re.I), "CRITICAL", "credentials/ssh-key", "reads SSH private key"),
    (re.compile(r"\bcrontab\b|\blaunchctl\b|/etc/(?:passwd|sudoers)", re.I), "HIGH", "persistence/system-config", "persistence or system config manipulation"),
]


def scan_shell_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return findings
    for i, line in enumerate(text.splitlines(), start=1):
        for pattern, severity, rule_id, message in SHELL_PATTERNS:
            if pattern.search(line):
                findings.append(
                    Finding(rule_id=rule_id, severity=severity, file=str(path), line=i, message=message)
                )
    return findings


def scan_scripts(skill_dir: Path) -> list[Finding]:
    findings: list[Finding] = []
    for p in sorted(Path(skill_dir).rglob("*")):
        if not p.is_file():
            continue
        if p.suffix == ".py":
            findings.extend(scan_python_file(p))
        elif p.suffix in {".sh", ".bash", ".zsh"}:
            findings.extend(scan_shell_file(p))
    return findings
