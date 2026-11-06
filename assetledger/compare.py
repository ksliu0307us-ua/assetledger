"""Pure manifest comparison logic."""

from __future__ import annotations

from dataclasses import dataclass

from .models import FileEntry, Manifest


@dataclass(frozen=True, slots=True)
class ModifiedEntry:
    path: str
    before: FileEntry
    after: FileEntry


@dataclass(frozen=True, slots=True)
class Comparison:
    added: tuple[FileEntry, ...]
    removed: tuple[FileEntry, ...]
    modified: tuple[ModifiedEntry, ...]
    unchanged: tuple[FileEntry, ...]

    @property
    def has_differences(self) -> bool:
        return bool(self.added or self.removed or self.modified)


def compare_manifests(before: Manifest, after: Manifest) -> Comparison:
    """Classify entries by normalized recorded path."""

    before_by_path = {entry.path: entry for entry in before.files}
    after_by_path = {entry.path: entry for entry in after.files}
    before_paths = set(before_by_path)
    after_paths = set(after_by_path)

    added = tuple(after_by_path[path] for path in sorted(after_paths - before_paths))
    removed = tuple(before_by_path[path] for path in sorted(before_paths - after_paths))
    modified: list[ModifiedEntry] = []
    unchanged: list[FileEntry] = []
    for path in sorted(before_paths & after_paths):
        old = before_by_path[path]
        new = after_by_path[path]
        if old.size_bytes != new.size_bytes or old.sha256 != new.sha256:
            modified.append(ModifiedEntry(path, old, new))
        else:
            unchanged.append(new)
    return Comparison(added, removed, tuple(modified), tuple(unchanged))
