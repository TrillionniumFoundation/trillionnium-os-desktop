//! Live MAC binding of the authenticated, original systemd lifetime owner.
//!
//! This observer cannot create a manager connection, adopt a PID, install a
//! unit, relabel a socket, signal a process, or issue Android readiness. The
//! cgroup owner supplies its existing kernel-authenticated manager connection
//! and original process/Invocation generation. The loaded MAC provider must
//! independently observe the same live manager and the fixed server inode.

use super::*;
use crate::production_cgroup::{CgroupError, SystemdOwnerGeneration, SystemdOwnerWitness};

const MANAGER_FILE: &str = "u:object_r:droidloom_manager_private_socket:s0";
const AA_MANAGER: &[u8] = b"unconfined\n";

fn original_systemd<T>(value: std::result::Result<T, CgroupError>) -> Result<T> {
    value.map_err(|error| match error {
        CgroupError::Io(error) => MacError::Io(error),
        other => MacError::Owner(other.to_string()),
    })
}

/// This is the O_PATH inode of /run/systemd/private held by the original
/// manager channel. Its connected client socket is a different kernel object
/// and cannot be used as evidence for the server sock_file label.
fn manager_file_context(file: &File) -> Result<Vec<u8>> {
    let before = Node::of(file)?;
    require(
        before.mode & libc::S_IFMT == libc::S_IFSOCK,
        "manager sock_file must be the actual held socket inode",
    )?;
    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    if flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        flags & libc::O_PATH != 0,
        "manager server inode must remain an original O_PATH descriptor",
    )?;
    // The exact target kernel rejects O_PATH in fgetxattr/getxattrat's fdget
    // branch. Follow only this process's owned FD alias; its owner brackets
    // this read with actual parent and named-inode revalidation.
    let alias = CString::new(format!("/proc/self/fd/{}", file.as_raw_fd()))
        .map_err(|_| MacError::Rejected("invalid original manager FD alias"))?;
    let mut bytes = [0_u8; 1024];
    let count = unsafe {
        libc::getxattr(
            alias.as_ptr(),
            c"security.selinux".as_ptr(),
            bytes.as_mut_ptr().cast(),
            bytes.len(),
        )
    };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        count > 0 && count as usize <= bytes.len(),
        "bounded actual manager server-inode label required",
    )?;
    require(
        Node::of(file)? == before,
        "manager server inode changed during its actual label observation",
    )?;
    Ok(bytes[..count as usize].to_vec())
}

fn systemd_decisions(mac: &MacPreflight) -> Result<()> {
    let mut sequence = Some(mac.loaded.av_sequence);
    access(
        &mac.loaded.root,
        BROKER,
        BROKER,
        "unix_stream_socket",
        &[
            "create", "connect", "getattr", "read", "write", "getopt", "setopt",
        ],
        true,
        &mut sequence,
    )?;
    access(
        &mac.loaded.root,
        BROKER,
        HOST,
        "unix_stream_socket",
        &["connectto"],
        true,
        &mut sequence,
    )?;
    access(
        &mac.loaded.root,
        BROKER,
        MANAGER_FILE,
        "sock_file",
        &["getattr", "write"],
        true,
        &mut sequence,
    )?;
    // GetUnitByPIDFD actually receives the original broker-created PIDFD.
    access(&mac.loaded.root, HOST, BROKER, "fd", &["use"], true, &mut sequence)?;
    access(
        &mac.loaded.root,
        BROKER,
        HOST,
        "process",
        &["getattr"],
        true,
        &mut sequence,
    )?;
    // This preflight covers the broker and fixed bootstrap roles. The
    // selected policy's complete Android service-domain closure and actual
    // dual-LSM daemon-death retirement remain separate activation gates.
    for target in [
        BROKER,
        INIT,
        "u:r:apexd:s0",
        LINKERCONFIG,
        "u:r:droidloom_query:s0",
    ] {
        access(
            &mac.loaded.root,
            HOST,
            target,
            "process",
            &["getattr", "signull", "signal", "sigkill", "sigstop"],
            true,
            &mut sequence,
        )?;
    }
    for source in [INIT, "u:r:apexd:s0", LINKERCONFIG, "u:r:droidloom_query:s0"] {
        access(
            &mac.loaded.root,
            source,
            HOST,
            "unix_stream_socket",
            &["connectto"],
            false,
            &mut sequence,
        )?;
        access(
            &mac.loaded.root,
            source,
            MANAGER_FILE,
            "sock_file",
            &["write"],
            false,
            &mut sequence,
        )?;
    }
    Ok(())
}

/// Equality binding of live kernel observations only. Successful validation
/// does not manufacture process ownership or certify an unexecuted MAC fault
/// fixture; callers must retain the actual owner and all later phase gates.
pub(crate) struct MacSystemdWitness {
    provider: ProviderBinding,
    generation: SystemdOwnerGeneration,
    boot: String,
    manager_pidfd: DescriptorIdentity,
    manager_proc: DescriptorIdentity,
    broker_pidfd: DescriptorIdentity,
    broker_proc: DescriptorIdentity,
    connection: DescriptorIdentity,
    server_file: Node,
    _same_thread: PhantomData<Rc<()>>,
}

