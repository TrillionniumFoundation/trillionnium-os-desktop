//! Kernel binding of a fixed activation trampoline's accepted connection.
//!
//! This module observes custody. It does not send an executable, authorize a
//! command or issue Ready. The MAC provider must separately observe the real
//! socket and held-proc domains before the broker can send AUTH or GO.

use super::activation_channel::{before, wait_event};
use super::*;
use crate::production_activation_protocol as wire;
use crate::production_runtime_assets::{
    RuntimeError, RuntimeOriginalLinkerconfig, RuntimeTrampoline,
};
use sha2::{Digest, Sha256};
use std::os::unix::fs::FileExt;

// Linux 7.0.14 include/uapi/asm-generic/socket.h. No numeric-pid fallback.
const SO_PEERPIDFD: libc::c_int = 77;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ElfIdentity {
    device: u64,
    inode: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    bytes: u64,
    mtime: i64,
    mtime_ns: i64,
    ctime: i64,
    ctime_ns: i64,
}

impl ElfIdentity {
    fn of(file: &File) -> Result<Self> {
        let m = file.metadata()?;
        Ok(Self {
            device: m.dev(),
            inode: m.ino(),
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            links: m.nlink(),
            bytes: m.size(),
            mtime: m.mtime(),
            mtime_ns: m.mtime_nsec(),
            ctime: m.ctime(),
            ctime_ns: m.ctime_nsec(),
        })
    }
}

fn image_input(file: &File) -> Result<()> {
    let kind = filesystem_kind(file)?;
    if ![0xef53, 0xe0f5_e1e2_u32 as libc::c_long].contains(&kind) {
        return Err(NamespaceError::Rejected(
            "activation input is not a held runtime image inode",
        ));
    }
    verify_process_statfs(file, kind, 1 | 2 | 4, 8)?;
    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    if flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if flags & (libc::O_ACCMODE | libc::O_PATH) != libc::O_RDONLY {
        return Err(NamespaceError::Rejected(
            "activation input must be a held readable FD",
        ));
    }
    let result = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.capability".as_ptr(),
            std::ptr::null_mut(),
            0,
        )
    };
    if result != -1 || io::Error::last_os_error().raw_os_error() != Some(libc::ENODATA) {
        return Err(NamespaceError::Rejected(
            "activation input file capability must be absent",
        ));
    }
    Ok(())
}

fn complete_digest(file: &File, bytes: u64, expected: [u8; 32], deadline: u64) -> Result<()> {
    let mut hash = Sha256::new();
    let mut chunk = [0_u8; 64 * 1024];
    let mut offset = 0;
    while offset < bytes {
        before(deadline)?;
        let size = (bytes - offset).min(chunk.len() as u64) as usize;
        file.read_exact_at(&mut chunk[..size], offset)?;
        hash.update(&chunk[..size]);
        offset += size as u64;
    }
    before(deadline)?;
    if <[u8; 32]>::from(hash.finalize()) != expected {
        return Err(NamespaceError::Rejected(
            "activation input complete digest differs",
        ));
    }
    Ok(())
}

fn runtime_input<T>(value: std::result::Result<T, RuntimeError>) -> Result<T> {
    value.map_err(|error| match error {
        RuntimeError::Io(error) => NamespaceError::Io(error),
        RuntimeError::Namespace(error) => error,
        RuntimeError::Identity(error) => NamespaceError::Identity(error),
        other => NamespaceError::RuntimeResource(other.to_string()),
    })
}

/// A same-runtime input observation. Only PreparedRuntime issues the opaque
/// input role; there is no caller-file/digest overload. This type still grants
/// no execution authority and keeps borrowing the actual selected owner.
pub(super) struct TrampolineInput<'a> {
    init: &'a ExecutedInitWitness<'a>,
    role: RuntimeTrampoline<'a>,
    file: &'a File,
    identity: ElfIdentity,
}

