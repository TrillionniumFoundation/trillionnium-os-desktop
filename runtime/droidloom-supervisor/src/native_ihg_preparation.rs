//! Fixed IHG preparation entry. Current Main/data custody and the actual fixed
//! child, not a saved result or caller command, delimit this invocation.
use crate::control::{
    NativeApplicationInspector, NativeLeafCommandKind, run_prepared_native_leaf_until,
};
use crate::native_leaf_baseline::NativeLeafBaselineObservation;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Seek, SeekFrom},
    os::unix::fs::{MetadataExt, OpenOptionsExt},
    path::{Path, PathBuf},
    process::Command,
    time::{Duration, Instant},
};

pub const TARGET: &str = "com.ihg.apps.android";
pub const HELPER: &str = "org.droidloom.qa.ihg.finalmain.r1";
const ROOT: &str = "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2";
const QUAL: &str = "/var/lib/droidloom/qualification/pocket4";
const RECIPE: &str =
    include_str!("../../../android/manifest/native-application-leaf-cohort-r2.json");
const MAX: u64 = 16 * 1024 * 1024;
type Result<T> = std::result::Result<T, String>;
fn hash(b: &[u8]) -> String {
    format!("{:x}", Sha256::digest(b))
}
fn digest(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn exact(v: &Value, keys: &[&str]) -> bool {
    v.as_object()
        .is_some_and(|o| o.len() == keys.len() && keys.iter().all(|k| o.contains_key(*k)))
}
fn require(ok: bool, why: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(why.into()) }
}
fn before(end: Instant) -> Result<()> {
    require(
        Instant::now() < end,
        "original IHG preparation deadline expired",
    )
}
fn node(m: &fs::Metadata) -> [i128; 9] {
    [
        m.dev() as i128,
        m.ino() as i128,
        m.mode() as i128,
        m.uid() as i128,
        m.gid() as i128,
        m.nlink() as i128,
        m.len() as i128,
        m.mtime() as i128 * 1_000_000_000 + m.mtime_nsec() as i128,
        m.ctime() as i128 * 1_000_000_000 + m.ctime_nsec() as i128,
    ]
}
fn text<'a>(v: &'a Value, k: &str) -> Result<&'a str> {
    v[k].as_str().ok_or_else(|| format!("missing IHG text {k}"))
}
fn pin_path(v: &Value) -> Result<&Path> {
    require(
        exact(v, &["path", "bytes", "sha256"])
            && v["bytes"].as_u64().is_some_and(|n| n <= MAX)
            && v["sha256"].as_str().is_some_and(digest),
        "IHG file pin shape differs",
    )?;
    let p = Path::new(text(v, "path")?);
    require(
        p.is_absolute()
            && p.components().all(|c| {
                matches!(
                    c,
                    std::path::Component::RootDir | std::path::Component::Normal(_)
                )
            })
            && p.as_os_str().len() <= 1024,
        "IHG path is not absolute and normalized",
    )?;
    Ok(p)
}
/// These names are the only exposed modes; they never accept an argv vector.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum IhgPreparationMode {
    TargetIdentity,
    HelperSource,
    HelperBuild,
    HelperInstall,
    HelperIdentity,
    Plan,
}
impl IhgPreparationMode {
    pub fn parse(s: &str) -> Result<Self> {
        match s {
            "target-identity" => Ok(Self::TargetIdentity),
            "helper-source" => Ok(Self::HelperSource),
            "helper-build" => Ok(Self::HelperBuild),
            "helper-install" => Ok(Self::HelperInstall),
            "helper-identity" => Ok(Self::HelperIdentity),
            "plan" => Ok(Self::Plan),
            _ => Err("unlisted fixed IHG preparation mode".into()),
        }
    }
    pub fn name(self) -> &'static str {
        match self {
            Self::TargetIdentity => "target-identity",
            Self::HelperSource => "helper-source",
            Self::HelperBuild => "helper-build",
            Self::HelperInstall => "helper-install",
            Self::HelperIdentity => "helper-identity",
            Self::Plan => "plan",
        }
    }
    fn entry_mode(self) -> &'static str {
        match self {
            Self::TargetIdentity | Self::HelperIdentity => "identity",
            Self::Plan => "plan",
            _ => self.name(),
        }
    }
    pub fn output_parent(self) -> &'static str {
        if self == Self::HelperBuild {
            "/home/alex/work"
        } else {
            QUAL
        }
    }
    pub fn output_prefix(self) -> &'static str {
        match self {
            Self::TargetIdentity | Self::HelperIdentity => "business-app-identity-",
            Self::HelperSource => "business-ihg-helper-source-",
            Self::HelperBuild => "pocket4-final-ihg-helper-build-",
            Self::HelperInstall => "business-ihg-install-",
            Self::Plan => "business-ihg-plan-",
        }
    }
    fn output_name(self) -> &'static str {
        match self {
            Self::HelperSource => "source.json",
            Self::HelperBuild => "build-result.json",
            Self::Plan => "plan.json",
            _ => "result.json",
        }
    }
    pub(crate) fn budget(self) -> Duration {
        Duration::from_secs(match self {
            Self::HelperBuild => 300,
            Self::HelperInstall => 240,
            Self::HelperIdentity => 360,
            Self::TargetIdentity => 300,
            _ => 180,
        })
    }
    fn keys(self) -> &'static [&'static str] {
        match self {
            Self::TargetIdentity | Self::HelperSource => &["baseline", "qualification"],
            Self::HelperBuild => &["source"],
            Self::HelperInstall => &["build", "target_identity"],
            Self::HelperIdentity => &[
                "baseline",
                "qualification",
                "build",
                "install",
                "target_identity",
            ],
            Self::Plan => &[
                "baseline",
                "qualification",
                "target_identity",
                "helper_identity",
                "helper_build",
                "helper_install",
            ],
        }
    }
}
fn output_shape(mode: IhgPreparationMode, path: &Path) -> Result<()> {
    let name = path
        .file_name()
        .and_then(|s| s.to_str())
        .ok_or("IHG output basename absent")?;
    let suffix = name
        .strip_prefix(mode.output_prefix())
        .ok_or("IHG output prefix differs")?;
    require(
        path.parent() == Some(Path::new(mode.output_parent()))
            && suffix.len() == 32
            && suffix
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "IHG output must be a fresh fixed mode directory",
    )?;
    Ok(())
}
fn output_path(mode: IhgPreparationMode, path: &Path) -> Result<()> {
    output_shape(mode, path)?;
    require(
        fs::symlink_metadata(path).is_err_and(|e| e.kind() == std::io::ErrorKind::NotFound),
        "IHG output already exists or cannot be established absent",
    )
}
fn request_shape(mode: IhgPreparationMode, v: &Value) -> Result<()> {
    require(
        exact(v, mode.keys()),
        "IHG request fields differ from its one fixed mode",
    )?;
    for key in mode.keys() {
        let p = pin_path(&v[key])?;
        require(
            p.starts_with(QUAL)
                || (p.starts_with("/home/alex/work")
                    && p.components()
                        .nth(4)
                        .and_then(|c| c.as_os_str().to_str())
                        .is_some_and(|s| s.starts_with("pocket4-final-ihg-helper-build-"))),
            "IHG reference is not a normal public preparation artifact",
        )?;
    }
    Ok(())
}
struct Held {
    path: PathBuf,
    file: File,
    identity: [i128; 9],
    raw: Vec<u8>,
}
impl Held {
    fn open(path: &Path, end: Instant, source: bool) -> Result<Self> {
        use std::{ffi::CString, os::fd::FromRawFd};
        before(end)?;
        require(
            path.is_absolute()
                && path.components().all(|c| {
                    matches!(
                        c,
                        std::path::Component::RootDir | std::path::Component::Normal(_)
                    )
                }),
            "noncanonical IHG file path",
        )?;
        #[repr(C)]
        struct How {
            flags: u64,
            mode: u64,
            resolve: u64,
        }
        let how = How {
            flags: (libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK) as u64,
            mode: 0,
            resolve: 0x04 | 0x02,
        };
        let name = CString::new(path.as_os_str().as_encoded_bytes()).map_err(|e| e.to_string())?;
        let fd = unsafe {
            libc::syscall(
                libc::SYS_openat2,
                libc::AT_FDCWD,
                name.as_ptr(),
                &how,
                std::mem::size_of::<How>(),
            )
        };
        if fd < 0 {
            return Err(std::io::Error::last_os_error().to_string());
        }
        let mut file = unsafe { File::from_raw_fd(fd as i32) };
        let m = file.metadata().map_err(|e| e.to_string())?;
        require(
            m.is_file() && m.nlink() == 1 && m.len() <= MAX && m.mode() & 0o7022 == 0,
            "IHG file is not a bounded ordinary single-link file",
        )?;
        if source {
            require(
                m.uid() == 0 && m.gid() == 0 && m.mode() & 0o7777 == 0o444,
                "compiled IHG source must be installed root:root 0444",
            )?
        } else {
            require(
                (m.uid() == 0 && m.gid() == 0)
                    || (m.uid() == 1000 && m.gid() == 1000 && path.starts_with("/home/alex/work")),
                "IHG public artifact owner differs",
            )?
        }
        let identity = node(&m);
        let mut raw = Vec::new();
        Read::by_ref(&mut file)
            .take(MAX + 1)
            .read_to_end(&mut raw)
            .map_err(|e| e.to_string())?;
        require(
            raw.len() as u64 == m.len()
                && node(&file.metadata().map_err(|e| e.to_string())?) == identity
                && node(&fs::symlink_metadata(path).map_err(|e| e.to_string())?) == identity,
            "IHG file changed while held",
        )?;
        before(end)?;
        Ok(Self {
            path: path.into(),
            file,
            identity,
            raw,
        })
    }
    fn pin(&self) -> Value {
        json!({"path":self.path,"bytes":self.raw.len(),"sha256":hash(&self.raw)})
    }
    fn json(&self) -> Result<Value> {
        serde_json::from_slice(&self.raw).map_err(|e| e.to_string())
    }
    fn recheck(&mut self, end: Instant) -> Result<()> {
        before(end)?;
        require(
            node(&self.file.metadata().map_err(|e| e.to_string())?) == self.identity
                && node(&fs::symlink_metadata(&self.path).map_err(|e| e.to_string())?)
                    == self.identity,
            "IHG held/named identity changed",
        )?;
        self.file
            .seek(SeekFrom::Start(0))
            .map_err(|e| e.to_string())?;
        let mut b = Vec::new();
        Read::by_ref(&mut self.file)
            .take(MAX + 1)
            .read_to_end(&mut b)
            .map_err(|e| e.to_string())?;
        require(
            b == self.raw
                && node(&self.file.metadata().map_err(|e| e.to_string())?) == self.identity,
            "IHG held full bytes changed",
        )?;
        before(end)
    }
}
fn public_artifact(path: &Path) -> Result<()> {
    let under = if let Ok(rest) = path.strip_prefix(QUAL) {
        rest.components()
            .next()
            .and_then(|c| c.as_os_str().to_str())
            .is_some_and(|name| {
                [
                    "native-leaf-",
                    "business-app-identity-",
                    "business-ihg-helper-source-",
                    "business-ihg-install-",
                    "business-ihg-plan-",
                ]
                .iter()
                .any(|p| name.starts_with(p))
            })
    } else if let Ok(rest) = path.strip_prefix("/home/alex/work") {
        rest.components()
            .next()
            .and_then(|c| c.as_os_str().to_str())
            .is_some_and(|name| name.starts_with("pocket4-final-ihg-helper-build-"))
    } else {
        false
    };
    require(
        under,
        "IHG readback is outside its fixed public preparation roots",
    )
}

