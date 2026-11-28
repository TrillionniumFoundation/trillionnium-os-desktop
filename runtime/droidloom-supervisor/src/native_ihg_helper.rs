//! Closed IHG static-helper installation and state-only comparison messages.
//! Only the actual normal preparation peer can dispatch these requests. No
//! caller command, package, path, UID, domain or success flag is accepted.
use crate::control::application_probe::ApplicationInspection;
use crate::main_custody::RuntimeMainCustody;
use crate::native_leaf_baseline::NativeLeafBaselineObservation;
use crate::package_inventory_observation::UserZeroPackageInventoryFacts;
use crate::native_package_help::ReadComparison;
use serde::{Deserialize,Serialize};
use serde_json::{Value,json};
use sha2::{Digest,Sha256};
use std::{time::{Duration,Instant},process::Output};

pub(crate) const TARGET:&str="com.ihg.apps.android";
pub(crate) const HELPER:&str="org.droidloom.qa.ihg.finalmain.r1";
pub(crate) const APK_BYTES:u64=24720;
pub(crate) const APK_SHA256:&str="c5e38378c6f61e989ecaa4177eed48039b836aa6311e18961824adfd238dde15";
pub(crate) const INSTALL_LIMIT:Duration=Duration::from_secs(600);
pub(crate) const STATE_LIMIT:Duration=Duration::from_secs(20);
pub(crate) const ABSENCE_LIMIT:Duration=Duration::from_secs(8);
pub(crate) const OUTPUT_LIMIT:usize=65536;
pub(crate) const MAX_RESPONSE_BYTES:usize=1024*1024;
type Result<T>=std::result::Result<T,String>;
fn need(ok:bool,why:&str)->Result<()> {if ok {Ok(())}else{Err(why.into())}}
pub(crate) fn hash(raw:&[u8])->String {format!("{:x}",Sha256::digest(raw))}
fn digest(v:&str)->bool {v.len()==64&&v.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b))}
fn nonce(v:&str)->bool {v.len()==32&&v.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b))}
fn exact(v:&Value,fields:&[&str])->bool {v.as_object().is_some_and(|o|o.len()==fields.len()&&fields.iter().all(|k|o.contains_key(*k)))}
fn monotonic_ns()->Result<u64> {
    let mut t:libc::timespec=unsafe{std::mem::zeroed()};
    if unsafe{libc::clock_gettime(libc::CLOCK_MONOTONIC,&mut t)}!=0{return Err(std::io::Error::last_os_error().to_string())}
    need(t.tv_sec>=0&&(0..1_000_000_000).contains(&t.tv_nsec),"IHG monotonic clock invalid")?;
    (t.tv_sec as u64).checked_mul(1_000_000_000).and_then(|v|v.checked_add(t.tv_nsec as u64)).ok_or("IHG monotonic overflow".into())
}
fn encode_end(end:Instant,limit:Duration)->Result<u64> {
    let clock=monotonic_ns()?;
    let left=end.checked_duration_since(Instant::now()).filter(|v|!v.is_zero()).ok_or("IHG original end elapsed")?.min(limit);
    clock.checked_add(u64::try_from(left.as_nanos()).map_err(|_|"IHG end overflow")?).ok_or("IHG end overflow".into())
}
fn decode_end(end:u64,limit:Duration)->Result<Instant> {
    let now=Instant::now();let left=end.checked_sub(monotonic_ns()?).filter(|v|*v>0).ok_or("IHG original end elapsed")?;
    need(u128::from(left)<=limit.as_nanos(),"IHG request enlarged its original cap")?;
    now.checked_add(Duration::from_nanos(left)).ok_or("IHG Instant overflow".into())
}
fn closed<'de,D,T>(de:D)->std::result::Result<T,D::Error>
where D:serde::Deserializer<'de>,T:serde::de::DeserializeOwned+Serialize {
    let raw=crate::native_preparation_json::unique_json_value(de)?;
    let value:T=serde_json::from_value(raw.clone()).map_err(serde::de::Error::custom)?;
    if serde_json::to_value(&value).map_err(serde::de::Error::custom)?!=raw{return Err(serde::de::Error::custom("unrecognized IHG comparison fields"))}
    Ok(value)
}
fn target(main:&RuntimeMainCustody,app:&ApplicationInspection)->Result<()> {
    main.validate(&app.epoch)?;
    need(main.epoch==app.epoch&&app.package==TARGET&&app.user==0&&app.uid==10137
        &&app.version_code==50023856&&app.apks.len()==1&&app.apks[0].name=="base.apk"
        &&app.apks[0].bytes==48083457
        &&app.apks[0].sha256=="7ecd61fd1be0541568705004f8a81f6914646c7e050fe9188283205968215ed0",
        "IHG target differs from the selected original complete identity")
}
fn helper(main:&RuntimeMainCustody,app:&ApplicationInspection)->Result<()> {
    main.validate(&app.epoch)?;
    need(main.epoch==app.epoch&&app.package==HELPER&&app.user==0
        &&(10000..100000).contains(&app.uid)&&app.uid!=10137&&app.version_code==1
        &&app.apks.len()==1&&app.apks[0].name=="base.apk"
        &&app.apks[0].bytes==APK_BYTES&&app.apks[0].sha256==APK_SHA256
        &&app.apks[0].path.starts_with("/data/app/")&&app.apks[0].path.ends_with("/base.apk"),
        "IHG helper is not the actual normal newly installed static APK")
}

