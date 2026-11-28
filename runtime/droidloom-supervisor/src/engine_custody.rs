//! Comparison records for one live application's positively observed runtime.
//!
//! These serializable records carry no authority. Only the authenticated normal
//! inspector constructs EngineMappingObservation after the actual owner returns
//! its held process, image and mapping observations.
use crate::control::application_custody::{CustodyFileIdentity, CustodyImage, CustodyNamespace};
use crate::control::application_probe::{ApplicationMetadata, RuntimeEpoch};
use crate::main_custody::{MainNodeIdentity, RuntimeMainCustody};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

#[path = "production_native_engine_profile.rs"]
pub(crate) mod native_profile;

pub const SCHEMA: &str = "droidloom.running-application-engine.v2";
pub const ENGINE_PATH: &str = "/system/system_ext/lib64/libberberis_arm64.so";
pub const ENGINE_RELATIVE: &str = "system/system_ext/lib64/libberberis_arm64.so";
pub const MAX_ENGINE_BYTES: u64 = 128 * 1024 * 1024;
pub const MAX_MAP_BYTES: usize = 2 * 1024 * 1024;
pub const MAX_ENGINE_MAPPINGS: usize = 64;
pub const MAX_WIRE_BYTES: usize = 128 * 1024;

/// Conditional process-label candidates from the selected immutable platform
/// seapp rules and the source-admitted 39-package SDK roster. These names bound
/// this observer; they do not infer a live UID, privilege or signer. Any actual
/// vendor/other process type outside this closed set is rejected.
pub(crate) const APP_TYPES: &[&str] = &[
    "gmscore_app",
    "platform_app",
    "platform_app_36",
    "priv_app",
    "priv_app_36",
    "system_app",
    "untrusted_app",
    "untrusted_app_25",
    "untrusted_app_27",
    "untrusted_app_29",
    "untrusted_app_30",
    "untrusted_app_32",
    "untrusted_app_34",
];

/// Exact source-admitted apps41 selection names. This only bounds the request;
/// actual UID, APK bytes, label, process and engine remain live observations.
pub(crate) const SELECTED_PACKAGES: &[&str] = &[
    "com.Hyatt.hyt",
    "com.MobileTicket",
    "com.amazon.mShop.android.shopping",
    "com.android.calendar",
    "com.android.camera2",
    "com.android.contacts",
    "com.android.deskclock",
    "com.android.dialer",
    "com.android.documentsui",
    "com.android.gallery3d",
    "com.android.messaging",
    "com.android.quicksearchbox",
    "com.android.settings",
    "com.bestbuy.android",
    "com.ehi.national.mobile",
    "com.google.android.gms",
    "com.hertz.android.digital",
    "com.hilton.android.hhonors",
    "com.ihg.apps.android",
    "com.jingdong.app.mall",
    "com.lianjia.beike",
    "com.marriott.mrt",
    "com.rytong.airchina",
    "com.rytong.ceair",
    "com.sankuai.meituan.takeoutnew",
    "com.sdu.didi.psnger",
    "com.ss.android.article.news",
    "com.ss.android.lark",
    "com.ss.android.ugc.aweme",
    "com.szzc",
    "com.taobao.taobao",
    "com.tencent.mm",
    "com.united.mobile.android",
    "com.xunmeng.pinduoduo",
    "com.zhubajie.client",
    "com.zillow.android.streeteasy",
    "ctrip.android.view",
    "jp.co.ana.android.tabidachi",
    "org.fcitx.fcitx5.android",
    "org.mozilla.firefox",
    "tv.danmaku.bili",
];
pub(crate) fn selected_package(value: &str) -> bool {
    SELECTED_PACKAGES.contains(&value)
}

/// A VMA read from the actual target's procfs, restricted to the fixed engine.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct EngineMapping {
    pub start: u64,
    pub end: u64,
    pub permissions: String,
    pub offset: u64,
    pub device: u64,
    pub inode: u64,
    pub path: String,
}

