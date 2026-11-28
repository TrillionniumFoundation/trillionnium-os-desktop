//! Actual MAC observation of the fixed owned activation listener.
//!
//! A socket pathname, serialized label or input digest cannot construct this
//! witness. The device owner lends the existing sock_file and server socket,
//! and rechecks the original private DEV, namespace, named inode and lease.
//! This observer does not bind, relabel, chmod or execute anything.

use super::*;
use crate::production_devices::OwnedActivationListener;

const LISTENER_FILE: &str = "u:object_r:droidloom_linkerconfig_socket:s0";

fn actual_listener<T>(
    value: std::result::Result<T, crate::production_devices::DeviceError>,
) -> Result<T> {
    value.map_err(|error| match error {
        crate::production_devices::DeviceError::Io(error) => MacError::Io(error),
        other => MacError::Owner(other.to_string()),
    })
}

/// O_PATH is rejected by fgetxattr and, on the exact target kernel, by the
/// fdget branch of getxattrat(AT_EMPTY_PATH) too. Follow only this calling
/// process's already held FD alias, never an externally supplied pathname.
/// The production caller brackets this with the complete device owner check.
fn held_alias_attribute(file: &File, name: &CStr) -> Result<Vec<u8>> {
    let before = Node::of(file)?;
    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    if flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        flags & libc::O_PATH != 0,
        "named socket must retain its actual O_PATH inode",
    )?;
    let alias = CString::new(format!("/proc/self/fd/{}", file.as_raw_fd()))
        .map_err(|_| MacError::Rejected("invalid held FD alias"))?;
    let mut value = [0_u8; 1024];
    let size = unsafe {
        libc::getxattr(
            alias.as_ptr(),
            name.as_ptr(),
            value.as_mut_ptr().cast(),
            value.len(),
        )
    };
    if size < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        size > 0 && size as usize <= value.len(),
        "bounded actual held-inode label",
    )?;
    require(
        Node::of(file)? == before,
        "held socket inode changed during attribute read",
    )?;
    Ok(value[..size as usize].to_vec())
}

pub(super) fn server_label(server: BorrowedFd<'_>) -> Result<Vec<u8>> {
    let before = descriptor_identity(server)?;
    require(
        before.kind == libc::S_IFSOCK,
        "activation server is not an actual socket FD",
    )?;
    let mut value = [0_u8; 1024];
    // This is the socket's own sockfs security inode, not SO_PEERSEC on an
    // unconnected listener. Unsupported/absent security state remains Err.
    let size = unsafe {
        libc::fgetxattr(
            server.as_raw_fd(),
            c"security.selinux".as_ptr(),
            value.as_mut_ptr().cast(),
            value.len(),
        )
    };
    if size < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        size > 0 && size as usize <= value.len(),
        "bounded actual server socket label",
    )?;
    require(
        descriptor_identity(server)? == before,
        "actual server socket inode changed",
    )?;
    Ok(value[..size as usize].to_vec())
}

fn decisions(mac: &MacPreflight) -> Result<()> {
    let mut sequence = Some(mac.loaded.av_sequence);
    access(
        &mac.loaded.root,
        BROKER,
        BROKER,
        "unix_stream_socket",
        &[
            "create", "bind", "listen", "accept", "getattr", "read", "write", "getopt", "setopt",
        ],
        true,
        &mut sequence,
    )?;
    access(
        &mac.loaded.root,
        BROKER,
        LISTENER_FILE,
        "sock_file",
        &["create", "getattr", "setattr", "write"],
        true,
        &mut sequence,
    )?;
    access(
        &mac.loaded.root,
        LINKERCONFIG,
        BROKER,
        "unix_stream_socket",
        &["connectto"],
        true,
        &mut sequence,
    )?;
    access(
        &mac.loaded.root,
        LINKERCONFIG,
        LISTENER_FILE,
        "sock_file",
        &["write"],
        true,
        &mut sequence,
    )?;
    // The original ELF's passed file description was opened by this broker.
    access(
        &mac.loaded.root,
        LINKERCONFIG,
        BROKER,
        "fd",
        &["use"],
        true,
        &mut sequence,
    )?;
    access(
        &mac.loaded.root,
        HOST,
        BROKER,
        "unix_stream_socket",
        &["connectto"],
        false,
        &mut sequence,
    )?;
    access(
        &mac.loaded.root,
        HOST,
        LISTENER_FILE,
        "sock_file",
        &["write"],
        false,
        &mut sequence,
    )
}