/// Comparison fields are minted from the held original baseline bytes and
/// actual opaque Main/PM. Deserialization on the private wire grants no owner.
#[derive(Clone,Debug,Eq,PartialEq,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct MainBinding {
    main_epoch_sha256:String,
    main_baseline_schema:String,
    main_baseline_sha256:String,
    main_baseline_qualification_sha256:String,
}
impl MainBinding {
    pub(crate) fn from_actual(baseline:&NativeLeafBaselineObservation<'_>,raw:&[u8],qualification:&[u8])->Result<Self> {
        let value:Value=serde_json::from_slice(raw).map_err(|e|e.to_string())?;
        let q:Value=serde_json::from_slice(qualification).map_err(|e|e.to_string())?;
        let core=serde_json::to_value(baseline.facts()).map_err(|e|e.to_string())?;
        need(value["schema"]=="droidloom.native-leaf-business-baseline.v1"
            &&value["native_owner"]==core
            &&q["schema"]=="droidloom.native-leaf-business-qualification.v1"
            &&q["baseline"]["bytes"]==raw.len()&&q["baseline"]["sha256"]==hash(raw)
            &&q["main_epoch_sha256"]==value["framework_epoch"]["sha256"]
            &&q["comparison_only"]==true&&q["business_actions_admitted"]==false
            &&q["whole_app_business_accepted"]==false&&q["production_ready"]==false,
            "IHG binding must use held current baseline/qualification for the actual Main")?;
        let v=Self{main_epoch_sha256:value["framework_epoch"]["sha256"].as_str().ok_or("IHG epoch digest absent")?.into(),
            main_baseline_schema:"droidloom.native-leaf-business-baseline.v1".into(),
            main_baseline_sha256:hash(raw),main_baseline_qualification_sha256:hash(qualification)};
        v.validate()?;Ok(v)
    }
    pub(crate) fn validate(&self)->Result<()> {
        need(self.main_baseline_schema=="droidloom.native-leaf-business-baseline.v1"
            &&[&self.main_epoch_sha256,&self.main_baseline_sha256,&self.main_baseline_qualification_sha256].iter().all(|v|digest(v)),
            "IHG exact typed runtime Main binding required")
    }
    pub(crate) fn canonical(&self)->Result<Vec<u8>> {
        self.validate()?;
        // Value's ordered map supplies the helper's original canonical ordering.
        serde_json::to_vec(&serde_json::to_value(self).map_err(|e|e.to_string())?).map_err(|e|e.to_string())
    }
    pub(crate) fn comparison(&self)->Result<Value> {serde_json::to_value(self).map_err(|e|e.to_string())}
}
#[derive(Debug,Eq,PartialEq,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IhgInstallRequest {
    schema:String,
    #[serde(deserialize_with="closed")] main:RuntimeMainCustody,
    #[serde(deserialize_with="closed")] target:ApplicationInspection,
    #[serde(deserialize_with="closed")] before_inventory:UserZeroPackageInventoryFacts,
    binding:MainBinding,
    deadline_monotonic_ns:u64,
}
impl Clone for IhgInstallRequest {
    fn clone(&self)->Self {
        // This is a comparison value, not an opaque inventory observation.
        serde_json::from_value(serde_json::to_value(self).expect("IHG comparison serializes"))
            .expect("IHG comparison roundtrips")
    }
}
impl IhgInstallRequest {
    pub(crate) fn from_owned(b:&NativeLeafBaselineObservation<'_>,binding:MainBinding,end:Instant)->Result<Self> {
        let value=Self{schema:"droidloom.ihg-helper-install-request.v2".into(),main:b.main().facts().clone(),
            target:b.application().clone(),before_inventory:serde_json::from_value(
                serde_json::to_value(b.inventory_facts().ok_or("IHG complete preinventory absent")?)
                    .map_err(|e|e.to_string())?).map_err(|e|e.to_string())?,
            binding,deadline_monotonic_ns:encode_end(end,INSTALL_LIMIT)?};value.validate()?;Ok(value)
    }
    pub(crate) fn validate(&self)->Result<()> {
        need(self.schema=="droidloom.ihg-helper-install-request.v2","IHG install schema differs")?;
        target(&self.main,&self.target)?;self.before_inventory.validate(&self.main.epoch)?;
        need(!self.before_inventory.records().contains_key(HELPER)
            &&self.before_inventory.records().get(TARGET)==Some(&self.target.uid),"IHG helper is already installed or target UID changed")?;
        self.binding.validate()?;self.deadline()?;Ok(())
    }
    pub(crate) fn main(&self)->&RuntimeMainCustody {&self.main}
    pub(crate) fn target(&self)->&ApplicationInspection {&self.target}
    pub(crate) fn before_inventory(&self)->&UserZeroPackageInventoryFacts {&self.before_inventory}
    pub(crate) fn deadline(&self)->Result<Instant> {decode_end(self.deadline_monotonic_ns,INSTALL_LIMIT)}
}
#[derive(Clone,Debug,Eq,PartialEq,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IhgStateRequest {
    schema:String,
    #[serde(deserialize_with="closed")] main:RuntimeMainCustody,
    #[serde(deserialize_with="closed")] target:ApplicationInspection,
    #[serde(deserialize_with="closed")] helper:ApplicationInspection,
    binding:MainBinding,
    nonce:String,
    deadline_monotonic_ns:u64,
}
impl IhgStateRequest {
    pub(crate) fn from_owned(b:&NativeLeafBaselineObservation<'_>,actual_helper:&crate::control::ActualApplicationObservation,
        binding:MainBinding,nonce:String,end:Instant)->Result<Self> {
        let v=Self{schema:"droidloom.ihg-helper-state-request.v2".into(),main:b.main().facts().clone(),
            target:b.application().clone(),helper:actual_helper.facts().clone(),binding,nonce,
            deadline_monotonic_ns:encode_end(end,STATE_LIMIT)?};v.validate()?;Ok(v)
    }
    pub(crate) fn validate(&self)->Result<()> {
        need(self.schema=="droidloom.ihg-helper-state-request.v2"&&nonce(&self.nonce),"IHG exact state request required")?;
        target(&self.main,&self.target)?;helper(&self.main,&self.helper)?;self.binding.validate()?;self.deadline()?;Ok(())
    }
    pub(crate) fn main(&self)->&RuntimeMainCustody {&self.main}
    pub(crate) fn target(&self)->&ApplicationInspection {&self.target}
    pub(crate) fn helper(&self)->&ApplicationInspection {&self.helper}
    pub(crate) fn binding(&self)->&MainBinding {&self.binding}
    pub(crate) fn nonce(&self)->&str {&self.nonce}
    pub(crate) fn deadline(&self)->Result<Instant> {decode_end(self.deadline_monotonic_ns,STATE_LIMIT)}
    pub(crate) fn logical_arguments(&self)->Result<Vec<String>> {
        self.validate()?;
        let request=json!({"protocol":"pocket4-owned-ihg-qa-final-main-v1","nonce":self.nonce,"op":"state"});
        let bytes=serde_json::to_vec(&request).map_err(|e|e.to_string())?;
        Ok(vec!["/system/bin/am".into(),"instrument".into(),"-w".into(),"-r".into(),"-e".into(),"request".into(),
            encode64(&bytes),"-e".into(),"main_binding".into(),encode64(&self.binding.canonical()?),
            format!("{HELPER}/{HELPER}.ActionRunner")])
    }
}
fn encode64(raw:&[u8])->String {
    const T:&[u8;64]=b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out=String::new();
    for p in raw.chunks(3) {let x=(u32::from(p[0])<<16)|(u32::from(p.get(1).copied().unwrap_or(0))<<8)|u32::from(p.get(2).copied().unwrap_or(0));
        out.push(T[((x>>18)&63)as usize]as char);out.push(T[((x>>12)&63)as usize]as char);
        out.push(if p.len()>1{T[((x>>6)&63)as usize]as char}else{'='});out.push(if p.len()>2{T[(x&63)as usize]as char}else{'='});}
    out
}
pub(crate) fn one_helper(before:&UserZeroPackageInventoryFacts,after:&UserZeroPackageInventoryFacts)->Result<u32> {
    before.validate(&before.epoch)?;after.validate(&before.epoch)?;
    let a=before.records();let b=after.records();let uid=*b.get(HELPER).ok_or("new IHG helper absent")?;
    need(!a.contains_key(HELPER)&&!a.values().any(|old|*old==uid)
        &&(10000..100000).contains(&uid)&&b.len()==a.len()+1&&a.iter().all(|(k,v)|b.get(k)==Some(v)),
        "full user-0 inventory changed beyond one distinct actual IHG helper")?;
    Ok(uid)
}

