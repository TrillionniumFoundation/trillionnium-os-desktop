//! Actual post-exec kernel state of the original owned init.
//!
//! The original runtime owner must retain the exact-image scoped capability
//! policy before this observer compares all five actual kernel masks to it.
//! Retaining arbitrary values from /proc cannot select a policy or construct
//! ExecutionAdmission. The issuer accepts only the existing original init
//! witness and reads its held proc FD.

use std::fs::{File, Metadata};
use std::io::{self, Read};
use std::marker::PhantomData;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::MetadataExt;
use std::rc::Rc;

use thiserror::Error;

use crate::production_execution_profile as profile;
use crate::production_namespace::{ExecutedInitGeneration, ExecutedInitWitness};

const PROC_MAGIC: libc::c_long = 0x9fa0;
const STATUS_LIMIT: usize = 64 * 1024;

#[derive(Debug, Error)]
pub(super) enum ObservationError {
    #[error("original init execution-state observation rejected: {0}")]
    Rejected(&'static str),
    #[error("original init owner observation failed: {0}")]
    Owner(String),
    #[error(transparent)]
    Io(#[from] io::Error),
}

type Result<T> = std::result::Result<T, ObservationError>;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ProcNode {
    device: u64,
    inode: u64,
    mode: u32,
    uid: u32,
    gid: u32,
}

impl ProcNode {
    fn of(metadata: &Metadata) -> Self {
        Self {
            device: metadata.dev(),
            inode: metadata.ino(),
            mode: metadata.mode(),
            uid: metadata.uid(),
            gid: metadata.gid(),
        }
    }
}

/// Complete observed masks, without guessing a capability ABI or approved
/// Android set. Unknown future bits are retained, never silently truncated.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct KernelExecutionState {
    inheritable: u64,
    permitted: u64,
    effective: u64,
    bounding: u64,
    ambient: u64,
    no_new_privileges: bool,
    seccomp_mode: u8,
}

fn field<'a>(text: &'a str, name: &str) -> Result<&'a str> {
    let mut values = text.lines().filter_map(|line| line.strip_prefix(name));
    let value = values.next().ok_or(ObservationError::Rejected(
        "required status field is missing",
    ))?;
    if values.next().is_some() {
        return Err(ObservationError::Rejected("duplicate status field"));
    }
    Ok(value.trim())
}

fn mask(text: &str, name: &str) -> Result<u64> {
    let value = field(text, name)?;
    if value.len() != 16 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(ObservationError::Rejected("capability mask encoding"));
    }
    u64::from_str_radix(value, 16)
        .map_err(|_| ObservationError::Rejected("capability mask overflow"))
}

fn parse_status(bytes: &[u8], expected_pid: u32) -> Result<KernelExecutionState> {
    if bytes.is_empty()
        || bytes.len() > STATUS_LIMIT
        || bytes.last() != Some(&b'\n')
        || bytes.contains(&0)
        || expected_pid == 0
        || expected_pid > i32::MAX as u32
    {
        return Err(ObservationError::Rejected(
            "bounded complete status required",
        ));
    }
    let text =
        std::str::from_utf8(bytes).map_err(|_| ObservationError::Rejected("status encoding"))?;
    for name in ["Pid:", "Tgid:"] {
        let value = field(text, name)?;
        if value.is_empty()
            || !value.bytes().all(|byte| byte.is_ascii_digit())
            || value.parse::<u32>().ok() != Some(expected_pid)
        {
            return Err(ObservationError::Rejected(
                "status is not the original process leader",
            ));
        }
    }
    Ok(KernelExecutionState {
        inheritable: mask(text, "CapInh:")?,
        permitted: mask(text, "CapPrm:")?,
        effective: mask(text, "CapEff:")?,
        bounding: mask(text, "CapBnd:")?,
        ambient: mask(text, "CapAmb:")?,
        no_new_privileges: match field(text, "NoNewPrivs:")? {
            "0" => false,
            "1" => true,
            _ => return Err(ObservationError::Rejected("NNP encoding")),
        },
        seccomp_mode: match field(text, "Seccomp:")? {
            "0" => 0,
            "1" => 1,
            "2" => 2,
            _ => return Err(ObservationError::Rejected("seccomp mode encoding")),
        },
    })
}

fn require_proc(file: &File, expected_kind: u32) -> Result<ProcNode> {
    let metadata = file.metadata()?;
    let mut filesystem: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut filesystem) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    if filesystem.f_type != PROC_MAGIC || metadata.mode() & libc::S_IFMT != expected_kind {
        return Err(ObservationError::Rejected(
            "execution state must come from held procfs",
        ));
    }
    Ok(ProcNode::of(&metadata))
}

