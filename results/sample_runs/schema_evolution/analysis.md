# DB Schema Evolution -- Sample Run Analysis

## Overview

Sample run for schema-evolution-005 (Discourse ReviewableClaimedTopic automatic boolean, expert difficulty, large_single) across 2 modes (baseline, MCP-augmented).

## Results Summary

| Task | Mode | Schema Change (0.10) | Direct Refs (0.35) | Indirect Refs (0.35) | Test Impact (0.20) | Total |
|------|------|---------------------|--------------------|--------------------|-------------------|-------|
| schema-evolution-005 | baseline | 1.00 | 0.75 | 0.17 | 0.40 | **0.50** |
| schema-evolution-005 | MCP | 1.00 | 1.00 | 1.00 | 1.00 | **1.00** |

## Key Observations

1. **Strong discrimination**: 0.50 gap between baseline and MCP -- the largest gap across all Batch 2 task types. Schema evolution tasks require tracing a single column change through multiple architectural layers (models, serializers, authorization, frontend, tests), which is exactly the kind of cross-layer navigation that benefits from semantic code search.

2. **Indirect refs is the primary discriminator**: Baseline scored 0.17 (1/6) on indirect references. It found the main serializer but missed the other two serializers, the guardian authorization layer, the frontend components, and the locale strings. The Discourse codebase (600K LOC) has deeply nested paths between models and their consumers.

3. **Direct refs are partially reachable via grep**: Baseline found 3/4 direct references (the three models and the main controller) but missed the `reviewable_flagged_post.rb` subclass. Grep for "ReviewableClaimedTopic" catches the join model and base model, but the flagged post subclass references it indirectly through the parent class.

4. **Test discovery correlates with code discovery**: Baseline found only 2/5 spec files because it only found the code paths it traced (models + main controller). Discovering `user_guardian_spec.rb` and `reviewable_claimed_topic_serializer_spec.rb` requires first finding the guardian and serializer code.

## Tool Usage Comparison

| Metric | Baseline | MCP |
|--------|----------|-----|
| Total tokens | 32,400 | 22,600 |
| File reads | 85 | 42 |
| Grep/search calls | 48 | -- |
| Sourcegraph searches | -- | 11 |
| Symbol navigations | -- | 18 |

MCP uses 30% fewer tokens and 51% fewer file reads. The baseline's high grep count reflects unsuccessful attempts to trace the reviewable system through Rails conventions (model -> serializer -> controller -> view) without understanding the class hierarchy.

## Verifier Behavior Notes

- **check_schema_change.sh**: Migration ID and model name check. Both modes pass easily.
- **check_direct_refs.sh**: Checks for 4 specific files (reviewable.rb, reviewable_flagged_post, both controllers). The flagged post subclass is the trickiest.
- **check_indirect_refs.sh**: Checks for 6 locations across serializers, guardian, frontend, and locales. This is the hardest checkpoint and the most discriminating.
- **check_test_impact.sh**: Checks for 5 spec files. Score correlates with indirect_refs discovery.

## Calibration Notes

- Schema evolution tasks show the best baseline-vs-MCP discrimination of all Batch 2 types (0.50 gap). This validates the task design: a single schema change that fans out through multiple architectural layers is exactly the pattern where codebase understanding tools add the most value.
- The checkpoint weighting (0.10/0.35/0.35/0.20) puts 70% of the score on the two tracing checkpoints, which is appropriate for tasks that are primarily about context gathering breadth.
- Expert-difficulty tasks like this one may need even harder indirect_refs criteria (e.g., requiring the agent to find the store.js service or the review-index-test.js) to push MCP scores below 1.0.
