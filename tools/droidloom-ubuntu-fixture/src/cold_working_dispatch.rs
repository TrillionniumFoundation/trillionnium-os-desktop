//! Consume the actual cold owner in a reversible working-publication transaction.
//!
//! This executes the real fixed runtime publisher and both data-directory
//! exchanges. It always returns the original pair and runtime before reporting
//! success. It cannot label a backing, publish selected.json, arm GRUB or reboot.
//! An unresolved reverse retains the same live owner and descriptors in process.
use super::{
    PublishedWorkingRuntime, RestoredWorkingRuntime, WorkingPublicationFailure,
    working_runtime::{
        PreparedWorkingRuntime, WorkingGrubSource, WorkingOriginalCellPreimage,
        WorkingRuntimeSources,
    },
};
use crate::{Result, boot_files as files, ensure};
use serde_json::{Value, json};
use std::{fs::File, path::PathBuf, thread, time::Duration};

/// The real implementation owns resources across every error. The test backend
/// exercises the same ordering with actual filesystem exchanges and fault points.
trait Actions {
    fn publish_runtime(&mut self) -> Result<()>;
    fn advance_pair(&mut self) -> Result<()>;
    fn verify_exchanged(&mut self) -> Result<()>;
    fn restore_pair(&mut self) -> Result<()>;
    fn restore_runtime(&mut self) -> Result<()>;
    fn verify_restored(&mut self) -> Result<()>;
}

fn forward(actions: &mut impl Actions) -> Result<()> {
    actions.publish_runtime()?;
    // The existing pair owner exposes two exact operations, Stage and Exchange.
    // Never restart forward after an error or infer a failed rename had no effect.
    actions.advance_pair()?;
    actions.advance_pair()?;
    actions.verify_exchanged()
}

fn reverse(actions: &mut impl Actions) -> Result<()> {
    // Restoring the original cell while the working pair is still selected by
    // pathname would create a mixed generation. Data must be restored first.
    actions.restore_pair()?;
    actions.restore_runtime()?;
    actions.verify_restored()
}

enum Runtime {
    Prepared {
        source: WorkingRuntimeSources,
        cell: WorkingOriginalCellPreimage,
    },
    Published(PublishedWorkingRuntime),
    Failed(WorkingPublicationFailure),
    Restored(RestoredWorkingRuntime),
}

struct LiveDispatch {
    runtime: Option<Runtime>,
    grub: WorkingGrubSource,
    work: PathBuf,
    candidate: String,
    published: bool,
    exchanged: bool,
}

impl LiveDispatch {
    fn new(prepared: PreparedWorkingRuntime) -> Result<Self> {
        let (source, cell, grub) = prepared.into_publication_sources()?;
        cell.require_sources(&source)?;
        grub.require_sources(&source)?;
        let work = source.work().to_owned();
        let candidate = source.candidate().to_owned();
        Ok(Self {
            runtime: Some(Runtime::Prepared { source, cell }),
            grub,
            work,
            candidate,
            published: false,
            exchanged: false,
        })
    }

    fn source(&self) -> Result<&WorkingRuntimeSources> {
        match self
            .runtime
            .as_ref()
            .ok_or("working dispatcher has no held state")?
        {
            Runtime::Prepared { source, .. } => Ok(source),
            Runtime::Published(value) => Ok(value.source()),
            Runtime::Failed(value) => Ok(value.source()),
            Runtime::Restored(value) => Ok(value.source()),
        }
    }

