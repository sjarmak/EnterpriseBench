# Schema Change: Add Dashboard Visit Tracking

## Context

Users have been asking for a "sort by recently visited" option in the dashboard list. Currently we have no way to track when a user last visited a dashboard.

We're creating a new `DashboardLastVisited` model to track per-user timestamps. The migration is `src/sentry/migrations/0947_add_dashboard_last_visited_model.py`.

## What I Need

This change spans the Django backend and React frontend. Sentry is a large codebase, so I need you to trace the impact:

1. **Schema change**: The migration file and where the new model is defined (it lives in the existing dashboard models file).

2. **Backend references**: Beyond the model itself, Sentry has a backup/restore system that needs to know about every model. Check:
   - The backup comparators file (`src/sentry/backup/comparators.py`) that defines how models are compared during backup validation
   - The backup test utilities (`src/sentry/testutils/helpers/backups.py`) that register models for backup testing

3. **Frontend references**: The dashboard management UI shows a table of dashboards. We need:
   - The table component (`tableView/table.tsx`) that renders the dashboard list — it needs a "last visited" column or sorting option
   - The TypeScript types file that defines the dashboard data shape

4. **Test coverage**: The frontend table component has a spec file that needs updated tests.

Write your analysis to `/workspace/sentry/SCHEMA_IMPACT.md`.
