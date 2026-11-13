from pathlib import Path
from contextlib import redirect_stdout
import sys
from datetime import datetime
from types import SimpleNamespace

import pytest

import green.cli as cli
from green.__main__ import main, run_demo
from green.models import EventSeries
from green.simulator import EventSimulator
import run
from run import _set_netconf_session_trace, run_with_trace


@pytest.fixture(autouse=True)
def stub_netconf_trace_redirection(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(run, "_set_netconf_session_trace", lambda _project_dir, _trace_path: True)
    monkeypatch.setattr(cli, "set_netconf_trace_enabled", lambda _enabled: tmp_path / "trace.log")
    monkeypatch.setattr(
        run,
        "generate_run_reports",
        lambda *_args, **_kwargs: (Path("implementation.md"), Path("tests.md")),
    )
    monkeypatch.setattr(
        run, "run_with_trace",
        lambda command, *, cwd, env, trace_log, stdin=None: run.subprocess.run(
            command, cwd=cwd, env=env, stdin=stdin, check=False,
        ).returncode,
    )


def run_with_commands(commands: list[str], **kwargs):
    command_iterator = iter(commands)
    output: list[str] = []
    sleep_calls: list[float] = []
    run_demo(
        EventSimulator(),
        auto=False,
        interval=1.0,
        input_fn=lambda: next(command_iterator),
        sleep_fn=sleep_calls.append,
        output_fn=output.append,
        **kwargs,
    )
    return output, sleep_calls


def event_lines(output: list[str]) -> list[str]:
    return [line for line in output if line.startswith("[UC ")]


@pytest.mark.parametrize("flag", ["-t", "--trace"])
@pytest.mark.parametrize("entrypoint", [run.main, main])
def test_removed_trace_options_are_rejected(flag, entrypoint) -> None:
    with pytest.raises(SystemExit) as error:
        entrypoint([flag])
    assert error.value.code == 2


def test_netconf_recording_continues_when_live_view_is_toggled() -> None:
    states: list[bool] = []
    snapshots: list[list[bool]] = []
    commands = iter(["", "d", "", "d", "", "q"])
    run_demo(
        EventSimulator(), auto=False, interval=0,
        input_fn=lambda: next(commands), sleep_fn=lambda _: None,
        output_fn=lambda _: None,
        snapshot_fn=lambda _event: snapshots.append(states.copy()),
        trace_fn=lambda enabled: states.append(enabled) or Path("trace.log"),
    )
    assert snapshots == [[True], [True], [True]]
    assert states == [True, False]


def test_netconf_log_contains_snapshots_before_and_after_live_view_toggle(monkeypatch, tmp_path) -> None:
    from green.netconf_bridge import set_netconf_trace_enabled, write_operational_snapshot

    snapshot_path = tmp_path / "operational.json"
    trace_path = tmp_path / "netconf.log"
    monkeypatch.setenv("GREEN_NETCONF_TRACE_FILE", str(trace_path))
    commands = iter(["", "d", "", "d", "", "q"])
    run_demo(
        EventSimulator(), auto=False, interval=0,
        input_fn=lambda: next(commands), sleep_fn=lambda _: None,
        output_fn=lambda _: None,
        snapshot_fn=lambda event: write_operational_snapshot(event, snapshot_path),
        trace_fn=lambda enabled: set_netconf_trace_enabled(enabled, snapshot_path),
    )
    assert trace_path.read_text(encoding="utf-8").count("operation: runtime snapshot") == 3


def test_enter_advances_exactly_one_group_a_event() -> None:
    output, sleep_calls = run_with_commands(["", "q"], snapshot_fn=None)
    assert any(line.startswith("Enter next UC | ") for line in output)
    assert event_lines(output) == ["[UC 2.1-Incremental / U1-0] LEGACY_BASELINE"]
    assert any(line.startswith("HW     ") for line in output)
    assert any(line.startswith("ENERGY ") for line in output)
    assert any(line.startswith("REL    ") for line in output)
    assert any(line.startswith("DIFF   ") for line in output)
    assert not any(len(line) >= 79 and set(line) == {"-"} for line in output)
    assert sleep_calls == []


def test_a_runs_remaining_events_across_all_uc_boundaries() -> None:
    output, sleep_calls = run_with_commands(["", "a"], snapshot_fn=None)
    events = event_lines(output)
    assert len(events) == 146
    assert events[0] == "[UC 2.1-Incremental / U1-0] LEGACY_BASELINE"
    assert events[-1] == "[UC 2.17-AI Agents / U17-7] SIMULATED_OUTCOME_CLOSED"
    assert len(sleep_calls) == 144
    assert "UCs executed: 17/17" in output
    assert "Events executed: 146 (minimum 146)" in output
    assert "FILL_IN_GAP entries: 8 (UC 2.17=3, UC 2.3=2, UC 2.4=1, UC 2.9=1, cross-cutting=1)" in output
    assert "UCs omitted: 0" in output
    assert sum(line.startswith("--- UC ") for line in output) == 17
    assert sum(" complete -> UC " in line for line in output) == 16


def test_q_exits_without_advancing() -> None:
    output, _ = run_with_commands(["q"], snapshot_fn=None)
    assert "GREEN allrun53 demo stopped." in output
    assert event_lines(output) == []


def test_d_toggles_trace_without_advancing_event() -> None:
    states: list[bool] = []
    commands = iter(["d", "", "d", "q"])
    output: list[str] = []
    run_demo(
        EventSimulator(),
        auto=False,
        interval=0,
        input_fn=lambda: next(commands),
        sleep_fn=lambda _: None,
        output_fn=output.append,
        snapshot_fn=None,
        trace_fn=lambda enabled: states.append(enabled) or Path("trace.log"),
    )
    assert states == [True, False]
    assert event_lines(output) == ["[UC 2.1-Incremental / U1-0] LEGACY_BASELINE"]
    assert any("NETCONF live view enabled" in line for line in output)
    assert any("NETCONF live view disabled" in line for line in output)


def test_netconf_recording_starts_before_first_event() -> None:
    states: list[bool] = []
    snapshots: list[list[bool]] = []
    output: list[str] = []
    commands = iter([None, "q"])
    main(
        ["--auto", "--interval", "0"],
        input_fn=lambda: pytest.fail("auto mode must not prompt between events"),
        poll_input_fn=lambda: next(commands),
        sleep_fn=lambda _: None,
        output_fn=output.append,
        snapshot_fn=lambda _event: snapshots.append(states.copy()),
        trace_fn=lambda enabled: states.append(enabled) or Path("trace.log"),
    )
    assert snapshots == [[True]]
    assert states == [True, False]


def test_netconf_recording_logs_all_runtime_snapshots(monkeypatch, tmp_path) -> None:
    from green.netconf_bridge import set_netconf_trace_enabled, write_operational_snapshot

    snapshot_path = tmp_path / "operational.json"
    trace_path = tmp_path / "netconf.log"
    monkeypatch.setenv("GREEN_NETCONF_TRACE_FILE", str(trace_path))
    output: list[str] = []
    commands = iter(["d"])
    main(
        ["--auto", "--interval", "0"],
        input_fn=lambda: pytest.fail("auto mode must not prompt between events"),
        poll_input_fn=lambda: next(commands, None),
        sleep_fn=lambda _: None,
        output_fn=output.append,
        snapshot_fn=lambda event: write_operational_snapshot(event, snapshot_path),
        trace_fn=lambda enabled: set_netconf_trace_enabled(enabled, snapshot_path),
    )
    assert trace_path.read_text(encoding="utf-8").count("operation: runtime snapshot") == 146
    assert sum(line.startswith("NETCONF TRACE\n") for line in output) == 146


def test_auto_mode_honors_d_and_q_commands() -> None:
    interactive_commands = iter(["", "a"])
    auto_commands = iter(["d", "q"])
    states: list[bool] = []
    output: list[str] = []
    run_demo(
        EventSimulator(),
        auto=False,
        interval=0,
        input_fn=lambda: next(interactive_commands),
        poll_input_fn=lambda: next(auto_commands, None),
        sleep_fn=lambda _: None,
        output_fn=output.append,
        snapshot_fn=None,
        trace_fn=lambda enabled: states.append(enabled) or Path("trace.log"),
    )

    assert len(event_lines(output)) == 2
    assert states == [True, False]
    assert any("NETCONF live view enabled" in line for line in output)
    assert any("GREEN allrun53 demo stopped." in line for line in output)
    assert any("Automatic mode enabled (q quit, d trace, n restart, +/- change UC)." in line for line in output)
    assert not any("Events executed:" in line for line in output)


def test_auto_mode_n_restarts_at_first_uc_and_continues() -> None:
    interactive_commands = iter(["", "a"])
    auto_commands = iter(["n", "n", None, "q"])
    output: list[str] = []
    snapshots = []
    run_demo(
        EventSimulator(),
        auto=False,
        interval=0,
        input_fn=lambda: next(interactive_commands),
        poll_input_fn=lambda: next(auto_commands, None),
        sleep_fn=lambda _: None,
        output_fn=output.append,
        snapshot_fn=snapshots.append,
    )

    assert [event.sequence for event in snapshots] == ["U1-0", "U1-0"]
    assert "Simulator restarted at UC 2.1 / U1-0 (run #2)." in output
    assert "Simulator restarted at UC 2.1 / U1-0 (run #3)." in output
    assert "GREEN allrun53 demo stopped." in output


def test_plus_and_minus_change_uc_from_the_first_event() -> None:
    commands = iter(["", "+", "", "-", "", "q"])
    output: list[str] = []
    snapshots = []
    run_demo(
        EventSimulator(),
        auto=False,
        interval=0,
        input_fn=lambda: next(commands),
        sleep_fn=lambda _: None,
        output_fn=output.append,
        snapshot_fn=snapshots.append,
    )

    assert [event.sequence for event in snapshots] == ["U1-0", "U2-0", "U1-0"]
    assert "Switched to UC 2.2; starting at its first event." in output
    assert "Switched to UC 2.1; starting at its first event." in output


def test_auto_mode_plus_changes_uc_and_reports_only_executed_events() -> None:
    polls = iter(["+", None, "q"])
    output: list[str] = []
    snapshots = []
    main(
        ["--auto", "--interval", "0"],
        poll_input_fn=lambda: next(polls, None),
        sleep_fn=lambda _: None,
        output_fn=output.append,
        snapshot_fn=snapshots.append,
    )

    assert [event.sequence for event in snapshots] == ["U2-0"]
    assert "Switched to UC 2.2; starting at its first event." in output


def test_uc_navigation_limits_emit_directional_indicators() -> None:
    first_output, _ = run_with_commands(["-", "q"], snapshot_fn=None)
    last_output: list[str] = []
    run_demo(
        EventSimulator(use_case=EventSeries.UC_2_17),
        auto=False,
        interval=0,
        input_fn=iter(["+", "q"]).__next__,
        sleep_fn=lambda _: None,
        output_fn=last_output.append,
        snapshot_fn=None,
    )

    assert any("LIMIT: - Already at the first UC (UC 2.1)." in line for line in first_output)
    assert "LIMIT: + Already at the last UC (UC 2.17)." in last_output


def test_navigating_and_finishing_reports_actual_run_coverage() -> None:
    commands = iter(["+", "a"])
    output: list[str] = []
    run_demo(
        EventSimulator(),
        auto=False,
        interval=0,
        input_fn=lambda: next(commands),
        poll_input_fn=lambda: None,
        sleep_fn=lambda _: None,
        output_fn=output.append,
        snapshot_fn=None,
    )

    assert "UCs executed: 16/17" in output
    assert "Events executed: 138" in output
    assert "UCs omitted: 1" in output


def test_gaps_view_reports_registered_entries_without_advancing() -> None:
    output, _ = run_with_commands(["gaps", "q"], snapshot_fn=None)

    assert event_lines(output) == []
    assert any('"gap_count": 8' in line for line in output)
    assert any('"UC 2.3": 2' in line for line in output)


def test_r_resets_catalog_state_and_restarts_at_uc21() -> None:
    output, _ = run_with_commands(["", "r", "", "q"], snapshot_fn=None)
    assert event_lines(output) == [
        "[UC 2.1-Incremental / U1-0] LEGACY_BASELINE",
        "[UC 2.1-Incremental / U1-0] LEGACY_BASELINE",
    ]
    assert "Simulator restarted at UC 2.1 / U1-0 (run #2)." in output


def test_human_and_raw_views_do_not_advance_the_event() -> None:
    commands = iter(["", "summary", "relationships", "json", "xml", "diff", "q"])
    output: list[str] = []
    run_demo(
        EventSimulator(),
        auto=False,
        interval=0,
        input_fn=lambda: next(commands),
        sleep_fn=lambda _: None,
        output_fn=output.append,
        snapshot_fn=None,
        xml_fn=lambda: "<rpc-reply><data/></rpc-reply>",
    )
    assert event_lines(output) == ["[UC 2.1-Incremental / U1-0] LEGACY_BASELINE"]
    assert any("1. HARDWARE INVENTORY" in line for line in output)
    assert any("3. ENERGY RELATIONSHIPS" in line for line in output)
    assert any('"ietf-power-and-energy:energy-objects"' in line for line in output)
    assert "<rpc-reply><data/></rpc-reply>" in output
    assert any("No previous event" in line for line in output)


def test_auto_main_runs_every_event_and_writes_every_snapshot() -> None:
    output: list[str] = []
    snapshots = []
    trace_states: list[bool] = []
    main(
        ["--auto", "--interval", "0"],
        input_fn=lambda: (_ for _ in ()).throw(AssertionError("auto requested input")),
        sleep_fn=lambda _: None,
        output_fn=output.append,
        snapshot_fn=snapshots.append,
        trace_fn=lambda enabled: trace_states.append(enabled) or Path("trace.log"),
    )
    assert len(event_lines(output)) == 146
    assert len(snapshots) == 146
    assert snapshots[0].sequence == "U1-0"
    assert snapshots[-1].sequence == "U17-7"
    assert trace_states == [True, False]


def test_loop_count_repeats_full_automatic_run_and_resets_counters() -> None:
    output: list[str] = []
    snapshots = []
    main(
        ["-n", "2", "--interval", "0"],
        input_fn=lambda: (_ for _ in ()).throw(AssertionError("loop mode must be automatic")),
        poll_input_fn=lambda: None,
        sleep_fn=lambda _: None,
        output_fn=output.append,
        snapshot_fn=snapshots.append,
        trace_fn=lambda enabled: Path("trace.log"),
    )

    assert len(snapshots) == 292
    assert snapshots[0].sequence == snapshots[146].sequence == "U1-0"
    assert "Automatic loop 1 complete; restarting (run #2)." in output
    assert output.count("Events executed: 146 (minimum 146)") == 2


def test_finite_loop_limit_counts_manual_n_restarts() -> None:
    output: list[str] = []
    snapshots = []
    polls = iter(["n", "n", "n", "n", "n"])

    main(
        ["-n", "5", "--interval", "0"],
        poll_input_fn=lambda: next(polls, None),
        sleep_fn=lambda _: None,
        output_fn=output.append,
        snapshot_fn=snapshots.append,
        trace_fn=lambda _enabled: Path("trace.log"),
    )

    assert snapshots == []
    assert "Simulator restarted at UC 2.1 / U1-0 (run #5)." in output
    assert "Run limit #5 reached; stopping." in output
    assert not any("run #6" in line for line in output)


def test_loop_without_count_repeats_until_q() -> None:
    output: list[str] = []
    snapshots = []
    polls = 0

    def poll_input() -> str | None:
        nonlocal polls
        polls += 1
        return "q" if polls == 147 else None

    main(
        ["-n", "--interval", "0"],
        poll_input_fn=poll_input,
        sleep_fn=lambda _: None,
        output_fn=output.append,
        snapshot_fn=snapshots.append,
        trace_fn=lambda _enabled: Path("trace.log"),
    )

    assert len(snapshots) == 146
    assert "Automatic loop 1 complete; restarting (run #2)." in output
    assert "GREEN allrun53 demo stopped." in output
    assert not any("Events executed:" in line for line in output[output.index("GREEN allrun53 demo stopped."):])


def test_launcher_prefers_project_virtualenv(tmp_path: Path, monkeypatch) -> None:
    environment_dir = tmp_path / ".venv"
    local_python = environment_dir / (
        Path("Scripts") / "python.exe" if run.os.name == "nt" else Path("bin") / "python"
    )
    local_python.parent.mkdir(parents=True)
    local_python.touch()
    monkeypatch.setattr(run, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(run.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0))
    assert run.project_python() == str(local_python)


def test_launcher_falls_back_when_project_virtualenv_lacks_dependencies(tmp_path: Path, monkeypatch) -> None:
    environment_dir = tmp_path / ".venv"
    local_python = environment_dir / (
        Path("Scripts") / "python.exe" if run.os.name == "nt" else Path("bin") / "python"
    )
    local_python.parent.mkdir(parents=True)
    local_python.touch()
    monkeypatch.setattr(run, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(run.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=1))

    assert run.project_python() == sys.executable


@pytest.fixture
def isolated_launcher(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(run, "__file__", str(tmp_path / "run.py"))


@pytest.mark.parametrize(
    ("test_returncode", "runtime_returncode", "expected_returncode"),
    [(0, 0, 0), (0, 3, 3), (2, None, 2)],
)
def test_launcher_stops_services_on_every_exit(
    monkeypatch,
    isolated_launcher,
    test_returncode: int,
    runtime_returncode: int | None,
    expected_returncode: int,
) -> None:
    commands: list[list[str]] = []
    steps: list[str] = []

    def fake_run(command: list[str], **_kwargs):
        commands.append(command)
        if "pytest" in command:
            steps.append("pytest")
            return SimpleNamespace(returncode=test_returncode)
        if "green" in command:
            steps.append("runtime")
            return SimpleNamespace(returncode=runtime_returncode)
        steps.append("stop")
        return SimpleNamespace(returncode=0, stdout="stopped", stderr="")

    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: steps.append("start") or True)
    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "pause_for_review", lambda *_args: None)
    assert run.main([]) == expected_returncode
    assert steps[0] == "start" and steps[-1] == "stop"
    assert commands[-1][0] == "wsl.exe"
    assert "scripts/wsl-netconf-stop.sh" in commands[-1][-1]
    runtime_commands = [command for command in commands if "green" in command]
    assert len(runtime_commands) == int(test_returncode == 0)
    if runtime_commands:
        assert runtime_commands[0] == ["project-python", "-m", "green"]


