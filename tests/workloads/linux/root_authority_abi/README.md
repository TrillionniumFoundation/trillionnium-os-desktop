# Original Root process ABI preflight

This workload checks the Linux interfaces used by the original Hepta Root
launcher and owner channels. It executes the **same static C ELF** first on
Linux and then in an existing ordinary Asterinas guest. It neither constructs
a Hepta authority nor runs the original writer, FinalUse, durable checkpoint,
CPU effect or recovery. Every receipt keeps `g2_complete=false`.

The 27 checks cover these connected operations:

* Stable canonical boot UUID, live nonzero `/proc/<pid>/stat` start time,
  retained `/proc/self/exe` inode identity and mountinfo mountpoint layout.
* `memfd_create(MFD_CLOEXEC|MFD_ALLOW_SEALING)`, Root-owned regular inode with
  no links, mode 0400, exact payload and all four seals. Real write, grow,
  shrink and shared writable mapping attempts must fail with `EPERM`.
* A Root-owned setgid private Unix socket directory. Its socket must inherit
  group 60001. A real child marks the entire descriptor table CLOEXEC, keeps
  only explicit stdout/stderr, drops all UID/GID fields to 60001, clears all
  supplementary groups and five capability sets, sets no-new-privileges, and
  uses `execveat(AT_EMPTY_PATH)` on the retained exact ELF descriptor. The
  execed image verifies all those restrictions and inherited descriptor
  closure. This deliberately tests ordinary process ABI; an exec cannot
  transfer an HOS2 Process/image role.
* Actual post-drop client `SO_PEERCRED`, original Root server `SO_PEERCRED`,
  exactly two `SCM_RIGHTS` descriptors received with
  `MSG_DONTWAIT|MSG_CMSG_CLOEXEC`, sealed memfd metadata/readback, and the
  received Root pidfd's exact `anon_inode:[pidfd]` link and fdinfo PID.
* A pidfd opened for that still-live child must initially have no `poll` or
  `ppoll` events.
  Signal zero must succeed; pidfd-delivered SIGKILL must wake `ppoll` with real `POLLIN`
  without `POLLERR`/`POLLNVAL`; `waitpid` must reap that child with SIGKILL;
  signaling the retained pidfd afterward must fail with `ESRCH`.

The parent keeps custody of its unreaped child until `waitpid` completes.
An inner alarm, outer timeout, unexpected errno, incomplete child proof,
duplicate/missing case or wrong guest exit fails the test. There is no skip
or substitute process identity. A failed test retains its output. The
success path closes descriptors and removes the private socket directory.

## Linux reference and native replay

Run from the repository root. Use a real Linux Root with UID/GID 60001
available in its user namespace; restricted development containers can reject
the required `chown`/identity change and are not an equivalent reference.

```sh
sudo python3 -I -B tests/workloads/linux/root_authority_abi/run_linux.py \
  --output /data/root-abi-linux-reference

python3 -I -B tests/workloads/linux/root_authority_abi/run_guest.py \
  --kernel /data/frozen-positive-556/product-kernel.elf \
  --initramfs build/asterinas/rootfs.cpio.gz \
  --probe /data/root-abi-linux-reference/probe.elf \
  --reference /data/root-abi-linux-reference/result.json \
  --output /data/root-abi-native
```

The Linux runner uses GCC `-O2 -std=c11 -Wall -Wextra -Werror -static`, keeps
the source/compiler/binary hashes and raw stdout/stderr, and requires all
27 checks. The guest runner reuses the original initramfs packing and ELF
inspection helpers, freezes the exact supplied kernel and reference ELF,
and checks hashes again after QEMU. It preserves the original 8 MiB
compressed-initramfs bound, one CPU, 512 MiB memory, KVM and ordinary boot
marker. A complete probe, exit marker 0, final boot marker and raw QEMU exit
33 are all required. No kernel rebuild is part of this runner.

The `/data` paths above are examples: use new evidence directories and the
actual previously frozen ordinary kernel/initramfs pair. Do not overwrite
an earlier failed run. Source inspection alone is not an ABI pass; a Linux
pass alone is not an Asterinas pass. Passing this workload establishes only
this ABI preflight, never the separate original-entry G2 gate.

The failure oracle is exercised independently:

```sh
python3 -I -B -m unittest discover \
  -s tests/workloads/linux/root_authority_abi -p test_check.py
```
