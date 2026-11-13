import argparse
import select
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from rich.console import Console
from rich.syntax import Syntax
from rich.text import Text

from green.accounting import AccountingEngine
from green.catalog import EVENT_CATALOG, UC_CATALOG, USE_CASES_BY_SERIES
from green.gaps import format_gap_summary, render_gap_report
from green.models import AccountingResult, EventSeries, SimulatedEvent
from green.netconf_bridge import set_netconf_trace_enabled, write_operational_snapshot
from green.netconf_trace import NetconfTraceTailer
from green.simulator import EventSimulator
from green.topology import RelationshipGraph, build_demo_topology
from green.views import (
    event_to_yang,
    fetch_netconf_xml,
    render_json,
    render_compact_event,
    render_relationship_diff,
    render_relationships,
    render_summary,
    filter_yang_instance_to_energy_objects,
)

_VIEW_COMMANDS = {"summary", "relationships", "json", "xml", "diff", "gaps"}
SUPPORTED_USE_CASE_IDS = tuple(
    sorted(
        {series.value.removeprefix("UC ") for series in EventSeries},
        key=lambda value: tuple(int(part) for part in value.split(".")),
    )
)


def parse_use_case(value: str) -> EventSeries:
    normalized = value.strip().upper()
    if normalized.startswith("UC"):
        normalized = normalized[2:].strip()
    normalized = normalized.replace(" ", "")
    for series in EventSeries:
        if series.value.removeprefix("UC ").replace(" ", "") == normalized:
            return series
    available = ", ".join(SUPPORTED_USE_CASE_IDS)
    raise argparse.ArgumentTypeError(
        f"unknown UC {value!r}; choose one of: {available}"
    )


def _poll_console_command() -> str | None:
    if not sys.stdin.isatty():
        return None
    try:
        if sys.platform == "win32":
            import msvcrt

            if not msvcrt.kbhit():
                return None
            command = msvcrt.getwch().lower()
            return command if command in {"q", "d", "n", "+", "-"} else None
        readable, _, _ = select.select([sys.stdin], [], [], 0)
        if readable:
            command = sys.stdin.readline().strip().lower()
            return command if command in {"q", "d", "n", "+", "-"} else None
    except (OSError, ValueError):
        return None
    return None


