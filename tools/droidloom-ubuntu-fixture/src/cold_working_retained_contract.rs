//! Cold-only comparison of the two continuously retained original images.
//! Recovered from cfd0c4e's maintained retained-data contract. This record is
//! provenance, never a constructor for a lease or a runtime helper permit.
//! The actual four image OFDs remain owned by the live cold pair transaction.
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
};

pub const SCHEMA: &str = "droidloom.working-retained-originals.v1";
pub const ORIGINAL_DATA_BYTES: u64 = 32 * 1024 * 1024 * 1024;
pub const ORIGINAL_METADATA_BYTES: u64 = 128 * 1024 * 1024;
pub const WORK_BASE: &str = "/var/lib/droidloom-qualification";

// One pair, one deadline: neither file nor a retry renews this window.
// The live helper also clamps every operation to the original PID1 preparation end.
pub const RETAINED_PAIR_HASH_SECONDS: u64 = 1200;

pub fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Identity {
    pub dev: u64,
    pub ino: u64,
    pub mode: u32,
    pub uid: u32,
    pub gid: u32,
    pub nlink: u64,
    pub size: u64,
    pub mtime_sec: i64,
    pub mtime_nsec: i64,
    pub ctime_sec: i64,
    pub ctime_nsec: i64,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PersistentHandle {
    pub handle_type: i32,
    pub bytes: Vec<u8>,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Snapshot {
    pub identity: Identity,
    pub handle: PersistentHandle,
    pub attributes: BTreeMap<String, Vec<u8>>,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct StableDirectoryIdentity {
    pub dev: u64,
    pub ino: u64,
    pub mode: u32,
    pub uid: u32,
    pub gid: u32,
    pub nlink: u64,
    pub size: u64,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RetainedDirectory {
    pub path: PathBuf,
    pub identity: StableDirectoryIdentity,
    pub handle: PersistentHandle,
    pub attributes: BTreeMap<String, Vec<u8>>,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RetainedOriginal {
    pub name: String,
    pub snapshot: Snapshot,
    pub sha256: String,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RetainedOriginalsSpec {
    pub schema: String,
    pub candidate_id: String,
    pub directory: RetainedDirectory,
    pub files: [RetainedOriginal; 2],
}
fn attributes(values: &BTreeMap<String, Vec<u8>>) -> bool {
    values.len() <= 32
        && values.iter().all(|(name, value)| {
            !name.is_empty()
                && name.len() <= 255
                && !name.as_bytes().contains(&0)
                && value.len() <= 16384
        })
        && values
            .iter()
            .map(|(name, value)| name.len() + value.len())
            .sum::<usize>()
            <= 65536
}
fn handle(value: &PersistentHandle, ino: u64) -> bool {
    // ext4's inode/generation handle; every byte, including generation, must
    // subsequently equal the independently captured actual kernel handle.
    value.handle_type == 1
        && value.bytes.len() == 8
        && u64::from(u32::from_ne_bytes(
            value.bytes[..4].try_into().expect("checked handle"),
        )) == ino
}
impl RetainedOriginalsSpec {
    pub fn expected_directory(&self) -> PathBuf {
        Path::new(WORK_BASE)
            .join(format!("working-qualification-{}", self.candidate_id))
            .join("data-pair.rollback")
    }
    pub fn validate(&self) -> Result<(), String> {
        let d = &self.directory;
        if self.schema != SCHEMA
            || !digest(&self.candidate_id)
            || d.path != self.expected_directory()
            || d.identity.dev == 0
            || d.identity.ino == 0
            || d.identity.mode & 0o170000 != 0o040000
            || d.identity.mode & 0o022 != 0
            || !matches!(d.identity.uid, 0 | 1000)
            || !matches!(d.identity.gid, 0 | 1000)
            || d.identity.nlink < 2
            || d.identity.size == 0
            || !handle(&d.handle, d.identity.ino)
            || !attributes(&d.attributes)
        {
            return Err(
                "retained original directory is not the fixed source-bound rollback generation"
                    .into(),
            );
        }
        for (file, (name, size)) in self.files.iter().zip([
            ("data.img", ORIGINAL_DATA_BYTES),
            ("metadata.img", ORIGINAL_METADATA_BYTES),
        ]) {
            let id = &file.snapshot.identity;
            if file.name != name
                || !digest(&file.sha256)
                || id.dev != d.identity.dev
                || id.ino == 0
                || id.mode & 0o170000 != 0o100000
                || id.mode & 0o133 != 0
                || id.nlink != 1
                || id.size != size
                || !matches!(id.uid, 0 | 1000)
                || !matches!(id.gid, 0 | 1000)
                || id.mtime_sec < 0
                || id.ctime_sec < 0
                || !(0..1_000_000_000).contains(&id.mtime_nsec)
                || !(0..1_000_000_000).contains(&id.ctime_nsec)
                || !handle(&file.snapshot.handle, id.ino)
                || !attributes(&file.snapshot.attributes)
            {
                return Err(
                    "retained original image comparison is incomplete or outside the fixed pair"
                        .into(),
                );
            }
        }
        if self.files[0].snapshot.identity.ino == self.files[1].snapshot.identity.ino {
            return Err("retained original data and metadata alias one inode".into());
        }
        Ok(())
    }
}
