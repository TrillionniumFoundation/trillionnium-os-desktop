//! Comparison projection of the one fixed complete user-0 package/UID query.
//!
//! Deserializing this document never creates an actual observation. Only the
//! authenticated NativeApplicationInspector can mint the separate opaque token.
use crate::control::application_probe::RuntimeEpoch;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

pub(crate) const MAX_WIRE_BYTES: usize = 196608;
pub const SCHEMA: &str = "droidloom.user-zero-package-inventory.v1";

#[derive(Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PackageUid {
    pub package: String,
    pub uid: u32,
}
#[derive(Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct UserZeroPackageInventoryFacts {
    pub schema: String,
    pub epoch: RuntimeEpoch,
    pub records: Vec<PackageUid>,
    pub records_sha256: String,
    pub stdout_bytes: usize,
    pub stdout_sha256: String,
    pub query_receipt: Value,
    pub comparison_only: bool,
}

fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn package_name(name: &str) -> bool {
    name == "android"
        || (!name.is_empty()
            && name.len() <= 255
            && name.contains('.')
            && name.split('.').all(|part| {
                !part.is_empty() && part.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'_')
            }))
}
fn exact(v: &Value, fields: &[&str]) -> bool {
    v.as_object()
        .is_some_and(|o| o.len() == fields.len() && fields.iter().all(|k| o.contains_key(*k)))
}
fn positive(v: &Value) -> bool {
    v.as_u64().is_some_and(|n| n > 0)
}
fn pid(v: &Value) -> bool {
    v.as_u64()
        .is_some_and(|n| (2..=u32::MAX as u64).contains(&n))
}
fn receipt_valid(receipt: &Value, bytes: usize, sha256: &str) -> bool {
    let lifecycle = &receipt["lifecycle"];
    let stdio = &lifecycle["stdio_creator"];
    // This repeats the actual source-owned ReadReceipt retirement contract for
    // the wire comparison. It is never a constructor for a process owner.
    exact(
        receipt,
        &[
            "schema",
            "lifecycle",
            "query_pid",
            "query_waitid_code",
            "query_waitid_status",
            "exec",
            "output_bytes",
            "output_sha256",
            "elapsed_millis",
            "cgroup_removed",
        ],
    ) && receipt["schema"] == 2
        && receipt["cgroup_removed"] == true
        && pid(&receipt["query_pid"])
        && receipt["query_waitid_code"] == libc::CLD_EXITED
        && receipt["query_waitid_status"] == 0
        && receipt["output_bytes"].as_u64() == Some(bytes as u64)
        && receipt["output_sha256"] == sha256
        && receipt["elapsed_millis"].as_u64().is_some()
        && receipt["exec"].is_object()
        && exact(
            lifecycle,
            &[
                "owner",
                "factory_pid",
                "factory_tid",
                "factory_pidfd_device",
                "factory_pidfd_inode",
                "query_pidfd_device",
                "query_pidfd_inode",
                "stdio_creator",
                "release_acknowledged",
            ],
        )
        && lifecycle["owner"] == "instance_factory"
        && pid(&lifecycle["factory_pid"])
        && lifecycle["factory_pid"] == lifecycle["factory_tid"]
        && lifecycle["factory_pid"] != receipt["query_pid"]
        && [
            "factory_pidfd_device",
            "factory_pidfd_inode",
            "query_pidfd_device",
            "query_pidfd_inode",
        ]
        .iter()
        .all(|k| positive(&lifecycle[k]))
        && lifecycle["release_acknowledged"] == true
        && exact(stdio, &["pid", "waitid_code", "waitid_status"])
        && pid(&stdio["pid"])
        && stdio["pid"] != receipt["query_pid"]
        && stdio["pid"] != lifecycle["factory_pid"]
        && stdio["waitid_code"] == libc::CLD_EXITED
        && stdio["waitid_status"] == 0
}
impl UserZeroPackageInventoryFacts {
    #[cfg(target_os = "linux")]
    pub(crate) fn from_actual(
        actual: &crate::production_application::UserZeroPackageInventoryObservation,
        expected: &RuntimeEpoch,
    ) -> Result<Self, String> {
        let records = actual
            .records()
            .iter()
            .map(|(package, uid)| PackageUid {
                package: package.clone(),
                uid: *uid,
            })
            .collect::<Vec<_>>();
        let value = Self {
            schema: SCHEMA.into(),
            epoch: actual.epoch().clone(),
            records_sha256: hash(&serde_json::to_vec(&records).map_err(|e| e.to_string())?),
            records,
            stdout_bytes: actual.stdout_bytes(),
            stdout_sha256: actual.stdout_sha256().into(),
            query_receipt: serde_json::to_value(actual.receipt()).map_err(|e| e.to_string())?,
            comparison_only: true,
        };
        value.validate(expected)?;
        Ok(value)
    }
    /// Validate a saved comparison document against an already observed epoch.
    /// This never creates an actual inventory token, peer/PIDFD custody, or an
    /// observation time, and does not issue a query or grant application credit.
    pub fn validate_comparison(&self, expected: &RuntimeEpoch) -> Result<(), String> {
        self.validate(expected)
    }
    pub(crate) fn validate(&self, expected: &RuntimeEpoch) -> Result<(), String> {
        if self.schema != SCHEMA
            || &self.epoch != expected
            || !self.comparison_only
            || self.records.is_empty()
            || self.records.len() > 2048
            || !(1..=65536).contains(&self.stdout_bytes)
            || !digest(&self.stdout_sha256)
            || !digest(&self.records_sha256)
            || self
                .records
                .iter()
                .any(|r| !package_name(&r.package) || r.uid >= 100_000)
            || !self.records.windows(2).all(|w| w[0].package < w[1].package)
        {
            return Err("complete fixed user-0 inventory identity or bounds differ".into());
        }
        let actual_bytes = self
            .records
            .iter()
            .map(|r| {
                "package:".len() + r.package.len() + " uid:".len() + r.uid.to_string().len() + 1
            })
            .sum::<usize>();
        if self.stdout_bytes != actual_bytes
            || self.records_sha256
                != hash(&serde_json::to_vec(&self.records).map_err(|e| e.to_string())?)
            || !receipt_valid(&self.query_receipt, self.stdout_bytes, &self.stdout_sha256)
        {
            return Err("complete inventory output or actual query retirement differs".into());
        }
        Ok(())
    }
    /// Factual comparison, never a new authority or selected-package filter.
    pub fn records(&self) -> BTreeMap<&str, u32> {
        self.records
            .iter()
            .map(|r| (r.package.as_str(), r.uid))
            .collect()
    }
    pub(crate) fn same_table(&self, other: &Self) -> bool {
        self.epoch == other.epoch
            && self.records == other.records
            && self.records_sha256 == other.records_sha256
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> UserZeroPackageInventoryFacts {
        // Pure wire parser data. These values cannot mint the opaque client token.
        let records = vec![
            PackageUid {
                package: "android".into(),
                uid: 1000,
            },
            PackageUid {
                package: "com.example.actual".into(),
                uid: 10123,
            },
            PackageUid {
                package: "com.example.shared".into(),
                uid: 1000,
            },
        ];
        let raw=b"package:com.example.shared uid:1000\npackage:android uid:1000\npackage:com.example.actual uid:10123\n";
        UserZeroPackageInventoryFacts {
            schema: SCHEMA.into(),
            epoch: RuntimeEpoch {
                boot_id: "fixture-boot".into(),
                cell_host_pid: 12,
                framework_host_pid: 13,
                framework_start_ticks: 30,
            },
            records_sha256: hash(&serde_json::to_vec(&records).unwrap()),
            records,
            stdout_bytes: raw.len(),
            stdout_sha256: hash(raw),
            comparison_only: true,
            query_receipt: serde_json::json!({
                "schema":2,"query_pid":300,"query_waitid_code":libc::CLD_EXITED,
                "query_waitid_status":0,"exec":{},"output_bytes":raw.len(),
                "output_sha256":hash(raw),"elapsed_millis":1,"cgroup_removed":true,
                "lifecycle":{"owner":"instance_factory","factory_pid":200,"factory_tid":200,
                "factory_pidfd_device":1,"factory_pidfd_inode":2,"query_pidfd_device":1,
                "query_pidfd_inode":3,"release_acknowledged":true,
                "stdio_creator":{"pid":400,"waitid_code":libc::CLD_EXITED,"waitid_status":0}}
            }),
        }
    }
    #[test]
    fn inventory_wire_preserves_shared_uids_full_rows_and_normal_retirement() {
        let row = fixture();
        row.validate(&row.epoch).unwrap();
        let table = row.records();
        assert_eq!(table.len(), 3);
        assert_eq!(table["android"], table["com.example.shared"]);
        let mut another = fixture();
        another.query_receipt["query_pid"] = serde_json::json!(301);
        another.query_receipt["elapsed_millis"] = serde_json::json!(2);
        another.validate(&another.epoch).unwrap();
        assert!(row.same_table(&another));
    }
    #[test]
    fn inventory_wire_rejects_partial_forged_epoch_or_retirement_comparisons() {
        for case in 0..13 {
            let mut row = fixture();
            let expected = row.epoch.clone();
            match case {
                0 => row.epoch.framework_start_ticks += 1,
                1 => {
                    row.records.remove(0);
                }
                2 => row.records.swap(0, 1),
                3 => row.records.push(PackageUid {
                    package: "android".into(),
                    uid: 1000,
                }),
                4 => row.records[0].uid = 101000,
                5 => row.stdout_bytes += 1,
                6 => row.records_sha256 = "a".repeat(64),
                7 => row.query_receipt["cgroup_removed"] = serde_json::json!(false),
                8 => row.query_receipt["query_waitid_status"] = serde_json::json!(1),
                9 => {
                    row.query_receipt["lifecycle"]["release_acknowledged"] =
                        serde_json::json!(false)
                }
                10 => {
                    row.query_receipt["lifecycle"]["stdio_creator"]["waitid_status"] =
                        serde_json::json!(1)
                }
                11 => row.query_receipt["lifecycle"]["owner"] = serde_json::json!("legacy_broker"),
                _ => row.comparison_only = false,
            }
            assert!(row.validate(&expected).is_err(), "{case}");
        }
        let mut wire = serde_json::to_value(fixture()).unwrap();
        wire["passed"] = serde_json::json!(true);
        assert!(serde_json::from_value::<UserZeroPackageInventoryFacts>(wire).is_err());
    }
}
