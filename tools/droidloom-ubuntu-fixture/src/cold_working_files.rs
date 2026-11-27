//! Fixed normal runtime publication for a real cold working qualification.
//! Source ownership is consumed, old inodes stay held, and every failure retains
//! the live owner and all transaction descriptors for an exact reverse.
#[path = "cold_working_file_custody.rs"]
mod custody;
use super::super::working_runtime::{WorkingOriginalCellPreimage, WorkingRuntimeSources};
use crate::{
    boot_files::{self as files, FilePin},
    cold_original_data::labels::WorkingLabelBatch,
    cold_working_recovery::contract as c,
    ensure, fs, Result,
};
use std::{
    collections::BTreeMap,
    fs::File,
    path::{Path, PathBuf},
};

const CREATED_PARENTS: [&str; 3] = [
    "/etc/droidloom/qualification",
    "/etc/droidloom/host-mac",
    "/etc/droidloom-maintenance",
];

fn roster() -> BTreeMap<PathBuf, u32> {
    let mut result = BTreeMap::from([
        (PathBuf::from("/etc/droidloom/cell.json"), 0o644),
        (
            PathBuf::from("/etc/droidloom/container-launcher.json"),
            0o644,
        ),
        (PathBuf::from(c::INSTALLATION), 0o400),
        (PathBuf::from(c::EARLY_CONFIG), 0o400),
        (PathBuf::from(c::RETURN_CONFIG), 0o400),
        (PathBuf::from(c::retained_data::INPUT_PATH), 0o400),
    ]);
    for name in [
        "contract.json",
        "manager-label.json",
        "policy.bin",
        "policy-export.bin",
        "derivation.json",
    ] {
        result.insert(Path::new("/etc/droidloom/host-mac").join(name), 0o400);
    }
    for name in [c::PARENT_UNIT, c::RETURN_UNIT, c::WORKING_TARGET] {
        result.insert(Path::new("/usr/lib/systemd/system").join(name), 0o644);
    }
    result
}
fn verify_roster<'a>(entries: impl IntoIterator<Item = (&'a Path, u32)>) -> Result<()> {
    let mut actual = BTreeMap::new();
    for (path, mode) in entries {
        ensure(
            actual.insert(path.to_owned(), mode).is_none(),
            "working runtime has a duplicate target",
        )?;
    }
    ensure(
        actual.len() == 14 && actual == roster(),
        "working runtime differs from the fixed fourteen normal target/mode pairs",
    )
}

struct Publication {
    source: WorkingRuntimeSources,
    // Retains the actual original Guard and the same Rc owner. Its named-path
    // validator is used only before the actual cell exchange, never refreshed.
    cell: WorkingOriginalCellPreimage,
    transaction: custody::Transaction,
}
impl Publication {
    fn publish(&mut self) -> Result<FilePin> {
        ensure(
            rustix::process::geteuid().is_root() && rustix::process::getegid().as_raw() == 0,
            "working publication requires the actual original root owner",
        )?;
        self.cell.require_sources(&self.source)?;
        verify_roster(self.source.entries().iter().map(|e| (e.target(), e.mode())))?;
        for path in ["/etc", "/etc/droidloom", "/usr/lib/systemd/system"] {
            fs::Tree::open("/", 0)?.dir(path)?;
        }
        self.transaction.initialize()?;
        for parent in CREATED_PARENTS {
            match std::fs::symlink_metadata(parent) {
                Ok(_) => {
                    fs::Tree::open("/", 0)?.dir(parent)?;
                }
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                    self.transaction.stage_directory(Path::new(parent))?
                }
                Err(error) => return Err(error.into()),
            }
        }
        for entry in self.source.entries() {
            self.transaction
                .stage_file(entry.target(), entry.source_pin(), entry.mode())?;
        }
        let lookup = self
            .source
            .work()
            .join("working-runtime-files")
            .join("normal-contexts");
        files::private_dir(&lookup)?;
        File::open(lookup.parent().ok_or("working context work parent")?)?.sync_all()?;
        let (contexts, record) = crate::cold_original_data::labels::lookup_held_runtime_contexts(
            self.source.label_sources(),
            &self.transaction.lookup_entries(),
            &lookup,
        )?;
        self.transaction.retain_seal(&record)?;
        self.transaction.apply_labels(&contexts)?;
        self.cell.require_sources(&self.source)?;
        // Every private inode has its actual normal context before any public
        // rename. Later full-root label batches may advance only held parent
        // differences proved by their actual source-owned inode transitions.
        for index in 0..self.transaction.len() {
            self.source.revalidate()?;
            self.transaction.guard()?;
            if self.transaction.target(index) == Path::new("/etc/droidloom/cell.json") {
                self.cell.require_sources(&self.source)?;
                self.transaction
                    .require_original(index, self.cell.identity(), self.cell.pin())?;
            }
            self.transaction.publish(index)?;
            self.source.revalidate()?;
        }
        self.source.revalidate()?;
        self.transaction.seal_summary(false)
    }
    fn restore(&mut self) -> Result<Option<FilePin>> {
        self.source.revalidate()?;
        if self.transaction.never_published() {
            // Staging is private. A failed admission cannot require a summary
            // directory which was never created or keep installed packages
            // stranded behind a nonexistent runtime reverse record.
            self.cell.require_sources(&self.source)?;
            return Ok(None);
        }
        self.transaction.reconcile_pending()?;
        for index in (0..self.transaction.len()).rev() {
            self.source.revalidate()?;
            self.transaction.restore(index)?;
            self.source.revalidate()?;
        }
        ensure(
            self.transaction.all_restored(),
            "working runtime reverse is incomplete",
        )?;
        self.transaction.guard()?;
        self.transaction.seal_summary(true).map(Some)
    }
}