def run_demo(
    simulator: EventSimulator,
    *,
    auto: bool,
    interval: float,
    input_fn: Callable[[], str],
    sleep_fn: Callable[[float], None],
    output_fn: Callable[[str], None],
    loops: int | None = None,
    poll_input_fn: Callable[[], str | None] | None = None,
    snapshot_fn: Callable[[SimulatedEvent], None] | None = None,
    trace_fn: Callable[[bool], Path] | None = None,
    xml_fn: Callable[[], str] | None = None,
) -> None:
    if loops is not None and loops < 0:
        raise ValueError("loops must be non-negative")
    auto = auto or loops is not None
    accounting = AccountingEngine()
    set_trace = trace_fn or set_netconf_trace_enabled
    trace_enabled = False
    trace_path: Path | None = None
    trace_tailer: NetconfTraceTailer | None = None
    current_event: SimulatedEvent | None = None
    previous_event: SimulatedEvent | None = None
    current_data: dict[str, object] | None = None
    run_number = 1
    executed_events: list[SimulatedEvent] = []
    executed_series: set[EventSeries] = set()
    visible_energy_object_ids: frozenset[str] | None = None
    if simulator.use_case is not None:
        scenario = simulator.network.scenarios_by_uc[simulator.use_case.value]
        visible_energy_object_ids = _visible_energy_object_ids_for_use_case(
            simulator, simulator.use_case, scenario.topology_ids
        )
    output_fn("GREEN allrun53 demo starting...")

    def disable_trace() -> None:
        nonlocal trace_enabled, trace_tailer
        if not trace_enabled:
            return
        try:
            trace_path = set_trace(False)
        except OSError as error:
            output_fn(f"NETCONF trace could not be disabled: {error}")
        else:
            output_fn(f"NETCONF trace disabled: {trace_path}")
        trace_enabled = False
        if trace_tailer is not None:
            trace_tailer.stop()
            trace_tailer = None

    def toggle_trace() -> None:
        nonlocal trace_tailer
        if not trace_enabled or trace_path is None:
            output_fn("NETCONF live view unavailable: tracing is not enabled.")
            return
        if trace_tailer is None:
            trace_tailer = NetconfTraceTailer(
                trace_path,
                output_fn,
                visible_energy_object_ids=visible_energy_object_ids,
            )
            trace_tailer.start()
            output_fn(f"NETCONF live view enabled: {trace_path}")
        else:
            trace_tailer.stop()
            trace_tailer = None
            output_fn(f"NETCONF live view disabled: {trace_path}")

    def restart_run(announcement: str | None = None) -> None:
        nonlocal accounting, current_event, previous_event, current_data, run_number
        simulator.reset()
        accounting = AccountingEngine()
        current_event = None
        previous_event = None
        current_data = None
        executed_events.clear()
        executed_series.clear()
        run_number += 1
        if announcement is None:
            output_fn(f"Simulator restarted at UC 2.1 / U1-0 (run #{run_number}).")
        else:
            output_fn(f"{announcement} (run #{run_number}).")

    def change_use_case(direction: int) -> bool:
        nonlocal accounting, current_event, previous_event, current_data
        nonlocal visible_energy_object_ids
        next_spec = simulator.peek_next()
        active_series = current_event.series if current_event is not None else (
            next_spec.series if next_spec is not None else None
        )
        if active_series is None:
            return False
        ordered_series = tuple(spec.series for spec in UC_CATALOG)
        target_index = ordered_series.index(active_series) + direction
        if not 0 <= target_index < len(ordered_series):
            edge = "first" if direction < 0 else "last"
            indicator = "-" if direction < 0 else "+"
            output_fn(f"LIMIT: {indicator} Already at the {edge} UC ({active_series.value}).")
            return False
        target_series = ordered_series[target_index]
        simulator.start_at_use_case(target_series)
        accounting = AccountingEngine()
        current_event = None
        previous_event = None
        current_data = None
        visible_energy_object_ids = None
        output_fn(f"Switched to {target_series.value}; starting at its first event.")
        return True

    def show_view(command: str) -> None:
        if command == "gaps":
            output_fn(render_gap_report(
                event for event in EVENT_CATALOG
                if simulator.use_case is None or event.series is simulator.use_case
            ))
            return
        if command == "xml":
            try:
                xml = (
                    xml_fn()
                    if xml_fn is not None
                    else fetch_netconf_xml(visible_energy_object_ids)
                )
                output_fn(xml)
            except Exception as error:
                output_fn(f"NETCONF XML view unavailable: {error}")
            return
        if current_event is None or current_data is None:
            output_fn(f"{command} view unavailable before the first event.")
            return
        if command == "summary":
            output_fn(render_summary(
                current_event,
                current_data,
                visible_energy_object_ids=visible_energy_object_ids,
            ))
        elif command == "relationships":
            output_fn(render_relationships(current_data))
        elif command == "json":
            output_fn(render_json(current_data))
        elif command == "diff":
            output_fn(render_relationship_diff(
                previous_event,
                current_event,
                visible_energy_object_ids=visible_energy_object_ids,
            ))

    try:
        trace_path = set_trace(True)
    except OSError as error:
        output_fn(f"NETCONF trace could not be enabled: {error}")
    else:
        trace_enabled = True

    completed_loops = 0
    while True:
        if not simulator.has_next:
            completed_loops += 1
            uc_count = len(executed_series)
            event_count = len(executed_events)
            output_fn(f"UCs executed: {uc_count}/17")
            if event_count == 146 and uc_count == 17:
                output_fn(f"Events executed: {event_count} (minimum 146)")
            else:
                output_fn(f"Events executed: {event_count}")
            output_fn(format_gap_summary(executed_events))
            output_fn(f"UCs omitted: {17 - uc_count}")

            should_repeat = loops == 0 or (
                loops is not None and run_number < loops
            )
            if not should_repeat:
                break
            restart_run(f"Automatic loop {completed_loops} complete; restarting")
            continue

        next_spec = simulator.peek_next()
        if next_spec is None:
            break
        next_series = next_spec.series
        if auto:
            command = (poll_input_fn or _poll_console_command)()
            if command == "q":
                disable_trace()
                output_fn("GREEN allrun53 demo stopped.")
                return
            if command == "d":
                toggle_trace()
            if command == "n":
                if loops not in (None, 0) and run_number >= loops:
                    disable_trace()
                    output_fn(f"Run limit #{loops} reached; stopping.")
                    return
                restart_run()
                continue
            if command in {"+", "-"}:
                change_use_case(1 if command == "+" else -1)
                continue
    # Print a separator at each use-case boundary.
        if current_event is None or current_event.series != next_series:
            output_fn(f"--- {next_series.value} {USE_CASES_BY_SERIES[next_series].title} ---")

        if not auto:
            output_fn("Enter next UC | a auto | d netconf | n new run | -/+ change UC | summary / relationships / json / xml / diff / gaps | r reset | q quit")
            command = input_fn().strip().lower()
            if command == "a":
                auto = True
                output_fn("Automatic mode enabled (q quit, d trace, n restart, +/- change UC).")
                continue
            if command == "d":
                toggle_trace()
                continue
            if command == "q":
                disable_trace()
                output_fn("GREEN allrun53 demo stopped.")
                return
            if command in {"n", "r"}:
                restart_run()
                continue
            if command in {"+", "-"}:
                change_use_case(1 if command == "+" else -1)
                continue
            if command in _VIEW_COMMANDS:
                show_view(command)
                continue
            if command:
                output_fn("Unknown command. Choose ENTER, a, d, n, +, -, summary, relationships, json, xml, diff, gaps, r, or q.")
                continue

        event = simulator.next_event()
        if event is None:
            break
        executed_events.append(event)
        executed_series.add(event.series)
        visible_energy_object_ids = _visible_energy_object_ids_for_use_case(
            simulator, event.series, event.topology_ids
        )
        if trace_tailer is not None:
            trace_tailer.visible_energy_object_ids = visible_energy_object_ids
        if snapshot_fn is not None:
            try:
                snapshot_fn(event)
            except OSError as error:
                output_fn(f"NETCONF snapshot warning: {error}")

        topology, boundary = build_demo_topology(relationships=event.relationships)
        result = None
        if event.series is EventSeries.UC_2_13:
            result = accounting.compute(
                boundary,
                event.measurements,
                topology,
                series=event.series.value,
                event_sequence=event.sequence,
                event_name=event.name,
            )
        data = event_to_yang(event, simulator.energy_objects)
        if visible_energy_object_ids is not None:
            data = filter_yang_instance_to_energy_objects(data, visible_energy_object_ids)
        prior_event = current_event
        previous_event, current_event = current_event, event
        current_data = data
        _display_event(
            event,
            result,
            topology,
            output_fn,
            prior_event,
            visible_energy_object_ids,
        )

        next_spec = simulator.peek_next()
        if next_spec is None:
            output_fn(f"{event.series.value} complete")
        elif next_spec.series != event.series:
            output_fn(f"{event.series.value} complete -> {next_spec.series.value} {USE_CASES_BY_SERIES[next_spec.series].title}")

        if auto and simulator.has_next:
            sleep_fn(interval)

    disable_trace()


