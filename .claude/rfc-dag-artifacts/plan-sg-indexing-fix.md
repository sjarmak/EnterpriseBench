# Plan: sg-indexing-fix

## Step 1: Update configs/sg_indexing_list.json

- Add `repos` list within each suite entry containing repo references with `_indexed` status
- Recompute `_indexed_count` from per-repo `_indexed` values (currently all false, so stays 0)
- Keep the flat `repos` array as the source of truth

## Step 2: Create scripts/infra/verify_sg_indexing.py

- Read `configs/sg_indexing_list.json`
- Iterate all repos, count indexed vs pending
- Per-suite breakdown using `_suites` field from repo entries
- Summary output: total, indexed, pending, per-suite
- `--check-api` flag stub for future SG API verification
- Proper argparse with `--help`

## Step 3: Write tests

- Test JSON loading and parsing
- Test summary computation logic
- Test per-suite breakdown
- Test `--check-api` stub behavior
- Test edge cases (empty suites, repos without suites)
