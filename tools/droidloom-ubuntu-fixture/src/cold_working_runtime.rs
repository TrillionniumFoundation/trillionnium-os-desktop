//! Source-derived runtime configuration for the actual prepared H2 boot.
//! This retains the cold owner and all original image OFDs. It prepares private
//! source files only: it neither publishes host paths nor grants a boot arm.
use super::{materials::Guard, owner::SealedInput, working_boot::PreparedWorkingBoot};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_working_recovery::contract::{self as c, PayloadPin, WorkingReturnConfiguration},
    ensure, fs,
};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    fs::File,
    path::{Path, PathBuf},
};

const UNIT_SOURCES: [(&str, &[u8]); 3] = [
    (
        c::PARENT_UNIT,
        include_bytes!("../../../packaging/systemd/system/droidloom-working-qualification.service"),
    ),
    (
        c::RETURN_UNIT,
        include_bytes!(
            "../../../packaging/systemd/system/droidloom-working-qualification-return.service"
        ),
    ),
    (
        c::WORKING_TARGET,
        include_bytes!("../../../packaging/systemd/system/droidloom-working-qualification.target"),
    ),
];

fn payload(pin: &FilePin) -> PayloadPin {
    PayloadPin {
        bytes: pin.bytes,
        sha256: pin.sha256.clone(),
    }
}

fn source(path: &Path, value: &impl serde::Serialize) -> Result<SealedInput> {
    let mut bytes = serde_json::to_vec_pretty(value)?;
    bytes.push(b'\n');
    ensure(
        bytes.len() <= 16 * 1024 * 1024,
        "bounded working runtime source required",
    )?;
    files::write_new(path, &bytes, 0o400)?;
    File::open(
        path.parent()
            .ok_or("working runtime source parent absent")?,
    )?
    .sync_all()?;
    SealedInput::open(&files::pin_file(path)?)
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key]
        .as_str()
        .ok_or_else(|| format!("actual working runtime source lacks {key}").into())
}

fn unit_paths(name: &str) -> Result<(String, PathBuf)> {
    ensure(
        UNIT_SOURCES
            .iter()
            .filter(|(known, _)| *known == name)
            .count()
            == 1,
        "working runtime cannot select another unit",
    )?;
    Ok((
        format!("usr/share/droidloom/production/{name}"),
        Path::new("/usr/lib/systemd/system").join(name),
    ))
}

fn verify_unit_source(name: &str, bytes: &[u8]) -> Result<()> {
    let matches: Vec<_> = UNIT_SOURCES
        .iter()
        .filter(|(known, _)| *known == name)
        .collect();
    ensure(
        matches.len() == 1 && bytes == matches[0].1,
        "normal working unit bytes differ from this source-owned contract",
    )
}

fn no_unit_overrides() -> Result<()> {
    for (name, _) in UNIT_SOURCES {
        for directory in [
            "/etc/systemd/system",
            "/run/systemd/system",
            "/etc/systemd/system.control",
            "/run/systemd/system.control",
        ] {
            for member in [name.to_owned(), format!("{name}.d")] {
                let path = Path::new(directory).join(member);
                match std::fs::symlink_metadata(&path) {
                    Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
                    Err(e) => return Err(e.into()),
                    Ok(_) => {
                        return Err(format!(
                            "working unit has an unadmitted override: {}",
                            path.display()
                        )
                        .into());
                    }
                }
            }
        }
    }
    Ok(())
}

fn working_arguments(intent: &str, early: &str, returned: &str) -> Result<String> {
    ensure(
        [intent, early, returned].into_iter().all(c::digest),
        "complete actual working boot commitments required",
    )?;
    let masks = c::PACKAGE_WRITERS
        .iter()
        .chain(c::SUSPEND_TARGETS.iter())
        .map(|name| format!(" systemd.mask={name}"))
        .collect::<String>();
    let value = format!(
        "root=UUID={} ro rootwait init=/usr/lib/droidloom/board-init lsm=lockdown,capability,landlock,yama,selinux,apparmor,bpf,ima,evm enforcing=1 selinux=1 audit=1 panic=10 systemd.wants={} droidloom.working={} droidloom.working.config={} droidloom.working.return={}{}",
        c::ROOT_UUID,
        c::WORKING_TARGET,
        intent,
        early,
        returned,
        masks
    );
    let actual = c::boot_arguments(&value)?;
    ensure(
        actual["droidloom.working"] == intent
            && actual["droidloom.working.config"] == early
            && actual["droidloom.working.return"] == returned,
        "working boot argument readback changed an actual source commitment",
    )?;
    Ok(value)
}

