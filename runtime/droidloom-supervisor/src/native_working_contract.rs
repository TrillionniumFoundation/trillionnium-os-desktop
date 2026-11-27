//! Source-owned second-stage working-copy boot contract.
//! This describes a new normal candidate. Deserialization conveys no authority:
//! cold Returned custody, actual normal sources and live process owners are
//! required by the factories that consume it. Original once semantics are
//! retained in their separate module and command-line namespace.
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, ffi::CString, io, path::PathBuf};
#[path = "physical_qualification_budget.rs"]
pub(crate) mod budget;
#[path = "native_working_layout.rs"]
pub(crate) mod layout;
#[path = "native_once_contract.rs"]
mod original;
pub(crate) use original::{
    CONFIG_SHA, INSTALLATION, KERNEL, KERNEL_SHA, MAINTENANCE_EXECUTABLE, MODULE_BYTES, MODULE_REL,
    MODULE_SHA, ORIGINAL_ENTRY, ORIGINAL_KERNEL, PACKAGE_WRITERS, PayloadPin, ROOT_UUID,
    SUSPEND_TARGETS, commit, digest, reject, uuid,
};

pub(crate) const KIND: &str = "working_copy_qualification";
pub(crate) const EARLY_CONFIG: &str = "/etc/droidloom/qualification/working-early.json";
pub(crate) const RETURN_CONFIG: &str = "/etc/droidloom/qualification/working-return.json";
pub(crate) const EARLY_EXECUTABLE: &str = "/usr/lib/droidloom/qualification/working-recovery";
pub(crate) const APPLICATIONS_EXECUTABLE: &str = "/usr/bin/droidloom-applications";
// The normal nine-binary release still supplies this executable. Its new,
// distinct fixed mode checks a separate context/configuration/boot namespace.
pub(crate) const RETURN_EXECUTABLE: &str = original::RETURN_EXECUTABLE;
pub(crate) const WORKING_TARGET: &str = "droidloom-working-qualification.target";
pub(crate) const PARENT_UNIT: &str = "droidloom-working-qualification.service";
pub(crate) const RETURN_UNIT: &str = "droidloom-working-qualification-return.service";
pub(crate) const PARENT_MODE: &str = "--owned-working-qualification";
pub(crate) const RETURN_MODE: &str = "--working-qualification-return";
pub(crate) const EARLY_MODE: &str = "working-qualification-early-recovery";

// A boot that cannot establish the normal owner by this time returns without
// any application execution. This is not added to an individual case window.
pub(crate) const OWNER_START_BY_BOOT_SECONDS: u64 = 600;
pub(crate) const WATCHDOG_INTERVAL_SECONDS: u32 = 900;
pub(crate) const KEEPALIVE_PERIOD_SECONDS: u64 = 120;
pub(crate) const MAIN_REVALIDATION_SECONDS: u64 = 70;
pub(crate) const RETURN_SECONDS: u64 = 180;
pub(crate) const PANIC_SECONDS: u32 = 10;

/// Comparison copied from the unique normal host payload member. The complete
/// ADMITTED-MATERIALS input is already held and boot-hash authenticated before
/// a live owner may expose this pin. Deserialization alone grants no execution.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct WorkingNamespaceEntryPin {
    pub(crate) path: String,
    pub(crate) bytes: u64,
    pub(crate) sha256: String,
}
impl WorkingNamespaceEntryPin {
    pub(crate) fn validate(&self) -> io::Result<()> {
        if self.path != layout::WORKING_NAMESPACE_ENTRY
            || !(1024..=layout::WORKING_NAMESPACE_ENTRY_MAX_BYTES).contains(&self.bytes)
            || !digest(&self.sha256)
        {
            return Err(reject(
                "working namespace entry differs from its fixed normal member",
            ));
        }
        Ok(())
    }
    pub(crate) fn from_admitted_materials(bytes: &[u8]) -> io::Result<Self> {
        if bytes.len() > 16 * 1024 * 1024 {
            return Err(reject(
                "working admitted material comparison exceeds its fixed bound",
            ));
        }
        let document: serde_json::Value = serde_json::from_slice(bytes)?;
        let value = document
            .get("working_namespace_entry")
            .ok_or_else(|| reject("normal working namespace entry member is absent"))?;
        let pin: Self = serde_json::from_value(value.clone())?;
        pin.validate()?;
        Ok(pin)
    }
}

