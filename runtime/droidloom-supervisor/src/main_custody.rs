//! Read-only observations from the normal early owner's held resources.
//!
//! These serialized values are comparisons, never an owner, a data-origin grant,
//! or business acceptance. Only the authenticated normal control client creates
//! the opaque `MainCustodyObservation`; saved JSON cannot recreate that fact.
use crate::control::application_custody::{CustodyNamespace, CustodyOwner};
use crate::control::application_probe::RuntimeEpoch;
use serde::{Deserialize, Serialize};
use std::os::unix::fs::MetadataExt;

pub use crate::control::MainCustodyObservation;

pub const SCHEMA: &str = "droidloom.runtime-main-custody.v1";

/// The seven stable backing fields. Runtime writes legitimately change both
/// mtime and ctime; those clocks cannot identify an unchanged mounted image.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MainBackingIdentity {
    pub device: u64,
    pub inode: u64,
    pub mode: u32,
    pub uid: u32,
    pub gid: u32,
    pub links: u64,
    pub bytes: u64,
}
impl MainBackingIdentity {
    pub(crate) fn of(m: &std::fs::Metadata) -> Self {
        Self {
            device: m.dev(),
            inode: m.ino(),
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            links: m.nlink(),
            bytes: m.len(),
        }
    }
    /// Exact source-admission order; mutable backing clocks are excluded.
    pub fn stable7(&self) -> [u64; 7] {
        [
            self.device,
            self.inode,
            u64::from(self.mode),
            u64::from(self.uid),
            u64::from(self.gid),
            self.links,
            self.bytes,
        ]
    }
}
#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MainNodeIdentity {
    pub device: u64,
    pub inode: u64,
}
impl MainNodeIdentity {
    pub(crate) fn of(m: &std::fs::Metadata) -> Self {
        Self {
            device: m.dev(),
            inode: m.ino(),
        }
    }
}
#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MainDataRole {
    Data,
    Metadata,
}

/// A directory's stable filesystem identity plus its actual held mount ID.
/// Directory entry counts, byte sizes and clocks can change during normal use.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MainMountRoot {
    pub device: u64,
    pub inode: u64,
    pub mount_id: u64,
    pub mode: u32,
    pub uid: u32,
    pub gid: u32,
}
impl MainMountRoot {
    pub(crate) fn same_filesystem_root(&self, other: &Self) -> bool {
        (self.device, self.inode, self.mode, self.uid, self.gid)
            == (other.device, other.inode, other.mode, other.uid, other.gid)
    }
}
#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MainLoopIdentity {
    pub node: MainNodeIdentity,
    pub block_device: u64,
}
#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MainBackingCustody {
    pub role: MainDataRole,
    pub backing: MainBackingIdentity,
    pub loop_binding: MainLoopIdentity,
    /// The owner's original detached mount retained for orderly retirement.
    pub retained_root: MainMountRoot,
    /// The actual fixed /data or /metadata root in the observed framework view.
    /// Android receives a cloned mount, so its ID is deliberately separate.
    pub framework_root: MainMountRoot,
}
/// Source-owned copy lineage projected from the sealed selected policy after
/// its exact working pair has been matched to the current held backing files.
/// It says nothing about account contents or successful application behavior.
#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MainOriginalCopyOrigin {
    pub schema: String,
    pub working_copy_sha256: String,
    pub cold_clone_sha256: String,
    pub original: [[u64; 7]; 2],
    pub working: [[u64; 7]; 2],
}
#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MainPersistentCustody {
    pub host_uid: u32,
    pub base_cohort_sha256: String,
    pub selection_binding_sha256: String,
    pub user_namespace: MainNodeIdentity,
    pub reservation_lease: MainNodeIdentity,
    pub backings: [MainBackingCustody; 2],
    /// Absent for a selection without the source-admitted copy lineage.
    pub original_copy_origin: Option<MainOriginalCopyOrigin>,
    /// Comparison from the actual readonly full-image admission, never a
    /// deserialized capability. Absent for every ordinary existing-data owner.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fresh_diagnostic_origin: Option<crate::empty_meituan_contract::Origin>,
}
#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MainProcessCustody {
    pub host_pid: u32,
    pub parent_host_pid: u32,
    pub start_ticks: u64,
    pub pidfd: MainNodeIdentity,
    pub root: MainNodeIdentity,
    pub executable: MainNodeIdentity,
}
#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeMainCustody {
    pub schema: String,
    pub epoch: RuntimeEpoch,
    pub owner: CustodyOwner,
    pub init: MainProcessCustody,
    pub zygote: MainProcessCustody,
    pub framework: MainProcessCustody,
    pub framework_namespaces: Vec<CustodyNamespace>,
    pub persistent_data: MainPersistentCustody,
    /// Selected comparison pins from the same live private configuration.
    pub normal_host_release: crate::normal_host_release::NormalHostRelease,
}

