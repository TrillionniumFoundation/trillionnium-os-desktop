//! Fixed working-boot file publication with the actual cold source owner.
//!
//! This is separate from the old once authority. It installs one working
//! initrd and one working-only menuentry, retaining every original inode for
//! an exact reverse. It does not arm grubenv or construct a selected-pair proof.
#[path = "cold_working_file_custody.rs"]
mod custody;
use super::super::{
    materials::Guard,
    working_runtime::{WorkingGrubSource, WorkingRuntimeSources},
};
use super::{Node, observe_kind, working::PublishedWorkingRuntime};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_working_recovery::contract as c,
    ensure, fs,
};
use std::{
    fs::File,
    path::{Path, PathBuf},
};

const CUSTOM: &str = "/boot/grub/custom.cfg";
const BASE: &str = "/boot/droidloom/working-qualification";
const ENTRY_PREFIX: &str = "droidloom-working-qualification-";

fn entry_id(candidate: &str) -> Result<String> {
    ensure(
        fs::valid_digest(candidate),
        "one full working boot candidate required",
    )?;
    Ok(format!("{ENTRY_PREFIX}{candidate}"))
}
fn initrd_target(candidate: &str) -> Result<PathBuf> {
    entry_id(candidate)?;
    Ok(Path::new(BASE).join(candidate).join("initrd.img"))
}

/// Inputs come only from WorkingRuntimeSources. This validation also keeps the
/// GRUB language boundary explicit rather than relying on shell-like escaping.
fn menuentry(original: &[u8], candidate: &str, arguments: &str) -> Result<Vec<u8>> {
    let id = entry_id(candidate)?;
    ensure(
        original.len() <= 1024 * 1024,
        "bounded original custom GRUB source required",
    )?;
    let text = std::str::from_utf8(original)?;
    ensure(
        !text.contains('\0')
            && !text.contains(ENTRY_PREFIX)
            && !text.contains("droidloom-original-once-"),
        "custom GRUB already contains an unresolved qualification entry",
    )?;
    c::boot_arguments(arguments)?;
    ensure(
        !arguments.is_empty()
            && arguments
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b" =_,-./:".contains(&b))
            && arguments
                .split_whitespace()
                .all(|a| !a.starts_with("systemd.unit=") && !a.starts_with("rd.systemd.unit=")),
        "working GRUB arguments contain another target or GRUB syntax",
    )?;
    let initrd = initrd_target(candidate)?;
    let entry = format!(
        "\nmenuentry 'Droidloom working qualification' --id '{id}' {{\n  search --no-floppy --fs-uuid --set=root {}\n  linux /boot/droidloom/kernels/{}/vmlinuz {arguments}\n  initrd {}\n}}\n",
        c::ROOT_UUID,
        c::KERNEL_SHA,
        fs::absolute_string(&initrd)?
    );
    let mut bytes = original.to_vec();
    bytes.extend_from_slice(entry.as_bytes());
    Ok(bytes)
}

fn source_file(path: &Path, bytes: &[u8]) -> Result<Guard> {
    files::write_new(path, bytes, 0o400)?;
    File::open(path.parent().ok_or("working boot source parent")?)?.sync_all()?;
    Guard::open(&files::pin_file(path)?)
}

