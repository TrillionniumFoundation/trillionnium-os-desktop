//! The real original-kernel continuation unit, separate from the twelve
//! candidate runtime files. Its fixed normal producer/input remain private;
//! a unit file never reconstructs any old ownership or four backing locks.
#[path = "cold_working_file_custody.rs"]
mod custody;
use super::{
    super::{WorkingRecoverySources, WorkingRuntimeSources, materials::Guard, owner::SealedInput},
    Payload,
};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_data::WorkingReturnData,
    cold_working_recovery::contract as c,
    ensure, fs,
};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::File,
    path::{Path, PathBuf},
};

const SOURCE: &str = "WORKING-RECOVERY-OWNER.service";
const DIRECTORY: &str = "working-recovery-service";
// Image hashes + one finite label window + two normal package commands,
// bounded source/PID1 commands and an explicit finalization allowance.
const TIMEOUT_SECONDS: u64 = 1200 + 600 + 2 * 600 + 12 * 180 + 120;

fn literal(path: &Path) -> Result<String> {
    let value = fs::absolute_string(path)?;
    ensure(
        path.starts_with("/var/lib/droidloom-qualification")
            && path != Path::new("/var/lib/droidloom-qualification")
            && path.components().all(|p| {
                matches!(
                    p,
                    std::path::Component::RootDir | std::path::Component::Normal(_)
                )
            })
            && value
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"/._-".contains(&b)),
        "normal recovery producer/input requires private literal unit-safe paths",
    )?;
    Ok(value)
}
fn unit(candidate: &str) -> Result<String> {
    ensure(
        fs::valid_digest(candidate),
        "one normal working candidate required",
    )?;
    Ok(format!("droidloom-working-recovery@{candidate}.service"))
}
fn body(candidate: &str, program: &FilePin, input: &FilePin, work: &Path) -> Result<Vec<u8>> {
    unit(candidate)?;
    ensure(
        fs::valid_digest(&program.sha256)
            && program.bytes > 0
            && fs::valid_digest(&input.sha256)
            && input.bytes > 0,
        "recovery unit requires complete actual normal pins",
    )?;
    let program = literal(&program.path)?;
    let input_path = literal(&input.path)?;
    ensure(
        work == Path::new("/var/lib/droidloom-qualification")
            .join(format!("working-qualification-{candidate}")),
        "recovery unit escaped its one actual working source",
    )?;
    let source = literal(&work.join("BOOT-INTENT.json"))?;
    let completed = literal(&work.join("WORKING-RETURN-COMPLETED.json"))?;
    Ok(format!("[Unit]\nDescription=Droidloom working qualification original-host recovery\nAfter=local-fs.target\nBefore=display-manager.service gdm.service graphical.target droidloomd.service droidloom-production.service droidloom-instance-factory.service droidloom-instance-launcher.service droidloom-working-qualification.service droidloom-working-qualification-return.service\nConditionKernelVersion={}\nConditionKernelCommandLine=!droidloom.working\nConditionPathExists={source}\nConditionPathExists=!{completed}\nStartLimitIntervalSec=600\nStartLimitBurst=3\n\n[Service]\nType=oneshot\nExecStart={program} recover-working-qualification --config {input_path} --config-sha256 {}\nRestart=on-failure\nRestartSec=5\nKillMode=control-group\nTimeoutStartSec={TIMEOUT_SECONDS}\nTimeoutStopSec=120\nUMask=0077\nAmbientCapabilities=\nNoNewPrivileges=no\nStandardInput=null\n\n[Install]\nWantedBy=multi-user.target\n",c::ORIGINAL_KERNEL,input.sha256).into_bytes())
}
fn required(candidate: &str, source: &FilePin) -> Result<BTreeMap<PathBuf, Payload>> {
    let name = unit(candidate)?;
    Ok(BTreeMap::from([
        (
            Path::new("/etc/systemd/system").join(&name),
            Payload::Regular {
                source: source.clone(),
                mode: 0o644,
            },
        ),
        (
            Path::new("/etc/systemd/system/multi-user.target.wants").join(&name),
            Payload::Symlink {
                target: format!("../{name}"),
            },
        ),
    ]))
}
fn validate_source(
    work: &Path,
    candidate: &str,
    program: &FilePin,
    input: &FilePin,
) -> Result<Guard> {
    let pin = files::pin_file(&work.join(SOURCE))?;
    let expected = body(candidate, program, input, work)?;
    ensure(
        pin.bytes == expected.len() as u64 && pin.sha256 == fs::digest(&expected),
        "owned recovery unit differs from its compiled normal recipe and actual pins",
    )?;
    Guard::open(&pin)
}

