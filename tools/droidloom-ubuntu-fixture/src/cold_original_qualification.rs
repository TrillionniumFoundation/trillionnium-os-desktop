//! Typed ownership boundary for original-machine qualification transactions.
//!
//! All fields are private. A JSON plan, preserved journal or success boolean
//! cannot construct this authority. The material-admission/physical dispatcher
//! is intentionally not exposed until its same-candidate verification is wired.
//! The data and label adapters may compile against this actual fence without
//! introducing a permissive production callback or mock authority.
#[path = "cold_original_once_cell.rs"]
mod cell;
#[path = "cold_original_once_owner.rs"]
mod owner;
#[path = "cold_original_once_state.rs"]
mod state;

use crate::{Result, boot_files as files, cold_original_data, ensure, fs, model::Identity};
use files::FilePin;
use owner::{OriginalOwner, SealedInput};
use state::{Journal, Phase};
use std::{
    cell::RefCell,
    fs::File,
    path::{Path, PathBuf},
};

enum RetirementSource {
    Initial,
    Prepared(SealedInput),
}

/// Non-serializable, non-cloneable custody retained by the sole once owner.
/// There is no public constructor and no physical CLI in this boundary commit.
/// Normal package, owned guest, MAC, initrd and recovery admission must produce
/// the private fields before the later dispatcher can obtain this type.
pub(super) struct OriginalQualificationAuthority {
    owner: RefCell<OriginalOwner>,
    candidate_id: String,
    work: PathBuf,
    work_fd: File,
    work_identity: Identity,
    intent: SealedInput,
    admitted_inputs: Vec<SealedInput>,
    original_cell: SealedInput,
    new_cell: SealedInput,
    expected_cell: FilePin,
    selection: SealedInput,
    cold_clone: SealedInput,
    retirement: RefCell<RetirementSource>,
    journal: RefCell<Journal>,
}

fn same_pin(a: &FilePin, b: &FilePin) -> bool {
    a.path == b.path && a.bytes == b.bytes && a.sha256 == b.sha256
}

fn root_file_matches(pin: &FilePin) -> Result<bool> {
    let tree = fs::Tree::open("/", 0)?;
    let path = fs::absolute_string(&pin.path)?;
    let held = tree.file(&path)?;
    let before = fs::stat(&held)?;
    ensure(
        before.uid == 0 && before.gid == 0 && before.nlink == 1 && before.mode & 0o7777 == 0o644,
        "actual original cell custody differs",
    )?;
    let matched = before.size == pin.bytes && fs::hash(&held)? == pin.sha256;
    ensure(
        fs::stat(&held)? == before && tree.identity(&path)? == before,
        "actual original cell changed during complete readback",
    )?;
    Ok(matched)
}

impl OriginalQualificationAuthority {
    pub(super) fn candidate_id(&self) -> &str {
        &self.candidate_id
    }
    pub(super) fn work(&self) -> &Path {
        &self.work
    }
    pub(super) fn expected_cell(&self) -> &FilePin {
        &self.expected_cell
    }
    pub(super) fn selection(&self) -> &FilePin {
        self.selection.pin()
    }

