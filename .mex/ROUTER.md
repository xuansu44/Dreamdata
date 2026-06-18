---
name: router
description: Session bootstrap and navigation hub. Read at the start of every session before any task. Contains project state, routing table, and behavioural contract.
edges:
  - target: context/architecture.md
    condition: when working on system design, integrations, or understanding how components connect
  - target: context/stack.md
    condition: when working with specific technologies, libraries, or making tech decisions
  - target: context/conventions.md
    condition: when writing new code, reviewing code, or unsure about project patterns
  - target: context/process.md
    condition: when shipping a feature, configuring CI, cutting a release, or auditing security
  - target: context/decisions.md
    condition: when making architectural choices or understanding why something is built a certain way
  - target: context/setup.md
    condition: when setting up the dev environment or running the project for the first time
  - target: context/versioning.md
    condition: when working on versions, map/filter_map, append, or row_sources
  - target: context/metadata-schema.md
    condition: when designing PostgreSQL schema or writing repository code
  - target: context/query-and-indexing.md
    condition: when working on search, filters, indexing, or scan performance
  - target: context/testing.md
    condition: when writing tests, designing coverage, or questioning whether something can be tested
  - target: patterns/INDEX.md
    condition: when starting a task — check the pattern index for a matching pattern file
last_updated: 2026-06-18 (v0.5.0 released - Web UI Permission Management complete!)
---

# Session Bootstrap

If you haven't already read `AGENTS.md`, read it now — it contains the project identity, non-negotiables, and commands.

Then read this file fully before doing anything else in this session.

## Current Project State

