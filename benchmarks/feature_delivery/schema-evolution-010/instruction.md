# Schema Change: Flatten View Model by Removing Icon and Nested Structures

## Context

We're simplifying the View model in Mattermost. The `icon` column in the views table is being dropped, and the Go model struct is being flattened by removing the nested `subviews` and `typed_board_props` fields. These were part of the old board-centric design and are no longer needed.

The SQL migration is at `server/channels/db/migrations/postgres/000167_views_drop_icon.up.sql`.

## What I Need

This is a Go codebase with raw SQL migrations (not an ORM), so the impact chain is different from Django/Rails:

1. **Schema change**: The SQL migration files (both up and down), and the `migrations.list` file that registers them.

2. **Direct references**:
   - The Go model struct in `server/public/model/view.go` — fields need to be removed from the struct definition
   - The SQL store in `server/channels/store/sqlstore/view_store.go` — SQL queries that SELECT or INSERT the `icon` column need updating

3. **Indirect references**:
   - The OpenAPI specification in `api/v4/source/` — both `definitions.yaml` (model schema) and `views.yaml` (endpoint definitions) define the View object shape
   - Internationalization strings in `server/i18n/en.json` that may reference view icons

4. **Test coverage**: There are test files at multiple layers:
   - Model tests (`server/public/model/view_test.go`)
   - Store tests (`server/channels/store/storetest/view_store.go`)
   - API tests (`server/channels/api4/view_test.go`)
   - App-layer tests (`server/channels/app/view_test.go`)

Write your analysis to `/workspace/mattermost/SCHEMA_IMPACT.md`.
