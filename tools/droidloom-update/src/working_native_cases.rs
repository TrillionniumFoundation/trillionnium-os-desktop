//! The fixed native preparation producer used by the actual working child.
//! This produces inputs, not application acceptance. It owns each real child,
//! each original step deadline, actual Main/PM observations and retired APK
//! history; caller JSON cannot supply a package, command or successful result.
use super::*;
use crate::native_leaf_sources::installed::InstalledCohort;
use droidloom_supervisor::control::{
    ClockPreparationKind, NativeCasePreparationStep as Step, NativeLeafApkHistory,
    NativeLeafCommandKind, NativeLeafPreparationCase as Case,
    NativeLeafPreparationMember as Member, NativeLeafPreparationRole as Role,
    run_prepared_native_leaf_until,
};
use droidloom_supervisor::control::physical_qualification_channel::WorkingPreparationChannel;
use std::{collections::BTreeMap, path::PathBuf, process::Command};
use std::os::unix::fs::{DirBuilderExt,FileExt};
use droidloom_supervisor::prebuilt_native_helpers::{DocumentsHelperKind,PrebuiltDocumentsMaterial};
use droidloom_supervisor::control::PackageHelpObservation;
use droidloom_supervisor::native_ihg_preparation::{
    self, IhgPreparationMode, HistoricalIhgPreparationExecution,
};
#[path = "working_preparation_artifacts.rs"]
mod artifacts;
use artifacts::Artifacts;

const CASES:[Case;14]=[
    Case::CalendarCore,Case::CalendarReminder,Case::CameraPhoto,Case::ContactsSearch,
    Case::ClockPair,Case::ClockAlarm,Case::DocumentsSaf,Case::DocumentsSearch,
    Case::GalleryRotation,Case::GalleryVideo,Case::GallerySeek,Case::GalleryAlbum,
    Case::SettingsSupportedPages,Case::IhgLondon,
];
// These allowances are source work phases, not replacements for a host
// command's original 1200 seconds or an APK session's 3000 second ceiling.
use droidloom_supervisor::working_preparation_budget::{
    IDENTITY_STEP_SECONDS, PLAN_STEP_SECONDS, BASELINE_STEP_SECONDS,
};
fn route(case:Case)->&'static str {
    match case {
        Case::CalendarCore=>"calendar_core",Case::CalendarReminder=>"calendar_reminder",
        Case::CameraPhoto=>"camera_photo",Case::ContactsSearch=>"contacts_search",
        Case::ClockPair=>"clock_timer_pair",Case::ClockAlarm=>"clock_alarm",
        Case::DocumentsSaf=>"documents_saf",Case::DocumentsSearch=>"documents_search_sort",
        Case::GalleryRotation=>"gallery_rotation",Case::GalleryVideo=>"gallery_video",
        Case::GallerySeek=>"gallery_seek",Case::GalleryAlbum=>"gallery_album",
        Case::SettingsSupportedPages=>"settings_supported_pages",Case::IhgLondon=>"ihg_london",
    }
}
fn primary(case:Case)->Result<Role> {Ok(Role::for_case(case,Member::Application)?)}
fn roles(case:Case)->Result<Vec<Role>> {
    let members:&[Member]=match case {
        Case::CalendarCore|Case::CalendarReminder|Case::ContactsSearch|Case::DocumentsSaf|Case::DocumentsSearch=>
            &[Member::Application,Member::Provider,Member::NativeHelper],
        Case::CameraPhoto|Case::ClockPair|Case::ClockAlarm|Case::SettingsSupportedPages=>
            &[Member::Application,Member::NativeHelper],
        // Gallery has no identity CLI; IHG retains its dedicated six-stage
        // factory, complete inventory and actual helper installation.
        _=>&[],
    };
    members.iter().map(|m|Ok(Role::for_case(case,*m)?)).collect()
}
fn fresh_output(prefix:&str)->Result<PathBuf> {
    if prefix.is_empty() || !prefix.bytes().all(|c|c.is_ascii_alphanumeric()||c==b'-') {
        return fail("preparation output prefix is not source fixed");
    }
    let mut random=[0u8;16];File::open("/dev/urandom")?.read_exact(&mut random)?;
    let path=Path::new(QUALIFICATION_ROOT).join(format!("{prefix}{}",hex::encode(random)));
    match fs::symlink_metadata(&path) {
        Err(error) if error.kind()==std::io::ErrorKind::NotFound=>Ok(path),
        _=>fail("fresh source preparation output already exists"),
    }
}
fn create_output_root(prefix:&str)->Result<PathBuf> {
    let parent=fs::symlink_metadata(QUALIFICATION_ROOT)?;
    if !parent.is_dir()||parent.uid()!=0||parent.gid()!=0||parent.mode()&0o7777!=0o700
        || Path::new(QUALIFICATION_ROOT).canonicalize()?!=Path::new(QUALIFICATION_ROOT) {
        return fail("normal preparation parent is not the fixed protected root");
    }
    let path=fresh_output(prefix)?;
    fs::DirBuilder::new().mode(0o700).create(&path)?;
    let actual=fs::symlink_metadata(&path)?;
    if !actual.is_dir()||actual.uid()!=0||actual.gid()!=0||actual.mode()&0o7777!=0o700
        || path.canonicalize()?!=path {return fail("new normal preparation output changed")}
    Ok(path)
}
fn read_material_apk(material:&PrebuiltDocumentsMaterial,end:Instant)->Result<Vec<u8>> {
    material.guard(end)?;
    let file=material.apk_file(end)?;
    let length=usize::try_from(material.apk_bytes())?;
    if length==0||length>1024*1024 {return fail("compiled Documents APK exceeds the original bound")}
    let mut raw=vec![0u8;length];let mut offset=0;
    while offset<raw.len() {
        check_before(end)?;
        let got=file.read_at(&mut raw[offset..],offset as u64)?;
        if got==0 {return fail("actual public helper APK was truncated")}
        offset+=got;
    }
    if sha(&raw)!=material.apk_sha256() {return fail("actual public helper APK changed")}
    material.guard(end)?;
    Ok(raw)
}