impl<'a> TrampolineInput<'a> {
    pub(super) fn observe(
        init: &'a ExecutedInitWitness<'a>,
        role: RuntimeTrampoline<'a>,
        deadline: u64,
    ) -> Result<Self> {
        before(deadline)?;
        init.revalidate()?;
        runtime_input(role.revalidate(init))?;
        let file = role.file();
        let bytes = role.bytes();
        let digest = role.digest();
        let identity = ElfIdentity::of(file)?;
        let (uid, gid) = init.mapped_root_ids();
        if identity.mode != libc::S_IFREG | 0o555
            || identity.uid != uid
            || identity.gid != gid
            || identity.links != 1
            || identity.bytes != bytes
            || !(64..=32 * 1024 * 1024).contains(&bytes)
        {
            return Err(NamespaceError::Rejected("fixed trampoline inode metadata"));
        }
        image_input(file)?;
        let mut header = [0_u8; 64];
        file.read_exact_at(&mut header, 0)?;
        if &header[..7] != b"\x7fELF\x02\x01\x01"
            || u16::from_le_bytes([header[16], header[17]]) != 2
            || u16::from_le_bytes([header[18], header[19]]) != 62
        {
            return Err(NamespaceError::Rejected(
                "fixed static trampoline ELF architecture",
            ));
        }
        let entry = u64::from_le_bytes(header[24..32].try_into().unwrap());
        let table = u64::from_le_bytes(header[32..40].try_into().unwrap());
        let width = u16::from_le_bytes(header[54..56].try_into().unwrap()) as u64;
        let count = u16::from_le_bytes(header[56..58].try_into().unwrap()) as u64;
        if width != 56
            || !(1..=16).contains(&count)
            || table
                .checked_add(width * count)
                .is_none_or(|end| end > bytes)
        {
            return Err(NamespaceError::Rejected(
                "fixed static trampoline program table",
            ));
        }
        let mut executable_entry = false;
        let mut stacks = 0;
        for index in 0..count {
            before(deadline)?;
            let mut row = [0_u8; 56];
            file.read_exact_at(&mut row, table + width * index)?;
            let kind = u32::from_le_bytes(row[..4].try_into().unwrap());
            let flags = u32::from_le_bytes(row[4..8].try_into().unwrap());
            if kind == 2 || kind == 3 {
                return Err(NamespaceError::Rejected(
                    "trampoline has a dynamic loader or table",
                ));
            }
            if kind == 0x6474_e551 {
                stacks += 1;
                if flags & 1 != 0 {
                    return Err(NamespaceError::Rejected("trampoline stack is executable"));
                }
            }
            if kind == 1 {
                let offset = u64::from_le_bytes(row[8..16].try_into().unwrap());
                let address = u64::from_le_bytes(row[16..24].try_into().unwrap());
                let file_bytes = u64::from_le_bytes(row[32..40].try_into().unwrap());
                let memory_bytes = u64::from_le_bytes(row[40..48].try_into().unwrap());
                let end = address
                    .checked_add(memory_bytes)
                    .ok_or(NamespaceError::Rejected(
                        "trampoline segment address overflow",
                    ))?;
                if flags & 3 == 3
                    || memory_bytes < file_bytes
                    || offset
                        .checked_add(file_bytes)
                        .is_none_or(|last| last > bytes)
                {
                    return Err(NamespaceError::Rejected(
                        "trampoline segment policy or bounds",
                    ));
                }
                executable_entry |= flags & 1 != 0 && address <= entry && entry < end;
            }
        }
        if stacks != 1 || !executable_entry {
            return Err(NamespaceError::Rejected(
                "trampoline static entry or stack contract",
            ));
        }
        complete_digest(file, bytes, digest, deadline)?;
        let value = Self {
            init,
            role,
            file,
            identity,
        };
        value.revalidate()?;
        init.revalidate()?;
        before(deadline)?;
        Ok(value)
    }

    fn revalidate(&self) -> Result<()> {
        runtime_input(self.role.revalidate(self.init))?;
        if ElfIdentity::of(self.file)? != self.identity {
            return Err(NamespaceError::Rejected("held trampoline input changed"));
        }
        image_input(self.file)
    }
}

/// The fixed original binary input, separate from the trampoline's inode.
/// This is an input observation, not an execution or activation capability.
/// Only the same-tree runtime provider may select the declaration and FD;
/// neither a packet nor an Android request has a path/digest/argv parameter.
pub(super) struct OriginalLinkerInput<'a> {
    init: &'a ExecutedInitWitness<'a>,
    role: RuntimeOriginalLinkerconfig<'a>,
    file: &'a File,
    identity: ElfIdentity,
}