fn held_pin(pin: &Value, end: Instant, held: &mut Vec<Held>) -> Result<Value> {
    let p = pin_path(pin)?;
    public_artifact(p)?;
    let f = Held::open(p, end, false)?;
    require(f.pin() == *pin, "IHG actual referenced file pin differs")?;
    let v = f.json()?;
    held.push(f);
    Ok(v)
}
fn held_bytes(pin: &Value, end: Instant, held: &mut Vec<Held>) -> Result<Vec<u8>> {
    let p = pin_path(pin)?;
    public_artifact(p)?;
    let f = Held::open(p, end, false)?;
    require(f.pin() == *pin, "IHG command body pin differs")?;
    let b = f.raw.clone();
    held.push(f);
    Ok(b)
}
fn save_capture(
    root: &Path,
    name: &str,
    raw: &[u8],
    end: Instant,
    held: &mut Vec<Held>,
) -> Result<Value> {
    use std::io::Write;
    require(
        [
            "ihg-entry.stdout",
            "ihg-entry.stderr",
            "IHG-ENTRY-EXECUTION.json",
            "IHG-ENTRY-FAILED.json",
        ]
        .contains(&name),
        "unlisted IHG capture member",
    )?;
    require(
        raw.len() as u64 <= MAX,
        "IHG entry output exceeds its capture bound",
    )?;
    before(end)?;
    let path = root.join(name);
    let mut file = OpenOptions::new()
        .read(true)
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
        .open(&path)
        .map_err(|e| e.to_string())?;
    file.write_all(raw).map_err(|e| e.to_string())?;
    file.sync_all().map_err(|e| e.to_string())?;
    drop(file);
    let f = Held::open(&path, end, false)?;
    require(f.raw == raw, "IHG capture full readback differs")?;
    let p = f.pin();
    held.push(f);
    Ok(p)
}
fn compiled_sources(end: Instant) -> Result<(Vec<Held>, Value)> {
    let r: Value = serde_json::from_str(RECIPE).map_err(|e| e.to_string())?;
    require(
        r["canonical_root"] == ROOT && r["output_file_count"] == 478,
        "compiled IHG recipe identity differs",
    )?;
    let rows = r["members"]
        .as_array()
        .ok_or("compiled IHG members absent")?;
    let mut files = Vec::new();
    let mut prep = Value::Null;
    for relative in ["source/ihg/app_entry.py", "preparations/ihg.json"] {
        let found = rows
            .iter()
            .filter(|row| row["relative_path"] == relative)
            .collect::<Vec<_>>();
        require(
            found.len() == 1,
            "compiled IHG member is missing or duplicated",
        )?;
        let pin = &found[0]["output"];
        require(
            pin_path(pin)? == Path::new(ROOT).join(relative),
            "compiled IHG source path differs",
        )?;
        let f = Held::open(pin_path(pin)?, end, true)?;
        require(
            f.pin() == *pin,
            "normal IHG source differs from its compiled recipe",
        )?;
        if relative.starts_with("preparations/") {
            prep = pin.clone()
        }
        files.push(f);
    }
    Ok((files, prep))
}
fn command(
    mode: IhgPreparationMode,
    request: &Path,
    request_sha: &str,
    output: &Path,
    prep: &Value,
) -> Result<Command> {
    require(digest(request_sha), "IHG request digest shape differs")?;
    let mut c = Command::new("/usr/bin/python3");
    c.args(["-I", "-B"])
        .arg(format!("{ROOT}/source/ihg/app_entry.py"))
        .arg("--preparation")
        .arg(format!("{ROOT}/preparations/ihg.json"))
        .arg("--expect-preparation-sha256")
        .arg(text(prep, "sha256")?)
        .arg(mode.entry_mode())
        .arg("--request")
        .arg(request)
        .arg("--expect-request-sha256")
        .arg(request_sha)
        .arg("--output")
        .arg(output);
    match mode {
        IhgPreparationMode::TargetIdentity => {
            c.args(["--role", "ihg"]);
        }
        IhgPreparationMode::HelperIdentity => {
            c.args(["--role", "ihg-helper"]);
        }
        IhgPreparationMode::Plan => {
            c.args(["--kind", "ihg_london"]);
        }
        _ => {}
    }
    c.env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LANG", "C.UTF-8");
    Ok(c)
}
pub(crate) fn check_command(c: &Command, mode: IhgPreparationMode) -> Result<()> {
    let argv = c
        .get_args()
        .map(|x| x.to_str())
        .collect::<Option<Vec<_>>>()
        .ok_or("IHG arguments are not UTF-8")?;
    let expected_len = if matches!(
        mode,
        IhgPreparationMode::TargetIdentity
            | IhgPreparationMode::HelperIdentity
            | IhgPreparationMode::Plan
    ) {
        16
    } else {
        14
    };
    require(
        c.get_program() == "/usr/bin/python3" && argv.len() == expected_len,
        "only the fixed IHG preparation entry may use this nonbusiness profile",
    )?;
    let recipe: Value = serde_json::from_str(RECIPE).map_err(|e| e.to_string())?;
    let pins = recipe["members"]
        .as_array()
        .ok_or("compiled members absent")?
        .iter()
        .filter(|r| r["relative_path"] == "preparations/ihg.json")
        .collect::<Vec<_>>();
    require(pins.len() == 1, "compiled preparation is not unique")?;
    require(
        Path::new(argv[9]).is_absolute(),
        "IHG request must be absolute",
    )?;
    output_shape(mode, Path::new(argv[13]))?;
    let expected = command(
        mode,
        Path::new(argv[9]),
        argv[11],
        Path::new(argv[13]),
        &pins[0]["output"],
    )?;
    require(
        c.get_program() == expected.get_program() && c.get_args().eq(expected.get_args()),
        "IHG preparation argv differs from its compiled mode",
    )
}

