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

/// Preserve the updater's complete compiled recovery/source checks before the
/// shared normal collector; no runtime or business authority comes from them.
pub fn capture_business(package: &str) -> Result<Value> {
    crate::native_leaf_sources::installed::validate_compiled_recipe()?;
    droidloom_supervisor::native_leaf_business_capture::capture_business(package)
}

/// Source-owned IHG preparation adapter. The public request contains only the
/// normal comparison/artifact pins for one fixed mode; it cannot select argv.
pub fn prepare_ihg(mode_name: &str, request: &Path, request_sha256: &str) -> Result<Value> {
    use droidloom_supervisor::native_ihg_preparation::{self, IhgPreparationMode};
    let mode = IhgPreparationMode::parse(mode_name).map_err(|e| format!("IHG mode: {e}"))?;
    let end = Instant::now() + Duration::from_secs(1800);
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
                "original_budget_seconds":1800,"fixed_source_entry_required":true,
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
