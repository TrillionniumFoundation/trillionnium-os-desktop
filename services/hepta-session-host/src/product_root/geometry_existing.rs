//! Open only an existing original deployment and its exact protected bind.
use super::*;
use codex_hepta_agentd::{HostAuthorityRegistration, HostAuthorityServiceConfig};

impl Product {
    pub(in crate::product_root) fn open_existing(
        inputs: &Inputs,
        config: &HostAuthorityServiceConfig,
        prior: &HostAuthorityRegistration,
        preparation: Arc<super::super::recovery_preparation::RecoveryPreparation>,
    ) -> Result<Self> {
        fs::root_directory(&inputs.prefix)?;
        let admin = inputs.prefix.join("admin");
        fs::root_directory(&admin)?;
        let source = inputs.prefix.join("a");
        let target = inputs.prefix.join("m");
        fs::root_directory(&source)?;
        fs::root_directory(&target)?;
        let runtime = inputs.prefix.join("r");
        fs::root_directory(&runtime)?;
        let mode = std::fs::symlink_metadata(&runtime)?;
        if mode.mode() & 0o7777 != 0o2710
            || mode.gid() != inputs.gid
            || [
                &config.sockets.observation,
                &config.sockets.issuer,
                &config.sockets.checkpoint,
                config
                    .sockets
                    .device_frontier
                    .as_ref()
                    .ok_or("old Device lane absent")?,
                config
                    .sockets
                    .notes_frontier
                    .as_ref()
                    .ok_or("old Notes lane absent")?,
            ]
            .iter()
            .any(|path| path.parent() != Some(runtime.as_path()))
        {
            return Err("original Root runtime lane custody differs".into());
        }
        let bind = &config.required_bind;
        let actual = std::fs::symlink_metadata(&source)?;
        if bind.source_path != source
            || bind.mountpoint != target
            || config.state_dir != target.join("state")
            || (actual.dev(), actual.ino()) != (bind.device, bind.inode)
            || actual.mode() & 0o7777 != 0o700
            || config.peer_uid != inputs.uid
            || config.peer_gid != inputs.gid
        {
            return Err(
                "existing Root source/custody/UID differs from original registration".into(),
            );
        }
        let mounted = std::fs::metadata(&target)?;
        let owned = (mounted.dev(), mounted.ino()) != (bind.device, bind.inode);
        if owned {
            if std::fs::read_dir(&target)?.next().is_some() {
                return Err("unmounted original mountpoint is not empty".into());
            }
            let from = CString::new(source.as_os_str().as_bytes())?;
            let to = CString::new(target.as_os_str().as_bytes())?;
            // SAFETY: Root reattaches only the original protected physical
            // source/inode. No filesystem, state, epoch or database is created.
            if unsafe {
                libc::mount(
                    from.as_ptr(),
                    to.as_ptr(),
                    std::ptr::null(),
                    libc::MS_BIND,
                    std::ptr::null(),
                )
            } != 0
            {
                return Err(std::io::Error::last_os_error().into());
            }
        }
        let mount = FreshMount {
            path: target.clone(),
            device: bind.device,
            inode: bind.inode,
            owned,
        };
        verify_existing_bind(bind)?;
        let fleet = HeptaFleetRoot::parse(inputs.prefix.join("f"))?;
        let registry = FleetRegistry::open_existing(fleet.clone())?;
        let agent = prior.registered_identity.agent_id.clone();
        // Original Fleet validates its complete transition history. A normal
        // Running/Draining/Stopped advances lifecycle generation, not spawn;
        // any later Starting, gap or corrupt transition still refuses recovery.
        let record =
            registry.load_agent_for_spawn(&agent, prior.registered_identity.spawn_generation)?;
        if registry.load()?.agents.len() != 1
            || prior.registered_identity.fleet_root != fleet.as_path()
            || prior.registered_identity.workspace != inputs.prefix.join("w")
            || record.manifest.workspace.as_path() != prior.registered_identity.workspace
            || serde_json::to_value(&record.manifest.resources)?
                != serde_json::to_value(&prior.registered_identity.resources)?
        {
            return Err(
                "original Fleet identity/generation differs; no fresh or later recovery fallback"
                    .into(),
            );
        }
        let user = inputs.prefix.join("u");
        fs::root_directory(&user)?;
        for name in ["home", "state", "replay", "notes"] {
            fs::user_directory(&user.join(name), inputs.uid)?;
        }
        Ok(Self {
            prefix: inputs.prefix.clone(),
            admin,
            authority: config.state_dir.clone(),
            bind: bind.clone(),
            registry,
            agent,
            record,
            user,
            mount,
            _recovery_preparation: Some(preparation),
        })
    }
}

pub(in crate::product_root) fn verify_existing_bind(
    bind: &HostAuthorityBindIdentity,
) -> Result<()> {
    fs::root_directory(&bind.mountpoint)?;
    fs::root_directory(&bind.source_path)?;
    let source = std::fs::symlink_metadata(&bind.source_path)?;
    let target = std::fs::metadata(&bind.mountpoint)?;
    if (source.dev(), source.ino()) != (bind.device, bind.inode)
        || (target.dev(), target.ino()) != (bind.device, bind.inode)
        || source.mode() & 0o7777 != 0o700
        || target.mode() & 0o7777 != 0o700
    {
        return Err("original bind geometry changed".into());
    }
    let mut mounts = String::new();
    std::io::Read::take(std::fs::File::open("/proc/self/mountinfo")?, 1_048_577)
        .read_to_string(&mut mounts)?;
    let path = bind.mountpoint.to_str().ok_or("mount path is not UTF-8")?;
    if mounts.len() > 1_048_576
        || !mounts
            .lines()
            .any(|line| line.split_whitespace().nth(4) == Some(path))
    {
        return Err("the exact original Root bind is not mounted".into());
    }
    Ok(())
}