impl<'a> OriginalLinkerInput<'a> {
    pub(super) fn observe(
        init: &'a ExecutedInitWitness<'a>,
        role: RuntimeOriginalLinkerconfig<'a>,
        deadline: u64,
    ) -> Result<Self> {
        before(deadline)?;
        init.revalidate()?;
        runtime_input(role.revalidate(init))?;
        let file = role.file();
        let bytes = role.bytes();
        let digest = role.digest();
        let interpreter = role.interpreter();
        let identity = ElfIdentity::of(file)?;
        let (uid, gid) = init.mapped_root_ids();
        if identity.mode & libc::S_IFMT != libc::S_IFREG
            || identity.mode & 0o6022 != 0
            || identity.mode & 0o111 == 0
            || identity.uid != uid
            || identity.gid != gid
            || identity.links != 1
            || identity.bytes != bytes
            || !(64..=32 * 1024 * 1024).contains(&bytes)
            || !matches!(
                interpreter,
                None | Some("/system/bin/bootstrap/linker64")
                    | Some("/system/bin/linker64")
                    | Some("/apex/com.android.runtime/bin/linker64")
            )
        {
            return Err(NamespaceError::Rejected(
                "original linkerconfig fixed input metadata",
            ));
        }
        image_input(file)?;
        let mut header = [0_u8; 64];
        file.read_exact_at(&mut header, 0)?;
        if &header[..7] != b"\x7fELF\x02\x01\x01"
            || ![2, 3].contains(&u16::from_le_bytes([header[16], header[17]]))
            || u16::from_le_bytes([header[18], header[19]]) != 62
            || u16::from_le_bytes([header[52], header[53]]) != 64
        {
            return Err(NamespaceError::Rejected(
                "original linkerconfig ELF architecture",
            ));
        }
        let table = u64::from_le_bytes(header[32..40].try_into().unwrap());
        let width = u16::from_le_bytes(header[54..56].try_into().unwrap()) as u64;
        let count = u16::from_le_bytes(header[56..58].try_into().unwrap()) as u64;
        if width != 56
            || !(1..=128).contains(&count)
            || table < 64
            || table
                .checked_add(width * count)
                .is_none_or(|end| end > bytes)
        {
            return Err(NamespaceError::Rejected(
                "original linkerconfig program headers",
            ));
        }
        let mut actual_interpreter = None;
        let mut executable = false;
        for index in 0..count {
            before(deadline)?;
            let mut row = [0_u8; 56];
            file.read_exact_at(&mut row, table + width * index)?;
            let kind = u32::from_le_bytes(row[..4].try_into().unwrap());
            let flags = u32::from_le_bytes(row[4..8].try_into().unwrap());
            let offset = u64::from_le_bytes(row[8..16].try_into().unwrap());
            let size = u64::from_le_bytes(row[32..40].try_into().unwrap());
            let memory = u64::from_le_bytes(row[40..48].try_into().unwrap());
            if offset.checked_add(size).is_none_or(|end| end > bytes)
                || (kind == 1 && (flags & 3 == 3 || memory < size))
            {
                return Err(NamespaceError::Rejected(
                    "original linkerconfig segment bounds or policy",
                ));
            }
            executable |= kind == 1 && flags & 1 != 0 && size > 0;
            if kind == 3 {
                if actual_interpreter.is_some() || !(2..=256).contains(&size) {
                    return Err(NamespaceError::Rejected(
                        "original linkerconfig interpreter bounds",
                    ));
                }
                let mut value = vec![0_u8; size as usize];
                file.read_exact_at(&mut value, offset)?;
                if value.last() != Some(&0) || value[..value.len() - 1].contains(&0) {
                    return Err(NamespaceError::Rejected(
                        "original linkerconfig interpreter termination",
                    ));
                }
                value.pop();
                actual_interpreter = Some(String::from_utf8(value).map_err(|_| {
                    NamespaceError::Rejected("original linkerconfig interpreter UTF-8")
                })?);
            }
        }
        if !executable || actual_interpreter.as_deref() != interpreter {
            return Err(NamespaceError::Rejected(
                "original linkerconfig declared interpreter differs",
            ));
        }
        complete_digest(file, bytes, digest, deadline)?;
        let value = Self {
            init,
            role,
            file,
            identity,
        };
        value.revalidate()?;
        init.revalidate()?;
        before(deadline)?;
        Ok(value)
    }

    pub(super) fn revalidate(&self) -> Result<()> {
        runtime_input(self.role.revalidate(self.init))?;
        if ElfIdentity::of(self.file)? != self.identity {
            return Err(NamespaceError::Rejected(
                "held original linkerconfig changed",
            ));
        }
        image_input(self.file)
    }

    pub(super) fn descriptor(&self) -> BorrowedFd<'_> {
        self.file.as_fd()
    }
    pub(super) fn file(&self) -> &File {
        self.file
    }
}

