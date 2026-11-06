"""Versioned manifest serialization and strict validation."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .models import FileEntry, Manifest, SkippedEntry

SCHEMA_VERSION = 1
HASH_ALGORITHM = "sha256"
_DIGEST_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_TOP_FIELDS = frozenset({"schema_version", "hash_algorithm", "files", "skipped"})
_FILE_FIELDS = frozenset({"path", "size_bytes", "sha256"})
_SKIPPED_FIELDS = frozenset({"path", "reason"})


class ManifestError(Exception):
    """A malformed, unsupported, unreadable, or unwritable manifest."""

    def __init__(self, messages: str | list[str] | tuple[str, ...]):
        if isinstance(messages, str):
            self.messages = (messages,)
        else:
            self.messages = tuple(messages)
        super().__init__("; ".join(self.messages))


class _DuplicateKeyError(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _path_problem(value: Any) -> str | None:
    if not isinstance(value, str):
        return "must be a string"
    if not value:
        return "must not be empty"
    if "\\" in value:
        return "must use forward slashes"
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        return "must be a relative path"
    if any(part in (".", "..") for part in posix.parts):
        return "must not contain '.' or '..' components"
    if str(posix) != value:
        return "must be normalized"
    return None


def _field_set_problems(data: dict[str, Any], expected: frozenset[str], context: str) -> list[str]:
    problems: list[str] = []
    missing = sorted(expected - set(data))
    unknown = sorted(set(data) - expected)
    if missing:
        problems.append(f"{context}: missing field(s): {', '.join(missing)}")
    if unknown:
        problems.append(f"{context}: unknown field(s): {', '.join(unknown)}")
    return problems


def manifest_from_data(data: Any) -> Manifest:
    """Validate decoded JSON data and return an immutable manifest."""

    if not isinstance(data, dict):
        raise ManifestError("manifest: top-level JSON value must be an object")

    problems = _field_set_problems(data, _TOP_FIELDS, "manifest")
    if data.get("schema_version") != SCHEMA_VERSION or isinstance(data.get("schema_version"), bool):
        problems.append(f"manifest: unsupported schema_version; expected {SCHEMA_VERSION}")
    if data.get("hash_algorithm") != HASH_ALGORITHM:
        problems.append(f"manifest: unsupported hash_algorithm; expected {HASH_ALGORITHM!r}")

    raw_files = data.get("files")
    raw_skipped = data.get("skipped")
    if not isinstance(raw_files, list):
        problems.append("manifest: 'files' must be an array")
        raw_files = []
    if not isinstance(raw_skipped, list):
        problems.append("manifest: 'skipped' must be an array")
        raw_skipped = []

    files: list[FileEntry] = []
    file_paths: set[str] = set()
    for index, raw in enumerate(raw_files):
        context = f"files[{index}]"
        if not isinstance(raw, dict):
            problems.append(f"{context}: must be an object")
            continue
        problems.extend(_field_set_problems(raw, _FILE_FIELDS, context))
        path = raw.get("path")
        path_issue = _path_problem(path)
        if path_issue:
            problems.append(f"{context}.path: {path_issue}")
        elif path in file_paths:
            problems.append(f"{context}.path: duplicate file path {path!r}")
        else:
            file_paths.add(path)

        size = raw.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            problems.append(f"{context}.size_bytes: must be a nonnegative integer")
        digest = raw.get("sha256")
        if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
            problems.append(f"{context}.sha256: must be 64 lowercase hexadecimal characters")

        if path_issue is None and isinstance(size, int) and not isinstance(size, bool) and size >= 0 and isinstance(digest, str) and _DIGEST_RE.fullmatch(digest):
            files.append(FileEntry(path, size, digest))

    skipped: list[SkippedEntry] = []
    skipped_paths: set[str] = set()
    for index, raw in enumerate(raw_skipped):
        context = f"skipped[{index}]"
        if not isinstance(raw, dict):
            problems.append(f"{context}: must be an object")
            continue
        problems.extend(_field_set_problems(raw, _SKIPPED_FIELDS, context))
        path = raw.get("path")
        path_issue = _path_problem(path)
        if path_issue:
            problems.append(f"{context}.path: {path_issue}")
        elif path in skipped_paths:
            problems.append(f"{context}.path: duplicate skipped path {path!r}")
        else:
            skipped_paths.add(path)
        reason = raw.get("reason")
        if not isinstance(reason, str) or not reason:
            problems.append(f"{context}.reason: must be a nonempty string")
        if path_issue is None and isinstance(reason, str) and reason:
            skipped.append(SkippedEntry(path, reason))

    if problems:
        raise ManifestError(problems)
    return Manifest(
        files=tuple(sorted(files, key=lambda item: item.path)),
        skipped=tuple(sorted(skipped, key=lambda item: item.path)),
    )


def manifest_to_data(manifest: Manifest) -> dict[str, Any]:
    return {
        "schema_version": manifest.schema_version,
        "hash_algorithm": manifest.hash_algorithm,
        "files": [
            {"path": entry.path, "size_bytes": entry.size_bytes, "sha256": entry.sha256}
            for entry in sorted(manifest.files, key=lambda item: item.path)
        ],
        "skipped": [
            {"path": entry.path, "reason": entry.reason}
            for entry in sorted(manifest.skipped, key=lambda item: item.path)
        ],
    }


def serialize_manifest(manifest: Manifest) -> bytes:
    """Return canonical UTF-8 JSON bytes for a validated manifest."""

    validated = manifest_from_data(manifest_to_data(manifest))
    return (
        json.dumps(manifest_to_data(validated), ensure_ascii=False, indent=2, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")


def load_manifest(path: Path) -> Manifest:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc
    try:
        data = json.loads(raw, object_pairs_hook=_strict_object)
    except _DuplicateKeyError as exc:
        raise ManifestError(str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(
            f"malformed JSON in {path} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    return manifest_from_data(data)


def save_manifest(path: Path, manifest: Manifest) -> None:
    """Exclusively write a complete canonical manifest."""

    payload = serialize_manifest(manifest)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ManifestError(f"cannot create output directory {path.parent}: {exc}") from exc
    created = False
    try:
        with path.open("xb") as handle:
            created = True
            handle.write(payload)
    except FileExistsError as exc:
        raise ManifestError(f"output file already exists: {path}") from exc
    except OSError as exc:
        if created:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise ManifestError(f"cannot write manifest {path}: {exc}") from exc
