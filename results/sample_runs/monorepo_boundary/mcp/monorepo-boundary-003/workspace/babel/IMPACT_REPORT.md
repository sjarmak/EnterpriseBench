# Impact Report: Babel v7.23.0 — Decorator Metadata + TS Tuple Labels

## Summary

Two features landing in babel v7.23.0 affect three sibling packages across package boundaries:

1. **Decorator metadata support** — changes in `@babel/helper-create-class-features-plugin` propagate to `@babel/helpers` and `@babel/plugin-proposal-decorators`
2. **TypeScript tuple label relaxation** — changes in `@babel/types` propagate to `@babel/parser`

## Affected Packages

### 1. @babel/helpers — Minor
- New `applyDecs2305` helper added for decorator metadata
- `packages/babel-helpers/src/helpers/applyDecs2305.js` — new helper implementation
- `packages/babel-helpers/src/helpers-generated.ts` — helper registry updated

### 2. @babel/plugin-proposal-decorators — Minor
- Decorator transformer updated to emit metadata using the new helper
- `packages/babel-plugin-proposal-decorators/src/transformer-2023-05.ts` — metadata support added
- New test fixtures: `test/fixtures/metadata/class/exec.js`, `test/fixtures/metadata/element/exec.js`

### 3. @babel/parser — Minor
- Parser updated to allow mixed labeled/unlabeled TS tuple elements (PR #15896)
- `packages/babel-parser/src/plugins/typescript/index.ts` — tuple parsing logic relaxed

## Impact Classification

| Package | Semver Bump | Rationale |
|---------|-------------|-----------|
| @babel/helpers | minor | New helper added (no breaking changes) |
| @babel/plugin-proposal-decorators | minor | New decorator metadata feature |
| @babel/parser | minor | Relaxed TS tuple restriction (additive) |

Overall release classification: **minor**

## Boundary Violations

Three files represent cross-package boundary crossings:

1. **`applyDecs2305.js`** — Helper defined in `babel-helpers`, consumed by `babel-plugin-proposal-decorators` transformer
2. **`transformer-2023-05.ts`** — Decorator transformer in `plugin-proposal-decorators` imports helpers from `babel-helpers`
3. **`typescript/index.ts`** — Parser plugin in `babel-parser` affected by `@babel/types` tuple type changes

## References
- PR #15895: Decorator metadata support
- PR #15896: Allow TS tuples with mixed labeled/unlabeled elements
