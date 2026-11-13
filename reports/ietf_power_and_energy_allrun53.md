# `ietf-power-and-energy` Implementation Report

Generated: <time datetime="2026-11-13T00:28:00+01:00">2026-11-13 00:28:00 +01:00</time>

## Coverage

| Area                                      | Implem             | Test        | Coverage                                                  |
| ----------------------------------------- | ------------------ | ----------- | --------------------------------------------------------- |
| Operational identity and hardware mapping | Implemented        | Covered     | Energy Objects link to RFC 8348 component names.          |
| Relationships                             | Implemented        | Covered     | Eight directional relationships map to peer IDs.         |
| Power and energy readings                 | Partial (3/4, 75%) | Partial     | Three of four directional reading leaves are emitted.    |
| Power state                               | Partial (3/4, 75%) | Partial     | Three of four simulator states map to YANG.               |
| Accuracy and defaults                     | Partial (3/5, 60%) | Not covered | Three metadata leaves appear through schema defaults.     |
| Power cap, nameplate, certifications      | Schema-only        | Not covered | Declared leaves have no adapter mapping.                  |
| Administrative control                    | Schema-only        | Not covered | Control leaves are not accepted or enforced.              |

## Scope and conclusion

This report analyzes the `2026-11-01` module in [the allrun53 YANG directory](../yang/ietf-power-and-energy@2026-11-01.yang) and its integration with the simulator, Sysrepo provider, controller reconstruction, and tests. Its scope is the allrun53 implementation and its own validation evidence.

Here, the NETCONF GET is the unfiltered `ncclient` call `netconf_manager.get()` in [the reconstruction test](../tests/netconf/test_controller_reconstruction.py). It sends a NETCONF `<get>` RPC to the single local endpoint and requests the running configuration and operational state visible to that session. The reconstruction helper consumes the reply's `/ietf-hardware:hardware/component` and `/ietf-power-and-energy:energy-objects/energy-object` subtrees, representing 44 hardware components and 44 Energy Objects. The test passes `device_id="DEMO-NETWORK-1"` separately because that identity is not carried in these YANG trees. Thus this validates reconstruction from one endpoint exposing the combined demo network, not collection from 23 independently addressable devices.

The module defines a broad monitoring and control model. The implementation is strongest for operational discovery: it publishes Energy Object identity, RFC 8348 hardware correlation, relationships, selected power and cumulative-energy values, and a subset of operational power states. It does not implement the declared configuration/control plane. Several other schema elements are schema-only or represented indirectly by defaults.

## Model inventory

| Model element                         | Purpose                                                                                                                                                                                         |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `data-source-accuracy` identity tree  | Describes unknown, inherited, estimated, static, historic, learned, and measured data, with bronze/silver/gold/red precision classes and absolute-tolerance variants.                           |
| `power-factor` typedef                | Integer percent from 0 to 100; defaults to 100.                                                                                                                                                 |
| `power-state` identities              | Base state plus `on`, `off`, and `sleep`; identities are extensible.                                                                                                                            |
| `energy-relationship-type` identities | Directional pairs for powered-by/powering, metered-by/metering, aggregated-by/aggregating, and enabled-by/enabling.                                                                             |
| `power-values` grouping               | Received/provided instantaneous power, nameplate power, accuracy, power factor, locality, and an operational power-cap container.                                                               |
| `energy-values` grouping              | Received/provided cumulative energy, accuracy, and locality.                                                                                                                                    |
| `certifications` grouping             | Zero or more certification identities imported from `iana-power-and-energy`.                                                                                                                    |
| `relationships` grouping              | One entry per relationship type, each with a list of peer IDs and optional details.                                                                                                             |
| `/energy-objects`                     | Read-only (`config false`) operational list keyed by Energy Object ID; optionally maps each object to an RFC 8348 component name, then includes the monitoring groupings and operational state. |
| `/energy-control/energy-objects`      | Writable configuration list for requested admin power state and power-cap limit; its ID leaf refers to an operational Energy Object without requiring an instance.                              |

The `source-component-id` leafref points to `/ietf-hardware/hardware/component/name`. It is not a UUID field. The model keeps the Energy Object ID, hardware component name, hardware UUID, and device identity as separate concepts; device identity is not carried in this module.

## Runtime data path

