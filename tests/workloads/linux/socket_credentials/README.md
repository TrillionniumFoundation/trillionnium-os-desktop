# Socket credential lifetime regression

`socket_credential_probe.c` is the frozen second Linux-reference probe: 59 ordered
records covering STREAM/DGRAM/SEQPACKET, actual capability-free saved-ID changes,
SCM_RIGHTS handoff/CLOEXEC, old/new queued SCM_CREDENTIALS, MSG_PEEK, connection
identity through exec/exit, real forged-credential rejection and complete reap.
`socket_group_probe.c` includes that source and supplies a separate 16-record
STREAM/SEQPACKET SO_PEERGROUPS fixture with actual CAP_SETGID=64, not caps zero.

The exact static binaries are pinned by the original Linux receipt hashes. The
runner checks the included source for the group probe as well. Each run uses the
original 512 MiB, SMP1/KVM, 120-second guest bound, original 8 MiB initramfs and
16 MiB mapped-image bounds. Inner child/parent alarms remain 20/60 seconds.

```sh
python3 -I -B tests/workloads/linux/socket_credentials/run_guest.py \
  --suite lifetime --kernel /absolute/qualified/kernel.elf \
  --initramfs /absolute/original/initramfs.cpio.gz \
  --probe /absolute/socket-credential-probe --output /absolute/new-evidence
# Repeat with --suite groups and the original socket-group-probe binary.
python3 -I -B tests/workloads/linux/socket_credentials/test_check.py
```

`check.py` accepts only the exact ordered record structure and semantic values of
the hash-pinned successful Linux references, plus a unique successful probe exit,
reap/summary and final boot marker, raw QEMU 33 and no timeout. It rejects changed
JSON types, missing/duplicated/reordered records, incomplete identities, wrong
capability sets, marker-only edits and the retained actual failures. Four host
mutation tests exercise these rejection paths; they are not native passes.

`socket_credential_probe_v1.c` and `linux-reference-01.*` retain the first probe.
`native-4aab-baseline-01-*` is its actual incomplete MSG_DONTWAIT failure: the
kernel ignored the datagram flag and the original alarm terminated the probe.
The v2 O_NONBLOCK fixture isolates credential lifetime without closing that API
bug. `native-4aab-baseline-02-*` is the complete 15-failure lifetime baseline;
`native-group-4aab-baseline-01-*` is the complete four-failure group baseline.
Raw poweroff status 33 is not success when the probe failed or did not finish.

See [the owner and scope contract](../../../../docs/agents/SOCKET_CREDENTIAL_SNAPSHOTS.md).
Frozen source `22e0a19f8ab95f730e0fedd85462157ed3d9a10e` passed the complete
original four-suite/ordinary/all-prior-native chain and these exact 59/16 records.
See the source/ELF-bound receipt linked in the owner contract; MSG_DONTWAIT remains
a separate open defect, and prior or later source states do not inherit this result.
