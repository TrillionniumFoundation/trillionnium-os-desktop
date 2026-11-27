//! Produce the complete physical plan from the actual fixed working owner.
//! Inputs are source commitments; no saved receipt grants runtime acceptance.
use super::{
    ApplicationPlan, FilePin, GateRegistry, RuntimePlan, leaf_release,
    leaf_routes::{self, LeafPlan, Route},
    physical_acceptance, physical_gate_roster as roster, runtime_identity, runtime_prepare,
    validate,
};
use droidloom_supervisor::{
    control::{DEFAULT_CONTROL_SOCKET, NativeApplicationInspector},
    native_ihg_preparation::{self, IhgPreparationExecution, IhgPreparationMode},
    native_leaf_business_capture::{
        WorkingBusinessBaseline, capture_working_business_from_observed,
    },
    native_working_preparation::{
        WORKING_NATIVE_PREPARATION_STEPS, WorkingNativePreparationStep as Step,
    },
    native_working_preparation_execution::{self, WorkingPreparationExecution},
    physical_qualification_channel::{
        WorkingPreparationDirectory, WorkingQualificationOwner, layout,
    },
};
use serde::Serialize;
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, DirBuilder, File, OpenOptions},
    io::Write,
    os::fd::AsRawFd,
    os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt},
    path::{Path, PathBuf},
    time::Instant,
};

type Result<T> = std::result::Result<T, String>;
const MAX: u64 = 16 * 1024 * 1024;
const NOFOLLOW: i32 = 0x20000;
const DIRECTORY: i32 = 0x10000;
const INPUT_DOCUMENTS: [&str; 4] = layout::WORKING_APPLICATION_INPUT_FILES;
fn require(ok: bool, why: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(why.into()) }
}
fn pin_value(value: &Value) -> Result<FilePin> {
    serde_json::from_value(value.clone()).map_err(|e| format!("actual preparation result pin: {e}"))
}
fn digest(raw: &[u8]) -> String {
    hex::encode(Sha256::digest(raw))
}

struct Directory {
    file: File,
    identity: [u64; 5],
}
struct Record {
    pin: FilePin,
    file: File,
    identity: [u64; 9],
}

