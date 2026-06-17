# 快速开始

60 秒了解 dreamdata SDK：注册数据集、给行打标签、添加备注、按字段搜索、按标签搜索、组合搜索——Phase 1 的完整流程。

## 设置

```python
from dreamdata import Engine
from dreamdata.config import Settings

settings = Settings(
    database_url="postgresql://user:password@localhost:5432/dreamdata",
    workspace_path="/abs/path/to/workspace",
    user_id="alice",
)

engine = Engine(settings=settings)
```

在生产环境中，`Settings()` 会从环境变量加载——详见 [安装指南](installation.md)。

## 注册数据集

```python
from pathlib import Path

ds = engine.register_dataset(
    "conversations_v1",
    [Path("data/conversations.jsonl")],
)
print(ds.row_count, ds.inferred_fields[:5])
```

提供的 JSONL 文件会被复制到工作区的 `<workspace>/conversations_v1/v1/data/` 目录下。原始文件不会被修改。所有元数据路径都相对于 `WORKSPACE_PATH` 存储。

## 打标签和添加备注

```python
ds.tag([0, 1, 2], "high_quality")
ds.tag(0, "favorite")
ds.note(0, "best conversation in the set")

print(ds.tags())
# [(0, 'high_quality'), (0, 'favorite'), (1, 'high_quality'), ...]

print(ds.notes())
# [(<id>, 0, 'best conversation in the set')]
```

标签是幂等的：重复标记同一 `(行, 标签)` 不会产生重复记录。标签值在写入时会进行 NFC 规范化。

## 搜索

```python
# F5: 按顶层字段搜索
df = ds.search_by_field("rating", 5)

# F5: 按嵌套字段路径搜索 (messages[0].role)
df = ds.search_by_field("messages.0.role", "user")

# F6: 按标签搜索
df = ds.search_by_tag("high_quality")

# F7: 组合搜索 (字段 AND 标签)
df = ds.search(field_path="rating", field_value=5, tag="high_quality")
```

所有搜索方法都返回一个 `pandas.DataFrame`，包含 `row_idx` 列（此版本中的全局逻辑行索引）和 `data` 列（行的解析 JSON 值）。

## 生命周期：重命名和覆盖

```python
# F9: 重命名保留标签、备注和数据
new_ds = engine.rename_dataset("conversations_v1", "conversations_v2")

# F10: 覆盖 = 删除 + 重新注册；标签和备注会丢失
fresh = engine.register_dataset(
    "conversations_v2",
    [Path("data/conversations_v2.jsonl")],
    overwrite=True,
)
```

## 生命周期：删除

```python
engine.delete_dataset("conversations_v2")
```

删除数据集的元数据、row_sources、注释和 file_stats，并删除工作区目录。注册时提供的原始 JSONL 文件不会被触及。

## 关闭引擎

```python
engine.close()
```

或使用上下文管理器：

```python
with Engine(settings=settings) as engine:
    ds = engine.register_dataset("temp", [Path("data/a.jsonl")])
    print(ds.scan())
```

## 语言切换

- [English](../quickstart.md)
- [简体中文](./quickstart.md)