/// Only the source-consuming publisher constructs this object. A report or
/// matching file body cannot construct published working runtime authority.
pub(crate) struct PublishedWorkingRuntime {
    publication: Publication,
    summary: FilePin,
}
/// A failed operation keeps the same actual cold owner, original four OFDs,
//  staged and original inodes, intents, and exact parent history.
pub(crate) struct WorkingPublicationFailure {
    publication: Publication,
    errors: Vec<String>,
}
pub(crate) struct RestoredWorkingRuntime {
    publication: Publication,
    summary: Option<FilePin>,
}
impl PublishedWorkingRuntime {
    pub(crate) fn publish(
        source: WorkingRuntimeSources,
        cell: WorkingOriginalCellPreimage,
    ) -> std::result::Result<Self, WorkingPublicationFailure> {
        let transaction = custody::Transaction::new(
            source.work().join("working-runtime-files"),
            source.candidate().into(),
        );
        let mut publication = Publication {
            source,
            cell,
            transaction,
        };
        match publication.publish() {
            Ok(summary) => Ok(Self {
                publication,
                summary,
            }),
            Err(error) => Err(WorkingPublicationFailure {
                publication,
                errors: vec![error.to_string()],
            }),
        }
    }
    pub(crate) fn source(&self) -> &WorkingRuntimeSources {
        &self.publication.source
    }
    pub(crate) fn summary(&self) -> &FilePin {
        &self.summary
    }
    pub(crate) fn guard_label_custody(&self) -> Result<()> {
        self.publication.source.revalidate_label_custody()?;
        ensure(self.publication.transaction.all_published(), "working label window lost runtime publication")?;
        self.publication.transaction.guard_label_custody()?;
        self.publication.source.revalidate_label_custody()
    }
    pub(crate) fn guard(&self) -> Result<()> {
        self.publication.source.revalidate()?;
        ensure(
            self.publication.transaction.all_published(),
            "working runtime is not fully published",
        )?;
        self.publication.transaction.guard()?;
        self.publication.source.revalidate()
    }
    /// Accept the same live owner's completed label batch after source and
    /// GRUB custody have accepted it. The window driver performs the final
    /// source-wide guards only after every consumer has advanced this batch.
    pub(crate) fn accept_working_label_batch(&mut self, batch: &WorkingLabelBatch) -> Result<()> {
        batch.require_source(&self.publication.source)?;
        self.publication
            .transaction
            .accept_working_label_batch(batch)
    }
    pub(crate) fn restore(
        self,
    ) -> std::result::Result<RestoredWorkingRuntime, WorkingPublicationFailure> {
        restore(self.publication, Vec::new())
    }
}
impl WorkingPublicationFailure {
    pub(crate) fn errors(&self) -> &[String] {
        &self.errors
    }
    pub(crate) fn source(&self) -> &WorkingRuntimeSources {
        &self.publication.source
    }
    /// Reconcile only the one recorded operation against the retained actual
    /// inodes. An unresolved effect blocks reverse and is never repeated.
    pub(crate) fn restore(self) -> std::result::Result<RestoredWorkingRuntime, Self> {
        restore(self.publication, self.errors)
    }
}
impl RestoredWorkingRuntime {
    pub(crate) fn source(&self) -> &WorkingRuntimeSources {
        &self.publication.source
    }
    pub(crate) fn summary(&self) -> Option<&FilePin> {
        self.summary.as_ref()
    }
    pub(crate) fn guard(&self) -> Result<()> {
        self.publication.source.revalidate()?;
        if self.summary.is_none() {
            ensure(
                self.publication.transaction.never_published(),
                "missing runtime reverse record after an actual public attempt",
            )?;
            return self
                .publication
                .cell
                .require_sources(&self.publication.source);
        }
        ensure(
            self.publication.transaction.all_restored(),
            "working runtime original restoration incomplete",
        )?;
        self.publication.transaction.guard()?;
        self.publication.source.revalidate()
    }
    /// The caller completes guard() before transferring this same source into
    /// normal package reverse. Package scripts subsequently change their own
    /// directory entries, so the retired runtime parent checkpoint is not
    /// falsely refreshed or reused as a post-package snapshot.
    pub(crate) fn into_source(self) -> (WorkingRuntimeSources, Option<FilePin>) {
        (self.publication.source, self.summary)
    }
}
fn restore(
    mut publication: Publication,
    mut errors: Vec<String>,
) -> std::result::Result<RestoredWorkingRuntime, WorkingPublicationFailure> {
    match publication.restore() {
        Ok(summary) => Ok(RestoredWorkingRuntime {
            publication,
            summary,
        }),
        Err(error) => {
            let message = error.to_string();
            if errors.last() != Some(&message) {
                // A retained owner can keep reconciling after a long external
                // failure. Preserve the initial cause and bounded recent
                // diagnostics without allowing that custody to grow forever.
                if errors.len() >= 32 {
                    errors.remove(1);
                }
                errors.push(message);
            }
            Err(WorkingPublicationFailure {
                publication,
                errors,
            })
        }
    }
}
impl std::fmt::Debug for WorkingPublicationFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("WorkingPublicationFailure")
            .field("candidate", &self.publication.source.candidate())
            .field("errors", &self.errors)
            .finish_non_exhaustive()
    }
}
impl std::fmt::Display for WorkingPublicationFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "working publication retains recovery custody: {}",
            self.errors.join("; ")
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fixed_working_roster_rejects_missing_duplicate_foreign_and_wrong_mode() {
        let expected = roster();
        assert_eq!(expected.len(), 14);
        assert_eq!(
            expected.get(Path::new(c::retained_data::INPUT_PATH)),
            Some(&0o400)
        );
        verify_roster(expected.iter().map(|(p, m)| (p.as_path(), *m))).unwrap();
        let mut missing = expected.clone();
        missing.remove(Path::new(c::EARLY_CONFIG));
        assert!(verify_roster(missing.iter().map(|(p, m)| (p.as_path(), *m))).is_err());
        let mut wrong = expected.clone();
        wrong.insert(PathBuf::from(c::RETURN_CONFIG), 0o644);
        assert!(verify_roster(wrong.iter().map(|(p, m)| (p.as_path(), *m))).is_err());
        let mut foreign = expected.clone();
        let mode = foreign.remove(Path::new(c::EARLY_CONFIG)).unwrap();
        foreign.insert(
            PathBuf::from("/etc/droidloom/qualification/early.json"),
            mode,
        );
        assert!(verify_roster(foreign.iter().map(|(p, m)| (p.as_path(), *m))).is_err());
        let mut duplicate = expected
            .iter()
            .map(|(p, m)| (p.as_path(), *m))
            .collect::<Vec<_>>();
        duplicate.push((Path::new(c::EARLY_CONFIG), 0o400));
        assert!(verify_roster(duplicate).is_err());
        assert!(
            expected
                .keys()
                .filter(|p| p.starts_with("/usr/lib/systemd/system"))
                .count()
                == 3
        );
        assert!(!expected
            .keys()
            .any(|p| p.starts_with("/etc/systemd/system")));
    }
}
