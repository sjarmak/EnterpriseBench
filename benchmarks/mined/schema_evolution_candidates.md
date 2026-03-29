# DB Schema Evolution — Mined Candidates

Task type: `db-schema-*`
Suite mapping: `feature_delivery` (primary), `technical_debt` (secondary)
Mined: 2026-03-29

---

## Zulip (Django) — 4 Candidates

### SE-1: Deactivate User Groups (HIGH confidence)

- **Repo:** `zulip/zulip`
- **PR:** zulip/zulip#30504
- **Schema change:** Add `deactivated` boolean column to `NamedUserGroup` model
- **Migration file:** `zerver/migrations/0578_namedusergroup_deactivated.py`
- **Files changed:** 22
- **Affected code paths:**
  - **Model:** `zerver/models/groups.py`
  - **Actions:** `zerver/actions/user_groups.py`
  - **Views:** `zerver/views/user_groups.py`, `zerver/views/streams.py`
  - **Events:** `zerver/lib/events.py`, `zerver/lib/event_schema.py`
  - **Utilities:** `zerver/lib/user_groups.py`, `zerver/lib/markdown/__init__.py`
  - **Import:** `zerver/lib/import_realm.py`
  - **API:** `zerver/openapi/zulip.yaml`, `zerver/openapi/curl_param_value_generators.py`
  - **Audit log:** `zerver/models/realm_audit_logs.py`
  - **Tests:** `zerver/tests/test_user_groups.py`, `zerver/tests/test_events.py`, `zerver/tests/test_audit_log.py`, `zerver/tests/test_markdown.py`
  - **API docs:** `api_docs/changelog.md`
  - **URLs:** `zproject/urls.py`
- **Impact categories:** Direct model change, views, event system, API schema, import/export, audit log, tests
- **Difficulty:** hard
- **Notes:** Excellent candidate — single boolean column addition but requires coordinated changes across model, views, events, API schema, and 4 test files. Demonstrates how a simple schema change propagates through a well-structured Django app.

### SE-2: RealmExport Model (HIGH confidence)

- **Repo:** `zulip/zulip`
- **PR:** zulip/zulip#31760
- **Schema change:** Create new `RealmExport` table, migrate from JSON file-based export tracking
- **Migration file:** `zerver/migrations/0595_add_realmexport_table_and_backfill.py`
- **Files changed:** 12
- **Affected code paths:**
  - **Model:** `zerver/models/realms.py`, `zerver/models/__init__.py`
  - **Actions:** `zerver/actions/realm_export.py`
  - **Views:** `zerver/views/realm_export.py`
  - **Export logic:** `zerver/lib/export.py`
  - **Management:** `zerver/management/commands/export.py`
  - **Worker:** `zerver/worker/deferred_work.py`
  - **Tests:** `zerver/tests/test_realm_export.py`, `zerver/tests/test_import_export.py`, `zerver/tests/test_events.py`, `zerver/tests/test_management_commands.py`
- **Impact categories:** New table creation, model registration, views, background worker, management commands, tests
- **Difficulty:** hard
- **Notes:** New model creation with backfill migration. Requires understanding how export tracking was previously done (JSON file) and how the new model integrates with views, workers, and management commands.

### SE-3: Group-Based Channel Creation Setting (HIGH confidence)

- **Repo:** `zulip/zulip`
- **PR:** zulip/zulip#30301
- **Schema change:** Replace boolean `create_public_stream_policy` with FK `can_create_public_channel_group` pointing to `NamedUserGroup`. 4 migrations (add column, backfill, alter, remove old).
- **Migration files:** `zerver/migrations/0532_realm_can_create_public_channel_group.py` through `0535_remove_realm_create_public_stream_policy.py`
- **Files changed:** 25+
- **Affected code paths:**
  - **Model:** `zerver/models/realms.py`
  - **Actions:** `zerver/actions/create_realm.py`, `zerver/actions/realm_settings.py`
  - **Events:** `zerver/lib/events.py`, `zerver/lib/event_schema.py`
  - **Frontend settings:** `web/src/settings_org.js`, `web/src/settings_data.ts`, `web/src/settings_components.ts`, `web/src/stream_settings_ui.js`, `web/src/state_data.ts`, `web/src/ui_init.js`
  - **Templates:** `web/templates/settings/organization_permissions_admin.hbs`
  - **API:** `zerver/openapi/zulip.yaml`, `api_docs/changelog.md`
  - **Tests:** `web/tests/dispatch.test.js`, `web/tests/settings_data.test.js`, `web/tests/settings_org.test.js`, `web/e2e-tests/admin.test.ts`
