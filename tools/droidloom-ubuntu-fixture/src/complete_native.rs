//! A complete, freshly bootstrapped Ubuntu root is a separate source authority.
//! It is never admitted by relaxing the historical public-file selector.
use crate::complete_snapshot::{self, CompleteEntry, Snapshot, StaticDevice};
use crate::model::{Content, Identity};
use crate::{Result, ensure, fs, paths};
use rustix::fs::{self as rfs, AtFlags, FileType, Mode, OFlags};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

pub(super) const SCHEMA: &str = "droidloom.complete-ubuntu-fixture-manifest.v1";
const SOURCE_SCHEMA: &str = "droidloom.complete-ubuntu-native-source.v1";
const LIMIT: u64 = 16 * 1024 * 1024;
const BASELINE_LIMIT: u64 = 64 * 1024 * 1024;
#[path = "complete_installed.rs"]
mod installed;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(super) struct EvidencePin {
    pub path: PathBuf,
    pub bytes: u64,
    pub sha256: String,
    pub device: u64,
    pub inode: u64,
    pub mode: u32,
    pub uid: u32,
    pub gid: u32,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(super) struct RootIdentity {
    pub path: PathBuf,
    pub device: u64,
    pub inode: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct SourceReceipt {
    pub schema: String,
    pub stage: String,
    pub root: RootIdentity,
    pub bootstrap_receipt: EvidencePin,
    pub baseline_receipt: Option<EvidencePin>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub baseline_manifest: Option<EvidencePin>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub installed_admission_directory: Option<PathBuf>,
    pub package_transactions: Vec<EvidencePin>,
    pub packages: EvidencePin,
    pub dpkg_status: EvidencePin,
    pub native_release: Option<EvidencePin>,
    pub native_transaction: Option<EvidencePin>,
    pub fresh_generated_root: bool,
    pub private_accounts_copied: bool,
    pub configured: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct RecordedJson {
    pub pin: EvidencePin,
    pub body: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(super) struct Package {
    pub package: String,
    pub version: String,
    pub architecture: String,
    pub status: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Packages {
    schema: String,
    packages: Vec<Package>,
    original_requested_count: usize,
    original_requested_versions_exact: bool,
    configured: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct CompleteManifest {
    pub schema: String,
    pub source: RecordedJson,
    pub proofs: Vec<RecordedJson>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub baseline_manifest_record: Option<RecordedJson>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub installed_admission: Option<installed::Admission>,
    pub source_root_identity: Identity,
    pub target_kernel_release: String,
    pub packages: Vec<Package>,
    pub entries: Vec<CompleteEntry>,
    pub static_devices: Vec<StaticDevice>,
    pub complete_package_database: bool,
    pub kernel_present: bool,
    pub guest_qualified: bool,
    pub unresolved_requirements: Vec<String>,
}

struct HeldInput {
    pin: EvidencePin,
    parent: File,
    name: String,
    file: File,
    identity: Identity,
}

impl HeldInput {
    fn open(pin: EvidencePin, limit: u64) -> Result<Self> {
        ensure(
            pin.path.is_absolute() && pin.bytes <= limit && fs::valid_digest(&pin.sha256),
            "complete source evidence pin is invalid",
        )?;
        let (parent, name) = fs::absolute_parent(&fs::absolute_string(&pin.path)?)?;
        let file = File::from(rfs::openat(
            &parent,
            name.as_str(),
            OFlags::RDONLY | OFlags::CLOEXEC | OFlags::NOFOLLOW | OFlags::NONBLOCK,
            Mode::empty(),
        )?);
        let identity = fs::stat(&file)?;
        ensure(
            FileType::from_raw_mode(identity.mode) == FileType::RegularFile
                && identity.nlink == 1
                && identity.size == pin.bytes
                && identity.dev == pin.device
                && identity.ino == pin.inode
                && identity.mode & 0o7777 == pin.mode
                && identity.uid == pin.uid
                && identity.gid == pin.gid
                && pin.mode & 0o022 == 0,
            "complete source evidence metadata differs",
        )?;
        let mut held = Self {
            pin,
            parent,
            name,
            file,
            identity,
        };
        held.revalidate()?;
        Ok(held)
    }

    fn from_path(path: &Path, sha: &str) -> Result<Self> {
        let (parent, name) = fs::absolute_parent(&fs::absolute_string(path)?)?;
        let id = fs::identity(&rfs::statat(&parent, name, AtFlags::SYMLINK_NOFOLLOW)?);
        ensure(
            id.uid == 0 && id.gid == 0 && id.mode & 0o077 == 0,
            "complete source receipt must be root-owned and private",
        )?;
        Self::open(
            EvidencePin {
                path: path.to_owned(),
                bytes: id.size,
                sha256: sha.into(),
                device: id.dev,
                inode: id.ino,
                mode: id.mode & 0o7777,
                uid: id.uid,
                gid: id.gid,
            },
            LIMIT,
        )
    }

    fn revalidate(&mut self) -> Result<()> {
        self.file.seek(SeekFrom::Start(0))?;
        ensure(
            fs::stat(&self.file)? == self.identity
                && fs::hash(&self.file)? == self.pin.sha256
                && fs::stat(&self.file)? == self.identity
                && fs::identity(&rfs::statat(
                    &self.parent,
                    self.name.as_str(),
                    AtFlags::SYMLINK_NOFOLLOW,
                )?) == self.identity,
            "complete evidence changed while consumed",
        )?;
        Ok(())
    }

    fn json(&mut self) -> Result<RecordedJson> {
        self.json_with_limit(LIMIT)
    }

    fn json_with_limit(&mut self, limit: u64) -> Result<RecordedJson> {
        ensure(
            self.pin.bytes <= limit,
            "complete JSON evidence exceeds bound",
        )?;
        self.file.seek(SeekFrom::Start(0))?;
        let mut body = String::new();
        Read::by_ref(&mut self.file)
            .take(limit + 1)
            .read_to_string(&mut body)?;
        self.revalidate()?;
        ensure(
            body.len() as u64 == self.pin.bytes && fs::digest(body.as_bytes()) == self.pin.sha256,
            "complete JSON evidence changed",
        )?;
        serde_json::from_str::<Value>(&body)?;
        Ok(RecordedJson {
            pin: self.pin.clone(),
            body,
        })
    }
}

impl RecordedJson {
    fn validate(&self) -> Result<Value> {
        self.validate_with_limit(LIMIT)
    }

    fn validate_with_limit(&self, limit: u64) -> Result<Value> {
        ensure(
            self.body.len() as u64 == self.pin.bytes
                && self.pin.bytes <= limit
                && fs::valid_digest(&self.pin.sha256)
                && fs::digest(self.body.as_bytes()) == self.pin.sha256,
            "embedded source proof digest differs",
        )?;
        Ok(serde_json::from_str(&self.body)?)
    }
}

fn source(document: &RecordedJson) -> Result<SourceReceipt> {
    let result: SourceReceipt = serde_json::from_value(document.validate()?)?;
    ensure(
        result.schema == SOURCE_SCHEMA
            && result.fresh_generated_root
            && !result.private_accounts_copied
            && result.configured,
        "complete source was not freshly and normally configured",
    )?;
    match result.stage.as_str() {
        "baseline" => ensure(
            result.baseline_receipt.is_none()
                && result.baseline_manifest.is_none()
                && result.installed_admission_directory.is_none()
                && result.native_release.is_none()
                && result.native_transaction.is_none(),
            "baseline capture cannot claim installed lineage",
        )?,
        "installed" => installed::source_shape(&result)?,
        _ => return Err("unsupported complete source stage".into()),
    }
    ensure(
        !result.package_transactions.is_empty() && result.package_transactions.len() <= 32,
        "complete source lacks bounded normal package transactions",
    )?;
    ensure(
        result.dpkg_status.path == result.root.path.join("var/lib/dpkg/status")
            && result.dpkg_status.uid == 0
            && result.dpkg_status.gid == 0,
        "complete source status is not its original package database",
    )?;
    Ok(result)
}

fn proof<'a>(proofs: &'a [RecordedJson], pin: &EvidencePin) -> Result<&'a RecordedJson> {
    let matches: Vec<_> = proofs.iter().filter(|p| p.pin == *pin).collect();
    ensure(
        matches.len() == 1,
        "complete source proof missing or duplicated",
    )?;
    Ok(matches[0])
}

fn normalize_package(name: &str, architecture: &str) -> Result<String> {
    let (base, qualifier) = name
        .split_once(':')
        .map_or((name, None), |(a, b)| (a, Some(b)));
    ensure(
        !base.is_empty()
            && base.len() < 256
            && base
                .bytes()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || b"+.-".contains(&c))
            && qualifier.is_none_or(|a| a == architecture)
            && !architecture.is_empty()
            && architecture
                .bytes()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'-'),
        "invalid package identity",
    )?;
    Ok(format!("{base}:{architecture}"))
}

fn package_map(packages: &[Package]) -> Result<BTreeMap<String, String>> {
    ensure(
        !packages.is_empty() && packages.len() <= 8192,
        "complete package roster count invalid",
    )?;
    let mut result = BTreeMap::new();
    for p in packages {
        ensure(
            p.status == "ii "
                && !p.version.is_empty()
                && p.version.len() < 1024
                && !p.version.bytes().any(|c| c.is_ascii_whitespace() || c == 0),
            "complete package is not fully configured",
        )?;
        ensure(
            result
                .insert(
                    normalize_package(&p.package, &p.architecture)?,
                    p.version.clone(),
                )
                .is_none(),
            "duplicate complete package identity",
        )?;
    }
    Ok(result)
}

pub(super) fn status_packages(bytes: &[u8]) -> Result<Vec<Package>> {
    let text = std::str::from_utf8(bytes)?;
    ensure(
        !text.contains('\0') && !text.contains('\r'),
        "invalid dpkg status encoding",
    )?;
    let mut result = Vec::new();
    for paragraph in text.split("\n\n").filter(|p| !p.trim().is_empty()) {
        let mut fields = BTreeMap::new();
        for line in paragraph.lines() {
            if line.starts_with([' ', '\t']) {
                continue;
            }
            let (key, value) = line.split_once(':').ok_or("invalid dpkg status field")?;
            ensure(
                fields.insert(key, value.trim_start()).is_none(),
                "duplicate dpkg status field",
            )?;
        }
        ensure(
            fields.get("Status") == Some(&"install ok installed"),
            "complete database contains an unconfigured or residual package",
        )?;
        result.push(Package {
            package: fields
                .get("Package")
                .ok_or("status package missing")?
                .to_string(),
            version: fields
                .get("Version")
                .ok_or("status version missing")?
                .to_string(),
            architecture: fields
                .get("Architecture")
                .ok_or("status architecture missing")?
                .to_string(),
            status: "ii ".into(),
        });
    }
    package_map(&result)?;
    result.sort_by(|a, b| (&a.package, &a.architecture).cmp(&(&b.package, &b.architecture)));
    Ok(result)
}

fn package_proofs(input: &SourceReceipt, proofs: &[RecordedJson]) -> Result<Vec<Package>> {
    let bootstrap = proof(proofs, &input.bootstrap_receipt)?.validate()?;
    ensure(
        bootstrap["schema"] == "p4-normal-complete-ubuntu-bootstrap-v1"
            && bootstrap["normal_bootstrap_exit_code"] == 0
            && bootstrap["fresh_generated_root"] == true
            && bootstrap["private_accounts_copied"] == false,
        "complete source bootstrap did not complete normally",
    )?;
    let steps = bootstrap["steps"]
        .as_array()
        .ok_or("bootstrap steps missing")?;
    ensure(
        steps.len() == 3
            && steps.iter().all(|v| v["exit_code"] == 0)
            && steps[2]["command"].as_array().is_some_and(|c| {
                c.iter().any(|v| v == "--force-check-sig")
                    && c.iter().any(|v| v.as_str() == input.root.path.to_str())
            }),
        "normal bootstrap signature or original root binding missing",
    )?;
    let mut prior_status = bootstrap["dpkg_status"].clone();
    for pin in &input.package_transactions {
        let transaction = proof(proofs, pin)?.validate()?;
        ensure(
            transaction["schema"] == "p4-complete-ubuntu-normal-package-install-v1"
                && transaction["configured"] == true
                && transaction["root"] == serde_json::to_value(&input.root)?
                && transaction["dpkg_status_before"] == prior_status,
            "normal package transaction root or prior database differs",
        )?;
        for name in ["install", "audit", "query"] {
            let op = &transaction[name];
            ensure(
                op["exit_code"] == 0
                    && op["command"].as_array().is_some_and(|c| {
                        c.first().and_then(Value::as_str) == Some("/usr/bin/chroot")
                            && c.get(1).and_then(Value::as_str) == input.root.path.to_str()
                    }),
                "normal package transaction did not complete in the original root",
            )?;
        }
        ensure(
            transaction["audit"]["stdout"]["bytes"] == 0
                && transaction["audit"]["stderr"]["bytes"] == 0,
            "normal dpkg audit reported an unresolved package",
        )?;
        prior_status = transaction["dpkg_status_after"].clone();
    }
    ensure(
        prior_status == serde_json::to_value(&input.dpkg_status)?,
        "normal package transaction is not the current whole database",
    )?;
    let result: Packages = serde_json::from_value(proof(proofs, &input.packages)?.validate()?)?;
    ensure(
        result.schema == "droidloom.actual-native-package-state.v1"
            && result.configured
            && result.original_requested_count == 971
            && result.original_requested_versions_exact
            && result.packages.len() >= 971,
        "complete original Ubuntu cohort was not normally configured",
    )?;
    package_map(&result.packages)?;
    let last = proof(
        proofs,
        input
            .package_transactions
            .last()
            .ok_or("normal transaction missing")?,
    )?
    .validate()?;
    ensure(
        last["packages"] == serde_json::to_value(&input.packages)?,
        "package roster is not from the final normal query",
    )?;
    Ok(result.packages)
}

fn validate_members(manifest: &CompleteManifest) -> Result<()> {
    ensure(
        !manifest.entries.is_empty()
            && manifest.entries.len() + manifest.static_devices.len()
                <= complete_snapshot::MAX_ENTRIES,
        "complete manifest entry count invalid",
    )?;
    let mut paths_map = BTreeMap::new();
    for entry in &manifest.entries {
        paths::parts(&entry.path)?;
        ensure(
            paths_map.insert(entry.path.as_str(), entry).is_none()
                && fs::content_type_matches(&entry.source, &entry.content),
            "complete manifest path or type invalid",
        )?;
        ensure(
            entry.xattrs.iter().all(|(k, v)| {
                [
                    "security.capability",
                    "system.posix_acl_access",
                    "system.posix_acl_default",
                ]
                .contains(&k.as_str())
                    && v.len() <= 131072
                    && hex::decode(v).is_ok()
            }),
            "complete privilege metadata invalid",
        )?;
        match &entry.content {
            Content::Regular { sha256 } | Content::Hardlink { sha256, .. } => {
                ensure(fs::valid_digest(sha256), "invalid complete digest")?
            }
            Content::Symlink { target } => {
                complete_snapshot::normalize_link(&entry.path, target)?;
            }
            Content::Directory => (),
        }
    }
    for entry in &manifest.entries {
        let parent = paths::parent(&entry.path);
        ensure(
            parent == "/"
                || paths_map
                    .get(parent)
                    .is_some_and(|e| e.content == Content::Directory),
            "complete manifest parent absent or symlink",
        )?;
        if let Content::Hardlink { target, sha256 } = &entry.content {
            let primary = paths_map
                .get(target.as_str())
                .ok_or("complete hardlink target absent")?;
            ensure(
                target < &entry.path
                    && matches!(&primary.content,Content::Regular{sha256:s} if s==sha256)
                    && primary.source == entry.source
                    && primary.xattrs == entry.xattrs,
                "complete hardlink source identity differs",
            )?;
        }
    }
    let mut devices = BTreeSet::new();
    for node in &manifest.static_devices {
        paths::parts(&node.path)?;
        ensure(
            !paths_map.contains_key(node.path.as_str())
                && devices.insert(&node.path)
                && complete_snapshot::device_allowed(&node.path, node.major, node.minor)
                && FileType::from_raw_mode(node.source.mode) == FileType::CharacterDevice
                && node.source.uid == 0
                && node.source.nlink == 1
                && paths_map
                    .get(paths::parent(&node.path))
                    .is_some_and(|e| e.content == Content::Directory),
            "unapproved complete static device",
        )?;
    }
    ensure(
        paths_map
            .get("/var/lib/dpkg/status")
            .is_some_and(|e| matches!(e.content, Content::Regular { .. }))
            && paths_map
                .get("/var/lib/dpkg/info")
                .is_some_and(|e| e.content == Content::Directory)
            && manifest
                .entries
                .iter()
                .any(|e| e.path.starts_with("/var/lib/dpkg/info/"))
            && manifest
                .entries
                .iter()
                .all(|e| !e.path.starts_with("/boot/") && !e.path.starts_with("/usr/lib/modules/")),
        "whole dpkg database absent or unrelated kernel material present",
    )?;
    Ok(())
}

pub(super) fn validate(manifest: &CompleteManifest) -> Result<SourceReceipt> {
    ensure(
        manifest.schema == SCHEMA
            && manifest.complete_package_database
            && !manifest.kernel_present
            && !manifest.guest_qualified
            && manifest.target_kernel_release.starts_with("6.18.")
            && manifest
                .target_kernel_release
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || b"._+-".contains(&c))
            && !manifest.unresolved_requirements.is_empty(),
        "invalid complete manifest authority",
    )?;
    let input = source(&manifest.source)?;
    ensure(
        manifest.source_root_identity.dev == input.root.device
            && manifest.source_root_identity.ino == input.root.inode
            && manifest.source_root_identity.uid == 0
            && manifest.source_root_identity.gid == 0,
        "complete source root identity differs",
    )?;
    let packages = match input.stage.as_str() {
        "baseline" => {
            ensure(
                manifest.baseline_manifest_record.is_none()
                    && manifest.installed_admission.is_none(),
                "baseline cannot embed an installed admission or another baseline",
            )?;
            package_proofs(&input, &manifest.proofs)?
        }
        "installed" => installed::validate(manifest, &input)?,
        _ => return Err("unsupported complete source stage".into()),
    };
    ensure(
        package_map(&packages)? == package_map(&manifest.packages)?,
        "manifest package roster changed",
    )?;
    validate_members(manifest)?;
    let status = manifest
        .entries
        .iter()
        .find(|e| e.path == "/var/lib/dpkg/status")
        .ok_or("status missing")?;
    ensure(
        status.source.dev == input.dpkg_status.device
            && status.source.ino == input.dpkg_status.inode
            && status.source.size == input.dpkg_status.bytes
            && matches!(&status.content,Content::Regular{sha256}if sha256==&input.dpkg_status.sha256),
        "whole database entry differs from source receipt",
    )?;
    Ok(input)
}

pub(super) fn capture(path: &Path, sha: &str, release: &str) -> Result<CompleteManifest> {
    let mut held = Vec::new();
    let mut source_file = HeldInput::from_path(path, sha)?;
    let source_doc = source_file.json()?;
    let input = source(&source_doc)?;
    let tree = Snapshot::open(&input.root.path)?;
    let root = fs::stat(&tree.root)?;
    ensure(
        root.dev == input.root.device && root.ino == input.root.inode,
        "complete source root no longer matches receipt",
    )?;
    let mut proofs = Vec::new();
    for pin in std::iter::once(&input.bootstrap_receipt)
        .chain(input.package_transactions.iter())
        .chain(std::iter::once(&input.packages))
    {
        let mut file = HeldInput::open(pin.clone(), LIMIT)?;
        proofs.push(file.json()?);
        held.push(file);
    }
    let (baseline_manifest_record, installed_admission) = if input.stage == "installed" {
        let (baseline, admission) = installed::capture(&input, release, &mut proofs, &mut held)?;
        (Some(baseline), Some(admission))
    } else {
        (None, None)
    };
    let packages = if input.stage == "baseline" {
        package_proofs(&input, &proofs)?
    } else {
        let roster: Packages =
            serde_json::from_value(proof(&proofs, &input.packages)?.validate()?)?;
        roster.packages
    };
    let status = tree.bytes("/var/lib/dpkg/status", LIMIT)?;
    ensure(
        fs::digest(&status) == input.dpkg_status.sha256
            && status.len() as u64 == input.dpkg_status.bytes
            && package_map(&status_packages(&status)?)? == package_map(&packages)?,
        "whole actual dpkg status differs from normal package query",
    )?;
    let (entries, static_devices) = complete_snapshot::capture(&tree)?;
    let mut result = CompleteManifest {
        schema: SCHEMA.into(),
        source: source_doc,
        proofs,
        baseline_manifest_record,
        installed_admission,
        source_root_identity: root,
        target_kernel_release: release.into(),
        packages,
        entries,
        static_devices,
        complete_package_database: true,
        kernel_present: false,
        guest_qualified: false,
        unresolved_requirements: vec![
            "normal patched native package transaction and complete installed payload admission"
                .into(),
            "separately published shared kernel and matching modules/initrd".into(),
            "fresh qualification identities, normal host/Android admission and actual boot".into(),
            "native, Android and application runtime qualification".into(),
        ],
    };
    if input.stage == "installed" {
        result.unresolved_requirements.remove(0);
    }
    ensure(
        serde_json::to_vec_pretty(&result)?.len() <= 128 * 1024 * 1024,
        "complete manifest exceeds the bounded reader contract",
    )?;
    validate(&result)?;
    ensure(
        fs::stat(&tree.root)? == result.source_root_identity
            && fs::stat(&Snapshot::open(&input.root.path)?.root)? == result.source_root_identity,
        "complete source root changed during capture",
    )?;
    source_file.revalidate()?;
    for file in &mut held {
        file.revalidate()?;
    }
    Ok(result)
}

fn receipt(
    manifest: &CompleteManifest,
    sha: &str,
    path: &Path,
    tree: &Snapshot,
    regular: usize,
    bytes: u64,
) -> Result<Value> {
    ensure(fs::valid_digest(sha), "complete manifest pin invalid")?;
    Ok(
        serde_json::json!({"schema":"droidloom.complete-ubuntu-materialization.v1",
        "manifest_sha256":sha,"destination":path,"destination_identity":fs::stat(&tree.root)?,
        "entries_verified":manifest.entries.len()+manifest.static_devices.len(),
        "regular_paths_verified":regular,"unique_regular_bytes":bytes,
        "complete_package_database":true,"materialization_complete":true,
        "source_stage":source(&manifest.source)?.stage,"kernel_present":false,"guest_qualified":false,
        "unresolved_requirements":manifest.unresolved_requirements}),
    )
}

pub(super) fn verify(manifest: &CompleteManifest, sha: &str, path: &Path) -> Result<Value> {
    validate(manifest)?;
    let tree = Snapshot::open(path)?;
    let (regular, bytes) =
        complete_snapshot::verify(&tree, &manifest.entries, &manifest.static_devices)?;
    let actual = tree.bytes("/var/lib/dpkg/status", LIMIT)?;
    ensure(
        package_map(&status_packages(&actual)?)? == package_map(&manifest.packages)?,
        "copied actual package database differs from complete manifest",
    )?;
    receipt(manifest, sha, path, &tree, regular, bytes)
}

pub(super) fn materialize(manifest: &CompleteManifest, sha: &str, path: &Path) -> Result<Value> {
    let input = validate(manifest)?;
    let original = Snapshot::open(&input.root.path)?;
    ensure(
        fs::stat(&original.root)? == manifest.source_root_identity,
        "complete source root identity changed",
    )?;
    let expected: BTreeMap<_, _> = manifest
        .entries
        .iter()
        .map(|e| (e.path.clone(), e.source.clone()))
        .chain(
            manifest
                .static_devices
                .iter()
                .map(|e| (e.path.clone(), e.source.clone())),
        )
        .collect();
    ensure(
        original.inventory()? == expected,
        "complete source changed after capture",
    )?;
    complete_snapshot::verify(&original, &manifest.entries, &manifest.static_devices)?;
    let copy =
        complete_snapshot::copy(&original, path, &manifest.entries, &manifest.static_devices)?;
    ensure(
        original.inventory()? == expected,
        "complete source changed during materialization",
    )?;
    let (regular, bytes) =
        complete_snapshot::verify(&copy, &manifest.entries, &manifest.static_devices)?;
    receipt(manifest, sha, path, &copy, regular, bytes)
}

#[cfg(test)]
mod complete_tests {
    use super::*;

