# Synthetic AssetLedger demonstration

These files are demonstrations only and do not represent a real project release.

- `before-assets/` and `after-assets/` are two synthetic directory states.
- `manifests/before.json` and `manifests/after.json` were generated from those
  directories by AssetLedger 0.1.0.

The second state adds `added.txt`, removes `removed.txt`, modifies `change.txt`,
and preserves three files. `common.txt` and `duplicate-copy.txt` deliberately have
identical content.

From the repository root:

```bash
python -m assetledger compare examples/manifests/before.json examples/manifests/after.json
python -m assetledger compare examples/manifests/before.json examples/manifests/after.json --format json
python -m assetledger duplicates examples/manifests/before.json
python -m assetledger inspect examples/manifests/before.json
```

The comparison intentionally exits with code `1` because differences were found.
Duplicate and inspect commands read only the stored manifest and leave all example
assets untouched.
