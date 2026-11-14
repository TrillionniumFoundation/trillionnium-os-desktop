//! Add package-owned leaf files without making Android partitions writable.
//!
//! Only parents which need a new leaf are projected. Original entries retain
//! their objects through read-only bind mounts, and symlinks retain their text
//! and ownership. The source directory stays open until every bind is complete.
use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fs::{self, OpenOptions};
use std::io;
use std::os::fd::AsRawFd;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt, lchown, symlink};
use std::path::{Component, Path, PathBuf};

use super::{DevelopmentError, create_mount_target, io_error, mount_tmpfs, run_os};
use crate::AndroidFileOverride;

#[derive(Debug)]
struct ParentPlan {
    parent: PathBuf,
    leaves: Vec<OsString>,
}

fn invalid(message: impl Into<String>) -> DevelopmentError {
    DevelopmentError::InvalidInput(message.into())
}

fn plan(
    root: &Path,
    overrides: &[AndroidFileOverride],
) -> Result<Vec<ParentPlan>, DevelopmentError> {
    let mut parents: BTreeMap<PathBuf, Vec<OsString>> = BTreeMap::new();
    for item in overrides {
        if !crate::is_android_file_override_target(&item.target)
            || item.target == Path::new("/system/bin/init")
        {
            return Err(invalid(format!(
                "invalid Android override target {}",
                item.target.display()
            )));
        }
        let relative = item
            .target
            .strip_prefix("/")
            .map_err(|_| invalid("absolute target required"))?;
        let target = root.join(relative);
        match fs::symlink_metadata(&target) {
            Ok(metadata) if metadata.is_file() => continue,
            Ok(_) => {
                return Err(invalid(format!(
                    "{} is not a regular Android partition file",
                    item.target.display()
                )));
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(io_error("inspect Android override target", error)),
        }
        // Do not create new directory hierarchies or follow an image symlink
        // into a different partition (or outside the cell before pivot_root).
        let mut parent = root.to_path_buf();
        for component in relative
            .parent()
            .ok_or_else(|| invalid("target has no parent"))?
            .components()
        {
            let Component::Normal(name) = component else {
                return Err(invalid("normalized Android override parent required"));
            };
            parent.push(name);
            let metadata = fs::symlink_metadata(&parent).map_err(|error| {
                io_error("new Android override requires an existing parent", error)
            })?;
            if !metadata.is_dir() {
                return Err(invalid(format!(
                    "Android override parent is not a real directory: {}",
                    parent.display()
                )));
            }
        }
        let leaf = relative
            .file_name()
            .ok_or_else(|| invalid("target has no filename"))?
            .to_owned();
        let leaves = parents.entry(parent).or_default();
        if leaves.contains(&leaf) {
            return Err(invalid("duplicate new Android override target"));
        }
        leaves.push(leaf);
    }
    let mut result: Vec<_> = parents
        .into_iter()
        .map(|(parent, leaves)| ParentPlan { parent, leaves })
        .collect();
    result.sort_by(|a, b| {
        a.parent
            .components()
            .count()
            .cmp(&b.parent.components().count())
            .then(a.parent.cmp(&b.parent))
    });
    Ok(result)
}

enum EntryKind {
    File,
    Directory,
    Symlink(PathBuf, u32, u32),
}

fn bind_original_entry(source: &Path, target: &Path) -> Result<(), DevelopmentError> {
    // mount(8)'s default canonicalization converts the held-FD path back into
    // the now-covered pathname. Keep the kernel's magic-link resolution so
    // the bind takes the original image object, not the new empty target.
    run_os(
        "mount",
        [
            OsString::from("--no-canonicalize"),
            OsString::from("--bind"),
            source.as_os_str().to_owned(),
            target.as_os_str().to_owned(),
        ],
    )?;
    run_os(
        "mount",
        [
            OsString::from("-o"),
            OsString::from("remount,bind,ro,nosuid,nodev"),
            target.as_os_str().to_owned(),
        ],
    )
}

fn project(parent: &Path, leaves: &[OsString]) -> Result<(), DevelopmentError> {
    let lower = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW)
        .open(parent)
        .map_err(|error| io_error("hold original Android override parent", error))?;
    let metadata = lower
        .metadata()
        .map_err(|error| io_error("stat original Android override parent", error))?;
    // Use this process's held descriptor: mount(8) does not inherit the
    // descriptor, and the pathname being projected is about to be hidden.
    let lower_path = PathBuf::from(format!(
        "/proc/{}/fd/{}",
        std::process::id(),
        lower.as_raw_fd()
    ));
    let mut entries = Vec::new();
    for entry in fs::read_dir(&lower_path)
        .map_err(|error| io_error("list original Android override parent", error))?
    {
        let entry = entry.map_err(|error| io_error("read Android override parent entry", error))?;
        let source = entry.path();
        let entry_metadata = fs::symlink_metadata(&source)
            .map_err(|error| io_error("stat Android override parent entry", error))?;
        let kind = if entry_metadata.is_file() {
            EntryKind::File
        } else if entry_metadata.is_dir() {
            EntryKind::Directory
        } else if entry_metadata.file_type().is_symlink() {
            EntryKind::Symlink(
                fs::read_link(&source)
                    .map_err(|error| io_error("read Android override symlink", error))?,
                entry_metadata.uid(),
                entry_metadata.gid(),
            )
        } else {
            return Err(invalid(format!(
                "unsupported entry in Android override parent: {}",
                source.display()
            )));
        };
        entries.push((entry.file_name(), source, kind));
    }
    entries.sort_by(|a, b| a.0.cmp(&b.0));
    // The partition is untouched. This new superblock lives in the already
    // private cell mount namespace and disappears when that namespace exits.
    mount_tmpfs(
        parent,
        &format!(
            "mode={:o},uid={},gid={},nosuid,nodev",
            metadata.mode() & 0o7777,
            metadata.uid(),
            metadata.gid()
        ),
    )?;
    for (name, source, kind) in entries {
        let destination = parent.join(name);
        match kind {
            EntryKind::Symlink(link, uid, gid) => {
                symlink(link, &destination).map_err(|error| {
                    io_error("recreate Android override sibling symlink", error)
                })?;
                lchown(&destination, Some(uid), Some(gid))
                    .map_err(|error| io_error("preserve Android override symlink owner", error))?;
            }
            EntryKind::Directory => {
                fs::create_dir(&destination).map_err(|error| {
                    io_error("create Android override sibling directory target", error)
                })?;
                bind_original_entry(&source, &destination)?;
            }
            EntryKind::File => {
                create_mount_target(&destination)?;
                bind_original_entry(&source, &destination)?;
            }
        }
    }
    for leaf in leaves {
        create_mount_target(&parent.join(leaf))?;
    }
    // Parent ownership/mode matters: the real Android /system/bin is 0:2000,
    // 0751. Seal the directory after creating only the declared new leaves.
    fs::set_permissions(parent, fs::Permissions::from_mode(metadata.mode() & 0o7777))
        .map_err(|error| io_error("preserve Android override parent mode", error))?;
    run_os(
        "mount",
        [
            OsString::from("-o"),
            OsString::from("remount,ro,nosuid,nodev"),
            parent.as_os_str().to_owned(),
        ],
    )?;
    Ok(())
}

