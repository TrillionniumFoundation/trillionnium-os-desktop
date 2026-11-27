//! Fixed, root-owned runtime inputs for the successor working qualification.
//! Public source documents retain their original bytes. Their historical path
//! fields are provenance data; the actual runtime opens only these fixed names.
use super::{CurrentPublicMaterials, FilePin, Identity, Result, SealedInput, ensure, fs};
use crate::cold_original_data::labels::{
    OriginalLabelSources,
    working_inputs::{self, WorkingInputLabelsApplied},
};
use rustix::fs::Mode;
use serde_json::Value;
use std::{
    fs::File,
    io::Write,
    os::unix::fs::FileExt,
    path::{Path, PathBuf},
    sync::Arc,
};

#[path = "../../../runtime/droidloom-supervisor/src/native_working_layout.rs"]
mod layout;

const BASE: &str = layout::WORKING_QUALIFICATION_BASE;
const MAX_INPUT: u64 = 16 * 1024 * 1024;
const NAMES: [&str; 6] = [
    layout::WORKING_ADMITTED_MATERIALS_FILE,
    layout::WORKING_APPLICATION_INPUT_FILES[0],
    layout::WORKING_APPLICATION_INPUT_FILES[1],
    layout::WORKING_APPLICATION_INPUT_FILES[2],
    layout::WORKING_APPLICATION_INPUT_FILES[3],
    layout::WORKING_GATE_REGISTRY_FILE,
];
const GATES: &[u8] =
    include_bytes!("../../../runtime/droidloom-applications/src/physical_gate_registry.json");

fn names(directory: &File) -> Result<Vec<String>> {
    let before = fs::stat(directory)?;
    let mut values = Vec::new();
    for item in rustix::fs::Dir::read_from(directory)? {
        let entry = item?;
        let name = entry.file_name().to_str()?;
        if name != "." && name != ".." {
            values.push(name.to_owned());
        }
    }
    ensure(
        fs::stat(directory)? == before,
        "fixed input directory changed while listed",
    )?;
    values.sort();
    Ok(values)
}

fn private(directory: &File, owner: u32) -> Result<Identity> {
    let value = fs::stat(directory)?;
    ensure(
        value.mode == 0o40700
            && value.uid == owner
            && value.gid == rustix::process::getegid().as_raw()
            && fs::xattrs(directory)?.is_empty(),
        "working runtime inputs require a private, unprivileged directory",
    )?;
    Ok(value)
}

// Positional reads preserve the one open description shared with the normal
// label proof. Revalidation must cover the complete body on every invocation.
fn held_hash(file: &File, bytes: u64) -> Result<String> {
    ensure(bytes > 0 && bytes <= MAX_INPUT, "working input hash bound")?;
    let mut raw = vec![0_u8; bytes as usize];
    file.read_exact_at(&mut raw, 0)?;
    let mut extra = [0_u8; 1];
    ensure(
        file.read_at(&mut extra, bytes)? == 0,
        "working input has an unlisted tail",
    )?;
    Ok(fs::digest(&raw))
}

