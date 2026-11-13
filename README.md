# GREEN Canonical Network Simulator (`allrun53`)

`allrun53/` is a self-contained topology-driven GREEN simulator. All source code, YANG, data, tests, scripts, generated snapshots, runtime files, and logs stay under this directory.

The event meanings follow the upstream [draft-ietf-green-use-cases](https://github.com/emile22/draft-ietf-green-use-cases/blob/main/draft-ietf-green-use-cases.md). Event IDs and descriptions are simulator-specific and are not represented as standardized IETF events.

## Use-Case Groups

This run implements **all 17 use cases (2.1–2.17)** as **146 deterministic events**. No UC is skipped or deferred. Unsupported lifecycle/carbon inputs, per-VNF attribution, hibernation-state mapping, agent reasoning, interval-energy outcome evaluation, and source-component prose conflicts remain explicit `FILL_IN_GAP` entries; they do not create fabricated YANG data. See [use_case_groups.md](docs/use_case_groups.md), [fill_in_gaps.md](docs/fill_in_gaps.md), the [deep gap analysis](docs/deep_gap_analysis.md), and the generated [event_catalog.md](docs/event_catalog.md).

| UC | Events | UC | Events |
| --- | ---: | --- | ---: |
| UC 2.1 | 8 | UC 2.10 | 8 |
| UC 2.2 | 10 | UC 2.11 | 8 |
| UC 2.3 | 8 | UC 2.12 | 10 |
| UC 2.4 | 8 | UC 2.13 | 8 |
| UC 2.5 | 8 | UC 2.14 | 10 |
| UC 2.6 | 8 | UC 2.15 | 8 |
| UC 2.7 | 8 | UC 2.16 | 10 |
| UC 2.8 | 8 | UC 2.17 | 8 |
| UC 2.9 | 10 | | |

## Canonical Network

`DEMO-NETWORK-1` contains one stable inventory of **7 device archetypes, 23 device instances, 44 RFC 8348 Components/Energy Objects**, and six reusable sub-topologies:

| Topology | Label | Name |
| --- | --- | --- |
| T1 | CORE | Fixed Network |
| T2 | AIR | WLAN / PoE |
| T3 | POWER | Power Infrastructure |
| T4 | BACKHAUL | Wireless Transport |
| T5 | EDGE | Edge / Compute |
| T6 | CITY | ISAC / Smart City |

Sub-topologies may share device instances; use-case scenarios select primary and secondary views rather than cloning equipment.

Device archetypes and instances live separately in `data/devices/`; sub-topologies live in `data/topologies/`; UC topology overlays live in `data/scenarios/`. The detailed maps are generated in [canonical_network.md](docs/canonical_network.md), [device_archetypes.md](docs/device_archetypes.md), and [uc_topology_matrix.md](docs/uc_topology_matrix.md).

The simulator internals follow this flow:

```text
device archetypes
       ↓
device instances
       ↓
canonical topology
       ↓
UC overlays
       ↓
YANG adapter
       ↓
Sysrepo / Netopeer2
       ↓
NETCONF
```

Each event is a patch over the canonical inventory: state, measurements, relationship visibility, and simulator-only metadata may change, but device IDs, component names/UUIDs, hierarchy, Energy Object IDs, and source-component mappings remain stable. Restart resets runtime state, not inventory identity.

Controller identity is scoped as `(device_id, hardware_component_name)` for Components and `(device_id, energy_object_id)` for Energy Objects. See [controller_identity_model.md](docs/controller_identity_model.md). Relationship behavior is classified as stable structural, physical dynamic, or knowledge/observability; UC 2.13 preserves actual metering topology separately from what the controller has discovered. See [relationship_behavior_classes.md](docs/relationship_behavior_classes.md).

## Architecture

```text
Windows Python 3.11 runtime and ncclient
       | shared allrun53/runtime/operational.json
       v
WSL Sysrepo operational-data plugin
       v
WSL Netopeer2 on TCP/830
```

Windows runs the GREEN event simulator, adapter, CLI, and ncclient tests. Runtime snapshots and generated test credentials stay in `runtime/`; formatted/runtime and provider traces stay in `logs/`. Sysrepo stores the YANG modules and invokes the C operational-data provider. Netopeer2 serves NETCONF over SSH. WSL is used for native Sysrepo/Netopeer2 only; no containers are used. Windows tests prefer `localhost` and fall back to `NETCONF_HOST` from `runtime/netconf/connection.env` if WSL localhost forwarding is unavailable.

The NETCONF reconstruction test calls `ncclient`'s `netconf_manager.get()` without a filter. This sends an unfiltered NETCONF `<get>` RPC to the single local endpoint, requesting the running configuration and operational state visible to that session. Reconstruction uses the returned `/ietf-hardware:hardware/component` and `/ietf-power-and-energy:energy-objects/energy-object` subtrees (44 entries each). The test supplies `device_id="DEMO-NETWORK-1"` separately because device identity is not present in these YANG trees; this endpoint exposes the combined demo network, not 23 independent NETCONF devices.

The pinned YANG revisions included in this project are:

| Module | Revision | Included file |
| --- | --- | --- |
| `ietf-power-and-energy` | `2026-11-01` | `yang/ietf-power-and-energy@2026-11-01.yang` |
| `iana-power-and-energy` | `2026-11-01` | `yang/iana-power-and-energy@2026-11-01.yang` |
| `ietf-hardware` | `2018-03-13` | `yang/ietf-hardware@2018-03-13.yang` |
| `iana-hardware` | `2018-03-13` | `yang/iana-hardware@2018-03-13.yang` |
| `ietf-inet-types` | `2025-12-22` | `yang/ietf-inet-types@2025-12-22.yang` |
| `ietf-yang-types` | `2025-12-22` | `yang/ietf-yang-types@2025-12-22.yang` |

The Power and Energy modules use the revisions embedded in the current working draft, [draft-ietf-green-power-and-energy-yang-05](https://datatracker.ietf.org/doc/draft-ietf-green-power-and-energy-yang/05/), dated 2 November 2026. The IANA YANG Module Names registry had not yet listed `iana-power-and-energy` when checked on 5 November 2026; treat this as the draft's proposed module revision pending IANA registration.

## Setup

For detailed Windows 11 and WSL 2 installation steps, see [INSTALL.md](INSTALL.md).

Create a separate Windows environment from this directory:

```powershell
cd allrun53
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

The inspected host is Windows Python 3.11.9 plus Ubuntu 22.04.1 / WSL 2, with Sysrepo 2.0.53, libyang 2.0.112, libnetconf2 2.0.24, and Netopeer2 2.0.35. See [source-versions.env](install/source-versions.env) and [apt-packages-lock.txt](install/apt-packages-lock.txt). No host packages were installed or upgraded. Run the read-only verifier first:

```bash
bash install/verify-wsl.sh
```

Only after reviewing the isolated-repository plan and confirming TCP/830 is free, start the services explicitly:

```bash
ALLRUN53_ALLOW_HOST_CONFIG=1 bash scripts/wsl-netconf-start.sh
bash scripts/wsl-netconf-status.sh
```

allrun53 uses `/var/lib/grmis/allrun53/sysrepo` and shared-memory prefix `gr53`. The host systemd service names and TCP port 830 are shared with other runs. Start/install refuse an active or unidentified stack; install additionally requires `ALLRUN53_ALLOW_HOST_CONFIG=1`. Stop only stops allrun53 when its repository is active. Do not stop or reconfigure another run to make room. Generated credentials stay in `runtime/netconf/connection.env`; never commit that file.

At launcher initialization, the compact WSL readiness display shows Sysrepo
and Netopeer2 process IDs plus explicit RFC 8348 hardware parent/sibling ties
using Energy Object IDs and `parent-rel-pos`.

## Runtime

```powershell
py .\allrun53\run.py
```

`run.py` checks WSL health and attempts the guarded allrun53 start only when the
stack is unavailable. The start script refuses to take over another or
unidentified repository. To authorize native setup, start the allrun53 stack
explicitly from WSL as shown above, then run `py .\allrun53\run.py`; the launcher
runs the tests and stops only the allrun53 stack on exit. For offline simulation
without NETCONF, use `python -m green --auto --interval 0` directly.

The launcher prefers `allrun53/.venv` when pytest, ncclient, and pyang are installed there. If that environment is incomplete, it uses the invoking interpreter and prepends `allrun53/src` to `PYTHONPATH`, so the allrun53 package is used rather than another installed GREEN package.

To run all 146 events automatically without delay after the allrun53 services are
ready, use `py .\allrun53\run.py --auto --interval 0`.
`--auto` and `-n` runs are unattended: they imply `-f` (authorizing the guarded
WSL setup without a prompt), wait for WSL boot to settle before the NETCONF
check, and skip the final "Press ENTER" pauses. Active-stack guards still apply.
Use `--interval SECONDS` to set another automatic-mode delay.

Each launcher run records console output, including detailed pytest and runtime
output, in a new `logs/allrun53-trace-YYYY-MM-DD_HH-MM-SS.log` file.
Selecting a UC with `-u` skips the full pytest suite.

Each launcher run also creates a new raw NETCONF session log named
`logs/netconf-trace-YYYY-MM-DD_HH-MM-SS.log`. It captures records
generated during the runtime and shares its run name with the console log and
that run's reports; `-2`, `-3`, ... is appended if two runs start in the same second.
The `d` control toggles the live NETCONF view
without stopping recording. The provider's fixed trace path points to the current session
file; any previous shared trace file is preserved as an archive.

To repeat the full automatic run three times, use `py .\allrun53\run.py -n 3`.
The count includes the initial pass. Use `py .\allrun53\run.py -n` to repeat
indefinitely; press `q` to stop. The same `-n` / `--loops` option works with
`python -m green`.

To run only one use case, pass its number with `-u` or
`--uc`, for example `py .\allrun53\run.py -u 2.13`. The same option works with
`python -m green -u 2.13`. Supported selections are UC 2.1–2.17. A selected-UC run skips the full pytest suite
to avoid rerunning it after a successful test-first run; run `python -m pytest`
separately after changing code.

Controls:

| Input | Behavior |
| --- | --- |
| ENTER | Advance exactly one event. |
| `a` | Run all remaining events across the 17 UC boundaries. |
| `+` / `-` | Start the next / previous UC at its first event; at the first or last UC, navigation stays in place. |
| `d` | Toggle the live NETCONF view; recording continues. |
| `n` | Start a new run at UC 2.1 / U1-0; works during automatic looping. |
| `r` | Reset all scenario state and restart at UC 2.1 / U1-0 (alias for `n`). |
| `q` | Exit cleanly. |
| `summary` | Display hardware, energy objects, relationships, and UC interpretation. |
| `relationships` | Display the directional Energy Object graph. |
| `json` | Display normalized full YANG JSON. |
| `xml` | Fetch and display the actual NETCONF XML reply. |
| `diff` | Compare relationship and observed-state changes with the previous event. |
| `gaps` | Display the registered scenario/model gaps as JSON, separate from YANG data. |

The default event display prints its UC/event ID, available UC nickname, and explanation, followed by
compact `HW`, `ENERGY`, `REL`, and `DIFF` lines. The `summary` command opens the
detailed hardware inventory, Energy Objects, relationships, and UC interpretation.

Every event has a deterministic explanation under 20 words. Runtime/controller metadata remains separate from YANG data. Missing measurements/capabilities remain unknown; interval and cumulative energy are distinct; cumulative counters reset only on `r`.

## Adding Events

To add an event to an existing Group A use case:

1. Add an `_event(...)` entry, in sequence order, to that use case's `events` tuple in [catalog.py](src/green/catalog.py). Give it a unique ID such as `U5-8`, a concise event name, and a single deterministic explanation sentence under 20 words.
2. Describe only the event's deltas: use existing Energy Object IDs for `energy`, `power`, and `states`; use `metadata` for simulator-only context; set `cumulative=True` only when the interval should advance that object's cumulative counter. Events must not create or rename inventory.
3. For relationships, reference an existing `profiles` entry in `catalog.py`. If a genuinely new relationship profile is needed, define its directional relationships and explicit inverse in `_RELATIONSHIPS`, then add or update focused UC/relationship tests. Change `data/scenarios/uc-topology-matrix.json` only if the UC's topology assignment itself changes.
4. Update the expected per-UC counts in [test_simulator.py](tests/test_simulator.py) and [test_catalog_docs.py](tests/test_catalog_docs.py). Add or extend a test under `tests/uc/` for the event's intended behavior. The catalog tests check unique IDs, sequence order, explanations, and generated documentation.
5. Regenerate the event and project docs, then run the checks:

       ```powershell
       python -m green.catalog_docs
       python scripts/generate_docs.py
       python -m pytest
       python -m green --auto --interval 0
       ```

The generated [event_catalog.md](docs/event_catalog.md) is documentation output; edit `catalog.py`, not that generated file. Adding a new use case is broader: it also requires a new `EventSeries`, a `UseCaseSpec`, a topology mapping, and use-case-specific tests and documentation.

## Relationship Semantics

All four YANG relationship families are represented with explicit inverse identities:

- `metering` / `metered-by`: measurement topology; only this family drives accounting de-duplication.
- `aggregating` / `aggregated-by`: aggregation of Energy Management information, not traffic concentration.
- `powering` / `powered-by`: electrical supply topology.
- `enabling` / `enabled-by`: functional dependency, not electrical power flow.

Forward and inverse links are stored as distinct directional relationships. `source-component-id` maps an Energy Object to the RFC 8348 hardware component name; it is not a relationship peer or hardware UUID. Hardware containment is represented only by RFC 8348 `parent` data. The WSL installer seeds that configuration from `yang/hardware-hierarchy.xml`; it does not infer parent links from Energy Object IDs or names. See the generated [relationship_coverage.md](docs/relationship_coverage.md).

## Capability-discovery Readiness

The [capability-discovery readiness inventory](docs/capability_discovery_readiness.md) records stable RFC 8348 Component names/UUIDs, Energy Object mappings, archetypes, topology membership, and future profile classes. This is correlation readiness only: allrun53 does not implement RFC 9196, `ietf-system-capabilities`, or `ietf-power-state-capabilities`, and UC 2.11 capability classification remains simulator/controller metadata. See [future_capability_profile_model.md](docs/future_capability_profile_model.md).

The per-object field evidence and display meanings are listed in [energy_object_observability.md](docs/energy_object_observability.md). All 44 Energy Objects have one class: `FULL`, `POWER_ONLY`, `STATE_ONLY`, `TOPOLOGY_ONLY`, or `UNOBSERVED`. `UNKNOWN` and `N/A` are display-only and are never inserted into numeric or identityref YANG leaves.

## NETCONF and Services

NETCONF is read-only in this increment. The simulator drives events and Sysrepo/Netopeer2 expose the resulting operational snapshot over `<get>`. No `<edit-config>`, custom RPC, notification, YANG Push, or RESTCONF is implemented.

From WSL, inspect first; stop affects only the allrun53 repository:

```bash
bash scripts/wsl-netconf-status.sh
 bash scripts/wsl-netconf-stop.sh
 ALLRUN53_ALLOW_HOST_CONFIG=1 bash scripts/wsl-netconf-start.sh
```

`start` refuses to replace another active repository or a listener on TCP/830. Its installer requires explicit `ALLRUN53_ALLOW_HOST_CONFIG=1`; it uses an isolated Sysrepo repository. `stop` is a no-op unless allrun53 owns the active repository. Run live client tests only after the guarded stack is ready:

If the installer requests authorization, the Windows launcher offers to restart setup with `ALLRUN53_ALLOW_HOST_CONFIG=1`. Answer `y` to permit the isolated allrun53 Sysrepo/Netopeer2 configuration, or press ENTER to decline. Pass `-f` or `--force` to automatically accept only this retry. The opt-in does not bypass the active-stack or TCP/830 guard.

```powershell
py .\allrun53\run.py --force
# equivalent short option
py .\allrun53\run.py -f
```

```powershell
.\scripts\run-netconf-smoke.ps1
```

## Tests and Validation

```powershell
python -m pytest --ignore=tests/netconf
python -m green --auto --interval 0
python -m green.catalog_docs
python scripts/generate_docs.py
pyang -p yang yang\ietf-power-and-energy@2026-11-01.yang
```

The offline pytest command covers runtime/accounting/adapters, all UC scenarios, gap registry, and relationship coverage. Live `ncclient` tests are in `tests/netconf/` and are intentionally separate because the host uses shared service names and TCP/830. `yanglint` can validate a generated operational instance from WSL:

```bash
yanglint -p yang \
       yang/ietf-inet-types@2025-12-22.yang \
       yang/ietf-yang-types@2025-12-22.yang \
  yang/iana-hardware@2018-03-13.yang \
  yang/ietf-hardware@2018-03-13.yang \
       yang/iana-power-and-energy@2026-11-01.yang \
       yang/ietf-power-and-energy@2026-11-01.yang \
  runtime/operational.json
```

The implementation is self-contained in this directory. Its capability is read-only operational simulation: UC 2.17 is a scenario sequence, not an AI engine or controller, and no NETCONF actuation is implemented.
