//! Fixed late-born helper transactions for the six owned Documents/Gallery
//! cases. These messages contain comparison data. A deserialized message never
//! constructs the broker's live fixture lease or authorizes package retirement.
use crate::control::application_probe::ApplicationInspection;
use crate::main_custody::RuntimeMainCustody;
use crate::native_leaf_baseline::NativeLeafBaselineObservation;
use crate::native_leaf_fixture_material::NativeLeafFixtureKind as Kind;
use crate::native_package_help::ReadComparison;
use crate::package_inventory_observation::UserZeroPackageInventoryFacts;
use crate::production_application::apk_scope::NativeLeafApkRoute;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, process::Output, time::{Duration, Instant}};

type Result<T> = std::result::Result<T, String>;
use crate::control::physical_qualification_channel::budget;
pub(crate) const BEGIN_LIMIT: Duration = Duration::from_secs(budget::NATIVE_FIXTURE_BEGIN_SECONDS);
pub(crate) const GUARD_LIMIT: Duration = Duration::from_secs(budget::NATIVE_FIXTURE_GUARD_SECONDS);
pub(crate) const RETIRE_LIMIT: Duration = Duration::from_secs(budget::NATIVE_FIXTURE_RETIRE_SECONDS);
pub(crate) const RETENTION_LIMIT: Duration = Duration::from_secs(7200);
pub(crate) const ABSENCE_LIMIT: Duration = Duration::from_secs(8);
pub(crate) const REMOVE_LIMIT: Duration = Duration::from_secs(110);
pub(crate) const STATE_LIMIT: Duration = Duration::from_secs(15);
pub(crate) const STATE_OUTPUT_LIMIT: usize = 262144;
pub(crate) const OUTPUT_LIMIT: usize = 65536;
pub(crate) const MAX_RESPONSE_BYTES: usize = 1024 * 1024;
fn need(ok: bool, why: &str) -> Result<()> { if ok { Ok(()) } else { Err(why.into()) } }
pub(crate) fn hash(raw: &[u8]) -> String { format!("{:x}", Sha256::digest(raw)) }
fn digest(s: &str) -> bool { s.len() == 64 && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) }
fn exact(v: &Value, fields: &[&str]) -> bool {
    v.as_object().is_some_and(|o| o.len() == fields.len() && fields.iter().all(|k| o.contains_key(*k)))
}
fn monotonic_ns() -> Result<u64> {
    let mut t: libc::timespec = unsafe { std::mem::zeroed() };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut t) } != 0 { return Err(std::io::Error::last_os_error().to_string()); }
    need(t.tv_sec >= 0 && (0..1_000_000_000).contains(&t.tv_nsec), "fixture monotonic clock differs")?;
    (t.tv_sec as u64).checked_mul(1_000_000_000).and_then(|v| v.checked_add(t.tv_nsec as u64)).ok_or("fixture clock overflow".into())
}
fn encode_end(end: Instant, cap: Duration) -> Result<u64> {
    let clock = monotonic_ns()?;
    let left = end.checked_duration_since(Instant::now()).filter(|v| !v.is_zero()).ok_or("fixture original end elapsed")?.min(cap);
    clock.checked_add(u64::try_from(left.as_nanos()).map_err(|_| "fixture end overflow")?).ok_or("fixture end overflow".into())
}
fn decode_end(end: u64, cap: Duration) -> Result<Instant> {
    let now = Instant::now();
    let left = end.checked_sub(monotonic_ns()?).filter(|v| *v > 0).ok_or("fixture original end elapsed")?;
    need(u128::from(left) <= cap.as_nanos(), "fixture request enlarged its source cap")?;
    now.checked_add(Duration::from_nanos(left)).ok_or("fixture Instant overflow".into())
}
fn closed<'de, D, T>(de: D) -> std::result::Result<T, D::Error>
where D: serde::Deserializer<'de>, T: serde::de::DeserializeOwned + Serialize {
    let raw = crate::native_preparation_json::unique_json_value(de)?;
    let v: T = serde_json::from_value(raw.clone()).map_err(serde::de::Error::custom)?;
    if serde_json::to_value(&v).map_err(serde::de::Error::custom)? != raw { return Err(serde::de::Error::custom("unknown fixture comparison field")); }
    Ok(v)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FixtureAction { Begin, Guard, State, Retire }