/// Names resolve through retained directory descriptors. Directory membership
/// may grow only through the fixed preparation; held file bodies remain exact.
struct PreparedFiles<'a> {
    owner: &'a WorkingQualificationOwner,
    root: PathBuf,
    directories: BTreeMap<PathBuf, Directory>,
    records: Vec<Record>,
}
impl<'a> PreparedFiles<'a> {
    fn new(owner: &'a WorkingQualificationOwner) -> Result<Self> {
        owner.guard()?;
        Ok(Self {
            owner,
            root: owner.runtime_evidence_directory()?.into(),
            directories: BTreeMap::new(),
            records: Vec::new(),
        })
    }
    fn before(&self) -> Result<()> {
        self.owner.guard()?;
        require(
            Instant::now() < self.owner.preparation_deadline(),
            "physical preparation exceeded its original PID1-derived end",
        )
    }
    fn anchored(&self, path: &Path) -> Result<PathBuf> {
        if path == Path::new("/") {
            return Ok(path.into());
        }
        let parent = self
            .directories
            .get(path.parent().ok_or("input parent absent")?)
            .ok_or("input parent descriptor is not held")?;
        Ok(
            PathBuf::from(format!("/proc/self/fd/{}", parent.file.as_raw_fd()))
                .join(path.file_name().ok_or("input basename absent")?),
        )
    }
    fn directory(&mut self, path: &Path) -> Result<()> {
        self.before()?;
        if self.directories.contains_key(path) {
            return self.check_directory(path);
        }
        if let Some(parent) = path.parent() {
            self.directory(parent)?;
        }
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(NOFOLLOW | DIRECTORY)
            .open(self.anchored(path)?)
            .map_err(|e| e.to_string())?;
        let observed = leaf_release::f9(&file.metadata().map_err(|e| e.to_string())?)?;
        let identity: [u64; 5] = observed[..5].try_into().map_err(|_| "directory identity")?;
        let build_root = ["documents-saf", "documents-search-sort", "ihg-london"]
            .iter()
            .any(|case| {
                path == self
                    .root
                    .join("native-inputs")
                    .join(case)
                    .join("helper-build")
            });
        let expected_owner = if build_root { [1000, 1000] } else { [0, 0] };
        require(
            identity[2] & 0o170000 == 0o040000
                && identity[3..5] == expected_owner
                && identity[2] & 0o022 == 0
                && (!path.starts_with(&self.root) || identity[2] & 0o7777 == 0o700),
            "fixed physical preparation parent is not root protected",
        )?;
        self.directories
            .insert(path.into(), Directory { file, identity });
        self.check_directory(path)
    }
    fn check_directory(&self, path: &Path) -> Result<()> {
        let held = &self.directories[path];
        require(
            leaf_release::f9(&held.file.metadata().map_err(|e| e.to_string())?)?[..5]
                == held.identity
                && leaf_release::f9(
                    &fs::symlink_metadata(self.anchored(path)?).map_err(|e| e.to_string())?,
                )?[..5]
                    == held.identity
                && leaf_release::f9(&fs::symlink_metadata(path).map_err(|e| e.to_string())?)?[..5]
                    == held.identity,
            "physical preparation held directory or pathname changed",
        )
    }
    fn mkdir(&mut self, path: &Path) -> Result<()> {
        self.before()?;
        require(
            path.starts_with(&self.root) && path != self.root,
            "preparation cannot create a directory outside this actual owner",
        )?;
        self.directory(path.parent().ok_or("new input parent absent")?)?;
        DirBuilder::new()
            .mode(0o700)
            .create(self.anchored(path)?)
            .map_err(|e| e.to_string())?;
        self.directory(path)?;
        self.directories[path.parent().unwrap()]
            .file
            .sync_all()
            .map_err(|e| e.to_string())
    }
    fn read(&mut self, pin: &FilePin) -> Result<Vec<u8>> {
        self.before()?;
        require(
            pin.bytes > 0
                && pin.bytes <= MAX
                && crate::release::valid_sha(&pin.sha256)
                && pin.path.is_absolute()
                && pin.path.canonicalize().map_err(|e| e.to_string())? == pin.path,
            "physical preparation requires a complete canonical bounded file",
        )?;
        self.directory(pin.path.parent().ok_or("input parent absent")?)?;
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(NOFOLLOW)
            .open(self.anchored(&pin.path)?)
            .map_err(|e| e.to_string())?;
        let identity = leaf_release::f9(&file.metadata().map_err(|e| e.to_string())?)?;
        require(
            identity[2] & 0o170000 == 0o100000
                && identity[2] & 0o022 == 0
                && identity[3..6] == [0, 0, 1]
                && identity[6] == pin.bytes,
            "physical input inode, ownership or complete length differs",
        )?;
        let raw = leaf_release::body(&file, pin.bytes)?;
        require(
            digest(&raw) == pin.sha256
                && leaf_release::f9(&file.metadata().map_err(|e| e.to_string())?)? == identity
                && leaf_release::f9(
                    &fs::symlink_metadata(self.anchored(&pin.path)?).map_err(|e| e.to_string())?,
                )? == identity,
            "physical input changed during its held complete read",
        )?;
        self.records.push(Record {
            pin: pin.clone(),
            file,
            identity,
        });
        Ok(raw)
    }
    fn save<T: Serialize>(&mut self, path: &Path, value: &T) -> Result<FilePin> {
        self.before()?;
        require(
            path.starts_with(&self.root),
            "fixed preparation output escaped its owner",
        )?;
        self.directory(path.parent().ok_or("output parent absent")?)?;
        let mut raw = serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?;
        raw.push(b'\n');
        require(raw.len() as u64 <= MAX, "physical plan output is too large")?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o400)
            .custom_flags(NOFOLLOW)
            .open(self.anchored(path)?)
            .map_err(|e| e.to_string())?;
        file.write_all(&raw)
            .and_then(|_| file.sync_all())
            .map_err(|e| e.to_string())?;
        self.directories[path.parent().unwrap()]
            .file
            .sync_all()
            .map_err(|e| e.to_string())?;
        let pin = FilePin {
            path: path.into(),
            bytes: raw.len() as u64,
            sha256: digest(&raw),
        };
        require(
            self.read(&pin)? == raw,
            "physical plan complete output readback differs",
        )?;
        require(
            self.records.last().unwrap().identity[2] == 0o100400,
            "physical plan output did not retain mode 0400",
        )?;
        Ok(pin)
    }
    fn guard(&self) -> Result<()> {
        self.before()?;
        for path in self.directories.keys() {
            self.check_directory(path)?;
        }
        for record in &self.records {
            require(
                leaf_release::f9(&record.file.metadata().map_err(|e| e.to_string())?)?
                    == record.identity
                    && leaf_release::f9(
                        &fs::symlink_metadata(self.anchored(&record.pin.path)?)
                            .map_err(|e| e.to_string())?,
                    )? == record.identity
                    && leaf_release::f9(
                        &fs::symlink_metadata(&record.pin.path).map_err(|e| e.to_string())?,
                    )? == record.identity
                    && digest(&leaf_release::body(&record.file, record.pin.bytes)?)
                        == record.pin.sha256
                    && leaf_release::f9(&record.file.metadata().map_err(|e| e.to_string())?)?
                        == record.identity,
                "prepared physical input lost actual inode or complete body custody",
            )?;
        }
        self.before()
    }
}