pub(super) fn require_activation_socket(socket: &OwnedFd) -> Result<()> {
    for (key, expected) in [
        (libc::SO_TYPE, libc::SOCK_SEQPACKET),
        (libc::SO_DOMAIN, libc::AF_UNIX),
        (libc::SO_PASSCRED, 1),
    ] {
        let mut got = 0_i32;
        let mut bytes = std::mem::size_of_val(&got) as libc::socklen_t;
        if unsafe {
            libc::getsockopt(
                socket.as_raw_fd(),
                libc::SOL_SOCKET,
                key,
                (&mut got as *mut i32).cast(),
                &mut bytes,
            )
        } != 0
        {
            // Preserve the actual syscall error, including ENOTSOCK. A
            // successful read with a wrong value is a different contract error.
            return Err(io::Error::last_os_error().into());
        }
        if bytes as usize != std::mem::size_of_val(&got) || got != expected {
            return Err(NamespaceError::Rejected(
                "activation socket type or credentials disabled",
            ));
        }
    }
    let socket_fd_flags = unsafe { libc::fcntl(socket.as_raw_fd(), libc::F_GETFD) };
    if socket_fd_flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let socket_status_flags = unsafe { libc::fcntl(socket.as_raw_fd(), libc::F_GETFL) };
    if socket_status_flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if socket_fd_flags & libc::FD_CLOEXEC == 0 || socket_status_flags & libc::O_NONBLOCK == 0 {
        return Err(NamespaceError::Rejected(
            "activation connection must be CLOEXEC and nonblocking",
        ));
    }
    Ok(())
}

fn actual_peer_pidfd(socket: &OwnedFd) -> Result<OwnedFd> {
    require_activation_socket(socket)?;
    let mut raw = -1_i32;
    let mut bytes = std::mem::size_of_val(&raw) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            SO_PEERPIDFD,
            (&mut raw as *mut i32).cast(),
            &mut bytes,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    if raw < 0 {
        return Err(NamespaceError::Rejected("actual socket peer PIDFD absent"));
    }
    let owned = unsafe { OwnedFd::from_raw_fd(raw) };
    let fd_flags = unsafe { libc::fcntl(owned.as_raw_fd(), libc::F_GETFD) };
    if fd_flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if bytes as usize != std::mem::size_of::<i32>() || fd_flags & libc::FD_CLOEXEC == 0 {
        return Err(NamespaceError::Rejected(
            "kernel peer PIDFD shape or CLOEXEC differs",
        ));
    }
    Ok(owned)
}

pub(super) fn peer_credentials(socket: &OwnedFd) -> Result<libc::ucred> {
    let mut value: libc::ucred = unsafe { std::mem::zeroed() };
    let mut size = std::mem::size_of_val(&value) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut value as *mut libc::ucred).cast(),
            &mut size,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    if size as usize != std::mem::size_of_val(&value) || value.pid <= 1 {
        return Err(NamespaceError::Rejected(
            "actual socket peer credential shape",
        ));
    }
    Ok(value)
}

fn peer_security(socket: &OwnedFd) -> Result<Vec<u8>> {
    let mut bytes = [0_u8; 1024];
    let mut length = bytes.len() as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERSEC,
            bytes.as_mut_ptr().cast(),
            &mut length,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    if length == 0 || length as usize > bytes.len() {
        return Err(NamespaceError::Rejected(
            "actual socket peer security label bound",
        ));
    }
    Ok(bytes[..length as usize].to_vec())
}

fn held_exe(proc: &File) -> Result<File> {
    // Only the kernel executable link in this already PIDFD-bound proc inode
    // is followed. No sender-supplied pathname is opened.
    let raw = unsafe {
        libc::openat(
            proc.as_raw_fd(),
            c"exe".as_ptr(),
            libc::O_PATH | libc::O_CLOEXEC | libc::O_NONBLOCK,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(raw) })
}

/// Raw kernel observations, intentionally not a production capability.
struct SocketProcess<'a> {
    socket: &'a OwnedFd,
    pidfd: OwnedFd,
    proc: File,
    proc_node: Node,
    identity: ProcessIdentity,
    uid: u32,
    gid: u32,
    executable: File,
    executable_identity: ElfIdentity,
    socket_label: Vec<u8>,
}

