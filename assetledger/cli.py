"""Command-line interface for AssetLedger."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .compare import compare_manifests
from .manifest import ManifestError, load_manifest
from .reports import (
    comparison_json,
    comparison_text,
    duplicate_groups,
    duplicates_json,
    duplicates_text,
    inspect_json,
    inspect_text,
    inventory_summary,
)
from .snapshot import SnapshotError, snapshot_to_file


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assetledger",
        description="Inventory local assets, compare manifests, and report duplicate content.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot", help="inventory a directory into a new manifest")
    snapshot.add_argument("directory", type=Path, help="directory to scan recursively")
    snapshot.add_argument("--output", required=True, type=Path, help="new output manifest path")

    compare = subparsers.add_parser("compare", help="compare two stored manifests")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--format", choices=("text", "json"), default="text")

    duplicates = subparsers.add_parser("duplicates", help="report duplicate content in a manifest")
    duplicates.add_argument("manifest", type=Path)
    duplicates.add_argument("--format", choices=("text", "json"), default="text")

    inspect = subparsers.add_parser("inspect", help="summarize a stored manifest")
    inspect.add_argument("manifest", type=Path)
    inspect.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            manifest = snapshot_to_file(args.directory, args.output)
            print(
                f"Wrote manifest: {args.output.resolve()} "
                f"({len(manifest.files)} files, {len(manifest.skipped)} skipped)"
            )
            return 0
        if args.command == "compare":
            comparison = compare_manifests(load_manifest(args.before), load_manifest(args.after))
            sys.stdout.write(
                comparison_json(comparison) if args.format == "json" else comparison_text(comparison)
            )
            return 1 if comparison.has_differences else 0
        if args.command == "duplicates":
            groups = duplicate_groups(load_manifest(args.manifest))
            sys.stdout.write(duplicates_json(groups) if args.format == "json" else duplicates_text(groups))
            return 0
        if args.command == "inspect":
            summary = inventory_summary(load_manifest(args.manifest))
            sys.stdout.write(inspect_json(summary) if args.format == "json" else inspect_text(summary))
            return 0
    except (ManifestError, SnapshotError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2
