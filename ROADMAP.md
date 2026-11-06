# AssetLedger development roadmap

All items below are proposed and unimplemented. Estimates are engineering hours,
not calendar commitments. Total estimated work: **30 hours**.

## 1. Configurable include and exclude rules — 5 hours

Add a versioned project configuration file with glob-based inclusions, exclusions,
and explicit precedence rules.

Acceptance criteria:

- Defaults remain identical when no configuration exists.
- Configuration validation identifies the exact invalid rule and source location.
- Cross-platform tests cover separators, hidden paths, negation, and rule ordering.

## 2. Persistent hash cache with reliable invalidation — 6 hours

Cache hashes locally to accelerate repeated snapshots while treating cached data as
an optimization rather than a source of truth.

Acceptance criteria:

- Cache keys account for path, size, modification metadata, and file identity.
- Suspicious metadata or cache corruption triggers rehashing, never silent reuse.
- Tests demonstrate cache hits, all invalidation paths, and identical cached/uncached manifests.

## 3. Content-based move and copy suggestions — 4 hours

Suggest likely moves and copies after the current path-based classification by
matching recorded size and digest.

Acceptance criteria:

- Ambiguous many-to-many matches are represented explicitly and deterministically.
- Suggestions never replace the underlying added/removed classifications.
- Text and JSON schemas distinguish exact evidence from heuristic labeling.

## 4. Standalone HTML comparison reports — 5 hours

Generate a self-contained, accessible HTML document from a comparison without
network-loaded scripts, fonts, or styles.

Acceptance criteria:

- The report includes summary filters and all recorded before/after metadata.
- Filenames and metadata are safely escaped against markup/script injection.
- A deterministic fixture and browser accessibility smoke test are included.

## 5. Configurable CI comparison policies — 4 hours

Evaluate comparison results against policies such as maximum added bytes, forbidden
extensions, or modification of protected paths.

Acceptance criteria:

- Policy failures have stable machine-readable codes and documented exit behavior.
- Multiple violations are reported in one run and in deterministic order.
- Examples cover permissive reporting and blocking CI workflows.

## 6. Signed integrity manifests — 3 hours

Add optional detached signatures so consumers can authenticate a manifest rather
than merely checking its internal hashes.

Acceptance criteria:

- Signing remains optional and unsigned version-1 manifests stay compatible.
- Verification distinguishes invalid signatures, unknown keys, and changed content.
- Key material is never embedded in manifests or written by default.

## 7. Large-inventory progress and performance work — 3 hours

Add opt-in progress reporting and benchmark memory/runtime behavior on synthetic
large inventories.

Acceptance criteria:

- Progress is sent to stderr and never corrupts text or JSON stdout reports.
- Non-interactive output remains quiet unless explicitly requested.
- Benchmarks document baseline performance and guard against material regressions.
