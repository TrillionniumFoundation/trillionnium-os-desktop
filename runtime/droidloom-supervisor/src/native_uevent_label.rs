//! Fixed coldplug preparation for the original native sysfs instance.
//!
//! Only the separately labelled executable can enter this zero-capability
//! operation. The six derived labels preserve the original Android access
//! matrix; native udev obtains event-trigger writes without generic sysfs writes.

use crate::native_hardware_label as held;
use serde::Deserialize;
use std::collections::BTreeSet;
use std::ffi::{CStr, CString, OsString};
use std::fs::File;
use std::io;
use std::os::fd::AsRawFd;

const ENTRY: &str = "__native-uevent-label";
const ROLE: &[u8] = b"u:system_r:p4_linux_uevent_label_t:s0";
const PROFILE: &[u8] = b"droidloom-native-uevent-label (enforce)";
const SELINUX: u64 = 101;
const APPARMOR: u64 = 104;
const MAX_DEPTH: usize = 64;
const MAX_DIRECTORIES: usize = 100_000;
const MAX_ENTRIES: usize = 1_000_000;
const MAX_EVENTS: usize = 16_384;
const MAP: &[u8] = include_bytes!(
    "../../../android/framework/droidloom-readiness/board-policy/native-uevent-labels.json"
);

fn reject(reason: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, reason)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct LabelMap {
    schema: String,
    labels: Vec<LabelPair>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct LabelPair {
    source: String,
    target: String,
}

fn labels() -> io::Result<Vec<(Vec<u8>, Vec<u8>)>> {
    let map: LabelMap = serde_json::from_slice(MAP).map_err(io::Error::other)?;
    if map.schema != "droidloom.native-uevent-label-map.v1" || map.labels.len() != 6 {
        return Err(reject("the compiled native uevent map differs"));
    }
    let mut names = BTreeSet::new();
    let mut result = Vec::new();
    for row in map.labels {
        if !row.source.starts_with("sysfs")
            || !row
                .source
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b == b'_')
            || row.target != format!("p4_native_uevent_{}", row.source)
            || !names.insert(row.source.clone())
        {
            return Err(reject("the compiled native uevent map is not one-to-one"));
        }
        result.push((
            format!("u:object_r:{}:s0", row.source).into_bytes(),
            format!("u:object_r:{}:s0", row.target).into_bytes(),
        ));
    }
    Ok(result)
}

#[derive(Default, Debug)]
struct Counts {
    directories: usize,
    entries: usize,
    events: usize,
    changed: usize,
    disappeared: usize,
}

fn gone(error: &io::Error) -> bool {
    matches!(
        error.raw_os_error(),
        Some(libc::ENOENT | libc::ENODEV | libc::ESTALE)
    )
}

fn same_directory_identity(a: &libc::stat, b: &libc::stat) -> bool {
    a.st_dev == b.st_dev
        && a.st_ino == b.st_ino
        && a.st_mode == b.st_mode
        && a.st_uid == b.st_uid
        && a.st_gid == b.st_gid
        && a.st_rdev == b.st_rdev
}

fn same_identity(a: &libc::stat, b: &libc::stat) -> bool {
    same_directory_identity(a, b) && a.st_nlink == b.st_nlink
}

fn same_sysfs(file: &File, device: libc::dev_t, mount: u64) -> io::Result<libc::stat> {
    let identity = held::metadata(file)?;
    let (actual_mount, flags, fs) = held::mount_identity(file)?;
    if identity.st_dev != device || actual_mount != mount || fs != b"sysfs" || flags & 1 != 0 {
        return Err(reject(
            "coldplug preparation crossed the original writable sysfs mount",
        ));
    }
    Ok(identity)
}

struct Directory(*mut libc::DIR);

impl Drop for Directory {
    fn drop(&mut self) {
        unsafe {
            libc::closedir(self.0);
        }
    }
}

impl Directory {
    fn new(file: &File) -> io::Result<Self> {
        let fd = unsafe {
            libc::openat(
                file.as_raw_fd(),
                c".".as_ptr(),
                libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            )
        };
        if fd < 0 {
            return Err(io::Error::last_os_error());
        }
        let stream = unsafe { libc::fdopendir(fd) };
        if stream.is_null() {
            let error = io::Error::last_os_error();
            unsafe {
                libc::close(fd);
            }
            return Err(error);
        }
        Ok(Self(stream))
    }

