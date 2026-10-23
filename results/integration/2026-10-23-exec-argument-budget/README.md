# Aggregate exec argument budget evidence — 2026-10-23

## Result

The ordinary Asterinas product kernel passed the native regression with 19 checks covering combined argv/envp bytes, pointer-slot overhead, per-string bounds, stack-relative limits, execveat, and shebang argument replacement. The shared pre-copy budget prevents unchecked aggregate copies before the new address space is established.

- Product source commit: `e0b5caa5100c7f9fb4b3219a4359642e5e791448`.
- Product source tree: `f552d8fec33d33c2afe4870e2933e5894a6c851f`.
- Product ELF SHA256: `b9d0d3780de7aa7cb2932a896eb894914e18a6a059881ad9ee1a948994205378`.
- Passing probe source commit: `8f2ea44317a9f5205fe09cc1f2fb87021cd18bfe`, tree `e55d1d685c7e992db3aa9ada383606a978fc8a52`.
- Probe ELF SHA256: `cdf00ca90e9b77ce72a4a4527d4a1b9c982a5de7699c93ab59492650f465dd2c`.
- Passing receipt SHA256: `7928db5ab5c352381d384c936fe217654cf4c34c47fa5b502b10b1649e76c5b6`.

The product and probe revisions are intentionally distinct: the final probe revision changes only the boot log level to avoid asynchronous kernel informational logs interleaving C output records. Kernel and build-wrapper bytes were checked identical. The strict oracle was not relaxed.

## Preserved rejected run

The initial native run at info log level returned from QEMU, but interleaved syscall logging made the strict record parser reject its output. Its result remains false and its original serial SHA256 is `642f74d75eb62d08e97370b3710c387e395e66ad788c6473a7cc18db6d0f3a91`. The passing warn-level rerun uses the same product ELF. Both raw serial streams, receipts, and full source manifests are archived.

## Scope

This is an aggregate exec-copy admission limit. It does not establish a complete memory controller, watchdog, global recovery reserve, native F1/F2, or production authority. It is a separate change from the later physical user-frame account.

`archive-manifest.json` binds every copied input by raw and stored SHA256. Large input files use lossless gzip. The original kernel and probe binaries are identified in the receipts; their frozen paths are retained, while source and raw execution evidence are committed here.
