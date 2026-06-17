# dreamdata

**🌐 语言:** <a href="../index.html">English</a> | 简体中文

> 用于 LLM 训练数据的版本化管理引擎

**dreamdata** 是一个用于管理 LLM 训练数据的版本化管理系统。它提供了 JSONL 原生存储、多用户标签隔离、灵活的检索功能、数据转换操作以及数据集版本控制，支持扩展到 TB 级别数据。

```{toctree}
:caption: 内容
:maxdepth: 2

installation
quickstart
phases/phase-1
phases/phase-2
api/engine
api/dataset
api/errors
```

## 项目状态

当前为 **v0.1.0** 稳定版本。

**已实现功能：**
- 数据集注册（F1）
- 数据集列表和信息查询（F2）
- 给行打标签（F3）
- 给行添加备注（F4）
- 按字段搜索（F5）
- 按标签搜索（F6）
- 组合搜索（F7）
- 删除数据集（F8）
- 重命名数据集（F9）
- 重新注册/覆盖（F10）
- 多用户标签隔离（F11）
- 高级过滤器（F12）
- 字段索引（F13）
- 索引和文件统计剪枝（F14）
- 删除索引（F15）

## 语言切换

- [English](../index.md)
- [简体中文](./index.md)
