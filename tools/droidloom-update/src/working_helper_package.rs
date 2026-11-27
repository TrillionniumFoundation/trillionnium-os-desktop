//! Package the three fixed working helpers from this checkout's declared Cargo
//! targets. Stale files left by an older target list cannot satisfy the build.
use crate::util::*;
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Seek, SeekFrom, Write},
    os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
    path::{Path, PathBuf},
    process::Command,
};

const MAX_BYTES: u64 = 32 * 1024 * 1024;
const MEMBERS: [(&str, &str); 3] = [
    (
        "droidloom-working-namespace-entry",
        "usr/lib/droidloom/qualification/working-namespace-entry",
    ),
    (
        "droidloom-working-owned-files",
        "usr/lib/droidloom/qualification/working-owned-files",
    ),
    (
        "droidloom-working-retained-data",
        "usr/lib/droidloom/qualification/working-retained-data",
    ),
];

pub(super) fn build(repo: &Path, target: &Path, jobs: usize) -> Result<()> {
    let mut command = Command::new("cargo");
    command
        .current_dir(repo)
        .env("CARGO_TARGET_DIR", target)
        .args(["build", "--locked", "--release", "--jobs"])
        .arg(jobs.to_string())
        .args(["-p", "droidloom-supervisor"]);
    for (binary, _) in MEMBERS {
        command.arg("--bin").arg(binary);
    }
    run_build(&mut command)
}

#[derive(Debug, PartialEq, Eq)]
struct Node(u64, u64, u32, u32, u32, u64, u64, i64, i64, i64, i64);
fn node(metadata: &fs::Metadata) -> Node {
    Node(
        metadata.dev(),
        metadata.ino(),
        metadata.mode(),
        metadata.uid(),
        metadata.gid(),
        metadata.nlink(),
        metadata.len(),
        metadata.mtime(),
        metadata.mtime_nsec(),
        metadata.ctime(),
        metadata.ctime_nsec(),
    )
}

struct HeldBuildFile {
    path: PathBuf,
    file: File,
    identity: Node,
    bytes: Vec<u8>,
}
impl HeldBuildFile {
    fn capture(path: PathBuf) -> Result<Self> {
        let named = fs::symlink_metadata(&path)?;
        if !named.is_file()
            || named.mode() & 0o177777 != 0o100755
            || !(1024..MAX_BYTES).contains(&named.len())
        {
            return fail("working helper is not a bounded ordinary executable build output");
        }
        let mut file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&path)?;
        let identity = node(&named);
        if node(&file.metadata()?) != identity {
            return fail("working helper named and opened build identities differ");
        }
        let mut bytes = Vec::new();
        Read::by_ref(&mut file)
            .take(MAX_BYTES)
            .read_to_end(&mut bytes)?;
        let result = Self {
            path,
            file,
            identity,
            bytes,
        };
        result.revalidate()?;
        if result.bytes.len() as u64 != named.len() {
            return fail("working helper complete build bytes changed while reading");
        }
        Ok(result)
    }

    fn revalidate(&self) -> Result<()> {
        if node(&self.file.metadata()?) != self.identity
            || node(&fs::symlink_metadata(&self.path)?) != self.identity
        {
            return fail("working helper left its held complete build identity");
        }
        Ok(())
    }
}

