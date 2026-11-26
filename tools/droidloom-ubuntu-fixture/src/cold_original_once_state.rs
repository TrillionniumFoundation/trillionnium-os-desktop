//! Append-only recovery journal for one original-machine qualification attempt.
//!
//! An event records an observed transaction phase. It is never installation,
//! runtime, or application authority. Physical writers keep their separately
//! verified locks and revalidate the actual filesystem before/after mutation.
use crate::{Result, boot_files as files, ensure, fs, model::Identity};
use files::FilePin;
use rustix::fs::{FileType, Mode, OFlags, RenameFlags};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    fs::File,
    io::Write,
    path::{Path, PathBuf},
};

const SCHEMA: &str = "droidloom.original-once-event.v1";
const MAX_EVENTS: usize = 128;
const MAX_EVENT_BYTES: u64 = 1024 * 1024;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(super) enum Phase {
    Admitted,
    PublicInstallIntent,
    PublicInstalled,
    NativeInstallIntent,
    NativeInstalled,
    CellPublishIntent,
    CellPublished,
    PairExchangeIntent,
    PairExchanged,
    RecoveryInstallIntent,
    RecoveryInstalled,
    GrubPublishIntent,
    GrubPublished,
    LabelsIntent,
    LabelsApplied,
    SelectionPublishIntent,
    SelectionPublished,
    ArmIntent,
    Armed,
    RebootRequested,
    CandidateObserved,
    Collecting,
    Retiring,
    ReturnSelected,
    ReturnRebootRequested,
    OriginalReturned,
    SelectionWithdrawIntent,
    Aborting,
    SelectionWithdrawn,
    PairRestored,
    LabelsRestored,
    CellRestored,
    NativeRestored,
    PublicRestored,
    GrubRestored,
    Returned,
}

impl Phase {
    fn permits(self, next: Self) -> bool {
        use Phase::*;
        if next == Aborting {
            return !matches!(
                self,
                Aborting
                    | SelectionWithdrawn
                    | PairRestored
                    | LabelsRestored
                    | CellRestored
                    | NativeRestored
                    | PublicRestored
                    | GrubRestored
                    | Returned
            );
        }
        matches!(
            (self, next),
            (Admitted, PublicInstallIntent)
                | (PublicInstallIntent, PublicInstalled)
                | (PublicInstalled, NativeInstallIntent)
                | (NativeInstallIntent, NativeInstalled)
                | (NativeInstalled, CellPublishIntent)
                | (CellPublishIntent, CellPublished)
                | (CellPublished, PairExchangeIntent)
                | (PairExchangeIntent, PairExchanged)
                | (PairExchanged, RecoveryInstallIntent)
                | (RecoveryInstallIntent, RecoveryInstalled)
                | (RecoveryInstalled, GrubPublishIntent)
                | (GrubPublishIntent, GrubPublished)
                | (GrubPublished, LabelsIntent)
                | (LabelsIntent, LabelsApplied)
                | (LabelsApplied, SelectionPublishIntent)
                | (SelectionPublishIntent, SelectionPublished)
                | (SelectionPublished, ArmIntent)
                | (ArmIntent, Armed)
                | (Armed, RebootRequested)
                | (RebootRequested, CandidateObserved)
                | (CandidateObserved, Collecting)
                | (Collecting, Retiring)
                | (Retiring, ReturnSelected)
                | (ReturnSelected, ReturnRebootRequested)
                | (ReturnRebootRequested, OriginalReturned)
                | (OriginalReturned, SelectionWithdrawIntent)
                | (Aborting, SelectionWithdrawIntent)
                | (SelectionWithdrawIntent, SelectionWithdrawn)
                | (SelectionWithdrawn, PairRestored)
                | (PairRestored, LabelsRestored)
                | (LabelsRestored, CellRestored)
                | (CellRestored, NativeRestored)
                | (NativeRestored, PublicRestored)
                | (PublicRestored, GrubRestored)
                | (GrubRestored, Returned)
        )
    }
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Event {
    schema: String,
    candidate_id: String,
    intent_sha256: String,
    sequence: u32,
    previous_sha256: Option<String>,
    pub(super) phase: Phase,
    pub(super) boot_id: String,
    // Each payload has already been read from the real operation by its owner.
    // A JSON value here cannot construct OriginalQualificationAuthority.
    pub(super) observation: Value,
}

struct GuardedDirectory {
    path: PathBuf,
    held: File,
    identity: Identity,
}

impl GuardedDirectory {
    fn open(path: &Path) -> Result<Self> {
        let tree = fs::Tree::open(
            &fs::absolute_string(path)?,
            rustix::process::geteuid().as_raw(),
        )?;
        let identity = fs::stat(&tree.root)?;
        ensure(
            identity.mode & 0o7777 == 0o700,
            "once journal must be a private directory",
        )?;
        Ok(Self {
            path: path.to_owned(),
            held: tree.root,
            identity,
        })
    }

