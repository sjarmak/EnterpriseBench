# EnterpriseBench × Snorkel — Collaboration & Division of Labor

**Status:** Draft for discussion · **Owner:** EnterpriseBench team

## Premise

Snorkel's CSB+ spec and EnterpriseBench (EB) are the same benchmark described in
two vocabularies. CSB+ contributes two ideas EB lacks — per-task *proof* that a
task is retrieval-bound (hard/guided variant gap), and *empirically measured*
difficulty against a frontier-model panel. EB contributes mature infrastructure
that **reduces the per-task expert-labor cost** that drives a services engagement.

The proposal: EB pre-computes everything that shrinks the human-expert surface;
Snorkel spends expert hours only on the irreducibly-human work. This aligns both
parties' incentives — every task EB makes cheaper to author is value delivered,
not margin lost.

## The cost lever

The spec's reliability rests on *expert-authored, per-item-ablated gold context*.
That is exactly the single-source manual curation that capped CSB's original
ground truth at **F1 = 0.70** — and it is also the primary cost driver of an
expert-hours-based engagement.

EB's **deterministic Tier 1** (AST parsing + import/dependency-graph extraction)
emits *candidate* gold context mechanically. This converts the expert task from
**author-from-scratch (expensive)** into **validate-and-prune (cheap review)**,
and anchors the result so it does not regress to the 0.70 ceiling. This is the
core of the collaboration and should be the contracted unit of work.

## Division of labor

| Area | Owner | EB asset / Snorkel deliverable |
|---|---|---|
| Task substrate | **EB** | 112 active + 275 CSB tasks, mined multi-repo candidates, pinned repos (`repo_versions.json`), 3-mode Dockerfiles, sandboxes |
| Candidate gold context | **EB** | Deterministic Tier 1 emits required/sufficient candidates with line ranges + provenance |
| Necessity pre-screen | **EB** | CRNT validator rejects non-retrieval-bound tasks *before* expert time is spent |
| Verifier harness + soundness gate | **EB** | `eb_verify` plugins; per-task gate (empty=0, oracle=full, reject no-op/inverted) |
| Output contract | **EB** | Unified `ScoreResult` (retrieval recall/precision/F1 + outcome + cost + tool-calls) |
| Gold-context validation + ablation | **Snorkel** | Confirm/prune EB candidates; per-item ablation confirming minimality |
| Hard/guided variants | **Snorkel** | Author the retrieval-bound proof (fails-hard, solves-guided) |
| Empirical difficulty | **Snorkel** | Frontier-panel calibration; exclude non-discriminating tasks |
| Milestone authoring | **Snorkel** | 2–5 step sequences where state + context carry forward |

## Interface contract (settle before volume authoring)

1. **On-disk layout.** Reconcile CSB+ (`environment/`, `solution/`,
   `tests/gold_context.json`) with EB (`task.toml`, `ground_truth.json`,
   `checks/`). Adopt one target schema so deliverables import natively — a
   translation layer paid per-task is pure waste. EB schema is the proposed target.
2. **Gold-context schema.** Keep EB's two-tier `required_files` / `sufficient_files`
   with chunk-level line ranges, confidence, and source provenance. Do not collapse
   to a single minimal set — the gradient drives retrieval partial-credit.
3. **Task-type taxonomy.** Map CSB+'s 7 format-grouped types onto EB's 10 workflow
   types; preserve resolution rather than folding to 7.
4. **Tool conditions.** Retain EB's three modes (baseline / mcp_only / hybrid).
   `hybrid` is the realistic enterprise condition; two-condition design cannot
   separate "tool helps when forced" from "agent chooses to use it well."

## Commercial terms to define

- **Unit of work** in the SOW: contract "validate EB-generated candidate context"
  (cheaper) explicitly, not "author context" — the deterministic-tier handoff is
  the price difference.
- **IP / reuse rights:** whether Snorkel may resell tasks; whether EB owns the
  merged benchmark.
- **Refresh ownership:** commit re-pinning + difficulty re-calibration as models
  improve — EB-internal (tooling exists) vs. Snorkel retainer.
- **Release model (public by design):** EB ships as a public benchmark. That does
  not mean publishing answers. Split the surface:
  - **Public:** harness, task format, metadata, methodology, and a small **dev
    split** for repro/tuning.
  - **Held-out:** the scored **test split's** `solution/` + `ground_truth.json`,
    served only through a **graded submission endpoint** — never in the repo.
  Privacy of the working repo is a staging concern, not the durability mechanism.

## Public-release & contamination strategy

A public, retrieval-bound benchmark cannot rely on secrecy — once published,
every task contaminates on a clock (a memorized task is solved without retrieval,
defeating the thesis). The durability mechanism is **refresh, not privacy**:

1. **Held-out scored split behind a grader** (above) — instructions public,
   answers not.
2. **Time-windowed mining** — the spec's "recent changes, pinned commit" seed,
   run continuously to mine tasks from commits *after* current model training
   cutoffs, keeping an uncontaminated live slice each generation.
3. **Generational recalibration + retirement** — re-run the frontier-difficulty
   panel each model generation; retire tasks the panel solves from memory.

CSB-derived tier: because CSB is already public, the 275 carried-forward tasks
are the **most contaminated** and lowest-trust. EB's net-new multi-repo tasks +
new gold context are the trustworthy core. Snorkel's empirical-difficulty panel
**doubles as the contamination filter** — "exclude tasks every model solves
regardless of retrieval" drops memorized tasks by the same mechanism. Run it on
the CSB tier first; record per-task contamination verdicts as a deliverable.

**Engagement consequence:** the refresh pipeline (mine post-cutoff tasks,
re-pin/re-calibrate, retire) is recurring expert-labor work, not a one-time
build. The "refresh ownership" commercial term below is therefore the *center*
of a durable public benchmark, not a footnote — and is squarely Snorkel's model.

## What EB needs from Snorkel to start

1. Confirmation of the target on-disk layout and gold-context schema.
2. A 5–10 task pilot batch run through the full split above, to price the
   validate-and-prune unit of work empirically before committing to volume.
