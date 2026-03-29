# Schema Change: Add Auto-Bump Cooldown Setting to Categories

## Context

Category auto-bumping currently uses a global site setting for cooldown between bumps. Category admins have been requesting per-category control, so we're adding `auto_bump_cooldown_days` directly to `CategorySetting`.

This is a two-step migration:
1. Add the column with `20230301071240_add_auto_bump_cooldown_days_to_category_settings.rb`
2. Backfill existing categories from the global site setting with `20230308042434_backfill_auto_bump_cooldown_days_category_setting.rb`

## What I Need

1. **Schema change**: Both migration files — the column addition and the backfill.

2. **Direct references**: The `CategorySetting` model (where the field lives), the `Category` model (which delegates to settings), the `CategoriesController` (which accepts the param), and the `CategorySerializer` (which exposes it in the API).

3. **Indirect references**: The frontend needs a UI for this:
   - The edit-category-settings Handlebars template
   - The Category JS model
   - The new-category route (for defaults)
   - Locale strings for the label and description
   - **Important**: The API response JSON schemas under `spec/requests/api/schemas/json/` — these are fixture files that define the expected shape of category API responses, and they need the new field added.

4. **Test coverage**: Model specs for both `CategorySetting` and `Category`, plus the API JSON schema fixtures (which function as both contract tests and documentation).

Write your findings to `/workspace/discourse/SCHEMA_IMPACT.md`.