fn pin_path(value:&Value)->Result<PathBuf> {
    Ok(PathBuf::from(value.get("path").and_then(Value::as_str).ok_or("preparation file path absent")?))
}
struct Primary {
    case:Case,
    main:MainCustodyObservation,
    application:ActualApplicationObservation,
    image:Option<ActualImageApplicationObservation>,
    baseline:Value,
    qualification:Value,
}
struct RetiredPackageHelp {subject:usize,observation:PackageHelpObservation}
struct RetiredIhgPreparation {subject:usize,history:HistoricalIhgPreparationExecution}
struct RetiredIdentity {
    subject:usize,
    role:Role,
    history:NativeLeafApkHistory,
}
/// Only the actual fixed producer constructs this value. It has no Clone,
/// Deserialize or receipt constructor, and cannot mint a physical gate.
pub struct WorkingPreparedCases {
    sources:InstalledCohort,
    artifacts:Artifacts,
    primary:Vec<Primary>,
    identities:Vec<RetiredIdentity>,
    documents_materials:Vec<PrebuiltDocumentsMaterial>,
    package_help:Vec<RetiredPackageHelp>,
    ihg_preparation:Vec<RetiredIhgPreparation>,
    cases:BTreeMap<&'static str,Value>,
}
impl WorkingPreparedCases {
    pub fn guard(&mut self,end:Instant)->Result<()> {
        check_before(end)?;
        self.sources.recheck(end)?;
        for retained in &self.identities {
            let subject=self.primary.get(retained.subject).ok_or("retained preparation subject absent")?;
            retained.history.require_preparation_subject(subject.main.facts(),subject.application.facts(),retained.role)?;
        }
        for material in &self.documents_materials {material.guard(end)?;}
        for history in &self.package_help {
            let subject=self.primary.get(history.subject).ok_or("actual package-help subject absent")?;
            history.observation.require_main(&subject.main,&subject.application)?;
        }
        for retained in &mut self.ihg_preparation {
            let subject=self.primary.get(retained.subject).ok_or("actual IHG primary history absent")?;
            retained.history.guard_immutable(&subject.main,&subject.application,end)?;
        }
        self.artifacts.guard(end)?;
        check_before(end)
    }
    pub fn comparison(&self)->Value {
        json!({"schema":"droidloom.working-native-case-inputs.v1",
            "normal_source_recipe":self.sources.recipe(),"cases":self.cases,
            "actual_primary_subjects":self.primary.iter().map(|s|json!({
                "route":route(s.case),"package":s.application.facts().package,
                "epoch":s.main.facts().epoch,"baseline":s.baseline,"qualification":s.qualification,
                "whole_image_observation":s.image.as_ref().map(|v|v.facts())})).collect::<Vec<_>>(),
            "retired_identity_intervals":self.identities.len(),"files":self.artifacts.comparison(),
            "normal_documents_materials":self.documents_materials.iter().map(|m|m.comparison()).collect::<Vec<_>>(),
            "actual_package_help_observations":self.package_help.len(),
            "actual_ihg_preparation_history":self.ihg_preparation.iter().map(|r|r.history.comparison_report()).collect::<Vec<_>>(),
            "application_gate_credit":false,"whole_app_business_accepted":false,"production_ready":false})
    }
    pub fn case(&self,package:&str,selected_route:&Value)->Result<Value> {
        let selected=CASES.iter().copied().find(|case|
            selected_route.as_str()==Some(route(*case))
                && primary(*case).is_ok_and(|role|role.package()==package))
            .ok_or("physical route/package is not in the fixed preparation roster")?;
        self.cases.get(route(selected)).cloned().ok_or_else(||
            "normal preparation did not produce this actual case".into())
    }
    fn write(&mut self,root:&Path,name:&str,value:&Value,end:Instant)->Result<Value> {
        let pin=write_value(root,name,value)?;
        self.artifacts.hold_tree(root,end)?;
        self.artifacts.require_reference(&pin,end)?;
        Ok(pin)
    }
    fn request_root(&mut self,value:&Value,end:Instant)->Result<(PathBuf,Value)> {
        let (root,fd,identity)=private_capture_root()?;
        let pin=self.write(&root,"REQUEST.json",value,end)?;
        if directory_identity(&fd.metadata()?)!=identity
            || directory_identity(&fs::symlink_metadata(&root)?)!=identity {return fail("fresh request root changed")}
        fd.sync_all()?;
        Ok((root,pin))
    }
    fn source_root(&mut self,pin:&Value,end:Instant)->Result<PathBuf> {
        let value=self.artifacts.json(pin,end)?;
        let root=PathBuf::from(value["case_root"].as_str().ok_or("normal case source has no root")?);
        if pin_path(pin)?.parent()!=Some(root.as_path()) {return fail("source pin does not belong to its actual new root")}
        self.artifacts.hold_tree(&root,end)?;
        Ok(root)
    }
    fn run_step(&mut self,inspector:&mut NativeApplicationInspector,subject:&Primary,
        subject_index:usize,step:Step,request:Value,whole_end:Instant)->Result<Value>
    {
        step.validate()?;
        if step.case()!=subject.case {return fail("normal step does not belong to the actual primary case")}
        let identity_role=if let Step::Identity(role)=step {Some(role)}else{None};
        let end=preparation_end(whole_end,
            if identity_role.is_some(){IDENTITY_STEP_SECONDS}else{PLAN_STEP_SECONDS})?;
        let (root,request_pin)=self.request_root(&request,end)?;
        let output=step.output_prefix()?.map(fresh_output).transpose()?;
        let result_root=if let Some(path)=&output {path.clone()} else {
            self.source_root(request.get("source").ok_or("bind request source absent")?,end)?
        };
        let result_name=match step {
            Step::Identity(_)|Step::DocumentsPackageHelp(_)=>"result.json",
            Step::Plan(_)=>"plan.json",
            Step::ClockSource(_)=>"case-source.json",
            Step::DocumentsSource(_)=>"helper-source.json",
            Step::ClockBind(_)|Step::DocumentsBind(_)=>"execution-plan.json",
        };
        let preparation=self.sources.reference(step.preparation_relative()?)?;
        let entry=self.sources.reference(step.entry_relative()?)?;
        let mut baseline=NativeLeafBaselineObservation::capture_from_observed(
            inspector,&subject.main,&subject.application,end)?;
        let operation=(||->Result<Value>{
            if let Some(role)=identity_role {
                let role_pm=inspector.inspect_observed_until(role.package(),0,end)?;
                inspector.require_application_local(&subject.main,&role_pm,end)?;
                baseline.capture_preparation_apks_until(inspector,role,role_pm,end)?;
            }
            self.sources.recheck(end)?;
            self.write(&root,"STEP-INTENT.json",&json!({
                "schema":"droidloom.working-case-preparation-intent.v1","case":route(subject.case),
                "mode":step.mode(),"role":step.identity_role()?,"request":request_pin,
                "entry":entry,"preparation":preparation,"output":output,
                "actual_primary":subject.application.facts(),"actual_main":subject.main.facts(),
                "host_cap_seconds":1200,"step_cap_seconds":if identity_role.is_some(){IDENTITY_STEP_SECONDS}else{PLAN_STEP_SECONDS},
                "automatic_retry":false,"application_gate_credit":false}),end)?;
            let mut command=Command::new("/usr/bin/python3");
            command.args(["-I","-B"]).arg(pin_path(&entry)?)
                .arg("--preparation").arg(pin_path(&preparation)?)
                .arg("--expect-preparation-sha256").arg(preparation["sha256"].as_str().ok_or("preparation digest absent")?)
                .arg(step.mode()).arg("--request").arg(pin_path(&request_pin)?)
                .arg("--expect-request-sha256").arg(request_pin["sha256"].as_str().ok_or("request digest absent")?);
            if let Some(role)=step.identity_role()? {command.arg("--role").arg(role);}
            if let Some(kind)=step.kind() {command.arg("--kind").arg(kind);}
            if let Some(output)=&output {command.arg("--output").arg(output);}
            command.env_clear().env("PATH","/usr/sbin:/usr/bin:/sbin:/bin").env("LANG","C.UTF-8");
            let execution=run_prepared_native_leaf_until(command,&subject.application.facts().epoch,
                NativeLeafCommandKind::CasePreparation{step},inspector,&mut baseline,end);
            let output=match execution {
                Ok(output)=>output,
                Err(error)=>{
                    // The failed runner does not imply reader retirement. The
                    // original final factory must really finish, or this fails.
                    let final_result=bookend(inspector,&mut baseline,&subject.application,subject.image.as_ref(),end);
                    return fail(format!("normal preparation host failed: {error}; actual final bookend={final_result:?}"));
                }
            };
            let stdout=write_private(&root,"STEP.stdout",&output.stdout)?;
            let stderr=write_private(&root,"STEP.stderr",&output.stderr)?;
            self.write(&root,"STEP-EXECUTION.json",&json!({
                "schema":"droidloom.working-case-preparation-execution.v1",
                "request":request_pin,"stdout":stdout,"stderr":stderr,
                "actual_returncode":output.status.code(),"owned_host_tree_retired":true,
                "automatic_retry":false,"application_gate_credit":false}),end)?;
            bookend(inspector,&mut baseline,&subject.application,subject.image.as_ref(),end)?;
            if let Some(role)=identity_role {
                let history=baseline.take_apk_history_until(inspector,end)?;
                history.require_preparation_subject(subject.main.facts(),subject.application.facts(),role)?;
                self.write(&root,"APK-HISTORY.json",&history.comparison()?,end)?;
                self.identities.push(RetiredIdentity{subject:subject_index,role,history});
            }
            if !output.status.success() || !output.stderr.is_empty() {
                return fail(format!("fixed preparation exited {:?} or emitted stderr; evidence {}",
                    output.status.code(),root.display()));
            }
            self.artifacts.hold_tree(&result_root,end)?;
            let expected=self.artifacts.reference(&result_root.join(result_name),end)?;
            let printed:Value=serde_json::from_slice(&output.stdout)?;
            if printed!=json!({"result":expected,"whole_app_business_accepted":false}) {
                return fail("normal preparation stdout differs from its actual fixed result inode");
            }
            self.artifacts.require_reference(&expected,end)?;
            self.sources.recheck(end)?;
            baseline.verify_local(inspector,end)?;
            Ok(expected)
        })();
        if let Err(error)=&operation {
            let _=write_value(&root,"FAILED.json",&json!({
                "schema":"droidloom.working-case-preparation-failure.v1","actual_error":error.to_string(),
                "case":route(subject.case),"mode":step.mode(),"automatic_retry":false,
                "application_gate_credit":false,"production_ready":false}));
        }
        operation
    }
    fn identities(&mut self,inspector:&mut NativeApplicationInspector,subject:&Primary,
        subject_index:usize,end:Instant)->Result<BTreeMap<&'static str,Value>>
    {
        let mut values=BTreeMap::new();
        for role in roles(subject.case)? {
            let pin=self.run_step(inspector,subject,subject_index,Step::Identity(role),
                json!({"baseline":subject.baseline,"qualification":subject.qualification}),end)?;
            let key=match role.member() {
                Member::Application=>"target_identity",Member::Provider=>"provider_identity",
                Member::NativeHelper=>"helper_identity",Member::IhgHelper=>return fail("IHG uses its dedicated identity factory"),
            };
            if values.insert(key,pin).is_some() {return fail("duplicate prepared identity role")}
        }
        Ok(values)
    }
    fn original_plan(&mut self,inspector:&mut NativeApplicationInspector,subject:&Primary,
        index:usize,end:Instant)->Result<Value>
    {
        let identities=self.identities(inspector,subject,index,end)?;
        let mut request=json!({"baseline":subject.baseline,"qualification":subject.qualification});
        for (key,pin) in identities {request[key]=pin;}
        self.run_step(inspector,subject,index,Step::Plan(subject.case),request,end)
    }
    fn clock_plan(&mut self,inspector:&mut NativeApplicationInspector,subject:&Primary,
        index:usize,end:Instant)->Result<Value>
    {
        let identities=self.identities(inspector,subject,index,end)?;
        let kinds:&[ClockPreparationKind]=if subject.case==Case::ClockPair {
            &[ClockPreparationKind::Timer15,ClockPreparationKind::Expiry06]
        }else{&[ClockPreparationKind::Alarm04]};
        let mut wrappers=BTreeMap::new();
        for kind in kinds {
            let source=self.run_step(inspector,subject,index,Step::ClockSource(*kind),json!({
                "kind":kind.name(),"baseline":subject.baseline,"qualification":subject.qualification,
                "target_identity":identities["target_identity"],"native_identity":identities["helper_identity"]}),end)?;
            let plan=self.run_step(inspector,subject,index,Step::ClockBind(*kind),json!({"source":source}),end)?;
            let (root,_,_)=private_capture_root()?;
            let wrapper=self.write(&root,"LEAF-REQUEST.json",&json!({"plan":plan}),end)?;
            wrappers.insert(kind.name(),wrapper);
        }
        if subject.case==Case::ClockPair {
            let (root,_,_)=private_capture_root()?;
            self.write(&root,"LEAF-REQUEST.json",&json!({"schema":"droidloom.clock-timer-pair-request.v1",
                "timer15":wrappers["timer15"],"expiry06":wrappers["expiry06"]}),end)
        }else{Ok(wrappers.remove("alarm04").ok_or("actual alarm request absent")?)}
    }

