# Dead Code / Feature Flag Necropsy Candidates

Mined candidates for `dead-code-*` tasks. Each candidate is a real cleanup PR
that removed dead code from a large OSS codebase. The task starting state is the
commit *before* the cleanup PR.

---

## facebook/react (4 candidates)

### Candidate 1: Remove dead code from modern event system

- **PR:** [#19233](https://github.com/facebook/react/pull/19233) — "Remove dead code from modern event system"
- **Author:** Dan Abramov (2020-07-01)
- **Cleanup commit:** `75b6921d6429cc2d7456bd66684263ae63dc6abb`
- **Parent commit (task start):** `9fba65efa50fe5f38e5664729d4aa6f85cf7be92`
- **Scope:** 38 files, +237 / -755 lines
- **Dead code removed:**
  - Entire `legacy-events/` directory (4 files: EventPluginRegistry, EventPluginUtils, accumulateInto, forEachAccumulated)
  - Dead event pooling logic in SyntheticEvent.js (getPooled, destructor)
  - Unused ReactDOMClientInjection.js (entire file)
  - Dead code in TopLevelEventTypes.js, ReactTestUtils.js
- **Feature flags:** Event pooling was behind `enableDeprecatedFlareAPI` (permanently off)
- **Difficulty:** Hard — dead code spans legacy-events directory, event system internals, and test utilities; requires understanding modern vs legacy event system boundary
- **Why interesting:** Agent must prove that entire `legacy-events/` directory has zero callers after the modern event system was complete. Dynamic dispatch through plugin registry makes grep insufficient.

### Candidate 2: Remove feature flag enableRenderableContext

- **PR:** [#33505](https://github.com/facebook/react/pull/33505) — "Remove feature flag enableRenderableContext"
- **Author:** Ruslan Lesiutin (2025-06-11)
- **Cleanup commit:** `6c86e56a0fa3`
- **Parent commit (task start):** `56408a5b12fa4099e9dbbeca7f6bc59e1307e507`
- **Scope:** 27 files, +48 / -292 lines across 7 packages
- **Dead code removed:**
  - `enableRenderableContext` flag from all feature flag forks (7 files)
  - Dead branches in ReactContext.js (73 lines of context provider/consumer logic)
  - Dead branches in ReactFiber.js, ReactFiberBeginWork.js, ReactFizzServer.js
  - Unused REACT_PROVIDER_TYPE symbol
- **Feature flags:** `enableRenderableContext` — permanently enabled, dead branches were the `else` paths
- **Difficulty:** Hard — cross-package (react, react-reconciler, react-server, react-is, shared), requires tracing feature flag through all forks
- **Why interesting:** Classic feature flag necropsy — flag was permanently on, so the `false` branches in 27 files were dead. Agent must identify the flag, trace all usages, and confirm the dead branches.

### Candidate 3: [compiler] Remove fallback compilation pipeline dead code

- **PR:** [#35827](https://github.com/facebook/react/pull/35827) — "[compiler] Remove fallback compilation pipeline dead code"
- **Author:** Joseph Savona (2026-02-23)
- **Cleanup commit:** `8b6b11f703a1f92dd2bb2e0e3b93a1836dc06de6`
- **Parent commit (task start):** `ab18f33d46171ed1963ae1ac955c5110bb1eb199`
- **Scope:** 6 files, +7 / -198 lines
- **Dead code removed:**
  - Entire `ValidateNoUntransformedReferences.ts` (162 lines, always a no-op)
  - `CompileProgramMetadata` type and `retryErrors` from ProgramContext
  - `'client-no-memo'` output mode
  - Dead return type (CompileProgramMetadata | null → void)
- **Difficulty:** Medium — focused in compiler package, but requires understanding compilation pipeline to confirm functions are unreachable
- **Why interesting:** A no-op validation pass that was left behind after feature removal. Agent must trace compilation pipeline to confirm `ValidateNoUntransformedReferences` is never invoked.

### Candidate 4: Remove feature flags warnAboutDefaultPropsOnFunctionComponents and warnAboutStringRefs

- **PR:** [#25980](https://github.com/facebook/react/pull/25980) — "[cleanup] remove feature flags warnAboutDefaultPropsOnFunctionComponents and warnAboutStringRefs"
- **Author:** Jan Kassens (2023-01-11)
- **Cleanup commit:** `0fce6bb49835`
- **Parent commit (task start):** `7002a6743ebb24ed55af8f626c89dd39460230fc`
- **Scope:** 20 files, +111 / -225 lines
- **Dead code removed:**
  - Two feature flags across all fork files (8 fork files)
  - Dead warning branches in ReactChildFiber.js, ReactFiberBeginWork.js
  - Dead test assertions for removed warnings
- **Feature flags:** `warnAboutDefaultPropsOnFunctionComponents`, `warnAboutStringRefs` — both permanently enabled
- **Difficulty:** Hard — two flags, cross-package, test file updates needed
- **Why interesting:** Dual feature flag removal — agent must identify both flags and trace all dead branches.

---

## microsoft/TypeScript (1 candidate)

### Candidate 5: Remove unused exports & dead code (using Knip)

- **PR:** [#56817](https://github.com/microsoft/TypeScript/pull/56817) — "Remove unused exports & dead code (using Knip)"
- **Author:** Lars Kappert (2024-06-27)
- **Cleanup commit:** `752135eb4046`
- **Parent commit (task start):** `f7833b2a72309dd695b45cf2cf2187e2f2f264df`
- **Scope:** 45 files, +1238 / -683 lines (excluding CI/tooling additions)
- **Dead code removed:**
  - 112 lines from `core.ts` (unused utility functions)
  - 193 lines from `utilities.ts` (dead helper functions)
  - 44 lines from `factory/utilities.ts`
  - 69 lines from `factory/emitHelpers.ts`
  - 37 lines from `utilitiesPublic.ts`
  - 10 lines from `corePublic.ts`
  - Dead exports across compiler, services, server modules
- **Difficulty:** Expert — massive codebase (900K+ LoC), dead code scattered across compiler internals, requires exhaustive reference search
- **Why interesting:** Systematic dead code removal using Knip tool. Agent must independently discover the same unused exports and functions that Knip found. Tests understanding of TypeScript's internal module structure.

---

## angular/angular (1 candidate)

### Candidate 6: Remove ViewEngine code from language service package

- **PR:** [#44064](https://github.com/angular/angular/pull/44064) — "Remove VE code from language service package"
- **Author:** ivanwonder (2021-11-04)
- **Cleanup commit:** `4738569220b4`
- **Parent commit (task start):** `891318e805da3cdfb9839bf6cb3412c15c146253`
- **Scope:** 99 files, +3612 / -15077 lines
- **Dead code removed:**
  - Entire `ivy/` subdirectory under language-service (merged into `src/`)
  - Dead ViewEngine-specific modules: expression_diagnostics, expression_type, expressions, global_symbols, hover, html_info, locate_symbol, diagnostic_messages
  - Dead binding_utils.ts (69 lines)
  - Removed ViewEngine language service adapter pattern
- **Difficulty:** Expert — 99 files, massive removal, requires understanding Ivy vs ViewEngine architecture
- **Why interesting:** Agent must identify which language service files are ViewEngine-only dead code now that Ivy is the sole compiler. Requires architectural understanding of Angular's rendering pipeline transition.

---

## Selection for Tasks (best 5)

| # | Candidate | Repo | Difficulty | Files | Deletions |
|---|-----------|------|-----------|-------|-----------|
| 1 | Legacy event system dead code | facebook/react | Hard | 38 | 755 |
| 2 | enableRenderableContext flag | facebook/react | Hard | 27 | 292 |
| 3 | Compiler pipeline dead code | facebook/react | Medium | 6 | 198 |
| 4 | Unused exports via Knip | microsoft/TypeScript | Expert | 45 | 683 |
| 5 | ViewEngine language service | angular/angular | Expert | 99 | 15077 |
