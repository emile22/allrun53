from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def _report_time(now: datetime | None) -> tuple[str, str]:
    value = now or datetime.now().astimezone()
    if value.tzinfo is None:
        value = value.astimezone()
    iso_value = value.isoformat(timespec="seconds")
    offset = value.strftime("%z")
    display_offset = f"{offset[:-2]}:{offset[-2:]}" if offset else ""
    display_value = value.strftime("%Y-%m-%d %H:%M:%S") + (
        f" {display_offset}" if display_offset else ""
    )
    return iso_value, display_value


def _report_paths(project_root: Path, run_tag: str | None) -> tuple[Path, Path]:
    suffix = f"_{run_tag}" if run_tag else ""
    reports_dir = project_root / "reports"
    return (
        reports_dir / f"ietf_power_and_energy_{project_root.name}{suffix}.md",
        reports_dir / f"test_report_{project_root.name}{suffix}.md",
    )


def _write_implementation_report(source: Path, destination: Path, now: datetime | None) -> None:
    if not source.is_file():
        return
    iso_value, display_value = _report_time(now)
    contents = source.read_text(encoding="utf-8")
    generated_line = (
        f'Generated: <time datetime="{iso_value}">{display_value}</time>'
    )
    updated, count = re.subn(
        r"(?m)^Generated: <time datetime=\"[^\"]+\">.*?</time>$",
        generated_line,
        contents,
        count=1,
    )
    if count == 0:
        first_heading, separator, remainder = contents.partition("\n")
        updated = f"{first_heading}\n\n{generated_line}\n{remainder}"
    destination.write_text(updated, encoding="utf-8", newline="\n")


def _test_file_link(classname: str) -> str:
    parts = classname.split(".")
    if not parts or parts[0] != "tests":
        parts.insert(0, "tests")
    target = "../" + "/".join(parts) + ".py"
    label = "/".join(parts) + ".py"
    return f"[{label}]({target})"


def _render_test_report(
    project_name: str,
    *,
    junit_xml_path: Path | None,
    test_command: str,
    not_run_reason: str | None,
    now: datetime | None,
) -> str:
    iso_value, display_value = _report_time(now)
    cases: list[ET.Element] = []
    if junit_xml_path is not None and junit_xml_path.is_file():
        cases = ET.parse(junit_xml_path).getroot().findall(".//testcase")

    failed_cases = [
        case
        for case in cases
        if case.find("failure") is not None or case.find("error") is not None
    ]
    skipped_cases = [case for case in cases if case.find("skipped") is not None]
    passed_count = len(cases) - len(failed_cases) - len(skipped_cases)
    duration = sum(float(case.get("time", "0")) for case in cases)
    by_module: dict[str, list[ET.Element]] = defaultdict(list)
    for case in cases:
        by_module[case.get("classname", "tests.unknown")].append(case)

    lines = [
        f"# Test Report: {project_name}",
        "",
        f'Generated: <time datetime="{iso_value}">{display_value}</time>',
        "",
        "## Stats",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        f"| Command | `{test_command}` |",
        f"| Total tests | {len(cases)} |",
        f"| Passed | {passed_count} |",
        f"| Failed | {len(failed_cases)} |",
        f"| Skipped | {len(skipped_cases)} |",
        f"| Test-case time | {duration:.2f} s |",
        "",
        "## Test List",
        "",
        "| Test module | Passed | Failed | Skipped |",
        "| --- | ---: | ---: | ---: |",
    ]
    for module, module_cases in sorted(by_module.items()):
        module_failed = sum(
            case.find("failure") is not None or case.find("error") is not None
            for case in module_cases
        )
        module_skipped = sum(case.find("skipped") is not None for case in module_cases)
        module_passed = len(module_cases) - module_failed - module_skipped
        lines.append(
            f"| {_test_file_link(module)} | {module_passed} | "
            f"{module_failed} | {module_skipped} |"
        )
    if not by_module:
        lines.append("| No test module ran | 0 | 0 | 0 |")

    lines.extend(["", "## Details", ""])
    if cases:
        lines.append(
            f"The offline test run collected {len(cases)} cases: "
            f"{passed_count} passed, {len(failed_cases)} failed, and "
            f"{len(skipped_cases)} skipped. Test-case time is the sum of "
            "JUnit case durations, not wall-clock suite time."
        )
        uc_count = sum(module.startswith("tests.uc.") for module in by_module)
        core_count = len(by_module) - uc_count
        lines.append(
            f"It includes {core_count} core test modules and {uc_count} use-case test modules."
        )
        if "--ignore=tests/netconf" in test_command:
            lines.append("The live `tests/netconf/` integration suite was excluded.")
        if failed_cases:
            lines.extend(["", "### Failures", ""])
            for case in failed_cases:
                result = case.find("failure")
                if result is None:
                    result = case.find("error")
                message = (result.get("message", "") if result is not None else "")
                lines.append(
                    f"- `{case.get('classname', 'unknown')}::"
                    f"{case.get('name', 'unknown')}`: {message or 'failed'}"
                )
    else:
        lines.append(
            "No test cases were collected. "
            f"{not_run_reason or 'The suite did not produce JUnit results.'}"
        )
    return "\n".join(lines) + "\n"


