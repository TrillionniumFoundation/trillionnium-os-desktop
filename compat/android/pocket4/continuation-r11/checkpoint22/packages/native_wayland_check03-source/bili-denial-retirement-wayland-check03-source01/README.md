# Wayland check03: stable absent default pkg-config directories

Source-only, unrun. Root is the sole dispatcher. No engine/service execution or deployment is authorized by this package.

Check02's actual full report (c3b78a325738ce8098bf4e76c58e3fb25e85eeed) stopped at /usr/local/lib/x86_64-linux-gnu/pkgconfig ENOENT. The isolated vendor input gate and locked metadata succeeded for 150 packages (141 registry), all 14 commands were joined with exit0, and the original three lifecycle controls passed. Cargo check did not start. This original failure remains preserved.

Only the checker changes. The nine ACK production sources plus their 500-entry map, original workspace/Cargo.lock, all eight reused authority records, prepared 193-package/8004-file vendor tree, resource profile and command/cleanup gates are unchanged. A default search directory that is absent at bounded before/after observations is recorded as ABSENT and provider_qualified=false. Its nearest existing protected directory is held while the first missing child and named/resolved ancestor identities are checked. Broken aliases, non-directory or permission errors, writable/foreign ancestors, appearing paths and close failures do not become qualified directories. Present default directories still use the complete immediate .pc snapshot and full hashes. Final snapshot equality includes the absence records and all present namespaces.

The fresh actual pkg-config default search order is preserved in PKG_CONFIG_LIBDIR. No default-search directory, system .pc file, fallback location or shared cache is created. Actual unchanged build scripts must still resolve required native metadata and the original offline locked cargo check must succeed; this source fix does not qualify native link libraries, headers, GPU behavior, Android Binder ABI or Main deployment.

Resources remain 2 GiB, one CPU, nice15, fresh 4 GiB MemAvailable gate, 900-second work/1020-second outer deadline. Expected 15 actual commands plus the same three lifecycle controls; the 112 host suite is not repeated. Snapshot equality is a before/after claim, not proof of no transient external change during the whole build.

Reproduce with generateExact(files,H) from reproduce-request.js, with the exact files in this package and the verified UTF-8/SHA256 helper. request-pins.json binds the full request/stdin/stage/transport. Controller inverse edits reconstruct the actual check02 source. Python and Cargo have not run for this candidate.
