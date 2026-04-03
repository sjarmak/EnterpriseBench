# Test Results: repo-versions-manifest

## Run: 2026-04-02

All 10 tests passed.

```
tests/test_repo_staleness.py::TestCheckStaleness::test_all_fresh PASSED
tests/test_repo_staleness.py::TestCheckStaleness::test_stale_detected PASSED
tests/test_repo_staleness.py::TestCheckStaleness::test_exactly_at_threshold_is_stale PASSED
tests/test_repo_staleness.py::TestCheckStaleness::test_one_day_before_threshold_is_fresh PASSED
tests/test_repo_staleness.py::TestCheckStaleness::test_stale_sorted_by_days_descending PASSED
tests/test_repo_staleness.py::TestCheckStaleness::test_custom_threshold PASSED
tests/test_repo_staleness.py::TestCheckStaleness::test_empty_entries PASSED
tests/test_repo_staleness.py::TestLoadManifest::test_load_from_file PASSED
tests/test_repo_staleness.py::TestCLI::test_json_flag PASSED
tests/test_repo_staleness.py::TestCLI::test_no_stale_exit_zero PASSED
```

## Coverage

- `check_staleness()` — fresh, stale, boundary, custom threshold, empty, sorting
- `load_manifest()` — file loading
- CLI — `--json` flag output, exit codes
