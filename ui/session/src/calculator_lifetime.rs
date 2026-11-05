//! A Root-reserved joint Session never falls back to volatile Calculator data.
use std::io;
use std::path::PathBuf;
pub(super) fn require_durable_storage() -> io::Result<()> {
    let root = std::env::var_os("TRILL_CALCULATOR_STATE_DIR")
        .map(PathBuf::from)
        .ok_or_else(|| io::Error::other("Root Calculator profile requires durable storage"))?;
    trill_ui_core::calculator_store::CalculatorStore::validate_existing_storage_root(&root)
}