/// These entries are comparisons, never an independently serializable publisher.
/// A later publisher must consume the owning PreparedWorkingRuntime itself.
pub(super) struct WorkingRuntimeFile {
    destination: PathBuf,
    source: FilePin,
    mode: u32,
}

/// Only PreparedWorkingBoot can supply the live owner/Returned/source custody.
/// There is deliberately no deserializer or constructor from a prepared report.
pub(super) struct PreparedWorkingRuntime {
    boot: PreparedWorkingBoot,
    configuration: WorkingReturnConfiguration,
    returned: SealedInput,
    installation: SealedInput,
    launcher: SealedInput,
    sources: Vec<Guard>,
    entries: Vec<WorkingRuntimeFile>,
    arguments: String,
    report: SealedInput,
}

impl PreparedWorkingRuntime {
    pub(super) fn prepare(boot: PreparedWorkingBoot) -> Result<Self> {
        boot.revalidate()?;
        no_unit_overrides()?;
        let materials = boot.materials();
        let admitted = materials.admitted()?;
        let normal = &admitted["normal_initramfs"];
        let normal_materials = &normal["normal_materials"];
        let original: Value =
            serde_json::from_slice(&files::read_pin(boot.intent(), 16 * 1024 * 1024)?)?;
        let (grub_cfg, grubenv) = materials.original_grub_inputs()?;
        let now = rustix::time::clock_gettime(rustix::time::ClockId::Monotonic);
        let installed_ns = u64::try_from(now.tv_sec)?
            .checked_mul(1_000_000_000)
            .and_then(|n| n.checked_add(now.tv_nsec as u64))
            .ok_or("working installation clock overflow")?;
        let installation = source(
            &materials.work().join("WORKING-INSTALLATION.json"),
            &json!({"schema":"droidloom-maintenance-installation-v1",
                "release_id":text(normal_materials, "public_release_id")?,
                "root_uuid":c::ROOT_UUID, "original_entry":c::ORIGINAL_ENTRY,
                "original_kernel":c::ORIGINAL_KERNEL, "grub_cfg":grub_cfg, "grubenv":grubenv,
                "installed_monotonic_ns":installed_ns}),
        )?;
        let executable = Guard::open(
            &materials.normal_host_file(c::RETURN_EXECUTABLE.trim_start_matches('/'))?,
        )?;
        let applications = Guard::open(
            &materials.normal_host_file(c::APPLICATIONS_EXECUTABLE.trim_start_matches('/'))?,
        )?;
        let maintenance = Guard::open(
            &materials.normal_host_file(c::MAINTENANCE_EXECUTABLE.trim_start_matches('/'))?,
        )?;
        let manager = Guard::open(
            &materials.normal_host_file("usr/lib/droidloom/production/current/droidloomd")?,
        )?;
        for guard in [&executable, &applications, &maintenance, &manager] {
            ensure(
                guard.identity().mode & 0o7777 == 0o755,
                "normal working executable mode differs",
            )?;
        }
        let cell = materials.candidate_cell()?;
        let selection = materials.selection()?;
        let mac_files = materials.mac_files()?;
        ensure(
            mac_files.len() == 5,
            "working runtime requires all five actual normal MAC files",
        )?;
        let policies: Vec<_> = mac_files
            .iter()
            .filter(|p| p.path.file_name().is_some_and(|s| s == "policy.bin"))
            .collect();
        ensure(
            policies.len() == 1,
            "one actual normal joint policy required",
        )?;
        let configuration = WorkingReturnConfiguration {
            schema: "droidloom.working-qualification-return.v1".into(),
            intent_sha256: boot.intent().sha256.clone(),
            candidate_id: materials.candidate().into(),
            first_once_candidate: boot.recovery().first_once_candidate.clone(),
            original_boot_id: text(&original, "original_boot_id")?.into(),
            original_kernel: c::ORIGINAL_KERNEL.into(),
            original_entry: c::ORIGINAL_ENTRY.into(),
            root_uuid: c::ROOT_UUID.into(),
            early_config_sha256: boot.early().sha256.clone(),
            admitted_materials_sha256: materials.report().sha256.clone(),
            joint_policy_sha256: policies[0].sha256.clone(),
            host_source_commit: text(normal, "host_source_commit")?.into(),
            host_source_tree: text(normal, "host_source_tree")?.into(),
            recovery: boot.recovery().clone(),
            executable: payload(executable.pin()),
            applications: payload(applications.pin()),
            maintenance: payload(maintenance.pin()),
            installation: payload(installation.pin()),
            cell: payload(&cell),
            selection: payload(&selection),
        };
        configuration.validate()?;
        let returned = source(
            &materials.work().join("WORKING-RETURN.json"),
            &configuration,
        )?;
        let launcher = source(
            &materials.work().join("WORKING-CONTAINER-LAUNCHER.json"),
            &json!({"schema":"droidloom-public-early-launcher-v1",
                "launcher":"early_boot_shared_kernel_v1", "selection_sha256":selection.sha256,
                "manager_sha256":manager.pin().sha256, "manager_bytes":manager.pin().bytes}),
        )?;
        let arguments = working_arguments(
            &configuration.intent_sha256,
            &configuration.early_config_sha256,
            &returned.pin().sha256,
        )?;
        let mut entries = vec![
            WorkingRuntimeFile {
                destination: PathBuf::from("/etc/droidloom/cell.json"),
                source: cell,
                mode: 0o644,
            },
            WorkingRuntimeFile {
                destination: PathBuf::from("/etc/droidloom/container-launcher.json"),
                source: launcher.pin().clone(),
                mode: 0o644,
            },
            WorkingRuntimeFile {
                destination: PathBuf::from(c::INSTALLATION),
                source: installation.pin().clone(),
                mode: 0o400,
            },
            WorkingRuntimeFile {
                destination: PathBuf::from(c::EARLY_CONFIG),
                source: boot.early().clone(),
                mode: 0o400,
            },
            WorkingRuntimeFile {
                destination: PathBuf::from(c::RETURN_CONFIG),
                source: returned.pin().clone(),
                mode: 0o400,
            },
        ];
        for pin in mac_files {
            entries.push(WorkingRuntimeFile {
                destination: Path::new("/etc/droidloom/host-mac")
                    .join(pin.path.file_name().ok_or("normal MAC member absent")?),
                source: pin,
                mode: 0o400,
            });
        }
        let mut sources = vec![executable, applications, maintenance, manager];
        for (name, _) in UNIT_SOURCES {
            let (relative, destination) = unit_paths(name)?;
            let pin = materials.normal_host_file(&relative)?;
            let guard = Guard::open(&pin)?;
            ensure(
                guard.identity().mode & 0o7777 == 0o644,
                "normal working unit mode differs",
            )?;
            verify_unit_source(name, &files::read_pin(&pin, 65536)?)?;
            guard.revalidate()?;
            entries.push(WorkingRuntimeFile {
                destination,
                source: pin,
                mode: 0o644,
            });
            sources.push(guard);
        }
        let mut destinations = BTreeSet::new();
        ensure(
            entries.len() == 13
                && entries
                    .iter()
                    .all(|e| destinations.insert(e.destination.clone())),
            "working runtime fixed publication roster differs",
        )?;
        boot.revalidate()?;
        let report = source(
            &materials.work().join("WORKING-RUNTIME-PREPARED.json"),
            &json!({"schema":"droidloom.working-qualification-runtime-prepared.v1",
                "candidate_id":materials.candidate(), "boot_prepared":boot.report(),
                "boot_intent":boot.intent(), "early_configuration":boot.early(),
                "return_configuration":returned.pin(), "installation":installation.pin(),
                "container_launcher":launcher.pin(), "selection":selection,
                "normal_arguments":arguments, "normal_arguments_sha256":fs::digest(arguments.as_bytes()),
                "runtime_files":entries.iter().map(|e| json!({"destination":e.destination,
                    "source":e.source,"mode":e.mode})).collect::<Vec<_>>(),
                "normal_host_payload_sources":sources.iter().map(|g| json!({"source":g.pin(),
                    "identity":g.identity()})).collect::<Vec<_>>(),
                "same_four_backing_ofds_retained":true, "old_live_retirement_reconstructed":false,
                "runtime_files_published":false, "data_exchanged":false, "boot_armed":false,
                "application_business_accepted":false, "production_ready":false}),
        )?;
        let value = Self {
            boot,
            configuration,
            returned,
            installation,
            launcher,
            sources,
            entries,
            arguments,
            report,
        };
        value.revalidate()?;
        Ok(value)
    }