- **Impact categories:** Multi-step migration, model FK change, actions, event system, frontend settings, API schema, e2e tests
- **Difficulty:** expert
- **Notes:** 4-migration sequence replacing a simple integer policy with a group-based FK. Cross-stack impact: Python model → Python views → JavaScript settings UI → API docs. Excellent for testing schema evolution understanding across frontend and backend.

### SE-4: Remove Default Avatar Source Setting (HIGH confidence)

- **Repo:** `zulip/zulip`
- **PR:** zulip/zulip#38020
- **Schema change:** Remove `default_avatar_source` field from `UserProfile` model, add `default_avatar_source` to `Realm` model
- **Migration file:** `zerver/migrations/0776_realm_default_avatar_source.py` + squashed migration updates
- **Files changed:** 18
- **Affected code paths:**
  - **Models:** `zerver/models/realms.py`, `zerver/models/users.py`
  - **Avatar logic:** `zerver/lib/avatar.py`
  - **API examples:** `zerver/openapi/python_examples.py`
  - **Frontend:** `web/templates/settings/organization_settings_admin.hbs`
  - **Dependencies:** `package.json`, `pnpm-lock.yaml`, `patches/jdenticon.patch`
  - **Tests:** `zerver/tests/test_events.py`, `zerver/tests/test_upload.py`, `zerver/tests/test_upload_s3.py`, `zerver/tests/test_mattermost_importer.py`, `zerver/tests/test_rocketchat_importer.py`, `zerver/tests/test_slack_importer.py`
- **Impact categories:** Field migration between models, avatar rendering logic, importer updates, frontend settings, multiple test suites
- **Difficulty:** hard
- **Notes:** Moving a field from user-level to realm-level. Impacts all importers (Slack, Mattermost, Rocket.Chat), avatar rendering, and multiple test suites.

---

## Discourse (Rails) — 4 Candidates

### SE-5: Sync Reviewable Status (HIGH confidence)

- **Repo:** `discourse/discourse`
- **PR:** discourse/discourse#31901
- **Schema change:** Add `automatic` boolean column to `ReviewableClaimedTopic` model
- **Migration file:** `db/migrate/20250319024514_add_automatic_to_reviewable_claimed_topic.rb`
- **Files changed:** 24
- **Affected code paths:**
  - **Models:** `app/models/reviewable.rb`, `app/models/reviewable_claimed_topic.rb`, `app/models/reviewable_flagged_post.rb`
  - **Controllers:** `app/controllers/reviewables_controller.rb`, `app/controllers/reviewable_claimed_topics_controller.rb`
  - **Serializers:** `app/serializers/reviewable_serializer.rb`, `app/serializers/reviewable_claimed_topic_serializer.rb`, `app/serializers/reviewable_topic_serializer.rb`
  - **Guardian:** `lib/guardian/user_guardian.rb`
  - **Frontend:** `app/assets/javascripts/discourse/app/components/reviewable-item.hbs`, `app/assets/javascripts/discourse/app/components/reviewable-item.js`, `app/assets/javascripts/discourse/app/routes/review-index.js`, `app/assets/javascripts/admin/addon/components/modal/penalize-user.js`, `app/assets/javascripts/admin/addon/services/admin-tools.js`
  - **Tests:** `spec/models/reviewable_claimed_topic_spec.rb`, `spec/models/reviewable_spec.rb`, `spec/requests/reviewable_claimed_topics_controller_spec.rb`, `spec/requests/reviewables_controller_spec.rb`, `spec/serializers/reviewable_claimed_topic_serializer_spec.rb`, `spec/lib/guardian/user_guardian_spec.rb`
  - **Locales:** `config/locales/client.en.yml`