/// File identity in the actual target USERNS; ownership is checked per source.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct EngineFile {
    pub identity: CustodyFileIdentity,
    pub sha256: String,
}

/// A private immutable image owner's comparison projection.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct BridgeEngineImageSource {
    pub base_cohort_sha256: String,
    pub library_image: CustodyImage,
    pub engine: EngineFile,
    pub whole_image_body_rehashed_by_this_observation: bool,
}

/// Source-owned route selector. A wire value alone conveys no authority.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum EngineKind {
    BerberisArm64,
    NativeX86_64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct NativeArtInput {
    pub name: String,
    pub version: u64,
    pub container_bytes: u64,
    pub container_sha256: String,
    pub original_apex_bytes: u64,
    pub original_apex_sha256: String,
    pub payload_bytes: u64,
    pub payload_sha256: String,
    pub member_path: String,
    pub member_bytes: u64,
    pub member_sha256: String,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct NativeEngineImageSource {
    pub base_cohort_sha256: String,
    pub system_image: CustodyImage,
    pub art_input: NativeArtInput,
    pub whole_image_body_rehashed_by_this_observation: bool,
    /// The normal original APEX/VINTF/AVB lifecycle is a separate gate.
    pub apex_mount_owner_borrowed: bool,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "route", deny_unknown_fields)]