    fn ihg_step(&mut self,inspector:&mut NativeApplicationInspector,subject:&Primary,
        index:usize,mode:IhgPreparationMode,request:Value,whole_end:Instant)->Result<Value>
    {
        if subject.case!=Case::IhgLondon {return fail("IHG preparation belongs to another primary case")}
        let end=preparation_end(whole_end,1800)?;
        let (evidence,request_pin)=self.request_root(&request,end)?;
        let output=fresh_output(mode.output_prefix())?;
        if output.parent()!=Some(Path::new(mode.output_parent())) {
            return fail("fixed IHG output root differs from the normal producer");
        }
        self.write(&evidence,"IHG-STEP-INTENT.json",&json!({
            "schema":"droidloom.working-ihg-preparation-intent.v2","mode":mode.name(),
            "request":request_pin,"output":output,"actual_main":subject.main.facts(),
            "actual_target":subject.application.facts(),"step_cap_seconds":1800,
            "original_working_end_is_not_renewed":true,"automatic_retry":false,
            "whole_app_business_accepted":false}),end)?;
        let mut baseline=NativeLeafBaselineObservation::capture_from_observed(
            inspector,&subject.main,&subject.application,end)?;
        let inventory=inspector.observe_user_zero_package_inventory_until(
            &subject.main,&subject.application,end)?;
        baseline.attach_user_zero_inventory(inspector,inventory)?;
        let execution=native_ihg_preparation::run(mode,&pin_path(&request_pin)?,
            request_pin["sha256"].as_str().ok_or("normal IHG request SHA absent")?,
            &output,&evidence,inspector,&mut baseline,end);
        let execution=match execution {
            Ok(value)=>value,
            Err(error)=>{
                let _=write_value(&evidence,"IHG-STEP-FAILED.json",&json!({
                    "schema":"droidloom.working-ihg-preparation-failure.v2","mode":mode.name(),
                    "actual_error":error,"automatic_retry":false,"whole_app_business_accepted":false}));
                return fail(error);
            }
        };
        self.artifacts.hold_tree(&evidence,end)?;
        self.artifacts.hold_tree(&output,end)?;
        let history=execution.seal_history_before(end)?;
        let pin=history.result_pin().clone();
        self.artifacts.require_reference(&pin,end)?;
        self.ihg_preparation.push(RetiredIhgPreparation{subject:index,history});
        self.sources.recheck(end)?;
        check_before(end)?;
        Ok(pin)
    }
    fn ihg_plan(&mut self,inspector:&mut NativeApplicationInspector,subject:&Primary,
        index:usize,whole_end:Instant)->Result<Value>
    {
        use IhgPreparationMode as M;
        let initial=json!({"baseline":subject.baseline,"qualification":subject.qualification});
        let target=self.ihg_step(inspector,subject,index,M::TargetIdentity,initial.clone(),whole_end)?;
        let source=self.ihg_step(inspector,subject,index,M::HelperSource,initial,whole_end)?;
        let build=self.ihg_step(inspector,subject,index,M::HelperBuild,json!({"source":source}),whole_end)?;
        let install=self.ihg_step(inspector,subject,index,M::HelperInstall,
            json!({"build":build,"target_identity":target}),whole_end)?;
        let helper=self.ihg_step(inspector,subject,index,M::HelperIdentity,json!({
            "baseline":subject.baseline,"qualification":subject.qualification,
            "build":build,"install":install,"target_identity":target}),whole_end)?;
        let plan=self.ihg_step(inspector,subject,index,M::Plan,json!({
            "baseline":subject.baseline,"qualification":subject.qualification,
            "target_identity":target,"helper_identity":helper,
            "helper_build":build,"helper_install":install}),whole_end)?;
        let (root,_,_)=private_capture_root()?;
        self.write(&root,"LEAF-REQUEST.json",&json!({"plan":plan}),whole_end)
    }

