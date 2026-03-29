# Impact Analysis: Decorator Metadata + TS Tuple Label Changes for v7.23.0

## Context

We have two features converging in the v7.23.0 release:

1. **Decorator metadata** — adds `Symbol.metadata` support to the decorator implementation. The core change is in `@babel/helper-create-class-features-plugin`, with a new helper (`applyDecs2305`) and updated decorator transformer.

2. **TS tuple label relaxation** — TypeScript now allows tuples with a mix of labeled and unlabeled elements (previously all-or-nothing). The grammar change is in `@babel/parser`'s TypeScript plugin.

These are independent features, but they're both landing in the same minor release. I need a combined impact analysis.

## What I Need

1. **Affected packages**: Which packages are affected by change (1), which by change (2), and are any hit by both?

2. **Impact classification**: Per package — none/patch/minor/major. Both changes are additive features, so I'd expect minor bumps, but verify.

3. **Boundary violations**: The specific files where these features cross package boundaries. For decorator metadata: trace the helper → plugin → preset chain. For tuple labels: trace the parser → types chain.

## Output

Write findings to `/workspace/babel/IMPACT_REPORT.md`.
