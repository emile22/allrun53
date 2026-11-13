# YANG Revisions and Source Manifest

Target: `draft-ietf-green-power-and-energy-yang-05`, published 2026-11-02. Local SHA-256 values are recorded in [the machine-readable manifest](../install/yang-module-manifest.json).

| Module                  | Revision   | Imports                               | Status in allrun53 repository |
| ----------------------- | ---------- | ------------------------------------- | ----------------------------- |
| `iana-hardware`         | 2018-03-13 | none                                  | Not installed                 |
| `ietf-hardware`         | 2018-03-13 | inet-types, yang-types, iana-hardware | Not installed                 |
| `ietf-inet-types`       | 2025-12-22 | none                                  | Not installed                 |
| `ietf-yang-types`       | 2025-12-22 | none                                  | Not installed                 |
| `iana-power-and-energy` | 2026-11-01 | none                                  | Not installed                 |
| `ietf-power-and-energy` | 2026-11-01 | ietf-hardware, iana-power-and-energy  | Not installed                 |

The allrun53 repository has not been installed, and no service or schema repository was changed. The host services were failed at the last read-only status check, so this is not live NETCONF validation evidence.

## Schema discrepancy

The -05 YANG statement for `source-component-id` is a leafref to `/hw:hardware/hw:component/hw:name`. Nearby prose says UUID. allrun53 follows the actual YANG path, keeps `hardware_component_uuid` separate, and records the discrepancy for draft feedback. The operational module sources remain unmodified copies.

## Sources

- GREEN Power and Energy modules: [draft -05](https://datatracker.ietf.org/doc/html/draft-ietf-green-power-and-energy-yang-05).
- Hardware: [RFC 8348](https://www.rfc-editor.org/rfc/rfc8348.html); IANA hardware identities from the [IANA YANG module registry](https://www.iana.org/assignments/yang-parameters/).
- Common IETF types: [RFC 6991](https://www.rfc-editor.org/rfc/rfc6991.html); allrun53 selects the local 2025-12-22 snapshots as compatible revisions.
