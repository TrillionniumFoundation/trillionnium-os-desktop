//! Explicit recovery of one owned source staging directory under the normal lock.
//!
//! A previous attempt's manifest or progress is never evidence of completion.
//! Every reused project is checked again. Incomplete checkouts keep their object
//! cache and original failure evidence; no force checkout, reset, clean, or
//! recursive directory removal is used. The caller holds the normal work locks.
use super::{build_plan, ensure_root_link, io_error, is_commit, sha256_file,
    verify_materialized, MaterializedManifest, PlannedProject, SourceError, SparseSourceLock};
use serde_json::{json, Value};
use sha2::{Digest as _, Sha256};
use std::collections::BTreeSet;
use std::ffi::{OsStr, OsString};
use std::fs::{self, File, Metadata, OpenOptions};
use std::io::{Read as _, Write as _};
use std::os::unix::fs::{MetadataExt as _, OpenOptionsExt as _};
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::thread;
use std::time::Instant;

const GIT_OUTPUT_LIMIT: u64 = 1024 * 1024;
const PROGRESS_LIMIT: usize = 8 * 1024 * 1024;
const MATERIALIZE_SECONDS: u64 = 5900;

fn invalid(message: impl Into<String>) -> SourceError {
    SourceError::Invalid(vec![message.into()])
}

fn identity(info: &Metadata) -> Value {
    json!({"device":info.dev(),"inode":info.ino(),"mode":info.mode(),
        "uid":info.uid(),"gid":info.gid(),"bytes":info.len(),
        "mtime":info.mtime(),"mtime_nsec":info.mtime_nsec(),
        "ctime":info.ctime(),"ctime_nsec":info.ctime_nsec()})
}

fn same_object(left: &Metadata, right: &Metadata) -> bool {
    (left.dev(), left.ino(), left.mode(), left.uid(), left.gid())
        == (right.dev(), right.ino(), right.mode(), right.uid(), right.gid())
}

fn real_directory(path: &Path, owner: u32) -> Result<Metadata, SourceError> {
    if !path.is_absolute() || path.components().any(|part|
        matches!(part, Component::CurDir | Component::ParentDir)) {
        return Err(invalid("recovery requires an absolute path without traversal"));
    }
    for ancestor in path.ancestors() {
        let info = fs::symlink_metadata(ancestor)
            .map_err(|error| io_error("stat fixed recovery directory", error))?;
        if !info.is_dir() || info.file_type().is_symlink() {
            return Err(invalid("recovery path has a symlink or non-directory component"));
        }
    }
    let info = fs::symlink_metadata(path)
        .map_err(|error| io_error("stat owned recovery directory", error))?;
    if info.uid() != owner || info.mode() & 0o022 != 0 {
        return Err(invalid("recovery directory is not exclusively writable by its owner"));
    }
    Ok(info)
}

struct Progress {
    file: File,
    started: Instant,
    sequence: usize,
    bytes: usize,
}

impl Progress {
    fn create(path: &Path, owner: u32) -> Result<Self, SourceError> {
        real_directory(path.parent().ok_or_else(|| invalid("progress has no parent"))?, owner)?;
        let file = OpenOptions::new().write(true).create_new(true).mode(0o600)
            .open(path).map_err(|error| io_error("create attempt-specific source progress", error))?;
        Ok(Self { file, started: Instant::now(), sequence: 0, bytes: 0 })
    }

    fn record(&mut self, state: &str, detail: Value) -> Result<(), SourceError> {
        self.sequence += 1;
        let raw = serde_json::to_vec(&json!({"schema":1,"sequence":self.sequence,
            "state":state,"seconds":self.started.elapsed().as_secs_f64(),"detail":detail,
            "build_or_runtime_qualified":false}))
            .map_err(|error| invalid(format!("serialize source progress: {error}")))?;
        if raw.len() > 16384 || self.bytes + raw.len() + 1 > PROGRESS_LIMIT {
            return Err(invalid("source progress exceeds its fixed bound"));
        }
        self.file.write_all(&raw).and_then(|()| self.file.write_all(b"\n"))
            .and_then(|()| self.file.sync_all())
            .map_err(|error| io_error("persist source progress before continuing", error))?;
        self.bytes += raw.len() + 1;
        // The durable record is written first. No captured Git output, URL,
        // environment, or unbounded list is printed in this progress stream.
        eprintln!("{}", String::from_utf8_lossy(&raw));
        Ok(())
    }

    fn remaining(&self, maximum: u64) -> Result<u64, SourceError> {
        let left = MATERIALIZE_SECONDS.saturating_sub(self.started.elapsed().as_secs());
        if left <= 3 {
            return Err(invalid("bounded source materialization deadline reached"));
        }
        Ok(maximum.min(left - 2))
    }
}

