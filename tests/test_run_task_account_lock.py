from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "orchestration"))

import run_task as run_task_module  # noqa: E402
from headline_provider_capacity import (  # noqa: E402
    exclusive_provider_account_locks,
)


def test_standalone_task_holds_all_provider_accounts(
    monkeypatch,
) -> None:
    config = SimpleNamespace(account=3, judge_account=1)
    events: list[object] = []

    @contextmanager
    def lock_factory(accounts: set[int]):
        events.append(("locked", accounts))
        yield
        events.append("unlocked")

    monkeypatch.setattr(
        run_task_module,
        "run_task",
        lambda _config: events.append("run") or "result",
    )

    result = run_task_module._run_task_with_provider_locks(
        config,
        environ={},
        lock_factory=lock_factory,
    )

    assert result == "result"
    assert events == [("locked", {1, 3}), "run", "unlocked"]


def test_dispatch_child_reuses_exact_parent_account_locks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = SimpleNamespace(account=3, judge_account=1)
    lock_called = False

    @contextmanager
    def forbidden_lock(_accounts: set[int]):
        nonlocal lock_called
        lock_called = True
        yield

    monkeypatch.setattr(run_task_module, "run_task", lambda _config: "result")

    with exclusive_provider_account_locks({1, 3}, lock_dir=tmp_path) as lock_fds:
        marker = ",".join(
            f"{account}:{lock_fds[account]}" for account in sorted(lock_fds)
        )
        result = run_task_module._run_task_with_provider_locks(
            config,
            environ={"ENTERPRISEBENCH_PROVIDER_ACCOUNT_LOCK_FDS": marker},
            lock_factory=forbidden_lock,
            lock_dir=tmp_path,
        )

    assert result == "result"
    assert lock_called is False


def test_dispatch_child_rejects_incomplete_parent_lock_marker() -> None:
    config = SimpleNamespace(account=3, judge_account=1)

    try:
        run_task_module._run_task_with_provider_locks(
            config,
            environ={"ENTERPRISEBENCH_PROVIDER_ACCOUNT_LOCK_FDS": "3:999"},
        )
    except RuntimeError as exc:
        assert "does not cover" in str(exc)
    else:
        raise AssertionError("incomplete parent account locks must fail closed")


def test_dispatch_child_rejects_forged_lock_descriptors(
    tmp_path: Path,
) -> None:
    config = SimpleNamespace(account=3, judge_account=1)

    try:
        run_task_module._run_task_with_provider_locks(
            config,
            environ={
                "ENTERPRISEBENCH_PROVIDER_ACCOUNT_LOCK_FDS": "1:998,3:999"
            },
            lock_dir=tmp_path,
        )
    except RuntimeError as exc:
        assert "not verifiable" in str(exc)
    else:
        raise AssertionError("forged lock descriptors must fail closed")