- **Impact categories:** Model + 2 controllers + 3 serializers + guardian + frontend JS + 6 test files
- **Difficulty:** expert
- **Notes:** Textbook schema evolution candidate. One boolean column triggers changes in 3 models, 2 controllers, 3 serializers, authorization guardian, frontend components, and 6 test files. Rails patterns fully represented.

### SE-6: Add Description to Invites (HIGH confidence)

- **Repo:** `discourse/discourse`
- **PR:** discourse/discourse#33207
- **Schema change:** Add `description` text column to `Invite` model
- **Migration file:** `db/migrate/20250614020437_add_description_to_invites.rb`
- **Files changed:** 14
- **Affected code paths:**
  - **Model:** `app/models/invite.rb`
  - **Controller:** `app/controllers/invites_controller.rb`
  - **Serializer:** `app/serializers/invite_serializer.rb`
  - **Frontend:** `app/assets/javascripts/discourse/app/components/modal/create-invite.gjs`, `app/assets/javascripts/discourse/app/templates/user-invited-show.gjs`, `app/assets/javascripts/discourse/app/lib/constants.js`
  - **Styles:** `app/assets/stylesheets/common/base/user.scss`
  - **Locales:** `config/locales/client.en.yml`
  - **Tests:** `spec/models/invite_spec.rb`, `spec/requests/invites_controller_spec.rb`, `spec/system/create_invite_spec.rb`, `spec/system/page_objects/pages/user_invited_pending.rb`
- **Impact categories:** Model + controller + serializer + frontend component + system tests + CSS
- **Difficulty:** medium
- **Notes:** Clean single-column addition with full-stack impact: model → controller → serializer → frontend modal → system tests. Good medium-difficulty candidate.

### SE-7: Category Approval Groups (HIGH confidence)

- **Repo:** `discourse/discourse`
- **PR:** discourse/discourse#38523
- **Schema change:** Create `CategoryApprovalGroup` join table, mark old boolean approval columns as readonly
- **Migration files:** `db/migrate/20260310072550_mark_category_approval_booleans_readonly.rb`, `db/migrate/20260310072759_create_category_approval_groups.rb`
- **Files changed:** 11
- **Affected code paths:**
  - **Models:** `app/models/category.rb`, `app/models/category_posting_review_group.rb`, `app/models/category_setting.rb`
  - **Import:** `script/bulk_import/discourse_merger.rb`
  - **Tests:** `spec/db/migrate/20260310072759_create_category_approval_groups_spec.rb`, `spec/models/category_posting_review_group_spec.rb`, `spec/models/category_setting_spec.rb`, `spec/models/category_spec.rb`, `spec/serializers/category_serializer_spec.rb`
- **Impact categories:** Multi-migration (deprecate booleans + new join table), 3 models, import script, 5 test files
- **Difficulty:** hard
- **Notes:** Schema normalization — moving from boolean columns to join table. Two-phase migration (mark readonly, then create new structure). Good for testing understanding of migration ordering.

### SE-8: Auto-Bump Cooldown Days (HIGH confidence)

- **Repo:** `discourse/discourse`
- **PR:** discourse/discourse#20507
- **Schema change:** Add `auto_bump_cooldown_days` column to `CategorySetting` model with backfill migration
- **Migration files:** `db/migrate/20230301071240_add_auto_bump_cooldown_days_to_category_settings.rb`, `db/migrate/20230308042434_backfill_auto_bump_cooldown_days_category_setting.rb`
- **Files changed:** 14
- **Affected code paths:**
  - **Models:** `app/models/category.rb`, `app/models/category_setting.rb`
  - **Controller:** `app/controllers/categories_controller.rb`
  - **Serializer:** `app/serializers/category_serializer.rb`
  - **Frontend:** `app/assets/javascripts/discourse/app/components/edit-category-settings.hbs`, `app/assets/javascripts/discourse/app/models/category.js`, `app/assets/javascripts/discourse/app/routes/new-category.js`
  - **Locales:** `config/locales/client.en.yml`
  - **API schema:** `spec/requests/api/schemas/json/category_create_response.json`, `spec/requests/api/schemas/json/category_update_response.json`
  - **Tests:** `spec/models/category_setting_spec.rb`, `spec/models/category_spec.rb`
