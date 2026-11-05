//! Durable Calculator state and observation-only reopening of an old target.
//! The original Hepta writer alone retains operation history and authority.
use crate::app_checkpoint_store::{
    lock_directory, open_directory, open_file, open_root, replace_checkpoint, IncarnationLock,
    Mode, MAX_CHECKPOINT_BYTES,
};
use crate::calculator::{
    CalculatorDocument, CalculatorResponse, CalculatorTargetIdentity, CalculatorValueState,
};
use std::fs::File;
use std::io::{self, Read};
use std::path::Path;

pub struct CalculatorStore {
    directory: File,
    _lock: IncarnationLock,
    document: CalculatorDocument,
    mode: Mode,
    frozen: bool,
}

impl CalculatorStore {
    pub fn validate_existing_storage_root(root: &Path) -> io::Result<()> {
        if root.canonicalize()? != root {
            return Err(io::Error::other(
                "Calculator storage root must be canonical",
            ));
        }
        let _directory = open_root(root, false)?;
        Ok(())
    }

    /// A fresh target is never reset or adopted from an existing directory.
    pub fn create(root: &Path, target: CalculatorTargetIdentity) -> io::Result<Self> {
        let document = CalculatorDocument::new(target.clone()).map_err(io::Error::other)?;
        let directory = open_directory(root, &name(&target), Mode::Application)?;
        let lock = lock_directory(&directory)?;
        let mut store = Self {
            directory,
            _lock: lock,
            document,
            mode: Mode::Application,
            frozen: false,
        };
        store.persist(&store.document.checkpoint().map_err(io::Error::other)?)?;
        Ok(store)
    }

    /// The same exclusive incarnation lock excludes a live app or other helper.
    /// Only readback and exact original-owner receipt retirement remain enabled.
    pub fn recover(root: &Path, target: &CalculatorTargetIdentity) -> io::Result<Self> {
        target.validate().map_err(io::Error::other)?;
        let directory = open_directory(root, &name(target), Mode::RecoveryOnly)?;
        let lock = lock_directory(&directory)?;
        let mut bytes = Vec::new();
        open_file(&directory, "document.json", libc::O_RDONLY)?
            .take(MAX_CHECKPOINT_BYTES + 1)
            .read_to_end(&mut bytes)?;
        let document =
            CalculatorDocument::restore_checkpoint(&bytes, target).map_err(io::Error::other)?;
        Ok(Self {
            directory,
            _lock: lock,
            document,
            mode: Mode::RecoveryOnly,
            frozen: false,
        })
    }
    pub fn target(&self) -> &CalculatorTargetIdentity {
        self.document.target()
    }
    pub fn state(&self) -> &CalculatorValueState {
        self.document.state()
    }
    pub fn revision(&self) -> u64 {
        self.document.revision()
    }
    pub fn receipt_pending(&self) -> bool {
        self.document.receipt_pending()
    }
    pub fn is_frozen(&self) -> bool {
        self.frozen
    }

    /// Applied is returned only after state and the causal receipt are synced.
    pub fn apply_exact(&mut self, raw: &[u8]) -> io::Result<CalculatorResponse> {
        self.require_application()?;
        let mut next = self.document.clone();
        let receipt = next.apply_exact(raw).map_err(io::Error::other)?;
        self.commit(next)?;
        Ok(receipt)
    }
    pub fn deadline_refusal(&self, raw: &[u8]) -> io::Result<CalculatorResponse> {
        self.require_available()?;
        self.document
            .deadline_refusal(raw)
            .map_err(io::Error::other)
    }
    pub fn local_edit(&mut self, state: CalculatorValueState) -> io::Result<()> {
        self.require_application()?;
        let mut next = self.document.clone();
        next.local_edit(state).map_err(io::Error::other)?;
        self.commit(next)
    }
    pub fn recovery_exact(&mut self, raw: &[u8]) -> io::Result<Vec<u8>> {
        self.require_available()?;
        let mut next = self.document.clone();
        let response = next.recovery_exact(raw).map_err(io::Error::other)?;
        self.commit(next)?;
        Ok(response)
    }
    fn require_application(&self) -> io::Result<()> {
        self.require_available()?;
        if self.mode != Mode::Application {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "recovered Calculator incarnation is observation-only",
            ));
        }
        Ok(())
    }
    fn require_available(&self) -> io::Result<()> {
        if self.frozen {
            return Err(io::Error::other(
                "Calculator storage outcome requires recovery",
            ));
        }
        Ok(())
    }
    fn commit(&mut self, next: CalculatorDocument) -> io::Result<()> {
        let bytes = next.checkpoint().map_err(io::Error::other)?;
        if bytes != self.document.checkpoint().map_err(io::Error::other)? {
            self.persist(&bytes)?;
        }
        self.document = next;
        Ok(())
    }
    fn persist(&mut self, bytes: &[u8]) -> io::Result<()> {
        let result = replace_checkpoint(&self.directory, bytes);
        if result.is_err() {
            self.frozen = true;
        }
        result
    }
}
fn name(target: &CalculatorTargetIdentity) -> String {
    format!(
        "{}-{}-{}",
        target.session_instance, target.task_id, target.incarnation
    )
}

#[cfg(test)]
#[path = "calculator_store_tests.rs"]
mod tests;