fn bounded_pipe(mut reader: impl std::io::Read) -> std::io::Result<Vec<u8>> {
    let mut raw = Vec::new();
    reader.by_ref().take(GIT_OUTPUT_LIMIT + 1).read_to_end(&mut raw)?;
    Ok(raw)
}

fn git_output(checkout: &Path, args: &[OsString], progress: &Progress,
              network: bool) -> Result<Output, SourceError> {
    let seconds = progress.remaining(if network { MATERIALIZE_SECONDS } else { 60 })?;
    let mut command = Command::new("/usr/bin/timeout");
    command.args(["--signal=TERM", "--kill-after=2s"])
        .arg(format!("{seconds}s")).arg("/usr/bin/git")
        .args(["--no-optional-locks", "-C"]).arg(checkout)
        .args(["-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
            "-c", "maintenance.auto=false", "-c", "gc.auto=0",
            "-c", "protocol.allow=never"]);
    if network {
        command.args(["-c", "protocol.https.allow=always"]);
    }
    // Unit controls exercise complete, locally cached objects only. A broken
    // cache expectation must fail instead of accessing a remote fixture URL.
    #[cfg(test)]
    command.args(["-c", "protocol.https.allow=never"]);
    // Keep the host's transport/CA environment, but do not inherit a caller's
    // GIT_DIR, alternate index, injected config parameters, or external helper.
    for (name, _) in std::env::vars_os() {
        if name.to_string_lossy().starts_with("GIT_") {
            command.env_remove(name);
        }
    }
    command.env("GIT_CONFIG_NOSYSTEM", "1").env("GIT_CONFIG_GLOBAL", "/dev/null")
        .env("GIT_TERMINAL_PROMPT", "0").env("GIT_ASKPASS", "/bin/false")
        .env("GIT_OPTIONAL_LOCKS", "0").env("GIT_NO_LAZY_FETCH", if network { "0" } else { "1" })
        .env("GIT_LFS_SKIP_SMUDGE", "1").env("LC_ALL", "C")
        .args(args).stdout(Stdio::piped()).stderr(Stdio::piped());
    let mut child = command.spawn().map_err(|error| io_error("start bounded source Git", error))?;
    let stdout = child.stdout.take().ok_or_else(|| invalid("source Git stdout unavailable"))?;
    let stderr = child.stderr.take().ok_or_else(|| invalid("source Git stderr unavailable"))?;
    let stdout = thread::spawn(move || bounded_pipe(stdout));
    let stderr = thread::spawn(move || bounded_pipe(stderr));
    let status = child.wait().map_err(|error| io_error("wait for bounded source Git", error));
    // Always join both readers before propagating any outcome. A reader panic
    // or pipe error must not detach its peer or replace an earlier wait error.
    let stdout = stdout.join();
    let stderr = stderr.join();
    let status = status?;
    let stdout = stdout.map_err(|_| invalid("source Git stdout reader panicked"))?
        .map_err(|error| io_error("read bounded source Git stdout", error))?;
    let stderr = stderr.map_err(|_| invalid("source Git stderr reader panicked"))?
        .map_err(|error| io_error("read bounded source Git stderr", error))?;
    if stdout.len() > GIT_OUTPUT_LIMIT as usize || stderr.len() > GIT_OUTPUT_LIMIT as usize {
        return Err(invalid("source Git output exceeded its fixed bound"));
    }
    Ok(Output { status, stdout, stderr })
}

fn arguments(values: &[&str]) -> Vec<OsString> {
    values.iter().map(|value| OsString::from(*value)).collect()
}

fn git(checkout: &Path, args: &[OsString], progress: &Progress,
       network: bool) -> Result<Vec<u8>, SourceError> {
    let output = git_output(checkout, args, progress, network)?;
    if output.status.success() {
        Ok(output.stdout)
    } else {
        Err(SourceError::Command { program: "bounded git".into(),
            status: output.status.to_string(),
            stderr: String::from_utf8_lossy(&output.stderr).chars().take(4096).collect() })
    }
}

fn exact_origin(checkout: &Path, project: &PlannedProject,
                progress: &Progress) -> Result<(), SourceError> {
    let origin = git(checkout, &arguments(&["remote", "get-url", "origin"]), progress, false)?;
    if origin != format!("{}\n", project.url).as_bytes() {
        return Err(invalid(format!("project {} origin differs from the exact lock", project.path.display())));
    }
    Ok(())
}

fn expected_sparse(project: &PlannedProject) -> BTreeSet<PathBuf> {
    project.sparse_paths.iter().filter(|path| !project.sparse_paths.iter()
        .any(|parent| parent != *path && path.starts_with(parent))).cloned().collect()
}

