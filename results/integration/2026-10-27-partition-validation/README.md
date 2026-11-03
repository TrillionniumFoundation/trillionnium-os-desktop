# Pinned partition parser execution — 2026-10-27

This is the actual optional `aster-block` decoder execution, not an inherited
`aster-core` or four-crate result.

| Input/result | Observed value |
| --- | --- |
| Desktop source | `d343c35da641f86a3fa0ff6c4293d4948bbe0b2e` |
| Working-tree difference at execution | Only the two newly generated `aster-block` lock/report files, recorded in `environment.json` |
| Compiler | `nightly-2026-07-21`, rustc `87e5904f5eb6398af6b22eac2802c78934260c48` |
| Test-base lock | 118 packages; SHA256 `b07ed64d57dd1122530f689ea6d4fb348c04f28b1a0e34589c67cc7c8fd1fc5d`; no external drift from the immutable upstream seed |
| OSDK | Built and installed from the same checkout into a private Cargo home |
| Guest | x86-64, q35, TCG, one vCPU, 512 MiB, SeaBIOS; no network or data disks |
| Required tests | 24 declared, 24 started, 24 passed, 0 failed, 0 filtered, 0 soft-skipped |
| Raw QEMU exit | 33, not timed out |
| Kernel ELF | 2,450,336 bytes; SHA256 `1a921de2d2124141d823b7d96789083168a38733294eb3785b1c340c307a3ae7` |
| Raw serial | SHA256 `948e55fc11b9dcf65dee683e937313acd021692cbedc56822c30b96f119d677c` |

The original kernel lock remained
`af94d71680ecf3b9631e21c958263d5e41229033214f88dcff858bb14765a666`;
the original OSDK lock remained
`99a21f72f6a9f1582553b34f06e80f86e539f38e62eab7a0847afd0906e75be3`.
Cargo's initial optional lock generation was offline after a separate locked
fetch of the immutable existing dependency inputs. Missing Git cache material
caused an initial preparation refusal; the subsequent original locked fetch
supplied it before successful normalization. No lock text was fabricated.

The same pinned compiler separately passed the 24 host decoder cases. The
committed `commands.json`, `environment.json`, `source-inputs.json`,
`aster-block/osdk-test.log` and raw guest files retain the actual source,
commands, compiler, checksums and execution. Build-path names are historical;
the original ELF stays on the execution host and is identified by its hash.
The serial and build logs preserve their original bytes, including carriage
returns. Revalidate the retained guest report from the repository root:

```sh
python3 -I -B support/build/ktest/check.py \
  results/integration/2026-10-27-partition-validation/aster-block/guests \
  --crate aster-block
```

This qualifies the bounded production decoder running inside the kernel with
controlled reader fixtures. It does not qualify physical disks, the complete
block I/O stack, DMA, power loss, SMP, all kernel suites, a production Hepta
backend, or an installed Desktop product. Later source combinations retain
their own build and acceptance obligations.