/// Publication keeps all actual partial effects until it can reverse. Once
/// complete it releases its old parent snapshots: later root labels and other
/// normal file publication cannot silently refresh those old handles.
pub(in crate::cold_original_qualification) struct WorkingRecoveryService {
    work: PathBuf,
    candidate: String,
    source: Guard,
    program: FilePin,
    input: FilePin,
    transaction: Option<custody::Transaction>,
    published: Option<SealedInput>,
    restored: Option<FilePin>,
}
impl WorkingRecoveryService {
    pub(in crate::cold_original_qualification) fn prepare(
        source: &WorkingRuntimeSources,
    ) -> Result<Self> {
        source.revalidate()?;
        let actual = source.current_owner_evidence()?;
        let program: FilePin = serde_json::from_value(actual["actual_producer"].clone())?;
        let input: FilePin = serde_json::from_value(actual["input"].clone())?;
        let bytes = body(source.candidate(), &program, &input, source.work())?;
        let path = source.work().join(SOURCE);
        files::write_new(&path, &bytes, 0o400)?;
        File::open(source.work())?.sync_all()?;
        let held = validate_source(source.work(), source.candidate(), &program, &input)?;
        let mut transaction =
            custody::Transaction::new(source.work().join(DIRECTORY), source.candidate().into());
        transaction.initialize()?;
        let name = unit(source.candidate())?;
        transaction.stage_file(
            &Path::new("/etc/systemd/system").join(&name),
            held.pin(),
            0o644,
        )?;
        transaction.stage_symlink(
            &Path::new("/etc/systemd/system/multi-user.target.wants").join(&name),
            &format!("../{name}"),
        )?;
        source.revalidate()?;
        Ok(Self {
            work: source.work().into(),
            candidate: source.candidate().into(),
            source: held,
            program,
            input,
            transaction: Some(transaction),
            published: None,
            restored: None,
        })
    }
    fn fence(&self, source: &WorkingRuntimeSources) -> Result<()> {
        ensure(
            source.work() == self.work && source.candidate() == self.candidate,
            "recovery unit belongs to another cold owner",
        )?;
        self.source.revalidate()?;
        if let Some(record) = &self.published {
            record.revalidate()?;
        }
        source.revalidate()
    }
    pub(in crate::cold_original_qualification) fn publish(
        &mut self,
        source: &WorkingRuntimeSources,
    ) -> Result<FilePin> {
        self.fence(source)?;
        ensure(
            self.published.is_none(),
            "working recovery service is create-only",
        )?;
        let core = self
            .transaction
            .as_mut()
            .ok_or("owned service publication already released its old snapshots")?;
        for index in 0..core.len() {
            core.publish_captured(index, None)?;
        }
        let summary = core.seal_summary(false)?;
        self.published = Some(SealedInput::open(&summary)?);
        // All following mutations use a fresh actual factory, never these
        // parent inventories after runtime files or label writes changed them.
        self.transaction = None;
        self.fence(source)?;
        Ok(summary)
    }
    pub(in crate::cold_original_qualification) fn restore_live(
        &mut self,
        source: &WorkingRuntimeSources,
    ) -> Result<Option<FilePin>> {
        self.fence(source)?;
        if let Some(pin) = &self.restored {
            return Ok(Some(pin.clone()));
        }
        if self.transaction.is_none() {
            self.transaction = Some(custody::Transaction::reopen_preserved_birth(
                self.work.join(DIRECTORY),
                self.candidate.clone(),
                &required(&self.candidate, self.source.pin())?,
            )?);
        }
        let core = self.transaction.as_mut().unwrap();
        core.reconcile_pending()?;
        for index in (0..core.len()).rev() {
            let operation = core.restore(index);
            core.reconcile_pending()?;
            operation?;
        }
        ensure(
            core.all_restored(),
            "owned recovery service inverse remains incomplete",
        )?;
        let pin = core.seal_summary(true)?;
        self.restored = Some(pin.clone());
        self.fence(source)?;
        Ok(Some(pin))
    }
    pub(in crate::cold_original_qualification) fn source_pin(&self) -> &FilePin {
        self.source.pin()
    }
}