    fn report(&self, forward_error: Option<&str>, recovered_errors: &[String]) -> Result<Value> {
        let restored = match self.runtime.as_ref() {
            Some(Runtime::Restored(value)) => {
                value.guard()?;
                value.summary().clone()
            }
            _ => return Err("working dispatch cannot report without complete reverse".into()),
        };
        self.grub.require_sources(self.source()?)?;
        let value = json!({
            "schema":"droidloom.working-publication-roundtrip.v1",
            "candidate_id":self.candidate,
            "boot_intent":self.source()?.boot_intent(),
            "runtime_publication_observed":self.published,
            "working_pair_exchange_observed":self.exchanged,
            "pair_restored":true,
            "runtime_restoration":restored,
            "grub_preimage_unchanged":true,
            "forward_succeeded":forward_error.is_none(),
            "forward_error":forward_error,
            "recovered_errors":recovered_errors,
            "same_cold_owner_and_four_backing_ofds_retained":true,
            "selected_json_published":false,
            "backing_labels_changed":false,
            "boot_armed":false,
            "host_reboots":0,
            "application_business_accepted":false,
            "production_ready":false
        });
        let mut raw = serde_json::to_vec_pretty(&value)?;
        raw.push(b'\n');
        let path = self.work.join("WORKING-PUBLICATION-ROUNDTRIP.json");
        files::write_new(&path, &raw, 0o400)?;
        File::open(&self.work)?.sync_all()?;
        let pin = files::pin_file(&path)?;
        ensure(
            files::read_pin(&pin, 1024 * 1024)? == raw,
            "working dispatch final record changed after complete reverse",
        )?;
        Ok(json!({"actual":value,"record":pin}))
    }
}

impl Actions for LiveDispatch {
    fn publish_runtime(&mut self) -> Result<()> {
        self.grub.require_sources(self.source()?)?;
        // No fallible operation is allowed while the state is moved out. Both
        // publisher outcomes return the same actual ownership to this enum.
        let state = self
            .runtime
            .take()
            .ok_or("working dispatcher state absent")?;
        match state {
            Runtime::Prepared { source, cell } => {
                match PublishedWorkingRuntime::publish(source, cell) {
                    Ok(value) => {
                        self.runtime = Some(Runtime::Published(value));
                        self.published = true;
                        Ok(())
                    }
                    Err(value) => {
                        let error = value.to_string();
                        self.runtime = Some(Runtime::Failed(value));
                        Err(error.into())
                    }
                }
            }
            other => {
                self.runtime = Some(other);
                Err("working runtime publication is create-only".into())
            }
        }
    }

    fn advance_pair(&mut self) -> Result<()> {
        let Some(Runtime::Published(value)) = self.runtime.as_ref() else {
            return Err("working pair requires the same fully published runtime".into());
        };
        self.grub.require_sources(value.source())?;
        value.source().advance_pair(value)?;
        value.guard()
    }

    fn verify_exchanged(&mut self) -> Result<()> {
        let Some(Runtime::Published(value)) = self.runtime.as_ref() else {
            return Err("working exchange lacks its live published owner".into());
        };
        ensure(
            value.source().pair_exchanged(value)?,
            "working pair did not reach its actual complete exchanged layout",
        )?;
        self.grub.require_sources(value.source())?;
        self.exchanged = true;
        Ok(())
    }

    fn restore_pair(&mut self) -> Result<()> {
        match self
            .runtime
            .as_ref()
            .ok_or("working dispatcher state absent")?
        {
            Runtime::Published(value) => value.source().restore_pair_cold(value),
            Runtime::Prepared { source, .. } => source.revalidate(),
            // Pair mutation is reachable only after runtime publication success.
            // A failed reverse of the runtime is reached only after pair restore.
            Runtime::Failed(value) => value.source().revalidate(),
            Runtime::Restored(value) => value.guard(),
        }
    }

    fn restore_runtime(&mut self) -> Result<()> {
        let state = self
            .runtime
            .take()
            .ok_or("working dispatcher state absent")?;
        let result = match state {
            Runtime::Published(value) => value.restore(),
            Runtime::Failed(value) => value.restore(),
            other => {
                self.runtime = Some(other);
                return Ok(());
            }
        };
        match result {
            Ok(value) => {
                self.runtime = Some(Runtime::Restored(value));
                Ok(())
            }
            Err(value) => {
                let error = value
                    .errors()
                    .last()
                    .cloned()
                    .unwrap_or_else(|| value.to_string());
                self.runtime = Some(Runtime::Failed(value));
                Err(error.into())
            }
        }
    }

