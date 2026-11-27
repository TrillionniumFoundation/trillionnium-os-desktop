//! Capture the current original-host GRUB preimage after a real Returned once.
//! The first once's fixed initial grubenv digest is not substituted for current
//! bytes. Only the existing normal read-only grub engine is invoked here.
use super::{
    commands, materials::Guard, owner::SealedInput,
    working_qualification::PreparedWorkingCopyObservation,
};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_data::labels::OriginalLabelSources,
    cold_original_once_recovery::contract as c,
    ensure, fs,
};
use serde_json::{Value, json};
use std::{
    fs::File,
    path::{Path, PathBuf},
};

const PYTHON_BYTES: u64 = 7_477_160;
const PYTHON_SHA: &str = "52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41";

fn save(path: &Path, value: &Value) -> Result<FilePin> {
    let mut bytes = serde_json::to_vec_pretty(value)?;
    bytes.push(b'\n');
    ensure(
        bytes.len() <= 16 * 1024 * 1024,
        "bounded working GRUB evidence required",
    )?;
    files::write_new(path, &bytes, 0o400)?;
    File::open(path.parent().ok_or("working GRUB parent absent")?)?.sync_all()?;
    let pin = files::pin_file(path)?;
    SealedInput::open(&pin)?;
    Ok(pin)
}