/// This runs only after actual original labels, pair and normal packages have
/// returned. The new factory holds current file/parent descriptors and exact
/// original generations; it never revives the forward service transaction.
pub(in crate::cold_original_qualification) fn restore_returned(
    data: &WorkingReturnData,
) -> Result<Option<FilePin>> {
    data.verify_original_restored()?;
    let sources = data.sources();
    let source_path = sources.work().join(SOURCE);
    match std::fs::symlink_metadata(&source_path) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            ensure(
                !sources.work().join("WORKING-RUN-INTENT.json").exists(),
                "actual physical run lost its owned recovery recipe",
            )?;
            return Ok(None);
        }
        Err(e) => return Err(e.into()),
        Ok(_) => (),
    }
    let source = validate_source(
        sources.work(),
        sources.candidate(),
        sources.owner().program_pin(),
        sources.owner().input_pin(),
    )?;
    let mut core = custody::Transaction::reopen_returned(
        sources.work().join(DIRECTORY),
        sources.candidate().into(),
        &required(sources.candidate(), source.pin())?,
        &BTreeSet::new(),
        &BTreeSet::new(),
        data.returned_label_history()?,
    )?;
    for index in (0..core.len()).rev() {
        data.verify_original_restored()?;
        source.revalidate()?;
        let operation = core.restore(index);
        core.reconcile_pending()?;
        operation?;
    }
    ensure(
        core.all_restored(),
        "returned recovery service inverse remains incomplete",
    )?;
    let value = json!({"schema":"droidloom.working-recovery-service-restored.v1",
        "candidate_id":sources.candidate(),"boot_intent":sources.boot_intent(),
        "actual_data_retirement":data.report(),"source":source.pin(),
        "completed_label_history":data.returned_label_history()?.handoff(),
        "actual":core.returned_evidence(&BTreeSet::new())?,"production_ready":false});
    let path = data
        .report()
        .path
        .parent()
        .ok_or("recovery service completion parent")?
        .join("RECOVERY-SERVICE-RESTORED.json");
    files::write_new(&path, &serde_json::to_vec(&value)?, 0o400)?;
    File::open(path.parent().unwrap())?.sync_all()?;
    let pin = files::pin_file(&path)?;
    SealedInput::open(&pin)?.revalidate()?;
    source.revalidate()?;
    data.verify_original_restored()?;
    Ok(Some(pin))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "root/ext4 only; newly created private unit/link fixture, never systemd paths"]
    fn actual_recovery_service_fresh_inverse_preserves_siblings_and_rejects_replaced_unit()
    -> Result<()> {
        for replace in [false, true] {
            ensure(
                rustix::process::geteuid().is_root(),
                "actual root private fixture required",
            )?;
            let base = fs::Tree::open("/", 0)?.dir("/var/lib/droidloom-qualification")?;
            ensure(
                rustix::fs::fstatfs(&base)?.f_type as u64 == 0xef53,
                "actual private ext4 fixture required",
            )?;
            let root = tempfile::Builder::new()
                .prefix("owned-recovery-unit-")
                .tempdir_in("/var/lib/droidloom-qualification")?;
            let public = root.path().join("units");
            files::private_dir(&public)?;
            let wants = public.join("wants");
            files::private_dir(&wants)?;
            let source = root.path().join("owner.source");
            files::write_new(
                &source,
                b"[Service]\nExecStart=/private/actual-normal\n",
                0o400,
            )?;
            let pin = files::pin_file(&source)?;
            let target = public.join("owned.service");
            let link = wants.join("owned.service");
            let work = root.path().join("publication");
            let candidate = "d".repeat(64);
            let mut transaction = custody::Transaction::new(work.clone(), candidate.clone());
            transaction.initialize()?;
            transaction.stage_file(&target, &pin, 0o644)?;
            transaction.stage_symlink(&link, "../owned.service")?;
            for index in 0..transaction.len() {
                transaction.publish_captured(index, None)?;
            }
            transaction.seal_summary(false)?;
            drop(transaction);
            // A new factory captures legitimate current sibling membership;
            // it never uses the old full parent inventory as a refresh permit.
            let sibling = public.join("unrelated");
            files::write_new(&sibling, b"keep", 0o400)?;
            if replace {
                std::fs::rename(&target, public.join("retained-original-candidate"))?;
                files::copy_pin(&pin, &target, 0o644)?;
            }
            let required = BTreeMap::from([
                (
                    target.clone(),
                    Payload::Regular {
                        source: pin,
                        mode: 0o644,
                    },
                ),
                (
                    link.clone(),
                    Payload::Symlink {
                        target: "../owned.service".into(),
                    },
                ),
            ]);
            let actual = custody::Transaction::reopen_preserved_birth(
                work.clone(),
                candidate.clone(),
                &required,
            );
            if replace {
                assert!(actual.is_err());
                continue;
            }
            let mut actual = actual?;
            for index in (0..actual.len()).rev() {
                actual.restore(index)?;
            }
            assert!(actual.all_restored());
            drop(actual);
            assert!(!target.exists() && std::fs::symlink_metadata(&link).is_err());
            assert_eq!(std::fs::read(&sibling)?, b"keep");
            let reopened =
                custody::Transaction::reopen_preserved_birth(work, candidate, &required)?;
            assert!(reopened.all_restored());
        }
        Ok(())
    }
    #[test]
    fn recovery_unit_has_one_literal_original_kernel_and_finite_owned_command() {
        let candidate = "a".repeat(64);
        let work = PathBuf::from(format!(
            "/var/lib/droidloom-qualification/working-qualification-{candidate}"
        ));
        let mut program = FilePin {
            path: "/var/lib/droidloom-qualification/normal/fixture".into(),
            bytes: 10,
            sha256: "b".repeat(64),
        };
        let input = FilePin {
            path: "/var/lib/droidloom-qualification/normal/plan.json".into(),
            bytes: 20,
            sha256: "c".repeat(64),
        };
        let text = String::from_utf8(body(&candidate, &program, &input, &work).unwrap()).unwrap();
        assert!(text.contains("ConditionKernelVersion=7.0.14-p4cred1\n"));
        assert_eq!(text.matches("ExecStart=").count(), 1);
        assert!(!text.contains("infinity"));
        assert!(text.contains(" recover-working-qualification --config "));
        for bad in [
            "/usr/bin/fixture",
            "/var/lib/droidloom-qualification/x%N",
            "/var/lib/droidloom-qualification/x$MAINPID",
            "/var/lib/droidloom-qualification/a\nExecStart=/bin/sh",
            "/var/lib/droidloom-qualification/../escape",
        ] {
            program.path = bad.into();
            assert!(body(&candidate, &program, &input, &work).is_err());
        }
    }
}
