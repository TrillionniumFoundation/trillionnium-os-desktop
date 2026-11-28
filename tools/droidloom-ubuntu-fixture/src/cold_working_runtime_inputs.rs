//! Complete byte-identical public provenance held by the actual cold owner.
//! e6's running producer consumes separately admitted normal host-package
//! materials. These root-only cold copies remain outside the runtime namespace;
//! no serialized copy or source path can create a runtime preparation permit.
use super::{CurrentPublicMaterials, FilePin, Identity, Result, SealedInput, ensure, fs};
use rustix::fs::Mode;
use serde_json::Value;
use std::{fs::File, io::Write, os::unix::fs::FileExt, path::{Path, PathBuf}};

const BASE: &str = "/var/lib/droidloom-qualification";
const MAX_INPUT: u64 = 16 * 1024 * 1024;
const NAMES: [&str; 6] = [
    "ADMITTED-MATERIALS.json", "application-selection.json",
    "application-signatures.json", "application-import.json",
    "application-input-verification.json", "gate-registry.json",
];
const GATES: &[u8] = include_bytes!("../../droidloom-update/resources/working-preparation/apps41/APP-RELEASE-GATES.json");

fn names(directory: &File) -> Result<Vec<String>> {
    let before = fs::stat(directory)?;
    let mut values = Vec::new();
    for item in rustix::fs::Dir::read_from(directory)? {
        let entry = item?;
        let name = entry.file_name().to_str()?;
        if name != "." && name != ".." { values.push(name.to_owned()); }
    }
    ensure(fs::stat(directory)? == before, "cold input directory changed while listed")?;
    values.sort();
    Ok(values)
}
fn private(directory: &File, owner: u32) -> Result<Identity> {
    let value = fs::stat(directory)?;
    ensure(value.mode == 0o40700 && value.uid == owner
        && value.gid == rustix::process::getegid().as_raw()
        && fs::xattrs(directory)?.is_empty(), "cold input directory is not protected")?;
    Ok(value)
}
fn held_hash(file: &File, bytes: u64) -> Result<String> {
    ensure(bytes > 0 && bytes <= MAX_INPUT, "cold input hash bound")?;
    let mut raw = vec![0; bytes as usize];
    file.read_exact_at(&mut raw, 0)?;
    ensure(file.read_at(&mut [0], bytes)? == 0, "cold input has an unlisted tail")?;
    Ok(fs::digest(&raw))
}
struct StagedInput { pin: FilePin, held: File, identity: Identity }
impl StagedInput {
    fn revalidate_custody(&self, tree: &fs::Tree) -> Result<()> {
        let name = self.pin.path.file_name().and_then(|s|s.to_str()).ok_or("cold input basename")?;
        ensure(NAMES.contains(&name) && fs::stat(&self.held)? == self.identity
            && tree.identity(&format!("/{name}"))? == self.identity
            && fs::xattrs(&self.held)?.is_empty(), "held cold input custody changed")
    }
    fn revalidate(&self, tree: &fs::Tree) -> Result<()> {
        self.revalidate_custody(tree)?;
        ensure(held_hash(&self.held, self.pin.bytes)? == self.pin.sha256,
            "held cold input complete bytes changed")?;
        self.revalidate_custody(tree)
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

/// No deserializer or constructor from a prior report. Every original source
/// remains held by CurrentPublicMaterials as well as these fresh copied inodes.
pub(super) struct RuntimeInputs {
    work: PathBuf, work_tree: fs::Tree, work_identity: Identity,
    inputs: fs::Tree, inputs_identity: Identity, records: Vec<StagedInput>,
}
impl RuntimeInputs {
    pub(super) fn publish(candidate: &str, materials: &CurrentPublicMaterials,
        admitted: &FilePin) -> Result<Self> {
        ensure(rustix::process::geteuid().as_raw() == 0
            && rustix::process::getegid().as_raw() == 0 && fs::valid_digest(candidate),
            "cold input publication requires actual root ownership and candidate")?;
        materials.revalidate()?;
        let source = SealedInput::open(admitted)?;
        let raw = source.read()?;
        let report: Value = serde_json::from_slice(&raw)?;
        let work = Path::new(BASE).join(format!("working-qualification-{candidate}"));
        ensure(raw.len() as u64 <= MAX_INPUT
            && admitted.path == work.join(NAMES[0])
            && report["schema"] == "droidloom.working-qualification-admitted-materials.v1"
            && report["candidate_id"] == candidate, "cold input admission is not this live work")?;
        ensure(GATES.len() == 32_688
            && fs::digest(GATES) == "f99217aa675c23b8cb671e36af7b3c1d8aa068eeba719a4b985f47d1539c5bb5",
            "compiled complete physical registry differs")?;
        let work_tree = fs::Tree::open(&fs::absolute_string(&work)?, 0)?;
        private(&work_tree.root, 0)?;
        work_tree.mkdir("/inputs")?;
        let path = work.join("inputs");
        let inputs = fs::Tree::open(&fs::absolute_string(&path)?, 0)?;
        private(&inputs.root, 0)?;
        let mut records = vec![write_input(&inputs, &path, NAMES[0], &raw,
            admitted.bytes, &admitted.sha256)?];
        let documents = materials.documents();
        ensure(documents.len() == 4, "exactly four actual source documents required")?;
        for (name, document) in NAMES[1..5].iter().zip(documents) {
            let bytes = document.bytes(MAX_INPUT)?;
            records.push(write_input(&inputs, &path, name, &bytes,
                document.pin().bytes, &document.pin().sha256)?);
            document.revalidate()?;
        }
        let gate = materials.gate_registry();
        let bytes = gate.bytes(MAX_INPUT)?;
        ensure(bytes == GATES, "actual source registry differs from normal source")?;
        records.push(write_input(&inputs, &path, NAMES[5], &bytes,
            gate.pin().bytes, &gate.pin().sha256)?);
        gate.revalidate()?;
        inputs.root.sync_all()?;
        work_tree.root.sync_all()?;
        source.revalidate()?;
        materials.revalidate()?;
        let work_identity = private(&work_tree.root, 0)?;
        let inputs_identity = private(&inputs.root, 0)?;
        let value = Self { work, work_tree, work_identity, inputs, inputs_identity, records };
        value.revalidate()?;
        Ok(value)
    }
    fn guard_directories(&self) -> Result<()> {
        fs::assert_root_namespace(&fs::absolute_string(&self.work)?, &self.work_tree)?;
        fs::assert_root_namespace(&fs::absolute_string(&self.work.join("inputs"))?, &self.inputs)?;
        let actual = private(&self.work_tree.root, 0)?;
        let old = &self.work_identity;
        // Other source-owned cold records are legitimately added to work.
        ensure((actual.dev,actual.ino,actual.mode,actual.uid,actual.gid)
            == (old.dev,old.ino,old.mode,old.uid,old.gid)
            && private(&self.inputs.root, 0)? == self.inputs_identity,
            "cold input parent identity changed")?;
        let mut expected = NAMES.iter().map(|s|s.to_string()).collect::<Vec<_>>();
        expected.sort();
        ensure(names(&self.inputs.root)? == expected && self.records.len() == NAMES.len(),
            "cold input exact membership changed")
    }
    pub(super) fn revalidate_label_custody(&self) -> Result<()> {
        self.guard_directories()?;
        for record in &self.records { record.revalidate_custody(&self.inputs)?; }
        self.guard_directories()
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        self.guard_directories()?;
        for record in &self.records { record.revalidate(&self.inputs)?; }
        self.guard_directories()
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
        pin.revalidate(&tree)?;
        assert_eq!(
            (&pin.held)
                .write_all(b"replacement")
                .unwrap_err()
                .raw_os_error(),
            Some(rustix::io::Errno::BADF.raw_os_error()),
        );
        pin.revalidate(&tree)?;
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
                && GATES.len() == 32_688
                && fs::digest(GATES)
                    == "f99217aa675c23b8cb671e36af7b3c1d8aa068eeba719a4b985f47d1539c5bb5",
            "compiled physical registry bytes differ",
        )?;
        Ok(())
    }
}