    fn revalidate(&self) -> Result<()> {
        let actual = fs::Tree::open(&fs::absolute_string(&self.path)?, self.identity.uid)?;
        for id in [fs::stat(&self.held)?, fs::stat(&actual.root)?] {
            ensure(
                id.dev == self.identity.dev
                    && id.ino == self.identity.ino
                    && id.uid == self.identity.uid
                    && id.gid == self.identity.gid
                    && id.mode == self.identity.mode
                    && id.nlink == self.identity.nlink,
                "once journal directory was replaced or changed ownership",
            )?;
        }
        Ok(())
    }

    fn durable_new(&self, name: &str, bytes: &[u8], sequence: usize) -> Result<()> {
        self.revalidate()?;
        ensure(
            bytes.len() as u64 <= MAX_EVENT_BYTES,
            "once event is too large",
        )?;
        let pending = format!("pending-{sequence:04}.json");
        let mut file = File::from(rustix::fs::openat(
            &self.held,
            pending.as_str(),
            OFlags::RDWR | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::from_raw_mode(0o600),
        )?);
        file.write_all(bytes)?;
        file.sync_all()?;
        let id = fs::stat(&file)?;
        ensure(
            id.nlink == 1
                && id.uid == self.identity.uid
                && id.gid == self.identity.gid
                && id.mode & 0o7777 == 0o600
                && id.size == bytes.len() as u64,
            "new once event inode has unexpected metadata",
        )?;
        use std::io::{Seek, SeekFrom};
        file.seek(SeekFrom::Start(0))?;
        ensure(
            fs::hash(&file)? == fs::digest(bytes),
            "new once event full readback differs",
        )?;
        rustix::fs::fchmod(&file, Mode::from_raw_mode(0o400))?;
        file.sync_all()?;
        rustix::fs::renameat_with(
            &self.held,
            pending.as_str(),
            &self.held,
            name,
            RenameFlags::NOREPLACE,
        )?;
        self.held.sync_all()?;
        self.revalidate()
    }

    fn preserve_pending(&self, name: &str, sequence: usize) -> Result<()> {
        self.revalidate()?;
        let file = File::from(rustix::fs::openat(
            &self.held,
            name,
            OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::CLOEXEC | OFlags::NONBLOCK,
            Mode::empty(),
        )?);
        let before = fs::stat(&file)?;
        ensure(
            FileType::from_raw_mode(before.mode) == FileType::RegularFile
                && before.uid == self.identity.uid
                && before.gid == self.identity.gid
                && before.nlink == 1
                && before.mode & 0o022 == 0
                && before.size <= MAX_EVENT_BYTES,
            "interrupted once event is not a bounded private ordinary inode",
        )?;
        let digest = fs::hash(&file)?;
        ensure(
            fs::stat(&file)? == before,
            "interrupted once event changed during preservation",
        )?;
        let destination = format!(
            "abandoned-{sequence:04}-{}-{}-{digest}.json",
            before.dev, before.ino
        );
        rustix::fs::renameat_with(
            &self.held,
            name,
            &self.held,
            destination.as_str(),
            RenameFlags::NOREPLACE,
        )?;
        self.held.sync_all()?;
        let after = fs::stat(&file)?;
        ensure(
            after.dev == before.dev
                && after.ino == before.ino
                && after.mode == before.mode
                && after.uid == before.uid
                && after.gid == before.gid
                && after.nlink == before.nlink
                && after.size == before.size
                && after.mtime_sec == before.mtime_sec
                && after.mtime_nsec == before.mtime_nsec,
            "preserved interrupted once event inode changed",
        )?;
        self.revalidate()
    }
}

pub(super) struct Journal {
    directory: GuardedDirectory,
    candidate_id: String,
    intent_sha256: String,
    events: Vec<(FilePin, Event, Identity, File)>,
}

impl Journal {
    pub(super) fn create(path: &Path, candidate_id: &str, intent_sha256: &str) -> Result<Self> {
        ensure(
            fs::valid_digest(candidate_id) && fs::valid_digest(intent_sha256),
            "invalid once journal binding",
        )?;
        files::private_dir(path)?;
        Ok(Self {
            directory: GuardedDirectory::open(path)?,
            candidate_id: candidate_id.into(),
            intent_sha256: intent_sha256.into(),
            events: Vec::new(),
        })
    }

