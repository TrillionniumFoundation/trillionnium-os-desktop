# Original CP3A genfs policy input

The maintained first-init policy source reader now collects the original
`/system/etc/selinux/plat_sepolicy_genfs_202604.cil` from the pinned CP3A system
image. This file is required by the complete platform/vendor policy composition.

The reader was rebuilt through ordinary Cargo on Pocket4. Its three existing
format controls passed. Actual extraction preserved all 22 previous image
members and added the original 303-byte genfs file with four CIL forms. The
source image and extraction tool retain their fixed identities and hashes.

`qualification.json`, `source.json`, and `retirement.json` retain the exact
ordinary run, producer source identities, and completed process retirement.
`original-genfs-202604.cil` is the unmodified image member, SHA256
`3bdfcfba699936cb12d007fee7bca2feb1a88c75cc947f98b14c55fe4932b0d3`.

This is source collection evidence. Compilation with the final vendor policy,
the vendor genfs label version, enforcing policy load, and actual Android boot
remain separate required checks. This source change does not grant runtime or
production acceptance.
