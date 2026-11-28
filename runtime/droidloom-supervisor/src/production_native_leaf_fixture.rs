//! The original factory owns every late-born Documents/Gallery installation.
//! The opaque lease records the actually absent all-user package, complete
//! user-0 preimage, real normal installation, and fresh UID. It is deliberately
//! not deserializable. Only this same lease can retire the newly born helper.
use super::*;
use crate::native_leaf_fixture::{self as wire, FixtureAction, FixtureCommandComparison, FixtureStateComparison, NativeFixtureReply, NativeFixtureRequest};
use crate::native_leaf_fixture_material::{NativeLeafFixtureKind as Kind, NativeLeafFixtureMaterial};
use crate::package_inventory_observation::UserZeroPackageInventoryFacts;
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use std::{os::unix::fs::FileExt, time::{Duration,Instant}};

/// Private same-image factory command. The public application transport does
/// not accept this enum, and no arbitrary package/path/argv can be represented.
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[serde(tag="fixture", deny_unknown_fields)]
pub(super) enum FixtureCommand {
    RetainedPackage { kind: Kind },
    RetireOwned { kind: Kind },
    State { kind: Kind },
}
impl FixtureCommand {
    pub(super) fn validate(&self) -> Result<()> { Ok(()) }
    pub(super) fn removes(&self) -> bool { matches!(self,Self::RetireOwned{..}) }
    pub(super) fn state(&self) -> bool { matches!(self,Self::State{..}) }
    pub(super) fn limit(&self) -> Duration { if self.state() {wire::STATE_LIMIT} else if self.removes() { wire::REMOVE_LIMIT } else { wire::ABSENCE_LIMIT } }
    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        if let Self::State{kind}=self {
            let values=vec!["/system/bin/app_process64".into(),"-Xint".into(),"-Xusejit:false".into(),
                "/system/bin".into(),"com.android.commands.content.Content".into(),"call".into(),
                "--uri".into(),format!("content://{}.state",kind.package()),"--method".into(),"state".into(),
                "--user".into(),"0".into()];
            return values.into_iter().map(|v:String|CString::new(v).map_err(external)).collect();
        }
        let (kind, mut argv) = match self {
            Self::RetainedPackage{kind} => (*kind,vec!["/system/bin/cmd","package","list","packages","-u","-U","--user","all"]),
            // A complete uninstall is reachable only after the live lease has
            // checked that this package was absent for every user and remains
            // the one exact user-0 installation made by this source invocation.
            Self::RetireOwned{kind} => (*kind,vec!["/system/bin/cmd","package","uninstall"]),
            Self::State{..}=>return Err(reject("state command is not a package command")),
        };
        argv.push(kind.package()); argv.into_iter().map(|v|CString::new(v).map_err(external)).collect()
    }
}
pub(crate) fn fixture_state_execution_profile()->PreparationReadExecutionProfile {
    let input=crate::production_execution_profile::query_inputs::INPUTS[2];
    PreparationReadExecutionProfile {process_selinux:OperationDomain::FixtureState.context(),
        process_apparmor:"droidloom-production-android (enforce)",executable_selinux:"u:object_r:droidloom_provider_exec:s0",
        executable_bytes:input.bytes,executable_sha256:input.sha256,guest_uid:2000}
}
fn current_main(owner: &EarlyApplicationAuthority<'_>, request: &NativeFixtureRequest, end: Instant) -> Result<crate::main_custody::RuntimeMainCustody> {
    owner.check_request_deadline().map_err(observation_authority_error)?;
    require(owner.request_deadline()==Some(end),"fixture operation lost its original admitted absolute end")?;
    let main=owner.observe_main_custody(&request.main().epoch,end).map_err(observation_authority_error)?;
    require(main==*request.main(),"fixture actual Main differs from its held original business owner")?;
    Ok(main)
}
fn inventory(owner: &EarlyApplicationAuthority<'_>, request: &NativeFixtureRequest, end: Instant) -> Result<UserZeroPackageInventoryFacts> {
    let actual=read_user_zero_package_inventory(owner,end)?;
    UserZeroPackageInventoryFacts::from_actual(&actual,&request.main().epoch).map_err(external)
}
fn retained(owner: &EarlyApplicationAuthority<'_>, kind: Kind, expected: &[u8], end: Instant) -> Result<FixtureCommandComparison> {
    let actual=factory_query::run(owner,&ApplicationOperation::NativeFixture{value:FixtureCommand::RetainedPackage{kind}},end)?;
    let out=FixtureCommandComparison::from_actual(&actual.output,&actual.receipt).map_err(external)?;
    out.require_output(false,expected).map_err(external)?; Ok(out)
}
fn payload_kind(kind: Kind) -> working_payload::WorkingPayloadKind {
    use working_payload::WorkingPayloadKind as P;
    match kind {Kind::DocumentsSaf=>P::DocumentsSaf,Kind::DocumentsFeatures=>P::DocumentsFeatures,
        Kind::GalleryRotation=>P::GalleryRotation,Kind::GalleryVideo=>P::GalleryVideo}
}

