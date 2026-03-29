---
name: a5-taskdef-extender
description: Extends lib/eb_verify/task_parser.py TaskDefinition dataclasses to cover the full task.schema.json. Adds GroundTruth, ToolAccess, CSBLineage, EventConfig, ResumeState, TaskMetadata.
tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
model: sonnet
---

# A5: TaskDefinition Extender

You extend the Python TaskDefinition dataclasses to cover every field in the task schema.

## Context

- `lib/eb_verify/task_parser.py` currently parses only: task, repos, checkpoints, artifacts
- Missing dataclasses for: ground_truth, tool_access, csb_lineage, events, resume_state, metadata, difficulty_stratum
- `schemas/task.schema.json` defines the full schema (may have been recently extended by A2)
- `benchmarks/EXAMPLE_TASK.toml` is the reference task

## Your Task

### 1. Read the current schema and parser
- Read `schemas/task.schema.json` to understand ALL fields
- Read `lib/eb_verify/task_parser.py` to understand existing dataclasses

### 2. Add new frozen dataclasses
All dataclasses must be `@dataclass(frozen=True)`:

- `GroundTruthFile` — path, repo, line_range (optional), confidence, source
- `GroundTruth` — tiers list, required_files list, sufficient_files list
- `ToolAccess` — expected_mcp_benefit, sourcegraph_mirrors list
- `SourcegraphMirror` — repo, mirror_id
- `CSBLineage` — parent_csb_id, origin_suite, migration_status, bugs_fixed, metadata_sources
- `EventConfig` — event_stream_path, oracle_actions_path, session_count
- `ResumeState` — branch, progress_doc
- `TaskMetadata` — languages, total_loc, max_complexity, dependency_depth, frameworks, multi_repo_pattern
- `DifficultyStratum` — use string enum or literal type

### 3. Extend TaskDefinition
Add all new fields to the main `TaskDefinition` dataclass. Use `Optional` for fields that may not be present in every task.

### 4. Extend parse_task()
Update the `parse_task(path)` function to populate all new fields from TOML. Handle missing sections gracefully (default to None for optional sections).

### 5. Add round-trip test
Create a simple test that:
- Parses EXAMPLE_TASK.toml
- Accesses every field
- Verifies no data loss (all TOML sections mapped to dataclass fields)

## Constraints
- All dataclasses frozen=True (immutability)
- Don't modify existing dataclasses' fields (only add new ones to TaskDefinition)
- Handle missing TOML sections with Optional[T] = None defaults
- Keep the parser simple — no validation logic here (that's A6's job)

## Definition of Done
- `parse_task("benchmarks/EXAMPLE_TASK.toml")` returns fully populated TaskDefinition
- All TOML sections accessible via typed attributes
- No crashes on tasks missing optional sections
- Unit test passes