struct Publication {
    runtime: PublishedWorkingRuntime,
    grub: WorkingGrubSource,
    transaction: custody::Transaction,
    sources: Vec<Guard>,
    original_custom: Option<Node>,
    original_observed: bool,
    candidate: String,
    initrd: PathBuf,
}
impl Publication {
    fn source(&self) -> &WorkingRuntimeSources {
        self.runtime.source()
    }
    fn guard_source(&self) -> Result<()> {
        self.runtime.guard()?;
        self.grub.require_sources(self.source())?;
        for source in &self.sources {
            source.revalidate()?;
        }
        self.runtime.guard()
    }
    fn publish(&mut self) -> Result<FilePin> {
        self.guard_source()?;
        ensure(
            self.source().pair_exchanged(&self.runtime)?,
            "working boot files require the actual fully exchanged data pair",
        )?;
        for path in ["/boot", "/boot/grub", "/boot/droidloom"] {
            fs::Tree::open("/", 0)?.dir(path)?;
        }
        let kernel = files::pin_file(
            &Path::new("/boot/droidloom/kernels")
                .join(c::KERNEL_SHA)
                .join("vmlinuz"),
        )?;
        ensure(
            kernel.sha256 == c::KERNEL_SHA && (1024..=128 * 1024 * 1024).contains(&kernel.bytes),
            "actual installed shared kernel differs from the working source",
        )?;
        self.sources.push(Guard::open(&kernel)?);
        self.original_custom = observe_kind(Path::new(CUSTOM), false)?;
        let original = match self.original_custom.as_ref() {
            Some(node) => {
                ensure(
                    node.link.is_none() && node.identity.mode & 0o170000 == 0o100000,
                    "working custom GRUB preimage is not a regular file",
                )?;
                let pin = files::pin_file(Path::new(CUSTOM))?;
                ensure(
                    pin.bytes == node.identity.size && node.sha256.as_ref() == Some(&pin.sha256),
                    "custom GRUB source changed during capture",
                )?;
                let bytes = files::read_pin(&pin, 1024 * 1024)?;
                ensure(
                    observe_kind(Path::new(CUSTOM), false)? == self.original_custom,
                    "custom GRUB full preimage changed while read",
                )?;
                bytes
            }
            None => Vec::new(),
        };
        self.original_observed = true;
        let body = menuentry(&original, &self.candidate, self.source().arguments())?;
        let custom = source_file(&self.source().work().join("WORKING-CUSTOM-GRUB.cfg"), &body)?;
        let custom_pin = custom.pin().clone();
        self.sources.push(custom);

        self.transaction.initialize()?;
        match std::fs::symlink_metadata(BASE) {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                self.transaction.stage_directory(Path::new(BASE))?;
            }
            Err(e) => return Err(e.into()),
            Ok(_) => {
                fs::Tree::open("/", 0)?.dir(BASE)?;
            }
        }
        let candidate_directory = self.initrd.parent().ok_or("working initrd parent")?;
        match std::fs::symlink_metadata(candidate_directory) {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
            Err(e) => return Err(e.into()),
            Ok(_) => return Err("working boot candidate directory must be newly owned".into()),
        }
        self.transaction.stage_directory(candidate_directory)?;
        let initrd_source = self.source().recovery_initrd().clone();
        self.transaction
            .stage_file(&self.initrd, &initrd_source, 0o400)?;
        self.transaction
            .stage_file(Path::new(CUSTOM), &custom_pin, 0o644)?;
        ensure(
            (3..=4).contains(&self.transaction.len()),
            "working boot file roster differs",
        )?;
        let lookup = self
            .source()
            .work()
            .join("working-grub-files/normal-contexts");
        files::private_dir(&lookup)?;
        File::open(lookup.parent().ok_or("working boot lookup parent")?)?.sync_all()?;
        let (contexts, record) = crate::cold_original_data::labels::lookup_held_runtime_contexts(
            self.source().label_sources(),
            &self.transaction.lookup_entries(),
            &lookup,
        )?;
        self.transaction.retain_seal(&record)?;
        self.transaction.apply_labels(&contexts)?;
        for index in 0..self.transaction.len() {
            self.guard_source()?;
            if self.transaction.target(index) == Path::new(CUSTOM) {
                ensure(
                    self.original_observed,
                    "working GRUB preimage was not observed",
                )?;
                self.transaction
                    .publish_captured(index, self.original_custom.as_ref())?;
            } else {
                // Both directories and the candidate initrd must be absent.
                self.transaction.publish_captured(index, None)?;
            }
            self.guard_source()?;
        }
        self.transaction.guard()?;
        self.guard_source()?;
        self.transaction.seal_summary(false)
    }
    fn restore(&mut self) -> Result<Option<FilePin>> {
        // Admission and staging failures cannot strand the already published
        // runtime behind an absent private summary directory. This fact comes
        // from the transaction states before any rename syscall, not a caller
        // assertion or a report. Transfer the same runtime owner back without
        // touching private or public paths. Any attempted effect uses the full
        // reconciliation and reverse path below.
        if self.transaction.never_published() {
            return Ok(None);
        }
        self.guard_source()?;
        self.transaction.reconcile_pending()?;
        for index in (0..self.transaction.len()).rev() {
            self.guard_source()?;
            self.transaction.restore(index)?;
        }
        ensure(
            self.transaction.all_restored(),
            "working boot reverse incomplete",
        )?;
        self.transaction.guard()?;
        self.guard_source()?;
        self.transaction.seal_summary(true).map(Some)
    }
}

