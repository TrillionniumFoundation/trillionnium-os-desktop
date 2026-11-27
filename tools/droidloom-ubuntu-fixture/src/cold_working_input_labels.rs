//! Fixed H2 cold input labels from the admitted normal matcher and contexts.
//! The live source object and held inodes are retained; serialized comparison
//! rows cannot create this proof. Only the fixed candidate, inputs and six files
//! are mutable. The normally installed common ancestor is observation-only.
use super::{OriginalLabelSources, Snapshot, only_ctime_changed, scope::Entry, snapshot};
use crate::{Result, boot_files as files, ensure, fs, model::Identity};
use rustix::fs::XattrFlags;
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    fs::File,
    os::unix::fs::FileExt,
    path::{Path, PathBuf},
    sync::Arc,
};

#[path = "../../../runtime/droidloom-supervisor/src/native_working_layout.rs"]
mod layout;

const FILE_LIMIT: u64 = 16 * 1024 * 1024;
const INPUT_NAMES: [&str; 6] = [
    layout::WORKING_ADMITTED_MATERIALS_FILE,
    layout::WORKING_APPLICATION_INPUT_FILES[0],
    layout::WORKING_APPLICATION_INPUT_FILES[1],
    layout::WORKING_APPLICATION_INPUT_FILES[2],
    layout::WORKING_APPLICATION_INPUT_FILES[3],
    layout::WORKING_GATE_REGISTRY_FILE,
];

fn fixed_paths(candidate_id: &str) -> Result<[PathBuf; 9]> {
    let candidate = layout::working_candidate_directory(candidate_id)
        .ok_or("working labels require the canonical candidate digest")?;
    let inputs = candidate.join(layout::WORKING_INPUT_DIRECTORY);
    Ok([
        PathBuf::from(layout::WORKING_QUALIFICATION_BASE),
        candidate,
        inputs.clone(),
        inputs.join(INPUT_NAMES[0]),
        inputs.join(INPUT_NAMES[1]),
        inputs.join(INPUT_NAMES[2]),
        inputs.join(INPUT_NAMES[3]),
        inputs.join(INPUT_NAMES[4]),
        inputs.join(INPUT_NAMES[5]),
    ])
}

fn expected_labels() -> Vec<Vec<u8>> {
    [
        layout::WORKING_ROOT_DIRECTORY_LABEL,
        layout::WORKING_CANDIDATE_DIRECTORY_LABEL,
        layout::WORKING_INPUT_DIRECTORY_LABEL,
        layout::WORKING_INPUT_FILE_LABEL,
        layout::WORKING_INPUT_FILE_LABEL,
        layout::WORKING_INPUT_FILE_LABEL,
        layout::WORKING_INPUT_FILE_LABEL,
        layout::WORKING_INPUT_FILE_LABEL,
        layout::WORKING_INPUT_FILE_LABEL,
    ]
    .iter()
    .map(|v| {
        let mut bytes = v.to_vec();
        bytes.push(0);
        bytes
    })
    .collect()
}

fn source_labels(labels: &[Vec<u8>]) -> Result<()> {
    ensure(
        labels == expected_labels(),
        "normal file contexts differ from the fixed working input roles",
    )
}

fn stable_directory(a: &Identity, b: &Identity) -> bool {
    (a.dev, a.ino, a.mode, a.uid, a.gid) == (b.dev, b.ino, b.mode, b.uid, b.gid)
}

fn named_identity(path: &Path, expected: &Identity) -> Result<()> {
    let named = fs::Tree::open("/", 0)?.identity(&fs::absolute_string(path)?)?;
    ensure(
        named == *expected,
        "working label name no longer identifies its held inode",
    )
}

fn regular_hash(file: &File, expected: &Identity) -> Result<String> {
    ensure(
        expected.size > 0 && expected.size <= FILE_LIMIT && fs::stat(file)? == *expected,
        "working input has no bounded stable body",
    )?;
    let mut hash = Sha256::new();
    let mut offset = 0u64;
    let mut buffer = [0u8; 65536];
    while offset < expected.size {
        let wanted = (expected.size - offset).min(buffer.len() as u64) as usize;
        let count = file.read_at(&mut buffer[..wanted], offset)?;
        ensure(
            count != 0,
            "working input truncated during complete label readback",
        )?;
        hash.update(&buffer[..count]);
        offset += count as u64;
    }
    ensure(
        file.read_at(&mut buffer[..1], offset)? == 0 && fs::stat(file)? == *expected,
        "working input grew or metadata changed during label readback",
    )?;
    Ok(hex::encode(hash.finalize()))
}

struct Held {
    path: PathBuf,
    file: File,
    before: Snapshot,
    after: Snapshot,
    body: Option<String>,
}

