//! Owned physical qualification channel. It carries current execution facts,
//! never a saved report or a caller-supplied permission to qualify.
//!
//! The installed applications ELF owns both endpoints. The child still mints
//! Complete only inside its normal application factory; the parent retains a
//! different capture object, conditional on exact child exit and retirement.
use super::{BoundProcess, bounded_text, current_cgroup_parent, open_at, same_file};
use crate::control::application_probe::RuntimeEpoch;
use crate::main_custody::RuntimeMainCustody;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs::{self, File, OpenOptions};
use std::io;
use std::os::fd::AsRawFd;
use std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant};

#[path = "physical_qualification_capture.rs"]
mod capture;
#[path = "physical_qualification_socket.rs"]
mod socket;
#[path = "physical_qualification_source_custody.rs"]
mod source_custody;
#[path = "physical_qualification_working_config.rs"]
mod working_config;
#[path = "working_qualification_runtime.rs"]
pub(crate) mod working_runtime;
use super::application_leaf_unit::qualification::{ChildPeer, KernelProfile};
pub(crate) use capture::WorkingDocumentsBuildResources;
pub use capture::{
    CapturedCompleteApplicationRun, WorkingPreparationDirectory, WorkingQualificationOwner,
};
pub use source_custody::WorkingNativeSourceCustody;
/// Fixed independent return entry; actual role, unit and boot are verified before work.
pub fn dispatch_working_return(args: &[std::ffi::OsString]) -> io::Result<bool> {
    working_runtime::dispatch_working_return(args)
}
use working_config::AdmittedWorkingConfiguration;
pub use working_config::{WorkingPayloadPin, WorkingSourcePins};

#[path = "physical_qualification_budget.rs"]
pub mod budget;
#[path = "native_working_layout.rs"]
pub mod layout;
pub use budget::{
    CASE_COUNT, FAMILY_CASE_COUNT, NATIVE_CASE_COUNT, NOFILE_LIMIT, PHOTO_CASE_COUNT,
    RETIREMENT_SECONDS, SERVICE_SECONDS, SUITE_SECONDS,
};
pub const SUMMARY_LIMIT: usize = 16 * 1024 * 1024;
pub const BINDING_LIMIT: usize = 128 * 1024;
pub(super) const EXE: &str = crate::native_working_contract::APPLICATIONS_EXECUTABLE;
pub(super) const UNIT_NAME: &str = crate::native_working_contract::PARENT_UNIT;
pub(super) const UNIT_FRAGMENT: &str =
    "/usr/lib/systemd/system/droidloom-working-qualification.service";
pub(super) const UNIT_SOURCE: &str =
    include_str!("../../../packaging/systemd/system/droidloom-working-qualification.service");
pub(super) fn require_working_actor() -> io::Result<()> {
    working_config::current_actor().map(|_| ())
}
pub(super) fn require_parent_actor() -> io::Result<()> {
    working_config::require_actor(working_config::WorkingActor::Parent)
}
pub(super) fn require_suite_actor() -> io::Result<()> {
    working_config::require_actor(working_config::WorkingActor::Suite)
}

fn error(why: &str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, why)
}
pub(super) fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
pub(super) fn digest_ok(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
pub(super) fn monotonic_ns() -> io::Result<u64> {
    let mut time = std::mem::MaybeUninit::<libc::timespec>::uninit();
    // SAFETY: time points to correctly sized writable timespec storage.
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, time.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let time = unsafe { time.assume_init() };
    u64::try_from(i128::from(time.tv_sec) * 1_000_000_000 + i128::from(time.tv_nsec))
        .map_err(|_| error("monotonic time is outside its normal range"))
}
fn end_ns(end: Instant) -> io::Result<u64> {
    let clock = monotonic_ns()?;
    let remaining = end
        .checked_duration_since(Instant::now())
        .ok_or_else(|| error("original qualification deadline exhausted"))?;
    clock
        .checked_add(
            u64::try_from(remaining.as_nanos())
                .map_err(|_| error("qualification deadline overflow"))?,
        )
        .ok_or_else(|| error("qualification deadline overflow"))
}
pub(super) fn instant_until(ns: u64, ceiling: Instant) -> io::Result<Instant> {
    let instant = Instant::now();
    let now = monotonic_ns()?;
    let remaining = ns
        .checked_sub(now)
        .filter(|v| *v > 0)
        .ok_or_else(|| error("original monotonic qualification deadline exhausted"))?;
    instant
        .checked_add(Duration::from_nanos(remaining))
        .map(|end| end.min(ceiling))
        .ok_or_else(|| error("qualification instant overflow"))
}
pub(super) fn unit_name() -> &'static str {
    UNIT_NAME
}
pub(super) fn parent_argv() -> Vec<String> {
    vec![
        EXE.into(),
        crate::native_working_contract::PARENT_MODE.into(),
    ]
}
pub(super) fn child_argv(path: &Path, digest: &str) -> io::Result<Vec<String>> {
    if !digest_ok(digest) || path.file_name().and_then(|n| n.to_str()) != Some("PLAN.json") {
        return Err(error("exact held working plan required"));
    }
    Ok(vec![
        EXE.into(),
        "--physical-application-plan".into(),
        path.to_string_lossy().into_owned(),
        "--expect-physical-plan-sha256".into(),
        digest.into(),
    ])
}