fn require(value: bool, why: &'static str) -> Result<(), String> {
    if value { Ok(()) } else { Err(why.into()) }
}
fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
}
fn namespaces(values: &[CustodyNamespace]) -> bool {
    values.iter().map(|v| v.name.as_str()).collect::<Vec<_>>()
        == ["cgroup", "ipc", "mount", "net", "pid", "user", "uts"]
        && values.iter().all(|v| v.inode != 0)
}
impl RuntimeMainCustody {
    /// Shape and cross-field consistency only. This cannot authenticate a
    /// server or construct the opaque fact from caller-supplied values.
    pub(crate) fn validate(&self, expected: &RuntimeEpoch) -> Result<(), String> {
        require(
            self.schema == SCHEMA && &self.epoch == expected,
            "Main observation belongs to a different fixed request or schema",
        )?;
        require(
            self.epoch.boot_id.len() == 36
                && self.epoch.cell_host_pid == self.init.host_pid
                && self.epoch.framework_host_pid == self.framework.host_pid
                && self.epoch.framework_start_ticks == self.framework.start_ticks
                && self.owner.cell_host_pid == self.init.host_pid
                && self.owner.cell_start_ticks == self.init.start_ticks
                && self.zygote.parent_host_pid == self.init.host_pid
                && self.framework.parent_host_pid == self.zygote.host_pid,
            "Main process epoch or original parent lineage differs",
        )?;
        require(
            [&self.init, &self.zygote, &self.framework].iter().all(|p| {
                p.host_pid > 1
                    && p.start_ticks != 0
                    && p.pidfd.inode != 0
                    && p.root.inode != 0
                    && p.executable.inode != 0
            }) && self.init.host_pid != self.zygote.host_pid
                && self.init.host_pid != self.framework.host_pid
                && self.zygote.host_pid != self.framework.host_pid,
            "Main requires three distinct live process identities",
        )?;
        require(
            namespaces(&self.owner.namespaces)
                && namespaces(&self.framework_namespaces)
                && digest(&self.owner.selection_binding_sha256)
                && digest(&self.owner.base_cohort_sha256)
                && digest(&self.owner.runtime_manifest_sha256),
            "Main owner or complete namespace binding differs",
        )?;
        self.normal_host_release.validate().map_err(str::to_owned)?;
        let data = &self.persistent_data;
        let user = &self.owner.namespaces[5];
        let framework_user = &self.framework_namespaces[5];
        require(
            data.host_uid == self.owner.host_uid
                && data.base_cohort_sha256 == self.owner.base_cohort_sha256
                && data.selection_binding_sha256 == self.owner.selection_binding_sha256
                && data.user_namespace
                    == (MainNodeIdentity {
                        device: user.device,
                        inode: user.inode,
                    })
                && (framework_user.device, framework_user.inode) == (user.device, user.inode)
                && data.reservation_lease.inode != 0,
            "Main data is not retained by the same selection, user namespace and lease",
        )?;
        require(
            data.backings[0].role == MainDataRole::Data
                && data.backings[1].role == MainDataRole::Metadata,
            "Main must observe exactly data then metadata",
        )?;
        for row in &data.backings {
            require(
                row.backing.mode == libc::S_IFREG | 0o600
                    && row.backing.uid == 0
                    && row.backing.gid == 0
                    && row.backing.links == 1
                    && row.backing.bytes > 0
                    && row.backing.inode != 0
                    && row.loop_binding.node.inode != 0
                    && libc::major(row.loop_binding.block_device) == 7
                    && row.loop_binding.block_device == row.retained_root.device
                    && row.retained_root.same_filesystem_root(&row.framework_root)
                    && row.retained_root.mount_id != 0
                    && row.framework_root.mount_id != 0
                    && row.retained_root.mount_id != row.framework_root.mount_id
                    && row.retained_root.mode & libc::S_IFMT == libc::S_IFDIR,
                "Main backing, owned loop or actual framework mount differs",
            )?;
        }
        if let Some(fresh) = &data.fresh_diagnostic_origin {
            require(data.original_copy_origin.is_none(), "EMPTY origin cannot describe an original-data copy")?;
            fresh.validate(data.backings.each_ref().map(|v| v.backing.stable7())).map_err(str::to_owned)?;
        }
        if let Some(origin) = &data.original_copy_origin {
            let policy = crate::native_once_contract::OriginalCopyPolicy {
                schema: origin.schema.clone(),
                working_copy_sha256: origin.working_copy_sha256.clone(),
                cold_clone_sha256: origin.cold_clone_sha256.clone(),
                original: origin.original,
                working: origin.working,
            };
            policy
                .verify_working([
                    data.backings[0].backing.stable7(),
                    data.backings[1].backing.stable7(),
                ])
                .map_err(|e| e.to_string())?;
        }
        let [data, metadata] = &data.backings;
        require(
            (data.backing.device, data.backing.inode)
                != (metadata.backing.device, metadata.backing.inode)
                && data.loop_binding.block_device != metadata.loop_binding.block_device,
            "Main data and metadata cannot share a backing or loop",
        )?;
        Ok(())
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use std::io::{Seek, Write};

    pub(crate) fn sample() -> RuntimeMainCustody {
        let copy = crate::native_once_contract::OriginalCopyPolicy::reviewed();
        let nodes = ["cgroup", "ipc", "mount", "net", "pid", "user", "uts"]
            .into_iter()
            .enumerate()
            .map(|(i, name)| CustodyNamespace {
                name: name.into(),
                device: 4,
                inode: 100 + i as u64,
            })
            .collect::<Vec<_>>();
        let process = |pid, parent, start| MainProcessCustody {
            host_pid: pid,
            parent_host_pid: parent,
            start_ticks: start,
            pidfd: MainNodeIdentity {
                device: 5,
                inode: pid as u64,
            },
            root: MainNodeIdentity {
                device: 8,
                inode: 2,
            },
            executable: MainNodeIdentity {
                device: 8,
                inode: 500 + u64::from(pid),
            },
        };
        let backing = |role, index: usize| {
            let n = copy.working[index];
            let device = libc::makedev(7, 20 + index as u32);
            let retained = MainMountRoot {
                device,
                inode: 2,
                mount_id: 1000 + index as u64,
                mode: libc::S_IFDIR | 0o771,
                uid: 2001000,
                gid: 2001000,
            };
            MainBackingCustody {
                role,
                backing: MainBackingIdentity {
                    device: n[0],
                    inode: n[1],
                    mode: n[2] as u32,
                    uid: n[3] as u32,
                    gid: n[4] as u32,
                    links: n[5],
                    bytes: n[6],
                },
                loop_binding: MainLoopIdentity {
                    node: MainNodeIdentity {
                        device: 10,
                        inode: 400 + index as u64,
                    },
                    block_device: device,
                },
                retained_root: retained,
                framework_root: MainMountRoot {
                    mount_id: 2000 + index as u64,
                    ..retained
                },
            }
        };
        RuntimeMainCustody {
            schema: SCHEMA.into(),
            epoch: RuntimeEpoch {
                boot_id: "01234567-1234-1234-1234-0123456789ab".into(),
                cell_host_pid: 100,
                framework_host_pid: 102,
                framework_start_ticks: 30,
            },
            owner: CustodyOwner {
                host_uid: 1000,
                cell_host_pid: 100,
                cell_start_ticks: 10,
                selection_binding_sha256: "a".repeat(64),
                base_cohort_sha256: "b".repeat(64),
                runtime_manifest_sha256: "c".repeat(64),
                namespaces: nodes.clone(),
            },
            init: process(100, 99, 10),
            zygote: process(101, 100, 20),
            framework: process(102, 101, 30),
            framework_namespaces: nodes,
            normal_host_release: crate::normal_host_release::NormalHostRelease {
                schema: crate::normal_host_release::SCHEMA.into(),
                manager: crate::normal_host_release::NormalHostProgramPin {
                    path: crate::normal_host_release::MANAGER.into(), bytes: 1024, sha256: "d".repeat(64),
                },
                presenter: crate::normal_host_release::NormalHostProgramPin {
                    path: crate::normal_host_release::PRESENTER.into(), bytes: 2048, sha256: "e".repeat(64),
                },
            },
            persistent_data: MainPersistentCustody {
                host_uid: 1000,
                base_cohort_sha256: "b".repeat(64),
                selection_binding_sha256: "a".repeat(64),
                user_namespace: MainNodeIdentity {
                    device: 4,
                    inode: 105,
                },
                reservation_lease: MainNodeIdentity {
                    device: 9,
                    inode: 10000,
                },
                backings: [
                    backing(MainDataRole::Data, 0),
                    backing(MainDataRole::Metadata, 1),
                ],
                fresh_diagnostic_origin: None,
                original_copy_origin: Some(MainOriginalCopyOrigin {
                    schema: copy.schema,
                    working_copy_sha256: copy.working_copy_sha256,
                    cold_clone_sha256: copy.cold_clone_sha256,
                    original: copy.original,
                    working: copy.working,
                }),
            },
        }
    }

    #[test]
    fn main_wire_checks_exact_pair_epoch_namespace_and_origin_without_creating_authority() {
        let original = sample();
        original.validate(&original.epoch).unwrap();
        for case in 0..11 {
            let mut altered = original.clone();
            match case {
                0 => altered.epoch.framework_start_ticks += 1,
                1 => altered.zygote.parent_host_pid += 1,
                2 => altered.owner.selection_binding_sha256 = "d".repeat(64),
                3 => altered.framework_namespaces[5].inode += 1,
                4 => altered.persistent_data.backings.swap(0, 1),
                5 => altered.persistent_data.backings[0].backing.links = 2,
                6 => {
                    altered.persistent_data.backings[0]
                        .loop_binding
                        .block_device += 1
                }
                7 => altered.persistent_data.backings[0].framework_root.inode += 1,
                8 => {
                    altered.persistent_data.backings[0].framework_root.mount_id =
                        altered.persistent_data.backings[0].retained_root.mount_id
                }
                9 => {
                    altered
                        .persistent_data
                        .original_copy_origin
                        .as_mut()
                        .unwrap()
                        .working[0][1] ^= 1
                }
                _ => altered.persistent_data.backings[0].backing.inode ^= 1,
            }
            assert!(altered.validate(&original.epoch).is_err(), "case {case}");
        }
        let mut ordinary = original.clone();
        ordinary.persistent_data.original_copy_origin = None;
        ordinary.validate(&original.epoch).unwrap();
        assert!(ordinary.persistent_data.original_copy_origin.is_none());
        let mut external = serde_json::to_value(original).unwrap();
        external["main_qualified"] = serde_json::json!(true);
        assert!(serde_json::from_value::<RuntimeMainCustody>(external).is_err());
    }

    #[test]
    fn main_stable_backing_identity_allows_real_runtime_clocks_but_not_replacement() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("data.img");
        let mut file = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .open(&path)
            .unwrap();
        file.write_all(b"before").unwrap();
        let before = MainBackingIdentity::of(&file.metadata().unwrap());
        file.rewind().unwrap();
        file.write_all(b"after!").unwrap();
        file.set_modified(std::time::UNIX_EPOCH + std::time::Duration::from_secs(7))
            .unwrap();
        assert_eq!(MainBackingIdentity::of(&file.metadata().unwrap()), before);
        std::fs::rename(&path, directory.path().join("original")).unwrap();
        std::fs::write(&path, b"after!").unwrap();
        assert_ne!(
            MainBackingIdentity::of(&std::fs::metadata(&path).unwrap()),
            before
        );
        assert_eq!(MainBackingIdentity::of(&file.metadata().unwrap()), before);
        file.set_len(7).unwrap();
        assert_ne!(MainBackingIdentity::of(&file.metadata().unwrap()), before);
    }

    #[test]
    fn main_mount_mapping_keeps_cloned_ids_separate_and_checks_every_stable_root_field() {
        let retained = MainMountRoot {
            device: 9,
            inode: 2,
            mount_id: 10,
            mode: libc::S_IFDIR | 0o755,
            uid: 100000,
            gid: 100000,
        };
        let clone = MainMountRoot {
            mount_id: 20,
            ..retained
        };
        assert!(retained.same_filesystem_root(&clone));
        assert_ne!(retained.mount_id, clone.mount_id);
        for field in 0..5 {
            let mut changed = clone;
            match field {
                0 => changed.device += 1,
                1 => changed.inode += 1,
                2 => changed.mode ^= 1,
                3 => changed.uid += 1,
                _ => changed.gid += 1,
            }
            assert!(!retained.same_filesystem_root(&changed));
        }
    }
}