fn base64(raw: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::new();
    for x in raw.chunks(3) {
        let v = ((x[0] as u32) << 16)
            | ((x.get(1).copied().unwrap_or(0) as u32) << 8)
            | (x.get(2).copied().unwrap_or(0) as u32);
        out.push(T[((v >> 18) & 63) as usize] as char);
        out.push(T[((v >> 12) & 63) as usize] as char);
        out.push(if x.len() > 1 {
            T[((v >> 6) & 63) as usize] as char
        } else {
            '='
        });
        out.push(if x.len() > 2 {
            T[(v & 63) as usize] as char
        } else {
            '='
        });
    }
    out
}
fn install_sequence(value: &Value) -> Result<Vec<(Value, u64, bool)>> {
    let nonce = text(value, "nonce")?;
    let state = text(value, "state_nonce")?;
    require(
        [nonce, state].iter().all(|s| {
            s.len() == 32
                && s.bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        }) && nonce != state,
        "distinct actual installation nonces required",
    )?;
    let listed = json!([
        "/system/bin/cmd",
        "package",
        "list",
        "packages",
        "-U",
        "--show-versioncode",
        "--user",
        "0",
        TARGET
    ]);
    let paths = json!(["/system/bin/cmd", "package", "path", "--user", "0", TARGET]);
    let uid = json!([
        "/system/bin/cmd",
        "package",
        "list",
        "packages",
        "-U",
        "--user",
        "0",
        HELPER
    ]);
    let ownpath = json!(["/system/bin/cmd", "package", "path", "--user", "0", HELPER]);
    let req = format!(
        "{{\"nonce\":\"{state}\",\"op\":\"state\",\"protocol\":\"pocket4-owned-ihg-qa-final-main-v1\"}}"
    );
    Ok(vec![
        (listed.clone(), 15, false),
        (paths.clone(), 15, false),
        (
            json!([
                "/system/bin/cmd",
                "package",
                "list",
                "packages",
                "-u",
                "-U",
                "--user",
                "all",
                HELPER
            ]),
            8,
            false,
        ),
        (
            json!([
                "/system/bin/cmd",
                "package",
                "install",
                "-R",
                "-t",
                "--user",
                "0",
                "--pkg",
                HELPER,
                format!("/data/local/tmp/pocket4-final-ihg-qa-{nonce}/owned-ihg-qa.apk")
            ]),
            40,
            true,
        ),
        (uid.clone(), 8, false),
        (uid.clone(), 8, false),
        (ownpath.clone(), 8, false),
        (
            json!([
                "/system/bin/am",
                "instrument",
                "-w",
                "-r",
                "-e",
                "request",
                base64(req.as_bytes()),
                format!("{HELPER}/{HELPER}.ActionRunner")
            ]),
            20,
            false,
        ),
        (uid, 8, false),
        (ownpath, 8, false),
        (
            json!([
                "/system/bin/cmd",
                "package",
                "list",
                "packages",
                "-U",
                "--user",
                "all",
                HELPER
            ]),
            8,
            false,
        ),
        (listed, 15, false),
        (paths, 15, false),
    ])
}
fn completed_install(
    value: &Value,
    request: &Value,
    root: &Path,
    before_inventory: &Value,
    end: Instant,
    held: &mut Vec<Held>,
) -> Result<(u32, u64, String)> {
    require(
        value["schema"] == "pocket4-final-ihg-helper-install-v1"
            && value["state"] == "INSTALLED_STATE_OBSERVED"
            && value["package"] == HELPER
            && value["build"] == request["build"]
            && value["target_identity"] == request["target_identity"]
            && value["error"].is_null()
            && value["install_attempted"] == true
            && value["install_success_observed"] == true
            && value["artifact_FDs_closed"] == true
            && value["held_Main_closed"] == true
            && value["Main_before"] == value["Main_after"]
            && value["automatic_retry"] == false
            && value["whole_app_business_accepted"] == false
            && value["UiAutomation_connection_requested"] == false
            && [
                "UI_actions",
                "App_launches",
                "commercial_package_writes",
                "task_removals",
                "uninstalls",
            ]
            .iter()
            .all(|k| value[k] == 0)
            && [
                "staged_apk_removed",
                "staged_directory_removed",
                "authority_fds_closed",
            ]
            .iter()
            .all(|k| value["staging_cleanup"][k] == true),
        "actual fixed installation did not complete its original limited scope",
    )?;
    // The recorded preimage was captured earlier. Both real query receipts
    // must be valid, but their process identities and elapsed times differ.
    // Compare the complete same-epoch table, never a selected-package subset.
    let original: crate::package_inventory_observation::UserZeroPackageInventoryFacts =
        serde_json::from_value(value["user_zero_inventory_before"].clone())
            .map_err(|e| e.to_string())?;
    let current: crate::package_inventory_observation::UserZeroPackageInventoryFacts =
        serde_json::from_value(before_inventory.clone()).map_err(|e| e.to_string())?;
    current.validate(&current.epoch)?;
    original.validate(&current.epoch)?;
    require(
        original.same_table(&current),
        "complete captured/current preinstall table differs",
    )?;
    let build = held_pin(&request["build"], end, held)?;
    require(
        build["state"] == "BUILT_STATIC_VERIFIED_ANDROID_UNRUN"
            && build["package"] == HELPER
            && build["error"].is_null()
            && value["source"] == build["source"],
        "actual installed helper differs from its normal build",
    )?;
    let source = held_pin(&build["source"], end, held)?;
    require(
        value["baseline"] == source["baseline"]
            && value["qualification"] == source["qualification"],
        "installation belongs to another baseline",
    )?;
    let expected = install_sequence(value)?;
    let commands = value["commands"]
        .as_array()
        .ok_or("installation command list absent")?;
    require(
        commands.len() == 13,
        "actual original thirteen commands are required",
    )?;
    let mut outputs = Vec::new();
    for (index, (entry, (argv, seconds, mutation))) in commands.iter().zip(expected).enumerate() {
        let name = format!("command-{:03}", index + 1);
        require(
            entry["argv"] == argv
                && entry["timeout"] == seconds
                && entry["mutation"] == mutation
                && pin_path(&entry["result"])?
                    == root.join("commands").join(format!("{name}.result.json"))
                && pin_path(&entry["transport"])?
                    == root.join("commands").join(format!("{name}.transport.json")),
            "actual installation command order or member path differs",
        )?;
        let result = held_pin(&entry["result"], end, held)?;
        let transport = held_pin(&entry["transport"], end, held)?;
        let physical = result["argv"].as_array().ok_or("command argv absent")?;
        let logical = argv.as_array().unwrap();
        require(
            physical.ends_with(logical)
                && result["host_retirement_proved"] == true
                && result["evidence_complete"] == true
                && result["returncode"] == 0
                && result["timed_out"] == false
                && result["errors"] == json!([])
                && result.get("first_error").is_none_or(Value::is_null)
                && transport["lease_entered"] == true
                && transport["lease_released"] == true
                && transport["host_retirement_proved"] == true
                && transport["error_type"].is_null()
                && transport["post_guard"]["business_baseline_sha256"]
                    == source["baseline"]["sha256"]
                && transport["post_guard"]["business_qualification_sha256"]
                    == source["qualification"]["sha256"],
            "installation command did not actually retire under the same Main",
        )?;
        for (k, suffix) in [("stdout", "stdout"), ("stderr", "stderr")] {
            require(
                pin_path(&result[k])? == root.join("commands").join(format!("{name}.{suffix}")),
                "installation stream member path differs",
            )?;
        }
        let stdout = held_bytes(&result["stdout"], end, held)?;
        let stderr = held_bytes(&result["stderr"], end, held)?;
        require(
            stderr.is_empty(),
            "installation command stderr was not empty",
        )?;
        outputs.push(stdout);
    }
    let uid = value["helper_uid"]
        .as_u64()
        .filter(|n| (10000..100000).contains(n))
        .ok_or("actual helper UID absent")? as u32;
    let expected_uid = format!("package:{HELPER} uid:{uid}\n").into_bytes();
    require(
        outputs[0] == outputs[11]
            && outputs[1] == outputs[12]
            && outputs[2].is_empty()
            && outputs[3] == b"Success\n"
            && [4, 5, 8, 10]
                .into_iter()
                .all(|i| outputs[i] == expected_uid)
            && outputs[6] == outputs[9]
            && value["target_before"] == value["target_after"]
            && value["installed_before_state"] == value["installed_after_state"],
        "actual installation UID or target preservation differs",
    )?;
    let installed = &value["installed_before_state"];
    let bytes = build["APK"]["bytes"]
        .as_u64()
        .filter(|n| (1..=2097152).contains(n))
        .ok_or("helper APK byte count differs")?;
    let digest = text(&build["APK"], "sha256")?;
    require(
        self::digest(digest)
            && installed["package"] == HELPER
            && installed["uid"] == uid
            && installed["apk_sha256"] == digest
            && installed["bytes"] == bytes
            && outputs[6] == format!("package:{}\n", text(installed, "base_apk")?).as_bytes()
            && installed["signer_bound_by_exact_signed_apk_bytes"]
                == build["signer_certificate_sha256"],
        "actual helper APK differs from the signed build",
    )?;
    let artifact = held_bytes(&build["APK"], end, held)?;
    require(
        artifact.len() as u64 == bytes && hash(&artifact) == digest,
        "normal helper APK changed",
    )?;
    require(
        pin_path(&value["state_observation"])? == root.join("state-observation.json"),
        "state-only observation member differs",
    )?;
    let state = held_pin(&value["state_observation"], end, held)?;
    require(
        state["helper"]["ui_automation_connected"] == false && state["helper"]["op"] == "state",
        "helper observation requested UI automation",
    )?;
    Ok((uid, bytes, digest.into()))
}
fn one_helper_delta(
    a: &std::collections::BTreeMap<&str, u32>,
    b: &std::collections::BTreeMap<&str, u32>,
    uid: u32,
) -> Result<()> {
    require(
        !a.contains_key(HELPER)
            && !a.values().any(|v| *v == uid)
            && (10000..100000).contains(&uid)
            && b.len() == a.len() + 1
            && b.get(HELPER) == Some(&uid)
            && a.iter().all(|(k, v)| b.get(k) == Some(v)),
        "complete user-0 inventory changed beyond the one actual new helper",
    )
}
fn same_or_one_helper(
    before: &crate::package_inventory_observation::UserZeroPackageInventoryFacts,
    after: &crate::package_inventory_observation::UserZeroPackageInventoryFacts,
    uid: u32,
) -> Result<()> {
    one_helper_delta(&before.records(), &after.records(), uid)
}
/// No public fields, Deserialize or Clone. Only this fixed live factory can
/// retain its original child/output/source witnesses through actual postchecks.
pub struct IhgPreparationExecution {
    result: Value,
    report: Value,
    held: Vec<Held>,
    until: Instant,
}
impl IhgPreparationExecution {
    pub fn result_pin(&self) -> &Value {
        &self.result
    }
    pub fn comparison_report(&self) -> &Value {
        &self.report
    }
    pub fn recheck(&mut self) -> Result<()> {
        for f in &mut self.held {
            f.recheck(self.until)?
        }
        Ok(())
    }
}
/// Runs only one fixed mode; callers cannot provide an executable, argv, tool
/// list or a claimed success. Its normal CLI holds the entire installed cohort
/// in addition to the fixed entry/preparation descriptors retained here.
pub fn run(
    mode: IhgPreparationMode,
    request_path: &Path,
    request_sha: &str,
    output: &Path,
    evidence: &Path,
    inspector: &mut NativeApplicationInspector,
    baseline: &mut NativeLeafBaselineObservation<'_>,
    until: Instant,
) -> Result<IhgPreparationExecution> {
    let end = until.min(baseline.deadline());
    before(end)?;
    require(
        unsafe { libc::getuid() } == 0
            && unsafe { libc::geteuid() } == 0
            && unsafe { libc::getgid() } == 0
            && unsafe { libc::getegid() } == 0,
        "IHG preparation requires the normal root operator",
    )?;
    require(
        baseline.application().package == TARGET
            && baseline.application().user == 0
            && baseline.inventory_facts().is_some(),
        "IHG actual target and complete user-0 preimage required",
    )?;
    baseline
        .verify_local(inspector, end)
        .map_err(|e| e.to_string())?;
    output_path(mode, output)?;
    let em = fs::symlink_metadata(evidence).map_err(|e| e.to_string())?;
    require(
        evidence.parent() == Some(Path::new(QUAL))
            && evidence
                .file_name()
                .and_then(|s| s.to_str())
                .is_some_and(|n| n.starts_with("native-leaf-"))
            && em.is_dir()
            && em.uid() == 0
            && em.gid() == 0
            && em.mode() & 0o7777 == 0o700
            && fs::canonicalize(evidence).map_err(|e| e.to_string())? == evidence,
        "IHG evidence requires the fresh normal private capture directory",
    )?;
    let pre =
        serde_json::to_value(baseline.inventory_facts().unwrap()).map_err(|e| e.to_string())?;
    if matches!(
        mode,
        IhgPreparationMode::HelperSource
            | IhgPreparationMode::HelperBuild
            | IhgPreparationMode::HelperInstall
    ) {
        require(
            !baseline
                .inventory_facts()
                .unwrap()
                .records()
                .contains_key(HELPER),
            "helper is already installed; no automatic preparation retry",
        )?;
    }
    let (mut held, prep) = compiled_sources(end)?;
    let request = Held::open(request_path, end, false)?;
    require(
        digest(request_sha)
            && hash(&request.raw) == request_sha
            && request.identity[3] == 0
            && request.identity[4] == 0,
        "actual root-owned IHG request pin differs",
    )?;
    let request_value = request.json()?;
    request_shape(mode, &request_value)?;
    let request_pin = request.pin();
    held.push(request);
    let command = command(mode, request_path, request_sha, output, &prep)?;
    // Additional helper PM inspection is reserved only for the installing mode.
    // NativeLeafRun also reserves target PM, Main, full inventory and retirement.
    let child_end = if mode == IhgPreparationMode::HelperInstall {
        end.checked_sub(Duration::from_secs(250))
            .ok_or("IHG post-inspection reserve underflow")?
    } else {
        end
    };
    let epoch = baseline.application().epoch.clone();
    let result = match run_prepared_native_leaf_until(
        command,
        &epoch,
        NativeLeafCommandKind::IhgPreparation { mode },
        inspector,
        baseline,
        child_end,
    ) {
        Ok(output) => output,
        Err(error) => {
            let bytes=serde_json::to_vec_pretty(&json!({"schema":"droidloom.native-ihg-entry-failure.v1","mode":mode.name(),"request":request_pin,"actual_error":error,"actual_exit":Value::Null,"automatic_retry":false,"whole_app_business_accepted":false})).map_err(|e|e.to_string())?;
            // Failure evidence does not assert retirement or invent an exit code.
            let _ = save_capture(evidence, "IHG-ENTRY-FAILED.json", &bytes, end, &mut held);
            return Err(error);
        }
    };
    let stdout = save_capture(evidence, "ihg-entry.stdout", &result.stdout, end, &mut held)?;
    let stderr = save_capture(evidence, "ihg-entry.stderr", &result.stderr, end, &mut held)?;
    let bytes=serde_json::to_vec_pretty(&json!({"schema":"droidloom.native-ihg-entry-execution.v1","mode":mode.name(),"request":request_pin,"preparation":prep,"actual_exit":result.status.code(),"stdout":stdout,"stderr":stderr,"owned_cgroup_empty_and_direct_child_reaped":true,"automatic_retry":false,"whole_app_business_accepted":false})).map_err(|e|e.to_string())?;
    save_capture(evidence, "IHG-ENTRY-EXECUTION.json", &bytes, end, &mut held)?;
    require(
        result.status.success() && result.stderr.is_empty(),
        "fixed IHG entry failed; preserve its outputs and do not retry automatically",
    )?;
    let printed: Value = serde_json::from_slice(&result.stdout)
        .map_err(|e| format!("actual IHG entry stdout: {e}"))?;
    require(
        exact(&printed, &["result", "ok", "whole_app_business_accepted"])
            && printed["ok"] == true
            && printed["whole_app_business_accepted"] == false
            && pin_path(&printed["result"])? == output.join(mode.output_name()),
        "actual fixed IHG entry did not name its fresh mode output",
    )?;
    let value = held_pin(&printed["result"], end, &mut held)?;
    let install = if mode == IhgPreparationMode::HelperInstall {
        Some(completed_install(
            &value,
            &request_value,
            output,
            &pre,
            end,
            &mut held,
        )?)
    } else {
        None
    };
    for f in &mut held {
        f.recheck(end)?
    }
    let post_application = inspector
        .inspect_observed_until(TARGET, 0, end)
        .map_err(|e| e.to_string())?;
    let post_main = inspector
        .refresh_main_until(baseline.main(), end)
        .map_err(|e| e.to_string())?;
    let post_inventory = inspector
        .observe_user_zero_package_inventory_until(&post_main, &post_application, end)
        .map_err(|e| e.to_string())?;
    let after = serde_json::to_value(post_inventory.facts()).map_err(|e| e.to_string())?;
    if let Some((uid, bytes, sha256)) = install {
        let helper = inspector
            .inspect_observed_until(HELPER, 0, end)
            .map_err(|e| e.to_string())?;
        inspector
            .require_observations_local(&post_main, &helper, end)
            .map_err(|e| e.to_string())?;
        let app = helper.facts();
        require(
            app.package == HELPER
                && app.user == 0
                && app.uid == uid
                && app.epoch == epoch
                && app.apks.len() == 1
                && app.apks[0].name == "base.apk"
                && app.apks[0].path.starts_with("/data/app/")
                && app.apks[0].path.ends_with("/base.apk")
                && app.apks[0].bytes == bytes
                && app.apks[0].sha256 == sha256,
            "actual post-install PM body differs from this fixed installation",
        )?;
        same_or_one_helper(
            baseline.inventory_facts().unwrap(),
            post_inventory.facts(),
            uid,
        )?;
        baseline
            .record_fixed_ihg_install_bookend(inspector, post_inventory, end)
            .map_err(|e| e.to_string())?;
    } else {
        baseline
            .record_inventory_bookend(inspector, post_inventory, end)
            .map_err(|e| e.to_string())?
    }
    baseline
        .finish_from_observed(inspector, &post_main, &post_application, end)
        .map_err(|e| e.to_string())?;
    for f in &mut held {
        f.recheck(end)?
    }
    baseline
        .verify_local(inspector, end)
        .map_err(|e| e.to_string())?;
    before(end)?;
    let report = json!({"schema":"droidloom.native-ihg-preparation-execution.v1","mode":mode.name(),
  "request":request_pin,"preparation":prep,"result":printed["result"],"actual_exit":result.status.code(),
  "stdout_bytes":result.stdout.len(),"stdout_sha256":hash(&result.stdout),"stderr_bytes":result.stderr.len(),"stderr_sha256":hash(&result.stderr),
  "owned_cgroup_empty_and_direct_child_reaped":true,"user_zero_before":pre,"user_zero_after":after,
  "full_user_zero_table_compared":true,"single_helper_installation":mode==IhgPreparationMode::HelperInstall,
  "actual_main_and_target_bookends_equal":true,"comparison_only":true,
  "business_acceptance_evaluated":false,"whole_app_business_accepted":false,"production_ready":false,"automatic_retry":false});
    Ok(IhgPreparationExecution {
        result: printed["result"].clone(),
        report,
        held,
        until: end,
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ihg_modes_cannot_select_an_entry_or_extra_request_fields() {
        for s in [
            "target-identity",
            "helper-source",
            "helper-build",
            "helper-install",
            "helper-identity",
            "plan",
        ] {
            assert_eq!(IhgPreparationMode::parse(s).unwrap().name(), s)
        }
        for s in [
            "execute",
            "clock-worker",
            "/bin/sh",
            "identity",
            "--role=clock",
        ] {
            assert!(IhgPreparationMode::parse(s).is_err())
        }
        let pin = json!({"path":format!("{QUAL}/native-leaf-fixture/BASELINE.json"),"bytes":1,"sha256":"a".repeat(64)});
        let mut v = json!({"baseline":pin,"qualification":pin});
        request_shape(IhgPreparationMode::TargetIdentity, &v).unwrap();
        v["argv"] = json!(["/bin/sh"]);
        assert!(request_shape(IhgPreparationMode::TargetIdentity, &v).is_err());
        v.as_object_mut().unwrap().remove("argv");
        v["baseline"]["path"] = json!("/etc/shadow");
        assert!(request_shape(IhgPreparationMode::TargetIdentity, &v).is_err());
    }
    #[test]
    fn ihg_install_sequence_preserves_all_thirteen_original_commands() {
        let v = json!({"nonce":"a".repeat(32),"state_nonce":"b".repeat(32)});
        let rows = install_sequence(&v).unwrap();
        assert_eq!(rows.len(), 13);
        assert_eq!(rows.iter().filter(|r| r.2).count(), 1);
        assert_eq!(rows[0], rows[11]);
        assert_eq!(rows[1], rows[12]);
        assert_eq!(rows[3].0[2], "install");
        assert_eq!(rows[7].0[1], "instrument");
        assert_eq!(base64(b""), "");
        assert_eq!(base64(b"f"), "Zg==");
        assert_eq!(base64(b"fo"), "Zm8=");
        assert_eq!(base64(b"foo"), "Zm9v");
        let mut bad = v;
        bad["state_nonce"] = bad["nonce"].clone();
        assert!(install_sequence(&bad).is_err());
    }

    #[test]
    fn ihg_global_preimage_allows_only_one_noncolliding_helper() {
        use std::collections::BTreeMap;
        let before = BTreeMap::from([
            ("android", 1000),
            ("com.ihg.apps.android", 10137),
            ("other.shared.one", 10100),
            ("other.shared.two", 10100),
        ]);
        let mut after = before.clone();
        after.insert(HELPER, 10200);
        one_helper_delta(&before, &after, 10200).unwrap();
        for uid in [0, 1000, 10100, 10137, 100000] {
            assert!(one_helper_delta(&before, &after, uid).is_err())
        }
        let mut bad = after.clone();
        bad.insert("unrelated.new", 10201);
        assert!(one_helper_delta(&before, &bad, 10200).is_err());
        let mut bad = after.clone();
        bad.remove("other.shared.one");
        assert!(one_helper_delta(&before, &bad, 10200).is_err());
        let mut bad = after.clone();
        bad.insert("other.shared.two", 10101);
        assert!(one_helper_delta(&before, &bad, 10200).is_err());
        assert!(one_helper_delta(&after, &after, 10200).is_err());
    }
    #[test]
    fn ihg_fixed_entry_rejects_alternate_programs_modes_and_extra_arguments() {
        let recipe: Value = serde_json::from_str(RECIPE).unwrap();
        let prep = recipe["members"]
            .as_array()
            .unwrap()
            .iter()
            .find(|r| r["relative_path"] == "preparations/ihg.json")
            .unwrap()["output"]
            .clone();
        for mode in [
            IhgPreparationMode::TargetIdentity,
            IhgPreparationMode::HelperSource,
            IhgPreparationMode::HelperBuild,
            IhgPreparationMode::HelperInstall,
            IhgPreparationMode::HelperIdentity,
            IhgPreparationMode::Plan,
        ] {
            let out = Path::new(mode.output_parent()).join(format!(
                "{}{}",
                mode.output_prefix(),
                "a".repeat(32)
            ));
            let mut c = command(
                mode,
                Path::new(
                    "/var/lib/droidloom/qualification/pocket4/native-leaf-fixture/request.json",
                ),
                &"b".repeat(64),
                &out,
                &prep,
            )
            .unwrap();
            check_command(&c, mode).unwrap();
            c.arg("--caller-passed");
            assert!(check_command(&c, mode).is_err());
            assert!(check_command(&Command::new("/bin/sh"), mode).is_err());
        }
        for path in [
            "/etc/shadow",
            "/home/alex/.ssh/id_ed25519",
            "/var/lib/unrelated/private.json",
        ] {
            assert!(public_artifact(Path::new(path)).is_err());
        }
    }
}
