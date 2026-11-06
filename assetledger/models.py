"""Immutable data structures used throughout AssetLedger."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FileEntry:
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SkippedEntry:
    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class Manifest:
    files: tuple[FileEntry, ...] = ()
    skipped: tuple[SkippedEntry, ...] = ()
    schema_version: int = 1
    hash_algorithm: str = "sha256"
