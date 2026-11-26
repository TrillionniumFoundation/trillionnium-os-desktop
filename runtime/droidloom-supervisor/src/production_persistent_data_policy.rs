//! Root-selected comparison data for the original mutable backing pair.
//!
//! A parsed policy cannot open an image or create a mount. The live provider
//! separately requires the original PreparedExecution, namespace witness,
//! identity lease and held fixed-directory backing inodes.

use serde::Deserialize;
use crate::native_once_contract::OriginalCopyPolicy;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct PersistentDataPolicy {
    pub(crate) mode: String,
    pub(crate) data: PersistentImagePolicy,
    pub(crate) metadata: PersistentImagePolicy,
    #[serde(default)]
    pub(crate) original_copy: Option<OriginalCopyPolicy>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct PersistentImagePolicy {
    pub(crate) image_bytes: u64,
    pub(crate) filesystem_uuid: String,
    pub(crate) feature_compat: u32,
    pub(crate) feature_incompat: u32,
    pub(crate) feature_ro_compat: u32,
    pub(crate) guest_root_uid: u32,
    pub(crate) guest_root_gid: u32,
    pub(crate) guest_root_mode: u32,
}

impl PersistentDataPolicy {
    pub(crate) fn validate(&self) -> Result<(), &'static str> {
        if self.mode != "original-ext4-v1" {
            return Err("unsupported persistent data policy");
        }
        self.data.validate()?;
        self.metadata.validate()?;
        if let Some(copy) = &self.original_copy {
            copy.validate()?;
            if copy.working[0][6] != self.data.image_bytes
                || copy.working[1][6] != self.metadata.image_bytes {
                return Err("original-copy roles differ from selected filesystem sizes");
            }
        }
        if self.data.filesystem_uuid == self.metadata.filesystem_uuid {
            return Err("data and metadata require distinct selected filesystem UUIDs");
        }
        Ok(())
    }
}

