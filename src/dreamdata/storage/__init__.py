"""Storage layer — workspace paths, JSONL scanning, and file staging.

The storage layer owns filesystem I/O. Every public function takes paths
relative to ``WORKSPACE_PATH`` and every return value uses paths relative
to ``WORKSPACE_PATH`` — workspaces must be movable.
"""

from dreamdata.storage.jsonl import (
    LineScanResult,
    iter_jsonl_offsets,
    parse_jsonl_line,
)
from dreamdata.storage.paths import (
    Workspace,
    dataset_data_dir_rel,
    dataset_dir_rel,
    dataset_version_dir_rel,
    relative_to_workspace,
    resolve_in_workspace,
)

__all__ = [
    "LineScanResult",
    "Workspace",
    "dataset_data_dir_rel",
    "dataset_dir_rel",
    "dataset_version_dir_rel",
    "iter_jsonl_offsets",
    "parse_jsonl_line",
    "relative_to_workspace",
    "resolve_in_workspace",
]