fn sparse_matches(checkout: &Path, project: &PlannedProject,
                  progress: &Progress) -> Result<(), SourceError> {
    let enabled = git_output(checkout, &arguments(&["config", "--bool", "core.sparseCheckout"]),
        progress, false)?;
    if project.sparse_paths.is_empty() {
        if (enabled.status.success() && enabled.stdout == b"false\n")
            || (enabled.status.code() == Some(1) && enabled.stdout.is_empty()) {
            return Ok(());
        }
        return Err(invalid("a full locked project has unexpected sparse-checkout configuration"));
    }
    if !enabled.status.success() || enabled.stdout != b"true\n" {
        return Err(invalid("locked sparse-checkout configuration is missing"));
    }
    let actual = git(checkout, &arguments(&["sparse-checkout", "list"]), progress, false)?;
    let actual = std::str::from_utf8(&actual).map_err(|_| invalid("sparse-checkout list is not UTF-8"))?
        .lines().map(PathBuf::from).collect::<BTreeSet<_>>();
    if actual != expected_sparse(project) {
        return Err(invalid("existing sparse-checkout paths differ from the locked plan"));
    }
    Ok(())
}

fn verify_project(checkout: &Path, project: &PlannedProject,
                  progress: &Progress, owner: u32) -> Result<(), SourceError> {
    real_directory(checkout, owner)?;
    real_directory(&checkout.join(".git"), owner)?;
    let head = git(checkout, &arguments(&["rev-parse", "--verify", "HEAD"]), progress, false)?;
    if head != format!("{}\n", project.commit).as_bytes() {
        return Err(invalid(format!("project {} HEAD differs from its locked commit", project.path.display())));
    }
    exact_origin(checkout, project, progress)?;
    sparse_matches(checkout, project, progress)?;
    let status = git(checkout, &arguments(&["status", "--porcelain=v1", "--untracked-files=all"]),
        progress, false)?;
    if !status.is_empty() {
        return Err(invalid(format!("project {} has local changes", project.path.display())));
    }
    Ok(())
}

fn read_owned(path: &Path, owner: u32, maximum: u64) -> Result<Vec<u8>, SourceError> {
    let before = fs::symlink_metadata(path).map_err(|error| io_error("stat exact recovery file", error))?;
    if !before.is_file() || before.file_type().is_symlink() || before.uid() != owner
        || before.nlink() != 1 || before.mode() & 0o022 != 0 || before.len() > maximum {
        return Err(invalid("exact recovery file has unsafe identity or size"));
    }
    let mut file = File::open(path).map_err(|error| io_error("open exact recovery file", error))?;
    let held = file.metadata().map_err(|error| io_error("stat held recovery file", error))?;
    let mut raw = Vec::new();
    std::io::Read::by_ref(&mut file).take(maximum + 1).read_to_end(&mut raw)
        .map_err(|error| io_error("read exact recovery file", error))?;
    let after = file.metadata().map_err(|error| io_error("restat held recovery file", error))?;
    let named = fs::symlink_metadata(path).map_err(|error| io_error("restat named recovery file", error))?;
    if identity(&before) != identity(&held) || identity(&held) != identity(&after)
        || identity(&held) != identity(&named) || raw.len() as u64 != held.len() {
        return Err(invalid("recovery file changed while observed"));
    }
    Ok(raw)
}

fn absent(path: &Path) -> Result<bool, SourceError> {
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(true),
        Err(error) => Err(io_error("stat exact source path", error)),
        Ok(_) => Ok(false),
    }
}

fn owned_parents(root: &Path, relative: &Path, owner: u32) -> Result<(), SourceError> {
    let parent = relative.parent().ok_or_else(|| invalid("locked path has no parent"))?;
    let mut current = root.to_owned();
    real_directory(&current, owner)?;
    for component in parent.components() {
        let Component::Normal(name) = component else {
            return Err(invalid("locked parent path is not normalized"));
        };
        current.push(name);
        if absent(&current)? {
            // Create a single child only after its parent was checked. Do not
            // let create_dir_all traverse an alias in recovered staging.
            fs::create_dir(&current).map_err(|error| io_error("create one owned locked parent", error))?;
        }
        real_directory(&current, owner)?;
    }
    Ok(())
}

fn configure_sparse(checkout: &Path, project: &PlannedProject,
                    progress: &Progress) -> Result<(), SourceError> {
    if project.sparse_paths.is_empty() { return Ok(()); }
    git(checkout, &arguments(&["sparse-checkout", "init", "--cone"]), progress, false)?;
    let mut args = arguments(&["sparse-checkout", "set", "--cone", "--skip-checks", "--"]);
    args.extend(project.sparse_paths.iter().map(|path| path.as_os_str().to_owned()));
    git(checkout, &args, progress, false)?;
    Ok(())
}

