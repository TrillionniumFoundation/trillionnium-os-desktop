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

This initial contract admits the original configured **baseline**. It explicitly
rejects an installed claim: the final patched native package transaction and
its whole payload need their separate completed admission contract. Baseline
capture/copy is neither a final release nor permission to skip normal package
installation.

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
The final installed transaction/whole-payload gate remains a distinct component.
