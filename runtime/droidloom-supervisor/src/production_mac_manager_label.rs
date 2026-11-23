//! Exact installed inputs and live MAC for one consumed manager label change.
//! The declaration selects reviewed inputs. Only current kernel observations
//! can issue this permit, which is never an execution or Ready capability.
use super::*;
use crate::production_cgroup::{CgroupError, ManagerEndpointGeneration, ManagerLabelObservation};

const RECORD: &str = "/etc/droidloom/host-mac/manager-label.json";
const MANAGER: &str = "/usr/lib/systemd/systemd";
const INSTALLER: &str = "/usr/lib/droidloom/production/current/droidloom-host-mac";
const INSTALLER_EXEC: &str = "u:object_r:droidloom_policy_loader_exec:s0";
pub(super) const MANAGER_LABEL: &str = "u:object_r:droidloom_manager_private_socket:s0";
const MAX_EXECUTABLE: usize = 64 * 1024 * 1024;

fn owner<T>(value: std::result::Result<T, CgroupError>) -> Result<T> {
    value.map_err(|error| match error {
        CgroupError::Io(error) => MacError::Io(error),
        other => MacError::Owner(other.to_string()),
    })
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Record {
    schema: String,
    base_cohort_sha256: String,
    runtime_manifest_sha256: String,
    policy_input_bytes: u64,
    policy_input_sha256: String,
    policy_export_bytes: u64,
    policy_export_sha256: String,
    manager_elf_bytes: u64,
    manager_elf_sha256: String,
    labeler_elf_bytes: u64,
    labeler_elf_sha256: String,
    original_server_context: String,
}
impl Record {
    fn validate_shape(&self) -> Result<()> {
        require(
            self.schema == "droidloom-original-systemd-label-v1",
            "fixed manager label declaration schema",
        )?;
        for value in [
            &self.base_cohort_sha256,
            &self.runtime_manifest_sha256,
            &self.policy_input_sha256,
            &self.policy_export_sha256,
            &self.manager_elf_sha256,
            &self.labeler_elf_sha256,
        ] {
            require(
                digest(value),
                "manager label declaration needs complete digests",
            )?;
        }
        for size in [self.manager_elf_bytes, self.labeler_elf_bytes] {
            require(
                (64..=MAX_EXECUTABLE as u64).contains(&size),
                "bounded complete original executable required",
            )?;
        }
        for size in [self.policy_input_bytes, self.policy_export_bytes] {
            require(
                (1024..=MAX_POLICY as u64).contains(&size),
                "complete manager label policy identities required",
            )?;
        }
        let value = self
            .original_server_context
            .strip_prefix("u:object_r:")
            .and_then(|v| v.strip_suffix(":s0"));
        require(
            value.is_some_and(|v| {
                !v.is_empty()
                    && v.len() <= 128
                    && v.as_bytes()[0].is_ascii_lowercase()
                    && v.bytes()
                        .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
            }) && self.original_server_context != MANAGER_LABEL,
            "exact reviewed original object context required",
        )
    }
    fn matches(&self, selection: &ProductionSelection, policy: &LoadedPolicyWitness) -> Result<()> {
        self.validate_shape()?;
        let expected = &policy.declaration;
        require(
            self.base_cohort_sha256 == selection.base_cohort()
                && self.runtime_manifest_sha256 == selection.runtime_manifest()
                && self.policy_input_bytes == expected.policy_input_bytes
                && self.policy_input_sha256 == expected.policy_input_sha256
                && self.policy_export_bytes == expected.policy_export_bytes
                && self.policy_export_sha256 == expected.policy_export_sha256,
            "label declaration does not match the same selection and both complete policy identities",
        )
    }
}

struct Executable {
    path: &'static str,
    file: File,
    node: Node,
}
impl Executable {
    fn read(path: &'static str, bytes: u64, expected: &str, held: &File) -> Result<Self> {
        let file = open_absolute(path, libc::O_RDONLY)?;
        let node = Node::of(&file)?;
        require(
            node.mode & libc::S_IFMT == libc::S_IFREG
                && node.uid == 0
                && node.gid == 0
                && node.links == 1
                && node.mode & 0o6022 == 0
                && node.mode & 0o111 != 0
                && node.bytes == bytes
                && node == Node::of(held)?,
            "original executable differs from its root-controlled fixed installed inode",
        )?;
        let raw = bounded(&file, MAX_EXECUTABLE)?;
        require(
            raw.len() as u64 == bytes && raw.starts_with(b"\x7fELF") && sha(&raw) == expected,
            "complete original executable differs from installed pin",
        )?;
        let result = Self { path, file, node };
        result.revalidate(held)?;
        Ok(result)
    }
    fn revalidate(&self, held: &File) -> Result<()> {
        require(
            Node::of(&self.file)? == self.node
                && Node::of(held)? == self.node
                && Node::of(&open_absolute(self.path, libc::O_RDONLY)?)? == self.node,
            "original executable or its fixed installed name changed",
        )
    }
}

fn mount_namespace(proc: &File) -> Result<File> {
    // Follow only the original held task's fixed namespace magic link.
    let fd = unsafe {
        libc::openat(
            proc.as_raw_fd(),
            c"ns/mnt".as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(fd) };
    const NS_GET_NSTYPE: libc::c_ulong = 0xb703;
    let actual = unsafe { libc::ioctl(fd, NS_GET_NSTYPE, 0 as libc::c_ulong) };
    if actual < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        actual == libc::CLONE_NEWNS,
        "actual manager mount namespace required",
    )?;
    Ok(file)
}

fn mount_id(file: &File) -> Result<u64> {
    const STATX_MNT_ID_UNIQUE: u32 = 0x4000;
    let mut value: libc::statx = unsafe { std::mem::zeroed() };
    if unsafe {
        libc::statx(
            file.as_raw_fd(),
            c"".as_ptr(),
            libc::AT_EMPTY_PATH,
            STATX_MNT_ID_UNIQUE,
            &mut value,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        value.stx_mask & STATX_MNT_ID_UNIQUE != 0 && value.stx_mnt_id != 0,
        "actual unique original socket mount identity required",
    )?;
    Ok(value.stx_mnt_id)
}

fn file_context(file: &File) -> Result<Vec<u8>> {
    let before = Node::of(file)?;
    let mut raw = [0_u8; 1024];
    let size = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            raw.as_mut_ptr().cast(),
            raw.len(),
        )
    };
    if size < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        size > 0 && size as usize <= raw.len() && Node::of(file)? == before,
        "complete stable actual original executable context required",
    )?;
    Ok(raw[..size as usize].to_vec())
}

