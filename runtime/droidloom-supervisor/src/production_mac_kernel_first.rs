//! The kernel creates Android init in the early generation. Only the original
//! manager and its named resource services can participate in host preparation.
use super::*;

pub(super) const MANAGER: &str = "u:system_r:init_t:s0";
pub(super) const NSFS: &str = "u:object_r:p4_kernel_ns_handle_t:s0";
pub(super) const INITIAL_SOCKET: &str = "u:object_r:p4_linux_manager_socket_initial_t:s0";
const HOST_DATA: &str = "u:object_r:p4_linux_host_config_t:s0";
const MANAGER_SOCKET: &str = "u:object_r:droidloom_manager_private_socket:s0";
const APP: &str = "u:r:untrusted_app:s0";

pub(super) fn required(root: &File, sequence: &mut Option<u32>) -> Result<()> {
    access(
        root,
        KERNEL,
        INIT,
        "process",
        &["transition"],
        true,
        sequence,
    )?;
    access(
        root,
        KERNEL,
        INIT_EXEC,
        "file",
        &["open", "read", "map", "execute"],
        true,
        sequence,
    )?;
    access(
        root,
        INIT,
        INIT_EXEC,
        "file",
        &["entrypoint"],
        true,
        sequence,
    )?;
    transition(root, KERNEL, INIT_EXEC, INIT)?;
    for target in ["u:r:apexd:s0", LINKERCONFIG] {
        access(
            root,
            INIT,
            target,
            "process",
            &["transition"],
            true,
            sequence,
        )?;
    }
    for host in [BROKER, LOADER, MANAGER] {
        for android in [INIT, APP] {
            access(
                root,
                host,
                android,
                "process",
                &["transition", "dyntransition", "ptrace", "signal"],
                false,
                sequence,
            )?;
            access(
                root,
                android,
                host,
                "process",
                &["transition", "dyntransition", "ptrace", "signal"],
                false,
                sequence,
            )?;
        }
    }
    access(
        root,
        BROKER,
        INIT,
        "process2",
        &["nnp_transition", "nosuid_transition"],
        false,
        sequence,
    )?;
    for android in [INIT, APP] {
        access(
            root,
            android,
            HOST_DATA,
            "file",
            &[
                "open",
                "read",
                "write",
                "append",
                "execute",
                "entrypoint",
                "relabelfrom",
                "relabelto",
            ],
            false,
            sequence,
        )?;
        access(
            root,
            android,
            HOST_DATA,
            "dir",
            &["search", "read", "write", "add_name", "remove_name"],
            false,
            sequence,
        )?;
        access(
            root,
            android,
            MANAGER,
            "unix_stream_socket",
            &["connectto"],
            false,
            sequence,
        )?;
        access(
            root,
            android,
            MANAGER_SOCKET,
            "sock_file",
            &["write", "relabelto", "relabelfrom"],
            false,
            sequence,
        )?;
    }
    for role in [BROKER, LOADER, APP] {
        access(
            root,
            role,
            KERNEL,
            "security",
            &["load_policy", "setenforce", "setbool"],
            false,
            sequence,
        )?;
    }
    Ok(())
}

pub(super) fn board(declaration: &Declaration) -> Result<()> {
    let raw = include_bytes!(
        "../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json"
    );
    let lock: serde_json::Value = serde_json::from_slice(raw)?;
    verify_board_fields(&lock, declaration)
}

pub(super) fn verify_board_fields(
    lock: &serde_json::Value,
    declaration: &Declaration,
) -> Result<()> {
    require(
        lock["kernel"]["release"].as_str() == Some(&declaration.kernel_release)
            && lock["files"]["joint.policy"]["size"].as_u64()
                == Some(declaration.policy_input_bytes)
            && lock["files"]["joint.policy"]["sha256"].as_str()
                == Some(&declaration.policy_input_sha256),
        "kernel-first policy input and release must match the selected board lock",
    )?;
    let profiles = &lock["files"]["ubuntu-apparmor.profiles"]["board_profiles"];
    for (role, expected) in [
        (
            "droidloom-production-broker",
            &declaration.apparmor_broker_policy_sha256,
        ),
        (
            "droidloom-production-android",
            &declaration.apparmor_android_policy_sha256,
        ),
        (
            "droidloom-policy-loader",
            &declaration.apparmor_loader_policy_sha256,
        ),
    ] {
        require(
            profiles[role]["kernel_profile_sha256"].as_str() == Some(expected.as_str()),
            "kernel-first profile digest differs from the reviewed kernel-exported profile",
        )?;
    }
    Ok(())
}

