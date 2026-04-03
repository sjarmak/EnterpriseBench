# Test Results: sg-indexing-fix

## Test Run

- **Date**: 2026-04-02
- **Command**: `python3 -m pytest tests/test_sg_indexing_list.py tests/test_verify_sg_indexing.py -v`
- **Result**: 49 passed in 0.21s

## Breakdown

### tests/test_sg_indexing_list.py (22 tests)

All existing tests pass, including regeneration consistency check.

### tests/test_verify_sg_indexing.py (27 tests)

- TestComputeSummary: 10 passed (total, indexed, pending, per-suite, empty, edge cases)
- TestFormatSummary: 3 passed (header, totals, suite breakdown)
- TestFormatJson: 3 passed (valid JSON, structure, repos)
- TestLoadIndex: 2 passed (valid file, nonexistent file)
- TestCLI: 6 passed (real index, json output, check-api stub, custom path, missing path, help)
- TestDataclassImmutability: 3 passed (all frozen dataclasses)
