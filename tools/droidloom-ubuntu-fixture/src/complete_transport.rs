//! A closed complete-root transport: one fixed header followed only by the
//! regular-file bytes in the already admitted manifest order. Paths, links,
//! devices and privilege metadata never come from the payload stream.
use crate::boot_files::{self, FilePin};
use crate::complete_native::{self, CompleteManifest};
use crate::complete_snapshot::{self, Snapshot};
use crate::model::{Content, Identity};
use crate::{Result, ensure, fs};
use rustix::fs::{self as rfs, AtFlags, FileType, Mode, OFlags};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::Path;

const MAGIC: &[u8; 8] = b"DLCNAT01";
const HEADER: usize = 56;
const MAX_BYTES: u64 = 64 * 1024 * 1024 * 1024;

fn header(manifest_sha: &str, count: u64, bytes: u64) -> Result<[u8; HEADER]> {
    ensure(
        fs::valid_digest(manifest_sha)
            && count > 0
            && count <= 500000
            && bytes > 0
            && bytes <= MAX_BYTES,
        "complete transport layout exceeds its fixed bound",
    )?;
    let mut value = [0u8; HEADER];
    value[..8].copy_from_slice(MAGIC);
    value[8..40].copy_from_slice(&hex::decode(manifest_sha)?);
    value[40..48].copy_from_slice(&count.to_be_bytes());
    value[48..56].copy_from_slice(&bytes.to_be_bytes());
    Ok(value)
}
fn layout(manifest: &CompleteManifest, sha: &str) -> Result<([u8; HEADER], u64, u64)> {
    let mut count = 0u64;
    let mut bytes = 0u64;
    for entry in &manifest.entries {
        if matches!(entry.content, Content::Regular { .. }) {
            count = count
                .checked_add(1)
                .ok_or("transport file count overflow")?;
            bytes = bytes
                .checked_add(entry.source.size)
                .ok_or("transport size overflow")?;
        }
    }
    Ok((header(sha, count, bytes)?, count, bytes))
}
fn check_header(actual: &[u8], expected: &[u8; HEADER]) -> Result<()> {
    ensure(
        actual == expected,
        "complete payload header is not the admitted manifest and exact layout",
    )
}
fn manifest(pin: &FilePin) -> Result<CompleteManifest> {
    let value: CompleteManifest =
        serde_json::from_slice(&boot_files::read_pin(pin, 128 * 1024 * 1024)?)?;
    let source = complete_native::validate(&value)?;
    ensure(
        source.stage == "installed",
        "complete transport requires the successful normal native transaction",
    )?;
    Ok(value)
}
fn original_inventory(manifest: &CompleteManifest) -> BTreeMap<String, Identity> {
    manifest
        .entries
        .iter()
        .map(|e| (e.path.clone(), e.source.clone()))
        .chain(
            manifest
                .static_devices
                .iter()
                .map(|e| (e.path.clone(), e.source.clone())),
        )
        .collect()
}

