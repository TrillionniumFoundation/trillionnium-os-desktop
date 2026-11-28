//! Independent fixed EMPTY diagnostic client. The existing working preparation
//! peer and its exact parent lineage are unchanged.
//! Reuses only the existing kernel socket/PIDFD observation core. Package
//! transaction roles and their admission rules are not extended.
use super::*;

const SELINUX: &[u8] = b"u:system_r:p4_linux_working_privateprep_t:s0";
const APPARMOR: &[u8] = b"droidloom-working-privateprep (enforce)";

fn fixed_invocation(command: &[u8], cgroup: &str) -> bool {
    command == b"/usr/bin/droidloomctl\0empty-meituan-diagnostic\0"
        && cgroup == format!("0::/system.slice/{}\n", crate::empty_meituan_contract::UNIT)
}

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
            "EMPTY Meituan diagnostic peer security length differs",
        ));
    }
    Ok(bytes[..length as usize].to_vec())
}
fn whole(file: &File, seal: &Seal, deadline: Instant) -> io::Result<[u8; 32]> {
    check(deadline)?;
    if Seal::of(file)? != *seal {
        return Err(reject(
            "EMPTY Meituan diagnostic installed executable changed before complete read",
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
                "EMPTY Meituan diagnostic installed program is not an ELF",
            ));
        }
        hash.update(&buffer[..length]);
        offset += length as u64;
    }
    if file.read_at(&mut buffer[..1], offset)? != 0 || Seal::of(file)? != *seal {
        return Err(reject(
            "EMPTY Meituan diagnostic installed executable changed during complete read",
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
                    "EMPTY Meituan diagnostic fixed program parent is not root controlled",
                ));
            }
            *expected = node(&m);
        }
        let file = opened(
            directories.last().unwrap().0.as_raw_fd(),
            c"droidloomctl",
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
                "EMPTY Meituan diagnostic fixed normal executable custody differs",
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
                "EMPTY Meituan diagnostic normal executable has file capabilities",
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
                "EMPTY Meituan diagnostic installed normal executable changed",
            ));
        }
        for ((held, expected), (_, actual)) in self.directories.iter().zip(&current.directories) {
            if node(&held.metadata()?) != *expected || expected != actual {
                return Err(reject(
                    "EMPTY Meituan diagnostic installed program ancestor changed",
                ));
            }
        }
        Ok(())
    }
}

/// Only an actual accepted socket and the fixed installed normal ELF construct
/// this peer. It has no PID/path/role/serialized-evidence constructor.
pub(crate) struct EmptyMeituanPeer {
    observed: ObservedProcess,
    installed: FixedProgram,
}
impl EmptyMeituanPeer {
    /// The existing birth primitive executes the parent's actual held ELF;
    /// its argv[0] is a protocol literal, not the image identity. Both ctl
    /// entries bind the running inode to this fixed installed pathname. O_PATH
    /// plus explicit fstat avoids new body readers or new seccomp permissions.
    pub(crate) fn require_installed_current() -> io::Result<()> {
        let running = crate::production_host_admission::application_worker_executable()
            .map_err(io::Error::other)?;
        let image = Seal::of(&running)?;
        let mut parents = Vec::new();
        let root = opened(libc::AT_FDCWD, c"/", libc::O_PATH, false)?;
        parents.push((root, [0u64; 5]));
        for part in [c"usr", c"bin"] {
            let current = opened(
                parents.last().unwrap().0.as_raw_fd(),
                part,
                libc::O_PATH,
                false,
            )?;
            parents.push((current, [0u64; 5]));
        }
        for (file, identity) in &mut parents {
            let m = file.metadata()?;
            if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o022 != 0 {
                return Err(reject("EMPTY ctl installed ancestor differs"));
            }
            *identity = node(&m);
        }
        let named = opened(
            parents.last().unwrap().0.as_raw_fd(),
            c"droidloomctl",
            libc::O_PATH,
            false,
        )?;
        if image != Seal::of(&named)?
            || image.node[2] != u64::from(libc::S_IFREG | 0o755)
            || image.node[3] != 0
            || image.node[4] != 0
            || image.node[5] != 1
            || image != Seal::of(&running)?
        {
            return Err(reject(
                "EMPTY ctl invocation is not the actual fixed installed executable inode",
            ));
        }
        for (file, identity) in parents {
            if node(&file.metadata()?) != identity {
                return Err(reject("EMPTY ctl installed ancestor changed"));
            }
        }
        Ok(())
    }
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
                "EMPTY Meituan diagnostic same-connection process or PIDFD changed",
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
                    "EMPTY Meituan diagnostic executor requires all actual root credentials",
                ));
            }
        }
        let command = proc_text(&self.observed.proc, c"cmdline")?;
        if !fixed_invocation(
            command.as_bytes(),
            &proc_text(&self.observed.proc, c"cgroup")?,
        ) {
            return Err(reject(
                "EMPTY Meituan diagnostic requires its actual fixed child mode and singleton cgroup",
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
                "EMPTY Meituan diagnostic caller is not the exact normal preparation executor MAC role",
            ));
        }
        self.installed.revalidate(deadline)?;
        if self.observed.executable_seal != self.installed.seal {
            return Err(reject(
                "EMPTY Meituan diagnostic caller did not execute the original fixed installed inode",
            ));
        }
        self.observed.revalidate()?;
        check(deadline)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn empty_meituan_peer_rejects_other_modes_units_and_arguments() {
        let command = b"/usr/bin/droidloomctl\0empty-meituan-diagnostic\0";
        let group = format!("0::/system.slice/{}\n", crate::empty_meituan_contract::UNIT);
        assert!(fixed_invocation(command, &group));
        for other in [
            b"/usr/bin/droidloomctl\0install\0official.apk\0".as_slice(),
            b"/usr/bin/droidloomctl\0empty-meituan-diagnostic\0--json\0".as_slice(),
            b"/usr/bin/droidloom-applications\0--working-qualification-prepare\0".as_slice(),
        ] {
            assert!(!fixed_invocation(other, &group));
        }
        for other in [
            "0::/system.slice/droidloom-working-qualification.service\n",
            "0::/system.slice/droidloom-empty-meituan-diagnostic.service/child\n",
            "",
        ] {
            assert!(!fixed_invocation(command, other));
        }
    }
}