fn resume_project(root: &Path, project: &PlannedProject, ordinal: usize,
                  progress: &mut Progress, owner: u32, recovery: &Path) -> Result<(), SourceError> {
    let checkout = root.join(&project.path);
    let detail = || json!({"ordinal":ordinal,"path":project.path,"commit":project.commit});
    progress.record("PROJECT_VERIFY_OR_INITIALIZE", detail())?;
    owned_parents(root, &project.path, owner)?;
    if absent(&checkout)? {
        let parent = checkout.parent().ok_or_else(|| invalid("locked checkout has no parent"))?;
        real_directory(parent, owner)?;
        let mut args = arguments(&["init", "--quiet", "--initial-branch=droidloom"]);
        args.push(checkout.as_os_str().to_owned());
        git(root, &args, progress, false)?;
        git(&checkout, &arguments(&["remote", "add", "origin", &project.url]), progress, false)?;
        configure_sparse(&checkout, project, progress)?;
    } else {
        real_directory(&checkout, owner)?;
        real_directory(&checkout.join(".git"), owner)?;
        let head = read_owned(&checkout.join(".git/HEAD"), owner, 256)?;
        if head == format!("{}\n", project.commit).as_bytes() {
            // An already checked-out project is either clean and reused, or
            // rejected. Its files and index are never reset or rewritten here.
            verify_project(&checkout, project, progress, owner)?;
            if !absent(&checkout.join(".git/index.lock"))? {
                return Err(invalid("a completed project has an unexplained index lock"));
            }
            progress.record("PROJECT_VERIFIED_REUSED_WITHOUT_FETCH_OR_CHECKOUT", detail())?;
            return Ok(());
        }
        if head != b"ref: refs/heads/droidloom\n"
            || !absent(&checkout.join(".git/refs/heads/droidloom"))?
            || !absent(&checkout.join(".git/packed-refs"))?
            || !absent(&checkout.join(".git/index"))? {
            return Err(invalid("existing project is neither exact-clean nor the initial interrupted checkout"));
        }
        exact_origin(&checkout, project, progress)?;
        sparse_matches(&checkout, project, progress)?;
        let index_lock = checkout.join(".git/index.lock");
        if !absent(&index_lock)? {
            // The observed retired checkout left an empty lock, not a partial
            // index payload. Preserve that exact supported shape; a nonempty
            // lock needs a separate observation and is never moved here.
            let bytes = read_owned(&index_lock, owner, 0)?;
            let before = fs::symlink_metadata(&index_lock)
                .map_err(|error| io_error("stat supported interrupted index lock", error))?;
            if before.mode() & 0o777 != 0o600 || before.nlink() != 1 || before.len() != 0 {
                return Err(invalid("interrupted index lock is not the observed empty private file shape"));
            }
            if absent(recovery)? {
                fs::create_dir(recovery).map_err(|error| io_error("create attempt-specific recovery evidence", error))?;
            }
            real_directory(recovery, owner)?;
            let retained = recovery.join(format!("project-{ordinal:03}-index.lock"));
            if !absent(&retained)? { return Err(invalid("recovery evidence path already exists")); }
            let digest = format!("{:x}", Sha256::digest(&bytes));
            progress.record("INITIAL_CHECKOUT_INDEX_LOCK_RETAIN_BEFORE_RENAME",
                json!({"ordinal":ordinal,"bytes":bytes.len(),"sha256":digest,
                    "original_identity":identity(&before),"retained":retained}))?;
            let current = fs::symlink_metadata(&index_lock)
                .map_err(|error| io_error("recheck interrupted lock immediately before retaining", error))?;
            if identity(&current) != identity(&before) || current.nlink() != 1 {
                return Err(invalid("interrupted index lock changed before retaining"));
            }
            fs::rename(&index_lock, &retained).map_err(|error| io_error("retain interrupted index lock", error))?;
            let after = fs::symlink_metadata(&retained)
                .map_err(|error| io_error("stat retained interrupted index lock", error))?;
            if !same_object(&before, &after) || after.nlink() != 1
                || read_owned(&retained, owner, 0)? != bytes {
                return Err(invalid("retained index lock identity or bytes changed"));
            }
            File::open(index_lock.parent().ok_or_else(|| invalid("index lock has no parent"))?)
                .and_then(|file| file.sync_all())
                .and_then(|()| File::open(recovery).and_then(|file| file.sync_all()))
                .map_err(|error| io_error("persist retained interrupted index lock rename", error))?;
        }
    }
    exact_origin(&checkout, project, progress)?;
    let commit = format!("{}^{{commit}}", project.commit);
    let cached = git_output(&checkout, &arguments(&["cat-file", "-e", &commit]), progress, false)?;
    if cached.status.success() {
        progress.record("PROJECT_EXACT_COMMIT_LOCAL_CHECKOUT_STILL_REQUIRED", detail())?;
    } else {
        if !matches!(cached.status.code(), Some(1 | 128)) {
            return Err(invalid(format!("local commit probe failed: {}", cached.status)));
        }
        progress.record("PROJECT_COMMIT_PROBE_NOT_PASSED", json!({"ordinal":ordinal,
            "returncode":cached.status.code(),
            "stderr":String::from_utf8_lossy(&cached.stderr).chars().take(4096).collect::<String>()}))?;
        progress.record("PROJECT_FETCH_EXACT_COMMIT", detail())?;
        // Fetch reuses completed object packs. The source files are not removed;
        // the exact locked commit is the only permitted new remote input.
        git(&checkout, &arguments(&["fetch", "--quiet", "--depth=1", "--filter=blob:none",
            "origin", &project.commit]), progress, true)?;
    }
    progress.record("PROJECT_CHECKOUT_EXACT_COMMIT", detail())?;
    // No --force: an untracked or modified conflicting file fails without
    // being discarded. The following clean-tree gate also rejects leftovers.
    git(&checkout, &arguments(&["checkout", "--quiet", "--detach", &project.commit]), progress, true)?;
    progress.record("PROJECT_VERIFY_AFTER_CHECKOUT", detail())?;
    verify_project(&checkout, project, progress, owner)?;
    progress.record("PROJECT_VERIFIED", detail())
}