def test_launcher_does_not_run_pytest_if_wsl_startup_fails(monkeypatch, isolated_launcher) -> None:
    stop_calls: list[str] = []

    def unexpected_subprocess(*_args, **_kwargs):
        raise AssertionError("pytest/runtime must not run when NETCONF startup fails")

    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: False)
    monkeypatch.setattr(run, "stop_netconf_services", lambda: stop_calls.append("stop"))
    monkeypatch.setattr(run.subprocess, "run", unexpected_subprocess)

    assert run.main([]) == 1
    assert stop_calls == ["stop"]


def test_launcher_stops_if_netconf_trace_redirection_fails(monkeypatch, tmp_path) -> None:
    stop_calls: list[str] = []
    monkeypatch.setattr(run, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: True)
    monkeypatch.setattr(run, "_set_netconf_session_trace", lambda _project_dir, _trace_path: False)
    monkeypatch.setattr(run, "stop_netconf_services", lambda: stop_calls.append("stop"))
    monkeypatch.setattr(run.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("must not run tests"))

    assert run.main([]) == 1
    assert stop_calls == ["stop"]
    assert list((tmp_path / "logs").glob("netconf-trace-*.log")) == []


def test_netconf_trace_redirection_reports_helper_failure(monkeypatch, tmp_path, capsys) -> None:
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=1, stdout="", stderr="link failed")

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    trace_path = tmp_path / "logs" / "netconf-trace-test.log"
    assert not _set_netconf_session_trace(tmp_path, trace_path)
    assert "wsl-netconf-trace-path.sh" in commands[0][-1]
    assert trace_path.name in commands[0][-1]
    assert "link failed" in capsys.readouterr().out


