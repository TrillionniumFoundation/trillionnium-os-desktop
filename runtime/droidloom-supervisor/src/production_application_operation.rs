//! Closed operations for the original broker's authenticated worker channel.
//! These values select literal argv and a fixed MAC role. They do not contain
//! an executable path, PID, namespace, descriptor number, or caller MAC label.
use super::*;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum OperationDomain {
    Query,
    Browser,
    ContactsRead,
    LaunchRead,
    LaunchStart,
    Install,
    CatalogRead,
    AppOpsRead,
    AccountRead,
    DisplayControl,
    PreparationRead,
    IhgInstrument,
    NativeUi,
    NativeUiRead,
    CalendarCounts,
    FixtureState,
}
impl OperationDomain {
    /// Guest credentials are fixed by the closed source operation; no old role changes.
    pub(super) const fn guest_uid(self) -> u32 {
        match self {
            Self::AccountRead => 1000,
            Self::PreparationRead => 0,
            Self::NativeUiRead => 0,
            Self::CalendarCounts => crate::native_calendar_counts::OBSERVER_UID,
            _ => 2000,
        }
    }
    pub(super) const fn context(self) -> &'static str {
        match self {
            Self::Query => "u:r:droidloom_query:s0",
            Self::Browser => "u:r:droidloom_browser:s0",
            Self::ContactsRead => "u:r:droidloom_contacts_read:s0",
            Self::LaunchRead => "u:r:droidloom_launch_read:s0",
            Self::LaunchStart => "u:r:droidloom_launch_start:s0",
            Self::Install => "u:r:droidloom_install:s0",
            Self::CatalogRead => "u:r:droidloom_catalog_read:s0",
            Self::AppOpsRead => "u:r:droidloom_appops_read:s0",
            Self::AccountRead => "u:r:droidloom_account_read:s0",
            Self::DisplayControl => "u:r:droidloom_display_control:s0",
            Self::PreparationRead => "u:r:droidloom_preparation_read:s0",
            Self::IhgInstrument => "u:r:droidloom_ihg_instrument:s0",
            Self::NativeUi => "u:r:droidloom_native_ui:s0",
            Self::NativeUiRead => "u:r:droidloom_native_ui_read:s0",
            Self::CalendarCounts => "u:r:droidloom_calendar_counts:s0:c512,c768",
            Self::FixtureState => "u:r:droidloom_fixture_state:s0",
        }
    }

    pub(super) const fn terminated(self) -> &'static [u8] {
        match self {
            Self::Query => b"u:r:droidloom_query:s0\0",
            Self::Browser => b"u:r:droidloom_browser:s0\0",
            Self::ContactsRead => b"u:r:droidloom_contacts_read:s0\0",
            Self::LaunchRead => b"u:r:droidloom_launch_read:s0\0",
            Self::LaunchStart => b"u:r:droidloom_launch_start:s0\0",
            Self::Install => b"u:r:droidloom_install:s0\0",
            Self::CatalogRead => b"u:r:droidloom_catalog_read:s0\0",
            Self::AppOpsRead => b"u:r:droidloom_appops_read:s0\0",
            Self::AccountRead => b"u:r:droidloom_account_read:s0\0",
            Self::DisplayControl => b"u:r:droidloom_display_control:s0\0",
            Self::PreparationRead => b"u:r:droidloom_preparation_read:s0\0",
            Self::IhgInstrument => b"u:r:droidloom_ihg_instrument:s0\0",
            Self::NativeUi => b"u:r:droidloom_native_ui:s0\0",
            Self::NativeUiRead => b"u:r:droidloom_native_ui_read:s0\0",
            Self::CalendarCounts => b"u:r:droidloom_calendar_counts:s0:c512,c768\0",
            Self::FixtureState => b"u:r:droidloom_fixture_state:s0\0",
        }
    }
}

/// This closed command can only be lent the original Ready owner. It carries
/// no package-success flag and cannot be converted to an application read.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "browser", deny_unknown_fields)]
pub(crate) enum BrowserCommand {
    Resolve { user: u32, url: String },
    Start { user: u32, url: String },
}

