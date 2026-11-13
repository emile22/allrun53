import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path


_GAP_REGISTRY = Path(__file__).resolve().parents[2] / "docs" / "fill_in_gaps.json"


def load_gap_registry() -> tuple[dict[str, object], ...]:
    data = json.loads(_GAP_REGISTRY.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("gaps"), list):
        raise ValueError(f"invalid FILL_IN_GAP registry: {_GAP_REGISTRY}")
    gaps = tuple(data["gaps"])
    gap_ids = [entry.get("id") for entry in gaps if isinstance(entry, dict)]
    if len(gap_ids) != len(gaps) or len(set(gap_ids)) != len(gap_ids):
        raise ValueError("FILL_IN_GAP registry contains malformed or duplicate IDs")
    return gaps


def gap_ids_for_events(events: Iterable[object]) -> set[str]:
    gap_ids = set()
    for event in events:
        metadata = dict(getattr(event, "metadata", ()))
        marker = metadata.get("FILL_IN_GAP")
        if marker:
            gap_ids.add(str(marker))
    return gap_ids


def format_gap_summary(events: Iterable[object]) -> str:
    registry = load_gap_registry()
    registry_by_id = {str(entry["id"]): entry for entry in registry}
    event_list = tuple(events)
    gap_ids = gap_ids_for_events(event_list)
    unknown_ids = gap_ids - registry_by_id.keys()
    if unknown_ids:
        raise ValueError(f"events reference unregistered FILL_IN_GAP IDs: {sorted(unknown_ids)}")

    cross_cutting_ids = {
        gap_id for gap_id, entry in registry_by_id.items()
        if entry.get("uc") == "cross-cutting"
    }
    reported_ids = gap_ids | cross_cutting_ids
    counts = Counter(str(registry_by_id[gap_id]["uc"]) for gap_id in reported_ids)
    by_uc = ", ".join(f"{uc}={counts[uc]}" for uc in sorted(counts)) or "none"
    return f"FILL_IN_GAP entries: {len(reported_ids)} ({by_uc})"


def render_gap_report(events: Iterable[object]) -> str:
    registry = load_gap_registry()
    registry_by_id = {str(entry["id"]): entry for entry in registry}
    event_list = tuple(events)
    gap_ids = gap_ids_for_events(event_list)
    unknown_ids = gap_ids - registry_by_id.keys()
    if unknown_ids:
        raise ValueError(f"events reference unregistered FILL_IN_GAP IDs: {sorted(unknown_ids)}")
    gap_ids.update(
        gap_id for gap_id, entry in registry_by_id.items()
        if entry.get("uc") == "cross-cutting"
    )
    entries = [registry_by_id[gap_id] for gap_id in sorted(gap_ids)]
    counts = Counter(str(entry["uc"]) for entry in entries)
    return json.dumps(
        {
            "uc_count": len({getattr(event, "series", None) for event in event_list}),
            "event_count": len(event_list),
            "gap_count": len(entries),
            "gaps_by_uc": dict(sorted(counts.items())),
            "gaps": entries,
        },
        indent=2,
    )
