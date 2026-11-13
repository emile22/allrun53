from pathlib import Path
import os
import shutil
import subprocess

import pytest

from green.netconf_bridge import set_netconf_trace_enabled, write_operational_snapshot
from green.netconf_trace import _energy_object_inventory
from green.simulator import generate_events
from run import _wsl_project_path


def test_provider_trace_path_switches_sessions_and_preserves_old_log(tmp_path: Path) -> None:
    prefix: list[str] = []
    if os.name == "nt":
        if not shutil.which("wsl.exe"):
            pytest.skip("WSL is unavailable")
        prefix = ["wsl.exe", "-e"]
        if subprocess.run([*prefix, "true"], capture_output=True).returncode != 0:
            pytest.skip("WSL is unavailable")
    elif not shutil.which("bash"):
        pytest.skip("bash is unavailable")

    script = Path(__file__).parents[1] / "scripts" / "wsl-netconf-trace-path.sh"
    log_dir = _wsl_project_path(tmp_path.resolve())
    shared = tmp_path / "netconf-trace.log"
    shared.write_text("old shared trace\n", encoding="utf-8")
    first = tmp_path / "netconf-trace-first.log"
    second = tmp_path / "netconf-trace-second.log"
    first.write_text("first runtime\n", encoding="utf-8")
    second.write_text("second runtime\n", encoding="utf-8")

    def select_session(session: Path) -> None:
        subprocess.run(
            [*prefix, "bash", _wsl_project_path(script.resolve()), log_dir, session.name],
            check=True, capture_output=True,
        )

    def provider_write(content: bytes) -> None:
        subprocess.run(
            [*prefix, "tee", "-a", f"{log_dir}/netconf-trace.log"],
            input=content, check=True, capture_output=True,
        )

    try:
        select_session(first)
        provider_write(b"first NETCONF reply\n")
        assert shared.read_text(encoding="utf-8") == "first runtime\nfirst NETCONF reply\n"
        invalid = subprocess.run(
            [*prefix, "bash", _wsl_project_path(script.resolve()), log_dir, "../other.log"],
            capture_output=True,
        )
        assert invalid.returncode != 0
        assert shared.read_text(encoding="utf-8") == "first runtime\nfirst NETCONF reply\n"
        select_session(second)
        provider_write(b"second NETCONF reply\n")
        assert first.read_text(encoding="utf-8") == "first runtime\nfirst NETCONF reply\n"
        assert second.read_text(encoding="utf-8") == "second runtime\nsecond NETCONF reply\n"
        archives = list(tmp_path.glob("netconf-trace-shared-*.log"))
        assert len(archives) == 1
        assert archives[0].read_text(encoding="utf-8") == "old shared trace\n"
    finally:
        subprocess.run([*prefix, "rm", "-f", f"{log_dir}/netconf-trace.log"], check=True)


def test_trace_inventory_displays_received_and_provided_power() -> None:
    rows = _energy_object_inventory(
        {
            "ietf-power-and-energy:energy-objects": {
                "energy-object": [
                    {
                        "id": "eo-router-a",
                        "source-component-id": "router-A",
                        "power": {"instantaneous-power-received": "340000"},
                    },
                    {
                        "id": "eo-router-b",
                        "source-component-id": "router-B",
                        "power": {"instantaneous-power-provided": "120000"},
                    },
                ]
            }
        },
        terminal_width=80,
    )

    assert rows is not None
    assert any("received=340000" in row for row in rows)
    assert any("provided=120000" in row for row in rows)


def test_trace_mode_logs_all_group_a_runtime_snapshots(monkeypatch, tmp_path: Path):
    snapshot_path = tmp_path / "operational.json"
    trace_path = tmp_path / "netconf.log"
    monkeypatch.setenv("GREEN_NETCONF_TRACE_FILE", str(trace_path))
    set_netconf_trace_enabled(True, snapshot_path)
    try:
        events = generate_events()
        for event in events:
            write_operational_snapshot(event, snapshot_path)
        trace = trace_path.read_text(encoding="utf-8")
    finally:
        set_netconf_trace_enabled(False, snapshot_path)
        trace_path.unlink(missing_ok=True)
        snapshot_path.unlink(missing_ok=True)
        Path(f"{snapshot_path}.netconf-context").unlink(missing_ok=True)
        Path(f"{snapshot_path}.netconf-trace-enabled").unlink(missing_ok=True)

        assert len(events) == 146
        assert trace.count("operation: runtime snapshot") == 146
    for event in events:
        assert event.sequence in trace
        assert f"{event.series.value} - " in trace
    assert "UC 2.16 - Network-level Cross Layer Energy Saving | U16-9" in trace
