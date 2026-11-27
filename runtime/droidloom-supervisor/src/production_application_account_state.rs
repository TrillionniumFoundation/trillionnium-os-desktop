//! One anonymous registered-account read using the original selected, sealed normal InputBridge JAR.
//! The actual Ready owner lends its fifteen descriptors and original absolute end.
use super::*;
use crate::application_account_state::{self, ParsedAccountState};
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use sha2::{Digest, Sha256};
use std::time::Instant;

const CLASS: &str = "com.android.droidloom.catalog.AccountState";
#[derive(Clone, Debug, Serialize)]
pub(super) struct ApplicationAccountStateRead {
    package: String,
    selected_jar_sha256: String,
}
impl<'de> Deserialize<'de> for ApplicationAccountStateRead {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> std::result::Result<Self,D::Error> {
        let raw = serde_json::Value::deserialize(deserializer)?;
        if !raw.is_object() {
            return Err(serde::de::Error::custom("account query must be a closed object"));
        }
        #[derive(Deserialize)]
        #[serde(deny_unknown_fields)]
        struct Wire { package: String, selected_jar_sha256: String }
        let wire: Wire = serde_json::from_value(raw)
            .map_err(|_| serde::de::Error::custom("account query fields differ"))?;
        Ok(Self { package: wire.package, selected_jar_sha256: wire.selected_jar_sha256 })
    }
}
impl ApplicationAccountStateRead {
    fn new(package: &str, selected_jar_sha256: String) -> Result<Self> {
        let value=Self{package:package.into(),selected_jar_sha256};
        value.validate()?;
        Ok(value)
    }
    pub(super) fn validate(&self) -> Result<()> {
        require(crate::engine_custody::selected_package(&self.package)
            && self.selected_jar_sha256.len()==64
            && self.selected_jar_sha256.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)),
            "Account requires a source-selected package and original sealed normal JAR")
    }
    pub(super) fn jar_digest(&self) -> &str { &self.selected_jar_sha256 }
    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        ["/system/bin/app_process64","-Xint","-Xusejit:false","/system/bin",CLASS,&self.package]
            .into_iter().map(|s|CString::new(s).map_err(external)).collect()
    }
}

