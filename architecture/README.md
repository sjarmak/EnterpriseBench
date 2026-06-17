# Architecture diagram (LikeC4)

Architecture-as-code model of `EnterpriseBench`, rendered with
[LikeC4](https://likec4.dev). The model is the source of truth across
[`spec.c4`](spec.c4) (element kinds, tags, deployment node kinds),
[`model.c4`](model.c4) (the system), and [`views.c4`](views.c4) (structure,
walkthrough, and risk views), with the deployment model in
[`deployment.c4`](deployment.c4). The narrative companion is
[`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) and the converged design
rationale in [`docs/CONVERGENCE_REPORT.md`](../docs/CONVERGENCE_REPORT.md).

Every element `link`s to its source (`benchmarks/…`, `lib/eb_verify/…`,
`scripts/…`, `agents/…`, `configs/…`) and, where one exists, to the relevant
design doc — so any box in the explorer is one click from the code and the
rationale behind it.

## Delivery state is tagged, not guessed

Every element carries a tag so **work whose science/contract is still moving
renders distinctly from what is already built** (legend in `spec.c4`):

| Tag | Meaning | Render |
|---|---|---|
| `#built` | code path exists and is exercised (Phase 5 complete) | solid |
| `#evolving` | built, but the science/contract is still moving | **amber** |
| `#planned` | designed; not yet implemented (or v1 is a stub/heuristic) | dashed, dimmed |
| `#research` | speculative research track | dashed, indigo |

The corpus, mining, sandbox, MCP integration, orchestration, and the
`eb_verify` scorer are all `#built`. The `#evolving` elements are the analysis /
statistical layer (mode-discrimination + power gates, the judge-based ablation
headline, the report/paper figures), the `eb_metrics` quality adapter, and the
LLM-curator (Tier-2 ground truth). No `#planned` or `#research` tracks exist in
the working tree today, so there is no `planned` lens.

## Views

**Structure** — the static map:

| View | Scope |
|---|---|
| `index` | system landscape — `EnterpriseBench` in context of OSS/GitHub, Sourcegraph (+ MCP), Docker, inference models |
| `ebSystem` | the `EnterpriseBench` system decomposed into its eight containers + the results datastore |
| `corpusContainer` | task corpus — TOML definitions, schema/preflight, layered ground truth, repo pins |
| `miningContainer` | task mining pipeline — OSS history → draft task, CRNT + mix gates |
| `sandboxContainer` | sandbox builder — Dockerfile generation, build/measure, health & test runners |
| `mcpContainer` | MCP integration — Sourcegraph preamble, mirror creation/indexing, staleness check |
| `orchestrationContainer` | dispatch + the four session-type runners (single / chain / event-replay / promotion) + sweep |
| `verifyContainer` | `eb_verify` — checkpoint runner, 9 artifact validators, deterministic parsers, LLM judge, scoring |
| `qaContainer` | QA & soundness gates — mutation test, contamination scan, solve-verify, curator/consensus |
| `analysisContainer` | analysis & reporting — score engine, triage, mode/power gates, ablation judge, cost, charts/figures |
| `deployment` | where each piece runs — local toolchain processes, Docker sandbox, Sourcegraph, OSS, inference host |

**Walkthrough flows** (dynamic / numbered-step views) — the narrative spine for
a design-review walkthrough:

| View | Flow |
|---|---|
| `mineTask` | mining a task from OSS history (discover → CRNT → mix gate → schema-validated corpus entry) |
| `benchmarkRun` | one benchmark run end-to-end (route → build sandbox → inject MCP → run agent → score) |
| `verifyFlow` | checkpoint verification of a completed task (route by artifact → structural + GT match → LLM judge → `min(grep, judge)` → reward) |
| `analysisFlow` | runs → MCP-benefit figures (re-scan → calibration/mode/power gates → judge rescore → paper figures) |

**Risk lens:**

| View | Scope |
|---|---|
| `risks` | the `#risk`-flagged elements with each open question stated in-box — ground-truth/verifier **contamination** (the active fix class), small N per stratum limiting mode-delta power, and the judge-based ablation headline still being pinned |

### Running the walkthrough

For a design review, present in this order: `index` → `ebSystem` (orient on
structure) → the four walkthrough flows in sequence (`mineTask` → `benchmarkRun`
→ `verifyFlow` → `analysisFlow`) → `deployment` (where it runs) → `risks` (what
to probe). In `npx likec4 start`, the dynamic views animate step-by-step and
each view's notes panel carries the gotchas (the three tool-access modes, the
`min(grep, judge)` scoring contract, the parallelize-across-accounts caveat).

## Viewing & regenerating

```bash
# Interactive, hot-reloading explorer (recommended)
npx likec4 start architecture

# Re-export the static PNGs in exports/ (needs a one-time browser download:
#   npx playwright install chromium-headless-shell)
npx likec4 export png architecture -o architecture/exports

# Validate the model (strict — the source of truth for correctness)
npx likec4 validate architecture
```

### Viewing the interactive explorer over SSH (headless remote)

`likec4 start` serves a Vite dev server on `localhost:5173`. From a headless
remote, forward that port to your laptop and open it locally — three options,
easiest first:

1. **VS Code / Cursor Remote-SSH** — run `npx likec4 start architecture` in the
   integrated terminal; the editor auto-forwards 5173 and offers "Open in
   Browser". Nothing else to configure.
2. **SSH local port-forward** — on your laptop:
   ```bash
   ssh -N -L 5173:localhost:5173 user@remote   # leave running
   ```
   then on the remote `npx likec4 start architecture` and open
   <http://localhost:5173> locally. (Already in an SSH session? Add the tunnel
   without reconnecting: press `~C` then type `-L 5173:localhost:5173`.)
3. **Bind + reach directly** — `npx likec4 start architecture --listen 0.0.0.0`
   and browse to `http://<remote-ip>:5173` (only if that port is reachable /
   firewall-open; the tunnel in option 2 is safer).

No browser at all? `npx likec4 export png` needs no display once
`chromium-headless-shell` is installed — `scp` the PNGs down, or view inline if
your terminal supports images.
