//! Normal live native-leaf comparison capture. No leaf, service or installation
//! is started. The supervisor factory owns actual peer and directory lifetimes.
use crate::util::*;
#[path = "working_native_cases.rs"]
mod working_native_cases;
pub use working_native_cases::{prepare_working_native_cases, WorkingPreparedCases};
use droidloom_supervisor::control::{
    ActualApplicationObservation, ActualImageApplicationObservation, DEFAULT_CONTROL_SOCKET, MainCustodyObservation,
    NativeApplicationInspector,
};
use droidloom_supervisor::native_leaf_baseline::NativeLeafBaselineObservation;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::Path;
use std::time::{Duration, Instant};

fn sha(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
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
fn read_held(file: &mut File) -> Result<Vec<u8>> {
    let before = node(&file.metadata()?);
    if !file.metadata()?.is_file() || before[5] != 1 || !(1..=262144).contains(&before[6]) {
        return fail("native leaf comparison must be a bounded regular single-link file");
    }
    file.seek(SeekFrom::Start(0))?;
    let mut raw = Vec::new();
    Read::by_ref(file).take(262145).read_to_end(&mut raw)?;
    if raw.len() as i128 != before[6] || node(&file.metadata()?) != before {
        return fail("native leaf comparison changed while held");
    }
    Ok(raw)
}

fn actual(
    package: &str,
    end: Instant,
) -> Result<(
    NativeApplicationInspector,
    MainCustodyObservation,
    ActualApplicationObservation,
    Option<ActualImageApplicationObservation>,
)> {
    let mut inspector =
        NativeApplicationInspector::acquire_until(Path::new(DEFAULT_CONTROL_SOCKET), end)?;
    let (application, image) = if package == "com.android.gallery3d" {
        let (application, image) = inspector.inspect_gallery_observed_until(end)?;
        (application, Some(image))
    } else {
        (inspector.inspect_observed_until(package, 0, end)?, None)
    };
    let main = inspector.observe_main_until(&application.facts().epoch, end)?;
    if let Some(image) = &image {
        inspector.require_image_application_local(&main, &application, image, end)?;
    }
    Ok((inspector, main, application, image))
}
fn bookend(
    inspector: &mut NativeApplicationInspector,
    held: &mut NativeLeafBaselineObservation<'_>,
    before_application: &ActualApplicationObservation,
    before_image: Option<&ActualImageApplicationObservation>,
    end: Instant,
) -> Result<()> {
    let (application, image) = if held.application().package == "com.android.gallery3d" {
        let before = before_image.ok_or("Gallery baseline lost its actual whole-image observation")?;
        inspector.require_image_application_local(held.main(), before_application, before, end)?;
        let (application, after) = inspector.inspect_gallery_observed_until(end)?;
        if before.facts().cohort != after.facts().cohort
            || before.facts().original_apk != after.facts().original_apk
            || before.facts().application != after.facts().application
        {
            return fail("Gallery baseline original image or complete installed identity changed");
        }
        (application, Some(after))
    } else {
        if before_image.is_some() {
            return fail("non-Gallery baseline cannot borrow whole-image observation");
        }
        (inspector.inspect_observed_until(&held.application().package, 0, end)?, None)
    };
    let main = inspector.refresh_main_until(held.main(), end)?;
    if let Some(image) = &image {
        inspector.require_image_application_local(&main, &application, image, end)?;
    }
    if held.requires_inventory_bookend() {
        let inventory =
            inspector.observe_user_zero_package_inventory_until(&main, &application, end)?;
        held.record_inventory_bookend(inspector, inventory, end)?;
    }
    held.finish_from_observed(inspector, &main, &application, end)?;
    Ok(())
}

pub fn capture(package: &str, output: &Path) -> Result<Value> {
    if !output.is_absolute() || output.file_name().is_none() || output.exists() {
        return fail("native leaf capture requires a fresh absolute output file");
    }
    let parent = output.parent().ok_or("native leaf output parent absent")?;
    if fs::canonicalize(parent)? != parent {
        return fail("native leaf output parent must not traverse symlinks");
    }
    let before = fs::symlink_metadata(parent)?;
    let uid = unsafe { libc::geteuid() };
    if !before.is_dir() || ![0, uid].contains(&before.uid()) || before.mode() & 0o022 != 0 {
        return fail("native leaf output parent is not held by this producer or root");
    }
    let parent_fd = File::open(parent)?;
    if (parent_fd.metadata()?.dev(), parent_fd.metadata()?.ino()) != (before.dev(), before.ino()) {
        return fail("native leaf output parent changed during open");
    }
    let end = Instant::now() + Duration::from_secs(900);
    let (mut inspector, main, application, image) = actual(package, end)?;
    let mut observed =
        NativeLeafBaselineObservation::capture_from_observed(&inspector, &main, &application, end)?;
    let mut raw = serde_json::to_vec_pretty(&observed.facts())?;
    raw.push(b'\n');
    if raw.len() > 262144 {
        return fail("native leaf comparison exceeds its bound");
    }
    let mut staged = tempfile::NamedTempFile::new_in(parent)?;
    staged.write_all(&raw)?;
    staged.as_file().sync_all()?;
    if read_held(staged.as_file_mut())? != raw {
        return fail("native leaf staged output changed");
    }
    bookend(&mut inspector, &mut observed, &application, image.as_ref(), end)?;
    let now = fs::symlink_metadata(parent)?;
    if (now.dev(), now.ino(), now.uid(), now.gid(), now.mode())
        != (
            before.dev(),
            before.ino(),
            before.uid(),
            before.gid(),
            before.mode(),
        )
    {
        return fail("native leaf output parent changed before publication");
    }
    let result = staged.persist_noclobber(output).map_err(|e| e.error)?;
    if node(&result.metadata()?) != node(&fs::symlink_metadata(output)?) {
        return fail("native leaf published comparison identity differs");
    }
    parent_fd.sync_all()?;
    Ok(json!({"schema":"droidloom.native-leaf-baseline-capture.v1",
        "file":{"path":output,"bytes":raw.len(),"sha256":sha(&raw)},
        "comparison_only":true,"leaf_executed":false,"account_contents_read":false,
        "business_acceptance_evaluated":false,"normal_runtime_qualified":false}))
}
pub fn compare(package: &str, input: &Path, expected_sha: &str) -> Result<Value> {
    if !input.is_absolute()
        || expected_sha.len() != 64
        || !expected_sha
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    {
        return fail("native leaf comparison requires an absolute exact file digest");
    }
    let mut held = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(input)?;
    let first = node(&held.metadata()?);
    let raw = read_held(&mut held)?;
    if sha(&raw) != expected_sha || node(&fs::symlink_metadata(input)?) != first {
        return fail("native leaf saved comparison pin differs");
    }
    let value: Value = serde_json::from_slice(&raw)?;
    // The saved document does not select an owner or process: a real capture is
    // acquired first, from the same fixed production API as every live caller.
    let end = Instant::now() + Duration::from_secs(900);
    let (mut inspector, main, application, image) = actual(package, end)?;
    let mut observed =
        NativeLeafBaselineObservation::capture_from_observed(&inspector, &main, &application, end)?;
    observed.compare(&value)?;
    bookend(&mut inspector, &mut observed, &application, image.as_ref(), end)?;
    if read_held(&mut held)? != raw
        || node(&held.metadata()?) != first
        || node(&fs::symlink_metadata(input)?) != first
    {
        return fail("native leaf saved comparison changed across actual observation");
    }
    Ok(
        json!({"schema":"droidloom.native-leaf-baseline-comparison.v1",
        "reference":{"path":input,"bytes":raw.len(),"sha256":expected_sha},
        "actual_owner_reobserved":true,"held_directory_identity_rechecked":true,
        "comparison_only":true,"business_acceptance_evaluated":false,
        "normal_runtime_qualified":false}),
    )
}

// Full current baseline capture uses the actual Rust owner, the compiled installed
// cohort, and one bounded fixed read-only collector. No saved report can replace
// the live Main/PM factories, and no application business action is requested.
const QUALIFICATION_ROOT: &str = "/var/lib/droidloom/qualification/pocket4";
const BASELINE_SCHEMA: &str = "droidloom.native-leaf-business-baseline.v1";
const QUALIFICATION_SCHEMA: &str = "droidloom.native-leaf-business-qualification.v1";
fn canonical_value(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let ordered: std::collections::BTreeMap<_, _> =
                map.iter().map(|(k, v)| (k, canonical_value(v))).collect();
            serde_json::to_value(ordered).expect("JSON values are serializable")
        }
        Value::Array(values) => Value::Array(values.iter().map(canonical_value).collect()),
        _ => value.clone(),
    }
}