impl MacPreflight {
    pub(crate) fn observe_systemd_owner(
        &self,
        owner: &SystemdOwnerWitness<'_>,
    ) -> Result<MacSystemdWitness> {
        self.revalidate(owner.selection())?;
        original_systemd(owner.revalidate())?;
        let value = MacSystemdWitness {
            provider: self.binding(),
            generation: original_systemd(owner.generation())?,
            boot: self.loaded.boot.clone(),
            manager_pidfd: descriptor_identity(owner.manager_pidfd())?,
            manager_proc: descriptor_identity(owner.manager_proc().as_fd())?,
            broker_pidfd: descriptor_identity(owner.broker_pidfd())?,
            broker_proc: descriptor_identity(owner.broker_proc().as_fd())?,
            connection: descriptor_identity(owner.manager_connection().as_fd())?,
            server_file: Node::of(owner.manager_socket_file())?,
            _same_thread: PhantomData,
        };
        value.revalidate(self, owner)?;
        Ok(value)
    }
}

impl MacSystemdWitness {
    fn original_descriptors(&self, owner: &SystemdOwnerWitness<'_>) -> Result<()> {
        require(
            descriptor_identity(owner.manager_pidfd())? == self.manager_pidfd
                && descriptor_identity(owner.manager_proc().as_fd())? == self.manager_proc
                && descriptor_identity(owner.broker_pidfd())? == self.broker_pidfd
                && descriptor_identity(owner.broker_proc().as_fd())? == self.broker_proc
                && descriptor_identity(owner.manager_connection().as_fd())? == self.connection
                && Node::of(owner.manager_socket_file())? == self.server_file,
            "original systemd PIDFD/proc/connection/server-inode custody changed",
        )
    }

    pub(crate) fn revalidate(
        &self,
        mac: &MacPreflight,
        owner: &SystemdOwnerWitness<'_>,
    ) -> Result<()> {
        require(
            self.provider == mac.binding() && self.boot == mac.loaded.boot,
            "systemd MAC witness belongs to another provider or boot",
        )?;
        mac.revalidate(owner.selection())?;
        original_systemd(owner.revalidate())?;
        require(
            original_systemd(owner.generation())? == self.generation,
            "original systemd manager/broker start or unit Invocation changed",
        )?;
        self.original_descriptors(owner)?;
        require(
            self.connection.kind == libc::S_IFSOCK,
            "actual manager connection is not a socket",
        )?;
        require(
            context_matches(&proc_attr(owner.manager_proc(), false)?, HOST),
            "actual original PID1 is not in the fixed host SELinux domain",
        )?;
        require(
            proc_attr(owner.manager_proc(), true)? == AA_MANAGER,
            "actual original PID1 AppArmor identity differs",
        )?;
        require(
            context_matches(&proc_attr(owner.broker_proc(), false)?, BROKER)
                && proc_attr(owner.broker_proc(), true)? == AA_BROKER,
            "original effective-unit broker differs from the live MAC broker",
        )?;
        // This is SO_PEERSEC on the authenticated client end, cross-checked
        // with the original live PID1. Never fgetxattr the client socket and
        // call that the server's label.
        require(
            context_matches(
                &actual_socket_security(owner.manager_connection().as_fd())?,
                HOST,
            ),
            "authenticated private manager socket peer differs from original PID1",
        )?;
        require(
            context_matches(
                &manager_file_context(owner.manager_socket_file())?,
                MANAGER_FILE,
            ),
            "actual manager server sock_file lacks its fixed dedicated label",
        )?;
        systemd_decisions(mac)?;
        original_systemd(owner.revalidate())?;
        require(
            original_systemd(owner.generation())? == self.generation,
            "systemd generation changed during live MAC observations",
        )?;
        self.original_descriptors(owner)?;
        mac.revalidate(owner.selection())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::OpenOptionsExt;

    #[test]
    fn actual_manager_server_inode_rejects_client_socket_and_regular_fd() {
        let mut pair = [-1; 2];
        assert_eq!(
            unsafe {
                libc::socketpair(
                    libc::AF_UNIX,
                    libc::SOCK_STREAM | libc::SOCK_CLOEXEC,
                    0,
                    pair.as_mut_ptr(),
                )
            },
            0
        );
        let sockets = unsafe { [File::from_raw_fd(pair[0]), File::from_raw_fd(pair[1])] };
        // A connected client socket is a socket inode too. Its own label
        // must never substitute for the separately held server pathname inode.
        for client in &sockets {
            match manager_file_context(client) {
                Err(MacError::Rejected(
                    "manager server inode must remain an original O_PATH descriptor",
                )) => {}
                other => panic!("connected client was not rejected precisely: {other:?}"),
            }
        }
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("regular");
        std::fs::write(&path, b"not a manager socket").unwrap();
        let held = std::fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&path)
            .unwrap();
        match manager_file_context(&held) {
            Err(MacError::Rejected("manager sock_file must be the actual held socket inode")) => {}
            other => panic!("regular O_PATH inode was not rejected precisely: {other:?}"),
        }
    }
}