/// Only the actual owner query can construct this internal observation.
pub(crate) struct ApplicationAccountStateObservation {
    package: String,
    epoch: RuntimeEpoch,
    parsed: ParsedAccountState,
    receipt: ReadReceipt,
}
impl ApplicationAccountStateObservation {
    pub(crate) fn package(&self) -> &str { &self.package }
    pub(crate) fn epoch(&self) -> &RuntimeEpoch { &self.epoch }
    pub(crate) fn parsed(&self) -> &ParsedAccountState { &self.parsed }
    pub(crate) fn receipt(&self) -> &ReadReceipt { &self.receipt }
    pub(crate) fn stdout_bytes(&self) -> usize { self.receipt.output_bytes }
    pub(crate) fn stdout_sha256(&self) -> &str { &self.receipt.output_sha256 }
}
pub(crate) fn read_application_account_state(
    owner: &EarlyApplicationAuthority<'_>,
    anonymity: &super::account_secret::AccountAnonymityKey,
    package: &str,
    expected_epoch: &RuntimeEpoch,
    deadline: Instant,
) -> Result<ApplicationAccountStateObservation> {
    owner.check_request_deadline().map_err(observation_authority_error)?;
    require(owner.request_deadline()==Some(deadline),
        "Account must borrow the original admitted absolute work deadline")?;
    crate::production_host_admission::check_observation_before(deadline)?;
    owner.ready().map_err(observation_authority_error)?;
    let framework=owner.observe_framework().map_err(observation_authority_error)?;
    let epoch=owner.epoch(&framework).map_err(observation_authority_error)?;
    require(&epoch==expected_epoch,"Account original framework epoch differs before dispatch")?;
    anonymity.bind_epoch(&epoch, deadline)?;
    let request=ApplicationAccountStateRead::new(
        package,owner.catalog_jar_digest().map_err(observation_authority_error)?)?;
    let files=owner.descriptors(c"app_process64").map_err(observation_authority_error)?;
    require(files.len()==12,"Account did not borrow the original fixed descriptor prefix")?;
    let(uid,gid)=owner.mapped_root().map_err(observation_authority_error)?;
    let jar=worker::executable::bind_catalog(&files[2],request.jar_digest(),uid,gid,deadline)?;
    let operation=ApplicationOperation::ApplicationAccountState{value:request.clone()};
    let result=factory_query::run_account(owner,&operation,anonymity,deadline);
    let actual=workflow::finish_effect(result,||{
        anonymity.require_epoch(&epoch, deadline)?;
        owner.ready().map_err(observation_authority_error)?;
        jar.revalidate(&files[2],request.jar_digest(),uid,gid,deadline)?;
        require(owner.catalog_jar_digest().map_err(observation_authority_error)?==request.selected_jar_sha256,
            "Account original normal JAR selection changed")?;
        require(owner.epoch(&framework).map_err(observation_authority_error)?==epoch,
            "Account query crossed the actual original framework epoch")?;
        owner.check_request_deadline().map_err(observation_authority_error)?;
        crate::production_host_admission::check_observation_before(deadline)?;
        Ok(())
    },deadline)?;
    require(actual.output.status.code()==Some(0) && actual.output.stderr.is_empty()
        && actual.stderr_bytes==0 && actual.stderr_sha256==format!("{:x}",Sha256::digest([]))
        && actual.receipt.successful_retirement()
        && actual.receipt.output_bytes==actual.output.stdout.len()
        && actual.receipt.output_sha256==format!("{:x}",Sha256::digest(&actual.output.stdout)),
        "Account actual exit, complete output, stderr or retirement differs")?;
    let text=std::str::from_utf8(&actual.output.stdout).map_err(|_|reject("Account non-UTF8 output"))?;
    let parsed=application_account_state::parse(package,text,deadline).map_err(external)?;
    owner.check_request_deadline().map_err(observation_authority_error)?;
    crate::production_host_admission::check_observation_before(deadline)?;
    Ok(ApplicationAccountStateObservation{package:package.into(),epoch,parsed,receipt:actual.receipt})
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn account_query_keeps_literal_normal_jar_and_closed_readonly_role() {
        let value=ApplicationAccountStateRead::new("com.android.settings","ab".repeat(32)).unwrap();
        let operation=ApplicationOperation::ApplicationAccountState{value};
        operation.validate().unwrap();
        assert_eq!(operation.domain(),OperationDomain::AccountRead);
        assert_eq!(operation.domain().context(),"u:r:droidloom_account_read:s0");
        assert_eq!(operation.domain().terminated(),b"u:r:droidloom_account_read:s0\0");
        assert_eq!(operation.binary(),c"app_process64");
        assert_eq!(operation.descriptor_count(),15);
        assert_eq!(operation.output_limit(),application_account_state::OUTPUT_BYTES);
        assert!(operation.uses_app_process());
        assert!(!operation.needs_content_jar());
        assert_eq!(operation.catalog_jar_digest(),Some("abababababababababababababababababababababababababababababababab"));
        let args=operation.arguments().unwrap().into_iter().map(|s|s.into_string().unwrap()).collect::<Vec<_>>();
        assert_eq!(args,["/system/bin/app_process64","-Xint","-Xusejit:false","/system/bin",CLASS,"com.android.settings"]);
        assert!(ApplicationRead::from_command(&args).is_err());
        let environment=operation.environment(QueryProjection::EarlyDev);
        assert!(environment.contains(&c"CLASSPATH=/system/system_ext/framework/droidloom-input-bridge.jar"));
        let wire=serde_json::to_string(&operation).unwrap();
        serde_json::from_str::<ApplicationOperation>(&wire).unwrap().validate().unwrap();
        for field in ["uid","user","pid","argv","classpath","domain","account","secret","stdin","passed"] {
            let mut bad:serde_json::Value=serde_json::from_str(&wire).unwrap();
            bad["value"][field]=serde_json::json!(1000);
            assert!(serde_json::from_value::<ApplicationOperation>(bad).is_err());
        }
        let mut sequence:serde_json::Value=serde_json::from_str(&wire).unwrap();
        sequence["value"]=serde_json::json!(["com.android.settings","ab".repeat(32)]);
        assert!(serde_json::from_value::<ApplicationOperation>(sequence).is_err());
        assert_eq!(operation.domain().guest_uid(),1000);
        for other in [OperationDomain::Query,OperationDomain::Browser,OperationDomain::ContactsRead,
            OperationDomain::LaunchRead,OperationDomain::LaunchStart,OperationDomain::Install,
            OperationDomain::CatalogRead,OperationDomain::AppOpsRead,OperationDomain::DisplayControl] {
            assert_eq!(other.guest_uid(),2000);
        }
        for(package,sha)in [("com.example.other","ab".repeat(32)),("com.android.settings","ab".repeat(31))]{
            assert!(ApplicationAccountStateRead::new(package,sha).is_err());
        }
    }
}
