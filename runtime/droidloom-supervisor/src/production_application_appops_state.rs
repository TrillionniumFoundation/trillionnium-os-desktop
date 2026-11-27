//! One scoped AppOps read using the original selected, sealed normal InputBridge JAR.
//! The actual Ready owner lends its fifteen descriptors and original absolute end.
use super::*;
use crate::application_appops_state::{self, ParsedAppOpsState};
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use sha2::{Digest, Sha256};
use std::time::Instant;

const CLASS: &str = "com.android.droidloom.catalog.ApplicationAppOpsState";
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct ApplicationAppOpsStateRead {
    package: String,
    selected_jar_sha256: String,
}
impl ApplicationAppOpsStateRead {
    fn new(package: &str, selected_jar_sha256: String) -> Result<Self> {
        let value=Self{package:package.into(),selected_jar_sha256};
        value.validate()?;
        Ok(value)
    }
    pub(super) fn validate(&self) -> Result<()> {
        require(crate::engine_custody::selected_package(&self.package)
            && self.selected_jar_sha256.len()==64
            && self.selected_jar_sha256.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)),
            "AppOps requires a source-selected package and original sealed normal JAR")
    }
    pub(super) fn jar_digest(&self) -> &str { &self.selected_jar_sha256 }
    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        ["/system/bin/app_process64","-Xint","-Xusejit:false","/system/bin",CLASS,&self.package]
            .into_iter().map(|s|CString::new(s).map_err(external)).collect()
    }
}

/// Only the actual owner query can construct this internal observation.
pub(crate) struct ApplicationAppOpsStateObservation {
    package: String,
    epoch: RuntimeEpoch,
    parsed: ParsedAppOpsState,
    receipt: ReadReceipt,
}
impl ApplicationAppOpsStateObservation {
    pub(crate) fn package(&self) -> &str { &self.package }
    pub(crate) fn epoch(&self) -> &RuntimeEpoch { &self.epoch }
    pub(crate) fn parsed(&self) -> &ParsedAppOpsState { &self.parsed }
    pub(crate) fn receipt(&self) -> &ReadReceipt { &self.receipt }
    pub(crate) fn stdout_bytes(&self) -> usize { self.receipt.output_bytes }
    pub(crate) fn stdout_sha256(&self) -> &str { &self.receipt.output_sha256 }
}
pub(crate) fn read_application_appops_state(
    owner: &EarlyApplicationAuthority<'_>,
    package: &str,
    expected_epoch: &RuntimeEpoch,
    deadline: Instant,
) -> Result<ApplicationAppOpsStateObservation> {
    owner.check_request_deadline().map_err(observation_authority_error)?;
    require(owner.request_deadline()==Some(deadline),
        "AppOps must borrow the original admitted absolute work deadline")?;
    crate::production_host_admission::check_observation_before(deadline)?;
    owner.ready().map_err(observation_authority_error)?;
    let framework=owner.observe_framework().map_err(observation_authority_error)?;
    let epoch=owner.epoch(&framework).map_err(observation_authority_error)?;
    require(&epoch==expected_epoch,"AppOps original framework epoch differs before dispatch")?;
    let request=ApplicationAppOpsStateRead::new(
        package,owner.catalog_jar_digest().map_err(observation_authority_error)?)?;
    let files=owner.descriptors(c"app_process64").map_err(observation_authority_error)?;
    require(files.len()==12,"AppOps did not borrow the original fixed descriptor prefix")?;
    let(uid,gid)=owner.mapped_root().map_err(observation_authority_error)?;
    let jar=worker::executable::bind_catalog(&files[2],request.jar_digest(),uid,gid,deadline)?;
    let operation=ApplicationOperation::ApplicationAppOpsState{value:request.clone()};
    let result=factory_query::run(owner,&operation,deadline);
    let actual=workflow::finish_effect(result,||{
        owner.ready().map_err(observation_authority_error)?;
        jar.revalidate(&files[2],request.jar_digest(),uid,gid,deadline)?;
        require(owner.catalog_jar_digest().map_err(observation_authority_error)?==request.selected_jar_sha256,
            "AppOps original normal JAR selection changed")?;
        require(owner.epoch(&framework).map_err(observation_authority_error)?==epoch,
            "AppOps query crossed the actual original framework epoch")?;
        owner.check_request_deadline().map_err(observation_authority_error)?;
        crate::production_host_admission::check_observation_before(deadline)?;
        Ok(())
    },deadline)?;
    require(actual.output.status.code()==Some(0) && actual.output.stderr.is_empty()
        && actual.stderr_bytes==0 && actual.stderr_sha256==format!("{:x}",Sha256::digest([]))
        && actual.receipt.successful_retirement()
        && actual.receipt.output_bytes==actual.output.stdout.len()
        && actual.receipt.output_sha256==format!("{:x}",Sha256::digest(&actual.output.stdout)),
        "AppOps actual exit, complete output, stderr or retirement differs")?;
    let text=std::str::from_utf8(&actual.output.stdout).map_err(|_|reject("AppOps non-UTF8 output"))?;
    let parsed=application_appops_state::parse(package,text,deadline).map_err(external)?;
    owner.check_request_deadline().map_err(observation_authority_error)?;
    crate::production_host_admission::check_observation_before(deadline)?;
    Ok(ApplicationAppOpsStateObservation{package:package.into(),epoch,parsed,receipt:actual.receipt})
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn appops_query_keeps_literal_normal_jar_and_closed_readonly_role() {
        let value=ApplicationAppOpsStateRead::new("com.android.settings","ab".repeat(32)).unwrap();
        let operation=ApplicationOperation::ApplicationAppOpsState{value};
        operation.validate().unwrap();
        assert_eq!(operation.domain(),OperationDomain::AppOpsRead);
        assert_eq!(operation.domain().context(),"u:r:droidloom_appops_read:s0");
        assert_eq!(operation.domain().terminated(),b"u:r:droidloom_appops_read:s0\0");
        assert_eq!(operation.binary(),c"app_process64");
        assert_eq!(operation.descriptor_count(),15);
        assert_eq!(operation.output_limit(),application_appops_state::OUTPUT_BYTES);
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
        for field in ["uid","user","pid","argv","classpath","domain","account","passed"] {
            let mut bad:serde_json::Value=serde_json::from_str(&wire).unwrap();
            bad["value"][field]=serde_json::json!(1000);
            assert!(serde_json::from_value::<ApplicationOperation>(bad).is_err());
        }
        for(package,sha)in [("com.example.other","ab".repeat(32)),("com.android.settings","ab".repeat(31))]{
            assert!(ApplicationAppOpsStateRead::new(package,sha).is_err());
        }
    }
}