def test_launcher_always_records_console_output(monkeypatch, tmp_path, capsys) -> None:
    commands: list[list[str]] = []

    def fake_trace(command, **_kwargs):
        commands.append(command)
        print("test output" if "pytest" in command else "runtime output")
        print("diagnostic output", file=sys.stderr)
        return 0

    monkeypatch.setattr(run, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: print("startup") or True)
    monkeypatch.setattr(run, "stop_netconf_services", lambda: print("shutdown"))
    monkeypatch.setattr(run, "run_with_trace", fake_trace)
    monkeypatch.setattr(run, "pause_for_review", lambda *_args: None)

    assert run.main([]) == 0
    assert commands[0][:7] == [
        "project-python", "-m", "pytest", "-s", "-v", "-p", "no:green.pytest_rich"
    ]
    assert commands[0][7] == "--junitxml"
    assert Path(commands[0][8]).suffix == ".xml"
    assert commands[1] == ["project-python", "-m", "green"]
    captured = capsys.readouterr()
    output = captured.out
    logs = list((tmp_path / "logs").glob("allrun53-trace-*.log"))
    assert len(logs) == 1
    logged = logs[0].read_text(encoding="utf-8")
    assert "diagnostic output" in captured.err
    assert logged.count("diagnostic output") == 2
    assert all(text in output for text in ("startup", "test output", "runtime output", "shutdown"))
    assert all(text in logged for text in ("startup", "test output", "runtime output", "shutdown"))


