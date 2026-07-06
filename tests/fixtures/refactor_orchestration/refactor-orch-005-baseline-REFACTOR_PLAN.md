# Babel 8 Plugin Removal Refactor Plan

## Overview

This plan covers the topologically ordered removal of four deprecated Babel plugins
as part of the Babel 8 migration:

- `@babel/plugin-transform-react-jsx-compat` (PR #17620)
- `@babel/plugin-transform-react-jsx-source` (PR #17620)
- `@babel/plugin-transform-react-jsx-self` (PR #17620)
- `@babel/plugin-transform-property-mutators` (PR #17882)

Plus the related removal of `isPluginRequired` from `@babel/preset-env` (PR #17670).

---

## Internal Dependency Graph

```
@babel/helper-builder-react-jsx
  └── @babel/plugin-transform-react-jsx-compat   [leaf; only consumer of helper-builder-react-jsx]

@babel/helper-plugin-utils
  ├── @babel/plugin-transform-react-jsx-compat   (runtime dep)
  ├── @babel/plugin-transform-react-jsx-source   (runtime dep)
  ├── @babel/plugin-transform-react-jsx-self     (runtime dep)
  └── @babel/plugin-transform-property-mutators  (runtime dep)

@babel/preset-react
  ├── @babel/plugin-transform-react-jsx
  ├── @babel/plugin-transform-react-jsx-development
  ├── @babel/plugin-transform-react-display-name
  └── @babel/plugin-transform-react-pure-annotations
  NOTE: does NOT directly depend on -compat, -source, or -self

@babel/preset-env
  ├── @babel/plugin-transform-property-literals  (retained)
  └── (all other transforms — NOT property-mutators)
  NOTE: property-mutators is NOT in preset-env's package.json or available-plugins.ts
  NOTE: isPluginRequired is exported from src/index.ts (marked TODO: Remove in Babel 8)

@babel/standalone  [devDependencies — the only monorepo consumer]
  ├── @babel/plugin-transform-property-mutators
  ├── @babel/plugin-transform-react-jsx-compat
  ├── @babel/plugin-transform-react-jsx-self
  ├── @babel/plugin-transform-react-jsx-source
  ├── @babel/preset-env
  └── @babel/preset-react
```

### Inter-plugin Dependencies (among the four removed plugins)

None. The four plugins are fully independent of each other.

### Diamond Dependency Structure

The "diamond" referenced in the task description is a user-facing concern rather
than a strict package.json constraint:

```
user config
    ├── @babel/preset-react  (includes react-jsx-development, which errors if
    │                          react-jsx-source or react-jsx-self are also present)
    └── @babel/preset-env    (historically included property-mutators; in v7.25.0
                               it is no longer in available-plugins.ts or compat-data)

Both presets converge in @babel/standalone (the only monorepo bundler).
```

---

## Topologically Sorted Execution Plan

The four plugins have no mutual dependencies, so the primary constraint is:

> **Leaf packages first → then aggregators (standalone, presets).**

### Step 1 — Remove Leaf Plugin Packages (Parallel Group A)

These three removals from PR #17620 are fully independent and can be executed in
parallel:

| # | Package | PR | Notes |
|---|---------|-----|-------|
| 1a | `@babel/plugin-transform-react-jsx-source` | #17620 | No dependents outside standalone |
| 1b | `@babel/plugin-transform-react-jsx-self`   | #17620 | No dependents outside standalone |
| 1c | `@babel/plugin-transform-react-jsx-compat` | #17620 | Also removes `@babel/helper-builder-react-jsx` if no other consumers remain |

### Step 2 — Remove Property Mutators Plugin (Parallel Group B, concurrent with Group A)

| # | Package | PR | Notes |
|---|---------|-----|-------|
| 2  | `@babel/plugin-transform-property-mutators` | #17882 | Standalone removal; no monorepo deps except helper-plugin-utils (retained) |

Group B can run fully in parallel with Group A since there is no dependency
between the react plugins and property-mutators.

### Step 3 — Remove isPluginRequired from preset-env (PR #17670)

| # | Package | PR | Notes |
|---|---------|-----|-------|
| 3  | `@babel/preset-env` | #17670 | Remove `export function isPluginRequired` from src/index.ts; it is a compatibility shim wrapping `isRequired` from @babel/helper-compilation-targets |

This step is independent of Steps 1/2 at the code level but should be sequenced
after them in release ordering to avoid external consumers seeing `isPluginRequired`
removed while still relying on the deprecated plugins.

### Step 4 — Update @babel/standalone

| # | Package | Notes |
|---|---------|-------|
| 4  | `@babel/standalone` | Remove imports from `src/generated/plugins.ts`; remove entries from `scripts/pluginConfig.json`; remove devDependencies from `package.json` |

This must come last because standalone explicitly imports all four plugins.

### Step 5 — Update @babel/preset-react (if needed)

`@babel/preset-react` does **not** currently depend on the removed plugins in its
`package.json` or `src/index.ts`. However, its development-mode plugin
(`@babel/plugin-transform-react-jsx-development`) emits an error if `-source` or
`-self` are present in the same Babel config, acting as a soft guard. After removal
of `-source`/`-self`, verify that the error-message text and test fixtures in
`babel-plugin-transform-react-jsx-development` are updated to remove references to
the deprecated plugins.

---

## Parallelization Annotations

```
Timeline (→ = can start after previous group completes):

  t=0  ┌─ [A] Remove react-jsx-source  ──────────────────┐
       ├─ [A] Remove react-jsx-self    ──────────────────┤ → [4] Update standalone
       ├─ [A] Remove react-jsx-compat  ──────────────────┤
       └─ [B] Remove property-mutators ──────────────────┘
              ↓ (independent, can start any time)
  t=?  └─ [3] Remove isPluginRequired from preset-env ────┘ (logically after A+B)

  Final: [4] standalone update, [5] preset-react fixture cleanup
```

**Fully parallel (no ordering constraint between them):**
- 1a, 1b, 1c, 2 — all four plugin removals

**Must follow all plugin removals:**
- 4 (standalone) — depends on plugins being removed from the monorepo first so
  generated plugin registry and devDependencies can be cleaned atomically.

**Independent but best sequenced after A+B in release:**
- 3 (isPluginRequired removal from preset-env)

---

## Breaking Change Impact Per Package

### `@babel/plugin-transform-react-jsx-compat`
- **Breaking:** Package deleted; users who configure this plugin directly will get
  a "Cannot find module" error at build time.
- **Migration:** No modern equivalent. This plugin targeted React < 0.12 JSX
  syntax (pre-namespace transforms). Users should upgrade to modern React and use
  `@babel/plugin-transform-react-jsx`.
- **Secondary impact:** `@babel/helper-builder-react-jsx` may be fully orphaned
  if no other packages depend on it — audit required.

### `@babel/plugin-transform-react-jsx-source`
- **Breaking:** Package deleted; users who include this plugin in `.babelrc` will
  get a module-not-found error.
- **Migration:** Use `@babel/plugin-transform-react-jsx-development` (automatic
  runtime) or `@babel/preset-react` with `{ development: true }`. The development
  plugin already injects `__source` automatically and will throw a clear error if
  this removed plugin is also present.
- **Secondary impact:** Test fixtures in `babel-plugin-transform-react-jsx-development`
  reference this plugin in error-message assertions — those must be cleaned up.

### `@babel/plugin-transform-react-jsx-self`
- **Breaking:** Package deleted; same module-not-found failure for direct users.
- **Migration:** Same as `-source`: use the development plugin/preset.
- **Secondary impact:** Same test-fixture cleanup in
  `babel-plugin-transform-react-jsx-development`.

### `@babel/plugin-transform-property-mutators`
- **Breaking:** Package deleted. Users who relied on this plugin to compile
  ES5 `get`/`set` shorthand object methods to `Object.defineProperties` calls will
  receive a module-not-found error.
- **Migration:** All modern JS engines (ES2015+) support getter/setter syntax
  natively. Remove the plugin from configs targeting ES2015+ environments. For
  legacy targets, inline the `Object.defineProperties` calls manually or keep the
  old plugin version pinned.
- **Secondary impact:** `@babel/standalone` loses the `transform-property-mutators`
  entry from its plugin registry — users of the browser-side `Babel.transform` API
  who pass this plugin name will get an "unknown plugin" error.

### `@babel/preset-env` (isPluginRequired removal, PR #17670)
- **Breaking:** The named export `isPluginRequired` is removed. Any tool that
  imports it directly from `@babel/preset-env` will fail at runtime.
- **Migration:** Use `isRequired` from `@babel/helper-compilation-targets` directly.
- **Note:** The function is already marked `// TODO: Remove in Babel 8` in
  `src/index.ts:43`.

### `@babel/standalone`
- **Non-breaking for standalone consumers at runtime** (all plugin references are
  purged from the bundle during its build step), but consumers who pass
  `"transform-property-mutators"`, `"transform-react-jsx-compat"`,
  `"transform-react-jsx-self"`, or `"transform-react-jsx-source"` as plugin names
  to `Babel.transform` or `Babel.registerPlugin` will get unknown-plugin errors
  after the regenerated bundle is published.

---

## Files to Modify (summary)

| File | Change |
|------|--------|
| `packages/babel-plugin-transform-react-jsx-compat/` | Delete entire package |
| `packages/babel-plugin-transform-react-jsx-source/` | Delete entire package |
| `packages/babel-plugin-transform-react-jsx-self/` | Delete entire package |
| `packages/babel-plugin-transform-property-mutators/` | Delete entire package |
| `packages/babel-standalone/package.json` | Remove 4 devDependencies |
| `packages/babel-standalone/src/generated/plugins.ts` | Remove 4 imports + 4 registry entries |
| `packages/babel-standalone/scripts/pluginConfig.json` | Remove 4 plugin name entries |
| `packages/babel-preset-env/src/index.ts` | Remove `isPluginRequired` export (lines 43–47) |
| `packages/babel-plugin-transform-react-jsx-development/test/fixtures/cross-platform/source-and-self-defined/` | Update or remove fixture |
| `packages/babel-plugin-transform-react-jsx-development/test/fixtures/cross-platform/disallow-__source-as-jsx-attribute/` | Update error message if needed |
| `packages/babel-plugin-transform-react-jsx-development/test/fixtures/cross-platform/disallow-__self-as-jsx-attribute/` | Update error message if needed |
| `tsconfig.json` (root) | Remove path references for 4 packages |
| `tsconfig.paths.json` (root) | Remove path alias entries for 4 packages |
| `yarn.lock` | Re-run `yarn` to purge workspace entries |
