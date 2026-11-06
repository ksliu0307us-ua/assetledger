"""Duplicate analysis, inventory summaries, and report rendering."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath

from .compare import Comparison
from .models import FileEntry, Manifest


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    sha256: str
    size_bytes: int
    paths: tuple[str, ...]

    @property
    def copies(self) -> int:
        return len(self.paths)

    @property
    def redundant_bytes(self) -> int:
        return self.size_bytes * (self.copies - 1)


@dataclass(frozen=True, slots=True)
class InventorySummary:
    file_count: int
    total_bytes: int
    extension_counts: tuple[tuple[str, int], ...]
    duplicate_group_count: int
    skipped_count: int


def duplicate_groups(manifest: Manifest) -> tuple[DuplicateGroup, ...]:
    grouped: dict[tuple[int, str], list[str]] = defaultdict(list)
    for entry in manifest.files:
        grouped[(entry.size_bytes, entry.sha256)].append(entry.path)
    groups = [
        DuplicateGroup(digest, size, tuple(sorted(paths)))
        for (size, digest), paths in grouped.items()
        if len(paths) > 1
    ]
    return tuple(sorted(groups, key=lambda group: (group.size_bytes, group.sha256, group.paths)))


def inventory_summary(manifest: Manifest) -> InventorySummary:
    extensions = Counter(
        PurePosixPath(entry.path).suffix.lower() or "[no extension]" for entry in manifest.files
    )
    return InventorySummary(
        file_count=len(manifest.files),
        total_bytes=sum(entry.size_bytes for entry in manifest.files),
        extension_counts=tuple(sorted(extensions.items())),
        duplicate_group_count=len(duplicate_groups(manifest)),
        skipped_count=len(manifest.skipped),
    )


def _safe(value: str) -> str:
    """Escape control characters while keeping readable Unicode."""

    return json.dumps(value, ensure_ascii=False)[1:-1]


def _entry_data(entry: FileEntry) -> dict[str, object]:
    return {"path": entry.path, "size_bytes": entry.size_bytes, "sha256": entry.sha256}


def comparison_json(comparison: Comparison) -> str:
    data = {
        "summary": {
            "added": len(comparison.added),
            "removed": len(comparison.removed),
            "modified": len(comparison.modified),
            "unchanged": len(comparison.unchanged),
        },
        "added": [_entry_data(entry) for entry in comparison.added],
        "removed": [_entry_data(entry) for entry in comparison.removed],
        "modified": [
            {
                "path": item.path,
                "before": _entry_data(item.before),
                "after": _entry_data(item.after),
            }
            for item in comparison.modified
        ],
        "unchanged": [_entry_data(entry) for entry in comparison.unchanged],
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def comparison_text(comparison: Comparison) -> str:
    lines = [
        "Comparison summary:",
        f"  Added: {len(comparison.added)}",
        f"  Removed: {len(comparison.removed)}",
        f"  Modified: {len(comparison.modified)}",
        f"  Unchanged: {len(comparison.unchanged)}",
    ]
    for title, paths in (
        ("Added", (entry.path for entry in comparison.added)),
        ("Removed", (entry.path for entry in comparison.removed)),
        ("Modified", (entry.path for entry in comparison.modified)),
    ):
        materialized = list(paths)
        if materialized:
            lines.extend(("", f"{title}:"))
            lines.extend(f"  {_safe(path)}" for path in materialized)
    if not comparison.has_differences:
        lines.extend(("", "No differences."))
    return "\n".join(lines) + "\n"


def duplicates_json(groups: tuple[DuplicateGroup, ...]) -> str:
    data = {
        "duplicate_group_count": len(groups),
        "potential_redundant_bytes": sum(group.redundant_bytes for group in groups),
        "groups": [
            {
                "sha256": group.sha256,
                "size_bytes": group.size_bytes,
                "copies": group.copies,
                "potential_redundant_bytes": group.redundant_bytes,
                "paths": list(group.paths),
            }
            for group in groups
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def duplicates_text(groups: tuple[DuplicateGroup, ...]) -> str:
    lines = [
        f"Duplicate groups: {len(groups)}",
        f"Potential redundant bytes: {sum(group.redundant_bytes for group in groups)}",
    ]
    for index, group in enumerate(groups, start=1):
        lines.extend(
            (
                "",
                f"Group {index}:",
                f"  Size: {group.size_bytes} bytes",
                f"  Copies: {group.copies}",
                f"  Potential redundant bytes: {group.redundant_bytes}",
                f"  SHA-256: {group.sha256}",
                "  Paths:",
            )
        )
        lines.extend(f"    {_safe(path)}" for path in group.paths)
    lines.extend(("", "Stored inventory only; no represented files were inspected or removed."))
    return "\n".join(lines) + "\n"


def inspect_json(summary: InventorySummary) -> str:
    data = {
        "file_count": summary.file_count,
        "total_bytes": summary.total_bytes,
        "extension_counts": dict(summary.extension_counts),
        "duplicate_group_count": summary.duplicate_group_count,
        "skipped_count": summary.skipped_count,
        "filesystem_verified": False,
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def inspect_text(summary: InventorySummary) -> str:
    lines = [
        "Stored inventory summary:",
        f"  Recorded files: {summary.file_count}",
        f"  Total recorded bytes: {summary.total_bytes}",
        f"  Duplicate groups: {summary.duplicate_group_count}",
        f"  Skipped entries: {summary.skipped_count}",
        "  Extensions:",
    ]
    if summary.extension_counts:
        lines.extend(f"    {_safe(extension)}: {count}" for extension, count in summary.extension_counts)
    else:
        lines.append("    (none)")
    lines.extend(("", "This summarizes the stored inventory; the current filesystem was not verified."))
    return "\n".join(lines) + "\n"
