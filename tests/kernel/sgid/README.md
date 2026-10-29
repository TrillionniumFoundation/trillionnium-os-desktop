# SGID creation guest probe

This probe checks real ramfs, tmpfs and ext2 inode creation and strict original
Root socket ownership. Its only disk is a newly generated private ext2 fixture.

After an ordinary product build on the exact clean source:

```sh
python3 -B tests/kernel/sgid/run.py --smp 4 \
  --product-evidence /path/to/exact-source-product --output /path/to/new-evidence
```

See [the implementation and qualification boundaries](../../../support/kernel-safety/SGID_CREATION.md).
The probe is never run on the host. The runner does not accept existing disks.
