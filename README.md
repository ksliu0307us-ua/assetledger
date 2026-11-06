# AssetLedger

AssetLedger is an offline command-line tool for developers who need reproducible
inventories of static project assets. It recursively records normalized relative
paths, byte sizes, and SHA-256 content hashes; compares two stored inventories;
reports duplicate content; and summarizes a manifest without contacting a service.

This is a new, original, AI-assisted implementation. It requires no third-party
runtime dependencies, uses only synthetic example and test files, and is licensed
under the MIT License.

Manifests are **inventories, not backups**. They contain paths, sizes, and hashes,
not file contents, so they cannot restore a missing or damaged file.

## Requirements and installation

AssetLedger requires Python 3.11 or later. From a checkout:

```bash
python -m venv .venv
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install .
```

On macOS or Linux:

```bash
source .venv/bin/activate
python -m pip install .
```

Use either the installed `assetledger` command or `python -m assetledger`. They
provide the same interface. `assetledger --version` prints the application version,
and `assetledger --help` lists all commands.

## Commands

### `snapshot`

Recursively inventory regular files and write a new manifest:

```bash
assetledger snapshot ./examples/before-assets --output ./snapshots/before.json
```

Files are hashed in chunks rather than loaded wholly into memory. Stored paths are
relative to the scan root and use forward slashes. Symbolic links and special files
such as sockets and pipes are skipped and recorded with a reason. These directory
names are excluded by default and recorded as skipped directory entries:

```text
.git  .venv  venv  node_modules  __pycache__  build  dist
```

Unreadable files and directories are errors; AssetLedger does not silently produce
an incomplete inventory. It compares file size, modification metadata, identity,
and bytes read before and after hashing to detect common concurrent changes.
Scanning a changing directory is not an atomic filesystem snapshot, however, so
applications should avoid modifying assets during a scan.

The output must be outside the scanned directory. AssetLedger resolves both paths
before checking this boundary, finishes scanning before writing, creates missing
output parent directories, and refuses to replace an existing file.

### `compare`

Compare manifests by recorded relative path:

```bash
assetledger compare ./snapshots/before.json ./snapshots/after.json
assetledger compare ./snapshots/before.json ./snapshots/after.json --format json
```

Entries are classified as added, removed, modified, or unchanged. A matching path
is modified if its recorded size or SHA-256 digest differs. This version does not
infer renames: a move appears as one removal and one addition.

Example text summary:

```text
Comparison summary:
  Added: 1
  Removed: 1
  Modified: 1
  Unchanged: 3

Added:
  added.txt
```

JSON output contains a `summary` object and deterministic `added`, `removed`,
`modified`, and `unchanged` arrays. Modified records include both complete entries:

```json
{
  "summary": {
    "added": 1,
    "removed": 1,
    "modified": 1,
    "unchanged": 3
  },
  "added": [],
  "removed": [],
  "modified": [],
  "unchanged": []
}
```

The shortened arrays above illustrate the report shape; the command emits every
entry.

### `duplicates`

Group entries whose recorded size and SHA-256 digest match:

```bash
assetledger duplicates ./snapshots/before.json
assetledger duplicates ./snapshots/before.json --format json
```

Each group reports its paths, file size, copy count, digest, and potential redundant
bytes (`size × extra copies`). Duplicate empty files are included with zero
redundant bytes. The command reads only the manifest—it neither reopens nor removes
the represented source files.

Example:

```text
Duplicate groups: 1
Potential redundant bytes: 23

Group 1:
  Size: 23 bytes
  Copies: 2
  Potential redundant bytes: 23
```

The JSON form contains `duplicate_group_count`, `potential_redundant_bytes`, and a
`groups` array with the same information.

### `inspect`

Summarize a stored inventory:

```bash
assetledger inspect ./snapshots/before.json
assetledger inspect ./snapshots/before.json --format json
```

The report gives the recorded file count, total bytes, lowercase extension counts,
duplicate-group count, and skipped-entry count. Files with no extension appear as
`[no extension]`. Both report formats make clear that the current filesystem was
not verified; JSON includes `"filesystem_verified": false`.

```json
{
  "file_count": 5,
  "total_bytes": 128,
  "extension_counts": {
    ".json": 1,
    ".txt": 4
  },
  "duplicate_group_count": 1,
  "skipped_count": 0,
  "filesystem_verified": false
}
```

Text reports escape control characters in paths so one filename cannot forge extra
report lines. JSON reports use standard JSON escaping.

## Manifest format

AssetLedger writes deterministic UTF-8 JSON with no machine-specific absolute paths
or timestamps:

```json
{
  "schema_version": 1,
  "hash_algorithm": "sha256",
  "files": [
    {
      "path": "images/example.bin",
      "size_bytes": 42,
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  ],
  "skipped": [
    {
      "path": "node_modules",
      "reason": "excluded directory"
    }
  ]
}
```

- `schema_version` is currently `1`.
- `hash_algorithm` is currently `sha256`.
- `files` contains normalized, unique relative paths, nonnegative byte sizes, and
  lowercase 64-character SHA-256 digests.
- `skipped` contains normalized relative paths and nonempty explanations.

File and skipped entries are sorted by path. Unicode filenames are retained, while
JSON escapes characters that require escaping. Identical inventories produce
identical manifest bytes.

All read commands validate manifests first. Unsupported schemas or algorithms,
malformed or duplicate JSON keys, unknown/missing fields, invalid types, negative
sizes, malformed digests, duplicate file paths, absolute paths, backslashes, and
parent-directory components are rejected.

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Successful snapshot/report, or comparison with no differences. |
| `1` | A completed comparison found at least one difference. |
| `2` | Invalid input/manifest, output conflict, or execution failure. |

Expected failures produce concise diagnostics without Python tracebacks. Duplicate
groups are findings, not command failures, so `duplicates` returns `0`.

## Synthetic demonstration

[`examples/`](examples) contains synthetic before/after asset trees and manifests
created by the actual implementation. From the repository root:

```bash
python -m assetledger compare examples/manifests/before.json examples/manifests/after.json
python -m assetledger duplicates examples/manifests/before.json
python -m assetledger inspect examples/manifests/before.json --format json
```

To prove deterministic snapshot output without overwriting the tracked example,
write to two new locations and compare their bytes:

```bash
python -m assetledger snapshot examples/before-assets --output /tmp/before-one.json
python -m assetledger snapshot examples/before-assets --output /tmp/before-two.json
```

On Windows, replace `/tmp/...` with paths outside `examples/before-assets`.

## Tests

Run the standard-library unittest suite:

```bash
python -m unittest discover -s tests -v
```

Tests use temporary directories and synthetic data. Symlink creation is skipped on
Windows when the process lacks the required privilege, and FIFO coverage is skipped
on platforms without POSIX named pipes. Unreadable-directory behavior is tested
portably with a mocked permission error because elevated accounts can bypass mode
bits.

## Current limitations

- Include/exclude rules are fixed rather than project-configurable.
- Every snapshot rehashes every included file; there is no persistent cache.
- Moves and copies are not inferred from matching content.
- Reports are text or JSON only; no standalone HTML report is generated.
- Comparison outcomes cannot yet be evaluated against configurable CI policies.
- A scan is not an atomic view of a directory being modified concurrently.
- Manifests provide integrity metadata but are not signed or authenticated.

These are proposed future additions, not partially implemented features. See
[`ROADMAP.md`](ROADMAP.md) for estimates and acceptance criteria.

## License

AssetLedger is available under the [MIT License](LICENSE).
