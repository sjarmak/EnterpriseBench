# Convergence Report: Evolving CodeScaleBench into EnterpriseBench

## Executive Summary

EnterpriseBench is an evolution of CodeScaleBench (CSB, 275 tasks, unpublished) that measures **codebase understanding and context gathering** — how well agents find and comprehend the right code across large, distributed codebases. Sourcegraph MCP is a first-class showcase but tool access is a controlled independent variable, not baked in. The benchmark is agent-agnostic and extensible.

This report synthesizes findings from:
- 6 divergent prototypes (sandbox, verification, session-chain, event-replay, task mining, MCP mirror integration)
- 4 research agents on MCP integration
- 3 research agents on Sourcegraph MCP vs local search head-to-head
- 4 research agents on context-gathering benchmark design
- Deep exploration of CodeScaleBench's architecture, QA pipeline, and curator agent
- 2 structured convergence debates (8 advocate positions total)

## Resolved Points (Unanimous)

1. **CSB's 275 tasks (especially 220 Org tasks) are the foundation** — keep, fix, extend, don't rebuild
2. **Context retrieval quality is the primary measurement target** — not code generation or implementation
3. **MCP is a controlled independent variable** — three-mode approach (baseline / MCP-only / hybrid)
4. **Sourcegraph must NOT contaminate ground truth** — curator is tool-independent
5. **Ground truth needs multiple validation signals** — layered architecture, not single-source
6. **Current curator F1=0.70 is insufficient** — needs deterministic layer + solve-verification
7. **Multi-repo tasks are the genuine differentiator** vs ContextBench and SWE-bench
8. **Tool-usage metadata must be captured** for every run

## Ground Truth Architecture (Layered)

- **Tier 1 — Deterministic**: AST parsing, import graphs, dependency manifests (go.mod, package.json). Mechanically verifiable. No LLM.
- **Tier 2 — LLM Curator**: Handles semantic relevance (config files, docs, cross-cutting concerns). Cross-backend validation (local vs deepsearch >80% F1 agreement). Two-tier annotation: required vs sufficient files.
- **Tier 3 — Solve-verification**: Different model attempts task using ONLY curated context. Failure = incomplete ground truth.
- **QA overlay**: Confidence-weighted scoring, adversarial audit on sample, mutation testing on verifiers.

## Curator Agent Best Practices

1. **Tool-independent generation**: Never uses Sourcegraph or any evaluated tool during ground truth creation
2. **Cross-backend validation**: Run with local-only AND separate search backend. Agreement >80% F1 = high confidence
3. **Deterministic verification layer**: Every structural claim verified by AST/import parsing
4. **Solve-verification loop**: Different model confirms context sufficiency
5. **Two-tier annotation**: Every file labeled "required" or "sufficient" — drives weighted scoring
6. **Chunk-level annotations**: Line ranges per file, not just paths
7. **Confidence metadata**: Each file carries confidence score + source
8. **Adversarial audit**: Sample re-curated with different prompt/temperature

## Scoring Architecture

- **Required files** (deterministic + curator agreement): Missing = significant penalty. Binary match.
- **Sufficient files** (curator-identified, lower confidence): Missing = small penalty. Soft matching.
- **Chunk-level**: Line ranges within files for block-level precision/recall
- **Checkpoint-based partial credit**: Graduated scoring from EnterpriseBench prototypes

## Task Architecture

| Component | Current CSB | Evolved Benchmark |
|---|---|---|
| Ground truth | Curator-only (F1=0.70) | Layered: deterministic + curator + solve-verification |
| Scoring | Binary file-set match | Two-tier (required/sufficient) + chunk-level + checkpoint partial credit |
| QA | Pre-flight + golden validation | + Cross-stage integration tests + expanded fixtures (6 types) + mutation testing |
| Taxonomy | SDLC phases + Org suites | 7 enterprise workflow clusters + difficulty gradient |
| Task mix | 186 single / 28 dual / 61 multi | 15% calibration + 25% large-single + 30% 2-repo + 20% 3-5 repo + 10% monorepo |
| MCP | 4 configs, separate runs | 3 modes per task (baseline/MCP-only/hybrid) + tool-usage metadata |
| Metadata | Scattered (8+ files) | Single source of truth, validated at startup |

## Sourcegraph MCP Integration

- **Showcase through honest comparison**: Tasks are about understanding, not tools. Tool access is the independent variable.
- **15% calibration tasks**: Single-repo, small codebase where MCP advantage should be <0.05. Bias check.
- **sg-evals mirrors**: 178 existing mirrors from CSB, extended via P6 prototype for multi-repo tasks
- **Three Dockerfile modes**: Standard (no MCP), SG-Only (mandatory MCP), Hybrid (realistic)
- **Rich metadata**: Which MCP tools called, frequency, latency, token cost — captured for every run

## Priority Ordering (Dependencies, Not Timelines)

Phase 1 (parallel tracks, all must complete before Phase 2):
- Track A: Fix 12 CSB bugs + single source of truth for metadata
- Track B: Build cross-stage integration tests (canary tasks)
- Track C: Add deterministic verification layer to curator
- Track D: Tag existing 275 tasks with difficulty gradient + 7-suite taxonomy

Phase 2 (depends on Phase 1):
- Extend curator with solve-verification loop
- Implement two-tier + chunk-level scoring
- Run expanded fixture matrix (6 types) on all 275 tasks
- Mine new multi-repo tasks with layered ground truth

Phase 3 (depends on Phase 2):
- MCP comparison runs (3 modes x selected tasks)
- Session-chain tasks for multi-session understanding
- Publish
- 15% calibration analysis (verify MCP bias < 0.05 on easy tasks)

## Prototype Inventory (Worktree Branches)

| Branch | Prototype | Quality | Key Deliverable |
|---|---|---|---|
| worktree-agent-a1e42ace | Multi-repo sandbox | 3/5 | Dockerfile gen + real measurements (11-33MB workspace) |
| worktree-agent-ab79e078 | eb_verify library | 3/5 | Plugin-based verifiers, checkpoint runner, CLI |
| worktree-agent-a4c13c21 | Session-chain orchestrator | 3/5 | Git-branch handoff, simulation mode |
| worktree-agent-abe10a0f | Event-replay engine | 3.5/5 | 4-dimension action scorer, 19-event scenario |
| worktree-agent-a366bfe8 | Task mining pipeline | 3/5 | 3 real mined tasks, 60% conversion rate |
| worktree-agent-a5024420 | MCP mirror integration | 4/5 | Three Dockerfile modes, sg-evals mirror gen |

## Research Provenance

Two convergence debates with 8 total advocate positions:

**Debate 1** (Architecture): Verification Purist, MCP-Integrated Realist, Ship-Fast Pragmatist, Research Maximalist
**Debate 2** (CSB Evolution): QA Architect, Curator Methodologist, MCP Showcase Designer, CSB Evolutionist

Key debate outcomes:
- Verification-first sequencing won (Debate 1)
- Schema includes MCP from day one won (Debate 1)
- Layered ground truth emerged from tension between deterministic and LLM approaches (Debate 2)
- Fix-extend-enhance beat replace-rebuild (Debate 2)
- Tool-independence of curator was unanimous (Debate 2)
