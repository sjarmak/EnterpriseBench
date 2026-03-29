# Schema Change: Normalize Category Approval from Booleans to Join Table

## Context

Our category approval system currently uses boolean columns on `CategorySetting` (like `require_topic_approval` and `require_reply_approval`). This is inflexible — we can't assign different approval groups to different categories, and it doesn't support the group-based permissions model we're moving toward.

We're replacing the booleans with a proper `CategoryApprovalGroup` join table. This is a two-phase migration:
1. First migration marks the old boolean columns as readonly (so nothing new writes to them)
2. Second migration creates the `CategoryApprovalGroup` table and backfills from the booleans

## What I Need

1. **Schema change**: Both migration files. I need to understand the ordering — why we mark readonly before creating the new table.

2. **Direct model references**: Three models are involved:
   - `Category` — the parent model with approval-related associations
   - `CategoryPostingReviewGroup` — the new join model (or existing model being extended)
   - `CategorySetting` — where the old booleans lived

3. **Indirect references**: The `discourse_merger.rb` bulk import script handles category data during site merges and needs to understand the new structure. Also check if any serializers need updating.

4. **Test coverage**: We should have a migration-specific spec (testing the backfill), plus model specs for all three models and the category serializer spec.

Write your findings to `/workspace/discourse/SCHEMA_IMPACT.md`.
