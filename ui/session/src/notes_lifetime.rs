//! Dedicated Root-reserved profile requires real durable application storage.
use std::io;
use std::path::PathBuf;
use trill_ui_core::notes::NotesTargetIdentity;
use trill_ui_core::notes_lifetime::{SessionLifetimeSource, StorageRequirement};

pub(super) fn require_durable_storage() -> io::Result<()> {
    let root = std::env::var_os("TRILL_NOTES_STATE_DIR")
        .map(PathBuf::from)
        .ok_or_else(|| io::Error::other("Root Notes profile requires original durable storage"))?;
    trill_ui_core::notes_store::NotesStore::validate_existing_storage_root(&root)
}

pub(super) fn attach(
    command: &mut std::process::Command,
    target: &NotesTargetIdentity,
    durable_required: bool,
) -> io::Result<()> {
    let storage = if durable_required {
        require_durable_storage()?;
        StorageRequirement::DurableRequired
    } else {
        StorageRequirement::Optional
    };
    SessionLifetimeSource::capture_current(target.clone(), storage)?.inherit_into(command)
}