def _display_event(
    event: SimulatedEvent,
    result: AccountingResult | None,
    topology: RelationshipGraph,
    output_fn: Callable[[str], None],
    previous: SimulatedEvent | None,
    visible_energy_object_ids: frozenset[str] | None = None,
) -> None:
    use_color = output_fn is print and sys.stdout.isatty()
    for line in render_compact_event(
        event,
        topology.energy_objects,
        previous,
        result,
        visible_energy_object_ids,
    ).splitlines():
        if use_color and line.startswith("["):
            line = f"\x1b[32m{line}\x1b[0m"
        output_fn(line)


def _rich_print(console: Console, message: str) -> None:
    stripped = message.lstrip()
    if stripped.startswith("{"):
        console.print(Syntax(message, "json", word_wrap=True))
        return
    if stripped.startswith("<"):
        console.print(Syntax(message, "xml", word_wrap=True))
        return

    text = Text(message)
    if message.startswith("LIMIT:"):
        text = Text(message.removeprefix("LIMIT:").strip())
        text.stylize("blink bold yellow")
    elif message.startswith("["):
        text.stylize("bold green")
    elif message.startswith("---"):
        text.stylize("bold cyan")
    elif message.startswith(("GREEN allrun53", "UCs executed", "Events executed", "FILL_IN_GAP", "UCs omitted")):
        text.stylize("bold green")
    elif message.startswith(("HW ", "ENERGY ", "REL ", "DIFF ", "ACCOUNT ")):
        label, separator, details = message.partition(" ")
        text = Text(label, style="bold cyan")
        text.append(separator + details)
    elif message.startswith("NETCONF") or message.startswith("Unknown command"):
        text.stylize("yellow")
    console.print(text)


