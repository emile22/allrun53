# Use-Case Coverage

`allrun53` executes all 17 use cases in numeric order. Each has a deterministic event sequence; event IDs are local simulator identifiers, not IETF-standard event names. Under-specified behavior remains executable with explicit `FILL_IN_GAP` metadata and a non-fabricating fallback.

| UC     | Minimum events | UC      | Minimum events |
| ------ | -------------: | ------- | -------------: |
| UC 2.1 | 8              | UC 2.10 | 8              |
| UC 2.2 | 10             | UC 2.11 | 8              |
| UC 2.3 | 8              | UC 2.12 | 10             |
| UC 2.4 | 8              | UC 2.13 | 8              |
| UC 2.5 | 8              | UC 2.14 | 10             |
| UC 2.6 | 8              | UC 2.15 | 8              |
| UC 2.7 | 8              | UC 2.16 | 10             |
| UC 2.8 | 8              | UC 2.17 | 8              |
| UC 2.9 | 10             |         |                |

Minimum total: **146 events**. There are no deferred or skipped UCs. Lifecycle/carbon inputs (UC 2.3), per-VNF attribution (UC 2.4), hibernation state (UC 2.9), agent reasoning/learning (UC 2.17), and the -05 component-name/UUID prose conflict have explicit entries in the [FILL_IN_GAP registry](fill_in_gaps.md) and [machine-readable registry](fill_in_gaps.json).

The event meanings follow the upstream [GREEN use-case draft](https://github.com/emile22/draft-ietf-green-use-cases/blob/main/draft-ietf-green-use-cases.md).