struct MaterialInputs {
    selection: FilePin,
    signatures: FilePin,
    gates: FilePin,
}
fn admitted_inputs(
    owner: &WorkingQualificationOwner,
    files: &mut PreparedFiles<'_>,
) -> Result<MaterialInputs> {
    let (bytes, sha256) = owner.admitted_materials_pin()?;
    let admitted = FilePin {
        path: owner.admitted_materials_path()?.into(),
        bytes,
        sha256: sha256.into(),
    };
    let body = leaf_release::json(&files.read(&admitted)?)?;
    require(
        body["schema"] == "droidloom.working-qualification-admitted-materials.v1"
            && body["candidate_id"].as_str() == Some(owner.source_pins()?.candidate_id.as_str()),
        "actual cold admitted materials identify another candidate",
    )?;
    let rows = body["public_materials"]["documents"]
        .as_array()
        .ok_or("four actual admitted public material documents absent")?;
    require(
        rows.len() == INPUT_DOCUMENTS.len(),
        "complete four-role public material closure required",
    )?;
    let directory = owner.input_directory()?;
    let mut inputs = Vec::new();
    for (name, row) in INPUT_DOCUMENTS.iter().zip(rows) {
        let original = pin_value(&row["source"])?;
        let copied = FilePin {
            path: directory.join(name),
            bytes: original.bytes,
            sha256: original.sha256,
        };
        files.read(&copied)?;
        inputs.push(copied);
    }
    let gates = FilePin {
        path: directory.join("gate-registry.json"),
        bytes: roster::REGISTRY_BYTES,
        sha256: roster::REGISTRY_SHA256.into(),
    };
    files.read(&gates)?;
    let mut names = fs::read_dir(directory)
        .map_err(|e| e.to_string())?
        .map(|e| {
            e.map_err(|e| e.to_string()).and_then(|e| {
                e.file_name()
                    .into_string()
                    .map_err(|_| "non-UTF8 runtime input".into())
            })
        })
        .collect::<Result<Vec<_>>>()?;
    names.sort();
    let mut expected = INPUT_DOCUMENTS
        .iter()
        .map(|n| n.to_string())
        .collect::<Vec<_>>();
    expected.extend([
        "ADMITTED-MATERIALS.json".into(),
        "gate-registry.json".into(),
    ]);
    expected.sort();
    require(
        names == expected,
        "working runtime inputs contain an unlisted or missing member",
    )?;
    files.guard()?;
    Ok(MaterialInputs {
        selection: inputs.remove(0),
        signatures: inputs.remove(0),
        gates,
    })
}

