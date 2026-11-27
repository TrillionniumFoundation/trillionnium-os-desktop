//! The original owner executes one fixed complete user-0 package/UID query.
//! No caller field can choose a package, user, command, UID, PID or namespace.
//! The returned comparison is tied to actual framework bookends and retirement.
use super::package_inventory::{self, UserZeroPackageInventoryRows};
use super::*;
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::time::Instant;

#[derive(Clone, Debug, Serialize)]
pub(super) struct UserZeroPackageInventoryRead {}
impl<'de> Deserialize<'de> for UserZeroPackageInventoryRead {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        // An empty named struct's derived visitor also accepts a JSON array.
        // This private command permits only the literal empty-object shape.
        struct EmptyObject;
        impl<'de> serde::de::Visitor<'de> for EmptyObject {
            type Value = UserZeroPackageInventoryRead;

            fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                formatter.write_str("an empty object for the fixed user-0 inventory query")
            }

            fn visit_map<M>(self, mut map: M) -> std::result::Result<Self::Value, M::Error>
            where
                M: serde::de::MapAccess<'de>,
            {
                if map.next_key::<serde::de::IgnoredAny>()?.is_some() {
                    return Err(serde::de::Error::custom(
                        "user-0 inventory query accepts no fields",
                    ));
                }
                Ok(UserZeroPackageInventoryRead {})
            }
        }
        deserializer.deserialize_map(EmptyObject)
    }
}
impl UserZeroPackageInventoryRead {
    pub(super) fn validate(&self) -> Result<()> {
        Ok(())
    }
    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        [
            "/system/bin/cmd",
            "package",
            "list",
            "packages",
            "-U",
            "--user",
            "0",
        ]
        .into_iter()
        .map(|s| CString::new(s).map_err(|_| reject("NUL in fixed user-0 inventory command")))
        .collect()
    }
}

/// Actual comparison observation minted only by the original owner query.
/// It has no Clone, Deserialize, public fields or public constructor.
pub(crate) struct UserZeroPackageInventoryObservation {
    rows: UserZeroPackageInventoryRows,
    epoch: RuntimeEpoch,
    receipt: ReadReceipt,
}
impl UserZeroPackageInventoryObservation {
    pub(crate) fn records(&self) -> &BTreeMap<String, u32> {
        self.rows.records()
    }
    pub(crate) fn epoch(&self) -> &RuntimeEpoch {
        &self.epoch
    }
    pub(crate) fn stdout_bytes(&self) -> usize {
        self.receipt.output_bytes
    }
    pub(crate) fn stdout_sha256(&self) -> &str {
        &self.receipt.output_sha256
    }
    pub(crate) fn receipt(&self) -> &ReadReceipt {
        &self.receipt
    }
}

pub(crate) fn read_user_zero_package_inventory(
    owner: &EarlyApplicationAuthority<'_>,
    deadline: Instant,
) -> Result<UserZeroPackageInventoryObservation> {
    owner
        .check_request_deadline()
        .map_err(observation_authority_error)?;
    require(
        owner.request_deadline() == Some(deadline),
        "user-0 inventory must borrow the original admitted absolute work deadline",
    )?;
    crate::production_host_admission::check_observation_before(deadline)?;
    let framework = owner
        .observe_framework()
        .map_err(observation_authority_error)?;
    let epoch = owner
        .epoch(&framework)
        .map_err(observation_authority_error)?;
    let actual = factory_query::run(
        owner,
        &ApplicationOperation::UserZeroPackageInventory {
            value: UserZeroPackageInventoryRead {},
        },
        deadline,
    )?;
    require(
        actual.output.status.code() == Some(0)
            && actual.output.stderr.is_empty()
            && actual.stderr_bytes == 0
            && actual.stderr_sha256 == format!("{:x}", Sha256::digest([]))
            && actual.receipt.successful_retirement()
            && actual.receipt.output_bytes == actual.output.stdout.len()
            && actual.receipt.output_sha256
                == format!("{:x}", Sha256::digest(&actual.output.stdout)),
        "user-0 inventory actual exit, captured output, or retirement mismatch",
    )?;
    let text = std::str::from_utf8(&actual.output.stdout)
        .map_err(|_| reject("user-0 package inventory non-UTF8 output"))?;
    let rows = package_inventory::parse(text, deadline)?;
    require(
        owner
            .epoch(&framework)
            .map_err(observation_authority_error)?
            == epoch,
        "user-0 package inventory crossed the actual framework epoch",
    )?;
    owner
        .check_request_deadline()
        .map_err(observation_authority_error)?;
    crate::production_host_admission::check_observation_before(deadline)?;
    Ok(UserZeroPackageInventoryObservation {
        rows,
        epoch,
        receipt: actual.receipt,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn user_zero_package_inventory_operation_has_no_selector_or_role_override() {
        let operation = ApplicationOperation::UserZeroPackageInventory {
            value: UserZeroPackageInventoryRead {},
        };
        operation.validate().unwrap();
        assert_eq!(operation.domain(), OperationDomain::Query);
        assert_eq!(operation.binary(), c"cmd");
        assert_eq!(operation.descriptor_count(), 15);
        assert_eq!(operation.output_limit(), package_inventory::OUTPUT_BYTES);
        assert!(!operation.uses_app_process());
        assert!(!operation.needs_content_jar());
        let args: Vec<_> = operation
            .arguments()
            .unwrap()
            .into_iter()
            .map(|arg| arg.into_string().unwrap())
            .collect();
        assert_eq!(
            args,
            [
                "/system/bin/cmd",
                "package",
                "list",
                "packages",
                "-U",
                "--user",
                "0"
            ]
        );
        // Existing public ApplicationRead shapes must remain unchanged.
        assert!(ApplicationRead::from_command(&args).is_err());
        for projection in [QueryProjection::LegacyRoot, QueryProjection::EarlyDev] {
            assert!(!operation.environment(projection).iter().any(|e| {
                e.to_bytes().starts_with(b"CLASSPATH=")
                    || e.to_bytes().starts_with(b"BOOTCLASSPATH=")
            }));
        }
        let roundtrip = serde_json::to_string(&operation).unwrap();
        assert_eq!(
            roundtrip,
            r#"{"operation":"UserZeroPackageInventory","value":{}}"#
        );
        assert!(serde_json::from_str::<ApplicationOperation>(&roundtrip).is_ok());
        for value in [
            r#"{"user":0}"#,
            r#"{"user":1}"#,
            r#"{"package":"android"}"#,
            r#"{"uid":1000}"#,
            r#"{"pid":432}"#,
            r#"{"argv":["true"]}"#,
            r#"{"domain":"u:r:shell:s0"}"#,
            r#"null"#,
            r#"[]"#,
        ] {
            let wire = format!(r#"{{"operation":"UserZeroPackageInventory","value":{value}}}"#);
            assert!(
                serde_json::from_str::<ApplicationOperation>(&wire).is_err(),
                "{wire}"
            );
        }
        assert!(
            serde_json::from_str::<ApplicationOperation>(
                r#"{"operation":"UserZeroPackageInventory","value":{},"pid":432}"#
            )
            .is_err()
        );
    }
}