fn server_context(file: &File) -> Result<Vec<u8>> {
    systemd::manager_file_context(file)
}

fn decisions(policy: &LoadedPolicyWitness, old: &str) -> Result<()> {
    let mut seq = Some(policy.av_sequence);
    for (target, class, perms) in [
        (
            LOADER,
            "unix_stream_socket",
            &["create", "connect", "getattr", "read", "write", "getopt"] as &[&str],
        ),
        (HOST, "unix_stream_socket", &["connectto"]),
        (HOST, "process", &["getattr"]),
        (old, "sock_file", &["getattr", "write", "relabelfrom"]),
        (
            MANAGER_LABEL,
            "sock_file",
            &["getattr", "write", "relabelto"],
        ),
    ] {
        access(&policy.root, LOADER, target, class, perms, true, &mut seq)?;
    }
    // No load/enforcement/creation override is part of this one-inode operation.
    access(
        &policy.root,
        LOADER,
        KERNEL,
        "security",
        &["load_policy", "setenforce"],
        false,
        &mut seq,
    )?;
    access(
        &policy.root,
        LOADER,
        LOADER,
        "process",
        &["setfscreate"],
        false,
        &mut seq,
    )?;
    Ok(())
}

/// The only issuer is the current fixed loader. The original endpoint is
/// supplied as an opaque borrow; descriptors or records cannot create it.
pub(crate) struct ManagerLabelPermit<'a> {
    loader: &'a LoaderMacWitness,
    selection: &'a ProductionSelection,
    record: Record,
    sealed: Sealed,
    manager: Executable,
    installer: Executable,
    generation: ManagerEndpointGeneration,
    initial_label: Vec<u8>,
    original_inode: Node,
    mount: File,
    mount_node: Node,
    mount_id: u64,
    deadline: Instant,
}