pub enum EngineImageSource {
    #[serde(rename = "berberis_arm64")]
    BerberisArm64 { image: BridgeEngineImageSource },
    #[serde(rename = "native_x86_64")]
    NativeX86_64 { image: NativeEngineImageSource },
}
impl EngineImageSource {
    pub fn kind(&self) -> EngineKind {
        match self {
            Self::BerberisArm64 { .. } => EngineKind::BerberisArm64,
            Self::NativeX86_64 { .. } => EngineKind::NativeX86_64,
        }
    }
    pub(crate) fn validate_origin(&self, main: &RuntimeMainCustody) -> Result<(), String> {
        match self {
            Self::BerberisArm64 { image: src } => need(
                src.base_cohort_sha256 == main.owner.base_cohort_sha256
                    && src.library_image.role == "system_ext_lib64"
                    && src.library_image.file.bytes >= 4096
                    && digest(&src.library_image.sha256)
                    && src.library_image.loop_source_device == src.library_image.file.device
                    && src.library_image.loop_source_inode == src.library_image.file.inode
                    && src.library_image.loop_device == src.library_image.mount_root.device
                    && src.library_image.mount_id > 0
                    && src.engine.identity.device == src.library_image.mount_root.device
                    && !src.whole_image_body_rehashed_by_this_observation
                    && valid_engine(&src.engine),
                "fixed bridge lacks its original immutable image owner",
            ),
            Self::NativeX86_64 { image: src } => need(
                src.base_cohort_sha256 == main.owner.base_cohort_sha256
                    && src.system_image.role == "system"
                    && src.system_image.file.bytes
                        == crate::production_execution_profile::SYSTEM_BYTES
                    && src.system_image.sha256
                        == crate::production_execution_profile::SYSTEM_SHA256
                    && src.system_image.loop_source_device == src.system_image.file.device
                    && src.system_image.loop_source_inode == src.system_image.file.inode
                    && src.system_image.loop_device == src.system_image.mount_root.device
                    && src.system_image.mount_id > 0
                    && src.art_input == native_profile::art_input().map_err(str::to_owned)?
                    && !src.whole_image_body_rehashed_by_this_observation
                    && !src.apex_mount_owner_borrowed,
                "native runtime differs from its actual selected system and fixed ART source",
            ),
        }
    }
}
/// Read from the actual mapped file descriptor, not supplied by AMS.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct EngineFileMount {
    pub filesystem_type: i64,
    pub mount_flags: u64,
    pub mount_id: u64,
}
impl EngineFileMount {
    pub(crate) fn readonly_ext4(&self) -> bool {
        self.filesystem_type == 0xef53
            && self.mount_flags & 1 != 0
            && self.mount_flags & 8 == 0
            && self.mount_id > 0
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct NativeExecutableObservation {
    pub file: EngineFile,
    pub mappings: Vec<EngineMapping>,
    pub mount: EngineFileMount,
    pub art_mount: EngineFileMount,
}
/// Two bounded normal AMS reads are comparison facts. The actual PIDFD,
/// namespace, UID and maps are independently obtained from the live owner.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct EngineAbiComparison {
    pub guest_pid: u32,
    pub uid: u32,
    pub user: u32,
    pub process_name: String,
    pub required_abi: String,
    pub instruction_set: Option<String>,
    pub start_seq: u64,
    pub before_query_sha256: String,
    pub after_query_sha256: String,
}
impl EngineAbiComparison {
    pub(crate) fn same_process(&self, other: &Self) -> bool {
        (
            self.guest_pid,
            self.uid,
            self.user,
            &self.process_name,
            &self.required_abi,
            &self.instruction_set,
            self.start_seq,
        ) == (
            other.guest_pid,
            other.uid,
            other.user,
            &other.process_name,
            &other.required_abi,
            &other.instruction_set,
            other.start_seq,
        )
    }
    pub(crate) fn validate(
        &self,
        kind: EngineKind,
        p: &EngineProcess,
        expected: &ApplicationMetadata,
    ) -> Result<(), String> {
        need(
            self.guest_pid == p.guest_pid
                && self.uid == expected.uid
                && self.user == 0
                && self.process_name == expected.package
                && self.process_name == p.command
                && self.start_seq > 0
                && digest(&self.before_query_sha256)
                && digest(&self.after_query_sha256),
            "AMS comparison differs from the actual held task",
        )?;
        let actual = self.instruction_set.as_deref();
        need(
            match kind {
                EngineKind::NativeX86_64 => {
                    self.required_abi == "x86_64" && matches!(actual, None | Some("x86_64"))
                }
                EngineKind::BerberisArm64 => {
                    self.required_abi == "arm64-v8a"
                        && matches!(actual, None | Some("arm64") | Some("x86_64"))
                }
            },
            "actual required ABI is incompatible with the positively observed runtime",
        )
    }
}

/// Actual process identity from the fixed scoped helper.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct EngineProcess {
    pub host_pid: u32,
    /// Kernel NSpid in the same held Main PID namespace, not an AMS-selected PID.
    pub guest_pid: u32,
    pub host_parent_pid: u32,
    pub start_ticks: u64,
    pub pidfd: MainNodeIdentity,
    pub proc: MainNodeIdentity,
    pub root: MainNodeIdentity,
    pub executable: MainNodeIdentity,
    pub scoped_uids: [u32; 4],
    pub scoped_gids: [u32; 4],
    pub host_uids: [u32; 4],
    pub host_gids: [u32; 4],
    pub command: String,
    pub cgroup: String,
    pub selinux: String,
    pub apparmor: String,
    pub namespaces: Vec<CustodyNamespace>,
}

/// This is a point observation, not continuous process or translation custody.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RuntimeEngineObservation {
    pub schema: String,
    pub application: ApplicationMetadata,
    pub apk_bytes_hashed_by_engine_observer: bool,
    pub main: RuntimeMainCustody,
    pub source: EngineImageSource,
    pub process: EngineProcess,
    pub actual_engine: EngineFile,
    pub mappings: Vec<EngineMapping>,
    pub native_executable: Option<NativeExecutableObservation>,
    pub runtime_abi: EngineAbiComparison,
    pub maps_before_sha256: String,
    pub maps_after_sha256: String,
    pub observed_monotonic_ns: u64,
    pub translation_business_success_verified: bool,
}