    fn next(&mut self) -> io::Result<Option<(CString, u8)>> {
        unsafe {
            *libc::__errno_location() = 0;
        }
        let entry = unsafe { libc::readdir(self.0) };
        if entry.is_null() {
            let error = unsafe { *libc::__errno_location() };
            return if error == 0 {
                Ok(None)
            } else {
                Err(io::Error::from_raw_os_error(error))
            };
        }
        let name = unsafe { CStr::from_ptr((*entry).d_name.as_ptr()) }.to_owned();
        if name.as_bytes().is_empty() || name.as_bytes().contains(&b'/') {
            return Err(reject("sysfs supplied a non-component directory entry"));
        }
        Ok(Some((name, unsafe { (*entry).d_type })))
    }
}

fn event_identity(file: &File, device: libc::dev_t, mount: u64) -> io::Result<libc::stat> {
    let st = same_sysfs(file, device, mount)?;
    if st.st_mode & libc::S_IFMT != libc::S_IFREG
        || ![0o200, 0o644].contains(&(st.st_mode & 0o7777))
        || st.st_uid != 0
        || st.st_gid != 0
        || st.st_nlink != 1
    {
        return Err(reject(
            "a native uevent inode is not the original root-owned kernel attribute",
        ));
    }
    Ok(st)
}

fn visit(
    parent: &File,
    file: &File,
    device: libc::dev_t,
    mount: u64,
    mapping: &[(Vec<u8>, Vec<u8>)],
) -> io::Result<bool> {
    let before = event_identity(file, device, mount)?;
    let named = held::path_at(parent.as_raw_fd(), c"uevent")?;
    if !same_identity(&before, &event_identity(&named, device, mount)?) {
        return Err(reject(
            "the uevent name no longer identifies the held inode",
        ));
    }
    let original = held::label(file)?;
    let target = mapping
        .iter()
        .find(|(source, target)| original == *source || original == *target)
        .map(|(_, target)| target)
        .ok_or_else(|| reject("the actual uevent source label is not in the compiled map"))?;
    let changed = original != *target;
    if changed {
        held::replace_label(file, &original, target)?;
    }
    if held::label(file)? != *target
        || !same_identity(&before, &event_identity(file, device, mount)?)
        || !same_identity(&before, &event_identity(&named, device, mount)?)
    {
        return Err(reject(
            "the held uevent inode changed during its fixed label operation",
        ));
    }
    let current = held::path_at(parent.as_raw_fd(), c"uevent")?;
    if !same_identity(&before, &event_identity(&current, device, mount)?) {
        return Err(reject(
            "the published uevent name changed during preparation",
        ));
    }
    Ok(changed)
}

fn walk<F>(
    directory: &File,
    device: libc::dev_t,
    mount: u64,
    depth: usize,
    counts: &mut Counts,
    action: &mut F,
) -> io::Result<()>
where
    F: FnMut(&File, &File, libc::dev_t, u64) -> io::Result<bool>,
{
    if depth > MAX_DEPTH || counts.directories >= MAX_DIRECTORIES {
        return Err(reject(
            "native sysfs traversal exceeds its fixed directory bound",
        ));
    }
    let before = held::directory(directory)?;
    same_sysfs(directory, device, mount)?;
    counts.directories += 1;
    let mut entries = Directory::new(directory)?;
    while let Some((name, kind)) = entries.next()? {
        if [b".".as_slice(), b".."].contains(&name.as_bytes()) {
            continue;
        }
        counts.entries += 1;
        if counts.entries > MAX_ENTRIES {
            return Err(reject(
                "native sysfs traversal exceeds its fixed entry bound",
            ));
        }
        let is_event = name.as_bytes() == b"uevent";
        if !is_event && kind != libc::DT_DIR && kind != libc::DT_UNKNOWN {
            continue;
        }
        let child = match held::path_at(directory.as_raw_fd(), &name) {
            Ok(file) => file,
            Err(error) if gone(&error) => {
                counts.disappeared += 1;
                continue;
            }
            Err(error) => return Err(error),
        };
        let state = held::metadata(&child)?;
        if is_event {
            // Never follow a link or accept a directory merely named uevent.
            event_identity(&child, device, mount)?;
            counts.events += 1;
            if counts.events > MAX_EVENTS {
                return Err(reject("native uevent set exceeds its fixed inode bound"));
            }
            match action(directory, &child, device, mount) {
                Ok(changed) => counts.changed += usize::from(changed),
                Err(error) if gone(&error) => counts.disappeared += 1,
                Err(error) => return Err(error),
            }
        } else if state.st_mode & libc::S_IFMT == libc::S_IFDIR {
            match walk(&child, device, mount, depth + 1, counts, action) {
                Ok(()) => {}
                Err(error) if gone(&error) => counts.disappeared += 1,
                Err(error) => return Err(error),
            }
        }
    }
    if !same_directory_identity(&before, &held::directory(directory)?) {
        return Err(reject(
            "native sysfs directory identity changed during traversal",
        ));
    }
    same_sysfs(directory, device, mount)?;
    Ok(())
}

