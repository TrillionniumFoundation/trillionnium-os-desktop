//! One selected-package ActivityManager exit-history query in LaunchRead.
//! The fixed original owner lends all fifteen descriptors and the original end.
use super::*;
use crate::application_exit_state::{self, ParsedExitState};
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use sha2::{Digest, Sha256};
use std::time::Instant;

#[derive(Clone, Debug, Serialize)]
pub(super) struct ApplicationExitStateRead {
    package: String,
}
impl<'de> Deserialize<'de> for ApplicationExitStateRead {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let value = serde_json::Value::deserialize(deserializer)?;
        let object = value
            .as_object()
            .ok_or_else(|| serde::de::Error::custom("exit-state query must be an object"))?;
        if object.len() != 1 {
            return Err(serde::de::Error::custom(
                "exit-state query has only its fixed selected package",
            ));
        }
        let package = object
            .get("package")
            .and_then(serde_json::Value::as_str)
            .ok_or_else(|| serde::de::Error::custom("exit-state package is absent or not text"))?;
        Self::new(package).map_err(serde::de::Error::custom)
    }
}
impl ApplicationExitStateRead {
    fn new(package: &str) -> Result<Self> {
        require(
            crate::engine_custody::selected_package(package),
            "exit-state requires a source-selected application",
        )?;
        Ok(Self {
            package: package.into(),
        })
    }
    pub(super) fn validate(&self) -> Result<()> {
        require(
            crate::engine_custody::selected_package(&self.package),
            "exit-state selected application differs",
        )
    }
    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        [
            "/system/bin/cmd",
            "activity",
            "dump",
            "exit-info",
            &self.package,
        ]
        .into_iter()
        .map(|s| CString::new(s).map_err(|_| reject("NUL in fixed exit-state command")))
        .collect()
    }
}

/// Only the actual owner query can construct this internal observation.
pub(crate) struct ApplicationExitStateObservation {
    package: String,
    epoch: RuntimeEpoch,
    parsed: ParsedExitState,
    receipt: ReadReceipt,
}
impl ApplicationExitStateObservation {
    pub(crate) fn package(&self) -> &str {
        &self.package
    }
    pub(crate) fn epoch(&self) -> &RuntimeEpoch {
        &self.epoch
    }
    pub(crate) fn parsed(&self) -> &ParsedExitState {
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
pub(crate) fn read_application_exit_state(
    owner: &EarlyApplicationAuthority<'_>,
    package: &str,
    expected_epoch: &RuntimeEpoch,
    deadline: Instant,
) -> Result<ApplicationExitStateObservation> {
    let operation = ApplicationOperation::ApplicationExitState {
        value: ApplicationExitStateRead::new(package)?,
    };
    owner
        .check_request_deadline()
        .map_err(observation_authority_error)?;
    require(
        owner.request_deadline() == Some(deadline),
        "exit-state query must borrow the original admitted absolute work deadline",
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
        "exit-state original framework epoch differs before dispatch",
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
        "exit-state actual exit, complete captured output or retirement differs",
    )?;
    let text = std::str::from_utf8(&actual.output.stdout)
        .map_err(|_| reject("exit-state non-UTF8 output"))?;
    let parsed = application_exit_state::parse(package, text, deadline).map_err(external)?;
    require(
        owner
            .epoch(&framework)
            .map_err(observation_authority_error)?
            == epoch,
        "exit-state query crossed the actual framework epoch",
    )?;
    owner
        .check_request_deadline()
        .map_err(observation_authority_error)?;
    crate::production_host_admission::check_observation_before(deadline)?;
    Ok(ApplicationExitStateObservation {
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
    fn exit_state_query_is_fixed_selected_readonly_and_cannot_carry_authority() {
        let operation = ApplicationOperation::ApplicationExitState {
            value: ApplicationExitStateRead::new("com.android.settings").unwrap(),
        };
        operation.validate().unwrap();
        assert_eq!(operation.domain(), OperationDomain::LaunchRead);
        assert_eq!(operation.binary(), c"cmd");
        assert_eq!(operation.descriptor_count(), 15);
        assert_eq!(
            operation.output_limit(),
            application_exit_state::OUTPUT_BYTES
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
                "activity",
                "dump",
                "exit-info",
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
            let wire = format!(r#"{{"operation":"ApplicationExitState","value":{payload}}}"#);
            assert!(
                serde_json::from_str::<ApplicationOperation>(&wire).is_err(),
                "{wire}"
            );
        }
    }
}
