# dreamdata

**🌐 Language:** English | <a href="zh_CN/index.html">简体中文</a>

```{toctree}
:maxdepth: 2
:caption: Get Started

installation
quickstart
```

```{toctree}
:maxdepth: 2
:caption: Per-Phase Guides

phases/phase-1
phases/phase-2
```

```{toctree}
:maxdepth: 2
:caption: API Reference

api/engine
api/dataset
api/errors
```

## What dreamdata is

dreamdata is a versioned management engine for LLM training data —
JSONL-native storage with multi-user tag isolation, flexible retrieval,
functional transforms, and dataset versioning. The Python SDK is the
only public surface; DuckDB (read-only) and PostgreSQL (metadata)
live behind it.

**Status:** v0.1.0 stable release. Phase 1 and Phase 2 are complete:
core registration + tagging + search + multi-user isolation + advanced
filters + field indexing. See [Installation](installation.md) for setup
and [Quickstart](quickstart.md) for a 30-second tour.
