# Exact-pin S08 Servo qualification adapter

This directory contains the test-only source appended to Servo's existing `components/servo/tests/accessibility.rs` after the reviewed retained-node patch is verified. It is not a standalone crate, product adapter, installed binary, listener, or alternate browser runtime.

The permanent S08 workflow compiles this source inside exact Servo commit `670ae8a70801b162e186f81cbb5bdd2d59c39108`, starts one real WebView-owning test process, and connects it to the product-side AgentPort/BrowserActor/receipt integration test through an absolute private atomic-file mailbox. The source proves real navigation, AccessKit observation, retained-node click, exactly-one callback completion, DOM mutation, second navigation, and close on that exact host test environment.

The mailbox protocol and synthetic procfs facts are qualification fixtures only. They provide no product IPC, installed-systemd, external-network, hardware, signing, publication, or release authority. See `docs/architecture/S08_SERVO_BROWSER_ACTOR_VERTICAL_SLICE.md` and `contracts/s08-servo-runtime-bridge.v1.json`.
