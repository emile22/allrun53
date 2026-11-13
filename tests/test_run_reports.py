import json
from datetime import datetime, timezone
from pathlib import Path

from green.run_reports import generate_power_and_energy_run_summary, generate_run_reports


def test_generate_run_reports_uses_junit_results_and_preserves_analysis(tmp_path: Path) -> None:
    project_root = tmp_path / Path(__file__).resolve().parents[1].name
    reports = project_root / "reports"
    reports.mkdir(parents=True)
    implementation_report = reports / f"ietf_power_and_energy_{project_root.name}.md"
    implementation_report.write_text(
        "# Implementation Report\n\nGenerated: <time datetime=\"old\">old</time>\n\nKeep this analysis.\n",
        encoding="utf-8",
    )
    junit_xml = tmp_path / "results.xml"
    junit_xml.write_text(
        """<testsuites><testsuite>
        <testcase classname="tests.test_adapter" name="test_mapping" time="0.10" />
        <testcase classname="tests.uc.test_uc01" name="test_scenario" time="0.20">
          <failure message="assertion mismatch" />
        </testcase>
        <testcase classname="tests.uc.test_uc02" name="test_skip" time="0.00">
          <skipped message="not applicable" />
        </testcase>
        </testsuite></testsuites>""",
        encoding="utf-8",
    )

    implementation_path, test_path = generate_run_reports(
        project_root,
        junit_xml_path=junit_xml,
        test_command="python -m pytest --ignore=tests/netconf",
        now=datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc),
    )

    implementation_text = implementation_path.read_text(encoding="utf-8")
    test_text = test_path.read_text(encoding="utf-8")
    assert 'datetime="2026-11-09T12:00:00+00:00"' in implementation_text
    assert "Keep this analysis." in implementation_text
    assert "Total tests | 3" in test_text
    assert "Passed | 1" in test_text
    assert "Failed | 1" in test_text
    assert "Skipped | 1" in test_text
    assert "assertion mismatch" in test_text
    assert "../tests/test_adapter.py" in test_text
    assert "../tests/uc/test_uc01.py" in test_text
    assert "live `tests/netconf/` integration suite was excluded" in test_text


def test_generate_run_reports_records_when_suite_did_not_run(tmp_path: Path) -> None:
    project_root = tmp_path / Path(__file__).resolve().parents[1].name
    reports = project_root / "reports"
    reports.mkdir(parents=True)
    implementation_report = reports / f"ietf_power_and_energy_{project_root.name}.md"
    implementation_report.write_text("# Implementation Report\n", encoding="utf-8")

    _, test_path = generate_run_reports(
        project_root,
        junit_xml_path=None,
        test_command="not run",
        not_run_reason="NETCONF startup failed before pytest.",
        now=datetime(2026, 11, 9, tzinfo=timezone.utc),
    )

    test_text = test_path.read_text(encoding="utf-8")
    assert "No test cases were collected." in test_text
    assert "NETCONF startup failed before pytest." in test_text
    implementation_time = next(
        line for line in implementation_report.read_text(encoding="utf-8").splitlines()
        if line.startswith("Generated:")
    )
    test_time = next(line for line in test_text.splitlines() if line.startswith("Generated:"))
    assert implementation_time == test_time


