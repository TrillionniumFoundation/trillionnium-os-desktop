//! Closed preparation graph for the actual working-qualification owner.
//! This module never accepts a command, output directory or renewed deadline.
use crate::{
    control::{NativeApplicationInspector, NativeLeafCommandKind, run_prepared_native_leaf_until},
    native_leaf_business_capture::WorkingBusinessBaseline,
    native_working_preparation::{PreparationOutput, WorkingNativePreparationStep as Step},
    physical_qualification_channel::WorkingQualificationOwner,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, DirBuilder, File, OpenOptions},
    io::Write,
    os::unix::fs::{DirBuilderExt, FileExt, MetadataExt, OpenOptionsExt},
    path::{Component, Path, PathBuf},
    process::Command,
    time::Instant,
};

type Result<T> = std::result::Result<T, String>;
const MAX: u64 = 16 * 1024 * 1024;
const SOURCES: &str = include_str!("../../droidloom-applications/src/leaf_sources.json");

fn require(ok: bool, message: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(message.into()) }
}
fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn before(end: Instant) -> Result<()> {
    crate::control::physical_qualification_channel::working_runtime::progress()?;
    require(
        Instant::now() < end,
        "original working preparation deadline expired",
    )
}
fn node(metadata: &fs::Metadata) -> [i128; 9] {
    [
        metadata.dev() as i128,
        metadata.ino() as i128,
        metadata.mode() as i128,
        metadata.uid() as i128,
        metadata.gid() as i128,
        metadata.nlink() as i128,
        metadata.len() as i128,
        metadata.mtime() as i128 * 1_000_000_000 + metadata.mtime_nsec() as i128,
        metadata.ctime() as i128 * 1_000_000_000 + metadata.ctime_nsec() as i128,
    ]
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct Pin {
    path: PathBuf,
    bytes: u64,
    sha256: String,
}
impl Pin {
    fn value(&self) -> Result<Value> {
        serde_json::to_value(self).map_err(|e| e.to_string())
    }
    fn from(value: &Value) -> Result<Self> {
        serde_json::from_value(value.clone())
            .map_err(|e| format!("fixed preparation file pin: {e}"))
    }
}

struct Held {
    pin: Pin,
    file: File,
    identity: [i128; 9],
    raw: Vec<u8>,
}
impl Held {
    fn open(pin: &Pin, end: Instant) -> Result<Self> {
        Self::open_bounded(pin, end, false)
    }
    fn open_output(pin: &Pin, end: Instant) -> Result<Self> {
        Self::open_bounded(pin, end, true)
    }
    fn open_bounded(pin: &Pin, end: Instant, empty_output: bool) -> Result<Self> {
        before(end)?;
        require(
            pin.path.is_absolute()
                && pin
                    .path
                    .components()
                    .all(|c| matches!(c, Component::RootDir | Component::Normal(_)))
                && (pin.bytes > 0 || empty_output)
                && pin.bytes <= MAX
                && digest(&pin.sha256)
                && fs::canonicalize(&pin.path).map_err(|e| e.to_string())? == pin.path,
            "fixed preparation source path or bound differs",
        )?;
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
            .open(&pin.path)
            .map_err(|e| e.to_string())?;
        let metadata = file.metadata().map_err(|e| e.to_string())?;
        require(
            metadata.is_file()
                && metadata.uid() == 0
                && metadata.gid() == 0
                && metadata.nlink() == 1
                && metadata.mode() & 0o022 == 0
                && metadata.len() == pin.bytes,
            "fixed preparation source inode differs",
        )?;
        let identity = node(&metadata);
        let mut raw = vec![0_u8; pin.bytes as usize];
        crate::control::physical_qualification_channel::working_runtime::read_exact_at_progress(&file, &mut raw, 0).map_err(|e| e.to_string())?;
        let value = Self {
            pin: pin.clone(),
            file,
            identity,
            raw,
        };
        value.recheck(end)?;
        Ok(value)
    }
    fn recheck(&self, end: Instant) -> Result<()> {
        before(end)?;
        let mut actual = vec![0_u8; self.raw.len()];
        crate::control::physical_qualification_channel::working_runtime::read_exact_at_progress(&self.file, &mut actual, 0)
            .map_err(|e| e.to_string())?;
        require(
            node(&self.file.metadata().map_err(|e| e.to_string())?) == self.identity
                && node(&fs::symlink_metadata(&self.pin.path).map_err(|e| e.to_string())?)
                    == self.identity
                && fs::canonicalize(&self.pin.path).map_err(|e| e.to_string())? == self.pin.path
                && actual == self.raw
                && hash(&actual) == self.pin.sha256,
            "held preparation file or its complete content changed",
        )?;
        before(end)
    }
    fn json(&self) -> Result<Value> {
        serde_json::from_slice(&self.raw).map_err(|e| e.to_string())
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Source {
    index: usize,
    entry: Pin,
    preparation: Pin,
}
fn source(step: Step) -> Result<Source> {
    let mut rows: Vec<Source> = serde_json::from_str(SOURCES).map_err(|e| e.to_string())?;
    require(
        rows.len() == 14 && rows.iter().enumerate().all(|(i, s)| i == s.index),
        "compiled normal preparation source roster differs",
    )?;
    let index = step.description().source_index;
    require(index < rows.len(), "fixed preparation source index absent")?;
    Ok(rows.remove(index))
}

fn exact(value: &Value, keys: &[&str]) -> bool {
    value
        .as_object()
        .is_some_and(|map| map.len() == keys.len() && keys.iter().all(|key| map.contains_key(*key)))
}
fn request_keys(step: Step) -> Result<Vec<&'static str>> {
    let description = step.description();
    require(
        !description.ihg_factory,
        "IHG preparation requires its dedicated inventory factory",
    )?;
    let keys = if description.mode == "identity" {
        vec!["baseline", "qualification"]
    } else if description.mode == "build"
        || description.mode == "pm-help"
        || (description.mode == "plan" && description.source_index == 4)
    {
        vec!["source"]
    } else if description.mode == "plan" && matches!(description.source_index, 6 | 7) {
        vec!["source", "build", "pm_help"]
    } else if description.mode == "source" && description.source_index == 4 {
        vec![
            "kind",
            "baseline",
            "qualification",
            "target_identity",
            "native_identity",
        ]
    } else if description.mode == "source" && matches!(description.source_index, 6 | 7) {
        vec![
            "baseline",
            "qualification",
            "target_identity",
            "provider_identity",
            "native_identity",
        ]
    } else if description.mode == "plan" && matches!(description.source_index, 0 | 1) {
        vec![
            "baseline",
            "qualification",
            "target_identity",
            "provider_identity",
            "helper_identity",
        ]
    } else if description.mode == "plan" && matches!(description.source_index, 2 | 13) {
        vec![
            "baseline",
            "qualification",
            "target_identity",
            "helper_identity",
        ]
    } else {
        return Err("unimplemented closed native preparation request".into());
    };
    Ok(keys)
}

fn clock_kind(step: Step) -> Option<&'static str> {
    match step {
        Step::ClockTimer15Source => Some("timer15"),
        Step::ClockExpiry06Source => Some("expiry06"),
        Step::ClockAlarm04Source => Some("alarm04"),
        _ => None,
    }
}
fn expected_reference(step: Step, key: &str, root: &Path) -> Result<PathBuf> {
    let d = step.description();
    let input_case = if d.source_index == 4 {
        "clock-timer-pair"
    } else {
        d.case_name
    };
    let role = match key {
        "target_identity" => match d.source_index {
            0 if d.case_name == "contacts-search" => "contacts",
            0 | 1 => "calendar",
            2 => "camera",
            4 => "clock",
            6 | 7 => "documents",
            13 => "settings",
            _ => return Err("unlisted actual target identity".into()),
        },
        "provider_identity" => match d.source_index {
            0 if d.case_name == "contacts-search" => "contacts-provider",
            0 | 1 => "calendar-provider",
            6 | 7 => "provider",
            _ => return Err("unlisted actual provider identity".into()),
        },
        "helper_identity" | "native_identity" => "native-helper",
        "source" => {
            return Ok(root
                .join("native-cases")
                .join(d.case_name)
                .join(if d.source_index == 4 {
                    "case-source.json"
                } else {
                    "helper-source.json"
                }));
        }
        "build" => {
            return Ok(root
                .join("native-inputs")
                .join(d.case_name)
                .join("helper-build/build-result.json"));
        }
        "pm_help" => {
            return Ok(root
                .join("native-inputs")
                .join(d.case_name)
                .join("pm-help/result.json"));
        }
        _ => return Err("unlisted preparation reference role".into()),
    };
    Ok(root
        .join("native-inputs")
        .join(input_case)
        .join(format!("identity-{role}/result.json")))
}

fn request(
    step: Step,
    value: &Value,
    baseline: &Value,
    root: &Path,
    end: Instant,
    held: &mut Vec<Held>,
) -> Result<()> {
    let keys = request_keys(step)?;
    require(
        exact(value, &keys),
        "fixed preparation request has missing or extra fields",
    )?;
    for key in keys {
        if key == "kind" {
            require(
                value[key].as_str() == clock_kind(step),
                "fixed Clock source kind differs",
            )?;
            continue;
        }
        if matches!(key, "baseline" | "qualification") {
            require(
                value[key] == baseline[key],
                "request substituted the actual captured baseline",
            )?;
        } else {
            require(
                Pin::from(&value[key])?.path == expected_reference(step, key, root)?,
                "preparation request substituted a fixed preceding step",
            )?;
        }
        held.push(Held::open(&Pin::from(&value[key])?, end)?);
    }
    Ok(())
}

fn output_path(step: Step, root: &Path) -> PathBuf {
    let d = step.description();
    match d.output {
        PreparationOutput::Input => root.join("native-inputs").join(d.case_name).join(d.purpose),
        PreparationOutput::BasePlan => root
            .join("native-inputs")
            .join(d.case_name)
            .join("base-plan"),
        PreparationOutput::Case | PreparationOutput::BoundCase => {
            root.join("native-cases").join(d.case_name)
        }
    }
}
fn private_directory(path: &Path) -> Result<()> {
    let actual = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
    require(
        actual.is_dir()
            && actual.uid() == 0
            && actual.gid() == 0
            && actual.mode() & 0o7777 == 0o700
            && fs::canonicalize(path).map_err(|e| e.to_string())? == path,
        "fixed native preparation directory is not private and canonical",
    )
}
fn save(
    directory: &Path,
    name: &str,
    raw: &[u8],
    end: Instant,
    held: &mut Vec<Held>,
) -> Result<Pin> {
    before(end)?;
    private_directory(directory)?;
    require(
        !name.contains('/') && raw.len() as u64 <= MAX,
        "bounded preparation evidence required",
    )?;
    let path = directory.join(name);
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o400)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(&path)
        .map_err(|e| e.to_string())?;
    file.write_all(raw)
        .and_then(|_| file.sync_all())
        .map_err(|e| e.to_string())?;
    File::open(directory)
        .and_then(|f| f.sync_all())
        .map_err(|e| e.to_string())?;
    let pin = Pin {
        path,
        bytes: raw.len() as u64,
        sha256: hash(raw),
    };
    // Empty stdout/stderr is legitimate evidence. All other held inputs are nonempty.
    held.push(Held::open_output(&pin, end)?);
    Ok(pin)
}