/// Source-owned case order. This is not parsed from an external action string.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum QualificationCase {
    CalendarCore,
    CalendarReminder,
    CameraPhoto,
    ContactsSearch,
    ClockTimerPair,
    ClockAlarm,
    DocumentsSaf,
    DocumentsSearchSort,
    GalleryRotation,
    GalleryVideo,
    GallerySeek,
    GalleryAlbum,
    SettingsSupportedPages,
    IhgLondon,
    FamilyHyatt,
    FamilyMobileTicket,
    FamilyAmazon,
    FamilyDialer,
    FamilyMessaging,
    FamilyQuickSearch,
    FamilyBestBuy,
    FamilyNational,
    FamilyGoogleServices,
    FamilyHertz,
    FamilyHilton,
    FamilyJingdong,
    FamilyBeike,
    FamilyMarriott,
    FamilyAirChina,
    FamilyChinaEastern,
    FamilyMeituan,
    FamilyDidi,
    FamilyDouyin,
    FamilySzzc,
    FamilyTaobao,
    FamilyWeChat,
    FamilyUnited,
    FamilyPinduoduo,
    FamilyZhubajie,
    FamilyStreetEasy,
    FamilyCtrip,
    FamilyAna,
    FamilyFcitx,
    FamilyFirefox,
    FamilyBilibili,
    // Append after all original fourteen native and thirty-one family cases.
    CameraPhotoCaptureReopen,
}
impl QualificationCase {
    pub(super) fn ordinal(self) -> u8 {
        self as u8
    }
    pub(super) fn from_ordinal(value: u8) -> io::Result<Self> {
        const ALL: [QualificationCase; CASE_COUNT] = [
            QualificationCase::CalendarCore,
            QualificationCase::CalendarReminder,
            QualificationCase::CameraPhoto,
            QualificationCase::ContactsSearch,
            QualificationCase::ClockTimerPair,
            QualificationCase::ClockAlarm,
            QualificationCase::DocumentsSaf,
            QualificationCase::DocumentsSearchSort,
            QualificationCase::GalleryRotation,
            QualificationCase::GalleryVideo,
            QualificationCase::GallerySeek,
            QualificationCase::GalleryAlbum,
            QualificationCase::SettingsSupportedPages,
            QualificationCase::IhgLondon,
            QualificationCase::FamilyHyatt,
            QualificationCase::FamilyMobileTicket,
            QualificationCase::FamilyAmazon,
            QualificationCase::FamilyDialer,
            QualificationCase::FamilyMessaging,
            QualificationCase::FamilyQuickSearch,
            QualificationCase::FamilyBestBuy,
            QualificationCase::FamilyNational,
            QualificationCase::FamilyGoogleServices,
            QualificationCase::FamilyHertz,
            QualificationCase::FamilyHilton,
            QualificationCase::FamilyJingdong,
            QualificationCase::FamilyBeike,
            QualificationCase::FamilyMarriott,
            QualificationCase::FamilyAirChina,
            QualificationCase::FamilyChinaEastern,
            QualificationCase::FamilyMeituan,
            QualificationCase::FamilyDidi,
            QualificationCase::FamilyDouyin,
            QualificationCase::FamilySzzc,
            QualificationCase::FamilyTaobao,
            QualificationCase::FamilyWeChat,
            QualificationCase::FamilyUnited,
            QualificationCase::FamilyPinduoduo,
            QualificationCase::FamilyZhubajie,
            QualificationCase::FamilyStreetEasy,
            QualificationCase::FamilyCtrip,
            QualificationCase::FamilyAna,
            QualificationCase::FamilyFcitx,
            QualificationCase::FamilyFirefox,
            QualificationCase::FamilyBilibili,
            QualificationCase::CameraPhotoCaptureReopen,
        ];
        ALL.get(value as usize)
            .copied()
            .ok_or_else(|| error("unknown qualification case"))
    }
    /// Complete original case budget; resource acknowledgements consume this window.
    pub fn window_seconds(self) -> u64 {
        if self == Self::CameraPhotoCaptureReopen {
            budget::CAMERA_PHOTO_CASE_SECONDS
        } else if matches!(
            self,
            Self::FamilyAmazon
                | Self::FamilyBestBuy
                | Self::FamilyJingdong
                | Self::FamilyTaobao
                | Self::FamilyPinduoduo
        ) {
            budget::RETAIL_CASE_SECONDS
        } else {
            budget::NATIVE_CASE_WINDOWS
                .get(self as usize)
                .copied()
                .unwrap_or(budget::FAMILY_CASE_SECONDS)
        }
    }
    /// Only these compiled selected packages have a family case. No caller
    /// ordinal, profile, command, or budget is admitted through this lookup.
    pub fn for_family(package: &str) -> io::Result<Self> {
        match package {
            "com.Hyatt.hyt" => Ok(Self::FamilyHyatt),
            "com.MobileTicket" => Ok(Self::FamilyMobileTicket),
            "com.amazon.mShop.android.shopping" => Ok(Self::FamilyAmazon),
            "com.android.dialer" => Ok(Self::FamilyDialer),
            "com.android.messaging" => Ok(Self::FamilyMessaging),
            "com.android.quicksearchbox" => Ok(Self::FamilyQuickSearch),
            "com.bestbuy.android" => Ok(Self::FamilyBestBuy),
            "com.ehi.national.mobile" => Ok(Self::FamilyNational),
            "com.google.android.gms" => Ok(Self::FamilyGoogleServices),
            "com.hertz.android.digital" => Ok(Self::FamilyHertz),
            "com.hilton.android.hhonors" => Ok(Self::FamilyHilton),
            "com.jingdong.app.mall" => Ok(Self::FamilyJingdong),
            "com.lianjia.beike" => Ok(Self::FamilyBeike),
            "com.marriott.mrt" => Ok(Self::FamilyMarriott),
            "com.rytong.airchina" => Ok(Self::FamilyAirChina),
            "com.rytong.ceair" => Ok(Self::FamilyChinaEastern),
            "com.sankuai.meituan.takeoutnew" => Ok(Self::FamilyMeituan),
            "com.sdu.didi.psnger" => Ok(Self::FamilyDidi),
            "com.ss.android.ugc.aweme" => Ok(Self::FamilyDouyin),
            "com.szzc" => Ok(Self::FamilySzzc),
            "com.taobao.taobao" => Ok(Self::FamilyTaobao),
            "com.tencent.mm" => Ok(Self::FamilyWeChat),
            "com.united.mobile.android" => Ok(Self::FamilyUnited),
            "com.xunmeng.pinduoduo" => Ok(Self::FamilyPinduoduo),
            "com.zhubajie.client" => Ok(Self::FamilyZhubajie),
            "com.zillow.android.streeteasy" => Ok(Self::FamilyStreetEasy),
            "ctrip.android.view" => Ok(Self::FamilyCtrip),
            "jp.co.ana.android.tabidachi" => Ok(Self::FamilyAna),
            "org.fcitx.fcitx5.android" => Ok(Self::FamilyFcitx),
            "org.mozilla.firefox" => Ok(Self::FamilyFirefox),
            "tv.danmaku.bili" => Ok(Self::FamilyBilibili),
            _ => Err(error("package has no compiled physical family case")),
        }
    }
    pub(super) fn package(self) -> &'static str {
        match self {
            Self::CalendarCore => "com.android.calendar",
            Self::CalendarReminder => "com.android.calendar",
            Self::CameraPhoto | Self::CameraPhotoCaptureReopen => "com.android.camera2",
            Self::ContactsSearch => "com.android.contacts",
            Self::ClockTimerPair => "com.android.deskclock",
            Self::ClockAlarm => "com.android.deskclock",
            Self::DocumentsSaf => "com.android.documentsui",
            Self::DocumentsSearchSort => "com.android.documentsui",
            Self::GalleryRotation => "com.android.gallery3d",
            Self::GalleryVideo => "com.android.gallery3d",
            Self::GallerySeek => "com.android.gallery3d",
            Self::GalleryAlbum => "com.android.gallery3d",
            Self::SettingsSupportedPages => "com.android.settings",
            Self::IhgLondon => "com.ihg.apps.android",
            Self::FamilyHyatt => "com.Hyatt.hyt",
            Self::FamilyMobileTicket => "com.MobileTicket",
            Self::FamilyAmazon => "com.amazon.mShop.android.shopping",
            Self::FamilyDialer => "com.android.dialer",
            Self::FamilyMessaging => "com.android.messaging",
            Self::FamilyQuickSearch => "com.android.quicksearchbox",
            Self::FamilyBestBuy => "com.bestbuy.android",
            Self::FamilyNational => "com.ehi.national.mobile",
            Self::FamilyGoogleServices => "com.google.android.gms",
            Self::FamilyHertz => "com.hertz.android.digital",
            Self::FamilyHilton => "com.hilton.android.hhonors",
            Self::FamilyJingdong => "com.jingdong.app.mall",
            Self::FamilyBeike => "com.lianjia.beike",
            Self::FamilyMarriott => "com.marriott.mrt",
            Self::FamilyAirChina => "com.rytong.airchina",
            Self::FamilyChinaEastern => "com.rytong.ceair",
            Self::FamilyMeituan => "com.sankuai.meituan.takeoutnew",
            Self::FamilyDidi => "com.sdu.didi.psnger",
            Self::FamilyDouyin => "com.ss.android.ugc.aweme",
            Self::FamilySzzc => "com.szzc",
            Self::FamilyTaobao => "com.taobao.taobao",
            Self::FamilyWeChat => "com.tencent.mm",
            Self::FamilyUnited => "com.united.mobile.android",
            Self::FamilyPinduoduo => "com.xunmeng.pinduoduo",
            Self::FamilyZhubajie => "com.zhubajie.client",
            Self::FamilyStreetEasy => "com.zillow.android.streeteasy",
            Self::FamilyCtrip => "ctrip.android.view",
            Self::FamilyAna => "jp.co.ana.android.tabidachi",
            Self::FamilyFcitx => "org.fcitx.fcitx5.android",
            Self::FamilyFirefox => "org.mozilla.firefox",
            Self::FamilyBilibili => "tv.danmaku.bili",
        }
    }
    pub(super) fn native_route(self) -> Option<&'static str> {
        match self {
            Self::CalendarCore => Some("calendar_core"),
            Self::CalendarReminder => Some("calendar_reminder"),
            Self::CameraPhoto => Some("camera_photo"),
            Self::ContactsSearch => Some("contacts_search"),
            Self::ClockTimerPair => Some("clock_timer_pair"),
            Self::ClockAlarm => Some("clock_alarm"),
            Self::DocumentsSaf => Some("documents_saf"),
            Self::DocumentsSearchSort => Some("documents_search_sort"),
            Self::GalleryRotation => Some("gallery_rotation"),
            Self::GalleryVideo => Some("gallery_video"),
            Self::GallerySeek => Some("gallery_seek"),
            Self::GalleryAlbum => Some("gallery_album"),
            Self::SettingsSupportedPages => Some("settings_supported_pages"),
            Self::IhgLondon => Some("ihg_london"),
            _ => None,
        }
    }
    pub(super) fn profile(self) -> KernelProfile {
        if self == Self::CalendarReminder {
            KernelProfile::Calendar
        } else {
            KernelProfile::Standard
        }
    }
}

