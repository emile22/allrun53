import json

from green.gaps import format_gap_summary, gap_ids_for_events, load_gap_registry, render_gap_report
from green.simulator import generate_events
from green.topology import demo_energy_objects
from green.yang_adapter import to_yang_instance


def test_every_gap_marker_matches_the_structured_registry() -> None:
    events = generate_events()
    events_by_id = {event.sequence: event for event in events}
    registry = load_gap_registry()
    registry_ids = {str(entry["id"]) for entry in registry if entry["events"]}
    assert gap_ids_for_events(events) == registry_ids

    for entry in registry:
        gap_id = str(entry["id"])
        for sequence in entry["events"]:
            assert dict(events_by_id[sequence].metadata)["FILL_IN_GAP"] == gap_id
    assert any(
        entry["id"] == "YANG05/SOURCE_COMPONENT_ID_UUID_DISCREPANCY"
        and entry["uc"] == "cross-cutting"
        for entry in registry
    )


def test_gap_fallbacks_are_explicit_and_never_appear_in_yang() -> None:
    events = {event.sequence: event for event in generate_events()}
    assert dict(events["U4-4"].metadata)["vnf-energy"] == "UNKNOWN"
    assert dict(events["U17-3"].metadata)["intent-source"] == "simulated-agent"

    for event in events.values():
        data = to_yang_instance(
            demo_energy_objects(),
            event.relationships,
            event.measurements,
            event.component_states,
            event.power_measurements,
        )
        assert "FILL_IN_GAP" not in json.dumps(data)
        assert "vnf-energy" not in json.dumps(data)
        assert "agent-intent" not in json.dumps(data)


def test_gap_summary_counts_unique_entries_by_uc() -> None:
    events = generate_events()

    assert format_gap_summary(events) == (
        "FILL_IN_GAP entries: 8 (UC 2.17=3, UC 2.3=2, UC 2.4=1, UC 2.9=1, cross-cutting=1)"
    )


def test_json_gap_report_is_separate_from_operational_yang() -> None:
    report = json.loads(render_gap_report(generate_events()))

    assert report["uc_count"] == 17
    assert report["event_count"] == 146
    assert report["gap_count"] == 8
    assert report["gaps_by_uc"]["cross-cutting"] == 1
