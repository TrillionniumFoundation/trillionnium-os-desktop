//! Held metadata of one real package in the owner's current working filesystem.
//!
//! This module never opens an account file, copies an image, selects a caller
//! pathname, changes a namespace, or mutates an Android directory. The input
//! process identity comes only from the live normal Main factory.
use crate::control::application_probe::ApplicationInspection;
use crate::main_custody::{MainDataRole, MainMountRoot, MainNodeIdentity, RuntimeMainCustody};
use serde::{Deserialize, Serialize};
use std::ffi::{CStr, CString};
use std::fs::File;
use std::io::{self, Read};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::MetadataExt;

fn require(value: bool, why: &'static str) -> io::Result<()> {
    if value {
        Ok(())
    } else {
        Err(io::Error::other(why))
    }
}
fn file(raw: libc::c_long) -> io::Result<File> {
    if raw < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(unsafe { File::from_raw_fd(raw as i32) })
    }
}
fn open_at(parent: &File, name: &CStr, flags: i32) -> io::Result<File> {
    file(unsafe { libc::openat(parent.as_raw_fd(), name.as_ptr(), flags | libc::O_CLOEXEC) } as _)
}
fn identity(f: &File) -> io::Result<MainNodeIdentity> {
    Ok(MainNodeIdentity::of(&f.metadata()?))
}
fn live(f: &File) -> io::Result<()> {
    let mut p = libc::pollfd {
        fd: f.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    let rc = unsafe { libc::poll(&mut p, 1, 0) };
    if rc < 0 {
        return Err(io::Error::last_os_error());
    }
    require(
        rc == 0 && p.revents == 0,
        "native leaf original framework has exited",
    )
}
fn fs_kind(f: &File, expected: libc::c_long) -> io::Result<()> {
    let mut st: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(f.as_raw_fd(), &mut st) } != 0 {
        return Err(io::Error::last_os_error());
    }
    require(st.f_type == expected, "native leaf held filesystem differs")
}
fn small(parent: &File, name: &CStr) -> io::Result<String> {
    let f = open_at(
        parent,
        name,
        libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_NONBLOCK,
    )?;
    fs_kind(&f, libc::PROC_SUPER_MAGIC)?;
    let mut bytes = Vec::new();
    f.take(16385).read_to_end(&mut bytes)?;
    require(bytes.len() <= 16384, "native leaf proc field exceeds bound")?;
    String::from_utf8(bytes).map_err(io::Error::other)
}
fn birth(text: &str, expected_pid: u32, expected_ticks: u64) -> io::Result<()> {
    let (pid, tail) = text
        .split_once(" (")
        .ok_or_else(|| io::Error::other("proc PID absent"))?;
    let (_, tail) = tail
        .rsplit_once(") ")
        .ok_or_else(|| io::Error::other("proc stat malformed"))?;
    let f: Vec<_> = tail.split_ascii_whitespace().collect();
    require(
        pid.parse::<u32>().ok() == Some(expected_pid)
            && f.len() >= 20
            && !matches!(f[0], "Z" | "X" | "x")
            && f[19].parse::<u64>().ok() == Some(expected_ticks),
        "native leaf framework process generation changed",
    )
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct IdMapRange {
    pub inside: u32,
    pub outside: u32,
    pub count: u32,
}
fn id_map(text: &str) -> io::Result<Vec<IdMapRange>> {
    require(
        !text.is_empty() && text.len() <= 16384,
        "native leaf ID map is absent or oversized",
    )?;
    let mut rows = Vec::new();
    for line in text.lines() {
        let values = line
            .split_ascii_whitespace()
            .map(str::parse::<u32>)
            .collect::<Result<Vec<_>, _>>()
            .map_err(io::Error::other)?;
        require(
            values.len() == 3 && values[2] != 0,
            "native leaf ID map row differs",
        )?;
        let row = IdMapRange {
            inside: values[0],
            outside: values[1],
            count: values[2],
        };
        for start in [row.inside, row.outside] {
            require(
                u64::from(start) + u64::from(row.count) <= (1_u64 << 32),
                "native leaf ID map overflows",
            )?;
        }
        rows.push(row);
    }
    require(
        !rows.is_empty() && rows.len() <= 340,
        "native leaf ID map count differs",
    )?;
    for (i, a) in rows.iter().enumerate() {
        for b in rows.iter().skip(i + 1) {
            for (x, y) in [(a.inside, b.inside), (a.outside, b.outside)] {
                require(
                    u64::from(x) + u64::from(a.count) <= u64::from(y)
                        || u64::from(y) + u64::from(b.count) <= u64::from(x),
                    "native leaf ID map overlaps",
                )?;
            }
        }
    }
    Ok(rows)
}
pub(crate) fn mapped(rows: &[IdMapRange], uid: u32) -> io::Result<u32> {
    let matches: Vec<_> = rows
        .iter()
        .filter(|r| uid >= r.inside && u64::from(uid) < u64::from(r.inside) + u64::from(r.count))
        .collect();
    require(
        matches.len() == 1,
        "actual package UID is not mapped exactly once",
    )?;
    matches[0]
        .outside
        .checked_add(uid - matches[0].inside)
        .ok_or_else(|| io::Error::other("mapped package UID overflow"))
}

/// Stable directory metadata. Child creation legitimately changes link count,
/// size, mtime and ctime, so those four fields do not identify the directory.
#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LeafDirectory {
    pub path: String,
    pub device: u64,
    pub inode: u64,
    pub mount_id: u64,
    pub mode: u32,
    pub host_uid: u32,
    pub host_gid: u32,
}
fn directory(f: &File, path: &str) -> io::Result<LeafDirectory> {
    let m = f.metadata()?;
    require(m.is_dir(), "native leaf target is not a directory")?;
    let mut st: libc::statx = unsafe { std::mem::zeroed() };
    if unsafe {
        libc::statx(
            f.as_raw_fd(),
            c"".as_ptr(),
            libc::AT_EMPTY_PATH | libc::AT_SYMLINK_NOFOLLOW,
            libc::STATX_MNT_ID,
            &mut st,
        )
    } != 0
    {
        return Err(io::Error::last_os_error());
    }
    require(
        st.stx_mask & libc::STATX_MNT_ID != 0 && st.stx_mnt_id != 0,
        "native leaf directory mount identity is unavailable",
    )?;
    Ok(LeafDirectory {
        path: path.into(),
        device: m.dev(),
        inode: m.ino(),
        mount_id: st.stx_mnt_id,
        mode: m.mode(),
        host_uid: m.uid(),
        host_gid: m.gid(),
    })
}
#[repr(C)]
struct OpenHow {
    flags: u64,
    mode: u64,
    resolve: u64,
}
fn rooted_kind(root: &File, path: &str, follow_final: bool) -> io::Result<File> {
    require(
        !path.is_empty()
            && !path.starts_with('/')
            && path
                .split('/')
                .all(|p| !p.is_empty() && p != "." && p != ".."),
        "native leaf path is not a fixed relative path",
    )?;
    let path = CString::new(path).map_err(io::Error::other)?;
    // IN_ROOT handles Android's normal absolute intermediate symlinks within
    // the held framework root. NO_MAGICLINKS and final NOFOLLOW are mandatory.
    let how = OpenHow {
        flags: (libc::O_PATH
            | libc::O_DIRECTORY
            | libc::O_CLOEXEC
            | if follow_final { 0 } else { libc::O_NOFOLLOW }) as u64,
        mode: 0,
        resolve: 0x10 | 0x02,
    };
    file(unsafe {
        libc::syscall(
            libc::SYS_openat2,
            root.as_raw_fd(),
            path.as_ptr(),
            &how,
            std::mem::size_of::<OpenHow>(),
        )
    })
}
fn rooted(root: &File, path: &str) -> io::Result<File> {
    rooted_kind(root, path, matches!(path, "data/user/0" | "data/user_de/0"))
}
pub(crate) fn package_paths(package: &str, user: u32) -> io::Result<[String; 4]> {
    require(
        user == 0
            && package.len() <= 255
            && package.contains('.')
            && package.split('.').all(|p| {
                !p.is_empty() && p.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_')
            }),
        "native leaf data currently requires one actual user-0 package",
    )?;
    Ok([
        "data/user/0".into(),
        "data/user_de/0".into(),
        format!("data/user/0/{package}"),
        format!("data/user_de/0/{package}"),
    ])
}
fn root_matches(actual: &LeafDirectory, expected: &MainMountRoot) -> io::Result<()> {
    require(
        (
            actual.device,
            actual.inode,
            actual.mount_id,
            actual.mode,
            actual.host_uid,
            actual.host_gid,
        ) == (
            expected.device,
            expected.inode,
            expected.mount_id,
            expected.mode,
            expected.uid,
            expected.gid,
        ),
        "native leaf /data is not the normal owner's current working mount",
    )
}

