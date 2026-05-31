---
description: "Use when modifying CoParenTime FastAPI app, config parsing, scheduling logic, or tests. Enforces local-first workflow, deterministic planning behavior, and project task conventions."
name: "CoParenTime FastAPI Conventions"
applyTo: "app/**/*.py, tests/**/*.py, README.md"
---
# CoParenTime FastAPI Conventions

- Treat these conventions as default preferences; allow exceptions when the task explicitly needs a different approach.

- Prefer workspace tasks over ad-hoc commands for routine workflows:
  - `CoParenTime: Test`
  - `CoParenTime: Run App`
  - `CoParenTime: Run App (Reload)`
- Use the project virtual environment interpreter for Python commands (`.venv/Scripts/python.exe` on Windows).

- Preserve deterministic planning behavior unless the task explicitly requests behavior changes.
- Keep timezone assumptions aligned with project docs (Europe/London) when touching date/time logic.

- Treat partner availability text so plain lines are availability windows.
- Treat `exclude:` and `unavailable:` entries as exclusion windows.
- Keep backward compatibility for legacy `kidfree:` entries unless removal is explicitly requested.

- When adding fields to runtime config models, update impacted tests that instantiate config objects directly.
- Keep local config (`coparentime.local.json`) local-only and out of commits.

- When changing API response shapes or scheduling/report outputs, update tests in the same change.
- Keep changes minimal and focused; avoid unrelated refactors in the same edit.