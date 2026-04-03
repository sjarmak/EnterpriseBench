# Schema Change: Add Automatic Claim Tracking to Reviewable System

## Context

Our moderation queue has a concept of "claimed topics" — when a moderator claims a flagged topic for review. Currently we can't distinguish between topics that were manually claimed by a moderator vs. automatically claimed by the system (e.g., when a moderator performs an action on a reviewable).

We're adding an `automatic` boolean column to `ReviewableClaimedTopic` to track this distinction. The migration is `db/migrate/20250319024514_add_automatic_to_reviewable_claimed_topic.rb`.

## What I Need

The reviewable system is one of our most interconnected subsystems. Before we merge, I need the full dependency map:

1. **Schema change**: The migration and the `ReviewableClaimedTopic` model.

2. **Direct model and controller references**: The reviewable model hierarchy is complex — `Reviewable` is the base, `ReviewableFlaggedPost` extends it, and `ReviewableClaimedTopic` is the join model. Both the `ReviewablesController` and `ReviewableClaimedTopicsController` need changes.

3. **Indirect references**: This change fans out widely:
   - **Serializers**: We have `ReviewableSerializer`, `ReviewableClaimedTopicSerializer`, and `ReviewableTopicSerializer` — all need the `automatic` field exposed or handled.
   - **Guardian**: The `UserGuardian` controls who can claim/unclaim — automatic claims may have different permission rules.
   - **Frontend**: The reviewable item Handlebars template and JS component, the review index route, the penalize-user modal, and the admin-tools service all interact with claim state.
   - **Locales**: New strings for automatic vs. manual claim UI labels.

4. **Test coverage**: We need spec updates for the claimed topic model, both controllers, the serializer, and the guardian.

Write your analysis to `/workspace/discourse/SCHEMA_IMPACT.md`.