    fn documents_package_help(&mut self,inspector:&mut NativeApplicationInspector,
        subject:&Primary,index:usize,source:&Value,preparation:&Value,whole_end:Instant)->Result<Value>
    {
        let end=preparation_end(whole_end,PLAN_STEP_SECONDS)?;
        let prefix=match subject.case {
            Case::DocumentsSaf=>"business-documents-saf-pm-help-",
            Case::DocumentsSearch=>"business-documents-pm-help-",
            _=>return fail("package help is exclusive to the two fixed Documents cases"),
        };
        let root=create_output_root(prefix)?;
        self.write(&root,"INTENT.json",&json!({"schema":"droidloom.documents-package-help-intent.v2",
            "source":source,"source_preparation":preparation,"baseline":subject.baseline,
            "qualification":subject.qualification,"actual_main":subject.main.facts(),
            "actual_application":subject.application.facts(),"command_cap_seconds":15,
            "step_cap_seconds":PLAN_STEP_SECONDS,"automatic_retry":false}),end)?;
        let mut baseline=NativeLeafBaselineObservation::capture_from_observed(
            inspector,&subject.main,&subject.application,end)?;
        let observed=inspector.observe_package_help_until(&subject.main,&subject.application,end);
        // Real Main/PM/source bookends are required even after a failed query.
        let finished=bookend(inspector,&mut baseline,&subject.application,None,end);
        let result=(||->Result<Value>{
            let observed=match (observed,finished) {
                (Ok(observed),Ok(()))=>observed,
                (Err(error),Ok(()))=>return Err(error.into()),
                (Ok(_),Err(error))=>return Err(error),
                (Err(error),Err(after))=>return fail(format!("{error}; package-help final custody also failed: {after}")),
            };
            observed.require_main(&subject.main,&subject.application)?;
            let output=observed.output();
            let stdout=write_private(&root,"stdout",&output.stdout)?;
            let stderr=write_private(&root,"stderr",&output.stderr)?;
            let observation=self.write(&root,"OBSERVATION.json",
                &observed.comparison().map_err(|e|format!("package help comparison: {e}"))?,end)?;
            let text=std::str::from_utf8(&output.stdout)?;
            let lines:Vec<_>=text.lines().filter(|s|s.trim_start().starts_with("-R:"))
                .map(str::to_owned).collect();
            let result=self.write(&root,"result.json",&json!({
                "schema":"droidloom.documents-package-help.v2","source":source,
                "source_preparation":preparation,"baseline":subject.baseline,
                "qualification":subject.qualification,"stdout":stdout,"stderr":stderr,
                "observation":observation,"actual_returncode":output.status.code(),
                "no_replace_flag":"-R","actual_flag_lines":lines,"ui_actions":0,
                "package_mutations":0,"automatic_retry":false,"application_gate_credit":false}),end)?;
            let acceptable=output.status.success()&&output.stderr.is_empty()
                && lines.iter().map(|s|s.trim()).collect::<Vec<_>>()
                    ==["-R: disallow replacement of existing application"];
            // Hold the actual typed observation; a saved result cannot replace it.
            self.package_help.push(RetiredPackageHelp{subject:index,observation:observed});
            if !acceptable {return fail(format!("actual package help failed or did not state the unique no-replace semantics: {}",root.display()))}
            self.sources.recheck(end)?;
            Ok(result)
        })();
        if let Err(error)=&result {
            let _=write_value(&root,"FAILED.json",&json!({"schema":"droidloom.documents-package-help-failure.v2",
                "actual_error":error.to_string(),"automatic_retry":false,"application_gate_credit":false}));
        }
        result
    }
    fn documents_plan(&mut self,inspector:&mut NativeApplicationInspector,subject:&Primary,
        index:usize,end:Instant)->Result<Value>
    {
        let (kind,prefix,apk_name)=match subject.case {
            Case::DocumentsSaf=>(DocumentsHelperKind::Saf,"business-documents-saf-helper-build-","owned-saf.apk"),
            Case::DocumentsSearch=>(DocumentsHelperKind::Features,"business-documents-helper-build-","owned-features.apk"),
            _=>return fail("not a fixed Documents preparation"),
        };
        // These immutable normal publication files remain held through Ready ACK.
        let material=PrebuiltDocumentsMaterial::capture(kind,end)?;
        let manifest=material.manifest_reference(end)?;
        let normal_source=material.source_reference(end)?;
        let identities=self.identities(inspector,subject,index,end)?;
        let source=self.run_step(inspector,subject,index,Step::DocumentsSource(subject.case),json!({
            "baseline":subject.baseline,"qualification":subject.qualification,
            "target_identity":identities["target_identity"],"provider_identity":identities["provider_identity"],
            "native_identity":identities["helper_identity"],"prebuilt_helper":manifest}),end)?;
        let preparation=self.sources.reference(Step::DocumentsSource(subject.case).preparation_relative()?)?;
        let source_value=self.artifacts.json(&source,end)?;
        if source_value["run_id"]!=material.run_id() || source_value["prebuilt_helper"]!=manifest
            || source_value["helper_manifest"]["package"]!=material.package() {
            return fail("normal Documents source did not render the actual fixed public helper");
        }
        let build_root=create_output_root(prefix)?;
        let raw=read_material_apk(&material,end)?;
        let apk=write_private(&build_root,apk_name,&raw)?;
        material.guard(end)?;
        let build=self.write(&build_root,"build-result.json",&json!({
            "schema":"droidloom.documents-prebuilt-binding.v2","source":source,
            "source_preparation":preparation,"baseline":subject.baseline,"qualification":subject.qualification,
            "prebuilt_helper":manifest,"normal_source":normal_source,"package":material.package(),
            "run_id":material.run_id(),"version_code":material.version_code(),"apk":apk,
            "signer_certificate_sha256":material.certificate_sha256(),
            "actual_main":subject.main.facts(),"actual_application":subject.application.facts(),
            "installed":false,"Android_UI_actions":0,"Main_mutations":0,
            "whole_app_business_accepted":false,"automatic_retry":false}),end)?;
        self.documents_materials.push(material);
        let help=self.documents_package_help(inspector,subject,index,&source,&preparation,end)?;
        let plan=self.run_step(inspector,subject,index,Step::DocumentsBind(subject.case),
            json!({"source":source,"build":build,"pm_help":help}),end)?;
        let (root,_,_)=private_capture_root()?;
        self.write(&root,"LEAF-REQUEST.json",&json!({"plan":plan}),end)
    }

