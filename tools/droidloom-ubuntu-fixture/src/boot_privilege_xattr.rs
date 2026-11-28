//! Compare native xattrs with libext2fs readback without changing their authority.
use crate::{Result, ensure};

#[derive(Debug, PartialEq, Eq)]
pub(super) struct Comparison {
    pub raw_equal: bool,
    pub unused_acl_ids_converted: usize,
}

/// Linux emits ACL_UNDEFINED_ID for the four ACL entries that have no ID.
/// libext2fs 1.47.2 convert_disk_buffer_to_posix_acl emits zero for those same
/// ext4 short entries (e2fsprogs Debian bug #1108534). IDs are absent from the
/// on-disk short entries. Accept only that representation difference; every
/// meaningful field, entry position and capability byte must remain exact.
pub(super) fn compare(name: &str, source: &[u8], image: &[u8]) -> Result<Comparison> {
    if name == "security.capability" {
        ensure(source == image, "ext4 security.capability bytes differ")?;
        return Ok(Comparison {
            raw_equal: true,
            unused_acl_ids_converted: 0,
        });
    }
    ensure(
        matches!(name, "system.posix_acl_access" | "system.posix_acl_default"),
        "unsupported native privilege xattr",
    )?;
    ensure(
        source.len() == image.len()
            && (28..=65_536).contains(&source.len())
            && (source.len() - 4) % 8 == 0,
        "ext4 POSIX ACL size or entry count differs",
    )?;
    ensure(
        source[..4] == 2u32.to_le_bytes() && image[..4] == source[..4],
        "ext4 POSIX ACL version differs or is unsupported",
    )?;
    let mut converted = 0;
    for (expected, actual) in source[4..].chunks_exact(8).zip(image[4..].chunks_exact(8)) {
        ensure(
            expected[..4] == actual[..4],
            "ext4 POSIX ACL tag, permissions or entry order differs",
        )?;
        let tag = u16::from_le_bytes([expected[0], expected[1]]);
        let permissions = u16::from_le_bytes([expected[2], expected[3]]);
        ensure(permissions <= 7, "invalid POSIX ACL permissions")?;
        let expected_id = u32::from_le_bytes(expected[4..8].try_into()?);
        let actual_id = u32::from_le_bytes(actual[4..8].try_into()?);
        match tag {
            // ACL_USER and ACL_GROUP carry meaningful IDs, including ID zero.
            0x02 | 0x08 => ensure(
                expected_id != u32::MAX && actual_id == expected_id,
                "ext4 POSIX ACL named user/group ID differs or is undefined",
            )?,
            // ACL_USER_OBJ, ACL_GROUP_OBJ, ACL_MASK and ACL_OTHER have no ID.
            0x01 | 0x04 | 0x10 | 0x20 => {
                ensure(
                    expected_id == u32::MAX && (actual_id == u32::MAX || actual_id == 0),
                    "unsupported POSIX ACL unused-ID representation",
                )?;
                converted += usize::from(actual_id == 0);
            }
            _ => return Err("unsupported POSIX ACL entry tag".into()),
        }
    }
    Ok(Comparison {
        raw_equal: source == image,
        unused_acl_ids_converted: converted,
    })
}

#[cfg(test)]
mod tests {
    use super::compare;

    // Actual full-native R2 journal access/default ACL: group adm (ID 4).
    const SOURCE: &str =
        "0200000001000700ffffffff04000500ffffffff080005000400000010000500ffffffff20000500ffffffff";
    const IMAGE: &str =
        "0200000001000700000000000400050000000000080005000400000010000500000000002000050000000000";

    fn acl() -> (Vec<u8>, Vec<u8>) {
        (hex::decode(SOURCE).unwrap(), hex::decode(IMAGE).unwrap())
    }

