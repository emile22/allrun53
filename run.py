import argparse
import codecs
import io
import os
import shlex
import subprocess
import sys
import tempfile
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from textwrap import wrap
from typing import TextIO

_wsl_keepalive: subprocess.Popen | None = None

project_source = str(Path(__file__).resolve().parent / "src")
if project_source not in sys.path:
    sys.path.insert(0, project_source)

from green.cli import SUPPORTED_USE_CASE_IDS, parse_use_case
from green.run_reports import (
    generate_power_and_energy_run_summary,
    generate_run_reports,
)
from green.topology import demo_energy_objects


def project_python() -> str:
    environment_dir = Path(__file__).resolve().parent / ".venv"
    relative_executable = (
        Path("Scripts") / "python.exe" if os.name == "nt" else Path("bin") / "python"
    )
    local_python = environment_dir / relative_executable
    if not local_python.is_file():
        return sys.executable
    dependencies = subprocess.run(
        [str(local_python), "-c", "import pytest, ncclient, pyang"],
        check=False,
        capture_output=True,
        text=True,
    )
    return str(local_python) if dependencies.returncode == 0 else sys.executable


def _create_run_trace(log_dir: Path) -> tuple[TextIO, Path, str]:
    base_tag = f"{datetime.now():%Y-%m-%d_%H-%M-%S}"
    attempt = 1
    while True:
        run_tag = base_tag if attempt == 1 else f"{base_tag}-{attempt}"
        trace_path = log_dir / f"allrun53-trace-{run_tag}.log"
        if not (log_dir / f"netconf-trace-{run_tag}.log").exists():
            try:
                return trace_path.open("x", encoding="utf-8"), trace_path, run_tag
            except FileExistsError:
                pass
        attempt += 1


def pause_for_review(message: str, input_fn: Callable[[str], str]) -> None:
    try:
        input_fn(message)
    except EOFError:
        pass


class ConsoleTee:
    def __init__(self, console: TextIO, log: TextIO) -> None:
        self.console = console
        self.log = log

    def write(self, text: str) -> int:
        count = self.console.write(text)
        self.log.write(text)
        self.log.flush()
        return count

    def flush(self) -> None:
        self.console.flush()
        self.log.flush()

    def __getattr__(self, name: str):
        return getattr(self.console, name)


def run_with_trace(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    trace_log: TextIO,
    stdin=None,
) -> int:
    with subprocess.Popen(
        command, cwd=cwd, env=env, stdin=stdin,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    ) as process:
        assert process.stdout is not None
        console = sys.stdout.console if isinstance(sys.stdout, ConsoleTee) else sys.stdout
        decoder = io.IncrementalNewlineDecoder(
            codecs.getincrementaldecoder("utf-8")(errors="replace"), translate=True
        )
        while chunk := process.stdout.read1(8192):
            text = decoder.decode(chunk)
            console.write(text)
            console.flush()
            trace_log.write(text)
            trace_log.flush()
        text = decoder.decode(b"", final=True)
        console.write(text)
        console.flush()
        trace_log.write(text)
        trace_log.flush()
        return process.wait()


def _wsl_command(project_dir: Path, shell_command: str) -> list[str]:
    if os.name == "nt":
        project_path = _wsl_project_path(project_dir)
        command = f"cd {shlex.quote(project_path)} && {shell_command}"
        return ["wsl.exe", "-e", "bash", "-lc", command]
    return ["bash", "-lc", f"cd {shlex.quote(str(project_dir))} && {shell_command}"]


def _wsl_project_path(project_dir: Path) -> str:
    if os.name == "nt":
        drive = project_dir.drive[0].lower()
        return f"/mnt/{drive}{project_dir.as_posix()[2:]}"
    return str(project_dir)


def _set_netconf_session_trace(project_dir: Path, trace_path: Path) -> bool:
    wsl_logs = f"{_wsl_project_path(project_dir)}/logs"
    command = (
        "bash scripts/wsl-netconf-trace-path.sh "
        f"{shlex.quote(wsl_logs)} {shlex.quote(trace_path.name)}"
    )
    try:
        result = subprocess.run(
            _wsl_command(project_dir, command), check=False, capture_output=True, text=True,
        )
    except OSError as error:
        print(f"Could not set NETCONF session trace: {error}")
        return False
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0:
        print(f"Could not set NETCONF session trace: {result.stderr.strip()}")
        return False
    return True


