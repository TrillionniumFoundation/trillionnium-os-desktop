//! Preserve the selected official GSI as one complete binary cohort.
//!
//! This path does not consume the CP2A source lock, source-built system files,
//! overlays, a vendor image, or an editable release mapping. The entire official
//! archive and every extracted member must match the compiled reviewed profile.
//! The embedded system, product, system_ext and all APEX containers consequently
//! remain the exact bytes from one official image. A separate vendor still needs
//! actual VINTF, policy, ABI and runtime qualification.

use std::fs::{self, File, Metadata};
use std::io::{BufReader, Read, Seek, SeekFrom, Write};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};
use std::time::{Duration, Instant};

use flate2::bufread::DeflateDecoder;
use rustix::fs::{Mode, OFlags, RenameFlags, open, openat, renameat_with};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::{PrepareError, io_error};

const PROFILE_BODY: &[u8] = include_bytes!("../../../android/manifest/official-gsi-x86_64.json");
const PROFILE_SHA256: &str = "be9e3660c2995d709831e0caf596917944482b2aee04302012be545cd335b8af";
const PREPARE_LIMIT: Duration = Duration::from_secs(180);
const BUFFER: usize = 1024 * 1024;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct BuildIdentity {
    id: String,
    incremental: String,
    release: String,
    sdk: u32,
    sdk_full: String,
    security_patch: String,
    variant: String,
    cpu_abi: String,
    uuid: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct EmbeddedFile {
    path: String,
    bytes: u64,
    sha256: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ArchiveMember {
    name: String,
    output: PathBuf,
    local_header_offset: u64,
    compressed_bytes: u64,
    bytes: u64,
    sha256: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Profile {
    schema: String,
    release_page: String,
    release_date: String,
    archive_url: String,
    archive_bytes: u64,
    archive_sha256: String,
    image_layout: String,
    build_identity: BuildIdentity,
    archive_members: Vec<ArchiveMember>,
    embedded_partitions: Vec<String>,
    apex_containers: Vec<EmbeddedFile>,
    runtime_inputs: Vec<EmbeddedFile>,
    vendor_supplied: bool,
    boot_kernel_supplied: bool,
    source_revision_equivalence_claimed: bool,
    runtime_qualification_claimed: bool,
}

/// Content provenance for prepared official binary inputs.
///
/// This is deliberately a different schema and Rust type from a source-built
/// complete product and the older Cuttlefish PreparedBaseManifest. It is not a
/// production admission or a vendor, source-equivalence, AVB or boot proof.
#[derive(Debug, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PreparedOfficialGsiManifest {
    schema: &'static str,
    profile_sha256: String,
    profile: Profile,
    original_archive: PathBuf,
    original_archive_identity: [u64; 9],
    binary_inputs_verified: bool,
    vendor_compatibility_qualified: bool,
    source_revision_equivalence_qualified: bool,
    avb_signature_qualified: bool,
    runtime_qualified: bool,
    production_ready: bool,
}

impl PreparedOfficialGsiManifest {
    /// Android build ID from the compiled, byte-verified official profile.
    pub fn build_id(&self) -> &str {
        &self.profile.build_identity.id
    }
}

fn rejected(message: impl Into<String>) -> PrepareError {
    PrepareError::Verification(message.into())
}

fn checkpoint(deadline: Instant) -> Result<(), PrepareError> {
    if Instant::now() >= deadline {
        return Err(rejected(
            "official GSI preparation exceeded its original deadline",
        ));
    }
    Ok(())
}

pub(crate) fn identity(metadata: &Metadata) -> Result<[u64; 9], PrepareError> {
    let nanos = |seconds: i64, subsecond: i64| {
        u64::try_from(i128::from(seconds) * 1_000_000_000 + i128::from(subsecond))
            .map_err(|_| rejected("official GSI input has an unsupported timestamp"))
    };
    Ok([
        metadata.dev(),
        metadata.ino(),
        u64::from(metadata.mode()),
        u64::from(metadata.uid()),
        u64::from(metadata.gid()),
        metadata.nlink(),
        metadata.len(),
        nanos(metadata.mtime(), metadata.mtime_nsec())?,
        nanos(metadata.ctime(), metadata.ctime_nsec())?,
    ])
}

fn directory_identity(metadata: &Metadata) -> [u64; 5] {
    [
        metadata.dev(),
        metadata.ino(),
        u64::from(metadata.mode()),
        u64::from(metadata.uid()),
        u64::from(metadata.gid()),
    ]
}

// Traverse from a held root directory, never through a symlink parent or leaf.
pub(crate) fn open_absolute(path: &Path, directory: bool) -> Result<File, PrepareError> {
    let bytes = path.as_os_str().as_bytes();
    if !path.is_absolute()
        || bytes == b"/"
        || bytes[1..]
            .split(|byte| *byte == b'/')
            .any(|part| part.is_empty() || part == b"." || part == b"..")
    {
        return Err(rejected(
            "official GSI paths must be absolute and unaliased",
        ));
    }
    let mut current: File = open(
        "/",
        OFlags::RDONLY | OFlags::DIRECTORY | OFlags::CLOEXEC,
        Mode::empty(),
    )
    .map_err(|error| io_error("open input root", error.into()))?
    .into();
    let components: Vec<_> = path
        .components()
        .filter_map(|part| match part {
            Component::Normal(name) => Some(name),
            _ => None,
        })
        .collect();
    for (index, name) in components.iter().enumerate() {
        let mut flags = OFlags::RDONLY | OFlags::CLOEXEC | OFlags::NOFOLLOW | OFlags::NONBLOCK;
        if directory || index + 1 != components.len() {
            flags |= OFlags::DIRECTORY;
        }
        current = openat(&current, *name, flags, Mode::empty())
            .map_err(|error| io_error("open unaliased official GSI path", error.into()))?
            .into();
    }
    Ok(current)
}

pub(crate) fn require_original(
    file: &File,
    path: &Path,
    expected: &[u64; 9],
) -> Result<(), PrepareError> {
    let reopened = open_absolute(path, false)?;
    if identity(
        &file
            .metadata()
            .map_err(|error| io_error("stat held GSI", error))?,
    )? != *expected
        || identity(
            &reopened
                .metadata()
                .map_err(|error| io_error("stat original GSI path", error))?,
        )? != *expected
    {
        return Err(rejected("official GSI archive changed or was replaced"));
    }
    Ok(())
}

pub(crate) fn hash_file(
    file: &mut File,
    expected_bytes: u64,
    deadline: Instant,
) -> Result<String, PrepareError> {
    file.seek(SeekFrom::Start(0))
        .map_err(|error| io_error("seek held official GSI", error))?;
    let mut hash = Sha256::new();
    let mut bytes = 0u64;
    let mut buffer = vec![0u8; BUFFER];
    loop {
        checkpoint(deadline)?;
        let count = file
            .read(&mut buffer)
            .map_err(|error| io_error("hash held official GSI", error))?;
        if count == 0 {
            break;
        }
        bytes = bytes
            .checked_add(count as u64)
            .ok_or_else(|| rejected("official GSI byte count overflow"))?;
        if bytes > expected_bytes {
            return Err(rejected("official GSI exceeded its exact byte count"));
        }
        hash.update(&buffer[..count]);
    }
    if bytes != expected_bytes {
        return Err(rejected("official GSI is truncated"));
    }
    Ok(hex::encode(hash.finalize()))
}

fn reviewed_profile() -> Result<Profile, PrepareError> {
    if hex::encode(Sha256::digest(PROFILE_BODY)) != PROFILE_SHA256 {
        return Err(rejected(
            "compiled official GSI profile changed without its review pin",
        ));
    }
    let profile: Profile = serde_json::from_slice(PROFILE_BODY)
        .map_err(|error| rejected(format!("invalid official GSI profile: {error}")))?;
    let outputs: Vec<_> = profile
        .archive_members
        .iter()
        .map(|member| (member.name.as_str(), member.output.as_path()))
        .collect();
    if profile.schema != "droidloom-official-gsi-binary-profile-v1"
        || profile.image_layout != "gsi_system_as_root"
        || profile.build_identity.id != "CP3A.260905.010"
        || profile.build_identity.incremental != "16176746"
        || profile.build_identity.variant != "user"
        || profile.build_identity.cpu_abi != "x86_64"
        || profile.vendor_supplied
        || profile.boot_kernel_supplied
        || profile.source_revision_equivalence_claimed
        || profile.runtime_qualification_claimed
        || outputs
            != [
                ("system.img", Path::new("images/system.img")),
                ("vbmeta.img", Path::new("provenance/vbmeta.img")),
                ("build.prop", Path::new("provenance/build.prop")),
            ]
        || profile.apex_containers.len() != 38
    {
        return Err(rejected(
            "official GSI profile changes the reviewed binary-only scope",
        ));
    }
    Ok(profile)
}

fn read_exact(file: &mut File, bytes: &mut [u8]) -> Result<(), PrepareError> {
    file.read_exact(bytes)
        .map_err(|error| io_error("read fixed official ZIP member", error))
}

fn extract_member(
    original: &mut File,
    archive_bytes: u64,
    member: &ArchiveMember,
    stage: &Path,
    deadline: Instant,
) -> Result<(), PrepareError> {
    checkpoint(deadline)?;
    if member.output.is_absolute()
        || member
            .output
            .components()
            .any(|part| !matches!(part, Component::Normal(_)))
        || member.name.as_bytes().len() > 256
        || member.bytes > 3 * 1024 * 1024 * 1024
    {
        return Err(rejected("official ZIP member exceeds its confined profile"));
    }
    original
        .seek(SeekFrom::Start(member.local_header_offset))
        .map_err(|error| io_error("seek official ZIP member", error))?;
    let mut header = [0u8; 30];
    read_exact(original, &mut header)?;
    let number16 = |offset| u16::from_le_bytes([header[offset], header[offset + 1]]);
    let number32 = |offset| {
        u64::from(u32::from_le_bytes([
            header[offset],
            header[offset + 1],
            header[offset + 2],
            header[offset + 3],
        ]))
    };
    let name_bytes = usize::from(number16(26));
    let extra_bytes = u64::from(number16(28));
    let data_offset = member
        .local_header_offset
        .checked_add(30)
        .and_then(|value| value.checked_add(name_bytes as u64))
        .and_then(|value| value.checked_add(extra_bytes))
        .ok_or_else(|| rejected("official ZIP member offset overflow"))?;
    if &header[..4] != b"PK\x03\x04"
        || number16(6) != 0
        || number16(8) != 8
        || number32(18) != member.compressed_bytes
        || number32(22) != member.bytes
        || name_bytes != member.name.len()
        || data_offset
            .checked_add(member.compressed_bytes)
            .is_none_or(|end| end > archive_bytes)
    {
        return Err(rejected(
            "official ZIP header differs from its exact member profile",
        ));
    }
    let mut name = vec![0; name_bytes];
    read_exact(original, &mut name)?;
    if name != member.name.as_bytes() {
        return Err(rejected("official ZIP member name differs"));
    }
    original
        .seek(SeekFrom::Start(data_offset))
        .map_err(|error| io_error("seek official ZIP payload", error))?;
    let path = stage.join(&member.output);
    let mut output = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&path)
        .map_err(|error| io_error("create new official binary member", error))?;
    let reader = BufReader::with_capacity(BUFFER, original.take(member.compressed_bytes));
    let mut decoder = DeflateDecoder::new(reader);
    let mut hash = Sha256::new();
    let mut bytes = 0u64;
    let mut buffer = vec![0; BUFFER];
    loop {
        checkpoint(deadline)?;
        let remaining = member.bytes.saturating_sub(bytes).saturating_add(1);
        let read_limit = usize::try_from(remaining.min(buffer.len() as u64))
            .map_err(|_| rejected("official extraction length overflow"))?;
        let count = decoder
            .read(&mut buffer[..read_limit])
            .map_err(|error| io_error("decode official ZIP member", error))?;
        if count == 0 {
            break;
        }
        bytes += count as u64;
        if bytes > member.bytes {
            return Err(rejected(
                "official ZIP member exceeds its reviewed expanded size",
            ));
        }
        hash.update(&buffer[..count]);
        output
            .write_all(&buffer[..count])
            .map_err(|error| io_error("write official binary member", error))?;
    }
    if bytes != member.bytes
        || decoder.total_in() != member.compressed_bytes
        || hex::encode(hash.finalize()) != member.sha256
    {
        return Err(rejected(
            "official ZIP member size, stream or SHA256 differs",
        ));
    }
    output
        .set_permissions(fs::Permissions::from_mode(0o444))
        .map_err(|error| io_error("make official binary member read-only", error))?;
    output
        .sync_all()
        .map_err(|error| io_error("sync official binary member", error))?;
    Ok(())
}

/// Prepare the fixed official CP3A GSI without rebuilding or modifying Android.
///
/// Only a whole-archive match is decoded. Output contains the unchanged
/// images/system.img and two original reference files; it contains no vendor,
/// boot image, replacement framework/APEX, or source-equivalence assertion.
/// Parents and input must be ordinary unaliased paths, the input must have one
/// hard link, and an existing output is never replaced. No image is mounted.
///
/// # Errors
///
/// Rejects mismatched or changed inputs, aliases, malformed ZIP members, expired
/// preparation, unsupported atomic no-replace publication, or an existing output.
pub fn prepare_official_gsi(
    archive: &Path,
    output: &Path,
) -> Result<PreparedOfficialGsiManifest, PrepareError> {
    let profile = reviewed_profile()?;
    prepare_with_profile(archive, output, &profile, PROFILE_SHA256)
}

fn prepare_with_profile(
    archive: &Path,
    output: &Path,
    profile: &Profile,
    profile_sha256: &str,
) -> Result<PreparedOfficialGsiManifest, PrepareError> {
    let deadline = Instant::now() + PREPARE_LIMIT;
    let parent_path = output
        .parent()
        .ok_or_else(|| rejected("official GSI output requires an absolute parent"))?;
    let parent = open_absolute(parent_path, true)?;
    let parent_id = directory_identity(
        &parent
            .metadata()
            .map_err(|error| io_error("stat output parent", error))?,
    );
    let output_name = output
        .file_name()
        .ok_or_else(|| rejected("official GSI output requires one new leaf"))?;
    // Validate the complete lexical spelling as well as the held parent.
    if !output.is_absolute()
        || output
            .as_os_str()
            .as_bytes()
            .split(|byte| *byte == b'/')
            .skip(1)
            .any(|part| part.is_empty() || part == b"." || part == b"..")
    {
        return Err(rejected(
            "official GSI output must be absolute and unaliased",
        ));
    }
    match fs::symlink_metadata(output) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
        Err(error) => return Err(io_error("inspect official GSI output", error)),
        Ok(_) => return Err(rejected("official GSI output already exists")),
    }
    let mut original = open_absolute(archive, false)?;
    let metadata = original
        .metadata()
        .map_err(|error| io_error("stat official GSI archive", error))?;
    if !metadata.is_file() || metadata.nlink() != 1 || metadata.len() != profile.archive_bytes {
        return Err(rejected(
            "official GSI input must be the exact single-link archive",
        ));
    }
    let original_id = identity(&metadata)?;
    if hash_file(&mut original, profile.archive_bytes, deadline)? != profile.archive_sha256 {
        return Err(rejected(
            "official GSI archive SHA256 differs from its reviewed release",
        ));
    }
    require_original(&original, archive, &original_id)?;
    let stage = tempfile::Builder::new()
        .prefix(".official-gsi-")
        .tempdir_in(parent_path)
        .map_err(|error| io_error("create private official GSI staging", error))?;
    let stage_name = stage
        .path()
        .file_name()
        .ok_or_else(|| rejected("staging leaf missing"))?;
    let stage_fd = open_absolute(stage.path(), true)?;
    let stage_id = directory_identity(
        &stage_fd
            .metadata()
            .map_err(|error| io_error("stat official GSI staging", error))?,
    );
    for directory in ["images", "provenance"] {
        fs::create_dir(stage.path().join(directory))
            .map_err(|error| io_error("create official GSI member directory", error))?;
    }
    for member in &profile.archive_members {
        extract_member(
            &mut original,
            profile.archive_bytes,
            member,
            stage.path(),
            deadline,
        )?;
    }
    require_original(&original, archive, &original_id)?;
    if hash_file(&mut original, profile.archive_bytes, deadline)? != profile.archive_sha256 {
        return Err(rejected("official GSI archive changed during preparation"));
    }
    require_original(&original, archive, &original_id)?;
    let manifest = PreparedOfficialGsiManifest {
        schema: "droidloom-prepared-official-gsi-binary-v1",
        profile_sha256: profile_sha256.to_owned(),
        profile: profile.clone(),
        original_archive: archive.to_owned(),
        original_archive_identity: original_id,
        binary_inputs_verified: true,
        vendor_compatibility_qualified: false,
        source_revision_equivalence_qualified: false,
        avb_signature_qualified: false,
        runtime_qualified: false,
        production_ready: false,
    };
    let mut manifest_file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(stage.path().join("official-gsi-manifest.json"))
        .map_err(|error| io_error("create official GSI manifest", error))?;
    serde_json::to_writer_pretty(&mut manifest_file, &manifest)
        .map_err(|error| rejected(format!("serialize official GSI manifest: {error}")))?;
    manifest_file
        .write_all(b"\n")
        .map_err(|error| io_error("finish GSI manifest", error))?;
    manifest_file
        .set_permissions(fs::Permissions::from_mode(0o444))
        .map_err(|error| io_error("make official GSI manifest read-only", error))?;
    manifest_file
        .sync_all()
        .map_err(|error| io_error("sync GSI manifest", error))?;
    for directory in ["images", "provenance"] {
        open_absolute(&stage.path().join(directory), true)?
            .sync_all()
            .map_err(|error| io_error("sync GSI member directory", error))?;
    }
    stage_fd
        .sync_all()
        .map_err(|error| io_error("sync GSI staging", error))?;
    checkpoint(deadline)?;
    if directory_identity(
        &open_absolute(parent_path, true)?
            .metadata()
            .map_err(|error| io_error("recheck official GSI parent", error))?,
    ) != parent_id
        || directory_identity(
            &open_absolute(stage.path(), true)?
                .metadata()
                .map_err(|error| io_error("recheck official GSI staging", error))?,
        ) != stage_id
    {
        return Err(rejected(
            "official GSI output parent or staging directory changed",
        ));
    }
    // Same held parent and kernel-enforced NOREPLACE: a concurrent new output,
    // including an empty directory or symlink, cannot be overwritten.
    renameat_with(
        &parent,
        stage_name,
        &parent,
        output_name,
        RenameFlags::NOREPLACE,
    )
    .map_err(|error| io_error("publish official GSI without replacement", error.into()))?;
    let _old_staging_name = stage.keep();
    parent
        .sync_all()
        .map_err(|error| io_error("sync published GSI parent", error))?;
    Ok(manifest)
}

#[cfg(test)]
mod tests;
