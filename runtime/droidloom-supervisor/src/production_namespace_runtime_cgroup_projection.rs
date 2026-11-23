//! A candidate check for the two fixed NativeV2 mount layers. The authorized
//! expected cgroup comes from the same already-active broker payload, and the
//! observed locations come from the original held PID1 tree.

use super::{NamespaceError, Node, Result, writable_proc::MountInventory};

pub(super) const SYS: &str = "/sys";
pub(super) const CGROUP: &str = "/sys/fs/cgroup";
const OWNED_PAYLOAD: &str = "/system.slice/droidloom-production.service/cell-u1000/payload";

#[derive(Clone, Copy)]
pub(super) struct NativeCgroupObservation {
    pub(super) sys_mount_id: u64,
    pub(super) sys_device: u64,
    pub(super) cgroup_mount_id: u64,
    pub(super) cgroup: Node,
}

/// Return the same inventory as if the verified two new roles were not yet
/// present. The ordinary runtime layout checker still checks every other row.
/// The caller stores the complete observed inventory, with both new rows, as
/// the authority for subsequent reobservations and original-init transitions.
pub(super) fn verify_native_cgroup_projection(
    before: &MountInventory,
    after: &MountInventory,
    active_payload: Node,
    observed: NativeCgroupObservation,
) -> Result<MountInventory> {
    let reject =
        || NamespaceError::Rejected("native cgroup projection differs from owned runtime roles");
    let lower_id = *before.visible.get(SYS).ok_or_else(reject)?;
    let lower = before.records.get(&lower_id).ok_or_else(reject)?;
    let sys = after
        .records
        .get(&observed.sys_mount_id)
        .ok_or_else(reject)?;
    let cgroup = after
        .records
        .get(&observed.cgroup_mount_id)
        .ok_or_else(reject)?;

    if lower.target != SYS
        || !["ext4", "erofs"].contains(&lower.filesystem.as_str())
        || !["ro", "nosuid", "nodev"]
            .iter()
            .all(|flag| lower.flags.contains(*flag))
        || lower.flags.contains("rw")
        || after.records.get(&lower_id) != Some(lower)
        || before.visible.contains_key(CGROUP)
        || before
            .records
            .values()
            .any(|record| record.target.starts_with("/sys/"))
        || before.records.contains_key(&sys.id)
        || before.records.contains_key(&cgroup.id)
        || sys.id == cgroup.id
        || sys.id != observed.sys_mount_id
        || cgroup.id != observed.cgroup_mount_id
        || after.visible.get(SYS) != Some(&sys.id)
        || after.visible.get(CGROUP) != Some(&cgroup.id)
        || sys.target != SYS
        || sys.parent != lower_id
        || sys.device != observed.sys_device
        || sys.device == lower.device
        || sys.device == active_payload.device
        || sys.filesystem != "tmpfs"
        || sys.root != "/"
        || !["ro", "nosuid", "nodev", "noexec"]
            .iter()
            .all(|flag| sys.flags.contains(*flag))
        || sys.flags.contains("rw")
        || cgroup.target != CGROUP
        || cgroup.parent != sys.id
        || cgroup.device != active_payload.device
        || cgroup.filesystem != "cgroup2"
        || cgroup.root != OWNED_PAYLOAD
        || !["rw", "nosuid", "nodev", "noexec"]
            .iter()
            .all(|flag| cgroup.flags.contains(*flag))
        || cgroup.flags.contains("ro")
        || !option_once(&cgroup.options, "rw")
        || !option_once(&cgroup.options, "nsdelegate")
        || cgroup.options.split(',').any(|option| option == "ro")
        || observed.cgroup != active_payload
    {
        return Err(reject());
    }

    let mut original_roles = after.clone();
    original_roles.records.remove(&sys.id);
    original_roles.records.remove(&cgroup.id);
    original_roles.visible.remove(CGROUP);
    original_roles.visible.insert(SYS.into(), lower_id);
    Ok(original_roles)
}

fn option_once(options: &str, expected: &str) -> bool {
    options
        .split(',')
        .filter(|option| *option == expected)
        .count()
        == 1
}

#[cfg(test)]
mod tests {
    use super::super::writable_proc::mount_records;
    use super::*;
    use std::collections::BTreeMap;

    const LOWER: &str = "10 9 7:4 /sys /sys ro,nosuid,nodev - ext4 loop4 ro\n";
    const FIXTURE: &str = "11 10 0:26 / /sys ro,nosuid,nodev,noexec - tmpfs tmpfs rw,size=64k,nr_inodes=8\n12 11 0:27 /system.slice/droidloom-production.service/cell-u1000/payload /sys/fs/cgroup rw,nosuid,nodev,noexec - cgroup2 none rw,nsdelegate\n";

    fn fixture(
        raw: &str,
    ) -> (
        MountInventory,
        MountInventory,
        Node,
        NativeCgroupObservation,
    ) {
        let before = MountInventory {
            records: mount_records(LOWER.as_bytes()).unwrap(),
            visible: BTreeMap::from([(SYS.into(), 10)]),
        };
        let after = MountInventory {
            records: mount_records(format!("{LOWER}{raw}").as_bytes()).unwrap(),
            visible: BTreeMap::from([(SYS.into(), 11), (CGROUP.into(), 12)]),
        };
        let expected = Node {
            device: libc::makedev(0, 27),
            inode: 93,
        };
        let observed = NativeCgroupObservation {
            sys_mount_id: 11,
            sys_device: libc::makedev(0, 26),
            cgroup_mount_id: 12,
            cgroup: expected,
        };
        (before, after, expected, observed)
    }

    #[test]
    fn layered_verification_preserves_every_original_row() {
        let (before, after, expected, observed) = fixture(FIXTURE);
        assert_eq!(
            verify_native_cgroup_projection(&before, &after, expected, observed).unwrap(),
            before
        );
        assert_eq!(after.records.len(), 3);
    }

    #[test]
    fn layered_verification_rejects_wrong_source_or_mount_structure() {
        let (before, after, expected, mut observed) = fixture(FIXTURE);
        observed.cgroup.inode += 1;
        assert!(verify_native_cgroup_projection(&before, &after, expected, observed).is_err());
        for (old, new) in [
            ("11 10 0:26", "11 9 0:26"),
            ("12 11 0:27", "12 10 0:27"),
            ("12 11 0:27", "12 11 0:99"),
            (OWNED_PAYLOAD, "/"),
            ("rw,nsdelegate", "rw"),
            ("rw,nsdelegate", "rw,nsdelegate,nsdelegate"),
            ("rw,nosuid,nodev,noexec", "rw,nosuid,nodev"),
            ("ro,nosuid,nodev,noexec", "rw,nosuid,nodev,noexec"),
        ] {
            let (before, after, expected, observed) = fixture(&FIXTURE.replace(old, new));
            assert!(
                verify_native_cgroup_projection(&before, &after, expected, observed).is_err(),
                "accepted {new}"
            );
        }
    }

    #[test]
    fn layered_verification_leaves_unexpected_rows_for_the_ordinary_check() {
        let (before, mut after, expected, observed) = fixture(FIXTURE);
        let mut alias = after.records.get(&12).unwrap().clone();
        alias.id = 13;
        alias.target = "/unapproved-cgroup".into();
        after.visible.insert(alias.target.clone(), alias.id);
        after.records.insert(alias.id, alias.clone());
        let rest = verify_native_cgroup_projection(&before, &after, expected, observed).unwrap();
        assert_ne!(rest, before);
        assert_eq!(rest.records.get(&13), Some(&alias));
    }
}
