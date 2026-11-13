import json

from green.models import EventSeries
from green.simulator import generate_events
from green.topology import demo_energy_objects
from green.views import event_to_yang

from tests.uc.helpers import events_for, metadata


def test_lifecycle_reporting_runs_with_explicit_carbon_and_source_gaps():
    events = events_for(EventSeries.UC_2_3)

    assert len(events) == 8
    assert events[0].sequence == "U3-0"
    assert events[3].sequence == "U3-3"
    assert events[-1].sequence == "U3-7"
    assert metadata(events[0])["FILL_IN_GAP"] == "UC2.3/LIFECYCLE_SOURCE_DATA"
    assert metadata(events[2])["carbon-factor"] == "UNKNOWN"
    assert metadata(events[2])["FILL_IN_GAP"] == "UC2.3/CARBON_ATTRIBUTION"
    assert metadata(events[-1])["embedded-impact"] == "UNKNOWN"

    for event in events:
        yang_data = event_to_yang(event, demo_energy_objects())
        encoded = json.dumps(yang_data)
        assert "carbon-factor" not in encoded
        assert "lifecycle-stage" not in encoded
        assert "FILL_IN_GAP" not in encoded


def test_all_events_remain_in_the_numeric_full_run():
    events = generate_events()
    assert sum(event.series is EventSeries.UC_2_3 for event in events) == 8