impl<'a> SocketProcess<'a> {
    fn observe(socket: &'a OwnedFd) -> Result<Self> {
        let pidfd = actual_peer_pidfd(socket)?;
        if pidfd_exited(&pidfd)? {
            return Err(NamespaceError::Rejected("activation peer already exited"));
        }
        let credential = peer_credentials(socket)?;
        let info = pidfd_info(pidfd.as_raw_fd())?;
        if info.pid != credential.pid as u32 || info.tgid != info.pid {
            return Err(NamespaceError::Rejected(
                "socket and peer PIDFD process differ",
            ));
        }
        require_pidfd_creds(&info, credential.uid, credential.gid)?;
        let root = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open("/proc")?;
        check_fs(root.as_raw_fd(), PROC_MAGIC)?;
        // The lookup number came from this exact kernel peer PIDFD, never a
        // packet. Before/after PIDFD and proc identity checks bind the lookup.
        let proc = open_proc_at(
            &root,
            &info.pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let proc_node = Node::of(&proc)?;
        let identity = read_identity(&proc, info.pid)?;
        if identity.parent != info.ppid {
            return Err(NamespaceError::Rejected(
                "peer proc and PIDFD parent differ",
            ));
        }
        let executable = held_exe(&proc)?;
        let executable_identity = ElfIdentity::of(&executable)?;
        let socket_label = peer_security(socket)?;
        let value = Self {
            socket,
            pidfd,
            proc,
            proc_node,
            identity,
            uid: credential.uid,
            gid: credential.gid,
            executable,
            executable_identity,
            socket_label,
        };
        value.revalidate()?;
        Ok(value)
    }

    fn revalidate(&self) -> Result<()> {
        require_activation_socket(self.socket)?;
        if pidfd_exited(&self.pidfd)? {
            return Err(NamespaceError::Rejected("original activation peer exited"));
        }
        let info = pidfd_info(self.pidfd.as_raw_fd())?;
        let credentials = peer_credentials(self.socket)?;
        if info.pid != self.identity.pid
            || info.tgid != self.identity.pid
            || info.ppid != self.identity.parent
            || credentials.pid as u32 != self.identity.pid
            || credentials.uid != self.uid
            || credentials.gid != self.gid
            || Node::of(&self.proc)? != self.proc_node
            || read_identity(&self.proc, info.pid)? != self.identity
            || ElfIdentity::of(&self.executable)? != self.executable_identity
            || ElfIdentity::of(&held_exe(&self.proc)?)? != self.executable_identity
            || peer_security(self.socket)? != self.socket_label
        {
            return Err(NamespaceError::Rejected(
                "original activation peer identity changed",
            ));
        }
        require_pidfd_creds(&info, self.uid, self.gid)?;
        if pidfd_exited(&self.pidfd)? {
            return Err(NamespaceError::Rejected(
                "activation peer exited during observation",
            ));
        }
        Ok(())
    }
}

/// Original init descendant plus exact fixed trampoline ELF. These facts are
/// necessary but insufficient for AUTH: the MAC provider must issue and keep
/// revalidating its separate actual linkerconfig-domain witness.
pub(crate) struct OwnedActivationPeer<'a> {
    init: &'a ExecutedInitWitness<'a>,
    generation: ExecutedInitGeneration,
    trampoline: &'a TrampolineInput<'a>,
    process: SocketProcess<'a>,
    namespace_pid: u32,
}

impl<'a> OwnedActivationPeer<'a> {
    pub(super) fn observe(
        init: &'a ExecutedInitWitness<'a>,
        socket: &'a OwnedFd,
        trampoline: &'a TrampolineInput<'a>,
    ) -> Result<Self> {
        init.revalidate()?;
        trampoline.revalidate()?;
        let process = SocketProcess::observe(socket)?;
        let status = read_proc(&process.proc, "status")?;
        let pids = status_field(&status, "NSpid:")?
            .split_ascii_whitespace()
            .map(str::parse::<u32>)
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(|_| NamespaceError::Rejected("activation peer NSpid grammar"))?;
        if pids.len() != 2 || pids[0] != process.identity.pid || pids[1] <= 1 {
            return Err(NamespaceError::Rejected(
                "activation peer is not in the owned PID level",
            ));
        }
        let value = Self {
            init,
            generation: init.generation()?,
            trampoline,
            process,
            namespace_pid: pids[1],
        };
        value.revalidate()?;
        Ok(value)
    }

