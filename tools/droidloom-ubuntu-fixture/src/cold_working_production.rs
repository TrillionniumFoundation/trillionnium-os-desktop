//! Normal cold production transition materials. Construction requires the
//! actual prepared working owner and its independently admitted normal image.
use super::*;
use crate::production_commit_contract as p;
pub(super) struct PreparedProduction {
    configuration: SealedInput,
    prefix: Guard,
    programs: Vec<Guard>,
}
fn bytes(pin: &FilePin) -> p::BytesPin {
    p::BytesPin {
        bytes: pin.bytes,
        sha256: pin.sha256.clone(),
    }
}
impl PreparedProduction {
    pub(super) fn prepare(
        boot: &PreparedWorkingBoot,
        working: &WorkingReturnConfiguration,
        grub_cfg: &FilePin,
    ) -> Result<Self> {
        boot.revalidate()?;
        working.validate()?;
        ensure(
            working.production_commit.is_none(),
            "production source core already refers to another commit",
        )?;
        let materials = boot.materials();
        let (systemctl, journalctl) = materials.normal_service_programs()?;
        let mut programs = vec![Guard::open(&systemctl)?, Guard::open(&journalctl)?];
        // This is the original-host normal tool already admitted by its source-owned
        // GRUB path. The exact complete ELF was read in the private normal-tool gate.
        let grub = FilePin {
            path: PathBuf::from(p::GRUB_TOOL),
            bytes: 1_368_360,
            sha256: "2e4f8b60ba8712989f87d927d731a368af8620da1227a3090455ea7897ce1338".into(),
        };
        let live = Guard::open(&grub)?;
        ensure(
            live.identity().mode & 0o7777 == 0o755,
            "normal GRUB tool is not executable",
        )?;
        let copy = materials.work().join("PRODUCTION-GRUB-EDITENV");
        files::copy_pin(&grub, &copy, 0o755)?;
        live.revalidate()?;
        let copied = files::pin_file(&copy)?;
        ensure(
            bytes(&copied) == bytes(&grub),
            "normal GRUB tool copy differs",
        )?;
        programs.push(Guard::open(&copied)?);
        let raw = match std::fs::symlink_metadata(p::CUSTOM) {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Vec::new(),
            Err(e) => return Err(e.into()),
            Ok(_) => {
                let pin = files::pin_file(Path::new(p::CUSTOM))?;
                ensure(
                    pin.bytes <= 1024 * 1024,
                    "original custom GRUB source exceeds fixed bound",
                )?;
                let held = Guard::open(&pin)?;
                let raw = files::read_pin(&pin, 1024 * 1024)?;
                held.revalidate()?;
                raw
            }
        };
        let text = std::str::from_utf8(&raw)?;
        ensure(
            !text.contains('\0')
                && !text.contains("droidloom-working-qualification-")
                && !text.contains("droidloom-original-once-")
                && !text.contains("droidloom_production")
                && !text.contains("droidloom-production-"),
            "unresolved original GRUB transition exists",
        )?;
        let prefix_path = materials.work().join("PRODUCTION-GRUB-PREFIX.cfg");
        files::write_new(&prefix_path, &raw, 0o400)?;
        let prefix = Guard::open(&files::pin_file(&prefix_path)?)?;
        let core = serde_json::to_vec(working)?;
        let configuration = p::Configuration {
            schema: "droidloom.production-commit-source.v1".into(),
            candidate_id: working.candidate_id.clone(),
            working_intent_sha256: working.intent_sha256.clone(),
            working_early_sha256: working.early_config_sha256.clone(),
            source_commit: working.host_source_commit.clone(),
            source_tree: working.host_source_tree.clone(),
            joint_policy_sha256: working.joint_policy_sha256.clone(),
            applications: p::BytesPin {
                bytes: working.applications.bytes,
                sha256: working.applications.sha256.clone(),
            },
            cell: p::BytesPin {
                bytes: working.cell.bytes,
                sha256: working.cell.sha256.clone(),
            },
            selection: p::BytesPin {
                bytes: working.selection.bytes,
                sha256: working.selection.sha256.clone(),
            },
            normal_initrd: bytes(boot.ordinary_initrd()),
            working_return_core: p::BytesPin {
                bytes: core.len() as u64,
                sha256: fs::digest(&core),
            },
            original_grub_cfg: bytes(grub_cfg),
            original_grub_cfg_mode: Guard::open(grub_cfg)?.identity().mode & 0o7777,
            original_custom: bytes(prefix.pin()),
            grub_editenv: bytes(&grub),
            systemctl: bytes(&systemctl),
            journalctl: bytes(&journalctl),
        };
        configuration.validate()?;
        let configuration = source(
            &materials.work().join("PRODUCTION-COMMIT.json"),
            &configuration,
        )?;
        let value = Self {
            configuration,
            prefix,
            programs,
        };
        value.revalidate()?;
        boot.revalidate()?;
        Ok(value)
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        self.configuration.revalidate()?;
        self.prefix.revalidate()?;
        for p in &self.programs {
            p.revalidate()?;
        }
        Ok(())
    }
    pub(super) fn revalidate_custody(&self) -> Result<()> {
        self.configuration.revalidate_custody()?;
        self.prefix.revalidate_custody()?;
        for p in &self.programs {
            p.revalidate_custody()?;
        }
        Ok(())
    }
    pub(super) fn configuration(&self) -> &FilePin {
        self.configuration.pin()
    }
    pub(super) fn prefix(&self) -> &FilePin {
        self.prefix.pin()
    }
    pub(super) fn document(&self) -> Result<p::Configuration> {
        self.revalidate()?;
        let doc = serde_json::from_slice(&self.configuration.read()?)?;
        Ok(doc)
    }
    pub(super) fn observation(&self) -> Value {
        json!({"source_configuration":self.configuration.pin(),"original_grub_prefix":self.prefix.pin(),
   "normal_program_sources":self.programs.iter().map(|g|g.pin()).collect::<Vec<_>>(),
   "live_complete_required":true,"production_ready":false})
    }
}
