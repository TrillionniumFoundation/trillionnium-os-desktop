//! Read-only extraction of the reviewed CP3A vendor build references.
//!
//! These files are never installed as replacement system or APEX libraries.
//! The official system and the independent vendor source retain different
//! provenance. Matching ELF bytes supplies a link reference, not ABI, signing,
//! SELinux, VINTF or runtime qualification.
use crate::official_gsi::{hash_file, identity, open_absolute, require_original};
use rustix::fs::{RenameFlags, renameat_with};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File};
use std::io::{Read, Seek, SeekFrom, Write};
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
const PROFILE: &[u8] = include_bytes!("../../../android/manifest/official-gsi-vendor-inputs.json");
/// SHA256 of the compiled binary-interface profile.
pub const PROFILE_SHA256: &str = "df24a620ef4db0fd10d735b5cb75bdfc59da8c3a08c4ab7185c37a5a2ee90eb9";
/// SHA256 of the complete unchanged official CP3A system image.
pub const SYSTEM_SHA256: &str = "dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4";
/// Exact complete official system image size.
pub const SYSTEM_BYTES: u64 = 2_294_853_632;
const LIMIT: Duration = Duration::from_secs(180);

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Exact {
    bytes: u64,
    sha256: String,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Container {
    path: String,
    bytes: u64,
    sha256: String,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Apex {
    name: String,
    container: Container,
    original_apex: Exact,
    payload: Exact,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Origin {
    apex: Option<String>,
    path: String,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Input {
    name: String,
    origin: Origin,
    bytes: u64,
    sha256: String,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Profile {
    schema: String,
    release_build_id: String,
    system_bytes: u64,
    system_sha256: String,
    apexes: Vec<Apex>,
    files: Vec<Input>,
    source_revision_equivalence_claimed: bool,
    abi_qualification_claimed: bool,
}

/// Extraction evidence. Every qualification beyond input identity stays false.
#[derive(Debug, Serialize)]
pub struct InputReceipt {
    schema: &'static str,
    profile_sha256: &'static str,
    source_system: PathBuf,
    source_system_f9: [u64; 9],
    source_system_sha256: &'static str,
    files: BTreeMap<String, FileIdentity>,
    official_system_bytes_preserved: bool,
    source_revision_equivalence_qualified: bool,
    abi_qualified: bool,
    runtime_qualified: bool,
    production_ready: bool,
}
impl InputReceipt {
    /// Number of independently byte-verified reference files.
    pub fn file_count(&self) -> usize {
        self.files.len()
    }
}
#[derive(Clone, Debug, Serialize)]
struct FileIdentity {
    bytes: u64,
    sha256: String,
    f9: [u64; 9],
}

fn require(value: bool, message: &str) -> Result<()> {
    if value { Ok(()) } else { Err(message.into()) }
}
fn profile() -> Result<Profile> {
    require(
        format!("{:x}", Sha256::digest(PROFILE)) == PROFILE_SHA256,
        "official vendor input profile changed without review",
    )?;
    let p: Profile = serde_json::from_slice(PROFILE)?;
    require(
        p.schema == "droidloom-official-cp3a-vendor-input-profile-v1"
            && p.release_build_id == "CP3A.260905.010"
            && p.system_bytes == SYSTEM_BYTES
            && p.system_sha256 == SYSTEM_SHA256
            && !p.source_revision_equivalence_claimed
            && !p.abi_qualification_claimed
            && p.files.len() == 29
            && p.apexes.len() == 3,
        "official vendor inputs changed their exact binary-only scope",
    )?;
    let mut names = BTreeSet::new();
    for input in &p.files {
        require(
            input.name.len() < 100
                && Path::new(&input.name).components().count() == 1
                && input
                    .name
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"-_.+".contains(&b))
                && names.insert(input.name.clone())
                && input.bytes > 0
                && input.bytes <= 64 * 1024 * 1024,
            "invalid or duplicate fixed vendor input name",
        )?;
    }
    Ok(p)
}

#[derive(Debug)]
struct Held {
    file: File,
    path: PathBuf,
    id: FileIdentity,
}
impl Held {
    fn open(path: &Path, bytes: u64, sha: &str, deadline: Instant) -> Result<Self> {
        let mut file = open_absolute(path, false)?;
        let m = file.metadata()?;
        require(
            m.is_file() && m.nlink() == 1 && m.len() == bytes,
            "official vendor input is not its exact single-link ordinary file",
        )?;
        let f9 = identity(&m)?;
        require(
            hash_file(&mut file, bytes, deadline)? == sha,
            "official vendor input SHA256 mismatch",
        )?;
        require_original(&file, path, &f9)?;
        Ok(Self {
            file,
            path: path.to_owned(),
            id: FileIdentity {
                bytes,
                sha256: sha.into(),
                f9,
            },
        })
    }
    fn verify(&self) -> Result<()> {
        require_original(&self.file, &self.path, &self.id.f9)?;
        Ok(())
    }
    fn copy(&self, output: &Path) -> Result<()> {
        self.verify()?;
        let mut source = self.file.try_clone()?;
        source.seek(SeekFrom::Start(0))?;
        let mut destination = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(output)?;
        require(
            std::io::copy(&mut source.take(self.id.bytes + 1), &mut destination)? == self.id.bytes,
            "official vendor input changed while copied",
        )?;
        destination.sync_all()?;
        fs::set_permissions(output, fs::Permissions::from_mode(0o644))?;
        let copied = Held::open(
            output,
            self.id.bytes,
            &self.id.sha256,
            Instant::now() + LIMIT,
        )?;
        copied.verify()?;
        self.verify()
    }
}

/// A held byte-verified system plus every reviewed link reference. The fields
/// are private so a manifest or caller declaration cannot mint this state.
#[derive(Debug)]
pub struct VerifiedVendorInputs {
    system: Held,
    inputs: BTreeMap<String, Held>,
}
impl VerifiedVendorInputs {
    /// Revalidate all held file identities before another build phase.
    pub fn verify_unchanged(&self) -> Result<()> {
        self.system.verify()?;
        for input in self.inputs.values() {
            input.verify()?;
        }
        Ok(())
    }
    /// Copy one fixed reference to a new file and recheck its bytes.
    pub fn copy_reference(&self, name: &str, destination: &Path) -> Result<()> {
        self.inputs
            .get(name)
            .ok_or("unreviewed official vendor reference")?
            .copy(destination)
    }
    /// Return one held reference path after an identity check.
    pub fn reference_path(&self, name: &str) -> Result<&Path> {
        let held = self
            .inputs
            .get(name)
            .ok_or("unreviewed official vendor reference")?;
        held.verify()?;
        Ok(&held.path)
    }
    /// Describe the observed inputs without granting compatibility credit.
    pub fn receipt(&self) -> Result<InputReceipt> {
        self.verify_unchanged()?;
        Ok(InputReceipt {
            schema: "droidloom-official-cp3a-vendor-inputs-v1",
            profile_sha256: PROFILE_SHA256,
            source_system: self.system.path.clone(),
            source_system_f9: self.system.id.f9,
            source_system_sha256: SYSTEM_SHA256,
            files: self
                .inputs
                .iter()
                .map(|(name, held)| (name.clone(), held.id.clone()))
                .collect(),
            official_system_bytes_preserved: true,
            source_revision_equivalence_qualified: false,
            abi_qualified: false,
            runtime_qualified: false,
            production_ready: false,
        })
    }
}

/// Verify the original complete system and all 29 exact references, holding their files.
pub fn verify_vendor_inputs(
    system_image: &Path,
    references: &Path,
) -> Result<VerifiedVendorInputs> {
    verify_vendor_inputs_until(system_image, references, Instant::now() + LIMIT)
}
fn verify_vendor_inputs_until(
    system_image: &Path,
    references: &Path,
    deadline: Instant,
) -> Result<VerifiedVendorInputs> {
    let p = profile()?;
    let system = Held::open(system_image, p.system_bytes, &p.system_sha256, deadline)?;
    let mut inputs = BTreeMap::new();
    for input in &p.files {
        let held = Held::open(
            &references.join(&input.name),
            input.bytes,
            &input.sha256,
            deadline,
        )?;
        if input.name.ends_with(".so") {
            let mut h = [0u8; 20];
            let mut file = held.file.try_clone()?;
            file.seek(SeekFrom::Start(0))?;
            file.read_exact(&mut h)?;
            require(
                &h[..6] == b"\x7fELF\x02\x01" && u16::from_le_bytes([h[18], h[19]]) == 62,
                "official host reference must be x86_64 ELF64",
            )?;
        }
        inputs.insert(input.name.clone(), held);
    }
    let result = VerifiedVendorInputs { system, inputs };
    result.verify_unchanged()?;
    Ok(result)
}

fn extract(
    command: &mut Command,
    output: &Path,
    bytes: u64,
    sha: &str,
    deadline: Instant,
) -> Result<()> {
    let file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(output)?;
    let stderr = PathBuf::from(format!("{}.extract-stderr", output.display()));
    let error_file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&stderr)?;
    let mut child = command
        .stdin(Stdio::null())
        .stdout(Stdio::from(file))
        .stderr(Stdio::from(error_file))
        .spawn()?;
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if Instant::now() >= deadline
            || fs::metadata(output)?.len() > bytes
            || fs::metadata(&stderr)?.len() > 1024 * 1024
        {
            child.kill()?;
            child.wait()?;
            return Err("official input extraction exceeded fixed size or deadline".into());
        }
        std::thread::sleep(Duration::from_millis(10));
    };
    require(
        status.success(),
        "read-only official input extractor failed",
    )?;
    Held::open(output, bytes, sha, deadline)?;
    fs::set_permissions(output, fs::Permissions::from_mode(0o644))?;
    Ok(())
}

/// Extract exact members with read-only debugfs/unzip. Every outer CAPEX,
/// original APEX, payload and final file must match its compiled identity.
pub fn prepare_official_vendor_inputs(system_image: &Path, output: &Path) -> Result<InputReceipt> {
    let p = profile()?;
    let deadline = Instant::now() + LIMIT;
    require(
        output.is_absolute()
            && !output
                .components()
                .any(|c| matches!(c, Component::CurDir | Component::ParentDir))
            && output.to_str().is_some_and(|s| {
                s.split('/')
                    .skip(1)
                    .all(|p| !p.is_empty() && p != "." && p != "..")
            }),
        "new absolute unaliased input output required",
    )?;
    let parent_path = output.parent().ok_or("output parent missing")?;
    let parent = open_absolute(parent_path, true)?;
    let parent_id = identity(&parent.metadata()?)?;
    match fs::symlink_metadata(output) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
        _ => return Err("official input output already exists or is not accessible".into()),
    }
    let system = Held::open(system_image, p.system_bytes, &p.system_sha256, deadline)?;
    let stage = tempfile::Builder::new()
        .prefix(".cp3a-vendor-inputs-")
        .tempdir_in(parent_path)?;
    let scratch = stage.path().join("extraction");
    fs::create_dir(&scratch)?;
    let mut payloads = BTreeMap::new();
    for apex in &p.apexes {
        let container = scratch.join(format!("{}.container", apex.name));
        extract(
            Command::new("debugfs")
                .args(["-R", &format!("cat {}", apex.container.path)])
                .arg(system_image),
            &container,
            apex.container.bytes,
            &apex.container.sha256,
            deadline,
        )?;
        let original = if apex.container.path.ends_with(".capex") {
            let original = scratch.join(format!("{}.apex", apex.name));
            extract(
                Command::new("unzip")
                    .arg("-p")
                    .arg(&container)
                    .arg("original_apex"),
                &original,
                apex.original_apex.bytes,
                &apex.original_apex.sha256,
                deadline,
            )?;
            original
        } else {
            Held::open(
                &container,
                apex.original_apex.bytes,
                &apex.original_apex.sha256,
                deadline,
            )?;
            container
        };
        let payload = scratch.join(format!("{}.payload", apex.name));
        extract(
            Command::new("unzip")
                .arg("-p")
                .arg(original)
                .arg("apex_payload.img"),
            &payload,
            apex.payload.bytes,
            &apex.payload.sha256,
            deadline,
        )?;
        payloads.insert(apex.name.clone(), payload);
    }
    for input in &p.files {
        let image = match &input.origin.apex {
            Some(name) => payloads
                .get(name)
                .ok_or("fixed input APEX payload missing")?
                .as_path(),
            None => system_image,
        };
        extract(
            Command::new("debugfs")
                .args(["-R", &format!("cat {}", input.origin.path)])
                .arg(image),
            &stage.path().join(&input.name),
            input.bytes,
            &input.sha256,
            deadline,
        )?;
    }
    system.verify()?;
    let mut system_copy = system.file.try_clone()?;
    require(
        hash_file(&mut system_copy, p.system_bytes, deadline)? == p.system_sha256,
        "official system changed during read-only vendor input extraction",
    )?;
    system.verify()?;
    // Containers and tools' stderr are process artifacts, not exported build references.
    fs::remove_dir_all(scratch)?;
    for input in &p.files {
        fs::remove_file(stage.path().join(format!("{}.extract-stderr", input.name)))?;
    }
    let checked = verify_vendor_inputs_until(system_image, stage.path(), deadline)?;
    let receipt = checked.receipt()?;
    let mut record = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(stage.path().join("official-vendor-inputs.json"))?;
    serde_json::to_writer_pretty(&mut record, &receipt)?;
    record.write_all(b"\n")?;
    record.sync_all()?;
    // Creation changes the directory mtime; retain its actual identity and ownership.
    let reopened = open_absolute(parent_path, true)?;
    let after = identity(&reopened.metadata()?)?;
    require(
        parent_id[..5] == after[..5],
        "official input output parent was replaced",
    )?;
    require(
        Instant::now() < deadline,
        "official input preparation deadline expired",
    )?;
    renameat_with(
        &parent,
        stage.path().file_name().ok_or("stage name")?,
        &parent,
        output.file_name().ok_or("output name")?,
        RenameFlags::NOREPLACE,
    )?;
    let _ = stage.keep();
    Ok(receipt)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;

    #[test]
    fn profile_binds_capex_to_actual_apex_payloads_and_no_qualification() {
        let p = profile().unwrap();
        assert_eq!(
            p.apexes.iter().map(|a| a.name.as_str()).collect::<Vec<_>>(),
            [
                "com.android.art",
                "com.android.neuralnetworks",
                "com.android.runtime"
            ]
        );
        assert!(p.apexes[0].container.path.ends_with(".capex"));
        assert_ne!(
            p.apexes[0].container.sha256,
            p.apexes[0].original_apex.sha256
        );
        assert_eq!(
            p.apexes[2].container.sha256,
            p.apexes[2].original_apex.sha256
        );
        assert_eq!(
            p.files.iter().filter(|f| f.name.ends_with(".so")).count(),
            28
        );
    }
    #[test]
    fn held_rejects_changed_content_hardlinks_and_parent_alias() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("input");
        fs::write(&path, b"exact input").unwrap();
        let sha = format!("{:x}", Sha256::digest(b"exact input"));
        let held = Held::open(&path, 11, &sha, Instant::now() + LIMIT).unwrap();
        fs::write(&path, b"wrong input").unwrap();
        assert!(held.verify().is_err());
        assert!(Held::open(&path, 11, &sha, Instant::now() + LIMIT).is_err());
        fs::write(&path, b"exact input").unwrap();
        fs::hard_link(&path, dir.path().join("hardlink")).unwrap();
        assert!(Held::open(&path, 11, &sha, Instant::now() + LIMIT).is_err());
        fs::remove_file(dir.path().join("hardlink")).unwrap();
        symlink(dir.path(), dir.path().join("alias")).unwrap();
        assert!(
            Held::open(
                &dir.path().join("alias/input"),
                11,
                &sha,
                Instant::now() + LIMIT
            )
            .is_err()
        );
    }
    #[test]
    fn held_copy_requires_new_output_and_preserves_bytes() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("input");
        fs::write(&path, b"exact input").unwrap();
        let sha = format!("{:x}", Sha256::digest(b"exact input"));
        let held = Held::open(&path, 11, &sha, Instant::now() + LIMIT).unwrap();
        let dest = dir.path().join("copy");
        held.copy(&dest).unwrap();
        assert_eq!(fs::read(&dest).unwrap(), b"exact input");
        assert!(held.copy(&dest).is_err());
    }
}
