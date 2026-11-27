//! Finite selected public APK updates on the actual held working Main.
//! This has no uninstall, data copying, caller path or package-manager flags.
use super::CellState;
use super::{
    ControlError, ControlRequest, ControlResponse, MainCustodyObservation,
    NativeApplicationInspector, apk_payload,
    application_probe::RuntimeEpoch,
    physical_qualification_channel::{WorkingQualificationOwner, budget},
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    fs::{self, File, OpenOptions},
    os::{
        fd::AsRawFd,
        unix::fs::{MetadataExt, OpenOptionsExt},
    },
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

#[path = "working_public_source_credentials.rs"]
mod credentials;
fn source_access<T>(action: impl FnOnce() -> Result<T, ControlError>) -> Result<T, ControlError> {
    credentials::with_public_source(|| action().map_err(|e| e.to_string())).map_err(reject)
}
const STAGE: &str = "/var/lib/droidloom-public-apks/u1000";
const MEITUAN: &str = "com.sankuai.meituan.takeoutnew";

/// A comparison from the admitted SDK material table. Constructing pins grants
/// no effect: install_working_public_apks also borrows the actual live owner.
#[derive(Clone, Debug)]
pub struct WorkingApkPin {
    pub bytes: u64,
    pub sha256: String,
    pub manifest_split: Option<String>,
}

/// These ten packages must come from the complete admitted GSI. They are never
/// independently replaced by the public third-party installer.
pub fn working_system_package(package: &str) -> bool {
    matches!(
        package,
        "com.android.calendar"
            | "com.android.camera2"
            | "com.android.contacts"
            | "com.android.deskclock"
            | "com.android.dialer"
            | "com.android.documentsui"
            | "com.android.gallery3d"
            | "com.android.messaging"
            | "com.android.quicksearchbox"
            | "com.android.settings"
    )
}
fn reject(message: impl Into<String>) -> ControlError {
    ControlError::Invalid(message.into())
}
fn allowed(package: &str) -> bool {
    crate::engine_custody::selected_package(package)
        && !working_system_package(package)
        && package != MEITUAN
}
fn pins(pins: &[WorkingApkPin]) -> Result<Vec<(u64, [u8; 32])>, ControlError> {
    if !(1..=32).contains(&pins.len()) || pins[0].manifest_split.is_some() {
        return Err(reject(
            "working install requires one base followed by every distinct split",
        ));
    }
    let mut total = 0u64;
    let mut identities = BTreeSet::new();
    let mut splits = BTreeSet::new();
    let mut result = Vec::new();
    for (index, pin) in pins.iter().enumerate() {
        let valid_split = pin.manifest_split.as_ref().is_none_or(|v| {
            !v.is_empty()
                && v.len() <= 255
                && v.bytes()
                    .all(|c| c.is_ascii_alphanumeric() || b"._".contains(&c))
        });
        if pin.bytes < 4
            || pin.bytes > 1024 * 1024 * 1024
            || pin.sha256.len() != 64
            || !pin
                .sha256
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
            || !identities.insert((pin.bytes, pin.sha256.clone()))
            || !splits.insert(pin.manifest_split.clone())
            || !valid_split
            || (index > 0
                && (pin.manifest_split.is_none()
                    || pins[index - 1].manifest_split >= pin.manifest_split))
        {
            return Err(reject(
                "working install source bytes or deterministic complete split order differ",
            ));
        }
        total = total
            .checked_add(pin.bytes)
            .filter(|v| *v <= 2 * 1024 * 1024 * 1024)
            .ok_or_else(|| reject("working original APK set exceeds 2 GiB"))?;
        let mut hash = [0u8; 32];
        for (index, byte) in hash.iter_mut().enumerate() {
            *byte = u8::from_str_radix(&pin.sha256[index * 2..index * 2 + 2], 16)
                .map_err(|e| reject(e.to_string()))?;
        }
        result.push((pin.bytes, hash));
    }
    Ok(result)
}
#[derive(Clone, Copy, PartialEq, Eq)]
struct Node {
    values: [u64; 7],
    times: [i64; 4],
}
fn node(m: &fs::Metadata) -> Node {
    Node {
        values: [
            m.dev(),
            m.ino(),
            u64::from(m.mode()),
            u64::from(m.uid()),
            u64::from(m.gid()),
            m.nlink(),
            m.len(),
        ],
        times: [m.mtime(), m.mtime_nsec(), m.ctime(), m.ctime_nsec()],
    }
}
struct Parent {
    path: PathBuf,
    file: File,
    identity: Node,
    exact: bool,
}
struct Input {
    path: PathBuf,
    file: File,
    identity: Node,
}
struct HeldStage {
    parents: Vec<Parent>,
    inputs: Vec<Input>,
}
impl HeldStage {
    fn capture(pins: &[WorkingApkPin]) -> Result<Self, ControlError> {
        let mut parents: Vec<Parent> = Vec::new();
        for path in [
            "/",
            "/var",
            "/var/lib",
            "/var/lib/droidloom-public-apks",
            STAGE,
        ] {
            let public = PathBuf::from(path);
            let anchored = match parents.last() {
                None => public.clone(),
                Some(parent) => PathBuf::from(format!("/proc/self/fd/{}", parent.file.as_raw_fd()))
                    .join(
                        public
                            .file_name()
                            .ok_or_else(|| reject("public APK parent name absent"))?,
                    ),
            };
            let file = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(anchored)
                .map_err(|e| reject(format!("open held public APK parent: {e}")))?;
            let identity = node(&file.metadata().map_err(|e| reject(e.to_string()))?);
            let final_stage = path == STAGE;
            let owner = if final_stage { 1000 } else { 0 };
            if identity.values[2] & libc::S_IFMT as u64 != libc::S_IFDIR as u64
                || identity.values[3..5] != [owner, owner]
                || (final_stage && identity.values[2] & 0o7777 != 0o700)
                || (!final_stage && identity.values[2] & 0o022 != 0)
            {
                return Err(reject(
                    "public APK parent is outside the normal protected staging tree",
                ));
            }
            parents.push(Parent {
                path: public,
                file,
                identity,
                exact: final_stage,
            });
        }
        let directory = parents
            .last()
            .ok_or_else(|| reject("held public APK stage absent"))?;
        let mut inputs = Vec::new();
        for pin in pins {
            let name = format!("{}.apk", pin.sha256);
            let path = Path::new(STAGE).join(&name);
            let file = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC)
                .open(format!(
                    "/proc/self/fd/{}/{}",
                    directory.file.as_raw_fd(),
                    name
                ))
                .map_err(|e| reject(format!("open exact staged original APK: {e}")))?;
            let identity = node(&file.metadata().map_err(|e| reject(e.to_string()))?);
            if identity.values[2] != u64::from(libc::S_IFREG | 0o400)
                || identity.values[3..7] != [1000, 1000, 1, pin.bytes]
            {
                return Err(reject(
                    "staged original APK type, owner, mode, links or length differs",
                ));
            }
            inputs.push(Input {
                path,
                file,
                identity,
            });
        }
        let result = Self { parents, inputs };
        result.guard()?;
        Ok(result)
    }
    fn guard(&self) -> Result<(), ControlError> {
        for parent in &self.parents {
            let held = node(&parent.file.metadata().map_err(|e| reject(e.to_string()))?);
            let named =
                node(&fs::symlink_metadata(&parent.path).map_err(|e| reject(e.to_string()))?);
            if [held, named].iter().any(|n| {
                if parent.exact {
                    *n != parent.identity
                } else {
                    n.values[..5] != parent.identity.values[..5]
                }
            }) {
                return Err(reject("held original APK staging directory changed"));
            }
        }
        for input in &self.inputs {
            if node(&input.file.metadata().map_err(|e| reject(e.to_string()))?) != input.identity
                || node(&fs::symlink_metadata(&input.path).map_err(|e| reject(e.to_string()))?)
                    != input.identity
            {
                return Err(reject("held original APK or its source pathname changed"));
            }
        }
        Ok(())
    }
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Segment {
    index: usize,
    bytes: u64,
    sha256: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Session {
    session: u32,
    user: u32,
    epoch: RuntimeEpoch,
    bytes: u64,
    segments: Vec<Segment>,
    commands: Vec<Value>,
}
fn confirmed(
    response: ControlResponse,
    epoch: &RuntimeEpoch,
    expected: &[WorkingApkPin],
) -> Result<Value, ControlError> {
    if !response.ok
        || response.state != CellState::Running
        || response.host_pid != Some(epoch.cell_host_pid)
        || response.launch.is_some()
        || response.applications.is_some()
        || response.application_icon.is_some()
        || response.inspection.is_some()
        || response.image_custody.is_some()
        || response.runtime_vintf.is_some()
    {
        return Err(reject(format!(
            "atomic install not confirmed; inspect the original epoch before any retry: {}",
            response.message
        )));
    }
    let raw = response
        .diagnostics
        .ok_or_else(|| reject("atomic session observation absent"))?;
    if raw.len() > 1024 * 1024 {
        return Err(reject("atomic session observation exceeds bound"));
    }
    let result: Session = serde_json::from_str(&raw)?;
    if result.session == 0
        || result.session > i32::MAX as u32
        || result.user != 0
        || result.epoch != *epoch
        || result.bytes != expected.iter().map(|p| p.bytes).sum::<u64>()
        || result.segments.len() != expected.len()
        || result.commands.len() != expected.len() + 2
        || result
            .segments
            .iter()
            .zip(expected)
            .enumerate()
            .any(|(i, (seen, wanted))| {
                seen.index != i || seen.bytes != wanted.bytes || seen.sha256 != wanted.sha256
            })
    {
        return Err(reject(
            "confirmed atomic session differs from this complete admitted APK set/epoch",
        ));
    }
    Ok(json!({"schema":"droidloom.working-application-install.v1",
        "epoch":epoch,"session":result.session,"original_apk_bytes":result.bytes,
        "original_apk_files":expected.len(),"atomic_session_confirmed":true,
        "installed_identity_verified":false,"original_data_migration_accepted":false,
        "application_accepted":false,"production_ready":false}))
}

/// Execute the original normal atomic PM adapter on the same actual working
/// owner. All public inputs are comparisons; a source document cannot recreate
/// owner/Main/peer custody. The caller must still inspect complete installed
/// bytes and preserve any previous UID before recording installed identity.
pub fn install_working_public_apks(
    owner: &WorkingQualificationOwner,
    inspector: &mut NativeApplicationInspector,
    main: &MainCustodyObservation,
    package: &str,
    inputs: &[WorkingApkPin],
) -> Result<Value, ControlError> {
    if !allowed(package) {
        return Err(reject(
            "package requires the full GSI or a separate retained-data migration; no public update is authorized",
        ));
    }
    let expected = pins(inputs)?;
    let end = owner.preparation_deadline();
    owner.compare_preparation_main(main).map_err(reject)?;
    inspector.require_main_local(main, end)?;
    let needed = Duration::from_secs(
        budget::APPLICATION_INSTALL_PAYLOAD_SECONDS
            + budget::APPLICATION_INSTALL_TRANSPORT_SECONDS
            + budget::APPLICATION_INSTALL_INSPECT_SECONDS,
    );
    if end.saturating_duration_since(Instant::now()) < needed {
        return Err(reject(
            "original working preparation window cannot fit this complete install",
        ));
    }
    let stage = source_access(|| HeldStage::capture(inputs))?;
    let files = stage
        .inputs
        .iter()
        .map(|input| &input.file)
        .collect::<Vec<_>>();
    let (payload, lengths) = apk_payload::prepare_pinned_until(&files, &expected, end)?;
    source_access(|| stage.guard())?;
    owner.compare_preparation_main(main).map_err(reject)?;
    inspector.require_main_local(main, end)?;
    if end.saturating_duration_since(Instant::now())
        < Duration::from_secs(
            budget::APPLICATION_INSTALL_TRANSPORT_SECONDS
                + budget::APPLICATION_INSTALL_INSPECT_SECONDS,
        )
    {
        return Err(reject(
            "original window cannot fit the atomic session and complete installed readback",
        ));
    }
    let result = inspector.request_fixed_file_until(
        &ControlRequest::InstallCurrentMultiple {
            user: 0,
            lengths,
            expected_epoch: main.facts().epoch.clone(),
        },
        Some(&payload),
        Some(end),
    );
    // Complete the actual custody bookend even when the wire outcome is unknown.
    let after = (|| {
        source_access(|| stage.guard())?;
        owner.compare_preparation_main(main).map_err(reject)?;
        inspector.require_main_local(main, end)
    })();
    let response = result?;
    after?;
    let mut observation = confirmed(response, &main.facts().epoch, inputs)?;
    observation["package"] = json!(package);
    Ok(observation)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn public_working_update_excludes_system_unknown_and_signer_migration() {
        for p in [
            "com.android.settings",
            "com.android.calendar",
            MEITUAN,
            "org.example.any",
        ] {
            assert!(!allowed(p), "{p}");
        }
        assert!(allowed("org.mozilla.firefox"));
        assert!(allowed("com.ihg.apps.android"));
    }
    #[test]
    fn public_working_inputs_require_complete_base_split_order_and_unique_originals() {
        let base = WorkingApkPin {
            bytes: 8,
            sha256: "a".repeat(64),
            manifest_split: None,
        };
        let split = WorkingApkPin {
            bytes: 9,
            sha256: "b".repeat(64),
            manifest_split: Some("config.en".into()),
        };
        assert!(pins(&[base.clone(), split.clone()]).is_ok());
        assert!(pins(&[split.clone(), base.clone()]).is_err());
        assert!(pins(&[base.clone(), base.clone()]).is_err());
        let mut bad = split.clone();
        bad.sha256 = "A".repeat(64);
        assert!(pins(&[base.clone(), bad]).is_err());
        let mut bad = split;
        bad.manifest_split = Some("../foreign".into());
        assert!(pins(&[base, bad]).is_err());
    }
}

#[cfg(test)]
mod readback_tests {
    use super::*;
    fn response(epoch: &RuntimeEpoch, pins: &[WorkingApkPin]) -> ControlResponse {
        let raw = json!({"session":42,"user":0,"epoch":epoch,
            "bytes":pins.iter().map(|p|p.bytes).sum::<u64>(),
            "segments":pins.iter().enumerate().map(|(i,p)|json!({
                "index":i,"bytes":p.bytes,"sha256":p.sha256})).collect::<Vec<_>>(),
            "commands":vec![json!({});pins.len()+2]});
        ControlResponse {
            ok: true,
            state: CellState::Running,
            message: "confirmed".into(),
            host_pid: Some(epoch.cell_host_pid),
            launch: None,
            applications: None,
            application_icon: None,
            diagnostics: Some(raw.to_string()),
            inspection: None,
            image_custody: None,
            runtime_vintf: None,
        }
    }
    #[test]
    fn actual_atomic_response_must_bind_complete_segments_and_epoch() {
        let epoch = RuntimeEpoch {
            boot_id: "00000000-0000-0000-0000-000000000001".into(),
            cell_host_pid: 100,
            framework_host_pid: 101,
            framework_start_ticks: 70,
        };
        let pins = vec![
            WorkingApkPin {
                bytes: 8,
                sha256: "a".repeat(64),
                manifest_split: None,
            },
            WorkingApkPin {
                bytes: 9,
                sha256: "b".repeat(64),
                manifest_split: Some("config.en".into()),
            },
        ];
        assert_eq!(
            confirmed(response(&epoch, &pins), &epoch, &pins).unwrap()["atomic_session_confirmed"],
            true
        );
        for variation in 0..5 {
            let mut reply = response(&epoch, &pins);
            let mut raw: Value = serde_json::from_str(reply.diagnostics.as_ref().unwrap()).unwrap();
            match variation {
                0 => raw["epoch"]["framework_start_ticks"] = json!(71),
                1 => raw["segments"][1]["sha256"] = json!("c".repeat(64)),
                2 => {
                    raw["segments"].as_array_mut().unwrap().pop();
                }
                3 => raw["bytes"] = json!(18),
                _ => reply.ok = false,
            }
            reply.diagnostics = Some(raw.to_string());
            assert!(confirmed(reply, &epoch, &pins).is_err());
        }
    }
    #[test]
    fn retained_stage_guard_rejects_real_file_writes_and_name_replacement() {
        use std::io::Write;
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("held.apk");
        fs::write(&path, b"PK\x03\x04original").unwrap();
        let file = File::open(&path).unwrap();
        let identity = node(&file.metadata().unwrap());
        let stage = HeldStage {
            parents: Vec::new(),
            inputs: vec![Input {
                path: path.clone(),
                file,
                identity,
            }],
        };
        stage.guard().unwrap();
        OpenOptions::new()
            .write(true)
            .open(&path)
            .unwrap()
            .write_all(b"PK\x03\x04mutation")
            .unwrap();
        assert!(stage.guard().is_err());
        fs::remove_file(&path).unwrap();
        fs::write(&path, b"PK\x03\x04original").unwrap();
        assert!(stage.guard().is_err());
    }
}
