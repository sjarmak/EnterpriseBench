# Trace schema evolution between Sentry's Django models and Relay's Rust schema definitions for event processing

Sentry uses a dual-language architecture: the main application is Django/Python, while
Relay (the event ingestion pipeline) is written in Rust. Both services need to agree on
the schema for events, envelopes, and project configuration.

After upgrading to Sentry 23.11.0, some event types are being rejected by Relay with
schema validation errors. The issue is that Sentry's Django models for event types and
project configuration have evolved, but Relay's Rust schema definitions haven't been
updated to match.

Your task:
1. Identify the Sentry Django models that define event types, project configuration,
   and data categories — focus on models in sentry/models/ and the event schema
   definitions in sentry/event_manager.py and related modules.
2. Find the corresponding Rust schema definitions in Relay — look in relay-general/src/
   and relay-server/src/ for Protocol structs, enums, and validation logic.
3. Identify schema drift points where the Sentry Python definitions have fields, enums,
   or validation rules that differ from Relay's Rust definitions.
4. For each drift point, document the Sentry definition, the Relay definition, and the
   impact on event processing.

Write your analysis to /workspace/SCHEMA_IMPACT.md with:
- Sentry model changes with file paths
- Corresponding Relay Rust schema definitions
- Schema drift points with both-side file references
- Impact on event ingestion pipeline
