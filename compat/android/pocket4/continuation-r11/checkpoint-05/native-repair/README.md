# Pocket4 native metadata checkpoint for cp05

This is a text-only checkpoint of exact source subsets, patches, build/audit evidence, and owned host controls. It is not a production deployment, a complete recovered R7 source tree, or whole-app acceptance.

## Observed result and scope

R18 and R19 actual Android failures remain preserved by the root coordinator. R19 isolated ten failed cases to the same host-libc statfs mismatch: ST_VALID (0x20) remained in the raw snapshot while Bionic fstatfs removed it. R20 changes only the successful host-libc snapshot publication on Bionic. The original twelve case assertions are unchanged. An exact Bionic wrapper body compiled in the host control reproduces the ten baseline failures; the fixed Bionic and ordinary glibc controls each observe all twelve expected behaviors. The known NOFILE=0 failure remains an expected red case.

The root coordinator separately reported R20 actual Android PASS for these twelve expected host-libc metadata behaviors, exact package removal, all owned children reaped, and unchanged Main. That primary runtime/root-review export is managed separately at /home/alex/work/pocket4-owned-fd-capability-r20-runtime-export-01/text-bundle.json, SHA256 5f06a1ae5e52bb272406a8bb12f60e61de9d906d1605c8960b16bb86642f1ef6. This checkpoint does not duplicate its eighteen files.

## Source ancestry

- R18 source is the immutable fifteen-file actual probe source; its eight real metadata files match the R7 subset.
- R19 changes only diagnostic fields and metadata; its eight core files match R18.
- R20 changes one core file at the Bionic host-libc publication boundary, plus the owned probe identifier and case-plan metadata. All original case comparisons are byte-identical to R19.
- R8 revision03 contains verified R16 lifecycle/syscall hook deltas, the eight R7 metadata inputs, and explicit ART private protocol source. It does not contain the missing complete R7 adapters. It retains the pre-R20 raw owner input; apply the separate R20 core delta only when creating a NEW full candidate manifest.
- Published cp03/cp04 manifests are read at their fixed Git commits. The recovered proc_maps_open pair is individually pinned; no reconstructed tree is claimed to have the old R7 thirty-six-file freeze hash.
- ART and Bionic source references are pinned source references. There is no claim here that their complete installed binaries were rebuilt from those references.

## Reports are scoped independently

The R8 first host attempt failed EPERM because the owned operator child inherited a nonzero capability bit. The gate was not weakened. Revision02 clears capabilities only in its own host child and verifies the empty set before testing. Its eleven controls pass. Revision03 Android translation-unit evidence includes three passing exec TUs and remaining baseline/candidate dispatcher/ART compilation setup failures. No complete ART or engine link is qualified by those TU checks.

The updater pair gate was built from a private copy of the exact R15 updater base. Nine tests pass, including real owned ext4 APEX and EROFS fixture traversal, mixed version rejection, component hashes, and whole-APEX metadata preservation. It has not built or activated a candidate ART APEX and does not establish APEX signature verification. The patch must be reviewed/merged into the current project version; older full updater files must not replace current unrelated changes.

## Remaining production blockers

Guest raw statfs syscall representation must be tested separately from the normalized host-libc Snapshot. Do not directly copy the normalized value into a guest raw-syscall buffer or restore 0x20 by assumption. A typed retained raw snapshot and independently verified guest layout are possible next steps, not completed work.

Other open gates include trusted factory positive provenance and O_PATH reopening, open/readlink ownership and negative-alias races, NOFILE=0, raw-owner host-native credential/root/mount and final-thread lifetime, complete ART/engine paired builds, signed APEX qualification, and actual application acceptance. Features remain default-off in the R8 source.

## Transfer format

MANIFEST.json lists every UTF-8 payload file and exact SHA256. The deterministic tar.gz contains only these text files plus the manifest. The sibling transfer directory splits base64 of that archive into ASCII files of at most 60000 bytes; its manifest records independent hashes and exact offsets. Decode the concatenated chunks and verify the archive SHA256 before extracting.

No APK, ELF, object file, image, signing key, commercial APK, or commercial application log is included.
