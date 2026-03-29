---
name: a2-schema-extender
description: Extends schemas/task.schema.json with csb_lineage section, checkpoint timeout_seconds, and deterministic verification sub-structure. Additive changes only.
tools: ["Read", "Write", "Edit", "Grep", "Glob"]
model: sonnet
---

# A2: Schema Extender

You extend the EnterpriseBench task schema with fields needed for CSB migration and layered ground truth.

## Context

- `~/EnterpriseBench/schemas/task.schema.json` — existing task schema (JSON Schema draft 2020-12)
- `~/EnterpriseBench/benchmarks/EXAMPLE_TASK.toml` — reference task using the schema
- CSB has 275 tasks to migrate; need provenance tracking
- Convergence report requires layered ground truth with deterministic verification details

## Your Task

### 1. Add `csb_lineage` section to schema
```json
"csb_lineage": {
  "type": "object",
  "properties": {
    "parent_csb_id": { "type": "string", "description": "Original CSB task ID" },
    "origin_suite": { "type": "string", "description": "Original CSB suite (e.g., csb_org_compliance)" },
    "migration_status": {
      "type": "string",
      "enum": ["pending", "schema_mapped", "metadata_merged", "verified", "complete"]
    },
    "bugs_fixed": {
      "type": "array",
      "items": { "type": "string" },
      "description": "CSB bug IDs fixed during migration (cross-ref docs/csb_bugs.md)"
    },
    "metadata_sources": {
      "type": "array",
      "items": { "type": "string" },
      "description": "CSB files merged into this task (e.g., task.toml, ground_truth_meta.json)"
    }
  }
}
```

### 2. Add `timeout_seconds` to checkpoint definition
- Currently hardcoded to 120 in the prototype runner
- Add as optional integer field with default 120 on each checkpoint

### 3. Update EXAMPLE_TASK.toml
- Add a `[csb_lineage]` section showing what a migrated task looks like
- Add `timeout_seconds` to at least one checkpoint

### Constraints
- NO breaking changes to existing schema fields
- All new fields are optional (existing tasks must still validate)
- Use JSON Schema `$defs` for reusable sub-schemas where appropriate
- Maintain the existing style and formatting of the schema file

## Definition of Done
- Schema validates as valid JSON Schema draft 2020-12
- EXAMPLE_TASK.toml includes new sections
- No existing required fields changed
- Changes are purely additive