/// This owns actual read-only preimages. It is not a grub-arm or publication
/// permit, and it never accepts externally supplied boot selection fields.
pub(super) struct WorkingGrubPreimage {
    current: Vec<Guard>,
    preserved: Vec<Guard>,
    report: SealedInput,
}
impl WorkingGrubPreimage {
    pub(super) fn capture(
        returned: &PreparedWorkingCopyObservation,
        sources: &OriginalLabelSources,
        candidate: &str,
        input: &FilePin,
        work: &Path,
    ) -> Result<Self> {
        returned.guard()?;
        sources.revalidate_custody()?;
        ensure(
            fs::valid_digest(candidate),
            "exact new working candidate required",
        )?;
        let source_dir = work.join("cold-source");
        files::private_dir(&source_dir)?;
        let mut preserved = Vec::new();
        for (relative, bytes) in crate::boot_host::cold_modules::FILES {
            let path = source_dir.join(
                Path::new(relative)
                    .file_name()
                    .ok_or("cold module basename")?,
            );
            files::write_new(&path, bytes, 0o444)?;
            preserved.push(Guard::open(&files::pin_file(&path)?)?);
        }
        let mut current = Vec::new();
        let mut preimages = Vec::new();
        for (path, limit, exact) in [
            ("/boot/grub/grub.cfg", 16 * 1024 * 1024, None),
            ("/boot/grub/grubenv", 1024, None),
            (
                "/boot/vmlinuz-7.0.14-p4cred1",
                17_134_080,
                Some((
                    17_134_080,
                    "83d50d51be0f6a2d574f6b04ab80205613383c60da7b96788c9c3122efb7b5ad",
                )),
            ),
            (
                "/boot/initrd.img-7.0.14-p4cred1",
                92_292_985,
                Some((
                    92_292_985,
                    "d9fd106a34f018fcf9805ce740b7aa3ab45cf18f3aaa1ba1335be4d4c6f8866d",
                )),
            ),
        ] {
            let pin = files::pin_file(Path::new(path))?;
            ensure(
                pin.bytes > 0
                    && pin.bytes <= limit
                    && exact.is_none_or(|(bytes, sha)| pin.bytes == bytes && pin.sha256 == sha),
                "current original boot input differs from its source-owned scope",
            )?;
            let guard = Guard::open(&pin)?;
            if path.ends_with("/grubenv") {
                ensure(
                    pin.bytes == 1024 && guard.identity().mode & 0o7777 == 0o644,
                    "current original GRUB environment shape differs",
                )?;
            }
            let copy = work.join(format!(
                "ORIGINAL-{}",
                pin.path.file_name().unwrap().to_string_lossy()
            ));
            files::copy_pin(&pin, &copy, 0o400)?;
            guard.revalidate()?;
            let copied = files::pin_file(&copy)?;
            ensure(
                copied.bytes == pin.bytes && copied.sha256 == pin.sha256,
                "GRUB preimage copy differs",
            )?;
            preserved.push(Guard::open(&copied)?);
            preimages.push(json!({"source":pin,"identity":guard.identity(),"preserved":copied}));
            current.push(guard);
        }
        let python = Guard::open(&FilePin {
            path: PathBuf::from("/usr/bin/python3.14"),
            bytes: PYTHON_BYTES,
            sha256: PYTHON_SHA.into(),
        })?;
        ensure(
            python.identity().mode & 0o7777 == 0o755,
            "normal Python executable mode differs",
        )?;
        let request = save(
            &work.join("GRUB-READ-INPUTS.json"),
            &json!({
                "schema":"droidloom.original-once-fixed-command.v1",
                "candidate_id":candidate, "intent":input, "operation":"grub-read",
                "arguments":{"original_cfg_sha256":current[0].pin().sha256},
                "materials":sources.fresh_initramfs_report()["normal_materials"]
            }),
        )?;
        let request_guard = SealedInput::open(&request)?;
        let command = files::run_logged(
            work,
            "normal-returned-grub-read",
            &python.command_path()?,
            &[
                "-I".into(),
                "-B".into(),
                "-c".into(),
                commands::historical_driver_source().into(),
                fs::absolute_string(&source_dir)?,
                fs::absolute_string(&request.path)?,
            ],
            90,
        )?;
        ensure(
            command.exit_code == Some(0) && !command.timed_out,
            "normal current GRUB read failed",
        )?;
        let actual: Value =
            serde_json::from_slice(&files::read_pin(&command.log, 16 * 1024 * 1024)?)?;
        let result = &actual["result"];
        ensure(
            actual["schema"] == "droidloom.original-once-fixed-command-result.v1"
                && actual["operation"] == "grub-read"
                && actual["candidate_id"] == candidate
                && actual["intent"] == serde_json::to_value(input)?
                && result["original"]["original_entry"] == c::ORIGINAL_ENTRY
                && result["original"]["original_default"] == c::ORIGINAL_ENTRY
                && result["before"] == result["after"]
                && result["before_fields"] == result["after_fields"]
                && result["after_fields"]
                    .as_object()
                    .ok_or("current GRUB fields absent")?
                    .get("next_entry")
                    .is_none_or(|v| v == "")
                && result["command"].is_null()
                && result["default_changed"] == false,
            "returned original GRUB is not an unchanged empty one-shot selection",
        )?;
        for guard in current.iter().chain(&preserved) {
            guard.revalidate()?;
        }
        python.revalidate()?;
        request_guard.revalidate()?;
        sources.revalidate_custody()?;
        returned.guard()?;
        let report = save(
            &work.join("WORKING-GRUB-PREIMAGE.json"),
            &json!({
                "schema":"droidloom.working-qualification-grub-preimage.v1",
                "first_once_candidate":returned.history().candidate(),
                "new_candidate":candidate,"request":request,"actual_normal_command":command,
                "normal_driver_sha256":fs::digest(commands::historical_driver_source().as_bytes()),
                "normal_python":python.pin(),"normal_python_identity":python.identity(),
                "actual":actual,"preserved":preimages,
                "original_default_changed":false,"one_shot_armed":false
            }),
        )?;
        preserved.push(python);
        let observation = Self {
            current,
            preserved,
            report: SealedInput::open(&report)?,
        };
        observation.revalidate()?;
        Ok(observation)
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        for guard in self.current.iter().chain(&self.preserved) {
            guard.revalidate()?;
        }
        self.report.revalidate()
    }
    pub(super) fn current_inputs(&self) -> Result<(FilePin, FilePin)> {
        self.revalidate()?;
        ensure(
            self.current.len() == 4
                && self.current[0].pin().path == Path::new("/boot/grub/grub.cfg")
                && self.current[1].pin().path == Path::new("/boot/grub/grubenv"),
            "actual current GRUB preimage roles differ",
        )?;
        Ok((self.current[0].pin().clone(), self.current[1].pin().clone()))
    }
    pub(super) fn pin(&self) -> &FilePin {
        self.report.pin()
    }
}