/// Actual source FD custody and actual create-only installation are retained
/// together. A reply JSON, request hash, package name, or UID cannot construct
/// this type. An uncertain mutation permanently blocks its retirement path.
pub(crate) struct NativeFixtureLease {
    material: NativeLeafFixtureMaterial,
    begin: NativeFixtureReply,
    retention_end: Instant,
    failed: Option<String>,
    retired: bool,
}
impl NativeFixtureLease {
    pub(crate) fn begin_reply(&self) -> &NativeFixtureReply { &self.begin }
    pub(crate) fn guard_source(&self,end:Instant) -> Result<()> {
        require(!self.retired && self.failed.is_none(),"fixture lease has retired or an unresolved original failure")?;
        require(end<=self.retention_end && Instant::now()<end,"fixture lease original lifetime elapsed")?;
        self.material.guard(end).map_err(external)
    }
    pub(crate) fn continue_with(&mut self, owner:&EarlyApplicationAuthority<'_>, request:NativeFixtureRequest,end:Instant) -> Result<NativeFixtureReply> {
        let result=self.perform(owner,request,end);
        if let Err(error)=&result {if self.failed.is_none(){self.failed=Some(error.to_string());}}
        result
    }
    fn perform(&mut self, owner:&EarlyApplicationAuthority<'_>, request:NativeFixtureRequest,end:Instant) -> Result<NativeFixtureReply> {
        request.matches_begin(self.begin.request()).map_err(external)?;
        self.guard_source(end)?;
        let kind=request.kind().map_err(external)?;
        let before_main=current_main(owner,&request,end)?;
        let before_inventory=inventory(owner,&request,end)?;
        require(before_inventory.same_table(self.begin.after_inventory()),"complete fixture package/UID table changed before continuation")?;
        let helper=inspect_early_before(owner,kind.package(),0,end)?;
        wire::helper(kind,request.main(),&helper).map_err(external)?;
        require(helper==*self.begin.helper(),"fixed late-born helper was replaced before its lease continuation")?;
        let line=format!("package:{} uid:{}\n",kind.package(),helper.uid);
        let retained_before=retained(owner,kind,line.as_bytes(),end)?;
        self.guard_source(end)?;
        let state=if request.action()==FixtureAction::State {
            let actual=factory_query::run(owner,&ApplicationOperation::NativeFixture{value:FixtureCommand::State{kind}},end)?;
            let command=FixtureStateComparison::from_actual(&actual.output,&actual.receipt).map_err(external)?;
            wire::parse_state(&actual.output.stdout,kind,helper.uid).map_err(external)?;
            Some(command)
        }else{None};
        let (retirement,retained_after)=if request.action()==FixtureAction::Retire {
            // The only delete-capable operation in this module is downstream
            // of the complete live lease and actual original PM checks above.
            // There is no -k, clear-data, replace, or retry branch.
            let actual=factory_query::run(owner,&ApplicationOperation::NativeFixture{value:FixtureCommand::RetireOwned{kind}},end)?;
            let command=FixtureCommandComparison::from_actual(&actual.output,&actual.receipt).map_err(external)?;
            command.require_output(true,b"Success\n").map_err(external)?;
            (Some(command),Some(retained(owner,kind,b"",end)?))
        } else {(None,None)};
        let after_inventory=inventory(owner,&request,end)?;
        let after_main=current_main(owner,&request,end)?;
        self.guard_source(end)?;
        let reply=NativeFixtureReply::actual(request,before_main,after_main,before_inventory,after_inventory,
            helper,retained_before,retained_after,self.begin.installation().clone(),self.begin.creator().clone(),retirement,state);
        reply.validate(reply.request(),Some(&self.begin)).map_err(external)?;
        owner.check_request_deadline().map_err(observation_authority_error)?;
        if reply.request().action()==FixtureAction::Retire {self.retired=true;}
        Ok(reply)
    }
}