type Results = BTreeMap<(&'static str, &'static str), FilePin>;
fn prior(results: &Results, case: &'static str, purpose: &'static str) -> Result<Value> {
    serde_json::to_value(
        results
            .get(&(case, purpose))
            .ok_or_else(|| format!("actual preceding preparation absent: {case}/{purpose}"))?,
    )
    .map_err(|e| e.to_string())
}
fn source_request(
    step: Step,
    capture: &WorkingBusinessBaseline<'_>,
    results: &Results,
) -> Result<Value> {
    let d = step.description();
    let mut request = Map::new();
    let baseline = capture.comparison_receipt();
    let mut baseline_fields = || {
        request.insert("baseline".into(), baseline["baseline"].clone());
        request.insert("qualification".into(), baseline["qualification"].clone());
    };
    if d.ihg_factory {
        match step {
            Step::IhgTargetIdentity | Step::IhgHelperSource => baseline_fields(),
            Step::IhgHelperBuild => {
                request.insert(
                    "source".into(),
                    prior(results, "ihg-london", "helper-source")?,
                );
            }
            Step::IhgHelperInstall => {
                request.insert(
                    "build".into(),
                    prior(results, "ihg-london", "helper-build")?,
                );
                request.insert(
                    "target_identity".into(),
                    prior(results, "ihg-london", "target-identity")?,
                );
            }
            Step::IhgHelperIdentity => {
                baseline_fields();
                for (key, purpose) in [
                    ("build", "helper-build"),
                    ("install", "helper-install"),
                    ("target_identity", "target-identity"),
                ] {
                    request.insert(key.into(), prior(results, "ihg-london", purpose)?);
                }
            }
            Step::IhgPlan => {
                baseline_fields();
                for (key, purpose) in [
                    ("target_identity", "target-identity"),
                    ("helper_identity", "helper-identity"),
                    ("helper_build", "helper-build"),
                    ("helper_install", "helper-install"),
                ] {
                    request.insert(key.into(), prior(results, "ihg-london", purpose)?);
                }
            }
            _ => return Err("unlisted fixed IHG preparation node".into()),
        }
    } else if d.mode == "identity" {
        baseline_fields();
    } else if matches!(d.mode, "build" | "pm-help")
        || (d.mode == "plan" && matches!(d.source_index, 4 | 6 | 7))
    {
        request.insert("source".into(), prior(results, d.case_name, "source")?);
        if d.mode == "plan" && matches!(d.source_index, 6 | 7) {
            request.insert("build".into(), prior(results, d.case_name, "helper-build")?);
            request.insert("pm_help".into(), prior(results, d.case_name, "pm-help")?);
        }
    } else {
        baseline_fields();
        let (identity_case, target, provider, helper_key) = match d.source_index {
            0 if d.case_name == "contacts-search" => (
                d.case_name,
                "identity-contacts",
                Some("identity-contacts-provider"),
                "helper_identity",
            ),
            0 | 1 => (
                d.case_name,
                "identity-calendar",
                Some("identity-calendar-provider"),
                "helper_identity",
            ),
            2 => (d.case_name, "identity-camera", None, "helper_identity"),
            4 => (
                "clock-timer-pair",
                "identity-clock",
                None,
                "native_identity",
            ),
            6 | 7 => (
                d.case_name,
                "identity-documents",
                Some("identity-provider"),
                "native_identity",
            ),
            13 => (d.case_name, "identity-settings", None, "helper_identity"),
            _ => return Err("unlisted closed native preparation source".into()),
        };
        request.insert(
            "target_identity".into(),
            prior(results, identity_case, target)?,
        );
        request.insert(
            helper_key.into(),
            prior(results, identity_case, "identity-native-helper")?,
        );
        if let Some(provider) = provider {
            request.insert(
                "provider_identity".into(),
                prior(results, identity_case, provider)?,
            );
        }
        if d.source_index == 4 {
            let kind = match step {
                Step::ClockTimer15Source => "timer15",
                Step::ClockExpiry06Source => "expiry06",
                Step::ClockAlarm04Source => "alarm04",
                _ => return Err("unlisted Clock source node".into()),
            };
            request.insert("kind".into(), kind.into());
        }
    }
    Ok(Value::Object(request))
}

