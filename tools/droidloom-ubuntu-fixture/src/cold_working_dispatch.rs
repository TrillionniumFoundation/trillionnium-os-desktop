//! Consume the actual cold owner in a reversible working-publication transaction.
//!
//! This installs the actual normal public/native packages, executes the fixed
//! runtime publisher and both data-directory exchanges, then publishes the
//! working initrd and menuentry. Reverse restores boot files, pair, runtime,
//! native/public packages and runtime masks before reporting success. The full
//! normal label writer runs under an independent finite freezer and restores
//! every actual xattr before file/data/package reverse. It cannot yet publish
//! selected.json, arm grubenv or reboot.
//! An unresolved reverse retains the same live owner and descriptors in process.
use super::{
    PublishedWorkingBootFiles, PublishedWorkingRuntime, RestoredWorkingRuntime,
    WorkingPublicationFailure, WorkingQuiescence,
    configurations::working_grub::WorkingBootPublicationFailure,
    working_packages::WorkingPackages,
    working_runtime::{
        PreparedWorkingRuntime, WorkingGrubSource, WorkingOriginalCellPreimage,
        WorkingRuntimeSources,
    },
};
use crate::cold_original_data::labels::{
    WorkingLabelTransaction, WorkingLabelsApplied, WorkingLabelsRestored,
};
use crate::{Result, boot_files as files, ensure};
use serde_json::{Value, json};
use std::{fs::File, path::PathBuf, thread, time::Duration};

/// The real implementation owns resources across every error. The test backend
/// exercises the same ordering with actual filesystem exchanges and fault points.
trait Actions {
    fn install_packages(&mut self) -> Result<()>;
    fn publish_runtime(&mut self) -> Result<()>;
    fn advance_pair(&mut self) -> Result<()>;
    fn verify_exchanged(&mut self) -> Result<()>;
    fn publish_boot_files(&mut self) -> Result<()>;
    fn apply_labels(&mut self) -> Result<()>;
    fn restore_labels(&mut self) -> Result<()>;
    fn restore_boot_files(&mut self) -> Result<()>;
    fn restore_pair(&mut self) -> Result<()>;
    fn restore_runtime(&mut self) -> Result<()>;
    fn verify_restored(&mut self) -> Result<()>;
    fn restore_packages(&mut self) -> Result<()>;
    fn verify_complete(&mut self) -> Result<()>;
}

fn forward(actions: &mut impl Actions) -> Result<()> {
    actions.install_packages()?;
    actions.publish_runtime()?;
    // The existing pair owner exposes two exact operations, Stage and Exchange.
    // Never restart forward after an error or infer a failed rename had no effect.
    actions.advance_pair()?;
    actions.advance_pair()?;
    actions.verify_exchanged()?;
    actions.publish_boot_files()?;
    actions.apply_labels()
}

fn reverse(actions: &mut impl Actions) -> Result<()> {
    actions.restore_labels()?;
    // Boot entries must be removed before their referenced data generation.
    actions.restore_boot_files()?;
    // Restoring the original cell while the working pair is still selected by
    // pathname would create a mixed generation. Data must be restored first.
    actions.restore_pair()?;
    actions.restore_runtime()?;
    actions.verify_restored()?;
    actions.restore_packages()?;
    actions.verify_complete()
}

enum Runtime {
    Prepared {
        source: WorkingRuntimeSources,
        cell: WorkingOriginalCellPreimage,
    },
    Published(PublishedWorkingRuntime),
    BootPublished(PublishedWorkingBootFiles),
    BootFailed(WorkingBootPublicationFailure),
    Failed(WorkingPublicationFailure),
    Restored(RestoredWorkingRuntime),
    PackageRestoring {
        source: WorkingRuntimeSources,
        runtime_restoration: Option<files::FilePin>,
    },
}

struct LiveDispatch {
    runtime: Option<Runtime>,
    packages: WorkingPackages,
    labels: Option<WorkingLabelTransaction>,
    frozen: Option<WorkingQuiescence>,
    labels_applied: Option<WorkingLabelsApplied>,
    labels_restored: Option<WorkingLabelsRestored>,
    grub: Option<WorkingGrubSource>,
    work: PathBuf,
    candidate: String,
    published: bool,
    exchanged: bool,
    boot_published: bool,
    boot_restored: Option<files::FilePin>,
}