pub(crate) fn begin_native_fixture(owner:&EarlyApplicationAuthority<'_>,request:NativeFixtureRequest,end:Instant) -> Result<NativeFixtureLease> {
    request.validate().map_err(external)?;
    require(request.action()==FixtureAction::Begin,"a new fixture requires the source begin action")?;
    let kind=request.kind().map_err(external)?;
    let retention_end=request.retention_end().map_err(external)?;
    let before_main=current_main(owner,&request,end)?;
    let material=NativeLeafFixtureMaterial::capture_before(kind,retention_end,end).map_err(external)?;
    let before_inventory=inventory(owner,&request,end)?;
    require(before_inventory.records().get(request.primary().package.as_str())==Some(&request.primary().uid),
        "fixture original selected application UID changed")?;
    require(!before_inventory.records().contains_key(kind.package()),"fixed fixture already exists; automatic replacement or retry is forbidden")?;
    let retained_before=retained(owner,kind,b"",end)?;
    let created=working_payload::create(payload_kind(kind),end)?;
    let payload=created.payload_file(end)?.try_clone()?;
    crate::control::apk_payload::validate(&payload,&[kind.apk_bytes()]).map_err(external)?;
    crate::control::apk_payload::validate_production_context(&payload).map_err(external)?;
    let mut raw=vec![0;kind.apk_bytes() as usize];payload.read_exact_at(&mut raw,0)?;
    require(wire::hash(&raw)==kind.apk_sha256() && payload.read_at(&mut[0],kind.apk_bytes())?==0,
        "fixed helper payload complete bytes differ")?;
    material.guard(end).map_err(external)?;created.guard(end)?;
    // All four variants use the existing source-owned normal streaming
    // installer, with its unchanged 110-second per-command limit and -R.
    let installation=install_create_only_early(owner,payload,&[kind.apk_bytes()],end)?;
    let helper=inspect_early_before(owner,kind.package(),0,end)?;
    wire::helper(kind,request.main(),&helper).map_err(external)?;
    let after_inventory=inventory(owner,&request,end)?;
    require(wire::one_helper(kind,&before_inventory,&after_inventory).map_err(external)?==helper.uid,
        "normal fixture installation did not create exactly its own fresh UID")?;
    let after_main=current_main(owner,&request,end)?;
    material.guard(end).map_err(external)?;created.guard(end)?;
    let begin=NativeFixtureReply::actual(request,before_main,after_main,before_inventory,after_inventory,helper,
        retained_before,None,serde_json::to_value(&installation).map_err(external)?,created.comparison(),None,None);
    begin.validate(begin.request(),None).map_err(external)?;
    owner.check_request_deadline().map_err(observation_authority_error)?;
    Ok(NativeFixtureLease{material,begin,retention_end,failed:None,retired:false})
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn four_fixture_creators_are_fixed_and_retirement_has_no_package_or_keep_data_argument() {
        for kind in [Kind::DocumentsSaf,Kind::DocumentsFeatures,Kind::GalleryRotation,Kind::GalleryVideo] {
            assert_ne!(payload_kind(kind),working_payload::WorkingPayloadKind::Ihg);
            let retained=FixtureCommand::RetainedPackage{kind}; retained.validate().unwrap();
            let args=retained.arguments().unwrap();
            assert_eq!(args.iter().map(|v|v.to_str().unwrap()).collect::<Vec<_>>(),
                vec!["/system/bin/cmd","package","list","packages","-u","-U","--user","all",kind.package()]);
            let remove=FixtureCommand::RetireOwned{kind};
            assert_eq!(remove.arguments().unwrap().iter().map(|v|v.to_str().unwrap()).collect::<Vec<_>>(),
                vec!["/system/bin/cmd","package","uninstall",kind.package()]);
            assert_eq!(remove.limit(),Duration::from_secs(110));
            let state=FixtureCommand::State{kind};
            assert_eq!(state.limit(),Duration::from_secs(15));
            assert_eq!(state.arguments().unwrap().iter().map(|v|v.to_str().unwrap().to_owned()).collect::<Vec<_>>(),
                vec!["/system/bin/app_process64".to_owned(),"-Xint".into(),"-Xusejit:false".into(),
                    "/system/bin".into(),"com.android.commands.content.Content".into(),"call".into(),
                    "--uri".into(),format!("content://{}.state",kind.package()),"--method".into(),
                    "state".into(),"--user".into(),"0".into()]);
            let mut extra=serde_json::to_value(state).unwrap();extra["uri"]="content://foreign/selected".into();
            assert!(serde_json::from_value::<FixtureCommand>(extra).is_err());
            let mut v=serde_json::to_value(remove).unwrap();v["package"]="com.sankuai.meituan.takeoutnew".into();
            assert!(serde_json::from_value::<FixtureCommand>(v).is_err());
        }
    }
}