def test_launcher_generates_reports_from_test_run_results(monkeypatch, tmp_path) -> None:
    report_calls: list[tuple[Path, Path | None]] = []

    def fake_trace(command, *, cwd, env, trace_log, stdin=None):
        if "pytest" in command:
            junit_xml_path = Path(command[command.index("--junitxml") + 1])
            junit_xml_path.write_text(
                '<testsuites><testsuite><testcase classname="tests.test_smoke" '
                'name="test_ok" /></testsuite></testsuites>',
                encoding="utf-8",
            )
        return 0

    def fake_generate(project_root: Path, *, junit_xml_path: Path | None, **_kwargs):
        report_calls.append((project_root, junit_xml_path))
        return (tmp_path / "implementation.md", tmp_path / "tests.md")

    monkeypatch.setattr(run, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: True)
    monkeypatch.setattr(run, "stop_netconf_services", lambda: None)
    monkeypatch.setattr(run, "run_with_trace", fake_trace)
    monkeypatch.setattr(run, "generate_run_reports", fake_generate)
    monkeypatch.setattr(run, "pause_for_review", lambda *_args: None)

    assert run.main([]) == 0
    assert len(report_calls) == 1
    project_root, junit_xml_path = report_calls[0]
    assert project_root == tmp_path
    assert junit_xml_path is not None
    assert not junit_xml_path.exists()