impl BrowserCommand {
    pub(super) fn validate(&self) -> Result<()> {
        let (user, url) = match self {
            Self::Resolve { user, url } | Self::Start { user, url } => (*user, url),
        };
        require(user <= 21_474, "invalid browser Android user")?;
        crate::control::application_probe::validate_https_url(url).map_err(external)
    }

    pub(super) fn from_command(args: &[String], user: u32, url: &str) -> Result<Self> {
        let text: Vec<&str> = args.iter().map(String::as_str).collect();
        let value = match text.as_slice() {
            [
                "/system/bin/cmd",
                "package",
                "resolve-activity",
                "--brief",
                "--user",
                observed_user,
                "-a",
                "android.intent.action.VIEW",
                "-c",
                "android.intent.category.BROWSABLE",
                "-d",
                observed_url,
            ] => {
                require(
                    canonical_user(observed_user)? == user && *observed_url == url,
                    "browser resolver input differs from this bound operation",
                )?;
                Self::Resolve {
                    user,
                    url: url.into(),
                }
            }
            [
                "/system/bin/cmd",
                "activity",
                "start-activity",
                "-W",
                "--user",
                observed_user,
                "-a",
                "android.intent.action.VIEW",
                "-c",
                "android.intent.category.BROWSABLE",
                "-d",
                observed_url,
            ] => {
                require(
                    canonical_user(observed_user)? == user && *observed_url == url,
                    "browser start input differs from this bound operation",
                )?;
                Self::Start {
                    user,
                    url: url.into(),
                }
            }
            _ => return Err(reject("command is outside the fixed implicit browser flow")),
        };
        value.validate()?;
        Ok(value)
    }

    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        let (user, url, service, action, option) = match self {
            Self::Resolve { user, url } => (*user, url, "package", "resolve-activity", "--brief"),
            Self::Start { user, url } => (*user, url, "activity", "start-activity", "-W"),
        };
        let user = user.to_string();
        [
            "/system/bin/cmd",
            service,
            action,
            option,
            "--user",
            &user,
            "-a",
            "android.intent.action.VIEW",
            "-c",
            "android.intent.category.BROWSABLE",
            "-d",
            url,
        ]
        .into_iter()
        .map(|value| CString::new(value).map_err(|_| reject("NUL in fixed browser input")))
        .collect()
    }

    pub(super) fn domain(&self) -> OperationDomain {
        match self {
            Self::Resolve { .. } => OperationDomain::Query,
            Self::Start { .. } => OperationDomain::Browser,
        }
    }
}

/// This is only the private same-binary worker message. Public control clients
/// cannot send it directly or acquire its original-owner descriptor channel.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(tag = "operation", deny_unknown_fields)]
pub(super) enum ApplicationOperation {
    Read {
        value: ApplicationRead,
    },
    PreparationRead {
        value: crate::native_preparation_read::PreparationReadRequest,
    },
    PackageHelp {
        value: crate::native_package_help::PackageHelpRequest,
    },
    IhgRead {
        value: super::ihg_helper::IhgRead,
    },
    EmptyMeituanRetainedAbsence {},
    NativeFixture {
        value: super::native_fixture::FixtureCommand,
    },
    Vintf {
        value: super::vintf::VintfRead,
    },
    RuntimeAbi {
        value: super::runtime_abi_query::RuntimeAbiRead,
    },
    ApplicationExitState {
        value: super::application_exit_state_query::ApplicationExitStateRead,
    },
    ApplicationPermissionState {
        value: super::application_permission_state_query::ApplicationPermissionStateRead,
    },
    ApplicationAppOpsState {
        value: super::application_appops_state_query::ApplicationAppOpsStateRead,
    },
    ApplicationAccountState {
        value: super::application_account_state_query::ApplicationAccountStateRead,
    },
    UserZeroPackageInventory {
        value: super::package_inventory_query::UserZeroPackageInventoryRead,
    },
    Browser {
        value: BrowserCommand,
    },
    ContactsRead {
        value: ContactsQuery,
    },
    Launch {
        value: LaunchCommand,
    },
    Install {
        value: InstallCommand,
    },
    Catalog {
        value: CatalogRequest,
    },
    Display {
        value: DisplayCommand,
    },
    CalendarCounts {
        value: super::calendar_counts::CalendarCountsRead,
    },
    NativeUi {
        value: crate::native_application_ui_gateway::GatewayRequest,
    },
    NativeLeafPackage {
        value: super::apk_session_owner::NativeLeafPackageRead,
    },
}