    #[test]
    fn real_acl_unused_ids_only_and_exact_readback_are_accepted() {
        let (source, image) = acl();
        for name in ["system.posix_acl_access", "system.posix_acl_default"] {
            let actual = compare(name, &source, &image).unwrap();
            assert!(!actual.raw_equal);
            assert_eq!(actual.unused_acl_ids_converted, 4);
            let exact = compare(name, &source, &source).unwrap();
            assert!(exact.raw_equal);
            assert_eq!(exact.unused_acl_ids_converted, 0);
        }
    }

    #[test]
    fn capability_readback_remains_byte_exact() {
        for value in [
            "0100000200200000000000000000000000000000",
            "00000002cf002c01000000000000000000000000",
            "0100000200148000000000000000000000000000",
        ] {
            let source = hex::decode(value).unwrap();
            assert!(
                compare("security.capability", &source, &source)
                    .unwrap()
                    .raw_equal
            );
            for index in 0..source.len() {
                let mut image = source.clone();
                image[index] ^= 1;
                assert!(compare("security.capability", &source, &image).is_err());
            }
        }
        let (source, image) = acl();
        assert!(compare("security.capability", &source, &image).is_err());
    }

    #[test]
    fn every_meaningful_acl_byte_is_exact() {
        let (source, image) = acl();
        for index in 0..image.len() {
            let in_unused_id = index >= 4 && (index - 4) % 8 >= 4 && (index - 4) / 8 != 2;
            if !in_unused_id {
                let mut changed = image.clone();
                changed[index] ^= 1;
                assert!(
                    compare("system.posix_acl_access", &source, &changed).is_err(),
                    "accepted changed meaningful ACL byte {index}"
                );
            }
        }
    }

    #[test]
    fn unknown_unused_ids_and_noncanonical_source_are_rejected() {
        let (source, image) = acl();
        for entry in [0, 1, 3, 4] {
            let offset = 4 + entry * 8 + 4;
            for id in [1u32, 4, 65_534, u32::MAX - 1] {
                let mut changed = image.clone();
                changed[offset..offset + 4].copy_from_slice(&id.to_le_bytes());
                assert!(compare("system.posix_acl_access", &source, &changed).is_err());
            }
            let mut changed_source = source.clone();
            changed_source[offset..offset + 4].copy_from_slice(&0u32.to_le_bytes());
            assert!(compare("system.posix_acl_access", &changed_source, &image).is_err());
            assert!(compare("system.posix_acl_access", &changed_source, &changed_source).is_err());
        }
    }

    #[test]
    fn named_root_user_and_group_ids_are_never_normalized() {
        let (mut source, mut image) = acl();
        for tag in [0x02u16, 0x08] {
            source[20..22].copy_from_slice(&tag.to_le_bytes());
            image[20..22].copy_from_slice(&tag.to_le_bytes());
            source[24..28].copy_from_slice(&0u32.to_le_bytes());
            image[24..28].copy_from_slice(&0u32.to_le_bytes());
            assert!(compare("system.posix_acl_default", &source, &image).is_ok());
            image[24..28].copy_from_slice(&u32::MAX.to_le_bytes());
            assert!(compare("system.posix_acl_default", &source, &image).is_err());
            source[24..28].copy_from_slice(&u32::MAX.to_le_bytes());
            assert!(compare("system.posix_acl_default", &source, &image).is_err());
        }
    }

    #[test]
    fn version_size_count_order_and_invalid_fields_are_rejected() {
        let (source, image) = acl();
        for length in [0, 3, 4, 12, 20, 27, 28, 43] {
            assert!(compare("system.posix_acl_default", &source, &image[..length]).is_err());
        }
        let mut reordered = image.clone();
        reordered[4..12].copy_from_slice(&image[12..20]);
        reordered[12..20].copy_from_slice(&image[4..12]);
        assert!(compare("system.posix_acl_default", &source, &reordered).is_err());
        for offset in [0, 4, 6] {
            let mut both = source.clone();
            both[offset] = 0xff;
            assert!(compare("system.posix_acl_default", &both, &both).is_err());
        }
        assert!(compare("security.selinux", &source, &image).is_err());
    }
}
