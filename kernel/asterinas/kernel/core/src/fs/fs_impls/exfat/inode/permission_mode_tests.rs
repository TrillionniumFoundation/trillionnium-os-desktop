// SPDX-License-Identifier: MPL-2.0

//! Regressions for synthesized exFAT permission bits.
//!
//! The production helper used by ExfatInode::mode/metadata must not invent
//! set-ID or sticky bits that the disk format cannot represent. The separate
//! disk guest checks stat and actual exec credentials on a mounted image.
//! Reference: Linux v6.16 fs/exfat/inode.c, exfat_fill_inode.

use ostd::prelude::ktest;

use super::*;

#[ktest]
fn exfat_modes_never_invent_setid_or_sticky() {
    // All combinations of the six supported DOS attribute bits. Hidden,
    // system, volume, and archive flags must not become Unix special bits.
    for bits in 0..=FatAttr::all().bits() {
        let attrs = FatAttr::from_bits_truncate(bits);
        let actual = attrs.make_mode(ExfatMountOptions::default()).bits();
        let expected = if attrs.contains(FatAttr::READONLY)
            && !attrs.contains(FatAttr::DIRECTORY)
        {
            0o555
        } else {
            0o777
        };
        assert_eq!(actual, expected, "DOS attributes: {bits:#x}");
        assert_eq!(actual & 0o7000, 0, "DOS attributes: {bits:#x}");
    }
}

#[ktest]
fn exfat_modes_keep_file_directory_masks_and_readonly() {
    let options = ExfatMountOptions {
        fs_fmask: 0o133,
        fs_dmask: 0o022,
        ..ExfatMountOptions::default()
    };
    let cases = [
        (FatAttr::empty(), 0o644),
        (FatAttr::ARCHIVE, 0o644),
        (FatAttr::READONLY, 0o444),
        (FatAttr::DIRECTORY, 0o755),
        (FatAttr::DIRECTORY | FatAttr::READONLY, 0o755),
        (FatAttr::all(), 0o755),
    ];
    for (attrs, expected) in cases {
        assert_eq!(attrs.make_mode(options.clone()).bits(), expected);
    }
    // Masking unrepresentable Unix special bits cannot manufacture them.
    let special_mask = ExfatMountOptions {
        fs_fmask: 0o7000,
        fs_dmask: 0o7000,
        ..ExfatMountOptions::default()
    };
    assert_eq!(FatAttr::empty().make_mode(special_mask.clone()).bits(), 0o777);
    assert_eq!(FatAttr::DIRECTORY.make_mode(special_mask).bits(), 0o777);
}