impl PersistentImagePolicy {
    pub(crate) fn validate(&self) -> Result<(), &'static str> {
        if !(16 * 1024 * 1024..=256 * 1024 * 1024 * 1024).contains(&self.image_bytes)
            || self.image_bytes % 4096 != 0
            || self.guest_root_uid == u32::MAX
            || self.guest_root_gid == u32::MAX
            || self.guest_root_mode & !0o777 != 0
            || self.guest_root_mode & 0o700 != 0o700
            || self.guest_root_mode & 0o002 != 0
        {
            return Err("invalid persistent image size or original root identity");
        }
        self.uuid()?;
        // Narrow reviewed ordinary ext4 profile: internal journal, filetype,
        // extents, optional 64bit/flex_bg/checksum seed, metadata checksums,
        // and the observed clean orphan-file / verity-compatible profiles.
        // RO_COMPAT_ORPHAN_PRESENT still cannot enter this constructor; an
        // allocated orphan inode is not evidence of pending orphan recovery.
        // External journals, encryption, bigalloc and snapshots remain excluded.
        if self.feature_compat & !0x103c != 0
            || self.feature_compat & 0x0004 == 0
            || self.feature_incompat & !0x22c2 != 0
            || self.feature_incompat & 0x0042 != 0x0042
            || self.feature_ro_compat & !0x846b != 0
            || self.feature_ro_compat & 0x0400 == 0
        {
            return Err("persistent image has an unreviewed ext4 feature profile");
        }
        Ok(())
    }

    pub(crate) fn uuid(&self) -> Result<[u8; 16], &'static str> {
        let raw = self.filesystem_uuid.as_bytes();
        if raw.len() != 36 {
            return Err("canonical lowercase filesystem UUID required");
        }
        let mut output = [0u8; 16];
        let mut nibbles = 0;
        for (index, byte) in raw.iter().copied().enumerate() {
            if [8, 13, 18, 23].contains(&index) {
                if byte != b'-' {
                    return Err("canonical filesystem UUID separators required");
                }
                continue;
            }
            let nibble = match byte {
                b'0'..=b'9' => byte - b'0',
                b'a'..=b'f' => byte - b'a' + 10,
                _ => return Err("canonical lowercase filesystem UUID required"),
            };
            if nibbles >= 32 {
                return Err("filesystem UUID overflow");
            }
            output[nibbles / 2] |= nibble << if nibbles % 2 == 0 { 4 } else { 0 };
            nibbles += 1;
        }
        if nibbles != 32 || output == [0; 16] {
            return Err("nonempty complete filesystem UUID required");
        }
        Ok(output)
    }

    pub(crate) fn mapped_root(
        &self,
        uids: crate::IdRange,
        gids: crate::IdRange,
    ) -> Result<(u32, u32), &'static str> {
        self.validate()?;
        if self.guest_root_uid >= uids.count || self.guest_root_gid >= gids.count {
            return Err("original filesystem root is outside the actual admitted maps");
        }
        Ok((
            uids.start.checked_add(self.guest_root_uid).ok_or("mapped root UID overflow")?,
            gids.start.checked_add(self.guest_root_gid).ok_or("mapped root GID overflow")?,
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn policy() -> PersistentImagePolicy {
        PersistentImagePolicy {
            image_bytes: 64 * 1024 * 1024,
            filesystem_uuid: "c2e0701f-f5d5-4234-87a7-506b21fe62cb".into(),
            feature_compat: 0x3c,
            feature_incompat: 0x22c2,
            feature_ro_compat: 0x46b,
            guest_root_uid: 1000,
            guest_root_gid: 1000,
            guest_root_mode: 0o771,
        }
    }

    #[test]
    fn persistent_policy_keeps_original_guest_ids_and_checks_actual_map_extent() {
        let value = policy();
        let range = crate::IdRange { start: 2_000_000, count: 65536 };
        assert_eq!(value.mapped_root(range, range).unwrap(), (2_001_000, 2_001_000));
        assert_eq!(value.guest_root_uid, 1000);
        assert!(value.mapped_root(crate::IdRange { count: 1000, ..range }, range).is_err());
        assert!(value.mapped_root(crate::IdRange { start: u32::MAX - 999, ..range }, range).is_err());
    }

    #[test]
    fn persistent_policy_rejects_alias_roles_and_unreviewed_mutable_features() {
        let original = policy();
        let pair = PersistentDataPolicy { mode: "original-ext4-v1".into(), data: original.clone(), metadata: original.clone(), original_copy: None };
        assert!(pair.validate().is_err());
        for mutation in 0..8 {
            let mut value = original.clone();
            match mutation {
                0 => value.feature_incompat |= 4,
                1 => value.feature_incompat |= 0x1_0000,
                2 => value.feature_compat |= 0x400,
                3 => value.feature_ro_compat |= 0x200,
                4 => value.feature_ro_compat &= !0x400,
                5 => value.guest_root_mode |= 0o002,
                6 => value.image_bytes += 1,
                _ => value.filesystem_uuid = value.filesystem_uuid.to_uppercase(),
            }
            assert!(value.validate().is_err());
        }
        assert_eq!(original.uuid().unwrap(), [0xc2,0xe0,0x70,0x1f,0xf5,0xd5,0x42,0x34,0x87,0xa7,0x50,0x6b,0x21,0xfe,0x62,0xcb]);
    }

    #[test]
    fn original_copy_is_optional_configuration_but_cannot_select_foreign_files() {
        let image = serde_json::json!({
            "image_bytes":34_359_738_368_u64,
            "filesystem_uuid":"c2e0701f-f5d5-4234-87a7-506b21fe62cb",
            "feature_compat":0x3c,"feature_incompat":0x22c2,
            "feature_ro_compat":0x46b,"guest_root_uid":1000,
            "guest_root_gid":1000,"guest_root_mode":0o771
        });
        let mut metadata = image.clone();
        metadata["image_bytes"] = serde_json::json!(134_217_728_u64);
        metadata["filesystem_uuid"] = serde_json::json!("c2e0701f-f5d5-4234-87a7-506b21fe62cc");
        let legacy = serde_json::json!({"mode":"original-ext4-v1",
            "data":image,"metadata":metadata});
        let old: PersistentDataPolicy = serde_json::from_value(legacy.clone()).unwrap();
        old.validate().unwrap();
        assert!(old.original_copy.is_none());
        let mut selected = legacy;
        selected["original_copy"] = serde_json::to_value(OriginalCopyPolicy::reviewed()).unwrap();
        let current: PersistentDataPolicy = serde_json::from_value(selected.clone()).unwrap();
        current.validate().unwrap();
        assert!(current.original_copy.is_some());
        let mut foreign = selected.clone();
        foreign["original_copy"]["working"][0][1] = serde_json::json!(444454);
        assert!(serde_json::from_value::<PersistentDataPolicy>(foreign).unwrap().validate().is_err());
        let mut wrong_size = selected.clone();
        wrong_size["data"]["image_bytes"] = serde_json::json!(134_217_728_u64);
        assert!(serde_json::from_value::<PersistentDataPolicy>(wrong_size).unwrap().validate().is_err());
        selected["original_copy"]["main_qualified"] = serde_json::json!(true);
        assert!(serde_json::from_value::<PersistentDataPolicy>(selected).is_err());
    }

    #[test]
    fn persistent_policy_admits_reviewed_orphan_file_and_verity_profiles() {
        for readonly in [0x046b, 0x846b] {
            let mut value = policy();
            value.feature_compat = 0x103c;
            value.feature_ro_compat = readonly;
            assert_eq!(value.validate(), Ok(()));
            let mut pending = value.clone();
            pending.feature_ro_compat |= 0x10000;
            assert!(pending.validate().is_err());
            let mut readonly_image = value.clone();
            readonly_image.feature_ro_compat |= 0x1000;
            assert!(readonly_image.validate().is_err());
        }
    }
}
