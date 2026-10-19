# Two real clean-target normal-kernel builds at one fixed path

Both source-to-kernel builds and QEMU boots completed at published source
`5bcec614c1a075782b6ffaa5a5212fdee29be37d`, tree
`00e70e58dfa0dbf4718db55240136683f0a23310`. Both public entries exited 0,
both normal workers were reaped, and both QEMU guests exited raw33 with full
initramfs markers. Independent saved-output boot checks passed twice.

| Result | A | B |
| --- | ---: | ---: |
| Controller elapsed seconds | 205.324 | 126.244 |
| Target absent before launch | true | true |
| Kernel bytes | 8,288,088 | 8,288,088 |
| Kernel SHA256 | `6c0c382ec88d2e59b58d50abb0ef3671635f30ce08c3b442d2bdc2204821d040` | same |
| Initramfs SHA256 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` | same |

The complete decompressed kernel bytes and initramfs bytes were independently
compared, not just their reported hashes. Each actual kernel gzip capture is
retained separately under artifacts/ and independently hashed; the identical
initramfs is retained once. artifact-bindings.json maps both original QEMU
receipts to those bytes. Serial logs differ and each keeps its own SHA.

The actual retained controller checks that target is absent before A. After
A has exited and copied every run output, it verifies stable-FD ELF bytes
against QEMU, writes and reopens gzip, and records completion. Under the
kernel lock it then rejects symlink/noncanonical target paths, confirms the
cache is ignored, moves only the newly generated target into private custody,
verifies device/inode, and deletes that custody tree. between-builds.json
records removal and target absence; B checks absence again before launch.
The archive never reads today's target or generated manifest.

pair.json and controller.py preserve selected environment, host/username,
exact workspace, epoch, TZ/locale and explicitly unset Rust flag variables.
Both environment logs and actual make commands remain readable. Source and
configuration Git blob/SHA bindings, six checked fixed upstream inputs, and
the source-enforced locked minimal dependency input are in source-bindings.
The separately retained B-only generated-lock follow-up was performed by the
root after the pair; its metadata was stable and bytes match committed b42d.
No A generated-lock snapshot survived cache deletion, and none is recreated.

This proves repeatability only on the recorded host, username and fixed
canonical workspace with the stated environment and two clean kernel target
directories. Cargo registry/download caches were shared. A rebuilt OSDK;
B reused that installed tool. This is not two fully cold toolchain/SDK builds,
and no cross-directory or cross-host bit-identity claim is made. No source
remap, component-metadata rewrite, VMX/SMP coverage or deterministic log claim
is inferred from this result. Historical e884/490 path analysis is separate.

All 35 original output files are indexed. raw-logs.tar.gz retains every byte
of the 31 nonbinary originals, including both full console/make/serial logs,
receipts and exact executed controller. Four original binary paths map to
the three separately indexed artifact files. Every tar member was independently reopened and
checked for byte equality, size and SHA. The three root follow-up records are
unaltered under provenance/. Archive generation used saved files and immutable
Git objects, with no new build, VM, source/Git writes or live target reads.