fn need(ok: bool, why: &str) -> Result<(), String> {
    if ok { Ok(()) } else { Err(why.into()) }
}
fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn package(value: &str) -> bool {
    value.len() <= 255
        && value.contains('.')
        && value.split('.').all(|part| {
            !part.is_empty() && part.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'_')
        })
}
pub(crate) fn user_zero_app_uid(uid: u32) -> bool {
    (1000..20000).contains(&uid) && uid != 2000
}
/// Parse only the source-owned app type set and a canonical Android s0 category
/// list. The label is observed from the target and is never used to transition
/// this helper, which always remains its independent fixed s0 role.
pub(crate) fn app_context(value: &str) -> bool {
    let value = value.trim_end_matches(['\n', '\0']);
    let Some(rest) = value.strip_prefix("u:r:") else {
        return false;
    };
    let Some((kind, level)) = rest.split_once(':') else {
        return false;
    };
    if !APP_TYPES.contains(&kind) {
        return false;
    }
    if level == "s0" {
        return true;
    }
    let Some(cats) = level.strip_prefix("s0:") else {
        return false;
    };
    let mut previous = None;
    for group in cats.split(',') {
        let number = |s: &str| -> Option<u16> {
            let n = s.strip_prefix('c')?;
            if n.is_empty() || (n.len() > 1 && n.starts_with('0')) {
                return None;
            }
            let value: u16 = n.parse().ok()?;
            (value < 1024).then_some(value)
        };
        let (first, last) = if let Some((a, b)) = group.split_once('.') {
            let (Some(a), Some(b)) = (number(a), number(b)) else {
                return false;
            };
            if a >= b {
                return false;
            }
            (a, b)
        } else {
            let Some(n) = number(group) else {
                return false;
            };
            (n, n)
        };
        if previous.is_some_and(|old| old >= first) {
            return false;
        }
        previous = Some(last);
    }
    previous.is_some()
}
fn namespace<'a>(rows: &'a [CustodyNamespace], name: &str) -> Option<&'a CustodyNamespace> {
    let values: Vec<_> = rows.iter().filter(|row| row.name == name).collect();
    (values.len() == 1).then(|| values[0])
}
pub(crate) fn valid_engine(file: &EngineFile) -> bool {
    let n = &file.identity;
    n.device > 0
        && n.inode > 0
        && n.mode & libc::S_IFMT == libc::S_IFREG
        && n.mode & 0o7777 == 0o644
        && n.uid == 0
        && n.gid == 0
        && n.links == 1
        && (64..=MAX_ENGINE_BYTES).contains(&n.bytes)
        && digest(&file.sha256)
}
fn valid_mappings_for(
    rows: &[EngineMapping],
    file: &EngineFile,
    paths: &[&str],
) -> Result<(), String> {
    need(
        !rows.is_empty() && rows.len() <= MAX_ENGINE_MAPPINGS,
        "fixed engine is not uniquely observed",
    )?;
    let mut last_end = 0;
    let mut executable = false;
    for m in rows {
        let p = m.permissions.as_bytes();
        need(
            m.start > 0
                && m.start < m.end
                && m.start >= last_end
                && m.start % 4096 == 0
                && m.end % 4096 == 0
                && m.offset % 4096 == 0
                && m.offset < file.identity.bytes.div_ceil(4096) * 4096
                && p.len() == 4
                && matches!(p[0], b'r' | b'-')
                && matches!(p[1], b'w' | b'-')
                && matches!(p[2], b'x' | b'-')
                && matches!(p[3], b'p' | b's')
                && !(p[1] == b'w' && p[2] == b'x')
                && m.device == file.identity.device
                && m.inode == file.identity.inode
                && paths.contains(&m.path.as_str()),
            "engine VMA identity, extent or permissions differ",
        )?;
        executable |= p[2] == b'x';
        last_end = m.end;
    }
    need(executable, "fixed engine has no executable mapping")
}
impl RuntimeEngineObservation {
    /// Validate comparison shape against an already owned Main observation.
    /// This function cannot construct the opaque normal observer fact.
    pub fn validate(
        &self,
        main: &RuntimeMainCustody,
        expected: &ApplicationMetadata,
    ) -> Result<(), String> {
        main.validate(&expected.epoch)?;
        need(
            self.schema == SCHEMA
                && &self.main == main
                && &self.application == expected
                && !self.apk_bytes_hashed_by_engine_observer,
            "engine observation differs from the exact Main or installed application",
        )?;
        need(
            package(&expected.package)
                && selected_package(&expected.package)
                && expected.user == 0
                && user_zero_app_uid(expected.uid)
                && expected.version_code > 0
                && !expected.apks.is_empty(),
            "engine observation needs an actual user-0 application identity",
        )?;
        let p = &self.process;
        need(
            p.host_pid > 1
                && p.guest_pid > 1
                && p.host_pid != main.init.host_pid
                && p.host_pid != main.framework.host_pid
                && p.host_pid != main.zygote.host_pid
                && p.host_parent_pid == main.zygote.host_pid
                && p.start_ticks > main.zygote.start_ticks
                && p.pidfd.device > 0
                && p.pidfd.inode > 0
                && p.proc.device > 0
                && p.proc.inode > 0
                && p.root == main.framework.root
                && p.executable == main.zygote.executable
                && p.scoped_uids == [expected.uid; 4]
                && p.scoped_gids == [expected.uid; 4]
                && p.host_uids.iter().all(|x| *x == p.host_uids[0])
                && p.host_gids.iter().all(|x| *x == p.host_gids[0])
                && p.host_uids[0] > expected.uid
                && p.host_gids[0] > expected.uid
                && p.command == expected.package
                && app_context(&p.selinux)
                && p.apparmor == "droidloom-production-android (enforce)\n",
            "engine process is not the actual selected main application",
        )?;
        need(
            p.cgroup
                .starts_with("0::/system.slice/droidloom-production.service/cell-u1000/payload/")
                && p.cgroup.lines().count() == 1
                && !p
                    .cgroup
                    .trim_end_matches('\n')
                    .split('/')
                    .skip(1)
                    .any(|x| x.is_empty() || x == "." || x == ".."),
            "engine process left the original payload",
        )?;
        let names: BTreeSet<_> = p.namespaces.iter().map(|x| x.name.as_str()).collect();
        need(
            p.namespaces.len() == 7
                && names == BTreeSet::from(["user", "pid", "mount", "ipc", "uts", "net", "cgroup"]),
            "engine process namespace roster differs",
        )?;
        for name in ["user", "pid", "ipc", "uts", "net", "cgroup"] {
            need(
                namespace(&p.namespaces, name) == namespace(&main.framework_namespaces, name),
                "engine process namespace differs from Main",
            )?;
        }
        need(
            p.namespaces.iter().all(|n| n.device > 0 && n.inode > 0),
            "engine process namespace inode absent",
        )?;
        self.source.validate_origin(main)?;
        self.runtime_abi.validate(self.source.kind(), p, expected)?;
        match &self.source {
            EngineImageSource::BerberisArm64 { image: src } => {
                need(
                    self.native_executable.is_none() && self.actual_engine == src.engine,
                    "bridge observation contains native or substituted file evidence",
                )?;
                valid_mappings_for(&self.mappings, &self.actual_engine, &[ENGINE_PATH])?;
            }
            EngineImageSource::NativeX86_64 { image: src } => {
                use native_profile::NativeFileKind;
                let exe = self
                    .native_executable
                    .as_ref()
                    .ok_or_else(|| "native runtime omitted its actual executable".to_owned())?;
                need(
                    NativeFileKind::Executable.validate(&exe.file)
                        && NativeFileKind::Art.validate(&self.actual_engine)
                        && exe.file.identity.device == p.executable.device
                        && exe.file.identity.inode == p.executable.inode
                        && exe.file.identity.device == src.system_image.mount_root.device
                        && self.actual_engine.identity.device != exe.file.identity.device
                        && exe.mount.readonly_ext4()
                        && exe.art_mount.readonly_ext4()
                        && exe.mount.mount_id != exe.art_mount.mount_id,
                    "native runtime lacks exact executable/ART bytes and readonly mounts",
                )?;
                valid_mappings_for(&exe.mappings, &exe.file, NativeFileKind::Executable.paths())?;
                valid_mappings_for(
                    &self.mappings,
                    &self.actual_engine,
                    NativeFileKind::Art.paths(),
                )?;
            }
        }
        need(
            digest(&self.maps_before_sha256)
                && digest(&self.maps_after_sha256)
                && self.observed_monotonic_ns > 0
                && !self.translation_business_success_verified,
            "engine observation scope or bounded maps digest differs",
        )
    }
}