    fn gallery_request(&mut self,subject:&Primary,publication:&Value,end:Instant)->Result<Value> {
        if subject.image.is_none() {return fail("Gallery preparation has no actual whole-image observation")}
        let scope=match subject.case {Case::GalleryRotation=>"rotation",Case::GalleryVideo=>"video",
            Case::GallerySeek=>"seek",Case::GalleryAlbum=>"album",_=>return fail("not a Gallery route")};
        let prefix=format!("gallery-image-{scope}-20261120-r");
        let mut maximum=0u32;let mut count=0usize;
        for entry in fs::read_dir(QUALIFICATION_ROOT)? {
            check_before(end)?;
            let entry=entry?;let name=entry.file_name();
            let Some(name)=name.to_str() else {continue};
            let Some(suffix)=name.strip_prefix(&prefix) else {continue};
            if suffix.is_empty()||!suffix.bytes().all(|c|c.is_ascii_digit()) {continue}
            count+=1;
            if count>128 {return fail("Gallery previous attempt roster exceeds source bound")}
            let attempt=suffix.parse::<u32>()?;
            let root=entry.path();let m=fs::symlink_metadata(&root)?;
            if !m.is_dir()||m.uid()!=0||m.gid()!=0||m.mode()&0o7777!=0o700||root.canonicalize()?!=root {
                return fail("previous Gallery attempt is not the protected original root");
            }
            let path=root.join("result.json");
            let mut file=OpenOptions::new().read(true).custom_flags(libc::O_CLOEXEC|libc::O_NOFOLLOW).open(&path)?;
            let before=node(&file.metadata()?);
            if before[3..6]!=[0,0,1]||before[6]<=0||before[6]>4*1024*1024 {return fail("previous Gallery result has invalid shape")}
            let mut bytes=Vec::new();Read::by_ref(&mut file).take(4*1024*1024+1).read_to_end(&mut bytes)?;
            let value:Value=serde_json::from_slice(&bytes)?;
            if node(&file.metadata()?)!=before||node(&fs::symlink_metadata(&path)?)!=before
                || !["CURRENT_IMAGE_SCOPE_AND_CLEANUP_VERIFIED","CURRENT_IMAGE_OBSERVED_BUSINESS_PENDING"]
                    .contains(&value["state"].as_str().unwrap_or(""))
                || value["outcome_unknown"]!=false {
                return fail("prior Gallery attempt has no terminal cleanup reconciliation");
            }
            maximum=maximum.max(attempt);
        }
        let next=maximum.checked_add(1).ok_or("Gallery attempt number overflow")?;
        let output=Path::new(QUALIFICATION_ROOT).join(format!("{prefix}{next}"));
        if fs::symlink_metadata(&output).is_ok() {return fail("new Gallery output already exists")}
        let (root,_,_)=private_capture_root()?;
        self.write(&root,"LEAF-REQUEST.json",&json!({"schema":"pocket4-gallery-image-request-v1",
            "baseline":subject.baseline,"qualification":subject.qualification,
            "output":output,"native_release":publication}),end)
    }
}

