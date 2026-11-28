//! Normal owner observations surrounding the separate live APK reader.
//! Fresh PM metadata chooses the paths; caller PM/Main values only compare.
use super::*;
use super::apk_protocol::Begin;
use super::apk_reader::Reader;
use crate::control::application_probe::{AndroidProbe,ApplicationMetadata};
use crate::production_selection::early_generation::{EarlyApplicationAuthority,EarlyFrameworkObservation};
use std::time::Instant;


/// Private normal-worker I/P/L command. Scope and ordinal select the literal
/// package; no package/path/UID/argv supplied by the leaf enters this wire.
#[derive(Clone,Debug,serde::Serialize,serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct NativeLeafPackageRead {
    scope:super::apk_scope::Scope,
    kind:super::apk_protocol::PackageReadKind,
    ordinal:u8,
}
impl NativeLeafPackageRead {
    pub(super) fn validate(&self)->Result<()>{
        self.scope.validate().map_err(external)?;
        super::apk_protocol::PackageReadKind::require_role(self.scope,self.ordinal).map_err(external)
    }
    pub(super) fn arguments(&self)->Result<Vec<CString>>{
        self.validate()?;
        let role=self.scope.roles()[self.ordinal as usize];
        self.kind.literal_arguments(role.package)
            .map_err(external)?.into_iter()
            .map(|value|CString::new(value).map_err(|_|reject("NUL in fixed APK package input")))
            .collect()
    }
    pub(super) fn domain(&self)->OperationDomain{
        match self.kind{
            super::apk_protocol::PackageReadKind::Launcher=>OperationDomain::LaunchRead,
            _=>OperationDomain::Query,
        }
    }
}
fn package_operation(scope:super::apk_scope::Scope,kind:super::apk_protocol::PackageReadKind,
    ordinal:u8)->Result<ApplicationOperation>
{
    use super::apk_protocol::PackageReadKind;
    scope.validate().map_err(external)?;
    PackageReadKind::require_role(scope,ordinal).map_err(external)?;
    let operation=ApplicationOperation::NativeLeafPackage{
        value:NativeLeafPackageRead{scope,kind,ordinal}};
    operation.validate()?;
    Ok(operation)
}

/// Source-fixed executable/domain comparisons for I/P/L. The actual factory
/// still owns TRACEEXEC/PIDFD/retirement; this function creates no observation.
pub(crate) fn package_execution_profile(kind:super::apk_protocol::PackageReadKind)
    ->super::NativeUiExecutionProfile
{
    let domain=match kind{
        super::apk_protocol::PackageReadKind::Launcher=>OperationDomain::LaunchRead,
        _=>OperationDomain::Query,
    };
    let input=crate::production_execution_profile::query_inputs::INPUTS[0];
    super::NativeUiExecutionProfile{
        process_selinux:domain.context(),
        process_apparmor:"droidloom-production-android (enforce)",
        executable_selinux:"u:object_r:droidloom_query_exec:s0",
        executable_bytes:input.bytes,
        executable_sha256:input.sha256,
        guest_uid:domain.guest_uid(),
    }
}

