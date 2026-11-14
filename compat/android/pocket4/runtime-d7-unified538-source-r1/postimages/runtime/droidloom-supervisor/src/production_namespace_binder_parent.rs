//! Parent verification for the fixed private Binder construction stage.
//!
//! Only an already-owned PID 1 may enter. No path, PID, mapping or descriptor
//! is supplied by a request. The stored scalar inventory is a comparison tied
//! to that owner's held namespaces; it cannot create another owner or lease.
use super::*;
use std::collections::BTreeSet;
use std::ffi::{CStr, OsString};

const BINDERFS_MAGIC: libc::c_long = 0x6c6f_6f70;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) struct DeviceIdentity {
    node: Node,
    rdev: u64,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) struct BinderFilesystem {
    pub(super) root: Node,
    control: DeviceIdentity,
    devices: [DeviceIdentity; 3],
}

pub(super) fn mount_options(path: &str, root: &str, flags: &str, options: &str) -> bool {
    let options: Vec<_> = options.split(',').collect();
    path == "/dev/binderfs"
        && root == "/"
        && has_flags(flags, &["rw", "nosuid", "noexec"], &["ro", "nodev"])
        && options.len() == 2
        && options.iter().copied().collect::<BTreeSet<_>>() == BTreeSet::from(["rw", "max=3"])
}

fn open_path(parent: &File, name: &CStr) -> Result<File> {
    let raw = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            libc::O_PATH | libc::O_CLOEXEC | libc::O_NOFOLLOW,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(raw) })
}

fn names(directory: &File, expected: &[&str]) -> Result<()> {
    let entries = root_subdirectory(directory, c".")?;
    let got = std::fs::read_dir(format!("/proc/self/fd/{}", entries.as_raw_fd()))?
        .take(expected.len() + 1)
        .map(|entry| entry.map(|entry| entry.file_name()))
        .collect::<io::Result<BTreeSet<_>>>()?;
    let expected = expected
        .iter()
        .map(|name| OsString::from(*name))
        .collect::<BTreeSet<_>>();
    if got != expected {
        return Err(NamespaceError::Rejected(
            "private Binder directory inventory differs",
        ));
    }
    Ok(())
}

fn distinct_devices(control: DeviceIdentity, devices: &[DeviceIdentity; 3]) -> bool {
    let major = libc::major(control.rdev);
    devices.iter().enumerate().all(|(index, value)| {
        value.node.device == control.node.device
            && value.node.inode == u64::from(libc::minor(value.rdev)) + 3
            && libc::major(value.rdev) == major
            && value.rdev != control.rdev
            && devices[..index]
                .iter()
                .all(|prior| prior.rdev != value.rdev && prior.node.inode != value.node.inode)
    })
}

impl IsolatedNamespaces {
    /// Construct only three new isolated contexts after the proc/DEV barriers.
    /// There is no context-manager registration, arbitrary input or Android exec.
    pub(crate) fn prepare_private_binder(mut self) -> Result<Self> {
        self.verify_live_admission()?;
        if self.binder.is_some() || !self.empty_root || !self.private_devices {
            return Err(NamespaceError::Rejected(
                "Binder requires one prepared process-filesystem barrier",
            ));
        }
        let process = self
            .process_filesystems
            .ok_or(NamespaceError::Rejected("process filesystems absent"))?;
        let bases = self
            .base_devices
            .ok_or(NamespaceError::Rejected("base custody absent"))?;
        let dev = self
            .device_node
            .ok_or(NamespaceError::Rejected("private DEV custody absent"))?;
        let init = self
            .init
            .as_ref()
            .ok_or(NamespaceError::Rejected("PID 1 absent"))?;
        init.verify_process_filesystems(bases, dev, Some(process))?;
        send_packet(
            init.control.as_raw_fd(),
            &Packet::new(init.nonce, Phase::PrepareBinder, 0, init.parent_pid),
        )?;
        init.receive_phase(Phase::BinderReady)?;
        let observed = init.verify_private_binder(bases, dev, process, None)?;
        self.binder = Some(observed);
        self.verify_live_admission()?;
        Ok(self)
    }
}