fn exact_keys(value: &Value, wanted: &[&str]) -> bool {
    value
        .as_object()
        .is_some_and(|v| v.len() == wanted.len() && wanted.iter().all(|k| v.contains_key(*k)))
}
fn check_before(end: Instant) -> Result<()> {
    if Instant::now() >= end {
        fail("normal leaf capture original deadline expired")
    } else {
        Ok(())
    }
}
fn directory_identity(m: &fs::Metadata) -> [u64; 5] {
    [
        m.dev(),
        m.ino(),
        u64::from(m.mode()),
        u64::from(m.uid()),
        u64::from(m.gid()),
    ]
}
fn private_capture_root() -> Result<(std::path::PathBuf, File, [u64; 5])> {
    use std::ffi::CString;
    use std::os::fd::{AsRawFd, FromRawFd};
    if unsafe { libc::getuid() } != 0
        || unsafe { libc::geteuid() } != 0
        || unsafe { libc::getgid() } != 0
        || unsafe { libc::getegid() } != 0
    {
        return fail("normal business baseline producer requires the original root operator");
    }
    let mut parent = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open("/")?;
    for part in ["var", "lib", "droidloom", "qualification", "pocket4"] {
        let name = CString::new(part)?;
        let mut fd = unsafe {
            libc::openat(
                parent.as_raw_fd(),
                name.as_ptr(),
                libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            )
        };
        if fd < 0
            && std::io::Error::last_os_error().raw_os_error() == Some(libc::ENOENT)
            && ["qualification", "pocket4"].contains(&part)
        {
            if unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o700) } != 0 {
                return Err(std::io::Error::last_os_error().into());
            }
            fd = unsafe {
                libc::openat(
                    parent.as_raw_fd(),
                    name.as_ptr(),
                    libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                )
            };
        }
        if fd < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        let file = unsafe { File::from_raw_fd(fd) };
        let m = file.metadata()?;
        if !m.is_dir()
            || m.uid() != 0
            || m.gid() != 0
            || m.mode() & 0o7022 != 0
            || (part == "pocket4" && m.mode() & 0o7777 != 0o700)
        {
            return fail("normal capture parent is not the fixed root-owned protected directory");
        }
        parent = file;
    }
    let selected = directory_identity(&parent.metadata()?);
    if directory_identity(&fs::symlink_metadata(QUALIFICATION_ROOT)?) != selected {
        return fail("normal capture qualification root changed");
    }
    let path = tempfile::Builder::new()
        .prefix("native-leaf-")
        .tempdir_in(QUALIFICATION_ROOT)?
        .keep();
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW)
        .open(&path)?;
    let m = file.metadata()?;
    if m.uid() != 0
        || m.gid() != 0
        || m.mode() & 0o7777 != 0o700
        || directory_identity(&fs::symlink_metadata(QUALIFICATION_ROOT)?) != selected
    {
        return fail("fresh normal capture directory changed");
    }
    Ok((path, file, directory_identity(&m)))
}
struct CapturedFile {
    relative: String,
    file: File,
    identity: [i128; 9],
    raw: Vec<u8>,
}
impl CapturedFile {
    fn open(root: &Path, relative: &str, maximum: u64) -> Result<Self> {
        if !["OBSERVED.json", "main-readonly-entry/result.json"].contains(&relative)
            && !["guest-uid", "guest-gid", "boot-completed"]
                .iter()
                .any(|name| {
                    ["intent.json", "stdout", "stderr", "result.json"]
                        .iter()
                        .any(|suffix| relative == format!("main-readonly-entry/{name}.{suffix}"))
                })
        {
            return fail("unlisted normal capture evidence member");
        }
        let path = root.join(relative);
        let parent = path.parent().ok_or("capture parent absent")?;
        let p = fs::symlink_metadata(parent)?;
        if !p.is_dir()
            || p.uid() != 0
            || p.gid() != 0
            || p.mode() & 0o7777 != 0o700
            || fs::canonicalize(parent)? != parent
        {
            return fail("normal capture evidence parent changed");
        }
        let mut file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
            .open(&path)?;
        let m = file.metadata()?;
        let identity = node(&m);
        if !m.is_file()
            || m.uid() != 0
            || m.gid() != 0
            || m.nlink() != 1
            || m.mode() & 0o7777 != 0o600
            || m.len() > maximum
        {
            return fail("normal capture evidence file shape differs");
        }
        let mut raw = Vec::new();
        Read::by_ref(&mut file)
            .take(maximum + 1)
            .read_to_end(&mut raw)?;
        if raw.len() as u64 != m.len()
            || node(&file.metadata()?) != identity
            || node(&fs::symlink_metadata(&path)?) != identity
        {
            return fail("normal capture evidence changed while held");
        }
        Ok(Self {
            relative: relative.into(),
            file,
            identity,
            raw,
        })
    }
    fn pin(&self, root: &Path) -> Value {
        json!({"path":root.join(&self.relative),"bytes":self.raw.len(),"sha256":sha(&self.raw)})
    }
    fn recheck(&mut self, root: &Path) -> Result<()> {
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(root.join(&self.relative))?;
        if node(&named.metadata()?) != self.identity
            || node(&self.file.metadata()?) != self.identity
        {
            return fail("normal capture evidence held/named identity changed");
        }
        self.file.seek(SeekFrom::Start(0))?;
        let mut raw = Vec::new();
        Read::by_ref(&mut self.file)
            .take(self.raw.len() as u64 + 1)
            .read_to_end(&mut raw)?;
        if raw != self.raw || node(&self.file.metadata()?) != self.identity {
            return fail("normal capture evidence full readback changed");
        }
        Ok(())
    }
}
fn write_private(root: &Path, name: &str, raw: &[u8]) -> Result<Value> {
    if name.is_empty() || name.contains('/') || name.contains("..") || raw.len() > 16 * 1024 * 1024
    {
        return fail("normal capture output name or size differs");
    }
    let path = root.join(name);
    let mut file = OpenOptions::new()
        .write(true)
        .read(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
        .open(&path)?;
    file.write_all(raw)?;
    file.sync_all()?;
    let first = node(&file.metadata()?);
    file.seek(SeekFrom::Start(0))?;
    let mut after = Vec::new();
    file.read_to_end(&mut after)?;
    if after != raw
        || node(&file.metadata()?) != first
        || node(&fs::symlink_metadata(&path)?) != first
    {
        return fail("normal capture output failed complete held readback");
    }
    Ok(json!({"path":path,"bytes":raw.len(),"sha256":sha(raw)}))
}
fn write_value(root: &Path, name: &str, value: &Value) -> Result<Value> {
    let mut raw = serde_json::to_vec_pretty(value)?;
    raw.push(b'\n');
    write_private(root, name, &raw)
}

const UNIT_FIELDS: [&str; 8] = [
    "ActiveState",
    "SubState",
    "MainPID",
    "ControlPID",
    "ControlGroup",
    "InvocationID",
    "FragmentPath",
    "DropInPaths",
];
const SYSTEMCTL_SHA: &str = "639bce3ce5c06b605079ea56f74e3f08216ddffcfa76e11f62073aa775180082";
fn unit_query_argv(role: &str) -> Vec<String> {
    let mut v = vec![
        "/usr/bin/systemctl".into(),
        "--no-pager".into(),
        "--no-ask-password".into(),
    ];
    if role == "presenter" {
        v.push("--user".into());
    }
    v.extend([
        "show".into(),
        if role == "daemon" {
            "droidloom-production.service".into()
        } else {
            "droidloom-production-desktop.service".into()
        },
        format!("--property={}", UNIT_FIELDS.join(",")),
    ]);
    v
}
fn validate_unit_observations(runtime: &Value) -> Result<()> {
    // These are full comparison receipts from this owned collector, never an
    // input constructor for Main, unit ownership or application authority.
    let rows = runtime["systemd_unit_observations"]
        .as_array()
        .ok_or("actual normal unit receipts absent")?;
    if !(2..=128).contains(&rows.len())
        || rows.len() % 2 != 0
        || !exact_keys(&runtime["systemd_units"], &["daemon", "presenter"])
    {
        return fail("two complete fixed unit roles are required");
    }
    let mut previous = 0;
    let mut first_program: Option<&Value> = None;
    for (index, row) in rows.iter().enumerate() {
        let role = if index % 2 == 0 {
            "daemon"
        } else {
            "presenter"
        };
        let uid = if role == "daemon" { 0 } else { 1000 };
        let argv = unit_query_argv(role);
        if !exact_keys(
            row,
            &[
                "schema",
                "role",
                "unit",
                "argv",
                "program",
                "program_file",
                "child_uid",
                "child_gid",
                "child_pre_exec_caps",
                "fork_clone_forbidden",
                "child_started",
                "child_reaped",
                "automatic_retry",
                "started_monotonic_ns",
                "deadline_monotonic_ns",
                "pid",
                "pidfd",
                "waitid_code",
                "waitid_status",
                "wait_status",
                "returncode",
                "retirement_within_deadline",
                "finished_monotonic_ns",
                "stdout",
                "stderr",
                "exec_error",
            ],
        ) || row["schema"] != "droidloom.native-host-unit-read.v1"
            || row["role"] != role
            || row["argv"] != json!(argv)
            || row["unit"] != argv[argv.len() - 2]
            || row["program"]
                != json!({"path":"/usr/bin/systemctl","bytes":302112,"sha256":SYSTEMCTL_SHA})
            || row["child_uid"] != uid
            || row["child_gid"] != uid
            || row["child_pre_exec_caps"] != 0
            || row["fork_clone_forbidden"] != true
            || row["child_started"] != true
            || row["child_reaped"] != true
            || row["retirement_within_deadline"] != true
            || row["automatic_retry"] != false
            || row["waitid_code"] != 1
            || row["waitid_status"] != 0
            || row["wait_status"] != 0
            || row["returncode"] != 0
            || !row["pid"].as_u64().is_some_and(|v| v > 1)
        {
            return fail("normal unit child command, identity or retirement differs");
        }
        let start = row["started_monotonic_ns"]
            .as_u64()
            .ok_or("unit start absent")?;
        let finish = row["finished_monotonic_ns"]
            .as_u64()
            .ok_or("unit finish absent")?;
        let end = row["deadline_monotonic_ns"]
            .as_u64()
            .ok_or("unit original deadline absent")?;
        if start == 0
            || previous > start
            || start > finish
            || finish > end
            || end - start > 3_000_000_000
        {
            return fail("normal unit original three-second window or receipt order differs");
        }
        previous = finish;
        if !exact_keys(&row["pidfd"], &["st_dev", "st_ino"])
            || ["st_dev", "st_ino"]
                .iter()
                .any(|k| !row["pidfd"][k].as_u64().is_some_and(|v| v > 0))
        {
            return fail("owned unit PIDFD identity absent");
        }
        let file = &row["program_file"];
        let keys = [
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_gid",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        ];
        if !exact_keys(file, &keys)
            || keys.iter().any(|k| file[k].as_u64().is_none())
            || !file["st_dev"].as_u64().is_some_and(|v| v > 0)
            || !file["st_ino"].as_u64().is_some_and(|v| v > 0)
            || file["st_mode"] != 0o100755
            || file["st_uid"] != 0
            || file["st_gid"] != 0
            || file["st_nlink"] != 1
            || file["st_size"] != 302112
            || first_program.is_some_and(|first| first != file)
        {
            return fail("same held normal systemctl file is required");
        }
        first_program = Some(file);
        let mut stdout = Vec::new();
        for stream in ["stdout", "stderr", "exec_error"] {
            let body = &row[stream];
            let encoded = body["hex"].as_str().ok_or("complete unit output absent")?;
            let limit = if stream == "stdout" { 16384 } else { 4096 };
            if !exact_keys(body, &["bytes", "sha256", "hex"]) || encoded.len() > limit * 2 {
                return fail("bounded complete unit output fields differ");
            }
            let raw = hex::decode(encoded)?;
            if hex::encode(&raw) != encoded
                || body["bytes"] != raw.len()
                || body["sha256"] != sha(&raw)
                || (stream != "stdout" && !raw.is_empty())
            {
                return fail("complete normal unit output or empty error stream differs");
            }
            if stream == "stdout" {
                stdout = raw;
            }
        }
        let text = std::str::from_utf8(&stdout)?;
        let mut fields = serde_json::Map::new();
        for line in text.lines() {
            let (key, value) = line
                .split_once('=')
                .ok_or("unit property separator absent")?;
            if !UNIT_FIELDS.contains(&key) || fields.insert(key.into(), json!(value)).is_some() {
                return fail("unit property was duplicated or not requested");
            }
        }
        let fields = Value::Object(fields);
        if !exact_keys(&fields, &UNIT_FIELDS)
            || fields != runtime["systemd_units"][role]
            || fields["ActiveState"] != "active"
            || fields["SubState"] != "running"
            || fields["ControlPID"] != "0"
            || !fields["MainPID"].as_str().is_some_and(|v| {
                !v.is_empty()
                    && v.bytes().all(|c| c.is_ascii_digit())
                    && v.parse::<u32>().is_ok_and(|pid| pid > 1)
            })
        {
            return fail("raw unit outputs differ from the same actual normal units");
        }
    }
    Ok(())
}

fn validate_current_observation(v: &Value, core: &Value, inventory: &Value) -> Result<()> {
    if !exact_keys(
        v,
        &[
            "schema",
            "native_owner",
            "runtime_observation",
            "framework_epoch",
            "observation",
            "classpath",
            "artifacts",
            "data_continuity",
            "user_zero_package_inventory",
            "sampling",
            "observation_fds",
            "captured_unix_ns",
            "comparison_only",
            "account_contents_read",
            "whole_app_business_accepted",
            "production_ready",
        ],
    ) || v["schema"] != BASELINE_SCHEMA
        || &v["native_owner"] != core
        || &v["user_zero_package_inventory"] != inventory
        || v["comparison_only"] != true
        || v["account_contents_read"] != false
        || v["whole_app_business_accepted"] != false
        || v["production_ready"] != false
    {
        return fail("fixed collector did not return this actual comparison-only owner");
    }
    let r = &v["runtime_observation"];
    validate_unit_observations(r)?;
    if r["schema"] != "droidloom.native-leaf-runtime-comparison.v1"
        || &r["native_owner"] != core
        || r["normal_host_release"] != core["main"]["normal_host_release"]
        || r["main_epoch"] != v["framework_epoch"]
        || r["saved_document_can_create_authority"] != false
        || r["business_acceptance_evaluated"] != false
        || ["observation", "classpath", "artifacts", "data_continuity"]
            .iter()
            .any(|key| r[key] != v[key])
    {
        return fail("fixed collector's runtime comparison components differ");
    }
    let epoch = &v["framework_epoch"];
    if epoch["schema"] != "pocket4-framework-epoch-v1"
        || epoch["binding"]["boot_id"] != core["main"]["epoch"]["boot_id"]
        || epoch["binding"]["processes"]["init"]["host_pid"] != core["main"]["init"]["host_pid"]
        || epoch["binding"]["processes"]["init"]["start_ticks"]
            != core["main"]["init"]["start_ticks"]
        || epoch["binding"]["processes"]["system_server"]["host_pid"]
            != core["main"]["framework"]["host_pid"]
        || epoch["binding"]["processes"]["system_server"]["start_ticks"]
            != core["main"]["framework"]["start_ticks"]
    {
        return fail("collector framework comparison differs from the actual Rust Main");
    }
    let data = &v["data_continuity"];
    let package = core["application"]["package"]
        .as_str()
        .ok_or("actual package absent")?;
    let mut uids = serde_json::Map::new();
    uids.insert(package.into(), core["application"]["uid"].clone());
    let rows = core["data"]["directories"]
        .as_array()
        .ok_or("actual data directories absent")?;
    if rows.len() != 4 {
        return fail("actual target directory count differs");
    }
    let mut directories = serde_json::Map::new();
    for row in &rows[2..] {
        let name = row["path"]
            .as_str()
            .and_then(|s| s.strip_prefix("/data/"))
            .ok_or("actual target path differs")?;
        directories.insert(
            name.into(),
            json!({"device":row["device"],"inode":row["inode"],"mount_id":row["mount_id"],
            "mode":row["mode"],"uid":row["host_uid"],"gid":row["host_gid"]}),
        );
    }
    let expected = json!({"schema":"droidloom.native-leaf-target-working-data.v1","scope":"actual_inspected_user_0_package_only",
        "package_uids":uids,"directories":directories,"working_data_root":core["data"]["data_root"],
        "original_copy_origin":core["main"]["persistent_data"]["original_copy_origin"],
        "original_directory_identity_compared":false,"account_contents_read":false});
    if data != &expected {
        return fail("collector broadened or changed the actual target-only data projection");
    }
    let s = &v["sampling"];
    let span = s["finished_monotonic_ns"].as_u64().and_then(|end| {
        s["started_monotonic_ns"]
            .as_u64()
            .and_then(|start| end.checked_sub(start))
    });
    if s["double_observation_pairs"] != 3
        || s["pairs_equal"] != true
        || !span.is_some_and(|n| (10_000_000_000..=120_000_000_000).contains(&n))
    {
        return fail("collector actual repeated observation window differs");
    }
    let f = &v["observation_fds"];
    if !f["acquired"].as_u64().is_some_and(|n| n > 0)
        || f["acquired"] != f["closed"]
        || f["acquired"] != f["close_attempts"]
        || f["remaining"] != 0
        || f["errors"] != json!([])
    {
        return fail("collector did not retire all actual observation descriptors");
    }
    Ok(())
}
fn validate_readonly_receipt(
    root: &Path,
    observed: &Value,
    evidence: &std::collections::BTreeMap<String, CapturedFile>,
    actual: &NativeLeafBaselineObservation<'_>,
) -> Result<()> {
    let get = |name: &str| {
        evidence
            .get(name)
            .ok_or_else(|| format!("missing exact capture evidence: {name}"))
    };
    let receipt = get("main-readonly-entry/result.json")?;
    let runtime = &observed["runtime_observation"];
    if runtime["main_readonly_entry"] != receipt.pin(root) {
        return fail("fixed collector readonly receipt pin differs");
    }
    let v: Value = serde_json::from_slice(&receipt.raw)?;
    let core = serde_json::to_value(actual.facts())?;
    let epoch = &runtime["main_epoch"];
    let binding = json!({
        "framework_epoch_sha256":epoch["sha256"],
        "boot_id":epoch["binding"]["boot_id"],
        "init":epoch["binding"]["processes"]["init"],
        "main_user_namespace":runtime["main_user_namespace"],
        "actual_rust_main":core["main"], "actual_rust_peer":core["peer"],
        "actual_application":core["application"], "target_working_data":core["data"],
        "daemon":runtime["host_processes"]["daemon"],
        "daemon_invocation":runtime["systemd_units"]["daemon"]["InvocationID"],
        "normal_host_release":runtime["normal_host_release"],
        "installed_daemon":runtime["installed_programs"]["/usr/lib/droidloom/production/current/droidloomd"]
    });
    if !exact_keys(
        &v,
        &[
            "schema",
            "main_binding",
            "historical_helper",
            "main_capture_output",
            "commands",
            "started_unix_ns",
            "finished_unix_ns",
            "started_monotonic_ns",
            "finished_monotonic_ns",
            "transport_close",
            "normal_factory_executions",
            "Main_readonly_entry_passed",
            "Android_readonly_commands",
            "Android_mutations",
            "automatic_retry",
            "native_execution_authority_transferred",
            "daemon_ReadyTreeWitness_issued",
            "whole_process_tree_cleanup_qualified",
            "whole_app_business_accepted",
            "production_ready",
        ],
    ) || v["schema"] != "droidloom.native-leaf-readonly-entry.v2"
        || v["main_binding"] != binding
        || runtime["native_owner"] != core
        || v["Main_readonly_entry_passed"] != true
        || v["normal_factory_executions"] != 3
        || v["Android_readonly_commands"] != 3
        || v["Android_mutations"] != 0
        || v["automatic_retry"] != false
        || v["native_execution_authority_transferred"] != false
        || v["daemon_ReadyTreeWitness_issued"] != false
        || v["whole_process_tree_cleanup_qualified"] != false
        || v["whole_app_business_accepted"] != false
        || v["production_ready"] != false
        || v["main_capture_output"] != root.join("BASELINE.json").to_string_lossy().as_ref()
        || !exact_keys(
            &v["historical_helper"],
            &[
                "source",
                "binary",
                "host_evidence",
                "current_Main_qualified",
                "whole_process_tree_cleanup_qualified",
            ],
        )
        || v["historical_helper"]["current_Main_qualified"] != false
        || v["historical_helper"]["whole_process_tree_cleanup_qualified"] != false
    {
        return fail("actual readonly receipt changed its fixed same-Main comparison scope");
    }
    // The original helper source/binary and all private controls are still
    // verified by the held normal Python producer. They remain historical;
    // this run's execution is independently tied to opaque normal-factory facts.
    let monotonic = |value: &Value| {
        value
            .as_u64()
            .filter(|n| *n != 0)
            .ok_or("readonly observation timestamp is absent")
    };
    let started = monotonic(&v["started_monotonic_ns"])?;
    let finished = monotonic(&v["finished_monotonic_ns"])?;
    let wall_start = monotonic(&v["started_unix_ns"])?;
    let wall_finish = monotonic(&v["finished_unix_ns"])?;
    if monotonic(&runtime["normal_live_comparison_before"]["finished_monotonic_ns"])? > started
        || started > finished
        || finished > monotonic(&runtime["normal_live_comparison_after"]["started_monotonic_ns"])?
        || wall_start > wall_finish
        || wall_finish > monotonic(&runtime["captured_unix_ns"])?
    {
        return fail("readonly diagnostics escaped this capture's original observation bookends");
    }
    let commands = v["commands"]
        .as_array()
        .ok_or("readonly command list absent")?;
    if commands.len() != 3 {
        return fail("readonly command count differs");
    }
    let mut previous = started;
    for (index, (name, literal, expected)) in [
        (
            "guest-uid",
            vec!["/system/bin/toybox", "id", "-u"],
            b"0\n".as_slice(),
        ),
        (
            "guest-gid",
            vec!["/system/bin/toybox", "id", "-g"],
            b"0\n".as_slice(),
        ),
        (
            "boot-completed",
            vec!["/system/bin/toolbox", "getprop", "sys.boot_completed"],
            b"1\n".as_slice(),
        ),
    ]
    .iter()
    .enumerate()
    {
        let prefix = format!("main-readonly-entry/{name}");
        let result = get(&format!("{prefix}.result.json"))?;
        let stdout = get(&format!("{prefix}.stdout"))?;
        let stderr = get(&format!("{prefix}.stderr"))?;
        let intent: Value = serde_json::from_slice(&get(&format!("{prefix}.intent.json"))?.raw)?;
        let r: Value = serde_json::from_slice(&result.raw)?;
        if commands[index] != json!({"name":name,"result":result.pin(root)})
            || !exact_keys(
                &r,
                &[
                    "schema",
                    "name",
                    "main_binding",
                    "gateway",
                    "stdout",
                    "stderr",
                    "started_monotonic_ns",
                    "finished_monotonic_ns",
                    "Android_mutations",
                    "automatic_retry",
                    "comparison_only",
                ],
            )
            || r["schema"] != "droidloom.preparation-read-command.v1"
            || r["name"] != *name
            || r["main_binding"] != binding
            || r["Android_mutations"] != 0
            || r["automatic_retry"] != false
            || r["comparison_only"] != true
            || r["stdout"] != stdout.pin(root)
            || r["stderr"] != stderr.pin(root)
            || stdout.raw != *expected
            || !stderr.raw.is_empty()
            || intent
                != json!({"schema":"droidloom.preparation-read-intent.v1",
                "name":name,"main_binding":binding,"literal_operation":literal,
                "started_monotonic_ns":r["started_monotonic_ns"],"mutation":false,"automatic_retry":false})
        {
            return fail(
                "normal readonly command record differs from its fixed fresh intent/output",
            );
        }
        let begin = monotonic(&r["started_monotonic_ns"])?;
        let end = monotonic(&r["finished_monotonic_ns"])?;
        if begin < previous
            || end < begin
            || end > finished
            || end >= monotonic(&r["gateway"]["request"]["deadline_monotonic_ns"])?
        {
            return fail("normal readonly command escaped its same original end or order");
        }
        // This is the sole acceptance join: no saved receipt, status or bool
        // can populate the parent's retained opaque observations.
        actual.compare_preparation_read(index, &r["gateway"])?;
        if r["gateway"]["stdout"] != serde_json::to_value(&stdout.raw)?
            || r["gateway"]["stderr"] != serde_json::to_value(&stderr.raw)?
        {
            return fail("held readonly stream differs from the same actual factory output");
        }
        previous = end;
    }
    if v["transport_close"]
        != json!({"sealed_reply_files_received":3,
        "sealed_reply_files_closed":3,"remaining":0,"namespace_authority_transferred":false})
    {
        return fail("readonly sealed reply descriptors were not all closed");
    }
    Ok(())
}
/// The original normal producer's fixed window, also used by the working owner.
pub const BUSINESS_CAPTURE_SECONDS: u64 = 1200;
/// Each fixed IHG preparation invocation keeps its original CLI upper bound.
pub const IHG_PREPARATION_SECONDS: u64 = 1800;

fn preparation_end(until: Instant, original_seconds: u64) -> Result<Instant> {
    let now = Instant::now();
    let original = now
        .checked_add(Duration::from_secs(original_seconds))
        .ok_or("normal preparation window overflow")?;
    let end = until.min(original);
    check_before(end)?;
    Ok(end)
}

pub fn capture_business(package: &str) -> Result<Value> {
    capture_business_until(
        package,
        Instant::now() + Duration::from_secs(BUSINESS_CAPTURE_SECONDS),
    )
}

/// Reuse the exact normal collector under its original cap and an earlier
/// source-owned parent's absolute end. The deadline grants no Main authority:
/// actual PM/Main, source custody, observations and retirement remain below.
pub fn capture_business_until(package: &str, until: Instant) -> Result<Value> {
    let end = preparation_end(until, BUSINESS_CAPTURE_SECONDS)?;
    let (mut inspector, main, application, image) = actual(package, end)?;
    capture_business_observed(&mut inspector, &main, &application, image.as_ref(), end)
}

// The working producer retains these original actual objects throughout one
// source-fixed case preparation. Reusing them preserves the exact baseline
// comparison across its separately owned role identities and plan steps.
fn capture_business_observed(
    inspector: &mut NativeApplicationInspector,
    main: &MainCustodyObservation,
    application: &ActualApplicationObservation,
    image: Option<&ActualImageApplicationObservation>,
    end: Instant,
) -> Result<Value> {
    use droidloom_supervisor::control::{NativeLeafCommandKind, run_prepared_native_leaf_until};
    check_before(end)?;
    inspector.require_application_local(main,application,end)?;
    if let Some(image)=image {inspector.require_image_application_local(main,application,image,end)?;}
    let package=application.facts().package.as_str();
    let mut observed =
        NativeLeafBaselineObservation::capture_from_observed(inspector, main, application, end)?;
    if package == droidloom_supervisor::native_ihg_preparation::TARGET {
        let inventory =
            inspector.observe_user_zero_package_inventory_until(&main, &application, end)?;
        observed.attach_user_zero_inventory(inspector, inventory)?;
    }
    let inventory = serde_json::to_value(observed.inventory_facts())?;
    let core = serde_json::to_value(observed.facts())?;
    let mut sources = crate::native_leaf_sources::installed::InstalledCohort::capture(end)?;
    let (root, root_fd, identity) = private_capture_root()?;
    let operation = (|| -> Result<Value> {
        check_before(end)?;
        write_value(
            &root,
            "CAPTURE-INTENT.json",
            &json!({"schema":"droidloom.native-leaf-business-capture-intent.v1",
            "package":package,"actual_comparison":core,"normal_source_recipe":sources.recipe(),
            "fixed_readonly_commands":3,"application_business_actions":0,"automatic_retry":false}),
        )?;
        let mut command = std::process::Command::new("/usr/bin/python3");
        command
            .args(["-I", "-B"])
            .arg(sources.collector()?)
            .arg("--collect")
            .arg("--output-directory")
            .arg(&root)
            .env_clear()
            .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
            .env("LANG", "C.UTF-8");
        let output = run_prepared_native_leaf_until(
            command,
            &application.facts().epoch,
            NativeLeafCommandKind::BaselineCapture,
            inspector,
            &mut observed,
            end,
        )
        .map_err(|e| format!("normal fixed comparison collector failed: {e}"))?;
        let out = write_private(&root, "collector.stdout", &output.stdout)?;
        let err = write_private(&root, "collector.stderr", &output.stderr)?;
        write_value(
            &root,
            "CAPTURE-EXECUTION.json",
            &json!({"schema":"droidloom.native-leaf-business-capture-execution.v1",
            "actual_exit":output.status.code(),"success":output.status.success(),
            "stdout":out,"stderr":err,"owned_cgroup_empty_and_direct_child_reaped":true,
            "normal_source_recipe":sources.recipe(),"application_business_actions":0}),
        )?;
        if !output.status.success() {
            return fail(format!(
                "fixed normal collector exited {:?}; evidence retained at {}",
                output.status.code(),
                root.display()
            ));
        }
        if directory_identity(&root_fd.metadata()?) != identity
            || directory_identity(&fs::symlink_metadata(&root)?) != identity
        {
            return fail("actual normal capture root changed");
        }
        let mut evidence = std::collections::BTreeMap::new();
        for name in ["OBSERVED.json", "main-readonly-entry/result.json"] {
            check_before(end)?;
            evidence.insert(
                name.into(),
                CapturedFile::open(&root, name, 16 * 1024 * 1024)?,
            );
        }
        for name in ["guest-uid", "guest-gid", "boot-completed"] {
            for suffix in ["intent.json", "stdout", "stderr", "result.json"] {
                check_before(end)?;
                let relative = format!("main-readonly-entry/{name}.{suffix}");
                evidence.insert(
                    relative.clone(),
                    CapturedFile::open(&root, &relative, 131072)?,
                );
            }
        }
        let raw = evidence
            .get("OBSERVED.json")
            .ok_or("normal observation absent")?;
        let value: Value = serde_json::from_slice(&raw.raw)?;
        let printed: Value = serde_json::from_slice(&output.stdout)?;
        if printed
            != json!({"schema":"droidloom.native-leaf-observer-output.v1","observation":raw.pin(&root),
            "comparison_only":true,"whole_app_business_accepted":false})
        {
            return fail("normal collector stdout did not name this exact new observation");
        }
        validate_current_observation(&value, &core, &inventory)?;
        validate_readonly_receipt(&root, &value, &evidence, &observed)?;
        sources.recheck(end)?;
        bookend(inspector, &mut observed, &application, image, end)?;
        for row in evidence.values_mut() {
            check_before(end)?;
            row.recheck(&root)?;
        }
        sources.recheck(end)?;
        observed.verify_local(inspector, end)?;
        let raw = &evidence
            .get("OBSERVED.json")
            .ok_or("normal observation disappeared")?
            .raw;
        let baseline = write_private(&root, "BASELINE.json", raw)?;
        let qualification = write_value(
            &root,
            "QUALIFICATION.json",
            &json!({
            "schema":QUALIFICATION_SCHEMA,"baseline":baseline,"normal_source_recipe":sources.recipe(),
            "core_sha256":sha(&serde_json::to_vec(&canonical_value(&core))?),
            "user_zero_package_inventory_sha256":sha(&serde_json::to_vec(&canonical_value(&inventory))?),
            "main_epoch_sha256":value["framework_epoch"]["sha256"],
            "actual_main_and_target_metadata_observed":true,"working_copy_lineage_bound":true,
            "working_target_directory_identity_preserved":true,"fixed_main_readonly_entry_observed":true,
            "comparison_only":true,"account_contents_read":false,"business_actions_admitted":false,
            "whole_app_business_accepted":false,"production_ready":false,"observation_fds":value["observation_fds"]}),
        )?;
        observed.verify_local(inspector, end)?;
        if directory_identity(&root_fd.metadata()?) != identity
            || directory_identity(&fs::symlink_metadata(&root)?) != identity
        {
            return fail("normal capture root changed before final receipt");
        }
        root_fd.sync_all()?;
        check_before(end)?;
        let result = json!({"schema":"droidloom.native-leaf-business-baseline-capture.v1",
            "baseline":baseline,"qualification":qualification,"normal_source_recipe":sources.recipe(),
            "actual_owner_reobserved":true,"original_working_copy_lineage_bound":true,
            "target_package_directories_only":true,"normal_readonly_commands":3,
            "complete_user_zero_inventory_observed":observed.requires_inventory_bookend(),
            "installed_source_full_bookends_equal":true,"all_observation_evidence_read_back":true,
            "application_leaf_executed":false,"application_business_actions":0,"account_contents_read":false,
            "normal_runtime_qualified":false,"whole_app_business_accepted":false,"production_ready":false});
        write_value(&root, "RESULT.json", &result)?;
        root_fd.sync_all()?;
        Ok(result)
    })();
    if let Err(error) = &operation {
        let _ = write_value(
            &root,
            "FAILED.json",
            &json!({"schema":"droidloom.native-leaf-business-baseline-capture-failure.v1",
            "error":error.to_string(),"evidence_directory":root,"automatic_retry":false,
            "whole_app_business_accepted":false,"production_ready":false}),
        );
    }
    operation
}

/// Source-owned IHG preparation adapter. The public request contains only the
/// normal comparison/artifact pins for one fixed mode; it cannot select argv.
pub fn prepare_ihg(mode_name: &str, request: &Path, request_sha256: &str) -> Result<Value> {
    prepare_ihg_until(
        mode_name,
        request,
        request_sha256,
        Instant::now() + Duration::from_secs(IHG_PREPARATION_SECONDS),
    )
}

/// The same six normal fixed modes; this accepts only an earlier absolute
/// ceiling, never a caller-selected operation, resource profile or authority.
pub fn prepare_ihg_until(
    mode_name: &str,
    request: &Path,
    request_sha256: &str,
    until: Instant,
) -> Result<Value> {
    use droidloom_supervisor::native_ihg_preparation::{self, IhgPreparationMode};
    let mode = IhgPreparationMode::parse(mode_name).map_err(|e| format!("IHG mode: {e}"))?;
    let end = preparation_end(until, IHG_PREPARATION_SECONDS)?;
    let (root, root_fd, identity) = private_capture_root()?;
    let operation = (|| -> Result<Value> {
        let mut random = [0_u8; 16];
        File::open("/dev/urandom")?.read_exact(&mut random)?;
        let output = Path::new(mode.output_parent()).join(format!(
            "{}{}",
            mode.output_prefix(),
            hex::encode(random)
        ));
        let (mut inspector, main, application, _image) = actual(native_ihg_preparation::TARGET, end)?;
        let mut observed = NativeLeafBaselineObservation::capture_from_observed(
            &inspector,
            &main,
            &application,
            end,
        )?;
        let inventory =
            inspector.observe_user_zero_package_inventory_until(&main, &application, end)?;
        observed.attach_user_zero_inventory(&inspector, inventory)?;
        let mut sources = crate::native_leaf_sources::installed::InstalledCohort::capture(end)?;
        write_value(
            &root,
            "IHG-PREPARATION-INTENT.json",
            &json!({
                "schema":"droidloom.native-ihg-preparation-intent.v1","mode":mode.name(),
                "request":{"path":request,"sha256":request_sha256},
                "fixed_output":output,"normal_source_recipe":sources.recipe(),
                "actual_owner_comparison":observed.facts(),
                "complete_user_zero_inventory":observed.inventory_facts(),
                "original_budget_seconds":IHG_PREPARATION_SECONDS,"fixed_source_entry_required":true,
                "application_business_actions":0,"automatic_retry":false,
                "whole_app_business_accepted":false,"production_ready":false
            }),
        )?;
        let mut execution = native_ihg_preparation::run(
            mode,
            request,
            request_sha256,
            &output,
            &root,
            &mut inspector,
            &mut observed,
            end,
        )
        .map_err(|e| format!("fixed IHG preparation: {e}"))?;
        sources.recheck(end)?;
        execution
            .recheck()
            .map_err(|e| format!("IHG final held readback: {e}"))?;
        observed.verify_local(&inspector, end)?;
        if directory_identity(&root_fd.metadata()?) != identity
            || directory_identity(&fs::symlink_metadata(&root)?) != identity
        {
            return fail("normal IHG capture root changed before final publication");
        }
        let result = json!({
            "schema":"droidloom.native-ihg-preparation.v1","mode":mode.name(),
            "normal_source_recipe":sources.recipe(),"execution":execution.comparison_report(),
            "result":execution.result_pin(),"source_full_bookends_equal":true,
            "complete_user_zero_table_observed":true,"actual_main_and_target_metadata_observed":true,
            "application_business_actions":0,"account_contents_read":false,
            "whole_app_business_accepted":false,"production_ready":false,"automatic_retry":false
        });
        let pin = write_value(&root, "IHG-PREPARATION-RESULT.json", &result)?;
        execution
            .recheck()
            .map_err(|e| format!("IHG retained evidence changed: {e}"))?;
        observed.verify_local(&inspector, end)?;
        root_fd.sync_all()?;
        check_before(end)?;
        Ok(json!({"report":pin,"result":execution.result_pin(),
            "whole_app_business_accepted":false,"production_ready":false}))
    })();
    if let Err(error) = &operation {
        let _ = write_value(
            &root,
            "FAILED.json",
            &json!({
                "schema":"droidloom.native-ihg-preparation-failure.v1","mode":mode.name(),
                "actual_error":error.to_string(),"evidence_directory":root,"automatic_retry":false,
                "whole_app_business_accepted":false,"production_ready":false
            }),
        );
    }
    operation
}

#[cfg(test)]
mod business_capture_tests {
    use super::*;
    #[test]
    fn normal_preparation_uses_the_earlier_original_end_without_extending_any_cap() {
        assert_eq!(BUSINESS_CAPTURE_SECONDS, 1200);
        assert_eq!(IHG_PREPARATION_SECONDS, 1800);
        let near = Instant::now() + Duration::from_secs(1);
        assert_eq!(
            preparation_end(near, BUSINESS_CAPTURE_SECONDS).unwrap(),
            near
        );
        let before = Instant::now();
        let far = before + Duration::from_secs(3600);
        let selected = preparation_end(far, IHG_PREPARATION_SECONDS).unwrap();
        assert!(selected >= before + Duration::from_secs(IHG_PREPARATION_SECONDS));
        assert!(selected <= Instant::now() + Duration::from_secs(IHG_PREPARATION_SECONDS));
        assert!(selected < far);
        assert!(
            preparation_end(before - Duration::from_secs(1), BUSINESS_CAPTURE_SECONDS).is_err()
        );
    }

    fn unit_receipt_fixture() -> (Value, Value) {
        let mut units = serde_json::Map::new();
        let mut receipts = Vec::new();
        for (index, role) in ["daemon", "presenter"].iter().enumerate() {
            let unit = if *role == "daemon" {
                "droidloom-production.service"
            } else {
                "droidloom-production-desktop.service"
            };
            let uid = if *role == "daemon" { 0 } else { 1000 };
            let fields = json!({
                "ActiveState":"active","SubState":"running","MainPID":(40+index).to_string(),
                "ControlPID":"0","ControlGroup":format!("/fixture/{unit}"),
                "InvocationID":"00000000000000000000000000000001",
                "FragmentPath":format!("/fixture/{unit}"),"DropInPaths":""
            });
            let output = UNIT_FIELDS
                .iter()
                .map(|key| format!("{key}={}\n", fields[key].as_str().unwrap()))
                .collect::<String>();
            let body =
                |raw: &[u8]| json!({"bytes":raw.len(),"sha256":sha(raw),"hex":hex::encode(raw)});
            let start = 1_000_000_000u64 + index as u64 * 3_000_000_000;
            receipts.push(json!({
                "schema":"droidloom.native-host-unit-read.v1","role":role,"unit":unit,
                "argv":unit_query_argv(role),"program":{"path":"/usr/bin/systemctl","bytes":302112,"sha256":SYSTEMCTL_SHA},
                "program_file":{"st_dev":1,"st_ino":2,"st_mode":0o100755,"st_uid":0,"st_gid":0,
                                "st_nlink":1,"st_size":302112,"st_mtime_ns":1,"st_ctime_ns":2},
                "child_uid":uid,"child_gid":uid,"child_pre_exec_caps":0,"fork_clone_forbidden":true,
                "child_started":true,"child_reaped":true,"automatic_retry":false,
                "started_monotonic_ns":start,"deadline_monotonic_ns":start+3_000_000_000u64,
                "finished_monotonic_ns":start+1_000_000u64,"pid":100+index,"pidfd":{"st_dev":5,"st_ino":100+index},
                "waitid_code":1,"waitid_status":0,"wait_status":0,"returncode":0,
                "retirement_within_deadline":true,"stdout":body(output.as_bytes()),"stderr":body(b""),"exec_error":body(b"")
            }));
            units.insert((*role).into(), fields);
        }
        (Value::Object(units), json!(receipts))
    }
    #[test]
    fn business_capture_requires_complete_retired_fixed_unit_receipts() {
        let (core, value) = fixture();
        validate_current_observation(&value, &core, &Value::Null).unwrap();
        for (key, wrong) in [
            ("child_uid", json!(1000)),
            ("child_reaped", json!(false)),
            ("retirement_within_deadline", json!(false)),
            ("returncode", json!(1)),
            ("automatic_retry", json!(true)),
            ("child_pre_exec_caps", json!(1)),
            ("finished_monotonic_ns", json!(5_000_000_000u64)),
        ] {
            let mut bad = value.clone();
            bad["runtime_observation"]["systemd_unit_observations"][0][key] = wrong;
            assert!(
                validate_current_observation(&bad, &core, &Value::Null).is_err(),
                "{key}"
            );
        }
        let mut bad = value.clone();
        bad["runtime_observation"]["systemd_unit_observations"][0]["argv"][0] = json!("/bin/false");
        assert!(validate_current_observation(&bad, &core, &Value::Null).is_err());
        let mut bad = value.clone();
        bad["runtime_observation"]["systemd_unit_observations"][0]["stdout"]["sha256"] =
            json!("0".repeat(64));
        assert!(validate_current_observation(&bad, &core, &Value::Null).is_err());
        let mut bad = value.clone();
        bad["runtime_observation"]["systemd_unit_observations"][1] =
            bad["runtime_observation"]["systemd_unit_observations"][0].clone();
        assert!(validate_current_observation(&bad, &core, &Value::Null).is_err());
        let mut bad = value;
        bad["runtime_observation"]["systemd_unit_observations"]
            .as_array_mut()
            .unwrap()
            .pop();
        assert!(validate_current_observation(&bad, &core, &Value::Null).is_err());
    }

    fn fixture() -> (Value, Value) {
        let application = json!({"package":"com.example.bound","uid":10123,"user":0});
        let directories = json!([
            {"path":"/data/user/0"},{"path":"/data/user_de/0"},
            {"path":"/data/user/0/com.example.bound","device":9,"inode":100,"mount_id":71,"mode":16832,"host_uid":110123,"host_gid":110123},
            {"path":"/data/user_de/0/com.example.bound","device":9,"inode":101,"mount_id":71,"mode":16832,"host_uid":110123,"host_gid":110123}
        ]);
        let main = json!({"epoch":{"boot_id":"fixture-boot"},"init":{"host_pid":12,"start_ticks":20},
            "framework":{"host_pid":13,"start_ticks":30},"normal_host_release":{"test_comparison":true},
            "persistent_data":{"original_copy_origin":{"test_comparison":true}}});
        let core = json!({"application":application,"main":main,"data":{"directories":directories,"data_root":{"device":9,"inode":2}}});
        let mut uid = serde_json::Map::new();
        uid.insert("com.example.bound".into(), json!(10123));
        let mut rows = serde_json::Map::new();
        for (path, inode) in [
            ("user/0/com.example.bound", 100),
            ("user_de/0/com.example.bound", 101),
        ] {
            rows.insert(path.into(),json!({"device":9,"inode":inode,"mount_id":71,"mode":16832,"uid":110123,"gid":110123}));
        }
        let data = json!({"schema":"droidloom.native-leaf-target-working-data.v1","scope":"actual_inspected_user_0_package_only",
            "package_uids":uid,"directories":rows,"working_data_root":core["data"]["data_root"],
            "original_copy_origin":core["main"]["persistent_data"]["original_copy_origin"],
            "original_directory_identity_compared":false,"account_contents_read":false});
        let epoch = json!({"schema":"pocket4-framework-epoch-v1","binding":{"boot_id":"fixture-boot",
            "processes":{"init":{"host_pid":12,"start_ticks":20},"system_server":{"host_pid":13,"start_ticks":30}}}});
        let observation = json!({"fixture":1});
        let classpath = json!({"fixture":2});
        let artifacts = json!({"fixture":3});
        let (units, unit_receipts) = unit_receipt_fixture();
        let runtime = json!({"schema":"droidloom.native-leaf-runtime-comparison.v1","native_owner":core,
            "normal_host_release":core["main"]["normal_host_release"],"main_epoch":epoch,
            "systemd_units":units,"systemd_unit_observations":unit_receipts,
            "saved_document_can_create_authority":false,"business_acceptance_evaluated":false,
            "observation":observation,"classpath":classpath,"artifacts":artifacts,"data_continuity":data});
        let value = json!({"schema":BASELINE_SCHEMA,"native_owner":core,"runtime_observation":runtime,
            "framework_epoch":epoch,"observation":observation,"classpath":classpath,"artifacts":artifacts,
            "data_continuity":data,"user_zero_package_inventory":Value::Null,"sampling":{"double_observation_pairs":3,"pairs_equal":true,
            "started_monotonic_ns":10,"finished_monotonic_ns":10_000_000_010u64},
            "observation_fds":{"acquired":12,"closed":12,"close_attempts":12,"remaining":0,"errors":[]},
            "captured_unix_ns":42,"comparison_only":true,"account_contents_read":false,
            "whole_app_business_accepted":false,"production_ready":false});
        (core, value)
    }
    #[test]
    fn business_capture_binds_actual_owner_epoch_and_only_target_working_directories() {
        // These are parser fixtures, not constructors for opaque runtime authority.
        let (core, value) = fixture();
        validate_current_observation(&value, &core, &Value::Null).unwrap();
        let mut wrong = core.clone();
        wrong["application"]["uid"] = json!(10124);
        assert!(validate_current_observation(&value, &wrong, &Value::Null).is_err());
        let mut bad = value.clone();
        bad["framework_epoch"]["binding"]["processes"]["init"]["start_ticks"] = json!(21);
        bad["runtime_observation"]["main_epoch"] = bad["framework_epoch"].clone();
        assert!(validate_current_observation(&bad, &core, &Value::Null).is_err());
        let mut bad = value.clone();
        bad["data_continuity"]["package_uids"]["com.unobserved.package"] = json!(10300);
        bad["runtime_observation"]["data_continuity"] = bad["data_continuity"].clone();
        assert!(validate_current_observation(&bad, &core, &Value::Null).is_err());
        let mut bad = value.clone();
        bad["data_continuity"]["original_directory_identity_compared"] = json!(true);
        bad["runtime_observation"]["data_continuity"] = bad["data_continuity"].clone();
        assert!(validate_current_observation(&bad, &core, &Value::Null).is_err());
    }
    #[test]
    fn business_capture_rejects_qualification_claims_unretired_fds_and_incomplete_samples() {
        let (core, value) = fixture();
        for key in [
            "whole_app_business_accepted",
            "production_ready",
            "account_contents_read",
        ] {
            let mut bad = value.clone();
            bad[key] = json!(true);
            assert!(validate_current_observation(&bad, &core, &Value::Null).is_err());
        }
        let mut bad = value.clone();
        bad["caller_passed"] = json!(true);
        assert!(validate_current_observation(&bad, &core, &Value::Null).is_err());
        let mut bad = value.clone();
        bad["observation_fds"]["remaining"] = json!(1);
        assert!(validate_current_observation(&bad, &core, &Value::Null).is_err());
        let mut bad = value.clone();
        bad["observation_fds"]["errors"] = json!(["close failed"]);
        assert!(validate_current_observation(&bad, &core, &Value::Null).is_err());
        let mut bad = value.clone();
        bad["sampling"]["finished_monotonic_ns"] = json!(11);
        assert!(validate_current_observation(&bad, &core, &Value::Null).is_err());
        let mut bad = value;
        bad["sampling"]["double_observation_pairs"] = json!(2);
        assert!(validate_current_observation(&bad, &core, &Value::Null).is_err());
    }
}