fn package_for_step(step: Step) -> Result<&'static str> {
    let d = step.description();
    match d.source_index {
        0 if d.case_name == "contacts-search" => Ok("com.android.contacts"),
        0 | 1 => Ok("com.android.calendar"),
        2 => Ok("com.android.camera2"),
        4 => Ok("com.android.deskclock"),
        5 => Ok("com.ihg.apps.android"),
        6 | 7 => Ok("com.android.documentsui"),
        13 => Ok("com.android.settings"),
        _ => Err("closed preparation step has no source-owned target".into()),
    }
}

enum Execution<'a> {
    Native(WorkingPreparationExecution<'a>),
    Ihg(IhgPreparationExecution),
}
impl Execution<'_> {
    fn result(&self) -> &Value {
        match self {
            Self::Native(v) => v.result_pin(),
            Self::Ihg(v) => v.result_pin(),
        }
    }
    fn recheck(&mut self) -> Result<()> {
        match self {
            Self::Native(v) => v.recheck(),
            Self::Ihg(v) => v.recheck(),
        }
    }
}

fn case_name(route: Route) -> Result<&'static str> {
    match route {
        Route::CalendarCore => Ok("calendar-core"),
        Route::CalendarReminder => Ok("calendar-reminder"),
        Route::ContactsSearch => Ok("contacts-search"),
        Route::CameraPhoto => Ok("camera-photo"),
        Route::ClockTimerPair => Ok("clock-timer-pair"),
        Route::ClockAlarm => Ok("clock-alarm"),
        Route::DocumentsSaf => Ok("documents-saf"),
        Route::DocumentsSearchSort => Ok("documents-search-sort"),
        Route::SettingsSupportedPages => Ok("settings-supported-pages"),
        Route::IhgLondon => Ok("ihg-london"),
        Route::GalleryRotation => Ok("gallery-image-rotation"),
        Route::GalleryVideo => Ok("gallery-image-video"),
        Route::GallerySeek => Ok("gallery-image-seek"),
        Route::GalleryAlbum => Ok("gallery-image-album"),
        _ => Err("physical source roster contains an unsupported preparation route".into()),
    }
}

fn build_leaf(
    route: Route,
    capture: &WorkingBusinessBaseline<'_>,
    results: &Results,
    files: &mut PreparedFiles<'_>,
) -> Result<LeafPlan> {
    let name = case_name(route)?;
    let root = files.root.clone();
    let request = match route {
        Route::CalendarCore
        | Route::CalendarReminder
        | Route::ContactsSearch
        | Route::SettingsSupportedPages => json!({"base_plan":prior(results,name,"plan")?}),
        Route::CameraPhoto => {
            let (_, catalog) = leaf_routes::compiled_release_sources();
            let rows: Vec<Value> = serde_json::from_str(catalog).map_err(|e| e.to_string())?;
            require(
                rows.len() == 14 && rows[2]["index"] == 2,
                "compiled Camera source absent",
            )?;
            let preparation = pin_value(&rows[2]["preparation"])?;
            files.read(&preparation)?;
            json!({"schema":"pocket4-camera-photo-display-input-v1",
                "plan":prior(results,name,"plan")?,"source_preparation":preparation,
                "automatic_retry":false,"whole_app_business_accepted":false})
        }
        Route::ClockTimerPair => {
            let timer = files.save(
                &root.join("native-inputs/clock-timer15/execute.request.json"),
                &json!({"plan":prior(results,"clock-timer15","plan")?}),
            )?;
            let expiry = files.save(
                &root.join("native-inputs/clock-expiry06/execute.request.json"),
                &json!({"plan":prior(results,"clock-expiry06","plan")?}),
            )?;
            json!({"schema":"droidloom.clock-timer-pair-request.v1","timer15":timer,"expiry06":expiry})
        }
        Route::ClockAlarm | Route::DocumentsSaf | Route::DocumentsSearchSort | Route::IhgLondon => {
            json!({"plan":prior(results,name,"plan")?})
        }
        Route::GalleryRotation | Route::GalleryVideo | Route::GallerySeek | Route::GalleryAlbum => {
            let baseline = capture.comparison_receipt();
            json!({"schema":"droidloom.working-gallery-image-request.v1",
                "baseline":baseline["baseline"],"qualification":baseline["qualification"],
                "output":root.join("native-cases").join(name)})
        }
        _ => return Err("unlisted physical business request".into()),
    };
    let request_pin = files.save(
        &root
            .join("native-inputs")
            .join(name)
            .join("execute.request.json"),
        &request,
    )?;
    Ok(LeafPlan {
        route,
        request: request_pin,
        output: if route == Route::CameraPhoto {
            Some(root.join("native-cases").join(name))
        } else {
            None
        },
    })
}

