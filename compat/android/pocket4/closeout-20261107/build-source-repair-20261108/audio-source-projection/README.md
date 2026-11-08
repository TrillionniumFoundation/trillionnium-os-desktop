# Audio source projection: prerequisite only

**State: `PREREQUISITE_RECONSTRUCTED_FINAL_REPAIR_PENDING`.** This directory records the boundary for the ongoing audio repair. It contains no final provider repair patch and reports no final repair test pass.

The [common base and audio prerequisite](../source-prerequisites/README.md) reconstruct 395 text source files from immutable local commit `fc90abf09eb0f09cc5f46bead149b4d324882722`, tree `1f28d43707ff707affde982e2e8b505dd728ebc0`. Both Pocket4 and Mac independently reproduced those exact bytes and executable modes.

The cumulative prerequisite includes the earlier host/status changes through `17ca3fa` and `5957add`, the real PCM input patch, source lock, resource-budget changes and original audio resource fixtures. It must be applied directly after the common base, without additionally applying the old host/status patch.

The final original-provider repair is still changing as additional real provider dependencies are checked. The prior 80,781-byte intermediate patch and its 18 tests are deliberately absent; those observations do not qualify a later candidate. The complete audio APEX build, source restoration/release, installation and runtime behavior remain unqualified. A later verified update can add the exact final repair to this same directory.
