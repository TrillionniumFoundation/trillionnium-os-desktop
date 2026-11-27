//! Produce the runtime comparison from the continuously held original images.
//! This never reopens an image or moves a directory. The old two image OFDs
//! stay owned by PreparedReturnedPair and later WorkingPairTransaction. Their
//! full identities are unchanged by the fixed directory exchanges and are
//! never included in the working label overlay.
use super::*;
use crate::cold_working_recovery::contract::retained_data as contract;
use sha2::{Digest, Sha256};
use std::{
    io,
    time::{Duration, Instant},
};
#[path = "../../../runtime/droidloom-supervisor/src/working_retained_read.rs"]
mod retained_read;

fn before_deadline(until: Instant) -> Result<()> {
    ensure(
        Instant::now() < until,
        "the fixed complete retained-pair read window expired",
    )
}

fn hash_retained_image(
    held: &File,
    expected: &labels::Snapshot,
    digest: &str,
    until: Instant,
) -> Result<String> {
    before_deadline(until)?;
    ensure(
        fs::valid_digest(digest)
            && rustix::fs::fcntl_getfl(held)? & OFlags::ACCMODE == OFlags::RDONLY
            && labels::snapshot(held)? == *expected,
        "retained original lost its exact read-only image descriptor",
    )?;
    rustix::fs::flock(held, FlockOperation::NonBlockingLockExclusive)?;
    let size = labels::snapshot_identity(expected).size;
    let mut hash = Sha256::new();
    let mut buffer = vec![0; retained_read::MAX_READ];
    let mut offset = 0u64;
    let mut guard = || -> io::Result<()> {
        let check = || -> Result<()> {
            before_deadline(until)?;
            ensure(
                labels::snapshot(held)? == *expected,
                "retained original changed across an actual no-cache read",
            )
        };
        check().map_err(|error| io::Error::other(error.to_string()))
    };
    while offset < size {
        let wanted = usize::try_from((size - offset).min(buffer.len() as u64))?;
        retained_read::read_exact_at(held, &mut buffer[..wanted], offset, until, &mut guard)?;
        hash.update(&buffer[..wanted]);
        before_deadline(until)?;
        offset = offset
            .checked_add(wanted as u64)
            .ok_or("retained image offset overflow")?;
    }
    ensure(
        labels::snapshot(held)? == *expected,
        "retained original changed while its complete contents were read",
    )?;
    rustix::fs::flock(held, FlockOperation::NonBlockingLockExclusive)?;
    let observed = hex::encode(hash.finalize());
    ensure(
        observed == digest,
        "held retained original bytes differ from their fixed cold-clone source",
    )?;
    before_deadline(until)?;
    Ok(observed)
}

impl PreparedReturnedPair {
    pub(crate) fn retained_originals(
        &self,
        history: &ReturnedOnceHistory,
    ) -> Result<contract::RetainedOriginalsSpec> {
        // One source-owned absolute deadline covers both complete images.
        // No per-file or per-chunk operation allocates another allowance.
        let until = Instant::now()
            .checked_add(Duration::from_secs(contract::RETAINED_PAIR_HASH_SECONDS))
            .ok_or("retained original pair deadline overflow")?;
        self.guard(history)?;
        before_deadline(until)?;
        let candidate = self
            .work
            .path
            .file_name()
            .and_then(|s| s.to_str())
            .and_then(|name| name.strip_prefix("working-qualification-"))
            .ok_or("retained originals require the fixed working candidate workspace")?;
        ensure(
            fs::valid_digest(candidate)
                && candidate != history.candidate()
                && self.work.path
                    == Path::new(contract::WORK_BASE)
                        .join(format!("working-qualification-{candidate}"))
                && self.pair.backings.len() == 4,
            "retained originals belong to another live candidate or backing roster",
        )?;
        let clone = history.retained_cold_clone()?;
        ensure(
            clone.bytes == 2843 && clone.sha256 == CLONE_SHA,
            "retained originals lost their exact historical cold-clone source",
        )?;
        let clone_bytes = root_pin(&clone, 64 * 1024)?;
        let lineage: Value = serde_json::from_slice(&clone_bytes)?;
        let rows = lineage["rows"]
            .as_array()
            .ok_or("cold-clone original rows absent")?;
        ensure(
            lineage["schema"] == "pocket4-original-data-cold-compatibility-clone-v1"
                && rows.len() == 2,
            "retained original source is not the complete fixed clone lineage",
        )?;
        let directory = fs::Tree::open("/", 0)?.dir(ORIGINAL)?;
        let directory_snapshot = labels::snapshot(&directory)?;
        ensure(
            directory_snapshot == self.pair.original.directory_label_identity,
            "original directory changed before retention comparison capture",
        )?;
        let directory_wire: contract::Snapshot =
            serde_json::from_value(serde_json::to_value(&directory_snapshot)?)?;
        let mut files = Vec::new();
        for (index, name) in IMAGES.iter().enumerate() {
            let original = &self.pair.backings[index];
            let working = &self.pair.backings[index + 2];
            let expected = &self.pair.original.members[*name];
            let prior = &rows[index];
            ensure(
                original.path == Path::new(ORIGINAL).join(name)
                    && working.path == Path::new(WORKING).join(name)
                    && original.identity == expected.identity
                    && original.snapshot == expected.label_identity
                    && !inode(&original.identity, &working.identity)
                    && prior["role"] == if index == 0 { "data" } else { "metadata" }
                    && prior["source_path"] == format!("{ORIGINAL}/{name}")
                    && prior["source_f9_before"] == as_f9(&original.identity)
                    && prior["source_f9_after"] == as_f9(&original.identity)
                    && prior["bytes"] == original.identity.size,
                "retained original differs from its actual held image role and fixed source F9",
            )?;
            let expected_hash = prior["sha256"]
                .as_str()
                .ok_or("original content commitment absent")?;
            let sha256 =
                hash_retained_image(&original.file, &original.snapshot, expected_hash, until)?;
            let snapshot = serde_json::from_value(serde_json::to_value(&original.snapshot)?)?;
            files.push(contract::RetainedOriginal {
                name: (*name).into(),
                snapshot,
                sha256,
            });
            self.guard(history)?;
        }
        ensure(
            labels::snapshot(&directory)? == directory_snapshot
                && root_pin(&clone, 64 * 1024)? == clone_bytes,
            "retained original directory or source changed during complete pair hashing",
        )?;
        let id = directory_wire.identity;
        let result = contract::RetainedOriginalsSpec {
            schema: contract::SCHEMA.into(),
            candidate_id: candidate.into(),
            directory: contract::RetainedDirectory {
                path: self.work.path.join(ROLLBACK),
                // A later rename changes directory times. This is explicitly
                // the stable generation, never a fabricated post-rename F9.
                identity: contract::StableDirectoryIdentity {
                    dev: id.dev,
                    ino: id.ino,
                    mode: id.mode,
                    uid: id.uid,
                    gid: id.gid,
                    nlink: id.nlink,
                    size: id.size,
                },
                handle: directory_wire.handle,
                attributes: directory_wire.attributes,
            },
            files: files
                .try_into()
                .map_err(|_| "exactly two actual retained original files required")?,
        };
        result.validate()?;
        self.guard(history)?;
        before_deadline(until)?;
        Ok(result)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Seek, SeekFrom};
    use std::os::unix::fs::OpenOptionsExt;

