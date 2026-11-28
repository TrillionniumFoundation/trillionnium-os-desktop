//! Bounded read-only admission of the selected original ext4 superblock.
//! No filesystem repair or journal replay is performed by this parser.
//!
//! Layout: Linux Documentation/filesystems/ext4/super.rst. Checksumming uses
//! CRC32C(~0, superblock[0..0x3fc]), as ext4_superblock_csum in fs/ext4/super.c.

use crate::production_selection::PersistentImagePolicy;

fn u16_at(raw: &[u8; 1024], offset: usize) -> u16 {
    u16::from_le_bytes(raw[offset..offset + 2].try_into().unwrap())
}
fn u32_at(raw: &[u8; 1024], offset: usize) -> u32 {
    u32::from_le_bytes(raw[offset..offset + 4].try_into().unwrap())
}

fn crc32c(raw: &[u8]) -> u32 {
    let mut crc = u32::MAX;
    for byte in raw {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            crc = (crc >> 1) ^ (0x82f6_3b78 & 0u32.wrapping_sub(crc & 1));
        }
    }
    crc
}

pub(super) fn validate(
    raw: &[u8; 1024],
    selected: &PersistentImagePolicy,
) -> Result<(), &'static str> {
    selected.validate()?;
    if u16_at(raw, 0x38) != 0xef53
        || u32_at(raw, 0x18) != 2
        || u32_at(raw, 0x1c) != 2
        || u32_at(raw, 0x14) != 0
        || u32_at(raw, 0x4c) != 1
        || u16_at(raw, 0x58) != 256
        || u16_at(raw, 0x5a) != 0
    {
        return Err("selected raw 4096-byte-block ext4 geometry required");
    }
    if u32_at(raw, 0x5c) != selected.feature_compat
        || u32_at(raw, 0x60) != selected.feature_incompat
        || u32_at(raw, 0x64) != selected.feature_ro_compat
        || raw[0x68..0x78] != selected.uuid()?
    {
        return Err("original ext4 UUID or exact selected feature profile changed");
    }
    let high = u32_at(raw, 0x150);
    if selected.feature_incompat & 0x80 == 0 && high != 0 {
        return Err("unexpected ext4 high block count without 64-bit support");
    }
    let blocks = u64::from(u32_at(raw, 4)) | (u64::from(high) << 32);
    if blocks.checked_mul(4096) != Some(selected.image_bytes)
        || u32_at(raw, 0x20) == 0
        || u32_at(raw, 0x20) != u32_at(raw, 0x24)
        || u32_at(raw, 0x28) == 0
        || u32_at(raw, 0) == 0
    {
        return Err("whole ext4 filesystem extent differs from the held original backing");
    }
    if u16_at(raw, 0x3a) != 1
        || u32_at(raw, 0x60) & 4 != 0
        || u32_at(raw, 0xe8) != 0
        || u32_at(raw, 0xe4) != 0
        || raw[0xd0..0xe0] != [0; 16]
        || u32_at(raw, 0xe0) == 0
        || u32_at(raw, 0xe0) >= u32_at(raw, 0)
    {
        return Err("original ext4 must be clean with an internal journal and no pending recovery");
    }
    let first_inode = u32_at(raw, 0x54);
    let orphan_inode = u32_at(raw, 0x280);
    let valid_orphan = if selected.feature_compat & 0x1000 != 0 {
        orphan_inode >= first_inode
            && orphan_inode < u32_at(raw, 0)
            && orphan_inode != u32_at(raw, 0xe0)
    } else {
        orphan_inode == 0
    };
    if first_inode != 11 || !valid_orphan {
        return Err("original ext4 orphan-file inode is not a distinct bounded non-reserved inode");
    }
    if raw[0x175] != 1 || u32_at(raw, 0x3fc) != crc32c(&raw[..0x3fc]) {
        return Err("original ext4 superblock checksum failed");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    // Exact 1024-byte preads from two ordinary, unmounted files created by the
    // pinned Pocket4 mke2fs in SOURCE-CHECK.json. Both full image files were
    // retired after extraction. These fixtures contain no original user data.
    const DATA: &[u8; 1024] =
        include_bytes!("production_persistent_data_fixtures/data-superblock.bin");
    const METADATA: &[u8; 1024] =
        include_bytes!("production_persistent_data_fixtures/metadata-superblock.bin");
    // Two further real, newly formatted and retired ordinary files reproduce
    // the original images' feature tuples. No original app content is stored.
    const KNOWN_DATA: &[u8; 1024] =
        include_bytes!("production_persistent_data_fixtures/data-known-features-superblock.bin");
    const KNOWN_METADATA: &[u8; 1024] =
        include_bytes!("production_persistent_data_fixtures/metadata-known-features-superblock.bin");

    fn selected(image_bytes: u64, uuid: &str) -> PersistentImagePolicy {
        PersistentImagePolicy {
            image_bytes,
            filesystem_uuid: uuid.into(),
            feature_compat: 0x3c,
            feature_incompat: 0x22c2,
            feature_ro_compat: 0x46b,
            guest_root_uid: 1000,
            guest_root_gid: 1000,
            guest_root_mode: 0o755,
        }
    }

    fn data_policy() -> PersistentImagePolicy {
        selected(64 * 1024 * 1024, "748861cb-65b5-4fcb-8aba-5c5dc40811df")
    }

    fn known_data_policy() -> PersistentImagePolicy {
        let mut policy = selected(64 * 1024 * 1024, "144320aa-5806-413a-9e39-7edb797c5f57");
        policy.feature_compat = 0x103c;
        policy.feature_ro_compat = 0x846b;
        policy
    }

    fn reseal(raw: &mut [u8; 1024]) {
        let checksum = crc32c(&raw[..0x3fc]);
        raw[0x3fc..].copy_from_slice(&checksum.to_le_bytes());
    }

    #[test]
    fn superblock_checksum_uses_crc32c_without_the_standard_final_complement() {
        assert_eq!(!crc32c(b"123456789"), 0xe306_9283);
    }

    #[test]
    fn actual_unmounted_ext4_superblocks_admit_only_the_selected_whole_filesystem() {
        assert_eq!(validate(DATA, &data_policy()), Ok(()));
        let metadata = selected(32 * 1024 * 1024, "a91dcb63-4c0a-49d2-b43e-14152cd85bdd");
        assert_eq!(validate(METADATA, &metadata), Ok(()));
        assert!(validate(DATA, &metadata).is_err());
        let mut wrong_size = data_policy();
        wrong_size.image_bytes += 4096;
        assert_eq!(validate(DATA, &wrong_size),
            Err("whole ext4 filesystem extent differs from the held original backing"));
        let mut wrong_uuid = *DATA;
        wrong_uuid[0x68] ^= 1;
        reseal(&mut wrong_uuid);
        assert_eq!(validate(&wrong_uuid, &data_policy()),
            Err("original ext4 UUID or exact selected feature profile changed"));
    }

    #[test]
    fn valid_checksums_do_not_admit_dirty_or_external_journal_superblocks() {
        for mutation in 0..4 {
            let mut raw = *DATA;
            match mutation {
                0 => raw[0x3a..0x3c].copy_from_slice(&3u16.to_le_bytes()),
                1 => raw[0xe8..0xec].copy_from_slice(&42u32.to_le_bytes()),
                2 => raw[0xe4..0xe8].copy_from_slice(&1u32.to_le_bytes()),
                _ => raw[0xd0] = 1,
            }
            reseal(&mut raw);
            assert_eq!(validate(&raw, &data_policy()),
                Err("original ext4 must be clean with an internal journal and no pending recovery"));
        }
        let mut recovery = data_policy();
        recovery.feature_incompat |= 4;
        let mut raw = *DATA;
        raw[0x60..0x64].copy_from_slice(&recovery.feature_incompat.to_le_bytes());
        reseal(&mut raw);
        assert_eq!(validate(&raw, &recovery),
            Err("persistent image has an unreviewed ext4 feature profile"));
    }

    #[test]
    fn actual_superblock_corruption_and_changed_geometry_fail_closed() {
        let mut bad_checksum = *DATA;
        bad_checksum[0x3fc] ^= 1;
        assert_eq!(validate(&bad_checksum, &data_policy()),
            Err("original ext4 superblock checksum failed"));
        let mut wrong_checksum_type = *DATA;
        wrong_checksum_type[0x175] = 0;
        reseal(&mut wrong_checksum_type);
        assert_eq!(validate(&wrong_checksum_type, &data_policy()),
            Err("original ext4 superblock checksum failed"));
        let mut wrong_block_size = *DATA;
        wrong_block_size[0x18..0x1c].copy_from_slice(&1u32.to_le_bytes());
        reseal(&mut wrong_block_size);
        assert_eq!(validate(&wrong_block_size, &data_policy()),
            Err("selected raw 4096-byte-block ext4 geometry required"));
    }

    #[test]
    fn actual_orphan_file_and_verity_superblocks_admit_clean_profiles() {
        assert_eq!(validate(KNOWN_DATA, &known_data_policy()), Ok(()));
        let mut metadata = selected(32 * 1024 * 1024, "a7f1f350-d947-4b29-81a9-0eab6ee1ed36");
        metadata.feature_compat = 0x103c;
        metadata.guest_root_uid = 131073;
        metadata.guest_root_gid = 262145;
        assert_eq!(validate(KNOWN_METADATA, &metadata), Ok(()));
        assert!(validate(KNOWN_DATA, &metadata).is_err());
        assert!(validate(KNOWN_METADATA, &known_data_policy()).is_err());
    }

    #[test]
    fn orphan_file_bounds_and_pending_scan_reject_resealed_superblocks() {
        for mutation in 0..6 {
            let mut raw = *KNOWN_DATA;
            let mut policy = known_data_policy();
            let (offset, value) = match mutation {
                0 => (0x280, 0),
                1 => (0x280, u32_at(&raw, 0xe0)),
                2 => (0x280, u32_at(&raw, 0)),
                3 => (0x54, 10),
                4 => {
                    policy.feature_compat &= !0x1000;
                    (0x5c, policy.feature_compat)
                }
                _ => {
                    policy.feature_ro_compat |= 0x10000;
                    (0x64, policy.feature_ro_compat)
                }
            };
            raw[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
            reseal(&mut raw);
            assert!(validate(&raw, &policy).is_err(), "unsafe orphan mutation {mutation}");
        }
    }
}
