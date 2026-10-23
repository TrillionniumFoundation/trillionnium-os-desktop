# Native CI: bootstrap the isolated Rustup home before installation

## Fixed source and change

This follow-up is based on Desktop `ce8378b71c426e6f5e0227b65624895cb81212cd`
(tree `8fe94570ea0ad5d63c44c6c02e5872fa532abcca`) from PR #257.
Only `.github/workflows/f1-original-runtime-native.yml` changes. Its original
blob is `d7a3d862d0037f1e3fa3fdcd39b26ec562927511`; the new blob is
`b8f5d5c2ce7e847fcaaa9c18dd367f3c4174699e`.

Source commit: `c120d6c92d9de4b2bfb96bc97512c066953f565d`.
Source tree: `a16c8c12fb7f2247b4d10f2e1bccb417b885fc84`.
All 8,157 remote non-tree entries were compared with the complete base tree plus
this one replacement; no other source changed.

The workflow creates a fresh `CARGO_HOME` but the ordinary kernel wrapper uses a
sanitized PATH containing only that home's bin directory and system directories.
An earlier #257 revision lacked proxies entirely. The current base added the
correct proxies after both toolchain installations. This patch moves the same
bootstrap before either installation so Rustup can resolve its own isolated-home
path throughout setup. It preserves the upstream binary, source pins, profiles,
build/guest commands, deadlines and qualification gates.

## Actual validation

The exact five-line bootstrap stanza was extracted from the candidate workflow
and run with the existing official Rustup executable (SHA256
`5be191e8c70a5007074254cb74d78dbfdd25cd5a61c27de7b8e5410122ec24f4`)
and existing official Rust 1.95.0 toolchain. Before bootstrap, actual calls to
`rustc -Vv`, `cargo -Vv` and `rustup component list --installed` under the
sanitized PATH each exited 127. After bootstrap, all three exited 0. The new
rustup link resolves to the exact same original executable. All seven command
stdout/stderr pairs and the execution receipt are retained without truncation.

This demonstrates real proxy resolution; it does not reproduce a fresh toolchain
installation failure, run a network installation, compile a kernel, or execute
QEMU. It is not an F1/G2 qualification. Separate static validation rejected
duplicate YAML keys, parsed the embedded Python, and ran `bash -n` on all eight
shell steps successfully.

`raw-evidence.tar.gz` is a deterministic, lossless archive of the exact final
reproducer, extracted stanza, current/base workflows, patch, complete execution
logs, syntax receipt and source readback. `manifest.json` lists every raw member
and its complete byte length/SHA256. Earlier exploratory bootstrap variants are
not part of this final execution or archive and are not claimed as its evidence.

## Remaining gates

The PR remains a candidate until its actual source-head native CI executes.
The original native workflow still needs fresh ordinary build/boot/QueryAbi,
three original userspace binaries, and the real guest lifecycle. No production
issuer, trusted role, durable retirement, physical device or power-loss result
is conferred by this setup correction.