struct Payload {
    pin: FilePin,
    parent: File,
    name: String,
    file: File,
    identity: Identity,
}
impl Payload {
    fn open(pin: &FilePin) -> Result<Self> {
        ensure(
            pin.bytes > HEADER as u64
                && pin.bytes <= MAX_BYTES + HEADER as u64
                && fs::valid_digest(&pin.sha256),
            "complete transport pin is invalid",
        )?;
        let (parent, name) = fs::absolute_parent(&fs::absolute_string(&pin.path)?)?;
        let file = File::from(rfs::openat(
            &parent,
            name.as_str(),
            OFlags::RDONLY | OFlags::CLOEXEC | OFlags::NOFOLLOW | OFlags::NONBLOCK,
            Mode::empty(),
        )?);
        let id = fs::stat(&file)?;
        ensure(
            FileType::from_raw_mode(id.mode) == FileType::RegularFile
                && id.nlink == 1
                && id.uid == 0
                && id.gid == 0
                && [0o400, 0o444].contains(&(id.mode & 0o7777))
                && id.size == pin.bytes,
            "complete payload is not an independent protected readonly regular file",
        )?;
        let mut result = Self {
            pin: pin.clone(),
            parent,
            name,
            file,
            identity: id,
        };
        result.revalidate()?;
        Ok(result)
    }
    fn revalidate(&mut self) -> Result<()> {
        self.file.rewind()?;
        ensure(
            fs::stat(&self.file)? == self.identity
                && fs::hash(&self.file)? == self.pin.sha256
                && fs::stat(&self.file)? == self.identity
                && fs::identity(&rfs::statat(
                    &self.parent,
                    self.name.as_str(),
                    AtFlags::SYMLINK_NOFOLLOW,
                )?) == self.identity,
            "complete payload changed while held",
        )?;
        self.file.rewind()?;
        Ok(())
    }
}

pub(super) fn export(path: &Path, expected_sha: &str, output: &Path) -> Result<Value> {
    let pin = boot_files::pin_file(path)?;
    ensure(
        pin.sha256 == expected_sha,
        "complete source manifest pin differs",
    )?;
    let input = manifest(&pin)?;
    let authority = complete_native::validate(&input)?;
    let source = Snapshot::open(&authority.root.path)?;
    let expected = original_inventory(&input);
    ensure(
        fs::stat(&source.root)? == input.source_root_identity && source.inventory()? == expected,
        "complete source no longer has its original capture identities",
    )?;
    complete_snapshot::verify(&source, &input.entries, &input.static_devices)?;
    let (frame, count, bytes) = layout(&input, expected_sha)?;
    ensure(
        output.file_name().and_then(|s| s.to_str()) == Some("NATIVE-PAYLOAD.bin")
            && output.parent().and_then(Path::parent)
                == Some(Path::new("/var/lib/droidloom-qualification")),
        "complete payload must have its fixed name inside a private qualification directory",
    )?;
    let (parent, name) = fs::absolute_parent(&fs::absolute_string(output)?)?;
    let parent_id = fs::stat(&parent)?;
    ensure(
        parent_id.uid == 0 && parent_id.gid == 0 && parent_id.mode & 0o7777 == 0o700,
        "complete payload output parent is not private",
    )?;
    let mut file = File::from(rfs::openat(
        &parent,
        name.as_str(),
        OFlags::RDWR | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::from_raw_mode(0o600),
    )?);
    file.write_all(&frame)?;
    let mut whole = Sha256::new();
    whole.update(frame);
    let mut buffer = vec![0u8; 1024 * 1024];
    let mut copied_total = 0u64;
    for entry in &input.entries {
        let Content::Regular { sha256 } = &entry.content else {
            continue;
        };
        let mut original = source.file(&entry.path)?;
        ensure(
            fs::stat(&original)? == entry.source && fs::xattrs(&original)? == entry.xattrs,
            "complete original file changed before export",
        )?;
        let mut digest = Sha256::new();
        let mut copied = 0u64;
        loop {
            let n = original.read(&mut buffer)?;
            if n == 0 {
                break;
            }
            copied = copied
                .checked_add(n as u64)
                .ok_or("complete original file overflow")?;
            ensure(
                copied <= entry.source.size,
                "complete original file grew during export",
            )?;
            file.write_all(&buffer[..n])?;
            digest.update(&buffer[..n]);
            whole.update(&buffer[..n]);
        }
        ensure(
            copied == entry.source.size
                && hex::encode(digest.finalize()) == *sha256
                && fs::stat(&original)? == entry.source
                && source.identity(&entry.path)? == entry.source,
            "complete original file changed during export",
        )?;
        copied_total = copied_total
            .checked_add(copied)
            .ok_or("complete export size overflow")?;
    }
    ensure(
        copied_total == bytes
            && source.inventory()? == expected
            && fs::stat(&source.root)? == input.source_root_identity
            && fs::stat(&Snapshot::open(&authority.root.path)?.root)? == input.source_root_identity,
        "complete original root changed during export",
    )?;
    file.flush()?;
    file.sync_all()?;
    rfs::fchmod(&file, Mode::from_raw_mode(0o400))?;
    let id = fs::stat(&file)?;
    ensure(
        id.nlink == 1 && id.uid == 0 && id.gid == 0 && id.size == bytes + HEADER as u64,
        "complete transport output identity differs",
    )?;
    let sha = hex::encode(whole.finalize());
    file.rewind()?;
    ensure(
        fs::hash(&file)? == sha
            && fs::stat(&file)? == id
            && fs::identity(&rfs::statat(
                &parent,
                name.as_str(),
                AtFlags::SYMLINK_NOFOLLOW,
            )?) == id,
        "complete transport full output readback differs",
    )?;
    let payload = FilePin {
        path: output.to_path_buf(),
        bytes: id.size,
        sha256: sha,
    };
    Ok(
        json!({"schema":"droidloom.complete-native-transport.v1","manifest":pin,
        "original_root":authority.root,"original_root_identity":input.source_root_identity,
        "payload":payload,"regular_files":count,"unique_regular_bytes":bytes,
        "source_unchanged":true,"complete_package_database":true,
        "guest_qualified":false,"production_ready":false}),
    )
}

