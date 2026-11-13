from green.models import EventSeries
from green.simulator import generate_events
from green.topology import AI_NODE_1_ID, demo_energy_objects
from green.views import event_to_yang

from tests.uc.helpers import events_for, metadata


def test_host_metering_runs_without_fabricated_per_vnf_values():
    events = events_for(EventSeries.UC_2_4)

    assert len(events) == 8
    host_measurements = [
        next(item for item in event.measurements if item.energy_object_id == AI_NODE_1_ID)
        for event in events
        if any(item.energy_object_id == AI_NODE_1_ID for item in event.measurements)
    ]
    assert host_measurements
    cumulative = [item.cumulative_energy_wh for item in host_measurements]
    assert cumulative == sorted(cumulative)
    assert all(value is not None for value in cumulative)
    assert metadata(events[0])["vnf-energy"] == "UNKNOWN"
    assert metadata(events[4])["FILL_IN_GAP"] == "UC2.4/PER_VNF_ATTRIBUTION"

    yang_data = event_to_yang(events[4], demo_energy_objects())
    yang_objects = yang_data["ietf-power-and-energy:energy-objects"]["energy-object"]
    assert {item["id"] for item in yang_objects} >= {AI_NODE_1_ID}
    assert not any("vnf" in item["id"].lower() for item in yang_objects)
    assert "FILL_IN_GAP" not in str(yang_data)


def test_vnf_uc_is_not_omitted_from_full_stream():
    assert sum(event.series is EventSeries.UC_2_4 for event in generate_events()) == 8