fn command(step: Step, selected: &Source, request: &Pin, output: &Path) -> Result<Command> {
    let d = step.description();
    request_keys(step)?;
    let mut cmd = Command::new("/usr/bin/python3");
    cmd.env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LANG", "C.UTF-8")
        .env("LC_ALL", "C.UTF-8");
    cmd.args(["-I", "-B"])
        .arg(&selected.entry.path)
        .arg("--preparation")
        .arg(&selected.preparation.path)
        .arg("--expect-preparation-sha256")
        .arg(&selected.preparation.sha256)
        .arg(d.mode)
        .arg("--request")
        .arg(&request.path)
        .arg("--expect-request-sha256")
        .arg(&request.sha256);
    if let Some(role) = d.role {
        cmd.arg("--role").arg(role);
    }
    if let Some(kind) = d.kind {
        cmd.arg("--kind").arg(kind);
    }
    if d.output != PreparationOutput::BoundCase {
        cmd.arg("--output").arg(output);
    }
    Ok(cmd)
}

/// Complete actual invocation evidence; it cannot be reconstructed from a receipt.
pub struct WorkingPreparationExecution<'a> {
    owner: &'a WorkingQualificationOwner,
    result: Value,
    report: Value,
    held: Vec<Held>,
    end: Instant,
}
impl WorkingPreparationExecution<'_> {
    pub fn result_pin(&self) -> &Value {
        &self.result
    }
    pub fn comparison_receipt(&self) -> &Value {
        &self.report
    }
    pub fn recheck(&self) -> Result<()> {
        self.owner.guard()?;
        for file in &self.held {
            file.recheck(self.end)?;
        }
        before(self.end)
    }
}