    pub(super) fn revalidate(&self) -> Result<()> {
        self.boot.revalidate()?;
        self.configuration.validate()?;
        no_unit_overrides()?;
        for source in [
            &self.returned,
            &self.installation,
            &self.launcher,
            &self.report,
        ] {
            source.revalidate()?;
        }
        for source in &self.sources {
            source.revalidate()?;
        }
        let readback: WorkingReturnConfiguration = serde_json::from_slice(&self.returned.read()?)?;
        ensure(
            serde_json::to_value(readback)? == serde_json::to_value(&self.configuration)?,
            "held working return configuration differs from its actual factory",
        )?;
        ensure(
            self.arguments
                == working_arguments(
                    &self.configuration.intent_sha256,
                    &self.configuration.early_config_sha256,
                    &self.returned.pin().sha256,
                )?,
            "working command line left its actual held configuration",
        )?;
        ensure(
            self.entries.len() == 13,
            "fixed working runtime source roster changed",
        )?;
        self.boot.revalidate()
    }

    pub(super) fn report(&self) -> &FilePin {
        self.report.pin()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn working_runtime_uses_fixed_normal_unit_members_and_live_usr_lib_paths() {
        for (name, bytes) in UNIT_SOURCES {
            let (source, target) = unit_paths(name).unwrap();
            assert_eq!(source, format!("usr/share/droidloom/production/{name}"));
            assert_eq!(target, Path::new("/usr/lib/systemd/system").join(name));
            verify_unit_source(name, bytes).unwrap();
            let mut changed = bytes.to_vec();
            changed.extend_from_slice(b"\n[Service]\nExecStart=/bin/true\n");
            assert!(verify_unit_source(name, &changed).is_err());
        }
        for name in [
            "droidloom-original-once.target",
            "../droidloom-working-qualification.service",
            "droidloom-working-qualification-extra.service",
        ] {
            assert!(unit_paths(name).is_err());
            assert!(verify_unit_source(name, b"").is_err());
        }
    }

    #[test]
    fn working_arguments_bind_all_three_actual_pins_and_one_normal_target() {
        let args = working_arguments(&"a".repeat(64), &"b".repeat(64), &"c".repeat(64)).unwrap();
        let parsed = c::boot_arguments(&args).unwrap();
        assert_eq!(parsed["droidloom.working"], "a".repeat(64));
        assert_eq!(parsed["droidloom.working.config"], "b".repeat(64));
        assert_eq!(parsed["droidloom.working.return"], "c".repeat(64));
        assert_eq!(
            args.split_whitespace()
                .filter(|x| x.starts_with("systemd.wants="))
                .count(),
            1
        );
        assert!(!args.contains("systemd.unit="));
        assert!(!args.contains("droidloom.once"));
        for required in [
            "init=/usr/lib/droidloom/board-init",
            "lsm=lockdown,capability,landlock,yama,selinux,apparmor,bpf,ima,evm",
            "enforcing=1",
            "selinux=1",
            "audit=1",
        ] {
            assert_eq!(
                args.split_whitespace().filter(|x| *x == required).count(),
                1
            );
        }
    }

    #[test]
    fn working_arguments_reject_unbound_pins_and_mixed_targets() {
        let pin = "a".repeat(64);
        let invalid = "x".repeat(64);
        for bad in ["", "a", invalid.as_str(), "a systemd.wants=evil.target"] {
            assert!(working_arguments(bad, &pin, &pin).is_err());
            assert!(working_arguments(&pin, bad, &pin).is_err());
            assert!(working_arguments(&pin, &pin, bad).is_err());
        }
        let args = working_arguments(&pin, &pin, &pin).unwrap();
        for extra in [
            "systemd.wants=droidloom-working-qualification.target",
            "systemd.wants=multi-user.target",
            "rd.systemd.wants=droidloom-working-qualification.target",
            "droidloom.once=anything",
        ] {
            assert!(c::boot_arguments(&format!("{args} {extra}")).is_err());
        }
    }
}

/// The fixed runtime input roster, still bound to the actual original-kernel
/// owner, normal sources, and the same four image OFDs. It is consumed by the
/// normal publisher; neither a report nor a caller path constructs this object.
pub(crate) struct WorkingRuntimeSources {
    custody: std::rc::Rc<super::working_custody::WorkingColdCustody>,
    configuration: WorkingReturnConfiguration,
    returned: SealedInput,
    installation: SealedInput,
    launcher: SealedInput,
    sources: Vec<Guard>,
    entries: Vec<WorkingRuntimeFile>,
    arguments: String,
    report: SealedInput,
}
pub(crate) struct WorkingOriginalCellPreimage {
    custody: std::rc::Rc<super::working_custody::WorkingColdCustody>,
    original: Guard,
}
pub(super) struct WorkingGrubSource {
    custody: std::rc::Rc<super::working_custody::WorkingColdCustody>,
    original: super::working_grub::WorkingGrubPreimage,
}
impl WorkingRuntimeFile {
    pub(super) fn target(&self) -> &Path {
        &self.destination
    }
    pub(super) fn source_pin(&self) -> &FilePin {
        &self.source
    }
    pub(super) fn mode(&self) -> u32 {
        self.mode
    }
}
impl PreparedWorkingRuntime {
    pub(super) fn into_publication_sources(
        self,
    ) -> Result<(
        WorkingRuntimeSources,
        WorkingOriginalCellPreimage,
        WorkingGrubSource,
    )> {
        self.revalidate()?;
        let Self {
            boot,
            configuration,
            returned,
            installation,
            launcher,
            sources,
            entries,
            arguments,
            report,
        } = self;
        let (boot, materials) = boot.into_sources()?;
        let (materials, pair, original_cell, grub) = materials.into_sources()?;
        let custody = std::rc::Rc::new(super::working_custody::WorkingColdCustody::new(
            materials, boot, pair,
        )?);
        let original_cell = WorkingOriginalCellPreimage {
            custody: std::rc::Rc::clone(&custody),
            original: original_cell,
        };
        let grub = WorkingGrubSource {
            custody: std::rc::Rc::clone(&custody),
            original: grub,
        };
        let value = WorkingRuntimeSources {
            custody,
            configuration,
            returned,
            installation,
            launcher,
            sources,
            entries,
            arguments,
            report,
        };
        value.revalidate()?;
        original_cell.revalidate()?;
        grub.revalidate()?;
        Ok((value, original_cell, grub))
    }
}
impl WorkingRuntimeSources {
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.custody.revalidate()?;
        self.configuration.validate()?;
        no_unit_overrides()?;
        for source in [
            &self.returned,
            &self.installation,
            &self.launcher,
            &self.report,
        ] {
            source.revalidate()?;
        }
        for source in &self.sources {
            source.revalidate()?;
        }
        let readback: WorkingReturnConfiguration = serde_json::from_slice(&self.returned.read()?)?;
        ensure(
            serde_json::to_value(readback)? == serde_json::to_value(&self.configuration)?,
            "held working return configuration differs from its actual factory",
        )?;
        ensure(
            self.arguments
                == working_arguments(
                    &self.configuration.intent_sha256,
                    &self.configuration.early_config_sha256,
                    &self.returned.pin().sha256,
                )?,
            "working command line left its actual held configuration",
        )?;
        ensure(
            self.entries.len() == 13,
            "fixed working runtime source roster changed",
        )?;
        self.custody.revalidate()
    }
    pub(crate) fn candidate(&self) -> &str {
        self.custody.materials().candidate()
    }
    pub(crate) fn work(&self) -> &Path {
        self.custody.materials().work()
    }
    pub(super) fn entries(&self) -> &[WorkingRuntimeFile] {
        &self.entries
    }
    pub(super) fn report(&self) -> &FilePin {
        self.report.pin()
    }
    pub(super) fn arguments(&self) -> &str {
        &self.arguments
    }
    pub(crate) fn configuration(&self) -> &WorkingReturnConfiguration {
        &self.configuration
    }
    pub(crate) fn boot_intent(&self) -> &FilePin {
        self.custody.boot().intent()
    }
    pub(super) fn recovery_initrd(&self) -> &FilePin {
        self.custody.boot().initrd()
    }
    /// Comparison of the one still-held private normal selection source.
    /// Publication and pair movement continue to require their actual owner.
    pub(crate) fn selection_source(&self) -> Result<FilePin> {
        self.revalidate()?;
        let pin = self.custody.materials().selection_source()?;
        ensure(
            pin.bytes == self.configuration.selection.bytes
                && pin.sha256 == self.configuration.selection.sha256,
            "working selection left its source-owned boot binding",
        )?;
        self.revalidate()?;
        Ok(pin)
    }
    pub(crate) fn label_sources(
        &self,
    ) -> &std::sync::Arc<crate::cold_original_data::labels::OriginalLabelSources> {
        self.custody.materials().label_sources()
    }
}
impl WorkingOriginalCellPreimage {
    pub(super) fn revalidate(&self) -> Result<()> {
        self.custody.revalidate()?;
        self.original.revalidate()?;
        self.custody.revalidate()
    }
    pub(super) fn require_sources(&self, source: &WorkingRuntimeSources) -> Result<()> {
        ensure(
            std::rc::Rc::ptr_eq(&self.custody, &source.custody),
            "working cell preimage belongs to a different live source owner",
        )?;
        self.revalidate()?;
        source.revalidate()
    }
    pub(super) fn pin(&self) -> &FilePin {
        self.original.pin()
    }
    pub(super) fn identity(&self) -> &crate::model::Identity {
        self.original.identity()
    }
}
impl WorkingGrubSource {
    pub(super) fn revalidate(&self) -> Result<()> {
        self.custody.revalidate()?;
        self.original.revalidate()?;
        self.custody.revalidate()
    }
    pub(super) fn require_sources(&self, source: &WorkingRuntimeSources) -> Result<()> {
        ensure(
            std::rc::Rc::ptr_eq(&self.custody, &source.custody),
            "working GRUB preimage belongs to a different live source owner",
        )?;
        self.revalidate()?;
        source.revalidate()
    }
}

