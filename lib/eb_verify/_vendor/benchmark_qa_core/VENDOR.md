# Vendored: benchmark_qa_core

Upstream: `codeprobe/src/codeprobe/qa/benchmark_qa_core/`
Source repo: codeprobe (private) — branch `feature/codeprobe-ceuu-benchmark-qa-core`
Source commit: `047df83 — feat(qa): benchmark_qa_core schema-agnostic QA library (codeprobe-ceuu)`
Vendored: 2026-04-30 by EnterpriseBench-1av (gc.routed_to=enterprisebench-worker)

## Why vendored

The upstream codeprobe lib is not pip-installable from EB because the codeprobe
repo is not pushed and is not on a registry. The bead spec called for a file
copy, not a submodule, so we drop the package under `_vendor/` and consume it
locally.

## Drift policy

- Upstream is the source of truth. Re-vendor (don't edit in place) when the
  upstream lib lands on `main` and a versioned release exists.
- The only intentional edit applied during vendoring is rewriting absolute
  imports (`codeprobe.qa.benchmark_qa_core.X`) to relative imports (`.X`) so
  the package is portable.
- If you find a real bug here, fix upstream first, then re-vendor. Do not
  fork.

## Intentional drift (EB-only patches)

These edits go beyond the import-rewrite and make the vendored copy diverge
from upstream. Each must be mirrored upstream and reconciled on the next
re-vendor.

- **`leakage.py` — generic build-manifest skip** (EnterpriseBench-zco,
  2026-05-31). `check_aux_file_leakage` now skips F2 for tokens that are bare
  generic build-manifest basenames (`go.mod`, `package.json`, `pom.xml`, …;
  see `GENERIC_MANIFEST_BASENAMES`). These names are non-discriminative —
  every repo of a language has one — so naming them in a prompt does not leak
  which file the agent should investigate. Tokens with directory components
  (e.g. `envoy/go.mod`) stay specific and still raise F2. Removes 10
  false-positive F2 warnings in the corpus.
  Upstream mirror tracked as **dr-2vydrm.1**; drop this note on re-vendor once
  it lands.

## File checksums

| file | upstream sha256 (047df83) | vendored sha256 |
|------|----------------------------|-----------------|
| `__init__.py` | a33e65dd4969939509e129ef9d5450a8e3db8b8e733160cf34b8842962bd9a05 | 6d67fa84ad40f9e67cc8e27285c7a759e03091458e5d3346329af4024ec828b7 |
| `types.py` | c4cb257591e932748517843a9e7714b0d56d35fa9c10e76a7560f398871ff53f | c4cb257591e932748517843a9e7714b0d56d35fa9c10e76a7560f398871ff53f |
| `oracle.py` | 8b4aef4989092ff1e5201171f59b58a89b855fc59db22de2669db73d2e04b6e6 | c3c1149ef5f0c0ce48f9366737ffd51f95a75fca5d622b4cbb9315bc6dc7ca69 |
| `scoring.py` | 129662ab689979832b32ad69cbd5c974c50769709e46bfe3594302c2056de248 | 5d22fea899b43ba7a91662531eb100d96a24bb2396926dc436403a6637a0e3f5 |
| `leakage.py` | 8c517f582209acccbcf62f5d1e4e1cc59cf017673f803ed9e59ca51914db5f74 | 7f367cd0a3b5685bc9925e0f6ef922da8af853c94ddf70cad8d64478b5929e08 |
| `_symbols.py` | 80517c41844366d3db4c6fe6289ffce4218b626d1ccbeec971d979dea01585a6 | 80517c41844366d3db4c6fe6289ffce4218b626d1ccbeec971d979dea01585a6 |

`types.py` and `_symbols.py` are byte-identical to upstream. `__init__.py`,
`oracle.py`, and `scoring.py` differ only by the import-rewrite described
above. `leakage.py` additionally carries the EB-only generic build-manifest
skip — see _Intentional drift_ above.
