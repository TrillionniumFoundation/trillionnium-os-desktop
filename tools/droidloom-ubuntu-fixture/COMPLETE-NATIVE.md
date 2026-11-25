# Complete normal Ubuntu source

This path consumes a fresh Ubuntu root created by normal signed debootstrap and
normal apt/dpkg transactions. It does not reuse or broaden the older selection
of public files from a running machine. The complete tree includes the original
package database, package metadata, service accounts, files, symlinks, hardlinks,
ownership, modes, capabilities and POSIX ACLs.

The source root must be a root-owned root directory directly inside a private
/var/lib/droidloom-qualification/WORK directory. The source receipt binds its
device/inode, the signed bootstrap, successful install/audit/query transactions,
the complete configured package roster and the actual dpkg status. All receipt
references use the producer's exact eight-field EvidencePin. Receipt inputs stay
open and are fully hashed again after capture.

The complete reader uses held directory descriptors and openat2 with BENEATH,
NO_SYMLINKS, NO_MAGICLINKS and NO_XDEV. It never follows guest links into the host,
crosses a mounted API filesystem, or opens a device. Only eight ordinary static
/dev character nodes are representable by their exact name and device number.
Sockets, FIFOs, unrelated devices and links outside the whole frozen inode set
are rejected. Every regular file has complete bytes and privilege metadata
checked between identity observations. A second exact inventory checks the
whole source after capture. Copying uses new inodes, then complete readback.

## Material commands

- capture-complete-native --source-receipt PATH --source-receipt-sha256 SHA --target-kernel-release RELEASE --output MANIFEST
- materialize-complete-native --manifest MANIFEST --manifest-sha256 SHA --destination /var/lib/droidloom-qualification/WORK/root --receipt RECEIPT
- verify-complete-native --manifest MANIFEST --manifest-sha256 SHA --destination /var/lib/droidloom-qualification/WORK/root --receipt RECEIPT

The original configured **baseline** remains useful construction material. Final
preparation requires the separate installed source: the fixed, normally built
fifteen-package release, its original baseline, the actual durable dpkg
transaction and the current whole package database. The consumer checks the
source-bound two-component release and all 108 original material files, including
the old and new package archives and full control/payload inventories.

The actual transaction must first unpack and configure the fixed
libsystemd-shared prerequisite, then normally unpack and configure the remaining
fourteen packages in their dependency order. All four actual command exits,
original-root/attempt identities, configuration preservation, original private
metadata, all fifteen configured versions and the complete final query must
agree. Failure, rollback and partial histories cannot become a final source.
Every installed payload member is checked. Only the two fixed credstore
directories use the original package's proven 0700 tmpfiles result; declared
conffiles retain their real original contents and selection semantics.

No kernel is fabricated from this root: its /boot is empty and it contains no
module release. A later normal boot consumes the separately published shared
kernel, its full modules and matching initrd. No machine/user credentials are
copied from Pocket4, no process is started inside the captured root, and no
physical package or service is changed by these three material commands.

## Fresh complete native preparation

The separate `prepare-complete-native` entry preserves all normally generated
service accounts and the entire dpkg database. It creates only the two fixed
qualification identities, fresh machine and SSH identities, and reviewed guest
configuration. A baseline capture cannot enter this path: the typed installed
source contract must pass first.

The normal full boot consumer admits `droidloom.complete-ubuntu-native-prepared.v1`
only after exact prepared-member readback. It installs the first, independently
published shared-kernel batch into a kernel-free base and rejects any mixture
with the historical single-ELF overlays. The historical public-root branch
retains its old selector and replacement-kernel contract.

The GDM session group is derived from the complete root's real normal account
database. The prepared account hashes and numeric identity are checked again
against the ended guest's actual passwd/group files; the journal proof must
have the same real group. The old public input still requires its original
GID 121. Greeter UID bounds and file GID 65534 are unchanged.

Validation: the complete 52,876-member independent materialization executed
the actual sysusers/firstboot/tmpfiles/SSH/systemctl-root initialization in
21.958 seconds. Its entire dpkg database and original service accounts were
unchanged. This was a baseline construction test, not a guest boot or a
successful final installed release. Five focused journal/source tests passed,
including a complete-root GID 981 positive and wrong-GID/absent-binding negatives.
Actual installed-root capture and complete preparation remain required; source
and material tests alone do not qualify a guest.


## Transport to another host

The export-complete-native command takes the source manifest and SHA, a fixed
/var/lib/droidloom-qualification/WORK/NATIVE-PAYLOAD.bin output and a receipt.
It exports an admitted installed root without changing its original identities.
The 56-byte fixed header binds the manifest SHA, original regular-file count
and exact byte count. The remaining bytes are only those regular files, in the
manifest order. The format carries no arbitrary path, link, device or metadata
commands. Every original file and the full tree retain their SHA/F9 bookends;
the output has complete readback.

A complete native plan can supply fixture_payload as an ordinary FilePin.
The fixture_root still names the original source for provenance, and no original
receipt or inode is rewritten to impersonate the destination. The importer
requires a root-owned, single-link, readonly payload and verifies its whole
SHA/F9 before and after use. It creates new local inodes from the manifest's
exact directories, links, eight static device nodes, ownership, modes and
privilege metadata. Each regular file, then the whole reconstructed tree, has
full readback before fresh native initialization. A truncated, altered or
extended payload cannot produce a native preparation receipt.
