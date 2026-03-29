# Schema Impact Analysis

## 1. Schema Change

Migration `db/migrate/20250319024514_add_automatic_to_reviewable_claimed_topic.rb`
adds an `automatic` boolean column to the `ReviewableClaimedTopic` model in
`app/models/reviewable_claimed_topic.rb`.

## 2. Direct Model and Controller References

- `app/models/reviewable.rb` — base Reviewable model, manages claimed topic lifecycle
- `app/models/reviewable_flagged_post.rb` — flagged post subclass, auto-claims on actions
- `app/models/reviewable_claimed_topic.rb` — the claim join model with new column
- `app/controllers/reviewables_controller.rb` — main review actions (approve, reject, etc.)
- `app/controllers/reviewable_claimed_topics_controller.rb` — claim/unclaim endpoints

## 3. Indirect References

### Serializers (3)
- `app/serializers/reviewable_serializer.rb` — main review queue serializer, exposes claim data
- `app/serializers/reviewable_claimed_topic_serializer.rb` — claim-specific serializer
- `app/serializers/reviewable_topic_serializer.rb` — topic view serializer with claim info

### Authorization
- `lib/guardian/user_guardian.rb` — controls who can claim/unclaim; automatic claims may have different permission rules

### Frontend
- `app/assets/javascripts/discourse/app/components/reviewable-item.hbs` — review item template shows claimed state
- `app/assets/javascripts/discourse/app/components/reviewable-item.js` — component logic for claim/unclaim actions
- `app/assets/javascripts/discourse/app/routes/review-index.js` — review queue route, filters by claimed status
- `app/assets/javascripts/admin/addon/components/modal/penalize-user.js` — penalization modal auto-claims
- `app/assets/javascripts/admin/addon/services/admin-tools.js` — admin service triggers auto-claims

### Locale Strings
- `config/locales/client.en.yml` — new strings for automatic vs manual claim labels

## 4. Test Impact

- `spec/models/reviewable_claimed_topic_spec.rb` — claim model spec, needs auto-claim tests
- `spec/models/reviewable_spec.rb` — base model spec
- `spec/requests/reviewables_controller_spec.rb` — controller request spec
- `spec/requests/reviewable_claimed_topics_controller_spec.rb` — claim controller spec
- `spec/serializers/reviewable_claimed_topic_serializer_spec.rb` — serializer spec
- `spec/lib/guardian/user_guardian_spec.rb` — guardian permission spec
