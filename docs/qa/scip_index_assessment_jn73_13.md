# SCIP Index Assessment — gate for a codenav-inclusive MCP arm

Bead: `EnterpriseBench-jn73.13` (epic `EnterpriseBench-jn73`)

## Verdict: NO-GO on a codenav-inclusive (`all` endpoint) MCP arm

NO-GO, but for the opposite reason to the one the epic assumed.

The epic's premise was that codenav might be inert over our mirrors — that
`go_to_definition` returning empty meant SCIP indexes were absent, so an `all`
arm would add nothing. That premise is **refuted**. The mirrors *are* precisely
indexed, codenav works, and it works well enough to be the problem: precise
cross-repo linking resolves references **out of the pinned mirror** and into
other revisions of the same project. Agents then follow those references and
read wrong-revision source.

Codenav is not inert. It is a live contamination vector against the revision
pin that the mirrors exist to provide.

## How to regenerate every number here

```bash
# Contamination audit over the trace corpus (results/runs is gitignored;
# point --runs-dir at wherever the corpus lives).
python scripts/analysis/audit_mirror_contamination.py --runs-dir results/runs
python scripts/analysis/audit_mirror_contamination.py --runs-dir results/runs --json

# Live precise-index status (needs a valid token; see Finding 4).
python scripts/infra/verify_sg_indexing.py --check-api
```

Corpus as audited: 408 traces, 273 of them scored (a run is scorable only if it
has an MCP preamble declaring an authorized mirror set). Runs under
`_invalidated/` (12) are excluded — they are already withdrawn from analysis.
Replicates (`<task>/<mode>/repN/`) are counted under the mode they repeat, not
as modes of their own.

## Finding 1 — the mirrors ARE precisely indexed (SCIP present)

We cannot ask the instance directly (Finding 4), but the traces answer it. The
discriminator is the SCIP moniker rule: **local monikers cannot cross repos;
package monikers can.** So a module-local symbol must stay inside its own repo,
while an exported symbol may resolve anywhere the package is known.

From `results/runs/dead-code-003/mcp_only`, all five `find_references` calls
scoped to `sg-evals/react--ab18f33d`:

| Symbol | Kind | Repos in result | Crossed? |
|---|---|---|---|
| `retryErrors` | module-local | `react--ab18f33d` only | no |
| `CompilerMode` | exported | `react--56408a5b` only | yes |
| `validateNoUntransformedReferences` | exported | `--ab18f33d` + `--56408a5b` | yes |
| `transformProgram` | exported | `--ab18f33d` + `--56408a5b` | yes |
| `pruneAllReactiveScopes` | exported | `--ab18f33d` + `--56408a5b` + `facebook/react` | yes |

A name-based search fallback would have matched `retryErrors` in the other two
copies as well — the identifier sits at an identical path in all three. It did
not. Exactly the exported symbols crossed. That local-vs-exported asymmetry is
the signature of precise indexes, not of text search.

Corollary: **"`go_to_definition` empty ⇒ SCIP absent" is refuted.** Across the
corpus `go_to_definition` returned results on every call; it was never silently
empty. (Sample is thin — n=5 calls corpus-wide — so this refutes the epic's
premise rather than establishing a rate.) The codenav null the epic set out to
explain has a different cause, and `find_references`' 5/16 Cloudflare transport
failures (filed separately) are a more likely contributor than indexing.

## Finding 2 — cross-revision contamination, and it is MCP-arm-only

Because ~22 projects sit on the instance at several pinned revisions, precise
linking walks between them. Per-mode, over the scored runs:

| Mode | Runs | Wrong-rev in results | Wrong-rev ACTIVELY READ | Foreign-repo bleed |
|---|---|---|---|---|
| `mcp_only` | 136 | 21 | **11** | 22 |
| `hybrid` | 136 | 1 | 0 | 0 |
| `baseline` | 123 | n/a — unscored | n/a | n/a |
| `ablate-*` | 12 | n/a — unscored | n/a | n/a |
| no mode dir | 1 | 0 | 0 | 0 |

Eleven `mcp_only` runs, spanning **eight distinct tasks**, pulled wrong-revision
source into context: `dead-code-003`, `schema-evolution-002`,
`schema-evolution-005`, `api-contract-gocp-module-007`,
`dep-graph-tri-prometheus-alertmanager-grafana-001`,
`incident-investigation-quad-containerd-001`, `error-trace-k8s-nftables-sync-001`,
and `incident-inv-docker-shutdown-004` (the last two contaminated across
several replicates each, which is why the run count exceeds the task count).

