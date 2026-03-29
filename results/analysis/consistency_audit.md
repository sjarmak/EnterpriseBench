# Cross-Task Consistency Audit

Generated: 2026-03-29 16:01:26 UTC

## Summary

| Metric | Count |
|--------|-------|
| Tasks scanned | 97 |
| Check scripts scanned | 337 |
| Tasks with violations | 0 |
| Total violations | 0 |

## Violations by Category

| Category | Count | Description |
|----------|-------|-------------|
| env_usage | 0 | Shell var expansion in python3 -c blocks |
| set_flags | 0 | Missing set -euo pipefail |
| json_output | 0 | Missing score/passed keys in output |
| weights | 0 | Checkpoint weights not summing to 1.0 |
| executable | 0 | Check scripts not chmod +x |
| artifact_match | 0 | Artifact type mismatch |

## Detailed Violations

No violations found.

## Checks Performed

1. **env_usage**: All python3 -c blocks use `os.environ` (not `'$VAR'` shell expansion)
2. **set_flags**: All scripts have `set -euo pipefail` or `set -uo pipefail`
3. **json_output**: All scripts produce JSON with `score` and `passed` keys
4. **weights**: Checkpoint weights sum to 1.0 (±0.01)
5. **executable**: All check scripts are chmod +x
6. **artifact_match**: Artifact types in task.toml match what check scripts read