/// Raw command comparison retained in full, never a constructor for execution.
#[derive(Debug,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct CommandComparison {
    stdout:Vec<u8>,stderr:Vec<u8>,stderr_bytes:usize,stderr_sha256:String,
    #[serde(deserialize_with="closed")] receipt:ReadComparison,
}
impl CommandComparison {
    pub(crate) fn from_actual(output:&Output,receipt:&crate::production_application::ReadReceipt)->Result<Self> {
        let v=Self{stdout:output.stdout.clone(),stderr:output.stderr.clone(),stderr_bytes:output.stderr.len(),stderr_sha256:hash(&output.stderr),
            receipt:serde_json::from_value(serde_json::to_value(receipt).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?};Ok(v)
    }
    fn output(&self,state:bool)->Result<Output> {
        need(self.stdout.len()<=OUTPUT_LIMIT&&self.stderr.len()<=OUTPUT_LIMIT
            &&self.stderr_bytes==self.stderr.len()&&self.stderr_sha256==hash(&self.stderr),"IHG complete command output differs")?;
        let p=crate::production_application::ihg_helper_execution_profile(state);
        self.receipt.validate_for(Some(&self.stdout),&p,if state{STATE_LIMIT}else{ABSENCE_LIMIT})?;
        Ok(Output{status:self.receipt.status()?,stdout:self.stdout.clone(),stderr:self.stderr.clone()})
    }
}
#[derive(Debug,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IhgInstallReply {
    schema:String,request:IhgInstallRequest,
    #[serde(deserialize_with="closed")] before_main:RuntimeMainCustody,
    #[serde(deserialize_with="closed")] after_main:RuntimeMainCustody,
    #[serde(deserialize_with="closed")] before_inventory:UserZeroPackageInventoryFacts,
    #[serde(deserialize_with="closed")] after_inventory:UserZeroPackageInventoryFacts,
    absence:CommandComparison,
    #[serde(deserialize_with="crate::native_preparation_json::unique_json_value")] installation:Value,
    #[serde(deserialize_with="crate::native_preparation_json::unique_json_value")] payload_creator:Value,
}
impl IhgInstallReply {
    pub(crate) fn from_actual(request:IhgInstallRequest,before_main:RuntimeMainCustody,after_main:RuntimeMainCustody,
        before_inventory:UserZeroPackageInventoryFacts,after_inventory:UserZeroPackageInventoryFacts,
        absence:CommandComparison,installation:&crate::production_application::InstallObservation,
        payload:&crate::production_application::working_payload::CreatedPayload)->Result<Self> {
        let v=Self{schema:"droidloom.ihg-helper-install-reply.v2".into(),request,before_main,after_main,before_inventory,after_inventory,
            absence,installation:serde_json::to_value(installation).map_err(|e|e.to_string())?,
            payload_creator:payload.comparison()};
        v.validate(&v.request)?;Ok(v)
    }
    pub(crate) fn validate(&self,request:&IhgInstallRequest)->Result<u32> {
        request.validate()?;
        need(self.schema=="droidloom.ihg-helper-install-reply.v2"&&self.request==*request
            &&self.before_main==*request.main()&&self.after_main==*request.main()
            &&self.before_inventory.same_table(request.before_inventory()),"IHG install reply changed actual request/Main/preimage")?;
        let output=self.absence.output(false)?;
        need(output.status.success()&&output.stdout.is_empty()&&output.stderr.is_empty(),"IHG all-users retained helper absence was not observed")?;
        validate_installation(&self.installation)?;
        validate_payload_creator(&self.payload_creator)?;
        let uid=one_helper(&self.before_inventory,&self.after_inventory)?;
        need(serde_json::to_vec(self).map_err(|e|e.to_string())?.len()<=MAX_RESPONSE_BYTES,"IHG complete install reply too large")?;
        Ok(uid)
    }
    pub(crate) fn matches(&self,main:&RuntimeMainCustody,target:&ApplicationInspection)->bool {
        self.request.main==*main&&self.request.target==*target&&self.before_main==*main&&self.after_main==*main
    }
    pub(crate) fn comparison(&self)->Result<Value> {serde_json::to_value(self).map_err(|e|e.to_string())}
}
fn validate_payload_creator(v:&Value)->Result<()> {
    need(exact(v,&["schema","kind","apk_bytes","apk_sha256","material","creator","creation_limit_seconds",
        "retirement_reserve_seconds","caller_path_accepted","broker_created_payload"])
        &&v["schema"]=="droidloom.working-apk-payload.v1"&&v["kind"]=="ihg"
        &&v["apk_bytes"]==APK_BYTES&&v["apk_sha256"]==APK_SHA256
        &&v["creation_limit_seconds"]==120&&v["retirement_reserve_seconds"]==3
        &&v["caller_path_accepted"]==false&&v["broker_created_payload"]==false,
        "IHG payload did not come from its fixed normal creator")?;
    let r=&v["creator"];
    need(exact(r,&["pid","pidfd_device","pidfd_inode","waitid_code","waitid_status","actual_reaped"])
        &&r["pid"].as_u64().is_some_and(|p|p>1&&p<=i32::MAX as u64)
        &&r["pidfd_device"].as_u64().is_some_and(|p|p>0)
        &&r["pidfd_inode"].as_u64().is_some_and(|p|p>0)
        &&r["waitid_code"]==libc::CLD_EXITED&&r["waitid_status"]==0&&r["actual_reaped"]==true,
        "IHG payload creator did not actually retire")?;
    need(v["material"]["schema"]=="droidloom.held-prebuilt-helper-material.v2"
        &&v["material"]["package"]==HELPER&&v["material"]["installation_authority"]==false,
        "IHG fixed public helper source comparison differs")
}
fn validate_installation(v:&Value)->Result<()> {
    need(exact(v,&["session","user","bytes","segments","commands"])&&v["user"]==0&&v["bytes"]==APK_BYTES,"IHG actual atomic install shape differs")?;
    let id=v["session"].as_u64().filter(|n|*n>0&&*n<=i32::MAX as u64).ok_or("IHG actual session absent")?;
    let commands=v["commands"].as_array().ok_or("IHG actual install commands absent")?;
    let expected=[json!({"install":"CreateOnly","bytes":APK_BYTES}),json!({"install":"Write","session":id,"index":0,"bytes":APK_BYTES}),json!({"install":"Commit","session":id})];
    need(commands.len()==3,"IHG create/write/commit actual sequence required")?;
    let mut profile=crate::production_application::package_help_execution_profile();
    profile.process_selinux="u:r:droidloom_install:s0";
    for (record,wanted) in commands.iter().zip(expected) {
        need(exact(record,&["command","receipt"])&&record["command"]==wanted,"IHG actual create-only command differs")?;
        let receipt:ReadComparison=serde_json::from_value(record["receipt"].clone()).map_err(|e|e.to_string())?;
        receipt.validate_for(None,&profile,Duration::from_secs(110))?;
        need(receipt.status()?.success(),"IHG create-only command did not exit successfully")?;
    }
    let rows=v["segments"].as_array().ok_or("IHG segment observation absent")?;
    need(rows.len()==1&&exact(&rows[0],&["index","bytes","sha256"])&&rows[0]["index"]==0&&rows[0]["bytes"]==APK_BYTES&&rows[0]["sha256"]==APK_SHA256,"IHG installed segment differs from normal immutable APK")
}
#[derive(Debug,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IhgStateReply {
    schema:String,request:IhgStateRequest,
    #[serde(deserialize_with="closed")] before_main:RuntimeMainCustody,
    #[serde(deserialize_with="closed")] after_main:RuntimeMainCustody,
    command:CommandComparison,
}
impl IhgStateReply {
    pub(crate) fn from_actual(request:IhgStateRequest,before_main:RuntimeMainCustody,after_main:RuntimeMainCustody,command:CommandComparison)->Result<Self> {
        let v=Self{schema:"droidloom.ihg-helper-state-reply.v2".into(),request,before_main,after_main,command};
        v.output_for(&v.request)?;Ok(v)
    }
    pub(crate) fn output_for(&self,request:&IhgStateRequest)->Result<Output> {
        request.validate()?;
        need(self.schema=="droidloom.ihg-helper-state-reply.v2"&&self.request==*request
            &&self.before_main==*request.main()&&self.after_main==*request.main(),"IHG state reply changed actual Main or request")?;
        self.command.output(true)
    }
    pub(crate) fn matches(&self,main:&RuntimeMainCustody,target:&ApplicationInspection)->bool {
        self.request.main==*main&&self.request.target==*target&&self.before_main==*main&&self.after_main==*main
    }
    pub(crate) fn comparison(&self)->Result<Value> {serde_json::to_value(self).map_err(|e|e.to_string())}
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::control::application_probe::InstalledApk;
    fn binding()->MainBinding {
        MainBinding {main_epoch_sha256:"a".repeat(64),main_baseline_schema:"droidloom.native-leaf-business-baseline.v1".into(),
            main_baseline_sha256:"b".repeat(64),main_baseline_qualification_sha256:"c".repeat(64)}
    }
    fn state()->IhgStateRequest {
        let main=crate::main_custody::tests::sample();
        let target=ApplicationInspection {package:TARGET.into(),user:0,uid:10137,version_code:50023856,epoch:main.epoch.clone(),
            apks:vec![InstalledApk{name:"base.apk".into(),path:"/data/app/ihg/base.apk".into(),bytes:48083457,
                sha256:"7ecd61fd1be0541568705004f8a81f6914646c7e050fe9188283205968215ed0".into()}]};
        let helper=ApplicationInspection {package:HELPER.into(),user:0,uid:10987,version_code:1,epoch:main.epoch.clone(),
            apks:vec![InstalledApk{name:"base.apk".into(),path:"/data/app/fixed-helper/base.apk".into(),bytes:APK_BYTES,sha256:APK_SHA256.into()}]};
        IhgStateRequest{schema:"droidloom.ihg-helper-state-request.v2".into(),main,target,helper,binding:binding(),
            nonce:"d".repeat(32),deadline_monotonic_ns:encode_end(Instant::now()+Duration::from_secs(10),STATE_LIMIT).unwrap()}
    }
    #[test]
    fn ihg_static_state_is_closed_to_one_package_one_operation_and_exact_binding() {
        let original=state();original.validate().unwrap();
        let argv=original.logical_arguments().unwrap();
        assert_eq!(argv.len(),11);
        assert_eq!(&argv[..6],["/system/bin/am","instrument","-w","-r","-e","request"]);
        assert_eq!(&argv[7..9],["-e","main_binding"]);
        assert_eq!(argv.last().unwrap(),&format!("{HELPER}/{HELPER}.ActionRunner"));
        assert_eq!(argv[9],encode64(&binding().canonical().unwrap()));
        for field in ["argv","uid","path","domain","success"] {
            let mut value=serde_json::to_value(&original).unwrap();value[field]=json!("forbidden");
            assert!(serde_json::from_value::<IhgStateRequest>(value).is_err());
        }
        let mut changed=original.clone();changed.helper.apks[0].sha256="e".repeat(64);assert!(changed.validate().is_err());
        let mut changed=original.clone();changed.target.uid+=1;assert!(changed.validate().is_err());
        let mut changed=original.clone();changed.nonce="../".into();assert!(changed.validate().is_err());
    }
    #[test]
    fn ihg_binding_rejects_old_schema_unknown_fields_and_an_extended_original_end() {
        let actual=binding();actual.validate().unwrap();
        let raw=actual.canonical().unwrap();
        assert_eq!(serde_json::from_slice::<MainBinding>(&raw).unwrap(),actual);
        let mut value=actual.comparison().unwrap();value["success"]=true.into();
        assert!(serde_json::from_value::<MainBinding>(value).is_err());
        let mut changed=actual.clone();changed.main_baseline_schema="old".into();assert!(changed.validate().is_err());
        let original=state();
        let mut changed=original.clone();changed.deadline_monotonic_ns=monotonic_ns().unwrap()+21_000_000_000;
        assert!(changed.deadline().is_err());
        let mut changed=original;changed.deadline_monotonic_ns=1;assert!(changed.deadline().is_err());
    }
    #[test]
    fn ihg_installation_comparison_never_accepts_a_saved_success_or_replacement_shape() {
        for value in [json!({"success":true}),json!({"session":1,"user":0,"bytes":APK_BYTES,
            "segments":[{"index":0,"bytes":APK_BYTES,"sha256":APK_SHA256}],"commands":[]}),
            json!({"session":1,"user":0,"bytes":APK_BYTES,
                "segments":[],"commands":[{"command":{"install":"Create","user":0,"bytes":APK_BYTES},"receipt":{}}]})] {
            assert!(validate_installation(&value).is_err());
        }
    }
}
