//! Fixed IHG helper preparation through the existing original factory.
//! Installation consumes a validated readonly payload and the source-fixed
//! normal bundle; state instrumentation is a separate closed guest operation.
use super::*;
use crate::native_ihg_helper::{
    self as wire, IhgInstallRequest,IhgInstallReply,IhgStateRequest,IhgStateReply,CommandComparison,
};
use crate::package_inventory_observation::UserZeroPackageInventoryFacts;
use crate::prebuilt_native_helpers::PrebuiltIhgMaterial;
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use crate::production_execution_profile::query_inputs as fixed;
use std::{os::unix::fs::FileExt,time::{Duration,Instant}};

#[derive(Clone,Debug,Serialize,Deserialize)]
#[serde(tag="ihg_read",deny_unknown_fields)]
pub(super) enum IhgRead {
    RetainedAbsence {},
    State { request:IhgStateRequest },
}
impl IhgRead {
    pub(super) fn validate(&self)->Result<()> {
        match self {Self::RetainedAbsence{}=>Ok(()),Self::State{request}=>request.validate().map_err(external)}
    }
    pub(super) fn state(&self)->bool {matches!(self,Self::State{..})}
    pub(super) fn limit(&self)->Duration {if self.state(){wire::STATE_LIMIT}else{wire::ABSENCE_LIMIT}}
    pub(super) fn arguments(&self)->Result<Vec<CString>> {
        self.validate()?;
        let values=match self {
            Self::RetainedAbsence{}=>vec!["/system/bin/cmd".into(),"package".into(),"list".into(),
                "packages".into(),"-u".into(),"-U".into(),"--user".into(),"all".into(),wire::HELPER.into()],
            Self::State{request}=>{
                let logical=request.logical_arguments().map_err(external)?;
                let mut values=vec!["/system/bin/app_process64".into(),"-Xint".into(),"-Xusejit:false".into(),
                    "/system/bin".into(),"com.android.commands.am.Am".into()];
                values.extend(logical.into_iter().skip(1));values
            }
        };
        values.into_iter().map(|v|CString::new(v).map_err(external)).collect()
    }
}
pub(crate) fn ihg_helper_execution_profile(state:bool)->PreparationReadExecutionProfile {
    let input=fixed::INPUTS[if state{2}else{0}];
    PreparationReadExecutionProfile {
        process_selinux:if state{OperationDomain::IhgInstrument.context()}else{OperationDomain::Query.context()},
        process_apparmor:"droidloom-production-android (enforce)",
        executable_selinux:if state{"u:object_r:droidloom_provider_exec:s0"}else{"u:object_r:droidloom_query_exec:s0"},
        executable_bytes:input.bytes,executable_sha256:input.sha256,guest_uid:2000,
    }
}
fn current_main(owner:&EarlyApplicationAuthority<'_>,request:&crate::main_custody::RuntimeMainCustody,end:Instant)
    ->Result<crate::main_custody::RuntimeMainCustody>
{
    owner.check_request_deadline().map_err(observation_authority_error)?;
    require(owner.request_deadline()==Some(end),"IHG original admitted absolute end differs")?;
    let actual=owner.observe_main_custody(&request.epoch,end).map_err(observation_authority_error)?;
    require(actual==*request,"IHG actual Main differs from the fixed preparation observation")?;
    Ok(actual)
}
fn inventory(owner:&EarlyApplicationAuthority<'_>,epoch:&RuntimeEpoch,end:Instant)->Result<UserZeroPackageInventoryFacts> {
    let actual=read_user_zero_package_inventory(owner,end)?;
    UserZeroPackageInventoryFacts::from_actual(&actual,epoch).map_err(external)
}
pub(crate) fn install_ihg_helper(
    owner:&EarlyApplicationAuthority<'_>,request:IhgInstallRequest,end:Instant,
)->Result<IhgInstallReply> {
    request.validate().map_err(external)?;
    let before_main=current_main(owner,request.main(),end)?;
    let material=PrebuiltIhgMaterial::capture(end).map_err(external)?;
    let created=working_payload::create(working_payload::WorkingPayloadKind::Ihg,end)?;
    let payload=created.payload_file(end)?.try_clone()?;
    crate::control::apk_payload::validate(&payload,&[wire::APK_BYTES]).map_err(external)?;
    crate::control::apk_payload::validate_production_context(&payload).map_err(external)?;
    let mut raw=vec![0u8;wire::APK_BYTES as usize];payload.read_exact_at(&mut raw,0)?;
    require(wire::hash(&raw)==wire::APK_SHA256&&material.apk_sha256()==wire::APK_SHA256
        &&material.apk_bytes()==wire::APK_BYTES,"IHG payload is not the fixed complete normal helper")?;
    material.guard(end).map_err(external)?;
    let before_inventory=inventory(owner,&request.main().epoch,end)?;
    require(before_inventory.same_table(request.before_inventory()),"IHG complete actual preinstall table changed")?;
    require(!before_inventory.records().contains_key(wire::HELPER),"IHG helper already installed; no automatic retry")?;
    let absence=factory_query::run(owner,&ApplicationOperation::IhgRead{value:IhgRead::RetainedAbsence{}},end)?;
    require(absence.output.status.success()&&absence.output.stdout.is_empty()&&absence.output.stderr.is_empty()
        &&absence.receipt.successful_retirement(),"IHG all-user retained package absence was not actually observed")?;
    let absence=CommandComparison::from_actual(&absence.output,&absence.receipt).map_err(external)?;
    crate::control::apk_payload::validate(&payload,&[wire::APK_BYTES]).map_err(external)?;
    material.guard(end).map_err(external)?;
    // The original factory retains every create/write/commit receipt and makes
    // no automatic retry. A failed/uncertain commit is never relabeled absent.
    created.guard(end)?;
    let installed=install_create_only_early(owner,payload,&[wire::APK_BYTES],end);
    let after_main=current_main(owner,request.main(),end);
    let after_inventory=inventory(owner,&request.main().epoch,end);
    if matches!(&installed,Err(ApplicationError::RetirementUnproven))
        ||matches!(&after_main,Err(ApplicationError::RetirementUnproven))
        ||matches!(&after_inventory,Err(ApplicationError::RetirementUnproven)) {
        return Err(ApplicationError::RetirementUnproven);
    }
    let installed=installed?;let after_main=after_main?;let after_inventory=after_inventory?;
    wire::one_helper(&before_inventory,&after_inventory).map_err(external)?;
    material.guard(end).map_err(external)?;
    owner.check_request_deadline().map_err(observation_authority_error)?;
    created.guard(end)?;
    IhgInstallReply::from_actual(request,before_main,after_main,before_inventory,after_inventory,absence,&installed,&created).map_err(external)
}
pub(crate) fn observe_ihg_helper_state(
    owner:&EarlyApplicationAuthority<'_>,request:IhgStateRequest,end:Instant,
)->Result<IhgStateReply> {
    request.validate().map_err(external)?;
    let before_main=current_main(owner,request.main(),end)?;
    let actual=factory_query::run(owner,&ApplicationOperation::IhgRead{value:IhgRead::State{request:request.clone()}},end);
    let after=current_main(owner,request.main(),end);
    if matches!(&actual,Err(ApplicationError::RetirementUnproven))||matches!(&after,Err(ApplicationError::RetirementUnproven)) {
        return Err(ApplicationError::RetirementUnproven)
    }
    let actual=actual?;let after_main=after?;
    require(actual.operation_deadline<=end&&actual.receipt.cgroup_removed
        &&matches!(&actual.receipt.lifecycle,ReadLifecycle::InstanceFactory{release_acknowledged:true,..})
        &&actual.receipt.output_bytes==actual.output.stdout.len()
        &&actual.receipt.output_sha256==wire::hash(&actual.output.stdout)
        &&actual.stderr_bytes==actual.output.stderr.len()&&actual.stderr_sha256==wire::hash(&actual.output.stderr),
        "IHG state did not actually retire with complete captured output")?;
    let command=CommandComparison::from_actual(&actual.output,&actual.receipt).map_err(external)?;
    IhgStateReply::from_actual(request,before_main,after_main,command).map_err(external)
}