impl Held {
    fn capture(path: PathBuf, source: &File, directory: bool) -> Result<Self> {
        let file = source.try_clone()?;
        let before = snapshot(&file)?;
        let id = &before.identity;
        ensure(
            id.uid == 0
                && id.gid == 0
                && id.mode == if directory { 0o40700 } else { 0o100400 }
                && (directory || id.nlink == 1)
                && fs::xattrs(&file)?.is_empty(),
            "working label scope requires private root-owned inodes without privilege attributes",
        )?;
        named_identity(&path, id)?;
        let body = if directory {
            None
        } else {
            Some(regular_hash(&file, id)?)
        };
        ensure(
            snapshot(&file)? == before,
            "working label initial snapshot changed",
        )?;
        Ok(Self {
            path,
            file,
            after: before.clone(),
            before,
            body,
        })
    }

    fn revalidate_before(&self) -> Result<()> {
        let actual = snapshot(&self.file)?;
        ensure(
            actual == self.before,
            "working input changed before its label operation",
        )?;
        named_identity(&self.path, &actual.identity)?;
        if let Some(expected) = &self.body {
            ensure(
                regular_hash(&self.file, &actual.identity)? == *expected,
                "working input body changed before labeling",
            )?;
        }
        ensure(
            snapshot(&self.file)? == actual,
            "working input raced its pre-label readback",
        )
    }

    fn revalidate(&self) -> Result<()> {
        let actual = snapshot(&self.file)?;
        let same_identity = if self.body.is_some() {
            actual.identity == self.after.identity
        } else {
            // The publisher may subsequently create the fixed boot/runtime
            // children. Those directory entries do not change inode custody.
            stable_directory(&actual.identity, &self.after.identity)
        };
        ensure(
            same_identity
                && actual.handle == self.after.handle
                && actual.attributes == self.after.attributes
                && fs::xattrs(&self.file)?.is_empty(),
            "applied working input label, inode or unrelated attributes changed",
        )?;
        named_identity(&self.path, &actual.identity)?;
        if let Some(expected) = &self.body {
            ensure(
                regular_hash(&self.file, &actual.identity)? == *expected,
                "labeled working input body changed",
            )?;
        }
        ensure(
            snapshot(&self.file)? == actual,
            "working label custody changed during readback",
        )
    }

    fn apply(&mut self, label: &[u8]) -> Result<()> {
        self.revalidate_before()?;
        // These are ordinary readable descriptors supplied by the create-only
        // publisher, not O_PATH and not a pathname/procfd redirection.
        rustix::fs::fsetxattr(&self.file, super::LABEL, label, XattrFlags::empty())?;
        self.file.sync_all()?;
        let after = snapshot(&self.file)?;
        let mut expected_attributes = self.before.attributes.clone();
        expected_attributes.insert(super::LABEL.to_owned(), label.to_vec());
        ensure(
            only_ctime_changed(&self.before.identity, &after.identity)
                && self.before.handle == after.handle
                && after.attributes == expected_attributes,
            "working label write changed more than its exact SELinux attribute and ctime",
        )?;
        self.after = after;
        self.revalidate()
    }
}

/// Constructed only by the normal-source, fixed-inode operation below.
/// Deliberately no Clone, Deserialize or public constructor.
pub(crate) struct WorkingInputLabelsApplied {
    sources: Arc<OriginalLabelSources>,
    held: Vec<Held>,
    lookups: files::FilePin,
    lookup_file: File,
    lookup_identity: Identity,
}

impl WorkingInputLabelsApplied {
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.sources.revalidate()?;
        ensure(
            fs::stat(&self.lookup_file)? == self.lookup_identity,
            "normal working context lookup evidence changed",
        )?;
        named_identity(&self.lookups.path, &self.lookup_identity)?;
        ensure(
            regular_hash(&self.lookup_file, &self.lookup_identity)? == self.lookups.sha256,
            "normal working context lookup bytes changed",
        )?;
        for held in &self.held {
            held.revalidate()?;
        }
        self.sources.revalidate()
    }

    pub(crate) fn verify_input_transition(
        &self,
        index: usize,
        before: &Identity,
        after: &Identity,
    ) -> Result<()> {
        ensure(
            index < INPUT_NAMES.len(),
            "working input role index is outside the fixed six",
        )?;
        self.revalidate()?;
        let held = &self.held[index + 3];
        ensure(
            held.before.identity == *before
                && held.after.identity == *after
                && only_ctime_changed(before, after),
            "working input seal is not this actual held label transition",
        )
    }
}