/// Materialize with durable per-project progress and optional explicit staging.
///
/// `resume` is never discovered by scanning directories. It must be a private
/// direct child of the destination's owned parent, selected by the operator
/// after the previous job has retired. The caller holds its existing source
/// and package locks. Failures keep staging and append a failed progress row.
/// No materialized manifest is written until every locked project and link
/// passes; the original normal verifier runs before atomic publication.
///
/// # Errors
/// Returns for unsafe or mismatched staging, changed or dirty projects,
/// conflicting initial checkout files, bounded Git failure, or I/O errors.
pub fn materialize_resuming(lock_path: &Path, lock: &SparseSourceLock,
    destination: &Path, resume: Option<&Path>, progress_path: &Path)
    -> Result<MaterializedManifest, SourceError> {
    let plan = build_plan(lock)?;
    if build_plan(&super::load_lock(lock_path)?)? != plan {
        return Err(invalid("in-memory source plan does not match the supplied lock file"));
    }
    if !absent(destination)? { return Err(invalid("materialization destination must remain absent")); }
    let parent = destination.parent().ok_or_else(|| invalid("materialization destination has no parent"))?;
    let parent_info = fs::symlink_metadata(parent).map_err(|error| io_error("stat source workspace", error))?;
    let owner = parent_info.uid();
    real_directory(parent, owner)?;
    let mut progress = Progress::create(progress_path, owner)?;
    let root = match resume {
        Some(root) => {
            if root.parent() != Some(parent) || root == destination
                || !root.file_name().and_then(OsStr::to_str)
                    .is_some_and(|name| name.starts_with(".droidloom-source-")
                        && name.len() <= 96 && name.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'-')) {
                return Err(invalid("explicit staging is not a bounded direct workspace child"));
            }
            root.to_owned()
        }
        None => tempfile::Builder::new().prefix(".droidloom-source-").tempdir_in(parent)
            .map_err(|error| io_error("create persistent source staging", error))?.keep(),
    };
    let root_info = real_directory(&root, owner)?;
    if root_info.dev() != parent_info.dev() || root_info.mode() & 0o777 != 0o700 {
        return Err(invalid("source staging must be private and on its owned workspace filesystem"));
    }
    let lock_sha = sha256_file(lock_path)?;
    progress.record("SOURCE_STAGING_BOUND", json!({"source_lock_sha256":lock_sha,
        "staging":root,"staging_identity":identity(&root_info),"destination":destination,
        "projects":plan.projects.len(),"links":plan.links.len(),"explicit_resume":resume.is_some()}))?;
    let recovery = progress_path.parent().ok_or_else(|| invalid("progress has no parent"))?
        .join("source-recovery");
    let mut publication_rename_completed = false;
    let outcome = (|| {
        for (ordinal, project) in plan.projects.iter().enumerate() {
            if !is_commit(&project.commit) { return Err(invalid("non-exact project commit")); }
            resume_project(&root, project, ordinal + 1, &mut progress, owner, &recovery)?;
        }
        progress.record("VERIFY_ROOT_LINKS", json!({"links":plan.links.len()}))?;
        for link in &plan.links {
            owned_parents(&root, &link.target, owner)?;
            ensure_root_link(&root, link)?;
        }
        if sha256_file(lock_path)? != lock_sha { return Err(invalid("source lock changed while materializing")); }
        let manifest = MaterializedManifest { schema_version:1, source_lock_sha256:lock_sha.clone(), plan };
        let bytes = serde_json::to_vec_pretty(&manifest)
            .map_err(|error| invalid(format!("serialize completed source manifest: {error}")))?;
        let path = root.join(".droidloom-source-manifest.json");
        if absent(&path)? {
            let mut file = tempfile::Builder::new().prefix(".droidloom-complete-manifest-")
                .tempfile_in(&root).map_err(|error| io_error("stage verified materialized manifest", error))?;
            file.write_all(&bytes).and_then(|()| file.as_file().sync_all())
                .map_err(|error| io_error("persist verified materialized manifest", error))?;
            file.persist_noclobber(&path)
                .map_err(|error| io_error("publish verified materialized manifest without replacement", error.error))?;
        } else if read_owned(&path, owner, 1024 * 1024)? != bytes {
            return Err(invalid("pre-existing staging manifest differs from the fully verified plan"));
        }
        progress.record("NORMAL_SOURCE_VERIFIER_BEFORE_PUBLICATION", json!({"projects":manifest.plan.projects.len()}))?;
        verify_materialized(lock_path, lock, &root)?;
        if !same_object(&root_info, &real_directory(&root, owner)?) || !absent(destination)? {
            return Err(invalid("source staging or destination identity changed before publication"));
        }
        fs::rename(&root, destination).map_err(|error| io_error("publish fully verified source staging", error))?;
        publication_rename_completed = true;
        File::open(parent).and_then(|file| file.sync_all())
            .map_err(|error| io_error("persist published source directory", error))?;
        progress.record("SOURCE_PUBLISHED_NOT_BUILD_QUALIFIED", json!({"destination":destination,
            "source_lock_sha256":lock_sha,"projects":manifest.plan.projects.len()}))?;
        Ok(manifest)
    })();
    if let Err(error) = &outcome {
        let remaining = match fs::symlink_metadata(&root) {
            Ok(info) => json!({"present":true,"identity":identity(&info)}),
            Err(error) => json!({"observed_error_kind":format!("{:?}", error.kind())}),
        };
        if let Err(secondary) = progress.record("SOURCE_MATERIALIZATION_FAILED",
            json!({"staging":root,"staging_metadata_after_failure":remaining,
                "publication_rename_completed":publication_rename_completed,
                "error":error.to_string().chars().take(4096).collect::<String>()})) {
            eprintln!("source progress also failed while preserving the original error: {secondary}");
        }
    }
    outcome
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt as _;

    fn local_git(root: &Path, args: &[OsString]) -> Vec<u8> {
        let output = Command::new("/usr/bin/git").env_clear()
            .env("PATH", "/usr/bin:/bin").env("LC_ALL", "C")
            .env("GIT_CONFIG_NOSYSTEM", "1").env("GIT_CONFIG_GLOBAL", "/dev/null")
            .args(["-c", "maintenance.auto=false", "-c", "gc.auto=0", "-C"])
            .arg(root).args(args).output().unwrap();
        assert!(output.status.success(), "local fixture Git: {}", String::from_utf8_lossy(&output.stderr));
        output.stdout
    }

    struct Fixture {
        _temporary: tempfile::TempDir,
        root: PathBuf,
        staging: PathBuf,
        checkout: PathBuf,
        destination: PathBuf,
        progress: PathBuf,
        lock_path: PathBuf,
        lock: SparseSourceLock,
    }

    impl Fixture {
        fn cached(checked_out: bool) -> Self {
            let temporary = tempfile::tempdir().unwrap();
            let root = temporary.path().to_owned();
            let origin = root.join("fixture-origin");
            fs::create_dir(&origin).unwrap();
            local_git(&origin, &arguments(&["init", "--quiet", "--initial-branch=main"]));
            fs::write(origin.join("marker"), b"locked bytes\n").unwrap();
            local_git(&origin, &arguments(&["add", "marker"]));
            local_git(&origin, &arguments(&["-c", "user.name=Owned source test", "-c",
                "user.email=owned-source-test@droidloom.invalid", "commit", "--quiet", "-m", "fixture"]));
            let commit = String::from_utf8(local_git(&origin, &arguments(&["rev-parse", "HEAD"])))
                .unwrap().trim().to_owned();
            let staging = root.join(".droidloom-source-fixture");
            fs::create_dir(&staging).unwrap();
            fs::set_permissions(&staging, fs::Permissions::from_mode(0o700)).unwrap();
            let checkout = staging.join("project");
            fs::create_dir(&checkout).unwrap();
            local_git(&checkout, &arguments(&["init", "--quiet", "--initial-branch=droidloom"]));
            // Populate objects through an explicit local fixture transport;
            // production recovery never enables protocol.file.
            local_git(&checkout, &arguments(&["-c", "protocol.allow=never", "-c", "protocol.file.allow=always",
                "fetch", "--quiet", "--depth=1", &format!("file://{}", origin.display()), &commit]));
            let url = "https://android.googlesource.com/platform/owned-resume-control";
            local_git(&checkout, &arguments(&["remote", "add", "origin", url]));
            if checked_out {
                local_git(&checkout, &arguments(&["checkout", "--quiet", "--detach", &commit]));
            }
            let lock_json = json!({"schema_version":1,"selected_at":"2026-11-05",
                "status":"seed_not_yet_build_proven",
                "remote_base":"https://android.googlesource.com/",
                "superproject":{"name":"platform/superproject","ref":"refs/heads/android-owned-resume-control",
                    "commit":"28f0bbddc24d56c8ec5a8df5342ac7a292184039"},
                "policy":{"allow_unrestricted_repo_sync":false,"require_exact_commits":true,
                    "add_dependencies_only_from_superproject":true,"base_partitions_come_from_aosp_ci_artifact":true},
                "links":[],"projects":[{"path":"project","name":"platform/owned-resume-control",
                    "commit":commit,"purpose":"local interrupted-checkout mechanism control"}]});
            let lock_path = root.join("fixture-lock.json");
            fs::write(&lock_path, serde_json::to_vec_pretty(&lock_json).unwrap()).unwrap();
            let lock = serde_json::from_value(lock_json).unwrap();
            let out = root.join("attempt");
            fs::create_dir(&out).unwrap();
            Self { _temporary:temporary, destination:root.join("aosp-source"),
                progress:out.join("droidloom-source-progress.jsonl"), root,
                staging, checkout, lock_path, lock }
        }

        fn resume(&self) -> Result<MaterializedManifest, SourceError> {
            materialize_resuming(&self.lock_path, &self.lock, &self.destination,
                Some(&self.staging), &self.progress)
        }

        fn records(&self) -> Vec<Value> {
            fs::read_to_string(&self.progress).unwrap().lines()
                .map(|line| serde_json::from_str(line).unwrap()).collect()
        }
    }

    #[test]
    fn completed_project_reuse_has_no_fetch_or_checkout_and_publishes_only_after_verify() {
        let fixture = Fixture::cached(true);
        let marker = fs::metadata(fixture.checkout.join("marker")).unwrap();
        let manifest = fixture.resume().unwrap();
        assert_eq!(manifest.plan.projects.len(), 1);
        let published = fixture.destination.join("project/marker");
        assert_eq!(fs::read(&published).unwrap(), b"locked bytes\n");
        assert_eq!(fs::metadata(published).unwrap().ino(), marker.ino());
        assert!(!fixture.staging.exists());
        verify_materialized(&fixture.lock_path, &fixture.lock, &fixture.destination).unwrap();
        let records = fixture.records();
        assert!(records.iter().any(|row| row["state"] == "PROJECT_VERIFIED_REUSED_WITHOUT_FETCH_OR_CHECKOUT"));
        assert!(!records.iter().any(|row| row["state"] == "PROJECT_FETCH_EXACT_COMMIT"
            || row["state"] == "PROJECT_CHECKOUT_EXACT_COMMIT"));
        assert_eq!(records.last().unwrap()["state"], "SOURCE_PUBLISHED_NOT_BUILD_QUALIFIED");
        assert!(records.iter().all(|row| row["build_or_runtime_qualified"] == false));
    }

    #[test]
    fn initial_checkout_reuses_cached_commit_and_preserves_interrupted_index_lock() {
        let fixture = Fixture::cached(false);
        assert!(!fixture.checkout.join(".git/index").exists());
        let original = fixture.checkout.join(".git/index.lock");
        fs::write(&original, b"").unwrap();
        fs::set_permissions(&original, fs::Permissions::from_mode(0o600)).unwrap();
        let original_identity = fs::metadata(&original).unwrap();
        fixture.resume().unwrap();
        let retained = fixture.progress.parent().unwrap().join("source-recovery/project-001-index.lock");
        assert_eq!(fs::read(&retained).unwrap(), b"");
        assert!(same_object(&original_identity, &fs::metadata(retained).unwrap()));
        assert_eq!(fs::read(fixture.destination.join("project/marker")).unwrap(), b"locked bytes\n");
        let records = fixture.records();
        assert!(records.iter().any(|row| row["state"] == "PROJECT_EXACT_COMMIT_LOCAL_CHECKOUT_STILL_REQUIRED"));
        assert!(!records.iter().any(|row| row["state"] == "PROJECT_FETCH_EXACT_COMMIT"));
    }

    #[test]
    fn nonempty_interrupted_index_lock_is_preserved_in_place_and_rejected() {
        let fixture = Fixture::cached(false);
        let path = fixture.checkout.join(".git/index.lock");
        fs::write(&path, b"unqualified partial index evidence").unwrap();
        let before = fs::metadata(&path).unwrap();
        assert!(fixture.resume().is_err());
        assert_eq!(fs::read(&path).unwrap(), b"unqualified partial index evidence");
        assert!(same_object(&before, &fs::metadata(&path).unwrap()));
        assert!(!fixture.destination.exists());
        assert!(!fixture.progress.parent().unwrap().join("source-recovery").exists());
        assert!(!fixture.records().iter().any(|row| row["state"] == "PROJECT_FETCH_EXACT_COMMIT"
            || row["state"] == "PROJECT_CHECKOUT_EXACT_COMMIT"));
    }

    #[test]
    fn dirty_completed_project_keeps_original_bytes_and_never_gets_manifest() {
        let fixture = Fixture::cached(true);
        fs::write(fixture.checkout.join("marker"), b"preserve this changed source\n").unwrap();
        assert!(fixture.resume().is_err());
        assert_eq!(fs::read(fixture.checkout.join("marker")).unwrap(), b"preserve this changed source\n");
        assert!(!fixture.destination.exists());
        assert!(!fixture.staging.join(".droidloom-source-manifest.json").exists());
        assert_eq!(fixture.records().last().unwrap()["state"], "SOURCE_MATERIALIZATION_FAILED");
        assert_eq!(fixture.records().last().unwrap()["detail"]["staging_metadata_after_failure"]["present"], true);
    }

    #[test]
    fn conflicting_untracked_partial_file_is_not_forced_or_removed() {
        let fixture = Fixture::cached(false);
        fs::write(fixture.checkout.join("marker"), b"preserve untracked conflict\n").unwrap();
        fs::write(fixture.checkout.join(".git/index.lock"), b"").unwrap();
        fs::set_permissions(fixture.checkout.join(".git/index.lock"), fs::Permissions::from_mode(0o600)).unwrap();
        assert!(fixture.resume().is_err());
        assert_eq!(fs::read(fixture.checkout.join("marker")).unwrap(), b"preserve untracked conflict\n");
        assert_eq!(fs::read(fixture.root.join("attempt/source-recovery/project-001-index.lock")).unwrap(),
            b"");
        assert!(!fixture.destination.exists());
        assert!(!fixture.staging.join(".droidloom-source-manifest.json").exists());
    }

    #[test]
    fn wrong_origin_is_rejected_before_any_fetch_or_checkout() {
        let fixture = Fixture::cached(false);
        local_git(&fixture.checkout, &arguments(&["remote", "set-url", "origin", "https://example.invalid/wrong"]));
        assert!(fixture.resume().is_err());
        let records = fixture.records();
        assert!(!records.iter().any(|row| row["state"] == "PROJECT_FETCH_EXACT_COMMIT"
            || row["state"] == "PROJECT_CHECKOUT_EXACT_COMMIT"));
        assert!(!fixture.destination.exists());
    }

    #[test]
    fn recovered_parent_symlink_cannot_create_a_project_outside_staging() {
        let mut fixture = Fixture::cached(true);
        let outside = fixture.root.join("outside-staging");
        fs::create_dir(&outside).unwrap();
        std::os::unix::fs::symlink(&outside, fixture.staging.join("alias")).unwrap();
        fixture.lock.projects[0].path = "alias/new-project".into();
        let mut lock_json: Value = serde_json::from_slice(&fs::read(&fixture.lock_path).unwrap()).unwrap();
        lock_json["projects"][0]["path"] = json!("alias/new-project");
        fs::write(&fixture.lock_path, serde_json::to_vec_pretty(&lock_json).unwrap()).unwrap();
        assert!(fixture.resume().is_err());
        assert!(!outside.join("new-project").exists());
        assert!(!fixture.destination.exists());
        assert!(!fixture.staging.join(".droidloom-source-manifest.json").exists());
    }

    #[test]
    fn mismatched_staging_manifest_is_preserved_and_not_published() {
        let fixture = Fixture::cached(true);
        let existing = fixture.staging.join(".droidloom-source-manifest.json");
        fs::write(&existing, b"original incomplete manifest evidence\n").unwrap();
        assert!(fixture.resume().is_err());
        assert_eq!(fs::read(existing).unwrap(), b"original incomplete manifest evidence\n");
        assert!(!fixture.destination.exists());
    }

    #[test]
    fn sparse_parent_normalization_keeps_exact_locked_selection() {
        let project = PlannedProject { path:"project".into(), url:"https://android.googlesource.com/platform/test".into(),
            commit:"1111111111111111111111111111111111111111".into(), purpose:"fixture".into(),
            sparse_paths:vec!["Android.bp".into(), "clang/lib/clang/22/include".into(),
                "clang/lib/clang/22/lib/linux".into(), "soong".into(), "clang".into()] };
        assert_eq!(expected_sparse(&project), [PathBuf::from("Android.bp"), PathBuf::from("clang"),
            PathBuf::from("soong")].into_iter().collect());
    }
}