/// Parse bounded kernel procfs lines, retaining no unrelated process paths.
/// Any line naming this engine, or this actual engine inode, must agree with
/// the fixed path. Anonymous/JIT content is never opened or returned.
pub(crate) fn engine_mappings(raw: &[u8], file: &EngineFile) -> Result<Vec<EngineMapping>, String> {
    need(valid_engine(file), "invalid fixed engine identity")?;
    selected_mappings(raw, file, &[ENGINE_PATH], b"libberberis_arm64.so")
}
pub(crate) fn native_mappings(
    raw: &[u8],
    file: &EngineFile,
    kind: native_profile::NativeFileKind,
) -> Result<Vec<EngineMapping>, String> {
    need(
        kind.validate(file),
        "native runtime file differs from exact selected bytes",
    )?;
    selected_mappings(raw, file, kind.paths(), kind.basename())
}
fn selected_mappings(
    raw: &[u8],
    file: &EngineFile,
    paths: &[&str],
    basename: &[u8],
) -> Result<Vec<EngineMapping>, String> {
    need(
        !raw.is_empty() && raw.len() <= MAX_MAP_BYTES && raw.ends_with(b"\n"),
        "maps input is empty, truncated or too large",
    )?;
    let mut out = Vec::new();
    let mut count = 0usize;
    let mut previous = 0;
    for line in raw.split(|b| *b == b'\n').filter(|x| !x.is_empty()) {
        count += 1;
        need(
            count <= 32768 && line.len() <= 16384,
            "maps row bound exceeded",
        )?;
        let mut fields = Vec::with_capacity(5);
        let mut offset = 0;
        for _ in 0..5 {
            while offset < line.len() && line[offset].is_ascii_whitespace() {
                offset += 1;
            }
            let start = offset;
            while offset < line.len() && !line[offset].is_ascii_whitespace() {
                offset += 1;
            }
            need(offset > start, "maps row lacks fixed columns")?;
            fields.push(&line[start..offset]);
        }
        while offset < line.len() && line[offset].is_ascii_whitespace() {
            offset += 1;
        }
        let path = &line[offset..];
        fn ascii(x: &[u8]) -> Result<&str, String> {
            std::str::from_utf8(x).map_err(|_| "maps numeric encoding".to_string())
        }
        let hex = |x: &[u8]| -> Result<u64, String> {
            let s = ascii(x)?;
            need(
                !s.is_empty() && s.bytes().all(|b| b.is_ascii_hexdigit()),
                "maps hex field",
            )?;
            u64::from_str_radix(s, 16).map_err(|_| "maps hex overflow".into())
        };
        let bounds = fields[0].split(|x| *x == b'-').collect::<Vec<_>>();
        need(bounds.len() == 2, "maps address range")?;
        let start = hex(bounds[0])?;
        let end = hex(bounds[1])?;
        need(
            start > 0 && start < end && start >= previous,
            "maps address order",
        )?;
        previous = end;
        let permissions = ascii(fields[1])?;
        let p = permissions.as_bytes();
        need(
            p.len() == 4
                && matches!(p[0], b'r' | b'-')
                && matches!(p[1], b'w' | b'-')
                && matches!(p[2], b'x' | b'-')
                && matches!(p[3], b'p' | b's'),
            "maps permission shape",
        )?;
        let map_offset = hex(fields[2])?;
        let dev = fields[3].split(|x| *x == b':').collect::<Vec<_>>();
        need(dev.len() == 2, "maps device field")?;
        let major = u32::try_from(hex(dev[0])?).map_err(|_| "maps major overflow")?;
        let minor = u32::try_from(hex(dev[1])?).map_err(|_| "maps minor overflow")?;
        let device = libc::makedev(major, minor);
        let number = ascii(fields[4])?;
        need(
            !number.is_empty() && number.bytes().all(|b| b.is_ascii_digit()),
            "maps inode field",
        )?;
        let inode = number.parse::<u64>().map_err(|_| "maps inode overflow")?;
        let named = path.windows(basename.len()).any(|s| s == basename);
        if named || (device == file.identity.device && inode == file.identity.inode) {
            need(
                paths.iter().any(|p| path == p.as_bytes())
                    && device == file.identity.device
                    && inode == file.identity.inode,
                "engine path or actual mapped inode differs",
            )?;
            need(
                out.len() < MAX_ENGINE_MAPPINGS,
                "engine mapping count bound",
            )?;
            out.push(EngineMapping {
                start,
                end,
                permissions: permissions.into(),
                offset: map_offset,
                device,
                inode,
                path: ascii(path)?.into(),
            });
        }
    }
    valid_mappings_for(&out, file, paths)?;
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn file() -> EngineFile {
        EngineFile {
            identity: CustodyFileIdentity {
                device: libc::makedev(8, 17),
                inode: 91,
                mode: 0o100644,
                uid: 0,
                gid: 0,
                links: 1,
                bytes: 8192,
                modified: (5, 6),
                changed: (7, 8),
            },
            sha256: "1".repeat(64),
        }
    }
    fn maps() -> Vec<u8> {
        format!("1000-2000 r--p 00000000 08:11 91 {ENGINE_PATH}\n2000-3000 r-xp 00001000 08:11 91 {ENGINE_PATH}\n4000-5000 rw-p 00000000 00:00 0 [anon:unrelated]\n").into_bytes()
    }
    #[test]
    fn engine_maps_bind_actual_file_and_keep_only_fixed_vmas() {
        let row = engine_mappings(&maps(), &file()).unwrap();
        assert_eq!(row.len(), 2);
        assert!(row.iter().all(|r| r.path == ENGINE_PATH && r.inode == 91));
        let mut other = maps();
        other.extend_from_slice(b"6000-7000 r--p 0 00:00 0 /private/unrelated\n");
        assert_eq!(engine_mappings(&other, &file()).unwrap(), row);
    }
    #[test]
    fn engine_maps_reject_wrong_inode_alias_deleted_execute_and_bounds() {
        let s = String::from_utf8(maps()).unwrap();
        for bad in [
            s.replace("08:11 91", "08:11 92"),
            s.replace(ENGINE_PATH, "/system/lib64/libberberis_arm64.so"),
            s.replace(ENGINE_PATH, &format!("{ENGINE_PATH} (deleted)")),
            s.replace("r-xp", "r--p"),
            s.replace("r-xp", "rwxp"),
            s.replace("2000-3000", "1800-3000"),
            s.replace("00001000", "00009000"),
            s.trim_end().to_owned(),
            s.replace("08:11", "08:badhex"),
        ] {
            assert!(engine_mappings(bad.as_bytes(), &file()).is_err(), "{bad}");
        }
        let mut duplicate = s.clone();
        duplicate.push_str(&s);
        assert!(engine_mappings(duplicate.as_bytes(), &file()).is_err());
    }
    #[test]
    fn engine_target_contexts_preserve_real_categories_without_caller_roles() {
        for label in [
            "u:r:untrusted_app:s0:c1,c257,c512,c768",
            "u:r:platform_app:s0",
            "u:r:priv_app:s0:c0.c1023\n",
        ] {
            assert!(app_context(label));
        }
        for label in [
            "u:r:system_server:s0",
            "u:r:droidloom_broker:s0",
            "u:r:untrusted_app:s1",
            "u:r:untrusted_app:s0:c01",
            "u:r:untrusted_app:s0:c1024",
            "u:r:untrusted_app:s0:c2,c1",
            "u:r:untrusted_app:s0:c1,c1",
            "u:r:untrusted_app:s0:",
            "u:r:untrusted_app:s0:c1.c1",
        ] {
            assert!(!app_context(label), "{label}");
        }
        assert!(user_zero_app_uid(1000));
        assert!(user_zero_app_uid(10001));
        for uid in [0, 999, 2000, 20000, 100001] {
            assert!(!user_zero_app_uid(uid));
        }
    }
    #[test]
    fn real_proc_maps_parser_does_not_infer_engine_from_absence() {
        let raw = std::fs::read("/proc/self/maps").unwrap();
        assert!(raw.ends_with(b"\n"));
        assert!(engine_mappings(&raw, &file()).is_err());
    }

    fn native_file(kind: native_profile::NativeFileKind) -> EngineFile {
        let (bytes, sha, mode, uid, gid) = kind.expected();
        let mut value = file();
        value.identity.bytes = bytes;
        value.identity.mode = mode;
        value.identity.uid = uid;
        value.identity.gid = gid;
        value.sha256 = sha.into();
        value
    }
    #[test]
    fn engine_native_maps_need_positive_selected_executable_and_art() {
        use native_profile::NativeFileKind;
        for kind in [NativeFileKind::Executable, NativeFileKind::Art] {
            let file = native_file(kind);
            for path in kind.paths() {
                let raw = format!(
                    "1000-2000 r--p 0 08:11 91 {path}\n2000-3000 r-xp 1000 08:11 91 {path}\n"
                );
                let rows = native_mappings(raw.as_bytes(), &file, kind).unwrap();
                assert_eq!(rows.len(), 2);
                assert!(rows.iter().all(|row| row.path == *path));
            }
        }
        let source = native_profile::art_input().unwrap();
        assert_eq!(source.version, 371_899_999);
        assert_eq!(source.member_bytes, native_profile::ART_BYTES);
        assert_eq!(source.member_sha256, native_profile::ART_SHA256);
    }
    #[test]
    fn engine_native_maps_reject_absence_alias_old_version_wrong_bytes_or_inode() {
        use native_profile::NativeFileKind;
        let kind = NativeFileKind::Art;
        let file = native_file(kind);
        let path = native_profile::ART_VERSIONED_PATH;
        let raw = format!("1000-2000 r-xp 0 08:11 91 {path}\n");
        for bad in [
            raw.replace("@371899999", "@371899998"),
            raw.replace(path, "/data/local/tmp/libart.so"),
            raw.replace(path, &format!("{path} (deleted)")),
            raw.replace("08:11 91", "08:11 92"),
            raw.replace("r-xp", "r--p"),
            raw.replace("r-xp", "rwxp"),
            "1000-2000 r-xp 0 00:00 0 [anon:unrelated]\n".into(),
        ] {
            assert!(
                native_mappings(bad.as_bytes(), &file, kind).is_err(),
                "{bad}"
            );
        }
        let mut wrong = file.clone();
        wrong.sha256 = "0".repeat(64);
        assert!(native_mappings(raw.as_bytes(), &wrong, kind).is_err());
        wrong = file.clone();
        wrong.identity.uid = 0;
        assert!(native_mappings(raw.as_bytes(), &wrong, kind).is_err());
        // Native proof never accepts a bridge-only mapping in lieu of ART.
        assert!(native_mappings(&maps(), &file, kind).is_err());
    }
}