/// Retains one live resource broker or one live fixed manager-socket labeler.
pub(crate) struct EarlyManagerClient(EarlyClient);
enum EarlyClient {
    Broker(crate::production_execution::RuntimeMacOwner),
    Loader(LoaderHostPeerOwner),
    Package(PackageMacOwner),
}

impl EarlyManagerClient {
    pub(crate) fn broker(owner: crate::production_execution::RuntimeMacOwner) -> Result<Self> {
        let value = Self(EarlyClient::Broker(owner));
        value.loaded()?;
        Ok(value)
    }

    pub(crate) fn loader(owner: LoaderHostPeerOwner) -> Result<Self> {
        let value = Self(EarlyClient::Loader(owner));
        value.loaded()?;
        Ok(value)
    }

    pub(crate) fn package(owner: PackageMacOwner) -> Result<Self> {
        let value = Self(EarlyClient::Package(owner));
        value.loaded()?;
        Ok(value)
    }

    fn loaded(&self) -> Result<&LoadedPolicyWitness> {
        let (loaded, selection) = match &self.0 {
            EarlyClient::Broker(owner) => {
                let (mac, selection) = owner
                    .objects()
                    .map_err(|e| MacError::Owner(e.to_string()))?;
                (mac.loaded_policy(), selection)
            }
            EarlyClient::Loader(owner) => {
                let (mac, selection) = owner.objects()?;
                (mac.loaded_policy(), selection)
            }
            EarlyClient::Package(owner) => owner.objects()?,
        };
        require(
            selection.is_kernel_first() && loaded.declaration.early() && loaded.early_media_held(),
            "direct manager connection requires the original kernel-first selection and four media",
        )?;
        Ok(loaded)
    }

    pub(crate) fn check_server(&self, server: &File) -> Result<()> {
        let loaded = self.loaded()?;
        let label = systemd::manager_file_context(server)?;
        require(
            context_matches(&label, MANAGER_SOCKET)
                || matches!(self.0, EarlyClient::Loader(_))
                    && context_matches(&label, INITIAL_SOCKET),
            "direct manager connection requires its fixed server inode label",
        )?;
        loaded.stable_epoch()
    }

    pub(crate) fn check_peer(&self, connection: &File, manager: &File) -> Result<()> {
        let loaded = self.loaded()?;
        require(
            context_matches(&actual_socket_security(connection.as_fd())?, MANAGER)
                && context_matches(&proc_attr(manager, false)?, MANAGER)
                && proc_attr(manager, true)? == b"unconfined\n",
            "direct manager peer and original PID 1 must have the fixed SELinux and AppArmor identities",
        )?;
        loaded.stable_epoch()
    }

    pub(crate) fn network(&self, file: &File) -> Result<()> {
        let loaded = self.loaded()?;
        require(
            kind(file)? == 0x6e736673,
            "direct manager network descriptor must be nsfs",
        )?;
        policy::fixed_namespace_label(file, &loaded.declaration)?;
        let mut id = 0_u64;
        let ty = unsafe { libc::ioctl(file.as_raw_fd(), 0xb703, 0 as libc::c_ulong) };
        if ty < 0 || unsafe { libc::ioctl(file.as_raw_fd(), 0x8008_b70d, &mut id) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
        require(
            ty == libc::CLONE_NEWNET && id == 7,
            "direct manager socket requires the kernel's initial network namespace",
        )?;
        loaded.stable_epoch()
    }
}
