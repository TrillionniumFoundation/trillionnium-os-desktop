# F1 CI source pair convergence

The workflow previously fetched Desktop `7d8906ef` while its checked-in source review required `0187bd57`. It now reads the exact Desktop and Hepta heads from the same source review consumed by the original builder. Full 40-digit commit/tree identities are validated before writing either environment value. The existing exact source/tree/blob verification remains unchanged.

The actual workflow Python block was executed against the current review and produced the reviewed pair. A malformed second repository head was rejected before any environment output. The original runtime host suite passed 68 tests. The kernel, ABI and build paths now trigger this workflow as well.

This verification fixes source selection. It does not claim a new guest execution or qualification of a later source pair. Historical runtime/store results remain bound to their original sources.
