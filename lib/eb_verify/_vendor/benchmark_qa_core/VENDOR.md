# benchmark_qa_core (first-party, self-contained copy)

`benchmark_qa_core` is a schema-agnostic QA library for benchmark task
definitions, maintained by the EnterpriseBench authors and shared across sibling
benchmark rigs (EB and CSB). It is kept here as a self-contained copy under
`_vendor/` — rather than an external dependency — so `eb_verify` has no
out-of-tree install requirement.

This is first-party code, covered by this repository's Apache 2.0 `LICENSE`.

## Layout

| file | purpose |
|------|---------|
| `types.py`    | shared dataclasses / `Finding` shape |
| `oracle.py`   | file & symbol existence checks against the cloned repo |
| `scoring.py`  | scoring-method tier validation |
| `leakage.py`  | prompt / aux-file leakage checks |
| `_symbols.py` | symbol-extraction helpers |

Each rig parses its own task-meta schema and feeds already-extracted inputs into
these pure-functional checks; findings come back as a flat `list[Finding]`.

## EB-local behavior

`leakage.py` — `check_aux_file_leakage` skips the F2 check for bare generic
build-manifest basenames (`go.mod`, `package.json`, `pom.xml`, … see
`GENERIC_MANIFEST_BASENAMES`). These names are non-discriminative — every repo of
a language has one — so naming them in a prompt does not leak which file the
agent should investigate. Tokens with directory components (e.g. `envoy/go.mod`)
stay specific and still raise F2.
