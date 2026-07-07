---
name: eb-git-and-dispatch-workflow
description: How change is gated and dispatched in EnterpriseBench — the branch-per-bead git model, squash-style main, which changes are HALT-branch-ready (require Stephanie's approval before merge), the parked-not-dead fix/eb-* branch inventory, the current direct-dispatch-only rule while the mol-focus-review formula is broken, and the .gc-reports audit cadence. Load this when you are about to start work on a bead, create or merge a branch, decide whether a change needs approval before landing, wonder whether an unlanded fix already exists on a branch, dispatch or claim EnterpriseBench work in the Gas City fleet, or interpret bead/mayor/formula/worktree machinery in this repo.
---

# EnterpriseBench git and dispatch workflow

How a change moves from idea to `main` in this repo, and where it must stop
and wait for a human. This is a process skill: it covers gating, branches,
beads, and dispatch — not what to change or how to test it.

> **INTERNAL-ORCHESTRATION NOTICE.** This is the ONLY skill in this library
> that documents Gas City fleet machinery (beads, mayor, formulas, `gc`/`bd`
> CLI, worktree dispatch). Every other `eb-*` skill is written to survive a
> public clone of the repo; this one is not. Sections marked
> `[internal-orchestration]` assume Stephanie's ds-research machine and the
> Gas City runtime, and should be stripped or excluded if the repo is
> published. (PROVISIONAL pending Stephanie — placement per discovery Q1.)

## When NOT to use this skill

| You actually want                                               | Use instead                   |
| --------------------------------------------------------------- | ----------------------------- |
| Repo map, what EnterpriseBench is, source-vs-worktree layout    | eb-orientation                |
| The score-integrity invariant and the silent-misscore bug class | eb-scoring-integrity-doctrine |
| Which scorer is production, checkpoint/judge mechanics          | eb-checkpoint-scoring         |
| Getting tests green the way CI is green                         | eb-build-and-test             |
| Running tasks/campaigns, promoting runs to official             | eb-run-and-analyze            |
| Authoring or editing a task                                     | eb-task-authoring             |
| The scorer_guard consolidation campaign                         | eb-scorer-guard-campaign      |

## Vocabulary (defined once)

- **bead** — a work item in the `bd` issue tracker (`.beads/`). IDs look like
  `EnterpriseBench-apfp`. The bead store, not code TODOs, is the backlog.
- **branch-ready** — a branch containing the finished change **with its tests
  in the same commits**, pushed nowhere, merged nowhere; ready for review.
- **HALT-branch-ready** — a gating class: work MUST stop at branch-ready.
  Merging/publishing is done by the mayor only after Stephanie approves.
- **mayor / PL / pool worker** `[internal-orchestration]` — Gas City agent
  roles: the mayor is the always-on orchestrator; the EnterpriseBench PL
  (`enterprisebench-pl-gc-454418`) runs periodic self-audits; pool workers
  execute dispatched beads in worktrees.
- **formula** `[internal-orchestration]` — a Gas City multi-step workflow
  template (e.g. `mol-focus-review`) attached to a bead at dispatch time.
- **direct dispatch** `[internal-orchestration]` — the mayor hands a bead
  straight to a worker session without a formula.

---

## 1. The git model (verified 2026-07-07)

- Remote: `origin = https://github.com/sjarmak/EnterpriseBench.git`.
- `main` is integration-only: **172 commits** (`git rev-list --count main`),
  almost all squash-style single commits carrying a bead ID in the subject,
  e.g.
  `fix(eb-verify): cap answer/incident_report artifact reads ... (EnterpriseBench-1cm8)`.
  7 true merge commits exist (recent `merge: wave-*-review` integrations), so
  "squash-merged" is the norm, not an absolute.
  Counting trap: `git log --oneline | wc -l` reports 50 on this machine
  because the rtk proxy truncates `git log` output at 50 lines — always use
  `git rev-list --count` for commit counts.
- The real history lives in **~51 branch refs**: `fix/eb-<bead>-<slug>`,
  `audit/eb-*`, `feat/eb-*`, plus `worktree-wf_*` leftovers from formula runs.
  Branch names encode the bead and the fight; read them as a chronicle.
- The repo CLAUDE.md convention line "All work on `main`" describes the
  integration target, not the working area: in practice (verified in `git
log` this session) work happens on a branch per bead and lands on `main`
  as one squash-style commit.
- **AGENTS.md override.** AGENTS.md's session-completion protocol (lines
  61-83: "Work is NOT complete until `git push` succeeds… NEVER stop before
  pushing") is generic beads-integration boilerplate and is **overridden by
  this skill for all bead/scoring-path work**: workers stop at branch-ready
  and never push (sections 1, 3, 8). Publication is the mayor's job after
  Stephanie's approval. If you are following AGENTS.md and this skill
  disagrees, this skill wins — the same way the CLAUDE.md "All work on
  `main`" line is overridden above.
- Commit style: conventional types (`fix|feat|refactor|test|docs`), scope in
  parens, bead ID in the subject or trailing parens.

```bash
git log --oneline -15                 # see the squash-style bead commits
git branch -a                         # the branch chronicle
git log --merges --oneline | wc -l    # 7 as of 2026-07-07
```

**Never run mutating git against `main`** (`merge`, `push`, `rebase main`,
`branch -D` on shared refs) as part of bead work. Branch-ready is the end
state for a worker; publication is the mayor's job after approval.

## 2. Parked-not-dead: check branches BEFORE writing code

The ~40 `fix/eb-*` / `audit/eb-*` branches are **parked, not dead**
(PROVISIONAL pending Stephanie — discovery Q5). Several known-good integrity
fixes exist ONLY on branches, not on `main` (verified against the 2026-07-06
audit): `fix/eb-7jpm-grading-integrity` (pristine-verifier re-copy),
`fix/eb-wbsq-scoring-gaps` (+ `-rebased`) (JSON-injection / awk-RCE),
`fix/eb-cdzi-runner-consolidation` (two-scorer duplication),
`fix/eb-5eq9-preserve-branch-triage` (holds the grounded-citation gate that
is absent from `main`).

Before starting any bead, run this sequence — duplicating an unlanded fix or
"discovering" a bug that is already fixed on a branch wastes a full cycle:

```bash
# 1. Does a branch already touch my area?
git branch -a | grep -i <topic>
# 2. What does it contain that main doesn't?
git log --oneline main..fix/eb-<bead>-<slug>
# 3. What does the bead thread say?  [internal-orchestration]
bd show EnterpriseBench-<bead>
```

Never declare a parked branch dead or delete it; if it looks superseded, say
so in the bead thread and leave the ref alone.

## 3. HALT-branch-ready gating

Some change classes must stop at branch-ready and wait for Stephanie's
personal sign-off. The canonical wording, verbatim from bead
`EnterpriseBench-apfp` (verified this session):

> "Tests ship with the fix. HALT branch-ready — mayor publishes after
> Stephanie approval; touches the production scoring path."

**Confirmed HALT class (production scoring path):** anything that can change
a recorded score —

| Surface                           | Files (verified to exist 2026-07-07)                   |
| --------------------------------- | ------------------------------------------------------ |
| Production scorer / orchestration | `scripts/orchestration/run_task.py`                    |
| In-container checkpoint runner    | `scripts/sandbox/test_runner.sh`                       |
| Artifact validators & scoring lib | `lib/eb_verify/` (validators, judge cap, groundedness) |

**Provisionally HALT (treat AS IF HALT until Stephanie rules — PROVISIONAL
pending Stephanie, discovery Q5):**

| Change class                                    | Where it lives                            | Precedent                                                                                   |
| ----------------------------------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------- |
| Task-mix changes (add/retire/re-stratify tasks) | `benchmarks/`, gated by `make verify-mix` | PRD mix targets are a published claim                                                       |
| Repo repins (SHA/tag bumps)                     | `configs/repo_versions.json`              | pins are ground-truth anchors; staleness checked by `scripts/infra/check_repo_staleness.py` |
| Grading-keyword relaxation/tightening           | per-task `task.toml` / `checks/*.sh`      | commit `c01c817` "relax brittle grading keywords in pilot tasks per solve-verification"     |

Rules inside the HALT class:

1. **Tests ship with the fix** — in the same commits on the branch, never a
   follow-up. A HALT branch without tests is not branch-ready.
2. Stop at branch-ready. Do not merge, do not push to `main`, do not close
   the bead as done. Record branch name + summary in the bead and hand off.
3. Run the local gates first so the approval is about the change, not the
   mechanics: `pip install -e lib/` once, then
   `pytest tests/ -m "not network and not docker"`, plus `make verify` if you
   touched anything under `benchmarks/` or `configs/`.

If you are unsure whether your change is in the HALT class, it is. The cost
asymmetry is absolute: a wrongly-gated cosmetic change costs one approval
round-trip; an ungated scoring change can contaminate published numbers
(the docker-cp silent-zero contaminated 5 published runs — see
eb-scoring-integrity-doctrine).

## 4. Beads: the work queue `[internal-orchestration]`

The backlog is the `bd` bead store (`.beads/`, Dolt-server-backed, issue
prefix `EnterpriseBench`), not code TODOs (only 7 TODO/FIXME markers exist in
non-worktree Python).

```bash
bd ready                       # what is claimable now
bd show EnterpriseBench-<id>   # full thread for one bead
bd list --assignee <you>       # your claims
```

Conventions and traps (each verified or inherited from the Gas City house
rules):

- **Never** run `bd dolt start|stop|status` in this repo — it kills the live
  gc-managed Dolt server (standing Gas City rule; `.beads/config.yaml` sets
  `dolt.auto-start: false` for the same reason).
- One bead = one branch = one squash landing. Name the branch
  `fix/eb-<bead-suffix>-<slug>` (or `audit/`, `feat/` as appropriate).
- Many `Rollup(enterprisebench)` beads are the PL's heartbeat/audit trail,
  not claimable work. Read them for state; don't claim them.
- **Do not claim `gc.kind=workflow` / `workflow-finalize` control beads**,
  even if a pool nudge repeatedly asks you to. Those latches belong to the
  control-dispatcher lane; claiming them stamps an assignee on bookkeeping
  and fights the graph controller (this exact failure wedged 23 workflows —
  bead `EnterpriseBench-mi5v`).
- Bead threads are the durable record: decisions, back-outs, and Stephanie
  rulings live there, not in git (squash hides reverts).

## 5. Dispatch: direct-dispatch ONLY while mol-focus-review is broken `[internal-orchestration]`

**Dated note — status as of 2026-07-07.** The `mol-focus-review` formula
(the default work formula for this rig) is broken in three verified ways,
each a live P1 bug in the bead store:

| Bead                   | Failure                                                                               |
| ---------------------- | ------------------------------------------------------------------------------------- |
| `EnterpriseBench-mi5v` | 23 workflow roots wedged on an empty `workflow-finalize` step                         |
| `EnterpriseBench-73pw` | finalize step lacks a cd-into-worktree guard — completed work (`uo8v`) landed nowhere |
| `EnterpriseBench-1fb2` | workspace-setup uses `--detach`, orphaning unreachable commits on worktree teardown   |

Consequences, until those beads close:

- **Do not sling work through `mol-focus-review`** — it manufactures orphaned
  commits and wedged convoys (the 2026-07-06 audit explicitly declined to
  dispatch its own findings for this reason).
- Scoring-path and other priority work is **direct-dispatched by the mayor**
  (bead handed to a worker session without a formula). If you are a worker:
  expect your task in the bead description + mayor mail, work on a branch in
  a worktree you own, and finish at branch-ready per section 3.
- If you must sling a skill-based job, the working pattern is
  `gc sling --no-formula` (formulas do not compose with pool-worker routing).

Re-check before relying on this note — it is volatile:

```bash
bd show EnterpriseBench-mi5v   # still open => formula still broken
bd show EnterpriseBench-73pw
bd show EnterpriseBench-1fb2
```

The formula definitions themselves are machine-local symlinks
(`.beads/formulas/*.formula.toml -> /home/ds/gas-city/formulas/...`) and are
NOT tracked by this repo's git — do not try to fix a formula with a repo
commit.

## 6. Worktree hygiene `[internal-orchestration]`

Formula and agent dispatch created ~105 stale `enterprisebench-*` directories
at the repo root plus `.claude/worktrees/*` — full copies of the tree. Two
rules:

- Never grep/edit/count across them; the real project is `lib/`, `scripts/`,
  `agents/`, `configs/`, `benchmarks/`, `schemas/`, `tests/`, `docs/`
  (see eb-orientation).
- Never delete them as part of bead work; worktree reaping is a mayor/ops
  concern with its own tooling.

## 7. The .gc-reports audit cadence

`.gc-reports/` holds the PL's deep-audits, named `audit-YYYY-MM-DD.md`.
Verified on disk: 2026-06-15, 2026-06-22, 2026-06-29, 2026-07-06 — a weekly
cadence (observed pattern, not a checked-in schedule). The directory is
`.gitignore`d (line 58), so audits exist only on the working machine.

Each audit has a fixed shape worth knowing before you read one:

1. **Smartest / most accretive addition** — the audit's designated
   highest-leverage next move (2026-07-06: the scorer_guard consolidation).
2. **Best-practices audit** — severity-ranked findings with verified
   file:line refs at a stated `main` HEAD.
3. **BLOCKED_CHECK** — whether anything needs a Stephanie answer.
4. **Actions** — beads filed, escalations made or declined.

Use them as the primary archaeology source: findings there are already
verified against a specific HEAD, and every major scoring-integrity incident
is cross-referenced to its bead and branch. Before trusting a finding, check
the HEAD it was verified at (`git log -1 --format=%h`) against the audit's
stated HEAD.

## 8. Checklists

**Before starting a bead**

- [ ] `bd show <bead>` read in full, including comments (rulings live there)
- [ ] Not a Rollup / workflow-control bead
- [ ] `git branch -a | grep <topic>` — no parked branch already does this
- [ ] Gating class identified (HALT vs normal) per section 3
- [ ] Working on a branch named `fix/eb-<bead>-<slug>` in your own worktree

**Before declaring branch-ready**

- [ ] Tests for the change are in the same commits
- [ ] `pip install -e lib/` done; `pytest tests/ -m "not network and not docker"` green
- [ ] `make verify` green if `benchmarks/` or `configs/` touched
- [ ] No commits touched `main`; no pushes anywhere
- [ ] Bead updated with branch name, summary, and (if HALT) an explicit
      "HALT branch-ready, awaiting Stephanie approval" line

## Provenance and maintenance

Authored 2026-07-07 against `main` HEAD `7cfb8b0` on the ds-research working
copy. Every path, command, count, and bead quote above was verified that day.
Volatile facts and their one-line re-verification commands:

```bash
git rev-list --count HEAD                          # main commit count (was 172; NOT `git log | wc -l` — rtk truncates at 50)
git log --merges --oneline | wc -l                 # merge commits (was 7)
git branch | wc -l                                 # local branch refs (was 51)
git log --oneline main..fix/eb-wbsq-scoring-gaps   # integrity fixes still unlanded?
bd show EnterpriseBench-mi5v                       # mol-focus-review still broken? (section 5 expires when closed)
bd show EnterpriseBench-apfp                       # HALT-branch-ready wording; scorer_guard status
ls .gc-reports/                                    # audit cadence still weekly?
grep -n "gc-reports" .gitignore                    # audits still untracked (was line 58)
git log --oneline --grep="relax"                   # grading-keyword precedent c01c817
ls scripts/orchestration/run_task.py scripts/sandbox/test_runner.sh  # HALT surface paths
```

Provisional dependencies (revisit when Stephanie answers the discovery
questions): Q1 — this skill's internal-orchestration placement and
strip-on-publish rule; Q5 — the provisional HALT classes (task-mix, repins,
grading keywords) and the parked-not-dead branch policy. Q2 is reflected only
in section 5 being a dated routing note rather than a campaign (the campaign
is eb-scorer-guard-campaign).
