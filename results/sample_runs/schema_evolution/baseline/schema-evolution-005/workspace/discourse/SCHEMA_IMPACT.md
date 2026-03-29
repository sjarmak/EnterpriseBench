# Schema Impact Analysis

## Schema Change

Migration `db/migrate/20250319024514_add_automatic_to_reviewable_claimed_topic.rb`
adds an `automatic` boolean column to `ReviewableClaimedTopic`.

The model is defined in `app/models/reviewable_claimed_topic.rb`.

## Direct References

- `app/models/reviewable.rb` — base Reviewable model, manages claimed topics
- `app/controllers/reviewables_controller.rb` — main review actions controller
- `app/controllers/reviewable_claimed_topics_controller.rb` — claiming endpoint

## Serializers

- `app/serializers/reviewable_serializer.rb` — needs the automatic flag

## Tests

- `spec/models/reviewable_spec.rb` — model tests
- `spec/requests/reviewables_controller_spec.rb` — controller tests
