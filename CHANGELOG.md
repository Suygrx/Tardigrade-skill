# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versioning: SemVer.

## [Unreleased]

### Added
- Desktop app (pywebview + FastAPI): CC-Switch-style UI with platform cards,
  Skills 管理 (library + per-platform toggles), market search with built-in audit,
  adaptation matrix, HITL pending queue, and zh/en language switching.
- Same-repo skill grouping in Skills 管理 with collapsible cards.
- Batch adaptation (`一键适配`): bucketed dispatch across all detected platforms.
- LLM config survives restarts; masked-key display, empty key = keep existing.

### Changed
- Product display name unified to **Tardigrade Skill** (window title, app UI, README,
  FastAPI title, LLM system prompt). The PyPI distribution name / CLI command stay
  `tardigrade-skill`, and the desktop bundle now builds to `dist/Tardigrade Skill/`.
- PyInstaller spec is now path-agnostic (`SPECPATH`-relative `pathex` / `datas`), so
  the build works no matter what the checkout folder is called.

### [0.2.0] - 2026-10
- SkillIR + platform profiles; deterministic rule layer (L0/L1) judging
  `full` / `full*` / `adapted` / `partial` / `incompatible` per skill × platform.
- BYOK LLM adaptation (L2) with canary fencing, forced-JSON changelog,
  coverage self-check, and fixation of confirmed products.
- HITL: adaptation products land in a pending queue and are installed only
  after human confirmation.
- Local skill library with market download (dual-source discovery) and
  local import, both gated by the static audit engine.
- Per-file SHA-256 lockfile (`skills.lock`) with `check` verification.
