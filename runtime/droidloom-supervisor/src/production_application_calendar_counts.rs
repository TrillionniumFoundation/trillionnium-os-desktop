//! Fixed read-only Calendar database counts in the selected normal InputBridge JAR.
//! The original owner supplies the JAR digest, descriptors and absolute end.
use super::*;
use crate::native_calendar_counts as fixed;
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use std::time::Instant;

#[derive(Clone, Debug, Serialize)]
pub(super) struct CalendarCountsRead {
    selected_jar_sha256: String,
}
impl<'de> Deserialize<'de> for CalendarCountsRead {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> std::result::Result<Self, D::Error> {
        struct OnlyDigest;
        impl<'de> serde::de::Visitor<'de> for OnlyDigest {
            type Value = CalendarCountsRead;
            fn expecting(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                f.write_str("one closed normal Calendar JAR digest object")
            }
            fn visit_map<M: serde::de::MapAccess<'de>>(self, mut map: M)
                -> std::result::Result<Self::Value, M::Error>
            {
                let mut digest = None;
                while let Some(key) = map.next_key::<String>()? {
                    if key != "selected_jar_sha256" {
                        return Err(serde::de::Error::unknown_field(&key, &["selected_jar_sha256"]));
                    }
                    if digest.is_some() {
                        return Err(serde::de::Error::duplicate_field("selected_jar_sha256"));
                    }
                    digest = Some(map.next_value::<String>()?);
                }
                Ok(CalendarCountsRead {
                    selected_jar_sha256: digest
                        .ok_or_else(|| serde::de::Error::missing_field("selected_jar_sha256"))?,
                })
            }
        }
        deserializer.deserialize_map(OnlyDigest)
    }
}
impl CalendarCountsRead {
    fn new(selected_jar_sha256: String) -> Result<Self> {
        let value = Self { selected_jar_sha256 };
        value.validate()?;
        Ok(value)
    }
    pub(super) fn validate(&self) -> Result<()> {
        require(self.selected_jar_sha256.len() == 64
            && self.selected_jar_sha256.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
            "Calendar requires the original selected sealed normal JAR")
    }
    pub(super) fn jar_digest(&self) -> &str { &self.selected_jar_sha256 }
    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        ["/system/bin/app_process64", "-Xint", "-Xusejit:false", "/system/bin", fixed::CLASS]
            .into_iter().map(|value| CString::new(value).map_err(external)).collect()
    }
}