/// The actual freshly created inode stays held read-only through source-derived
/// labeling. It is sealed only after that one metadata transition completes.
struct StagedInput {
    pin: FilePin,
    held: File,
    identity: Identity,
}
impl StagedInput {
    fn revalidate_before_label(&self, tree: &fs::Tree) -> Result<()> {
        let name = self
            .pin
            .path
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or("staged input basename absent")?;
        ensure(
            NAMES.contains(&name)
                && fs::stat(&self.held)? == self.identity
                && tree.identity(&format!("/{name}"))? == self.identity
                && fs::xattrs(&self.held)?.is_empty()
                && held_hash(&self.held, self.pin.bytes)? == self.pin.sha256
                && fs::stat(&self.held)? == self.identity,
            "new working input changed before its source-derived label",
        )
    }
    fn seal(
        &self,
        index: usize,
        tree: &fs::Tree,
        labels: &WorkingInputLabelsApplied,
    ) -> Result<SealedInput> {
        labels.revalidate()?;
        let actual = fs::stat(&self.held)?;
        labels.verify_input_transition(index, &self.identity, &actual)?;
        let before = &self.identity;
        let unchanged = (
            before.dev,
            before.ino,
            before.mode,
            before.uid,
            before.gid,
            before.nlink,
            before.size,
            before.mtime_sec,
            before.mtime_nsec,
        );
        let after = (
            actual.dev,
            actual.ino,
            actual.mode,
            actual.uid,
            actual.gid,
            actual.nlink,
            actual.size,
            actual.mtime_sec,
            actual.mtime_nsec,
        );
        let name = self
            .pin
            .path
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or("staged input basename absent")?;
        ensure(
            unchanged == after
                && fs::xattrs(&self.held)?.is_empty()
                && tree.identity(&format!("/{name}"))? == actual
                && held_hash(&self.held, self.pin.bytes)? == self.pin.sha256
                && fs::stat(&self.held)? == actual,
            "source-derived input labeling changed bytes or a non-ctime identity field",
        )?;
        // The normal seal observes the final actual ctime, never a substituted
        // receipt or an identity captured before fsetxattr.
        let sealed = SealedInput::open(&self.pin)?;
        labels.revalidate()?;
        ensure(
            fs::stat(&self.held)? == actual && tree.identity(&format!("/{name}"))? == actual,
            "source-labeled input was replaced while finally sealed",
        )?;
        sealed.revalidate()?;
        Ok(sealed)
    }
}

fn write_input(
    tree: &fs::Tree,
    directory: &Path,
    name: &str,
    raw: &[u8],
    expected_bytes: u64,
    expected_sha256: &str,
) -> Result<StagedInput> {
    ensure(
        NAMES.contains(&name)
            && !raw.is_empty()
            && raw.len() as u64 <= MAX_INPUT
            && raw.len() as u64 == expected_bytes
            && fs::digest(raw) == expected_sha256,
        "fixed working input name, complete bytes or source commitment differs",
    )?;
    private(&tree.root, tree.owner)?;
    let relative = format!("/{name}");
    let mut held = tree.create_file(&relative)?;
    held.write_all(raw)?;
    rustix::fs::fchmod(&held, Mode::from_raw_mode(0o400))?;
    held.sync_all()?;
    let actual = fs::stat(&held)?;
    ensure(
        actual.mode == 0o100400
            && actual.uid == tree.owner
            && actual.gid == rustix::process::getegid().as_raw()
            && actual.nlink == 1
            && actual.size == expected_bytes
            && fs::xattrs(&held)?.is_empty(),
        "new working input inode or privilege attributes differ",
    )?;
    let mut readback = vec![0_u8; raw.len()];
    held.read_exact_at(&mut readback, 0)?;
    ensure(
        readback == raw && fs::stat(&held)? == actual && tree.identity(&relative)? == actual,
        "new working input complete readback or pathname differs",
    )?;
    tree.root.sync_all()?;
    let readonly = tree.file(&relative)?;
    ensure(
        fs::stat(&readonly)? == actual && tree.identity(&relative)? == actual,
        "new working input changed while retained read-only",
    )?;
    Ok(StagedInput {
        pin: FilePin {
            path: directory.join(name),
            bytes: expected_bytes,
            sha256: expected_sha256.to_owned(),
        },
        held: readonly,
        identity: actual,
    })
}

/// This value is constructed only inside the actual cold material admission.
/// It is source custody, never evidence of Android or application acceptance.
pub(super) struct RuntimeInputs {
    candidate: PathBuf,
    candidate_tree: fs::Tree,
    candidate_identity: Identity,
    inputs: fs::Tree,
    inputs_identity: Identity,
    records: Vec<SealedInput>,
    labels: WorkingInputLabelsApplied,
}

