# Contributing to Tardigrade Skill

Thanks for your interest! The project is in alpha; issues and PRs are both welcome.

## Development setup

```bash
git clone https://github.com/Suygrx/Tardigrade-skill.git
cd Tardigrade-skill
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # Windows
# Linux/macOS: .venv/bin/python -m pip install -r requirements-dev.txt
```

Run the test suite (no API keys needed — L2 adaptation tests mock the model):

```bash
python -m pytest tests/ -q
```

Run the desktop app in dev mode (falls back to the default browser):

```bash
python desktop/main.py
```

## Project layout

```
core/       engine package (spec · audit · installer · lockfile · dispatcher · ir · profiles)
server/     FastAPI app — thin REST layer over core
desktop/    pywebview shell + frontend SPA (vanilla JS in desktop/static)
profiles/   platform profiles (add a platform = add a YAML card)
demo/       demo skills, including intentionally broken/evil ones used by tests
```

## Guidelines

- **Add a platform** by dropping a YAML profile into `profiles/` — no engine code changes required.
- **Engine changes** (`core/`) need test coverage in `tests/`; the suite must stay green without network access.
- **Audit rules**: extend `audit/rules_text.py` / `rules_code.py` and add a fixture under `demo/` plus a test. Keep rules conservative — false CRITICALs block installs.
- **Frontend** is dependency-free vanilla JS; user-facing strings go through the i18n dict (`I18N` in `desktop/static/app.js`, zh + en).
- Keep the spec validator strict about what it rejects; anything new should be a *warning* unless it makes a skill genuinely unloadable.

## Reporting security issues

Please do NOT open a public issue for vulnerabilities in the audit gate
(bypasses, smuggling techniques it misses). Open a GitHub security advisory
instead.
