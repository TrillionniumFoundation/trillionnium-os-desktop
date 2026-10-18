//! User-opt-in local plain-text draft snapshot, never a Hepta task ledger.
//! A security namespace, encryption or file-portal authority is NOT provided.
use serde::{Deserialize, Serialize};
use std::fs::{self, DirBuilder, File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use trill_ui_core::conversation::{LocalDraft, MAX_LOCAL_DRAFTS};
use trill_ui_core::Workspace;

const VERSION: u32 = 1;
const MAX_ENTRIES: usize = 127;
const MAX_ENTRY_BYTES: usize = 16 * 1024;
const MAX_FILE_BYTES: u64 = 4 * 1024 * 1024;
const FILE_NAME: &str = "local-drafts-v1.json";
const CONTEXT_FILE_NAME: &str = "local-context-drafts-v2.json";
// Linux O_NOFOLLOW ensures a raced file-to-symlink replacement is refused
// by the kernel during open, not merely by an earlier path metadata check.
#[cfg(target_os = "linux")]
const LINUX_O_NOFOLLOW: i32 = 0o400000;
// Open must reach the descriptor type check even for an unexpected FIFO
// with no writer. O_NONBLOCK has no effect on ordinary regular-file reads.
#[cfg(target_os = "linux")]
const LINUX_O_NONBLOCK: i32 = 0o4000;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Snapshot {
    version: u32,
    drafts: Vec<String>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ContextSnapshot {
    version: u32,
    drafts: Vec<LocalDraft>,
}

fn validate_context(drafts: &[LocalDraft]) -> io::Result<()> {
    if drafts.is_empty() || drafts.len() > MAX_LOCAL_DRAFTS {
        return Err(invalid("Invalid local context draft count"));
    }
    for draft in drafts {
        draft.validate().map_err(invalid)?;
    }
    Ok(())
}

pub fn save_context_at(dir: &Path, drafts: &[LocalDraft]) -> io::Result<PathBuf> {
    validate_context(drafts)?;
    let payload = serde_json::to_vec(&ContextSnapshot {
        version: 2,
        drafts: drafts.to_vec(),
    })
    .map_err(io::Error::other)?;
    save_payload(dir, CONTEXT_FILE_NAME, &payload)
}

/// Prefer v2. Fall back to legacy text only when the v2 file is absent, never
/// when v2 is corrupt/insecure. Legacy had no workspace or source references;
/// explicit import assigns its text to the currently chosen workspace.
pub fn load_context_at(dir: &Path, legacy_workspace: Workspace) -> io::Result<Vec<LocalDraft>> {
    let bytes = match load_payload(dir, CONTEXT_FILE_NAME) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            return load_at(dir).map(|drafts| {
                drafts
                    .into_iter()
                    .map(|text| LocalDraft {
                        workspace: legacy_workspace,
                        text,
                        contexts: Vec::new(),
                    })
                    .collect()
            });
        }
        Err(error) => return Err(error),
    };
    let snapshot: ContextSnapshot = serde_json::from_slice(&bytes).map_err(io::Error::other)?;
    if snapshot.version != 2 {
        return Err(invalid("Unsupported local context draft schema"));
    }
    validate_context(&snapshot.drafts)?;
    Ok(snapshot.drafts)
}

fn invalid(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

fn validate(drafts: &[String]) -> io::Result<()> {
    if drafts.is_empty() {
        return Err(invalid(
            "Refusing to replace local export with an empty snapshot",
        ));
    }
    if drafts.len() > MAX_ENTRIES {
        return Err(invalid("Too many drafts in snapshot"));
    }
    if drafts
        .iter()
        .any(|s| s.len() > MAX_ENTRY_BYTES || s.trim().is_empty())
    {
        return Err(invalid("Draft exceeds 16 KiB or is empty"));
    }
    Ok(())
}

pub fn state_dir() -> io::Result<PathBuf> {
    let root = match std::env::var_os("XDG_STATE_HOME") {
        Some(value) => PathBuf::from(value),
        None => {
            let home = std::env::var_os("HOME")
                .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "HOME is not configured"))?;
            PathBuf::from(home).join(".local").join("state")
        }
    };
    if !root.is_absolute() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "XDG_STATE_HOME must be absolute",
        ));
    }
    Ok(root.join("trillionnium-ui"))
}