impl FixtureAction {
    pub(crate) const fn cap(self) -> Duration { match self { Self::Begin => BEGIN_LIMIT, Self::Guard => GUARD_LIMIT,
        Self::State => Duration::from_secs(budget::NATIVE_FIXTURE_GUARD_SECONDS+15), Self::Retire => RETIRE_LIMIT } }
}

/// A source route is selected from the caller's already held business APK
/// interval. There is no package, UID, pathname, command, or MAC override.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NativeFixtureRequest {
    schema: String,
    action: FixtureAction,
    route: NativeLeafApkRoute,
    #[serde(deserialize_with = "closed")] main: RuntimeMainCustody,
    #[serde(deserialize_with = "closed")] primary: ApplicationInspection,
    begin_sha256: Option<String>,
    retention_monotonic_ns: u64,
    deadline_monotonic_ns: u64,
}
impl NativeFixtureRequest {
    pub(crate) fn begin(b: &NativeLeafBaselineObservation<'_>, route: NativeLeafApkRoute, end: Instant) -> Result<Self> {
        let retention_monotonic_ns=encode_end(b.deadline(),RETENTION_LIMIT)?;
        let v = Self { schema: "droidloom.native-fixture-request.v1".into(), action: FixtureAction::Begin, route,
            main: b.main().facts().clone(), primary: b.application().clone(), begin_sha256: None,
            retention_monotonic_ns,
            deadline_monotonic_ns: encode_end(end.min(b.deadline()), BEGIN_LIMIT)?.min(retention_monotonic_ns) };
        v.validate()?; Ok(v)
    }
    pub(crate) fn continuation(&self, action: FixtureAction, end: Instant) -> Result<Self> {
        need(self.action == FixtureAction::Begin && action != FixtureAction::Begin, "fixture continuation requires its original begin")?;
        let mut v = self.clone(); v.action = action; v.begin_sha256 = Some(self.identity()?);
        v.deadline_monotonic_ns = encode_end(end.min(self.retention_end()?), action.cap())?.min(v.retention_monotonic_ns);
        v.validate()?; Ok(v)
    }
    pub(crate) fn validate(&self) -> Result<()> {
        need(self.schema == "droidloom.native-fixture-request.v1", "fixture request schema differs")?;
        self.kind()?;
        self.main.validate(&self.primary.epoch)?;
        need(self.primary.package == self.route.package() && self.primary.user == 0
            && self.primary.epoch == self.main.epoch && self.primary.version_code > 0
            && (1..100_000).contains(&self.primary.uid) && !self.primary.apks.is_empty()
            && self.primary.apks.len() <= 32 && self.primary.apks.iter().filter(|a| a.name == "base.apk").count() == 1
            && self.primary.apks.iter().all(|a| a.bytes > 0 && digest(&a.sha256)),
            "fixture route is not the actually held original primary")?;
        need(match self.action { FixtureAction::Begin => self.begin_sha256.is_none(), _ => self.begin_sha256.as_deref().is_some_and(digest) },
            "fixture begin/continuation comparison differs")?;
        need(self.deadline_monotonic_ns <= self.retention_monotonic_ns, "fixture operation exceeds its original lifetime")?;
        self.deadline()?; self.retention_end()?; Ok(())
    }
    pub(crate) fn action(&self) -> FixtureAction { self.action }
    pub(crate) fn route(&self) -> NativeLeafApkRoute { self.route }
    pub(crate) fn kind(&self) -> Result<Kind> { Kind::for_route(self.route).map_err(|e| e.to_string()) }
    pub(crate) fn main(&self) -> &RuntimeMainCustody { &self.main }
    pub(crate) fn primary(&self) -> &ApplicationInspection { &self.primary }
    pub(crate) fn deadline(&self) -> Result<Instant> { decode_end(self.deadline_monotonic_ns, self.action.cap()) }
    pub(crate) fn retention_end(&self) -> Result<Instant> { decode_end(self.retention_monotonic_ns, RETENTION_LIMIT) }
    pub(crate) fn identity(&self) -> Result<String> { Ok(hash(&serde_json::to_vec(self).map_err(|e| e.to_string())?)) }
    pub(crate) fn matches_begin(&self, begin: &Self) -> Result<()> {
        self.validate()?;
        need(begin.action == FixtureAction::Begin && self.action != FixtureAction::Begin
            && self.route == begin.route && self.main == begin.main && self.primary == begin.primary
            && self.retention_monotonic_ns == begin.retention_monotonic_ns
            && self.begin_sha256.as_deref() == Some(begin.identity()?.as_str()),
            "fixture continuation does not match the retained live begin")
    }
}

