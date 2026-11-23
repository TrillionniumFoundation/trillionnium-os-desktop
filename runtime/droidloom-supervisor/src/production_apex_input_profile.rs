//! Complete original CP3A APEX input lineage shared by producer and consumer.
//! Exact bytes identify the selected immutable cohort. They are not an AVB
//! signature check, mounted-payload observation or apexd execution witness.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

#[path = "production_apex_archive.rs"]
pub(crate) mod archive;

const PROFILE: &[u8] = include_bytes!("production_apex_input_profile.json");
const PROFILE_SHA256: &str = "f3ab57e31c73ea963bd6cf4bed81779f49ebb052c68207582c75039b6fdc039f";

#[derive(Clone, Debug, Serialize, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct ApexInput {
    pub(crate) name: String,
    pub(crate) version: u64,
    pub(crate) container_file: String,
    pub(crate) container_bytes: u64,
    pub(crate) container_sha256: String,
    pub(crate) original_apex_bytes: u64,
    pub(crate) original_apex_sha256: String,
    pub(crate) payload_bytes: u64,
    pub(crate) payload_sha256: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "lowercase")]
pub(crate) enum PayloadFilesystem {
    Ext4,
    Erofs,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FixedApex {
    pub(crate) input: ApexInput,
    pub(crate) filesystem: PayloadFilesystem,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Profile {
    schema: String,
    source_system_bytes: u64,
    source_system_sha256: String,
    original_capture_sha256: String,
    apexes: Vec<FixedApex>,
}

pub(crate) fn original_inputs() -> Result<Vec<FixedApex>, &'static str> {
    if format!("{:x}", Sha256::digest(PROFILE)) != PROFILE_SHA256 {
        return Err("compiled CP3A APEX source profile bytes changed");
    }
    let profile: Profile = serde_json::from_slice(PROFILE)
        .map_err(|_| "compiled CP3A APEX source profile is malformed")?;
    if profile.schema != "droidloom-fixed-cp3a-apex-input-profile-v1"
        || profile.source_system_bytes != 2_294_853_632
        || profile.source_system_sha256
            != "dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4"
        || profile.original_capture_sha256
            != "1c1ff9866f5828990abb71884720c1d3aa6cc35eccf1ff0950c658ce52d2939a"
        || profile.apexes.len() != 38
        || profile
            .apexes
            .windows(2)
            .any(|pair| pair[0].input.name >= pair[1].input.name)
        || profile.apexes.iter().any(|row| {
            (row.filesystem == PayloadFilesystem::Erofs) != (row.input.name == "com.android.virt")
        })
    {
        return Err("compiled CP3A APEX profile must retain all 38 exact source roles");
    }
    Ok(profile.apexes)
}

pub(crate) fn validate(inputs: &[ApexInput]) -> Result<(), &'static str> {
    let expected = original_inputs()?;
    if expected.len() != inputs.len()
        || !expected
            .iter()
            .zip(inputs)
            .all(|(fixed, actual)| fixed.input == *actual)
    {
        return Err(
            "CP3A execution requires the complete exact original 38-container/APEX/payload lineage",
        );
    }
    Ok(())
}

/// The builtin loop provider never opens or accepts a decompressed data file.
/// A separate immutable-output provider is required for the 28 CAPEX inputs.
pub(crate) fn original_builtin(index: usize) -> Result<FixedApex, &'static str> {
    let row = original_inputs()?
        .into_iter()
        .nth(index)
        .ok_or("fixed original APEX role index")?;
    if !row.input.container_file.ends_with(".apex")
        || row.input.container_bytes != row.input.original_apex_bytes
        || row.input.container_sha256 != row.input.original_apex_sha256
    {
        return Err("builtin APEX block source must be an uncompressed original system member");
    }
    Ok(row)
}

