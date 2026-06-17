"""JSONL scanning — stream lines, capture (byte_offset, byte_length, parsed JSON).

The scanner is single-pass and yields row content lazily so registration of
multi-GB JSONL files does not blow memory. Encoding is always UTF-8.
Malformed lines are reported through the caller's policy (skip-with-warning
or abort) — the scanner itself only collects failures.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from dreamdata.errors import FileNotReadable, RegistrationFileError


@dataclass(slots=True, frozen=True)
class LineScanResult:
    """One row scanned from a JSONL file."""

    row_idx: int
    byte_offset: int
    byte_length: int
    line: str
    line_ending_bytes: int


@dataclass(slots=True, frozen=True)
class JSONLRow:
    """A scanned row paired with its parsed JSON value.

    Currently only used internally during registration; kept exposed for
    Phase 3 transforms where row-level (offset, value) pairs become useful.
    """

    row_idx: int
    byte_offset: int
    byte_length: int
    value: object


def _check_readable(file_path: Path) -> None:
    if not file_path.exists():
        raise FileNotReadable(path=str(file_path), reason="file does not exist")
    if not file_path.is_file():
        raise FileNotReadable(path=str(file_path), reason="not a regular file")
    if not os.access(file_path, os.R_OK):
        raise FileNotReadable(path=str(file_path), reason="permission denied")


def iter_jsonl_offsets(file_path: Path, *, strict: bool = True) -> Iterator[LineScanResult]:
    """Stream a JSONL file, yielding one :class:`LineScanResult` per row.

    *strict* = True (default) aborts on the first invalid UTF-8 byte sequence
    by raising :class:`RegistrationFileError`. *strict* = False replaces
    invalid bytes with U+FFFD and continues.

    The file is opened in binary mode and decoded as UTF-8 so the
    byte offsets reflect the on-disk bytes (not the decoded string).
    Trailing newline at EOF is not emitted as a separate row.
    """
    _check_readable(file_path)
    row_idx = 0
    byte_offset = 0
    try:
        with file_path.open("rb") as fh:
            for raw in fh:
                # Strip exactly one trailing newline (CRLF or LF) — the
                # scanner does not emit a trailing empty line at EOF.
                line_ending_bytes = 0
                if raw.endswith(b"\r\n"):
                    line_ending_bytes = 2
                    line_bytes = raw[:-2]
                elif raw.endswith(b"\n"):
                    line_ending_bytes = 1
                    line_bytes = raw[:-1]
                else:
                    line_bytes = raw
                byte_length = len(line_bytes)
                if strict:
                    try:
                        line = line_bytes.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise RegistrationFileError(
                            path=str(file_path),
                            reason=f"non-UTF-8 byte at offset {byte_offset + exc.start}: {exc.reason}",
                        ) from exc
                else:
                    line = line_bytes.decode("utf-8", errors="replace")
                yield LineScanResult(
                    row_idx=row_idx,
                    byte_offset=byte_offset,
                    byte_length=byte_length,
                    line=line,
                    line_ending_bytes=line_ending_bytes,
                )
                row_idx += 1
                byte_offset += byte_length + line_ending_bytes
    except OSError as exc:
        raise FileNotReadable(path=str(file_path), reason=str(exc)) from exc


def parse_jsonl_line(
    file_path: Path,
    line: str,
    *,
    byte_offset: int,
) -> object:
    """Parse a single JSONL line, raising :class:`RegistrationFileError` on failure."""
    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        raise RegistrationFileError(
            path=str(file_path),
            reason=f"invalid JSON at byte {byte_offset + exc.pos}: {exc.msg}",
        ) from exc


_ = os  # keep import for future helpers (e.g. fadvise)