- **Impact categories:** 2-migration (add + backfill), model, controller, serializer, frontend, API response schema, tests
- **Difficulty:** medium
- **Notes:** Two-step migration with backfill. Impacts API response schema — agent must find the JSON schema fixtures in addition to the code changes.

---

## Sentry (Django) — 2 Candidates

### SE-9: Dashboard Last Visited Tracking (MEDIUM confidence)

- **Repo:** `getsentry/sentry`
- **PRs:** getsentry/sentry#95361 (backend) + getsentry/sentry#95788 (frontend)
- **Schema change:** Create `DashboardLastVisited` model to track per-user dashboard visit timestamps
- **Migration file:** `src/sentry/migrations/0947_add_dashboard_last_visited_model.py`
- **Files changed:** 8 (backend) + 3 (frontend) = 11 total
- **Affected code paths:**
  - **Model:** `src/sentry/models/dashboard.py`
  - **Backup:** `src/sentry/backup/comparators.py`, `src/sentry/testutils/helpers/backups.py`
  - **Frontend:** `static/app/views/dashboards/manage/tableView/table.tsx`, `static/app/views/dashboards/types.tsx`
  - **Tests:** `static/app/views/dashboards/manage/tableView/table.spec.tsx`
- **Impact categories:** New model, backup comparators, frontend table component, TypeScript types
- **Difficulty:** medium
- **Notes:** Split across two PRs (backend + frontend) but both are atomic. Demonstrates how Sentry's Django models connect to React frontend types.

### SE-10: ProjectOwnership Schema to JSONField (MEDIUM confidence)

- **Repo:** `getsentry/sentry`
- **PR:** getsentry/sentry#99929
- **Schema change:** Convert `ProjectOwnership.schema` from `TextField` storing raw JSON to native `JSONField`
- **Migration file:** `src/sentry/migrations/0991_projectownership_json_field.py`
- **Files changed:** 3
- **Affected code paths:**
  - **Model:** `src/sentry/models/projectownership.py`
  - **Migration:** `src/sentry/migrations/0991_projectownership_json_field.py`
- **Impact categories:** Field type change, migration
- **Difficulty:** medium
- **Notes:** Simpler candidate but demonstrates a common Django pattern: converting a TextField with JSON to proper JSONField. Limited direct impact but requires understanding of all code that reads/writes this field (implicit JSON serialization behavior changes).

---

## Mattermost (Go) — 2 Candidates

### SE-11: Flatten View Model (HIGH confidence)

- **Repo:** `mattermost/mattermost`
- **PR:** mattermost/mattermost#35726
- **Schema change:** Drop `icon` column from views table, remove nested `subviews` and `typed_board_props` from view model
- **Migration files:** `server/channels/db/migrations/postgres/000167_views_drop_icon.up.sql`, `000167_views_drop_icon.down.sql`
- **Files changed:** 12
- **Affected code paths:**
  - **Migration list:** `server/channels/db/migrations/migrations.list`
  - **API schema:** `api/v4/source/definitions.yaml`, `api/v4/source/views.yaml`
  - **Model:** `server/public/model/view.go`
  - **Store:** `server/channels/store/sqlstore/view_store.go`
  - **Store tests:** `server/channels/store/storetest/view_store.go`
  - **API tests:** `server/channels/api4/view_test.go`, `server/channels/app/view_test.go`
  - **Model tests:** `server/public/model/view_test.go`
  - **i18n:** `server/i18n/en.json`
- **Impact categories:** SQL migration, Go model struct, SQL store, OpenAPI schema, 4 test files
- **Difficulty:** hard
- **Notes:** Go equivalent of Django migration — SQL migration + struct field removal + OpenAPI spec update. Agent must find both the SQL migration AND the API definition changes.

### SE-12: Enforce Unique Policy Names (HIGH confidence)