def test_launcher_uses_one_run_tag_for_logs_and_reports(monkeypatch, tmp_path) -> None:
    run_tags: list[str] = []

    def fake_generate(_project_root: Path, *, run_tag: str, **_kwargs):
        run_tags.append(run_tag)
        return (tmp_path / "implementation.md", tmp_path / "tests.md")

    def fake_summary(_project_root: Path, *, run_tag: str, **_kwargs):
        run_tags.append(run_tag)
        return tmp_path / "summary.md"

    monkeypatch.setattr(run, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: True)
    monkeypatch.setattr(run, "stop_netconf_services", lambda: None)
    monkeypatch.setattr(run, "_set_netconf_session_trace", lambda _project_dir, _trace_path: True)
    monkeypatch.setattr(run, "run_with_trace", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(run, "generate_run_reports", fake_generate)
    monkeypatch.setattr(run, "generate_power_and_energy_run_summary", fake_summary)
    monkeypatch.setattr(run, "pause_for_review", lambda *_args: None)

    assert run.main([]) == 0
    console_trace = next((tmp_path / "logs").glob("allrun53-trace-*.log"))
    netconf_trace = next((tmp_path / "logs").glob("netconf-trace-*.log"))
    run_tag = console_trace.stem.removeprefix("allrun53-trace-")
    assert netconf_trace.name == f"netconf-trace-{run_tag}.log"
    assert run_tags == [run_tag, run_tag]


def test_launcher_defaults_to_interactive_runtime(monkeypatch, tmp_path, isolated_launcher) -> None:
    commands: list[list[str]] = []
    working_directories: list[Path | None] = []
    runtime_pythonpaths: list[str] = []

    def fake_run(command: list[str], **kwargs):
        commands.append(command)
        working_directories.append(kwargs.get("cwd"))
        if "green" in command:
            runtime_pythonpaths.append(kwargs["env"]["PYTHONPATH"])
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: True)
    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "pause_for_review", lambda *_args: None)

    assert run.main([]) == 0
    assert commands[0][:7] == [
        "project-python", "-m", "pytest", "-s", "-v", "-p", "no:green.pytest_rich"
    ]
    assert commands[0][7] == "--junitxml"
    assert commands[1] == ["project-python", "-m", "green"]
    project_dir = Path(run.__file__).resolve().parent
    assert working_directories[:2] == [project_dir, project_dir]
    assert runtime_pythonpaths[0].split(run.os.pathsep)[0] == run.project_source
    assert len(list((tmp_path / "logs").glob("netconf-trace-*.log"))) == 1


def test_launcher_logs_tests_and_runtime(monkeypatch, tmp_path) -> None:
    commands: list[list[str]] = []

    def fake_trace(command, *, cwd, env, trace_log, stdin=None):
        commands.append(command)
        trace_log.write("test output\n" if "pytest" in command else "runtime output\n")
        return 0

    monkeypatch.setattr(run, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: True)
    monkeypatch.setattr(run, "stop_netconf_services", lambda: None)
    monkeypatch.setattr(run, "run_with_trace", fake_trace)
    monkeypatch.setattr(run, "pause_for_review", lambda *_args: None)

    assert run.main([]) == 0
    assert commands[0][:7] == [
        "project-python", "-m", "pytest", "-s", "-v", "-p", "no:green.pytest_rich"
    ]
    assert commands[0][7] == "--junitxml"
    assert commands[1] == ["project-python", "-m", "green"]
    trace_files = list((tmp_path / "logs").glob("allrun53-trace-*.log"))
    assert len(trace_files) == 1
    content = trace_files[0].read_text(encoding="utf-8")
    assert "test output\n" in content and "runtime output\n" in content


