//! Normal live native-leaf comparison capture. No leaf, service or installation
//! is started. The supervisor factory owns actual peer and directory lifetimes.
use crate::util::*;
use droidloom_supervisor::control::{
    ActualApplicationObservation, DEFAULT_CONTROL_SOCKET, MainCustodyObservation,
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
)> {
    let mut inspector =
        NativeApplicationInspector::acquire_until(Path::new(DEFAULT_CONTROL_SOCKET), end)?;
    let application = inspector.inspect_observed_until(package, 0, end)?;
    let main = inspector.observe_main_until(&application.facts().epoch, end)?;
    Ok((inspector, main, application))
}
fn bookend(
    inspector: &mut NativeApplicationInspector,
    held: &mut NativeLeafBaselineObservation<'_>,
    end: Instant,
) -> Result<()> {
    let application = inspector.inspect_observed_until(&held.application().package, 0, end)?;
    let main = inspector.refresh_main_until(held.main(), end)?;
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
    let (mut inspector, main, application) = actual(package, end)?;
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
    bookend(&mut inspector, &mut observed, end)?;
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
    let (mut inspector, main, application) = actual(package, end)?;
    let mut observed =
        NativeLeafBaselineObservation::capture_from_observed(&inspector, &main, &application, end)?;
    observed.compare(&value)?;
    bookend(&mut inspector, &mut observed, end)?;
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
) -> Result<()> {
    let get = |name: &str| {
        evidence
            .get(name)
            .ok_or_else(|| format!("missing exact capture evidence: {name}"))
    };
    let receipt = get("main-readonly-entry/result.json")?;
    if observed["runtime_observation"]["main_readonly_entry"] != receipt.pin(root) {
        return fail("fixed collector readonly receipt pin differs");
    }
    let v: Value = serde_json::from_slice(&receipt.raw)?;
    if v["schema"] != "droidloom.native-leaf-readonly-entry.v1"
        || v["Main_readonly_entry_passed"] != true
        || v["Android_readonly_commands"] != 3
        || v["Android_mutations"] != 0
        || v["automatic_retry"] != false
        || v["native_execution_authority_transferred"] != false
        || v["daemon_ReadyTreeWitness_issued"] != false
        || v["whole_process_tree_cleanup_qualified"] != false
        || v["whole_app_business_accepted"] != false
        || v["production_ready"] != false
        || v["main_capture_output"] != root.join("BASELINE.json").to_string_lossy().as_ref()
    {
        return fail("actual readonly receipt changed the fixed scope");
    }
    let commands = v["commands"]
        .as_array()
        .ok_or("readonly command list absent")?;
    if commands.len() != 3 {
        return fail("readonly command count differs");
    }
    for (index, (name, expected)) in [
        ("guest-uid", b"0\n".as_slice()),
        ("guest-gid", b"0\n".as_slice()),
        ("boot-completed", b"1\n".as_slice()),
    ]
    .iter()
    .enumerate()
    {
        let prefix = format!("main-readonly-entry/{name}");
        let result = get(&format!("{prefix}.result.json"))?;
        let stdout = get(&format!("{prefix}.stdout"))?;
        let stderr = get(&format!("{prefix}.stderr"))?;
        let r: Value = serde_json::from_slice(&result.raw)?;
        if commands[index] != json!({"name":name,"result":result.pin(root)})
            || r["schema"] != "pocket4-business-host-result-v1"
            || r["name"] != *name
            || r["Main_before"] != v["main_binding"]
            || r["Main_after"] != v["main_binding"]
            || r["returncode"] != 0
            || r["timed_out"] != false
            || r["spawned"] != true
            || r["host_retirement_proved"] != true
            || r["evidence_complete"] != true
            || r["errors"] != json!([])
            || r["action_attempted"] != false
            || r["Android_outcome_unknown"] != false
            || r["automatic_retry"] != false
            || r["post_guard_deferred_to_held_transport"] != false
            || r["cancellation"] != json!({"count":0,"signals":[]})
            || r["stdout"] != stdout.pin(root)
            || r["stderr"] != stderr.pin(root)
            || stdout.raw != *expected
            || !stderr.raw.is_empty()
        {
            return fail(
                "an actual fixed readonly command failed, changed scope, or lost its output",
            );
        }
        if [
            "child_started",
            "child_reaped",
            "owned_tree_cleanup_complete",
            "all_acquired_fds_closed",
            "retirement_within_deadline",
        ]
        .iter()
        .any(|k| r["lifecycle"][k] != true)
            || r["lifecycle"]["remaining_owned_children"] != json!([])
            || ["begin_passed", "restored", "final_children_empty"]
                .iter()
                .any(|k| r["subreaper"][k] != true)
        {
            return fail("actual readonly command retirement is unproven");
        }
    }
    let f = &v["authority_close"];
    if !f["acquired"].as_u64().is_some_and(|n| n > 0)
        || f["acquired"] != f["closed"]
        || f["remaining"] != 0
        || f["errors"] != json!([])
    {
        return fail("actual readonly entry authority descriptors were not retired");
    }
    Ok(())
}
/// The original normal producer's fixed window, also used by the working owner.
pub const BUSINESS_CAPTURE_SECONDS: u64 = 1200;
/// Each fixed IHG preparation invocation keeps its original CLI upper bound.
pub const IHG_PREPARATION_SECONDS: u64 = 1800;

