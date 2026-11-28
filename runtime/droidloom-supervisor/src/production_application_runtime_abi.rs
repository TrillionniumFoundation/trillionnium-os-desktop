//! Fixed package-filtered ActivityManager ABI metadata in the existing LaunchRead
//! role. Only the original early owner can run it; a package name is a selector,
//! never a PID/namespace/UID/ABI/engine assertion.
use super::runtime_abi::{self, RuntimeAbiRecord, RuntimeAbiRecords};
use super::*;
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use sha2::{Digest, Sha256};
use std::time::Instant;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct RuntimeAbiRead {
    package: String,
}
impl RuntimeAbiRead {
    pub(super) fn new(package: &str) -> Result<Self> {
        runtime_abi::validate_package(package)?;
        Ok(Self {
            package: package.into(),
        })
    }
    pub(super) fn validate(&self) -> Result<()> {
        runtime_abi::validate_package(&self.package)
    }
    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        [
            "/system/bin/cmd",
            "activity",
            "dump",
            "processes",
            &self.package,
        ]
        .into_iter()
        .map(|s| CString::new(s).map_err(|_| reject("NUL in fixed runtime ABI query")))
        .collect()
    }
}

/// Actual finite-query output parsed for comparison, retaining its real
/// retirement/exec receipt. No Deserialize/Clone or public constructor exists.
pub(crate) struct RuntimeAbiObservation {
    records: RuntimeAbiRecords,
    receipt: ReadReceipt,
}
impl RuntimeAbiObservation {
    pub(crate) fn records(&self) -> &[RuntimeAbiRecord] {
        self.records.records()
    }
    pub(crate) fn main_process(&self, uid: u32, command: &str) -> Result<&RuntimeAbiRecord> {
        self.records.main_process(uid, command)
    }
    pub(crate) fn match_process(
        &self,
        guest_pid: u32,
        uid: u32,
        command: &str,
    ) -> Result<&RuntimeAbiRecord> {
        self.records.match_process(guest_pid, uid, command)
    }
    pub(crate) fn receipt(&self) -> &ReadReceipt {
        &self.receipt
    }
}

pub(crate) fn read_runtime_abi(
    owner: &EarlyApplicationAuthority<'_>,
    package: &str,
    deadline: Instant,
) -> Result<RuntimeAbiObservation> {
    let query = RuntimeAbiRead::new(package)?;
    owner
        .check_request_deadline()
        .map_err(observation_authority_error)?;
    require(
        owner.request_deadline() == Some(deadline),
        "runtime ABI query must borrow the original admitted absolute work deadline",
    )?;
    crate::production_host_admission::check_observation_before(deadline)?;
    // This retains the existing factory waitid, query I/O, metadata observer,
    // cgroup retirement and error priority. It opens no new observation window.
    let actual = factory_query::run(
        owner,
        &ApplicationOperation::RuntimeAbi { value: query },
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
        "runtime ABI actual exit, output, or retirement mismatch",
    )?;
    owner
        .check_request_deadline()
        .map_err(observation_authority_error)?;
    let text = std::str::from_utf8(&actual.output.stdout)
        .map_err(|_| reject("runtime ABI non-UTF8 output"))?;
    let records = runtime_abi::parse(package, text, deadline)?;
    crate::production_host_admission::check_observation_before(deadline)?;
    Ok(RuntimeAbiObservation {
        records,
        receipt: actual.receipt,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn runtime_abi_query_is_one_fixed_read_role_and_cannot_carry_process_authority() {
        for package in runtime_abi::PACKAGES {
            let operation = ApplicationOperation::RuntimeAbi {
                value: RuntimeAbiRead::new(package).unwrap(),
            };
            assert_eq!(operation.domain(), OperationDomain::LaunchRead);
            assert_eq!(operation.binary(), c"cmd");
            assert_eq!(operation.descriptor_count(), 15);
            assert_eq!(operation.output_limit(), runtime_abi::OUTPUT_BYTES);
            assert!(!operation.uses_app_process());
            let args: Vec<_> = operation
                .arguments()
                .unwrap()
                .into_iter()
                .map(|a| a.into_string().unwrap())
                .collect();
            assert_eq!(
                args,
                ["/system/bin/cmd", "activity", "dump", "processes", package]
            );
            assert!(ApplicationRead::from_command(&args).is_err());
            assert!(
                !operation
                    .environment(QueryProjection::EarlyDev)
                    .iter()
                    .any(|v| v.to_bytes().starts_with(b"CLASSPATH="))
            );
        }
        for text in [
            r#"{"operation":"RuntimeAbi","value":{"package":"com.android.settings","uid":1000}}"#,
            r#"{"operation":"RuntimeAbi","value":{"package":"com.android.settings","pid":432}}"#,
            r#"{"operation":"RuntimeAbi","value":{"package":"com.android.settings","requiredAbi":"x86_64"}}"#,
            r#"{"operation":"RuntimeAbi","value":{"package":"com.android.settings","argv":["true"]}}"#,
            r#"{"operation":"RuntimeAbi","value":{"package":"com.android.settings"},"domain":"u:r:shell:s0"}"#,
        ] {
            assert!(serde_json::from_str::<ApplicationOperation>(text).is_err());
        }
        for package in [
            "com.example.other",
            "com.android.settings --user 0",
            "/proc/432",
        ] {
            assert!(RuntimeAbiRead::new(package).is_err());
        }
    }
}