impl RuntimeInputs {
    pub(super) fn publish(
        candidate_id: &str,
        materials: &CurrentPublicMaterials,
        admitted: &FilePin,
        label_sources: Arc<OriginalLabelSources>,
    ) -> Result<Self> {
        ensure(
            rustix::process::geteuid().as_raw() == 0
                && rustix::process::getegid().as_raw() == 0
                && fs::valid_digest(candidate_id),
            "working runtime input publication requires the actual root cold owner",
        )?;
        materials.revalidate()?;
        let source = SealedInput::open(admitted)?;
        let raw = source.read()?;
        ensure(
            raw.len() as u64 <= MAX_INPUT,
            "admitted material input exceeds fixed runtime bound",
        )?;
        let report: Value = serde_json::from_slice(&raw)?;
        ensure(
            report["schema"] == "droidloom.working-qualification-admitted-materials.v1"
                && report["candidate_id"] == candidate_id,
            "working input admission names another source stage or candidate",
        )?;
        let gates: Value = serde_json::from_slice(GATES)?;
        ensure(
            gates["schema"] == "pocket4-app-release-gates-v1"
                && GATES.len() == 27_878
                && fs::digest(GATES)
                    == "0b21f963898308b082f3808dd48165c1397badd1fa8a753c3a766e135b3cb3c8",
            "compiled complete application gate registry differs",
        )?;

        // Only this source-owned namespace may be created. An existing parent
        // must already be protected; no existing directory mode is relaxed.
        let parent = fs::Tree::open("/var/lib/droidloom", 0)?;
        match rustix::fs::mkdirat(&parent.root, "qualification", Mode::from_raw_mode(0o700)) {
            Ok(()) => (),
            Err(error) if error == rustix::io::Errno::EXIST => (),
            Err(error) => return Err(error.into()),
        }
        let base = fs::Tree::open(BASE, 0)?;
        private(&base.root, 0)?;
        let candidate = layout::working_candidate_directory(candidate_id)
            .ok_or("working input candidate differs from the shared source layout")?;
        let candidate_tree = fs::Tree::create(&fs::absolute_string(&candidate)?, 0)?;
        private(&candidate_tree.root, 0)?;
        candidate_tree.mkdir(&format!("/{}", layout::WORKING_INPUT_DIRECTORY))?;
        let input_path = candidate.join(layout::WORKING_INPUT_DIRECTORY);
        let inputs = fs::Tree::open(&fs::absolute_string(&input_path)?, 0)?;
        private(&inputs.root, 0)?;

        let mut staged = Vec::with_capacity(NAMES.len());
        let mut put = |name: &str, body: &[u8], expected: &FilePin| -> Result<()> {
            let copied = write_input(
                &inputs,
                &input_path,
                name,
                body,
                expected.bytes,
                &expected.sha256,
            )?;
            staged.push(copied);
            Ok(())
        };
        put(NAMES[0], &raw, admitted)?;
        let documents = materials.documents();
        ensure(
            documents.len() == 4,
            "exactly four admitted public input roles required",
        )?;
        for (name, document) in NAMES[1..5].iter().zip(documents) {
            let body = document.bytes(MAX_INPUT)?;
            put(name, &body, document.pin())?;
            document.revalidate()?;
        }
        let gate_pin = FilePin {
            path: input_path.join(NAMES[5]),
            bytes: GATES.len() as u64,
            sha256: fs::digest(GATES),
        };
        put(NAMES[5], GATES, &gate_pin)?;
        for entry in &staged {
            entry.revalidate_before_label(&inputs)?;
        }
        let held_files: [&File; 6] = staged
            .iter()
            .map(|entry| &entry.held)
            .collect::<Vec<_>>()
            .try_into()
            .map_err(|_| "source-derived working label input roster differs")?;
        let labels = working_inputs::apply(
            label_sources,
            candidate_id,
            &candidate_tree.root,
            &inputs.root,
            held_files,
        )?;
        let records = staged
            .iter()
            .enumerate()
            .map(|(index, entry)| entry.seal(index, &inputs, &labels))
            .collect::<Result<Vec<_>>>()?;
        inputs.root.sync_all()?;
        candidate_tree.root.sync_all()?;
        base.root.sync_all()?;
        parent.root.sync_all()?;
        source.revalidate()?;
        materials.revalidate()?;
        let candidate_identity = private(&candidate_tree.root, 0)?;
        let inputs_identity = private(&inputs.root, 0)?;
        let value = Self {
            candidate,
            candidate_tree,
            candidate_identity,
            inputs,
            inputs_identity,
            records,
            labels,
        };
        value.revalidate()?;
        Ok(value)
    }

