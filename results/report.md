# Contract experiment

All inputs are fictional. No model or external API was called.

The guarded packer met 14/14 authored contracts; the deliberately incomplete recent-first baseline met 1/14, and validity-aware recent-first packing met 10/14.

| Case | Expected | Recent-first | Validity + recent-first | Guarded |
|---|---|---|---|---|
| latest-explicit-version | ready | fail | fail | pass |
| historical-before-new-version | ready | pass | pass | pass |
| mandatory-low-recency | ready | fail | fail | pass |
| expired-required | refused | fail | pass | pass |
| conflicting-required | refused | fail | pass | pass |
| withdrawal-no-resurrection | refused | fail | pass | pass |
| draft-no-resurrection | refused | fail | pass | pass |
| changed-source-no-resurrection | refused | fail | pass | pass |
| budget-too-small | refused | fail | pass | pass |
| unicode-byte-budget | ready | fail | fail | pass |
| no-authority-from-text | ready | fail | fail | pass |
| missing-required | refused | fail | pass | pass |
| cross-tenant-key | refused | fail | pass | pass |
| unauthorized-tenant | denied | fail | pass | pass |

These cases target known failure boundaries. They are not a representative distribution of agent tasks,
and passing them does not establish prompt-injection resistance, correct model answers, or production authorization.