fn read_status(proc: &File, expected_pid: u32) -> Result<KernelExecutionState> {
    let raw = unsafe {
        libc::openat(
            proc.as_raw_fd(),
            c"status".as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let status = unsafe { File::from_raw_fd(raw) };
    require_proc(&status, libc::S_IFREG)?;
    let mut bytes = Vec::new();
    status
        .take((STATUS_LIMIT + 1) as u64)
        .read_to_end(&mut bytes)?;
    parse_status(&bytes, expected_pid)
}

fn observe_status(proc: &File, expected_pid: u32) -> Result<(ProcNode, KernelExecutionState)> {
    let node = require_proc(proc, libc::S_IFDIR)?;
    let first = read_status(proc, expected_pid)?;
    let second = read_status(proc, expected_pid)?;
    if require_proc(proc, libc::S_IFDIR)? != node || first != second {
        return Err(ObservationError::Rejected(
            "execution state changed during observation",
        ));
    }
    Ok((node, second))
}

fn existing_execution_boundary(state: &KernelExecutionState) -> Result<()> {
    // These conditions are already required by the actual init MAC observer.
    // Mode 2 does not identify a particular BPF program or qualify its policy.
    if !state.no_new_privileges || state.seccomp_mode != 2 {
        return Err(ObservationError::Rejected(
            "original init lost NNP or seccomp filtering",
        ));
    }
    Ok(())
}

fn selected_android_boundary(state: &KernelExecutionState) -> Result<()> {
    existing_execution_boundary(state)?;
    if state.inheritable != 0
        || state.ambient != 0
        || state.permitted != profile::CAPABILITIES
        || state.effective != profile::CAPABILITIES
        || state.bounding != profile::CAPABILITIES
    {
        return Err(ObservationError::Rejected(
            "actual original init differs from its selected scoped Android capability profile",
        ));
    }
    Ok(())
}

fn owner<T>(
    value: std::result::Result<T, crate::production_namespace::NamespaceError>,
) -> Result<T> {
    value.map_err(|error| ObservationError::Owner(error.to_string()))
}

/// An opaque same-thread observation bound to the selected capability policy.
/// It does not satisfy the remaining activation and execution contracts.
/// It retains no new process, namespace, mount or executable descriptor.
pub(super) struct FinalExecutionObservation {
    generation: ExecutedInitGeneration,
    proc: ProcNode,
    state: KernelExecutionState,
    creator_tid: libc::c_long,
    _same_thread: PhantomData<Rc<()>>,
}

impl FinalExecutionObservation {
    pub(super) fn observe(init: &ExecutedInitWitness<'_>) -> Result<Self> {
        owner(init.revalidate())?;
        owner(init.revalidate_capability_contract())?;
        let creator_tid = unsafe { libc::syscall(libc::SYS_gettid) };
        let generation = owner(init.generation())?;
        let (proc, state) = observe_status(init.proc_directory(), init.host_pid())?;
        selected_android_boundary(&state)?;
        owner(init.revalidate())?;
        if owner(init.generation())? != generation
            || unsafe { libc::syscall(libc::SYS_gettid) } != creator_tid
        {
            return Err(ObservationError::Rejected(
                "original init generation or observer thread changed",
            ));
        }
        Ok(Self {
            generation,
            proc,
            state,
            creator_tid,
            _same_thread: PhantomData,
        })
    }

    pub(super) fn revalidate(&self, init: &ExecutedInitWitness<'_>) -> Result<()> {
        if unsafe { libc::syscall(libc::SYS_gettid) } != self.creator_tid {
            return Err(ObservationError::Rejected(
                "execution observer moved threads",
            ));
        }
        owner(init.revalidate())?;
        if owner(init.generation())? != self.generation {
            return Err(ObservationError::Rejected(
                "execution observation belongs to another init",
            ));
        }
        owner(init.revalidate_capability_contract())?;
        let (proc, state) = observe_status(init.proc_directory(), init.host_pid())?;
        selected_android_boundary(&state)?;
        if proc != self.proc || state != self.state {
            return Err(ObservationError::Rejected(
                "original execution state or proc custody changed",
            ));
        }
        owner(init.revalidate())?;
        if owner(init.generation())? != self.generation
            || unsafe { libc::syscall(libc::SYS_gettid) } != self.creator_tid
        {
            return Err(ObservationError::Rejected(
                "original init generation or observer thread changed",
            ));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process::{Child, Command, Stdio};

    #[test]
    fn selected_android_observation_requires_all_five_exact_masks_and_existing_confinement() {
        let exact = KernelExecutionState {
            inheritable: 0,
            permitted: profile::CAPABILITIES,
            effective: profile::CAPABILITIES,
            bounding: profile::CAPABILITIES,
            ambient: 0,
            no_new_privileges: true,
            seccomp_mode: 2,
        };
        selected_android_boundary(&exact).unwrap();
        for field in 0..7 {
            let mut changed = exact;
            match field {
                0 => changed.inheritable = 1,
                1 => changed.permitted ^= 1,
                2 => changed.effective ^= 1,
                3 => changed.bounding ^= 1,
                4 => changed.ambient = 1,
                5 => changed.no_new_privileges = false,
                6 => changed.seccomp_mode = 0,
                _ => unreachable!(),
            }
            assert!(selected_android_boundary(&changed).is_err());
        }
        let mut broadened = exact;
        broadened.permitted |= 1 << 39;
        broadened.effective |= 1 << 39;
        broadened.bounding |= 1 << 39;
        assert!(selected_android_boundary(&broadened).is_err());
    }

    fn status() -> Vec<u8> {
        b"Name:\tinit\nTgid:\t123\nPid:\t123\nCapInh:\t8000000000000001\nCapPrm:\t8000000000000003\nCapEff:\t0000000000000002\nCapBnd:\tffffffffffffffff\nCapAmb:\t0000000000000001\nNoNewPrivs:\t1\nSeccomp:\t2\n".to_vec()
    }

    #[test]
    fn observed_capability_masks_are_complete_without_inventing_an_android_profile() {
        let observed = parse_status(&status(), 123).unwrap();
        assert_eq!(observed.inheritable, 0x8000_0000_0000_0001);
        assert_eq!(observed.permitted, 0x8000_0000_0000_0003);
        assert_eq!(observed.effective, 2);
        assert_eq!(observed.bounding, u64::MAX);
        assert_eq!(observed.ambient, 1);
        existing_execution_boundary(&observed).unwrap();
    }

    #[test]
    fn missing_duplicate_truncated_or_malformed_status_never_becomes_an_observation() {
        let original = String::from_utf8(status()).unwrap();
        for invalid in [
            original.replace("CapEff:\t0000000000000002\n", ""),
            format!("{original}CapEff:\t0000000000000002\n"),
            original.replace("0000000000000002", "0x00000000000002"),
            original.replace("0000000000000002", "00000000000000000"),
            original.replace("0000000000000002", "000000000000000g"),
            original.replace("NoNewPrivs:\t1", "NoNewPrivs:\ttrue"),
            original.replace("Seccomp:\t2", "Seccomp:\t3"),
            original.replace("Tgid:\t123", "Tgid:\t124"),
            original.replace("Pid:\t123", "Pid:\t+123"),
            original.trim_end().into(),
            format!("{original}\0\n"),
            format!("{}\n", "x".repeat(STATUS_LIMIT)),
        ] {
            assert!(parse_status(invalid.as_bytes(), 123).is_err());
        }
        assert!(parse_status(&status(), 124).is_err());
        assert!(parse_status(&status(), 0).is_err());
        assert!(parse_status(&[0xff, b'\n'], 123).is_err());
    }

    #[test]
    fn kernel_observation_cannot_replace_the_existing_nnp_and_filter_boundary() {
        let original = String::from_utf8(status()).unwrap();
        for invalid in [
            original.replace("NoNewPrivs:\t1", "NoNewPrivs:\t0"),
            original.replace("Seccomp:\t2", "Seccomp:\t0"),
            original.replace("Seccomp:\t2", "Seccomp:\t1"),
        ] {
            let observed = parse_status(invalid.as_bytes(), 123).unwrap();
            assert!(existing_execution_boundary(&observed).is_err());
        }
    }

    struct ChildGuard(Child);
    impl Drop for ChildGuard {
        fn drop(&mut self) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }

    fn ordinary_child() -> ChildGuard {
        ChildGuard(
            Command::new("/bin/sleep")
                .arg("30")
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap(),
        )
    }

    #[test]
    fn actual_ordinary_child_status_is_read_only_through_its_retained_proc_descriptor() {
        let child = ordinary_child();
        // A test-only ordinary process is not an ExecutedInitWitness and
        // cannot construct FinalExecutionObservation or execution admission.
        let proc = File::open(format!("/proc/{}", child.0.id())).unwrap();
        let (node, first) = observe_status(&proc, child.0.id()).unwrap();
        let (again, second) = observe_status(&proc, child.0.id()).unwrap();
        assert_eq!(node, again);
        assert_eq!(first, second);
        assert!(node.inode != 0);
        assert_eq!(first.effective & !first.permitted, 0);
        assert_eq!(first.ambient & !(first.permitted & first.inheritable), 0);
    }

    #[test]
    fn actual_proc_reader_rejects_another_process_and_a_reaped_original_child() {
        let mut child = ordinary_child();
        let pid = child.0.id();
        let proc = File::open(format!("/proc/{pid}")).unwrap();
        assert!(observe_status(&proc, pid + 1).is_err());
        child.0.kill().unwrap();
        child.0.wait().unwrap();
        assert!(observe_status(&proc, pid).is_err());
    }

    #[test]
    fn a_regular_directory_or_file_cannot_forge_proc_status_custody() {
        let temporary = tempfile::tempdir().unwrap();
        std::fs::write(temporary.path().join("status"), status()).unwrap();
        let directory = File::open(temporary.path()).unwrap();
        let file = File::open(temporary.path().join("status")).unwrap();
        assert!(observe_status(&directory, 123).is_err());
        assert!(observe_status(&file, 123).is_err());
    }
}
