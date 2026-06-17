# Installation

## Prerequisites

- **Python 3.11+**
- **PostgreSQL 15+** running and reachable
- **uv** — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- A local filesystem directory the engine can read/write into

## Steps

1. **Install dependencies:**

   ```bash
   # Core installation (JSONL only)
   uv sync --extra dev

   # With Parquet cache support (optional)
   uv sync --extra parquet --extra dev
   ```

   For users installing from PyPI:
   ```bash
   pip install dreamdata  # core
   pip install "dreamdata[parquet]"  # with Parquet cache
   ```

2. **Create a PostgreSQL database:**

   ```bash
   createdb dreamdata        # main DB
   createdb dreamdata_test   # optional, for the test suite
   ```

3. **Create a `.env` file** at the project root:

   ```bash
   DATABASE_URL=postgresql://user:password@localhost:5432/dreamdata
   WORKSPACE_PATH=/absolute/path/to/dreamdata_workspace
   USER_ID=your_name
   ```

   The workspace path is the root directory under which all JSONL files
   (and, in later phases, Parquet caches) live. Workspaces must be
   absolute paths; the engine stores every metadata path *relative* to
   `WORKSPACE_PATH` so workspaces are movable.

4. **Apply the schema migration:**

   ```bash
   uv run alembic upgrade head
   ```

5. **Create the workspace directory:**

   ```bash
   mkdir -p "$WORKSPACE_PATH"
   ```

6. **Smoke test:**

   ```bash
   uv run pytest tests/sdk/test_register.py -q
   ```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | yes | PostgreSQL connection string (`postgresql://...`) |
| `WORKSPACE_PATH` | yes | Absolute path to the dataset storage root |
| `USER_ID` | yes | Single-user MVP author for annotations |
| `DUCKDB_MEMORY_LIMIT` | no | DuckDB memory budget, e.g. `4GB` |
| `DUCKDB_THREADS` | no | DuckDB worker threads |
| `LOG_LEVEL` | no | Root log level; default `INFO` |
| `TAG_VALUE_MAX_BYTES` | no | Max byte length of a tag value; default 4096 |
| `NOTE_VALUE_MAX_BYTES` | no | Max byte length of a note body; default 64 KB |

## Common issues

- **`psycopg.OperationalError`** — verify `DATABASE_URL` is reachable
  (`pg_isready`) and that the database exists
  (`psql -lqt | grep dreamdata`).
- **DuckDB out-of-memory on large scans** — lower
  `DUCKDB_MEMORY_LIMIT` or `DUCKDB_THREADS`; ensure the workspace is
  on fast local disk, not a network mount.
- **Workspace path permissions** — the SDK process needs read+write
  on `WORKSPACE_PATH`; the engine writes a `.engine/.write-test`
  sentinel on construction to verify.