impl LoaderMacWitness {
    pub(crate) fn manager_label_permit<'a>(
        &'a self,
        selection: &'a ProductionSelection,
        endpoint: &ManagerLabelObservation<'_>,
        deadline: Instant,
    ) -> Result<ManagerLabelPermit<'a>> {
        owner(endpoint.revalidate_until(deadline))?;
        self.revalidate(selection)?;
        let (sealed, raw) = Sealed::read(RECORD, MAX_RECORD)?;
        let record: Record = serde_json::from_slice(&raw)?;
        record.matches(selection, self.loaded_policy())?;
        let manager = Executable::read(
            MANAGER,
            record.manager_elf_bytes,
            &record.manager_elf_sha256,
            endpoint.manager_executable(),
        )?;
        let installer = Executable::read(
            INSTALLER,
            record.labeler_elf_bytes,
            &record.labeler_elf_sha256,
            endpoint.observer_executable(),
        )?;
        let initial_label = server_context(endpoint.server_inode())?;
        require(
            context_matches(&initial_label, &record.original_server_context)
                || context_matches(&initial_label, MANAGER_LABEL),
            "actual original server context is neither the reviewed input nor the fixed final label",
        )?;
        let mount = mount_namespace(endpoint.manager_proc())?;
        let result = ManagerLabelPermit {
            loader: self,
            selection,
            record,
            sealed,
            manager,
            installer,
            generation: owner(endpoint.generation())?,
            initial_label,
            original_inode: Node::of(endpoint.server_inode())?,
            mount_node: Node::of(&mount)?,
            mount,
            mount_id: mount_id(endpoint.server_inode())?,
            deadline,
        };
        decisions(self.loaded_policy(), &result.record.original_server_context)?;
        result.revalidate_original(endpoint, deadline)?;
        Ok(result)
    }
}
impl ManagerLabelPermit<'_> {
    fn common(&self, endpoint: &ManagerLabelObservation<'_>, deadline: Instant) -> Result<()> {
        require(
            deadline == self.deadline,
            "original label deadline cannot be extended",
        )?;
        owner(endpoint.revalidate_until(deadline))?;
        self.loader.revalidate(self.selection)?;
        self.sealed.revalidate()?;
        self.record
            .matches(self.selection, self.loader.loaded_policy())?;
        require(
            owner(endpoint.generation())? == self.generation,
            "label permit belongs to another original manager or observer generation",
        )?;
        require(
            self.original_inode
                .same_inode(Node::of(endpoint.server_inode())?),
            "label permit belongs to another original server inode",
        )?;
        require(
            mount_id(endpoint.server_inode())? == self.mount_id,
            "original socket mount was replaced",
        )?;
        require(
            Node::of(&self.mount)? == self.mount_node,
            "original manager mount namespace custody changed",
        )?;
        for proc in [endpoint.manager_proc(), endpoint.observer_proc()] {
            require(
                Node::of(&mount_namespace(proc)?)?.same_inode(self.mount_node),
                "loader and manager must remain in the same original mount namespace",
            )?;
        }
        self.manager.revalidate(endpoint.manager_executable())?;
        self.installer.revalidate(endpoint.observer_executable())?;
        require(
            context_matches(&file_context(&self.installer.file)?, INSTALLER_EXEC),
            "actual fixed loader executable label differs",
        )?;
        self.loader
            .manager_label_roles(self.selection, endpoint, deadline)?;
        require(
            context_matches(
                &actual_socket_security(endpoint.connection().as_fd())?,
                HOST,
            ),
            "actual same-connection manager SO_PEERSEC differs",
        )?;
        self.loader.loaded_policy().stable_epoch()?;
        owner(endpoint.revalidate_until(deadline))
    }
    pub(crate) fn already_labeled(&self) -> bool {
        context_matches(&self.initial_label, MANAGER_LABEL)
    }
    pub(crate) fn revalidate_original(
        &self,
        endpoint: &ManagerLabelObservation<'_>,
        deadline: Instant,
    ) -> Result<()> {
        self.common(endpoint, deadline)?;
        require(
            server_context(endpoint.server_inode())? == self.initial_label,
            "original server label changed before the fixed operation",
        )?;
        self.common(endpoint, deadline)
    }
    pub(crate) fn revalidate_labeled(
        &self,
        endpoint: &ManagerLabelObservation<'_>,
        deadline: Instant,
    ) -> Result<()> {
        self.common(endpoint, deadline)?;
        require(
            context_matches(&server_context(endpoint.server_inode())?, MANAGER_LABEL),
            "actual original server did not retain the exact dedicated label",
        )?;
        self.common(endpoint, deadline)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn declaration() -> Record {
        Record {
            schema: "droidloom-original-systemd-label-v1".into(),
            base_cohort_sha256: "a".repeat(64),
            runtime_manifest_sha256: "b".repeat(64),
            policy_input_bytes: 2048,
            policy_input_sha256: "c".repeat(64),
            policy_export_bytes: 2048,
            policy_export_sha256: "d".repeat(64),
            manager_elf_bytes: 4096,
            manager_elf_sha256: "e".repeat(64),
            labeler_elf_bytes: 4096,
            labeler_elf_sha256: "f".repeat(64),
            original_server_context: "u:object_r:fixture_socket:s0".into(),
        }
    }
    #[test]
    fn original_label_record_cannot_supply_a_role_path_or_success() {
        assert!(declaration().validate_shape().is_ok());
        for bad in [
            MANAGER_LABEL,
            HOST,
            LOADER,
            "u:object_r:*:s0",
            "u:object_r:tmpfs:s0\n",
            "u:object_r:tmpfs:s0\0",
            "u:object_r:tmpfs:s0:c1",
        ] {
            let mut record = declaration();
            record.original_server_context = bad.into();
            assert!(matches!(
                record.validate_shape(),
                Err(MacError::Rejected(
                    "exact reviewed original object context required"
                ))
            ));
        }
        let mut record = declaration();
        record.policy_export_sha256 = "0".repeat(63);
        assert!(matches!(
            record.validate_shape(),
            Err(MacError::Rejected(
                "manager label declaration needs complete digests"
            ))
        ));
        // No runtime witness or permit is constructed by this declaration test.
    }
}