- **Repo:** `mattermost/mattermost`
- **PR:** mattermost/mattermost#35676
- **Schema change:** Add unique constraint + deduplication migration for access control policy names
- **Migration files:** `server/channels/db/migrations/postgres/000159_deduplicate_policy_names.up.sql`, `000159_deduplicate_policy_names.down.sql`
- **Files changed:** 10
- **Affected code paths:**
  - **Migration list:** `server/channels/db/migrations/migrations.list`
  - **Store:** `server/channels/store/sqlstore/access_control_policy_store.go`
  - **Store tests:** `server/channels/store/storetest/access_control_policy_store.go`
  - **Frontend:** `webapp/channels/src/components/admin_console/access_control/policy_details/policy_details.tsx`
  - **E2E tests:** `e2e-tests/playwright/specs/functional/system_console/abac/policies/create_policies.spec.ts`, `e2e-tests/playwright/specs/functional/system_console/abac/policy_management/edit_policies.spec.ts`
  - **i18n:** `server/i18n/en.json`, `webapp/channels/src/i18n/en.json`
- **Impact categories:** SQL deduplication migration, unique constraint, store code, frontend validation, E2E tests, i18n (2 locales)
- **Difficulty:** hard
- **Notes:** Constraint addition with deduplication — migration must handle existing duplicates before adding unique index. Cross-stack: Go store, React frontend, Playwright E2E tests.

---

## Summary

| # | Candidate | Repo | Framework | Files | Difficulty | Confidence |
|---|-----------|------|-----------|-------|------------|------------|
| SE-1 | Deactivate user groups | zulip/zulip | Django | 22 | hard | HIGH |
| SE-2 | RealmExport model | zulip/zulip | Django | 12 | hard | HIGH |
| SE-3 | Group-based channel setting | zulip/zulip | Django | 25+ | expert | HIGH |
| SE-4 | Remove default_avatar_source | zulip/zulip | Django | 18 | hard | HIGH |
| SE-5 | Sync reviewable status | discourse/discourse | Rails | 24 | expert | HIGH |
| SE-6 | Add description to invites | discourse/discourse | Rails | 14 | medium | HIGH |
| SE-7 | Category approval groups | discourse/discourse | Rails | 11 | hard | HIGH |
| SE-8 | Auto-bump cooldown days | discourse/discourse | Rails | 14 | medium | HIGH |
| SE-9 | Dashboard visit tracking | getsentry/sentry | Django | 11 | medium | MEDIUM |
| SE-10 | Ownership JSONField | getsentry/sentry | Django | 3 | medium | MEDIUM |
| SE-11 | Flatten view model | mattermost/mattermost | Go | 12 | hard | HIGH |
| SE-12 | Enforce unique policy names | mattermost/mattermost | Go | 10 | hard | HIGH |

### Difficulty Distribution
- Medium: 4 (33%) — target: 30%
- Hard: 6 (50%) — target: 50%
- Expert: 2 (17%) — target: 20%

### Framework Coverage
- Django (Zulip + Sentry): 6 candidates
- Rails (Discourse): 4 candidates
- Go (Mattermost): 2 candidates

### Key Metrics
- All 12 candidates have atomic PRs (migration + code changes shipped together)
- 10/12 are HIGH confidence with 10+ files changed
- Every candidate has at least: migration file, model change, and test changes
- Best candidates (SE-1, SE-3, SE-5) have 20+ files spanning model → views → serializer → API → frontend → tests

### Candidates NOT Selected (Investigated but Rejected)
- **Sentry #99491 (groupredirect model):** Only 4 files, too narrow
- **Sentry #106476 (debug column):** Only 3 files, trivial add-column
- **Sentry #102443 (non-nullable):** Only 3 files, constraint change only
- **Discourse #16666 (last_seen_reviewable_id):** Only 2 files, too simple
- **Mattermost #35554 (PermissionManageOauth):** Only 6 files, permissions-only
- **Zulip #30307 (resolve topic grace period):** Only 8 files, limited breadth
- **Discourse #38506 (field type):** 60+ files, too broad (framework-wide form-kit refactor, not schema evolution)

### Next Steps (for P2.7)
1. Extract exact file lists and line ranges for ground truth
2. For SE-3 and SE-5 (expert), verify all 4 migration files execute correctly in sequence
3. Pin repo revisions to specific tags/commits (pre-migration state)
4. Build checkpoint structures matching PRD (schema change → direct refs → indirect refs → test impact)
