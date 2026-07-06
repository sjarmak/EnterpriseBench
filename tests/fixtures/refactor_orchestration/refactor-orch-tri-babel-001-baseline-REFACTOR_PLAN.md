# Refactor Execution Plan: DecoratorMetadata AST Node Propagation

## Overview

Propagating Babel's new `DecoratorMetadata` AST node (stage 3 decorators) through the JS
build pipeline requires updating three repos in strict dependency order. Babel is the
source of truth; webpack consumes Babel via `babel-loader`; Next.js configures both.

---

## 1. Execution Order (Topologically Sorted)

```
Step 1: babel       (no upstream deps in this pipeline)
Step 2: webpack     (depends on: babel)
Step 3: nextjs      (depends on: babel, webpack)
```

---

## 2. Dependency Graph

```
babel (parser/compiler)
│
│  exports: DecoratorMetadata AST node via @babel/types
│           parsing via @babel/parser
│           transformation via @babel/plugin-proposal-decorators
│           @babel/helper-create-class-features-plugin
│
├──▶ webpack (bundler)
│       consumes babel via: babel-loader ^8.1.0 (devDep)
│       consumes @babel/core: ^7.21.4 (peerDep)
│       internal parser: Acorn (independent of Babel parser)
│       tree-shaking: SideEffectsFlagPlugin, HarmonyImportSideEffectDependency
│       decorator runtime: ModuleDecoratorDependency (HMD/NMD runtime globals)
│       affected files:
│         lib/dependencies/ModuleDecoratorDependency.js
│         lib/optimize/SideEffectsFlagPlugin.js
│         lib/dependencies/HarmonyImportSideEffectDependency.js
│         lib/javascript/JavascriptParser.js
│
└──▶ nextjs (framework)
        consumes babel via:
          @babel/core 7.18.0 (devDep)
          @babel/parser 7.12.11 (devDep)
          @babel/plugin-proposal-decorators (devDep)
          packages/next/src/build/babel/preset.ts
          packages/next/src/build/babel/loader/
        consumes webpack: 5.86.0 (dep)
        consumes SWC via:
          @swc/core 1.3.55
          packages/next/src/build/swc/options.ts
          packages/next-swc/crates/next-core/src/transform_options.rs
        decorator config:
          jsConfig.compilerOptions.experimentalDecorators → legacyDecorator
          jsConfig.compilerOptions.emitDecoratorMetadata  → decoratorMetadata
        SWC/Babel selection:
          packages/next/src/build/webpack-config.ts (lines 813-838)
```

---

## 3. Step-by-Step Execution Plan

### Step 1 — Babel (Source of Change)

**Must complete before:** Step 2, Step 3

#### 1a. Add `DecoratorMetadata` AST node definition (BREAKING within Babel internals)
- **File**: `packages/babel-types/src/definitions/experimental.ts`
- **Action**: Define new `DecoratorMetadata` node type alongside existing `Decorator`
- **Parallel with**: 1b, 1c

#### 1b. Implement `DecoratorMetadata` parsing in the parser (BREAKING — new AST shape)
- **Files**:
  - `packages/babel-parser/src/parser/statement.ts` — `parseDecorators()`, `parseDecorator()`
  - `packages/babel-parser/src/parser/expression.ts` — class expression decorator handling
- **Action**: Emit `DecoratorMetadata` node when parsing stage 3 decorator expressions
- **Parallel with**: 1a, 1c

#### 1c. Update `babel-plugin-proposal-decorators` transform (COMPATIBLE — additive)
- **Files**:
  - `packages/babel-plugin-proposal-decorators/src/index.ts`
  - `packages/babel-helper-create-class-features-plugin/src/decorators.ts`
- **Action**: Handle `DecoratorMetadata` node in transformer; update `hasOwnDecorators()`,
  `extractElementDescriptor()` to read metadata from the new node
- **Parallel with**: 1a, 1b (after 1b lands, integration tests run)

#### 1d. Update `babel-plugin-syntax-decorators` (COMPATIBLE — additive)
- **File**: `packages/babel-plugin-syntax-decorators/`
- **Action**: Expose `DecoratorMetadata` in the syntax plugin manifest so downstream
  tools that only enable the syntax plugin still see the new node
- **Depends on**: 1b

#### 1e. Publish new `@babel/parser`, `@babel/types`, `@babel/plugin-proposal-decorators`
- Minimum versions required downstream: must be pinned in webpack and nextjs updates

---

### Step 2 — webpack (Intermediary — depends on Step 1)

**Must complete before:** Step 3

#### 2a. Update `babel-loader` / `@babel/core` version pin (COMPATIBLE)
- **File**: `package.json` (devDependencies: babel-loader, @babel/core)
- **Action**: Bump to versions that include `DecoratorMetadata` node support
- **Parallel with**: 2b

