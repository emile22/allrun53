from green.models import ComponentState, EventSeries
from green.simulator import generate_events
from green.views import event_to_yang
from green.topology import demo_energy_objects


def test_hibernation_is_scenario_state_when_no_yang_identity_exists():
    event = next(
        item for item in generate_events(EventSeries.UC_2_9)
        if item.sequence == "U9-2"
    )
    assert dict(event.component_states)["eo-ap-1"] is ComponentState.HIBERNATING
    assert dict(event.metadata)["FILL_IN_GAP"] == "UC2.9/HIBERNATING_STATE_MAPPING"
    data = event_to_yang(event, demo_energy_objects())
    objects = data["ietf-power-and-energy:energy-objects"]["energy-object"]
    ap = next(item for item in objects if item["id"] == "eo-ap-1")
    assert "power-state" not in ap
    assert dict(event.metadata)["wlan-mode"] == "hibernating"
