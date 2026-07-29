"""Deep-link contract for publication trace evidence."""

from pathlib import Path


def test_console_applies_query_filters_and_selects_an_exact_run() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    ui = (repo_root / "scripts" / "analysis" / "rootcause_console_ui.js").read_text()

    assert "new URLSearchParams(window.location.search)" in ui
    assert 'setFilterFromQuery(params, "q", "q")' in ui
    assert 'setFilterFromQuery(params, "arm", "fmode")' in ui
    assert 'setFilterFromQuery(params, "harness", "fharness")' in ui
    assert 'params.get("run")' in ui
    assert "cell.run_id === requestedRun" in ui
    assert "renderDetail(CELLS[selectedIndex])" in ui


def test_tracked_console_inlines_the_current_deep_link_ui() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    ui = (repo_root / "scripts" / "analysis" / "rootcause_console_ui.js").read_text()
    console = (repo_root / "rootcause_console.html").read_text()

    assert "new URLSearchParams(window.location.search)" in ui
    assert "new URLSearchParams(window.location.search)" in console
