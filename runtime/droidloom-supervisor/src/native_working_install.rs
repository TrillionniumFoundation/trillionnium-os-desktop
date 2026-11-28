//! Closed original public-APK installation on the actual working-copy Main.
//! Serialized comparisons never acquire a Main, choose paths, or authorize a
//! signature bypass. Only the fixed preparation peer can dispatch this request.
use crate::main_custody::RuntimeMainCustody;
use crate::control::MainCustodyObservation;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{collections::BTreeSet, fs::File, os::unix::fs::FileExt, time::{Duration, Instant}};

pub const SOURCE_CAPTURE_SECONDS: u64 = crate::native_working_contract::preparation::ORIGINAL_APK_CAPTURE_SECONDS;
// One nonrenewable package window: 120 s original-FD capture, 120 s receiver
// full-body verification, two 70 s Main bookends, the normal 110 s PM session,
// and 70 s transport/retirement reserve. Individual factory limits stay intact.
pub const PACKAGE_SECONDS: u64 = crate::native_working_contract::preparation::ORIGINAL_APK_PACKAGE_SECONDS;
pub(crate) const PACKAGE_LIMIT: Duration = Duration::from_secs(PACKAGE_SECONDS);
pub(crate) const MAX_REPLY_BYTES: usize = 1024 * 1024;
pub const SELECTION_SHA256: &str = "4abd5c5d0a8ac89e739b2ba6dd508435a1d355b9ce975ba5ceacb50c1ee4a4a0";
const SELECTION: &[u8] = include_bytes!("../../../tools/droidloom-update/resources/working-preparation/apps41/SELECTED41.json");
const SIGNATURES: &[u8] = include_bytes!("../../../tools/droidloom-update/resources/working-preparation/apps41/SIGNATURE-HANDOFF.json");
const IMPORT: &[u8] = include_bytes!("../../../tools/droidloom-update/resources/working-preparation/apps41/IMPORT.json");
const VERIFICATION: &[u8] = include_bytes!("../../../tools/droidloom-update/resources/working-preparation/apps41/NORMAL-INPUT-VERIFICATION.json");
type Result<T> = std::result::Result<T, String>;
fn need(ok: bool, message: &str) -> Result<()> { if ok { Ok(()) } else { Err(message.into()) } }
pub(crate) fn hash(raw: &[u8]) -> String { format!("{:x}", Sha256::digest(raw)) }
fn digest(v: &str) -> bool {
    v.len() == 64 && v.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct OriginalSegment {
    pub(crate) bytes: u64,
    pub(crate) sha256: String,
    pub(crate) manifest_split_name: Option<String>,
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct OriginalApplication {
    pub(crate) package: String,
    pub(crate) version_code: u64,
    pub(crate) version_name: String,
    pub(crate) signer_certificates_sha256: BTreeSet<String>,
    pub(crate) segments: Vec<OriginalSegment>,
}
impl OriginalApplication {
    pub(crate) fn lengths(&self) -> Vec<u64> { self.segments.iter().map(|v| v.bytes).collect() }
    pub(crate) fn bytes(&self) -> u64 { self.segments.iter().map(|v| v.bytes).sum() }
    pub(crate) fn require_payload(&self, file: &File, end: Instant) -> Result<()> {
        crate::control::apk_payload::validate(file, &self.lengths()).map_err(|e| e.to_string())?;
        let mut buffer = vec![0_u8; 1024 * 1024];
        let mut offset = 0_u64;
        for segment in &self.segments {
            let mut digest = Sha256::new();
            let mut done = 0_u64;
            while done < segment.bytes {
                need(Instant::now() < end, "original public APK verification deadline expired")?;
                let count = buffer.len().min((segment.bytes - done) as usize);
                file.read_exact_at(&mut buffer[..count], offset + done).map_err(|e| e.to_string())?;
                digest.update(&buffer[..count]); done += count as u64;
            }
            need(format!("{:x}", digest.finalize()) == segment.sha256,
                "normal install payload differs from the fixed publisher-signed original")?;
            offset += segment.bytes;
        }
        need(file.read_at(&mut [0], offset).map_err(|e| e.to_string())? == 0
            && Instant::now() < end, "normal install payload has extra bytes or expired")?;
        crate::control::apk_payload::validate(file, &self.lengths()).map_err(|e| e.to_string())
    }
}
fn source() -> Result<Value> {
    for (raw, expected) in [
        (SELECTION, SELECTION_SHA256),
        (SIGNATURES, "1d44a6f5cb247de704bd64a0973226612672619545ecd328e4536bdda0236731"),
        (IMPORT, "1f06db0be3a790bad7a4ba61507b06024289b145cfe3de8f27cea3ca890b091d"),
        (VERIFICATION, "78a512d9cf3465613b2f4ccd79de656a4280dee37311e8c6958a6136f2bf2513"),
    ] { need(hash(raw) == expected, "compiled normal apps41 source admission changed")?; }
    let value: Value = serde_json::from_slice(SELECTION).map_err(|e| e.to_string())?;
    need(value["schema"] == "p4-selected41-static-launch-inputs-v1"
        && value["package_count"] == 41 && value["apk_file_count"] == 67
        && value["apk_total_bytes"] == 5_192_131_867_u64,
        "normal install source is not the complete fixed apps41 cohort")?;
    Ok(value)
}
pub(crate) fn application(package: &str) -> Result<OriginalApplication> {
    need(package != "com.android.gallery3d",
        "Gallery is admitted only by its actual system-image observation, never a data APK replacement")?;
    let value = source()?;
    let rows = value["applications"].as_array().ok_or("compiled application rows absent")?;
    let matching: Vec<_> = rows.iter().filter(|r| r["package"] == package).collect();
    need(rows.len() == 41 && matching.len() == 1, "package is outside the compiled original installation roster")?;
    let row = matching[0];
    let signers: BTreeSet<String> = serde_json::from_value(row["signer_certificates_sha256"].clone()).map_err(|e| e.to_string())?;
    need(!signers.is_empty() && signers.len() <= 4 && signers.iter().all(|v| digest(v)),
        "compiled original APK signer set invalid")?;
    let version_code = row["version_code"].as_u64().filter(|n| *n > 0).ok_or("original APK version absent")?;
    let version_name = row["version_name"].as_str().ok_or("original APK version name absent")?.to_owned();
    let files = row["material_files"].as_array().ok_or("original APK files absent")?;
    need((1..=32).contains(&files.len()), "original APK split count outside the normal transport")?;
    let mut segments = Vec::new();
    let mut names = BTreeSet::new();
    for (index, v) in files.iter().enumerate() {
        let bytes = v["bytes"].as_u64().filter(|n| (4..=2_147_483_648).contains(n)).ok_or("original APK size invalid")?;
        let sha256 = v["sha256"].as_str().filter(|n| digest(n)).ok_or("original APK digest invalid")?.to_owned();
        let manifest_split_name: Option<String> = serde_json::from_value(v["manifest_split_name"].clone()).map_err(|e| e.to_string())?;
        let actual_signers: BTreeSet<String> = serde_json::from_value(v["verified_signer_certificates_sha256"].clone()).map_err(|e| e.to_string())?;
        need(v["sdk37_signature_valid"] == true && actual_signers == signers
            && v["metadata"]["name"] == package
            && v["metadata"]["versionCode"].as_str().and_then(|v| v.parse::<u64>().ok()) == Some(version_code)
            && (index == 0) == manifest_split_name.is_none() && names.insert(manifest_split_name.clone()),
            "original APK signer, manifest, or complete base/split set differs")?;
        segments.push(OriginalSegment { bytes, sha256, manifest_split_name });
    }
    let result = OriginalApplication { package: package.into(), version_code, version_name,
        signer_certificates_sha256: signers, segments };
    need(result.bytes() <= 2_147_483_648, "one normal original APK set exceeds 2 GiB")?;
    Ok(result)
}
fn original_working_main(main: &RuntimeMainCustody) -> Result<()> {
    main.validate(&main.epoch)?;
    let origin = main.persistent_data.original_copy_origin.as_ref()
        .ok_or("ordinary app preparation requires the actual source-owned working copy origin")?;
    let working = main.persistent_data.backings.each_ref().map(|v| v.backing.stable7());
    need(origin.working == working && origin.original.iter().zip(&working)
        .all(|(original, held)| original[0..2] != held[0..2]),
        "ordinary app installation cannot touch the retained original data pair")
}
fn monotonic_ns() -> Result<u64> {
    let mut value: libc::timespec = unsafe { std::mem::zeroed() };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut value) } != 0 {
        return Err(std::io::Error::last_os_error().to_string());
    }
    need(value.tv_sec >= 0 && (0..1_000_000_000).contains(&value.tv_nsec), "working install monotonic clock invalid")?;
    (value.tv_sec as u64).checked_mul(1_000_000_000).and_then(|v| v.checked_add(value.tv_nsec as u64)).ok_or("working install clock overflow".into())
}
fn encode_end(end: Instant) -> Result<u64> {
    let clock = monotonic_ns()?;
    let left = end.checked_duration_since(Instant::now()).filter(|v| !v.is_zero()).ok_or("original working install deadline elapsed")?;
    need(left <= PACKAGE_LIMIT, "working install package end exceeds its fixed cap")?;
    clock.checked_add(u64::try_from(left.as_nanos()).map_err(|_| "working install end overflow")?).ok_or("working install end overflow".into())
}
fn decode_end(end: u64) -> Result<Instant> {
    let now = Instant::now();
    let left = end.checked_sub(monotonic_ns()?).filter(|v| *v > 0).ok_or("original working install deadline elapsed")?;
    need(u128::from(left) <= PACKAGE_LIMIT.as_nanos(), "working install request enlarged its original end")?;
    now.checked_add(Duration::from_nanos(left)).ok_or("working install deadline overflow".into())
}
fn closed<'de, D, T>(de: D) -> std::result::Result<T, D::Error>
where D: serde::Deserializer<'de>, T: serde::de::DeserializeOwned + Serialize {
    let raw = crate::native_preparation_json::unique_json_value(de)?;
    let value: T = serde_json::from_value(raw.clone()).map_err(serde::de::Error::custom)?;
    if serde_json::to_value(&value).map_err(serde::de::Error::custom)? != raw {
        return Err(serde::de::Error::custom("unrecognized original installation comparison fields"));
    }
    Ok(value)
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorkingInstallRequest {
    schema: String,
    #[serde(deserialize_with = "closed")]
    main: RuntimeMainCustody,
    package: String,
    deadline_monotonic_ns: u64,
}
impl WorkingInstallRequest {
    pub(crate) fn from_owned(main: &MainCustodyObservation, package: &str, end: Instant) -> Result<Self> {
        let result = Self { schema: "droidloom.working-original-apk-install-request.v1".into(),
            main: main.facts().clone(), package: package.into(), deadline_monotonic_ns: encode_end(end)? };
        result.validate()?; Ok(result)
    }
    pub(crate) fn validate(&self) -> Result<()> {
        need(self.schema == "droidloom.working-original-apk-install-request.v1", "working install request schema differs")?;
        original_working_main(&self.main)?; application(&self.package)?; self.deadline()?; Ok(())
    }
    pub(crate) fn main(&self) -> &RuntimeMainCustody { &self.main }
    pub(crate) fn package(&self) -> &str { &self.package }
    pub(crate) fn deadline(&self) -> Result<Instant> { decode_end(self.deadline_monotonic_ns) }
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorkingInstallReply {
    schema: String,
    request: WorkingInstallRequest,
    #[serde(deserialize_with = "closed")]
    before_main: RuntimeMainCustody,
    #[serde(deserialize_with = "closed")]
    after_main: RuntimeMainCustody,
    installation: Value,
}
impl WorkingInstallReply {
    pub(crate) fn from_actual(request: WorkingInstallRequest, before_main: RuntimeMainCustody,
        after_main: RuntimeMainCustody, installation: &crate::production_application::InstallObservation) -> Result<Self>
    {
        let result = Self { schema: "droidloom.working-original-apk-install-reply.v1".into(),
            request, before_main, after_main, installation: serde_json::to_value(installation).map_err(|e| e.to_string())? };
        result.validate(&result.request)?; Ok(result)
    }
    pub(crate) fn validate(&self, expected: &WorkingInstallRequest) -> Result<()> {
        need(self.schema == "droidloom.working-original-apk-install-reply.v1"
            && &self.request == expected && self.before_main == *expected.main()
            && self.after_main == self.before_main, "actual installation Main or original request changed")?;
        original_working_main(&self.before_main)?;
        let source = application(expected.package())?;
        let value = &self.installation;
        let session = value["session"].as_u64().filter(|v| (1..=i32::MAX as u64).contains(v)).ok_or("normal install session absent")?;
        let segments = value["segments"].as_array().ok_or("normal install segment observations absent")?;
        need(value["user"] == 0 && value["bytes"] == source.bytes() && segments.len() == source.segments.len(),
            "normal install original package bytes or user differs")?;
        for (index, (actual, pin)) in segments.iter().zip(&source.segments).enumerate() {
            need(*actual == json!({"index":index,"bytes":pin.bytes,"sha256":pin.sha256}),
                "normal install consumed different original APK bytes")?;
        }
        let commands = value["commands"].as_array().ok_or("actual install command receipts absent")?;
        let mut expected_commands = vec![json!({"install":"Create","user":0,"bytes":source.bytes()})];
        expected_commands.extend(source.segments.iter().enumerate().map(|(index, v)|
            json!({"install":"Write","session":session,"index":index,"bytes":v.bytes})));
        expected_commands.push(json!({"install":"Commit","session":session}));
        need(commands.len() == expected_commands.len() && commands.iter().zip(expected_commands)
            .all(|(actual, expected)| actual["command"] == expected),
            "normal install did not retain one create/all-original-segments/commit history")?;
        Ok(())
    }
    pub(crate) fn main(&self) -> &RuntimeMainCustody { &self.after_main }
    pub(crate) fn comparison(&self) -> Result<Value> {
        let mut value = serde_json::to_value(self).map_err(|e| e.to_string())?;
        value["source_selection_sha256"] = SELECTION_SHA256.into();
        value["package_manager_commit_observed"] = true.into();
        value["fresh_runtime_identity_and_business_acceptance_pending"] = true.into();
        value["production_ready"] = false.into();
        Ok(value)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn working_original_install_roster_is_exact_and_excludes_image_gallery() {
        let raw = source().unwrap();
        let mut count = 0; let mut segments = 0; let mut bytes = 0;
        for row in raw["applications"].as_array().unwrap() {
            let name = row["package"].as_str().unwrap();
            if name == "com.android.gallery3d" { assert!(application(name).is_err()); continue; }
            let app = application(name).unwrap(); count += 1; segments += app.segments.len(); bytes += app.bytes();
        }
        assert_eq!((count, segments, bytes), (40, 66, 5_184_741_442));
        for unknown in ["com.test.app", "com.sankuai.meituan.takeoutnew --user 10", "../SELECTED41.json"] {
            assert!(application(unknown).is_err());
        }
        assert_eq!(application("com.ss.android.lark").unwrap().version_code, 8_080_550);
        assert_eq!(application("com.ss.android.article.news").unwrap().version_code, 19_300);
    }
    #[test]
    fn working_original_install_payload_rejects_other_bytes_and_unrenewable_end() {
        let file = crate::control::apk_payload::test_payload(b"PK\x03\x04onePK\x03\x04two");
        let spec = OriginalApplication { package: "test.only".into(), version_code: 1, version_name: "1".into(),
            signer_certificates_sha256: BTreeSet::new(), segments: vec![
                OriginalSegment { bytes: 7, sha256: hash(b"PK\x03\x04one"), manifest_split_name: None },
                OriginalSegment { bytes: 7, sha256: hash(b"PK\x03\x04two"), manifest_split_name: Some("feature".into()) },
            ] };
        let end = Instant::now() + Duration::from_secs(10);
        spec.require_payload(&file, end).unwrap();
        let mut wrong = spec.clone(); wrong.segments[1].sha256 = "0".repeat(64);
        assert!(wrong.require_payload(&file, end).is_err());
        let mut truncated = spec.clone(); truncated.segments.pop();
        assert!(truncated.require_payload(&file, end).is_err());
        assert!(spec.require_payload(&file, Instant::now()).is_err());
        assert!(encode_end(Instant::now()).is_err());
        assert!(encode_end(Instant::now() + PACKAGE_LIMIT + Duration::from_secs(1)).is_err());
        let encoded = encode_end(end).unwrap();
        assert!(decode_end(encoded).unwrap() <= end + Duration::from_millis(5));
        assert!(decode_end(0).is_err());
    }
}