    fn end() -> Instant {
        Instant::now() + Duration::from_secs(5)
    }

    fn actual() -> (tempfile::TempDir, File, labels::Snapshot, Vec<u8>) {
        let directory = tempfile::Builder::new()
            .prefix(".p4-retained-original-")
            .tempdir_in(std::env::current_dir().unwrap())
            .unwrap();
        let path = directory.path().join("image");
        let bytes = (0..(1024 * 1024 + 43))
            .map(|n| (n % 251) as u8)
            .collect::<Vec<_>>();
        let mut writer = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&path)
            .unwrap();
        writer.write_all(&bytes).unwrap();
        writer.sync_all().unwrap();
        drop(writer);
        let held = File::open(&path).unwrap();
        let snapshot = labels::snapshot(&held).unwrap();
        (directory, held, snapshot, bytes)
    }

    #[test]
    fn retained_original_hash_reads_all_bytes_without_changing_the_shared_ofd_offset() {
        let (_directory, mut held, snapshot, bytes) = actual();
        held.seek(SeekFrom::Start(17)).unwrap();
        let expected = fs::digest(&bytes);
        assert_eq!(
            hash_retained_image(&held, &snapshot, &expected, end()).unwrap(),
            expected
        );
        assert_eq!(held.stream_position().unwrap(), 17);
        assert_eq!(labels::snapshot(&held).unwrap(), snapshot);
        assert_eq!(
            rustix::fs::fcntl_getfl(&held).unwrap() & OFlags::ACCMODE,
            OFlags::RDONLY
        );
    }

    #[test]
    fn retained_original_hash_rejects_wrong_content_commitment_without_an_effect() {
        let (_directory, held, snapshot, bytes) = actual();
        assert!(hash_retained_image(&held, &snapshot, &"a".repeat(64), end()).is_err());
        assert_eq!(labels::snapshot(&held).unwrap(), snapshot);
        assert_eq!(
            hash_retained_image(&held, &snapshot, &fs::digest(&bytes), end()).unwrap(),
            fs::digest(&bytes)
        );
    }

    #[test]
    fn retained_original_hash_rejects_same_length_mutation_of_the_actual_inode() {
        let (directory, held, snapshot, mut bytes) = actual();
        bytes[1024 * 1024 + 42] ^= 1;
        std::fs::write(directory.path().join("image"), &bytes).unwrap();
        assert!(hash_retained_image(&held, &snapshot, &fs::digest(&bytes), end()).is_err());
    }

    #[test]
    fn retained_original_hash_rejects_a_same_bytes_different_descriptor() {
        let (_directory, _held, snapshot, bytes) = actual();
        let (_other_directory, other, _, other_bytes) = actual();
        assert_eq!(bytes, other_bytes);
        assert!(hash_retained_image(&other, &snapshot, &fs::digest(&bytes), end()).is_err());
    }

    #[test]
    fn retained_original_hash_rejects_a_writable_description() {
        let (directory, _held, snapshot, bytes) = actual();
        let writable = std::fs::OpenOptions::new()
            .read(true)
            .write(true)
            .open(directory.path().join("image"))
            .unwrap();
        assert!(hash_retained_image(&writable, &snapshot, &fs::digest(&bytes), end()).is_err());
    }
    #[test]
    fn retained_original_hash_rejects_an_expired_shared_pair_deadline() {
        let (_directory, mut held, snapshot, bytes) = actual();
        held.seek(SeekFrom::Start(19)).unwrap();
        let expired = Instant::now();
        assert!(hash_retained_image(&held, &snapshot, &fs::digest(&bytes), expired).is_err());
        assert_eq!(held.stream_position().unwrap(), 19);
        assert_eq!(labels::snapshot(&held).unwrap(), snapshot);
    }
}
