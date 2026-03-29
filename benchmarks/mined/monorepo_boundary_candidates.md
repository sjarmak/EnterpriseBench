# Monorepo Package Boundary Candidates

Mined candidates for `monorepo-boundary-*` tasks. Each candidate represents a change
in one monorepo package that triggered semver bumps and/or boundary impacts in sibling packages.

---

## babel/babel (5 candidates)

### Candidate 1: AST Field Traversal Order Fix (v7.25.4)

- **PR:** [#16710](https://github.com/babel/babel/pull/16710) — "Visit AST fields nodes according to their syntactical order"
- **Release:** v7.25.4 (2024-08-22), commit `cbf124ca`
- **Source package:** `@babel/types` — changed AST node field visit order to match source order
- **Dependent packages bumped (21):**
  - `@babel/generator`, `@babel/traverse`, `@babel/parser` (direct AST consumers)
  - `@babel/helper-create-class-features-plugin` (traversal on class nodes)
  - `@babel/plugin-transform-classes`, `@babel/plugin-transform-class-properties`, `@babel/plugin-transform-private-methods`, `@babel/plugin-transform-async-generator-functions`
  - `@babel/plugin-transform-runtime`, `@babel/preset-env`, `@babel/standalone`
  - `@babel/runtime`, `@babel/runtime-corejs2`
- **Semver:** **Patch** — bug fix but affects all visitor traversal order
- **Difficulty:** Medium — single change in types cascading through field ordering contract
- **Why interesting:** `@babel/types` is the single source of truth for AST node shape. Changing field visit order affects `@babel/traverse`'s walk sequence, which in turn affects every transform plugin relying on visitor execution order.

### Candidate 2: Absorb `helper-environment-visitor` into `@babel/traverse` (v7.25.0)

- **PR:** [#16649](https://github.com/babel/babel/pull/16649) — "Move `environment-visitor` helper into `@babel/traverse`"
- **Release:** v7.25.0 (2024-07-26), commit `d2e3ee2c`
- **Source package:** `@babel/helper-environment-visitor` (deprecated/absorbed) → `@babel/traverse`
- **Dependent packages bumped (37):**
  - `@babel/traverse` — received the moved logic
  - `@babel/helper-create-class-features-plugin`, `@babel/helper-remap-async-to-generator`, `@babel/helper-replace-supers`, `@babel/helper-wrap-function`
  - `@babel/plugin-bugfix-firefox-class-in-computed-class-key`, `@babel/plugin-transform-async-generator-functions`, `@babel/plugin-transform-classes`, `@babel/plugin-transform-block-scoping`, `@babel/plugin-transform-function-name`, `@babel/plugin-transform-modules-systemjs`, `@babel/plugin-transform-typescript`
  - `@babel/preset-env`, `@babel/standalone`, and 20+ more
- **Semver:** **Minor** — new API surface on `@babel/traverse`; deprecation of helper
- **Difficulty:** Hard — helper absorption pattern; all importers need dependency declaration updates; cycle elimination motivation
- **Why interesting:** Tests whether an agent can trace import paths from a deprecated helper package to all consumers, and understand the dependency graph restructuring.

### Candidate 3: Enable Import Attributes Parsing by Default (v7.26.0)

- **PR:** [#16850](https://github.com/babel/babel/pull/16850) — "Enable import attributes parsing by default"
- **Release:** v7.26.0 (2024-10-25), commit `63d30381`
- **Source package:** `@babel/parser` — `importAttributes` plugin made always-on (Stage 4)
- **Dependent packages bumped (27):**
  - `@babel/generator` — default print format for import attributes changed
  - `@babel/types` — `ImportAttribute` node definition updated
  - `@babel/core` — plugin resolution path updated
  - `@babel/plugin-syntax-import-assertions`, `@babel/plugin-syntax-import-attributes`
  - `@babel/preset-env`, `@babel/standalone`, `@babel/code-frame`
  - `@babel/helper-module-transforms`, `@babel/plugin-transform-json-modules`
- **Semver:** **Minor** — parser default behavior change
- **Difficulty:** Hard — parser default change flows to generator, types, presets; agent must understand which packages produce/consume `ImportAttribute` AST nodes

### Candidate 4: Formalize `@babel/types` as Dependency of `@babel/parser` (v7.25.3)

- **PR:** [#16688](https://github.com/babel/babel/pull/16688) — "Add `@babel/types` as a dependency of `@babel/parser`"
- **Release:** v7.25.3 (2024-07-31), commit `787c7cd6`
- **Source package:** `@babel/parser` — formalized missing dependency declaration (`.d.ts` files referenced types' types)
- **Dependent packages bumped (5):**
  - `@babel/parser`, `@babel/traverse`, `@babel/plugin-bugfix-firefox-class-in-computed-class-key`
  - `@babel/preset-env`, `@babel/standalone`
- **Semver:** **Patch** — dependency graph fix, no user-facing behavior change
- **Difficulty:** Medium — "formalize what already worked" but lerna's fixed versioning bumps the transitive chain
- **Why interesting:** Shows how a missing dependency declaration causes a cascade when formalized. Tests understanding of `workspace:*` dependency propagation.

### Candidate 5: Mass `@babel/plugin-proposal-*` → `@babel/plugin-transform-*` Rename (v7.22.0)

- **PR:** [#15614](https://github.com/babel/babel/pull/15614) — "Rename `-proposal-`s that became standard to `-transform-`"
- **Release:** v7.22.0 (2023-05-26), commit `389ecb08`
- **Source packages:** 18 `@babel/plugin-proposal-*` packages renamed to `@babel/plugin-transform-*`
- **Dependent packages bumped (53):**
  - `@babel/core` — plugin resolution for old/new names
  - `@babel/preset-env` — all 18 plugin references updated
  - `@babel/standalone` — full rebuild
  - All helpers consumed by renamed plugins
  - Same release also landed import attributes ([#15536](https://github.com/babel/babel/pull/15536)) and `await using` ([#15520](https://github.com/babel/babel/pull/15520))
- **Semver:** **Minor** — new packages created; old ones deprecated as re-exports
- **Difficulty:** Expert — 18 packages renamed, 53 total bumps, multiple interrelated changes in same release
- **Why interesting:** Package rename + deprecation pattern combined with new language features. Agent must differentiate which bumps come from which source change.

---

## pnpm/pnpm (4 candidates)

### Candidate 6: Peer Resolution Fix Cascading Through pkg-manager Stack

- **PR:** [#7583](https://github.com/pnpm/pnpm/pull/7583) — "fix: resolve peer having peer correctly"
- **Release commit:** `211d2acbc6a7` (2024-01-31)
- **Source package:** `@pnpm/resolve-dependencies` — properly resolves peer dependencies of peer dependencies
- **Dependent packages bumped (6):**
  - `@pnpm/core` (13.4.1 → 13.4.2)
  - `@pnpm/plugin-commands-installation` (14.2.1 → 14.2.2)
  - `@pnpm/plugin-commands-script-runners` (8.0.22 → 8.0.23)
  - `@pnpm/plugin-commands-patching` (5.1.2 → 5.1.3)
  - `@pnpm/plugin-commands-deploy` (4.0.21 → 4.0.22)
- **Semver:** **Patch** everywhere — cascade depth 3 hops
- **Difficulty:** Medium (calibration) — clean single-fix, mechanical cascade via `workspace:*`

### Candidate 7: `hoist-workspace-packages` Option Threading Through Install Stack

- **PR:** [#7451](https://github.com/pnpm/pnpm/pull/7451) — "feat: add hoist-workspace-packages option"
- **Release commit:** `7bef886144ef` (v8.14.0 era)
- **Source packages:** `@pnpm/hoist`, `@pnpm/config`
- **Dependent packages bumped:**
  - `@pnpm/config` (20.3.0 → 20.4.0, **minor**)
  - `@pnpm/hoist` (8.1.5 → 8.2.0, **minor**)
  - `@pnpm/headless` (22.3.12 → 22.4.0, **minor**)
  - `@pnpm/core` (13.2.1 → 13.3.0, **minor**)
  - `@pnpm/plugin-commands-installation` (14.0.15 → 14.1.0, **minor**)
  - `@pnpm/fs.is-empty-dir-or-nothing` (0.0.0 → 1.0.0, **major** — initial release)
  - ~20 leaf command plugins (**patch**)
- **Semver:** Minor at feature boundary → minor through install stack → patch at leaves; 4-hop cascade
- **Difficulty:** Hard — new option surface in config forces minor bump in every package that passes through; new-package dependency extraction sub-problem

### Candidate 8: Store Controller Types + CAFS Types API Rename (v8.x)

- **PR:** [#7083](https://github.com/pnpm/pnpm/pull/7083) — "feat: new option for disabling local directory dependencies relinking"
- **Release commit:** `3ed5a7cd4469` (2023-09-13)
- **Source packages:** `@pnpm/store-controller-types`, `@pnpm/cafs-types` — `fromStore` renamed to `resolvedFrom`; `disableRelinkFromStore` replaced with `disableRelinkLocalDirDeps`
- **Dependent packages bumped (major):**
  - `@pnpm/cafs-types` (3.1.0 → 4.0.0), `@pnpm/store-controller-types` (16.1.0 → 17.0.0)
  - `@pnpm/store-connection-manager` (6.2.1 → 7.0.0), `@pnpm/package-store` (18.0.1 → 19.0.0)
  - `@pnpm/server` (16.0.2 → 17.0.0), `@pnpm/create-cafs-store` (5.1.1 → 6.0.0)
  - `@pnpm/fs.indexed-pkg-importer` (4.1.1 → 5.0.0), `@pnpm/package-requester` (23.0.1 → 24.0.0)
  - `@pnpm/tarball-fetcher` (17.0.1 → 18.0.0), `@pnpm/lifecycle` (15.0.9 → 16.0.0)
  - `@pnpm/headless` (22.0.1 → 22.1.0, **minor**), `@pnpm/core` (12.0.1 → 12.1.0, **minor**)
  - ~40 leaf packages (**patch**)
- **Semver:** 10 **major** bumps, 3 **minor**, ~40 **patch** — cascade depth 5 hops
- **Difficulty:** Expert — two interleaved breaking changes across type boundaries; 10 simultaneous major bumps; agent must identify which packages are the true boundary (type definitions) vs downstream consumers

### Candidate 9: Peer Issue Rendering Filter (v8.x)

- **PR:** [#7747](https://github.com/pnpm/pnpm/pull/7747) + commit `7a326142` — "feat: filtering peer dependency issues in the reporter"
- **Release commit:** `3c50981dd260` (2024-03-13)
- **Source packages:** `@pnpm/render-peer-issues` (new filtering API), `@pnpm/run-npm` (Corepack fix, independent)
- **Dependent packages bumped:**
  - `@pnpm/render-peer-issues` (4.0.6 → 4.1.0, **minor**)
  - `@pnpm/default-reporter` (12.4.14 → 12.5.0, **minor**)
  - `@pnpm/cli-utils` (2.1.10 → 2.1.11, **patch**)
  - `@pnpm/plugin-commands-installation` and ~18 other plugin packages (**patch**)
- **Semver:** Minor at reporting boundary → patch wave through ~20 CLI plugins; 2-hop cascade
- **Difficulty:** Medium — two independent changes in same release; tests distinguishing true semantic boundary changes from mechanical transitive bumps

---

## vercel/next.js (3 candidates)

### Candidate 10: Move ImageResponse to `next/og` (v14.0.0)

- **PR:** [#56662](https://github.com/vercel/next.js/pull/56662) — "Move ImageResponse to next/og"
- **Release:** v14.0.0
- **Source package:** `next` — moved `ImageResponse` from `next/server` to `next/og` (bundle size concern)
- **Dependent packages affected:**
  - `@next/swc` (Rust crate `next-core`) — import map updated (`next_import_map.rs`)
  - `next` internal: `webpack-config.ts`, `middleware-plugin.ts`, `taskfile.js`
  - `@next/codemod` ([#57074](https://github.com/vercel/next.js/pull/57074)) — migration tool for import paths
- **Semver:** **Major** (v13 → v14) — breaking API surface change
- **Difficulty:** Medium — clear API move but crosses JS/Rust boundary (next-swc import map) + barrel file re-exports
- **Why interesting:** Requires understanding both JavaScript bundler config AND the Rust-based SWC compiler's import map — cross-language package boundaries.

### Candidate 11: Coordinated 16-Package Version Bump (v14.0.0)

- **PR:** [#57071](https://github.com/vercel/next.js/pull/57071) — "Bump packages version to match canary versions"
- **Release:** v14.0.0
- **Packages bumped (16):**
  - `create-next-app`, `eslint-config-next`, `eslint-plugin-next`, `@next/font`
  - `next-bundle-analyzer`, `@next/codemod`, `@next/env`, `@next/mdx`
  - `@next/plugin-storybook`, `next-polyfill-module`, `next-polyfill-nomodule`
  - `@next/swc`, `next`, `react-dev-overlay`, `react-refresh-utils`, `@next/third-parties`
- **Semver:** **Major** (all to v14.0.0) — lockstep versioning
- **Difficulty:** Medium — understanding which packages are public vs internal, which need independent vs lockstep versioning

### Candidate 12: Drop Node.js 16 + Remove Experimental `serverActions` Flag (v14.0.0)

- **PR:** [#56896](https://github.com/vercel/next.js/pull/56896) (drop Node 16), [#57145](https://github.com/vercel/next.js/pull/57145) (remove serverActions flag)
- **Release:** v14.0.0
- **Source package:** `next` — engines field change + API removal
- **Dependent packages affected:**
  - `create-next-app` — Node.js engine requirement
  - `eslint-config-next` — peer dependency on `next`
  - `@next/env` — Node.js compatibility
  - `@next/swc` — native binary compatibility matrix
- **Semver:** **Major** (v14.0.0) — engine requirement is breaking
- **Difficulty:** Medium — engine field change propagation through peer dependencies

---

## rust-lang/rust workspace (3 candidates)

### Candidate 13: Remove `Nonterminal` and `TokenKind::Interpolated` from `rustc_ast`

- **PR:** [#124141](https://github.com/rust-lang/rust/pull/124141) — "Remove `Nonterminal` and `TokenKind::Interpolated`"
- **Merged:** 2025-04-14, commit `f836ae4e`
- **Source crate:** `rustc_ast` — removed `Nonterminal` enum and `TokenKind::Interpolated` variant (legacy macro expansion mechanism)
- **Dependent crates affected (31):**
  - Direct AST consumers: `rustc_parse`, `rustc_expand`, `rustc_ast_lowering`, `rustc_ast_pretty`, `rustc_builtin_macros`
  - Mid-layer: `rustc_middle`, `rustc_metadata`, `rustc_incremental`, `rustc_query_impl`
  - Analysis: `rustc_hir`, `rustc_hir_analysis`, `rustc_hir_typeck`, `rustc_borrowck`, `rustc_lint`, `rustc_resolve`, `rustc_passes`, `rustc_privacy`
  - Codegen: `rustc_codegen_ssa`, `rustc_mir_build`, `rustc_mir_transform`, `rustc_symbol_mangling`, `rustc_monomorphize`
  - Tooling: `rustc_smir`, `rustc_transmute`, `rustc_sanitizers`
- **Semver equivalent:** **Major** — enum variant removal; third attempt (previous: #96724, #114647)
- **Difficulty:** Expert — 31 crates affected; every crate matching on `TokenKind` needs updating; labeled `relnotes` and `perf-regression`
- **Why interesting:** Agent must trace all downstream consumers of `TokenKind::Interpolated` across the workspace and understand which match arms need new handling.

### Candidate 14: Replace `Vec<T>` with `ThinVec<T>` in AST Node Types

- **PR:** [#104754](https://github.com/rust-lang/rust/pull/104754) — "Use `ThinVec` more in the AST"
- **Merged:** 2023-02-21, commit `3fee48c1`
- **Source crate:** `rustc_ast` — replaced `Vec<T>` fields in expressions, items, patterns, generics with `ThinVec<T>`; `rustc_data_structures` re-exports
- **Dependent crates affected (16):**
  - Direct: `rustc_parse`, `rustc_ast_lowering`, `rustc_ast_passes`, `rustc_ast_pretty`, `rustc_expand`, `rustc_builtin_macros`
  - Mid-layer: `rustc_middle`, `rustc_resolve`, `rustc_hir_analysis`, `rustc_incremental`
  - Infrastructure: `rustc_data_structures`, `rustc_query_impl`, `rustc_query_system`, `rustc_serialize`
  - Plus `librustdoc`
- **Semver equivalent:** **Minor** (API-compatible but Cargo.toml edits in 16 crates for `thin-vec` dependency); 77 files modified
- **Difficulty:** Hard — agent must identify all crates that construct/destructure specific AST nodes (not just importers), plus determine which crates need `thin-vec` in Cargo.toml

### Candidate 15: Represent Trait Constness as Distinct Predicate

- **PR:** [#131985](https://github.com/rust-lang/rust/pull/131985) — "Represent trait constness as a distinct predicate"
- **Merged:** 2024-10-24, commit `1d4a7670`
- **Source crate:** `rustc_middle` / `rustc_type_ir` — new `HostEffectPredicate` replacing old `~const` HOST effect desugaring; removed `EffectVar` inference variable kind
- **Dependent crates affected (20):**
  - Type system: `rustc_type_ir`, `rustc_infer`, `rustc_trait_selection`, `rustc_traits`, `rustc_next_trait_solver`
  - HIR: `rustc_hir`, `rustc_hir_analysis`, `rustc_hir_typeck`, `rustc_hir_pretty`, `rustc_ast_lowering`
  - Query/storage: `rustc_metadata`, `rustc_monomorphize`
  - Tooling: `rustc_smir`, `rustc_lint`, `rustc_privacy`
  - Feature gating: `rustc_feature`, `rustc_span`
- **Semver equivalent:** **Major** — 100 files modified; removes old desugaring infrastructure entirely
- **Difficulty:** Expert — spans full compiler pipeline (lowering → type collection → trait selection → codegen); requires understanding both data-flow and control-flow directions

---

## Summary

| # | Repo | PR(s) | Source Package | Affected Pkgs | Semver | Difficulty |
|---|------|-------|----------------|---------------|--------|------------|
| 1 | babel/babel | #16710 | @babel/types | 21 | patch | medium |
| 2 | babel/babel | #16649 | helper-environment-visitor → traverse | 37 | minor | hard |
| 3 | babel/babel | #16850 | @babel/parser | 27 | minor | hard |
| 4 | babel/babel | #16688 | @babel/parser | 5 | patch | medium |
| 5 | babel/babel | #15614 | 18 proposal→transform plugins | 53 | minor | expert |
| 6 | pnpm/pnpm | #7583 | @pnpm/resolve-dependencies | 6 | patch | medium |
| 7 | pnpm/pnpm | #7451 | @pnpm/hoist, @pnpm/config | ~25 | minor→patch | hard |
| 8 | pnpm/pnpm | #7083 | store-controller-types, cafs-types | ~50 | major→minor→patch | expert |
| 9 | pnpm/pnpm | #7747 | @pnpm/render-peer-issues | ~20 | minor→patch | medium |
| 10 | vercel/next.js | #56662 | next | 3 | major | medium |
| 11 | vercel/next.js | #57071 | all | 16 | major | medium |
| 12 | vercel/next.js | #56896+#57145 | next | 4 | major | medium |
| 13 | rust-lang/rust | #124141 | rustc_ast | 31 | major-equiv | expert |
| 14 | rust-lang/rust | #104754 | rustc_ast | 16 | minor-equiv | hard |
| 15 | rust-lang/rust | #131985 | rustc_middle/rustc_type_ir | 20 | major-equiv | expert |

**Coverage:** 4 monorepos, 15 candidates
**Difficulty mix:** 5 medium (33%), 5 hard (33%), 5 expert (33%)
**Semver mix:** patch (3), minor (5), major (7)