fn sysfs_root(root: &File) -> io::Result<(File, libc::dev_t, u64)> {
    let sys = held::path_at(root.as_raw_fd(), c"sys")?;
    let state = held::directory(&sys)?;
    let (mount, flags, fs) = held::mount_identity(&sys)?;
    if state.st_ino != 1 || fs != b"sysfs" || flags & 1 != 0 {
        return Err(reject(
            "coldplug preparation requires the original writable sysfs root",
        ));
    }
    Ok((sys, state.st_dev, mount))
}

fn scan<F>(root: &File, action: &mut F) -> io::Result<Counts>
where
    F: FnMut(&File, &File, libc::dev_t, u64) -> io::Result<bool>,
{
    let (sys, device, mount) = sysfs_root(root)?;
    let mut counts = Counts::default();
    for (name, optional) in [
        (c"devices", false),
        (c"bus", false),
        (c"class", false),
        (c"module", false),
        (c"subsystem", true),
    ] {
        let directory = match held::path_at(sys.as_raw_fd(), name) {
            Ok(file) => file,
            Err(error) if optional && error.raw_os_error() == Some(libc::ENOENT) => continue,
            Err(error) => return Err(error),
        };
        walk(&directory, device, mount, 0, &mut counts, action)?;
    }
    if counts.events == 0 {
        return Err(reject("the original sysfs has no native uevent attributes"));
    }
    let (after, actual_device, actual_mount) = sysfs_root(root)?;
    if actual_device != device
        || actual_mount != mount
        || !same_directory_identity(&held::metadata(&sys)?, &held::metadata(&after)?)
    {
        return Err(reject(
            "the original sysfs root changed during coldplug preparation",
        ));
    }
    Ok(counts)
}

/// Dispatch before normal daemon options. No caller supplies a path or label.
pub fn dispatch(arguments: &[OsString]) -> io::Result<bool> {
    let requested = arguments.first().is_some_and(|v| v == ENTRY);
    let role = held::current(SELINUX);
    let own_role = role.as_ref().is_ok_and(|v| v == ROLE);
    if !requested && !own_role {
        return Ok(false);
    }
    if !requested || arguments.len() != 1 || !own_role || held::current(APPARMOR)? != PROFILE {
        return Err(reject(
            "native uevent preparation requires its fixed executable and MAC roles",
        ));
    }
    let mapping = labels()?;
    held::root_without_capabilities()?;
    let root = held::path_at(libc::AT_FDCWD, c"/")?;
    held::directory(&root)?;
    held::namespaces(&root)?;
    let counts = scan(&root, &mut |parent, file, device, mount| {
        visit(parent, file, device, mount, &mapping)
    })?;
    held::namespaces(&root)?;
    if held::current(SELINUX)? != ROLE || held::current(APPARMOR)? != PROFILE {
        return Err(reject(
            "native uevent preparation lost its original MAC identities",
        ));
    }
    eprintln!(
        "Droidloom native coldplug: inspected {} uevent inodes, labelled {}, disappeared {}",
        counts.events, counts.changed, counts.disappeared
    );
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::ffi::OsStrExt;

    #[test]
    fn unrelated_filesystem_and_symlink_root_cannot_be_a_sysfs_source() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::create_dir(temp.path().join("sys")).unwrap();
        let root = held::path_at(
            libc::AT_FDCWD,
            &CString::new(temp.path().as_os_str().as_bytes()).unwrap(),
        )
        .unwrap();
        assert!(sysfs_root(&root).is_err());
        std::fs::remove_dir(temp.path().join("sys")).unwrap();
        std::os::unix::fs::symlink("/sys", temp.path().join("sys")).unwrap();
        assert!(sysfs_root(&root).is_err());
    }

    #[test]
    fn non_helper_role_cannot_select_labels_or_paths() {
        assert!(dispatch(&[ENTRY.into()]).is_err());
        assert!(dispatch(&[ENTRY.into(), "/sys/devices".into()]).is_err());
    }

    #[test]
    #[ignore = "read-only traversal of an actual original root-owned writable sysfs; no labels are changed"]
    fn actual_original_sysfs_traversal_never_opens_attribute_bodies() {
        let root = held::path_at(libc::AT_FDCWD, c"/").unwrap();
        let counts = scan(&root, &mut |_, file, device, mount| {
            event_identity(file, device, mount)?;
            Ok(false)
        })
        .unwrap();
        assert!(counts.events > 0);
        assert_eq!(counts.changed, 0);
        println!("actual native sysfs read-only traversal: {counts:?}");
    }
}
