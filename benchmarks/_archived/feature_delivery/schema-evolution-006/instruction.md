# Schema Change: Add Description Field to Invites

## Context

Admins have been asking for a way to annotate invites with notes — things like "new marketing hire" or "vendor access for Q3 project". Currently invites only track the email and link, with no way to add context.

We're adding a `description` text column to the `Invite` model. The migration is `db/migrate/20250614020437_add_description_to_invites.rb`.

## What I Need

This is a clean add-column change, but it touches the full MVC stack plus frontend:

1. **Schema change**: The migration and model update.

2. **Direct references**: The `Invite` model needs the field permitted, the `InvitesController` needs to accept it in params, and the `InviteSerializer` needs to expose it in API responses.

3. **Indirect references**: The frontend side needs work:
   - The create-invite modal component (`.gjs` file) needs a description input field
   - The invited-show template needs to display it
   - The constants file may need a max-length constant
   - CSS/SCSS for styling the new field
   - Locale strings for field labels and placeholders

4. **Test coverage**: Model spec, controller request spec, and importantly the system test for the invite creation flow (plus its page object).

Write your findings to `/workspace/discourse/SCHEMA_IMPACT.md`.
