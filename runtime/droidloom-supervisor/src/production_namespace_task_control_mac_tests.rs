use super::*;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::os::unix::net::UnixDatagram;

fn deadline() -> Instant {
    Instant::now() + Duration::from_secs(5)
}

fn socket_inode(path: &std::path::Path) -> File {
    std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_PATH | libc::O_CLOEXEC | libc::O_NOFOLLOW)
        .open(path)
        .unwrap()
}

fn pair() -> (File, File) {
    let mut fds = [-1_i32; 2];
    assert_eq!(
        unsafe {
            libc::socketpair(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
                0,
                fds.as_mut_ptr(),
            )
        },
        0,
    );
    unsafe { (File::from_raw_fd(fds[0]), File::from_raw_fd(fds[1])) }
}

#[test]
fn task_control_context_frames_keep_raw_bytes_and_reject_unbounded_records() {
    // Synthetic opaque observations have no selected-policy interpretation.
    // In particular, accepting an LSM's bytes is not SELinux-domain evidence.
    for raw in [
        b"synthetic-inode-observation".to_vec(),
        b"synthetic peer LSM observation\0".to_vec(),
        (0_u8..=255).collect(),
        vec![0],
        vec![b'a'; CONTEXT_LIMIT],
    ] {
        assert_eq!(bounded_observation(raw.clone()).unwrap(), raw);
    }
    for raw in [Vec::new(), vec![b'a'; CONTEXT_LIMIT + 1]] {
        assert!(bounded_observation(raw).is_err());
    }
}

#[test]
fn task_control_inode_read_rejects_wrong_objects_before_attribute_io() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("ordinary");
    std::fs::write(&path, b"owned private fixture").unwrap();
    let regular = socket_inode(&path);
    assert!(
        InodeSelinuxContext::observe(&regular, deadline(), |_| {
            panic!("regular file must not reach the xattr reader")
        })
        .is_err()
    );
    let (connected, _other) = pair();
    assert!(
        InodeSelinuxContext::observe(&connected, deadline(), |_| {
            panic!("connected socket must not substitute for the O_PATH server inode")
        })
        .is_err()
    );
}

#[test]
fn task_control_inode_alias_retains_original_after_name_replacement() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("endpoint");
    let original_socket = UnixDatagram::bind(&path).unwrap();
    let held = socket_inode(&path);
    let original = Node::of(&held).unwrap();
    std::fs::rename(&path, directory.path().join("retained-original")).unwrap();
    let replacement = UnixDatagram::bind(&path).unwrap();
    let replacement_inode = socket_inode(&path);
    assert_ne!(Node::of(&replacement_inode).unwrap(), original);
    let observed = InodeSelinuxContext::observe(&held, deadline(), |alias| {
        let actual = std::fs::metadata(std::ffi::OsStr::from_bytes(alias.to_bytes()))?;
        assert_eq!(
            (actual.dev(), actual.ino()),
            (original.device, original.inode)
        );
        Ok(b"synthetic-inode-observation\0".to_vec())
    })
    .unwrap();
    assert_eq!(
        observed.seal.integers[0..2],
        [original.device, original.inode]
    );
    // The inode/alias check above is real. The injected bytes only exercise
    // storage and do not claim a successful native xattr or selected policy.
    drop((original_socket, replacement));
}

#[test]
fn task_control_inode_change_during_label_read_is_rejected() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("endpoint");
    let _socket = UnixDatagram::bind(&path).unwrap();
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o660)).unwrap();
    let held = socket_inode(&path);
    assert!(
        InodeSelinuxContext::observe(&held, deadline(), |_| {
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))?;
            Ok(b"synthetic-inode-observation\0".to_vec())
        })
        .is_err()
    );
    assert_eq!(held.metadata().unwrap().mode() & 0o777, 0o600);
}

#[test]
fn task_control_context_errors_and_original_deadline_are_not_replaced() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("endpoint");
    let _socket = UnixDatagram::bind(&path).unwrap();
    let held = socket_inode(&path);
    let error = InodeSelinuxContext::observe(&held, deadline(), |_| {
        Err(io::Error::from_raw_os_error(libc::ERANGE).into())
    })
    .err()
    .unwrap();
    assert!(
        matches!(error, NamespaceError::Io(error) if error.raw_os_error() == Some(libc::ERANGE))
    );
    assert!(
        InodeSelinuxContext::observe(&held, Instant::now(), |_| {
            panic!("expired original deadline must prevent the context read")
        })
        .is_err()
    );
}

#[test]
fn task_control_peer_observation_rejects_other_connection_and_context_change() {
    let (socket, _peer) = pair();
    let (other, _other_peer) = pair();
    // Real distinct socket inodes; synthetic SO_PEERSEC bytes only. There is
    // no mocked Ready, listener PIDFD, Composer, or selected-policy witness.
    let label = b"synthetic-peer-lsm-observation\0";
    let original =
        ConnectionPeerSecurity::observe(&socket, deadline(), |_| Ok(label.to_vec())).unwrap();
    let repeated =
        ConnectionPeerSecurity::observe(&socket, deadline(), |_| Ok(label.to_vec())).unwrap();
    original.check_observation(&repeated).unwrap();
    let replaced =
        ConnectionPeerSecurity::observe(&other, deadline(), |_| Ok(label.to_vec())).unwrap();
    assert!(original.check_observation(&replaced).is_err());
    let changed = ConnectionPeerSecurity::observe(&socket, deadline(), |_| {
        Ok(b"different-peer-lsm-observation\0".to_vec())
    })
    .unwrap();
    assert!(original.check_observation(&changed).is_err());
    let terminator_changed = ConnectionPeerSecurity::observe(&socket, deadline(), |_| {
        Ok(b"synthetic-peer-lsm-observation".to_vec())
    })
    .unwrap();
    assert!(original.check_observation(&terminator_changed).is_err());
    let error = ConnectionPeerSecurity::observe(&socket, deadline(), |_| {
        Err(io::Error::from_raw_os_error(libc::EOPNOTSUPP).into())
    })
    .err()
    .unwrap();
    assert!(
        matches!(error, NamespaceError::Io(error) if error.raw_os_error() == Some(libc::EOPNOTSUPP))
    );
    assert!(
        ConnectionPeerSecurity::observe(&socket, Instant::now(), |_| {
            panic!("expired deadline must not query another peer context")
        })
        .is_err()
    );
}
