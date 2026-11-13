# Deep Gap Analysis: Newly Covered Use Cases

Scope: UC 2.3, UC 2.4, and UC 2.17 were added to allrun53 as deterministic, device-side simulator scenarios. This analysis compares their requirements with the event catalog, operational adapter, target -05 YANG schema, and explicit fallbacks. It does not claim controller or AI-agent implementation.

## UC 2.3: Lifecycle Reporting

Source: [draft-ietf-green-use-cases-02, Section 2.3](https://datatracker.ietf.org/doc/html/draft-ietf-green-use-cases-02#section-2.3).

The draft calls out lifecycle impacts such as manufacturing energy, transport, recyclability, and end-of-life; location-correlated carbon factors; energy mix; and awareness of backup sources. It asks for vendor/database ingestion but does not define a device-side schema, source contract, lifecycle boundary, or calculation method.

Implemented: eight events cover inventory baseline, age review, energy-mix check, reporting close, and gap events. Existing device power can be observed. Unknown age, missing source evidence, carbon factors, and backup-source windows remain metadata or UNKNOWN; no emissions value is fabricated.

Still missing:
- An authoritative lifecycle record keyed to stable device/component identity, with source, revision, date, units, lifecycle boundary, and uncertainty.
- Location and interval alignment for grid-carbon factors, plus a defined treatment of energy mix and backup-source transitions.
- A validated computation for embodied and operational emissions; `total-energy-received` alone is not a carbon measure.

Acceptance for future work: provide versioned source data and provenance, define the attribution interval and lifecycle boundary, then test missing inputs as UNKNOWN and sourced inputs against independently calculated results.

## UC 2.4: Virtualized/Cloud-Native Metering

Source: [draft-ietf-green-use-cases-02, Section 2.4](https://datatracker.ietf.org/doc/html/draft-ietf-green-use-cases-02#section-2.4).

The draft asks for real-time metering at hardware and software layers, but its GREEN WG requirements section is `TODO`. It does not define a VNF identity, host-to-function allocation algorithm, shared-overhead policy, migration behavior, uncertainty, or standardized wire representation.

Implemented: eight events meter an existing compute host, preserve interval Wh internally, advance a monotonic cumulative counter, expose host power/energy, and represent workload/allocation changes as scenario metadata. Per-VNF energy is UNKNOWN and no VNF Energy Object is invented.

Still missing:
- A stable function identity and binding to host, vCPU/GPU/NIC allocation, and time-varying placement.
- A defensible allocation method for shared host idle power, accelerators, storage, and network overhead, including uncertainty and double-counting rules.
- A defined real-time sampling cadence and correlation between workload changes and measurement windows. Current intervals are deterministic one-hour simulator samples, not live telemetry.
- A schema for software-function energy. The target module's `source-component-id` leafref points to RFC 8348 hardware component names, not arbitrary VNF identities.

Acceptance for future work: specify identity, allocation inputs, migration semantics, interval alignment, uncertainty, and a standard schema before emitting per-function measurements. Until then, host-only measurements remain the boundary.

## UC 2.17: AI Agents

Source: [draft-ietf-green-use-cases-02, Section 2.17](https://datatracker.ietf.org/doc/html/draft-ietf-green-use-cases-02#section-2.17).

The draft describes agents that monitor energy and operations data, identify opportunities, coordinate energy-saving actions while preserving service, and learn from outcomes. It requires standardized interfaces and respect for power-state definitions, but does not specify an agent protocol, reasoning schema, objective function, safety model, or feedback format.

Implemented: eight events represent telemetry, candidate, scenario guard result, simulated intent, internal device-state change, observed power, missing outcome-energy evidence, and missing learning feedback. The state transition is internal to the simulator. No AI model, external controller, NETCONF write, configuration RPC, or autonomous action is implemented.

Still missing:
- The telemetry inputs and service/SLA constraints that make a candidate safe; current guard results are scenario metadata, not evaluated policy rules.
- Decision rationale, confidence, provenance, operator approval, rollback, and action acknowledgment semantics.
- Interval-compatible Energy evidence for outcome evaluation. U17-5 currently has instantaneous Power observations only; its `ENERGY_OUTCOME_INTERVAL` gap keeps energy savings UNKNOWN.
- Any defined learning signal, retention policy, or privacy/security boundary.

Acceptance for future work: define an external decision contract and safety policy, add interval Energy evidence, then verify every hypothetical action against independent service constraints. This remains outside the current device-side scope.

## Cross-Cutting Schema and Platform Boundaries

- -05 reports received/provided Power and Energy as unsigned values in mW/mWh. allrun53 keeps accounting intervals in Wh and converts cumulative received energy at the YANG boundary. It has no provided-energy measurement source, certification evidence, nameplate values, or enforced power caps, so those leaves are omitted.
- -05 operational power-state identities are on, off, and sleep. UC 2.9 hibernation remains scenario metadata under `UC2.9/HIBERNATING_STATE_MAPPING`; the adapter does not invent an identity.
- `source-component-id` is a leafref to `/hw:hardware/hw:component/hw:name`, despite nearby draft prose saying UUID. The adapter follows the actual YANG statement and retains hardware UUID separately; see `YANG05/SOURCE_COMPONENT_ID_UUID_DISCREPANCY`.
- The allrun53 isolated Sysrepo repository has not been installed. The shared services were failed at inspection and no TCP/830 listener was available. All 18 live NETCONF tests therefore skipped; schema and offline tests do not establish live provider behavior.

Machine-readable gap details and validation criteria: [fill_in_gaps.json](fill_in_gaps.json). Source revisions and local hashes: [yang_revision_and_source_manifest.md](yang_revision_and_source_manifest.md).
