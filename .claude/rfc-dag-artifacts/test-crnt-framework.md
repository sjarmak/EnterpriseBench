# CRNT Framework Test Results

## Test Run: 2026-04-02

```
31 passed in 0.04s
```

## Test Coverage

| Test Class                | Tests | Status |
| ------------------------- | ----- | ------ |
| TestExtractRepos          | 4     | PASS   |
| TestExtractCheckpoints    | 2     | PASS   |
| TestMapCheckpointsToRepos | 3     | PASS   |
| TestGenerateAblations     | 5     | PASS   |
| TestComputeMaxScore       | 3     | PASS   |
| TestEvaluateCRNT          | 4     | PASS   |
| TestFormatResult          | 2     | PASS   |
| TestWriteAblatedConfigs   | 2     | PASS   |
| TestParseTOML             | 2     | PASS   |
| TestCLI                   | 4     | PASS   |

## Real task validation

- `dep-traversal-001` (3 repos): CRNT PASS — removing any repo drops score to 0.0
- CLI --dry-run, --json, single-repo skip all verified