impl LiveDispatch {
    fn new(prepared: PreparedWorkingRuntime) -> Result<Self> {
        let (source, cell, grub) = prepared.into_publication_sources()?;
        cell.require_sources(&source)?;
        grub.require_sources(&source)?;
        let work = source.work().to_owned();
        let candidate = source.candidate().to_owned();
        let packages = WorkingPackages::prepare(&source)?;
        Ok(Self {
            runtime: Some(Runtime::Prepared { source, cell }),
            packages,
            labels: None,
            frozen: None,
            labels_applied: None,
            labels_restored: None,
            grub: Some(grub),
            work,
            candidate,
            published: false,
            exchanged: false,
            boot_published: false,
            boot_restored: None,
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
            Runtime::BootPublished(value) => Ok(value.runtime().source()),
            Runtime::BootFailed(value) => Ok(value.runtime().source()),
            Runtime::Failed(value) => Ok(value.source()),
            Runtime::Restored(value) => Ok(value.source()),
            Runtime::PackageRestoring { source, .. } => Ok(source),
        }
    }

    fn grub(&self) -> Result<&WorkingGrubSource> {
        self.grub
            .as_ref()
            .ok_or_else(|| "working boot files still retain GRUB custody".into())
    }

    fn report(&self, forward_error: Option<&str>, recovered_errors: &[String]) -> Result<Value> {
        let restored =
            match self.runtime.as_ref() {
                Some(Runtime::PackageRestoring {
                    source,
                    runtime_restoration,
                }) => {
                    source.revalidate()?;
                    self.packages.guard_restored()?;
                    runtime_restoration.clone()
                }
                _ => return Err(
                    "working dispatch cannot report without complete package and runtime reverse"
                        .into(),
                ),
            };
        self.grub()?.require_sources(self.source()?)?;
        let value = json!({
            "schema":"droidloom.working-publication-roundtrip.v1",
            "candidate_id":self.candidate,
            "boot_intent":self.source()?.boot_intent(),
            "runtime_publication_observed":self.published,
            "working_pair_exchange_observed":self.exchanged,
            "working_boot_files_publication_observed":self.boot_published,
            "working_boot_files_restoration":self.boot_restored,
            "pair_restored":true,
            "runtime_restoration":restored,
            "normal_package_restoration":self.packages.evidence()?,
            "grub_preimage_unchanged":true,
            "forward_succeeded":forward_error.is_none(),
            "forward_error":forward_error,
            "recovered_errors":recovered_errors,
            "same_cold_owner_and_four_backing_ofds_retained":true,
            "selected_json_published":false,
            "normal_label_transaction_prepared":self.labels.is_some(),
            "normal_labels_applied":self.labels_applied.as_ref().map(|v|v.report()),
            "normal_labels_restored":self.labels_restored.as_ref().map(|v|v.report()),
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
    fn install_packages(&mut self) -> Result<()> {
        self.grub()?.require_sources(self.source()?)?;
        self.packages.install()
    }
    fn publish_runtime(&mut self) -> Result<()> {
        self.packages.verify_installed()?;
        self.grub()?.require_sources(self.source()?)?;
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
        self.grub()?.require_sources(value.source())?;
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
        self.grub()?.require_sources(value.source())?;
        self.exchanged = true;
        Ok(())
    }

    fn publish_boot_files(&mut self) -> Result<()> {
        let state = self
            .runtime
            .take()
            .ok_or("working dispatcher state absent")?;
        let runtime = match state {
            Runtime::Published(value) => value,
            other => {
                self.runtime = Some(other);
                return Err("working boot files require the same published runtime".into());
            }
        };
        let Some(grub) = self.grub.take() else {
            self.runtime = Some(Runtime::Published(runtime));
            return Err("working boot publication has no original GRUB owner".into());
        };
        // Both outcomes return the same runtime and GRUB owner. There is no
        // fallible operation while these resources are outside this state.
        match PublishedWorkingBootFiles::publish(runtime, grub) {
            Ok(value) => {
                self.boot_published = true;
                self.runtime = Some(Runtime::BootPublished(value));
                Ok(())
            }
            Err(value) => {
                let error = value
                    .errors()
                    .last()
                    .cloned()
                    .unwrap_or_else(|| "working boot publication failed".into());
                self.runtime = Some(Runtime::BootFailed(value));
                Err(error.into())
            }
        }
    }

    fn apply_labels(&mut self) -> Result<()> {
        let Some(Runtime::BootPublished(boot)) = self.runtime.as_mut() else {
            return Err("working labels require the actual retained boot publication".into());
        };
        ensure(
            self.labels.is_none() && self.frozen.is_none(),
            "working label forward is create-only",
        )?;
        self.frozen = Some(WorkingQuiescence::begin(boot, &mut self.packages)?);
        let frozen = self.frozen.as_ref().unwrap();
        self.labels = Some(WorkingLabelTransaction::prepare(boot, frozen)?);
        self.labels_applied = Some(self.labels.as_mut().unwrap().apply(
            boot,
            &mut self.packages,
            frozen,
        )?);
        Ok(())
    }

    fn restore_labels(&mut self) -> Result<()> {
        if self.labels_restored.is_none() {
            if let Some(labels) = &mut self.labels {
                let Some(Runtime::BootPublished(boot)) = self.runtime.as_mut() else {
                    return Err("working label recovery lost its same boot/runtime owner".into());
                };
                let frozen = self
                    .frozen
                    .as_ref()
                    .ok_or("working label recovery lost its independent freezer")?;
                let restored = labels.restore(boot, &mut self.packages, frozen)?;
                self.packages.bind_label_restoration(&restored)?;
                self.labels_restored = Some(restored);
            }
        }
        if let Some(frozen) = &mut self.frozen {
            frozen.finish()?;
        }
        self.frozen = None;
        Ok(())
    }

    fn restore_boot_files(&mut self) -> Result<()> {
        let state = self
            .runtime
            .take()
            .ok_or("working dispatcher state absent")?;
        let result = match state {
            Runtime::BootPublished(value) => value.restore(),
            Runtime::BootFailed(value) => value.restore(),
            other => {
                self.runtime = Some(other);
                return Ok(());
            }
        };
        match result {
            Ok(value) => {
                self.boot_restored = value.summary().cloned();
                let (runtime, grub) = value.into_runtime();
                self.runtime = Some(Runtime::Published(runtime));
                self.grub = Some(grub);
                Ok(())
            }
            Err(value) => {
                let error = value
                    .errors()
                    .last()
                    .cloned()
                    .unwrap_or_else(|| "working boot restoration remains incomplete".into());
                self.runtime = Some(Runtime::BootFailed(value));
                Err(error.into())
            }
        }
    }

    fn restore_pair(&mut self) -> Result<()> {
        match self
            .runtime
            .as_ref()
            .ok_or("working dispatcher state absent")?
        {
            Runtime::Published(value) => value.source().restore_pair_cold(value),
            Runtime::BootPublished(_) | Runtime::BootFailed(_) => {
                Err("working boot files must be restored before the data pair".into())
            }
            Runtime::Prepared { source, .. } => source.revalidate(),
            // Pair mutation is reachable only after runtime publication success.
            // A failed reverse of the runtime is reached only after pair restore.
            Runtime::Failed(value) => value.source().revalidate(),
            Runtime::Restored(value) => value.guard(),
            Runtime::PackageRestoring { source, .. } => source.revalidate(),
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
        match self
            .runtime
            .as_ref()
            .ok_or("working dispatcher state absent")?
        {
            Runtime::Restored(value) => value.guard()?,
            Runtime::Prepared { source, cell } => cell.require_sources(source)?,
            Runtime::PackageRestoring { source, .. } => source.revalidate()?,
            _ => return Err("working runtime restoration remains incomplete".into()),
        }
        self.grub()?.require_sources(self.source()?)
    }

    fn restore_packages(&mut self) -> Result<()> {
        // The normal package engine changes its own installed parent members.
        // Finish the runtime reverse against its exact post-install checkpoint
        // first, then transfer the same cold owner without a fallible gap.
        self.verify_restored()?;
        let state = self
            .runtime
            .take()
            .ok_or("working dispatcher state absent")?;
        self.runtime = Some(match state {
            Runtime::Restored(value) => {
                let (source, summary) = value.into_source();
                Runtime::PackageRestoring {
                    source,
                    runtime_restoration: summary,
                }
            }
            Runtime::Prepared { source, .. } => Runtime::PackageRestoring {
                source,
                runtime_restoration: None,
            },
            Runtime::PackageRestoring {
                source,
                runtime_restoration,
            } => Runtime::PackageRestoring {
                source,
                runtime_restoration,
            },
            other => {
                self.runtime = Some(other);
                return Err("normal package reverse requires completed runtime reverse".into());
            }
        });
        self.packages.restore()
    }

    fn verify_complete(&mut self) -> Result<()> {
        self.packages.guard_restored()?;
        let Some(Runtime::PackageRestoring {
            source,
            runtime_restoration,
        }) = self.runtime.as_ref()
        else {
            return Err("working package reverse has not retained the final cold owner".into());
        };
        if let Some(pin) = runtime_restoration {
            files::read_pin(pin, 64 * 1024 * 1024)?;
        }
        self.grub()?.require_sources(source)
    }
}

/// Actual effectful cold entry. A new fixed CLI mode explicitly selects it;
/// the existing preparation command continues to prepare private files only.
pub(super) fn run(prepared: PreparedWorkingRuntime) -> Result<Value> {
    let mut dispatch = LiveDispatch::new(prepared)?;
    let forward_error = forward(&mut dispatch).err().map(|e| e.to_string());
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
        PackageInstallAfterEffect,
        PublishAfterEffect,
        StageAfterEffect,
        ExchangeAfterEffect,
        BootPublishAfterEffect,
        LabelsAfterEffect,
        RestoreLabelsOnce,
        RuntimeAdmissionBeforeEffect,
        RestoreBootOnce,
        RestorePairOnce,
        RestoreRuntimeOnce,
        RestorePackagesOnce,
    }

    /// Real files, not a success-returning mock: each failure can happen after
    /// its filesystem effect. Recovery must observe/restore the original bytes.
    struct Files {
        root: tempfile::TempDir,
        fault: Fault,
        pair_phase: usize,
        runtime_published: bool,
        packages_installed: bool,
        installs: usize,
        restore_packages_failed: bool,
        boot_published: bool,
        labels_applied: bool,
        label_applications: usize,
        restore_labels_failed: bool,
        boot_publishes: usize,
        restore_boot_failed: bool,
        publishes: usize,
        advances: usize,
        restore_pair_failed: bool,
        restore_runtime_failed: bool,
    }
    impl Files {
        fn new(fault: Fault) -> Result<Self> {
            let root = tempfile::tempdir()?;
            fs::write(root.path().join("runtime"), b"original runtime")?;
            fs::write(root.path().join("packages"), b"original packages")?;
            fs::write(root.path().join("boot"), b"original boot")?;
            fs::write(root.path().join("original-data"), b"original data")?;
            fs::write(root.path().join("working-data"), b"working data")?;
            Ok(Self {
                root,
                fault,
                pair_phase: 0,
                runtime_published: false,
                packages_installed: false,
                installs: 0,
                restore_packages_failed: false,
                boot_published: false,
                labels_applied: false,
                label_applications: 0,
                restore_labels_failed: false,
                boot_publishes: 0,
                restore_boot_failed: false,
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
            let working = File::open(self.path("working-data"))?;
            ensure(
                matches!(
                    rustix::fs::fgetxattr(
                        &working,
                        "user.droidloom.working-dispatch-test",
                        &mut [0u8; 128]
                    ),
                    Err(rustix::io::Errno::NODATA)
                ),
                "working labels not restored",
            )?;
            ensure(
                fs::read(self.path("boot"))? == b"original boot",
                "boot files not restored",
            )?;
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
                !self.path("staged-data").exists()
                    && !self.path("old-runtime").exists()
                    && !self.path("old-boot").exists(),
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
        fn install_packages(&mut self) -> Result<()> {
            self.installs += 1;
            self.move_file("packages", "old-packages")?;
            fs::write(self.path("packages"), b"new normal packages")?;
            self.packages_installed = true;
            ensure(
                self.fault != Fault::PackageInstallAfterEffect,
                "injected partial normal package install",
            )
        }
        fn publish_runtime(&mut self) -> Result<()> {
            ensure(
                self.packages_installed,
                "runtime published before normal packages",
            )?;
            self.publishes += 1;
            ensure(
                self.fault != Fault::RuntimeAdmissionBeforeEffect,
                "injected runtime admission before any rename",
            )?;
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
        fn publish_boot_files(&mut self) -> Result<()> {
            ensure(
                self.pair_phase == 2,
                "boot files published before pair exchange",
            )?;
            self.boot_publishes += 1;
            self.move_file("boot", "old-boot")?;
            fs::write(self.path("boot"), b"candidate boot")?;
            self.boot_published = true;
            ensure(
                self.fault != Fault::BootPublishAfterEffect,
                "injected error after boot effect",
            )
        }
        fn apply_labels(&mut self) -> Result<()> {
            ensure(
                self.boot_published && self.pair_phase == 2,
                "labels preceded actual boot/data publication",
            )?;
            let file = File::open(self.path("original-data"))?;
            rustix::fs::fsetxattr(
                &file,
                "user.droidloom.working-dispatch-test",
                b"actual-normal-context",
                rustix::fs::XattrFlags::empty(),
            )?;
            self.labels_applied = true;
            self.label_applications += 1;
            ensure(
                self.fault != Fault::LabelsAfterEffect,
                "injected actual label effect failure",
            )
        }
        fn restore_labels(&mut self) -> Result<()> {
            if self.labels_applied {
                ensure(
                    self.boot_published && self.pair_phase == 2,
                    "labels restored after moving their original target",
                )?;
                if self.fault == Fault::RestoreLabelsOnce && !self.restore_labels_failed {
                    self.restore_labels_failed = true;
                    return Err("injected label reverse failure".into());
                }
                let file = File::open(self.path("original-data"))?;
                let mut actual = [0u8; 128];
                let n = rustix::fs::fgetxattr(
                    &file,
                    "user.droidloom.working-dispatch-test",
                    &mut actual,
                )?;
                ensure(
                    &actual[..n] == b"actual-normal-context",
                    "unknown test label outcome",
                )?;
                rustix::fs::fremovexattr(&file, "user.droidloom.working-dispatch-test")?;
                self.labels_applied = false;
            }
            Ok(())
        }
        fn restore_boot_files(&mut self) -> Result<()> {
            ensure(
                !self.labels_applied,
                "boot files reversed while source labels remain",
            )?;
            if self.fault == Fault::RestoreBootOnce && !self.restore_boot_failed {
                self.restore_boot_failed = true;
                return Err("injected boot restore failure".into());
            }
            if self.boot_published {
                fs::remove_file(self.path("boot"))?;
                self.move_file("old-boot", "boot")?;
                self.boot_published = false;
            }
            Ok(())
        }
        fn restore_pair(&mut self) -> Result<()> {
            ensure(
                !self.boot_published,
                "data restored while candidate boot files remain",
            )?;
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
        fn restore_packages(&mut self) -> Result<()> {
            self.original()?;
            if self.fault == Fault::RestorePackagesOnce && !self.restore_packages_failed {
                self.restore_packages_failed = true;
                return Err("injected normal package rollback failure".into());
            }
            if self.packages_installed {
                fs::remove_file(self.path("packages"))?;
                self.move_file("old-packages", "packages")?;
                self.packages_installed = false;
            }
            Ok(())
        }
        fn verify_complete(&mut self) -> Result<()> {
            self.original()?;
            ensure(
                fs::read(self.path("packages"))? == b"original packages"
                    && !self.path("old-packages").exists(),
                "normal packages not restored",
            )
        }
    }

    #[test]
    fn working_dispatch_reverses_real_partial_effects_without_forward_replay() -> Result<()> {
        for fault in [
            Fault::None,
            Fault::PackageInstallAfterEffect,
            Fault::PublishAfterEffect,
            Fault::StageAfterEffect,
            Fault::ExchangeAfterEffect,
            Fault::BootPublishAfterEffect,
            Fault::LabelsAfterEffect,
            Fault::RuntimeAdmissionBeforeEffect,
        ] {
            let mut files = Files::new(fault)?;
            let outcome = forward(&mut files);
            assert_eq!(outcome.is_ok(), fault == Fault::None);
            let counts = (files.publishes, files.advances, files.boot_publishes);
            reverse(&mut files)?;
            files.original()?;
            assert_eq!(
                (files.publishes, files.advances, files.boot_publishes),
                counts
            );
            assert_eq!(
                files.publishes,
                usize::from(fault != Fault::PackageInstallAfterEffect)
            );
            assert_eq!(files.installs, 1);
        }
        Ok(())
    }

    #[test]
    fn working_dispatch_retains_pair_and_runtime_until_boot_files_restore() -> Result<()> {
        let mut files = Files::new(Fault::RestoreBootOnce)?;
        forward(&mut files)?;
        let counts = (files.publishes, files.advances, files.boot_publishes);
        assert!(reverse(&mut files).is_err());
        assert!(files.boot_published && files.runtime_published);
        assert_eq!(files.pair_phase, 2);
        assert_eq!(fs::read(files.path("original-data"))?, b"working data");
        reverse(&mut files)?;
        files.original()?;
        assert_eq!(
            (files.publishes, files.advances, files.boot_publishes),
            counts
        );
        Ok(())
    }

    #[test]
    fn working_dispatch_retains_runtime_until_pair_restoration_succeeds() -> Result<()> {
        let mut files = Files::new(Fault::RestorePairOnce)?;
        forward(&mut files)?;
        assert!(reverse(&mut files).is_err());
        assert!(files.runtime_published);
        assert_eq!(fs::read(files.path("runtime"))?, b"candidate runtime");
        let counts = (files.publishes, files.advances, files.boot_publishes);
        reverse(&mut files)?;
        files.original()?;
        assert_eq!(
            (files.publishes, files.advances, files.boot_publishes),
            counts
        );
        Ok(())
    }

    #[test]
    fn working_dispatch_reconciles_reverse_failure_without_republishing() -> Result<()> {
        let mut files = Files::new(Fault::RestoreRuntimeOnce)?;
        forward(&mut files)?;
        assert!(reverse(&mut files).is_err());
        files.original()?;
        let counts = (files.publishes, files.advances, files.boot_publishes);
        reverse(&mut files)?;
        files.original()?;
        assert_eq!(
            (files.publishes, files.advances, files.boot_publishes),
            counts
        );
        Ok(())
    }
    #[test]
    fn working_dispatch_holds_actual_package_state_until_runtime_reverse_and_retries_only_reverse()
    -> Result<()> {
        let mut files = Files::new(Fault::RestorePackagesOnce)?;
        forward(&mut files)?;
        assert!(reverse(&mut files).is_err());
        files.original()?;
        assert!(files.packages_installed);
        assert_eq!(fs::read(files.path("packages"))?, b"new normal packages");
        let counts = (
            files.installs,
            files.publishes,
            files.advances,
            files.boot_publishes,
        );
        reverse(&mut files)?;
        files.verify_complete()?;
        assert_eq!(
            (
                files.installs,
                files.publishes,
                files.advances,
                files.boot_publishes
            ),
            counts
        );
        Ok(())
    }
    #[test]
    fn working_dispatch_keeps_boot_pair_runtime_and_packages_until_actual_labels_restore()
    -> Result<()> {
        let mut files = Files::new(Fault::RestoreLabelsOnce)?;
        forward(&mut files)?;
        assert!(reverse(&mut files).is_err());
        assert!(
            files.labels_applied
                && files.boot_published
                && files.runtime_published
                && files.packages_installed
        );
        assert_eq!(files.pair_phase, 2);
        assert_eq!(files.label_applications, 1);
        reverse(&mut files)?;
        files.verify_complete()?;
        assert_eq!(files.label_applications, 1);
        Ok(())
    }
}
