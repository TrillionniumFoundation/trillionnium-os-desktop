//! Original Fleet creation and one explicit new bind mount. Never recovery.
use super::{Result, config::Inputs, fs};
use codex_hepta_agentd::HostAuthorityBindIdentity;
use codex_hepta_contracts::AgentId;
use codex_hepta_fleet::{
    AgentManifest, AgentRecord, FleetRegistry, ResourceBudget, WorkspaceBinding,
};
use codex_hepta_paths::HeptaFleetRoot;
use std::ffi::CString;
use std::io::Read;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};

pub(super) struct Fresh {
    pub prefix: PathBuf,
    pub admin: PathBuf,
    pub authority: PathBuf,
    pub bind: HostAuthorityBindIdentity,
    pub registry: FleetRegistry,
    pub agent: AgentId,
    pub record: AgentRecord,
    pub user: PathBuf,
    mount: FreshMount,
}

struct FreshMount {
    path: PathBuf,
    device: u64,
    inode: u64,
}

impl Drop for FreshMount {
    fn drop(&mut self) {
        if std::fs::metadata(&self.path)
            .is_ok_and(|m| m.dev() == self.device && m.ino() == self.inode)
            && let Ok(path) = CString::new(self.path.as_os_str().as_bytes())
        {
            // SAFETY: this invocation created this exact pinned mount. No force
            // or lazy detach: busy/error remains visible for explicit cleanup.
            if unsafe { libc::umount2(path.as_ptr(), 0) } != 0 {
                eprintln!(
                    "original Root bind remains mounted: {}",
                    self.path.display()
                );
            }
        }
    }
}

impl Fresh {
    pub(super) fn create(inputs: &Inputs) -> Result<Self> {
        // SAFETY: only reads real credentials.
        if unsafe { libc::getuid() } != 0 || unsafe { libc::geteuid() } != 0 {
            return Err("first deployment requires explicit actual UID0".into());
        }
        let base = Path::new("/var/lib/trill");
        if !base.exists() {
            fs::root_directory(Path::new("/var/lib"))?;
            fs::directory_new(base, 0o755, None)?;
        }
        fs::root_directory(base)?;
        if std::fs::symlink_metadata(&inputs.prefix).is_ok() {
            return Err("fresh entry refuses an existing or partial deployment".into());
        }
        fs::directory_new(&inputs.prefix, 0o750, Some((0, inputs.gid)))?;
        let admin = inputs.prefix.join("admin");
        fs::directory_new(&admin, 0o700, None)?;
        let source = inputs.prefix.join("a");
        let target = inputs.prefix.join("m");
        fs::directory_new(&source, 0o700, None)?;
        fs::directory_new(&target, 0o700, None)?;
        let from = CString::new(source.as_os_str().as_bytes())?;
        let to = CString::new(target.as_os_str().as_bytes())?;
        // SAFETY: explicit Root binds two newly created physical directories.
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
        let metadata = std::fs::metadata(&target)?;
        let mount = FreshMount {
            path: target.clone(),
            device: metadata.dev(),
            inode: metadata.ino(),
        };
        let bind = HostAuthorityBindIdentity {
            mountpoint: target.clone(),
            source_path: source,
            device: metadata.dev(),
            inode: metadata.ino(),
        };
        let fleet_path = inputs.prefix.join("f");
        let fleet = HeptaFleetRoot::parse(fleet_path)?;
        let registry = FleetRegistry::initialize(fleet.clone())?;
        let workspace = inputs.prefix.join("w");
        fs::directory_new(&workspace, 0o700, None)?;
        let mut random = [0u8; 16];
        std::fs::File::open("/dev/urandom")?.read_exact(&mut random)?;
        random[6] = (random[6] & 0x0f) | 0x40;
        random[8] = (random[8] & 0x3f) | 0x80;
        let mut uuid = String::with_capacity(36);
        for (index, byte) in random.iter().enumerate() {
            if [4, 6, 8, 10].contains(&index) {
                uuid.push('-');
            }
            uuid.push_str(&format!("{byte:02x}"));
        }
        let agent = AgentId::parse(uuid)?;
        let record = registry.register(AgentManifest::new(
            agent.clone(),
            WorkspaceBinding::new(workspace, &fleet)?,
            ResourceBudget::local_default(),
        )?)?;
        let user = inputs.prefix.join("u");
        // Root retains the parent entries; the owner gets only these four
        // private child directories. It cannot redirect a later Root create.
        fs::directory_new(&user, 0o750, Some((0, inputs.gid)))?;
        for name in ["home", "state", "replay", "notes"] {
            fs::directory_new(&user.join(name), 0o700, Some((inputs.uid, inputs.gid)))?;
        }
        Ok(Self {
            prefix: inputs.prefix.clone(),
            admin,
            authority: target.join("state"),
            bind,
            registry,
            agent,
            record,
            user,
            mount,
        })
    }

    pub(super) fn mounted(&self) -> bool {
        std::fs::metadata(&self.mount.path)
            .is_ok_and(|m| m.dev() == self.mount.device && m.ino() == self.mount.inode)
    }
}