impl ApplicationOperation {
    pub(super) fn validate(&self) -> Result<()> {
        match self {
            Self::Read { value } => value.validate(),
            Self::PreparationRead { value } => value.validate().map_err(external),
            Self::PackageHelp { value } => value.validate().map_err(external),
            Self::IhgRead { value } => value.validate(),
            Self::EmptyMeituanRetainedAbsence {} => Ok(()),
            Self::NativeFixture { value } => value.validate(),
            Self::Vintf { value } => value.validate(),
            Self::RuntimeAbi { value } => value.validate(),
            Self::ApplicationExitState { value } => value.validate(),
            Self::ApplicationPermissionState { value } => value.validate(),
            Self::ApplicationAppOpsState { value } => value.validate(),
            Self::ApplicationAccountState { value } => value.validate(),
            Self::UserZeroPackageInventory { value } => value.validate(),
            Self::Browser { value } => value.validate(),
            Self::ContactsRead { value } => value.validate(),
            Self::Launch { value } => value.validate(),
            Self::Install { value } => value.validate(),
            Self::Catalog { value } => value.validate(),
            Self::Display { value } => value.validate(),
            Self::CalendarCounts { value } => value.validate(),
            Self::NativeUi { value } => {
                value.validate().map_err(external)?;
                require(!matches!(value.command(),
                    crate::native_application_ui_gateway::GatewayCommand::CalendarCounts {}),
                    "Calendar counts require their independently bound normal JAR operation")
            },
            Self::NativeLeafPackage { value } => value.validate(),
        }
    }

    pub(super) fn uses_app_process(&self) -> bool {
        matches!(
            self,
            Self::ContactsRead { .. }
                | Self::Catalog { .. }
                | Self::ApplicationAppOpsState { .. }
                | Self::ApplicationAccountState { .. }
                | Self::CalendarCounts { .. }
        ) || matches!(self, Self::NativeUi { value } if super::native_ui::uses_app_process(value.command()))
          || matches!(self, Self::IhgRead { value } if value.state())
          || matches!(self, Self::NativeFixture { value } if value.state())
    }
    pub(super) fn execution_limit(&self) -> std::time::Duration {
        match self {
            Self::CalendarCounts { .. } => crate::native_calendar_counts::MAX_DURATION,
            Self::NativeUi { value } => value.command().maximum_duration(),
            Self::NativeLeafPackage { .. } => super::apk_protocol::PACKAGE_READ_CAP,
            Self::IhgRead { value } => value.limit(),
            Self::NativeFixture { value } => value.limit(),
            Self::PreparationRead { .. } => crate::native_preparation_read::COMMAND_LIMIT,
            Self::PackageHelp { .. } => crate::native_package_help::COMMAND_LIMIT,
            _ => QUERY_LIMIT,
        }
    }
    pub(super) fn catalog_jar_digest(&self) -> Option<&str> {
        match self {
            Self::Catalog { value } => Some(value.jar_digest()),
            Self::ApplicationAppOpsState { value } => Some(value.jar_digest()),
            Self::ApplicationAccountState { value } => Some(value.jar_digest()),
            Self::CalendarCounts { value } => Some(value.jar_digest()),
            _ => None,
        }
    }
    pub(super) fn output_limit(&self) -> usize {
        match self {
            Self::CalendarCounts { .. } => crate::native_calendar_counts::OUTPUT_BYTES,
            Self::NativeUi { value } => value.command().stdout_limit(),
            Self::Catalog { .. } => super::catalog::OUTPUT_BYTES,
            Self::PreparationRead { .. } => crate::native_preparation_read::OUTPUT_LIMIT,
            Self::PackageHelp { .. } => crate::native_package_help::OUTPUT_LIMIT,
            Self::IhgRead { .. } => crate::native_ihg_helper::OUTPUT_LIMIT,
            Self::EmptyMeituanRetainedAbsence {} => 65536,
            Self::NativeFixture { value } => if value.state(){crate::native_leaf_fixture::STATE_OUTPUT_LIMIT}else{crate::native_leaf_fixture::OUTPUT_LIMIT},
            Self::Vintf { value } => value.output_limit(),
            Self::RuntimeAbi { .. } => super::runtime_abi::OUTPUT_BYTES,
            Self::ApplicationExitState { .. } => crate::application_exit_state::OUTPUT_BYTES,
            Self::ApplicationPermissionState { .. } => {
                crate::application_permission_state::OUTPUT_BYTES
            }
            Self::ApplicationAppOpsState { .. } => crate::application_appops_state::OUTPUT_BYTES,
            Self::ApplicationAccountState { .. } => crate::application_account_state::OUTPUT_BYTES,
            Self::UserZeroPackageInventory { .. } => super::package_inventory::OUTPUT_BYTES,
            _ => OUTPUT_LIMIT,
        }
    }