pub(super) fn run(
    owner: &EarlyApplicationAuthority<'_>,
    deadline: Instant,
) -> Result<LaunchCommandResult> {
    owner.check_request_deadline().map_err(observation_authority_error)?;
    require(owner.request_deadline() == Some(deadline),
        "Calendar must borrow the original admitted absolute command end")?;
    crate::production_host_admission::check_observation_before(deadline)?;
    owner.ready().map_err(observation_authority_error)?;
    let framework = owner.observe_framework().map_err(observation_authority_error)?;
    let epoch = owner.epoch(&framework).map_err(observation_authority_error)?;
    let request = CalendarCountsRead::new(
        owner.catalog_jar_digest().map_err(observation_authority_error)?)?;
    let files = owner.descriptors(c"app_process64").map_err(observation_authority_error)?;
    require(files.len() == 12, "Calendar original descriptor prefix differs")?;
    let (uid, gid) = owner.mapped_root().map_err(observation_authority_error)?;
    let jar = worker::executable::bind_catalog(&files[2], request.jar_digest(), uid, gid, deadline)?;
    let operation = ApplicationOperation::CalendarCounts { value: request.clone() };
    let result = factory_query::run(owner, &operation, deadline);
    workflow::finish_effect(result, || {
        owner.ready().map_err(observation_authority_error)?;
        jar.revalidate(&files[2], request.jar_digest(), uid, gid, deadline)?;
        require(owner.catalog_jar_digest().map_err(observation_authority_error)?
                    == request.selected_jar_sha256,
            "Calendar original normal JAR selection changed")?;
        require(owner.epoch(&framework).map_err(observation_authority_error)? == epoch,
            "Calendar query crossed the actual original framework epoch")?;
        owner.check_request_deadline().map_err(observation_authority_error)?;
        crate::production_host_admission::check_observation_before(deadline)?;
        Ok(())
    }, deadline)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn calendar_counts_fixed_normal_operation_rejects_input_selection() {
        let operation = ApplicationOperation::CalendarCounts {
            value: CalendarCountsRead::new("ab".repeat(32)).unwrap(),
        };
        operation.validate().unwrap();
        assert_eq!(operation.domain(), OperationDomain::CalendarCounts);
        assert_eq!(operation.domain().guest_uid(), fixed::OBSERVER_UID);
        assert_eq!(operation.binary(), c"app_process64");
        assert_eq!(operation.descriptor_count(), 15);
        assert!(operation.uses_app_process());
        assert!(!operation.needs_content_jar() && !operation.needs_am_jar());
        assert_eq!(operation.output_limit(), fixed::OUTPUT_BYTES);
        assert_eq!(operation.execution_limit(), fixed::MAX_DURATION);
        assert_eq!(operation.catalog_jar_digest(), Some("abababababababababababababababababababababababababababababababab"));
        let args = operation.arguments().unwrap().into_iter()
            .map(|value| value.into_string().unwrap()).collect::<Vec<_>>();
        assert_eq!(args, ["/system/bin/app_process64", "-Xint", "-Xusejit:false", "/system/bin", fixed::CLASS]);
        assert!(ApplicationRead::from_command(&args).is_err());
        assert!(operation.environment(QueryProjection::EarlyDev)
            .contains(&c"CLASSPATH=/system/system_ext/framework/droidloom-input-bridge.jar"));
        let main = crate::main_custody::tests::sample();
        let application = ApplicationInspection {
            package: fixed::SUBJECT.into(), user: 0, uid: 10061, version_code: 37,
            epoch: main.epoch.clone(),
            apks: vec![crate::control::application_probe::InstalledApk {
                name: "base.apk".into(), path: "/system/app/Calendar/Calendar.apk".into(),
                bytes: 512, sha256: "a".repeat(64),
            }],
        };
        let command = crate::native_application_ui_gateway::GatewayCommand::CalendarCounts {};
        let public = crate::native_application_ui_gateway::GatewayRequest::from_owned(
            &main, &application, &command.literal_arguments().unwrap(), false,
            Instant::now() + fixed::MAX_DURATION,
        ).unwrap();
        // Public comparison data cannot choose the old operation and thereby
        // bypass the separately bound normal JAR or fixed Calendar role.
        assert!(ApplicationOperation::NativeUi { value: public }.validate().is_err());
        let wire = serde_json::to_string(&operation).unwrap();
        serde_json::from_str::<ApplicationOperation>(&wire).unwrap().validate().unwrap();
        for field in ["package", "database", "sql", "uid", "gid", "user", "pid", "argv",
            "classpath", "domain", "output", "passed"] {
            let mut changed: serde_json::Value = serde_json::from_str(&wire).unwrap();
            changed["value"][field] = serde_json::json!("caller input");
            assert!(serde_json::from_value::<ApplicationOperation>(changed).is_err(), "{field}");
        }
        for invalid in ["[]", "\"x\"", "null", "{}",
            r#"{"selected_jar_sha256":"a","selected_jar_sha256":"b"}"#] {
            assert!(serde_json::from_str::<CalendarCountsRead>(invalid).is_err());
        }
        for digest in ["", &"ab".repeat(31), &"AB".repeat(32), &"ab".repeat(33)] {
            assert!(CalendarCountsRead::new(digest.into()).is_err());
        }
        assert_eq!(OperationDomain::AccountRead.guest_uid(), 1000);
        assert_eq!(OperationDomain::NativeUiRead.guest_uid(), 0);
        assert_eq!(OperationDomain::Query.guest_uid(), 2000);
    }
}