1. The simulator event is passed to `write_operational_snapshot()` in [netconf_bridge.py](../src/green/netconf_bridge.py).
2. `to_yang_instance()` in [yang_adapter.py](../src/green/yang_adapter.py) produces RFC 7951-shaped `ietf-hardware` and `ietf-power-and-energy` JSON. The bridge atomically replaces the snapshot file.
3. The C plugin in [green_snapshot_plugin.c](../netconf/green_snapshot_plugin.c) subscribes only to operational reads for `/ietf-hardware:hardware` and `/ietf-power-and-energy:energy-objects`. It parses the snapshot strictly with libyang validation and returns a duplicate of the requested root.
4. NETCONF clients retrieve the validated operational data. [controller_reconstruction.py](../src/green/controller_reconstruction.py) uses the source-component name and relationships to reconstruct internal objects; multi-device IDs are supplied out of band.

The provider is a snapshot-backed operational-data source, not a device-control agent. The C plugin has no edit/config subscription or callback for `energy-control`.

## Implementation details

Coverage ratios use explicit element sets: four directional power/energy reading leaves; four simulator power states; and five accuracy, power-factor, and locality leaves. Schema defaults count as represented values, but do not count as application-level inheritance or locality resolution.

| Element                                              | Implementation status             | Observed behavior                                                                                                                                                                                         |
| ---------------------------------------------------- | --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Energy Object `id`                                   | Implemented                       | Adapter checks uniqueness and emits IDs.                                                                                                                                                                  |
| `source-component-id`                                | Implemented                       | Adapter emits hardware component `name`, validates its presence/uniqueness, and creates a matching RFC 8348 component. Tests explicitly distinguish the component name from its UUID.                     |
| `power.instantaneous-power-received` / `-provided`   | Partial                           | Watts are converted to milliwatts. Non-negative values become received; negative values become provided with the absolute magnitude. RFC 7951 64-bit values are serialized as JSON strings.               |
| `power.nameplate-power`                              | Not populated                     | No adapter mapping from internal objects or simulator events.                                                                                                                                             |
| Power accuracy, factor, locality                     | Defaults or schema-only           | The adapter omits these fields. Sysrepo/libyang replies show schema defaults such as `accuracy-like-parent` and power factor `100`; no runtime code computes inherited accuracy or measurement locality.  |
| Operational `power-cap`                              | Not populated                     | The schema defines the currently enforced cap and whether it is limiting; the snapshot adapter does not emit either leaf.                                                                                 |
| `energy.total-energy-received`                       | Partial                           | Only cumulative consumed-energy measurements are mapped, from Wh to mWh. Negative values are rejected. Interval energy is not exported.                                                                   |
| `energy.total-energy-provided`                       | Not populated                     | The internal metric type and adapter handle consumed energy only.                                                                                                                                         |
| Energy accuracy and locality                         | Defaults or schema-only           | Not explicitly populated or derived by the adapter.                                                                                                                                                       |
| Certifications                                       | Not populated                     | The grouping is not used by the adapter.                                                                                                                                                                  |
| `power-state.oper`                                   | Partial                           | `ACTIVE`, `LOW_POWER`, and `OFF` map to `on`, `sleep`, and `off`. An unmapped state is omitted. `HIBERNATING` is intentionally not represented by these identities and remains scenario metadata.         |
| Relationships                                        | Implemented for the current model | All eight directional identities are mapped. The writer rejects self-links, duplicate links, and links whose source or peer is absent from the supplied Energy Object set; peer details carry provenance. |
| `energy-control` admin state and requested power cap | Schema-only                       | No adapter, provider callback, configuration workflow, or enforcement path found. The runtime exposes monitored state only.                                                                               |

## Test coverage details

The overview's Test labels indicate direct assertions in the listed tests. `Not covered` means no direct assertion for that area was found, not that the behavior is invalid.

