# Reconstruct the actual successor QA source without new Main reads

This local program reconstructs the already generated Beike recorder/helper source from one recorded source_contract.py and the frozen 31-file generator closure. It never calls generate(), the successor guard, an Android transport, a compiler, an installer or UI.

Required actual input is the complete 20,684-byte recorder/source_contract.py with SHA-256 0cbb8c79b494a529e7cb7fe0ce99eec444103ae7207a02a768dbc76d3bb3cbc3. Until that input is supplied, the program reports missing input; it does not invent a BINDING or produce a substitute closure.

## Exact reconstruction

1. Read the fixed input and actual recorded manifests with byte count/SHA, non-following leaf opens, before/after stat and path checks.
2. Parse the source with Python AST and literal_eval the single top-level BINDING assignment. Do not execute source_contract.py. Preserve Python integer precision and original dictionary order.
3. Require canonical BINDING SHA-256 8f89f253350ba2fa7adce2296e36c66c9029ebd538f10870e44540feab74c980.
4. Pin generate_successor_sources.py and GENERATOR_PINS.json, then let the frozen reference_closure routine verify all 31 original sources.
5. Invoke only render_host and render_helper with the actual binding and exact build name pocket4-successor-qa-build-b34f158f88bbebf112840fd88df25d03.
6. Require the generated recorder and helper manifest bytes to equal the actual 1,759-byte/646f6e4c… and 2,431-byte/dfb9b6a4… manifests, and require helper package org.droidloom.qa.successor.p8f89f253350ba2fa.r1.
7. Check all 13 recorder and 13 helper files individually against the actual manifest counts and SHA-256 values. Require the regenerated source_contract.py to equal the supplied recorded input exactly.
8. Re-read the frozen closure and all pinned inputs before saving anything.

The default is verify-only. Explicit source publication writes only a new local successor_qa/reconstructed/source-generation-r2 tree with O_EXCL files and fsync/readback. An existing output root is never overwritten. The reconstruction receipt is written last; any incomplete write has no success receipt.

## Commands

After the actual source_contract.py has been saved at successor_qa/actual/source-generation-r2/generated/recorder/source_contract.py:

```sh
python3 -B -I reconstruct_generated_source.py
python3 -B -I reconstruct_generated_source.py --write-source-once
```

An alternative local input path may be supplied with --source-contract; the exact same fixed byte/SHA pin remains mandatory. The output location and runtime identities are not configurable.

The generated source files are reconstructed bytes, not newly direct-read remote files. The actual two manifests are copied byte-for-byte into the local source tree. Their historic build/UI flags are retained. The reconstruction receipt explicitly records the method and does not claim build, install, runtime QA or production readiness.

Four local controls cover integer values above 2^53, preserving dictionary order without executing surrounding source, rejecting literal calls and duplicate BINDING assignments, rejecting missing/extra/changed output files, and missing actual input without publication. Synthetic bindings exist only inside those controls and never feed the actual reconstruction entry point.