    pub(super) fn reopen(path: &Path, candidate_id: &str, intent_sha256: &str) -> Result<Self> {
        ensure(
            fs::valid_digest(candidate_id) && fs::valid_digest(intent_sha256),
            "invalid once journal binding",
        )?;
        let directory = GuardedDirectory::open(path)?;
        let mut names = Vec::new();
        for entry in std::fs::read_dir(path)? {
            let entry = entry?;
            let name = entry
                .file_name()
                .into_string()
                .map_err(|_| "non-UTF8 once journal entry")?;
            ensure(
                names.len() < MAX_EVENTS * 3,
                "once journal entry bound exceeded",
            )?;
            names.push(name);
        }
        names.sort();
        let mut result = Self {
            directory,
            candidate_id: candidate_id.into(),
            intent_sha256: intent_sha256.into(),
            events: Vec::new(),
        };
        for name in names.iter().filter(|name| name.starts_with("event-")) {
            let index = result.events.len();
            ensure(
                index < MAX_EVENTS && *name == format!("event-{index:04}.json"),
                "once journal sequence has a gap",
            )?;
            let pin = files::pin_file(&path.join(name))?;
            let (held, id) = files::open_pin(&pin)?;
            ensure(
                id.uid == result.directory.identity.uid
                    && id.gid == result.directory.identity.gid
                    && id.nlink == 1
                    && id.mode & 0o7777 == 0o400,
                "once event ownership or mode changed",
            )?;
            let raw = files::read_pin(&pin, MAX_EVENT_BYTES)?;
            ensure(
                fs::stat(&held)? == id && files::open_pin(&pin)?.1 == id,
                "once event replaced during readback",
            )?;
            let event: Event = serde_json::from_slice(&raw)?;
            result.validate(&event)?;
            result.events.push((pin, event, id, held));
        }
        for name in names {
            if name.starts_with("event-") {
                continue;
            }
            if name.starts_with("abandoned-") {
                let parts: Vec<_> = name
                    .strip_suffix(".json")
                    .ok_or("abandoned event suffix")?
                    .split('-')
                    .collect();
                ensure(
                    parts.len() == 5
                        && parts[1].len() == 4
                        && parts[1].bytes().all(|b| b.is_ascii_digit())
                        && fs::valid_digest(parts[4]),
                    "malformed abandoned once event",
                )?;
                let file = File::from(rustix::fs::openat(
                    &result.directory.held,
                    name.as_str(),
                    OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC,
                    Mode::empty(),
                )?);
                let id = fs::stat(&file)?;
                ensure(
                    FileType::from_raw_mode(id.mode) == FileType::RegularFile
                        && id.nlink == 1
                        && id.uid == result.directory.identity.uid
                        && id.gid == result.directory.identity.gid
                        && id.mode & 0o022 == 0
                        && id.size <= MAX_EVENT_BYTES
                        && parts[2].parse::<u64>()? == id.dev
                        && parts[3].parse::<u64>()? == id.ino
                        && fs::hash(&file)? == parts[4]
                        && fs::stat(&file)? == id,
                    "preserved interrupted event inode or bytes changed",
                )?;
                continue;
            }
            let expected = format!("pending-{:04}.json", result.events.len());
            ensure(
                name == expected,
                "unlisted or out-of-order once journal entry",
            )?;
            result
                .directory
                .preserve_pending(&name, result.events.len())?;
        }
        result.directory.revalidate()?;
        Ok(result)
    }

    fn validate(&self, event: &Event) -> Result<()> {
        ensure(
            event.schema == SCHEMA
                && event.candidate_id == self.candidate_id
                && event.intent_sha256 == self.intent_sha256
                && event.sequence as usize == self.events.len(),
            "once event is not bound to this immutable intent",
        )?;
        ensure(
            valid_boot_id(&event.boot_id) && event.observation.is_object(),
            "invalid once event observation",
        )?;
        match self.events.last() {
            None => ensure(
                event.phase == Phase::Admitted && event.previous_sha256.is_none(),
                "once journal must begin with admission",
            ),
            Some((pin, previous, _, _)) => ensure(
                event.previous_sha256.as_ref() == Some(&pin.sha256)
                    && previous.phase.permits(event.phase),
                "once phase is out of order or its hash chain changed",
            ),
        }
    }