| Area | Test coverage | Evidence and gaps |
| --- | --- | --- |
| Operational identity and hardware mapping | Covered | [Adapter test](../tests/test_yang_adapter.py) checks Energy Object/component correlation; [NETCONF tests](../tests/netconf/test_read_only_smoke.py) check inventory and source-component mapping. |
| Relationships | Covered | [Adapter tests](../tests/test_yang_adapter.py) check identity mapping and peers; [relationship NETCONF test](../tests/netconf/test_group_a_smoke.py) checks all eight directional identities. |
| Power and energy readings | Partial | [Adapter tests](../tests/test_yang_adapter.py) cover received/provided power and received energy. [NETCONF tests](../tests/netconf/test_read_only_smoke.py) check received power and cumulative received energy; provided energy and several optional metrics lack direct assertions. |
| Power state | Partial | [NETCONF tests](../tests/netconf/test_read_only_smoke.py) check on/sleep/off transitions; [UC 2.9 tests](../tests/uc/test_uc09_wlan.py) and [state fallback test](../tests/uc/test_uc09_state_fallback.py) check hibernation handling. |
| Accuracy and defaults | Not covered | Tests do not directly assert accuracy, power-factor, or locality leaves/defaults. |
| Power cap, nameplate, certifications | Not covered | No direct tests found for these leaves. |
| Administrative control | Not covered | No configuration-write or actuation tests found. |

## Findings and implications

### High: control is declared but not implemented

`energy-control` models requested power state and power-cap values, but the live provider subscribes only to the two operational roots. A client cannot rely on this implementation to accept, persist, translate, or enforce those requests. The distinction between requested cap and currently enforced cap is present in the schema descriptions but has no runtime implementation. Treat these leaves as an unimplemented contract, not working control functionality.

### Medium: operational coverage is asymmetric

The adapter exposes cumulative received energy but not provided energy, interval energy, nameplate power, certifications, locality, or explicit accuracy. It also maps a signed internal power value by direction, while the YANG leaves themselves are unsigned. This is consistent for the currently modeled simulator inputs, but it does not demonstrate a complete implementation of the module's measurement surface.

### Medium: power-state vocabulary is narrower than simulator state

The schema has `on`, `off`, and `sleep`; the internal model also has `HIBERNATING`. The adapter lookup returns no identity for that state, so the operational leaf disappears rather than carrying an approximation. The UC 2.9 test verifies that hibernation is retained as metadata and marked as not defined in standard YANG. Any consumer must therefore interpret an absent `oper` as unknown/unreported, not as `on` or `off`.

### Medium: relationship scope is local to the conversion input

YANG peer IDs are plain strings, but the outbound adapter requires every peer to be among the supplied Energy Objects. This makes conversion of relationships to external or separately retrieved objects fail even though the YANG leaf itself does not encode such a restriction. The current controller also needs device-ID correlation out of band. Multi-device collection should define whether peer IDs are globally unique, device-scoped, or resolved through an external index before broadening this adapter.

### Low: inherited accuracy is descriptive, not resolved

`accuracy-like-parent` is the default identity and its description specifies how to find an ancestor Energy Object via the hardware containment tree. The runtime relies on schema defaults but has no code that walks that tree and determines the ancestor's accuracy. Thus the default communicates an inheritance rule; it does not prove that the reported measurement accuracy has been resolved or checked. Root objects should be explicitly assigned an appropriate accuracy by a producer if that distinction matters to clients.

### Low: standards references still contain placeholders

The module revision and references include `RFC XXXX` / `RFC XXXX: Power and Energy YANG Module` placeholders, including the module's claimed RFC publication reference. These should be updated when the governing document number and status are settled; as written, the metadata is draft-like rather than a final RFC citation.

## Verification

- `pyang -p yang yang\\ietf-power-and-energy@2026-11-01.yang`: passed using the allrun53 virtual environment.
- `tests/test_yang_adapter.py` and `tests/test_yang_manifest.py`: 10 passed.
- The inspected NETCONF tests cover operational GETs, hardware correlation, state transitions, and relationship identities. The live NETCONF suite was not run for this report.

## Recommended implementation order

1. Mark `energy-control` as unsupported in user-facing capability/readiness documentation, or implement configuration callbacks and explicit device-side actuation before advertising it as usable.
2. Decide whether hibernation needs a standard identity extension or should remain intentionally absent; preserve the current no-false-mapping behavior until resolved.
3. Extend internal measurement contracts and adapter tests before exposing provided energy, nameplate values, accuracy, locality, or power-cap state. Include units, uint bounds, and missing-data semantics in those tests.
4. Specify peer identity scope for multi-device collection and adjust validation only after that contract is clear.
5. Replace the `RFC XXXX` placeholders when the module's publication metadata is authoritative.

Useful implementation and test references: [adapter tests](../tests/test_yang_adapter.py), [NETCONF operational tests](../tests/netconf/test_read_only_smoke.py), [UC 2.9 state test](../tests/uc/test_uc09_wlan.py), and [module manifest test](../tests/test_yang_manifest.py).