fn protocol_before(begin:&Begin)->Result<bool>{
    Ok(super::apk_protocol::monotonic_ns().map_err(external)? < begin.deadline_ns())
}
struct Probe<'a,'owner> {
    owner:&'a EarlyApplicationAuthority<'owner>,
    framework:EarlyFrameworkObservation,
    end:Instant,
    reads:Vec<ReadReceipt>,
    outputs:Vec<String>,
    failure:Option<ApplicationError>,
}
impl Probe<'_,'_> {
    fn retain<T>(&mut self,value:Result<T>)->std::result::Result<T,String>{
        value.map_err(|error|{
            let text=error.to_string();
            if self.failure.is_none() || matches!(&error,ApplicationError::RetirementUnproven){self.failure=Some(error);}
            text
        })
    }
}
impl AndroidProbe for Probe<'_,'_> {
    fn epoch(&mut self)->std::result::Result<RuntimeEpoch,String>{
        let result=(||{
            crate::production_host_admission::check_observation_before(self.end)?;
            self.owner.epoch(&self.framework).map_err(observation_authority_error)
        })();
        self.retain(result)
    }
    fn command(&mut self,args:&[String])->std::result::Result<String,String>{
        let result=(||{
            crate::production_host_admission::check_observation_before(self.end)?;
            require(self.reads.len()<2,"APK metadata query count")?;
            self.owner.epoch(&self.framework).map_err(observation_authority_error)?;
            let query=ApplicationRead::from_command(args)?;
            require(matches!(&query,ApplicationRead::PackageIdentity{..}|ApplicationRead::PackagePaths{..}),
                "APK owner only reads fixed PM identity and paths")?;
            let read=run_read_before(self.owner,&query,self.end)?;
            require(read.receipt.successful_retirement() && read.receipt.cgroup_removed
                && read.receipt.query_waitid_code==libc::CLD_EXITED && read.receipt.query_waitid_status==0,
                "APK PM metadata has no actual complete retirement")?;
            self.owner.epoch(&self.framework).map_err(observation_authority_error)?;
            self.outputs.push(read.output.clone());
            self.reads.push(read.receipt);
            Ok(read.output)
        })();
        self.retain(result)
    }
}
fn metadata(owner:&EarlyApplicationAuthority<'_>,begin:&Begin,index:usize,end:Instant)
    ->Result<(ApplicationMetadata,Vec<super::apk_protocol::MetadataRead>)>
{
    require(owner.request_deadline()==Some(end),"APK metadata must use the original admitted observation end")?;
    let roles=begin.scope().roles();
    let role=roles.get(index).ok_or_else(||reject("APK metadata role index differs"))?;
    let mut probe=Probe{owner,framework:owner.observe_framework().map_err(observation_authority_error)?,
        end,reads:Vec::new(),outputs:Vec::new(),failure:None};
    let read=crate::control::application_probe::inspect_metadata(&mut probe,role.package,0);
    if let Some(error)=probe.failure.take(){return Err(error);}
    let actual=read.map_err(external)?;
    require(probe.reads.len()==2 && actual.package==role.package && actual.user==0
        && actual.uid<100_000 && actual.version_code>0 && actual.epoch==begin.main().epoch
        && !actual.apks.is_empty() && actual.apks.len()<=role.max_apks,
        "APK actual complete fixed-role PM metadata differs")?;
    if index==0 {
        require(actual.matches_inspection(begin.application()),
            "APK actual primary PM differs from its borrowed opaque observation")?;
    }
    owner.check_request_deadline().map_err(observation_authority_error)?;
    let reads=probe.outputs.into_iter().zip(probe.reads).map(|(stdout,receipt)|{
        serde_json::to_value(receipt).map(|receipt|super::apk_protocol::MetadataRead{stdout,receipt})
    }).collect::<std::result::Result<Vec<_>,_>>().map_err(external)?;
    require(super::apk_protocol::compare_metadata_reads(&reads,&actual).map_err(external)?==actual,
        "APK actual PM output/read receipt comparison differs")?;
    Ok((actual,reads))
}

/// One role per broker poll. Each call retains the original normal 70-second
/// PM/Main cap, while the session also holds the whole group's original end.
pub(crate) fn observe_begin(owner:&EarlyApplicationAuthority<'_>,begin:&Begin,index:usize,end:Instant)
    ->Result<super::apk_protocol::Bookend>
{
    begin.validate().map_err(external)?;
    require(protocol_before(begin)? && owner.request_deadline()==Some(end),
        "APK begin must borrow the admitted original end")?;
    let main=owner.observe_main_custody(&begin.main().epoch,end).map_err(observation_authority_error)?;
    require(&main==begin.main(),"APK begin actual Main differs")?;
    let (metadata,reads)=metadata(owner,begin,index,end)?;
    Ok(super::apk_protocol::Bookend{main,metadata,reads})
}
pub(crate) fn spawn(owner:&EarlyApplicationAuthority<'_>,begin:&Begin,
    before:&[super::apk_protocol::Bookend],nonce:[u8;16],end:Instant)->Result<Reader>
{
    require(before.len()==begin.scope().roles().len() && owner.request_deadline()==Some(end),
        "APK actual group observations are incomplete")?;
    let inputs=owner.native_leaf_apk_inputs(begin.main()).map_err(observation_authority_error)?;
    let mut reader=Reader::spawn(begin.clone(),before.iter().map(|v|v.metadata.clone()).collect(),inputs,nonce)?;
    if let Err(error)=owner.revalidate().map_err(observation_authority_error){
        reader.retire()?;
        return Err(error);
    }
    Ok(reader)
}
/// Called only after the reader's actual full-group hash, while every original
/// APK FD is still held. One role is re-observed per admitted owner call.
pub(crate) fn observe_finish(owner:&EarlyApplicationAuthority<'_>,begin:&Begin,
    packages:&[super::apk_protocol::PackageFiles],index:usize,end:Instant)
    ->Result<super::apk_protocol::Bookend>
{
    require(owner.request_deadline()==Some(end) && protocol_before(begin)?,
        "APK final bookends cannot restart the original deadline")?;
    let (metadata,reads)=metadata(owner,begin,index,end)?;
    let expected=packages.get(index).ok_or_else(||reject("APK actual final role absent"))?;
    require(metadata.matches_inspection(&expected.application),"APK final actual role PM differs")?;
    let main=owner.observe_main_custody(&begin.main().epoch,end).map_err(observation_authority_error)?;
    require(&main==begin.main(),"APK final actual Main differs")?;
    owner.check_request_deadline().map_err(observation_authority_error)?;
    Ok(super::apk_protocol::Bookend{main,metadata,reads})
}


/// Created only by one real normal Query factory call. This is not a wire
/// constructor and cannot be supplied by the private host child.
pub(crate) struct FixedPackageObservation {
    comparison:super::apk_protocol::PackageReadComparison,
}
impl FixedPackageObservation {
    pub(crate) fn comparison(&self)->&super::apk_protocol::PackageReadComparison{&self.comparison}
}
pub(crate) fn read_package(owner:&EarlyApplicationAuthority<'_>,begin:&Begin,
    packages:&[super::apk_protocol::PackageFiles],kind:super::apk_protocol::PackageReadKind,
    ordinal:u8,end:Instant)->Result<FixedPackageObservation>
{
    use super::apk_protocol as p;
    use sha2::{Digest,Sha256};
    require(owner.request_deadline()==Some(end) && protocol_before(begin)?
        && end.saturating_duration_since(Instant::now())<=p::PACKAGE_READ_CAP,
        "APK fixed PM query must borrow its actual 15-second original end")?;
    p::validate_packages(begin,packages).map_err(external)?;
    let roles=begin.scope().roles();
    let role=roles.get(ordinal as usize).ok_or_else(||reject("APK PM role is outside the actual slot"))?;
    let expected=packages.get(ordinal as usize).ok_or_else(||reject("APK PM actual package is absent"))?;
    require(role.package==expected.application.package,"APK PM fixed role changed")?;
    let main_before=owner.observe_main_custody(&begin.main().epoch,end).map_err(observation_authority_error)?;
    require(&main_before==begin.main(),"APK PM before Main differs")?;
    let operation=package_operation(begin.scope(),kind,ordinal)?;
    let result=factory_query::run(owner,&operation,end);
    // Keep the normal actual retirement failure stronger than a later owner
    // check. There is no automatic retry or fresh relative command budget.
    let result=workflow::finish_effect(result,||owner.ready().map_err(observation_authority_error),end)?;
    let main_after=owner.observe_main_custody(&begin.main().epoch,end).map_err(observation_authority_error)?;
    require(&main_after==begin.main(),"APK PM after Main differs")?;
    require(result.output.stdout.len()<=65_536 && result.output.stderr.len()<=65_536,
        "APK PM complete output exceeds its fixed bound")?;
    let comparison=p::PackageReadComparison{
        schema:"droidloom.native-leaf-package-read.v2".into(),kind,ordinal,main_before,main_after,
        application:expected.application.clone(),
        stdout_base64:crate::native_application_ui_protocol::encode64(&result.output.stdout),
        stderr_base64:crate::native_application_ui_protocol::encode64(&result.output.stderr),
        stderr_bytes:result.output.stderr.len(),
        stderr_sha256:format!("{:x}",Sha256::digest(&result.output.stderr)),
        receipt:serde_json::to_value(&result.receipt).map_err(external)?,
    };
    let decoded=comparison.output_for(begin,packages,kind,ordinal).map_err(external)?;
    require(decoded.status==result.output.status && decoded.stdout==result.output.stdout
        && decoded.stderr==result.output.stderr,"APK PM transport differs from its actual factory output")?;
    owner.check_request_deadline().map_err(observation_authority_error)?;
    Ok(FixedPackageObservation{comparison})
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::apk_protocol::{PackageReadKind as K,PACKAGE_READ_CAP};
    use super::super::apk_scope::{
        NativeLeafApkRoute as R,NativeLeafPreparationMember as M,NativeLeafPreparationRole,Scope,
    };
    use crate::native_application_ui_gateway::GatewayCommand as G;

    #[test]
    fn native_leaf_apk_fixed_roles_use_real_query_and_launcher_mappings(){
        let routes=[R::CalendarCore,R::CalendarReminder,R::CameraPhoto,R::ContactsSearch,
            R::ClockPair,R::ClockAlarm,R::DocumentsSaf,R::DocumentsSearch,R::GalleryRotation,
            R::GalleryVideo,R::GallerySeek,R::GalleryAlbum,R::SettingsSupportedPages,R::IhgLondon];
        let kinds=[K::Identity,K::Paths,K::Launcher];
        let check=|scope:Scope,ordinal:u8,kind:K|{
            let role=scope.roles()[ordinal as usize];
            let expected=match kind{
                K::Identity=>vec!["/system/bin/cmd","package","list","packages","-U",
                    "--show-versioncode","--user","0",role.package],
                K::Paths=>vec!["/system/bin/cmd","package","path","--user","0",role.package],
                K::Launcher=>vec!["/system/bin/cmd","package","resolve-activity","--brief",
                    "--user","0","-a","android.intent.action.MAIN","-c",
                    "android.intent.category.LAUNCHER",role.package],
            };
            let operation=package_operation(scope,kind,ordinal).unwrap();
            let actual=operation.arguments().unwrap().into_iter()
                .map(|value|value.into_string().unwrap()).collect::<Vec<_>>();
            assert_eq!(actual,expected);
            let domain=if kind==K::Launcher{OperationDomain::LaunchRead}else{OperationDomain::Query};
            assert_eq!(operation.domain(),domain);
            assert_eq!(operation.binary(),c"cmd");
            assert_eq!(operation.domain().guest_uid(),2000);
            assert_eq!(operation.descriptor_count(),15);
            assert!(!operation.uses_app_process()&&!operation.needs_am_jar()&&!operation.needs_content_jar());
            assert_eq!(PACKAGE_READ_CAP,std::time::Duration::from_secs(15));
            assert_eq!(operation.execution_limit(),PACKAGE_READ_CAP);
            if kind!=K::Launcher{
                let metadata=super::super::apk_protocol::metadata_arguments(role.package,kind==K::Paths).unwrap();
                let expected_metadata=if kind==K::Identity{
                    vec!["/system/bin/cmd","package","list","packages","--user","0","-U",
                        "--show-versioncode",role.package]
                }else{vec!["/system/bin/cmd","package","path","--user","0",role.package]};
                assert_eq!(metadata,expected_metadata);
                let original=ApplicationRead::from_command(&metadata).unwrap();
                let original=ApplicationOperation::Read{value:original};
                assert_eq!(original.domain(),OperationDomain::Query);
                assert_eq!(original.execution_limit(),QUERY_LIMIT);
                assert_eq!(original.descriptor_count(),15);
            }
            let profile=package_execution_profile(kind);
            assert_eq!(profile.process_selinux,domain.context());
            assert_eq!(profile.guest_uid,2000);
            assert_eq!(profile.executable_sha256,
                crate::production_execution_profile::query_inputs::INPUTS[0].sha256);
            let decoded:ApplicationOperation=serde_json::from_value(serde_json::to_value(&operation).unwrap()).unwrap();
            decoded.validate().unwrap();
            assert_eq!(decoded.arguments().unwrap(),operation.arguments().unwrap());
            let value=serde_json::to_value(&operation).unwrap();
            let body=value.get("value").unwrap().as_object().unwrap();
            assert_eq!(body.len(),3);
            assert!(body.contains_key("scope")&&body.contains_key("kind")&&body.contains_key("ordinal"));
        };
        let mut business_roles=0;
        for route in routes{
            let scope=Scope::Business{route};
            for ordinal in 0..scope.roles().len(){
                business_roles+=1;
                for kind in kinds{check(scope,ordinal as u8,kind);}
            }
            for kind in kinds{
                assert!(package_operation(scope,kind,scope.roles().len() as u8).is_err());
                assert!(package_operation(scope,kind,u8::MAX).is_err());
            }
            for member in [M::Application,M::Provider,M::NativeHelper,M::IhgHelper]{
                if let Ok(role)=NativeLeafPreparationRole::for_case(route,member){
                    let preparation=Scope::preparation(role);
                    for kind in kinds{
                        check(preparation,0,kind);
                        assert!(package_operation(preparation,kind,1).is_err());
                    }
                }
            }
        }
        assert_eq!(business_roles,35); // ClockPair supplies the second interval's two roles.
        for package in ["com.android.providers.calendar","com.android.providers.contacts",
            "com.android.providers.media.module","com.android.externalstorage",
            "local.pocket4.actions.v2","org.droidloom.qa.ihg.finalmain.r1"]{
            for command in [G::PackageIdentity{package:package.into()},G::PackagePaths{package:package.into()},
                G::PackageLauncher{package:package.into()}]{
                assert!(command.literal_arguments().is_err(),"public UI39 admitted {package}");
            }
        }
        for kind in kinds{
            assert!(kind.literal_arguments("com.example.unlisted").is_err());
        }
        let invalid=NativeLeafPackageRead{
            scope:Scope::Preparation{case:R::CameraPhoto,member:M::Provider},kind:K::Launcher,ordinal:0};
        assert!(invalid.validate().is_err());
        let valid=NativeLeafPackageRead{scope:Scope::Business{route:R::ContactsSearch},kind:K::Identity,ordinal:1};
        let mut value=serde_json::to_value(valid).unwrap();
        value.as_object_mut().unwrap().insert("package".into(),serde_json::json!("com.android.settings"));
        assert!(serde_json::from_value::<NativeLeafPackageRead>(value).is_err());
    }
}