/// Normal installed producer only: zero caller-selected case/input/path/epoch.
pub fn prepare_working_native_cases(channel:&mut WorkingPreparationChannel)->Result<WorkingPreparedCases> {
    channel.guard()?;
    let end=channel.deadline();
    let publication=serde_json::to_value(channel.source_publication())?;
    let mut output=WorkingPreparedCases{sources:InstalledCohort::capture(end)?,artifacts:Artifacts::new(),
        primary:Vec::new(),identities:Vec::new(),documents_materials:Vec::new(),package_help:Vec::new(),ihg_preparation:Vec::new(),cases:BTreeMap::new()};
    for case in CASES {
        channel.guard()?;
        let baseline_end=preparation_end(end,BASELINE_STEP_SECONDS)?;
        let role=primary(case)?;
        let (inspector,expected_main)=channel.observations();
        let (application,image)=if role.package()=="com.android.gallery3d" {
            let (application,image)=inspector.inspect_gallery_observed_until(baseline_end)?;
            (application,Some(image))
        }else{(inspector.inspect_observed_until(role.package(),0,baseline_end)?,None)};
        let main=inspector.refresh_main_until(expected_main,baseline_end)?;
        if main.facts()!=expected_main.facts() {return fail("normal case preparation changed actual Main")}
        inspector.require_application_local(&main,&application,baseline_end)?;
        if let Some(image)=&image {inspector.require_image_application_local(&main,&application,image,baseline_end)?;}
        let capture=capture_business_observed(inspector,&main,&application,image.as_ref(),baseline_end)?;
        let baseline=capture.get("baseline").cloned().ok_or("actual baseline producer omitted baseline")?;
        let qualification=capture.get("qualification").cloned().ok_or("actual baseline producer omitted qualification")?;
        let baseline_path=pin_path(&baseline)?;
        let root=baseline_path.parent().ok_or("baseline producer root absent")?;
        output.artifacts.hold_tree(root,end)?;
        output.artifacts.require_reference(&baseline,end)?;
        output.artifacts.require_reference(&qualification,end)?;
        let subject=Primary{case,main,application,image,baseline,qualification};
        let index=output.primary.len();
        let mut physical_output=Value::Null;
        let request=match case {
            Case::ClockPair|Case::ClockAlarm=>output.clock_plan(inspector,&subject,index,end)?,
            Case::GalleryRotation|Case::GalleryVideo|Case::GallerySeek|Case::GalleryAlbum=>
                output.gallery_request(&subject,&publication,end)?,
            Case::DocumentsSaf|Case::DocumentsSearch=>
                output.documents_plan(inspector,&subject,index,end)?,
            Case::IhgLondon=>output.ihg_plan(inspector,&subject,index,end)?,
            _=>{
                let plan=output.original_plan(inspector,&subject,index,end)?;
                let value=if case==Case::CameraPhoto {
                    physical_output=serde_json::to_value(fresh_output("camera-photo-display-")?)?;
                    json!({"schema":"pocket4-camera-photo-display-input-v1","plan":plan,
                        "source_preparation":output.sources.reference("preparations/camera-photo.json")?,
                        "automatic_retry":false,"whole_app_business_accepted":false})
                }else{json!({"base_plan":plan})};
                let (root,_,_)=private_capture_root()?;
                output.write(&root,"LEAF-REQUEST.json",&value,end)?
            }
        };
        let prepared=json!({"leaf":{"route":route(case),"request":request,"output":physical_output},
            "main_qualification":subject.qualification});
        if output.cases.insert(route(case),prepared).is_some() {return fail("duplicate normal native case")}
        output.primary.push(subject);
        channel.guard()?;
    }
    if output.cases.len()!=CASES.len()||output.primary.len()!=CASES.len() {
        return fail("normal native preparation did not complete its fixed roster");
    }
    output.guard(end)?;
    channel.guard()?;
    Ok(output)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn working_preparation_has_exact_original_fourteen_case_and_twenty_three_identity_rosters() {
        assert_eq!(CASES.len(),14);
        let mut names=std::collections::BTreeSet::new();let mut identity_count=0;
        for case in CASES {
            assert!(names.insert(route(case)));identity_count+=roles(case).unwrap().len();
            for role in roles(case).unwrap() {assert_eq!(role.case(),case);}
        }
        assert_eq!(identity_count,23);
        assert!(roles(Case::GalleryRotation).unwrap().is_empty());
        assert!(roles(Case::IhgLondon).unwrap().is_empty());
        assert_eq!(route(Case::ClockPair),"clock_timer_pair");
        assert_eq!(route(Case::DocumentsSearch),"documents_search_sort");
    }
    #[test]
    fn working_preparation_steps_share_one_bounded_end_without_resetting_the_whole_window() {
        assert_eq!(IDENTITY_STEP_SECONDS,2160);
        assert_eq!(PLAN_STEP_SECONDS,1640);
        assert!(IDENTITY_STEP_SECONDS<3000);
        let earlier=Instant::now()+Duration::from_secs(1);
        assert_eq!(preparation_end(earlier,IDENTITY_STEP_SECONDS).unwrap(),earlier);
        assert!(preparation_end(Instant::now()-Duration::from_secs(1),PLAN_STEP_SECONDS).is_err());
    }
}
