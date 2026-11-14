//! Test-only same-PIDFD post-exec observation. This is not Android execution
//! admission, a namespace constructor, or a public command interface.
use super::*;
use sha2::{Digest, Sha256};
use std::os::unix::fs::FileExt;

include!("production_postexec_probe_identity.rs");

#[derive(Clone, Debug, Eq, PartialEq)]
struct Identity {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    nlink: u64,
    size: u64,
    mtime: i64,
    mtime_ns: i64,
    ctime: i64,
    ctime_ns: i64,
}
impl Identity {
    fn of(file: &File) -> Result<Self> {
        let m = file.metadata()?;
        Ok(Self {
            dev: m.dev(),
            ino: m.ino(),
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            nlink: m.nlink(),
            size: m.size(),
            mtime: m.mtime(),
            mtime_ns: m.mtime_nsec(),
            ctime: m.ctime(),
            ctime_ns: m.ctime_nsec(),
        })
    }
}
struct SealedProbe {
    file: File,
    path: std::path::PathBuf,
    identity: Identity,
}

fn bounded_elf(bytes: &[u8]) -> Result<()> {
    let reject = || NamespaceError::Rejected("fixed static post-exec ELF layout");
    if bytes.len() < 64
        || &bytes[..7] != b"\x7fELF\x02\x01\x01"
        || bytes[7] != 0
        || u16::from_le_bytes(bytes[16..18].try_into().unwrap()) != 2
        || u16::from_le_bytes(bytes[18..20].try_into().unwrap()) != 62
        || u16::from_le_bytes(bytes[52..54].try_into().unwrap()) != 64
    {
        return Err(reject());
    }
    let u64at = |at| u64::from_le_bytes(bytes[at..at + 8].try_into().unwrap());
    let entry = u64at(24);
    let ph = u64at(32);
    let count = u16::from_le_bytes(bytes[56..58].try_into().unwrap()) as u64;
    if u16::from_le_bytes(bytes[54..56].try_into().unwrap()) != 56
        || !(1..=32).contains(&count)
        || ph < 64
        || ph
            .checked_add(count * 56)
            .is_none_or(|end| end > bytes.len() as u64)
    {
        return Err(reject());
    }
    let mut executable_entry = false;
    let mut safe_stack = false;
    for i in 0..count {
        let p = (ph + i * 56) as usize;
        let kind = u32::from_le_bytes(bytes[p..p + 4].try_into().unwrap());
        let flags = u32::from_le_bytes(bytes[p + 4..p + 8].try_into().unwrap());
        if kind == 2 || kind == 3 {
            return Err(reject());
        }
        if kind == 1 {
            let offset = u64at(p + 8);
            let address = u64at(p + 16);
            let file = u64at(p + 32);
            let memory = u64at(p + 40);
            if flags & 3 == 3
                || flags & !7 != 0
                || memory < file
                || offset
                    .checked_add(file)
                    .is_none_or(|x| x > bytes.len() as u64)
                || address.checked_add(memory).is_none()
            {
                return Err(reject());
            }
            if flags & 1 != 0 && entry >= address && entry < address + memory {
                executable_entry = true;
            }
        }
        if kind == 0x6474_e551 {
            if flags & 1 != 0 || safe_stack {
                return Err(reject());
            }
            safe_stack = true;
        }
    }
    if !executable_entry || !safe_stack {
        return Err(reject());
    }
    Ok(())
}
fn public_sealed(file: &File) -> Result<Identity> {
    let node = Identity::of(file)?;
    if node.mode != libc::S_IFREG | 0o555
        || node.uid != 0
        || node.gid != 0
        || node.nlink != 1
        || node.size != PRIVATE_PROBE_BYTES
        || !(64..=1_048_576).contains(&node.size)
    {
        return Err(NamespaceError::Rejected(
            "root-sealed static post-exec input",
        ));
    }
    let cap = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.capability".as_ptr(),
            std::ptr::null_mut(),
            0,
        )
    };
    if cap != -1
        || !matches!(
            io::Error::last_os_error().raw_os_error(),
            Some(libc::ENODATA) | Some(libc::EOPNOTSUPP)
        )
    {
        return Err(NamespaceError::Rejected(
            "post-exec input has file capability or is unobservable",
        ));
    }
    let mut bytes = vec![0; node.size as usize];
    file.read_exact_at(&mut bytes, 0)?;
    if format!("{:x}", Sha256::digest(&bytes)) != PRIVATE_PROBE_SHA256
        || Identity::of(file)? != node
    {
        return Err(NamespaceError::Rejected(
            "post-exec input changed or hash differs",
        ));
    }
    bounded_elf(&bytes)?;
    Ok(node)
}
impl SealedProbe {
    fn load() -> Result<Self> {
        let me = std::env::current_exe()?;
        let parent = me.parent().ok_or(NamespaceError::Rejected(
            "sealed test executable parent absent",
        ))?;
        // Exact sibling of the actually executing root-sealed test binary.
        // No CLI, JSON or environment variable supplies this filename/path.
        let path = parent.join("private-proc-postexec-probe");
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(&path)?;
        let identity = public_sealed(&file)?;
        let value = Self {
            file,
            path,
            identity,
        };
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate(&self) -> Result<()> {
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(&self.path)?;
        if Identity::of(&named)? != self.identity || public_sealed(&self.file)? != self.identity {
            return Err(NamespaceError::Rejected(
                "sealed probe path/held descriptor differ",
            ));
        }
        Ok(())
    }
}

fn record(
    control: RawFd,
    nonce: [u8; 16],
    pid: u32,
    uid: u32,
    gid: u32,
    wanted: Phase,
    live: impl FnOnce() -> Result<()>,
) -> Result<i32> {
    let (packet, creds) = receive_packet(control)?;
    if !packet.matches(nonce, 1) || creds.pid != pid as i32 || creds.uid != uid || creds.gid != gid
    {
        return Err(NamespaceError::Rejected(
            "post-exec original nonce/SCM peer differs",
        ));
    }
    if packet.phase == Phase::Failed as u32 {
        let (stage, line, errno) = child::postexec_private_failure(packet.errno)
            .ok_or(NamespaceError::Rejected("post-exec failure encoding"))?;
        return Err(io::Error::other(format!(
            "authenticated fixed post-exec Failed: stage={stage} source-line={line} errno={errno}"
        ))
        .into());
    }
    if packet.phase != wanted as u32
        || (wanted as u32 == Phase::PostExecReady as u32 && packet.errno != 0)
        || (wanted as u32 == Phase::PostExecChecked as u32 && !(0..4096).contains(&packet.errno))
    {
        return Err(NamespaceError::Rejected(
            "fixed post-exec phase or xattr errno differs",
        ));
    }
    live()?;
    Ok(packet.errno)
}

fn score_node(
    child: &TreeChild,
    expected_uid: u32,
    expected_gid: u32,
) -> Result<serde_json::Value> {
    child.verify()?;
    let root = held_child_root(child)?;
    let file = writable_proc::target_from_root(&root, "/proc/1/oom_score_adj")?;
    let node = Identity::of(&file)?;
    let proc = writable_proc::target_from_root(&root, "/proc")?;
    if node.mode != libc::S_IFREG | 0o644
        || node.uid != expected_uid
        || node.gid != expected_gid
        || node.dev != proc.metadata()?.dev()
        || filesystem_kind(&file)? != 0x9fa0
        || writable_proc::held_mount_id(&file)? != writable_proc::held_mount_id(&proc)?
    {
        return Err(NamespaceError::Rejected(
            "actual owned proc inode/mm ownership differs",
        ));
    }
    let value = serde_json::json!({"identity":format!("{node:?}"),"mount_id":writable_proc::held_mount_id(&file)?,"host_uid":node.uid,"host_gid":node.gid,"body_read":false});
    child.verify()?;
    Ok(value)
}
fn actual_postexec(child: &TreeChild, probe: &SealedProbe) -> Result<serde_json::Value> {
    child.verify()?;
    probe.revalidate()?;
    // This is the one deliberate proc magic-link follow: open the actual
    // executable target from the already held exact proc-directory FD.
    // O_NOFOLLOW would return the symlink inode and cannot establish exec.
    let raw = unsafe {
        libc::openat(
            child.proc_dir.as_raw_fd(),
            c"exe".as_ptr(),
            libc::O_PATH | libc::O_CLOEXEC,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let executable = unsafe { File::from_raw_fd(raw) };
    if Identity::of(&executable)? != probe.identity {
        return Err(NamespaceError::Rejected(
            "same PIDFD executable is not sealed probe inode",
        ));
    }
    let raw = read_proc(&child.proc_dir, "status")?;
    let status = writable_proc::private_status_fields(&raw, child.uids.start, child.gids.start)?;
    if status["Seccomp"] != "2"
        || ["CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"]
            .iter()
            .any(|name| status[*name] != "0000000000000000")
    {
        return Err(NamespaceError::Rejected(
            "post-exec actual capabilities/filter differ",
        ));
    }
    let score = score_node(child, child.uids.start, child.gids.start)?;
    child.verify()?;
    Ok(
        serde_json::json!({"actual_host_pid":child.identity.pid,"actual_start_ticks":child.identity.start_ticks,"exe_identity":format!("{:?}",Identity::of(&executable)?),"score":score,"status":status,"same_pidfd":true,"same_namespaces":true,"executed_android":false}),
    )
}

pub(super) fn run_private(tree: &mut IsolatedNamespaces) -> Result<i32> {
    let probe = SealedProbe::load()?;
    let child = tree
        .init
        .as_ref()
        .ok_or(NamespaceError::Rejected("owned PID1 absent"))?;
    tree.writable_proc
        .as_mut()
        .ok_or(NamespaceError::Rejected("private writable proc absent"))?
        .verify(child)?;
    let before = score_node(child, 0, 0)?;
    writable_proc::trace_private_proc_authority(child)?;
    probe.revalidate()?;
    send_one_fd(
        child.control.as_raw_fd(),
        &Packet::new(
            child.nonce,
            Phase::PreparePostExecProbe,
            0,
            child.parent_pid,
        ),
        probe.file.as_fd(),
    )?;
    wait_readable(&child.control, &child.pidfd)?;
    record(
        child.control.as_raw_fd(),
        child.nonce,
        child.identity.pid,
        child.uids.start,
        child.gids.start,
        Phase::PostExecReady,
        || child.verify(),
    )?;
    let after = actual_postexec(child, &probe)?;
    eprintln!(
        "private fixed post-exec ready: {}",
        serde_json::json!({"preexec_score":before,"postexec":after,"dumpable_zero_report_from_sealed_image":true,"private_zero_profile_only":true})
    );
    send_packet(
        child.control.as_raw_fd(),
        &Packet::new(child.nonce, Phase::CheckPostExecProbe, 0, child.parent_pid),
    )?;
    wait_readable(&child.control, &child.pidfd)?;
    let observed = record(
        child.control.as_raw_fd(),
        child.nonce,
        child.identity.pid,
        child.uids.start,
        child.gids.start,
        Phase::PostExecChecked,
        || child.verify(),
    )?;
    let checked = actual_postexec(child, &probe)?;
    tree.writable_proc.as_mut().unwrap().verify(child)?;
    let root = held_child_root(child)?;
    let dev = root_subdirectory(&root, c"dev")?;
    let raw = unsafe {
        libc::openat(
            dev.as_raw_fd(),
            c"selinux-xattr-private-observation".as_ptr(),
            libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if raw >= 0 {
        drop(unsafe { File::from_raw_fd(raw) });
        return Err(NamespaceError::Rejected(
            "private xattr observation file retained",
        ));
    }
    if io::Error::last_os_error().raw_os_error() != Some(libc::ENOENT) {
        return Err(io::Error::last_os_error().into());
    }
    if filesystem_kind(&dev)? != 0x0102_1994 {
        return Err(NamespaceError::Rejected(
            "xattr observation filesystem differs",
        ));
    }
    eprintln!(
        "private fixed post-exec checked: {}",
        serde_json::json!({"actual":checked,"own_oom_original_value_restored":true,"global_write_opens_denied_without_writes":true,"private_filesystem":"tmpfs","security_selinux_set_get_errno":observed,"mac_qualified":false,"production_admission":false,"Android":0})
    );
    probe.revalidate()?;
    Ok(observed)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn channel() -> (OwnedFd, OwnedFd) {
        let mut f = [-1; 2];
        assert_eq!(
            unsafe {
                libc::socketpair(
                    libc::AF_UNIX,
                    libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                    0,
                    f.as_mut_ptr(),
                )
            },
            0
        );
        let a = unsafe { OwnedFd::from_raw_fd(f[0]) };
        let b = unsafe { OwnedFd::from_raw_fd(f[1]) };
        let one = 1_i32;
        assert_eq!(
            unsafe {
                libc::setsockopt(
                    a.as_raw_fd(),
                    libc::SOL_SOCKET,
                    libc::SO_PASSCRED,
                    (&one as *const i32).cast(),
                    4,
                )
            },
            0
        );
        (a, b)
    }
    #[test]
    fn production_postexec_queued_failure_keeps_real_errno_without_live_success() {
        let (r, s) = channel();
        let n = [88; 16];
        let value = (0x5400_0000u32 | (123 << 12) | 13) as i32;
        send_packet(s.as_raw_fd(), &Packet::new(n, Phase::Failed, value, 1)).unwrap();
        drop(s);
        let calls = std::cell::Cell::new(0);
        let e = record(
            r.as_raw_fd(),
            n,
            unsafe { libc::getpid() } as u32,
            unsafe { libc::getuid() },
            unsafe { libc::getgid() },
            Phase::PostExecReady,
            || {
                calls.set(1);
                Ok(())
            },
        )
        .unwrap_err();
        assert!(e.to_string().contains("stage=4 source-line=123 errno=13"));
        assert_eq!(calls.get(), 0);
    }
    #[test]
    fn production_postexec_checks_peer_phase_rights_and_bounded_xattr_separately() {
        let n = [89; 16];
        let pid = unsafe { libc::getpid() } as u32;
        let uid = unsafe { libc::getuid() };
        let gid = unsafe { libc::getgid() };
        for case in 0..8 {
            let (r, s) = channel();
            let mut packet = Packet::new(n, Phase::PostExecChecked, libc::EPERM, 1);
            match case {
                0 => packet = Packet::new([90; 16], Phase::PostExecChecked, 1, 1),
                1 => packet = Packet::new(n, Phase::PostExecReady, 0, 1),
                2 => packet = Packet::new(n, Phase::PostExecChecked, -1, 1),
                3 => packet = Packet::new(n, Phase::PostExecChecked, 4096, 1),
                4 => packet = Packet::new(n, Phase::PostExecChecked, 1, 2),
                _ => {}
            }
            if case == 5 {
                let file = File::open("/dev/null").unwrap();
                send_one_fd(s.as_raw_fd(), &packet, file.as_fd()).unwrap();
            } else {
                send_packet(s.as_raw_fd(), &packet).unwrap();
            }
            let result = record(
                r.as_raw_fd(),
                n,
                pid,
                if case == 6 { uid.wrapping_add(1) } else { uid },
                gid,
                Phase::PostExecChecked,
                || {
                    if case == 7 {
                        Err(NamespaceError::Rejected("not live"))
                    } else {
                        Ok(())
                    }
                },
            );
            assert!(result.is_err(), "case {case}");
        }
        for errno in [0, libc::EPERM, libc::EOPNOTSUPP, 4095] {
            let (r, s) = channel();
            send_packet(
                s.as_raw_fd(),
                &Packet::new(n, Phase::PostExecChecked, errno, 1),
            )
            .unwrap();
            assert_eq!(
                record(
                    r.as_raw_fd(),
                    n,
                    pid,
                    uid,
                    gid,
                    Phase::PostExecChecked,
                    || Ok(())
                )
                .unwrap(),
                errno
            );
        }
    }
}
