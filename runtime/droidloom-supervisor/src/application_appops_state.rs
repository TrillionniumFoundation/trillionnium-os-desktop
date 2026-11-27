//! Complete selected user-zero AppOps mode comparison from the normal sealed JAR.
//!
//! The selected services.jar bc5d11f4f09ec079c5804a01008e8317a0854231502550acaff89aa9f1083a86
//! and classes.dex 242185b43c8d7d4cebc3488b6deb628ee5a971f94cde7816d1d896704c118658
//! establish getUidOps/getOpsForPackage scopes. The shell's get renderer loses
//! their boundary, so the source-owned Java adapter uses the typed Binder rows.
//! All 181 defaults are read in that actual framework. Only package records
//! equal to those defaults are normalized; actual UID overrides remain exact.
//! Access timestamps/durations are not mode settings. This partial comparison
//! does not prove accounts, data persistence, effective access or acceptance.
use crate::control::application_probe::{ApplicationInspection, RuntimeEpoch};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::time::Instant;

pub(crate) const OUTPUT_BYTES: usize = 131_072;
pub(crate) const MAX_WIRE_BYTES: usize = 196_608;
const STATE_BYTES: usize = 131_072;
const OP_COUNT: usize = 181;
pub const SCHEMA: &str = "droidloom.application-appops-state.v1";
const ANDROID_SCHEMA: &str = "droidloom.application-appops-android.v1";

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AppOpDefault {
    op: u16,
    name: String,
    mode: u8,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ModeRow {
    op: u16,
    mode: u8,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct AndroidState {
    schema: String,
    observer_uid: u32,
    user: u32,
    package: String,
    uid: u32,
    version_code: u64,
    source_paths: Vec<String>,
    defaults: Vec<AppOpDefault>,
    uid_modes: Vec<ModeRow>,
    package_modes: Vec<ModeRow>,
    samples: u32,
}

/// Comparison only. The Inspector's live token has no deserializer or constructor.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PackageAppOpsState {
    package: String,
    user: u32,
    app_id: u32,
    version_code: u64,
    source_paths: BTreeSet<String>,
    defaults: Vec<AppOpDefault>,
    uid_modes: BTreeMap<u16, u8>,
    package_overrides: BTreeMap<u16, u8>,
}
impl PackageAppOpsState {
    pub fn package(&self) -> &str { &self.package }
    pub fn app_id(&self) -> u32 { self.app_id }
    pub fn version_code(&self) -> u64 { self.version_code }
    pub fn uid_modes(&self) -> &BTreeMap<u16, u8> { &self.uid_modes }
    pub fn package_overrides(&self) -> &BTreeMap<u16, u8> { &self.package_overrides }

    fn validate(&self) -> Result<(), String> {
        let mut names = BTreeSet::new();
        if !crate::engine_custody::selected_package(&self.package) || self.user != 0
            || !(1..100_000).contains(&self.app_id)
            || self.source_paths.is_empty() || self.source_paths.len() > 128
            || self.source_paths.iter().any(|s| !code_path(s))
            || self.defaults.len() != OP_COUNT
            || self.defaults.iter().enumerate().any(|(index, row)| {
                usize::from(row.op) != index || row.mode > 4 || !op_name(&row.name)
                    || !names.insert(&row.name)
            })
            || self.uid_modes.len() > OP_COUNT || self.package_overrides.len() > OP_COUNT
            || self.uid_modes.iter().chain(&self.package_overrides)
                .any(|(&op, &mode)| usize::from(op) >= OP_COUNT || mode > 4)
            || self.package_overrides.iter().any(|(&op, &mode)| {
                self.defaults.get(usize::from(op)).is_none_or(|row| row.mode == mode)
            })
            || serde_json::to_vec(self).map_err(|e| e.to_string())?.len() > STATE_BYTES
        {
            return Err("complete AppOps identity, scoped modes, defaults or bounds differ".into());
        }
        Ok(())
    }
    fn require_application(&self, actual: &ApplicationInspection) -> Result<(), String> {
        self.validate()?;
        let actual_paths: BTreeSet<_> = actual.apks.iter().map(|apk| apk.path.clone()).collect();
        if actual.user != 0 || self.package != actual.package || self.app_id != actual.uid
            || self.version_code != actual.version_code || actual_paths != self.source_paths
            || actual_paths.len() != actual.apks.len() {
            return Err("AppOps sample differs from the actual installed subject".into());
        }
        Ok(())
    }
}

#[derive(Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ApplicationAppOpsStateFacts {
    schema: String,
    epoch: RuntimeEpoch,
    state: PackageAppOpsState,
    state_sha256: String,
    stdout_bytes: usize,
    stdout_sha256: String,
    query_receipt: Value,
    comparison_only: bool,
}
pub(crate) type ParsedAppOpsState = PackageAppOpsState;
fn hash(value: &[u8]) -> String { format!("{:x}", Sha256::digest(value)) }
fn digest(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn op_name(value: &str) -> bool {
    !value.is_empty() && value.len() <= 128 && value.as_bytes()[0].is_ascii_uppercase()
        && value.bytes().all(|c| c.is_ascii_uppercase() || c.is_ascii_digit() || c == b'_')
}
fn code_path(value: &str) -> bool {
    value.starts_with('/') && value.len() <= 4096 && !value.chars().any(char::is_control)
        && value.split('/').skip(1).all(|part| !part.is_empty() && part != "." && part != "..")
}
fn check(end: Instant) -> Result<(), String> {
    if Instant::now() >= end { Err("original AppOps observation deadline elapsed".into()) }
    else { Ok(()) }
}
fn modes(rows: Vec<ModeRow>) -> Result<BTreeMap<u16, u8>, String> {
    if rows.len() > OP_COUNT { return Err("AppOps modes exceed selected roster".into()); }
    let mut result = BTreeMap::new();
    for row in rows {
        if usize::from(row.op) >= OP_COUNT || row.mode > 4
            || result.insert(row.op, row.mode).is_some() {
            return Err("duplicate, foreign or invalid actual AppOps operation".into());
        }
    }
    Ok(result)
}
pub(crate) fn parse(package: &str, raw: &str, end: Instant) -> Result<ParsedAppOpsState, String> {
    check(end)?;
    if !crate::engine_custody::selected_package(package) || raw.is_empty()
        || raw.len() > OUTPUT_BYTES || !raw.ends_with('\n')
        || raw[..raw.len() - 1].chars().any(char::is_control) {
        return Err("complete AppOps output is invalid, truncated or unbounded".into());
    }
    let wire: AndroidState = serde_json::from_str(raw).map_err(|e| e.to_string())?;
    if wire.schema != ANDROID_SCHEMA || wire.observer_uid != 2000 || wire.user != 0
        || wire.package != package || wire.samples != 2
        || wire.defaults.len() != OP_COUNT || wire.source_paths.is_empty()
        || wire.source_paths.len() > 128 {
        return Err("normal AppOps adapter scope or complete sample contract differs".into());
    }
    let path_count = wire.source_paths.len();
    let source_paths: BTreeSet<_> = wire.source_paths.into_iter().collect();
    if source_paths.len() != path_count { return Err("duplicate actual installed code path".into()); }
    let uid_modes = modes(wire.uid_modes)?;
    let mut package_overrides = modes(wire.package_modes)?;
    // Validate the complete default table before using it to omit access-only
    // entries. The raw package rows remain committed by the full stdout receipt.
    let mut names = BTreeSet::new();
    if wire.defaults.iter().enumerate().any(|(index, row)| {
        usize::from(row.op) != index || row.mode > 4 || !op_name(&row.name)
            || !names.insert(&row.name)
    }) {
        return Err("actual AppOps default table is incomplete, duplicated or reordered".into());
    }
    package_overrides.retain(|op, mode| wire.defaults[usize::from(*op)].mode != *mode);
    let state = PackageAppOpsState {
        package: wire.package, user: wire.user, app_id: wire.uid,
        version_code: wire.version_code, source_paths, defaults: wire.defaults,
        uid_modes, package_overrides,
    };
    state.validate()?;
    check(end)?;
    Ok(state)
}
impl ApplicationAppOpsStateFacts {
    #[cfg(target_os = "linux")]
    pub(crate) fn from_actual(
        actual: &crate::production_application::ApplicationAppOpsStateObservation,
        expected: &RuntimeEpoch,
    ) -> Result<Self, String> {
        let state = actual.parsed().clone();
        let facts = Self {
            schema: SCHEMA.into(), epoch: actual.epoch().clone(),
            state_sha256: hash(&serde_json::to_vec(&state).map_err(|e| e.to_string())?),
            state, stdout_bytes: actual.stdout_bytes(),
            stdout_sha256: actual.stdout_sha256().into(),
            query_receipt: serde_json::to_value(actual.receipt()).map_err(|e| e.to_string())?,
            comparison_only: true,
        };
        facts.validate(expected, actual.package())?;
        Ok(facts)
    }
    pub(crate) fn validate(&self, expected: &RuntimeEpoch, package: &str) -> Result<(), String> {
        self.state.validate()?;
        if self.schema != SCHEMA || &self.epoch != expected || self.state.package != package
            || !self.comparison_only || !(1..=OUTPUT_BYTES).contains(&self.stdout_bytes)
            || !digest(&self.stdout_sha256)
            || self.state_sha256 != hash(&serde_json::to_vec(&self.state).map_err(|e| e.to_string())?)
            || !crate::package_inventory_observation::receipt_valid(
                &self.query_receipt, self.stdout_bytes, &self.stdout_sha256) {
            return Err("actual AppOps owner, complete comparison or retirement differs".into());
        }
        Ok(())
    }
    pub fn epoch(&self) -> &RuntimeEpoch { &self.epoch }
    pub fn state(&self) -> &PackageAppOpsState { &self.state }
    pub fn state_sha256(&self) -> &str { &self.state_sha256 }
    pub fn stdout_sha256(&self) -> &str { &self.stdout_sha256 }
    pub fn require_application(&self, actual: &ApplicationInspection) -> Result<(), String> {
        self.validate(&actual.epoch, &actual.package)?;
        self.state.require_application(actual)
    }
    pub fn same_modes(&self, other: &Self) -> Result<(), String> {
        self.validate(&self.epoch, &self.state.package)?;
        other.validate(&self.epoch, &self.state.package)?;
        if self.state != other.state { return Err("complete user-zero AppOps modes changed".into()); }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn end() -> Instant { Instant::now() + std::time::Duration::from_secs(5) }
    fn wire() -> Value {
        json!({"schema":ANDROID_SCHEMA,"observer_uid":2000,"user":0,
            "package":"com.android.settings","uid":1000,"version_code":36,
            "source_paths":["/system/priv-app/Settings/Settings.apk"],
            "defaults":(0..OP_COUNT).map(|i|json!({"op":i,"name":format!("OP_{i}"),"mode":0})).collect::<Vec<_>>(),
            "uid_modes":[],"package_modes":[],"samples":2})
    }
    fn read(value: &Value) -> Result<PackageAppOpsState, String> {
        parse("com.android.settings", &(value.to_string()+"\n"), end())
    }
    #[test]
    fn appops_state_default_access_records_do_not_change_modes_but_uid_scope_does() {
        let base = wire();
        let before = read(&base).unwrap();
        let mut access = base.clone();
        access["package_modes"] = json!([{"op":2,"mode":0},{"op":3,"mode":0}]);
        assert_eq!(before, read(&access).unwrap());
        access["uid_modes"] = json!([{"op":2,"mode":0}]);
        assert_ne!(before, read(&access).unwrap());
        assert_eq!(read(&access).unwrap().uid_modes(), &BTreeMap::from([(2,0)]));
        let mut changed = base.clone();
        changed["package_modes"] = json!([{"op":2,"mode":1}]);
        assert_ne!(before, read(&changed).unwrap());
        changed["uid_modes"] = changed["package_modes"].clone();
        changed["package_modes"] = json!([]);
        assert_ne!(read(&changed).unwrap().uid_modes(), &BTreeMap::new());
    }
    #[test]
    fn appops_state_rejects_incomplete_defaults_duplicate_modes_and_foreign_subjects() {
        let base=wire();
        let mut invalid=Vec::new();
        for (field,value) in [
            ("observer_uid",json!(0)),("user",json!(10)),("uid",json!(100001)),
            ("samples",json!(1)),("package",json!("com.example.other")),
            ("source_paths",json!(["/a/../b"])),
            ("source_paths",json!(["/a.apk","/a.apk"])),
            ("uid_modes",json!([{"op":1,"mode":0},{"op":1,"mode":1}])),
            ("package_modes",json!([{"op":181,"mode":0}])),
            ("package_modes",json!([{"op":1,"mode":5}])),
        ] {
            let mut v=base.clone();v[field]=value;invalid.push(v);
        }
        let mut v=base.clone();v["defaults"].as_array_mut().unwrap().pop();invalid.push(v);
        let mut v=base.clone();v["defaults"][1]["op"]=json!(0);invalid.push(v);
        let mut v=base.clone();v["defaults"][1]["name"]=v["defaults"][0]["name"].clone();invalid.push(v);
        let mut v=base.clone();v["defaults"][1]["mode"]=json!(5);invalid.push(v);
        let mut v=base.clone();v["caller_pass"]=json!(true);invalid.push(v);
        for v in invalid { assert!(read(&v).is_err(),"{v}"); }
        assert!(parse("com.android.settings",&base.to_string(),end()).is_err());
        assert!(parse("com.android.settings",&(base.to_string()+"\n"),Instant::now()).is_err());
        assert!(parse("com.example.other",&(base.to_string()+"\n"),end()).is_err());
    }
    #[test]
    fn appops_state_keeps_defaults_uid_version_and_all_code_paths_in_semantic_comparison() {
        let base=wire();let before=read(&base).unwrap();
        for(field,value)in [
            ("uid",json!(1001)),("version_code",json!(37)),
            ("source_paths",json!(["/system/priv-app/Settings/Settings.apk","/data/app/split.apk"])),
            ("uid_modes",json!([{"op":17,"mode":4}])),
        ] {
            let mut v=base.clone();v[field]=value;assert_ne!(before,read(&v).unwrap());
        }
        let mut v=base.clone();v["defaults"][17]["mode"]=json!(1);
        assert_ne!(before,read(&v).unwrap());
    }
    #[test]
    fn appops_state_java_roster_is_exactly_the_normal_selected_packages() {
        let java=include_str!("../../../android/framework/droidloom-input-bridge/src/com/android/droidloom/catalog/ApplicationAppOpsState.java");
        let block=java.split("PACKAGES = new HashSet<>(Arrays.asList(\n").nth(1).unwrap()
            .split("\n    ));").next().unwrap();
        let actual=block.lines().map(|line|line.trim().trim_end_matches(',').trim_matches('"'))
            .collect::<BTreeSet<_>>();
        let expected=crate::engine_custody::SELECTED_PACKAGES.iter().copied().collect::<BTreeSet<_>>();
        assert_eq!(actual,expected);
        assert_eq!(actual.len(),39);
    }
}