    pub(super) fn verify_current_owner(&self) -> Result<()> {
        self.owner.borrow().revalidate()?;
        ensure(
            fs::valid_digest(&self.candidate_id)
                && self.work.parent() == Some(Path::new("/var/lib/droidloom-qualification")),
            "once candidate or protected work path differs",
        )?;
        let named = fs::Tree::open(&fs::absolute_string(&self.work)?, 0)?;
        for actual in [fs::stat(&self.work_fd)?, fs::stat(&named.root)?] {
            ensure(
                (actual.dev, actual.ino, actual.mode, actual.uid, actual.gid)
                    == (
                        self.work_identity.dev,
                        self.work_identity.ino,
                        self.work_identity.mode,
                        self.work_identity.uid,
                        self.work_identity.gid,
                    )
                    && actual.uid == 0
                    && actual.gid == 0
                    && actual.mode & 0o7777 == 0o700,
                "once work custody changed",
            )?;
        }
        for input in [
            &self.intent,
            &self.original_cell,
            &self.new_cell,
            &self.selection,
            &self.cold_clone,
        ] {
            input.revalidate()?;
        }
        for input in &self.admitted_inputs {
            input.revalidate()?;
        }
        ensure(
            self.expected_cell.path == Path::new("/etc/droidloom/cell.json")
                && self.expected_cell.bytes == self.new_cell.pin().bytes
                && self.expected_cell.sha256 == self.new_cell.pin().sha256
                && self.selection.pin().path.parent() == Some(self.work()),
            "once selected configuration lost its immutable source",
        )?;
        let journal = self.journal.borrow();
        journal.revalidate()?;
        let phase = journal
            .phase()
            .ok_or("once owner has no admitted intent event")?;
        let original = FilePin {
            path: self.expected_cell.path.clone(),
            bytes: self.original_cell.pin().bytes,
            sha256: self.original_cell.pin().sha256.clone(),
        };
        use Phase::*;
        match phase {
            Admitted | PublicInstallIntent | PublicInstalled | NativeInstallIntent
            | NativeInstalled | CellRestored | NativeRestored | PublicRestored | GrubRestored
            | Returned => {
                ensure(
                    root_file_matches(&original)?,
                    "original cell is not the preserved preimage",
                )?;
            }
            CellPublishIntent | Aborting => {
                ensure(
                    root_file_matches(&original)? || root_file_matches(&self.expected_cell)?,
                    "interrupted cell publication is outside its two exact inode payloads",
                )?;
            }
            _ => ensure(
                root_file_matches(&self.expected_cell)?,
                "candidate cell does not match the sealed exact recipe",
            )?,
        }
        match &*self.retirement.borrow() {
            RetirementSource::Initial => {
                cold_original_data::assert_initial_pair_retired(self.cold_clone.pin())?;
            }
            RetirementSource::Prepared(intent) => {
                intent.revalidate()?;
                let actual = cold_original_data::assert_prepared_pair_retired(intent.pin())?;
                ensure(
                    actual["candidate_id"] == self.candidate_id,
                    "actual prepared data transaction belongs to another candidate",
                )?;
                intent.revalidate()?;
            }
        }
        self.owner.borrow().revalidate()?;
        self.intent.revalidate()?;
        Ok(())
    }

    /// Only the once dispatcher may bind the adapter's real immutable intent.
    /// This does not move images or grant a later phase from caller JSON.
    fn bind_pair_intent(&self, pin: &FilePin) -> Result<()> {
        self.verify_current_owner()?;
        ensure(
            matches!(self.journal.borrow().phase(), Some(Phase::CellPublished))
                && matches!(*self.retirement.borrow(), RetirementSource::Initial),
            "data intent can only be bound after the exact cell publication",
        )?;
        ensure(
            pin.path == self.work.join("DATA-EXCHANGE-INTENT.json"),
            "pair intent is outside the owned work",
        )?;
        let sealed = SealedInput::open(pin)?;
        let intent: serde_json::Value = serde_json::from_slice(&sealed.read()?)?;
        ensure(
            intent["candidate_id"] == self.candidate_id
                && intent["original_boot_id"] == self.owner.borrow().boot_id()
                && intent["work"] == self.work.to_string_lossy().as_ref(),
            "pair intent identity differs from the actual once owner",
        )?;
        for (field, expected) in [
            ("expected_cell", self.expected_cell()),
            ("selection", self.selection()),
            ("cold_clone", self.cold_clone.pin()),
        ] {
            let actual: FilePin = serde_json::from_value(intent[field].clone())?;
            ensure(
                same_pin(&actual, expected),
                "pair intent input differs from once immutable inputs",
            )?;
        }
        cold_original_data::assert_prepared_pair_retired(pin)?;
        sealed.revalidate()?;
        *self.retirement.borrow_mut() = RetirementSource::Prepared(sealed);
        self.verify_current_owner()
    }
}
