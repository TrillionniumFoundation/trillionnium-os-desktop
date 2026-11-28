//! Whole original APK descriptors from one immutable, compiled public cohort.
//! Operator paths are provenance only. No caller can choose the installed root,
//! a package roster, a payload path, a signer, or an expected digest here.
use super::{directory, f9, invalid, PreparationMaterial, WorkingPreparationMaterials};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    ffi::OsString,
    fs::{self, File, OpenOptions},
    io,
    os::unix::fs::{FileExt, OpenOptionsExt},
    path::{Path, PathBuf},
    time::Instant,
};

pub const WORKING_APK_ROOT: &str = "/var/lib/droidloom-public-apks/4abd5c5d0a8ac89e739b2ba6dd508435a1d355b9ce975ba5ceacb50c1ee4a4a0";
const PACKAGE_COUNT: usize = 41;
const APK_COUNT: usize = 67;
const APK_BYTES: u64 = 5_192_131_867;
const IMAGE_PACKAGE: &str = "com.android.gallery3d";

fn need(ok: bool, message: &str) -> io::Result<()> {
    if ok { Ok(()) } else { Err(invalid(message)) }
}
fn before(end: Instant) -> io::Result<()> {
    need(Instant::now() < end, "public APK custody exceeded its original deadline")
}
fn digest(v: &str) -> bool {
    v.len() == 64 && v.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn field<'a>(v: &'a Value, key: &str) -> io::Result<&'a str> {
    v[key].as_str().ok_or_else(|| invalid("compiled APK source field is absent"))
}
fn signers(v: &Value) -> io::Result<BTreeSet<String>> {
    let values = v.as_array().ok_or_else(|| invalid("APK signer list is absent"))?;
    let mut result = BTreeSet::new();
    for value in values {
        let value = value.as_str().ok_or_else(|| invalid("APK signer is not text"))?;
        need(digest(value) && result.insert(value.to_owned()), "APK signer is invalid or repeated")?;
    }
    need((1..=4).contains(&result.len()), "APK signer count is outside its closed bound")?;
    Ok(result)
}
#[derive(Clone, Debug)]
struct ApkPin {
    bytes: u64,
    sha256: String,
    split: Option<String>,
}
#[derive(Clone, Debug)]
struct ApplicationPin {
    package: String,
    version_code: u64,
    version_name: String,
    signers: BTreeSet<String>,
    apks: Vec<ApkPin>,
    image_only: bool,
}
fn selected(raw: &[u8]) -> io::Result<Vec<ApplicationPin>> {
    let v: Value = serde_json::from_slice(raw).map_err(io::Error::other)?;
    need(v["schema"] == "p4-selected41-static-launch-inputs-v1"
        && v["package_count"] == PACKAGE_COUNT && v["apk_file_count"] == APK_COUNT
        && v["apk_total_bytes"] == APK_BYTES
        && v["all_current_apk_hashes_match_verified_signature_receipt"] == true,
        "public APK input is not the complete compiled apps41 cohort")?;
    let rows = v["applications"].as_array().ok_or_else(|| invalid("APK applications absent"))?;
    let mut packages = BTreeSet::new();
    let mut payloads = BTreeSet::new();
    let mut total = 0_u64;
    let mut result = Vec::new();
    for row in rows {
        let package = field(row, "package")?;
        need(package.len() < 256 && package.contains('.')
            && package.bytes().all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_'))
            && packages.insert(package.to_owned()), "APK package is invalid or repeated")?;
        let version_code = row["version_code"].as_u64().filter(|n| *n > 0)
            .ok_or_else(|| invalid("APK version code is absent"))?;
        let version_name = field(row, "version_name")?.to_owned();
        let expected_signers = signers(&row["signer_certificates_sha256"])?;
        let files = row["material_files"].as_array().ok_or_else(|| invalid("APK file set absent"))?;
        need((1..=32).contains(&files.len()), "APK set is outside the normal PackageInstaller bound")?;
        let mut apks = Vec::new();
        let mut splits = BTreeSet::new();
        for (index, item) in files.iter().enumerate() {
            let sha256 = field(item, "sha256")?.to_owned();
            let bytes = item["bytes"].as_u64().filter(|n| (4..=2_147_483_648).contains(n))
                .ok_or_else(|| invalid("APK byte count differs"))?;
            let split = if item["manifest_split_name"].is_null() { None }
                else { Some(field(item, "manifest_split_name")?.to_owned()) };
            need(digest(&sha256) && payloads.insert(sha256.clone())
                && splits.insert(split.clone()) && (index == 0) == split.is_none()
                && (index != 0 || item["expected_normalized_pm_name"] == "base.apk")
                && item["sdk37_signature_valid"] == true
                && signers(&item["verified_signer_certificates_sha256"])? == expected_signers
                && item["metadata"]["name"] == package
                && item["metadata"]["versionCode"].as_str()
                    .and_then(|n| n.parse::<u64>().ok()) == Some(version_code),
                "APK original manifest, signer, base/split order or digest differs")?;
            total = total.checked_add(bytes).ok_or_else(|| invalid("APK cohort size overflow"))?;
            apks.push(ApkPin { bytes, sha256, split });
        }
        need(apks.iter().map(|a| a.bytes).sum::<u64>() <= 2_147_483_648,
            "one APK set exceeds the normal original installer transport")?;
        result.push(ApplicationPin { package: package.to_owned(), version_code, version_name,
            signers: expected_signers, apks, image_only: package == IMAGE_PACKAGE });
    }
    need(result.len() == PACKAGE_COUNT && payloads.len() == APK_COUNT && total == APK_BYTES
        && result.iter().filter(|p| p.image_only).count() == 1,
        "APK cohort is incomplete or its whole byte count differs")?;
    result.sort_by(|a, b| a.package.cmp(&b.package));
    Ok(result)
}
fn name(pin: &ApkPin) -> OsString { OsString::from(format!("{}.apk", pin.sha256)) }
fn roster(root: &Path, expected: &BTreeSet<OsString>) -> io::Result<()> {
    let actual = fs::read_dir(root)?.map(|e| e.map(|e| e.file_name()))
        .collect::<io::Result<BTreeSet<_>>>()?;
    need(&actual == expected, "published APK directory has missing or extra members")
}
struct HeldApk { pin: ApkPin, file: File, identity: [u64; 9] }
impl HeldApk {
    fn verify_body(&self, end: Instant) -> io::Result<()> {
        before(end)?;
        need(f9(&self.file.metadata()?)? == self.identity, "original APK descriptor changed")?;
        let mut hash = Sha256::new();
        let mut at = 0_u64;
        let mut buffer = vec![0_u8; 1024 * 1024];
        while at < self.pin.bytes {
            before(end)?;
            let size = buffer.len().min((self.pin.bytes - at) as usize);
            self.file.read_exact_at(&mut buffer[..size], at)?;
            if at == 0 { need(buffer[..4] == *b"PK\x03\x04", "original APK has no ZIP header")?; }
            hash.update(&buffer[..size]); at += size as u64;
        }
        need(self.file.read_at(&mut [0], at)? == 0
            && format!("{:x}", hash.finalize()) == self.pin.sha256
            && f9(&self.file.metadata()?)? == self.identity,
            "original APK whole bytes, EOF or held identity changed")?;
        before(end)
    }
}
/// One admitted original APK set; only capture() can construct it.
/// These descriptors are data sources, not a record of a successful installation.
pub struct WorkingApplicationApks { pin: ApplicationPin, files: Vec<HeldApk> }
impl WorkingApplicationApks {
    pub fn package(&self) -> &str { &self.pin.package }
    pub fn version_code(&self) -> u64 { self.pin.version_code }
    pub fn version_name(&self) -> &str { &self.pin.version_name }
    pub fn signer_certificates(&self) -> &BTreeSet<String> { &self.pin.signers }
    pub fn image_only(&self) -> bool { self.pin.image_only }
    pub fn files(&self) -> Vec<&File> { self.files.iter().map(|a| &a.file).collect() }
    pub fn lengths(&self) -> Vec<u64> { self.files.iter().map(|a| a.pin.bytes).collect() }
    pub fn expected_apks(&self) -> Vec<Value> {
        self.files.iter().map(|a| json!({"bytes":a.pin.bytes,"sha256":a.pin.sha256,
            "manifest_split_name":a.pin.split})).collect()
    }
    pub fn verify(&self, end: Instant) -> io::Result<()> {
        for apk in &self.files {
            let named = OpenOptions::new().read(true).custom_flags(0x20000 | 0x80000 | 0x800)
                .open(Path::new(WORKING_APK_ROOT).join(name(&apk.pin)))?;
            need(f9(&named.metadata()?)? == apk.identity, "original APK named inode changed")?;
            apk.verify_body(end)?;
            need(f9(&named.metadata()?)? == apk.identity, "APK name changed during readback")?;
        }
        Ok(())
    }
    pub fn comparison(&self) -> Value {
        json!({"package":self.pin.package,"version_code":self.pin.version_code,
            "version_name":self.pin.version_name,"signer_certificates_sha256":self.pin.signers,
            "image_only":self.pin.image_only,"apks":self.files.iter().map(|a| json!({
                "path":Path::new(WORKING_APK_ROOT).join(name(&a.pin)),"bytes":a.pin.bytes,
                "sha256":a.pin.sha256,"manifest_split_name":a.pin.split,"held_identity":a.identity,
            })).collect::<Vec<_>>(),"source_only":true,"installed":false,"production_ready":false})
    }
}
/// Keeps all 67 actual source descriptors and protected parents for the whole phase.
/// No Deserialize, Clone, caller path or caller-supplied acceptance flag exists.
pub struct WorkingApkMaterials<'a> {
    documents: &'a WorkingPreparationMaterials,
    parents: Vec<(PathBuf, File, [u64; 5])>,
    packages: Vec<WorkingApplicationApks>,
    names: BTreeSet<OsString>,
}
impl<'a> WorkingApkMaterials<'a> {
    pub fn capture(documents: &'a WorkingPreparationMaterials, end: Instant) -> io::Result<Self> {
        before(end)?;
        let rows = selected(documents.bytes(PreparationMaterial::Selection)?)?;
        let root = Path::new(WORKING_APK_ROOT);
        need(root.canonicalize()? == root, "published APK root is aliased")?;
        let mut parents = Vec::new();
        for path in root.ancestors() {
            let file = directory(path)?;
            let identity = f9(&file.metadata()?)?;
            need(identity[2] & 0o170000 == 0o040000 && identity[2] & 0o022 == 0
                && identity[3..5] == [0, 0], "APK source parent is not protected root custody")?;
            if path == root { need(identity[2] == 0o040700, "APK cohort directory is not root 0700")?; }
            parents.push((path.into(), file, identity[..5].try_into().map_err(io::Error::other)?));
        }
        let names = rows.iter().flat_map(|p| p.apks.iter().map(name)).collect();
        roster(root, &names)?;
        let mut packages = Vec::new();
        for pin in rows {
            let mut files = Vec::new();
            for apk in &pin.apks {
                before(end)?;
                let file = OpenOptions::new().read(true).custom_flags(0x20000 | 0x80000 | 0x800)
                    .open(root.join(name(apk)))?;
                let identity = f9(&file.metadata()?)?;
                need(identity[2] == 0o100400 && identity[3..6] == [0, 0, 1]
                    && identity[6] == apk.bytes, "APK is not its exact root 0400 single-link original")?;
                let held = HeldApk { pin: apk.clone(), file, identity };
                held.verify_body(end)?;
                files.push(held);
            }
            packages.push(WorkingApplicationApks { pin, files });
        }
        let value = Self { documents, parents, packages, names };
        value.guard()?; before(end)?; Ok(value)
    }
    pub fn guard(&self) -> io::Result<()> {
        self.documents.guard()?;
        roster(Path::new(WORKING_APK_ROOT), &self.names)?;
        for (path, file, identity) in &self.parents {
            need(f9(&file.metadata()?)?[..5] == *identity
                && f9(&directory(path)?.metadata()?)?[..5] == *identity,
                "APK parent custody changed")?;
        }
        for package in &self.packages { for apk in &package.files {
            let named = OpenOptions::new().read(true).custom_flags(0x20000 | 0x80000 | 0x800)
                .open(Path::new(WORKING_APK_ROOT).join(name(&apk.pin)))?;
            need(f9(&apk.file.metadata()?)? == apk.identity && f9(&named.metadata()?)? == apk.identity,
                "APK held or named identity changed")?;
        }}
        Ok(())
    }
    pub fn applications(&self) -> &[WorkingApplicationApks] { &self.packages }
    pub fn comparison(&self) -> Value {
        json!({"schema":"droidloom.working-public-apk-source-custody.v1",
            "root":WORKING_APK_ROOT,"package_count":PACKAGE_COUNT,"apk_count":APK_COUNT,
            "apk_bytes":APK_BYTES,"packages":self.packages.iter().map(|p|p.comparison()).collect::<Vec<_>>(),
            "source_only":true,"production_ready":false})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{io::Write, time::Duration};
    #[test]
    fn working_apk_manifest_closes_all_originals_and_keeps_image_gallery_distinct() {
        let rows = selected(PreparationMaterial::Selection.checked().unwrap()).unwrap();
        assert_eq!(rows.len(), 41);
        assert_eq!(rows.iter().map(|r|r.apks.len()).sum::<usize>(), 67);
        assert_eq!(rows.iter().filter(|r|!r.image_only).count(), 40);
        assert_eq!(rows.iter().filter(|r|r.image_only).map(|r|r.package.as_str()).collect::<Vec<_>>(), [IMAGE_PACKAGE]);
        for key in ["sdk37_signature_valid", "verified_signer_certificates_sha256"] {
            let mut value: Value = serde_json::from_slice(PreparationMaterial::Selection.checked().unwrap()).unwrap();
            value["applications"][0]["material_files"][0][key] = Value::Null;
            assert!(selected(&serde_json::to_vec(&value).unwrap()).is_err());
        }
        let mut value: Value = serde_json::from_slice(PreparationMaterial::Selection.checked().unwrap()).unwrap();
        value["applications"][0]["material_files"][0]["metadata"]["name"] = json!("other.package");
        assert!(selected(&serde_json::to_vec(&value).unwrap()).is_err());
    }
    #[test]
    fn working_apk_whole_descriptor_rejects_wrong_bytes_growth_and_expired_end() {
        let mut file = tempfile::tempfile().unwrap(); let body = b"PK\x03\x04unchanged-original";
        file.write_all(body).unwrap(); file.sync_all().unwrap();
        let pin = ApkPin { bytes:body.len() as u64, sha256:format!("{:x}",Sha256::digest(body)), split:None };
        let mut held = HeldApk { identity:f9(&file.metadata().unwrap()).unwrap(), pin, file };
        let end = Instant::now()+Duration::from_secs(10); held.verify_body(end).unwrap();
        assert!(held.verify_body(Instant::now()).is_err());
        held.pin.sha256 = "0".repeat(64); assert!(held.verify_body(end).is_err());
        held.pin.sha256 = format!("{:x}",Sha256::digest(body));
        held.file.set_len(body.len() as u64+1).unwrap(); assert!(held.verify_body(end).is_err());
    }
    #[test]
    fn working_apk_published_directory_rejects_missing_and_unexpected_members() {
        let root = tempfile::tempdir().unwrap(); let expected:BTreeSet<_>=[OsString::from("fixed.apk")].into_iter().collect();
        assert!(roster(root.path(), &expected).is_err());
        fs::write(root.path().join("fixed.apk"), b"data").unwrap(); roster(root.path(), &expected).unwrap();
        fs::write(root.path().join("extra.apk"), b"data").unwrap(); assert!(roster(root.path(), &expected).is_err());
    }
}
