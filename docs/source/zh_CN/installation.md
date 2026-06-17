# 安装指南

## 前置条件

- **Python 3.11+**
- **PostgreSQL 15+** 已运行并可连接
- **uv** — 安装命令 `curl -LsSf https://astral.sh/uv/install.sh | sh`
- 一个引擎可以读写的本地文件系统目录

## 安装步骤

1. **安装依赖：**

   ```bash
   uv sync --extra dev
   ```

2. **创建 PostgreSQL 数据库：**

   ```bash
   createdb dreamdata        # 主数据库
   createdb dreamdata_test   # 可选，用于测试套件
   ```

3. **在项目根目录创建 `.env` 文件：**

   ```bash
   DATABASE_URL=postgresql://user:password@localhost:5432/dreamdata
   WORKSPACE_PATH=/absolute/path/to/dreamdata_workspace
   USER_ID=your_name
   ```

   工作区路径是所有 JSONL 文件（以及后续阶段的 Parquet 缓存）所在的根目录。工作区必须是绝对路径；引擎将所有元数据路径存储为相对于 `WORKSPACE_PATH` 的路径，因此工作区是可移动的。

4. **应用数据库迁移：**

   ```bash
   uv run alembic upgrade head
   ```

5. **创建工作区目录：**

   ```bash
   mkdir -p "$WORKSPACE_PATH"
   ```

6. **冒烟测试：**

   ```bash
   uv run pytest tests/sdk/test_register.py -q
   ```

## 环境变量

| 变量 | 是否必需 | 说明 |
|------|----------|------|
| `DATABASE_URL` | 是 | PostgreSQL 连接字符串 (`postgresql://...`) |
| `WORKSPACE_PATH` | 是 | 数据集存储根目录的绝对路径 |
| `USER_ID` | 是 | 注释的单用户 MVP 作者 |
| `DUCKDB_MEMORY_LIMIT` | 否 | DuckDB 内存预算，例如 `4GB` |
| `DUCKDB_THREADS` | 否 | DuckDB 工作线程数 |
| `LOG_LEVEL` | 否 | 根日志级别；默认 `INFO` |
| `TAG_VALUE_MAX_BYTES` | 否 | 标签值的最大字节数；默认 4096 |
| `NOTE_VALUE_MAX_BYTES` | 否 | 备注正文的最大字节数；默认 64 KB |

## 常见问题

- **`psycopg.OperationalError`** — 验证 `DATABASE_URL` 可以连接（使用 `pg_isready`）且数据库存在（使用 `psql -lqt | grep dreamdata`）。
- **大扫描时 DuckDB 内存不足** — 降低 `DUCKDB_MEMORY_LIMIT` 或 `DUCKDB_THREADS`；确保工作区在快速的本地磁盘上，而非网络挂载。
- **工作区路径权限** — SDK 进程需要 `WORKSPACE_PATH` 的读写权限；引擎在构造时会写入一个 `.engine/.write-test` 哨兵文件来验证。

## 语言切换

- [English](../installation.md)
- [简体中文](./installation.md)
