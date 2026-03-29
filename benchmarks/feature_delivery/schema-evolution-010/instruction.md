# Schema Change: Flatten View Model by Removing Icon and Nested Structures

## Context

We're simplifying the View model in Mattermost. The `icon` column in the views table is being dropped, and the Go model struct is being flattened by removing the nested `subviews` and `typed_board_props` fields. These were part of the old board-centric design and are no longer needed.

## What I Need

This is a Go codebase with raw SQL migrations (not an ORM), so the impact chain is different from Django/Rails. Trace the full impact of dropping the `icon` column and flattening the View struct:

1. **Schema change**: Find the SQL migration files (both up and down) for this column drop, and the migrations list file that registers them.

2. **Direct references**: Identify the Go model struct definition for the View type (where the fields need to be removed) and the SQL store implementation where queries SELECT or INSERT the `icon` column.

3. **Indirect references**: The Mattermost API has an OpenAPI specification — find both the model schema definitions and the views endpoint definitions that describe the View object shape. Also check for internationalization strings that may reference view icons.

4. **Test coverage**: This change impacts multiple test layers. Find the test files for the View model, the SQL store, the API layer, and the app layer.

Write your analysis to `/workspace/mattermost/SCHEMA_IMPACT.md`.
