# Full Wayland retirement ACK compile-only candidate

State: **SOURCE_ONLY / UNRUN**. Root is the sole dispatcher.

This package uses the exact nine final production sources and 500-file manifest from `f8d3aa8c7bde5c81da5fed04eaea517fbfa42ba5`. It retains the original workspace and Cargo.lock and runs exactly one full `droidloom-wayland` binary `cargo check --offline --locked -j1`. It does not repeat the separate 112 host tests.

Resource profile is 2 GiB, one CPU, nice 15, a 900-second work qualification window and a 1020-second tool timeout. A fresh bounded meminfo record is saved before requiring 4 GiB MemAvailable. The global swap observation supplies no admission budget. No Main process or Android command is accessed.

The fixed pkg-config executable and dynamic libraries are qualified on this attempt. One bounded query obtains its actual default pc_path. Every returned directory and finite immediate .pc namespace is checked and rechecked; missing or unsafe input fails without a guessed layout or fallback. These are first-observed inputs, not old prequalified pins. System native headers/libraries and GPU ABI are outside this source-level check.

Run the pure JS `reproduceWaylandCheckRequest(files, H)` from `reproduce-request.js` with `pure_js_binary.js` helpers to regenerate exact-request.json, stdin.json, stage.py and transport.py. The packet contains 11 transferred source files and five fixed reused authorities; stdin remains below one MiB.

On execution, attempt01/result.json and each complete commandNN.stdout/stderr are create-only. The summary includes the exact failure phase, last original log pins, resource observations and child cleanup. A Rust compile error or missing dependency remains a failure. No source, package, tool, system limit, service, ref or PR outside this owned workspace is changed.

The full compiled binary target metadata and successful compiler completion are required. This alone will not establish real compositor/GPU retirement, Android Binder ABI, installed Main provenance or whole-App production readiness.
