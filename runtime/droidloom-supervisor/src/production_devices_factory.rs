//! Measurements made by the board while the selected Android PID 1 is still waiting.
use super::*;

const KEY: &CStr = c"trusted.droidloom.device-source";
const TEMPLATE: &str = "b5b7ee1522f87c6fafb668d671ff028685db9e8e346564b1edda1f7ef867d5f7.img";
const SOURCE_NODES: [&str; 7] = ["null", "random", "urandom", "zero", "full", "tty", "fuse"];

#[derive(Debug, PartialEq, Eq)]
pub(super) struct FactoryDevices {
    bytes: Vec<u8>,
    original_leaves: [u64; 4],
}

fn fields(line: Option<&str>) -> Result<[u64; 4]> {
    let mut numbers = [0; 4];
    let mut values = line.unwrap_or_default().split(' ');
    for number in &mut numbers {
        *number = values
            .next()
            .and_then(|n| n.parse().ok())
            .ok_or(DeviceError::Rejected("invalid board device measurement"))?;
    }
    need(
        values.next().is_none(),
        "extra board device measurement fields",
    )?;
    Ok(numbers)
}

impl FactoryDevices {
    fn parse(bytes: Vec<u8>, cohort: &str, original: (u64, u64, u64)) -> Result<Self> {
        let source = std::str::from_utf8(&bytes)
            .map_err(|_| DeviceError::Rejected("invalid board device measurement encoding"))?;
        need(
            source.ends_with('\n'),
            "incomplete board device measurement",
        )?;
        let mut lines = source.lines();
        need(
            lines.next() == Some("DROIDLOOM_DEVICES_V1")
                && lines.next() == Some(cohort)
                && lines.next() == Some(TEMPLATE),
            "device source or release selection differs",
        )?;
        let root = fields(lines.next())?;
        need(
            root[0] == u64::from(libc::major(original.0))
                && root[1] == u64::from(libc::minor(original.0))
                && root[2] == original.1
                && root[3] == original.2,
            "board measured a different device filesystem",
        )?;
        let mut native_inodes = std::collections::BTreeSet::new();
        let mut backing_filesystem = None;
        let mut leaves = Vec::new();
        for (index, name) in SOURCE_NODES.iter().enumerate() {
            let row = lines.next().and_then(|line| line.split_once(' '));
            let (actual, raw) =
                row.ok_or(DeviceError::Rejected("missing factory device measurement"))?;
            need(actual == *name, "wrong factory device name or order")?;
            let item = fields(Some(raw))?;
            let dev = (item[0], item[1]);
            need(
                item[2] != 0 && item[3] != 0 && native_inodes.insert((dev, item[2])),
                "ambiguous factory device identity",
            )?;
            if index < 3 {
                need(
                    dev == (root[0], root[1]) && item[3] == root[3],
                    "board-local devices left the private tmpfs",
                )?;
            } else {
                let backing = *backing_filesystem.get_or_insert(dev);
                need(
                    dev == backing && dev != (root[0], root[1]) && item[3] != root[3],
                    "factory image devices differ from the selected separate filesystem",
                )?;
                leaves.push(item[3]);
            }
        }
        need(lines.next().is_none(), "extra board device measurements")?;
        leaves.sort_unstable();
        need(
            leaves.windows(2).all(|s| s[0] != s[1]),
            "factory device mounts must be distinct",
        )?;
        Ok(Self {
            bytes,
            original_leaves: leaves.try_into().expect("four fixed factory nodes"),
        })
    }

    fn read(root: &File) -> Result<Vec<u8>> {
        let mut measured = vec![0_u8; 1536];
        let count = unsafe {
            libc::fgetxattr(
                root.as_raw_fd(),
                KEY.as_ptr(),
                measured.as_mut_ptr().cast(),
                measured.len(),
            )
        };
        if count < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        measured.truncate(count as usize);
        Ok(measured)
    }

    pub(super) fn acquire(root: &File, cohort: &str, original: (u64, u64, u64)) -> Result<Self> {
        let witness = Self::parse(Self::read(root)?, cohort, original)?;
        // listmount reads the actual topology of the original child mount namespace.
        // Its Linux 6.18 version-zero request has a size of 24 bytes.
        #[repr(C)]
        struct MountRequest {
            size: u32,
            namespace: u32,
            parent: u64,
            after: u64,
        }
        let request = MountRequest {
            size: 24,
            namespace: 0,
            parent: original.2,
            after: 0,
        };
        let mut ids = [0_u64; 5];
        // Selected x86_64 kernel ABI; libc 0.2.188 does not export SYS_listmount.
        const SYS_LISTMOUNT: libc::c_long = 458;
        let count = unsafe {
            libc::syscall(
                SYS_LISTMOUNT,
                &request,
                ids.as_mut_ptr(),
                ids.len(),
                0,
            )
        };
        if count < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        need(
            count == 4,
            "unexpected descendant mounts in the original private device tree",
        )?;
        ids[..4].sort_unstable();
        need(
            ids[..4] == witness.original_leaves,
            "device mounts differ from the board measurement",
        )?;
        witness.verify(root, false)?;
        Ok(witness)
    }