fn preparation_end(until: Instant, original_seconds: u64) -> Result<Instant> {
    let now = Instant::now();
    let original = now.checked_add(Duration::from_secs(original_seconds))
        .ok_or("normal preparation window overflow")?;
    let end = until.min(original);
    check_before(end)?;
    Ok(end)
}

pub fn capture_business(package: &str) -> Result<Value> {
    capture_business_until(package, Instant::now() + Duration::from_secs(BUSINESS_CAPTURE_SECONDS))
}

/// Reuse the exact normal collector under its original cap and an earlier
/// source-owned parent's absolute end. The deadline grants no Main authority:
/// actual PM/Main, source custody, observations and retirement remain below.
pub fn capture_business_until(package: &str, until: Instant) -> Result<Value> {
    use droidloom_supervisor::control::{NativeLeafCommandKind, run_prepared_native_leaf_until};
    let end = preparation_end(until, BUSINESS_CAPTURE_SECONDS)?;
    let (mut inspector, main, application) = actual(package, end)?;
    let mut observed =
        NativeLeafBaselineObservation::capture_from_observed(&inspector, &main, &application, end)?;
    if package == droidloom_supervisor::native_ihg_preparation::TARGET {
        let inventory =
            inspector.observe_user_zero_package_inventory_until(&main, &application, end)?;
        observed.attach_user_zero_inventory(&inspector, inventory)?;
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
            &mut inspector,
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
        validate_readonly_receipt(&root, &value, &evidence)?;
        sources.recheck(end)?;
        bookend(&mut inspector, &mut observed, end)?;
        for row in evidence.values_mut() {
            check_before(end)?;
            row.recheck(&root)?;
        }
        sources.recheck(end)?;
        observed.verify_local(&inspector, end)?;
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
        observed.verify_local(&inspector, end)?;
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
    prepare_ihg_until(mode_name, request, request_sha256,
        Instant::now() + Duration::from_secs(IHG_PREPARATION_SECONDS))
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
        let (mut inspector, main, application) = actual(native_ihg_preparation::TARGET, end)?;
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
        assert_eq!(preparation_end(near, BUSINESS_CAPTURE_SECONDS).unwrap(), near);
        let before = Instant::now();
        let far = before + Duration::from_secs(3600);
        let selected = preparation_end(far, IHG_PREPARATION_SECONDS).unwrap();
        assert!(selected >= before + Duration::from_secs(IHG_PREPARATION_SECONDS));
        assert!(selected <= Instant::now() + Duration::from_secs(IHG_PREPARATION_SECONDS));
        assert!(selected < far);
        assert!(preparation_end(before - Duration::from_secs(1), BUSINESS_CAPTURE_SECONDS).is_err());
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
        let runtime = json!({"schema":"droidloom.native-leaf-runtime-comparison.v1","native_owner":core,
            "normal_host_release":core["main"]["normal_host_release"],"main_epoch":epoch,
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