    #[test]
    fn real_status_requires_every_package_configured_and_matches_architecture() {
        let good=b"Package: liba\nStatus: install ok installed\nArchitecture: amd64\nVersion: 1.0-1\nDescription: public package\n continued text\n\nPackage: data\nStatus: install ok installed\nArchitecture: all\nVersion: 2\n\n";
        let packages = status_packages(good).unwrap();
        assert_eq!(packages.len(), 2);
        assert_eq!(package_map(&packages).unwrap()["liba:amd64"], "1.0-1");
        for bad in [
            String::from_utf8(good.to_vec())
                .unwrap()
                .replace("install ok installed", "deinstall ok config-files"),
            String::from_utf8(good.to_vec())
                .unwrap()
                .replace("Version: 1.0-1", "Version: 1.0-1\nVersion: 1.0-2"),
            String::from_utf8(good.to_vec())
                .unwrap()
                .replace("Package: data", "Package: liba")
                .replace("Architecture: all", "Architecture: amd64"),
        ] {
            assert!(status_packages(bad.as_bytes()).is_err());
        }
        assert!(normalize_package("liba:arm64", "amd64").is_err());
    }

    #[test]
    fn complete_receipt_cannot_claim_installed_from_a_baseline_boolean() {
        let pin = EvidencePin {
            path: "/proof".into(),
            bytes: 1,
            sha256: "a".repeat(64),
            device: 1,
            inode: 2,
            mode: 0o400,
            uid: 0,
            gid: 0,
        };
        let mut value = serde_json::json!({
            "schema":SOURCE_SCHEMA,"stage":"baseline","root":{"path":"/var/lib/droidloom-qualification/test/root","device":1,"inode":2},
            "bootstrap_receipt":pin,"baseline_receipt":null,"package_transactions":[pin],
            "packages":pin,"dpkg_status":{ "path":"/var/lib/droidloom-qualification/test/root/var/lib/dpkg/status", "bytes":1,"sha256":"a".repeat(64),"device":1,"inode":3,"mode":420,"uid":0,"gid":0 },
            "native_release":null,"native_transaction":null,"fresh_generated_root":true,"private_accounts_copied":false,"configured":true
        });
        let document = |v: &Value| {
            let body = serde_json::to_string(v).unwrap();
            RecordedJson {
                pin: EvidencePin {
                    bytes: body.len() as u64,
                    sha256: fs::digest(body.as_bytes()),
                    ..pin.clone()
                },
                body,
            }
        };
        source(&document(&value)).unwrap();
        value["stage"] = "installed".into();
        assert!(source(&document(&value)).is_err());
        value["stage"] = "baseline".into();
        value["private_accounts_copied"] = true.into();
        assert!(source(&document(&value)).is_err());
        let mut bad = document(&value);
        bad.body.push(' ');
        assert!(bad.validate().is_err());
    }
}