def generate_run_reports(
    project_root: Path,
    *,
    junit_xml_path: Path | None,
    test_command: str,
    not_run_reason: str | None = None,
    now: datetime | None = None,
    run_tag: str | None = None,
) -> tuple[Path, Path]:
    project_root = Path(project_root)
    report_time = now or datetime.now().astimezone()
    base_implementation_report, _ = _report_paths(project_root, None)
    implementation_report, test_report = _report_paths(project_root, run_tag)
    test_report.parent.mkdir(parents=True, exist_ok=True)
    # Tagged runs copy the curated base analysis so it is not rewritten per run.
    _write_implementation_report(base_implementation_report, implementation_report, report_time)
    test_report.write_text(
        _render_test_report(
            project_root.name,
            junit_xml_path=junit_xml_path,
            test_command=test_command,
            not_run_reason=not_run_reason,
            now=report_time,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return implementation_report, test_report


def generate_power_and_energy_run_summary(
    project_root: Path,
    *,
    junit_xml_path: Path | None,
    test_command: str,
    netconf_status: str,
    not_run_reason: str | None = None,
    now: datetime | None = None,
    run_tag: str | None = None,
) -> Path:
    project_root = Path(project_root)
    report_time = now or datetime.now().astimezone()
    iso_value, display_value = _report_time(report_time)
    timestamp = run_tag or report_time.strftime("%Y%m%d_%H%M%S")
    reports_dir = project_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = project_root / "install" / "yang-module-manifest.json"
    yang_revision = "UNKNOWN"
    yang_hash = "UNKNOWN"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        target_module = next(
            module
            for module in manifest.get("modules", [])
            if module.get("name") == "ietf-power-and-energy"
        )
        yang_revision = str(target_module.get("revision", "UNKNOWN"))
        yang_hash = str(target_module.get("sha256", "UNKNOWN"))
    except (OSError, ValueError, StopIteration, AttributeError, TypeError):
        pass

    cases: list[ET.Element] = []
    if junit_xml_path is not None and Path(junit_xml_path).is_file():
        cases = ET.parse(junit_xml_path).getroot().findall(".//testcase")
    failed_count = sum(case.find("failure") is not None for case in cases)
    error_count = sum(case.find("error") is not None for case in cases)
    skipped_count = sum(case.find("skipped") is not None for case in cases)
    passed_count = len(cases) - failed_count - error_count - skipped_count
    duration = sum(float(case.get("time", "0")) for case in cases)
    netconf_cases = [
        case
        for case in cases
        if case.get("classname", "").startswith("tests.netconf.")
    ]
    netconf_failed = sum(
        case.find("failure") is not None or case.find("error") is not None
        for case in netconf_cases
    )
    netconf_skipped = sum(case.find("skipped") is not None for case in netconf_cases)
    netconf_passed = len(netconf_cases) - netconf_failed - netconf_skipped
    test_status = "EXECUTED" if junit_xml_path is not None and Path(junit_xml_path).is_file() else "NOT_RUN"
    implementation_path, test_path = _report_paths(project_root, run_tag)
    implementation_report = implementation_path.name
    test_report = test_path.name
    implementation_link = (
        f"[{implementation_report}]({implementation_report})"
        if (reports_dir / implementation_report).is_file()
        else "NOT_FOUND"
    )
    test_link = (
        f"[{test_report}]({test_report})"
        if (reports_dir / test_report).is_file()
        else "NOT_FOUND"
    )

    lines = [
        f"# Current Power and Energy Run Summary: {project_root.name}",
        "",
        f'Generated: <time datetime="{iso_value}">{display_value}</time>',
        "",
        "## Scope",
        "",
        f"- Run directory: `{project_root}`",
        f"- YANG module: `ietf-power-and-energy@{yang_revision}`",
        f"- Manifest SHA-256: `{yang_hash}`",
        f"- NETCONF preflight: `{netconf_status}` (launcher setup result; not an interoperability claim)",
        "",
        "## This invocation",
        "",
        f"- Test phase: `{test_status}`",
        f"- Command: `{test_command}`",
        f"- JUnit cases: {len(cases)}; passed: {passed_count}; failed: {failed_count}; errors: {error_count}; skipped: {skipped_count}",
        f"- JUnit case time: {duration:.2f} s",
        f"- NETCONF test cases in JUnit: {len(netconf_cases)}; passed: {netconf_passed}; failed/errors: {netconf_failed}; skipped: {netconf_skipped}",
    ]
    if test_status == "NOT_RUN":
        lines.append(f"- Not-run reason: {not_run_reason or 'No JUnit results were produced.'}")
    lines.extend(
        [
            "",
            "## Detailed reports",
            "",
            f"- Implementation analysis: {implementation_link}",
            f"- Test results: {test_link}",
            "",
            "This summary covers only this run invocation. It does not compare other run directories or establish independent implementation interoperability.",
        ]
    )
    summary_path = reports_dir / (
        f"ietf_power_and_energy_run_summary_{project_root.name}_{timestamp}.md"
    )
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return summary_path