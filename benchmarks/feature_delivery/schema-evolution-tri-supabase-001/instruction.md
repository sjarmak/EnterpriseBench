# Trace schema migration impact across Supabase core, PostgREST auto-API, and GoTrue auth

Your team runs a Supabase-based platform. A schema migration adds a new RLS
(Row Level Security) policy column to the auth.users table and modifies the
auth.sessions table structure. After applying the migration, PostgREST's
auto-generated API endpoints return unexpected 403 errors for authenticated
users, and GoTrue's token refresh flow fails intermittently.

The issue spans three repositories: the migration is defined in the Supabase
monorepo, PostgREST auto-generates API routes from the database schema, and
GoTrue directly queries auth tables with hardcoded column expectations.

Your task:

1. Find where Supabase defines the auth schema migrations — locate the SQL
   migration files for auth.users and auth.sessions tables in the Supabase
   monorepo. Identify the migration that modifies RLS policies and session
   structure.
2. Find where PostgREST discovers database schema to generate API endpoints —
   locate the schema cache, table introspection, and RLS policy evaluation code.
   Identify how PostgREST resolves permissions when RLS policies reference
   columns it hasn't cached yet.
3. Find where GoTrue queries auth tables — locate the session management,
   token refresh, and user retrieval code. Identify all hardcoded column
   references and table structure assumptions.
4. Map the impact chain: which Supabase migration changes break which PostgREST
   behaviors and which GoTrue queries.

Write your analysis to /workspace/SCHEMA_IMPACT.md with:

- Supabase migration changes (with file paths)
- Affected PostgREST schema cache and API generation logic
- Affected GoTrue query and session management code
- Impact chain showing migration -> PostgREST failure -> GoTrue failure