@pytest.mark.parametrize(
    ("arguments", "expected_runtime"),
    [
        (["--interactive"], []),
        (["--auto", "-n", "2", "--interval", "0"],
         ["--auto", "--interval", "0.0", "--loops", "2"]),
    ],
)
def test_launcher_logging_preserves_runtime_modes(monkeypatch, tmp_path, arguments, expected_runtime) -> None:
    commands: list[list[str]] = []

    def fake_trace(command, **_kwargs):
        commands.append(command)
        return 0

    monkeypatch.setattr(run, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: True)
    monkeypatch.setattr(run, "stop_netconf_services", lambda: None)
    monkeypatch.setattr(run, "run_with_trace", fake_trace)
    monkeypatch.setattr(run, "pause_for_review", lambda *_args: None)

    assert run.main(arguments) == 0
    assert commands[1] == ["project-python", "-m", "green", *expected_runtime]


def test_launcher_creates_distinct_timestamped_logs(monkeypatch, tmp_path) -> None:
    log_names: list[str] = []

    def fake_trace(command, *, cwd, env, trace_log, stdin=None):
        if "pytest" in command:
            log_names.append(trace_log.name)
            trace_log.write(f"session {len(log_names)}\n")
        return 0

    monkeypatch.setattr(run, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(run, "datetime", SimpleNamespace(now=lambda: datetime(2026, 11, 8, 14, 30, 45)))
    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: True)
    monkeypatch.setattr(run, "stop_netconf_services", lambda: None)
    monkeypatch.setattr(run, "run_with_trace", fake_trace)
    monkeypatch.setattr(run, "pause_for_review", lambda *_args: None)

    assert run.main([]) == 0
    assert run.main([]) == 0
    trace_files = sorted((tmp_path / "logs").glob("allrun53-trace-2026-11-08_14-30-45*.log"))
    assert [path.name for path in trace_files] == [
        "allrun53-trace-2026-11-08_14-30-45-2.log",
        "allrun53-trace-2026-11-08_14-30-45.log",
    ]
    assert all(any(f"session {index}\n" in path.read_text(encoding="utf-8") for path in trace_files) for index in (1, 2))
    netconf_files = list((tmp_path / "logs").glob("netconf-trace-2026-11-08_14-30-45*.log"))
    assert len(netconf_files) == 2
    assert {path.name.removeprefix("allrun53-trace-") for path in trace_files} == {
        path.name.removeprefix("netconf-trace-") for path in netconf_files
    }


def test_launcher_skips_run_name_with_existing_netconf_log(monkeypatch, tmp_path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    existing_netconf = log_dir / "netconf-trace-2026-11-08_14-30-45.log"
    existing_netconf.write_text("existing NETCONF data\n", encoding="utf-8")

    monkeypatch.setattr(run, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(run, "datetime", SimpleNamespace(now=lambda: datetime(2026, 11, 8, 14, 30, 45)))
    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: True)
    monkeypatch.setattr(run, "stop_netconf_services", lambda: None)
    monkeypatch.setattr(run, "run_with_trace", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(run, "pause_for_review", lambda *_args: None)

    assert run.main([]) == 0
    assert existing_netconf.read_text(encoding="utf-8") == "existing NETCONF data\n"
    assert not (log_dir / "allrun53-trace-2026-11-08_14-30-45.log").exists()
    assert (log_dir / "allrun53-trace-2026-11-08_14-30-45-2.log").is_file()
    assert (log_dir / "netconf-trace-2026-11-08_14-30-45-2.log").is_file()


@pytest.mark.parametrize("arguments", [[], ["--auto"]])
def test_launcher_creates_distinct_netconf_session_logs(monkeypatch, tmp_path, arguments) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    source = log_dir / "netconf-trace.log"
    source.write_text("previous session\n", encoding="utf-8")
    runtime_count = 0

    def fake_run(command, *, cwd, env, **kwargs):
        nonlocal runtime_count
        session_trace = Path(env["GREEN_NETCONF_TRACE_FILE"])
        assert session_trace.parent == log_dir
        assert session_trace != source
        if "green" in command:
            runtime_count += 1
            with session_trace.open("a", encoding="utf-8") as stream:
                stream.write(f"runtime {runtime_count}\nNETCONF get {runtime_count}\n")
        return SimpleNamespace(returncode=0)

    def fake_trace(command, *, cwd, env, trace_log, stdin=None):
        return fake_run(command, cwd=cwd, env=env).returncode

    monkeypatch.setattr(run, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(run, "datetime", SimpleNamespace(now=lambda: datetime(2026, 11, 8, 14, 30, 45)))
    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: True)
    monkeypatch.setattr(run, "stop_netconf_services", lambda: None)
    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "run_with_trace", fake_trace)
    monkeypatch.setattr(run, "pause_for_review", lambda *_args: None)

    assert run.main(arguments) == 0
    assert run.main(arguments) == 0
    files = list(log_dir.glob("netconf-trace-2026-11-08_14-30-45*.log"))
    assert len(files) == 2
    assert {path.read_text(encoding="utf-8") for path in files} == {
        "runtime 1\nNETCONF get 1\n", "runtime 2\nNETCONF get 2\n",
    }
    assert source.read_text(encoding="utf-8") == "previous session\n"


def test_run_with_trace_streams_stdout_and_stderr(tmp_path, capsys) -> None:
    trace_path = tmp_path / "session.log"
    with trace_path.open("w", encoding="utf-8") as trace_log:
        result = run_with_trace(
            [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)"],
            cwd=tmp_path, env={**run.os.environ, "PYTHONIOENCODING": "utf-8"},
            trace_log=trace_log,
        )
    assert result == 0
    assert set(trace_path.read_text(encoding="utf-8").splitlines()) == {"out", "err"}
    assert set(capsys.readouterr().out.splitlines()) == {"out", "err"}


def test_subprocess_output_is_not_duplicated_in_console_log(tmp_path, capsys) -> None:
    trace_path = tmp_path / "session.log"
    with trace_path.open("w", encoding="utf-8") as trace_log:
        with redirect_stdout(run.ConsoleTee(sys.stdout, trace_log)):
            result = run_with_trace(
                [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)"],
                cwd=tmp_path, env={**run.os.environ, "PYTHONIOENCODING": "utf-8"},
                trace_log=trace_log,
            )
    assert result == 0
    assert sorted(trace_path.read_text(encoding="utf-8").splitlines()) == ["err", "out"]
    assert sorted(capsys.readouterr().out.splitlines()) == ["err", "out"]


def test_launcher_preserves_failure_output_and_skips_runtime(monkeypatch, tmp_path) -> None:
    commands: list[list[str]] = []

    def fake_trace(command, *, cwd, env, trace_log, stdin=None):
        commands.append(command)
        trace_log.write("test failure\n")
        return 2

    monkeypatch.setattr(run, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: True)
    monkeypatch.setattr(run, "stop_netconf_services", lambda: None)
    monkeypatch.setattr(run, "run_with_trace", fake_trace)
    monkeypatch.setattr(run, "pause_for_review", lambda *_args: None)

    assert run.main([]) == 2
    assert len(commands) == 1 and "pytest" in commands[0]
    trace_files = list((tmp_path / "logs").glob("allrun53-trace-*.log"))
    assert len(trace_files) == 1
    assert "test failure\n" in trace_files[0].read_text(encoding="utf-8")


def test_launcher_auto_mode_can_run_without_delay(monkeypatch, isolated_launcher) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: True)
    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "pause_for_review", lambda *_args: None)

    assert run.main(["--auto", "--interval", "0"]) == 0
    assert commands[1] == [
        "project-python", "-m", "green", "--auto", "--interval", "0.0"
    ]


