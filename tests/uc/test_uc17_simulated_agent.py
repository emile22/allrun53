from green.models import ComponentState, EventSeries
from green.topology import ROUTER_A_ID

from tests.uc.helpers import events_for, metadata


def test_agent_sequence_is_simulated_guarded_and_read_only():
    events = events_for(EventSeries.UC_2_17)

    assert len(events) == 8
    assert [event.sequence for event in events] == [f"U17-{index}" for index in range(8)]
    assert metadata(events[0])["agent-input"] == "device-observation"
    assert metadata(events[1])["decision"] == "simulated"
    assert metadata(events[2])["service-guard"] == "pass"
    assert metadata(events[2])["safety-guard"] == "pass"
    assert metadata(events[3])["FILL_IN_GAP"] == "UC2.17/AGENT_REASONING"
    assert metadata(events[5])["energy-interval"] == "UNKNOWN"
    assert metadata(events[5])["FILL_IN_GAP"] == "UC2.17/ENERGY_OUTCOME_INTERVAL"
    assert metadata(events[6])["FILL_IN_GAP"] == "UC2.17/LEARNING_FEEDBACK"
    assert dict(events[0].component_states)[ROUTER_A_ID] is ComponentState.ACTIVE
    assert dict(events[4].component_states)[ROUTER_A_ID] is ComponentState.LOW_POWER
    assert metadata(events[7])["autonomous-agent"] == "not-implemented"
