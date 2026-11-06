"""Filesystem discovery and chunked SHA-256 hashing."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from .manifest import ManifestError, save_manifest
from .models import FileEntry, Manifest, SkippedEntry

DEFAULT_EXCLUDED_DIRECTORIES = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"}
)
HASH_CHUNK_SIZE = 1024 * 1024


class SnapshotError(Exception):
    """A filesystem condition prevented a complete trustworthy inventory."""


def _signature(metadata: os.stat_result) -> tuple[int, int, int, int]:
    return (
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_dev,
        metadata.st_ino,
    )


def hash_file(path: Path, chunk_size: int = HASH_CHUNK_SIZE) -> tuple[int, str]:
    """Hash a regular file in chunks and reject common concurrent changes."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    try:
        before = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise SnapshotError(f"not a regular file: {path}")
        digest = hashlib.sha256()
        bytes_read = 0
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                bytes_read += len(chunk)
                digest.update(chunk)
            opened_after = os.fstat(handle.fileno())
        path_after = path.stat(follow_symlinks=False)
    except SnapshotError:
        raise
    except OSError as exc:
        raise SnapshotError(f"cannot read file {path}: {exc}") from exc

    if (
        bytes_read != before.st_size
        or _signature(before) != _signature(opened_after)
        or _signature(before) != _signature(path_after)
    ):
        raise SnapshotError(f"file changed while hashing: {path}")
    return bytes_read, digest.hexdigest()


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def create_snapshot(
    root: Path, excluded_directories: frozenset[str] = DEFAULT_EXCLUDED_DIRECTORIES
) -> Manifest:
    """Build a complete in-memory inventory without writing output."""

    root = root.resolve()
    if not root.exists():
        raise SnapshotError(f"scan root does not exist: {root}")
    if root.is_symlink() or not root.is_dir():
        raise SnapshotError(f"scan root must be a real directory: {root}")

    files: list[FileEntry] = []
    skipped: list[SkippedEntry] = []

    def visit(directory: Path) -> None:
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda item: item.name)
        except OSError as exc:
            raise SnapshotError(f"cannot read directory {directory}: {exc}") from exc

        for entry in entries:
            path = Path(entry.path)
            relative = _relative(root, path)
            try:
                if entry.is_symlink():
                    skipped.append(SkippedEntry(relative, "symbolic link"))
                elif entry.is_dir(follow_symlinks=False):
                    if entry.name in excluded_directories:
                        skipped.append(SkippedEntry(relative, "excluded directory"))
                    else:
                        visit(path)
                elif entry.is_file(follow_symlinks=False):
                    size, digest = hash_file(path)
                    files.append(FileEntry(relative, size, digest))
                else:
                    skipped.append(SkippedEntry(relative, "special file"))
            except OSError as exc:
                raise SnapshotError(f"cannot inspect {path}: {exc}") from exc

    visit(root)
    return Manifest(
        files=tuple(sorted(files, key=lambda item: item.path)),
        skipped=tuple(sorted(skipped, key=lambda item: item.path)),
    )


def snapshot_to_file(root: Path, output: Path) -> Manifest:
    """Scan completely, then exclusively write an output outside the scan root."""

    resolved_root = root.resolve()
    resolved_output = output.resolve()
    if resolved_output == resolved_root or resolved_output.is_relative_to(resolved_root):
        raise SnapshotError("output manifest must be outside the scanned directory")
    if resolved_output.exists():
        raise SnapshotError(f"output file already exists: {resolved_output}")
    manifest = create_snapshot(resolved_root)
    try:
        save_manifest(resolved_output, manifest)
    except ManifestError as exc:
        raise SnapshotError(str(exc)) from exc
    return manifest
