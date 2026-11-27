//! One selected-package PackageManager permission query in the existing Query role.
//! The fixed original owner lends all fifteen descriptors and the original end.
use super::*;
use crate::application_permission_state::{self, ParsedPermissionState};
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use sha2::{Digest, Sha256};
use std::time::Instant;

#[derive(Clone, Debug, Serialize)]
pub(super) struct ApplicationPermissionStateRead {
    package: String,
}
impl<'de> Deserialize<'de> for ApplicationPermissionStateRead {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let value = serde_json::Value::deserialize(deserializer)?;
        let object = value
            .as_object()
            .ok_or_else(|| serde::de::Error::custom("PM-permission query must be an object"))?;
        if object.len() != 1 {
            return Err(serde::de::Error::custom(
                "PM-permission query has only its fixed selected package",
            ));
        }
        let package = object
            .get("package")
            .and_then(serde_json::Value::as_str)
            .ok_or_else(|| {
                serde::de::Error::custom("PM-permission package is absent or not text")
            })?;
        Self::new(package).map_err(serde::de::Error::custom)
    }
}
impl ApplicationPermissionStateRead {
    fn new(package: &str) -> Result<Self> {
        require(
            crate::engine_custody::selected_package(package),
            "PM-permission requires a source-selected application",
        )?;
        Ok(Self {
            package: package.into(),
        })
    }
    pub(super) fn validate(&self) -> Result<()> {
        require(
            crate::engine_custody::selected_package(&self.package),
            "PM-permission selected application differs",
        )
    }
    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        ["/system/bin/cmd", "package", "dump-package", &self.package]
            .into_iter()
            .map(|s| CString::new(s).map_err(|_| reject("NUL in fixed PM-permission command")))
            .collect()
    }
}

/// Only the actual owner query can construct this internal observation.
pub(crate) struct ApplicationPermissionStateObservation {
    package: String,
    epoch: RuntimeEpoch,
    parsed: ParsedPermissionState,
    receipt: ReadReceipt,
}
impl ApplicationPermissionStateObservation {
    pub(crate) fn package(&self) -> &str {
        &self.package
    }
    pub(crate) fn epoch(&self) -> &RuntimeEpoch {
        &self.epoch
    }
    pub(crate) fn parsed(&self) -> &ParsedPermissionState {
        &self.parsed
    }
    pub(crate) fn receipt(&self) -> &ReadReceipt {
        &self.receipt
    }
    pub(crate) fn stdout_bytes(&self) -> usize {
        self.receipt.output_bytes
    }
    pub(crate) fn stdout_sha256(&self) -> &str {
        &self.receipt.output_sha256
    }
}
pub(crate) fn read_application_permission_state(
    owner: &EarlyApplicationAuthority<'_>,
    package: &str,
    expected_epoch: &RuntimeEpoch,
    deadline: Instant,
) -> Result<ApplicationPermissionStateObservation> {
    let operation = ApplicationOperation::ApplicationPermissionState {
        value: ApplicationPermissionStateRead::new(package)?,
    };
    owner
        .check_request_deadline()
        .map_err(observation_authority_error)?;
    require(
        owner.request_deadline() == Some(deadline),
        "PM-permission query must borrow the original admitted absolute work deadline",
    )?;
    crate::production_host_admission::check_observation_before(deadline)?;
    let framework = owner
        .observe_framework()
        .map_err(observation_authority_error)?;
    let epoch = owner
        .epoch(&framework)
        .map_err(observation_authority_error)?;
    require(
        &epoch == expected_epoch,
        "PM-permission original framework epoch differs before dispatch",
    )?;
    let actual = factory_query::run(owner, &operation, deadline)?;
    require(
        actual.output.status.code() == Some(0)
            && actual.output.stderr.is_empty()
            && actual.stderr_bytes == 0
            && actual.stderr_sha256 == format!("{:x}", Sha256::digest([]))
            && actual.receipt.successful_retirement()
            && actual.receipt.output_bytes == actual.output.stdout.len()
            && actual.receipt.output_sha256
                == format!("{:x}", Sha256::digest(&actual.output.stdout)),
        "PM-permission actual exit, complete captured output or retirement differs",
    )?;
    let text = std::str::from_utf8(&actual.output.stdout)
        .map_err(|_| reject("PM-permission non-UTF8 output"))?;
    let parsed = application_permission_state::parse(package, text, deadline).map_err(external)?;
    require(
        owner
            .epoch(&framework)
            .map_err(observation_authority_error)?
            == epoch,
        "PM-permission query crossed the actual framework epoch",
    )?;
    owner
        .check_request_deadline()
        .map_err(observation_authority_error)?;
    crate::production_host_admission::check_observation_before(deadline)?;
    Ok(ApplicationPermissionStateObservation {
        package: package.into(),
        epoch,
        parsed,
        receipt: actual.receipt,
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn pm_permissions_query_is_fixed_selected_readonly_and_cannot_carry_authority() {
        let operation = ApplicationOperation::ApplicationPermissionState {
            value: ApplicationPermissionStateRead::new("com.android.settings").unwrap(),
        };
        operation.validate().unwrap();
        assert_eq!(operation.domain(), OperationDomain::Query);
        assert_eq!(operation.binary(), c"cmd");
        assert_eq!(operation.descriptor_count(), 15);
        assert_eq!(
            operation.output_limit(),
            application_permission_state::OUTPUT_BYTES
        );
        assert!(!operation.uses_app_process());
        assert!(!operation.needs_content_jar());
        let args = operation
            .arguments()
            .unwrap()
            .into_iter()
            .map(|s| s.into_string().unwrap())
            .collect::<Vec<_>>();
        assert_eq!(
            args,
            [
                "/system/bin/cmd",
                "package",
                "dump-package",
                "com.android.settings"
            ]
        );
        assert!(ApplicationRead::from_command(&args).is_err());
        let wire = serde_json::to_string(&operation).unwrap();
        assert!(serde_json::from_str::<ApplicationOperation>(&wire).is_ok());
        for payload in [
            r#"{"package":"com.example.unselected"}"#,
            r#"{"package":"com.android.settings","uid":1000}"#,
            r#"{"package":"com.android.settings","pid":123}"#,
            r#"{"package":"com.android.settings","user":0}"#,
            r#"{"package":"com.android.settings","argv":["true"]}"#,
            r#"["com.android.settings"]"#,
            r#"null"#,
            r#"{}"#,
        ] {
            let wire = format!(r#"{{"operation":"ApplicationPermissionState","value":{payload}}}"#);
            assert!(
                serde_json::from_str::<ApplicationOperation>(&wire).is_err(),
                "{wire}"
            );
        }
    }
}