def _start_wsl_keepalive() -> bool:
    global _wsl_keepalive
    if os.name != "nt":
        return True
    if _wsl_keepalive is not None:
        if _wsl_keepalive.poll() is None:
            return True
        _wsl_keepalive = None

    try:
        _wsl_keepalive = subprocess.Popen(
            ["wsl.exe", "--exec", "/bin/cat"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as error:
        print(f"Could not keep WSL session alive: {error}")
        return False

    if _wsl_keepalive.poll() is not None:
        print("Could not keep WSL session alive: wsl.exe exited immediately.")
        _wsl_keepalive = None
        return False
    return True


def _stop_wsl_keepalive() -> None:
    global _wsl_keepalive
    process = _wsl_keepalive
    _wsl_keepalive = None
    if process is None:
        return

    try:
        if process.stdin is not None:
            process.stdin.close()
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def _hardware_component_ties() -> list[str]:
    objects = demo_energy_objects()
    object_ids_by_name = {
        item.hardware_component_name: item.energy_object_id for item in objects
    }
    children_by_parent: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for item in objects:
        if item.hardware_parent_name and item.hardware_component_name:
            children_by_parent[item.hardware_parent_name].append(
                (item.hardware_component_name, item.energy_object_id)
            )

    lines = []
    for parent, children in sorted(children_by_parent.items()):
        child_names = ", ".join(f"{object_id}/{name}" for name, object_id in children)
        sibling_label = " [siblings]" if len(children) > 1 else ""
        parent_id = object_ids_by_name.get(parent, "unmapped")
        lines.append(f"{parent_id}/{parent} -> {child_names}{sibling_label}")
    return lines


def _print_netconf_ready(project_dir: Path) -> None:
    pid_command = (
        "printf '%s\\n' "
        "\"$(systemctl show sysrepo-plugind.service -p MainPID --value)\" "
        "\"$(systemctl show netopeer2.service -p MainPID --value)\""
    )
    try:
        result = subprocess.run(
            _wsl_command(project_dir, pid_command),
            check=False,
            capture_output=True,
            text=True,
        )
        pids = result.stdout.splitlines() if result.returncode == 0 else []
    except OSError:
        pids = []
    sysrepo_pid = pids[0].strip() if len(pids) > 0 else "unknown"
    netopeer_pid = pids[1].strip() if len(pids) > 1 else "unknown"
    print("WSL NETCONF ready (Netopeer2 TCP/830).")
    print(f"WSL service PIDs: sysrepo-plugind={sysrepo_pid}, netopeer2={netopeer_pid}.")
    ties = _hardware_component_ties()
    if ties:
        print("Hardware component ties (Energy Object ID/component; parent/siblings):")
        for tie in ties:
            for line in wrap(
                tie,
                width=88,
                subsequent_indent="    ",
                break_long_words=False,
                break_on_hyphens=False,
            ):
                print(line)


def _refresh_reports(
    project_dir: Path,
    junit_xml_path: Path | None,
    *,
    run_tag: str,
    not_run_reason: str | None = None,
    netconf_status: str = "NOT_EVALUATED",
) -> None:
    report_time = datetime.now().astimezone()
    implementation_report, test_report = generate_run_reports(
        project_dir,
        junit_xml_path=junit_xml_path,
        test_command="python -m pytest -s -v -p no:green.pytest_rich",
        not_run_reason=not_run_reason,
        now=report_time,
        run_tag=run_tag,
    )
    print(f"Reports updated: {implementation_report} and {test_report}")
    summary_report = generate_power_and_energy_run_summary(
        project_dir,
        junit_xml_path=junit_xml_path,
        test_command="python -m pytest -s -v -p no:green.pytest_rich",
        netconf_status=netconf_status,
        not_run_reason=not_run_reason,
        now=report_time,
        run_tag=run_tag,
    )
    print(f"Current-run summary updated: {summary_report}")


def _wait_for_wsl_boot(project_dir: Path) -> None:
    # Boot-enabled NETCONF units crash-loop until systemd gives up; checking earlier trips the active-stack guard.
    try:
        subprocess.run(
            _wsl_command(project_dir, "systemctl is-system-running --wait"),
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"Warning: could not wait for WSL boot to finish: {error}")


def ensure_netconf_services(force: bool = False) -> bool:
    if not _start_wsl_keepalive():
        return False
    project_dir = Path(__file__).resolve().parent
    _wait_for_wsl_boot(project_dir)
    wsl_project = _wsl_project_path(project_dir)
    expected_environment = (
        "SYSREPO_REPOSITORY_PATH=/var/lib/grmis/allrun53/sysrepo",
        "SYSREPO_SHM_PREFIX=gr53",
        f"SRPD_PLUGINS_PATH={wsl_project}/netconf/plugins",
        f"GREEN_NETCONF_STATE_FILE={wsl_project}/runtime/operational.json",
        f"GREEN_NETCONF_TRACE_FILE={wsl_project}/logs/netconf-trace.log",
    )
    environment_check = " && ".join(
        f"systemctl show-environment | grep -Fx {shlex.quote(value)}"
        for value in expected_environment
    )
    health_check = (
        "systemctl is-active --quiet sysrepo-plugind.service && "
        "systemctl is-active --quiet netopeer2.service && "
        "ss -ltn | awk '$4 ~ /:830$/ { found=1 } END { exit !found }' && "
        "sysrepoctl -l | awk -F'|' '$1 ~ /^ietf-power-and-energy[[:space:]]/ { found=1 } END { exit !found }' && "
        f"{environment_check}"
    )
    try:
        health = subprocess.run(
            _wsl_command(project_dir, health_check),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        print(f"NETCONF infrastructure health check failed: {error}")
        return False

    if health.returncode == 0:
        _print_netconf_ready(project_dir)
        return True

    allow_host_config = os.environ.get("ALLRUN53_ALLOW_HOST_CONFIG") == "1"
    startup_command = "bash scripts/wsl-netconf-start.sh"
    if allow_host_config:
        startup_command = f"ALLRUN53_ALLOW_HOST_CONFIG=1 {startup_command}"

    try:
        startup = subprocess.run(
            _wsl_command(project_dir, startup_command),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        print(f"Could not start WSL NETCONF services: {error}")
        return False

    authorization_required = (
        startup.returncode == 3
        and "rerun with allrun53_allow_host_config=1" in startup.stderr.lower()
    )
    if authorization_required and not allow_host_config:
        if force:
            answer = "y"
        else:
            try:
                answer = input(
                    "WSL setup needs permission to configure native Sysrepo/Netopeer2. "
                    "Restart with ALLRUN53_ALLOW_HOST_CONFIG=1? [y/N]: "
                )
            except EOFError:
                answer = ""
        if answer.strip().lower() in {"y", "yes"}:
            print("Restarting WSL NETCONF startup with the explicit host-config opt-in.")
            try:
                startup = subprocess.run(
                    _wsl_command(
                        project_dir,
                        "ALLRUN53_ALLOW_HOST_CONFIG=1 bash scripts/wsl-netconf-start.sh",
                    ),
                    check=False,
                    capture_output=True,
                    text=True,
                )
            except OSError as error:
                print(f"Could not restart WSL NETCONF services: {error}")
                return False
        else:
            print("WSL NETCONF startup was not authorized; no host configuration was changed.")

    if startup.returncode != 0:
        print(f"WSL NETCONF startup failed with exit {startup.returncode}.")
        if startup.stdout.strip():
            print(startup.stdout.strip())
        if startup.stderr.strip():
            print(startup.stderr.strip())
        return False
    _print_netconf_ready(project_dir)
    return True


def stop_netconf_services() -> None:
    project_dir = Path(__file__).resolve().parent
    stop_script = project_dir / "scripts" / "wsl-netconf-stop.sh"
    if os.name == "nt":
        drive = project_dir.drive[0].lower()
        project_path = f"/mnt/{drive}{project_dir.as_posix()[2:]}"
        wsl_command = (
            f"cd {shlex.quote(project_path)} && bash scripts/wsl-netconf-stop.sh"
        )
        command = ["wsl.exe", "-e", "bash", "-lc", wsl_command]
    else:
        command = ["bash", str(stop_script)]

    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as error:
        print(f"Warning: could not stop NETCONF services: {error}")
        _stop_wsl_keepalive()
        return

    output = result.stdout.strip()
    if result.returncode == 0:
        if output:
            print(output)
        _stop_wsl_keepalive()
        return
    detail = result.stderr.strip() or output
    print(f"Warning: could not stop NETCONF services (exit {result.returncode}).")
    if detail:
        print(detail)
    _stop_wsl_keepalive()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test and run the GREEN allrun53 simulator")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--auto", dest="auto", action="store_true", help="run all events automatically without prompts")
    mode.add_argument("--interactive", dest="auto", action="store_false", help="prompt between events (default)")
    parser.set_defaults(auto=False)
    parser.add_argument("--interval", type=float, help="automatic-mode delay in seconds (default: 1)")
    parser.add_argument(
        "-n",
        "--loops",
        type=int,
        nargs="?",
        const=0,
        default=None,
        metavar="LOOPS",
        help="repeat the automatic run LOOPS times; omit the count to repeat forever",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="automatically authorize the WSL setup retry if requested (implied by --auto and -n); does not bypass active-stack guards",
    )
    parser.add_argument(
        "-u",
        "--uc",
        type=parse_use_case,
        metavar="UC",
        help=f"run only one implemented UC (available: {', '.join(SUPPORTED_USE_CASE_IDS)})",
    )
    args = parser.parse_args(argv)
    if args.interval is not None and args.interval < 0:
        parser.error("--interval must be non-negative")
    if args.loops is not None and args.loops < 0:
        parser.error("--loops must be non-negative; omit the count for infinite looping")

    project_dir = Path(__file__).resolve().parent
    unattended = args.auto or args.loops is not None
    log_dir = project_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    trace_log, trace_name, run_tag = _create_run_trace(log_dir)
    original_stdout, original_stderr = sys.stdout, sys.stderr
    sys.stdout = ConsoleTee(original_stdout, trace_log)
    sys.stderr = ConsoleTee(original_stderr, trace_log)
    try:
        print(f"Session trace: {trace_name}", flush=True)
        if not ensure_netconf_services(force=args.force or unattended):
            _refresh_reports(
                project_dir,
                None,
                run_tag=run_tag,
                not_run_reason="NETCONF startup failed before pytest ran.",
                netconf_status="NOT_READY",
            )
            print("Tests were not started because NETCONF infrastructure is unavailable.")
            return 1
        python = project_python()
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            path for path in (project_source, environment.get("PYTHONPATH", "")) if path
        )
        netconf_path = log_dir / f"netconf-trace-{run_tag}.log"
        try:
            netconf_path.touch(exist_ok=False)
        except OSError as error:
            _refresh_reports(
                project_dir,
                None,
                run_tag=run_tag,
                not_run_reason="NETCONF trace setup failed before pytest ran.",
                netconf_status="READY; trace setup failed",
            )
            print(f"Could not create NETCONF session trace: {error}")
            return 1
        if not _set_netconf_session_trace(project_dir, netconf_path):
            netconf_path.unlink(missing_ok=True)
            _refresh_reports(
                project_dir,
                None,
                run_tag=run_tag,
                not_run_reason="NETCONF trace setup failed before pytest ran.",
                netconf_status="READY; trace setup failed",
            )
            return 1
        environment["GREEN_NETCONF_TRACE_FILE"] = str(netconf_path)
        print(f"NETCONF session trace: {netconf_path}", flush=True)
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PYTHONUNBUFFERED"] = "1"
        if args.uc is None:
            with tempfile.TemporaryDirectory(prefix="allrun53-pytest-") as temp_dir:
                junit_xml_path = Path(temp_dir) / "results.xml"
                test_command = [
                    python, "-m", "pytest", "-s", "-v", "-p",
                    "no:green.pytest_rich", "--junitxml", str(junit_xml_path),
                ]
                test_returncode = run_with_trace(
                    test_command, stdin=subprocess.DEVNULL, cwd=project_dir,
                    env=environment, trace_log=trace_log,
                )
                _refresh_reports(
                    project_dir,
                    junit_xml_path if junit_xml_path.is_file() else None,
                    run_tag=run_tag,
                    not_run_reason=(
                        f"pytest exited {test_returncode} without JUnit results."
                    ),
                    netconf_status="READY",
                )
            if test_returncode != 0:
                if not unattended:
                    pause_for_review("\nTests failed. Press ENTER to review the trace...", input)
                return test_returncode
        else:
            _refresh_reports(
                project_dir,
                None,
                run_tag=run_tag,
                not_run_reason=f"Full pytest suite skipped for selected {args.uc.value}.",
                netconf_status="READY",
            )
            print(
                f"Skipping full pytest suite for selected {args.uc.value}; "
                "run python -m pytest separately after code changes.",
                flush=True,
            )

        if args.uc is None:
            print("\nAll tests passed. Starting the GREEN runtime...\n", flush=True)
        else:
            print(f"\nStarting selected {args.uc.value}...\n", flush=True)
        runtime_command = [python, "-m", "green"]
        if args.auto or args.loops is not None:
            runtime_command.append("--auto")
        if args.interval is not None:
            runtime_command.extend(("--interval", str(args.interval)))
        if args.loops is not None:
            runtime_command.extend(("--loops", str(args.loops)))
        if args.uc is not None:
            runtime_command.extend(("--uc", args.uc.value.removeprefix("UC ")))
        runtime_returncode = run_with_trace(
            runtime_command, cwd=project_dir, env=environment, trace_log=trace_log,
        )
        if not unattended:
            pause_for_review("\nGREEN runtime ended. Press ENTER to review the trace...", input)
        return runtime_returncode
    finally:
        try:
            stop_netconf_services()
        finally:
            sys.stdout, sys.stderr = original_stdout, original_stderr
            trace_log.close()


if __name__ == "__main__":
    raise SystemExit(main())