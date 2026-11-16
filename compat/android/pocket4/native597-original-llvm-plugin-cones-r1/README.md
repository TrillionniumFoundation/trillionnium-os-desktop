# Native597: include the original LLVM and Clang Soong plugins

The strict ordinary Native engine/ART build reached Blueprint parsing and failed
on `llvm_defaults`, `llvm_tblgen`, `force_build_llvm_components_defaults`, and
`clang_tblgen`. The selected LLVM and Clang projects included Blueprint consumers
of these types, but their sparse selections omitted each project's `soong`
directory. Their locked Git trees contain the original registration code.

## Source change

`native597-original-llvm-plugin-cones.patch` updates two normal producer files.
The Native source lock appends `soong` to `external/llvm` and `external/clang`.
The pair producer binds the new exact lock bytes and the same two additions in
its existing source-extension validator. Its new Rust regression test rejects
the original missing-cone selection, a Blueprint-only selection, a single-Go-file
selection, and a different project commit. It retains the complete ordinary pair
targets and Strict dependency handling.

All 597 project identities and commits, all eight root links, and every other
source selection remain unchanged. LLVM stays at
`429d6c6097aea3326e49fc8e87cc7658b750c5d7`; Clang stays at
`bdc4d062dc4550869e0825da19fe8fa720db860a`.

The eight files under `original/` are the exact upstream files from those
commits. Each was independently obtained from the original public Gitiles URL,
verified against its SHA-256 and Git blob SHA-1, and then compared with the files
produced by the normal source reconciler. `source-pins.json` contains those
identities, the patch preimages, and the updated source hashes.

## Normal validation

The patch was applied to the exact previously qualified 458-file recipe, which
includes the explicit Go-budget fix. A normal clean Git commit produced
`e5cfc1ed9d6d9469b8a30ef896301ce578f46991`, tree
`c5710921146efd61a98527e1f3cf4495c3264856`. The old recipe remained unchanged.

Using Rust 1.93, the normal tool build completed all 23 owned commands. The
requested filters passed 26 source-tool tests, 21 ordinary-pair tests, and 13
pair-producer tests, with no failures or ignored tests. Filter counts can
overlap. The source and updater binaries were compiled through normal Cargo.
They were copied to the independent build host, their complete bytes were
verified, and both actual loaders and normal lock validation succeeded.

From the complete matching recipe, the same normal test/build commands are:

```sh
cargo test --locked --offline -j 1 -p droidloom-source
cargo test --locked --offline -j 1 -p droidloom-update ordinary_pair
cargo test --locked --offline -j 1 -p droidloom-update native_generation_pair
cargo build --locked --offline -j 1 -p droidloom-source -p droidloom-update
```

The independent host then executed normal verification of the original 597
projects, normal reconciliation of the two cones, and normal verification of the
new source. All five owned commands, including the two retired-unit checks,
returned zero. The three original ownership locks were released and individually
probed free. The normal reconciler generated manifest SHA-256
`924637edc039b0f23013a7ca921b4c6c05a0800574599742cddcc75eeed160e2`
(386,435 bytes). Its exact parsed delta contains only the two approved cone
additions and the new source-lock digest.

The existing 43 lifecycle, actual executable/argument/temporary-directory,
resource, Go-metric, and ordinary-pair controls also passed on the build host,
with zero skips. The full profile and runtime ownership implementation remain
unchanged. `validation.json` holds compact actual results and receipt hashes;
private device, account, and host logs are excluded.

## Acceptance boundary

This capsule qualifies the normal source selection and tested build tools.
The strict Android pair full attempt runs separately with the newly generated
manifest, the new normal recipe, the previous failure's restoration evidence,
and fresh admission. Full engine/ART artifacts, actual translation units,
signing and payload verification, QPR1 compatibility, deployment, and application
runtime acceptance remain independent required gates. No gate in this capsule
grants those qualifications.
