# Real chmod, chown and mount permission replay

`permission_probe.c` executes **32 real syscall cases**: 23 file permission
cases and 9 mount, unmount and `pivot_root` cases. `run_permission_guest.py`
first executes one frozen static ELF on the Linux CI host, then replays the
same ELF on the exact ordinary Asterinas product kernel accepted by the
existing QueryAbi gate. This is an additional gate; it does not replace the
SCM_RIGHTS, RLIMIT_NOFILE, QueryAbi, or complete Linux workload gates.

The permission profile is qualified only when both fresh Linux and guest
receipts pass and their raw records are independently accepted. Parser unit
tests, compilation, historical boot records, and kernel test listings do not
qualify the profile. Its receipts explicitly leave pinned Debian 13 and Hepta
HOS2 qualification false.

The candidate kernel carries five upstream permission backports and two
separate local corrections. Successful `Path::chown` updates ctime even when
both IDs are omitted and no mode/owner/group setter runs. The local ctime
change is not attributed to the upstream backports. The 32nd added behavior,
`chown_nonowner_noop`, verifies it through actual Linux and guest observations;
its implementation alone is not a qualification result.

New RAMFS/tmpfs roots also inherit the caller's filesystem UID/GID through
the existing `current_fs_ids` helper, which retains root IDs for early boot
and kernel threads without userspace credentials. The raw Linux/guest
comparison from [PR #212's A06 run](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39369677714)
exposed root IDs `65533:65533` on Linux and `0:0` on the prior Asterinas
candidate. The existing `mount_sysadmin` case now checks those IDs and mode
`0755` in both C and the independent Python oracle. Rejudging that retained
old guest record fails precisely the root UID/GID checks while the retained
Linux reference still passes. Fresh execution is required for the corrected
kernel; the historical 32-case pass does not qualify this stronger check.

### Backport sources

The five upstream commits are applied as patches to the existing v0.19.0
vendor base. The local FD reservation/install behavior in `fsopen` and
`fsmount` is retained, as are the project's CPU and process-image changes.

| Upstream commit | Scope |
|---|---|
| [21c0b04d3e012589e1e7339f46c818574b56b7b1](https://github.com/asterinas/asterinas/commit/21c0b04d3e012589e1e7339f46c818574b56b7b1) | chmod authorization, group checks and pseudo-inode creator FS IDs |
| [9f53affb22188a14085a2289ef60f527bd1f9ddb](https://github.com/asterinas/asterinas/commit/9f53affb22188a14085a2289ef60f527bd1f9ddb) | shared mount capability check |
| [01acaa7eeed755a32fc658e7d732b080061b4872](https://github.com/asterinas/asterinas/commit/01acaa7eeed755a32fc658e7d732b080061b4872) | upstream mount capability regression |
| [dbf521a1bf75c2a0ce8e7c7309369af1ac429349](https://github.com/asterinas/asterinas/commit/dbf521a1bf75c2a0ce8e7c7309369af1ac429349) | chown authorization and set-ID handling |
| [26cb04660e20053b7fb7a91cfd7ffd21b372839f](https://github.com/asterinas/asterinas/commit/26cb04660e20053b7fb7a91cfd7ffd21b372839f) | enable six upstream chown denial conformance cases |

The original upstream C/LTP/gVisor entries remain present. This minimal
product profile runs its own static ELF; it does not claim to run the full
upstream LTP or gVisor suites merely because their entries are enabled.

## Credentials and observable effects

Every case starts in a separate child. The root parent prepares a fresh
fixture, and the child sets its real, effective, saved and filesystem IDs,
supplementary groups, and capability sets before the syscall under test.
Most cases use a real non-root UID. The two root denial cases retain UID 0
and clear every effective, permitted and inheritable capability.

The fixture owner is UID/GID 65534; the non-owner is 65533; the supplemental
group is 65532; a foreign group is 65531. Linux reference execution needs
these IDs to be mapped and the initial process to possess the capabilities
needed to create fixtures, change credentials and mount tmpfs. An environment
whose `uid_map` or `gid_map` contains only `0 0 1` cannot run this reference.
Fixture setup failure is a failure, not a skip or a permission-test pass.

For capability positive cases, the child uses `PR_SET_KEEPCAPS` before dropping
UID, then `capset` restricts both permitted and effective sets to exactly the
one capability requested by the case. Inheritable capabilities are empty.
`capget`, `getresuid`, `getresgid`, `setfsuid(-1)`, `setfsgid(-1)` and
`getgroups` read the actual credentials back. The filesystem-UID case keeps
real/saved UID 65534, effective UID 65533, filesystem UID 65534 and no
capabilities, so it exercises filesystem ownership independently of EUID.

Each raw `PERMISSION_OBSERVATION` includes these credentials, the actual
syscall return and errno, before/after UID, GID, permission bits, inode,
device and nanosecond ctime, plus visibility of an underlying mount marker.
Denied calls must leave all recorded metadata unchanged. Successful file
calls must keep inode/device identity and produce the exact expected IDs and
mode. For the successful non-owner `fchown(-1,-1)` case, the probe pauses
1.1 seconds between its before snapshot and syscall; both C and Python require
ctime to advance while IDs and mode stay unchanged. This makes a missing
ctime update observable even with one-second filesystem timestamp resolution.

The C program emits its own case status. The Python oracle separately
evaluates the raw credential and metadata fields, requires all 32 cases in
order, and rejects omissions, duplicates, unknown markers, assertion failures
and unexpected exits. Changing a `PASS` label or receipt boolean cannot make
an incorrect raw observation pass.

## Fixed case matrix

Unless a row says otherwise, the actor has no capabilities or supplementary
groups, and a regular file starts as owner 65534, group 65534, mode `0644`.
`EPERM` means return `-1`, errno 1 and unchanged metadata; `ENOENT` means errno
2 and unchanged metadata on the adjacent existing fixture.

| Case | Credential / operation | Required result |
|---|---|---|
| `chmod_nonowner_path` | Non-owner `chmod` | `EPERM` |
| `chmod_nonowner_fd` | Non-owner `fchmod` on inherited FD | `EPERM` |
| `chmod_nonowner_at` | Non-owner `fchmodat` | `EPERM` |
| `chmod_owner` | Owner `fchmod` | Mode `0600` |
| `chmod_fowner` | Non-owner, only `CAP_FOWNER` | Mode `0600` |
| `chmod_chown_cap_denied` | Non-owner, only `CAP_CHOWN`, `fchmod` | `EPERM` |
| `chmod_owner_sgid_member` | Owner, file group in supplementary groups, request `02755` | `02755` |
| `chmod_owner_sgid_nonmember` | Owner, file group outside all groups, request `02755` | `0755`; SGID cleared |
| `chmod_owner_sgid_fsetid` | Owner, foreign file group, only `CAP_FSETID`, request `02755` | `02755` |
| `chown_nonowner_path` | Non-owner `chown` requests its own UID | `EPERM` |
| `chown_nonowner_fd` | Non-owner `fchown` requests its own UID | `EPERM` |
| `chown_nonowner_at` | Non-owner `fchownat` requests its own UID | `EPERM` |
| `chown_nonowner_same_uid` | Non-owner explicitly requests the file's existing UID | `EPERM` |
| `chown_nonowner_noop` | Non-owner `fchown(-1,-1)` on ordinary `0644` | Success; IDs/mode unchanged; ctime advances |
| `chown_owner_uid_denied` | Owner requests a different UID | `EPERM` |
| `chown_owner_group_primary` | Owner changes file's foreign group to its primary GID | GID 65534 |
| `chown_owner_group_member` | Owner changes group to its supplementary GID | GID 65532 |
| `chown_owner_group_denied` | Owner requests a group it does not belong to | `EPERM` |
| `chown_cap` | Non-owner, only `CAP_CHOWN`, ordinary `0644` | UID 65533, GID 65531 |
| `chown_fowner_denied` | Non-owner, only `CAP_FOWNER`, changes owner | `EPERM` |
| `chown_regular_clear_setid` | Owner `fchown(-1,-1)` on regular `06755` | Mode `0755` |
| `chown_directory_keep_setid` | Owner `fchown(-1,-1)` on directory `02775` | Mode stays `02775` |
| `chmod_fsuid_owner` | FSUID is owner, EUID is non-owner, no capabilities | Mode `0600` |
| `mount_nonroot_denied` | Non-root mounts tmpfs at an existing directory | `EPERM`; underlying marker visible |
| `mount_root_without_cap_denied` | UID 0 without capabilities mounts tmpfs | `EPERM`; marker visible |
| `mount_sysadmin` | Non-root, only `CAP_SYS_ADMIN`, mounts tmpfs | Success; marker hidden; root UID/GID `65533:65533`, mode `0755` |
| `umount_nonroot_denied` | Non-root unmounts prepared tmpfs | `EPERM`; underlying marker still hidden |
| `umount_root_without_cap_denied` | UID 0 without capabilities unmounts tmpfs | `EPERM`; marker hidden |
| `umount_sysadmin` | Non-root, only `CAP_SYS_ADMIN`, unmounts tmpfs | Success; underlying marker visible again |
| `mount_missing_path` | Non-root mount at missing target | `ENOENT` |
| `umount_missing_path` | Non-root unmount at missing target | `ENOENT` |
| `pivot_without_cap` | Non-root `pivot_root(NULL,NULL)` | `EPERM` before argument access |

The distinction between explicit unchanged IDs and `-1` comes from Linux's
`chown_common` and `setattr_prepare`: `-1` leaves the corresponding UID/GID
attribute absent, while an explicit ID still requests an attribute operation.
See [Linux v6.12 fs/open.c](https://github.com/torvalds/linux/blob/v6.12/fs/open.c)
and [fs/attr.c](https://github.com/torvalds/linux/blob/v6.12/fs/attr.c).

## Build and Linux reference

Run in the project's disposable Ubuntu 24.04 x86_64 CI environment with
`cc`, static glibc development files, binutils, Python 3 and util-linux
`unshare`. The reference runner executes `unshare --mount --propagation
private` before the ELF. No user namespace or ID-remapping workaround is
used. Mount changes stay inside this private namespace, use new tmpfs
instances, and never attach host disks.

From the clean, committed product checkout:

```sh
permission_root=$(mktemp -d "${TMPDIR:-/tmp}/a04-permission.XXXXXX")
python3 -I -B tests/workloads/linux/test_permission_guest.py
python3 -I -B -O tests/workloads/linux/test_permission_guest.py
cc -O2 -std=c11 -Wall -Wextra -Werror -static \
  tests/workloads/linux/permission_probe.c -o "$permission_root/probe.elf"
sha256sum "$permission_root/probe.elf" > "$permission_root/probe.sha256"
permission_sha=$(cut -d' ' -f1 "$permission_root/probe.sha256")
permission_status=0
sudo python3 -I -B tests/workloads/linux/run_permission_guest.py reference \
  --probe-elf "$permission_root/probe.elf" \
  --expected-probe-sha256 "$permission_sha" \
  --output "$permission_root/reference" || permission_status=$?
# Preserve the original exit status and make even failed evidence readable.
if [ -d "$permission_root/reference" ]; then
  sudo chown -R -- "$(id -u):$(id -g)" "$permission_root/reference"
fi
test "$permission_status" -eq 0
sha256sum --check "$permission_root/probe.sha256"
```

The reference directory contains the frozen `probe.elf`, `probe.sha256`,
pre-execution `input.json`, original `stdout.log`, `stderr.log`, raw
`exit-code.txt` and independently derived `result.json`. Output directories
must be new. The static ELF is inspected for ELF format, architecture and
absence of dynamic interpreter/dependencies. The process-session guard
terminates descendants before reaping its original process-group anchor.
Every child is reaped by the probe, has a five-second alarm, and the full
runner has a configurable 1–180 second deadline (default 120 seconds).

`--case NAME` exists on the C executable only for failure diagnosis. A partial
execution cannot satisfy the Python reference or guest gate. Preserve failed
raw output, the frozen binary and its source when diagnosing a case; do not
approve a replacement ELF by recomputing its digest after execution.

## Ordinary product guest replay

First obtain successful fresh evidence from
`tests/kernel/control/run_queryabi_candidate_guest.py` on the same committed
source. Its source-before snapshot must include this probe and the complete
runner dependency closure with the same bytes and hashes. Then run:

```sh
python3 -I -B tests/workloads/linux/run_permission_guest.py guest \
  --linux-reference "$permission_root/reference" \
  --expected-probe-sha256 "$permission_sha" \
  --product-evidence "${RUNNER_TEMP}/a06-queryabi-candidate" \
  --expected-source-head "$(git rev-parse HEAD)" \
  --expected-source-tree "$(git rev-parse HEAD^{tree})" \
  --a01-initramfs support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz \
  --output "$permission_root/guest"
```

The runner rehashes and independently rejudges the Linux raw evidence before
launch. It uses the existing ordinary-product input verifier and the pinned
A01 initramfs and SeaBIOS. It preserves the original init checks, injects one
static ELF, and records the real probe-process exit before the original boot
marker. QEMU 8.2.2 runs q35, TCG, CPU `max`, one vCPU and 512 MiB, with no NIC,
block devices, KVM, host filesystem sharing or external service connection.

The guest directory retains kernel, probe, BIOS, initramfs, complete serial,
QEMU arguments and version, source identities, input hashes and result. A
pass requires all 32 independently accepted observations, the probe exit 0,
ordered completion/boot markers, QEMU exit 33, no timeout or kernel panic,
and unchanged inputs after execution. The retained Linux, product and runner
identities are checked again after QEMU finishes.

This bounded profile covers single-threaded credential and metadata behavior
on temporary in-memory filesystems. It does not establish concurrent inode
update atomicity, arbitrary mount namespaces or idmapped mounts, persistent
disk behavior, Android Binder policy, Hepta request authorization, or complete
Linux ABI compatibility. Those require their own real execution evidence.
