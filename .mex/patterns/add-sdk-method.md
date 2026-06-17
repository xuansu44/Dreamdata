---
name: add-sdk-method
description: Add a new method to the Engine or Dataset facade. The core repeatable structural task — every feature is an SDK method that coordinates the internal engine/meta/versioning layers.
triggers:
  - "add method"
  - "new sdk method"
  - "add feature"
  - "extend sdk"
edges:
  - target: context/conventions.md
    condition: when the SDK naming, structure, and verify checklist are needed
  - target: context/architecture.md
    condition: when deciding which internal layer a method delegates to
  - target: patterns/debug-duckdb-scan.md
    condition: when the new method has a read path through DuckDB
last_updated: 2026-06-16
---

# Add an SDK Method

## Context

Load `context/conventions.md` for the SDK structure, naming, and verify checklist. Load `context/architecture.md` for the layer responsibilities (`engine/`, `meta/`, `versioning/`). The SDK facade (`Engine`, `Dataset`) only orchestrates and shapes return values — it must not contain business logic or call DuckDB/PostgreSQL directly.

## Steps

1. **Decide the layer.** Read methods that scan files → `engine/`. Metadata reads/writes → `meta/`. Version-producing transforms → `versioning/`. The facade combines them; it does not implement them.
2. **Write the internal layer method first.** With full type hints. One responsibility. No DataFrame shaping here — that's the facade's job.
3. **Add the facade method.** Full type hints on signature. Docstring. Delegates to the internal layer, shapes the return (`pandas.DataFrame` for reads, new `Dataset` handle for transforms).
4. **Error handling.** Raise typed exceptions (subclass a project `DreamDataError`) with context. Never return `None` on failure; never swallow.
5. **Write tests** under `tests/sdk/` and the relevant internal-layer test under `tests/<layer>/`.
6. **Export** the new method on the public surface if it is user-facing.

## Gotchas

- **Don't put business logic in the facade.** If the facade method is more than orchestration + return shaping, push the logic into the right internal layer.
- **No direct DuckDB/PostgreSQL from the facade.** Use the `engine/` and `meta/` layers.
- **Reads return DataFrame; transforms return new `Dataset`.** Don't mix — a transform that mutates `self` breaks immutability.
- **Type hints are required on the facade signature** — mypy runs on the public surface.
- **Connection lifecycle.** DuckDB and PostgreSQL handles are owned by `Engine`; methods must not open/close their own. [VERIFY AFTER FIRST IMPLEMENTATION — confirm the lifecycle pattern after the first connection-management pass.]
- **User context (`user_id`, `workspace`) comes from the Engine**, not from method arguments. Don't thread them through.

## Verify

Before presenting the new method:
- [ ] Facade signature has full type hints and a docstring.
- [ ] Facade body is orchestration + return shaping only — no business logic.
- [ ] No direct DuckDB/PostgreSQL calls from the facade.
- [ ] Errors are typed exceptions with context — no `None`-on-failure, no swallowed exceptions.
- [ ] Read methods return `pandas.DataFrame`; transforms return new `Dataset` handles.
- [ ] Tests exist under `tests/sdk/` and the relevant internal-layer test directory.
- [ ] mypy passes on the public surface; ruff passes.

## Debug

- **mypy complains about the return type:** the internal layer returns a different shape than the facade promises — fix the shaping in the facade, not the type hint.
- **Tests pass in isolation but fail in the full suite:** connection lifecycle leak — the method is opening/closing a handle it shouldn't. Route through `Engine`-owned handles.
- **Method works but breaks immutability:** check whether the method mutates `self.version_id` or `self._state`; transforms must construct and return a new `Dataset`.

## Update Scaffold

- [ ] If the method introduces a new internal layer or responsibility, update `context/architecture.md` Key Components.
- [ ] If a new convention emerged (e.g. a new error type pattern), add it to `context/conventions.md`.
- [ ] If the method is a new task type without a pattern, create one in `.mex/patterns/` and add to `INDEX.md`.