def _visible_energy_object_ids(
    simulator: EventSimulator,
    topology_ids: Sequence[str],
) -> frozenset[str]:
    selected_topologies = set(topology_ids)
    return frozenset(
        energy_object_id
        for topology in simulator.network.topologies
        if topology.topology_id in selected_topologies
        for energy_object_id in topology.energy_object_ids
    )


def _visible_energy_object_ids_for_use_case(
    simulator: EventSimulator,
    series: EventSeries,
    topology_ids: Sequence[str],
) -> frozenset[str]:
    topology_object_ids = _visible_energy_object_ids(simulator, topology_ids)
    use_case_value_ids = {
        energy_object_id
        for event in EVENT_CATALOG
        if event.series is series
        for energy_object_id, _ in (
            *event.interval_energy_wh,
            *event.instantaneous_power_w,
            *event.component_states,
        )
    }
    return frozenset(topology_object_ids & use_case_value_ids)


def main(
    argv: Sequence[str] | None = None,
    *,
    input_fn: Callable[[], str] = input,
    poll_input_fn: Callable[[], str | None] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    output_fn: Callable[[str], None] = print,
    snapshot_fn: Callable[[SimulatedEvent], None] | None = write_operational_snapshot,
    trace_fn: Callable[[bool], Path] | None = None,
    xml_fn: Callable[[], str] | None = None,
) -> None:
    parser = argparse.ArgumentParser(description="Run the GREEN allrun53 event simulator")
    parser.add_argument("--auto", action="store_true", help="run all remaining events without prompts")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument(
        "-n",
        "--loops",
        type=int,
        nargs="?",
        const=0,
        default=None,
        metavar="LOOPS",
        help="run automatically for LOOPS passes; omit LOOPS to repeat forever",
    )
    parser.add_argument(
        "-u",
        "--uc",
        type=parse_use_case,
        metavar="UC",
        help=f"run only one implemented UC (available: {', '.join(SUPPORTED_USE_CASE_IDS)})",
    )
    args = parser.parse_args(argv)
    if args.interval < 0:
        parser.error("--interval must be non-negative")
    if args.loops is not None and args.loops < 0:
        parser.error("--loops must be non-negative; omit the count for infinite looping")

    if output_fn is print:
        console = Console()
        output_fn = lambda message: _rich_print(console, message)

    run_demo(
        EventSimulator(use_case=args.uc),
        auto=args.auto or args.loops is not None,
        interval=args.interval,
        input_fn=input_fn,
        loops=args.loops,
        poll_input_fn=poll_input_fn,
        sleep_fn=sleep_fn,
        output_fn=output_fn,
        snapshot_fn=snapshot_fn,
        trace_fn=trace_fn,
        xml_fn=xml_fn,
    )


if __name__ == "__main__":
    main()
