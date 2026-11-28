//! Complete, stable DEV observation for the original executed generation.
//!
//! This stage neither reuses the fresh eight-entry verifier nor ignores the
//! entries Android has created. It observes every entry without opening any
//! device body or following symlinks. Only the three already-owned filesystem
//! mounts are admissible; runtime mount/namespace transitions remain closed.

use super::*;
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::CString;
use std::os::unix::ffi::OsStrExt;

const MAX_NODES: usize = 18_432; // bounded DEV inodes + devpts and Binder leaves
const MAX_DEPTH: usize = 32;
const MAX_PATH: usize = 4096;

#[derive(Clone, Debug, Eq, PartialEq)]
struct Entry {
    node: Node,
    mount: u64,
    filesystem: libc::c_long,
    rdev: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    bytes: u64,
    mtime: (i64, i64),
    ctime: (i64, i64),
    link: Option<Vec<u8>>,
}

impl Entry {
    fn read(file: &File) -> Result<Self> {
        let m = file.metadata()?;
        let mut entry = Self {
            node: Node::of(file)?,
            mount: writable_proc::held_mount_id(file)?,
            filesystem: filesystem_kind(file)?,
            rdev: m.rdev(),
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            links: m.nlink(),
            bytes: m.size(),
            mtime: (m.mtime(), m.mtime_nsec()),
            ctime: (m.ctime(), m.ctime_nsec()),
            link: None,
        };
        if m.mode() & libc::S_IFMT == libc::S_IFLNK {
            let mut bytes = vec![0_u8; MAX_PATH + 1];
            // AT_EMPTY_PATH semantics of readlinkat operate on this O_PATH
            // symlink itself. Its target is recorded, never traversed.
            let length = unsafe {
                libc::readlinkat(
                    file.as_raw_fd(),
                    c"".as_ptr(),
                    bytes.as_mut_ptr().cast(),
                    bytes.len(),
                )
            };
            if length < 0 {
                return Err(io::Error::last_os_error().into());
            }
            if length == 0 || length as usize > MAX_PATH {
                return Err(NamespaceError::Rejected(
                    "executed DEV symlink observation bound",
                ));
            }
            bytes.truncate(length as usize);
            entry.link = Some(bytes);
        }
        Ok(entry)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Mount {
    id: u64,
    device: u64,
    filesystem: libc::c_long,
}

struct Mounts {
    dev: Mount,
    pts: Mount,
    binder: Mount,
}

impl Mounts {
    fn expected(&self, path: &[u8]) -> Mount {
        if path == b"pts" || path.starts_with(b"pts/") {
            self.pts
        } else if path == b"binderfs" || path.starts_with(b"binderfs/") {
            self.binder
        } else {
            self.dev
        }
    }

    fn require(&self, path: &[u8], entry: &Entry) -> Result<()> {
        let expected = self.expected(path);
        if (entry.mount, entry.node.device, entry.filesystem)
            != (expected.id, expected.device, expected.filesystem)
        {
            return Err(NamespaceError::Rejected(
                "executed DEV entry crossed an undeclared mount",
            ));
        }
        Ok(())
    }
}

fn before_deadline(deadline: Instant) -> Result<()> {
    if Instant::now() >= deadline {
        return Err(NamespaceError::Rejected(
            "complete executed DEV observation deadline",
        ));
    }
    Ok(())
}

fn collect(
    file: &File,
    path: &[u8],
    mounts: &Mounts,
    ranges: (IdRange, IdRange),
    deadline: Instant,
    depth: usize,
    entries: &mut BTreeMap<Vec<u8>, Entry>,
    directories: &mut BTreeSet<(u64, u64, u64)>,
) -> Result<()> {
    before_deadline(deadline)?;
    if depth > MAX_DEPTH || path.len() > MAX_PATH || entries.len() >= MAX_NODES {
        return Err(NamespaceError::Rejected(
            "complete executed DEV traversal bound",
        ));
    }
    let before = Entry::read(file)?;
    mounts.require(path, &before)?;
    if !ranges.0.contains(before.uid) || !ranges.1.contains(before.gid) || before.links == 0 {
        return Err(NamespaceError::Rejected(
            "executed DEV inode escaped its original mapped IDs",
        ));
    }
    if entries.insert(path.to_vec(), before.clone()).is_some() {
        return Err(NamespaceError::Rejected("duplicate executed DEV path"));
    }
    if before.mode & libc::S_IFMT == libc::S_IFDIR {
        if !directories.insert((before.mount, before.node.device, before.node.inode)) {
            return Err(NamespaceError::Rejected("executed DEV directory alias"));
        }
        let directory = root_subdirectory(file, c".")?;
        let mut names = Vec::new();
        for row in std::fs::read_dir(format!("/proc/self/fd/{}", directory.as_raw_fd()))? {
            before_deadline(deadline)?;
            if names.len() >= MAX_NODES - entries.len() {
                return Err(NamespaceError::Rejected(
                    "complete executed DEV directory bound",
                ));
            }
            names.push(row?.file_name());
        }
        names.sort();
        if names.windows(2).any(|pair| pair[0] == pair[1]) {
            return Err(NamespaceError::Rejected(
                "executed DEV directory changed during enumeration",
            ));
        }
        for name in names {
            let bytes = name.as_bytes();
            if bytes.is_empty() || bytes == b"." || bytes == b".." || bytes.contains(&b'/') {
                return Err(NamespaceError::Rejected("executed DEV directory component"));
            }
            let name = CString::new(bytes)
                .map_err(|_| NamespaceError::Rejected("executed DEV name NUL"))?;
            let raw = unsafe {
                libc::openat(
                    directory.as_raw_fd(),
                    name.as_ptr(),
                    libc::O_PATH | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
                )
            };
            if raw < 0 {
                return Err(io::Error::last_os_error().into());
            }
            let child = unsafe { File::from_raw_fd(raw) };
            let mut child_path = path.to_vec();
            if !child_path.is_empty() {
                child_path.push(b'/');
            }
            child_path.extend_from_slice(bytes);
            collect(
                &child,
                &child_path,
                mounts,
                ranges,
                deadline,
                depth + 1,
                entries,
                directories,
            )?;
        }
    }
    if Entry::read(file)? != before {
        return Err(NamespaceError::Rejected(
            "executed DEV inode changed during traversal",
        ));
    }
    before_deadline(deadline)
}

#[derive(Debug, Eq, PartialEq)]
struct Snapshot {
    mounts: writable_proc::MountInventory,
    entries: BTreeMap<Vec<u8>, Entry>,
}

fn snapshot(
    init: &ExecutedInitWitness<'_>,
    original: &File,
    deadline: Instant,
) -> Result<Snapshot> {
    before_deadline(deadline)?;
    init.revalidate()?;
    let tree = &init.owner.tree;
    let child = init.init();
    let runtime = tree
        .runtime_observation
        .as_ref()
        .ok_or(NamespaceError::Rejected(
            "executed DEV lost runtime mount custody",
        ))?;
    let inventory = runtime.verify_current(child)?;
    let root = held_child_root(child)?;
    let dev = root_subdirectory(&root, c"dev")?;
    let expected = tree.device_node.ok_or(NamespaceError::Rejected(
        "executed DEV original node absent",
    ))?;
    if Node::of(&dev)? != expected
        || Node::of(original)? != expected
        || child.activation_nodes.is_none()
    {
        return Err(NamespaceError::Rejected(
            "executed DEV is not the original activation filesystem",
        ));
    }
    let process = tree.process_filesystems.ok_or(NamespaceError::Rejected(
        "executed DEV process filesystem custody absent",
    ))?;
    let binder = tree.binder.ok_or(NamespaceError::Rejected(
        "executed DEV Binder custody absent",
    ))?;
    let pts = root_subdirectory(&dev, c"pts")?;
    let binder_root = root_subdirectory(&dev, c"binderfs")?;
    if Node::of(&pts)? != process.pts || Node::of(&binder_root)? != binder.root {
        return Err(NamespaceError::Rejected(
            "executed DEV original devpts or Binder instance changed",
        ));
    }
    let observe_mount = |file: &File, target: &str, filesystem: libc::c_long| -> Result<Mount> {
        let id = writable_proc::held_mount_id(file)?;
        let device = Node::of(file)?.device;
        if inventory.visible.get(target) != Some(&id) || filesystem_kind(file)? != filesystem {
            return Err(NamespaceError::Rejected(
                "executed DEV mount differs from original complete inventory",
            ));
        }
        Ok(Mount {
            id,
            device,
            filesystem,
        })
    };
    let mounts = Mounts {
        dev: observe_mount(&dev, "/dev", 0x0102_1994)?,
        pts: observe_mount(&pts, "/dev/pts", 0x1cd1)?,
        binder: observe_mount(&binder_root, "/dev/binderfs", 0x6c6f_6f70)?,
    };
    let mut entries = BTreeMap::new();
    collect(
        &dev,
        b"",
        &mounts,
        (child.uids, child.gids),
        deadline,
        0,
        &mut entries,
        &mut BTreeSet::new(),
    )?;
    if runtime.verify_current(child)? != inventory {
        return Err(NamespaceError::Rejected(
            "executed DEV mount generation changed during traversal",
        ));
    }
    init.revalidate()?;
    before_deadline(deadline)?;
    Ok(Snapshot {
        mounts: inventory,
        entries,
    })
}

/// A comparison capability for one actual, stable executed DEV generation.
/// No caller inventory, saved inode, PID or Ready flag can construct it.
pub(crate) struct ExecutedDevObservation {
    generation: ExecutedInitGeneration,
    snapshot: Snapshot,
    deadline: Instant,
}

impl ExecutedDevObservation {
    pub(crate) fn observe(
        init: &ExecutedInitWitness<'_>,
        original: &File,
        deadline: Instant,
    ) -> Result<Self> {
        let generation = init.generation()?;
        let first = snapshot(init, original, deadline)?;
        let second = snapshot(init, original, deadline)?;
        if first != second || init.generation()? != generation {
            return Err(NamespaceError::Rejected(
                "complete executed DEV generation did not remain stable",
            ));
        }
        Ok(Self {
            generation,
            snapshot: second,
            deadline,
        })
    }

    pub(crate) fn revalidate(&self, init: &ExecutedInitWitness<'_>, original: &File) -> Result<()> {
        if init.generation()? != self.generation
            || snapshot(init, original, self.deadline)? != self.snapshot
        {
            return Err(NamespaceError::Rejected(
                "complete executed DEV generation changed",
            ));
        }
        if init.generation()? != self.generation {
            return Err(NamespaceError::Rejected(
                "executed DEV original init changed",
            ));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;

    fn actual_fixture(root: &File) -> (Mounts, (IdRange, IdRange)) {
        let entry = Entry::read(root).unwrap();
        let mount = Mount {
            id: entry.mount,
            device: entry.node.device,
            filesystem: entry.filesystem,
        };
        (
            Mounts {
                dev: mount,
                pts: mount,
                binder: mount,
            },
            (
                IdRange {
                    start: entry.uid,
                    count: 1,
                },
                IdRange {
                    start: entry.gid,
                    count: 1,
                },
            ),
        )
    }

    #[test]
    fn executed_dev_walk_records_all_real_entries_without_following_symlinks() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::create_dir(temp.path().join("socket")).unwrap();
        std::fs::write(
            temp.path().join("socket/ordinary"),
            b"ordinary inventory fixture",
        )
        .unwrap();
        symlink("/proc/self/mem", temp.path().join("outside")).unwrap();
        let root = File::open(temp.path()).unwrap();
        let (mounts, ranges) = actual_fixture(&root);
        let mut entries = BTreeMap::new();
        collect(
            &root,
            b"",
            &mounts,
            ranges,
            Instant::now() + Duration::from_secs(5),
            0,
            &mut entries,
            &mut BTreeSet::new(),
        )
        .unwrap();
        assert_eq!(
            entries.keys().cloned().collect::<BTreeSet<_>>(),
            [
                b"".to_vec(),
                b"socket".to_vec(),
                b"socket/ordinary".to_vec(),
                b"outside".to_vec()
            ]
            .into()
        );
        assert_eq!(
            entries[b"outside".as_slice()].link.as_deref(),
            Some(b"/proc/self/mem".as_slice())
        );
        assert_eq!(
            entries[b"outside".as_slice()].mode & libc::S_IFMT,
            libc::S_IFLNK
        );
        let prior = entries;
        std::fs::write(temp.path().join("added"), b"new").unwrap();
        let mut changed = BTreeMap::new();
        collect(
            &root,
            b"",
            &mounts,
            ranges,
            Instant::now() + Duration::from_secs(5),
            0,
            &mut changed,
            &mut BTreeSet::new(),
        )
        .unwrap();
        assert_ne!(prior, changed);
        assert!(changed.contains_key(b"added".as_slice()));
    }

    #[test]
    fn executed_dev_walk_rejects_changed_mount_ids_owners_and_expired_deadlines() {
        let temp = tempfile::tempdir().unwrap();
        let root = File::open(temp.path()).unwrap();
        let (mut mounts, ranges) = actual_fixture(&root);
        let mut entry = Entry::read(&root).unwrap();
        entry.mount += 1;
        assert!(mounts.require(b"", &entry).is_err());
        assert!(
            collect(
                &root,
                b"",
                &mounts,
                ranges,
                Instant::now(),
                0,
                &mut BTreeMap::new(),
                &mut BTreeSet::new()
            )
            .is_err()
        );
        let wrong = IdRange {
            start: ranges.0.start.wrapping_add(1),
            count: 1,
        };
        assert!(
            collect(
                &root,
                b"",
                &mounts,
                (wrong, ranges.1),
                Instant::now() + Duration::from_secs(5),
                0,
                &mut BTreeMap::new(),
                &mut BTreeSet::new()
            )
            .is_err()
        );
        mounts.pts.id += 1;
        assert!(
            mounts
                .require(b"pts/ptmx", &Entry::read(&root).unwrap())
                .is_err()
        );
        assert!(
            mounts
                .require(b"pts-alias", &Entry::read(&root).unwrap())
                .is_ok()
        );
    }
}