    pub(super) fn revalidate(&self) -> Result<()> {
        self.labels.revalidate()?;
        fs::assert_root_namespace(&fs::absolute_string(&self.candidate)?, &self.candidate_tree)?;
        fs::assert_root_namespace(
            &fs::absolute_string(&self.candidate.join(layout::WORKING_INPUT_DIRECTORY))?,
            &self.inputs,
        )?;
        let mut expected = NAMES
            .iter()
            .map(|name| (*name).to_owned())
            .collect::<Vec<_>>();
        expected.sort();
        ensure(
            private(&self.candidate_tree.root, 0)? == self.candidate_identity
                && private(&self.inputs.root, 0)? == self.inputs_identity
                && names(&self.candidate_tree.root)? == [layout::WORKING_INPUT_DIRECTORY]
                && names(&self.inputs.root)? == expected
                && self.records.len() == NAMES.len(),
            "cold working runtime input inode or exact membership changed",
        )?;
        for record in &self.records {
            record.revalidate()?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fixed_runtime_input_copy_preserves_raw_bytes_and_refuses_replacement() -> Result<()> {
        let temp = tempfile::tempdir()?;
        rustix::fs::chmod(temp.path(), Mode::from_raw_mode(0o700))?;
        let owner = rustix::process::geteuid().as_raw();
        let tree = fs::Tree::open(&fs::absolute_string(temp.path())?, owner)?;
        let raw = b"{ \"historical_path\": \"/home/source/file.json\" }\n";
        let pin = write_input(
            &tree,
            temp.path(),
            NAMES[1],
            raw,
            raw.len() as u64,
            &fs::digest(raw),
        )?;
        assert_eq!(std::fs::read(&pin.pin.path)?, raw);
        pin.revalidate_before_label(&tree)?;
        assert_eq!(
            (&pin.held)
                .write_all(b"replacement")
                .unwrap_err()
                .raw_os_error(),
            Some(rustix::io::Errno::BADF.raw_os_error()),
        );
        pin.revalidate_before_label(&tree)?;
        assert_eq!(tree.identity(&format!("/{}", NAMES[1]))?.mode, 0o100400);
        assert!(write_input(&tree, temp.path(), NAMES[1], b"{}", 2, &fs::digest(b"{}")).is_err());
        assert!(
            write_input(
                &tree,
                temp.path(),
                "../PLAN.json",
                raw,
                raw.len() as u64,
                &fs::digest(raw)
            )
            .is_err()
        );
        assert!(
            write_input(
                &tree,
                temp.path(),
                NAMES[2],
                raw,
                raw.len() as u64,
                &"0".repeat(64)
            )
            .is_err()
        );
        assert_eq!(names(&tree.root)?, vec![NAMES[1].to_owned()]);
        Ok(())
    }

    #[test]
    fn compiled_registry_is_the_complete_physical_factory_registry() -> Result<()> {
        let registry: Value = serde_json::from_slice(GATES)?;
        ensure(
            registry["schema"] == "pocket4-app-release-gates-v1"
                && GATES.len() == 27_878
                && fs::digest(GATES)
                    == "0b21f963898308b082f3808dd48165c1397badd1fa8a753c3a766e135b3cb3c8",
            "compiled physical registry bytes differ",
        )?;
        Ok(())
    }
}