pub(super) fn stage(host: &Path, runtime: &Path) -> Result<()> {
    // Cargo's release aliases may be hard links. Retain those actual source
    // inodes, but publish new independent ordinary files in the private stage.
    let held = MEMBERS
        .iter()
        .map(|(binary, relative)| Ok((HeldBuildFile::capture(host.join(binary))?, *relative)))
        .collect::<Result<Vec<_>>>()?;
    for (source, relative) in &held {
        source.revalidate()?;
        let target = runtime.join(relative);
        let parent = target
            .parent()
            .ok_or("working helper target lacks parent")?;
        fs::create_dir_all(parent)?;
        let mut output = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .mode(0o755)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&target)?;
        output.write_all(&source.bytes)?;
        output.set_permissions(fs::Permissions::from_mode(0o755))?;
        output.sync_all()?;
        let before = output.metadata()?;
        if before.mode() != 0o100755
            || before.nlink() != 1
            || before.len() != source.bytes.len() as u64
        {
            return fail("working helper stage did not retain its complete independent file");
        }
        output.seek(SeekFrom::Start(0))?;
        let mut actual = Vec::new();
        Read::by_ref(&mut output)
            .take(MAX_BYTES)
            .read_to_end(&mut actual)?;
        if actual != source.bytes
            || node(&output.metadata()?) != node(&before)
            || node(&fs::symlink_metadata(&target)?) != node(&before)
        {
            return fail("working helper staged bytes or named identity changed");
        }
        source.revalidate()?;
        File::open(parent)?.sync_all()?;
    }
    for (source, _) in &held {
        source.revalidate()?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture(path: &Path, byte: u8) {
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, vec![byte; 2048]).unwrap();
        fs::set_permissions(path, fs::Permissions::from_mode(0o755)).unwrap();
    }

    #[test]
    fn normal_working_helpers_require_all_three_current_build_outputs() {
        let root = tempfile::tempdir().unwrap();
        let host = root.path().join("release");
        let runtime = root.path().join("stage");
        fixture(&host.join(MEMBERS[0].0), 1);
        assert!(stage(&host, &runtime).is_err());
        assert!(!runtime.exists());
        fixture(&host.join(MEMBERS[1].0), 2);
        assert!(stage(&host, &runtime).is_err());
        assert!(!runtime.exists());
        fixture(&host.join(MEMBERS[2].0), 3);
        stage(&host, &runtime).unwrap();
        for (binary, relative) in MEMBERS {
            let source = host.join(binary);
            let target = runtime.join(relative);
            let metadata = fs::symlink_metadata(&target).unwrap();
            assert_eq!(metadata.mode(), 0o100755);
            assert_eq!(metadata.nlink(), 1);
            assert_ne!(metadata.ino(), fs::metadata(&source).unwrap().ino());
            assert_eq!(fs::read(target).unwrap(), fs::read(source).unwrap());
        }
        let first = runtime.join(MEMBERS[0].1);
        fs::write(&first, b"existing member must remain intact").unwrap();
        assert!(stage(&host, &runtime).is_err());
        assert_eq!(
            fs::read(first).unwrap(),
            b"existing member must remain intact"
        );
    }

    #[test]
    fn normal_working_helpers_reject_aliases_modes_and_short_members() {
        let root = tempfile::tempdir().unwrap();
        let source = root.path().join("actual");
        let alias = root.path().join("alias");
        fixture(&source, 1);
        std::os::unix::fs::symlink(&source, &alias).unwrap();
        assert!(HeldBuildFile::capture(alias).is_err());
        for mode in [0o644, 0o777, 0o4755] {
            fs::set_permissions(&source, fs::Permissions::from_mode(mode)).unwrap();
            assert!(HeldBuildFile::capture(source.clone()).is_err());
        }
        fs::set_permissions(&source, fs::Permissions::from_mode(0o755)).unwrap();
        fs::write(&source, b"not a complete helper").unwrap();
        assert!(HeldBuildFile::capture(source).is_err());
    }

    #[test]
    fn normal_working_helpers_reject_real_held_source_changes() {
        let root = tempfile::tempdir().unwrap();
        let source = root.path().join("member");
        fixture(&source, 1);
        let held = HeldBuildFile::capture(source.clone()).unwrap();
        fs::write(&source, vec![2; 2048]).unwrap();
        assert!(held.revalidate().is_err());
        let held = HeldBuildFile::capture(source.clone()).unwrap();
        fs::rename(&source, root.path().join("old")).unwrap();
        fixture(&source, 2);
        assert!(held.revalidate().is_err());
    }
}
