# 第一阶段 — 注册、打标签、搜索、生命周期

**范围：** F1 注册 · F2 列表和信息 · F3 给行打标签 · F4 给行加备注 · F5 按字段搜索 · F6 按标签搜索 · F7 组合搜索 · F8 删除 · F9 重命名 · F10 覆盖。

**规模：** 可演示处理高达 100 万行。

**状态：** L1–L8 全部通过。开发标签 `v0.0.1`。第一个公开发布版 `0.1.0` 将在第二阶段完成后推出（详见 [发布时间](../index.md)）。

## 你能做什么

第一阶段 SDK 是一个垂直切片：注册数据集、给行加注释、按字段或标签或两者同时搜索、然后重命名、覆盖或删除。完整的 API 文档在 [Engine](../api/engine.md) 和 [Dataset](../api/dataset.md) 参考文档中。

```python
from pathlib import Path
from dreamdata import Engine
from dreamdata.config import Settings

engine = Engine(Settings(
    database_url="postgresql://localhost/dreamdata",
    workspace_path="/abs/path/to/workspace",
    user_id="alice",
))

ds = engine.register_dataset("phase1_demo", [Path("conversations.jsonl")])
ds.tag([0, 1], "good")
ds.note(0, "best row")
print(ds.search_by_field("rating", 5))
print(ds.search_by_tag("good"))
print(ds.search(field_path="rating", field_value=5, tag="good"))
```

## 完整示例

### 正常流程：打标签、搜索、组合搜索

```python
import json
from pathlib import Path
from dreamdata import Engine
from dreamdata.config import Settings

# 1. 准备一个小的 JSONL 测试文件
fixture = Path("/tmp/phase1_demo.jsonl")
fixture.write_text("\n".join(json.dumps({
    "id": i,
    "messages": [{"role": "user" if i % 2 == 0 else "assistant"}],
    "rating": 5 if i % 3 == 0 else 3,
}) for i in range(10)) + "\n")

# 2. 注册并打标签
engine = Engine(Settings(
    database_url="postgresql://localhost/dreamdata",
    workspace_path="/tmp/dreamdata_ws",
    user_id="alice",
))
ds = engine.register_dataset("demo", [fixture])
ds.tag([0, 3, 6, 9], "top_rated")  # rating == 5 的行

# 3. 三种搜索模式
field_results = ds.search_by_field("rating", 5)
tag_results = ds.search_by_tag("top_rated")
combined = ds.search(field_path="rating", field_value=5, tag="top_rated")

# 组合结果正好是两者的交集
assert set(combined["row_idx"]) == set(field_results["row_idx"]) & set(tag_results["row_idx"])

engine.close()
```

### 错误路径：无效的数据集名称

```python
from dreamdata import Engine
from dreamdata.errors import DatasetNameInvalid

engine = Engine(Settings(...))

# 路径遍历、空字节、斜杠和过长名称都会引发异常
try:
    engine.register_dataset("../escape", [Path("a.jsonl")])
except DatasetNameInvalid as exc:
    print(exc.context)  # {'name': '../escape', 'reason': '...'}
```

有效的数据集名称字符集是 `^[a-zA-Z0-9_-]{1,128}$`。检查在 SDK 边界进行，在任何文件系统或 SQL 使用之前——因此路径遍历（`../etc/passwd`）、绝对路径、空字节和空字符串无法到达任何一层。

## 架构不变量

第一阶段建立了项目其余部分所依赖的不变量。测试套件直接断言这些——不仅仅是功能正确性：

- **JSONL 文件是只读的。** 注册时 *复制* 用户提供的文件到工作区；原始文件的 SHA-256 和 mtime 被保留。`tests/sdk/test_register.py::test_register_does_not_modify_original_file` 确保了这一点。
- **所有元数据都存储在 PostgreSQL 中。** 标签、备注、row_sources、file_stats 以及数据集/版本表是“什么存在以及在哪里”的唯一真实来源。`tests/component/test_meta.py` 覆盖了每个仓库方法。
- **DuckDB 对业务数据是只读的。** 内存中的 DuckDB 实例以 read_only=False 打开，这样它可以注册临时视图进行查询处理——但没有方法会向 JSONL 文件发出 INSERT。`tests/component/test_engine.py::test_engine_writes_no_business_files` 断言扫描后工作区文件集没有变化。
- **SDK 是唯一的公开接口。** `Engine` 和 `Dataset` 从不暴露原始 DuckDB 连接或 SQL。`engine/`、`meta/`、`storage/` 层是私有的；导入它们的用户代码不受支持，并且可能在开发标签之间破坏。
- **有类型的异常，永远不会在失败时返回 `None`。** 每个公共方法要么成功，要么引发带有命名字段（`name`、`path`、`reason` 等）的 `SdkError` 子类。秘密（`DATABASE_URL`、原始行内容）永远不会出现在错误消息中。

## 推迟的功能

| 功能 | 阶段 |
|------|------|
| 用于剪枝的字段索引（`field_index`）| 第二阶段 |
| 多用户标签隔离（`user_id` 过滤）| 第二阶段 |
| 正则表达式/范围/IN/布尔过滤器 | 第二阶段 |
| 真正的版本升级覆盖（COW）| 第三阶段 |
| `map` / `filter_map` / `append` 转换 | 第三阶段 |
| 跨版本的 `row_sources` 继承 | 第三阶段 |
| 热门字段的 Parquet 缓存 | 第四阶段 |
| FastAPI REST + Web UI | 第五阶段 |
| Ray 分布式执行 | 第六阶段（可选）|

## 需要了解的 MVP 限制

1. **标签对所有用户可见。** 第一阶段在每个注释上存储 `user_id`，但在读取时不过滤它——单用户 MVP 语义。第二阶段引入过滤器，因此每个用户只看到自己的标签。
2. **搜索是直接的 DuckDB 扫描。** 没有字段索引，没有 file_stats 剪枝。在普通硬件上，100 万行的扫描是亚秒级的；1 亿行的扫描才是第二阶段索引重要的地方。
3. **覆盖是删除后重新注册。** 第一阶段的 `overwrite=True` 替换数据集（标签/备注丢失）。保留历史的真正版本升级覆盖将在第三阶段通过 COW 引入。
4. **每个数据集一个隐式版本。** 第一阶段总是有 `version_number = 1`。创建新版本的 map/filter_map/append 将在第三阶段引入。

## 测试覆盖

八层，每一层都完全自动化。设计文档见 `.mex/context/testing.md`。

| 层 | 范围 | 路径 |
|----|------|------|
| L1 单元 | 纯辅助函数（字段路径、错误、设置、存储）| `tests/unit/` |
| L2 组件 | 一个内部层对真实的 PostgreSQL / DuckDB / 文件系统 | `tests/component/` |
| L3 SDK 集成 | 每个 F 功能一个模块（正常 + 边缘 + 错误）| `tests/sdk/` |
| L4 属性 | Hypothesis 生成的不变量 | `tests/property/` |
| L5 模糊测试 | 对抗性输入（格式错误的 JSON、路径遍历等）| `tests/fuzz/` |
| L6 规模 | 100 万行冒烟测试（慢；夜间）| `tests/scale/` |
| L7 变异测试 | 对 `meta/`、`engine/`、`storage/` 的 mutmut（夜间）| 不适用 |
| L8 验收 | 端到端注册 → 打标签 → 搜索 → 重命名 → 覆盖 → 删除 | `tests/e2e/` |

## 语言切换

- [English](../../phases/phase-1.md)
- [简体中文](./phase-1.md)
