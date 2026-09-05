use crate::{AnyError, JOURNAL_PATH, JOURNAL_ROOT, invalid};
use hepta_session_core::receipt_journal::MAX_CHAIN_SEGMENTS;
use hepta_session_core::{
    JournalId, JournalOpenPolicy, PrivacyClass, ReceiptEffectClass, ReceiptJournal,
    ReceiptLifecycleState,
};
use std::fs;
use std::io;
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

const JOURNAL_ID: JournalId = JournalId([0xd3; 16]);

/// The new store is explicit opt-in. No old file/path list is silently adopted.
pub(crate) fn open_configured() -> Result<ReceiptJournal, AnyError> {
    let store = std::env::var_os("HEPTA_D3_RECEIPT_STORE");
    if let Some(root) = parse_managed_path(
        store.as_deref(),
        std::env::var_os("HEPTA_D3_RECEIPT_JOURNAL").is_some(),
        std::env::var_os("HEPTA_D3_RECEIPT_PREDECESSORS").is_some(),
    )? {
        return open_or_create_managed(&root);
    }
    let path = configured_path()?;
    let predecessors = configured_predecessors(&path)?;
    open_or_create(&path, &predecessors)
}

fn parse_managed_path(
    store: Option<&std::ffi::OsStr>,
    journal_present: bool,
    predecessors_present: bool,
) -> Result<Option<PathBuf>, AnyError> {
    let Some(store) = store else {
        return Ok(None);
    };
    if journal_present || predecessors_present {
        return Err(invalid(
            "managed store and legacy journal configuration are mutually exclusive",
        )
        .into());
    }
    let root = PathBuf::from(store);
    validate_journal_path(&root)?;
    if store.len() > 4000 {
        return Err(invalid("managed store path is too long").into());
    }
    Ok(Some(root))
}

pub(crate) fn open_or_create_managed(root: &Path) -> Result<ReceiptJournal, AnyError> {
    match fs::symlink_metadata(root) {
        Ok(_) => Ok(ReceiptJournal::open_managed(
            root,
            JOURNAL_ID,
            hepta_session_core::ManagedOpenPolicy::RECOVER_CRASH,
        )?),
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            ensure_parent(root)?;
            Ok(ReceiptJournal::create_managed(
                root,
                JOURNAL_ID,
                wall_clock_unix_ms()?,
            )?)
        }
        Err(error) => Err(error.into()),
    }
}

pub(crate) fn configured_path() -> Result<PathBuf, AnyError> {
    let path = std::env::var_os("HEPTA_D3_RECEIPT_JOURNAL")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(JOURNAL_PATH));
    validate_journal_path(&path)?;
    Ok(path)
}

pub(crate) fn validate_journal_path(path: &Path) -> Result<(), AnyError> {
    let text = path
        .to_str()
        .ok_or_else(|| invalid("journal path must be UTF-8"))?;
    if text.len() > 4096
        || !text.starts_with(&format!("{JOURNAL_ROOT}/"))
        || text
            .bytes()
            .any(|byte| byte <= 0x20 || byte == 0x7f || byte == b':' || byte == b'\\')
        || text
            .chars()
            .any(|character| character.is_control() || character.is_whitespace())
        || text[1..]
            .split('/')
            .any(|part| part.is_empty() || part == "." || part == "..")
    {
        return Err(invalid("receipt journal path escapes the canonical development root").into());
    }
    Ok(())
}

pub(crate) fn configured_predecessors(active: &Path) -> Result<Vec<PathBuf>, AnyError> {
    let configured = std::env::var_os("HEPTA_D3_RECEIPT_PREDECESSORS");
    let text = configured
        .as_deref()
        .map(|value| {
            value
                .to_str()
                .ok_or_else(|| invalid("receipt predecessor list must be UTF-8"))
        })
        .transpose()?;
    parse_predecessors(active, text)
}

fn parse_predecessors(active: &Path, text: Option<&str>) -> Result<Vec<PathBuf>, AnyError> {
    validate_journal_path(active)?;
    let Some(text) = text else {
        return Ok(Vec::new());
    };
    if text.is_empty() || text.len() > (MAX_CHAIN_SEGMENTS - 1) * 4097 {
        return Err(invalid("receipt predecessor list is empty or too large").into());
    }
    let paths: Vec<_> = text
        .split(':')
        .take(MAX_CHAIN_SEGMENTS)
        .map(PathBuf::from)
        .collect();
    if paths.len() >= MAX_CHAIN_SEGMENTS {
        return Err(invalid("receipt predecessor list exceeds the chain bound").into());
    }
    let mut seen = std::collections::HashSet::new();
    for path in &paths {
        validate_journal_path(path)?;
        if path == active || !seen.insert(path.clone()) {
            return Err(
                invalid("receipt predecessor list repeats an active or archived path").into(),
            );
        }
    }
    Ok(paths)
}

pub(crate) fn open_or_create(
    path: &Path,
    predecessors: &[PathBuf],
) -> Result<ReceiptJournal, AnyError> {
    if predecessors.len() >= MAX_CHAIN_SEGMENTS {
        return Err(invalid("receipt predecessor list exceeds the chain bound").into());
    }
    // symlink_metadata, not exists(): a dangling link is an invalid existing
    // input, never a reason to create a new journal or ignore predecessor state.
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(ReceiptJournal::open_chain(
            predecessors
                .iter()
                .map(PathBuf::as_path)
                .chain(std::iter::once(path)),
            JOURNAL_ID,
            JournalOpenPolicy::RECOVER_CRASH,
        )?),
        Err(error) if error.kind() == io::ErrorKind::NotFound && predecessors.is_empty() => {
            ensure_parent(path)?;
            Ok(ReceiptJournal::create(
                path,
                JOURNAL_ID,
                wall_clock_unix_ms()?,
            )?)
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            Err(invalid("active journal missing from an explicitly configured chain").into())
        }
        Err(error) => Err(error.into()),
    }
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
        // A recovery annotation must not violate the source record's privacy
        // class. In particular SecretRedacted forbids persisting any detail.
        terminal.detail = (terminal.privacy_class != PrivacyClass::SecretRedacted)
            .then(|| "reconciled_after_sessiond_restart".to_owned());
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

pub(crate) fn wall_clock_unix_ms() -> Result<u64, AnyError> {
    Ok(u64::try_from(
        SystemTime::now().duration_since(UNIX_EPOCH)?.as_millis(),
    )?)
}

#[cfg(test)]
#[path = "storage_tests.rs"]
mod tests;