**Working:**
- **Git & CI Agent updated!** (2026-06-17). Monitor-based CI tracking:
  - `.claude/agents/git-ci-agent.md` - Agent definition (replaces old release-agent)
  - Features: commit management, push to remote, GitHub Actions CI monitoring (Monitor tool with 30s polling — replaces broken `gh run watch` approach)
  - Pattern: `.mex/patterns/git-ci-workflow.md
- **Local Test Agent enhanced!** (2026-06-18). Comprehensive local testing with semantic docs checks:
  - `.claude/agents/local-test-agent.md` - Full agent definition
  - `scripts/run_local_tests.py` - Enhanced runner with:
    - Semantic docs checks: version consistency, SDK API consistency, library usage consistency, feature consistency
    - Tech debt detection: TODO/FIXME, unused imports, complex functions
    - 8-layer test support, bilingual docs build check
  - Pattern: `.mex/patterns/local-testing.md`
- **Phase 1 complete!** `v0.0.1` dev tag (2026-06-17).
  - F1–F10: register, list/info, tag rows, note rows, field search, tag search, combined search, delete, rename, overwrite.
  - 8-layer test suite (L1–L8) implemented and passing — 220 tests + 1M-row scale smoke.
  - Concurrency bugfix: `register_dataset` reordered so DB insertion happens before filesystem operations to prevent race conditions; `test_concurrent_register_same_name_one_wins` updated.
  - Sphinx docs (`docs/source/phases/phase-1.md`) written; `sphinx-build -W` exits clean.
  - **Bilingual (English / 简体中文) docs added**; Chinese translation for all user-facing pages, with inter-language links in headers.
  - Ruff clean, ruff format clean, mypy --strict clean on `sdk.py`, mypy clean on internals.
  - Coverage 92% overall (target ≥80%); per-module gaps tracked under Known issues.
  - PostgreSQL schema applied via `alembic 0001_initial`; `dreamdata` and `dreamdata_test` databases provisioned.
- **Phase 2 complete!** `v0.0.2` dev tag (2026-06-17).
  - F11: multi-user tag isolation (tags/notes private by default; `user_id="*"` to see all)
  - F12: advanced filters (regex/range/IN/boolean combinations)
  - F13: field indexes (create index, list indexes)
  - F14: index and file_stats pruning (automatic when index exists)
  - F15: drop index
  - Alembic migration `0002_field_index` added
  - Phase-2 SDK surface: `search_with_filter`, `create_index`, `drop_index`, `list_indexes`; plus filter helpers `eq_filter`, `range_filter`, `in_filter`, `regex_filter`, `and_filter`, `or_filter`
  - `tags()`, `notes()`, `search_by_tag()`, `search()` now accept `user_id` parameter
  - `file_stats` now collects stats for nested fields too
  - `rename_dataset` now updates `file_stats` paths in addition to `row_sources`
  - 219/220 tests passing (1 skipped); 8-layer suite continues to pass
  - Sphinx docs (`docs/source/phases/phase-2.md`) written
- **v0.1.0 released!** (2026-06-17). First public stable release with SemVer guarantee.
- **v0.2.0 released!** (2026-06-17). Phase 3 (versioning) + Phase 4 (Parquet cache) shipped!
  - Phase 3: F16-F22 (list_versions, get_version, append, map, filter_map, overwrite creates new version, tag inheritance)
  - Phase 4: F23-F26 (refresh_parquet_cache, list_parquet_caches, auto cache stub, cost-based routing stub)
  - Alembic migrations 0002_field_index, 0003_parquet_caches
  - Optional pyarrow dependency for Parquet cache
  - 219/220 tests passing (1 skipped)
  - Sphinx docs updated (phase-3.md, phase-4.md, quickstart, installation, index)
- **v0.3.0 released!** (2026-06-18). Phase 5 (REST API + Web UI) shipped!
  - Phase 5: F27-F35 (FastAPI REST server, version API, tag/note API, search API, index API, Parquet cache API, Web UI dataset explorer, Web UI tag/note editor, Web UI search & filter)
  - FastAPI added as dependency, with auto-generated OpenAPI docs at `/docs`
  - Web UI at `/` - React-based dataset explorer with search, tagging, annotations
  - 257/258 tests passing (1 skipped)
  - All lint/mypy checks clean, CI green
- **v0.4.0 released!** (2026-06-18). Phase 6 (User Authentication & Permissions) shipped!
  - Phase 6: F36-F50 (users table, password hashing, JWT tokens, API keys, fine-grained permissions, auth endpoints, user management, permission management)
  - Alembic migration `0004_users_permissions` adds `users`, `api_keys`, `dataset_permissions`, `password_reset_tokens` tables
  - New dependencies: `python-jose[cryptography]`, `email-validator`, optional `argon2-cffi`
  - Backward compatibility: old `X-API-Key` + `X-User-ID` continue to work; existing datasets default to admin-only access
  - 255/255 tests passing; all lint/mypy checks clean, CI green
- Testing strategy designed and locked (2026-06-17) — 8-layer fully-automated model, no manual-exploratory layer. See `.mex/context/testing.md`.
- Coding conventions locked (2026-06-17) — Git workflow, error hierarchy, logging, config, type hints, comments, dependency management added to `.mex/context/conventions.md`.
- Process policies locked (2026-06-17) — DoD, CI pipeline, code review, benchmarks, release policy, security in `.mex/context/process.md`. Phase-boundary review, 0.1.0 after Phase 2, per-phase SDK docs mandatory. See `.mex/context/decisions.md`.
- Stack TBDs resolved (2026-06-17) — package `dreamdata`; driver psycopg v3 (sync); migration Alembic; pydantic v2; no ORM; no async until FastAPI. See `.mex/context/stack.md`.

**Phase-1 technical decisions (executed 2026-06-17):**
- **Read engine = Python JSONL streaming, not DuckDB query path.** DuckDB's parallel `read_json_auto` returned rows out of source order at 1M scale, breaking the per-file `row_idx → global row_idx` mapping. Pure-Python streaming is simple, correct at 1M rows, and keeps the architectural invariant ("DuckDB never writes business data") trivially intact. DuckDB stays in deps for the Phase 2 columnar/index path. Recorded in `context/decisions.md`.
- **psycopg autocommit=True + explicit `transaction()` for multi-statement ops.** Tag/note writes from one Engine become visible to a second Engine in the same process — required for thread-safety tests and the future REST handlers.
- **Atomic overwrite via `.{name}.bak.<uuid>` workspace move.** A failed `register_dataset(..., overwrite=True)` restores the previous workspace dir AND re-imports its metadata so the dataset returns to its pre-overwrite state.

**Phase-1 MVP scope (locked 2026-06-16; testing layer definitions locked 2026-06-17):**
- F1 register dataset; F2 list + info; F3 tag rows (multiple per row); F4 note rows; F5 search by field (top-level + nested, equality); F6 search by tag; F7 combined search (field AND tag — the architecture-validating test); F8 delete dataset; F9 rename dataset; F10 re-register / overwrite (delete + re-register, tags/notes lost).
- Scale bar: must demonstrably work up to 1M rows.
- **Done!** Layers L1–L8 all green per `context/testing.md` AND `docs/source/phases/phase-1.md` written AND `sphinx-build` exits clean.

**Process policies (locked 2026-06-17):**
- **PM review cadence:** Phase-boundary only. Claude develops each phase end-to-end autonomously; the PM reviews the entire phase outcome (SDK surface, L8 scenario, phase docs) at one go. Claude does not pause mid-phase for product-level questions unless a failure implies the phase scope itself was wrong. See `.mex/context/decisions.md`.
- **Release timing:** First public release `0.1.0` cuts NOW (Phase 2 complete)! Phase 1 and Phase 2 shipped under `0.0.x` dev tags; `0.1.0` is first stable release with SemVer stability guarantee. `CHANGELOG.md` maintained from day one.
- **Per-phase docs mandatory:** Every phase ships updated SDK documentation alongside code; phase not done until `docs/source/phases/phase-N.md` written and `sphinx-build` clean. See `.mex/context/conventions.md` → Documentation section.

## v0.2.0 Planning

**Scope:** Phase 3 (versioning) + Phase 4 (Parquet cache)

### User Stories
1. **View history:** As a data scientist, I want to `list_versions()` and `get_version(id)` to see and load previous versions.
2. **Append safely:** As a data engineer, I want to `append(new_rows.jsonl)` to add data without copying the whole dataset, preserving old versions.
3. **Cleanse with safety:** As a data scientist, I want to `map(fn)` to transform data while keeping the original version intact; unchanged rows are inherited via copy-on-write.
4. **Filter low-quality:** As a data scientist, I want to `filter_map(fn)` to remove bad samples while preserving them in history.
5. **Auto-accelerate queries:** As a data scientist, I want the system to auto-generate Parquet caches for hot queries, making them ≥5x faster.
6. **Branch from history:** As a data scientist, I want to create new versions from old versions (`map(fn, parent_version=1)`) to experiment with different strategies.

### Features (F16–F26)
- **F16:** `list_versions(dataset)` — list all versions of a dataset
- **F17:** `get_version(dataset, version_id)` — load a specific historical version
- **F18:** `append(dataset, new_rows_jsonl, parent_version=None)` — append rows as new version
- **F19:** `map(dataset, fn, parent_version=None)` — transform rows with copy-on-write
- **F20:** `filter_map(dataset, fn, parent_version=None)` — filter + transform rows
- **F21:** `register_dataset(..., overwrite=True)` — overwrite creates new version instead of delete+re-register
- **F22:** Tag/index inheritance — unchanged rows inherit tags and indexes from parent
- **F23:** `refresh_parquet_cache(dataset, fields=None)` — manually generate Parquet cache
- **F24:** `list_parquet_caches(dataset)` — list existing Parquet caches
- **F25:** Auto cache generation — hot queries trigger Parquet generation
- **F26:** Cost-based query routing — auto-choose between index, JSONL scan, or Parquet

### Test Strategy
- L1: COW hash calculation, version chain logic, cost model
- L2: `versioning/` components, `parquet_engine`, `meta/versioning_repository`
- L3: SDK modules for versions, append, map, filter_map, parquet_cache
- L4: Property tests for version invariants, COW correctness, inheritance
- L5: Fuzz for deep version chains, concurrent branching, partial failures
- L6: Scale smoke for 1M-row map, Parquet speedup, multi-version read
- L7: Mutation testing for versioning and parquet modules
- L8: E2E scenario covering full workflow (register → tag → append → map → filter_map → query with cache)

### Non-Negotiables
- JSONL files remain read-only
- Versions are immutable after creation
- DuckDB remains read-only for business data
- SDK is the only public surface

**Not yet built (deferred phases):**
- Phase 5: FastAPI REST + Web UI.
- Phase 6 (optional): Ray, object storage, fine-grained permissions/audit.

**Known issues:**
- L7 mutation testing (mutmut) not yet wired — nightly job stub only.
- L6 scale takes ~3 min on dev hardware; CI nightly should pre-cache the 1M-row fixture.
- **Phase 3/4 coverage gap** (current 64% < 75% threshold) — needs test suite expansion:
  - `src/dreamdata/versioning/core.py`: 34% → needs L1-L3 tests for version chain, COW, append/map/filter_map
  - `src/dreamdata/parquet_cache.py`: 26% → needs L1-L3 tests for cache generation, listing, and invalidation
  - `src/dreamdata/engine/duckdb_engine.py`: 47% → needs more tests for Parquet path and versioned scans
  - `src/dreamdata/sdk.py`: 70% → needs tests for new versioning and cache SDK methods
  - Tracking issue: add L3 integration tests for `list_versions()`, `get_version()`, `append()`, `map()`, `filter_map()`, `refresh_parquet_cache()`, `list_parquet_caches()`

## Routing Table

Load the relevant file based on the current task. Always load `context/architecture.md` first if not already in context this session.

| Task type | Load |
|-----------|------|
| Understanding how the system works | `context/architecture.md` |
| Working with a specific technology | `context/stack.md` |
| Writing or reviewing code | `context/conventions.md` |
| Shipping a feature, CI, release, security | `context/process.md` |
| Making a design decision | `context/decisions.md` |
| Setting up or running the project | `context/setup.md` |
| Working on versions, map/filter_map, append, row_sources | `context/versioning.md` |
| Designing PostgreSQL schema or writing repository code | `context/metadata-schema.md` |
| Working on search, filters, indexing, or scan performance | `context/query-and-indexing.md` |
| Writing tests, designing coverage, or automation gates | `context/testing.md` |
| Any specific task | Check `patterns/INDEX.md` for a matching pattern |

## Behavioural Contract

For every task, follow this loop:

1. **CONTEXT** — Load the relevant context file(s) from the routing table above. Check `patterns/INDEX.md` for a matching pattern. If one exists, follow it. Narrate what you load: "Loading architecture context..."
2. **BUILD** — Do the work. If a pattern exists, follow its Steps. If you are about to deviate from an established pattern, say so before writing any code — state the deviation and why.
3. **VERIFY** — Load `context/conventions.md` and run the Verify Checklist item by item. State each item and whether the output passes. Do not summarise — enumerate explicitly.
4. **DEBUG** — If verification fails or something breaks, check `patterns/INDEX.md` for a debug pattern. Follow it. Fix the issue and re-run VERIFY.
5. **GROW** — After meaningful work, run this binary checklist:
   - **Ground:** What changed in reality? Name the changed behavior, system, command, dependency, or workflow.
   - **Record:** If project state changed, update the "Current Project State" section above. If documented facts changed, update the relevant `.mex/context/` file surgically.
   - **Orient:** If this task can recur and no pattern exists, create one in `patterns/` using `patterns/README.md`, then add it to `patterns/INDEX.md`. If a pattern exists but you learned a gotcha, update it.
   - **Write:** Bump `last_updated` in every scaffold file you changed. If the why matters, run `mex log --type decision "<what changed and why>"` or `mex log "<note>"`.

---

## v0.3.0 Planning (Phase 5: FastAPI REST + Web UI)

**Scope:** Phase 5 (REST API + Web UI)
**Status:** PM Approved (2026-06-18)

### User Stories (PM Approved)
1. **Remote access:** As a data scientist, I want to access dreamdata via REST API from a notebook or script running on a different machine so that I don't need a full local install.
2. **Web UI for exploration:** As a data scientist, I want a web UI to browse datasets, view rows, add tags/notes, and run searches without writing Python.
3. **AuthN/Z:** As an admin, I want API key auth + user ID enforcement to keep the system secure.
4. **Async operations:** As a data engineer, I want long-running ops (map/filter_map, Parquet cache refresh) to run as async background jobs so I don't have to wait.
5. **API docs:** As a data scientist, I want auto-generated OpenAPI docs so I can understand the API without reading source code.

### Features (F27–F35) (PM Approved)
- **F27:** FastAPI REST server wrapping Engine
  - `GET /datasets` - list datasets
  - `GET /datasets/{name}` - get dataset info
  - `POST /datasets` - register dataset (multipart/form-data upload)
  - `DELETE /datasets/{name}` - delete dataset
  - `POST /datasets/{name}/rename` - rename dataset
  - `GET /docs` + `GET /openapi.json` - auto-generated OpenAPI docs
  - **Auth:** `X-API-Key` header + `X-User-ID` header
- **F28:** Version API
  - `GET /datasets/{name}/versions` - list versions
  - `GET /datasets/{name}/versions/{v}` - get version
  - `POST /datasets/{name}/versions/{v}/append` - append (async)
  - `POST /datasets/{name}/versions/{v}/map` - map (async)
  - `POST /datasets/{name}/versions/{v}/filter-map` - filter_map (async)
  - `GET /jobs/{job_id}` - async job status polling
- **F29:** Tag/note API
  - `GET /datasets/{name}/tags` - list tags
  - `POST /datasets/{name}/tags` - add tags
  - `DELETE /datasets/{name}/tags` - delete tags
  - `GET /datasets/{name}/notes` - list notes
  - `POST /datasets/{name}/notes` - add notes
- **F30:** Search API
  - `GET /datasets/{name}/search` - field search (field_path + value)
  - `GET /datasets/{name}/search-by-tag` - tag search
  - `POST /datasets/{name}/search-with-filter` - advanced filter search
  - `GET /datasets/{name}/scan` - full scan (limit + offset pagination)
- **F31:** Index API
  - `GET /datasets/{name}/indexes` - list indexes
  - `POST /datasets/{name}/indexes` - create index
  - `DELETE /datasets/{name}/indexes/{field}` - drop index
- **F32:** Parquet cache API
  - `POST /datasets/{name}/parquet-cache` - refresh cache (async)
  - `GET /datasets/{name}/parquet-cache` - list caches
- **F33:** Web UI - Dataset explorer
  - Dataset list cards (name, row count, version count, last updated)
  - Version timeline view
  - Row browser: JSON/table dual view
  - Pagination for large datasets
  - API Key config panel
- **F34:** Web UI - Tag/Note editor
  - Tag cloud display
  - Filter rows by tag
  - Bulk add/remove tags
  - Inline note editing
  - Notes per row display
- **F35:** Web UI - Search & filter
  - Field search form (nested fields like `messages.0.role` supported)
  - Tag search
  - Advanced filter builder (visual and/or/eq/range/regex)
  - Results table: column selection, sorting
  - Export to CSV button

### Non-Negotiables (PM Approved)
| Rule | Reason |
|------|--------|
| REST server wraps Engine — no new business logic in FastAPI handlers | Keep business logic centralized |
| API key auth (simple header-based for v0.3.0; OAuth2 deferred) | Simple enough for v0.3.0 |
| Web UI uses modern React/Next.js with TypeScript | Modern frontend stack |
| Async job tracking via `background_tasks` + status endpoint | Simple enough; Celery deferred |
| OpenAPI docs auto-generated via FastAPI at `/docs` and `/openapi.json` | Auto-docs are table stakes |

### Test Strategy (PM Approved)
- L1: Unit tests for API models, auth middleware, job state tracking
- L2: Component tests for handler logic without HTTP server
- L3: Integration tests with TestClient hitting real endpoints
- L4: Property tests for request/response round-trips, filter expressions
- L5: Fuzz API endpoints with invalid inputs, malformed JSON
- L6: Scale smoke for concurrent API requests
- L7: Mutation testing for API layer (mutation score ≥85%)
- L8: E2E scenario with Playwright: register → browse → tag → search → export CSV

### Out of Scope (Deferred to v0.4.0+) (PM Approved)
- OAuth2/SSO
- Fine-grained permissions/ACL
- Audit log UI
- Real-time WebSocket updates
- Multi-node deployment / Kubernetes

---

## v0.4.0 Complete (Phase 6: User Auth & Permissions)

**Scope**: Phase 6 (User Authentication & Fine-grained Permissions)
**Status**: **Shipped!** (2026-06-18)
**Reference**: See `V040_IMPLEMENTATION_PLAN.md` for full details

### User Stories (PM Review Required)

| ID | User Story | Priority |
|----|-----------|---------|
| US-001 | As a system administrator, I want to create an initial admin account on first setup so that I can start managing the system. | P0 |
| US-002 | As an admin, I want to create new user accounts so that my team can collaborate. | P0 |
| US-003 | As an admin or dataset owner, I want to assign dataset permissions to users so that I can control who can access what. | P0 |
| US-004 | As an admin, I want to view all datasets and users so that I can monitor the system. | P0 |
| US-005 | As a user, I want to log in with username/password so that I can access the system securely. | P0 |
| US-006 | As a user, I want to access datasets I have permissions for so that I can do my work. | P0 |
| US-007 | As a user, I want to create datasets (with admins as co-owners) so that I can manage my data. | P0 |
| US-008 | As a user, I want to change my password so that I can keep my account secure. | P1 |
| US-010 | As a user, I want to see my permission levels visualized in the UI so that I understand what I can do. | P1 |
| US-011 | As an admin, I want to optionally assign initial permissions when creating a user so that setup is faster. | P1 |

### Features (F36-F50)

| Feature | Description |
|---------|-------------|
| **F36** | User table & auth schema (users, api_keys, dataset_permissions) |
| **F37** | Password hashing (Argon2id) & JWT token generation |
| **F38** | Initial setup endpoint (`POST /auth/setup`) |
| **F39** | Login/logout endpoints with JWT refresh tokens |
| **F40** | API key management (create, list, revoke) |
| **F41** | User management endpoints (CRUD) |
| **F42** | Dataset permission endpoints (grant, revoke, update) |
| **F43** | Permission middleware & dependency injection |
| **F44** | Backward compatibility layer for old API keys |
| **F45** | All existing endpoints enforce permissions |
| **F46** | Web UI: Login page |
| **F47** | Web UI: User management (admin) |
| **F48** | Web UI: Permission management |
| **F49** | Web UI: User settings (change password, API keys) |
| **F50** | Permission level visualization in UI |

### Permission Levels

| Level | Description |
|------|-------------|
| `admin` | System administrator: full access to everything |
| `owner` | Dataset owner: full access to the dataset, can assign permissions |
| `read_write` | Read-write access: view, modify, tag, append, transform |
| `read_only` | Read-only access: view, search, export |

### Database Changes

New tables:
- `users` - user accounts
- `api_keys` - persistent API keys
- `dataset_permissions` - fine-grained dataset ACL
- `password_reset_tokens` - password reset support

Alembic migration: `0004_users_permissions.py`

### API Endpoints

**Auth** (`/auth`):
- `POST /auth/setup` - initial admin setup
- `POST /auth/login` - user login
- `POST /auth/logout` - user logout
- `POST /auth/change-password` - change password
- `POST /auth/api-keys` - create API key
- `GET /auth/api-keys` - list API keys
- `DELETE /auth/api-keys/:id` - revoke API key

**Users** (`/users`):
- `GET /users` - list users (admin)
- `POST /users` - create user (admin)
- `GET /users/:id` - get user (admin or self)
- `PATCH /users/:id` - update user (admin or self)
- `DELETE /users/:id` - delete user (admin)
- `GET /users/me` - get current user

**Permissions** (`/permissions`):
- `GET /permissions/datasets/:name` - get dataset permissions
- `POST /permissions/datasets/:name` - grant permission
- `PATCH /permissions/datasets/:name/users/:id` - update permission
- `DELETE /permissions/datasets/:name/users/:id` - revoke permission
- `GET /permissions/me/datasets` - get my datasets with permissions

### Backward Compatibility

- Old `X-API-Key` + `X-User-ID` headers continue to work (mapped to "anonymous" user)
- Existing datasets default to admin-only access
- Legacy string `user_id` in `user_annotations` preserved

### Test Strategy

- L1: Password hashing, token generation, permission logic
- L2: AuthRepository unit tests
- L3: API integration tests with permission flows
- L4: Permission matrix validation
- L5: Security tests (privilege escalation, SQL injection)
- L6: Concurrent permission changes
- L7: Mutation testing for auth logic
- L8: E2E: Setup admin → create user → create dataset → assign permission → verify access

### Non-Negotiables

- Passwords stored with Argon2id, never plaintext
- JWT tokens short-lived (30 mins) with refresh tokens
- API keys revocable at any time
- All dataset endpoints enforce permissions
- Admin bypasses all permission checks
- Audit trail for permission changes (DB-level)

### Out of Scope (Deferred to v0.4.1+)

- OAuth2/SSO integration
- Audit log UI
- Temporary/expiring permissions
- Fine-grained per-action permissions (e.g., tag-only, export-only)
- Permission templates/roles
- WebSocket real-time updates

### Environment Variables (New)

```bash
JWT_SECRET_KEY=               # Required for JWT signing
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
ARGON2_TIME_COST=3
ARGON2_MEMORY_COST=65536
ARGON2_PARALLELISM=4
```

---

## v0.5.0 Complete (Phase 7-8: Web UI 权限管理完善)

**Scope**: Phase 7-8 (Web UI 权限管理完善)
**Status**: 已完成并发布 ✅
**版本**: v0.5.0

### 用户故事完成情况
| ID | 用户故事 | 状态 |
|----|---------|------|
| US-025 | 作为用户，我想在 Web UI 的登录页面登录，这样我就能通过浏览器安全访问。 | ✅ 完成 |
| US-026 | 作为管理员，我想在 Web UI 中管理用户（创建/编辑/删除），这样我不用写 API 调用就能管理团队。 | ✅ 完成 |
| US-027 | 作为数据集所有者，我想在 Web UI 中管理数据集权限（分配/撤销/更新），这样我就能直观地控制访问。 | ✅ 完成 |
| US-028 | 作为用户，我想在 Web UI 的用户设置页面修改密码和管理 API keys，这样我就能自助维护账号。 | ✅ 完成 |
| US-029 | 作为用户，我想在 Web UI 中看到我的权限级别可视化，这样我就能清楚知道我能做什么操作。 | ✅ 完成 |

### 功能实现详情

#### 新增 Web UI 功能
- **登录页面**：支持用户名/密码登录，支持首次初始化设置
- **用户管理（管理员）**：创建、编辑、删除用户，管理用户角色和状态
- **数据集权限管理**：所有者可分配/撤销/更新用户权限
- **用户设置页面**：修改密码、创建/撤销 API keys
- **权限级别可视化**：彩色标签显示权限级别（管理员/所有者/读写/只读）

#### 新增 API 端点
- `GET /auth/setup/status` - 检查是否需要初始化设置
- `POST /auth/refresh` - 使用 refresh token 获取新的 access token

#### 技术特性
- Token 自动刷新机制
- 响应式设计，支持中文界面
- Modal 弹窗交互
- 安全的密码处理

### 已取消的用户故事（不会实现）
- US-030: 审计日志 UI
- US-031: OAuth2/SSO 集成
- US-032: 临时/过期权限
- US-033: 细粒度操作权限（延期）

### 测试状态
- ✅ 所有 222 个测试通过
- ✅ Lint 检查通过
- ✅ Mypy 类型检查通过
- ✅ 文档构建通过

