//! Bounded transport for the five files emitted by the kernel-first board observer.
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

pub const NAMES: [&str; 5] = [
    "contract.json",
    "manager-label.json",
    "policy.bin",
    "policy-export.bin",
    "derivation.json",
];
pub const LIMITS: [usize; 5] = [
    65536,
    65536,
    64 * 1024 * 1024,
    64 * 1024 * 1024,
    4 * 1024 * 1024,
];
pub const MAX_ENCODED: u64 = 2 * (65536 * 2 + 132 * 1024 * 1024) + 65536;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Member {
    file: String,
    bytes: usize,
    sha256: String,
    hex: String,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Release {
    schema: u32,
    scope: String,
    pub calibration_boot_id: String,
    pub systemd_invocation_id: String,
    pub base_cohort_sha256: String,
    pub runtime_manifest_sha256: String,
    files: [Member; 5],
}

fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

fn identity(boot: &str, invocation: &str) -> bool {
    let lower_hex=|v:u8| v.is_ascii_digit() || (b'a'..=b'f').contains(&v);
    boot.len()==36 && boot.bytes().enumerate().all(|(i,b)| if [8,13,18,23].contains(&i){b==b'-'}else{lower_hex(b)})
        && boot.bytes().any(|b|lower_hex(b) && b!=b'0')
        && invocation.len()==32 && invocation.bytes().all(lower_hex) && invocation.bytes().any(|b|b!=b'0')
}

impl Release {
    pub fn from_files(base: &str, runtime: &str, boot: &str, invocation: &str, files: [&[u8]; 5]) -> Result<Self, &'static str> {
        if !digest(base) || !digest(runtime) || !identity(boot, invocation) {
            return Err("complete selected digests required");
        }
        for (data, maximum) in files.iter().zip(LIMITS) {
            if data.is_empty() || data.len() > maximum {
                return Err("invalid board release member size");
            }
        }
        Ok(Self {
            schema: 1,
            calibration_boot_id: boot.into(),
            systemd_invocation_id: invocation.into(),
            scope: "android_kernel_first_mac_release_v1".into(),
            base_cohort_sha256: base.into(),
            runtime_manifest_sha256: runtime.into(),
            files: std::array::from_fn(|i| Member {
                file: NAMES[i].into(),
                bytes: files[i].len(),
                sha256: hex::encode(Sha256::digest(files[i])),
                hex: hex::encode(files[i]),
            }),
        })
    }
    pub fn files(&self, base: &str, runtime: &str) -> Result<Vec<Vec<u8>>, &'static str> {
        if self.schema != 1
            || self.scope != "android_kernel_first_mac_release_v1"
            || !identity(&self.calibration_boot_id, &self.systemd_invocation_id)
            || !digest(base)
            || !digest(runtime)
            || self.base_cohort_sha256 != base
            || self.runtime_manifest_sha256 != runtime
        {
            return Err("board capture belongs to a different selected release");
        }
        self.files
            .iter()
            .enumerate()
            .map(|(i, item)| {
                if item.file != NAMES[i]
                    || item.bytes == 0
                    || item.bytes > LIMITS[i]
                    || item.hex.len() != 2 * item.bytes
                    || !digest(&item.sha256)
                {
                    return Err("unexpected board capture member");
                }
                let bytes = hex::decode(&item.hex).map_err(|_| "invalid board capture bytes")?;
                if hex::encode(Sha256::digest(&bytes)) != item.sha256 {
                    return Err("board capture member digest mismatch");
                }
                Ok(bytes)
            })
            .collect()
    }
}