pub(crate) fn apply(
    sources: Arc<OriginalLabelSources>,
    candidate_id: &str,
    candidate: &File,
    inputs: &File,
    files: [&File; 6],
) -> Result<WorkingInputLabelsApplied> {
    ensure(
        rustix::process::getuid().as_raw() == 0 && rustix::process::geteuid().as_raw() == 0,
        "working input labels require the actual cold root publisher",
    )?;
    sources.revalidate()?;
    let paths = fixed_paths(candidate_id)?;
    let base = fs::Tree::open(layout::WORKING_QUALIFICATION_BASE, 0)?.root;
    let descriptors = [
        &base, candidate, inputs, files[0], files[1], files[2], files[3], files[4], files[5],
    ];
    let mut held = paths
        .into_iter()
        .zip(descriptors)
        .enumerate()
        .map(|(i, (path, file))| Held::capture(path, file, i < 3))
        .collect::<Result<Vec<_>>>()?;
    let device = held[0].before.identity.dev;
    let mut identities = BTreeSet::new();
    for item in &held {
        ensure(
            item.before.identity.dev == device
                && identities.insert((item.before.identity.dev, item.before.identity.ino)),
            "working label scope crosses devices or repeats a held inode",
        )?;
    }
    let entries = held
        .iter()
        .enumerate()
        .map(|(i, item)| Entry {
            path: item.path.clone(),
            snapshot: item.before.clone(),
            matcher_type: if i < 3 { "dir".into() } else { "file".into() },
        })
        .collect::<Vec<_>>();
    let work = sources
        .source_pin()
        .path
        .parent()
        .ok_or("normal source work parent missing")?
        .join(format!("working-input-labels-{candidate_id}"));
    files::private_dir(&work)?;
    let (labels, lookups) = sources.lookup_entries(&entries, &work)?;
    source_labels(&labels)?;
    for item in &held {
        item.revalidate_before()?;
    }
    // The common ancestor must have been labeled by normal H2 installation.
    // This factory has no authority to fix or create that ninth label.
    ensure(
        held[0].before.attributes.get(super::LABEL) == Some(&labels[0]),
        "working common ancestor lacks its normally installed exact label",
    )?;
    for i in 1..held.len() {
        sources.revalidate_custody()?;
        held[0].revalidate_before()?;
        held[i].apply(&labels[i])?;
    }
    inputs.sync_all()?;
    candidate.sync_all()?;
    let (lookup_file, lookup_identity) = files::open_pin(&lookups)?;
    let result = WorkingInputLabelsApplied {
        sources,
        held,
        lookups,
        lookup_file,
        lookup_identity,
    };
    result.revalidate()?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    #[test]
    fn only_canonical_candidate_and_exact_six_input_names_are_derived() {
        let paths = fixed_paths(&"a".repeat(64)).unwrap();
        assert_eq!(paths.len(), 9);
        assert_eq!(paths[0], Path::new(layout::WORKING_QUALIFICATION_BASE));
        assert_eq!(paths[3].file_name().unwrap(), "ADMITTED-MATERIALS.json");
        assert_eq!(paths[8].file_name().unwrap(), "gate-registry.json");
        assert_eq!(paths.iter().collect::<BTreeSet<_>>().len(), 9);
        for bad in [
            "a".repeat(63),
            "a".repeat(65),
            "G".repeat(64),
            "../inputs".into(),
        ] {
            assert!(fixed_paths(&bad).is_err());
        }
    }

    #[test]
    fn normal_source_must_match_every_exact_role_including_readonly_base() {
        let expected = expected_labels();
        source_labels(&expected).unwrap();
        for index in 0..expected.len() {
            let mut different = expected.clone();
            different[index] = b"u:object_r:p4_linux_native_data_t:s0\0".to_vec();
            assert!(source_labels(&different).is_err());
        }
        assert!(source_labels(&expected[..8]).is_err());
        let mut extra = expected.clone();
        extra.push(expected[0].clone());
        assert!(source_labels(&extra).is_err());
        let mut reordered = expected;
        reordered.swap(1, 2);
        assert!(source_labels(&reordered).is_err());
    }

    #[test]
    fn real_descriptor_body_readback_rejects_stale_metadata_and_preserves_cursor() {
        let area = tempfile::tempdir().unwrap();
        let path = area.path().join("input");
        std::fs::write(&path, b"actual complete public input").unwrap();
        let held = File::open(&path).unwrap();
        let identity = fs::stat(&held).unwrap();
        assert_eq!(
            regular_hash(&held, &identity).unwrap(),
            fs::digest(b"actual complete public input")
        );
        let mut copy = held.try_clone().unwrap();
        use std::io::Read;
        let mut prefix = [0u8; 6];
        copy.read_exact(&mut prefix).unwrap();
        assert_eq!(&prefix, b"actual");
        regular_hash(&held, &identity).unwrap();
        let mut next = [0u8; 1];
        copy.read_exact(&mut next).unwrap();
        assert_eq!(&next, b" ");
        std::fs::write(&path, b"replacement").unwrap();
        assert!(regular_hash(&held, &identity).is_err());
    }

    #[test]
    fn directory_growth_is_allowed_but_mode_owner_and_inode_changes_are_not() {
        let area = tempfile::tempdir().unwrap();
        let held = File::open(area.path()).unwrap();
        let before = fs::stat(&held).unwrap();
        std::fs::create_dir(area.path().join("fixed-child")).unwrap();
        let grown = fs::stat(&held).unwrap();
        assert!(stable_directory(&before, &grown));
        assert_ne!(before, grown);
        std::fs::set_permissions(area.path(), std::fs::Permissions::from_mode(0o755)).unwrap();
        assert!(!stable_directory(&before, &fs::stat(&held).unwrap()));
        for field in 0..3 {
            let mut other = before.clone();
            match field {
                0 => other.ino += 1,
                1 => other.uid += 1,
                _ => other.gid += 1,
            }
            assert!(!stable_directory(&before, &other));
        }
    }
}