fn ensure_private_dir(dir: &Path) -> io::Result<()> {
    let mut builder = DirBuilder::new();
    builder.recursive(true).mode(0o700);
    builder.create(dir)?;
    let meta = fs::symlink_metadata(dir)?;
    if !meta.is_dir() || meta.permissions().mode() & 0o777 != 0o700 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "Draft directory must be real and 0700",
        ));
    }
    Ok(())
}

#[cfg(test)]
fn save_at(dir: &Path, drafts: &[String]) -> io::Result<PathBuf> {
    validate(drafts)?;
    let payload = serde_json::to_vec(&Snapshot {
        version: VERSION,
        drafts: drafts.to_vec(),
    })
    .map_err(io::Error::other)?;
    save_payload(dir, FILE_NAME, &payload)
}

fn save_payload(dir: &Path, name: &str, payload: &[u8]) -> io::Result<PathBuf> {
    if payload.len() as u64 > MAX_FILE_BYTES {
        return Err(invalid("Draft snapshot exceeds 4 MiB"));
    }
    ensure_private_dir(dir)?;
    let target = dir.join(name);
    match fs::symlink_metadata(&target) {
        Ok(meta) => {
            // Do not silently replace an existing backup whose visibility
            // has changed. Explicitly reject directory, symlink and 0644.
            if !meta.file_type().is_file() || meta.permissions().mode() & 0o777 != 0o600 {
                return Err(io::Error::new(
                    io::ErrorKind::PermissionDenied,
                    "Existing draft snapshot must be a private 0600 regular file",
                ));
            }
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(error) => return Err(error), // e.g. EACCES is NOT "not found"
    }

    // Same-directory create-new + rename avoids an in-place partial export.
    // We never follow a preexisting target symlink.
    for attempt in 0..16u8 {
        let temp = dir.join(format!(
            ".local-drafts-{}-{}-{attempt}.tmp",
            std::process::id(),
            trill_ui_core::unix_ms()
        ));
        let opened = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&temp);
        let mut file = match opened {
            Ok(file) => file,
            Err(ref error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        };
        let result = (|| -> io::Result<()> {
            file.write_all(payload)?;
            file.sync_all()?;
            fs::rename(&temp, &target)?;
            // The rename is atomic, but without fsync on the containing
            // directory a power loss can still lose its directory entry.
            // An fsync error means durability is UNKNOWN, not a success.
            File::open(dir)?.sync_all().map_err(|error| {
                io::Error::new(
                    error.kind(),
                    format!("Draft file replaced but directory durability unconfirmed: {error}"),
                )
            })?;
            Ok(())
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temp);
        }
        result?;
        return Ok(target);
    }
    Err(io::Error::new(
        io::ErrorKind::AlreadyExists,
        "No unique temp snapshot name",
    ))
}

pub fn load_at(dir: &Path) -> io::Result<Vec<String>> {
    let bytes = load_payload(dir, FILE_NAME)?;
    let snapshot: Snapshot = serde_json::from_slice(&bytes).map_err(io::Error::other)?;
    if snapshot.version != VERSION {
        return Err(invalid("Unsupported local draft snapshot schema"));
    }
    validate(&snapshot.drafts)?;
    Ok(snapshot.drafts)
}

fn load_payload(dir: &Path, name: &str) -> io::Result<Vec<u8>> {
    // Loading never creates or modifies directories; user must first export.
    let dir_meta = fs::symlink_metadata(dir)?;
    if !dir_meta.file_type().is_dir() || dir_meta.permissions().mode() & 0o777 != 0o700 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "Draft directory is not private",
        ));
    }
    let target = dir.join(name);
    // Open without following any final-component symlink; check the *opened
    // file's* metadata rather than trusting a potentially stale path stat.
    // No guarantee is made against a malicious other process under the same
    // host UID, but this prevents an ordinary symlink replacement race.
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(target_os = "linux")]
    {
        options.custom_flags(LINUX_O_NOFOLLOW | LINUX_O_NONBLOCK);
    }
    #[cfg(not(target_os = "linux"))]
    {
        return Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "Linux host-only snapshot import",
        ));
    }
    let opened = options.open(&target)?;
    let meta = opened.metadata()?;
    if !meta.file_type().is_file() || meta.permissions().mode() & 0o777 != 0o600 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "Draft snapshot must be 0600 regular file",
        ));
    }
    if meta.len() > MAX_FILE_BYTES {
        return Err(invalid("Draft snapshot is oversized"));
    }
    let mut bytes = Vec::new();
    opened.take(MAX_FILE_BYTES + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_FILE_BYTES {
        return Err(invalid("Draft snapshot grew too large while reading"));
    }
    Ok(bytes)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;

    struct Fixture(PathBuf);
    impl Fixture {
        fn new(label: &str) -> Self {
            for counter in 0..32u8 {
                let dir = std::env::temp_dir().join(format!(
                    "trill-drafts-{label}-{}-{}-{counter}",
                    std::process::id(),
                    trill_ui_core::unix_ms(),
                ));
                match fs::create_dir(&dir) {
                    Ok(()) => {
                        fs::set_permissions(&dir, fs::Permissions::from_mode(0o700)).unwrap();
                        return Self(dir);
                    }
                    Err(ref e) if e.kind() == io::ErrorKind::AlreadyExists => continue,
                    Err(e) => panic!("cannot create fixture: {e}"),
                }
            }
            panic!("cannot create unique fixture");
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn explicit_unicode_roundtrip_and_replacement_is_atomic() {
        let fixture = Fixture::new("roundtrip");
        let dir = fixture.0.join("private");
        let original = vec!["你好 📝".to_owned(), "draft two".to_owned()];
        let path = save_at(&dir, &original).unwrap();
        assert_eq!(
            fs::symlink_metadata(&dir).unwrap().permissions().mode() & 0o777,
            0o700
        );
        assert_eq!(
            fs::symlink_metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );
        assert_eq!(load_at(&dir).unwrap(), original);
        let updated = vec!["updated 中文".to_owned()];
        save_at(&dir, &updated).unwrap();
        assert_eq!(load_at(&dir).unwrap(), updated);
        let hidden_temps: Vec<_> = fs::read_dir(&dir)
            .unwrap()
            .filter_map(Result::ok)
            .filter(|entry| entry.file_name().to_string_lossy().ends_with(".tmp"))
            .collect();
        assert!(
            hidden_temps.is_empty(),
            "successful export left uncommitted temporary files"
        );
    }

    #[test]
    fn reject_oversized_or_malformed_data_without_replacing_existing_export() {
        let fixture = Fixture::new("size");
        let dir = fixture.0.join("private");
        let known = vec!["keep this".to_owned()];
        save_at(&dir, &known).unwrap();
        let too_large = vec!["中".repeat(MAX_ENTRY_BYTES / 3 + 1)];
        assert!(save_at(&dir, &too_large).is_err());
        assert!(
            save_at(&dir, &[]).is_err(),
            "empty export must not delete older saved drafts"
        );
        assert_eq!(load_at(&dir).unwrap(), known);
        fs::write(dir.join(FILE_NAME), b"{\"version\":2,\"drafts\":[\"old\"]}").unwrap();
        assert!(load_at(&dir).is_err());
    }

    #[test]
    fn private_store_rejects_symlinks_and_insecure_permissions() {
        let fixture = Fixture::new("symlinks");
        let dir = fixture.0.join("private");
        fs::create_dir(&dir).unwrap();
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o755)).unwrap();
        assert!(save_at(&dir, &["safe".into()]).is_err());
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o700)).unwrap();
        let target = dir.join(FILE_NAME);
        symlink(fixture.0.join("elsewhere"), &target).unwrap();
        assert!(save_at(&dir, &["safe".into()]).is_err());
        assert!(load_at(&dir).is_err());
    }

    #[test]
    fn export_rejects_existing_public_file_without_changing_its_bytes() {
        let fixture = Fixture::new("public-backup");
        let dir = fixture.0.join("private");
        let path = save_at(&dir, &["previous safe draft".to_owned()]).unwrap();
        let original = fs::read(&path).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        let attempt = save_at(&dir, &["new private draft".into()]);
        assert_eq!(attempt.unwrap_err().kind(), io::ErrorKind::PermissionDenied);
        assert_eq!(fs::read(&path).unwrap(), original);
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        assert_eq!(load_at(&dir).unwrap(), vec!["previous safe draft"]);
    }

    #[test]
    fn load_rejects_public_mode_and_truncated_json() {
        let fixture = Fixture::new("bad-mode");
        let dir = fixture.0.join("private");
        let path = save_at(&dir, &["keep 中文".to_owned()]).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        assert!(
            load_at(&dir).is_err(),
            "world-readable draft must not be imported"
        );
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        fs::write(&path, b"{\"version\":1,\"drafts\":[").unwrap();
        assert!(
            load_at(&dir).is_err(),
            "truncated JSON cannot be a successful restore"
        );
    }

    #[test]
    fn rejects_more_than_ui_capacity() {
        let fixture = Fixture::new("capacity");
        let drafts = vec!["ok".into(); MAX_ENTRIES + 1];
        assert!(save_at(&fixture.0, &drafts).is_err());
    }

    #[test]
    fn context_export_roundtrip_preserves_workspace_and_reference_without_live_status() {
        use trill_ui_core::conversation::ContextRef;
        use trill_ui_core::{AppKind, TaskRecord};
        let fixture = Fixture::new("context-v2");
        let task = TaskRecord::new(42, Workspace::Research, AppKind::Notes);
        let draft = LocalDraft {
            workspace: Workspace::Research,
            text: "保留这个引用 📝".into(),
            contexts: vec![ContextRef::host_task(
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                &task,
                20_000,
            )],
        };
        let path = save_context_at(&fixture.0, &[draft.clone()]).unwrap();
        assert_eq!(path.file_name().unwrap(), CONTEXT_FILE_NAME);
        assert_eq!(
            load_context_at(&fixture.0, Workspace::Build).unwrap(),
            vec![draft]
        );
        let json: serde_json::Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        assert!(json["drafts"][0].get("current").is_none());
        assert_eq!(
            fs::metadata(path).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }

    #[test]
    fn legacy_import_is_explicitly_rehomed_and_corrupt_v2_never_falls_back() {
        let fixture = Fixture::new("legacy-v2");
        save_at(&fixture.0, &["legacy 中文".into()]).unwrap();
        let imported = load_context_at(&fixture.0, Workspace::Build).unwrap();
        assert_eq!(imported[0].workspace, Workspace::Build);
        assert!(imported[0].contexts.is_empty());
        let path = save_context_at(&fixture.0, &imported).unwrap();
        fs::write(&path, b"{\"version\":2,\"drafts\":[").unwrap();
        assert!(load_context_at(&fixture.0, Workspace::Personal).is_err());
        fs::remove_file(path).unwrap();
        symlink(
            fixture.0.join("not-present"),
            fixture.0.join(CONTEXT_FILE_NAME),
        )
        .unwrap();
        assert!(load_context_at(&fixture.0, Workspace::Personal).is_err());
    }
}