    pub(crate) fn revalidate(&self) -> Result<()> {
        self.init.revalidate()?;
        self.trampoline.revalidate()?;
        self.process.revalidate()?;
        let (uid, gid) = self.init.mapped_root_ids();
        if self.init.generation()? != self.generation
            || self.process.identity.parent != self.init.host_pid()
            || self.process.uid != uid
            || self.process.gid != gid
            || self.process.executable_identity != self.trampoline.identity
        {
            return Err(NamespaceError::Rejected(
                "peer is not this init's fixed trampoline",
            ));
        }
        let user = from_pidfd(&self.process.pidfd, 0xff09, libc::CLONE_NEWUSER)?;
        let expected_user = Node::of(self.init.user_namespace())?;
        if Node::of(&user)? != expected_user {
            return Err(NamespaceError::Rejected(
                "activation peer user namespace differs",
            ));
        }
        for (command, kind) in [
            (0xff05, libc::CLONE_NEWPID),
            (0xff03, libc::CLONE_NEWNS),
            (0xff02, libc::CLONE_NEWIPC),
            (0xff0a, libc::CLONE_NEWUTS),
            (0xff04, libc::CLONE_NEWNET),
            (0xff01, libc::CLONE_NEWCGROUP),
        ] {
            let peer = from_pidfd(&self.process.pidfd, command, kind)?;
            let raw =
                unsafe { libc::ioctl(self.init.pidfd().as_raw_fd(), command, 0 as libc::c_ulong) };
            if raw < 0 {
                return Err(io::Error::last_os_error().into());
            }
            let original = unsafe { File::from_raw_fd(raw) };
            check_fs(original.as_raw_fd(), NSFS_MAGIC)?;
            if unsafe { libc::ioctl(original.as_raw_fd(), NS_GET_NSTYPE, 0 as libc::c_ulong) }
                != kind
                || Node::of(&peer)? != Node::of(&original)?
            {
                return Err(NamespaceError::Rejected(
                    "activation peer and original init namespace differ",
                ));
            }
            require_namespace_owner(&peer, expected_user)?;
        }
        let status = read_proc(&self.process.proc, "status")?;
        require_ids(&status, "Uid:", uid)?;
        require_ids(&status, "Gid:", gid)?;
        require_empty_groups(&status)?;
        let expected = format!("{} {}", self.process.identity.pid, self.namespace_pid);
        let pids = status_field(&status, "NSpid:")?
            .split_ascii_whitespace()
            .collect::<Vec<_>>()
            .join(" ");
        if pids != expected
            || status_field(&status, "NoNewPrivs:")?.trim() != "1"
            || status_field(&status, "Seccomp:")?.trim() != "2"
        {
            return Err(NamespaceError::Rejected(
                "activation peer PID/NNP/seccomp state differs",
            ));
        }
        self.process.revalidate()?;
        self.init.revalidate()
    }

    pub(crate) fn pidfd(&self) -> BorrowedFd<'_> {
        self.process.pidfd.as_fd()
    }
    pub(crate) fn proc_directory(&self) -> &File {
        &self.process.proc
    }
    pub(crate) fn socket(&self) -> BorrowedFd<'_> {
        self.process.socket.as_fd()
    }
    pub(crate) fn generation(&self) -> ExecutedInitGeneration {
        self.generation
    }
    pub(crate) fn socket_security(&self) -> &[u8] {
        &self.process.socket_label
    }
    pub(super) fn namespace_pid(&self) -> u32 {
        self.namespace_pid
    }
    pub(super) fn control(&self) -> &OwnedFd {
        self.process.socket
    }

    /// This observer is not the trampoline's parent. Only original init may
    /// reap it; this waits for HUP on the kernel socket peer PIDFD and then
    /// independently reads the retained kernel wait status. No waitid or
    /// signal by a packet's numeric PID is performed here.
    pub(super) fn require_retired(&self, code: i32, status: i32, deadline: u64) -> Result<()> {
        self.init.revalidate()?;
        let events = wait_event(self.process.pidfd.as_fd(), 0, deadline)?;
        if events & libc::POLLHUP == 0 {
            return Err(NamespaceError::Rejected(
                "original trampoline has not been reaped",
            ));
        }
        let observed = retained_wait_status(self.process.pidfd.as_fd())?;
        let expected = wire::raw_wait_status(code, status).ok_or(NamespaceError::Rejected(
            "invalid original linkerconfig wait status",
        ))?;
        // The wrapper re-raises a terminating signal without enabling core
        // dumps. Preserve the original child's full CLD_DUMPED result in its
        // own proof, while checking the wrapper's actual terminating signal.
        if (code == libc::CLD_EXITED && observed != expected)
            || (code != libc::CLD_EXITED && observed & 0x7f != expected & 0x7f)
        {
            return Err(NamespaceError::Rejected(
                "actual trampoline return status differs",
            ));
        }
        require_held_proc_retired(&self.process.proc)?;
        self.init.revalidate()?;
        before(deadline)
    }
}