/// Only the exact 28 compressed roles enter the sealed-output provider.
/// This selector cannot authorize an arbitrary decompressed file or pathname.
pub(crate) fn original_compressed(index: usize) -> Result<FixedApex, &'static str> {
    let row = original_inputs()?
        .into_iter()
        .nth(index)
        .ok_or("fixed original compressed APEX role index")?;
    if !row.input.container_file.ends_with(".capex")
        || row.input.container_bytes == 0
        || row.input.container_bytes > 32 * 1024 * 1024
        || row.input.original_apex_bytes == 0
        || row.input.original_apex_bytes > 64 * 1024 * 1024
        || row.input.container_sha256 == row.input.original_apex_sha256
    {
        return Err("compressed APEX source must be a fixed bounded original CAPEX member");
    }
    Ok(row)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cp3a_apex_profile_keeps_all_38_original_containers_and_erofs_virt() {
        let inputs = original_inputs().unwrap();
        assert_eq!(inputs.len(), 38);
        assert_eq!(
            inputs
                .iter()
                .filter(|row| row.filesystem == PayloadFilesystem::Ext4)
                .count(),
            37
        );
        let virt = inputs
            .iter()
            .find(|row| row.input.name == "com.android.virt")
            .unwrap();
        assert_eq!(virt.filesystem, PayloadFilesystem::Erofs);
        assert_eq!(virt.input.payload_bytes, 69_070_848);
        let runtime = inputs
            .iter()
            .find(|row| row.input.name == "com.android.runtime")
            .unwrap();
        assert_eq!(runtime.input.payload_bytes, 11_452_416);
        assert_eq!(
            runtime.input.payload_sha256,
            "f97a0b03fb4b5dc91ddc71b02fc1f9831749d4a2e3f7cd6db47e3378f31a6345"
        );
        validate(&inputs.into_iter().map(|row| row.input).collect::<Vec<_>>()).unwrap();
    }

    #[test]
    fn cp3a_apex_profile_rejects_omissions_order_versions_and_cross_cohort_layers() {
        let inputs: Vec<_> = original_inputs()
            .unwrap()
            .into_iter()
            .map(|row| row.input)
            .collect();
        for index in 0..inputs.len() {
            let mut missing = inputs.clone();
            missing.remove(index);
            assert!(validate(&missing).is_err());
            for mutation in 0..9 {
                let mut changed = inputs.clone();
                let row = &mut changed[index];
                match mutation {
                    0 => row.name.push_str(".other"),
                    1 => row.version += 1,
                    2 => row.container_file.push_str(".other"),
                    3 => row.container_bytes += 1,
                    4 => row.container_sha256 = "0".repeat(64),
                    5 => row.original_apex_bytes += 1,
                    6 => row.original_apex_sha256 = "0".repeat(64),
                    7 => row.payload_bytes += 1,
                    _ => row.payload_sha256 = "0".repeat(64),
                }
                assert!(validate(&changed).is_err());
            }
        }
        let mut reordered = inputs.clone();
        reordered.swap(0, 1);
        assert!(validate(&reordered).is_err());
        let mut extra = inputs.clone();
        extra.push(inputs[0].clone());
        assert!(validate(&extra).is_err());
        assert!(validate(&[]).is_err());
    }

    #[test]
    fn compressed_apex_roles_are_disjoint_bounded_and_complete() {
        let rows = original_inputs().unwrap();
        let mut count = 0;
        let mut container_bytes = 0;
        let mut original_bytes = 0;
        for (index, row) in rows.iter().enumerate() {
            let compressed = original_compressed(index);
            assert_ne!(compressed.is_ok(), original_builtin(index).is_ok());
            if compressed.is_ok() {
                assert!(row.input.container_file.ends_with(".capex"));
                container_bytes += row.input.container_bytes;
                original_bytes += row.input.original_apex_bytes;
                count += 1;
            }
        }
        assert_eq!(
            (count, container_bytes, original_bytes),
            (28, 179_560_448, 451_764_224)
        );
        assert!(original_compressed(38).is_err());
        assert!(original_compressed(usize::MAX).is_err());
    }

    #[test]
    fn builtin_apex_sources_exclude_all_decompression_outputs() {
        let rows = original_inputs().unwrap();
        let mut accepted = 0;
        for (index, row) in rows.iter().enumerate() {
            let result = original_builtin(index);
            assert_eq!(result.is_ok(), row.input.container_file.ends_with(".apex"));
            if result.is_ok() {
                accepted += 1;
            }
        }
        assert_eq!(accepted, 10);
        assert!(original_builtin(38).is_err());
        assert!(original_builtin(usize::MAX).is_err());
    }
}
