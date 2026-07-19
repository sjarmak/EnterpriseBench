"""Invariants for the rryas curated 3-arm candidate manifest.

Everything the manifest depends on is RE-DERIVED from the live corpus (a static read of
``gate_analysis.json`` would rubber-stamp stale evidence, same reasoning as the
scorer-guard doctrine: a verdict is valid only if the pristine verifier ran):
  * gates 2+3+4: ``analyzer.analyze`` re-runs the source-file heuristic, the prompt-echo
    attack, and the expected_solution consistency checks per manifest task — a drift in
    any gate flips ``all_pass`` and fails here. (An earlier mtime "staleness" guard was
    removed: git does not version mtimes, so on a fresh clone it passed vacuously — the
    exact CI environment where drift lands. Live re-derivation is the honest guard.)
  * the per-vector class scan (ozbjt freebie / v9okc patch-grep) is re-run per task. NB:
    the test re-runs the SAME heuristic detector curate() used, so it is a regression
    tripwire, not an independent oracle — a freebie shape the detector cannot recognize
    passes both. The independent guard against reward-hacking is the pilot's
    "baseline does not trivially win" criterion (see MANIFEST.md);
  * the name-set lookup is re-queried live from ``bd`` and matched to the committed
    snapshot, so a ``bd`` outage fails LOUD rather than reading as "no task named".

The committed ``gate_analysis.json`` supplies only the task LIST/metadata (suite, type);
its cached verdicts are ignored — ``analyze`` recomputes them. Metadata drift is caught
by the sync test.

Guards, per the architect + reviewer findings folded into MANIFEST.md.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "results" / "rryas_dataset"
MANIFEST = OUT_DIR / "candidate_manifest.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses resolves cls.__module__ via sys.modules
    spec.loader.exec_module(mod)
    return mod


analyzer = _load_module(
    "curated_gate_analyzer",
    REPO_ROOT / "scripts" / "validation" / "curated_gate_analyzer.py",
)
curator = _load_module(
    "curate_rryas_manifest",
    REPO_ROOT / "scripts" / "validation" / "curate_rryas_manifest.py",
)


def _manifest_task_ids() -> list[str]:
    if not MANIFEST.exists():
        # allow_module_level: this runs at import time, before any test function.
        pytest.skip("candidate_manifest.json not generated; run curate_rryas_manifest.py",
                    allow_module_level=True)
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["task_ids"]


MANIFEST_IDS = _manifest_task_ids()

# task_id -> pool dict (task LIST/metadata only; analyze() recomputes every gate verdict).
_POOL_BY_ID = {t["task_id"]: t
               for t in json.loads((OUT_DIR / "gate_analysis.json").read_text(encoding="utf-8"))}


def test_manifest_nonempty_and_bounded():
    # The candidate set is the full verified-clean survivor pool; it must not be
    # empty, and if it ever exceeds the active corpus something is doubly-counted.
    assert MANIFEST_IDS, "candidate manifest is empty"
    assert len(MANIFEST_IDS) == len(set(MANIFEST_IDS)), "duplicate task ids in manifest"


@pytest.mark.parametrize("task_id", MANIFEST_IDS)
def test_candidate_rederives_all_pass(task_id):
    """RE-DERIVED live: re-run gates 2+3+4 (source heuristic, prompt-echo, expected_solution
    consistency) from the corpus; a drift in any gate flips all_pass and fails here."""
    task = _POOL_BY_ID.get(task_id)
    assert task is not None, f"{task_id}: absent from gate_analysis.json"
    result = analyzer.analyze(task)
    assert result.all_pass, (
        f"{task_id}: re-derived gates no longer all-pass "
        f"(gate2_suspects={result.gate2_suspects}, gate3_pass={result.gate3_pass}, "
        f"gate4_pass={result.gate4_pass})"
    )


def _tdir(task_id: str) -> Path:
    """Suite-qualified task dir (matches analyze()'s resolution; avoids cross-suite id
    collisions). Fails the test loudly rather than passing None downstream."""
    task = _POOL_BY_ID.get(task_id)
    assert task is not None, f"{task_id}: absent from gate_analysis.json"
    tdir = curator.task_dir(task_id, task["suite"])
    assert tdir is not None, f"{task_id}: task dir not resolvable in suite {task['suite']}"
    return tdir


@pytest.mark.parametrize("task_id", MANIFEST_IDS)
def test_candidate_has_no_freebie_or_patchgrep(task_id):
    """RE-DERIVED per-vector class scan for the ozbjt/v9okc mechanisms."""
    tdir = _tdir(task_id)
    assert curator.freebie_checks(tdir) == [], f"{task_id}: ozbjt freebie mechanism present"
    assert curator.patch_checks(tdir) == [], f"{task_id}: v9okc patch-grep mechanism present"


@pytest.mark.parametrize("task_id", MANIFEST_IDS)
def test_candidate_is_md_report_and_multirepo(task_id):
    """Retrieval-necessity (>=2 repos) + the md-report-only scope the study is limited to."""
    tdir = _tdir(task_id)
    deliverables = analyzer.deliverable_paths(tdir)
    assert deliverables, f"{task_id}: no deliverable declared"
    assert all(d.endswith(".md") for d in deliverables), \
        f"{task_id}: non-md deliverable {deliverables} (JSON deliverables are excluded, 639lv)"
    assert _POOL_BY_ID[task_id]["repos"] >= 2, \
        f"{task_id}: single-repo task cannot separate the arms (repos={_POOL_BY_ID[task_id]['repos']})"


def test_committed_snapshot_has_no_manifest_overlap():
    """Hermetic: the committed finding-named snapshot must not name any candidate."""
    snapshot = json.loads((OUT_DIR / "exclusions.json").read_text(encoding="utf-8"))
    named = set().union(*snapshot["finding_named_snapshot"].values())
    overlap = named & set(MANIFEST_IDS)
    assert not overlap, f"candidates named by an open integrity finding: {sorted(overlap)}"


def test_live_finding_lookup_names_no_candidate():
    """RE-DERIVED + fail-loud: re-query bd (a bd outage raises FindingLookupError here,
    never a vacuous pass) and assert the LIVE named set overlaps no candidate. Asserts the
    invariant that matters rather than exact snapshot equality, so an unrelated edit to a
    finding bead's prose does not break CI — only a finding that actually names a candidate
    does."""
    live = set().union(*curator.finding_named_sets().values())  # raises if bd unavailable
    overlap = live & set(MANIFEST_IDS)
    assert not overlap, f"live bd finding names a candidate: {sorted(overlap)}"


def test_committed_manifest_and_exclusions_in_sync_with_curation():
    """The committed manifest AND exclusion-reason map must equal what curate() derives."""
    result = curator.curate()
    fresh = {r["task_id"] for r in result["eligible"]}
    committed = set(MANIFEST_IDS)
    assert committed == fresh, (
        f"manifest drift: committed-only={sorted(committed - fresh)} "
        f"fresh-only={sorted(fresh - committed)}; re-run curate_rryas_manifest.py"
    )
    fresh_excl = {r["task_id"]: r["reason"] for r in result["exclusions"]}
    committed_excl = {t["task_id"]: t["reason"]
                      for t in json.loads((OUT_DIR / "exclusions.json").read_text(
                          encoding="utf-8"))["tasks"]}
    assert committed_excl == fresh_excl, "exclusions.json reason attribution drifted"


_EXCLUDED = json.loads((OUT_DIR / "exclusions.json").read_text(encoding="utf-8"))
_EXCLUDED_IDS = [t["task_id"] for t in _EXCLUDED["tasks"]]
_SNAPSHOT_NAMED = set().union(*_EXCLUDED["finding_named_snapshot"].values())


@pytest.mark.parametrize("task_id", _EXCLUDED_IDS)
def test_excluded_task_still_belongs_excluded(task_id):
    """RE-DERIVED for the EXCLUDED set too (not just eligible): curate() reads gate
    verdicts from the committed gate_analysis.json, so a task whose checks were fixed to
    all-pass could stay excluded forever with a stale reason and no test would notice.
    Re-derive gates live; if a committed-excluded task now all-passes AND carries neither a
    class-scan mechanism nor a finding name, it should have been promoted to eligible."""
    task = _POOL_BY_ID.get(task_id)
    assert task is not None, f"{task_id}: absent from gate_analysis.json"
    if not analyzer.analyze(task).all_pass:
        return  # legitimately excluded by a gate — nothing stale
    tdir = curator.task_dir(task_id, task["suite"])
    class_excluded = bool(curator.freebie_checks(tdir) or curator.patch_checks(tdir))
    assert class_excluded or task_id in _SNAPSHOT_NAMED, (
        f"{task_id} re-derives all-pass and is neither class- nor finding-excluded; it "
        f"belongs in the eligible pool but is committed as excluded — regenerate "
        f"gate_analysis.json and re-run curate_rryas_manifest.py"
    )