/// Prepare the fixed complete plan only while the actual PID1-owned process,
/// its original source descriptors and its original deadline remain live.
pub fn prepare_owned_physical_plan(owner: &WorkingQualificationOwner) -> Result<()> {
    owner.guard()?;
    let mut files = PreparedFiles::new(owner)?;
    let inputs = admitted_inputs(owner, &mut files)?;
    let registry: GateRegistry = serde_json::from_slice(&files.read(&inputs.gates)?)
        .map_err(|e| format!("actual complete gate registry: {e}"))?;
    let (preparation_selection, _) = leaf_routes::compiled_release_sources();
    files.read(&preparation_selection)?;
    leaf_routes::validate_selection(&preparation_selection)?;
    for kind in [
        WorkingPreparationDirectory::NativeBaselines,
        WorkingPreparationDirectory::NativeInputs,
        WorkingPreparationDirectory::NativeCases,
    ] {
        let created = owner.create_preparation_directory(kind)?;
        files.directory(&created)?;
    }
    let root = files.root.clone();
    let mut input_cases = BTreeSet::new();
    for step in WORKING_NATIVE_PREPARATION_STEPS {
        input_cases.insert(step.description().case_name);
    }
    for fixed in roster::PACKAGES {
        for route in fixed.cases {
            input_cases.insert(case_name(*route)?);
        }
    }
    for name in input_cases {
        files.mkdir(&root.join("native-inputs").join(name))?;
    }

    let end = owner.preparation_deadline();
    let mut inspector =
        NativeApplicationInspector::acquire_until(Path::new(DEFAULT_CONTROL_SOCKET), end)
            .map_err(|e| e.to_string())?;
    let mut observations = Vec::with_capacity(roster::PACKAGE_COUNT);
    for fixed in roster::PACKAGES {
        owner.guard()?;
        observations.push(
            inspector
                .inspect_observed_until(fixed.package, 0, end)
                .map_err(|e| e.to_string())?,
        );
    }
    let epoch = observations
        .first()
        .ok_or("compiled physical package roster empty")?
        .facts()
        .epoch
        .clone();
    require(
        observations.iter().all(|row| row.facts().epoch == epoch),
        "initial complete application PM observations crossed Main epochs",
    )?;
    let main = inspector
        .observe_main_until(&epoch, end)
        .map_err(|e| e.to_string())?;
    let facts = observations
        .iter()
        .map(|row| row.facts())
        .collect::<Vec<_>>();
    let applications: Vec<ApplicationPlan> = runtime_prepare::bind_physical_observations(
        &inputs.selection,
        &inputs.signatures,
        &epoch,
        &facts,
    )?;
    let mut captures = BTreeMap::new();
    for (fixed, actual) in roster::PACKAGES.iter().zip(&observations) {
        if fixed.cases.is_empty() {
            continue;
        }
        owner.guard()?;
        let capture = capture_working_business_from_observed(owner, &mut inspector, &main, actual)?;
        require(
            captures.insert(fixed.package, capture).is_none(),
            "a native package baseline was prepared twice",
        )?;
    }
    require(
        captures.len() == 8,
        "compiled native baseline roster differs from its shared budget",
    )?;
    let qualification = pin_value(
        &captures
            .get("com.android.calendar")
            .ok_or("actual Calendar Main baseline absent")?
            .comparison_receipt()["qualification"],
    )?;
    let runtime = RuntimePlan {
        schema: 3,
        android_user: 0,
        main_qualification: qualification,
        expected_epoch: epoch,
        gate_registry: inputs.gates,
        applications,
        execute_public_browser: false,
        browser_fixture: None,
        preparation_selection: Some(preparation_selection),
        source_selection: Some(inputs.selection),
    };
    validate(&runtime, &registry, roster::PACKAGE_COUNT)?;
    let _materials = runtime_identity::admit_plan(&runtime)?
        .ok_or("the complete current material batch is not source admitted")?;
    files.guard()?;

    let mut results = Results::new();
    let mut executions = Vec::new();
    for step in WORKING_NATIVE_PREPARATION_STEPS {
        owner.guard()?;
        let d = step.description();
        let capture = captures
            .get_mut(package_for_step(step)?)
            .ok_or("fixed preparation lacks its actual native package baseline")?;
        capture.recheck()?;
        let value = source_request(step, capture, &results)?;
        let request = files.save(
            &root
                .join("native-inputs")
                .join(d.case_name)
                .join(format!("{}.request.json", d.purpose)),
            &value,
        )?;
        let mut execution = if d.ihg_factory {
            Execution::Ihg(native_ihg_preparation::run_working(
                IhgPreparationMode::parse(d.purpose)?,
                &request.sha256,
                &mut inspector,
                capture,
            )?)
        } else {
            Execution::Native(native_working_preparation_execution::run_working(
                step,
                &request.sha256,
                &mut inspector,
                capture,
            )?)
        };
        execution.recheck()?;
        let result = pin_value(execution.result())?;
        files.read(&result)?;
        require(
            results.insert((d.case_name, d.purpose), result).is_none(),
            "closed preparation produced a second result for one node",
        )?;
        executions.push(execution);
        files.guard()?;
    }
    require(
        results.len() == WORKING_NATIVE_PREPARATION_STEPS.len(),
        "physical plan omitted a source-owned preparation step",
    )?;
    let mut rows = Vec::new();
    for fixed in roster::PACKAGES {
        let mut cases = Vec::new();
        for route in fixed.cases {
            let capture = captures
                .get_mut(fixed.package)
                .ok_or("compiled native baseline absent")?;
            capture.recheck()?;
            let leaf = build_leaf(*route, capture, &results, &mut files)?;
            let qualification = pin_value(&capture.comparison_receipt()["qualification"])?;
            cases.push(json!({"leaf":leaf,"main_qualification":qualification}));
        }
        rows.push(json!({"package":fixed.package,"cases":cases}));
    }
    for capture in captures.values_mut() {
        capture.recheck()?;
    }
    for execution in &mut executions {
        execution.recheck()?;
    }
    files.guard()?;
    let runtime_pin = files.save(&root.join("RUNTIME-PLAN.json"), &runtime)?;
    let plan = json!({
        "schema":"droidloom.physical-application-plan.v1",
        "runtime_plan":runtime_pin,"applications":rows
    });
    physical_acceptance::validate_prepared_plan(&plan, &runtime, &registry)?;
    let raw = serde_json::to_vec(&plan).map_err(|e| e.to_string())?;
    require(
        raw.len() <= 4 * 1024 * 1024,
        "physical plan exceeds the parent's held input bound",
    )?;
    let plan_pin = files.save(&root.join("PLAN.json"), &plan)?;
    require(
        plan_pin.bytes <= 4 * 1024 * 1024,
        "serialized physical plan exceeds fixed bound",
    )?;
    files.guard()?;
    owner.guard()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn physical_preparation_has_exact_native_targets_and_all_fixed_request_directories() {
        let targets = WORKING_NATIVE_PREPARATION_STEPS
            .iter()
            .copied()
            .map(|step| package_for_step(step).unwrap())
            .collect::<BTreeSet<_>>();
        assert_eq!(targets.len(), 7); // Gallery needs only the eighth actual baseline.
        let native = roster::PACKAGES
            .iter()
            .filter(|row| !row.cases.is_empty())
            .collect::<Vec<_>>();
        assert_eq!(native.len(), 8);
        let mut routes = BTreeSet::new();
        for row in native {
            for route in row.cases {
                assert!(routes.insert(case_name(*route).unwrap()));
                assert_eq!(route.package(), row.package);
            }
        }
        assert_eq!(routes.len(), 14);
        assert!(
            targets
                .iter()
                .all(|package| roster::PACKAGES.iter().any(|row| row.package == *package))
        );
        assert!(case_name(Route::ClockTimer).is_err());
        assert!(case_name(Route::ClockTimerRemaining).is_err());
    }
}