impl WorkingRuntimeSources {
    fn require_published_owner(&self, published: &super::PublishedWorkingRuntime) -> Result<()> {
        ensure(
            std::rc::Rc::ptr_eq(&self.custody, &published.source().custody),
            "working pair belongs to another actual published source owner",
        )?;
        published.guard()
    }
    pub(super) fn advance_pair(&self, published: &super::PublishedWorkingRuntime) -> Result<()> {
        self.require_published_owner(published)?;
        self.custody.advance_pair(published)?;
        published.guard()
    }
    pub(super) fn pair_exchanged(
        &self,
        published: &super::PublishedWorkingRuntime,
    ) -> Result<bool> {
        self.require_published_owner(published)?;
        let result = self.custody.pair_exchanged()?;
        published.guard()?;
        Ok(result)
    }
    pub(super) fn restore_pair_cold(
        &self,
        published: &super::PublishedWorkingRuntime,
    ) -> Result<()> {
        self.require_published_owner(published)?;
        self.custody.restore_pair_cold()?;
        published.guard()
    }
}

/// Identity of one actual still-owned cold source. This is not a label proof:
/// only the full normal label transaction can create a batch of inode changes.
pub(crate) struct WorkingLabelSourceIdentity {
    custody: std::rc::Rc<super::working_custody::WorkingColdCustody>,
}
impl WorkingRuntimeSources {
    pub(crate) fn label_source_identity(&self) -> Result<WorkingLabelSourceIdentity> {
        self.revalidate()?;
        Ok(WorkingLabelSourceIdentity {
            custody: std::rc::Rc::clone(&self.custody),
        })
    }
}
impl WorkingLabelSourceIdentity {
    /// Comparison only. A label batch temporarily precedes adoption of the
    /// owner's exact changed checkpoints, so full source guarding belongs after
    /// all batch checkpoints have been verified and advanced together.
    pub(crate) fn require_source(&self, source: &WorkingRuntimeSources) -> Result<()> {
        ensure(
            std::rc::Rc::ptr_eq(&self.custody, &source.custody),
            "working label batch belongs to another actual live source owner",
        )
    }
    pub(crate) fn candidate(&self) -> &str {
        self.custody.materials().candidate()
    }
    pub(crate) fn work(&self) -> &Path {
        self.custody.materials().work()
    }
    pub(crate) fn source_pin(&self) -> &FilePin {
        self.custody.materials().label_sources().source_pin()
    }
    pub(crate) fn revalidate_normal_source(&self) -> Result<()> {
        self.custody
            .materials()
            .label_sources()
            .revalidate_custody()
    }
}