    fn verify_restored(&mut self) -> Result<()> {
        let Some(Runtime::Restored(value)) = self.runtime.as_ref() else {
            return Err("working dispatch has not completed runtime restoration".into());
        };
        value.guard()?;
        self.grub.require_sources(value.source())
    }
}

/// Actual effectful cold entry. A new fixed CLI mode explicitly selects it;
/// the existing preparation command continues to prepare private files only.
pub(super) fn run(prepared: PreparedWorkingRuntime) -> Result<Value> {
    let mut dispatch = LiveDispatch::new(prepared)?;
    let forward_error = forward(&mut dispatch).err().map(|e| e.to_string());
    if matches!(dispatch.runtime.as_ref(), Some(Runtime::Prepared { .. })) {
        return Err(format!(
            "working publication did not begin: {}",
            forward_error
                .as_deref()
                .unwrap_or("actual publication state absent")
        )
        .into());
    }
    let mut recovered_errors = Vec::new();
    let mut last_recovery_error = None;
    loop {
        match reverse(&mut dispatch) {
            Ok(()) => break,
            Err(error) => {
                let message = error.to_string();
                if last_recovery_error.as_ref() != Some(&message) {
                    last_recovery_error = Some(message.clone());
                    eprintln!(
                        "DROIDLOOM_WORKING_REVERSE_PENDING candidate={} error={message}",
                        dispatch.candidate
                    );
                    // Bounded diagnostics; the live resource owner remains in
                    // dispatch. Repeated observations never repeat forward.
                    if recovered_errors.len() < 32 {
                        recovered_errors.push(message);
                    }
                }
                // The existing transaction first reconciles its exact retained
                // pending operation. Its finite reverse-attempt bound remains
                // authoritative. A foreign change is never overwritten.
                thread::sleep(Duration::from_secs(5));
            }
        }
    }
    let result = dispatch.report(forward_error.as_deref(), &recovered_errors)?;
    if let Some(error) = forward_error {
        eprintln!("{}", serde_json::to_string(&result)?);
        return Err(format!(
            "working publication failed and actual original state was restored: {error}"
        )
        .into());
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    enum Fault {
        None,
        PublishAfterEffect,
        StageAfterEffect,
        ExchangeAfterEffect,
        RestorePairOnce,
        RestoreRuntimeOnce,
    }

    /// Real files, not a success-returning mock: each failure can happen after
    /// its filesystem effect. Recovery must observe/restore the original bytes.
    struct Files {
        root: tempfile::TempDir,
        fault: Fault,
        pair_phase: usize,
        runtime_published: bool,
        publishes: usize,
        advances: usize,
        restore_pair_failed: bool,
        restore_runtime_failed: bool,
    }
    impl Files {
        fn new(fault: Fault) -> Result<Self> {
            let root = tempfile::tempdir()?;
            fs::write(root.path().join("runtime"), b"original runtime")?;
            fs::write(root.path().join("original-data"), b"original data")?;
            fs::write(root.path().join("working-data"), b"working data")?;
            Ok(Self {
                root,
                fault,
                pair_phase: 0,
                runtime_published: false,
                publishes: 0,
                advances: 0,
                restore_pair_failed: false,
                restore_runtime_failed: false,
            })
        }
        fn path(&self, name: &str) -> PathBuf {
            self.root.path().join(name)
        }
        fn original(&self) -> Result<()> {
            ensure(
                fs::read(self.path("runtime"))? == b"original runtime",
                "runtime not restored",
            )?;
            ensure(
                fs::read(self.path("original-data"))? == b"original data",
                "original data not restored",
            )?;
            ensure(
                fs::read(self.path("working-data"))? == b"working data",
                "working data not retained",
            )?;
            ensure(
                !self.path("staged-data").exists() && !self.path("old-runtime").exists(),
                "partial state remains",
            )
        }
        fn move_file(&self, from: &str, to: &str) -> Result<()> {
            ensure(!self.path(to).exists(), "test move would overwrite")?;
            fs::rename(self.path(from), self.path(to))?;
            Ok(())
        }
    }
    impl Actions for Files {
        fn publish_runtime(&mut self) -> Result<()> {
            self.publishes += 1;
            self.move_file("runtime", "old-runtime")?;
            fs::write(self.path("runtime"), b"candidate runtime")?;
            self.runtime_published = true;
            ensure(
                self.fault != Fault::PublishAfterEffect,
                "injected error after runtime effect",
            )
        }
        fn advance_pair(&mut self) -> Result<()> {
            self.advances += 1;
            match self.pair_phase {
                0 => {
                    self.move_file("working-data", "staged-data")?;
                    self.pair_phase = 1;
                    ensure(
                        self.fault != Fault::StageAfterEffect,
                        "injected error after stage",
                    )
                }
                1 => {
                    self.move_file("original-data", "working-data")?;
                    self.move_file("staged-data", "original-data")?;
                    self.pair_phase = 2;
                    ensure(
                        self.fault != Fault::ExchangeAfterEffect,
                        "injected error after exchange",
                    )
                }
                _ => Err("forward was incorrectly replayed".into()),
            }
        }
        fn verify_exchanged(&mut self) -> Result<()> {
            ensure(
                self.pair_phase == 2
                    && fs::read(self.path("original-data"))? == b"working data"
                    && fs::read(self.path("working-data"))? == b"original data",
                "actual pair was not exchanged",
            )
        }
        fn restore_pair(&mut self) -> Result<()> {
            if self.fault == Fault::RestorePairOnce && !self.restore_pair_failed {
                self.restore_pair_failed = true;
                return Err("injected pair restore readback failure".into());
            }
            if self.pair_phase == 2 {
                self.move_file("original-data", "staged-data")?;
                self.move_file("working-data", "original-data")?;
                self.pair_phase = 1;
            }
            if self.pair_phase == 1 {
                self.move_file("staged-data", "working-data")?;
                self.pair_phase = 0;
            }
            Ok(())
        }
        fn restore_runtime(&mut self) -> Result<()> {
            ensure(self.pair_phase == 0, "runtime restored before data")?;
            if self.runtime_published {
                fs::remove_file(self.path("runtime"))?;
                self.move_file("old-runtime", "runtime")?;
                self.runtime_published = false;
            }
            if self.fault == Fault::RestoreRuntimeOnce && !self.restore_runtime_failed {
                self.restore_runtime_failed = true;
                return Err("injected error after runtime reverse effect".into());
            }
            Ok(())
        }
        fn verify_restored(&mut self) -> Result<()> {
            self.original()
        }
    }

    #[test]
    fn working_dispatch_reverses_real_partial_effects_without_forward_replay() -> Result<()> {
        for fault in [
            Fault::None,
            Fault::PublishAfterEffect,
            Fault::StageAfterEffect,
            Fault::ExchangeAfterEffect,
        ] {
            let mut files = Files::new(fault)?;
            let outcome = forward(&mut files);
            assert_eq!(outcome.is_ok(), fault == Fault::None);
            let counts = (files.publishes, files.advances);
            reverse(&mut files)?;
            files.original()?;
            assert_eq!((files.publishes, files.advances), counts);
            assert_eq!(files.publishes, 1);
        }
        Ok(())
    }

    #[test]
    fn working_dispatch_retains_runtime_until_pair_restoration_succeeds() -> Result<()> {
        let mut files = Files::new(Fault::RestorePairOnce)?;
        forward(&mut files)?;
        assert!(reverse(&mut files).is_err());
        assert!(files.runtime_published);
        assert_eq!(fs::read(files.path("runtime"))?, b"candidate runtime");
        let counts = (files.publishes, files.advances);
        reverse(&mut files)?;
        files.original()?;
        assert_eq!((files.publishes, files.advances), counts);
        Ok(())
    }

    #[test]
    fn working_dispatch_reconciles_reverse_failure_without_republishing() -> Result<()> {
        let mut files = Files::new(Fault::RestoreRuntimeOnce)?;
        forward(&mut files)?;
        assert!(reverse(&mut files).is_err());
        files.original()?;
        let counts = (files.publishes, files.advances);
        reverse(&mut files)?;
        files.original()?;
        assert_eq!((files.publishes, files.advances), counts);
        Ok(())
    }
}
