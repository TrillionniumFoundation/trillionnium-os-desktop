use crate::{AnyError, JOURNAL_PATH, JOURNAL_ROOT, invalid};
use hepta_session_core::{
    JournalId, JournalOpenPolicy, ReceiptEffectClass, ReceiptJournal, ReceiptLifecycleState,
};
use std::fs;
use std::io;
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

const JOURNAL_ID: JournalId = JournalId([0xd3; 16]);

pub(crate) fn configured_path() -> Result<PathBuf, AnyError> {
    let path = std::env::var_os("HEPTA_D3_RECEIPT_JOURNAL")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(JOURNAL_PATH));
    validate_journal_path(&path)?;
    Ok(path)
}

pub(crate) fn validate_journal_path(path: &Path) -> Result<(), AnyError> {
    if !path.is_absolute()
        || path
            .components()
            .any(|component| matches!(component, Component::ParentDir))
        || !path.starts_with(JOURNAL_ROOT)
        || path == Path::new(JOURNAL_ROOT)
        || path.file_name().is_none()
    {
        return Err(invalid("receipt journal path escapes the development root").into());
    }
    Ok(())
}

pub(crate) fn open_or_create(path: &Path) -> Result<ReceiptJournal, AnyError> {
    ensure_parent(path)?;
    let mut journal = if path.exists() {
        ReceiptJournal::open(path, JournalOpenPolicy::RECOVER_CRASH)?
    } else {
        ReceiptJournal::create(path, JOURNAL_ID, wall_clock_unix_ms()?)?
    };
    let report = journal.inspect()?;
    if report.header.journal_id != JOURNAL_ID || report.header.segment_number != 1 {
        return Err(invalid("receipt journal identity or segment chain is invalid").into());
    }
    Ok(journal)
}

pub(crate) fn reconcile_unresolved(journal: &mut ReceiptJournal) -> Result<usize, AnyError> {
    let report = journal.inspect()?;
    let mut clock = journal.last_monotonic_ms();
    let mut count = 0_usize;
    for unresolved in report.unresolved {
        let source = report
            .records
            .iter()
            .rev()
            .find(|record| record.event.receipt_id == unresolved.receipt_id)
            .ok_or_else(|| invalid("unresolved receipt has no source record"))?;
        let mut terminal = source.event.clone();
        terminal.lifecycle = if unresolved.last_state == ReceiptLifecycleState::Dispatched
            && unresolved.effect_class == ReceiptEffectClass::PotentialExternalEffect
        {
            ReceiptLifecycleState::Indeterminate
        } else {
            ReceiptLifecycleState::Interrupted
        };
        terminal.outcome = None;
        terminal.response_sha256 = None;
        terminal.error_code = Some(
            if terminal.lifecycle == ReceiptLifecycleState::Indeterminate {
                "browser_crashed"
            } else {
                "internal"
            }
            .to_owned(),
        );
        terminal.detail = Some("reconciled_after_sessiond_restart".to_owned());
        clock = clock
            .checked_add(1)
            .ok_or_else(|| invalid("receipt logical clock exhausted"))?;
        terminal.monotonic_ms = clock;
        terminal.wall_clock_unix_ms = wall_clock_unix_ms()?;
        journal.append(terminal)?;
        count = count
            .checked_add(1)
            .ok_or_else(|| invalid("receipt reconciliation count overflowed"))?;
    }
    Ok(count)
}

fn ensure_parent(path: &Path) -> Result<(), AnyError> {
    let parent = path
        .parent()
        .ok_or_else(|| invalid("receipt journal has no parent"))?;
    let mut current = PathBuf::new();
    for component in parent.components() {
        match component {
            Component::RootDir => current.push(component.as_os_str()),
            Component::CurDir => {}
            Component::Normal(name) => {
                current.push(name);
                match fs::symlink_metadata(&current) {
                    Ok(metadata) => validate_directory(&metadata)?,
                    Err(error) if error.kind() == io::ErrorKind::NotFound => {
                        fs::create_dir(&current)?;
                        validate_directory(&fs::symlink_metadata(&current)?)?;
                    }
                    Err(error) => return Err(error.into()),
                }
            }
            Component::ParentDir | Component::Prefix(_) => {
                return Err(invalid("receipt journal parent is unsafe").into());
            }
        }
    }
    Ok(())
}

fn validate_directory(metadata: &fs::Metadata) -> Result<(), AnyError> {
    let mode = metadata.permissions().mode();
    let root_sticky = metadata.uid() == 0 && mode & 0o1000 != 0;
    if metadata.file_type().is_symlink()
        || !metadata.is_dir()
        || (mode & 0o022 != 0 && !root_sticky)
    {
        return Err(invalid("receipt journal directory is unsafe").into());
    }
    Ok(())
}

fn wall_clock_unix_ms() -> Result<u64, AnyError> {
    Ok(u64::try_from(
        SystemTime::now().duration_since(UNIX_EPOCH)?.as_millis(),
    )?)
}
