"""Workspace path resolution and dataset layout helpers.

The workspace is the only filesystem location the engine may write into.
User-supplied paths are validated to stay inside the workspace after
symlink resolution; dataset-relative paths are constructed via the
helpers in this module so layout is consistent across the engine.
"""

from __future__ import annotations

import os
from pathlib import Path

from dreamdata.errors import WorkspaceMisconfigured


class Workspace:
    """A resolved, validated workspace root.

    All dataset content lives under ``<root>/<dataset_name>/vN/data/*.jsonl``
    plus a transient ``<root>/.engine/`` directory for caches (later phase).
    """

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        if not root.is_absolute():
            raise WorkspaceMisconfigured(
                setting="workspace_path", expected="absolute path", value=str(root)
            )
        # Resolve symlinks on the root itself if it exists; otherwise fall back.
        try:
            resolved = root.resolve(strict=True)
        except FileNotFoundError:
            resolved = root.resolve(strict=False)
        self._root = resolved

    @property
    def root(self) -> Path:
        return self._root

    def ensure(self) -> None:
        """Create the workspace root if it does not exist."""
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / ".engine").mkdir(exist_ok=True)
        (self._root / ".engine" / ".write-test").touch()

    def dataset_dir(self, dataset_name: str) -> Path:
        return self._root / dataset_name

    def dataset_version_dir(self, dataset_name: str, version_number: int) -> Path:
        return self.dataset_dir(dataset_name) / f"v{version_number}"

    def dataset_data_dir(self, dataset_name: str, version_number: int) -> Path:
        return self.dataset_version_dir(dataset_name, version_number) / "data"

    def to_rel(self, absolute: Path) -> str:
        """Return *absolute* as a workspace-relative POSIX string.

        Raises :class:`WorkspaceMisconfigured` if *absolute* is outside the
        workspace after symlink resolution.
        """
        return relative_to_workspace(self._root, absolute)

    def to_abs(self, relative: str) -> Path:
        """Resolve *relative* (workspace-relative POSIX) to an absolute path.

        The resulting path must stay inside the workspace; symlinks pointing
        outside are rejected.
        """
        return resolve_in_workspace(self._root, relative)


def relative_to_workspace(workspace_root: Path, absolute: Path) -> str:
    """Return *absolute* relative to *workspace_root* as a POSIX string."""
    try:
        workspace_resolved = workspace_root.resolve(strict=False)
        # Resolve the input path; tolerate symlinks but require the final
        # location to be inside the workspace.
        try:
            abs_resolved = absolute.resolve(strict=True)
        except FileNotFoundError:
            abs_resolved = absolute.resolve(strict=False)
        rel = abs_resolved.relative_to(workspace_resolved)
    except ValueError as exc:
        raise WorkspaceMisconfigured(
            setting="path",
            expected=f"under workspace {workspace_root}",
            value=str(absolute),
        ) from exc
    return rel.as_posix()


def resolve_in_workspace(workspace_root: Path, relative: str) -> Path:
    """Resolve *relative* against *workspace_root*, refusing escapes.

    Symlinks are resolved; if the resolved target falls outside the
    workspace, :class:`WorkspaceMisconfigured` is raised.
    """
    if relative.startswith("/"):
        raise WorkspaceMisconfigured(
            setting="path",
            expected="relative (not absolute)",
            value=relative,
        )
    if "\x00" in relative:
        raise WorkspaceMisconfigured(
            setting="path",
            expected="no null bytes",
            value=relative,
        )
    workspace_resolved = workspace_root.resolve(strict=False)
    candidate = (workspace_resolved / relative).resolve(strict=False)
    try:
        candidate.relative_to(workspace_resolved)
    except ValueError as exc:
        raise WorkspaceMisconfigured(
            setting="path",
            expected=f"inside workspace {workspace_resolved}",
            value=relative,
        ) from exc
    return candidate


def dataset_dir_rel(dataset_name: str) -> str:
    """Workspace-relative path to a dataset's root directory."""
    return dataset_name


def dataset_version_dir_rel(dataset_name: str, version_number: int) -> str:
    """Workspace-relative path to a specific version directory."""
    return f"{dataset_name}/v{version_number}"


def dataset_data_dir_rel(dataset_name: str, version_number: int) -> str:
    """Workspace-relative path to a version's data directory."""
    return f"{dataset_name}/v{version_number}/data"


_ = os  # keep os import in case future helpers need it
