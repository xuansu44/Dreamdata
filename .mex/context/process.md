---
name: process
description: How work flows from feature to release — Definition of Done, CI pipeline, code review, benchmarks, release policy, security. Load when shipping a feature, configuring CI, cutting a release, or auditing security posture.
triggers:
  - "definition of done"
  - "release"
  - "ci"
  - "code review"
  - "benchmark"
  - "security"
  - "0.1.0"
  - "shipping"
edges:
  - target: context/conventions.md
    condition: when applying coding rules to a shipped change
  - target: context/testing.md
    condition: when DoD references test layers or CI gates
  - target: context/decisions.md
    condition: when a process policy's reasoning is needed
  - target: context/setup.md
    condition: when CI reproduces local environment
last_updated: 2026-06-17 (git-ci-agent Monitor approach updated)
---

# Process

How work moves from "feature scoped" to "released". Locked 2026-06-17 alongside the coding conventions in `conventions.md`.

## Definition of Done

### Per feature (F-feature)

A single F-feature is "done" when ALL of:

1. **Tests green** — L1 (helpers used), L2 (each internal layer touched), L3 (SDK integration: happy + edge + error), L4 (property invariants), L5 (fuzz on input boundaries).
2. **Static gates pass** — `ruff check .`, `ruff format --check .`, `mypy --strict src/dreamdata/sdk.py`, coverage thresholds from `testing.md`.
3. **Verify Checklist complete** — every item in `conventions.md` → Verify Checklist passes.
4. **Architectural invariants asserted** — immutability, metadata-as-source-of-truth, DuckDB read-only (asserted in L3, not just code review).
5. **No forbidden mocks** — L2+ never mocks PostgreSQL / DuckDB / filesystem.
6. **Phase docs updated** — if user-visible behavior changed, `docs/source/quickstart.md` and the active `docs/source/phases/phase-N.md` are updated.
7. **GROW executed** — ROUTER "Current Project State" reflects new state; relevant `context/` files bumped; pattern created or updated if the task recurs.

### Per phase

A phase is "done" when ALL of:

1. Every F-feature in the phase is individually done.
2. **L8 acceptance E2E green** — the end-to-end pytest scenario under `tests/e2e/` passes for the full phase scope.
3. **L6 scale smoke passes** (if applicable) — 1M-row fixture within time/memory budget.
4. **L7 mutation score ≥ 85%** on `meta/`, `engine/`, `storage/` (nightly gate, not PR gate).
5. **Phase docs complete** — `docs/source/phases/phase-N.md` written; `sphinx-build` exits clean.
6. **Phase-boundary handoff** — Claude reports to PM: what works, what's deferred, any genuine product-level tradeoffs.

A phase is **not** "done" if the docs are missing even if all tests pass. See `decisions.md` → "Per-phase Python SDK documentation is mandatory".

## CI Pipeline

Three GitHub Actions workflows under `.github/workflows/`. All run on Linux runners; macOS dev-machine parity is enforced by local `uv run pytest`.

### `ci-pr.yml` — every pull request

Jobs:
1. **lint-and-types** — `ruff check`, `ruff format --check`, `mypy --strict src/dreamdata/sdk.py`, `mypy --check-untyped-defs --disallow-untyped-defs src/dreamdata` (excluding `sdk.py`).
2. **unit-component-sdk-fuzz** — `pytest tests/unit/ tests/component/ tests/sdk/ tests/fuzz/ -q`.
3. **security** — `uv pip audit`; `ruff` security rules (`S` band); grep for forbidden patterns (`os.getenv`, `print(` in `src/`).
4. **docs-build** — `uv run sphinx-build docs/source docs/build -W` (warnings as errors).

PostgreSQL service container: PostgreSQL 15 and 16 (matrix). DuckDB via uv lockfile (single pinned version per branch). Cache: `~/.cache/uv`, `~/.cache/pytest`.

### `ci-main.yml` — merge to main

Adds:
- L4 property tests
- L8 acceptance E2E
- Coverage upload (Codecov or local artifact)
- Build artifact: `sphinx-build` HTML, wheel via `uv build`.

### `ci-nightly.yml` — nightly

