//! Immutable original-machine once-boot contract, shared by early recovery and
//! the normal-root return helper. These fields are not an admission receipt.
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, io};
pub(crate) const KERNEL: &str = "6.18.64-p4ctx6181-fusectl-aafs-peer-r1";
pub(crate) const KERNEL_SHA: &str =
    "19052ac77e40a86147f6bc186739763628916033f7c36f3448b4a872914090df";
pub(crate) const CONFIG_SHA: &str =
    "bccb147083a909408e25dc63f1dd58cf465ee19bcabc660916a1fa28cc67a3e1";
pub(crate) const MODULE_SHA: &str =
    "4986134839bcf86e84a07c75f8d22d686893aeae6c423af9e7af3276e1d8f61c";
pub(crate) const MODULE_REL: &str = "kernel/drivers/watchdog/softdog.ko";
pub(crate) const MODULE_BYTES: u64 = 21561;
pub(crate) const ROOT_UUID: &str = "01c27223-3933-481e-9836-7bd0ef1be8c9";
pub(crate) const ORIGINAL_KERNEL: &str = "7.0.14-p4cred1";
pub(crate) const ORIGINAL_ENTRY: &str = "gnulinux-advanced-01c27223-3933-481e-9836-7bd0ef1be8c9>gnulinux-7.0.14-p4cred1-advanced-01c27223-3933-481e-9836-7bd0ef1be8c9";
pub(crate) const EARLY_CONFIG: &str = "/etc/droidloom/qualification/early.json";
pub(crate) const RETURN_CONFIG: &str = "/etc/droidloom/qualification/return.json";
pub(crate) const EARLY_EXECUTABLE: &str = "/usr/lib/droidloom/qualification/once-recovery";
pub(crate) const RETURN_EXECUTABLE: &str =
    "/usr/lib/droidloom/production/current/droidloom-original-once-return";
pub(crate) const MAINTENANCE_EXECUTABLE: &str =
    "/usr/lib/droidloom/production/current/droidloom-maintenance";
