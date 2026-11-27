//! Anonymous registered-account comparison from the selected normal JAR.
//!
//! The selected CP3A AccountManager getAccountsAndVisibilityForPackage(null)
//! admits the independently fixed uid-1000 observer and traverses the complete
//! registered authenticator roster. This does not expose credentials or prove
//! an orphan database, login session, persistent data or whole application gate.
//! Only the live Inspector can mint authority; these serde values are comparison.
use crate::control::application_probe::{ApplicationInspection, RuntimeEpoch};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::time::Instant;

pub(crate) const OUTPUT_BYTES: usize = 131_072;
pub(crate) const MAX_WIRE_BYTES: usize = 196_608;
const MAX_AUTHENTICATORS: usize = 128;
const MAX_ACCOUNTS: usize = 512;
const SCOPE: &str = "all_registered_authenticator_accounts_and_target_visibility";
const ANDROID_SCHEMA: &str = "droidloom.application-account-android.v1";
pub const SCHEMA: &str = "droidloom.application-account-state.v1";

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AccountPackageIdentity {
    package: String,
    uid: u32,
    version_code: u64,
    source_paths: Vec<String>,
}
impl AccountPackageIdentity {
    fn validate(&self) -> Result<(), String> {
        let paths = self.source_paths.iter().collect::<BTreeSet<_>>();
        if !package_name(&self.package) || !(1..100_000).contains(&self.uid)
            || self.source_paths.is_empty() || self.source_paths.len() > 128
            || paths.len() != self.source_paths.len()
            || self.source_paths.iter().any(|p| !code_path(p))
            || self.source_paths.windows(2).any(|p| p[0] >= p[1]) {
            return Err("account package identity is incomplete or noncanonical".into());
        }
        Ok(())
    }
    fn require_application(&self, actual: &ApplicationInspection) -> Result<(), String> {
        self.validate()?;
        let paths: BTreeSet<_> = actual.apks.iter().map(|a| a.path.as_str()).collect();
        if actual.user != 0 || actual.package != self.package || actual.uid != self.uid
            || actual.version_code != self.version_code || paths.len() != actual.apks.len()
            || paths != self.source_paths.iter().map(String::as_str).collect() {
            return Err("account query differs from the actual full installed subject".into());
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AnonymousAuthenticator {
    type_token: String,
    provider: AccountPackageIdentity,
    label_id: u32,
    icon_id: u32,
    small_icon_id: u32,
    preferences_id: u32,
    custom_tokens: bool,
}
#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AnonymousAccount {
    account_token: String,
    type_token: String,
    visibility: u8,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct AndroidAccountState {
    schema: String,
    observer_uid: u32,
    user: u32,
    target: AccountPackageIdentity,
    authenticators: Vec<AnonymousAuthenticator>,
    accounts: Vec<AnonymousAccount>,
    samples: u32,
    scope: String,
}
#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PackageAccountState {
    user: u32,
    target: AccountPackageIdentity,
    authenticators: BTreeMap<String, AnonymousAuthenticator>,
    accounts: BTreeMap<String, AnonymousAccount>,
    scope: String,
}
pub(crate) type ParsedAccountState = PackageAccountState;
impl PackageAccountState {
    pub fn package(&self) -> &str { &self.target.package }
    pub fn uid(&self) -> u32 { self.target.uid }
    pub fn account_count(&self) -> usize { self.accounts.len() }
    pub fn authenticator_count(&self) -> usize { self.authenticators.len() }
    fn validate(&self) -> Result<(), String> {
        self.target.validate()?;
        if self.user != 0 || !crate::engine_custody::selected_package(self.package())
            || self.scope != SCOPE || self.authenticators.is_empty()
            || self.authenticators.len() > MAX_AUTHENTICATORS || self.accounts.len() > MAX_ACCOUNTS {
            return Err("account comparison scope or complete bounded registry differs".into());
        }
        for (token, row) in &self.authenticators {
            row.provider.validate()?;
            if !digest(token) || token != &row.type_token
                || [row.label_id, row.icon_id, row.small_icon_id, row.preferences_id]
                    .iter().any(|&n| n > i32::MAX as u32) {
                return Err("account authenticator comparison is invalid".into());
            }
        }
        for (token, row) in &self.accounts {
            if !digest(token) || token != &row.account_token || !digest(&row.type_token)
                || !self.authenticators.contains_key(&row.type_token)
                || !(1..=4).contains(&row.visibility) {
                return Err("account identity, registry relation or visibility is invalid".into());
            }
        }
        if canonical(self)?.len() > OUTPUT_BYTES {
            return Err("complete anonymous account comparison exceeds its bound".into());
        }
        Ok(())
    }
}

#[derive(Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ApplicationAccountStateFacts {
    schema: String,
    epoch: RuntimeEpoch,
    state: PackageAccountState,
    state_sha256: String,
    stdout_bytes: usize,
    stdout_sha256: String,
    query_receipt: Value,
    comparison_only: bool,
}
fn canonical<T: Serialize>(value: &T) -> Result<Vec<u8>, String> {
    serde_json::to_vec(value).map_err(|_| "account comparison cannot be encoded".into())
}
fn hash(bytes: &[u8]) -> String { format!("{:x}", Sha256::digest(bytes)) }
fn digest(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn package_name(value: &str) -> bool {
    value.len() <= 255 && value.split('.').all(|p| !p.is_empty()
        && p.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_'))
        && value.as_bytes().first().is_some_and(u8::is_ascii_alphabetic)
}
fn code_path(value: &str) -> bool {
    value.starts_with('/') && value.len() <= 4096 && !value.chars().any(char::is_control)
        && value.split('/').skip(1).all(|p| !p.is_empty() && p != "." && p != "..")
}
fn before(end: Instant) -> Result<(), String> {
    if Instant::now() >= end { Err("original account observation deadline elapsed".into()) }
    else { Ok(()) }
}
pub(crate) fn parse(package: &str, raw: &str, end: Instant) -> Result<ParsedAccountState, String> {
    before(end)?;
    if !crate::engine_custody::selected_package(package) || raw.is_empty()
        || raw.len() > OUTPUT_BYTES || !raw.ends_with('\n')
        || raw[..raw.len()-1].chars().any(char::is_control) {
        return Err("account observation is invalid, truncated or unbounded".into());
    }
    // Do not forward parser diagnostics: malformed input could contain a private
    // string. The normal producer emits only the fixed anonymous schema.
    let wire: AndroidAccountState = serde_json::from_str(raw)
        .map_err(|_| "account observation schema differs".to_string())?;
    if wire.schema != ANDROID_SCHEMA || wire.observer_uid != 1000 || wire.user != 0
        || wire.target.package != package || wire.samples != 2 || wire.scope != SCOPE
        || wire.authenticators.is_empty() || wire.authenticators.len() > MAX_AUTHENTICATORS
        || wire.accounts.len() > MAX_ACCOUNTS {
        return Err("normal account observer or complete sample contract differs".into());
    }
    let mut authenticators = BTreeMap::new();
    let mut accounts = BTreeMap::new();
    for row in wire.authenticators {
        if authenticators.last_key_value().is_some_and(|(prior, _)| prior >= &row.type_token)
            || authenticators.insert(row.type_token.clone(), row).is_some() {
            return Err("account authenticator roster is duplicate or unordered".into());
        }
    }
    for row in wire.accounts {
        if accounts.last_key_value().is_some_and(|(prior, _)| prior >= &row.account_token)
            || accounts.insert(row.account_token.clone(), row).is_some() {
            return Err("account roster is duplicate or unordered".into());
        }
    }
    let state = PackageAccountState { user: wire.user, target: wire.target,
        authenticators, accounts, scope: wire.scope };
    state.validate()?;
    before(end)?;
    Ok(state)
}
impl ApplicationAccountStateFacts {
    #[cfg(target_os = "linux")]
    pub(crate) fn from_actual(
        actual: &crate::production_application::ApplicationAccountStateObservation,
        expected: &RuntimeEpoch,
    ) -> Result<Self, String> {
        let state = actual.parsed().clone();
        let value = Self { schema: SCHEMA.into(), epoch: actual.epoch().clone(),
            state_sha256: hash(&canonical(&state)?), state,
            stdout_bytes: actual.stdout_bytes(), stdout_sha256: actual.stdout_sha256().into(),
            query_receipt: serde_json::to_value(actual.receipt())
                .map_err(|_| "account retirement cannot be encoded".to_string())?,
            comparison_only: true };
        value.validate(expected, actual.package())?;
        Ok(value)
    }
    pub(crate) fn validate(&self, epoch: &RuntimeEpoch, package: &str) -> Result<(), String> {
        self.state.validate()?;
        if self.schema != SCHEMA || &self.epoch != epoch || self.state.package() != package
            || !self.comparison_only || !(1..=OUTPUT_BYTES).contains(&self.stdout_bytes)
            || !digest(&self.stdout_sha256)
            || self.state_sha256 != hash(&canonical(&self.state)?)
            || !crate::package_inventory_observation::receipt_valid(
                &self.query_receipt, self.stdout_bytes, &self.stdout_sha256) {
            return Err("account comparison, actual owner or complete retirement differs".into());
        }
        Ok(())
    }
    pub fn epoch(&self) -> &RuntimeEpoch { &self.epoch }
    pub fn state(&self) -> &PackageAccountState { &self.state }
    pub fn state_sha256(&self) -> &str { &self.state_sha256 }
    pub fn stdout_sha256(&self) -> &str { &self.stdout_sha256 }
    pub fn require_application(&self, actual: &ApplicationInspection) -> Result<(), String> {
        self.validate(&actual.epoch, &actual.package)?;
        self.state.target.require_application(actual)
    }
    /// Comparison only. Callers need two actual tokens from the same still-live
    /// Inspector peer before attributing preservation to a real UI interval.
    pub fn same_registered_accounts(&self, other: &Self) -> Result<(), String> {
        self.validate(&self.epoch, self.state.package())?;
        other.validate(&self.epoch, self.state.package())?;
        if self.state != other.state { return Err("registered account comparison changed".into()); }
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn end() -> Instant { Instant::now()+std::time::Duration::from_secs(5) }
    fn wire() -> Value {
        json!({"schema":ANDROID_SCHEMA,"observer_uid":1000,"user":0,
            "target":{"package":"com.android.settings","uid":1000,"version_code":36,
              "source_paths":["/system/priv-app/Settings/Settings.apk"]},
            "authenticators":[{"type_token":"ab".repeat(32),"provider":{
              "package":"com.example.authenticator","uid":10042,"version_code":1,
              "source_paths":["/data/app/auth/base.apk"]},
              "label_id":1,"icon_id":2,"small_icon_id":0,"preferences_id":0,"custom_tokens":false}],
            "accounts":[{"account_token":"cd".repeat(32),"type_token":"ab".repeat(32),"visibility":4}],
            "samples":2,"scope":SCOPE})
    }
    fn read(v: &Value) -> Result<PackageAccountState,String> {
        parse("com.android.settings",&(v.to_string()+"\n"),end())
    }
    #[test]
    fn account_state_complete_anonymous_registry_allows_proven_empty_accounts_only() {
        let value=wire();let a=read(&value).unwrap();
        assert_eq!(a.account_count(),1);assert_eq!(a.authenticator_count(),1);
        let mut empty=value.clone();empty["accounts"]=json!([]);
        assert_eq!(read(&empty).unwrap().account_count(),0);
        empty["authenticators"]=json!([]);
        assert!(read(&empty).is_err());
        let mut invisible=value.clone();invisible["accounts"][0]["visibility"]=json!(3);
        assert_ne!(a,read(&invisible).unwrap());
        for field in ["name","type","password","access_token"] {
            let mut v=value.clone();v["accounts"][0][field]=json!("private-sentinel");
            let error=read(&v).unwrap_err();assert!(!error.contains("private-sentinel"));
        }
    }
    #[test]
    fn account_state_rejects_unknown_empty_scope_duplicate_foreign_and_unbounded_rows() {
        let base=wire();
        for(field,value)in [
            ("observer_uid",json!(2000)),("user",json!(1)),("samples",json!(1)),
            ("scope",json!("visible_accounts_only")),("accounts",Value::Null),
            ("authenticators",json!([])),("passed",json!(true)),
        ] {let mut v=base.clone();v[field]=value;assert!(read(&v).is_err());}
        for(field,value)in [
            ("account_token",json!("name@example.invalid")),
            ("type_token",json!("ef".repeat(32))),("visibility",json!(0)),
            ("visibility",json!(5)),
        ]{let mut v=base.clone();v["accounts"][0][field]=value;assert!(read(&v).is_err());}
        let mut v=base.clone();v["accounts"]=json!([v["accounts"][0].clone(),v["accounts"][0].clone()]);
        assert!(read(&v).is_err());
        let mut v=base.clone();v["authenticators"][0]["provider"]["source_paths"]=json!(["/a","/a"]);
        assert!(read(&v).is_err());
        assert!(parse("com.android.settings",&base.to_string(),end()).is_err());
        assert!(parse("com.android.settings",&(base.to_string()+"\n"),Instant::now()).is_err());
    }
    #[test]
    fn account_state_preserves_authenticator_full_code_paths_and_target_identity() {
        let base=wire();let before=read(&base).unwrap();
        for (field,value)in [
            ("uid",json!(10043)),("version_code",json!(2)),
            ("source_paths",json!(["/data/app/auth/base.apk","/data/app/auth/split.apk"]))
        ]{let mut v=base.clone();v["authenticators"][0]["provider"][field]=value;
            assert_ne!(before,read(&v).unwrap());}
        let mut v=base.clone();v["target"]["uid"]=json!(1001);
        assert_ne!(before,read(&v).unwrap());
        let mut v=base.clone();v["target"]["package"]=json!("com.example.other");
        assert!(read(&v).is_err());
        let mut v=base.clone();v["authenticators"][0]["provider"]["source_paths"]=json!(["/a/../b"]);
        assert!(read(&v).is_err());
    }
}