`dead-code-003` is the clean illustration: the task pins
`react--ab18f33d`, `find_references` returned hits in `react--56408a5b`
(`dead-code-002`'s pin), and the agent then issued `read_file` **against
`react--56408a5b`**. Source at the wrong revision entered the transcript.

Two caveats on this table, stated rather than smoothed over:

- **Baseline is unscored, not clean.** Baseline runs carry no MCP preamble and
  therefore no authorized set, so there is nothing to violate. This is the point:
  baseline has `/workspace` at the pinned revision and no cross-repo index to
  traverse, so it is *structurally* incapable of this leak. Counting it as "0
  violations" would wrongly imply it was tested and passed.
- **The one hybrid hit is weaker than the mcp_only ones.** `refactor-orch-002`
  cites upstream `spf13/cobra` inside a *subagent's* report, not from a direct
  MCP call, and no hybrid run actively read wrong-revision source.
- **12 runs (6 tasks) have an ambiguous authorized set, and are reported as
  such rather than counted as clean.** `ansible-abc-imports-fix-001`,
  `ansible-galaxy-tar-regression-prove-001`, `beam-pipeline-builder-refac-001`,
  `camel-routing-arch-001`, `ccx-dep-trace-106`, `ceph-rgw-auth-secure-001`
  (each ×`mcp_only`+`hybrid`) carry a generic scoping block *and* a
  task-specific one naming a **different revision of the same project**. Only
  one is the task's real pin; the other is boilerplate bleed. Both land in the
  authorized set, so a reference escaping into the wrong one would score
  AUTHORIZED — a false negative. Checked by hand: in all 12, the agent only
  ever touched the correct mirror, **so the table above is unaffected**. The
  auditor now prints an `AMBIGUOUS AUTHORIZED SET` warning for them, because a
  "clean" verdict there is *unsound*, not negative. Fixing the preambles is
  filed as its own bead.

Leaks by tool (calls whose results carried a wrong-revision repo): `keyword_search`
66, `read_file` 56, `find_references` 4, `Agent` (subagent report) 1. These are
corpus-wide call tallies over the scored runs, so they are unaffected by the
per-mode attribution. Two distinct modes hide in that spread, and they are not
equally serious:

- **Pin-violating** — a different revision of the *same* project. Breaks the
  revision pin. This is the acute mode, and codenav drives it.
- **Global-index bleed** — an unrelated third-party repo. Widens context and adds
  noise, but does not violate the pin.

The auditor keeps them apart deliberately; collapsing them would overstate the
harm.

### Exposure surface

| | |
|---|---|
| Mirrors | 133 |
| Distinct projects | 71 |
| Projects at **multiple** revisions | **22** |
| Mirrors belonging to a multi-rev project | **84 (63%)** |

Worst offenders: `grpc-go` ×12, `kubernetes` ×10, `etcd` ×9. Any MCP-arm task on
those projects is exposed.

## Finding 3 — the preamble promises scoping that codenav cannot honor

Every MCP preamble says:

> **Always scope your MCP searches to these repos:**
> `repo:^github.com/sg-evals/react--ab18f33d$`

Agents comply. In `dead-code-003` every single call carried the correct
`repo:` filter — and the leak happened anyway. For codenav the `repo` argument is
a **seed position, not a filter**: it says where to start resolving, not where
results may come from. There is no client-side way to honor the instruction the
preamble gives. This is a harness bug, not agent misbehavior (bead filed).

## Finding 4 — live per-repo status is UNKNOWN, and the acceptance criterion is not dischargeable

The bead asks for "per-repo SCIP index status for all stratum repos." That half
cannot be discharged now, and this document will not paper over it with a table
of UNKNOWNs:

- **The token is dead.** The `SOURCEGRAPH_ACCESS_TOKEN` in the environment
  (value redacted) returns **HTTP 401 on both** `demo.sourcegraph.com` (the arm
  target) and `sourcegraph.com`. Verified, not inherited.
- **The stratum is undefined.** Bead `.2` (difficulty stratum) is still open, so
  "stratum repos" has no referent yet.

What ships instead is the *instrument*: `verify_sg_indexing.py --check-api` now
performs a real GraphQL query per mirror and reports one of
`PRECISE | NONE | ABSENT | UNKNOWN`. Its load-bearing invariant is that a
failure to determine status (auth, transport, schema drift) yields **UNKNOWN and
never NONE** — reporting "not indexed" when we mean "could not tell" would
fabricate the very finding the tool exists to establish. With no token it exits
non-zero rather than printing a table of zeroes. Run it when a valid token
exists; the answer today is UNKNOWN for all 133 mirrors.

It keys on `repos[].sg_name` (the mirror). The per-suite view carries only
*upstream* names, and querying those would ask about `github.com/ansible/ansible`
— indexed on any public instance — and return a **false GREEN** for a mirror that
may not exist at all.

### `_indexed` is a placeholder and cannot corroborate anything

`configs/sg_indexing_list.json` reports `_indexed: false` for all 133 mirrors.
This is **not evidence**. `generate_sg_index.py` writes the field as a hardcoded
literal `False` for every entry; reading "0/133 indexed" back out is the tool
reporting its own placeholder. It is circular and it is cited nowhere in this
assessment. The literal is now annotated at its source, and the inventory output
labels it as an unverified placeholder rather than printing a bare "Indexed: 0"
that reads like a finding.

(The field is left in place: `validate_tasks_preflight.py` gates on its presence.
Replacing it with real status is filed as a separate bead rather than smuggled
into this one.)

## What would flip this to GO

The blocker is scope leakage, not index absence. Any one of these fixes it:

1. **Server-side scoping** — codenav honors a repo filter, so results cannot
   escape the authorized set.
2. **Harness-side guard** — the MCP layer drops or flags results from any repo
   outside the run's authorized mirror set. Cheapest option; the authorized set
   is already in the preamble and this audit already parses it.
3. **De-duplicate the corpus** — one revision per project on the instance. Kills
   the sibling-mirror class outright, but not upstream-HEAD leaks, and it costs
   the multi-revision tasks that several suites depend on.

Until one lands, an `all`-endpoint arm would amplify a known contamination path.

## Consequences for the current 3-arm study

Cross-revision contamination is a confound in the **MCP-vs-baseline headline**:
it affects `mcp_only` runs only, so it is asymmetric across arms, and it is the
same class of problem as the `docker-cp`/`pt0n` contamination already tracked.
Eleven runs across eight tasks demonstrably read wrong-revision source. Whether
to rescore or exclude them is filed as its own bead — it is a scoring-integrity
decision, not an indexing one, and it should not be settled inside this
assessment.