    pub(super) fn append(
        &mut self,
        phase: Phase,
        boot_id: &str,
        observation: Value,
    ) -> Result<FilePin> {
        ensure(self.events.len() < MAX_EVENTS, "once event count exceeded")?;
        self.revalidate()?;
        let event = Event {
            schema: SCHEMA.into(),
            candidate_id: self.candidate_id.clone(),
            intent_sha256: self.intent_sha256.clone(),
            sequence: self.events.len() as u32,
            previous_sha256: self.events.last().map(|(pin, _, _, _)| pin.sha256.clone()),
            phase,
            boot_id: boot_id.into(),
            observation,
        };
        self.validate(&event)?;
        let mut raw = serde_json::to_vec_pretty(&event)?;
        raw.push(b'\n');
        let name = format!("event-{:04}.json", self.events.len());
        self.directory.durable_new(&name, &raw, self.events.len())?;
        let pin = files::pin_file(&self.directory.path.join(name))?;
        ensure(
            pin.bytes == raw.len() as u64 && pin.sha256 == fs::digest(&raw),
            "published once event differs",
        )?;
        let held = files::checked_file(&pin)?;
        let id = fs::stat(&held)?;
        ensure(
            id.uid == self.directory.identity.uid
                && id.gid == self.directory.identity.gid
                && id.nlink == 1
                && id.mode & 0o7777 == 0o400,
            "published once event custody differs",
        )?;
        self.events.push((pin.clone(), event, id, held));
        Ok(pin)
    }

    pub(super) fn phase(&self) -> Option<Phase> {
        self.events.last().map(|(_, event, _, _)| event.phase)
    }