#### 2b. Update tree-shaking side-effects analysis for `DecoratorMetadata` (BREAKING)
- **Files**:
  - `lib/optimize/SideEffectsFlagPlugin.js` — add `DecoratorMetadata` as a node type
    that implies side effects (decorators mutate class metadata at load time)
  - `lib/dependencies/HarmonyImportSideEffectDependency.js` — `getCondition()` /
    `getSideEffectsConnectionState()` must treat modules with `DecoratorMetadata` nodes
    as having side effects unless the package.json `sideEffects` field explicitly opts out
  - `lib/javascript/JavascriptParser.js` — Acorn-based parsing does not emit Babel AST
    nodes directly, but the loader output (transpiled by babel-loader) must be
    re-analyzed; any decorator-helper-import patterns emitted by
    `@babel/plugin-proposal-decorators` must be recognized as side-effectful
- **Parallel with**: 2a

#### 2c. Update `ModuleDecoratorDependency` runtime behavior (COMPATIBLE)
- **File**: `lib/dependencies/ModuleDecoratorDependency.js`
- **Action**: Ensure HMD/NMD runtime wrapping (`RuntimeGlobals.harmonyModuleDecorator`,
  `RuntimeGlobals.nodeModuleDecorator`) is preserved for decorated modules; the new AST
  node should not accidentally suppress the init-fragment injection
- **Depends on**: 2b

---

### Step 3 — Next.js (Consumer — depends on Steps 1 & 2)

#### 3a. Bump `@babel/core`, `@babel/parser`, `@babel/plugin-proposal-decorators` (COMPATIBLE)
- **Files**: `package.json` (root), `packages/next/package.json`
- **Action**: Pin to versions from Step 1e; verify no preset conflicts
- **Parallel with**: 3b

#### 3b. Update SWC decorator options for `DecoratorMetadata` (BREAKING)
- **Files**:
  - `packages/next/src/build/swc/options.ts` (lines 65–103)
    - Add new option for `decoratorMetadata` to pass `DecoratorMetadata` node awareness
      to SWC's `@swc/core` transform (once `@swc/core` adds support)
  - `packages/next-swc/crates/next-core/src/transform_options.rs` (lines 67–123)
    - Add `DecoratorsKind::Stage3WithMetadata` variant (or extend `Ecma` variant) to
      handle the new AST shape from Babel when SWC processes the same source
- **Parallel with**: 3a

#### 3c. Update Babel preset in Next.js (COMPATIBLE)
- **File**: `packages/next/src/build/babel/preset.ts`
- **Action**: Ensure `@babel/plugin-proposal-decorators` is pinned to the new version;
  confirm preset version string (e.g. `"2023-05"`) matches what emits `DecoratorMetadata`
- **Depends on**: 3a

#### 3d. Update `jsconfig`/`tsconfig` loading for new decorator flag (COMPATIBLE)
- **File**: `packages/next/src/build/load-jsconfig.ts`
- **Action**: If the new stage 3 decorator spec introduces a new `compilerOptions` key
  (e.g. `"decoratorMetadata": true` separate from `emitDecoratorMetadata`), add it to
  the config reader and pipe it through to both SWC (`options.ts`) and Babel (preset.ts)
- **Depends on**: 3b, 3c

#### 3e. Verify SWC vs Babel path selection (COMPATIBLE — no change expected)
- **File**: `packages/next/src/build/webpack-config.ts` (lines 813–838)
- **Action**: Confirm that the `useSWCLoader` decision logic is unaffected; if a project
  has a custom `.babelrc` with `@babel/plugin-proposal-decorators`, it will use Babel and
  must pick up the new version; if no `.babelrc`, SWC handles decorators and the Rust
  transform must be updated (3b)

---

## 4. Parallelization Annotations

```
TIME ──────────────────────────────────────────────────────────────►

[Step 1 — Babel]
  1a ──────────────────────────────────────────────────┐
  1b ─────────────────────────────────────────────────►├─► 1d ─► 1e
  1c ──────────────────────────────────────────────────┘

                    [Step 2 — webpack]  (starts after 1e)
                      2a ─────────────────────────────┐
                      2b ─────────────────────────────►├─► 2c
                                                       

                              [Step 3 — Next.js]  (starts after 2c)
                                3a ──────────────────────────────┐
                                3b ──────────────────────────────►├─► 3d ─► 3e
                                3c ──────────────────────────────┘
```

- **1a, 1b, 1c** can run in parallel (different packages in the Babel monorepo)
- **1d** depends on 1b (needs stable node shape)
- **2a, 2b** can run in parallel (different concerns — version pin vs. analysis logic)
- **2c** depends on 2b (needs updated side-effects contract)
- **3a, 3b, 3c** can run in parallel (different configs/runtimes)
- **3d** depends on 3b and 3c (needs stable option names from both paths)
- **3e** is a verification step, no code changes expected

---

## 5. Breaking vs. Compatible Change Annotations