Adds:
- L6 scale smoke at 1M rows (separate job; cached generated fixture).
- L7 mutation testing (`mutmut run` on `meta/`, `engine/`, `storage/`). Mutation score < 85% opens a GitHub issue; does not fail the build.
- Benchmarks (see below) appended to `benchmarks/history.jsonl`.

### Required gates

- **PR must be green on `ci-pr.yml`** before merge.
- **`main` must be green on `ci-main.yml`** to cut a release tag.
- Nightly failures open issues, not page alerts.

## Code Review

- All changes via PR; no direct pushes to `main`.
- **Claude self-reviews before handoff** with the `simplify` and `security-review` skills. Both must be clean (or have explicit, recorded exceptions).
- **PM reviews at phase boundary only** — outcome-level (SDK surface, L8 scenario, phase docs). Per-feature review is explicitly NOT required (see `decisions.md`).
- Approvals: during Phase 1 and Phase 2 (pre-0.1.0), Claude's self-review plus green CI suffices for merge. Post-0.1.0, revisit whether a human approval step is needed.

## Performance Benchmarks (L6.5)

Lives under `tests/benchmarks/` using `pytest-benchmark`.

- Three fixture sizes: **1K, 10K, 100K rows** (deterministic, seeded, generated at test time — no committed large fixtures).
- Tracked operations: `register_dataset`, `scan` (full), `search` (field filter), `search` (tag filter), `search` (combined), `tag_rows`.
- Run on every merge to `main` (in `ci-main.yml`) and nightly.
- Results appended to `benchmarks/history.jsonl` (one JSON line per run per operation per size).
- **Regression policy:** > 10% slowdown vs the previous main build emits a warning comment on the PR (or a nightly issue); does NOT fail the build. > 25% slowdown blocks the merge.
- Calibration: after Phase 1 L8 green, capture baseline numbers and commit them to `benchmarks/baseline-phase-1.json`. Future comparisons are against the most recent main, not against phase-1 baseline.

## Release Policy

- **`0.0.x` dev tags** during Phase 1 and Phase 2 — no SemVer stability guarantee. SDK API may break between dev tags.
- **`v0.1.0`** cuts after Phase 2 L8 green + PM sign-off — first public release. See `decisions.md`.
- **`CHANGELOG.md`** maintained from day one (Keep a Changelog format; sections: Added / Changed / Removed / Fixed).
- **Tagging:** `git tag v0.0.x` after each phase boundary; `git tag v0.1.0` at release.
- Post-0.1.0: breaking API changes require a minor bump (`0.2.0`) and a migration note in CHANGELOG.
- **Git & CI Agent** (2026-06-17 added, replaces old release-agent):
  - Project-level Claude Code agent under `.claude/agents/git-ci-agent.md`
  - Automates: commit staging/writing → push to remote → GitHub Actions CI monitoring (Monitor tool with 30s polling — tracks both `ci-pr` and `ci-main` until completion) → test report analysis
  - Requires: GitHub CLI (`gh`) authenticated, git remote configured

## Security Conventions

- **Dataset names** must match `^[a-zA-Z0-9_-]{1,128}$` — enforced at the SDK boundary, before any filesystem or SQL use. Rejects path traversal (`../`), null bytes, absolute paths, empty strings.
- **SQL** is 100% parameterized in `meta/`. No f-strings, no `%` formatting, no `.format()` for SQL assembly. Table/column names (which cannot be parameterized) come from a closed allow-list in the repository layer.
- **Secrets** (`DATABASE_URL`, `USER_ID`) are `SecretStr` in `Settings`; their `repr` is masked; they are never logged, never echoed in error messages, never included in exception `__str__`.
- **File paths** from user input go through a single path-relativization helper (`storage/paths.py`) that resolves, normalizes, and asserts the result stays inside `WORKSPACE_PATH`. Symlinks pointing outside the workspace are rejected.
- **Tag/note values** are length-capped (configurable, default 4 KB) and unicode-normalized (NFC) at write time to prevent storage abuse and ambiguity.
- **`uv pip audit`** runs in CI; new advisories block the PR.
- No `eval`, no `exec`, no `pickle` of untrusted data anywhere in `src/`.