def test_launcher_passes_finite_loop_count_to_runtime(monkeypatch, isolated_launcher) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: True)
    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "pause_for_review", lambda *_args: None)

    assert run.main(["-n", "3", "--interval", "0"]) == 0
    assert commands[1] == [
        "project-python", "-m", "green", "--auto", "--interval", "0.0",
        "--loops", "3",
    ]


def test_launcher_passes_unbounded_loop_mode_to_runtime(monkeypatch, isolated_launcher) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: True)
    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "pause_for_review", lambda *_args: None)

    assert run.main(["-n"]) == 0
    assert commands[1] == [
        "project-python", "-m", "green", "--auto", "--loops", "0"
    ]


def test_launcher_passes_selected_uc_to_runtime(monkeypatch, capsys, isolated_launcher) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "ensure_netconf_services", lambda force=False: True)
    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "pause_for_review", lambda *_args: None)

    assert run.main(["-u", "2.13", "--auto", "--interval", "0"]) == 0
    stop_command = run._wsl_command(
        Path(run.__file__).resolve().parent,
        "bash scripts/wsl-netconf-stop.sh",
    )
    assert commands == [
        [
            "project-python", "-m", "green", "--auto", "--interval", "0.0",
            "--uc", "2.13",
        ],
        stop_command,
    ]
    output = capsys.readouterr().out
    assert "Skipping full pytest suite for selected UC 2.13" in output
    assert "All tests passed" not in output


@pytest.mark.parametrize("flag", ["-f", "--force"])
def test_launcher_passes_force_flag_to_netconf_setup(monkeypatch, flag, isolated_launcher) -> None:
    force_values: list[bool] = []
    monkeypatch.setattr(
        run,
        "ensure_netconf_services",
        lambda force=False: force_values.append(force) or False,
    )
    monkeypatch.setattr(run, "stop_netconf_services", lambda: None)

    assert run.main([flag]) == 1
    assert force_values == [True]


@pytest.mark.parametrize("arguments", [["--auto"], ["-n", "1"]])
def test_unattended_launcher_authorizes_setup_without_prompts(monkeypatch, arguments, isolated_launcher) -> None:
    force_values: list[bool] = []

    def fake_ensure(force=False):
        force_values.append(force)
        return True

    monkeypatch.setattr(run, "ensure_netconf_services", fake_ensure)
    monkeypatch.setattr(run, "stop_netconf_services", lambda: None)
    monkeypatch.setattr(run, "project_python", lambda: "project-python")
    monkeypatch.setattr(run, "run_with_trace", lambda command, **_kwargs: 1 if "pytest" in command else 0)
    monkeypatch.setattr(
        run, "pause_for_review",
        lambda *_args: pytest.fail("unattended runs must not wait for ENTER"),
    )

    assert run.main(arguments) == 1
    assert force_values == [True]

    monkeypatch.setattr(run, "run_with_trace", lambda *_args, **_kwargs: 0)
    assert run.main(arguments) == 0


def test_netconf_health_check_waits_for_wsl_boot(monkeypatch) -> None:
    commands: list[str] = []

    def fake_run(command: list[str], **_kwargs):
        commands.append(command[-1])
        return SimpleNamespace(returncode=0, stdout="101\n202\n", stderr="")

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "_start_wsl_keepalive", lambda: True)

    assert run.ensure_netconf_services()
    boot_wait = next(index for index, command in enumerate(commands) if "is-system-running --wait" in command)
    health_check = next(index for index, command in enumerate(commands) if "systemctl is-active" in command)
    assert boot_wait < health_check


