"""Deep-link contract for publication trace evidence."""

import json
from pathlib import Path
import re


def test_console_applies_query_filters_and_selects_an_exact_run() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    ui = (repo_root / "scripts" / "analysis" / "rootcause_console_ui.js").read_text()

    assert "new URLSearchParams(window.location.search)" in ui
    assert 'setFilterFromQuery(params, "q", "q")' in ui
    assert 'setFilterFromQuery(params, "arm", "fmode")' in ui
    assert 'setFilterFromQuery(params, "harness", "fharness")' in ui
    assert 'params.get("trial")' in ui
    assert "cell.trial_key === requestedTrial" in ui
    assert "trialMatches.length === 1" in ui
    assert 'params.get("run")' in ui
    assert "cell.run_id === requestedRun" in ui
    assert "renderDetail(CELLS[selectedIndex])" in ui


def test_tracked_console_inlines_the_current_deep_link_ui() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    ui = (repo_root / "scripts" / "analysis" / "rootcause_console_ui.js").read_text()
    console = (repo_root / "rootcause_console.html").read_text()

    assert "new URLSearchParams(window.location.search)" in ui
    assert "new URLSearchParams(window.location.search)" in console
    assert 'params.get("trial")' in console
    assert "cell.trial_key === requestedTrial" in console


def test_tracked_console_has_unique_keys_for_every_locked_study_cell() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    console = (repo_root / "rootcause_console.html").read_text()
    match = re.search(
        r'<script id="data" type="application/json">(.*?)</script>',
        console,
        re.DOTALL,
    )
    assert match is not None
    cells = json.loads(match.group(1))
    locked = [
        cell
        for cell in cells
        if all(
            cell.get(field) for field in ("study_id", "task", "mode", "rep", "attempt")
        )
    ]
    trial_keys = [cell.get("trial_key") for cell in locked]

    assert locked
    assert all(isinstance(trial_key, str) and trial_key for trial_key in trial_keys)
    assert len(trial_keys) == len(set(trial_keys))
