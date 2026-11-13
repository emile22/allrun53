# FILL_IN_GAP Registry

These entries document unsupported inputs or representations without removing their UCs from execution. Fallbacks remain scenario metadata or explicit UNKNOWN values; no gap invents a YANG node.

## `UC2.3/LIFECYCLE_SOURCE_DATA`
UC/event: UC 2.3 / U3-0. Asset age and lifecycle evidence remain UNKNOWN or unavailable.

## `UC2.3/CARBON_ATTRIBUTION`
UC/events: UC 2.3 / U3-2, U3-4. Carbon factor and total remain UNKNOWN.

## `UC2.4/PER_VNF_ATTRIBUTION`
UC/events: UC 2.4 / U4-0, U4-4. Host measurements are visible; VNF energy remains UNKNOWN.

## `UC2.9/HIBERNATING_STATE_MAPPING`
UC/event: UC 2.9 / U9-2. The hibernation mode stays in scenario metadata; operational power state is omitted.

## `YANG05/SOURCE_COMPONENT_ID_UUID_DISCREPANCY`
Cross-cutting schema feedback: the -05 leafref targets component/name despite nearby UUID prose. The adapter follows the leafref and retains UUID separately.

## `UC2.17/AGENT_REASONING`
UC/event: UC 2.17 / U17-3. Intent is simulated scenario metadata only.

## `UC2.17/ENERGY_OUTCOME_INTERVAL`
UC/event: UC 2.17 / U17-5. Power is observed, but interval Energy and energy savings remain UNKNOWN.

## `UC2.17/LEARNING_FEEDBACK`
UC/event: UC 2.17 / U17-6. Learning feedback is NOT_MODELED.

Machine-readable fields, evidence, TODOs, and validation criteria are in [fill_in_gaps.json](fill_in_gaps.json). Each ID has an adjacent `FILL_IN_GAP` code comment and a non-fatal event fallback.
