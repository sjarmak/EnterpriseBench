# Impact Report: Babel v7.23.0 Changes

## Affected Packages

### @babel/helpers
- **Impact**: Minor
- The `applyDecs2305` helper was added to support decorator metadata.
- File: `packages/babel-helpers/src/helpers/applyDecs2305.js`

### @babel/plugin-proposal-decorators
- Likely affected but could not fully trace the dependency chain from the helpers package.

## Change Classification

The decorator metadata change is classified as a **minor** version bump since it adds new functionality without breaking existing APIs.

## Boundary Notes

The `applyDecs2305.js` helper is imported by the decorators plugin transformer, crossing the package boundary between `babel-helpers` and `babel-plugin-proposal-decorators`.

Could not fully trace the TypeScript tuple label change impact.
