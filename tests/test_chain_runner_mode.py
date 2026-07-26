"""Tests for --mode argument in chain_runner."""

import sys
from unittest.mock import patch

import pytest

sys.path.insert(
    0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "scripts")
)

from orchestration.chain_runner import build_parser, run_chain
from orchestration.session import SessionConfig


class TestChainRunnerModeArgparse:
    """Verify --mode argument is accepted and parsed correctly."""

    def _parse(self, args: list[str]):
        """Parse arguments through the production parser."""
        return build_parser().parse_args(["dummy.toml", *args])

    def test_mode_default_is_baseline(self):
        ns = self._parse([])
        assert ns.mode == "baseline"

    def test_mode_baseline(self):
        ns = self._parse(["--mode", "baseline"])
        assert ns.mode == "baseline"

    def test_mode_mcp_only(self):
        ns = self._parse(["--mode", "mcp_only"])
        assert ns.mode == "mcp_only"

    def test_mode_hybrid(self):
        ns = self._parse(["--mode", "hybrid"])
        assert ns.mode == "hybrid"

    @pytest.mark.parametrize(
        "mode",
        ["mcp_code_finder", "mcp_assisted", "cli", "cli_code_finder"],
    )
    def test_extended_modes(self, mode: str):
        ns = self._parse(["--mode", mode])
        assert ns.mode == mode

    def test_mode_invalid_rejected(self):
        with pytest.raises(SystemExit):
            self._parse(["--mode", "invalid_mode"])

    def test_mode_coexists_with_simulate(self):
        ns = self._parse(["--mode", "hybrid", "--simulate"])
        assert ns.mode == "hybrid"
        assert ns.simulate is True


class TestRunChainModePassthrough:
    """Verify run_chain propagates mode to SessionConfig objects."""

    def test_mode_propagated_to_sessions(self):
        s1 = SessionConfig(session_number=1, prompt="do stuff")
        s2 = SessionConfig(session_number=2, prompt="more stuff")
        assert s1.mode == "baseline"
        assert s2.mode == "baseline"

        from dataclasses import dataclass, field

        @dataclass
        class FakeTaskDef:
            task_id: str = "test-task"
            suite: str = "test"
            difficulty: str = "easy"
            session_count: int = 2
            repos: list = field(
                default_factory=lambda: [{"path": "repo1", "url": "x", "rev": "y"}]
            )
            sessions: list = field(default_factory=list)
            final_checkpoints: list = field(default_factory=list)
            metadata: dict = field(default_factory=dict)
            simulation: dict = field(default_factory=dict)

        task_def = FakeTaskDef(sessions=[s1, s2])

        # run_chain with mode="hybrid" — we expect it to set mode on sessions
        # before running. We mock run_session to avoid actual execution.
        with patch("orchestration.chain_runner.run_session") as mock_run:
            from orchestration.session import SessionResult

            mock_run.return_value = SessionResult(session_number=1, success=True)
            try:
                run_chain(task_def=task_def, simulate=True, mode="hybrid")
            except Exception:
                pass  # may fail on workspace setup, but mode should be set

        assert s1.mode == "hybrid"
        assert s2.mode == "hybrid"

    def test_session_config_mode_field_default(self):
        sc = SessionConfig(session_number=1, prompt="test")
        assert sc.mode == "baseline"

    def test_session_config_mode_field_custom(self):
        sc = SessionConfig(session_number=1, prompt="test", mode="mcp_only")
        assert sc.mode == "mcp_only"