impl TreeChild {
    fn verify_private_binder(
        &self,
        bases: [u64; 2],
        dev_node: Node,
        process: ProcessFilesystems,
        prior: Option<BinderFilesystem>,
    ) -> Result<BinderFilesystem> {
        self.verify()?;
        let root = held_child_root(self)?;
        let dev = root_subdirectory(&root, c"dev")?;
        let binder = root_subdirectory(&dev, c"binderfs")?;
        let root_node = Node::of(&binder)?;
        let meta = binder.metadata()?;
        if meta.mode() != (libc::S_IFDIR | 0o755)
            || meta.ino() != 1
            || meta.uid() != self.uids.start
            || meta.gid() != self.gids.start
            || [
                root.metadata()?.dev(),
                dev_node.device,
                process.proc.device,
                process.pts.device,
                bases[0],
                bases[1],
            ]
            .contains(&root_node.device)
        {
            return Err(NamespaceError::Rejected(
                "private Binder instance aliases an existing filesystem",
            ));
        }
        verify_process_statfs(&binder, BINDERFS_MAGIC, 2 | 8, 1 | 4)?;
        names(
            &binder,
            &[
                "binder-control",
                "features",
                "binder",
                "hwbinder",
                "vndbinder",
            ],
        )?;
        let control = open_path(&binder, c"binder-control")?;
        let cm = control.metadata()?;
        if cm.dev() != root_node.device
            || cm.ino() != 2
            || cm.mode() != (libc::S_IFCHR | 0o600)
            || cm.uid() != self.uids.start
            || cm.gid() != self.gids.start
            || cm.nlink() != 1
        {
            return Err(NamespaceError::Rejected(
                "private Binder control inode differs",
            ));
        }
        let control = DeviceIdentity {
            node: Node::of(&control)?,
            rdev: cm.rdev(),
        };
        let mut devices = Vec::new();
        for (name, target) in [
            (c"binder", b"binderfs/binder".as_slice()),
            (c"hwbinder", b"binderfs/hwbinder".as_slice()),
            (c"vndbinder", b"binderfs/vndbinder".as_slice()),
        ] {
            let held = open_path(&binder, name)?;
            let dm = held.metadata()?;
            if dm.dev() != root_node.device
                || dm.mode() != (libc::S_IFCHR | 0o666)
                || dm.uid() != self.uids.start
                || dm.gid() != self.gids.start
                || dm.nlink() != 1
            {
                return Err(NamespaceError::Rejected(
                    "private Binder context inode differs",
                ));
            }
            devices.push(DeviceIdentity {
                node: Node::of(&held)?,
                rdev: dm.rdev(),
            });
            let link = open_path(&dev, name)?;
            let lm = link.metadata()?;
            let mut bytes = [0_u8; 64];
            let size = unsafe {
                libc::readlinkat(
                    dev.as_raw_fd(),
                    name.as_ptr(),
                    bytes.as_mut_ptr().cast(),
                    bytes.len(),
                )
            };
            if lm.dev() != dev_node.device
                || lm.mode() != (libc::S_IFLNK | 0o777)
                || lm.uid() != self.uids.start
                || lm.gid() != self.gids.start
                || lm.nlink() != 1
                || size != target.len() as isize
                || &bytes[..target.len()] != target
            {
                return Err(NamespaceError::Rejected(
                    "private Binder alias is not the fixed relative link",
                ));
            }
        }
        let devices: [DeviceIdentity; 3] = devices
            .try_into()
            .map_err(|_| NamespaceError::Rejected("three Binder contexts required"))?;
        if !distinct_devices(control, &devices) {
            return Err(NamespaceError::Rejected(
                "private Binder contexts are not distinct",
            ));
        }

        let features = root_subdirectory(&binder, c"features")?;
        let fm = features.metadata()?;
        if fm.dev() != root_node.device
            || fm.mode() != (libc::S_IFDIR | 0o755)
            || fm.uid() != self.uids.start
            || fm.gid() != self.gids.start
        {
            return Err(NamespaceError::Rejected(
                "private Binder feature directory differs",
            ));
        }
        names(
            &features,
            &[
                "oneway_spam_detection",
                "extended_error",
                "freeze_notification",
                "transaction_report",
            ],
        )?;
        for name in [
            c"oneway_spam_detection",
            c"extended_error",
            c"freeze_notification",
            c"transaction_report",
        ] {
            let raw = unsafe {
                libc::openat(
                    features.as_raw_fd(),
                    name.as_ptr(),
                    libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC,
                )
            };
            if raw < 0 {
                return Err(io::Error::last_os_error().into());
            }
            let mut file = unsafe { File::from_raw_fd(raw) };
            let before = file.metadata()?;
            let mut bytes = [0_u8; 3];
            let count = file.read(&mut bytes)?;
            let after = file.metadata()?;
            if before.dev() != root_node.device
                || before.mode() != (libc::S_IFREG | 0o444)
                || before.nlink() != 1
                || before.uid() != self.uids.start
                || before.gid() != self.gids.start
                || count != 2
                || &bytes[..2] != b"1\n"
                || file.read(&mut bytes)? != 0
                || before.dev() != after.dev()
                || before.ino() != after.ino()
                || before.mode() != after.mode()
                || before.uid() != after.uid()
                || before.gid() != after.gid()
            {
                return Err(NamespaceError::Rejected(
                    "private Binder kernel feature differs",
                ));
            }
        }
        let got = BinderFilesystem {
            root: root_node,
            control,
            devices,
        };
        if prior.is_some_and(|expected| expected != got) {
            return Err(NamespaceError::Rejected(
                "private Binder identities changed after the barrier",
            ));
        }
        self.verify_process_filesystems_with_binder(bases, dev_node, Some(process), Some(got))?;
        self.verify()?;
        Ok(got)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::production_identity::tests::broker_fixture;
    use std::fs;

    #[test]
    fn binder_mount_policy_rejects_inherited_global_or_device_disabled_mounts() {
        assert!(mount_options(
            "/dev/binderfs",
            "/",
            "rw,nosuid,noexec,relatime",
            "rw,max=3"
        ));
        for (path, root, flags, options) in [
            ("/dev/binder", "/", "rw,nosuid,noexec", "rw,max=3"),
            ("/dev/binderfs", "/subdir", "rw,nosuid,noexec", "rw,max=3"),
            ("/dev/binderfs", "/", "rw,nosuid,nodev,noexec", "rw,max=3"),
            ("/dev/binderfs", "/", "ro,nosuid,noexec", "rw,max=3"),
            ("/dev/binderfs", "/", "rw,nosuid", "rw,max=3"),
            ("/dev/binderfs", "/", "rw,noexec", "rw,max=3"),
            ("/dev/binderfs", "/", "rw,nosuid,noexec", "rw,max=4"),
            (
                "/dev/binderfs",
                "/",
                "rw,nosuid,noexec",
                "rw,max=3,stats=global",
            ),
            ("/dev/binderfs", "/", "rw,nosuid,noexec", "rw,max=3,max=3"),
        ] {
            assert!(!mount_options(path, root, flags, options));
        }
    }

    #[test]
    fn binder_context_inventory_rejects_alias_and_foreign_major() {
        let control = DeviceIdentity {
            node: Node {
                device: 9,
                inode: 2,
            },
            rdev: libc::makedev(511, 0),
        };
        let values = [1_u32, 2, 3].map(|minor| DeviceIdentity {
            node: Node {
                device: 9,
                inode: u64::from(minor) + 3,
            },
            rdev: libc::makedev(511, minor),
        });
        assert!(distinct_devices(control, &values));
        let mut wrong = values;
        wrong[2] = wrong[0];
        assert!(!distinct_devices(control, &wrong));
        let mut wrong = values;
        wrong[1].rdev = libc::makedev(510, 2);
        assert!(!distinct_devices(control, &wrong));
        let mut wrong = values;
        wrong[0].node.device = 10;
        assert!(!distinct_devices(control, &wrong));
        let mut wrong = values;
        wrong[0].node.inode += 1;
        assert!(!distinct_devices(control, &wrong));
    }

    fn children() -> String {
        let tid = unsafe { libc::syscall(libc::SYS_gettid) };
        fs::read_to_string(format!("/proc/self/task/{tid}/children")).unwrap()
    }
    fn lease_available(root: &std::path::Path) -> bool {
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .open(root.join("registry/u1000.lease"))
            .unwrap();
        let rc = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) };
        if rc == 0 {
            assert_eq!(unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_UN) }, 0);
            true
        } else {
            assert_eq!(io::Error::last_os_error().kind(), io::ErrorKind::WouldBlock);
            false
        }
    }
    fn mapped_private(lease: IdentityLease, mode: child::Mode) -> MappedUserNamespace {
        let mut owner = Owner::spawn(Some(lease), mode).unwrap();
        owner.enter_userns().unwrap();
        let (uids, gids) = owner.install_maps().unwrap();
        owner.mapped_go(uids, gids).unwrap();
        MappedUserNamespace { owner }
    }
    fn prepared(lease: IdentityLease, mode: child::Mode, probes: bool) -> IsolatedNamespaces {
        let tree = IsolatedNamespaces::from_mapped(mapped_private(lease, mode)).unwrap();
        let bases = crate::production_mounts::private_control::prepare_private_control_mounts(
            &tree.witness().unwrap(),
        )
        .unwrap();
        let tree = tree
            .attach_base_inner(BaseMounts::PrivateControl(bases))
            .unwrap();
        if probes {
            let init = tree.init.as_ref().unwrap();
            send_packet(
                init.control.as_raw_fd(),
                &Packet::new(init.nonce, Phase::ProbeEmptyRoot, 0, init.parent_pid),
            )
            .unwrap();
            init.receive_phase(Phase::EmptyRootChecked).unwrap();
        }
        let devices = crate::production_devices::private_control::prepare_private_control_devices(
            &tree.witness().unwrap(),
        )
        .unwrap();
        let tree = tree
            .attach_device_inner(DeviceMounts::PrivateControl(devices))
            .unwrap();
        if probes {
            let init = tree.init.as_ref().unwrap();
            send_packet(
                init.control.as_raw_fd(),
                &Packet::new(init.nonce, Phase::ProbePrivateDev, 0, init.parent_pid),
            )
            .unwrap();
            init.receive_phase(Phase::PrivateDevChecked).unwrap();
        }
        let tree = tree.prepare_process_filesystems().unwrap();
        if probes {
            let init = tree.init.as_ref().unwrap();
            send_packet(
                init.control.as_raw_fd(),
                &Packet::new(
                    init.nonce,
                    Phase::ProbeProcessFilesystems,
                    0,
                    init.parent_pid,
                ),
            )
            .unwrap();
            init.receive_phase(Phase::ProcessFilesystemsChecked)
                .unwrap();
        }
        tree
    }

    #[test]
    #[ignore = "requires separately reviewed root private Binder-major, loop and namespace control"]
    fn privileged_private_binder_controls() {
        assert_eq!(unsafe { libc::getuid() }, 0);
        assert_eq!(unsafe { libc::geteuid() }, 0);
        let original_children = children();
        let original_mounts = fs::read("/proc/self/mountinfo").unwrap();
        let original_uid = fs::read("/proc/self/uid_map").unwrap();
        let original_gid = fs::read("/proc/self/gid_map").unwrap();
        let namespace_nodes = || {
            ["user", "pid", "mnt", "ipc", "uts", "net", "cgroup"].map(|name| {
                Node::of(&File::open(format!("/proc/self/ns/{name}")).unwrap()).unwrap()
            })
        };
        let before_namespaces = namespace_nodes();
        let (identity_root, lease) = broker_fixture();
        let tree = prepared(lease, child::Mode::BinderControl, true);
        let mut tree = tree.prepare_private_binder().unwrap();
        let binder = tree.binder.unwrap();
        let process = tree.process_filesystems.unwrap();
        let bases = tree.base_devices.unwrap();
        let dev = tree.device_node.unwrap();
        let init = tree.init.as_ref().unwrap();
        let fd_names = || {
            fs::read_dir(format!("/proc/{}/fd", init.identity.pid))
                .unwrap()
                .map(|row| row.unwrap().file_name())
                .collect::<Vec<_>>()
        };
        assert_eq!(fd_names(), [OsString::from("3")]);
        init.verify_private_binder(bases, dev, process, Some(binder))
            .unwrap();
        send_packet(
            init.control.as_raw_fd(),
            &Packet::new(init.nonce, Phase::ProbeBinder, 0, init.parent_pid),
        )
        .unwrap();
        init.receive_phase(Phase::BinderChecked).unwrap();
        init.verify_private_binder(bases, dev, process, Some(binder))
            .unwrap();
        assert_eq!(fd_names(), [OsString::from("3")]);
        match tree.bases.as_ref().unwrap() {
            BaseMounts::PrivateControl(value) => value.verify_images_unchanged().unwrap(),
            _ => panic!("private control cannot create production admission"),
        }
        assert!(!lease_available(identity_root.path()));
        {
            let retired = tree.reap_init().unwrap();
            assert_eq!(retired.tree.init.as_ref().unwrap().namespaces.held.len(), 1);
            assert_eq!(
                retired.tree.init.as_ref().unwrap().namespaces.held[0].1,
                libc::CLONE_NEWPID
            );
            assert!(retired.tree.init.as_ref().unwrap().proc_mount.is_none());
            assert!(!lease_available(identity_root.path()));
        }
        let exit = tree.retire().unwrap();
        assert_eq!((exit.init.reason, exit.init.status), (libc::CLD_EXITED, 0));
        assert_eq!(
            (exit.keeper.reason, exit.keeper.status),
            (libc::CLD_EXITED, 0)
        );
        assert!(lease_available(identity_root.path()));
        assert_eq!(children(), original_children);
        println!(
            "private Binder control: fresh max3 binderfs and three distinct protocol8 contexts; no host Binder path or FD; actual private TXN_SECURITY_CTX UID10001 and reply in each context; atomic PIDFD client reap; fd3 only; PID1, live namespace, DEV/loops and keeper retired; Android=0 production admission=false"
        );

        for negative in ["wrong_nonce", "extra_fd", "wrong_phase"] {
            let (identity_root, lease) = broker_fixture();
            let tree = prepared(lease, child::Mode::UserNamespace, false);
            let init = tree.init.as_ref().unwrap();
            let mut nonce = init.nonce;
            if negative == "wrong_nonce" {
                nonce[0] ^= 1;
            }
            let phase = if negative == "wrong_phase" {
                Phase::PrepareProcessFilesystems
            } else {
                Phase::PrepareBinder
            };
            let packet = Packet::new(nonce, phase, 0, init.parent_pid);
            if negative == "extra_fd" {
                let unrelated = OpenOptions::new()
                    .read(true)
                    .custom_flags(libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                    .open("/dev/null")
                    .unwrap();
                send_one_fd(init.control.as_raw_fd(), &packet, unrelated.as_fd()).unwrap();
            } else {
                send_packet(init.control.as_raw_fd(), &packet).unwrap();
            }
            assert!(init.receive_phase(Phase::BinderReady).is_err());
            let exit = tree.retire().unwrap();
            assert_eq!(exit.init.reason, libc::CLD_EXITED);
            assert_ne!(exit.init.status, 0);
            assert_eq!(
                (exit.keeper.reason, exit.keeper.status),
                (libc::CLD_EXITED, 0)
            );
            assert!(lease_available(identity_root.path()));
            assert_eq!(children(), original_children);
            assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
            println!(
                "private Binder negative: {negative}; zero-external-FD gate rejected before ready; same tree and lease retired"
            );
        }
        assert_eq!(fs::read("/proc/self/uid_map").unwrap(), original_uid);
        assert_eq!(fs::read("/proc/self/gid_map").unwrap(), original_gid);
        assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
        assert_eq!(namespace_nodes(), before_namespaces);
    }
}