pub(crate) fn helper(kind: Kind, main: &RuntimeMainCustody, app: &ApplicationInspection) -> Result<()> {
    main.validate(&app.epoch)?;
    need(app.epoch == main.epoch && app.package == kind.package() && app.user == 0
        && (10000..100000).contains(&app.uid) && app.version_code == kind.version_code()
        && app.apks.len() == 1 && app.apks[0].name == "base.apk"
        && app.apks[0].bytes == kind.apk_bytes() && app.apks[0].sha256 == kind.apk_sha256()
        && app.apks[0].path.starts_with("/data/app/") && app.apks[0].path.ends_with("/base.apk")
        && !app.apks[0].path.split('/').any(|v| v == "." || v == ".."),
        "late-born helper actual PM/complete APK identity differs")
}
fn added_uid(before: &BTreeMap<&str,u32>, after: &BTreeMap<&str,u32>, package: &str) -> Result<u32> {
    need(!before.contains_key(package) && after.len() == before.len() + 1
        && before.iter().all(|(p,u)| after.get(p) == Some(u)), "fixture changed a preexisting package or was already installed")?;
    let uid = *after.get(package).ok_or("fixture is absent from actual postinstall inventory")?;
    need((10000..20000).contains(&uid) && !before.values().any(|v| *v == uid), "fixture did not receive a distinct fresh user-0 UID")?;
    Ok(uid)
}
pub(crate) fn one_helper(kind: Kind, before: &UserZeroPackageInventoryFacts, after: &UserZeroPackageInventoryFacts) -> Result<u32> {
    before.validate(&after.epoch)?; after.validate(&before.epoch)?;
    added_uid(&before.records(), &after.records(), kind.package())
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FixtureCommandComparison {
    stdout: Vec<u8>, stderr: Vec<u8>,
    #[serde(deserialize_with = "closed")] receipt: ReadComparison,
}
impl FixtureCommandComparison {
    pub(crate) fn from_actual(out: &Output, receipt: &crate::production_application::ReadReceipt) -> Result<Self> {
        Ok(Self { stdout: out.stdout.clone(), stderr: out.stderr.clone(), receipt: serde_json::from_value(
            serde_json::to_value(receipt).map_err(|e| e.to_string())?).map_err(|e| e.to_string())? })
    }
    fn output(&self, remove: bool) -> Result<Output> {
        need(self.stdout.len() <= OUTPUT_LIMIT && self.stderr.len() <= OUTPUT_LIMIT, "fixture raw output exceeds its bound")?;
        let mut p = crate::production_application::package_help_execution_profile();
        if remove { p.process_selinux = "u:r:droidloom_install:s0"; }
        self.receipt.validate_for(Some(&self.stdout), &p, if remove { REMOVE_LIMIT } else { ABSENCE_LIMIT })?;
        Ok(Output { status: self.receipt.status()?, stdout: self.stdout.clone(), stderr: self.stderr.clone() })
    }
    pub(crate) fn require_output(&self, remove: bool, expected: &[u8]) -> Result<()> {
        let out = self.output(remove)?;
        need(out.status.success() && out.stdout == expected && out.stderr.is_empty(), "fixture actual package command did not return the exact complete output")
    }
}

pub(crate) fn validate_installation(v: &Value, kind: Kind) -> Result<()> {
    need(exact(v, &["session","user","bytes","segments","commands"])
        && v["user"] == 0 && v["bytes"] == kind.apk_bytes(), "fixture normal atomic installation shape differs")?;
    let id = v["session"].as_u64().filter(|n| *n > 0 && *n <= i32::MAX as u64).ok_or("fixture actual install session absent")?;
    let commands = v["commands"].as_array().ok_or("fixture actual install commands absent")?;
    let expected = [json!({"install":"CreateOnly","bytes":kind.apk_bytes()}),
        json!({"install":"Write","session":id,"index":0,"bytes":kind.apk_bytes()}), json!({"install":"Commit","session":id})];
    need(commands.len() == 3, "fixture requires one actual create-only/write/commit sequence")?;
    let mut profile = crate::production_application::package_help_execution_profile();
    profile.process_selinux = "u:r:droidloom_install:s0";
    for (row, wanted) in commands.iter().zip(expected) {
        need(exact(row, &["command","receipt"]) && row["command"] == wanted, "fixture install command differs")?;
        let receipt: ReadComparison = serde_json::from_value(row["receipt"].clone()).map_err(|e| e.to_string())?;
        need(serde_json::to_value(&receipt).map_err(|e| e.to_string())? == row["receipt"], "fixture install receipt has unknown fields")?;
        receipt.validate_for(None, &profile, REMOVE_LIMIT)?;
        need(receipt.status()?.success(), "fixture create-only command did not retire successfully")?;
    }
    let rows = v["segments"].as_array().ok_or("fixture actual segment observation absent")?;
    need(rows.len() == 1 && exact(&rows[0], &["index","bytes","sha256"])
        && rows[0]["index"] == 0 && rows[0]["bytes"] == kind.apk_bytes()
        && rows[0]["sha256"] == kind.apk_sha256(), "fixture installed complete segment differs from its fixed signed source")
}
pub(crate) fn validate_creator(v: &Value, kind: Kind) -> Result<()> {
    need(exact(v, &["schema","kind","apk_bytes","apk_sha256","material","creator","creation_limit_seconds",
        "retirement_reserve_seconds","caller_path_accepted","broker_created_payload"])
        && v["schema"] == "droidloom.working-apk-payload.v1"
        && v["kind"] == serde_json::to_value(kind).map_err(|e|e.to_string())?
        && v["apk_bytes"] == kind.apk_bytes() && v["apk_sha256"] == kind.apk_sha256()
        && v["creation_limit_seconds"] == 120 && v["retirement_reserve_seconds"] == 3
        && v["caller_path_accepted"] == false && v["broker_created_payload"] == false,
        "fixture payload did not come from its independent complete-source creator")?;
    let r = &v["creator"];
    need(exact(r, &["pid","pidfd_device","pidfd_inode","waitid_code","waitid_status","actual_reaped"])
        && r["pid"].as_u64().is_some_and(|n| n > 1 && n <= i32::MAX as u64)
        && r["pidfd_device"].as_u64().is_some_and(|n| n > 0) && r["pidfd_inode"].as_u64().is_some_and(|n| n > 0)
        && r["waitid_code"] == libc::CLD_EXITED && r["waitid_status"] == 0 && r["actual_reaped"] == true,
        "fixture original complete-payload creator was not actually reaped")?;
    need(v["material"]["package"] == kind.package() && v["material"]["apk_sha256"] == kind.apk_sha256()
        && v["material"]["certificate_sha256"] == kind.certificate_sha256()
        && v["material"]["installation_authority"] == false && v["material"]["guest_staging_used"] == false,
        "fixture held signed material comparison differs")
}

/// Complete stock content-call output and the actual factory retirement.
/// The fixed provider runs under its own app UID; no host app-data body is read.
#[derive(Debug,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FixtureStateComparison {
    stdout:Vec<u8>, stderr:Vec<u8>,
    #[serde(deserialize_with="closed")] receipt:ReadComparison,
}
impl FixtureStateComparison {
    pub(crate) fn from_actual(out:&Output,receipt:&crate::production_application::ReadReceipt)->Result<Self> {
        Ok(Self{stdout:out.stdout.clone(),stderr:out.stderr.clone(),receipt:serde_json::from_value(
            serde_json::to_value(receipt).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?})
    }
    fn validate(&self,kind:Kind,app:&ApplicationInspection)->Result<()> {
        need(self.stdout.len()<=STATE_OUTPUT_LIMIT && self.stderr.is_empty(),"fixed provider output bounds differ")?;
        self.receipt.validate_for(Some(&self.stdout),&crate::production_application::fixture_state_execution_profile(),STATE_LIMIT)?;
        need(self.receipt.status()?.success(),"fixed provider normal factory did not retire successfully")?;
        parse_state(&self.stdout,kind,app.uid).map(|_|())
    }
}
fn decode_state_base64(text:&str,maximum:usize)->Result<Vec<u8>> {
    crate::native_application_ui_protocol::decode64_bounded(text,maximum,false,false).map_err(|e|e.to_string())
}
pub(crate) fn parse_state(stdout:&[u8],kind:Kind,uid:u32)->Result<Value> {
    let text=std::str::from_utf8(stdout).map_err(|e|e.to_string())?;
    let encoded=text.strip_prefix("Result: Bundle[{reply=").and_then(|v|v.strip_suffix("}]\n"))
        .ok_or("fixed provider did not return exactly one complete Bundle string")?;
    let body=decode_state_base64(encoded,147456)?;
    let mut de=serde_json::Deserializer::from_slice(&body);
    let v=crate::native_preparation_json::unique_json_value(&mut de).map_err(|e|e.to_string())?;
    de.end().map_err(|e|e.to_string())?;
    validate_state(&v,kind,uid)?; Ok(v)
}
fn validate_state(v:&Value,kind:Kind,uid:u32)->Result<()> {
    need(exact(v,&["schema","package","run","uid","pid","caller_uid","ce","de","prefs",
        "process_selinux","started_elapsed_ns","finished_elapsed_ns","state_mutated","activity_started"])
        && v["schema"]=="droidloom.owned-fixture-state.v1" && v["package"]==kind.package()
        && v["run"]==kind.run_id() && v["uid"]==uid && (10000..20000).contains(&uid)
        && v["caller_uid"]==2000 && v["pid"].as_u64().is_some_and(|n|n>0 && n<=i32::MAX as u64)
        && v["state_mutated"]==false && v["activity_started"]==false,
        "fixed provider identity or read-only scope differs")?;
    // The helper reports its actual bounded kernel procattr bytes. UID and
    // data inodes are independently compared with live PM and held CE/DE.
    let label=&v["process_selinux"];
    need(exact(label,&["value","bytes","sha256","terminal_nul"]),"provider actual process context absent")?;
    let context=label["value"].as_str().ok_or("provider process context is not text")?;
    let categories=context.strip_prefix("u:r:untrusted_app_32:s0:")
        .ok_or("provider did not run in the selected target-33 application domain")?;
    let mut prior=None;let mut count=0;
    for category in categories.split(',') {
        let number=category.strip_prefix('c').and_then(|s|s.parse::<u16>().ok())
            .filter(|n|*n<1024).ok_or("provider MCS category differs")?;
        need(category==format!("c{number}") && prior.is_none_or(|p|p<number),"provider MCS categories are not canonical")?;
        prior=Some(number);count+=1;
    }
    need(count==4,"provider selected levelFrom=all context requires four categories")?;
    // Selected system image libselinux.so f53a7a8514698a3c8d047e60247e760f9d8a2f3bce845f6feb28c9da2755e0de:
    // its actual set_range_from_level (0xa500, 371 bytes) and seapp_context_lookup
    // normalize ordinary app IDs by 10000 and encode both app/user bytes.
    // This channel admits only normal user 0 helpers, never isolated/SDK UIDs.
    let app_id=uid-10000;
    need(context==format!("u:r:untrusted_app_32:s0:c{},c{},c512,c768",
        app_id&255,256+((app_id>>8)&255)),
        "provider MCS does not match the actual ordinary user-zero helper UID")?;
    let terminal=label["terminal_nul"].as_bool().ok_or("provider raw context terminator shape absent")?;
    let mut raw=context.as_bytes().to_vec();if terminal{raw.push(0);}
    need(raw.len()<=256 && label["bytes"]==raw.len() && label["sha256"]==hash(&raw),
        "provider complete raw context bytes or digest differ")?;
    let started=v["started_elapsed_ns"].as_u64().filter(|n|*n>0).ok_or("provider start clock absent")?;
    let finished=v["finished_elapsed_ns"].as_u64().filter(|n|*n>=started).ok_or("provider final clock differs")?;
    need(u128::from(finished-started)<=STATE_LIMIT.as_nanos(),"provider exceeded the fixed state read bound")?;
    for name in ["ce","de"] {
        let d=v[name].as_array().filter(|a|a.len()==5).ok_or("provider directory identity absent")?;
        need(d.iter().all(|n|n.as_u64().is_some()) && d[0].as_u64().is_some_and(|n|n>0)
            && d[1].as_u64().is_some_and(|n|n>0) && d[2].as_u64().is_some_and(|n|n&0o170022==0o040000)
            && d[3]==uid && d[4]==uid,"provider own CE/DE metadata differs")?;
    }
    need(v["ce"][0]==v["de"][0] && v["ce"][1]!=v["de"][1],"provider CE/DE directory alias")?;
    if !v["prefs"].is_null() {
        let p=&v["prefs"];
        need(exact(p,&["name","metadata","bytes","sha256","base64"])
            && p["name"]==kind.preference_name(),"provider changed its sole fixed preference name")?;
        let raw=decode_state_base64(p["base64"].as_str().ok_or("provider preference body absent")?,65536)?;
        need(!raw.is_empty() && p["bytes"]==raw.len() && p["sha256"]==hash(&raw),"provider whole preference bytes differ")?;
        let m=p["metadata"].as_array().filter(|a|a.len()==11).ok_or("provider preference metadata absent")?;
        need(m.iter().all(|n|n.as_i64().is_some()) && m[0]==v["ce"][0]
            && m[1].as_u64().is_some_and(|n|n>0) && m[2].as_u64().is_some_and(|n|n&0o170022==0o100000)
            && m[3]==uid && m[4]==uid && m[5]==1 && m[6]==raw.len()
            && m[8].as_u64().is_some_and(|n|n<1_000_000_000) && m[10].as_u64().is_some_and(|n|n<1_000_000_000),
            "provider preference ownership or single-file identity differs")?;
    }
    Ok(())
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NativeFixtureReply {
    schema: String, request: NativeFixtureRequest,
    #[serde(deserialize_with = "closed")] before_main: RuntimeMainCustody,
    #[serde(deserialize_with = "closed")] after_main: RuntimeMainCustody,
    #[serde(deserialize_with = "closed")] before_inventory: UserZeroPackageInventoryFacts,
    #[serde(deserialize_with = "closed")] after_inventory: UserZeroPackageInventoryFacts,
    #[serde(deserialize_with = "closed")] helper: ApplicationInspection,
    retained_before: FixtureCommandComparison,
    retained_after: Option<FixtureCommandComparison>,
    #[serde(deserialize_with = "crate::native_preparation_json::unique_json_value")] installation: Value,
    #[serde(deserialize_with = "crate::native_preparation_json::unique_json_value")] payload_creator: Value,
    retirement: Option<FixtureCommandComparison>,
    state: Option<FixtureStateComparison>,
    comparison_only: bool,
    business_accepted: bool,
}
impl NativeFixtureReply {
    pub(crate) fn actual(request: NativeFixtureRequest, before_main: RuntimeMainCustody, after_main: RuntimeMainCustody,
        before_inventory: UserZeroPackageInventoryFacts, after_inventory: UserZeroPackageInventoryFacts,
        helper: ApplicationInspection, retained_before: FixtureCommandComparison,
        retained_after: Option<FixtureCommandComparison>, installation: Value, payload_creator: Value,
        retirement: Option<FixtureCommandComparison>, state: Option<FixtureStateComparison>) -> Self {
        Self { schema:"droidloom.native-fixture-reply.v1".into(), request, before_main, after_main, before_inventory,
            after_inventory, helper, retained_before, retained_after, installation, payload_creator, retirement, state,
            comparison_only:true, business_accepted:false }
    }
    pub(crate) fn validate(&self, request: &NativeFixtureRequest, original: Option<&Self>) -> Result<()> {
        request.validate()?; let kind=request.kind()?;
        need(self.schema == "droidloom.native-fixture-reply.v1" && self.request == *request
            && self.before_main == *request.main() && self.after_main == *request.main()
            && self.comparison_only && !self.business_accepted, "fixture reply changed actual request/Main or claimed business acceptance")?;
        helper(kind, request.main(), &self.helper)?;
        self.before_inventory.validate(&request.main().epoch)?; self.after_inventory.validate(&request.main().epoch)?;
        validate_installation(&self.installation, kind)?; validate_creator(&self.payload_creator, kind)?;
        match (&self.state,request.action()) {
            (Some(actual),FixtureAction::State)=>{actual.validate(kind,&self.helper)?;},
            (None,action) if action!=FixtureAction::State=>{},
            _=>return Err("fixture state comparison does not match its fixed action".into()),
        }
        let installed_line = format!("package:{} uid:{}\n",kind.package(),self.helper.uid);
        match request.action() {
            FixtureAction::Begin => {
                need(original.is_none() && self.retirement.is_none() && self.retained_after.is_none(), "fixture begin cannot contain retirement or a prior installation")?;
                self.retained_before.require_output(false,b"")?;
                need(one_helper(kind,&self.before_inventory,&self.after_inventory)? == self.helper.uid, "fixture actual newly allocated UID differs")?;
            }
            FixtureAction::Guard | FixtureAction::State | FixtureAction::Retire => {
                let prior=original.ok_or("fixture continuation has no retained actual begin reply")?;
                request.matches_begin(&prior.request)?;
                need(self.helper == prior.helper && self.installation == prior.installation && self.payload_creator == prior.payload_creator
                    && self.before_inventory.same_table(&prior.after_inventory), "fixture continuation changed its actual installation preimage")?;
                self.retained_before.require_output(false,installed_line.as_bytes())?;
                if request.action() == FixtureAction::Retire {
                    self.retirement.as_ref().ok_or("fixture actual retirement command absent")?.require_output(true,b"Success\n")?;
                    self.retained_after.as_ref().ok_or("fixture postretirement retained-package observation absent")?.require_output(false,b"")?;
                    need(self.after_inventory.same_table(&prior.before_inventory), "fixture retirement did not restore the complete original package/UID table")?;
                } else {
                    need(self.retirement.is_none() && self.retained_after.is_none() && self.after_inventory.same_table(&prior.after_inventory),
                        "fixture guard changed its complete installed package table")?;
                }
            }
        }
        need(serde_json::to_vec(self).map_err(|e|e.to_string())?.len() <= MAX_RESPONSE_BYTES, "complete fixture reply exceeds its wire bound")
    }
    pub(crate) fn helper(&self) -> &ApplicationInspection { &self.helper }
    pub(crate) fn request(&self) -> &NativeFixtureRequest { &self.request }
    pub(crate) fn before_inventory(&self) -> &UserZeroPackageInventoryFacts { &self.before_inventory }
    pub(crate) fn after_inventory(&self) -> &UserZeroPackageInventoryFacts { &self.after_inventory }
    pub(crate) fn installation(&self) -> &Value { &self.installation }
    pub(crate) fn creator(&self) -> &Value { &self.payload_creator }
    pub(crate) fn state_value(&self)->Result<Option<Value>> {
        self.state.as_ref().map(|s|parse_state(&s.stdout,self.request.kind()?,self.helper.uid)).transpose()
    }
    pub(crate) fn comparison(&self) -> Result<Value> { serde_json::to_value(self).map_err(|e|e.to_string()) }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fixture_only_accepts_one_new_package_with_a_previously_unused_uid() {
        let before=BTreeMap::from([("android".into(),1000),("com.android.documentsui".into(),10022)]);
        let mut after=before.clone(); after.insert(Kind::DocumentsSaf.package().into(),10999);
        assert_eq!(added_uid(&before,&after,Kind::DocumentsSaf.package()).unwrap(),10999);
        for mutate in 0..5 {
            let mut changed=after.clone();
            match mutate { 0=>{changed.insert("android".into(),1001);},1=>{changed.insert("foreign.pkg".into(),10998);},
                2=>{changed.remove("android");},3=>{changed.insert(Kind::DocumentsSaf.package().into(),10022);},
                _=>{changed.insert(Kind::DocumentsSaf.package().into(),100_000);} }
            assert!(added_uid(&before,&changed,Kind::DocumentsSaf.package()).is_err());
        }
        assert!(added_uid(&after,&after,Kind::DocumentsSaf.package()).is_err());
    }
    #[test]
    fn fixture_source_routes_cannot_select_user_packages_or_creator_ihg() {
        for raw in [r#""ihg""#,r#"{"package":"com.sankuai.meituan.takeoutnew"}"#,r#"{"action":"retire","uid":10147}"#] {
            assert!(serde_json::from_str::<Kind>(raw).is_err());
        }
        assert!(Kind::for_route(NativeLeafApkRoute::IhgLondon).is_err());
        assert!(Kind::for_route(NativeLeafApkRoute::GalleryAlbum).is_ok());
        assert!(decode_end(encode_end(Instant::now()+Duration::from_secs(20),BEGIN_LIMIT).unwrap(),ABSENCE_LIMIT).is_err());
    }
    #[test]
    fn fixed_state_requires_actual_label_uid_whole_bytes_and_closed_fields() {
        let kind=Kind::DocumentsSaf;let uid=10999;
        let context="u:r:untrusted_app_32:s0:c231,c259,c512,c768";
        let mut v=json!({"schema":"droidloom.owned-fixture-state.v1","package":kind.package(),
            "run":kind.run_id(),"uid":uid,"pid":231,"caller_uid":2000,
            "ce":[19,20,0o40700,uid,uid],"de":[19,21,0o40700,uid,uid],"prefs":null,
            "process_selinux":{"value":context,"bytes":context.len()+1,
                "sha256":hash(format!("{context}\0").as_bytes()),"terminal_nul":true},
            "started_elapsed_ns":10,"finished_elapsed_ns":20,"state_mutated":false,"activity_started":false});
        validate_state(&v,kind,uid).unwrap();
        for mutate in 0..12 {
            let mut wrong=v.clone();
            match mutate {
                0=>wrong["uid"]=json!(uid+1),1=>wrong["package"]="com.android.settings".into(),
                2=>wrong["caller_uid"]=1000.into(),3=>wrong["ce"][1]=wrong["de"][1].clone(),
                4=>wrong["ce"][3]=1000.into(),5=>wrong["extra"]=true.into(),
                6=>wrong["process_selinux"]["value"]="u:r:untrusted_app_34:s0:c1,c256,c512,c768".into(),
                7=>wrong["process_selinux"]["sha256"]="0".repeat(64).into(),
                8=>wrong["process_selinux"]["value"]="u:r:untrusted_app_32:s0:c1,c1,c512,c768".into(),
                9=>wrong["process_selinux"]["value"]="u:r:untrusted_app_32:s0:c01,c256,c512,c768".into(),
                10=>wrong["state_mutated"]=true.into(),_=>wrong["finished_elapsed_ns"]=json!(15_000_000_011u64),
            }
            assert!(validate_state(&wrong,kind,uid).is_err(),"mutation {mutate}");
        }
        v["process_selinux"]["bytes"]=context.len().into();
        v["process_selinux"]["terminal_nul"]=false.into();
        v["process_selinux"]["sha256"]=hash(context.as_bytes()).into();
        validate_state(&v,kind,uid).unwrap();
        let mut wrong=v.clone();
        let other="u:r:untrusted_app_32:s0:c232,c259,c512,c768";
        wrong["process_selinux"]=json!({"value":other,"bytes":other.len(),"sha256":hash(other.as_bytes()),"terminal_nul":false});
        assert!(validate_state(&wrong,kind,uid).is_err());
        for other_uid in [9999,20000,99000,110999] {
            let mut wrong=v.clone();wrong["uid"]=other_uid.into();
            wrong["ce"][3]=other_uid.into();wrong["ce"][4]=other_uid.into();
            wrong["de"][3]=other_uid.into();wrong["de"][4]=other_uid.into();
            assert!(validate_state(&wrong,kind,other_uid).is_err());
        }
        assert!(parse_state(b"Result: Bundle[{reply=e30=}]\nextra\n",kind,uid).is_err());
        assert!(parse_state(b"Result: Bundle[{reply=e30=,other=x}]\n",kind,uid).is_err());
    }
}