pub(super) fn materialize(
    input: &CompleteManifest,
    manifest_sha: &str,
    pin: &FilePin,
    destination: &Path,
) -> Result<Value> {
    let authority = complete_native::validate(input)?;
    ensure(
        authority.stage == "installed",
        "complete payload is not an installed source",
    )?;
    let (frame, count, bytes) = layout(input, manifest_sha)?;
    ensure(
        pin.bytes == bytes + HEADER as u64,
        "complete payload length differs from the whole manifest",
    )?;
    let mut payload = Payload::open(pin)?;
    let mut observed = [0u8; HEADER];
    payload.file.read_exact(&mut observed)?;
    check_header(&observed, &frame)?;
    let output = complete_snapshot::copy_payload(
        &mut payload.file,
        destination,
        &input.entries,
        &input.static_devices,
    )?;
    let mut extra = [0u8; 1];
    ensure(
        payload.file.read(&mut extra)? == 0 && payload.file.stream_position()? == pin.bytes,
        "complete payload has missing or trailing bytes",
    )?;
    payload.revalidate()?;
    let (regular, verified_bytes) =
        complete_snapshot::verify(&output, &input.entries, &input.static_devices)?;
    ensure(
        verified_bytes == bytes && regular as u64 >= count,
        "complete transported root readback differs",
    )?;
    payload.revalidate()?;
    let mut receipt =
        complete_native::receipt(input, manifest_sha, destination, &output, regular, bytes)?;
    receipt["transport"] = json!({"schema":"droidloom.complete-native-transport.v1",
        "source_manifest_sha256":manifest_sha,"original_root":authority.root,
        "original_root_identity":input.source_root_identity,"payload":pin,
        "held_payload_identity":payload.identity,"whole_payload_verified":true,
        "destination_has_new_local_inodes":true});
    Ok(receipt)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn payload_header_binds_digest_count_size_and_rejects_truncation() {
        let good = header(&"a".repeat(64), 3, 1234).unwrap();
        check_header(&good, &good).unwrap();
        for index in [0, 8, 39, 40, 47, 48, 55] {
            let mut bad = good;
            bad[index] ^= 1;
            assert!(check_header(&bad, &good).is_err());
        }
        assert!(check_header(&good[..55], &good).is_err());
        assert!(header(&"a".repeat(64), 0, 1234).is_err());
        assert!(header(&"a".repeat(64), 3, MAX_BYTES + 1).is_err());
    }
}
