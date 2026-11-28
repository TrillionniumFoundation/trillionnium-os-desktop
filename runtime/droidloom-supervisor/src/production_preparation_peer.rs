//! Fixed normal preparation-executor peer for the closed preparation diagnostic gateway.
//! Reuses only the existing kernel socket/PIDFD observation core. Package
//! transaction roles and their admission rules are not extended.
use super::*;

const SELINUX: &[u8] = b"u:system_r:p4_linux_working_privateprep_t:s0";
const APPARMOR: &[u8] = b"droidloom-working-privateprep (enforce)";

fn check(deadline: Instant) -> io::Result<()> {
    crate::production_host_admission::check_observation_before(deadline).map_err(io::Error::other)
}
fn label_matches(actual: &[u8], expected: &[u8]) -> bool {
    actual == expected
        || actual.strip_suffix(b"\n") == Some(expected)
        || actual.strip_suffix(b"\0") == Some(expected)
}
fn socket_security(stream: &UnixStream) -> io::Result<Vec<u8>> {
    let mut bytes = [0u8; 256];
    let mut length = bytes.len() as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            stream.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERSEC,
            bytes.as_mut_ptr().cast(),
            &mut length,
        )
    } != 0
    {
        return Err(io::Error::last_os_error());
    }
    if length == 0 || length as usize > bytes.len() {
        return Err(reject(
            "preparation diagnostic peer security length differs",
        ));
    }
    Ok(bytes[..length as usize].to_vec())
}
fn whole(file: &File, seal: &Seal, deadline: Instant) -> io::Result<[u8; 32]> {
    check(deadline)?;
    if Seal::of(file)? != *seal {
        return Err(reject(
            "preparation diagnostic installed executable changed before complete read",
        ));
    }
    let bytes = seal.node[6];
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 65536];
    let mut offset = 0;
    while offset < bytes {
        check(deadline)?;
        let length = (bytes - offset).min(buffer.len() as u64) as usize;
        file.read_exact_at(&mut buffer[..length], offset)?;
        if offset == 0 && !buffer[..length].starts_with(b"\x7fELF") {
            return Err(reject(
                "preparation diagnostic installed program is not an ELF",
            ));
        }
        hash.update(&buffer[..length]);
        offset += length as u64;
    }
    if file.read_at(&mut buffer[..1], offset)? != 0 || Seal::of(file)? != *seal {
        return Err(reject(
            "preparation diagnostic installed executable changed during complete read",
        ));
    }
    check(deadline)?;
    Ok(hash.finalize().into())
}

struct FixedProgram {
    directories: Vec<(File, [u64; 5])>,
    file: File,
    seal: Seal,
    digest: [u8; 32],
}
impl FixedProgram {
    fn open(deadline: Instant) -> io::Result<Self> {
        check(deadline)?;
        let root = opened(
            libc::AT_FDCWD,
            c"/",
            libc::O_PATH | libc::O_DIRECTORY,
            false,
        )?;
        let mut directories = vec![(root, [0; 5])];
        for part in [c"usr", c"bin"] {
            let directory = opened(
                directories.last().unwrap().0.as_raw_fd(),
                part,
                libc::O_PATH | libc::O_DIRECTORY,
                false,
            )?;
            directories.push((directory, [0; 5]));
        }
        for (file, expected) in &mut directories {
            let m = file.metadata()?;
            if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o022 != 0 {
                return Err(reject(
                    "preparation diagnostic fixed program parent is not root controlled",
                ));
            }
            *expected = node(&m);
        }
        let file = opened(
            directories.last().unwrap().0.as_raw_fd(),
            c"droidloom-applications",
            libc::O_RDONLY | libc::O_NONBLOCK,
            false,
        )?;
        let m = file.metadata()?;
        if m.mode() != libc::S_IFREG | 0o755
            || m.uid() != 0
            || m.gid() != 0
            || m.nlink() != 1
            || !(64..=ELF_LIMIT).contains(&m.len())
        {
            return Err(reject(
                "preparation diagnostic fixed normal executable custody differs",
            ));
        }
        let n = unsafe {
            libc::fgetxattr(
                file.as_raw_fd(),
                c"security.capability".as_ptr(),
                std::ptr::null_mut(),
                0,
            )
        };
        if n != -1 || io::Error::last_os_error().raw_os_error() != Some(libc::ENODATA) {
            return Err(reject(
                "preparation diagnostic normal executable has file capabilities",
            ));
        }
        let seal = Seal::of(&file)?;
        let digest = whole(&file, &seal, deadline)?;
        Ok(Self {
            directories,
            file,
            seal,
            digest,
        })
    }
    fn revalidate(&self, deadline: Instant) -> io::Result<()> {
        let current = Self::open(deadline)?;
        if current.seal != self.seal
            || current.digest != self.digest
            || whole(&self.file, &self.seal, deadline)? != self.digest
            || current.directories.len() != self.directories.len()
        {
            return Err(reject(
                "preparation diagnostic installed normal executable changed",
            ));
        }
        for ((held, expected), (_, actual)) in self.directories.iter().zip(&current.directories) {
            if node(&held.metadata()?) != *expected || expected != actual {
                return Err(reject(
                    "preparation diagnostic installed program ancestor changed",
                ));
            }
        }
        Ok(())
    }
}

