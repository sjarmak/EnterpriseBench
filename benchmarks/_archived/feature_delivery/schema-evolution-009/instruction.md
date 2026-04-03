# Schema Change: Add Dashboard Visit Tracking

## Context

Users have been asking for a "sort by recently visited" option in the dashboard list. Currently we have no way to track when a user last visited a dashboard.

We're creating a new `DashboardLastVisited` model to track per-user timestamps.

## What I Need

This change spans the Django backend and React frontend. Sentry is a large codebase, so I need you to trace the full impact of adding this new model:

1. **Schema change**: Find the migration file that creates the new table and identify where the new model class is defined alongside the existing dashboard models.

2. **Backend references**: Sentry has a backup/restore system that must be aware of every model. Identify which backup-related files need updating — both the comparator definitions used during backup validation and the test utilities that register models for backup testing.

3. **Frontend references**: The dashboard management UI renders a table of dashboards. Find the React component that renders this table (it would need a "last visited" column or sorting option) and the TypeScript types file that defines the dashboard data shape.

4. **Test coverage**: Identify the test file for the dashboard table component that would need updated tests.

Write your analysis to `/workspace/sentry/SCHEMA_IMPACT.md`.