/// Output-only facts; deserialize is for exact comparison, not an authority.
#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LeafDataFacts {
    pub schema: String,
    pub package: String,
    pub user: u32,
    pub android_uid: u32,
    pub mapped_host_uid: u32,
    pub framework_root: MainNodeIdentity,
    pub user_namespace: MainNodeIdentity,
    pub uid_map: Vec<IdMapRange>,
    pub gid_map: Vec<IdMapRange>,
    pub data_root: LeafDirectory,
    /// CE parent, DE parent, actual package CE, actual package DE, in this order.
    pub directories: [LeafDirectory; 4],
}

struct HeldDirectories {
    root: File,
    data: File,
    leaves: [File; 4],
    facts: LeafDataFacts,
}
impl HeldDirectories {
    fn capture(
        root: File,
        main: &RuntimeMainCustody,
        app: &ApplicationInspection,
        uid_map: Vec<IdMapRange>,
        gid_map: Vec<IdMapRange>,
    ) -> io::Result<Self> {
        let data_view = main
            .persistent_data
            .backings
            .iter()
            .find(|v| v.role == MainDataRole::Data)
            .ok_or_else(|| io::Error::other("normal Main data role absent"))?;
        require(
            main.persistent_data.original_copy_origin.is_some(),
            "native leaf requires the source-admitted original-to-working copy lineage",
        )?;
        require(
            identity(&root)? == main.framework.root,
            "native leaf framework root differs",
        )?;
        let data = rooted(&root, "data")?;
        let data_root = directory(&data, "/data")?;
        root_matches(&data_root, &data_view.framework_root)?;
        let paths = package_paths(&app.package, app.user)?;
        let host_uid = mapped(&uid_map, app.uid)?;
        let mut files = Vec::new();
        let mut values = Vec::new();
        for (index, path) in paths.iter().enumerate() {
            let f = rooted(&root, path)?;
            let actual = directory(&f, &format!("/{path}"))?;
            require(
                actual.device == data_root.device,
                "native leaf directory is not on the current working data filesystem",
            )?;
            if index >= 2 {
                require(
                    actual.host_uid == host_uid,
                    "actual CE/DE directory owner does not match the inspected package UID",
                )?;
            }
            files.push(f);
            values.push(actual);
        }
        require(
            (values[2].device, values[2].inode) != (values[3].device, values[3].inode),
            "actual package CE and DE directories alias the same inode",
        )?;
        let result = Self {
            root,
            data,
            leaves: files
                .try_into()
                .map_err(|_| io::Error::other("directory count"))?,
            facts: LeafDataFacts {
                schema: "droidloom.native-leaf-data.v1".into(),
                package: app.package.clone(),
                user: app.user,
                android_uid: app.uid,
                mapped_host_uid: host_uid,
                framework_root: main.framework.root,
                user_namespace: main.persistent_data.user_namespace,
                uid_map,
                gid_map,
                data_root,
                directories: values
                    .try_into()
                    .map_err(|_| io::Error::other("directory count"))?,
            },
        };
        result.verify()?;
        Ok(result)
    }
    fn verify(&self) -> io::Result<()> {
        require(
            identity(&self.root)? == self.facts.framework_root,
            "held framework root changed",
        )?;
        require(
            directory(&self.data, "/data")? == self.facts.data_root
                && directory(&rooted(&self.root, "data")?, "/data")? == self.facts.data_root,
            "held or named working /data changed",
        )?;
        for (held, old) in self.leaves.iter().zip(&self.facts.directories) {
            require(
                directory(held, &old.path)? == *old
                    && directory(
                        &rooted(
                            &self.root,
                            old.path
                                .strip_prefix('/')
                                .ok_or_else(|| io::Error::other("fixed data path absent"))?,
                        )?,
                        &old.path,
                    )? == *old,
                "held or named CE/DE directory identity changed",
            )?;
        }
        Ok(())
    }
}