/// Only an actual accepted socket and the fixed installed normal ELF construct
/// this peer. It has no PID/path/role/serialized-evidence constructor.
pub(crate) struct PreparationPeer {
    observed: ObservedProcess,
    installed: FixedProgram,
}
impl PreparationPeer {
    pub(crate) fn bind(stream: &UnixStream, deadline: Instant) -> io::Result<Self> {
        check(deadline)?;
        let observed = ObservedProcess::peer(stream)?;
        let installed = FixedProgram::open(deadline)?;
        let value = Self {
            observed,
            installed,
        };
        value.revalidate(stream, deadline)?;
        Ok(value)
    }
    pub(crate) fn revalidate(&self, stream: &UnixStream, deadline: Instant) -> io::Result<()> {
        check(deadline)?;
        self.observed.revalidate()?;
        let peer = ObservedProcess::peer(stream)?;
        if peer.pid != self.observed.pid
            || peer.start != self.observed.start
            || peer.proc_node != self.observed.proc_node
            || node(&peer.pidfd.metadata()?) != node(&self.observed.pidfd.metadata()?)
            || peer.executable_seal != self.observed.executable_seal
        {
            return Err(reject(
                "preparation diagnostic same-connection process or PIDFD changed",
            ));
        }
        let status = proc_text(&self.observed.proc, c"status")?;
        for key in ["Uid:", "Gid:"] {
            let values: Vec<_> = status
                .lines()
                .filter_map(|line| line.strip_prefix(key))
                .collect();
            if values.len() != 1 || values[0].split_whitespace().collect::<Vec<_>>() != ["0"; 4] {
                return Err(reject(
                    "preparation diagnostic executor requires all actual root credentials",
                ));
            }
        }
        let command = proc_text(&self.observed.proc, c"cmdline")?;
        if command.as_bytes()
            != b"/usr/bin/droidloom-applications\0--working-qualification-prepare\0"
            || proc_text(&self.observed.proc, c"cgroup")?
                != format!(
                    "0::/system.slice/{}\n",
                    crate::native_working_contract::PARENT_UNIT
                )
        {
            return Err(reject(
                "preparation diagnostic requires its actual fixed child mode and singleton cgroup",
            ));
        }
        // The selected host socket route is AA-first. SO_PEERSEC is never
        // substituted for the independently observed named SELinux slot.
        if socket_security(stream)?.as_slice() != APPARMOR
            || !label_matches(
                proc_text(&self.observed.proc, c"attr/selinux/current")?.as_bytes(),
                SELINUX,
            )
            || !label_matches(
                proc_text(&self.observed.proc, c"attr/apparmor/current")?.as_bytes(),
                APPARMOR,
            )
        {
            return Err(reject(
                "preparation diagnostic caller is not the exact normal preparation executor MAC role",
            ));
        }
        self.installed.revalidate(deadline)?;
        if self.observed.executable_seal != self.installed.seal {
            return Err(reject(
                "preparation diagnostic caller did not execute the original fixed installed inode",
            ));
        }
        self.observed.revalidate()?;
        check(deadline)
    }
}