def test_generate_power_and_energy_run_summary_uses_manifest_and_junit(tmp_path: Path) -> None:
    project_root = tmp_path / "allrun53"
    (project_root / "install").mkdir(parents=True)
    reports = project_root / "reports"
    reports.mkdir()
    (reports / "ietf_power_and_energy_allrun53.md").write_text("# Implementation\n", encoding="utf-8")
    (reports / "test_report_allrun53.md").write_text("# Tests\n", encoding="utf-8")
    (project_root / "install" / "yang-module-manifest.json").write_text(
        json.dumps({"modules": [{"name": "ietf-power-and-energy", "revision": "2026-11-01", "sha256": "abc123"}]}),
        encoding="utf-8",
    )
    junit_xml = tmp_path / "results.xml"
    junit_xml.write_text(
        """<testsuites><testsuite>
        <testcase classname="tests.test_adapter" name="test_mapping" time="0.10" />
        <testcase classname="tests.netconf.test_smoke" name="test_get" time="0.20" />
        <testcase classname="tests.netconf.test_smoke" name="test_reject" time="0.03">
          <failure message="rpc error" />
        </testcase>
        <testcase classname="tests.test_runtime" name="test_skip" time="0.00">
          <skipped message="not applicable" />
        </testcase>
        </testsuite></testsuites>""",
        encoding="utf-8",
    )

    summary_path = generate_power_and_energy_run_summary(
        project_root,
        junit_xml_path=junit_xml,
        test_command="python -m pytest",
        netconf_status="READY",
        now=datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc),
    )

    summary = summary_path.read_text(encoding="utf-8")
    assert summary_path.name == "ietf_power_and_energy_run_summary_allrun53_20261109_120000.md"
    assert "ietf-power-and-energy@2026-11-01" in summary
    assert "Manifest SHA-256: `abc123`" in summary
    assert "JUnit cases: 4; passed: 2; failed: 1; errors: 0; skipped: 1" in summary
    assert "NETCONF test cases in JUnit: 2; passed: 1; failed/errors: 1; skipped: 0" in summary
    assert "NETCONF preflight: `READY`" in summary
    assert "[ietf_power_and_energy_allrun53.md](ietf_power_and_energy_allrun53.md)" in summary
    assert "does not compare other run directories" in summary


def test_generate_power_and_energy_run_summary_records_not_run_reason(tmp_path: Path) -> None:
    project_root = tmp_path / "allrun53"
    summary_path = generate_power_and_energy_run_summary(
        project_root,
        junit_xml_path=None,
        test_command="not run",
        netconf_status="NOT_READY",
        not_run_reason="NETCONF startup failed before pytest.",
        now=datetime(2026, 11, 9, tzinfo=timezone.utc),
    )

    summary = summary_path.read_text(encoding="utf-8")
    assert "Test phase: `NOT_RUN`" in summary
    assert "Not-run reason: NETCONF startup failed before pytest." in summary
    assert "NETCONF preflight: `NOT_READY`" in summary


def test_run_tag_names_all_reports_and_preserves_base_analysis(tmp_path: Path) -> None:
    project_root = tmp_path / "allrun53"
    reports = project_root / "reports"
    reports.mkdir(parents=True)
    base_report = reports / "ietf_power_and_energy_allrun53.md"
    base_report.write_text("# Implementation\n\nKeep this analysis.\n", encoding="utf-8")
    run_tag = "2026-11-13_00-27-06-n3hhpfc6"
    now = datetime(2026, 11, 13, 0, 28, tzinfo=timezone.utc)

    implementation_path, test_path = generate_run_reports(
        project_root,
        junit_xml_path=None,
        test_command="not run",
        now=now,
        run_tag=run_tag,
    )
    summary_path = generate_power_and_energy_run_summary(
        project_root,
        junit_xml_path=None,
        test_command="not run",
        netconf_status="NOT_READY",
        now=now,
        run_tag=run_tag,
    )

    assert implementation_path.name == f"ietf_power_and_energy_allrun53_{run_tag}.md"
    assert test_path.name == f"test_report_allrun53_{run_tag}.md"
    assert summary_path.name == f"ietf_power_and_energy_run_summary_allrun53_{run_tag}.md"
    assert "Keep this analysis." in implementation_path.read_text(encoding="utf-8")
    assert "Generated:" not in base_report.read_text(encoding="utf-8")
    summary = summary_path.read_text(encoding="utf-8")
    assert f"({implementation_path.name})" in summary
    assert f"({test_path.name})" in summary