/// Execute one of forty non-IHG nodes. The other six nodes have their own
/// complete package-inventory and single-helper-installation factory.
pub fn run_working<'a>(
    step: Step,
    request_sha256: &str,
    inspector: &mut NativeApplicationInspector,
    capture: &mut WorkingBusinessBaseline<'a>,
) -> Result<WorkingPreparationExecution<'a>> {
    let d = step.description();
    request_keys(step)?;
    let owner = capture.owner();
    owner.guard()?;
    capture.recheck()?;
    let end = owner.preparation_deadline();
    before(end)?;
    let root = owner.runtime_evidence_directory()?.to_owned();
    let input_case = root.join("native-inputs").join(d.case_name);
    private_directory(&input_case)?;
    let request_path = input_case.join(format!("{}.request.json", d.purpose));
    let metadata = fs::symlink_metadata(&request_path).map_err(|e| e.to_string())?;
    require(
        metadata.mode() & 0o7777 == 0o400 && metadata.len() <= 131_072,
        "fixed preparation request must be an immutable bounded file",
    )?;
    let request_pin = Pin {
        path: request_path,
        bytes: metadata.len(),
        sha256: request_sha256.into(),
    };
    let request_file = Held::open(&request_pin, end)?;
    let request_value = request_file.json()?;
    let selected = source(step)?;
    let mut held = vec![
        Held::open(&selected.entry, end)?,
        Held::open(&selected.preparation, end)?,
        request_file,
    ];
    request(
        step,
        &request_value,
        capture.comparison_receipt(),
        &root,
        end,
        &mut held,
    )?;
    let output = output_path(step, &root);
    if d.output == PreparationOutput::BoundCase {
        private_directory(&output)?;
    } else {
        match fs::symlink_metadata(&output) {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
            _ => {
                return Err(
                    "fixed preparation output already exists; automatic replay forbidden".into(),
                );
            }
        }
    }
    let evidence = input_case.join(format!("{}.evidence", d.purpose));
    DirBuilder::new()
        .mode(0o700)
        .create(&evidence)
        .map_err(|e| e.to_string())?;
    private_directory(&evidence)?;
    let cmd = command(step, &selected, &request_pin, &output)?;
    let resources = if step.is_documents_build() {
        Some(owner.begin_documents_build_resources()?)
    } else {
        None
    };
    let actual = {
        let baseline = capture.observation_mut()?;
        let epoch = baseline.application().epoch.clone();
        run_prepared_native_leaf_until(
            cmd,
            &epoch,
            NativeLeafCommandKind::Standard {
                budget: step.child_budget(),
            },
            inspector,
            baseline,
            end,
        )
    };
    // finish checks the actual owned-probe is gone before restoring limits.
    // If retirement is uncertain it poisons the owner; it cannot fabricate success.
    if let Some(scope) = resources {
        scope.finish()?;
    }
    let actual = match actual {
        Ok(value) => value,
        Err(error) => {
            let raw = serde_json::to_vec_pretty(&json!({
                "schema":"droidloom.working-native-preparation-failed.v1",
                "case":d.case_name,"purpose":d.purpose,"request":request_pin,
                "actual_error":error,"actual_exit":Value::Null,"automatic_retry":false
            }))
            .map_err(|e| e.to_string())?;
            let _ = save(&evidence, "FAILED.json", &raw, end, &mut held);
            return Err(error);
        }
    };
    let stdout = save(&evidence, "entry.stdout", &actual.stdout, end, &mut held)?;
    let stderr = save(&evidence, "entry.stderr", &actual.stderr, end, &mut held)?;
    let execution = json!({
        "schema":"droidloom.working-native-preparation-invocation.v1",
        "case":d.case_name,"purpose":d.purpose,"request":request_pin,
        "entry":selected.entry,"preparation":selected.preparation,
        "actual_exit":actual.status.code(),"stdout":stdout,"stderr":stderr,
        "owned_cgroup_empty_and_direct_child_reaped":true,"automatic_retry":false,
        "whole_app_business_accepted":false
    });
    save(
        &evidence,
        "EXECUTION.json",
        &serde_json::to_vec_pretty(&execution).map_err(|e| e.to_string())?,
        end,
        &mut held,
    )?;
    require(
        actual.status.success() && actual.stderr.is_empty(),
        "fixed native preparation failed; preserve its original output",
    )?;
    let printed: Value =
        serde_json::from_slice(&actual.stdout).map_err(|e| format!("preparation stdout: {e}"))?;
    require(
        exact(&printed, &["result", "whole_app_business_accepted"])
            && printed["whole_app_business_accepted"] == false,
        "fixed native preparation stdout contract differs",
    )?;
    let result_pin = Pin::from(&printed["result"])?;
    require(
        result_pin.path == output.join(d.result_name),
        "fixed preparation returned another result pathname",
    )?;
    held.push(Held::open(&result_pin, end)?);
    for file in &held {
        file.recheck(end)?;
    }
    {
        let baseline = capture.observation_mut()?;
        let after_application = inspector
            .inspect_observed_until(&baseline.application().package, 0, end)
            .map_err(|e| e.to_string())?;
        let after_main = inspector
            .refresh_main_until(baseline.main(), end)
            .map_err(|e| e.to_string())?;
        baseline
            .finish_from_observed(inspector, &after_main, &after_application, end)
            .map_err(|e| e.to_string())?;
    }
    capture.recheck()?;
    let result = result_pin.value()?;
    let value = WorkingPreparationExecution {
        owner,
        result: result.clone(),
        held,
        end,
        report: json!({
            "schema":"droidloom.working-native-preparation-execution.v1",
            "case":d.case_name,"purpose":d.purpose,"result":result,
            "actual_invocation":execution,"actual_main_and_target_bookends_equal":true,
            "comparison_only":true,"business_acceptance_evaluated":false,
            "whole_app_business_accepted":false,"production_ready":false,"automatic_retry":false
        }),
    };
    value.recheck()?;
    Ok(value)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::native_working_preparation::WORKING_NATIVE_PREPARATION_STEPS;
    #[test]
    fn closed_preparation_commands_cover_only_the_forty_non_installing_nodes() {
        let mut count = 0;
        for step in WORKING_NATIVE_PREPARATION_STEPS {
            if step.description().ihg_factory {
                assert!(request_keys(step).is_err());
                continue;
            }
            count += 1;
            let source = source(step).unwrap();
            let pin = Pin {
                path: "/fixed/request.json".into(),
                bytes: 2,
                sha256: "a".repeat(64),
            };
            let cmd = command(step, &source, &pin, Path::new("/fixed/output")).unwrap();
            assert_eq!(cmd.get_program(), "/usr/bin/python3");
            let args = cmd
                .get_args()
                .map(|v| v.to_str().unwrap())
                .collect::<Vec<_>>();
            assert_eq!(&args[..2], &["-I", "-B"]);
            assert!(
                !args.contains(&"--kind")
                    || matches!(
                        step,
                        Step::CalendarCorePlan
                            | Step::CalendarReminderPlan
                            | Step::ContactsSearchPlan
                    )
            );
            assert_eq!(
                args.contains(&"--output"),
                step.description().output != PreparationOutput::BoundCase
            );
        }
        assert_eq!(count, 40);
    }
    #[test]
    fn fixed_request_roles_do_not_alias_another_case_or_repurpose_a_clock_plan() {
        let root = Path::new("/fixed");
        assert_eq!(clock_kind(Step::ClockTimer15Source), Some("timer15"));
        assert_eq!(clock_kind(Step::ClockExpiry06Source), Some("expiry06"));
        assert_eq!(clock_kind(Step::ClockAlarm04Source), Some("alarm04"));
        assert_eq!(clock_kind(Step::ClockAlarm04Plan), None);
        assert_eq!(
            expected_reference(Step::ClockAlarm04Source, "target_identity", root).unwrap(),
            root.join("native-inputs/clock-timer-pair/identity-clock/result.json")
        );
        assert_ne!(
            expected_reference(Step::DocumentsSafPlan, "source", root).unwrap(),
            expected_reference(Step::DocumentsSearchPlan, "source", root).unwrap()
        );
        let ordinary = json!({"source":{}});
        assert!(exact(
            &ordinary,
            &request_keys(Step::ClockTimer15Plan).unwrap()
        ));
        assert!(!exact(
            &json!({"source":{},"command":"/bin/sh"}),
            &request_keys(Step::ClockTimer15Plan).unwrap()
        ));
        assert!(expected_reference(Step::CalendarCorePlan, "command", root).is_err());
    }
}
