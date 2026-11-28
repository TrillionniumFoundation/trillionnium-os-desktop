//! Closed comparison protocol for one official package on the positively
//! admitted independent EMPTY generation. No JSON constructor grants storage.
use crate::{
    control::MainCustodyObservation, empty_meituan_contract as fixed,
    main_custody::RuntimeMainCustody, package_inventory_observation::UserZeroPackageInventoryFacts,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    time::{Duration, Instant},
};

pub(crate) const LIMIT: Duration = Duration::from_secs(720);
pub(crate) const MAX_REPLY_BYTES: usize = 1024 * 1024;
type Result<T> = std::result::Result<T, String>;
fn need(ok: bool, why: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(why.into()) }
}
pub(crate) fn official() -> crate::native_working_install::OriginalApplication {
    crate::native_working_install::OriginalApplication {
        package: fixed::PACKAGE.into(),
        version_code: fixed::VERSION_CODE,
        version_name: fixed::VERSION_NAME.into(),
        signer_certificates_sha256: BTreeSet::from([fixed::SIGNER_SHA256.into()]),
        segments: vec![crate::native_working_install::OriginalSegment {
            bytes: fixed::APK_BYTES,
            sha256: fixed::APK_SHA256.into(),
            manifest_split_name: None,
        }],
    }
}
pub(crate) fn require_main(main: &RuntimeMainCustody) -> Result<()> {
    main.validate(&main.epoch)?;
    need(
        main.persistent_data.original_copy_origin.is_none(),
        "EMPTY diagnostic cannot consume original-copy data",
    )?;
    main.persistent_data
        .fresh_diagnostic_origin
        .as_ref()
        .ok_or("ordinary existing data has no positive EMPTY origin")?
        .validate(
            main.persistent_data
                .backings
                .each_ref()
                .map(|v| v.backing.stable7()),
        )
        .map_err(str::to_owned)
}
fn monotonic_ns() -> Result<u64> {
    let mut t: libc::timespec = unsafe { std::mem::zeroed() };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut t) } != 0 {
        return Err(std::io::Error::last_os_error().to_string());
    }
    need(
        t.tv_sec >= 0 && (0..1_000_000_000).contains(&t.tv_nsec),
        "EMPTY monotonic clock invalid",
    )?;
    (t.tv_sec as u64)
        .checked_mul(1_000_000_000)
        .and_then(|v| v.checked_add(t.tv_nsec as u64))
        .ok_or("EMPTY clock overflow".into())
}
fn encode_end(end: Instant) -> Result<u64> {
    let clock = monotonic_ns()?;
    let left = end
        .checked_duration_since(Instant::now())
        .filter(|v| !v.is_zero())
        .ok_or("EMPTY installation end elapsed")?;
    need(
        left <= LIMIT,
        "EMPTY installation enlarged fixed original budget",
    )?;
    clock
        .checked_add(u64::try_from(left.as_nanos()).map_err(|_| "EMPTY end overflow")?)
        .ok_or("EMPTY end overflow".into())
}
fn decode_end(value: u64) -> Result<Instant> {
    let now = Instant::now();
    let left = value
        .checked_sub(monotonic_ns()?)
        .filter(|v| *v > 0)
        .ok_or("EMPTY end elapsed")?;
    need(
        u128::from(left) <= LIMIT.as_nanos(),
        "EMPTY request enlarged original deadline",
    )?;
    now.checked_add(Duration::from_nanos(left))
        .ok_or("EMPTY end overflow".into())
}
fn closed<'de, D, T>(d: D) -> std::result::Result<T, D::Error>
where
    D: serde::Deserializer<'de>,
    T: serde::de::DeserializeOwned + Serialize,
{
    let raw = crate::native_preparation_json::unique_json_value(d)?;
    let v: T = serde_json::from_value(raw.clone()).map_err(serde::de::Error::custom)?;
    if serde_json::to_value(&v).map_err(serde::de::Error::custom)? != raw {
        return Err(serde::de::Error::custom(
            "unrecognized independent EMPTY comparison fields",
        ));
    }
    Ok(v)
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    schema: String,
    #[serde(deserialize_with = "closed")]
    main: RuntimeMainCustody,
    deadline_monotonic_ns: u64,
}
impl Request {
    pub(crate) fn from_owned(main: &MainCustodyObservation, end: Instant) -> Result<Self> {
        let v = Self {
            schema: fixed::SCHEMA.into(),
            main: main.facts().clone(),
            deadline_monotonic_ns: encode_end(end)?,
        };
        v.validate()?;
        Ok(v)
    }
    pub(crate) fn validate(&self) -> Result<()> {
        need(self.schema == fixed::SCHEMA, "EMPTY request schema differs")?;
        require_main(&self.main)?;
        self.deadline()?;
        Ok(())
    }
    pub(crate) fn main(&self) -> &RuntimeMainCustody {
        &self.main
    }
    pub(crate) fn deadline(&self) -> Result<Instant> {
        decode_end(self.deadline_monotonic_ns)
    }
}
fn inventory_delta(
    before: &UserZeroPackageInventoryFacts,
    after: &UserZeroPackageInventoryFacts,
) -> Result<u32> {
    before.validate(&before.epoch)?;
    after.validate(&before.epoch)?;
    let a = before.records();
    let b = after.records();
    let uid = *b
        .get(fixed::PACKAGE)
        .ok_or("official Meituan absent after normal commit")?;
    need(
        !a.contains_key(fixed::PACKAGE)
            && !a.values().any(|v| *v == uid)
            && (10000..100000).contains(&uid)
            && b.len() == a.len() + 1
            && a.iter().all(|(k, v)| b.get(k) == Some(v)),
        "complete user-zero table changed beyond one new distinct official Meituan",
    )?;
    Ok(uid)
}
fn installation(value: &Value) -> Result<()> {
    let session = value["session"]
        .as_u64()
        .filter(|v| (1..=i32::MAX as u64).contains(v))
        .ok_or("normal EMPTY session absent")?;
    need(
        value["user"] == 0
            && value["bytes"] == fixed::APK_BYTES
            && value["segments"]
                == json!([{"index":0,"bytes":fixed::APK_BYTES,"sha256":fixed::APK_SHA256}]),
        "EMPTY install consumed another payload or user",
    )?;
    let commands = value["commands"]
        .as_array()
        .ok_or("normal EMPTY command history absent")?;
    let expected = [
        json!({"install":"CreateOnly","bytes":fixed::APK_BYTES}),
        json!({"install":"Write","session":session,"index":0,"bytes":fixed::APK_BYTES}),
        json!({"install":"Commit","session":session}),
    ];
    need(
        commands.len() == 3
            && commands
                .iter()
                .zip(expected)
                .all(|(v, e)| v["command"] == e),
        "EMPTY transaction must be one create-only, one complete original write and one commit",
    )
}
fn installation_retirement(value: &Value) -> Result<()> {
    let mut profile = crate::production_application::package_help_execution_profile();
    profile.process_selinux = "u:r:droidloom_install:s0";
    for command in value["commands"]
        .as_array()
        .ok_or("normal install receipts absent")?
    {
        need(
            command.as_object().is_some_and(|v| {
                v.len() == 2 && v.contains_key("command") && v.contains_key("receipt")
            }),
            "normal EMPTY install requires each complete command and retirement receipt",
        )?;
        let receipt: crate::native_package_help::ReadComparison =
            serde_json::from_value(command["receipt"].clone()).map_err(|e| e.to_string())?;
        receipt.validate_for(None, &profile, Duration::from_secs(110))?;
        need(
            receipt.status()?.success(),
            "normal EMPTY installer command did not actually exit successfully",
        )?;
    }
    Ok(())
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Reply {
    schema: String,
    request: Request,
    #[serde(deserialize_with = "closed")]
    before_main: RuntimeMainCustody,
    #[serde(deserialize_with = "closed")]
    after_main: RuntimeMainCustody,
    #[serde(deserialize_with = "closed")]
    before_inventory: UserZeroPackageInventoryFacts,
    #[serde(deserialize_with = "closed")]
    after_inventory: UserZeroPackageInventoryFacts,
    #[serde(deserialize_with = "crate::native_preparation_json::unique_json_value")]
    absence_receipt: Value,
    #[serde(deserialize_with = "crate::native_preparation_json::unique_json_value")]
    installation: Value,
}
impl Reply {
    pub(crate) fn from_actual(
        request: Request,
        before_main: RuntimeMainCustody,
        after_main: RuntimeMainCustody,
        before_inventory: UserZeroPackageInventoryFacts,
        after_inventory: UserZeroPackageInventoryFacts,
        absence: &crate::production_application::ReadReceipt,
        installed: &crate::production_application::InstallObservation,
    ) -> Result<Self> {
        let v = Self {
            schema: fixed::SCHEMA.into(),
            request,
            before_main,
            after_main,
            before_inventory,
            after_inventory,
            absence_receipt: serde_json::to_value(absence).map_err(|e| e.to_string())?,
            installation: serde_json::to_value(installed).map_err(|e| e.to_string())?,
        };
        v.validate(&v.request)?;
        Ok(v)
    }
    pub(crate) fn validate(&self, request: &Request) -> Result<u32> {
        need(
            self.schema == fixed::SCHEMA
                && self.request == *request
                && self.before_main == *request.main()
                && self.after_main == self.before_main,
            "EMPTY reply does not retain the same actual Main/request",
        )?;
        require_main(&self.after_main)?;
        need(
            self.before_inventory.epoch == self.before_main.epoch,
            "EMPTY preinstall table belongs to another Main",
        )?;
        let uid = inventory_delta(&self.before_inventory, &self.after_inventory)?;
        need(
            crate::package_inventory_observation::receipt_valid(
                &self.absence_receipt,
                0,
                &crate::native_working_install::hash(&[]),
            ),
            "all-user retained absence did not actually retire",
        )?;
        let absence: crate::native_package_help::ReadComparison =
            serde_json::from_value(self.absence_receipt.clone()).map_err(|e| e.to_string())?;
        absence.validate_for(
            Some(&[]),
            &crate::production_application::package_help_execution_profile(),
            Duration::from_secs(30),
        )?;
        need(
            absence.status()?.success(),
            "EMPTY retained-absence query failed",
        )?;
        installation(&self.installation)?;
        installation_retirement(&self.installation)?;
        Ok(uid)
    }
    pub(crate) fn main(&self) -> &RuntimeMainCustody {
        &self.after_main
    }
    pub(crate) fn installed_uid(&self) -> Result<u32> {
        self.validate(&self.request)
    }
    pub(crate) fn comparison(&self) -> Result<Value> {
        let uid = self.validate(&self.request)?;
        let mut v = serde_json::to_value(self).map_err(|e| e.to_string())?;
        v["installed_uid"] = uid.into();
        v["official_apk_sha256"] = fixed::APK_SHA256.into();
        v["production_ready"] = false.into();
        v["original_data_migration"] = false.into();
        v["business_acceptance"] = false.into();
        Ok(v)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn empty_meituan_neither_none_nor_original_copy_is_positive_authority() {
        let mut main = crate::main_custody::tests::sample();
        assert!(require_main(&main).is_err());
        main.persistent_data.original_copy_origin = None;
        assert!(require_main(&main).is_err());
        assert!(encode_end(Instant::now()).is_err());
        assert!(encode_end(Instant::now() + LIMIT + Duration::from_secs(1)).is_err());
    }
    #[test]
    fn empty_meituan_requires_create_only_and_exact_original_bytes() {
        let value = json!({"session":42,"user":0,"bytes":fixed::APK_BYTES,
            "segments":[{"index":0,"bytes":fixed::APK_BYTES,"sha256":fixed::APK_SHA256}],
            "commands":[{"command":{"install":"CreateOnly","bytes":fixed::APK_BYTES}},
                {"command":{"install":"Write","session":42,"index":0,"bytes":fixed::APK_BYTES}},
                {"command":{"install":"Commit","session":42}}]});
        installation(&value).unwrap();
        // Command-shaped JSON alone never proves any actual child retirement.
        assert!(installation_retirement(&value).is_err());
        for change in 0..4 {
            let mut other = value.clone();
            match change {
                0 => {
                    other["commands"][0]["command"] =
                        json!({"install":"Create","user":0,"bytes":fixed::APK_BYTES})
                }
                1 => other["segments"][0]["sha256"] = "0".repeat(64).into(),
                2 => other["commands"][2]["command"]["session"] = 43.into(),
                _ => other["user"] = 10.into(),
            }
            assert!(installation(&other).is_err());
        }
    }
    #[test]
    fn empty_meituan_official_pin_matches_the_reviewed_normal_material() {
        let bytes = include_bytes!(
            "../../../tools/droidloom-update/resources/working-preparation/apps41/SELECTED41.json"
        );
        let raw: Value = serde_json::from_slice(bytes).unwrap();
        let rows = raw["applications"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|v| v["package"] == fixed::PACKAGE)
            .collect::<Vec<_>>();
        assert_eq!(rows.len(), 1);
        let r = rows[0];
        assert_eq!(r["version_code"], fixed::VERSION_CODE);
        assert_eq!(r["version_name"], fixed::VERSION_NAME);
        assert_eq!(
            r["signer_certificates_sha256"],
            json!([fixed::SIGNER_SHA256])
        );
        let files = r["material_files"].as_array().unwrap();
        assert_eq!(files.len(), 1);
        assert_eq!(files[0]["bytes"], fixed::APK_BYTES);
        assert_eq!(files[0]["sha256"], fixed::APK_SHA256);
        assert_eq!(files[0]["sdk37_signature_valid"], true);
        assert_eq!(
            files[0]["verified_signer_certificates_sha256"],
            json!([fixed::SIGNER_SHA256])
        );
    }
}