/// A successful physical boot-file publication. The existing working runtime
/// owner is retained here, not recreated from the summary or boot arguments.
pub(crate) struct PublishedWorkingBootFiles {
    publication: Publication,
    summary: FilePin,
}
pub(crate) struct WorkingBootPublicationFailure {
    publication: Publication,
    errors: Vec<String>,
}
pub(crate) struct RestoredWorkingBootFiles {
    publication: Publication,
    summary: Option<FilePin>,
}
impl PublishedWorkingBootFiles {
    pub(crate) fn publish(
        runtime: PublishedWorkingRuntime,
        grub: WorkingGrubSource,
    ) -> std::result::Result<Self, WorkingBootPublicationFailure> {
        let source = runtime.source();
        let candidate = source.candidate().to_owned();
        let initrd = Path::new(BASE).join(&candidate).join("initrd.img");
        let transaction =
            custody::Transaction::new(source.work().join("working-grub-files"), candidate.clone());
        let mut publication = Publication {
            runtime,
            grub,
            transaction,
            sources: Vec::new(),
            original_custom: None,
            original_observed: false,
            candidate,
            initrd,
        };
        match publication.publish() {
            Ok(summary) => Ok(Self {
                publication,
                summary,
            }),
            Err(error) => Err(WorkingBootPublicationFailure {
                publication,
                errors: vec![error.to_string()],
            }),
        }
    }
    pub(crate) fn runtime(&self) -> &PublishedWorkingRuntime {
        &self.publication.runtime
    }
    pub(crate) fn summary(&self) -> &FilePin {
        &self.summary
    }
    pub(crate) fn entry_id(&self) -> Result<String> {
        entry_id(&self.publication.candidate)
    }
    pub(crate) fn guard(&self) -> Result<()> {
        self.publication.guard_source()?;
        ensure(
            self.publication.transaction.all_published(),
            "working boot files unpublished",
        )?;
        self.publication.transaction.guard()
    }
    pub(crate) fn restore(
        self,
    ) -> std::result::Result<RestoredWorkingBootFiles, WorkingBootPublicationFailure> {
        restore(self.publication, Vec::new())
    }
}
impl WorkingBootPublicationFailure {
    pub(crate) fn errors(&self) -> &[String] {
        &self.errors
    }
    pub(crate) fn runtime(&self) -> &PublishedWorkingRuntime {
        &self.publication.runtime
    }
    pub(crate) fn restore(self) -> std::result::Result<RestoredWorkingBootFiles, Self> {
        restore(self.publication, self.errors)
    }
}
impl RestoredWorkingBootFiles {
    pub(crate) fn guard(&self) -> Result<()> {
        self.publication.guard_source()?;
        ensure(
            self.publication.transaction.all_restored(),
            "working boot files unrestored",
        )?;
        self.publication.transaction.guard()
    }
    pub(crate) fn summary(&self) -> Option<&FilePin> {
        self.summary.as_ref()
    }
    /// Transfer the same owner without a fallible gap. A later source drift
    /// must be handled by the receiver while it still owns the runtime pair.
    pub(crate) fn into_runtime(self) -> (PublishedWorkingRuntime, WorkingGrubSource) {
        (self.publication.runtime, self.publication.grub)
    }
}
fn restore(
    mut publication: Publication,
    mut errors: Vec<String>,
) -> std::result::Result<RestoredWorkingBootFiles, WorkingBootPublicationFailure> {
    match publication.restore() {
        Ok(summary) => Ok(RestoredWorkingBootFiles {
            publication,
            summary,
        }),
        Err(error) => {
            let message = error.to_string();
            if errors.last() != Some(&message) {
                if errors.len() >= 32 {
                    errors.remove(1);
                }
                errors.push(message);
            }
            Err(WorkingBootPublicationFailure {
                publication,
                errors,
            })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn arguments() -> String {
        format!(
            "root=UUID={} ro rootwait init=/usr/lib/droidloom/board-init lsm=lockdown,capability,landlock,yama,selinux,apparmor,bpf,ima,evm enforcing=1 selinux=1 audit=1 panic=10 systemd.wants={} droidloom.working={} droidloom.working.config={} droidloom.working.return={}{}",
            c::ROOT_UUID,
            c::WORKING_TARGET,
            "a".repeat(64),
            "b".repeat(64),
            "c".repeat(64),
            c::PACKAGE_WRITERS
                .iter()
                .chain(c::SUSPEND_TARGETS.iter())
                .map(|s| format!(" systemd.mask={s}"))
                .collect::<String>()
        )
    }
    #[test]
    fn working_grub_entry_preserves_original_and_binds_distinct_boot_namespace() -> Result<()> {
        let original = b"# retained original custom entries\n";
        let candidate = "d".repeat(64);
        let value = menuentry(original, &candidate, &arguments())?;
        assert!(value.starts_with(original));
        let text = std::str::from_utf8(&value)?;
        assert!(text.contains(&format!("--id '{}'", entry_id(&candidate)?)));
        assert!(text.contains(&format!("initrd {}", initrd_target(&candidate)?.display())));
        assert!(text.contains(&format!(
            "linux /boot/droidloom/kernels/{}/vmlinuz",
            c::KERNEL_SHA
        )));
        assert!(!text.contains("droidloom-original-once-"));
        assert!(!text.contains("systemd.unit="));
        assert_eq!(text.matches("menuentry ").count(), 1);
        Ok(())
    }
    #[test]
    fn working_grub_entry_rejects_unresolved_entries_and_language_injection() {
        let candidate = "d".repeat(64);
        for old in [
            "menuentry x --id droidloom-original-once-a {}",
            "menuentry x --id droidloom-working-qualification-a {}",
            "bad\0input",
        ] {
            assert!(menuentry(old.as_bytes(), &candidate, &arguments()).is_err());
        }
        for extra in [
            "; reboot",
            "\nreboot",
            "' }",
            " systemd.unit=evil.target",
            " rd.systemd.unit=evil.target",
        ] {
            assert!(menuentry(b"", &candidate, &format!("{}{}", arguments(), extra)).is_err());
        }
        for candidate in ["", "../working", "short", "x".repeat(64).as_str()] {
            assert!(menuentry(b"", candidate, &arguments()).is_err());
        }
    }
}