/// Live MAC binding only. The separate original device owner retains the
/// listener and its filesystem resources; this value grants no command/Ready.
pub(crate) struct MacListenerWitness {
    provider: ProviderBinding,
    file: Node,
    server: DescriptorIdentity,
}

impl MacPreflight {
    pub(crate) fn observe_linkerconfig_listener(
        &self,
        listener: &OwnedActivationListener<'_>,
    ) -> Result<MacListenerWitness> {
        actual_listener(listener.revalidate())?;
        self.revalidate(listener.selection())?;
        let witness = MacListenerWitness {
            provider: self.binding(),
            file: Node::of(listener.sock_file())?,
            server: descriptor_identity(listener.server())?,
        };
        witness.revalidate(self, listener)?;
        Ok(witness)
    }
}

impl MacListenerWitness {
    pub(crate) fn revalidate(
        &self,
        mac: &MacPreflight,
        listener: &OwnedActivationListener<'_>,
    ) -> Result<()> {
        require(
            self.provider == mac.binding(),
            "listener witness belongs to another live MAC provider",
        )?;
        mac.revalidate(listener.selection())?;
        actual_listener(listener.revalidate())?;
        actual_listener(listener.revalidate_context_provider(mac))?;
        require(
            Node::of(listener.sock_file())? == self.file
                && self.file.mode & libc::S_IFMT == libc::S_IFSOCK
                && descriptor_identity(listener.server())? == self.server,
            "original activation listener descriptors changed",
        )?;
        require(
            context_matches(
                &held_alias_attribute(listener.sock_file(), c"security.selinux")?,
                LISTENER_FILE,
            ),
            "actual fixed sock_file has another SELinux label",
        )?;
        require(
            context_matches(&server_label(listener.server())?, BROKER),
            "actual server socket was not created in the broker SELinux domain",
        )?;
        decisions(mac)?;
        actual_listener(listener.revalidate_context_provider(mac))?;
        actual_listener(listener.revalidate())?;
        mac.revalidate(listener.selection())?;
        require(
            Node::of(listener.sock_file())? == self.file
                && descriptor_identity(listener.server())? == self.server,
            "listener changed during actual MAC decisions",
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::OpenOptionsExt;

    #[test]
    fn held_path_attribute_uses_original_inode_after_path_replacement() {
        let temp = tempfile::tempdir().unwrap();
        let named = temp.path().join("node");
        std::fs::write(&named, b"first").unwrap();
        let original = File::open(&named).unwrap();
        let value = b"original";
        assert_eq!(
            unsafe {
                libc::fsetxattr(
                    original.as_raw_fd(),
                    c"user.droidloom.control".as_ptr(),
                    value.as_ptr().cast(),
                    value.len(),
                    libc::XATTR_CREATE,
                )
            },
            0
        );
        let held = std::fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&named)
            .unwrap();
        let before = Node::of(&held).unwrap();
        std::fs::rename(&named, temp.path().join("old")).unwrap();
        std::fs::write(&named, b"replacement").unwrap();
        assert!(Node::of(&held).unwrap().same_inode(before));
        assert!(
            !Node::of(&File::open(&named).unwrap())
                .unwrap()
                .same_inode(before)
        );
        let mut byte = [0_u8; 32];
        assert_eq!(
            unsafe {
                libc::fgetxattr(
                    held.as_raw_fd(),
                    c"user.droidloom.control".as_ptr(),
                    byte.as_mut_ptr().cast(),
                    byte.len(),
                )
            },
            -1
        );
        assert_eq!(io::Error::last_os_error().raw_os_error(), Some(libc::EBADF));
        assert_eq!(
            held_alias_attribute(&held, c"user.droidloom.control").unwrap(),
            value
        );
        match held_alias_attribute(&held, c"user.droidloom.absent") {
            Err(MacError::Io(error)) => assert_eq!(error.raw_os_error(), Some(libc::ENODATA)),
            _ => panic!("absent actual attribute did not retain exact ENODATA"),
        }
    }
}