def test_allrun53_netconf_ready_display_includes_process_pids_and_siblings(monkeypatch, capsys) -> None:
    commands: list[list[str]] = []
    monkeypatch.delenv("ALLRUN53_ALLOW_HOST_CONFIG", raising=False)

    def fake_run(command: list[str], **_kwargs):
        commands.append(command)
        if "systemctl is-active" in command[-1]:
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        if "wsl-netconf-start.sh" in command[-1]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="101\n202\n", stderr="")

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "_start_wsl_keepalive", lambda: True)

    assert run.ensure_netconf_services()
    output = capsys.readouterr().out
    assert "WSL NETCONF ready (Netopeer2 TCP/830)." in output
    assert "WSL service PIDs: sysrepo-plugind=101, netopeer2=202." in output
    assert "eo-router-a/router-A" in output
    assert "eo-router-a-linecard-1/linecard-1" in output
    assert "eo-router-a-linecard-2/linecard-2" in output
    assert "[siblings]" in output
    assert any("sysrepo-plugind.service" in command[-1] for command in commands)
    assert any("SYSREPO_REPOSITORY_PATH=/var/lib/grmis/allrun53/sysrepo" in command[-1] for command in commands)
    assert any(
        "bash scripts/wsl-netconf-start.sh" in command[-1]
        and "ALLRUN53_ALLOW_HOST_CONFIG" not in command[-1]
        for command in commands
    )


def test_netconf_start_forwards_only_explicit_host_config_opt_in(monkeypatch) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs):
        commands.append(command)
        if "systemctl is-active" in command[-1]:
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setenv("ALLRUN53_ALLOW_HOST_CONFIG", "1")
    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "_start_wsl_keepalive", lambda: True)

    assert run.ensure_netconf_services()
    assert any(
        "ALLRUN53_ALLOW_HOST_CONFIG=1 bash scripts/wsl-netconf-start.sh" in command[-1]
        for command in commands
    )


@pytest.mark.parametrize("force", [False, True])
def test_netconf_start_retries_only_after_authorization_denial(monkeypatch, capsys, force) -> None:
    commands: list[list[str]] = []
    monkeypatch.delenv("ALLRUN53_ALLOW_HOST_CONFIG", raising=False)
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: "y" if not force else (_ for _ in ()).throw(
            AssertionError("--force must not prompt")
        ),
    )

    def fake_run(command: list[str], **_kwargs):
        commands.append(command)
        if "systemctl is-active" in command[-1]:
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        if "ALLRUN53_ALLOW_HOST_CONFIG=1" in command[-1]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "wsl-netconf-start.sh" in command[-1]:
            return SimpleNamespace(
                returncode=3,
                stdout="",
                stderr="Rerun with ALLRUN53_ALLOW_HOST_CONFIG=1",
            )
        return SimpleNamespace(returncode=0, stdout="101\n202\n", stderr="")

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "_start_wsl_keepalive", lambda: True)

    assert run.ensure_netconf_services(force=force)
    assert sum("wsl-netconf-start.sh" in command[-1] for command in commands) == 2
    assert "Restarting WSL NETCONF startup with the explicit host-config opt-in." in capsys.readouterr().out


def test_netconf_start_does_not_prompt_for_active_stack_conflict(monkeypatch, capsys) -> None:
    commands: list[list[str]] = []
    monkeypatch.delenv("ALLRUN53_ALLOW_HOST_CONFIG", raising=False)
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: (_ for _ in ()).throw(AssertionError("must not prompt for conflict")),
    )

    def fake_run(command: list[str], **_kwargs):
        commands.append(command)
        if "systemctl is-active" in command[-1]:
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        return SimpleNamespace(
            returncode=2,
            stdout="",
            stderr="Refusing to replace another active NETCONF stack",
        )

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(run, "_start_wsl_keepalive", lambda: True)

    assert not run.ensure_netconf_services()
    assert sum("wsl-netconf-start.sh" in command[-1] for command in commands) == 1
    assert "WSL NETCONF startup failed with exit 2." in capsys.readouterr().out


def test_windows_netconf_run_holds_and_releases_wsl_session(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []
    lifecycle: list[str] = []

    class FakeStdin:
        def close(self) -> None:
            lifecycle.append("stdin-closed")

    class FakeProcess:
        stdin = FakeStdin()

        def poll(self) -> None:
            return None

        def wait(self, timeout: float) -> None:
            lifecycle.append(f"waited-{timeout}")

    process = FakeProcess()

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        calls.append((command, kwargs))
        return process

    monkeypatch.setattr(run, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(run, "_wsl_keepalive", None)
    monkeypatch.setattr(run.subprocess, "Popen", fake_popen)

    assert run._start_wsl_keepalive()
    assert calls == [
        (
            ["wsl.exe", "--exec", "/bin/cat"],
            {
                "stdin": run.subprocess.PIPE,
                "stdout": run.subprocess.DEVNULL,
                "stderr": run.subprocess.DEVNULL,
                "creationflags": getattr(run.subprocess, "CREATE_NO_WINDOW", 0),
            },
        )
    ]

    run._stop_wsl_keepalive()
    assert lifecycle == ["stdin-closed", "waited-5"]
    assert run._wsl_keepalive is None