    pub(super) fn revalidate(&self) -> Result<()> {
        self.directory.revalidate()?;
        for (pin, _, id, held) in &self.events {
            ensure(
                fs::stat(held)? == *id && files::open_pin(pin)?.1 == *id,
                "held or named once event identity changed",
            )?;
            files::checked_file(pin)?;
        }
        Ok(())
    }
}

fn valid_boot_id(value: &str) -> bool {
    value.len() == 36
        && value.bytes().enumerate().all(|(i, b)| {
            if [8, 13, 18, 23].contains(&i) {
                b == b'-'
            } else {
                b.is_ascii_digit() || (b'a'..=b'f').contains(&b)
            }
        })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    const BOOT: &str = "7b39f717-0e21-4bbe-8365-b0d4f6fe04d3";
    fn identifiers() -> (String, String) {
        ("a".repeat(64), "b".repeat(64))
    }

    #[test]
    fn persisted_intent_chain_rejects_skipped_or_repeated_effects() -> Result<()> {
        let tmp = tempfile::tempdir()?;
        let path = tmp.path().join("journal");
        let (candidate, intent) = identifiers();
        let mut journal = Journal::create(&path, &candidate, &intent)?;
        journal.append(Phase::Admitted, BOOT, json!({"observed":"original"}))?;
        assert!(
            journal
                .append(Phase::PublicInstalled, BOOT, json!({}))
                .is_err()
        );
        journal.append(
            Phase::PublicInstallIntent,
            BOOT,
            json!({"snapshot":"fixed"}),
        )?;
        journal.append(Phase::PublicInstalled, BOOT, json!({"readback":"actual"}))?;
        let recovered = Journal::reopen(&path, &candidate, &intent)?;
        assert_eq!(recovered.phase(), Some(Phase::PublicInstalled));
        assert!(Journal::reopen(&path, &candidate, &"c".repeat(64)).is_err());
        assert!(
            journal
                .append(Phase::PublicInstalled, BOOT, json!({}))
                .is_err()
        );
        Ok(())
    }

    #[test]
    fn partial_prepublication_event_is_preserved_without_advancing_phase() -> Result<()> {
        let tmp = tempfile::tempdir()?;
        let path = tmp.path().join("journal");
        let (candidate, intent) = identifiers();
        let mut journal = Journal::create(&path, &candidate, &intent)?;
        journal.append(Phase::Admitted, BOOT, json!({}))?;
        files::write_new(&path.join("pending-0001.json"), b"{interrupted", 0o600)?;
        let mut recovered = Journal::reopen(&path, &candidate, &intent)?;
        assert_eq!(recovered.phase(), Some(Phase::Admitted));
        assert!(std::fs::read_dir(&path)?.any(|e| {
            e.unwrap()
                .file_name()
                .to_string_lossy()
                .starts_with("abandoned-0001-")
        }));
        recovered.append(
            Phase::Aborting,
            BOOT,
            json!({"partial_event_preserved":true}),
        )?;
        assert_eq!(
            Journal::reopen(&path, &candidate, &intent)?.phase(),
            Some(Phase::Aborting)
        );
        Ok(())
    }

    #[test]
    fn all_public_files_precede_labels_and_arm_is_the_last_separate_intent() -> Result<()> {
        let tmp = tempfile::tempdir()?;
        let path = tmp.path().join("journal");
        let (candidate, intent) = identifiers();
        let mut j = Journal::create(&path, &candidate, &intent)?;
        for phase in [
            Phase::Admitted,
            Phase::PublicInstallIntent,
            Phase::PublicInstalled,
            Phase::NativeInstallIntent,
            Phase::NativeInstalled,
            Phase::CellPublishIntent,
            Phase::CellPublished,
            Phase::PairExchangeIntent,
            Phase::PairExchanged,
        ] {
            j.append(phase, BOOT, json!({}))?;
        }
        assert!(j.append(Phase::LabelsIntent, BOOT, json!({})).is_err());
        for phase in [
            Phase::RecoveryInstallIntent,
            Phase::RecoveryInstalled,
            Phase::GrubPublishIntent,
            Phase::GrubPublished,
            Phase::LabelsIntent,
            Phase::LabelsApplied,
            Phase::SelectionPublishIntent,
            Phase::SelectionPublished,
        ] {
            j.append(phase, BOOT, json!({}))?;
        }
        assert!(j.append(Phase::Armed, BOOT, json!({})).is_err());
        j.append(Phase::ArmIntent, BOOT, json!({"next_entry_before":""}))?;
        let mut recovered = Journal::reopen(&path, &candidate, &intent)?;
        assert_eq!(recovered.phase(), Some(Phase::ArmIntent));
        assert!(
            recovered
                .append(Phase::RebootRequested, BOOT, json!({}))
                .is_err()
        );
        recovered.append(Phase::Armed, BOOT, json!({"actual_next_entry":"test-only"}))?;
        Ok(())
    }

    #[test]
    fn withdrawal_intent_survives_interruption_before_any_restore() -> Result<()> {
        assert!(!Phase::OriginalReturned.permits(Phase::SelectionWithdrawn));
        assert!(Phase::OriginalReturned.permits(Phase::SelectionWithdrawIntent));
        assert!(!Phase::SelectionWithdrawIntent.permits(Phase::PairRestored));
        let tmp = tempfile::tempdir()?;
        let path = tmp.path().join("journal");
        let (candidate, intent) = identifiers();
        let mut j = Journal::create(&path, &candidate, &intent)?;
        j.append(Phase::Admitted, BOOT, json!({}))?;
        j.append(Phase::Aborting, BOOT, json!({"test_interruption":true}))?;
        assert!(
            j.append(Phase::SelectionWithdrawn, BOOT, json!({}))
                .is_err()
        );
        j.append(
            Phase::SelectionWithdrawIntent,
            BOOT,
            json!({"preimage":"exact"}),
        )?;
        let mut recovered = Journal::reopen(&path, &candidate, &intent)?;
        assert_eq!(recovered.phase(), Some(Phase::SelectionWithdrawIntent));
        assert!(
            recovered
                .append(Phase::PairRestored, BOOT, json!({}))
                .is_err()
        );
        recovered.append(
            Phase::SelectionWithdrawn,
            BOOT,
            json!({"readback":"test-only"}),
        )?;
        assert_eq!(
            Journal::reopen(&path, &candidate, &intent)?.phase(),
            Some(Phase::SelectionWithdrawn)
        );
        Ok(())
    }

    #[test]
    fn changing_published_event_or_directory_is_rejected() -> Result<()> {
        let tmp = tempfile::tempdir()?;
        let path = tmp.path().join("journal");
        let (candidate, intent) = identifiers();
        let mut journal = Journal::create(&path, &candidate, &intent)?;
        let first = journal.append(Phase::Admitted, BOOT, json!({}))?;
        std::fs::rename(&path, tmp.path().join("retained"))?;
        files::private_dir(&path)?;
        assert!(journal.revalidate().is_err());
        std::fs::remove_dir(&path)?;
        std::fs::rename(tmp.path().join("retained"), &path)?;
        let mut event: Value = serde_json::from_slice(&files::read_pin(&first, MAX_EVENT_BYTES)?)?;
        event["candidate_id"] = json!("c".repeat(64));
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&first.path, std::fs::Permissions::from_mode(0o600))?;
        std::fs::write(&first.path, serde_json::to_vec(&event)?)?;
        std::fs::set_permissions(&first.path, std::fs::Permissions::from_mode(0o400))?;
        assert!(Journal::reopen(&path, &candidate, &intent).is_err());
        Ok(())
    }
}