| Step | Change | Classification | Reason |
|------|--------|---------------|--------|
| 1a | Add `DecoratorMetadata` node type | **BREAKING** (major semver) | New AST node changes the tree shape; any visitor that does a `node.type` exhaustive switch will hit an unhandled case |
| 1b | Emit `DecoratorMetadata` from parser | **BREAKING** | Old consumers that walk the AST will encounter the new node; codegen for `DecoratorMetadata` must be added to `babel-generator` |
| 1c | Update proposal-decorators transformer | Compatible (additive) | New code path alongside existing; gated by decorator version string |
| 1d | Update syntax-decorators manifest | Compatible (additive) | Purely declarative addition |
| 1e | Publish new package versions | Breaking (semver bump required) | Downstream must explicitly upgrade |
| 2a | Bump babel-loader / @babel/core | Compatible | Version pin change; no API break |
| 2b | Side-effects analysis for decorators | **BREAKING** | Modules that were previously tree-shaken may now be retained; changes bundle output |
| 2c | ModuleDecoratorDependency update | Compatible | Defensive guard; does not change existing behavior |
| 3a | Bump @babel deps in Next.js | Compatible | Version pin; preset compatibility checked in 3c |
| 3b | SWC decorator options / Rust transform | **BREAKING** | New `DecoratorsKind` variant required in `@swc/core`; Rust crate must be updated |
| 3c | Update Babel preset version string | Compatible | Additive; existing decorator version strings still supported |
| 3d | jsconfig new decorator flag | Compatible | Additive; defaults preserve existing behavior |
| 3e | Verify SWC/Babel selection | Compatible | No code change expected |

---

## 6. Risk Assessment

### Step 1 — Babel

| Risk | Severity | Mitigation |
|------|----------|-----------|
| New `DecoratorMetadata` node breaks existing AST visitors in plugins | HIGH | Add exhaustive test suite in `babel-parser` with fixture snapshots; run existing plugin test suite with updated parser |
| `babel-generator` missing codegen for new node type causes generation errors | HIGH | Add `DecoratorMetadata` printer to `babel-generator` before releasing; add round-trip parse→generate tests |
| Plugin ecosystem (non-Babel plugins) breaks on unknown node type | MEDIUM | Node type is emitted only when `decorators` plugin version `"stage3"` is explicitly requested; existing projects using `"legacy"` or `"2023-05"` are unaffected unless they opt in |
| Performance regression in parser hot path | LOW | Profile `parseDecorator()` before/after; decorator parsing is not on the critical path for most files |

### Step 2 — webpack

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Side-effects analysis change incorrectly retains dead code | HIGH | Compare bundle sizes with existing snapshot tests; run `test/cases/side-effects/` suite |
| Side-effects analysis change incorrectly drops live decorator code | CRITICAL | Decorated modules must be explicitly tested; add test case where `DecoratorMetadata` node is present and the module must be retained |
| babel-loader version mismatch causes silent parsing errors | MEDIUM | Pin exact `@babel/core` version in `package.json`; add integration test that verifies decorated files parse correctly end-to-end |
| `ModuleDecoratorDependency` (HMD/NMD) interacts unexpectedly with new node | LOW | Existing runtime tests cover HMD/NMD; add a test with a class using stage 3 decorators |

### Step 3 — Next.js

| Risk | Severity | Mitigation |
|------|----------|-----------|
| SWC and Babel produce different output for same decorated source | CRITICAL | Add integration test that runs the same source through both paths and validates runtime behavior is identical |
| `@swc/core` Rust crate not yet updated when Next.js bumps (timing dependency) | HIGH | Gate 3b on confirmed `@swc/core` release that supports `DecoratorMetadata`; use `forceSwcTransforms: false` as temporary fallback |
| `emitDecoratorMetadata` / new metadata flag naming collision with TypeScript | MEDIUM | Audit `load-jsconfig.ts` to distinguish old `emitDecoratorMetadata` (legacy) from new `DecoratorMetadata` node flag; add deprecation notice |
| Users with custom `.babelrc` get old Babel version (no auto-upgrade) | MEDIUM | Add warning in Next.js build output when `@babel/plugin-proposal-decorators` version is below the minimum required |
| Breaking change in webpack side-effects (Step 2b) causes Next.js bundles to grow | LOW | Monitor bundle size in Next.js CI; add size limit check for a representative decorated page |

---

## 7. Summary

The refactor touches three layers and must be executed in strict order: Babel first,
webpack second, Next.js last. Within each layer several sub-tasks are parallelizable.
The two highest-risk transitions are:

1. **Babel 1a/1b** — the new AST node is a breaking change for the entire plugin ecosystem
2. **Next.js 3b** — the Rust-level SWC transform must be updated in lockstep with the
   new Babel output; a timing mismatch between `@swc/core` and `next-swc` releases is
   the most likely source of a production regression.
