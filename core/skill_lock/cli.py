"""skill-lock CLI: validate / audit / install / list / check."""

from __future__ import annotations

import tempfile
from pathlib import Path

import typer

from . import __version__
from .audit import run_audit
from .dispatcher import DispatchError, dispatch, target_dir
from .installer import SourceError, find_skill_dirs, resolve_source
from .lockfile import LockFile, build_entry
from .spec import SpecError, validate_skill

app = typer.Typer(help="Package manager for Agent Skills: reproducible, audited installs.", no_args_is_help=True)


def _echo_findings(report) -> None:
    for f in report.findings:
        typer.secho(f"  {f}", fg="red" if f.severity == "CRITICAL" else ("yellow" if f.severity == "HIGH" else None))


@app.command()
def validate(path: Path = typer.Argument(..., help="Skill directory to validate.")) -> None:
    """Validate a skill directory against the Agent Skills spec."""
    problems = validate_skill(path)
    if problems:
        for p in problems:
            typer.secho(f"INVALID: {p}", fg="red")
        raise typer.Exit(1)
    typer.secho(f"valid: {path} conforms to the Agent Skills spec", fg="green")


@app.command()
def audit(
    path: Path = typer.Argument(..., help="Skill directory to audit."),
    allow_risk: bool = typer.Option(False, "--allow-risk", help="Exit 0 even if CRITICAL findings exist (still reported)."),
) -> None:
    """Run the static security gate against a skill directory."""
    report = run_audit(path)
    typer.echo(report.summary())
    _echo_findings(report)
    if report.blocked and not allow_risk:
        raise typer.Exit(2)


@app.command()
def install(
    source: str = typer.Argument(..., help="Local dir, .zip archive, or git URL."),
    to: str = typer.Option(..., "--to", help="Target agent id (claude-code, codex, gemini-cli, cursor, opencode)."),
    project: bool = typer.Option(False, "--project", help="Install into the current project instead of the user home."),
    dest: Path = typer.Option(None, "--dest", help="Override the target directory entirely."),
    allow_risk: bool = typer.Option(False, "--allow-risk", help="Proceed even if the audit gate reports CRITICAL findings."),
    lock_root: Path = typer.Option(Path.cwd(), "--lock-root", hidden=True),
) -> None:
    """Audited install pipeline: resolve → validate → audit → lock → dispatch."""
    with tempfile.TemporaryDirectory(prefix="skill-lock-") as tmp:
        workdir = Path(tmp)
        try:
            root, source_desc, resolved_sha = resolve_source(source, workdir)
        except SourceError as e:
            typer.secho(f"source error: {e}", fg="red")
            raise typer.Exit(1)

        skill_dirs = find_skill_dirs(root)
        if not skill_dirs:
            typer.secho("no skill directories found (no SKILL.md within 2 levels)", fg="red")
            raise typer.Exit(1)

        lock = LockFile.load(lock_root)
        installed: list[str] = []
        for skill_dir in skill_dirs:
            problems = validate_skill(skill_dir)
            if problems:
                typer.secho(f"skip {skill_dir.name}: {problems[0]}", fg="red")
                continue

            report = run_audit(skill_dir)
            typer.echo(f"{skill_dir.name}: {report.summary()}")
            _echo_findings(report)
            if report.blocked and not allow_risk:
                typer.secho(f"blocked: {skill_dir.name} has CRITICAL findings (use --allow-risk to override)", fg="red")
                raise typer.Exit(2)

            try:
                target = dispatch(skill_dir, to, project=project, dest_override=dest)
            except DispatchError as e:
                typer.secho(str(e), fg="red")
                raise typer.Exit(1)

            lock.record(build_entry(skill_dir.name, source_desc, skill_dir, resolved_sha=resolved_sha))
            installed.append(f"{skill_dir.name} -> {target}")

        if installed:
            lock_path = lock.save(lock_root)
            for line in installed:
                typer.secho(f"installed: {line}", fg="green")
            typer.echo(f"lockfile updated: {lock_path}")
        else:
            typer.secho("nothing installed", fg="yellow")
            raise typer.Exit(1)


@app.command("list")
def list_cmd(
    lock_root: Path = typer.Option(Path.cwd(), "--lock-root", help="Directory containing skills.lock."),
) -> None:
    """List skills recorded in the lockfile."""
    lock = LockFile.load(lock_root)
    if not lock.entries:
        typer.echo("no skills in lockfile (run: skill-lock install ...)")
        return
    for name, entry in lock.entries.items():
        typer.echo(f"{name}  source={entry.source}  rev={entry.rev or '-'}  files={len(entry.files)}  at={entry.installed_at}")


@app.command()
def check(
    name: str = typer.Argument(..., help="Skill name recorded in the lockfile."),
    location: Path = typer.Argument(..., help="Directory where the skill is installed."),
    lock_root: Path = typer.Option(Path.cwd(), "--lock-root"),
) -> None:
    """Verify installed files still match the lockfile hashes (rug-pull / tamper detection)."""
    lock = LockFile.load(lock_root)
    tampered = lock.check(location, name)
    if tampered:
        typer.secho(f"TAMPERED ({len(tampered)}):", fg="red")
        for t in tampered:
            typer.secho(f"  {t}", fg="red")
        raise typer.Exit(1)
    typer.secho(f"ok: {name} matches the lockfile ({len(lock.entries[name].files)} files verified)", fg="green")


def _targets_completer() -> None:  # pragma: no cover - helper for docs only
    for agent in sorted({"claude-code", "codex", "gemini-cli", "cursor", "opencode"}):
        typer.echo(agent)


@app.command()
def targets() -> None:
    """Show supported target agents and their directories."""
    for agent, (glob, proj) in sorted(target_map().items()):
        typer.echo(f"{agent:12s} global={glob}  project={proj}")


def target_map() -> dict[str, tuple[str, str]]:
    from .dispatcher import TARGETS

    return {k: (str(Path(v[0]).expanduser()), v[1]) for k, v in TARGETS.items()}


@app.callback()
def main_callback(
    version: bool = typer.Option(None, "--version", callback=lambda v: _print_version(v), is_eager=True),
) -> None:
    pass


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"skill-lock {__version__}")
        raise typer.Exit()


def main() -> None:  # entry point for [project.scripts]
    app()


if __name__ == "__main__":
    main()