pub(super) fn prepare_targets(
    root: &Path,
    overrides: &[AndroidFileOverride],
) -> Result<(), DevelopmentError> {
    for parent in plan(root, overrides)? {
        project(&parent.parent, &parent.leaves)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::super::bind_mount_read_only_executable;
    use super::*;
    fn item(target: &str) -> AndroidFileOverride {
        AndroidFileOverride {
            source: "/unused".into(),
            target: target.into(),
        }
    }
    #[test]
    fn existing_regular_targets_need_no_projection() {
        let temp = tempfile::tempdir().unwrap();
        fs::create_dir_all(temp.path().join("system/bin")).unwrap();
        let file = temp.path().join("system/bin/existing");
        fs::write(&file, b"original").unwrap();
        let before = fs::metadata(&file).unwrap().ino();
        assert!(
            plan(temp.path(), &[item("/system/bin/existing")])
                .unwrap()
                .is_empty()
        );
        assert_eq!(fs::metadata(&file).unwrap().ino(), before);
        assert_eq!(fs::read(file).unwrap(), b"original");
    }
    #[test]
    fn missing_leaves_are_grouped_without_modifying_the_image() {
        let temp = tempfile::tempdir().unwrap();
        fs::create_dir_all(temp.path().join("system/bin")).unwrap();
        fs::create_dir_all(temp.path().join("system/etc")).unwrap();
        let groups = plan(
            temp.path(),
            &[
                item("/system/bin/owner"),
                item("/system/bin/factory"),
                item("/system/etc/pair.json"),
            ],
        )
        .unwrap();
        assert_eq!(groups.len(), 2);
        assert_eq!(groups[0].leaves.len(), 2);
        assert_eq!(groups[1].leaves.len(), 1);
        assert!(!temp.path().join("system/bin/owner").exists());
        assert!(!temp.path().join("system/etc/pair.json").exists());
    }
    #[test]
    fn missing_directories_symlink_parents_and_nonfiles_are_rejected() {
        let temp = tempfile::tempdir().unwrap();
        fs::create_dir_all(temp.path().join("system/bin")).unwrap();
        assert!(plan(temp.path(), &[item("/system/missing/new")]).is_err());
        symlink("bin", temp.path().join("system/alias")).unwrap();
        assert!(plan(temp.path(), &[item("/system/alias/new")]).is_err());
        symlink("absent", temp.path().join("system/bin/link")).unwrap();
        assert!(plan(temp.path(), &[item("/system/bin/link")]).is_err());
        fs::create_dir(temp.path().join("system/bin/directory")).unwrap();
        assert!(plan(temp.path(), &[item("/system/bin/directory")]).is_err());
        assert!(plan(temp.path(), &[item("/system/bin/init")]).is_err());
        assert!(plan(temp.path(), &[item("/system/bin/../escape")]).is_err());
    }
    #[test]
    #[ignore = "requires root in a dedicated mount namespace; run the owned Pocket4 mount fixture"]
    fn private_projection_preserves_metadata_and_enforces_read_only_mounts() {
        assert_eq!(super::super::effective_uid().unwrap(), 0);
        let parent_ns =
            std::env::var("DROIDLOOM_OVERRIDE_PARENT_MNT_NS").expect("parent namespace identity");
        assert_ne!(
            fs::read_link("/proc/self/ns/mnt")
                .unwrap()
                .to_string_lossy(),
            parent_ns
        );
        super::super::make_mounts_private().unwrap();
        let fixture = PathBuf::from(
            std::env::var("DROIDLOOM_OVERRIDE_MOUNT_FIXTURE").expect("owned fixture path"),
        );
        assert!(fixture.is_absolute() && fixture.is_dir());
        let root = fixture.join("root");
        let bin = root.join("system/bin");
        let etc = root.join("system/etc");
        fs::create_dir_all(&bin).unwrap();
        fs::create_dir_all(&etc).unwrap();
        super::super::set_owner(&bin, 0, 2000).unwrap();
        fs::set_permissions(&bin, fs::Permissions::from_mode(0o751)).unwrap();
        fs::write(bin.join("unchanged"), b"original-image-content").unwrap();
        super::super::set_owner(&bin.join("unchanged"), 0, 2000).unwrap();
        fs::set_permissions(bin.join("unchanged"), fs::Permissions::from_mode(0o640)).unwrap();
        fs::write(bin.join("existing"), b"old").unwrap();
        symlink("existing", bin.join("alias")).unwrap();
        lchown(bin.join("alias"), Some(0), Some(2000)).unwrap();
        fs::create_dir(etc.join("policy")).unwrap();
        fs::write(etc.join("policy/item"), b"original-policy").unwrap();
        let before = fs::metadata(bin.join("unchanged")).unwrap();
        let original_bin = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY)
            .open(&bin)
            .unwrap();
        let original_path = PathBuf::from(format!(
            "/proc/{}/fd/{}",
            std::process::id(),
            original_bin.as_raw_fd()
        ));
        let payload = fixture.join("payload");
        fs::create_dir(&payload).unwrap();
        fs::copy("/usr/bin/true", payload.join("new-elf")).unwrap();
        fs::write(payload.join("replacement"), b"replacement").unwrap();
        fs::write(payload.join("pair.json"), b"{\"matched\":true}\n").unwrap();
        let overrides = vec![
            AndroidFileOverride {
                source: payload.join("new-elf"),
                target: "/system/bin/new-owner".into(),
            },
            AndroidFileOverride {
                source: payload.join("replacement"),
                target: "/system/bin/existing".into(),
            },
            AndroidFileOverride {
                source: payload.join("pair.json"),
                target: "/system/etc/new-pair.json".into(),
            },
        ];
        prepare_targets(&root, &overrides).unwrap();
        for override_file in &overrides {
            bind_mount_read_only_executable(
                &override_file.source,
                &root.join(override_file.target.strip_prefix("/").unwrap()),
            )
            .unwrap();
        }
        let after = fs::metadata(bin.join("unchanged")).unwrap();
        assert_eq!(
            (
                after.dev(),
                after.ino(),
                after.mode(),
                after.uid(),
                after.gid()
            ),
            (
                before.dev(),
                before.ino(),
                before.mode(),
                before.uid(),
                before.gid()
            )
        );
        let directory = fs::metadata(&bin).unwrap();
        assert_eq!(
            (directory.uid(), directory.gid(), directory.mode() & 0o7777),
            (0, 2000, 0o751)
        );
        let link = fs::symlink_metadata(bin.join("alias")).unwrap();
        assert_eq!((link.uid(), link.gid()), (0, 2000));
        assert_eq!(
            fs::read_link(bin.join("alias")).unwrap(),
            Path::new("existing")
        );
        assert_eq!(fs::read(bin.join("alias")).unwrap(), b"replacement");
        assert_eq!(fs::read(original_path.join("existing")).unwrap(), b"old");
        assert!(!original_path.join("new-owner").exists());
        assert_eq!(
            fs::read(etc.join("policy/item")).unwrap(),
            b"original-policy"
        );
        assert!(
            std::process::Command::new(bin.join("new-owner"))
                .status()
                .unwrap()
                .success()
        );
        for path in [
            bin.join("unchanged"),
            bin.join("existing"),
            bin.join("new-owner"),
            etc.join("policy/item"),
            etc.join("new-pair.json"),
            bin.join("undeclared"),
        ] {
            assert_eq!(
                OpenOptions::new()
                    .write(true)
                    .create(true)
                    .open(path)
                    .unwrap_err()
                    .raw_os_error(),
                Some(libc::EROFS)
            );
        }
        // Namespace teardown releases these mounts. The outer test owner then
        // verifies that no new leaves or replacements reached the original tree.
    }
}