fn f9(file: &File) -> io::Result<[u64; 9]> {
    let m = file.metadata()?;
    let ns = |s: i64, n: i64| {
        u64::try_from(i128::from(s) * 1_000_000_000 + i128::from(n))
            .map_err(|_| error("negative qualification input timestamp"))
    };
    Ok([
        m.dev(),
        m.ino(),
        m.mode() as u64,
        m.uid() as u64,
        m.gid() as u64,
        m.nlink(),
        m.len(),
        ns(m.mtime(), m.mtime_nsec())?,
        ns(m.ctime(), m.ctime_nsec())?,
    ])
}

pub(super) struct Plan {
    pub path: PathBuf,
    pub file: File,
    pub pin: [u64; 9],
    pub digest: String,
    parents: Vec<(PathBuf, File, [u64; 9])>,
    configuration: Arc<AdmittedWorkingConfiguration>,
}
impl Plan {
    pub fn open(digest: &str) -> io::Result<Self> {
        if !digest_ok(digest) {
            return Err(error("exact working plan digest required"));
        }
        require_suite_actor()?;
        let configuration = Arc::new(AdmittedWorkingConfiguration::acquire()?);
        let plan = Self::open_admitted(configuration)?;
        if plan.digest != digest {
            return Err(error(
                "working plan differs from the parent's actual held input",
            ));
        }
        Ok(plan)
    }
    fn open_admitted(configuration: Arc<AdmittedWorkingConfiguration>) -> io::Result<Self> {
        configuration.guard()?;
        let path = configuration
            .runtime_evidence_directory()
            .join(layout::WORKING_PLAN_FILE);
        if path.canonicalize()? != path {
            return Err(error("physical plan path has an alias"));
        }
        let mut parents = Vec::new();
        for p in path
            .parent()
            .ok_or_else(|| error("physical plan parent absent"))?
            .ancestors()
        {
            let file = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(p)?;
            let pin = f9(&file)?;
            if pin[3..5] != [0, 0]
                || pin[2] & 0o022 != 0
                || (Some(p) == path.parent() && pin[2] & 0o7777 != 0o700)
            {
                return Err(error("root protected physical stage parent required"));
            }
            parents.push((p.into(), file, pin));
        }
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&path)?;
        let pin = f9(&file)?;
        if pin[2] != u64::from(libc::S_IFREG | 0o400)
            || pin[3..6] != [0, 0, 1]
            || pin[6] == 0
            || pin[6] > 4 * 1024 * 1024
        {
            return Err(error("root immutable regular physical plan required"));
        }
        if crate::native_hardware_label::label(&file)? != working_config::PLAN_LABEL {
            return Err(error("working PLAN lacks its immutable source-input label"));
        }
        let mut raw = vec![0; pin[6] as usize];
        crate::control::physical_qualification_channel::working_runtime::read_exact_at_progress(
            &file, &mut raw, 0,
        )?;
        if file.read_at(&mut [0; 1], pin[6])? != 0 || f9(&file)? != pin {
            return Err(error("working PLAN changed during initial whole read"));
        }
        let result = Self {
            path,
            file,
            pin,
            digest: sha(&raw),
            parents,
            configuration,
        };
        result.guard()?;
        Ok(result)
    }
    pub fn bytes(&self) -> io::Result<Vec<u8>> {
        let mut raw = vec![0; self.pin[6] as usize];
        crate::control::physical_qualification_channel::working_runtime::read_exact_at_progress(
            &self.file, &mut raw, 0,
        )?;
        if self.file.read_at(&mut [0; 1], self.pin[6])? != 0 || sha(&raw) != self.digest {
            return Err(error("actual whole physical plan differs"));
        }
        Ok(raw)
    }
    pub fn guard(&self) -> io::Result<()> {
        self.configuration.guard()?;
        for (p, file, pin) in &self.parents {
            let named = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(p)?;
            if f9(file)?[..5] != pin[..5] || f9(&named)?[..5] != pin[..5] {
                return Err(error("held physical stage parent changed"));
            }
        }
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&self.path)?;
        if f9(&self.file)? != self.pin
            || f9(&named)? != self.pin
            || crate::native_hardware_label::label(&self.file)? != working_config::PLAN_LABEL
            || crate::native_hardware_label::label(&named)? != working_config::PLAN_LABEL
        {
            return Err(error("held physical plan changed"));
        }
        self.bytes()?;
        if f9(&self.file)? != self.pin || f9(&named)? != self.pin {
            return Err(error("physical plan changed during whole read"));
        }
        Ok(())
    }
    pub(super) fn working_namespace_entry_pin(
        &self,
    ) -> io::Result<&crate::native_working_contract::WorkingNamespaceEntryPin> {
        self.configuration.guard()?;
        Ok(self.configuration.namespace_entry_pin())
    }
    pub(super) fn working_applications_pin(
        &self,
    ) -> io::Result<&crate::native_working_contract::PayloadPin> {
        self.configuration.guard()?;
        Ok(self.configuration.applications_pin())
    }
    pub(super) fn working_runtime_evidence_directory(&self) -> io::Result<&Path> {
        self.configuration.guard()?;
        Ok(self.configuration.runtime_evidence_directory())
    }
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Hello {
    pub plan_bytes: u64,
    pub plan_sha256: String,
    pub epoch: RuntimeEpoch,
    pub suite_seconds: u64,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct HelloAcknowledgement {
    pub owner_start_ns: u64,
    pub preparation_end_ns: u64,
}
impl HelloAcknowledgement {
    fn validate(&self, suite_end_ns: u64) -> io::Result<()> {
        let schedule = crate::native_working_contract::WorkingSchedule::selected();
        if schedule.authorization_end_ns(self.owner_start_ns)? != suite_end_ns
            || self
                .owner_start_ns
                .checked_add(budget::SOURCE_AND_CAPTURE_SECONDS * 1_000_000_000)
                != Some(self.preparation_end_ns)
        {
            return Err(error(
                "private parent ACK changed the original source preparation or suite end",
            ));
        }
        Ok(())
    }
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct CompleteHeader {
    pub summary_bytes: u64,
    pub summary_sha256: String,
    pub binding_bytes: u64,
    pub binding_sha256: String,
    pub selected_applications: u32,
    pub required_gates: u32,
}

/// The child-side private connection. It cannot be made from a saved receipt.
pub struct ChildChannel {
    socket: Option<socket::Socket>,
    peer: Arc<ChildPeer>,
    plan: Arc<Plan>,
    source: Option<WorkingNativeSourceCustody>,
    probe_scope: Option<super::working_owned_probe::Scope>,
    epoch: RuntimeEpoch,
    end: Instant,
    preparation_end: Instant,
    wire_end: u64,
    next_case: u8,
    sequence: u32,
    complete: bool,
}
impl ChildChannel {
    /// Called only by the normal physical factory after it reads its whole plan.
    pub fn acquire(
        path: &Path,
        bytes: u64,
        digest: &str,
        epoch: &RuntimeEpoch,
        original_end: Instant,
    ) -> io::Result<Self> {
        let plan = Arc::new(Plan::open(digest)?);
        if path != plan.path || bytes != plan.pin[6] {
            return Err(error(
                "child physical plan is not the exact parent-selected input",
            ));
        }
        let peer = Arc::new(ChildPeer::capture(&plan)?);
        let socket = socket::Socket::inherited()?;
        let wire_end = end_ns(original_end)?;
        let hello = Hello {
            plan_bytes: bytes,
            plan_sha256: digest.into(),
            epoch: epoch.clone(),
            suite_seconds: SUITE_SECONDS,
        };
        let mut result = Self {
            socket: Some(socket),
            peer,
            plan,
            source: None,
            probe_scope: None,
            epoch: epoch.clone(),
            end: original_end,
            preparation_end: original_end,
            wire_end,
            next_case: 0,
            sequence: 0,
            complete: false,
        };
        let ack = result.exchange(1, 255, wire_end, serde_json::to_vec(&hello)?, original_end)?;
        if ack.end_ns > wire_end {
            return Err(error("parent attempted to extend the suite window"));
        }
        result.wire_end = ack.end_ns;
        result.end = instant_until(ack.end_ns, original_end)?;
        let acknowledgement: HelloAcknowledgement = serde_json::from_slice(&ack.payload)?;
        acknowledgement.validate(ack.end_ns)?;
        result.preparation_end = instant_until(acknowledgement.preparation_end_ns, result.end)?;
        result.source = Some(WorkingNativeSourceCustody::from_hello(
            Arc::clone(&result.peer),
            Arc::clone(&result.plan),
            result.end,
        )?);
        result.probe_scope = Some(super::working_owned_probe::Scope::child(
            &result.peer,
            result.end,
        )?);
        Ok(result)
    }
    pub fn deadline(&self) -> Instant {
        self.end
    }
    /// The same preparation end admitted from the actual parent's first start.
    pub fn preparation_deadline(&self) -> Instant {
        self.preparation_end
    }
    /// Retain the one actual inherited source owner after the private Hello ACK.
    pub fn working_source_custody(&self) -> io::Result<WorkingNativeSourceCustody> {
        self.peer.guard()?;
        self.plan.guard()?;
        let source = self
            .source
            .as_ref()
            .ok_or_else(|| error("working source Hello has not completed"))?;
        source.guard()?;
        Ok(source.retained())
    }
    fn exchange(
        &mut self,
        kind: u8,
        case: u8,
        wire_end: u64,
        payload: Vec<u8>,
        end: Instant,
    ) -> io::Result<socket::Packet> {
        self.peer.guard()?;
        self.plan.guard()?;
        if let Some(source) = &self.source {
            source.guard()?;
        }
        if self.complete || end > self.end {
            return Err(error("qualification channel is closed or extended"));
        }
        let socket = self
            .socket
            .as_ref()
            .ok_or_else(|| error("qualification channel was cancelled"))?;
        let packet = socket::Packet {
            sequence: self.sequence,
            kind,
            case,
            end_ns: wire_end,
            payload,
        };
        socket.send(&packet, end)?;
        let ack = socket.receive(self.peer.parent_pid(), end)?;
        if ack.kind != 5
            || ack.sequence != self.sequence
            || ack.case != case
            || (kind != 1 && !ack.payload.is_empty())
            || (kind == 1 && (ack.payload.is_empty() || ack.payload.len() > 256))
        {
            self.socket.take();
            return Err(error(
                "qualification acknowledgement differs from this exact request",
            ));
        }
        self.peer.guard()?;
        self.plan.guard()?;
        if let Some(source) = &self.source {
            source.guard()?;
        }
        if Instant::now() >= end {
            return Err(error(
                "qualification acknowledgement exceeded original deadline",
            ));
        }
        self.sequence += 1;
        Ok(ack)
    }
    /// Begin exactly the next compiled case after the original case_end exists.
    pub fn begin_case(
        &mut self,
        case: QualificationCase,
        case_end: Instant,
    ) -> io::Result<CaseGuard<'_>> {
        if case.ordinal() != self.next_case
            || case_end > self.end
            || case_end
                .checked_duration_since(Instant::now())
                .is_none_or(|d| d > Duration::from_secs(case.window_seconds()))
        {
            return Err(error("qualification case order or original window differs"));
        }
        let wire = end_ns(case_end)?.min(self.wire_end);
        let ack = self.exchange(2, case.ordinal(), wire, Vec::new(), case_end)?;
        if ack.end_ns != wire {
            return Err(error("case resource ACK changed its original deadline"));
        }
        Ok(CaseGuard {
            channel: self,
            case,
            end: case_end,
            wire_end: wire,
            finished: false,
        })
    }
    /// The caller retains its actual Complete/source/results until this ACK.
    /// This method never reconstructs Complete from the serialized comparison.
    pub fn complete(
        &mut self,
        summary: &[u8],
        binding: &RuntimeMainCustody,
        end: Instant,
    ) -> io::Result<()> {
        if self.next_case as usize != CASE_COUNT
            || summary.is_empty()
            || summary.len() > SUMMARY_LIMIT
            || end > self.end
            || binding.epoch != self.epoch
        {
            return Err(error(
                "complete qualification requires all exact case boundaries and same Main",
            ));
        }
        binding.validate(&self.epoch).map_err(|e| error(&e))?;
        let body = serde_json::to_vec(binding)?;
        if body.len() > BINDING_LIMIT {
            return Err(error("complete Main comparison body exceeds bound"));
        }
        let header = CompleteHeader {
            summary_bytes: summary.len() as u64,
            summary_sha256: sha(summary),
            binding_bytes: body.len() as u64,
            binding_sha256: sha(&body),
            selected_applications: 39,
            required_gates: 377,
        };
        let mut payload = serde_json::to_vec(&header)?;
        payload.push(b'\n');
        payload.extend_from_slice(&body);
        let ack = self.exchange(4, 255, self.wire_end, payload, end)?;
        if ack.end_ns != self.wire_end {
            return Err(error("Complete ACK changed the suite deadline"));
        }
        self.complete = true;
        self.socket.take();
        Ok(())
    }
}

/// Drop cancels the private connection. It never fabricates a completed case.
pub struct CaseGuard<'a> {
    channel: &'a mut ChildChannel,
    case: QualificationCase,
    end: Instant,
    wire_end: u64,
    finished: bool,
}
impl CaseGuard<'_> {
    /// Call only after consuming the original case's successful historical seal.
    pub fn finish_after_history(mut self, original_case_end: Instant) -> io::Result<()> {
        if original_case_end != self.end {
            return Err(error("case end cannot be replaced"));
        }
        let ack =
            self.channel
                .exchange(3, self.case.ordinal(), self.wire_end, Vec::new(), self.end)?;
        if ack.end_ns != self.wire_end {
            return Err(error("case retirement ACK changed its end"));
        }
        self.channel.next_case += 1;
        self.finished = true;
        Ok(())
    }
}
impl Drop for CaseGuard<'_> {
    fn drop(&mut self) {
        if !self.finished {
            self.channel.socket.take();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fixed_case_order_and_window_preserve_all_original_budgets() {
        let mut total = 0;
        for n in 0..14 {
            let c = QualificationCase::from_ordinal(n).unwrap();
            assert_eq!(c.ordinal(), n);
            total += c.window_seconds();
            assert_eq!(
                c.profile(),
                if n == 1 {
                    KernelProfile::Calendar
                } else {
                    KernelProfile::Standard
                }
            );
        }
        assert_eq!(total, 25_430);
        assert_eq!(total, budget::NATIVE_SECONDS);
        assert_eq!(
            total
                + budget::FAMILY_SECONDS
                + budget::CAMERA_PHOTO_CASE_SECONDS
                + 140
                + budget::SOURCE_AND_CAPTURE_SECONDS,
            SUITE_SECONDS
        );
        assert_eq!(budget::SOURCE_AND_CAPTURE_SECONDS, 46_622);
        assert_eq!(SUITE_SECONDS, 195_672);
        assert_eq!(SERVICE_SECONDS, 195_852);
        assert_eq!(budget::RETAIL_WORK_SECONDS, 8_690);
        assert_eq!(CASE_COUNT, 46);
        assert_eq!(PHOTO_CASE_COUNT, 1);
        assert_eq!(QualificationCase::CameraPhoto.ordinal(), 2);
        assert_eq!(QualificationCase::CameraPhoto.window_seconds(), 1_260);
        assert_eq!(QualificationCase::FamilyBilibili.ordinal(), 44);
        let photo = QualificationCase::from_ordinal(45).unwrap();
        assert_eq!(photo, QualificationCase::CameraPhotoCaptureReopen);
        assert_eq!(photo.package(), "com.android.camera2");
        assert_eq!(photo.window_seconds(), 250 + 4_040);
        assert_eq!(photo.profile(), KernelProfile::Standard);
        assert!(photo.native_route().is_none());
        assert!(QualificationCase::for_family(photo.package()).is_err());
        assert!(QualificationCase::from_ordinal(CASE_COUNT as u8).is_err());
        assert!(child_argv(Path::new("/PLAN.json"), "../caller").is_err());
    }
    #[test]
    fn physical_family_channel_rejects_foreign_native_and_reordered_cases() {
        let mut selected = std::collections::BTreeSet::new();
        for ordinal in NATIVE_CASE_COUNT..NATIVE_CASE_COUNT + FAMILY_CASE_COUNT {
            let case = QualificationCase::from_ordinal(ordinal as u8).unwrap();
            assert_eq!(case.ordinal() as usize, ordinal);
            assert_eq!(QualificationCase::for_family(case.package()).unwrap(), case);
            assert!(case.native_route().is_none());
            let retail = matches!(
                case,
                QualificationCase::FamilyAmazon
                    | QualificationCase::FamilyBestBuy
                    | QualificationCase::FamilyJingdong
                    | QualificationCase::FamilyTaobao
                    | QualificationCase::FamilyPinduoduo
            );
            assert_eq!(case.window_seconds(), if retail { 8_940 } else { 2_865 });
            assert_eq!(case.profile(), KernelProfile::Standard);
            assert!(selected.insert(case.package()));
        }
        assert_eq!(selected.len(), FAMILY_CASE_COUNT);
        for ordinal in 0..NATIVE_CASE_COUNT {
            let case = QualificationCase::from_ordinal(ordinal as u8).unwrap();
            assert!(QualificationCase::for_family(case.package()).is_err());
            assert!(case.native_route().is_some());
        }
        for package in [
            "",
            "../caller",
            "com.android.permissioncontroller",
            "org.droidloom.qa.editorcontract",
            "com.Hyatt.hyt ",
            "com.hyatt.hyt",
            "caller.package",
        ] {
            assert!(QualificationCase::for_family(package).is_err(), "{package}");
        }
        assert_eq!(QualificationCase::FamilyHyatt.ordinal(), 14);
        assert_eq!(QualificationCase::FamilyBilibili.ordinal(), 44);
    }

    #[test]
    fn physical_family_template_and_shared_budget_preserve_the_fixed_owner_bounds() {
        let lines: std::collections::BTreeSet<_> = UNIT_SOURCE.lines().collect();
        for line in [
            format!("RuntimeMaxSec={}s", SERVICE_SECONDS),
            format!("TimeoutStopSec={}s", RETIREMENT_SECONDS),
            format!("LimitNOFILE={NOFILE_LIMIT}"),
        ] {
            assert!(lines.contains(line.as_str()), "{line}");
        }
        assert_eq!(NOFILE_LIMIT, 32_768);
        assert_eq!(SERVICE_SECONDS, 195_852);
        assert!(lines.contains("MemoryMax=2147483648"));
        assert!(lines.contains("MemorySwapMax=0"));
        assert!(lines.contains("CPUQuota=200%"));
        assert!(lines.contains("TasksMax=64"));
    }
}

/// Fence each privileged installed ELF before Clap handles help or public actions.
/// The actual SELinux and independent AppArmor entry must agree. The fixed
/// parent and suite use different domains; this parser grants no write authority.
pub fn admit_working_entry(arguments: &[std::ffi::OsString]) -> io::Result<()> {
    let requested = arguments.first().is_some_and(|v| {
        v == crate::native_working_contract::PARENT_MODE || v == "--physical-application-plan"
    });
    let role = crate::native_hardware_label::current(101);
    let actor = role
        .as_ref()
        .ok()
        .and_then(|v| working_config::WorkingActor::from_role(v));
    let privileged_leaf = role.as_ref().is_ok_and(|v| v == layout::WORKING_LEAF_ROLE);
    if !requested && actor.is_none() && !privileged_leaf {
        return Ok(());
    }
    let actor =
        actor.ok_or_else(|| error("working mode requires its actual parent or suite domain"))?;
    if !working_entry_arguments(actor, arguments) {
        return Err(error(
            "working entry mode differs from its actual parent or suite domain",
        ));
    }
    working_config::require_actor(actor)
}
fn working_entry_arguments(
    actor: working_config::WorkingActor,
    arguments: &[std::ffi::OsString],
) -> bool {
    use working_config::WorkingActor;
    match (actor, arguments) {
        (WorkingActor::Parent, [mode]) => mode == crate::native_working_contract::PARENT_MODE,
        (WorkingActor::Suite, [mode, path, expected, digest]) => {
            mode == "--physical-application-plan"
                && expected == "--expect-physical-plan-sha256"
                && layout::fixed_plan_path(Path::new(path))
                && digest.to_str().is_some_and(digest_ok)
        }
        _ => false,
    }
}
#[cfg(test)]
mod working_entry_tests {
    use super::*;
    #[test]
    fn physical_working_entry_binds_real_child_shape_to_suite_domain_only() {
        use working_config::WorkingActor;
        let parent = vec![std::ffi::OsString::from(
            crate::native_working_contract::PARENT_MODE,
        )];
        let plan = layout::working_candidate_directory(&"a".repeat(64))
            .unwrap()
            .join(layout::WORKING_EVIDENCE_DIRECTORY)
            .join(layout::WORKING_PLAN_FILE);
        let child = child_argv(&plan, &"b".repeat(64))
            .unwrap()
            .into_iter()
            .skip(1)
            .map(std::ffi::OsString::from)
            .collect::<Vec<_>>();
        assert!(working_entry_arguments(WorkingActor::Parent, &parent));
        assert!(working_entry_arguments(WorkingActor::Suite, &child));
        assert!(!working_entry_arguments(WorkingActor::Parent, &child));
        assert!(!working_entry_arguments(WorkingActor::Suite, &parent));
        for actor in [WorkingActor::Parent, WorkingActor::Suite] {
            for args in [
                vec![],
                vec!["--help".into()],
                vec!["list".into()],
                vec![
                    "--owned-physical-application-plan".into(),
                    "b".repeat(64).into(),
                ],
            ] {
                assert!(!working_entry_arguments(actor, &args));
            }
        }
        let mut wrong = child.clone();
        wrong[1] = "/PLAN.json".into();
        assert!(!working_entry_arguments(WorkingActor::Suite, &wrong));
        let mut wrong = child.clone();
        wrong.push("--json".into());
        assert!(!working_entry_arguments(WorkingActor::Suite, &wrong));
    }
}
