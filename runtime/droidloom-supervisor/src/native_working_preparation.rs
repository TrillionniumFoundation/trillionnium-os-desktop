//! Closed preparation sequence for the complete physical application roster.
//! These source descriptions select existing normal factories, never authority,
//! a caller command, a success receipt, or a renewable execution deadline.
use std::time::Duration;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WorkingNativePreparationStep {
    CalendarCoreTargetIdentity,
    CalendarCoreProviderIdentity,
    CalendarCoreHelperIdentity,
    CalendarCorePlan,
    CalendarReminderTargetIdentity,
    CalendarReminderProviderIdentity,
    CalendarReminderHelperIdentity,
    CalendarReminderPlan,
    ContactsSearchTargetIdentity,
    ContactsSearchProviderIdentity,
    ContactsSearchHelperIdentity,
    ContactsSearchPlan,
    CameraPhotoTargetIdentity,
    CameraPhotoHelperIdentity,
    CameraPhotoPlan,
    SettingsPagesTargetIdentity,
    SettingsPagesHelperIdentity,
    SettingsPagesPlan,
    ClockTargetIdentity,
    ClockHelperIdentity,
    ClockTimer15Source,
    ClockTimer15Plan,
    ClockExpiry06Source,
    ClockExpiry06Plan,
    ClockAlarm04Source,
    ClockAlarm04Plan,
    DocumentsSafTargetIdentity,
    DocumentsSafProviderIdentity,
    DocumentsSafHelperIdentity,
    DocumentsSafSource,
    DocumentsSafBuild,
    DocumentsSafPmHelp,
    DocumentsSafPlan,
    DocumentsSearchTargetIdentity,
    DocumentsSearchProviderIdentity,
    DocumentsSearchHelperIdentity,
    DocumentsSearchSource,
    DocumentsSearchBuild,
    DocumentsSearchPmHelp,
    DocumentsSearchPlan,
    IhgTargetIdentity,
    IhgHelperSource,
    IhgHelperBuild,
    IhgHelperInstall,
    IhgHelperIdentity,
    IhgPlan,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PreparationOutput {
    /// A fresh directory under the candidate's native-inputs/<case>.
    Input,
    /// The fixed native-cases/<case> directory created by the existing factory.
    Case,
    /// Existing source chooses its own case directory; no output argv is sent.
    BoundCase,
}

/// Immutable compiled routing data. It cannot run a command or create custody.
#[derive(Clone, Copy, Debug)]
pub struct PreparationStepDescription {
    pub case_name: &'static str,
    pub source_index: usize,
    pub mode: &'static str,
    pub role: Option<&'static str>,
    pub kind: Option<&'static str>,
    pub purpose: &'static str,
    pub output: PreparationOutput,
    pub result_name: &'static str,
    pub child_seconds: u64,
    pub ihg_factory: bool,
}

pub const WORKING_NATIVE_PREPARATION_STEPS: [WorkingNativePreparationStep; 46] = [
    WorkingNativePreparationStep::CalendarCoreTargetIdentity,
    WorkingNativePreparationStep::CalendarCoreProviderIdentity,
    WorkingNativePreparationStep::CalendarCoreHelperIdentity,
    WorkingNativePreparationStep::CalendarCorePlan,
    WorkingNativePreparationStep::CalendarReminderTargetIdentity,
    WorkingNativePreparationStep::CalendarReminderProviderIdentity,
    WorkingNativePreparationStep::CalendarReminderHelperIdentity,
    WorkingNativePreparationStep::CalendarReminderPlan,
    WorkingNativePreparationStep::ContactsSearchTargetIdentity,
    WorkingNativePreparationStep::ContactsSearchProviderIdentity,
    WorkingNativePreparationStep::ContactsSearchHelperIdentity,
    WorkingNativePreparationStep::ContactsSearchPlan,
    WorkingNativePreparationStep::CameraPhotoTargetIdentity,
    WorkingNativePreparationStep::CameraPhotoHelperIdentity,
    WorkingNativePreparationStep::CameraPhotoPlan,
    WorkingNativePreparationStep::SettingsPagesTargetIdentity,
    WorkingNativePreparationStep::SettingsPagesHelperIdentity,
    WorkingNativePreparationStep::SettingsPagesPlan,
    WorkingNativePreparationStep::ClockTargetIdentity,
    WorkingNativePreparationStep::ClockHelperIdentity,
    WorkingNativePreparationStep::ClockTimer15Source,
    WorkingNativePreparationStep::ClockTimer15Plan,
    WorkingNativePreparationStep::ClockExpiry06Source,
    WorkingNativePreparationStep::ClockExpiry06Plan,
    WorkingNativePreparationStep::ClockAlarm04Source,
    WorkingNativePreparationStep::ClockAlarm04Plan,
    WorkingNativePreparationStep::DocumentsSafTargetIdentity,
    WorkingNativePreparationStep::DocumentsSafProviderIdentity,
    WorkingNativePreparationStep::DocumentsSafHelperIdentity,
    WorkingNativePreparationStep::DocumentsSafSource,
    WorkingNativePreparationStep::DocumentsSafBuild,
    WorkingNativePreparationStep::DocumentsSafPmHelp,
    WorkingNativePreparationStep::DocumentsSafPlan,
    WorkingNativePreparationStep::DocumentsSearchTargetIdentity,
    WorkingNativePreparationStep::DocumentsSearchProviderIdentity,
    WorkingNativePreparationStep::DocumentsSearchHelperIdentity,
    WorkingNativePreparationStep::DocumentsSearchSource,
    WorkingNativePreparationStep::DocumentsSearchBuild,
    WorkingNativePreparationStep::DocumentsSearchPmHelp,
    WorkingNativePreparationStep::DocumentsSearchPlan,
    WorkingNativePreparationStep::IhgTargetIdentity,
    WorkingNativePreparationStep::IhgHelperSource,
    WorkingNativePreparationStep::IhgHelperBuild,
    WorkingNativePreparationStep::IhgHelperInstall,
    WorkingNativePreparationStep::IhgHelperIdentity,
    WorkingNativePreparationStep::IhgPlan,
];

impl WorkingNativePreparationStep {
    pub fn description(self) -> PreparationStepDescription {
        use PreparationOutput::*;
        use WorkingNativePreparationStep::*;
        match self {
            CalendarCoreTargetIdentity => PreparationStepDescription {
                case_name: "calendar-core",
                source_index: 0,
                mode: "identity",
                role: Some("calendar"),
                kind: None,
                purpose: "identity-calendar",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            CalendarCoreProviderIdentity => PreparationStepDescription {
                case_name: "calendar-core",
                source_index: 0,
                mode: "identity",
                role: Some("calendar-provider"),
                kind: None,
                purpose: "identity-calendar-provider",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            CalendarCoreHelperIdentity => PreparationStepDescription {
                case_name: "calendar-core",
                source_index: 0,
                mode: "identity",
                role: Some("native-helper"),
                kind: None,
                purpose: "identity-native-helper",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            CalendarCorePlan => PreparationStepDescription {
                case_name: "calendar-core",
                source_index: 0,
                mode: "plan",
                role: None,
                kind: Some("calendar_core"),
                purpose: "plan",
                output: Case,
                result_name: "plan.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            CalendarReminderTargetIdentity => PreparationStepDescription {
                case_name: "calendar-reminder",
                source_index: 1,
                mode: "identity",
                role: Some("calendar"),
                kind: None,
                purpose: "identity-calendar",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            CalendarReminderProviderIdentity => PreparationStepDescription {
                case_name: "calendar-reminder",
                source_index: 1,
                mode: "identity",
                role: Some("calendar-provider"),
                kind: None,
                purpose: "identity-calendar-provider",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            CalendarReminderHelperIdentity => PreparationStepDescription {
                case_name: "calendar-reminder",
                source_index: 1,
                mode: "identity",
                role: Some("native-helper"),
                kind: None,
                purpose: "identity-native-helper",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            CalendarReminderPlan => PreparationStepDescription {
                case_name: "calendar-reminder",
                source_index: 1,
                mode: "plan",
                role: None,
                kind: Some("calendar_reminder"),
                purpose: "plan",
                output: Case,
                result_name: "plan.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            ContactsSearchTargetIdentity => PreparationStepDescription {
                case_name: "contacts-search",
                source_index: 0,
                mode: "identity",
                role: Some("contacts"),
                kind: None,
                purpose: "identity-contacts",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            ContactsSearchProviderIdentity => PreparationStepDescription {
                case_name: "contacts-search",
                source_index: 0,
                mode: "identity",
                role: Some("contacts-provider"),
                kind: None,
                purpose: "identity-contacts-provider",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            ContactsSearchHelperIdentity => PreparationStepDescription {
                case_name: "contacts-search",
                source_index: 0,
                mode: "identity",
                role: Some("native-helper"),
                kind: None,
                purpose: "identity-native-helper",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            ContactsSearchPlan => PreparationStepDescription {
                case_name: "contacts-search",
                source_index: 0,
                mode: "plan",
                role: None,
                kind: Some("contacts_search"),
                purpose: "plan",
                output: Case,
                result_name: "plan.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            CameraPhotoTargetIdentity => PreparationStepDescription {
                case_name: "camera-photo",
                source_index: 2,
                mode: "identity",
                role: Some("camera"),
                kind: None,
                purpose: "identity-camera",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            CameraPhotoHelperIdentity => PreparationStepDescription {
                case_name: "camera-photo",
                source_index: 2,
                mode: "identity",
                role: Some("native-helper"),
                kind: None,
                purpose: "identity-native-helper",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            CameraPhotoPlan => PreparationStepDescription {
                case_name: "camera-photo",
                source_index: 2,
                mode: "plan",
                role: None,
                kind: None,
                purpose: "plan",
                output: Case,
                result_name: "plan.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            SettingsPagesTargetIdentity => PreparationStepDescription {
                case_name: "settings-supported-pages",
                source_index: 13,
                mode: "identity",
                role: Some("settings"),
                kind: None,
                purpose: "identity-settings",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            SettingsPagesHelperIdentity => PreparationStepDescription {
                case_name: "settings-supported-pages",
                source_index: 13,
                mode: "identity",
                role: Some("native-helper"),
                kind: None,
                purpose: "identity-native-helper",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            SettingsPagesPlan => PreparationStepDescription {
                case_name: "settings-supported-pages",
                source_index: 13,
                mode: "plan",
                role: None,
                kind: None,
                purpose: "plan",
                output: Case,
                result_name: "plan.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            ClockTargetIdentity => PreparationStepDescription {
                case_name: "clock-timer-pair",
                source_index: 4,
                mode: "identity",
                role: Some("clock"),
                kind: None,
                purpose: "identity-clock",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            ClockHelperIdentity => PreparationStepDescription {
                case_name: "clock-timer-pair",
                source_index: 4,
                mode: "identity",
                role: Some("native-helper"),
                kind: None,
                purpose: "identity-native-helper",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            ClockTimer15Source => PreparationStepDescription {
                case_name: "clock-timer15",
                source_index: 4,
                mode: "source",
                role: None,
                kind: None,
                purpose: "source",
                output: Case,
                result_name: "case-source.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            ClockTimer15Plan => PreparationStepDescription {
                case_name: "clock-timer15",
                source_index: 4,
                mode: "plan",
                role: None,
                kind: None,
                purpose: "plan",
                output: BoundCase,
                result_name: "execution-plan.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            ClockExpiry06Source => PreparationStepDescription {
                case_name: "clock-expiry06",
                source_index: 4,
                mode: "source",
                role: None,
                kind: None,
                purpose: "source",
                output: Case,
                result_name: "case-source.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            ClockExpiry06Plan => PreparationStepDescription {
                case_name: "clock-expiry06",
                source_index: 4,
                mode: "plan",
                role: None,
                kind: None,
                purpose: "plan",
                output: BoundCase,
                result_name: "execution-plan.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            ClockAlarm04Source => PreparationStepDescription {
                case_name: "clock-alarm",
                source_index: 4,
                mode: "source",
                role: None,
                kind: None,
                purpose: "source",
                output: Case,
                result_name: "case-source.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            ClockAlarm04Plan => PreparationStepDescription {
                case_name: "clock-alarm",
                source_index: 4,
                mode: "plan",
                role: None,
                kind: None,
                purpose: "plan",
                output: BoundCase,
                result_name: "execution-plan.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            DocumentsSafTargetIdentity => PreparationStepDescription {
                case_name: "documents-saf",
                source_index: 6,
                mode: "identity",
                role: Some("documents"),
                kind: None,
                purpose: "identity-documents",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            DocumentsSafProviderIdentity => PreparationStepDescription {
                case_name: "documents-saf",
                source_index: 6,
                mode: "identity",
                role: Some("provider"),
                kind: None,
                purpose: "identity-provider",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            DocumentsSafHelperIdentity => PreparationStepDescription {
                case_name: "documents-saf",
                source_index: 6,
                mode: "identity",
                role: Some("native-helper"),
                kind: None,
                purpose: "identity-native-helper",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            DocumentsSafSource => PreparationStepDescription {
                case_name: "documents-saf",
                source_index: 6,
                mode: "source",
                role: None,
                kind: None,
                purpose: "source",
                output: Case,
                result_name: "helper-source.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            DocumentsSafBuild => PreparationStepDescription {
                case_name: "documents-saf",
                source_index: 6,
                mode: "build",
                role: None,
                kind: None,
                purpose: "helper-build",
                output: Input,
                result_name: "build-result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            DocumentsSafPmHelp => PreparationStepDescription {
                case_name: "documents-saf",
                source_index: 6,
                mode: "pm-help",
                role: None,
                kind: None,
                purpose: "pm-help",
                output: Input,
                result_name: "result.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            DocumentsSafPlan => PreparationStepDescription {
                case_name: "documents-saf",
                source_index: 6,
                mode: "plan",
                role: None,
                kind: None,
                purpose: "plan",
                output: BoundCase,
                result_name: "execution-plan.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            DocumentsSearchTargetIdentity => PreparationStepDescription {
                case_name: "documents-search-sort",
                source_index: 7,
                mode: "identity",
                role: Some("documents"),
                kind: None,
                purpose: "identity-documents",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            DocumentsSearchProviderIdentity => PreparationStepDescription {
                case_name: "documents-search-sort",
                source_index: 7,
                mode: "identity",
                role: Some("provider"),
                kind: None,
                purpose: "identity-provider",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            DocumentsSearchHelperIdentity => PreparationStepDescription {
                case_name: "documents-search-sort",
                source_index: 7,
                mode: "identity",
                role: Some("native-helper"),
                kind: None,
                purpose: "identity-native-helper",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            DocumentsSearchSource => PreparationStepDescription {
                case_name: "documents-search-sort",
                source_index: 7,
                mode: "source",
                role: None,
                kind: None,
                purpose: "source",
                output: Case,
                result_name: "helper-source.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            DocumentsSearchBuild => PreparationStepDescription {
                case_name: "documents-search-sort",
                source_index: 7,
                mode: "build",
                role: None,
                kind: None,
                purpose: "helper-build",
                output: Input,
                result_name: "build-result.json",
                child_seconds: 300,
                ihg_factory: false,
            },
            DocumentsSearchPmHelp => PreparationStepDescription {
                case_name: "documents-search-sort",
                source_index: 7,
                mode: "pm-help",
                role: None,
                kind: None,
                purpose: "pm-help",
                output: Input,
                result_name: "result.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            DocumentsSearchPlan => PreparationStepDescription {
                case_name: "documents-search-sort",
                source_index: 7,
                mode: "plan",
                role: None,
                kind: None,
                purpose: "plan",
                output: BoundCase,
                result_name: "execution-plan.json",
                child_seconds: 180,
                ihg_factory: false,
            },
            IhgTargetIdentity => PreparationStepDescription {
                case_name: "ihg-london",
                source_index: 5,
                mode: "identity",
                role: None,
                kind: None,
                purpose: "target-identity",
                output: Input,
                result_name: "result.json",
                child_seconds: 300,
                ihg_factory: true,
            },
            IhgHelperSource => PreparationStepDescription {
                case_name: "ihg-london",
                source_index: 5,
                mode: "helper-source",
                role: None,
                kind: None,
                purpose: "helper-source",
                output: Input,
                result_name: "source.json",
                child_seconds: 180,
                ihg_factory: true,
            },
            IhgHelperBuild => PreparationStepDescription {
                case_name: "ihg-london",
                source_index: 5,
                mode: "helper-build",
                role: None,
                kind: None,
                purpose: "helper-build",
                output: Input,
                result_name: "build-result.json",
                child_seconds: 300,
                ihg_factory: true,
            },
            IhgHelperInstall => PreparationStepDescription {
                case_name: "ihg-london",
                source_index: 5,
                mode: "helper-install",
                role: None,
                kind: None,
                purpose: "helper-install",
                output: Input,
                result_name: "result.json",
                child_seconds: 240,
                ihg_factory: true,
            },
            IhgHelperIdentity => PreparationStepDescription {
                case_name: "ihg-london",
                source_index: 5,
                mode: "identity",
                role: None,
                kind: None,
                purpose: "helper-identity",
                output: Input,
                result_name: "result.json",
                child_seconds: 360,
                ihg_factory: true,
            },
            IhgPlan => PreparationStepDescription {
                case_name: "ihg-london",
                source_index: 5,
                mode: "plan",
                role: None,
                kind: None,
                purpose: "plan",
                output: Case,
                result_name: "plan.json",
                child_seconds: 180,
                ihg_factory: true,
            },
        }
    }
    pub fn is_documents_build(self) -> bool {
        matches!(self, Self::DocumentsSafBuild | Self::DocumentsSearchBuild)
    }
    pub fn child_budget(self) -> Duration {
        Duration::from_secs(self.description().child_seconds)
    }
    /// Existing normal runner retains target PM (250), Main (70), retirement
    /// (2), and IHG's whole-user inventory (70). This is a reserve, not a sleep.
    pub fn normal_postcheck_seconds(self) -> u64 {
        250 + 70
            + 2
            + if self.description().ihg_factory {
                70
            } else {
                0
            }
    }
    /// The normal postcheck above is performed by the caller factory, not
    /// repeated inside the runner. Only installation adds a second package PM
    /// inspection, proving the actual new IHG helper rather than the target.
    pub fn factory_postcheck_seconds(self) -> u64 {
        if self == Self::IhgHelperInstall {
            250
        } else {
            0
        }
    }
}

/// Work and actual bookends of these fixed factories only. The shared physical
/// qualification budget separately owns baseline, source binding, and local
/// preparation costs, and allocates the complete deadline once at PID1 start.
pub fn native_preparation_seconds() -> u64 {
    WORKING_NATIVE_PREPARATION_STEPS
        .iter()
        .map(|step| {
            step.description().child_seconds
                + step.normal_postcheck_seconds()
                + step.factory_postcheck_seconds()
        })
        .sum()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeSet;
    #[test]
    fn fixed_preparation_graph_has_distinct_inputs_and_source_before_bound_plans() {
        let mut requests = BTreeSet::new();
        let mut sources = BTreeSet::new();
        for step in WORKING_NATIVE_PREPARATION_STEPS {
            let d = step.description();
            assert!(requests.insert((d.case_name, d.purpose)));
            assert!(d.source_index < 14 && d.child_seconds > 0);
            if d.mode == "source" {
                assert!(sources.insert(d.case_name));
            }
            if d.output == PreparationOutput::BoundCase {
                assert!(sources.contains(d.case_name));
            }
            assert_eq!(step.is_documents_build(), d.mode == "build");
        }
        assert_eq!(sources.len(), 5);
    }
    #[test]
    fn preparation_reserves_every_existing_postcheck_once_per_real_layer() {
        let sum = |f: fn(WorkingNativePreparationStep) -> u64| {
            WORKING_NATIVE_PREPARATION_STEPS
                .iter()
                .copied()
                .map(f)
                .sum::<u64>()
        };
        assert_eq!(sum(|s| s.description().child_seconds), 11520);
        assert_eq!(
            sum(WorkingNativePreparationStep::normal_postcheck_seconds),
            15232
        );
        assert_eq!(
            sum(WorkingNativePreparationStep::factory_postcheck_seconds),
            250
        );
        assert_eq!(native_preparation_seconds(), 27002);
        assert!(
            WorkingNativePreparationStep::IhgHelperInstall.factory_postcheck_seconds()
                > WorkingNativePreparationStep::IhgPlan.factory_postcheck_seconds()
        );
    }
}