    pub(super) fn verify(&self, root: &File, has_socket: bool) -> Result<()> {
        need(
            Self::read(root)? == self.bytes,
            "original device measurement changed during handoff",
        )?;
        let mut names: Vec<_> = SOURCE_NODES
            .iter()
            .map(|name| name.as_bytes().to_vec())
            .collect();
        names.push(b"__properties__".to_vec());
        if has_socket {
            names.push(b"socket".to_vec());
        }
        names.sort();
        need(
            directory_names_bounded(root, names.len())? == names,
            "factory device directory changed",
        )?;
        #[repr(C)]
        struct OpenHow {
            flags: u64,
            mode: u64,
            resolve: u64,
        }
        // A no-cross-device lookup must stop at precisely four mounts. The broker
        // never opens a character driver or asks for private Android inode metadata.
        let how = OpenHow {
            flags: (libc::O_PATH | O_SAFE) as u64,
            mode: 0,
            resolve: 0x01 | 0x02 | 0x04,
        };
        for (index, name) in [
            c"null",
            c"random",
            c"urandom",
            c"zero",
            c"full",
            c"tty",
            c"fuse",
            c"__properties__",
        ]
        .iter()
        .enumerate()
        {
            let fd = unsafe {
                libc::syscall(
                    libc::SYS_openat2,
                    root.as_raw_fd(),
                    name.as_ptr(),
                    &how,
                    std::mem::size_of::<OpenHow>(),
                )
            };
            if fd < 0 {
                let error = std::io::Error::last_os_error();
                if (3..7).contains(&index) && error.raw_os_error() == Some(libc::EXDEV) {
                    continue;
                }
                return Err(error.into());
            }
            drop(unsafe { File::from_raw_fd(fd as i32) });
            need(
                !(3..7).contains(&index),
                "factory character node lost its separate mount",
            )?;
        }
        Ok(())
    }
    pub(super) fn len(&self) -> usize {
        SOURCE_NODES.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn measured() -> Vec<u8> {
        format!("DROIDLOOM_DEVICES_V1\n{}\n{}\n0 24 1 600\nnull 0 24 2 600\nrandom 0 24 3 600\nurandom 0 24 4 600\nzero 7 1 12 701\nfull 7 1 13 702\ntty 7 1 14 703\nfuse 7 1 15 704\n","a".repeat(64),TEMPLATE).into_bytes()
    }

    #[test]
    fn original_device_measurement_requires_every_independent_mount_and_factory_inode() {
        let bytes = measured();
        let cohort = "a".repeat(64);
        let root = (libc::makedev(0, 24), 1, 600);
        let proof = FactoryDevices::parse(bytes.clone(), &cohort, root).unwrap();
        assert_eq!(proof.original_leaves, [701, 702, 703, 704]);
        assert!(FactoryDevices::parse(bytes.clone(), &"b".repeat(64), root).is_err());
        assert!(FactoryDevices::parse(bytes.clone(), &cohort, (root.0, root.1, 601)).is_err());
        for (key, wrong) in [
            ("zero 7 1 12 701", "zero 0 24 12 701"),
            ("full 7 1 13 702", "full 7 1 12 702"),
            ("tty 7 1 14 703", "tty 7 1 14 702"),
            ("null 0 24 2 600", "null 0 24 2 901"),
            ("fuse 7 1 15 704", "extra 7 1 15 704"),
            ("fuse 7 1 15 704\n", ""),
            ("DROIDLOOM_DEVICES_V1", "other"),
            (TEMPLATE, "another.img"),
        ] {
            let observed = std::str::from_utf8(&bytes).unwrap().replace(key, wrong);
            assert!(
                FactoryDevices::parse(observed.into_bytes(), &cohort, root).is_err(),
                "{key}"
            );
        }
    }
}

#[cfg(test)]
mod kernel_device_supply {
    use super::*;

    #[test]
    #[ignore = "requires the private, populated board device tree on the selected kernel"]
    fn original_factory_nodes_survive_normal_mount_custody() {
        let cohort = "029b45ac4044cdb11b51988e36fd5fa75e1acd69760bdcba02deb8d687a35790";
        // FD 9 is the board parent's original private tmpfs, populated by the release code.
        let root = fd_result(unsafe { libc::fcntl(9, libc::F_DUPFD_CLOEXEC, 10) as _ }).unwrap();
        let mut stat: libc::statx = unsafe { std::mem::zeroed() };
        const UNIQUE: u32 = 0x4000;
        zero(unsafe {
            libc::syscall(libc::SYS_statx, root.as_raw_fd(), c"".as_ptr(),
                          AT_EMPTY_PATH, UNIQUE, &mut stat)
        }).unwrap();
        assert_ne!(stat.stx_mask & UNIQUE, 0);
        let (dev, ino) = node(&root).unwrap();
        let identity = (dev, ino, stat.stx_mnt_id);
        let factory = FactoryDevices::acquire(&root, cohort, identity).unwrap();
        assert!(FactoryDevices::acquire(&root, &"0".repeat(64), identity).is_err());
        assert!(FactoryDevices::acquire(&root, cohort, (dev, ino, stat.stx_mnt_id+1)).is_err());
        let clone = fd_result(unsafe {
            libc::syscall(libc::SYS_open_tree, root.as_raw_fd(), c"".as_ptr(),
                          libc::OPEN_TREE_CLONE | libc::O_CLOEXEC as u32 | AT_EMPTY_PATH | libc::AT_RECURSIVE as u32)
        }).unwrap();
        require_detached(&clone).unwrap();
        assert_eq!(node(&clone).unwrap(), (dev, ino));
        factory.verify(&clone, false).unwrap();
    }
}
