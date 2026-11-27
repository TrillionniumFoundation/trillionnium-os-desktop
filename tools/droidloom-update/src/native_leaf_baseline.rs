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
