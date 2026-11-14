//! Fixed loader identity over the same complete loaded-policy observation.
//!
//! This observer has no policy-load, xattr mutation, exec or Ready operation.
//! A future fixed installer still needs the actual original manager endpoint,
//! reviewed old server label, executable identity and a consumed mutation stage.
use super::*;

fn fixed_loader_identity(selinux: &[u8], apparmor: &[u8]) -> Result<()> {
    require(
        context_matches(selinux, LOADER),
        "actual loader SELinux identity differs",
    )?;
    require(
        apparmor == AA_LOADER,
        "loader AppArmor profile is not the reviewed enforcing profile",
    )
}

fn loader_nnp(proc: &File) -> Result<()> {
    let status = open_at(proc.as_raw_fd(), c"status", libc::O_RDONLY)?;
    require(
        kind(&status)? == PROC_MAGIC,
        "actual loader status from procfs",
    )?;
    let raw = bounded(&status, 65536)?;
    let text = std::str::from_utf8(&raw).map_err(|_| MacError::Rejected("loader status UTF-8"))?;
    let mut values = text
        .lines()
        .filter_map(|line| line.strip_prefix("NoNewPrivs:"));
    require(
        values.next().is_some_and(|value| value.trim() == "1") && values.next().is_none(),
        "fixed loader requires actual no_new_privs",
    )
}

fn loader_socket_identity() -> Result<()> {
    let mut fds = [-1; 2];
    if unsafe {
        libc::socketpair(
            libc::AF_UNIX,
            libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
            0,
            fds.as_mut_ptr(),
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    let pair = unsafe { [File::from_raw_fd(fds[0]), File::from_raw_fd(fds[1])] };
    for file in &pair {
        require(
            context_matches(&actual_socket_security(file.as_fd())?, LOADER),
            "socket peer identity is not the actual loader SELinux context",
        )?;
    }
    Ok(())
}

/// Distinct from the broker capability, with no conversion between the roles.
/// Construction reads the current thread through fixed kernel interfaces; no
/// caller-supplied role, process, pathname, descriptor or JSON creates a witness.
pub(crate) struct LoaderMacWitness {
    loaded: LoadedPolicyWitness,
}

impl LoaderMacWitness {
    pub(crate) fn acquire(selection: &ProductionSelection) -> Result<Self> {
        let value = Self {
            loaded: LoadedPolicyWitness::acquire(selection)?,
        };
        value.revalidate(selection)?;
        loader_socket_identity()?;
        value.revalidate(selection)?;
        Ok(value)
    }

    pub(crate) fn revalidate(&self, selection: &ProductionSelection) -> Result<()> {
        self.loaded.revalidate(selection)?;
        fixed_loader_identity(
            &proc_attr(&self.loaded.own_proc, false)?,
            &proc_attr(&self.loaded.own_proc, true)?,
        )?;
        loader_nnp(&self.loaded.own_proc)?;
        self.loaded.stable_epoch()
    }

    pub(crate) fn loaded_policy(&self) -> &LoadedPolicyWitness {
        &self.loaded
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixed_loader_role_rejects_broker_host_and_wrong_enforcement() {
        // These are only wire-value controls, never runtime witness factories.
        assert!(fixed_loader_identity(LOADER.as_bytes(), AA_LOADER).is_ok());
        for wrong in [
            BROKER.as_bytes(),
            HOST.as_bytes(),
            INIT.as_bytes(),
            b"unconfined",
        ] {
            assert!(matches!(
                fixed_loader_identity(wrong, AA_LOADER),
                Err(MacError::Rejected("actual loader SELinux identity differs"))
            ));
        }
        for wrong in [
            AA_BROKER,
            AA_ANDROID,
            b"unconfined\n",
            b"droidloom-policy-loader (complain)\n",
            b"droidloom-policy-loader (enforce)\n\n",
        ] {
            assert!(matches!(
                fixed_loader_identity(LOADER.as_bytes(), wrong),
                Err(MacError::Rejected(
                    "loader AppArmor profile is not the reviewed enforcing profile"
                ))
            ));
        }
        assert!(!context_matches(
            b"u:r:droidloom_policy_loader:s0\0extra",
            LOADER
        ));
    }
}
