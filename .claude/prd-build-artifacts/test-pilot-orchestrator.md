# Test Results: pilot-orchestrator

## pytest tests/test_pilot_orchestrator.py -v

- 32 passed in 0.03s
- All test classes pass: ManifestLoading, ManifestStructure, AccountRoundRobin, OutputPaths, AblationDetection, RunManifestCreation, SummaryCSV, DryRun, FrozenDataclasses

## python3 scripts/orchestration/run_pilot.py --help

- Shows usage with --manifest flag (required), --dry-run, --max-parallel

## Manifest entry count

- `python3 -c "import json; m=json.load(open('configs/pilot_manifest.json')); print(len(m))"` outputs 48

## Dry-run verification

- `python3 scripts/orchestration/run_pilot.py --manifest configs/pilot_manifest.json --dry-run` completes successfully
- Writes results/phase1_pilot/run_manifest.json (19420 bytes)
- Writes results/phase1_pilot/summary.csv (2832 bytes)
- Reports: 48 total, 0 completed, 0 failed, 48 dry-run

## Acceptance Criteria Checklist

- [x] scripts/orchestration/run_pilot.py exists
- [x] --help shows usage with --manifest flag
- [x] configs/pilot_manifest.json exists with exactly 48 entries
- [x] Entries include task_id, mode, rep_index, account_id fields
- [x] Output paths follow results/runs/<task_id>/<mode>/rep<N>/ convention
- [x] pytest tests pass
- [x] Orchestrator writes results/phase1_pilot/run_manifest.json