    pub(super) fn install_input_bytes(&self) -> Option<u64> {
        match self {
            Self::Install { value } => value.input_bytes(),
            _ => None,
        }
    }
    pub(super) fn needs_content_jar(&self) -> bool {
        matches!(self, Self::ContactsRead { .. })
            || matches!(self, Self::NativeUi { value } if super::native_ui::needs_content_jar(value.command()))
            || matches!(self, Self::NativeFixture { value } if value.state())
    }
    pub(super) fn needs_am_jar(&self) -> bool {
        matches!(self, Self::NativeUi { value } if super::native_ui::needs_am_jar(value.command()))
            || matches!(self, Self::IhgRead { value } if value.state())
    }
    pub(super) fn descriptor_count(&self) -> usize {
        if self.needs_content_jar() || self.needs_am_jar() {
            17
        } else {
            15
        }
    }

    pub(super) fn environment(&self, projection: QueryProjection) -> Vec<&'static CStr> {
        let mut values = vec![
            c"PATH=/system/bin:/system/xbin",
            c"LC_ALL=C",
            c"ANDROID_ROOT=/system",
            c"ANDROID_DATA=/data",
            c"ANDROID_ART_ROOT=/apex/com.android.art",
            c"ANDROID_RUNTIME_ROOT=/apex/com.android.runtime",
            c"ANDROID_I18N_ROOT=/apex/com.android.i18n",
            c"ANDROID_TZDATA_ROOT=/apex/com.android.tzdata",
        ];
        if self.uses_app_process() {
            values.extend(super::art_profile::ENVIRONMENT);
        }
        if self.needs_content_jar() {
            values.push(projection.content_classpath());
        } else if self.needs_am_jar() {
            values.push(projection.am_classpath());
        } else if matches!(
            self,
            Self::Catalog { .. }
                | Self::ApplicationAppOpsState { .. }
                | Self::ApplicationAccountState { .. }
                | Self::CalendarCounts { .. }
        ) {
            values.push(c"CLASSPATH=/system/system_ext/framework/droidloom-input-bridge.jar");
        }
        values
    }

    pub(super) fn binary(&self) -> &'static CStr {
        match self {
            Self::NativeUi { value } => super::native_ui::binary(value.command()),
            Self::Read { value } => value.binary(),
            Self::PreparationRead { value } => super::preparation_read::binary(&value.kind()),
            Self::IhgRead { value } => if value.state() { c"app_process64" } else { c"cmd" },
            Self::NativeFixture { value } => if value.state(){c"app_process64"}else{c"cmd"},
            Self::Vintf { value } => value.binary(),
            Self::PackageHelp { .. }
            | Self::EmptyMeituanRetainedAbsence {}
            | Self::Browser { .. }
            | Self::RuntimeAbi { .. }
            | Self::ApplicationExitState { .. }
            | Self::ApplicationPermissionState { .. }
            | Self::UserZeroPackageInventory { .. }
            | Self::NativeLeafPackage { .. } => c"cmd",
            Self::ContactsRead { .. }
            | Self::Catalog { .. }
            | Self::ApplicationAppOpsState { .. }
            | Self::ApplicationAccountState { .. }
            | Self::CalendarCounts { .. } => c"app_process64",
            Self::Launch { .. } | Self::Install { .. } | Self::Display { .. } => c"cmd",
        }
    }

    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        match self {
            Self::NativeUi { value } => super::native_ui::arguments(value),
            Self::NativeLeafPackage { value } => value.arguments(),
            Self::Read { value } => value.arguments(),
            Self::PreparationRead { value } => super::preparation_read::arguments(value),
            Self::PackageHelp { value } => super::package_help::arguments(value),
            Self::IhgRead { value } => value.arguments(),
            Self::EmptyMeituanRetainedAbsence {} => super::empty_meituan::absence_arguments(),
            Self::NativeFixture { value } => value.arguments(),
            Self::Vintf { value } => value.arguments(),
            Self::RuntimeAbi { value } => value.arguments(),
            Self::ApplicationExitState { value } => value.arguments(),
            Self::ApplicationPermissionState { value } => value.arguments(),
            Self::ApplicationAppOpsState { value } => value.arguments(),
            Self::ApplicationAccountState { value } => value.arguments(),
            Self::CalendarCounts { value } => value.arguments(),
            Self::UserZeroPackageInventory { value } => value.arguments(),
            Self::Browser { value } => value.arguments(),
            Self::ContactsRead { value } => value.arguments(),
            Self::Launch { value } => value.arguments(),
            Self::Install { value } => value.arguments(),
            Self::Catalog { value } => value.arguments(),
            Self::Display { value } => value.arguments(),
        }
    }

    pub(super) fn domain(&self) -> OperationDomain {
        match self {
            Self::Read { .. }
            | Self::EmptyMeituanRetainedAbsence {}
            | Self::PackageHelp { .. }
            | Self::Vintf { .. }
            | Self::UserZeroPackageInventory { .. }
            | Self::ApplicationPermissionState { .. } => OperationDomain::Query,
            Self::RuntimeAbi { .. } | Self::ApplicationExitState { .. } => {
                OperationDomain::LaunchRead
            }
            Self::Browser { value } => value.domain(),
            Self::ContactsRead { .. } => OperationDomain::ContactsRead,
            Self::Launch { value } => value.domain(),
            Self::Install { .. } => OperationDomain::Install,
            Self::Catalog { .. } => OperationDomain::CatalogRead,
            Self::ApplicationAppOpsState { .. } => OperationDomain::AppOpsRead,
            Self::ApplicationAccountState { .. } => OperationDomain::AccountRead,
            Self::CalendarCounts { .. } => OperationDomain::CalendarCounts,
            Self::Display { .. } => OperationDomain::DisplayControl,
            Self::PreparationRead { .. } => OperationDomain::PreparationRead,
            Self::IhgRead { value } => if value.state() { OperationDomain::IhgInstrument } else { OperationDomain::Query },
            Self::NativeFixture { value } => if value.state(){OperationDomain::FixtureState}else if value.removes() { OperationDomain::Install } else { OperationDomain::Query },
            Self::NativeUi { value } => super::native_ui::domain(value.command()),
            Self::NativeLeafPackage { value } => value.domain(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_meituan_retained_absence_is_a_fixed_readonly_query() {
        let operation=ApplicationOperation::EmptyMeituanRetainedAbsence{};
        operation.validate().unwrap();
        assert_eq!(operation.domain(),OperationDomain::Query);
        assert_eq!(operation.binary(),c"cmd");
        assert_eq!(operation.arguments().unwrap().iter().map(|v|v.to_str().unwrap()).collect::<Vec<_>>(),
            ["/system/bin/cmd","package","list","packages","-u","-U","--user","all",crate::empty_meituan_contract::PACKAGE]);
        let mut raw=serde_json::to_value(&operation).unwrap();raw["package"]="other.package".into();
        assert!(serde_json::from_value::<ApplicationOperation>(raw).is_err());
    }

    #[test]
    fn ihg_static_helper_retained_absence_keeps_query_role_and_state_has_its_own_profile() {
        let operation = ApplicationOperation::IhgRead {
            value: super::super::ihg_helper::IhgRead::RetainedAbsence {},
        };
        operation.validate().unwrap();
        assert_eq!(operation.domain(), OperationDomain::Query);
        assert_eq!(operation.binary(), c"cmd");
        assert_eq!(operation.descriptor_count(), 15);
        assert!(!operation.uses_app_process());
        assert!(!operation.needs_am_jar());
        assert_eq!(operation.execution_limit(), std::time::Duration::from_secs(8));
        let argv:Vec<_>=operation.arguments().unwrap().iter().map(|x|x.to_string_lossy().into_owned()).collect();
        assert_eq!(argv, ["/system/bin/cmd","package","list","packages","-u","-U","--user","all","org.droidloom.qa.ihg.finalmain.r1"]);
        let profile=super::super::ihg_helper::ihg_helper_execution_profile(true);
        assert_eq!(profile.process_selinux, OperationDomain::IhgInstrument.context());
        assert_eq!(profile.guest_uid,2000);
        assert_ne!(profile.process_selinux,OperationDomain::NativeUi.context());
        assert_ne!(profile.process_selinux,OperationDomain::PreparationRead.context());
        for value in [
            r#"{"operation":"IhgRead","value":{"ihg_read":"RetainedAbsence","package":"other"}}"#,
            r#"{"operation":"IhgRead","value":{"ihg_read":"Install","argv":["true"]}}"#,
            r#"{"operation":"IhgRead","value":{"ihg_read":"State","request":null}}"#,
        ] {
            assert!(serde_json::from_str::<ApplicationOperation>(value).is_err());
        }
    }

    #[test]
    fn contacts_read_operation_keeps_classpath_and_domain_out_of_existing_read_and_browser_roles() {
        let operation = ApplicationOperation::ContactsRead {
            value: ContactsQuery::RawRows,
        };
        let environment = operation.environment(QueryProjection::LegacyRoot);
        assert_eq!(operation.domain(), OperationDomain::ContactsRead);
        assert_eq!(operation.binary(), c"app_process64");
        assert_eq!(operation.descriptor_count(), 17);
        assert!(environment.contains(&c"CLASSPATH=/.droidloom-query/content.jar"));
        assert_eq!(
            OperationDomain::ContactsRead.terminated(),
            b"u:r:droidloom_contacts_read:s0\0"
        );
        for other in [
            ApplicationOperation::Read {
                value: ApplicationRead::PackagePaths {
                    package: "com.android.contacts".into(),
                    user: 0,
                },
            },
            ApplicationOperation::Browser {
                value: BrowserCommand::Start {
                    user: 0,
                    url: "https://example.org/fixture".into(),
                },
            },
        ] {
            assert_eq!(other.descriptor_count(), 15);
            assert!(!other.needs_content_jar());
            assert!(
                !other
                    .environment(QueryProjection::LegacyRoot)
                    .iter()
                    .any(|x| x.to_bytes().starts_with(b"CLASSPATH="))
            );
            assert_ne!(other.domain(), OperationDomain::ContactsRead);
        }
        for message in [
            r#"{"operation":"ContactsRead","value":{"contacts_read":"RawRows"},"domain":"u:r:shell:s0"}"#,
            r#"{"operation":"ContactsRead","value":{"contacts_read":"RawRows","classpath":"/data/other.jar"}}"#,
            r#"{"operation":"ContactsRead","value":{"contacts_read":"Delete","raw_contact_id":"1"}}"#,
        ] {
            assert!(serde_json::from_str::<ApplicationOperation>(message).is_err());
        }
    }
    fn strings(command: &BrowserCommand) -> Vec<String> {
        command
            .arguments()
            .unwrap()
            .into_iter()
            .map(|v| v.into_string().unwrap())
            .collect()
    }

    #[test]
    fn production_browser_operation_keeps_read_role_separate_from_activity_start() {
        let url = "https://example.org/firefox-fixture?mode=public";
        for command in [
            BrowserCommand::Resolve {
                user: 0,
                url: url.into(),
            },
            BrowserCommand::Start {
                user: 0,
                url: url.into(),
            },
        ] {
            let argv = strings(&command);
            assert_eq!(
                BrowserCommand::from_command(&argv, 0, url).unwrap(),
                command
            );
            assert!(ApplicationRead::from_command(&argv).is_err());
        }
        let read = ApplicationOperation::Read {
            value: ApplicationRead::PackagePaths {
                package: "org.mozilla.firefox".into(),
                user: 0,
            },
        };
        assert_eq!(read.domain(), OperationDomain::Query);
        assert_eq!(
            BrowserCommand::Resolve {
                user: 0,
                url: url.into()
            }
            .domain(),
            OperationDomain::Query
        );
        assert_eq!(
            BrowserCommand::Start {
                user: 0,
                url: url.into()
            }
            .domain(),
            OperationDomain::Browser
        );
        assert_ne!(
            OperationDomain::Query.context(),
            OperationDomain::Browser.context()
        );
        assert_eq!(
            OperationDomain::Query.terminated(),
            b"u:r:droidloom_query:s0\0"
        );
        assert_eq!(
            OperationDomain::Browser.terminated(),
            b"u:r:droidloom_browser:s0\0"
        );
    }

    #[test]
    fn production_browser_operation_rejects_cross_user_url_explicit_component_and_injected_role() {
        let url = "https://example.org/fixture";
        let start = BrowserCommand::Start {
            user: 10,
            url: url.into(),
        };
        let argv = strings(&start);
        assert!(BrowserCommand::from_command(&argv, 0, url).is_err());
        assert!(BrowserCommand::from_command(&argv, 10, "https://example.org/other").is_err());
        let mut explicit = argv.clone();
        explicit.extend(["-n".into(), "org.mozilla.firefox/.App".into()]);
        assert!(BrowserCommand::from_command(&explicit, 10, url).is_err());
        for invalid in [
            "file:///data/user/0/a",
            "https://example.org/\nsecret",
            "https://user:pass@example.org/",
        ] {
            assert!(
                BrowserCommand::Start {
                    user: 10,
                    url: invalid.into()
                }
                .arguments()
                .is_err()
            );
        }
        for message in [
            r#"{"operation":"Browser","value":{"browser":"Start","user":0,"url":"https://example.org/","domain":"u:r:shell:s0"}}"#,
            r#"{"operation":"Browser","value":{"browser":"Start","user":0,"url":"https://example.org/"},"pid":123}"#,
            r#"{"operation":"Command","argv":["/system/bin/sh","-c","true"]}"#,
        ] {
            assert!(serde_json::from_str::<ApplicationOperation>(message).is_err());
        }
    }
    #[test]
    fn only_fixed_app_process_roles_receive_the_complete_original_art_environment() {
        let catalog = serde_json::from_value(serde_json::json!({
            "command":{"catalog":"List","user":0},
            "selected_jar_sha256":"a".repeat(64)
        }))
        .unwrap();
        for operation in [
            ApplicationOperation::ContactsRead {
                value: ContactsQuery::RawRows,
            },
            ApplicationOperation::Catalog { value: catalog },
        ] {
            for projection in [QueryProjection::LegacyRoot, QueryProjection::EarlyDev] {
                let environment = operation.environment(projection);
                for fixed in super::super::art_profile::ENVIRONMENT {
                    assert_eq!(environment.iter().filter(|e| **e == fixed).count(), 1);
                }
                assert_eq!(
                    environment
                        .iter()
                        .filter(|e| e.to_bytes().starts_with(b"CLASSPATH="))
                        .count(),
                    1
                );
            }
        }
        let native = ApplicationOperation::Read {
            value: ApplicationRead::PackagePaths {
                package: "com.android.contacts".into(),
                user: 0,
            },
        };
        assert!(
            !native
                .environment(QueryProjection::EarlyDev)
                .iter()
                .any(|e| e.to_bytes().starts_with(b"BOOTCLASSPATH=")
                    || e.to_bytes().starts_with(b"DEX2OATBOOTCLASSPATH="))
        );
    }
}
