# Current-baseline helper source compiler

This pure JavaScript source emits the four helper source bundles and static build requests only after receiving exact actual baseline result, qualification and generated guard bytes. It performs no IO, subprocess, device operation or dispatch.

Inputs to createCurrentBaselineForkCompiler(h).compileHelpersActual(actual, parents):

- h.sha(string) and h.utf8(string): audited SHA-256 and UTF-8 helpers.
- actual: exactly result_raw, result_pin {bytes, sha256}, qualification_raw, current_guard_raw. The external result pin must come from the actual full durable successful qualification job, independently reviewed by Root. A synthetic object is not device evidence.
- parents: byte-exact JSON from parents.json, pinned below. Every source is rehashed against its original frozen manifest before modification.

The source compiler is itself valid JavaScript and was instantiated in V8. An absent actual input is rejected. The new Python/Java sources and controls have not been executed; actual compilation remains required. No actual epoch, helper UID, signed APK or signer is invented.

Parent files preserve historical JSON references byte for byte, including large integer timestamps in their original strings. Transformations are checked by exact inverse substitution. New protocols add three required scope fields: main_baseline_schema, main_baseline_sha256, main_baseline_qualification_sha256. Existing full-tree, window, node refresh, player, idle, single-action and restoration bodies are preserved.

Packages/protocols after a qualifying actual baseline: Bili r9/v9; IHG r2/v2; Amazon r3/v3; BestBuy r3/v3. Target UIDs are taken from the actual baseline result. New helper UIDs/APK hashes/signers remain null until real build/install. Twelve production-parser scope controls are inserted into each existing static builder; inherited controls are retained. No extra child command is added for the new controls.

This helper compiler is independent from the host R5 recorder/source fork that is still being implemented. Neither this artifact nor a static helper build authorizes UI or installation. The unresolved framework exit cause remains an explicit production gate. All 45 apps remain 0 production-ready.
