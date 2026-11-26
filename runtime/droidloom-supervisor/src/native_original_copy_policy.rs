//! Source-admitted original-account copy identities for the selected Pocket4.
//!
//! This is configuration/comparison data only. Deserialization, a digest, or a
//! matching inode cannot create a namespace, a data provider, Main authority,
//! or an application acceptance. The normal cold producer checks the complete
//! original copy proofs and actual four inodes before publishing selection;
//! the live provider separately binds the selected pair to its held lease,
//! loop devices, mapped filesystems and actual process lifetime.
use serde::{Deserialize, Serialize};

pub(crate) const COPY_SHA256: &str =
    "d5864566bd978921b427f2ff70df218214fc512406f8e491d46f3fdd80a39a89";
pub(crate) const CLONE_SHA256: &str =
    "3eda27b424c264102e609fbb87392b4d34e14ce8440d1ab40ab250131fc92ca0";

// device, inode, full mode, uid, gid, nlink, bytes. These were independently
// observed from O_PATH descriptors while the two complete fixed proof files
// and all four full file identities were unchanged at both read boundaries.
// Runtime filesystem writes may change mtime/ctime, not these seven fields.
// The corresponding complete source proofs remain private cold inputs.
const ORIGINAL: [[u64; 7]; 2] = [
    [66306, 111810948, 0o100600, 0, 0, 1, 34_359_738_368],
    [66306, 111810949, 0o100600, 0, 0, 1, 134_217_728],
];
const WORKING: [[u64; 7]; 2] = [
    [66306, 444453, 0o100600, 0, 0, 1, 34_359_738_368],
    [66306, 444455, 0o100600, 0, 0, 1, 134_217_728],
];

#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct OriginalCopyPolicy {
    pub(crate) schema: String,
    pub(crate) working_copy_sha256: String,
    pub(crate) cold_clone_sha256: String,
    /// Fixed order: data, metadata. No paths, live PIDs or caller permissions.
    pub(crate) original: [[u64; 7]; 2],
    pub(crate) working: [[u64; 7]; 2],
}

impl OriginalCopyPolicy {
    /// Produce comparison bytes only. Cold admission and live ownership remain
    /// independent mandatory checks at their actual normal call sites.
    pub(crate) fn reviewed() -> Self {
        Self {
            schema: "droidloom.original-copy-policy.v1".into(),
            working_copy_sha256: COPY_SHA256.into(),
            cold_clone_sha256: CLONE_SHA256.into(),
            original: ORIGINAL,
            working: WORKING,
        }
    }

    pub(crate) fn validate(&self) -> Result<(), &'static str> {
        if self != &Self::reviewed() {
            return Err("original-copy policy differs from the reviewed complete source proofs and four inode identities");
        }
        Ok(())
    }

    /// The cold producer verifies the complete COPY/CLONE bodies and four
    /// named inodes before this comparison, then brackets its whole admission
    /// with actual retirement checks. This method grants no mutation authority.
    pub(crate) fn bind_cold_pairs(
        original: [[u64; 7]; 2],
        working: [[u64; 7]; 2],
    ) -> Result<Self, &'static str> {
        let policy = Self::reviewed();
        if original != policy.original || working != policy.working {
            return Err("actual original and independent working pair differ from the source admission");
        }
        Ok(policy)
    }

    /// No body hash or account-business continuity is asserted by this method.
    /// The argument is read from the live provider's own held backing files.
    pub(crate) fn verify_working(&self, observed: [[u64; 7]; 2]) -> Result<(), &'static str> {
        self.validate()?;
        if observed != self.working {
            return Err("selected live data/metadata are not the reviewed independent working copy");
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_the_actual_ordered_source_pair_is_admitted() {
        let policy = OriginalCopyPolicy::bind_cold_pairs(ORIGINAL, WORKING).unwrap();
        policy.validate().unwrap();
        policy.verify_working(WORKING).unwrap();
        assert!(policy.verify_working(ORIGINAL).is_err());
        assert!(policy.verify_working([WORKING[1], WORKING[0]]).is_err());
        assert!(policy.verify_working([WORKING[0], WORKING[0]]).is_err());
        assert!(OriginalCopyPolicy::bind_cold_pairs(WORKING, ORIGINAL).is_err());
    }

    #[test]
    fn every_original_and_working_identity_field_is_committed() {
        for role in 0..2 {
            for field in 0..7 {
                let mut old = ORIGINAL;
                old[role][field] ^= 1;
                assert!(OriginalCopyPolicy::bind_cold_pairs(old, WORKING).is_err());
                let mut new = WORKING;
                new[role][field] ^= 1;
                assert!(OriginalCopyPolicy::bind_cold_pairs(ORIGINAL, new).is_err());
                assert!(OriginalCopyPolicy::reviewed().verify_working(new).is_err());
            }
        }
    }

    #[test]
    fn a_saved_policy_cannot_extend_the_compiled_admission() {
        let good = serde_json::to_value(OriginalCopyPolicy::reviewed()).unwrap();
        for key in ["working_copy_sha256", "cold_clone_sha256", "schema"] {
            let mut changed = good.clone();
            changed[key] = serde_json::json!("unreviewed");
            let value: OriginalCopyPolicy = serde_json::from_value(changed).unwrap();
            assert!(value.validate().is_err());
        }
        for key in ["main_qualified", "account_state_preserved", "path", "expected_pid"] {
            let mut changed = good.clone();
            changed[key] = serde_json::json!(true);
            assert!(serde_json::from_value::<OriginalCopyPolicy>(changed).is_err());
        }
        let mut changed = good;
        changed["working"][0][1] = serde_json::json!(true);
        assert!(serde_json::from_value::<OriginalCopyPolicy>(changed).is_err());
    }
}