pub(crate) const INSTALLATION: &str = "/etc/droidloom-maintenance/installation.json";
pub(crate) const COLLECT_BUDGET_SECONDS: u32 = 90;
// These exact original-host units can mutate package/source or snap state.
// Their persistent mask transaction and actual retirement are independently
// verified by the physical owner; command-line masks are an additional gate.
pub(crate) const PACKAGE_WRITERS: [&str; 11] = [
    "apt-daily.service",
    "apt-daily.timer",
    "apt-daily-upgrade.service",
    "apt-daily-upgrade.timer",
    "unattended-upgrades.service",
    "packagekit.service",
    "packagekit-offline-update.service",
    "snapd.service",
    "snapd.socket",
    "snapd.snap-repair.service",
    "snapd.snap-repair.timer",
];
pub(crate) const SUSPEND_TARGETS: [&str; 5] = [
    "sleep.target",
    "suspend.target",
    "hibernate.target",
    "hybrid-sleep.target",
    "suspend-then-hibernate.target",
];
pub(crate) fn reject(why: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, why)
}
pub(crate) fn digest(v: &str) -> bool {
    v.len() == 64
        && v.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
pub(crate) fn commit(v: &str) -> bool {
    v.len() == 40
        && v.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
pub(crate) fn uuid(v: &str) -> bool {
    v.len() == 36
        && v.bytes().enumerate().all(|(i, b)| {
            if [8, 13, 18, 23].contains(&i) {
                b == b'-'
            } else {
                b.is_ascii_digit() || (b'a'..=b'f').contains(&b)
            }
        })
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RecoveryBootSpec {
    pub(crate) schema: String,
    pub(crate) candidate_id: String,
    pub(crate) helper_bytes: u64,
    pub(crate) helper_sha256: String,
    pub(crate) kernel_release: String,
    pub(crate) kernel_sha256: String,
    pub(crate) kernel_config_sha256: String,
    pub(crate) module_relative: String,
    pub(crate) module_bytes: u64,
    pub(crate) module_sha256: String,
    pub(crate) watchdog_seconds: u32,
    pub(crate) collect_at_boot_seconds: u32,
    pub(crate) return_at_boot_seconds: u32,
    pub(crate) panic_seconds: u32,
}
impl RecoveryBootSpec {
    pub(crate) fn validate(&self) -> io::Result<()> {
        if self.schema != "droidloom.original-once-recovery-boot.v1"
            || !digest(&self.candidate_id)
            || !digest(&self.helper_sha256)
            || !(1024..=128 * 1024 * 1024).contains(&self.helper_bytes)
            || self.kernel_release != KERNEL
            || self.kernel_sha256 != KERNEL_SHA
            || self.kernel_config_sha256 != CONFIG_SHA
            || self.module_relative != MODULE_REL
            || self.module_bytes != MODULE_BYTES
            || self.module_sha256 != MODULE_SHA
        {
            return Err(reject(
                "recovery is not the exact selected shared kernel and normal helper",
            ));
        }
        // unit_state passes every system/user name in one command: two 10s
        // batches per status, status twice, plus one 30s journal = 70s.
        // Permit a 90s command, 30s collection slack and 180s reboot margin.
        if !(600..=3600).contains(&self.watchdog_seconds)
            || self.panic_seconds != 10
            || self.collect_at_boot_seconds < 120
            || self
                .collect_at_boot_seconds
                .checked_add(120)
                .is_none_or(|v| v > self.return_at_boot_seconds)
            || self
                .return_at_boot_seconds
                .checked_add(180)
                .is_none_or(|v| v > self.watchdog_seconds)
        {
            return Err(reject(
                "once deadlines do not cover the normal collector and reboot",
            ));
        }
        Ok(())
    }
    pub(crate) fn parameters(&self) -> io::Result<std::ffi::CString> {
        self.validate()?;
        std::ffi::CString::new(format!(
            "soft_margin={} nowayout=1 soft_active_on_boot=1 soft_noboot=0 soft_panic=0",
            self.watchdog_seconds
        ))
        .map_err(io::Error::other)
    }
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct EarlyConfiguration {
    pub(crate) schema: String,
    pub(crate) intent_sha256: String,
    pub(crate) recovery: RecoveryBootSpec,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct PayloadPin {
    pub(crate) bytes: u64,
    pub(crate) sha256: String,
}
impl PayloadPin {
    pub(crate) fn validate(&self, limit: u64) -> io::Result<()> {
        if self.bytes == 0 || self.bytes > limit || !digest(&self.sha256) {
            return Err(reject("invalid fixed once payload pin"));
        }
        Ok(())
    }
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ReturnConfiguration {
    pub(crate) schema: String,
    pub(crate) intent_sha256: String,
    pub(crate) candidate_id: String,
    pub(crate) original_boot_id: String,
    pub(crate) original_kernel: String,
    pub(crate) original_entry: String,
    pub(crate) root_uuid: String,
    pub(crate) early_config_sha256: String,
    pub(crate) admitted_materials_sha256: String,
    pub(crate) joint_policy_sha256: String,
    pub(crate) host_source_commit: String,
    pub(crate) host_source_tree: String,
    pub(crate) recovery: RecoveryBootSpec,
    pub(crate) executable: PayloadPin,
    pub(crate) maintenance: PayloadPin,
    pub(crate) installation: PayloadPin,
    pub(crate) cell: PayloadPin,
    pub(crate) selection: PayloadPin,
}
impl ReturnConfiguration {
    pub(crate) fn validate(&self) -> io::Result<()> {
        self.recovery.validate()?;
        if self.schema != "droidloom.original-once-return.v1"
            || !digest(&self.intent_sha256)
            || !digest(&self.candidate_id)
            || self.candidate_id != self.recovery.candidate_id
            || !uuid(&self.original_boot_id)
            || self.original_kernel != ORIGINAL_KERNEL
            || self.original_entry != ORIGINAL_ENTRY
            || self.root_uuid != ROOT_UUID
            || !digest(&self.early_config_sha256)
            || !digest(&self.admitted_materials_sha256)
            || !digest(&self.joint_policy_sha256)
            || !commit(&self.host_source_commit)
            || !commit(&self.host_source_tree)
        {
            return Err(reject(
                "return configuration is not bound to the original-machine qualification",
            ));
        }
        self.executable.validate(128 * 1024 * 1024)?;
        self.maintenance.validate(1024 * 1024)?;
        self.installation.validate(1024 * 1024)?;
        self.cell.validate(1024 * 1024)?;
        self.selection.validate(1024 * 1024)
    }
    pub(crate) fn runtime_evidence_directory(&self) -> std::path::PathBuf {
        // Candidate-visible output is separate from the excluded private
        // qualification intents, original preimages and rollback material.
        std::path::Path::new("/var/lib/droidloom/qualification")
            .join(format!("original-once-{}", self.candidate_id))
            .join("runtime-evidence")
    }
}
pub(crate) fn boot_arguments(input: &str) -> io::Result<BTreeMap<String, String>> {
    if input.len() > 32768 {
        return Err(reject("once command line exceeds bound"));
    }
    let mut result = BTreeMap::new();
    let mut masks = BTreeMap::<&str, usize>::new();
    for arg in input.split_whitespace() {
        let Some((name, value)) = arg.split_once('=') else {
            continue;
        };
        if [
            "droidloom.once",
            "droidloom.once.config",
            "droidloom.once.return",
            "root",
            "panic",
        ]
        .contains(&name)
        {
            if result.insert(name.into(), value.into()).is_some() {
                return Err(reject("duplicate once boot argument"));
            }
        } else if name.starts_with("droidloom.once") {
            return Err(reject("unknown once boot argument"));
        }
        if name == "systemd.mask" {
            *masks.entry(value).or_default() += 1;
        }
    }
    if result.len() != 5
        || result.get("root") != Some(&format!("UUID={ROOT_UUID}"))
        || result.get("panic").map(String::as_str) != Some("10")
        || [
            "droidloom.once",
            "droidloom.once.config",
            "droidloom.once.return",
        ]
        .iter()
        .any(|key| !digest(result.get(*key).map_or("", String::as_str)))
    {
        return Err(reject("missing or invalid qualification boot binding"));
    }
    if masks.len() != PACKAGE_WRITERS.len() + SUSPEND_TARGETS.len() {
        return Err(reject("once boot masks must be the exact fixed set"));
    }
    for target in PACKAGE_WRITERS.iter().chain(SUSPEND_TARGETS.iter()) {
        if masks.get(target) != Some(&1) {
            return Err(reject(
                "once qualification requires every fixed writer and suspend mask",
            ));
        }
    }
    Ok(result)
}
#[cfg(test)]
mod tests {
    use super::*;
    fn cmdline() -> String {
        format!(
            "root=UUID={ROOT_UUID} panic=10 droidloom.once={} droidloom.once.config={} droidloom.once.return={} systemd.mask=sleep.target systemd.mask=suspend.target systemd.mask=hibernate.target systemd.mask=hybrid-sleep.target systemd.mask=suspend-then-hibernate.target",
            "a".repeat(64),
            "b".repeat(64),
            "c".repeat(64)
        ) + &PACKAGE_WRITERS
            .iter()
            .map(|name| format!(" systemd.mask={name}"))
            .collect::<String>()
    }
    #[test]
    fn unique_binding_and_all_suspend_masks_are_required() {
        let line = cmdline();
        assert_eq!(boot_arguments(&line).unwrap().len(), 5);
        for extra in [
            "root=UUID=bad",
            "panic=0",
            "droidloom.once.skip=yes",
            "systemd.mask=sleep.target",
            "systemd.mask=droidloom-original-once-return.service",
        ] {
            assert!(boot_arguments(&format!("{line} {extra}")).is_err());
        }
        assert!(boot_arguments(&line.replace("systemd.mask=hibernate.target", "")).is_err());
        for name in PACKAGE_WRITERS {
            assert!(boot_arguments(&line.replace(&format!(" systemd.mask={name}"), "")).is_err());
        }
        assert!(
            boot_arguments(
                &line.replace(&format!(" droidloom.once.return={}", "c".repeat(64)), "")
            )
            .is_err()
        );
    }
}