/// Two distinct clocks: one immutable source-derived work end and a shorter
/// failure-recovery interval. Refreshing the latter cannot alter the former.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct WorkingSchedule {
    pub(crate) owner_start_by_boot_seconds: u64,
    pub(crate) whole_suite_seconds: u64,
    pub(crate) case_count: usize,
    pub(crate) native_case_count: usize,
    pub(crate) family_case_count: usize,
    pub(crate) photo_case_count: usize,
    pub(crate) settings_case_count: usize,
    pub(crate) authorization_end_by_boot_seconds: u64,
    pub(crate) parent_retirement_seconds: u64,
    pub(crate) service_runtime_seconds: u64,
    pub(crate) parent_stop_end_by_boot_seconds: u64,
    pub(crate) normal_return_seconds: u64,
    pub(crate) normal_return_end_by_boot_seconds: u64,
    pub(crate) watchdog_interval_seconds: u32,
    pub(crate) keepalive_period_seconds: u64,
    pub(crate) main_revalidation_seconds: u64,
    pub(crate) fallback_end_by_boot_seconds: u64,
    pub(crate) nofile_limit: u64,
}
impl WorkingSchedule {
    pub(crate) fn selected() -> Self {
        let authorization_end = OWNER_START_BY_BOOT_SECONDS + budget::SUITE_SECONDS;
        // RuntimeMax includes the parent's cooperative retirement allowance.
        // If the parent itself stalls, systemd can then spend TimeoutStop once
        // more before its final SIGKILL. Count both source-fixed bounds before
        // the one final nowayout close ping. Neither adds working authorization.
        let parent_end =
            OWNER_START_BY_BOOT_SECONDS + budget::SERVICE_SECONDS + budget::RETIREMENT_SECONDS;
        Self {
            owner_start_by_boot_seconds: OWNER_START_BY_BOOT_SECONDS,
            whole_suite_seconds: budget::SUITE_SECONDS,
            case_count: budget::CASE_COUNT,
            native_case_count: budget::NATIVE_CASE_COUNT,
            family_case_count: budget::FAMILY_CASE_COUNT,
            photo_case_count: budget::PHOTO_CASE_COUNT,
            settings_case_count: budget::SETTINGS_CASE_COUNT,
            authorization_end_by_boot_seconds: authorization_end,
            parent_retirement_seconds: budget::RETIREMENT_SECONDS,
            service_runtime_seconds: budget::SERVICE_SECONDS,
            parent_stop_end_by_boot_seconds: parent_end,
            normal_return_seconds: RETURN_SECONDS,
            normal_return_end_by_boot_seconds: parent_end + RETURN_SECONDS,
            watchdog_interval_seconds: WATCHDOG_INTERVAL_SECONDS,
            keepalive_period_seconds: KEEPALIVE_PERIOD_SECONDS,
            main_revalidation_seconds: MAIN_REVALIDATION_SECONDS,
            fallback_end_by_boot_seconds: parent_end + u64::from(WATCHDOG_INTERVAL_SECONDS),
            nofile_limit: budget::NOFILE_LIMIT,
        }
    }
    pub(crate) fn validate(&self) -> io::Result<()> {
        if self != &Self::selected()
            || self.whole_suite_seconds <= u64::from(u16::MAX)
            || self.watchdog_interval_seconds > u32::from(u16::MAX)
            || self.keepalive_period_seconds + self.main_revalidation_seconds
                >= u64::from(self.watchdog_interval_seconds)
            || self.owner_start_by_boot_seconds + budget::PREPARATION_BOOTSTRAP_SECONDS
                >= u64::from(self.watchdog_interval_seconds)
            || self.normal_return_seconds >= u64::from(self.watchdog_interval_seconds)
        {
            return Err(reject(
                "working schedule differs from its exact source-owned dual clocks",
            ));
        }
        Ok(())
    }
    /// A scalar comparison for the owner's kernel monotonic observation. It is
    /// not a constructor for a watchdog permit or a substitute for owner/Main
    /// revalidation; the real parent must independently hold those resources.
    pub(crate) fn authorization_end_ns(&self, actual_owner_start_ns: u64) -> io::Result<u64> {
        self.validate()?;
        let bootstrap_end = self
            .owner_start_by_boot_seconds
            .checked_mul(1_000_000_000)
            .ok_or_else(|| reject("working bootstrap time overflow"))?;
        if actual_owner_start_ns == 0 || actual_owner_start_ns > bootstrap_end {
            return Err(reject(
                "working owner started outside its fixed bootstrap window",
            ));
        }
        let end = actual_owner_start_ns
            .checked_add(
                self.whole_suite_seconds
                    .checked_mul(1_000_000_000)
                    .ok_or_else(|| reject("working suite time overflow"))?,
            )
            .ok_or_else(|| reject("working owner time overflow"))?;
        let cap = self
            .authorization_end_by_boot_seconds
            .checked_mul(1_000_000_000)
            .ok_or_else(|| reject("working absolute cap overflow"))?;
        if end > cap {
            return Err(reject("working source end exceeded its fixed boot cap"));
        }
        Ok(end)
    }
    pub(crate) fn check_keepalive_time(
        &self,
        original_end_ns: u64,
        owner_start_ns: u64,
        observed_now_ns: u64,
    ) -> io::Result<()> {
        if original_end_ns != self.authorization_end_ns(owner_start_ns)?
            || observed_now_ns < owner_start_ns
            || observed_now_ns >= original_end_ns
        {
            return Err(reject(
                "watchdog keepalive is outside the original working authorization",
            ));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct WorkingBootSpec {
    pub(crate) schema: String,
    pub(crate) kind: String,
    pub(crate) candidate_id: String,
    pub(crate) first_once_candidate: String,
    pub(crate) helper_bytes: u64,
    pub(crate) helper_sha256: String,
    pub(crate) kernel_release: String,
    pub(crate) kernel_sha256: String,
    pub(crate) kernel_config_sha256: String,
    pub(crate) module_relative: String,
    pub(crate) module_bytes: u64,
    pub(crate) module_sha256: String,
    pub(crate) panic_seconds: u32,
    pub(crate) schedule: WorkingSchedule,
}
impl WorkingBootSpec {
    pub(crate) fn validate(&self) -> io::Result<()> {
        self.schedule.validate()?;
        if self.schema != "droidloom.working-qualification-boot.v1"
            || self.kind != KIND
            || !digest(&self.candidate_id)
            || !digest(&self.first_once_candidate)
            || self.candidate_id == self.first_once_candidate
            || !(1024..=128 * 1024 * 1024).contains(&self.helper_bytes)
            || !digest(&self.helper_sha256)
            || self.kernel_release != KERNEL
            || self.kernel_sha256 != KERNEL_SHA
            || self.kernel_config_sha256 != CONFIG_SHA
            || self.module_relative != MODULE_REL
            || self.module_bytes != MODULE_BYTES
            || self.module_sha256 != MODULE_SHA
            || self.panic_seconds != PANIC_SECONDS
        {
            return Err(reject(
                "working boot is not a distinct source-bound selected-kernel candidate",
            ));
        }
        Ok(())
    }
    pub(crate) fn parameters(&self) -> io::Result<CString> {
        self.validate()?;
        CString::new(format!(
            "soft_margin={} nowayout=1 soft_active_on_boot=1 soft_noboot=0 soft_panic=0",
            self.schedule.watchdog_interval_seconds
        ))
        .map_err(io::Error::other)
    }
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct WorkingEarlyConfiguration {
    pub(crate) schema: String,
    pub(crate) intent_sha256: String,
    pub(crate) recovery: WorkingBootSpec,
}
impl WorkingEarlyConfiguration {
    pub(crate) fn validate(&self) -> io::Result<()> {
        self.recovery.validate()?;
        if self.schema != "droidloom.working-qualification-early.v1" || !digest(&self.intent_sha256)
        {
            return Err(reject(
                "working early configuration lacks its exact new intent",
            ));
        }
        Ok(())
    }
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct WorkingReturnConfiguration {
    pub(crate) schema: String,
    pub(crate) intent_sha256: String,
    pub(crate) candidate_id: String,
    pub(crate) first_once_candidate: String,
    pub(crate) original_boot_id: String,
    pub(crate) original_kernel: String,
    pub(crate) original_entry: String,
    pub(crate) root_uuid: String,
    pub(crate) early_config_sha256: String,
    pub(crate) admitted_materials_sha256: String,
    pub(crate) joint_policy_sha256: String,
    pub(crate) host_source_commit: String,
    pub(crate) host_source_tree: String,
    pub(crate) recovery: WorkingBootSpec,
    pub(crate) executable: PayloadPin,
    pub(crate) applications: PayloadPin,
    pub(crate) maintenance: PayloadPin,
    pub(crate) installation: PayloadPin,
    pub(crate) cell: PayloadPin,
    pub(crate) selection: PayloadPin,
}
impl WorkingReturnConfiguration {
    pub(crate) fn validate(&self) -> io::Result<()> {
        self.recovery.validate()?;
        if self.schema != "droidloom.working-qualification-return.v1"
            || !digest(&self.intent_sha256)
            || self.candidate_id != self.recovery.candidate_id
            || self.first_once_candidate != self.recovery.first_once_candidate
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
                "working return is not bound to its actual H2 material/boot intent",
            ));
        }
        self.executable.validate(128 * 1024 * 1024)?;
        self.applications.validate(128 * 1024 * 1024)?;
        self.maintenance.validate(1024 * 1024)?;
        self.installation.validate(1024 * 1024)?;
        self.cell.validate(1024 * 1024)?;
        self.selection.validate(1024 * 1024)
    }
    pub(crate) fn runtime_evidence_directory(&self) -> PathBuf {
        // The running candidate never reads the original/rollback/private
        // Returned tree under /var/lib/droidloom-qualification.
        std::path::Path::new(layout::WORKING_QUALIFICATION_BASE)
            .join(format!(
                "{}{}",
                layout::WORKING_CANDIDATE_PREFIX,
                self.candidate_id
            ))
            .join(layout::WORKING_EVIDENCE_DIRECTORY)
    }
}

pub(crate) fn boot_arguments(input: &str) -> io::Result<BTreeMap<String, String>> {
    if input.len() > 32768 {
        return Err(reject("working command line exceeds bound"));
    }
    let mut result = BTreeMap::new();
    let mut masks = BTreeMap::<&str, usize>::new();
    let mut wants = 0usize;
    for arg in input.split_whitespace() {
        let Some((name, value)) = arg.split_once('=') else {
            if arg.starts_with("droidloom.working")
                || arg.starts_with("droidloom.once")
                || arg == "systemd.wants"
                || arg == "rd.systemd.wants"
            {
                return Err(reject("bare or mixed recovery boot argument"));
            }
            continue;
        };
        if [
            "droidloom.working",
            "droidloom.working.config",
            "droidloom.working.return",
            "root",
            "panic",
        ]
        .contains(&name)
        {
            if result.insert(name.into(), value.into()).is_some() {
                return Err(reject("duplicate working boot argument"));
            }
        } else if name.starts_with("droidloom.working") || name.starts_with("droidloom.once") {
            return Err(reject(
                "mixed once/working or unknown working boot argument",
            ));
        }
        if name == "systemd.wants" {
            if value != WORKING_TARGET {
                return Err(reject("working boot selects another host target"));
            }
            wants += 1;
        } else if name == "rd.systemd.wants" {
            return Err(reject(
                "working boot does not admit an additional initrd target",
            ));
        }
        if name == "systemd.mask" {
            *masks.entry(value).or_default() += 1;
        }
    }
    if result.len() != 5
        || wants != 1
        || result.get("root") != Some(&format!("UUID={ROOT_UUID}"))
        || result.get("panic").map(String::as_str) != Some("10")
        || [
            "droidloom.working",
            "droidloom.working.config",
            "droidloom.working.return",
        ]
        .iter()
        .any(|key| !digest(result.get(*key).map_or("", String::as_str)))
        || masks.len() != PACKAGE_WRITERS.len() + SUSPEND_TARGETS.len()
        || PACKAGE_WRITERS
            .iter()
            .chain(SUSPEND_TARGETS.iter())
            .any(|name| masks.get(name) != Some(&1))
    {
        return Err(reject(
            "working boot requires its exact intent/root/panic, one fixed target and writer/suspend masks",
        ));
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn spec() -> WorkingBootSpec {
        WorkingBootSpec {
            schema: "droidloom.working-qualification-boot.v1".into(),
            kind: KIND.into(),
            candidate_id: "a".repeat(64),
            first_once_candidate: "b".repeat(64),
            helper_bytes: 10000,
            helper_sha256: "c".repeat(64),
            kernel_release: KERNEL.into(),
            kernel_sha256: KERNEL_SHA.into(),
            kernel_config_sha256: CONFIG_SHA.into(),
            module_relative: MODULE_REL.into(),
            module_bytes: MODULE_BYTES,
            module_sha256: MODULE_SHA.into(),
            panic_seconds: 10,
            schedule: WorkingSchedule::selected(),
        }
    }
    fn line() -> String {
        format!(
            "root=UUID={ROOT_UUID} panic=10 droidloom.working={} droidloom.working.config={} droidloom.working.return={} systemd.wants={WORKING_TARGET} {}",
            "a".repeat(64),
            "b".repeat(64),
            "c".repeat(64),
            PACKAGE_WRITERS
                .iter()
                .chain(SUSPEND_TARGETS.iter())
                .map(|s| format!("systemd.mask={s}"))
                .collect::<Vec<_>>()
                .join(" ")
        )
    }
    #[test]
    fn physical_working_namespace_pin_requires_exact_normal_member() {
        let good = serde_json::json!({"working_namespace_entry":{
            "path":layout::WORKING_NAMESPACE_ENTRY, "bytes":4096, "sha256":"a".repeat(64)}});
        let read = |v: &serde_json::Value| {
            WorkingNamespaceEntryPin::from_admitted_materials(&serde_json::to_vec(v).unwrap())
        };
        read(&good).unwrap();
        for path in [
            "",
            "/usr/bin/droidloom-applications",
            "/usr/lib/droidloom/qualification/../qualification/working-namespace-entry",
            "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/bin/held-namespace-entry",
        ] {
            let mut bad = good.clone();
            bad["working_namespace_entry"]["path"] = path.into();
            assert!(read(&bad).is_err());
        }
        for bytes in [0, 1023, layout::WORKING_NAMESPACE_ENTRY_MAX_BYTES + 1] {
            let mut bad = good.clone();
            bad["working_namespace_entry"]["bytes"] = bytes.into();
            assert!(read(&bad).is_err());
        }
        for sha in ["a".repeat(63), "A".repeat(64), "g".repeat(64)] {
            let mut bad = good.clone();
            bad["working_namespace_entry"]["sha256"] = sha.into();
            assert!(read(&bad).is_err());
        }
        let mut bad = good.clone();
        bad["working_namespace_entry"]["runtime_qualified"] = true.into();
        assert!(read(&bad).is_err());
        assert!(read(&serde_json::json!({"production_ready":true})).is_err());
        assert!(read(&serde_json::json!({"working_namespace_entry":null})).is_err());
    }
    #[test]
    fn working_dual_clock_is_source_sum_not_softdog_duration() {
        let s = WorkingSchedule::selected();
        s.validate().unwrap();
        assert_eq!(
            (s.native_case_count, s.family_case_count, s.photo_case_count, s.settings_case_count, s.case_count),
            (14, 31, 1, 1, 47)
        );
        assert_eq!(budget::SOURCE_AND_CAPTURE_SECONDS, 46_622);
        assert_eq!(s.whole_suite_seconds, 315_742);
        assert_eq!(
            s.whole_suite_seconds,
            budget::NATIVE_CASE_WINDOWS.iter().sum::<u64>()
                + 26 * (250 + 6_910)
                + 5 * (250 + 9_110)
                + budget::CAMERA_PHOTO_CASE_SECONDS
                + budget::SETTINGS_PERMISSION_CASE_SECONDS
                + 2 * budget::MAIN_SECONDS
                + budget::SOURCE_AND_CAPTURE_SECONDS
        );
        assert_eq!(s.watchdog_interval_seconds, 900);
        assert_eq!(
            s.authorization_end_by_boot_seconds,
            600 + budget::SUITE_SECONDS
        );
        assert_eq!(s.service_runtime_seconds, budget::SUITE_SECONDS + 180);
        assert_eq!(
            s.parent_stop_end_by_boot_seconds,
            600 + s.service_runtime_seconds + 180
        );
        assert_eq!(
            s.normal_return_end_by_boot_seconds,
            s.parent_stop_end_by_boot_seconds + 180
        );
        assert!(s.normal_return_end_by_boot_seconds < s.fallback_end_by_boot_seconds);
        assert_eq!(
            s.fallback_end_by_boot_seconds - s.authorization_end_by_boot_seconds,
            (budget::SERVICE_SECONDS - budget::SUITE_SECONDS) + budget::RETIREMENT_SECONDS + 900
        );
        for field in [
            "case_count",
            "native_case_count",
            "family_case_count",
            "photo_case_count",
            "settings_case_count",
            "whole_suite_seconds",
            "watchdog_interval_seconds",
            "keepalive_period_seconds",
            "authorization_end_by_boot_seconds",
            "fallback_end_by_boot_seconds",
            "parent_stop_end_by_boot_seconds",
            "service_runtime_seconds",
            "parent_retirement_seconds",
            "normal_return_seconds",
            "normal_return_end_by_boot_seconds",
            "nofile_limit",
        ] {
            let mut value = serde_json::to_value(&s).unwrap();
            value[field] = serde_json::json!(value[field].as_u64().unwrap() + 1);
            assert!(
                serde_json::from_value::<WorkingSchedule>(value)
                    .unwrap()
                    .validate()
                    .is_err()
            );
        }
    }
    #[test]
    fn working_keepalive_comparison_never_renews_original_end() {
        let s = WorkingSchedule::selected();
        let start = 100_000_000_000;
        let end = s.authorization_end_ns(start).unwrap();
        s.check_keepalive_time(end, start, start).unwrap();
        s.check_keepalive_time(end, start, end - 1).unwrap();
        for (wrong_end, now) in [
            (end + 1, end - 1),
            (end, end),
            (end, end + 1),
            (end, start - 1),
        ] {
            assert!(s.check_keepalive_time(wrong_end, start, now).is_err());
        }
        assert!(s.authorization_end_ns(0).is_err());
        assert!(s.authorization_end_ns(600_000_000_001).is_err());
    }
    #[test]
    fn working_contract_preserves_shared_kernel_and_distinct_candidate() {
        let s = spec();
        s.validate().unwrap();
        assert_eq!(
            s.parameters().unwrap().to_str().unwrap(),
            "soft_margin=900 nowayout=1 soft_active_on_boot=1 soft_noboot=0 soft_panic=0"
        );
        let mut bad = spec();
        bad.candidate_id = bad.first_once_candidate.clone();
        assert!(bad.validate().is_err());
        let mut bad = spec();
        bad.module_sha256 = "d".repeat(64);
        assert!(bad.validate().is_err());
        let mut bad = spec();
        bad.kind = "original_once".into();
        assert!(bad.validate().is_err());
        let mut bad = spec();
        bad.schedule.watchdog_interval_seconds = 65536;
        assert!(bad.validate().is_err());
    }
    #[test]
    fn working_command_line_rejects_mixed_once_unknown_and_masked_return() {
        let s = line();
        boot_arguments(&s).unwrap();
        for extra in [
            "droidloom.once=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "droidloom.working.skip=true",
            "droidloom.once",
            "droidloom.working",
            "root=bad",
            "panic=0",
            "systemd.wants",
            "rd.systemd.wants=droidloom-working-qualification.target",
            "systemd.wants=droidloom-working-qualification.target",
            "systemd.wants=caller.service",
            "systemd.mask=sleep.target",
            "systemd.mask=droidloom-working-qualification-return.service",
        ] {
            assert!(boot_arguments(&format!("{s} {extra}")).is_err());
        }
        assert!(
            boot_arguments(&s.replace(&format!("systemd.wants={WORKING_TARGET}"), "")).is_err()
        );
        for name in PACKAGE_WRITERS.iter().chain(SUSPEND_TARGETS.iter()) {
            assert!(boot_arguments(&s.replace(&format!("systemd.mask={name}"), "")).is_err());
        }
    }
}