/// Private live handle. No public path constructor, Clone or Deserialize.
pub(crate) struct HeldLeafData {
    proc_root: File,
    process: File,
    process_identity: MainNodeIdentity,
    pidfd: File,
    pid: u32,
    start: u64,
    userns: File,
    directories: HeldDirectories,
}
impl HeldLeafData {
    pub(crate) fn capture(
        main: &RuntimeMainCustody,
        app: &ApplicationInspection,
    ) -> io::Result<Self> {
        main.validate(&app.epoch).map_err(io::Error::other)?;
        let pid = main.framework.host_pid;
        let start = main.framework.start_ticks;
        // The PID is derived solely from the authenticated actual Main response.
        // PIDFD and proc/root identities are checked before and after every read.
        let pidfd = file(unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0_u32) })?;
        live(&pidfd)?;
        require(
            identity(&pidfd)? == main.framework.pidfd,
            "native leaf PIDFD differs from the authenticated framework owner",
        )?;
        let proc_root = File::open("/proc")?;
        fs_kind(&proc_root, libc::PROC_SUPER_MAGIC)?;
        let name = CString::new(pid.to_string()).map_err(io::Error::other)?;
        let process = open_at(
            &proc_root,
            &name,
            libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW,
        )?;
        let process_identity = identity(&process)?;
        birth(&small(&process, c"stat")?, pid, start)?;
        let root = open_at(&process, c"root", libc::O_PATH | libc::O_DIRECTORY)?;
        let userns = open_at(&process, c"ns/user", libc::O_RDONLY)?;
        fs_kind(&userns, 0x6e736673)?;
        require(
            unsafe { libc::ioctl(userns.as_raw_fd(), 0xb703 as libc::c_ulong) }
                == libc::CLONE_NEWUSER,
            "native leaf held namespace is not a user namespace",
        )?;
        require(
            identity(&userns)? == main.persistent_data.user_namespace,
            "native leaf user namespace differs from the actual persistent owner",
        )?;
        let uid_map = id_map(&small(&process, c"uid_map")?)?;
        let gid_map = id_map(&small(&process, c"gid_map")?)?;
        let directories = HeldDirectories::capture(root, main, app, uid_map, gid_map)?;
        let result = Self {
            proc_root,
            process,
            process_identity,
            pidfd,
            pid,
            start,
            userns,
            directories,
        };
        result.verify()?;
        Ok(result)
    }
    pub(crate) fn facts(&self) -> &LeafDataFacts {
        &self.directories.facts
    }
    pub(crate) fn verify(&self) -> io::Result<()> {
        live(&self.pidfd)?;
        let name = CString::new(self.pid.to_string()).map_err(io::Error::other)?;
        require(
            identity(&self.process)? == self.process_identity
                && identity(&open_at(
                    &self.proc_root,
                    &name,
                    libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW,
                )?)? == self.process_identity,
            "native leaf held framework proc identity changed",
        )?;
        birth(&small(&self.process, c"stat")?, self.pid, self.start)?;
        require(
            identity(&open_at(
                &self.process,
                c"root",
                libc::O_PATH | libc::O_DIRECTORY,
            )?)? == self.facts().framework_root,
            "native leaf process root changed",
        )?;
        require(
            identity(&self.userns)? == self.facts().user_namespace
                && identity(&open_at(&self.process, c"ns/user", libc::O_RDONLY)?)?
                    == self.facts().user_namespace
                && id_map(&small(&self.process, c"uid_map")?)? == self.facts().uid_map
                && id_map(&small(&self.process, c"gid_map")?)? == self.facts().gid_map,
            "native leaf namespace or actual ID maps changed",
        )?;
        self.directories.verify()?;
        birth(&small(&self.process, c"stat")?, self.pid, self.start)?;
        live(&self.pidfd)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::os::unix::fs::symlink;

    fn fixture() -> (tempfile::TempDir, HeldDirectories) {
        let d = tempfile::tempdir().unwrap();
        for path in [
            "data/user/0/org.example.app",
            "data/user_de/0/org.example.app",
        ] {
            fs::create_dir_all(d.path().join(path)).unwrap();
        }
        let root = File::open(d.path()).unwrap();
        let mut main = crate::main_custody::tests::sample();
        main.framework.root = identity(&root).unwrap();
        let data = directory(&File::open(d.path().join("data")).unwrap(), "/data").unwrap();
        main.persistent_data.backings[0].framework_root = MainMountRoot {
            device: data.device,
            inode: data.inode,
            mount_id: data.mount_id,
            mode: data.mode,
            uid: data.host_uid,
            gid: data.host_gid,
        };
        let app = ApplicationInspection {
            package: "org.example.app".into(),
            user: 0,
            uid: 10001,
            version_code: 1,
            epoch: main.epoch.clone(),
            apks: Vec::new(),
        };
        let uid = root.metadata().unwrap().uid();
        let gid = root.metadata().unwrap().gid();
        let held = HeldDirectories::capture(
            root,
            &main,
            &app,
            id_map(&format!("10001 {uid} 1\n")).unwrap(),
            id_map(&format!("10001 {gid} 1\n")).unwrap(),
        )
        .unwrap();
        (d, held)
    }
    #[test]
    fn native_leaf_data_holds_current_working_directories_across_legitimate_contents() {
        let (d, held) = fixture();
        fs::create_dir(d.path().join("data/user/0/org.example.app/new-child")).unwrap();
        fs::write(
            d.path().join("data/user/0/org.example.app/new-child/file"),
            b"private fixture",
        )
        .unwrap();
        held.verify().unwrap();
        assert_eq!(held.facts.directories.len(), 4);
        assert_ne!(
            held.facts.directories[2].inode,
            held.facts.directories[3].inode
        );
    }
    #[test]
    fn native_leaf_data_rejects_named_directory_substitution_while_holding_original() {
        let (d, held) = fixture();
        let p = d.path().join("data/user/0/org.example.app");
        fs::rename(&p, p.with_file_name("retained")).unwrap();
        fs::create_dir(&p).unwrap();
        assert!(held.verify().is_err());
    }
    #[test]
    fn native_leaf_data_rejects_final_symlink_and_escapes_but_supports_normal_intermediate_link() {
        let d = tempfile::tempdir().unwrap();
        fs::create_dir_all(d.path().join("data/user")).unwrap();
        fs::create_dir_all(d.path().join("data/data/org.example.app")).unwrap();
        symlink("/data/data", d.path().join("data/user/0")).unwrap();
        let root = File::open(d.path()).unwrap();
        let got = rooted(&root, "data/user/0/org.example.app").unwrap();
        assert_eq!(
            identity(&got).unwrap(),
            identity(&File::open(d.path().join("data/data/org.example.app")).unwrap()).unwrap()
        );
        symlink(
            "/data/data/org.example.app",
            d.path().join("data/data/another"),
        )
        .unwrap();
        assert!(rooted(&root, "data/data/another").is_err());
        assert!(rooted(&root, "../outside").is_err());
        symlink("/proc/self/fd/0", d.path().join("escape")).unwrap();
        assert!(rooted(&root, "escape").is_err());
    }
    #[test]
    fn native_leaf_data_requires_exact_uid_mapping_and_fixed_user_package_paths() {
        let rows = id_map("0 2000000 1000\n1000 1000 1\n1001 2001001 64535\n").unwrap();
        assert_eq!(mapped(&rows, 10123).unwrap(), 2010123);
        assert!(mapped(&rows, 70000).is_err());
        assert!(id_map("0 1000 10\n9 2000 10\n").is_err());
        assert!(id_map("0 1000 10\n20 1009 10\n").is_err());
        assert!(id_map("0 4294967295 2\n").is_err());
        for (p, u) in [
            ("../pkg", 0),
            ("a/evil.b", 0),
            ("a..b", 0),
            ("org.example.app", 1),
        ] {
            assert!(package_paths(p, u).is_err());
        }
    }
    #[test]
    fn native_leaf_data_rejects_foreign_root_and_changed_owner_without_image_identity_fiction() {
        let (d, held) = fixture();
        let mut altered = held.facts.data_root.clone();
        altered.inode += 1;
        let expected = MainMountRoot {
            device: altered.device,
            inode: altered.inode,
            mount_id: altered.mount_id,
            mode: altered.mode,
            uid: altered.host_uid,
            gid: altered.host_gid,
        };
        assert!(root_matches(&held.facts.data_root, &expected).is_err());
        use std::os::unix::fs::PermissionsExt;
        let p = d.path().join("data/user_de/0/org.example.app");
        let changed = fs::metadata(&p).unwrap().mode() ^ 0o001;
        fs::set_permissions(&p, fs::Permissions::from_mode(changed & 0o7777)).unwrap();
        assert!(held.verify().is_err());
    }
}
