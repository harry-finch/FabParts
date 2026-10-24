"""Native harness safety checks, without a UI or real process signals."""

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest


@pytest.fixture
def harness() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[1]
        / "prototypes/fabparts-tech-01/scripts/check-native-lifecycle.py"
    )
    spec = importlib.util.spec_from_file_location("native_harness", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "parent,group,allowed", [(100, 200, True), (999, 200, False), (100, 100, False)]
)
def test_signal_requires_owned_isolated_engine(
    harness: ModuleType, monkeypatch: pytest.MonkeyPatch, parent: int, group: int, allowed: bool
) -> None:
    rows = {100: {"ppid": 10, "pgid": 10}, 200: {"ppid": parent, "pgid": group}}
    monkeypatch.setattr(harness, "processes", lambda: rows)
    monkeypatch.setattr(harness.os, "getpgid", lambda pid: group)
    signal_mock = Mock()
    monkeypatch.setattr(harness.os, "killpg", signal_mock)
    launcher = SimpleNamespace(pid=100, poll=lambda: None)
    if allowed:
        harness.signal_owned_engine(launcher, 100, 200)
    else:
        with pytest.raises(RuntimeError, match="no signal sent"):
            harness.signal_owned_engine(launcher, 100, 200)
    assert signal_mock.call_count == int(allowed)


def test_dev_parent_chain_and_unrelated_process(harness: ModuleType) -> None:
    rows = {100: {"ppid": 1}, 101: {"ppid": 100}, 102: {"ppid": 101}, 999: {"ppid": 1}}
    assert harness.descendant(102, 100, rows)
    assert not harness.descendant(999, 100, rows)


def test_log_parser_ignores_build_output_and_partial_json(
    harness: ModuleType, tmp_path: Path
) -> None:
    log = tmp_path / "runtime.log"
    log.write_text('Compiling…\n{"component":"fabparts-runtime","event":"ready"}\n{"component":')
    assert harness.events(log) == [{"component": "fabparts-runtime", "event": "ready"}]


def test_orphan_check_includes_previous_engine_groups(
    harness: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = {250: {"ppid": 1, "pgid": 200}}
    monkeypatch.setattr(harness, "processes", lambda: rows)
    ticks: Any = iter([0, 10])
    monkeypatch.setattr(harness.time, "monotonic", lambda: next(ticks))
    with pytest.raises(RuntimeError, match="Processes remaining"):
        harness.wait_no_orphans(100, {200, 300})