fn retained_wait_status(pidfd: BorrowedFd<'_>) -> Result<i32> {
    let mut info = wire::PidfdInfo::request_exit();
    if unsafe {
        libc::ioctl(
            pidfd.as_raw_fd(),
            wire::PIDFD_GET_INFO as libc::c_ulong,
            &mut info,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    if info.mask & wire::PIDFD_INFO_EXIT == 0 {
        return Err(NamespaceError::Rejected(
            "kernel has not retained the original exit status",
        ));
    }
    Ok(info.exit_code)
}

fn require_held_proc_retired(proc: &File) -> Result<()> {
    let raw = unsafe {
        libc::openat(
            proc.as_raw_fd(),
            c"ns".as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if raw >= 0 {
        drop(unsafe { OwnedFd::from_raw_fd(raw) });
        return Err(NamespaceError::Rejected(
            "original held proc task has not been retired",
        ));
    }
    let error = io::Error::last_os_error();
    if error.raw_os_error() != Some(libc::ESRCH) {
        return Err(error.into());
    }
    Ok(())
}

fn same_namespaces(left: &OwnedFd, right: &OwnedFd) -> Result<()> {
    let user = from_pidfd(left, 0xff09, libc::CLONE_NEWUSER)?;
    let expected_user = Node::of(&user)?;
    for (command, kind) in [
        (0xff09, libc::CLONE_NEWUSER),
        (0xff05, libc::CLONE_NEWPID),
        (0xff03, libc::CLONE_NEWNS),
        (0xff02, libc::CLONE_NEWIPC),
        (0xff0a, libc::CLONE_NEWUTS),
        (0xff04, libc::CLONE_NEWNET),
        (0xff01, libc::CLONE_NEWCGROUP),
    ] {
        let original = from_pidfd(left, command, kind)?;
        let child = from_pidfd(right, command, kind)?;
        if Node::of(&original)? != Node::of(&child)? {
            return Err(NamespaceError::Rejected(
                "linkerconfig child namespace differs from its peer parent",
            ));
        }
        if kind != libc::CLONE_NEWUSER {
            require_namespace_owner(&child, expected_user)?;
        }
    }
    Ok(())
}

/// The original atomic child PIDFD received from the authenticated static
/// trampoline. A numeric PID is used only to compare its actual NSpid record.
/// This non-parent never consumes waitid and cannot mint a Ready witness.
pub(super) struct ActivationChild {
    pidfd: OwnedFd,
    proc: File,
    proc_node: Node,
    identity: ProcessIdentity,
    generation: ExecutedInitGeneration,
    namespace_pid: u32,
    cgroup: u64,
}

impl ActivationChild {
    pub(super) fn observe(
        peer: &OwnedActivationPeer<'_>,
        pidfd: OwnedFd,
        namespace_pid: u32,
    ) -> Result<Self> {
        peer.revalidate()?;
        if pidfd_exited(&pidfd)? {
            return Err(NamespaceError::Rejected(
                "linkerconfig child exited before GO",
            ));
        }
        let info = pidfd_info(pidfd.as_raw_fd())?;
        let parent = pidfd_info(peer.process.pidfd.as_raw_fd())?;
        if info.pid != info.tgid
            || info.ppid != parent.pid
            || info.mask & 4 == 0
            || parent.mask & 4 == 0
            || info.cgroup_id == 0
            || info.cgroup_id != parent.cgroup_id
        {
            return Err(NamespaceError::Rejected(
                "received child is not this trampoline's original descendant",
            ));
        }
        let root = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open("/proc")?;
        check_fs(root.as_raw_fd(), PROC_MAGIC)?;
        let proc = open_proc_at(
            &root,
            &info.pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let value = Self {
            pidfd,
            proc_node: Node::of(&proc)?,
            identity: read_identity(&proc, info.pid)?,
            proc,
            generation: peer.generation,
            namespace_pid,
            cgroup: info.cgroup_id,
        };
        value.revalidate_before_go(peer)?;
        Ok(value)
    }

    pub(super) fn revalidate_before_go(&self, peer: &OwnedActivationPeer<'_>) -> Result<()> {
        peer.revalidate()?;
        if peer.generation != self.generation || pidfd_exited(&self.pidfd)? {
            return Err(NamespaceError::Rejected(
                "linkerconfig child lost its live owner generation",
            ));
        }
        let info = pidfd_info(self.pidfd.as_raw_fd())?;
        let parent = pidfd_info(peer.process.pidfd.as_raw_fd())?;
        if info.pid != self.identity.pid
            || info.tgid != self.identity.pid
            || info.ppid != peer.process.identity.pid
            || self.identity.parent != info.ppid
            || info.mask & 4 == 0
            || info.cgroup_id != self.cgroup
            || parent.mask & 4 == 0
            || parent.cgroup_id != self.cgroup
            || Node::of(&self.proc)? != self.proc_node
            || read_identity(&self.proc, info.pid)? != self.identity
            || ElfIdentity::of(&held_exe(&self.proc)?)? != peer.trampoline.identity
        {
            return Err(NamespaceError::Rejected(
                "original pre-exec linkerconfig child identity changed",
            ));
        }
        let (uid, gid) = peer.init.mapped_root_ids();
        require_pidfd_creds(&info, uid, gid)?;
        same_namespaces(&peer.process.pidfd, &self.pidfd)?;
        let status = read_proc(&self.proc, "status")?;
        require_ids(&status, "Uid:", uid)?;
        require_ids(&status, "Gid:", gid)?;
        require_empty_groups(&status)?;
        let pids = status_field(&status, "NSpid:")?
            .split_ascii_whitespace()
            .map(str::parse::<u32>)
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(|_| NamespaceError::Rejected("linkerconfig child NSpid grammar"))?;
        if self.namespace_pid <= 1
            || pids != [self.identity.pid, self.namespace_pid]
            || status_field(&status, "NoNewPrivs:")?.trim() != "1"
            || status_field(&status, "Seccomp:")?.trim() != "2"
        {
            return Err(NamespaceError::Rejected(
                "original linkerconfig child PID/NNP/seccomp changed",
            ));
        }
        peer.revalidate()?;
        if pidfd_exited(&self.pidfd)? {
            return Err(NamespaceError::Rejected(
                "linkerconfig child died before original GO",
            ));
        }
        Ok(())
    }

    pub(super) fn require_exited_unreaped(&self, deadline: u64) -> Result<()> {
        let events = wait_event(self.pidfd.as_fd(), libc::POLLIN, deadline)?;
        if events & libc::POLLIN == 0 || events & libc::POLLHUP != 0 {
            return Err(NamespaceError::Rejected(
                "original linkerconfig child exit/reap phase differs",
            ));
        }
        before(deadline)
    }

    pub(super) fn require_reaped(&self, code: i32, status: i32, deadline: u64) -> Result<()> {
        let expected = wire::raw_wait_status(code, status).ok_or(NamespaceError::Rejected(
            "invalid linkerconfig terminal status",
        ))?;
        let events = wait_event(self.pidfd.as_fd(), 0, deadline)?;
        if events & libc::POLLHUP == 0 || retained_wait_status(self.pidfd.as_fd())? != expected {
            return Err(NamespaceError::Rejected(
                "original linkerconfig kernel exit differs from parent waitid",
            ));
        }
        require_held_proc_retired(&self.proc)?;
        before(deadline)
    }

    /// The failed-operation caller retires the entire init tree first. This
    /// checks the exact retained child without guessing its resulting status
    /// or replacing the original operation's error with cleanup success.
    pub(super) fn require_retired_after_tree(&self, deadline: u64) -> Result<i32> {
        let events = wait_event(self.pidfd.as_fd(), 0, deadline)?;
        if events & libc::POLLHUP == 0 {
            return Err(NamespaceError::Rejected(
                "activation child remains after tree retirement",
            ));
        }
        let status = retained_wait_status(self.pidfd.as_fd())?;
        require_held_proc_retired(&self.proc)?;
        before(deadline)?;
        Ok(status)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn activation_peer_reads_real_socket_pidfd_and_rejects_a_regular_file() {
        let mut raw = [-1_i32; 2];
        assert_eq!(
            unsafe {
                libc::socketpair(
                    libc::AF_UNIX,
                    libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
                    0,
                    raw.as_mut_ptr(),
                )
            },
            0
        );
        let pair = unsafe { [OwnedFd::from_raw_fd(raw[0]), OwnedFd::from_raw_fd(raw[1])] };
        for fd in &pair {
            let one = 1_i32;
            assert_eq!(
                unsafe {
                    libc::setsockopt(
                        fd.as_raw_fd(),
                        libc::SOL_SOCKET,
                        libc::SO_PASSCRED,
                        (&one as *const i32).cast(),
                        std::mem::size_of_val(&one) as _,
                    )
                },
                0
            );
        }
        // A socketpair reports its actual creating process. This low-level
        // observation does not fabricate an init/Ready/production capability.
        let observed = SocketProcess::observe(&pair[0]).unwrap();
        assert_eq!(observed.identity.pid, unsafe { libc::getpid() as u32 });
        assert_eq!(observed.uid, unsafe { libc::getuid() });
        assert_eq!(observed.gid, unsafe { libc::getgid() });
        observed.revalidate().unwrap();
        let real = File::open(std::env::current_exe().unwrap()).unwrap();
        assert_eq!(
            ElfIdentity::of(&real).unwrap(),
            observed.executable_identity
        );
        assert!(!observed.socket_label.is_empty());
        let unrelated: OwnedFd = tempfile::tempfile().unwrap().into();
        match actual_peer_pidfd(&unrelated) {
            Err(NamespaceError::Io(error)) => {
                assert_eq!(error.raw_os_error(), Some(libc::ENOTSOCK))
            }
            _ => panic!("regular file did not produce exact ENOTSOCK"),
        }
    }
}
