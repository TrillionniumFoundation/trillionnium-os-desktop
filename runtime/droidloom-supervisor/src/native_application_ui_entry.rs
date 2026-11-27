//! Live Rust entry for the already installed fixed native accessibility helper.
//!
//! This factory borrows actual normal Main/PM custody. It retains the helper,
//! seven namespace/root descriptors and original budget through real owned
//! child retirement. Serialized output is evidence only, never a passed gate.
use super::{BoundProcess, invalid, open_at};
use crate::control::{
    ActualApplicationObservation, CellState, ControlRequest, NativeApplicationInspector,
};
use crate::main_custody::{MainNodeIdentity, RuntimeMainCustody};
use crate::native_application_ui_protocol as wire;
use crate::native_leaf_baseline::NativeLeafBaselineObservation;
use crate::native_working_contract::{WorkingNamespaceEntryPin, layout as working_layout};
use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::CString;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, RawFd};
use std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::process::CommandExt;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};

#[path = "native_application_ui_pair.rs"]
mod pair;
pub use pair::{NativeUiPairSession, RetainedNativeUiPairTranscript, pair_additional_window_seconds};

#[path = "native_application_ui_common.rs"]
mod common;
#[path = "native_application_ui_tasks.rs"]
mod tasks;
pub use common::{
    NativeUiStabilityEvidence, NativeUiStabilitySummary, NativeUiStabilityWindow,
    RetainedNativeUiTranscript, stability_additional_window_seconds,
};
#[path = "native_application_ui_permissions.rs"]
mod permissions;
pub use permissions::{NativeUiPermissionWindow, NativeUiPermissionPreservation, permission_preservation_additional_window_seconds};
#[path = "native_application_ui_family.rs"]
mod family;
pub use family::{NativeFamilyUiEvidence, observe_native_family_ui, family_ui_window_seconds, family_ui_retained_members_bound};
#[path = "native_application_ui_settings.rs"]
mod settings;
pub use settings::{SettingsPermissionCaseObservation, run_settings_permission_case, settings_permission_case_window_seconds};
#[path = "native_application_ui_media.rs"]
mod media;
pub use media::{
    CameraPhotoCaseObservation, CameraPhotoObservation, CameraPhotoSceneObservation,
    RetainedScopedWindowPixels, ScopedWindowPixels, camera_photo_case_window_seconds,
    run_camera_photo_case,
};

const COHORT: &str =
    "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2";
const HELPER: &str = "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/bin/held-namespace-entry";
const HELPER_SHA: &str = "67cfd1c212e9f40ce3f0ff7be856a05f8189c674cbfa270757a672ea596a6c3f";
const SOURCE_SHA: &str = "5367f5c9786b9d3795b14c51af6c6bd488782a624b9066ce84e64af7feacf792";
const PROOF_SHA: &str = "3aad09d9e19677a3318a0110613d03e758b9133d582c1e1e858a7819726d7ac3";
const JOURNALS: &str = "/var/lib/droidloom-qualification";
const ACTION_LOCK: &str = "/run/lock/android-digitalis-actions.lock";
const HELPER_UID: u32 = 10125;
const MAX_INPUT: u64 = 8 * 1024 * 1024;
const COMMAND_CAP: Duration = Duration::from_secs(70);
const CLEANUP_RESERVE: Duration = Duration::from_secs(60);
static NEXT_JOURNAL: AtomicU64 = AtomicU64::new(0);

fn need(value: bool, why: &str) -> Result<(), String> {
    if value { Ok(()) } else { Err(why.into()) }
}
fn before(end: Instant) -> Result<(), String> {
    need(Instant::now() < end, "native UI original deadline expired")
}
fn node(file: &File) -> io::Result<MainNodeIdentity> {
    Ok(MainNodeIdentity::of(&file.metadata()?))
}
#[derive(Debug, Eq, PartialEq)]
struct Identity {
    device: u64,
    inode: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    bytes: u64,
    modified: (i64, i64),
    changed: (i64, i64),
}
impl Identity {
    fn of(m: &fs::Metadata) -> Self {
        Self {
            device: m.dev(),
            inode: m.ino(),
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            links: m.nlink(),
            bytes: m.len(),
            modified: (m.mtime(), m.mtime_nsec()),
            changed: (m.ctime(), m.ctime_nsec()),
        }
    }
}
struct Parent {
    path: PathBuf,
    file: File,
    identity: [u64; 5],
}
fn directory_identity(file: &File) -> io::Result<[u64; 5]> {
    let m = file.metadata()?;
    if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o022 != 0 {
        return Err(invalid("native UI root-protected directory required"));
    }
    Ok([
        m.dev(),
        m.ino(),
        u64::from(m.mode()),
        u64::from(m.uid()),
        u64::from(m.gid()),
    ])
}
fn parent_identity(file: &File, path: &Path) -> io::Result<[u64; 5]> {
    let m = file.metadata()?;
    // The original shared lock lives in Ubuntu's root-owned sticky /run/lock.
    // Sticky ownership protects the root-owned 0600 leaf, which is checked
    // separately under its held FD. No other writable parent is accepted.
    if path == Path::new("/run/lock")
        && m.mode() == libc::S_IFDIR | 0o1777
        && m.uid() == 0
        && m.gid() == 0
    {
        return Ok([m.dev(), m.ino(), u64::from(m.mode()), 0, 0]);
    }
    directory_identity(file)
}
fn protected_parents(path: &Path) -> io::Result<Vec<Parent>> {
    if !path.is_absolute()
        || path
            .components()
            .any(|c| !matches!(c, Component::RootDir | Component::Normal(_)))
    {
        return Err(invalid("native UI canonical absolute input required"));
    }
    let mut parents = Vec::new();
    let mut current = PathBuf::from("/");
    let root = open_at(
        libc::AT_FDCWD,
        c"/",
        libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW,
    )?;
    let identity = parent_identity(&root, &current)?;
    parents.push(Parent {
        path: current.clone(),
        file: root,
        identity,
    });
    let parent = path
        .parent()
        .ok_or_else(|| invalid("native UI input has no parent"))?;
    for part in parent.components().filter_map(|part| match part {
        Component::Normal(v) => Some(v),
        _ => None,
    }) {
        let name =
            CString::new(part.as_encoded_bytes()).map_err(|_| invalid("native UI parent name"))?;
        let file = open_at(
            parents.last().unwrap().file.as_raw_fd(),
            &name,
            libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW,
        )?;
        current.push(part);
        let identity = parent_identity(&file, &current)?;
        parents.push(Parent {
            path: current.clone(),
            file,
            identity,
        });
    }
    Ok(parents)
}
fn verify_parents(parents: &[Parent]) -> io::Result<()> {
    for parent in parents {
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&parent.path)?;
        if parent_identity(&parent.file, &parent.path)? != parent.identity
            || parent_identity(&named, &parent.path)? != parent.identity
        {
            return Err(invalid("native UI held input parent changed"));
        }
    }
    Ok(())
}
fn working_label(file: &File, expected: &[u8]) -> Result<(), String> {
    let mut bytes = [0_u8; 256];
    let count = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            bytes.as_mut_ptr().cast(),
            bytes.len(),
        )
    };
    if count <= 0 || count as usize >= bytes.len() {
        return Err("working native UI expected a finite normal SELinux label".into());
    }
    let mut actual = &bytes[..count as usize];
    if actual.last() == Some(&0) {
        actual = &actual[..actual.len() - 1];
    }
    need(actual == expected, "working native UI normal label differs")
}

struct HeldInput {
    path: PathBuf,
    file: File,
    parents: Vec<Parent>,
    identity: Identity,
    sha256: String,
    required_label: Option<&'static [u8]>,
}
impl HeldInput {
    fn open(path: &Path, bytes: u64, sha256: &str, mode: u32) -> Result<Self, String> {
        need(
            path.starts_with(COHORT)
                && bytes <= MAX_INPUT
                && sha256.len() == 64
                && sha256
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
            "native UI source-owned helper input differs",
        )?;
        Self::open_verified(path, bytes, sha256, mode, None)
    }
    fn open_working(pin: &WorkingNamespaceEntryPin) -> Result<Self, String> {
        pin.validate().map_err(|e| e.to_string())?;
        let input = Self::open_verified(
            Path::new(&pin.path),
            pin.bytes,
            &pin.sha256,
            0o755,
            Some(working_layout::WORKING_NAMESPACE_ENTRY_EXEC_LABEL),
        )?;
        let mut elf = [0_u8; 64];
        input
            .file
            .read_exact_at(&mut elf, 0)
            .map_err(|e| e.to_string())?;
        need(
            &elf[..7] == b"\x7fELF\x02\x01\x01"
                && matches!(u16::from_le_bytes([elf[16], elf[17]]), 2 | 3)
                && u16::from_le_bytes([elf[18], elf[19]]) == 62,
            "working namespace entry is not its normal x86-64 ELF",
        )?;
        for attribute in [
            c"security.capability",
            c"system.posix_acl_access",
            c"system.posix_acl_default",
        ] {
            let count = unsafe {
                libc::fgetxattr(
                    input.file.as_raw_fd(),
                    attribute.as_ptr(),
                    std::ptr::null_mut(),
                    0,
                )
            };
            need(
                count < 0 && io::Error::last_os_error().raw_os_error() == Some(libc::ENODATA),
                "working namespace entry has an unadmitted capability or ACL",
            )?;
        }
        input.verify()?;
        Ok(input)
    }
    fn open_verified(
        path: &Path,
        bytes: u64,
        sha256: &str,
        mode: u32,
        required_label: Option<&'static [u8]>,
    ) -> Result<Self, String> {
        let parents = protected_parents(path).map_err(|e| e.to_string())?;
        let name = CString::new(
            path.file_name()
                .ok_or("native UI input name absent")?
                .as_encoded_bytes(),
        )
        .map_err(|_| "native UI input name invalid")?;
        let file = open_at(
            parents.last().unwrap().file.as_raw_fd(),
            &name,
            libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_NONBLOCK,
        )
        .map_err(|e| e.to_string())?;
        let identity = Identity::of(&file.metadata().map_err(|e| e.to_string())?);
        need(
            identity.mode == libc::S_IFREG | mode
                && identity.uid == 0
                && identity.gid == 0
                && identity.links == 1
                && identity.bytes == bytes,
            "native UI helper input metadata differs",
        )?;
        let result = Self {
            path: path.into(),
            file,
            parents,
            identity,
            sha256: sha256.into(),
            required_label,
        };
        result.full()?;
        Ok(result)
    }
    fn verify(&self) -> Result<(), String> {
        verify_parents(&self.parents).map_err(|e| e.to_string())?;
        if let Some(label) = self.required_label {
            working_label(&self.file, label)?;
        }
        need(
            Identity::of(&self.file.metadata().map_err(|e| e.to_string())?) == self.identity
                && Identity::of(&fs::symlink_metadata(&self.path).map_err(|e| e.to_string())?)
                    == self.identity,
            "native UI pinned helper body changed",
        )
    }
    fn bytes(&self) -> Result<Vec<u8>, String> {
        self.verify()?;
        let mut bytes = vec![0_u8; self.identity.bytes as usize];
        self.file
            .read_exact_at(&mut bytes, 0)
            .map_err(|e| e.to_string())?;
        let mut extra = [0_u8; 1];
        need(
            self.file
                .read_at(&mut extra, self.identity.bytes)
                .map_err(|e| e.to_string())?
                == 0,
            "native UI helper body grew",
        )?;
        self.verify()?;
        Ok(bytes)
    }
    fn full(&self) -> Result<(), String> {
        let bytes = self.bytes()?;
        need(
            format!("{:x}", Sha256::digest(bytes)) == self.sha256,
            "native UI helper whole-byte hash differs",
        )
    }
}
struct HelperInputs {
    held: Vec<HeldInput>,
}
impl HelperInputs {
    fn capture(baseline: &NativeLeafBaselineObservation<'_>) -> Result<Self, String> {
        let working = if let Some(source) = baseline.working_source_custody() {
            Some(source.namespace_entry_pin().map_err(|e| e.to_string())?)
        } else if let Some(owner) = baseline.preparation_owner() {
            Some(owner.namespace_entry_pin()?)
        } else {
            None
        };
        if let Some(pin) = working {
            // This independently built normal host member cannot inherit any
            // historical cohort proof credit. Its actual Main entry is tested.
            let result = Self {
                held: vec![HeldInput::open_working(pin)?],
            };
            result.verify()?;
            return Ok(result);
        }
        let binary = HeldInput::open(Path::new(HELPER), 3_972_024, HELPER_SHA, 0o755)?;
        let source = HeldInput::open(
            &Path::new(COHORT).join("source/held_namespace_entry.rs"),
            21_907,
            SOURCE_SHA,
            0o444,
        )?;
        let proof = HeldInput::open(
            &Path::new(COHORT).join("evidence/helper/evidence-manifest.json"),
            19_353,
            PROOF_SHA,
            0o444,
        )?;
        let packet: Value = serde_json::from_slice(&proof.bytes()?)
            .map_err(|_| "native UI helper proof malformed")?;
        need(
            packet["schema"] == "pocket4-byte-preserved-helper-evidence-v1"
                && packet["Main_readonly_entry_passed"] == false
                && packet["runtime_qualified"] == false
                && packet["production_ready"] == false
                && packet["historical_paths_grant_current_authority"] == false,
            "native UI historical helper material cannot supply Main authority",
        )?;
        let copies = packet["copies"]
            .as_object()
            .ok_or("native UI helper proof copies absent")?;
        let raw = packet["raw_outputs"]
            .as_array()
            .ok_or("native UI helper raw proof absent")?;
        need(
            copies.len() == 5 && raw.len() == 20,
            "native UI full original helper proof roster differs",
        )?;
        let mut held = vec![binary, source, proof];
        for value in copies
            .values()
            .map(|v| &v["copy"])
            .chain(raw.iter().map(|v| &v["copy"]))
        {
            let path = PathBuf::from(
                value["path"]
                    .as_str()
                    .ok_or("native UI helper proof path absent")?,
            );
            let bytes = value["bytes"]
                .as_u64()
                .ok_or("native UI helper proof bytes absent")?;
            let sha = value["sha256"]
                .as_str()
                .ok_or("native UI helper proof hash absent")?;
            if let Some(existing) = held.iter().find(|f| f.path == path) {
                need(
                    existing.identity.bytes == bytes && existing.sha256 == sha,
                    "native UI repeated helper pin differs",
                )?;
            } else {
                held.push(HeldInput::open(&path, bytes, sha, 0o444)?);
            }
        }
        let result = Self { held };
        result.verify()?;
        Ok(result)
    }
    fn binary(&self) -> &File {
        &self.held[0].file
    }
    fn path(&self) -> &Path {
        &self.held[0].path
    }
    fn verify(&self) -> Result<(), String> {
        for input in &self.held {
            input.verify()?;
        }
        Ok(())
    }
    fn full(&self) -> Result<(), String> {
        for input in &self.held {
            input.full()?;
        }
        Ok(())
    }
}
const ENVIRONMENT: [&str; 18] = [
    "PATH",
    "BOOTCLASSPATH",
    "DEX2OATBOOTCLASSPATH",
    "ANDROID_ART_ROOT",
    "ANDROID_ASSETS",
    "ANDROID_BOOTLOGO",
    "ANDROID_DATA",
    "ANDROID_I18N_ROOT",
    "ANDROID_ROOT",
    "ANDROID_STORAGE",
    "ANDROID_TZDATA_ROOT",
    "ASEC_MOUNTPOINT",
    "DOWNLOAD_CACHE",
    "EXTERNAL_STORAGE",
    "LOOP_MOUNTPOINT",
    "STANDALONE_SYSTEMSERVER_JARS",
    "SYSTEMSERVERCLASSPATH",
    "LANG",
];
fn environment(bytes: &[u8]) -> Result<BTreeMap<String, String>, String> {
    need(
        bytes.len() <= 1024 * 1024,
        "native UI actual framework environment exceeds bound",
    )?;
    let mut result = BTreeMap::new();
    for row in bytes.split(|b| *b == 0).filter(|v| !v.is_empty()) {
        let Some(split) = row.iter().position(|b| *b == b'=') else {
            continue;
        };
        let Ok(key) = std::str::from_utf8(&row[..split]) else {
            continue;
        };
        if !ENVIRONMENT.contains(&key) {
            continue;
        }
        let value = std::str::from_utf8(&row[split + 1..])
            .map_err(|_| "native UI environment is not UTF-8")?;
        need(
            value.len() <= 65_536 && result.insert(key.into(), value.into()).is_none(),
            "native UI environment duplicate or oversized value",
        )?;
    }
    for key in [
        "PATH",
        "BOOTCLASSPATH",
        "DEX2OATBOOTCLASSPATH",
        "ANDROID_ROOT",
        "ANDROID_DATA",
        "ANDROID_ART_ROOT",
    ] {
        need(
            result.get(key).is_some_and(|s: &String| !s.is_empty()),
            "native UI required actual Android environment absent",
        )?;
    }
    need(
        result["ANDROID_ROOT"] == "/system" && result["ANDROID_DATA"] == "/data",
        "native UI actual Android roots differ",
    )?;
    Ok(result)
}
struct Target {
    init: BoundProcess,
    framework: BoundProcess,
    root: File,
    user: File,
    namespaces: Vec<(&'static str, &'static str, File)>,
    expected: RuntimeMainCustody,
    environment: BTreeMap<String, String>,
}
impl Target {
    fn capture(baseline: &NativeLeafBaselineObservation<'_>) -> Result<Self, String> {
        let expected = baseline.main().facts().clone();
        let init = BoundProcess::capture(expected.init.host_pid).map_err(|e| e.to_string())?;
        let framework =
            BoundProcess::capture(expected.framework.host_pid).map_err(|e| e.to_string())?;
        let root = init.open("root", true).map_err(|e| e.to_string())?;
        let user = init.open("ns/user", false).map_err(|e| e.to_string())?;
        let namespaces = [
            ("mnt", "mount", "ns/mnt"),
            ("pid", "pid", "ns/pid"),
            ("uts", "uts", "ns/uts"),
            ("ipc", "ipc", "ns/ipc"),
            ("net", "net", "ns/net"),
            ("cgroup", "cgroup", "ns/cgroup"),
        ]
        .into_iter()
        .map(|(flag, name, path)| init.open(path, false).map(|file| (flag, name, file)))
        .collect::<io::Result<Vec<_>>>()
        .map_err(|e| e.to_string())?;
        let mut raw = Vec::new();
        framework
            .open("environ", false)
            .map_err(|e| e.to_string())?
            .take(1024 * 1024 + 1)
            .read_to_end(&mut raw)
            .map_err(|e| e.to_string())?;
        let environment = environment(&raw)?;
        let result = Self {
            init,
            framework,
            root,
            user,
            namespaces,
            expected,
            environment,
        };
        result.verify()?;
        Ok(result)
    }
    fn verify(&self) -> Result<(), String> {
        self.init
            .validate()
            .and_then(|_| self.framework.validate())
            .map_err(|e| e.to_string())?;
        need(
            self.init.identity.start_ticks == self.expected.init.start_ticks
                && self.framework.identity.start_ticks == self.expected.framework.start_ticks,
            "native UI original process generation differs",
        )?;
        let init_pidfd = fs::metadata(format!("/proc/self/fd/{}", self.init.pidfd.as_raw_fd()))
            .map_err(|e| e.to_string())?;
        let framework_pidfd = fs::metadata(format!(
            "/proc/self/fd/{}",
            self.framework.pidfd.as_raw_fd()
        ))
        .map_err(|e| e.to_string())?;
        need(
            MainNodeIdentity::of(&init_pidfd) == self.expected.init.pidfd
                && MainNodeIdentity::of(&framework_pidfd) == self.expected.framework.pidfd
                && node(&self.root).map_err(|e| e.to_string())? == self.expected.init.root
                && node(&self.init.open("root", true).map_err(|e| e.to_string())?)
                    .map_err(|e| e.to_string())?
                    == self.expected.init.root
                && node(&self.user).map_err(|e| e.to_string())?
                    == self.expected.persistent_data.user_namespace
                && node(
                    &self
                        .init
                        .open("ns/user", false)
                        .map_err(|e| e.to_string())?,
                )
                .map_err(|e| e.to_string())?
                    == self.expected.persistent_data.user_namespace,
            "native UI PIDFD, held root or mapped user namespace differs",
        )?;
        for (flag, name, held) in &self.namespaces {
            let expected = self
                .expected
                .owner
                .namespaces
                .iter()
                .find(|v| v.name == *name)
                .ok_or("native UI actual Main namespace absent")?;
            let current = self
                .init
                .open(&format!("ns/{flag}"), false)
                .map_err(|e| e.to_string())?;
            let wanted = MainNodeIdentity {
                device: expected.device,
                inode: expected.inode,
            };
            need(
                node(held).map_err(|e| e.to_string())? == wanted
                    && node(&current).map_err(|e| e.to_string())? == wanted,
                "native UI original Main namespace changed",
            )?;
        }
        for (process, expected) in [
            (&self.init, &self.expected.init),
            (&self.framework, &self.expected.framework),
        ] {
            let stat = super::bounded_text(
                process.open("stat", false).map_err(|e| e.to_string())?,
                4096,
            )
            .map_err(|e| e.to_string())?;
            let (_, fields) = stat
                .rsplit_once(") ")
                .ok_or("native UI proc stat malformed")?;
            need(
                fields
                    .split_ascii_whitespace()
                    .nth(1)
                    .and_then(|s| s.parse::<u32>().ok())
                    == Some(expected.parent_host_pid)
                    && node(&process.open("exe", false).map_err(|e| e.to_string())?)
                        .map_err(|e| e.to_string())?
                        == expected.executable,
                "native UI actual process parent or executable changed",
            )?;
        }
        need(
            fs::read_to_string("/proc/sys/kernel/random/boot_id")
                .map_err(|e| e.to_string())?
                .trim()
                == self.expected.epoch.boot_id,
            "native UI host boot changed",
        )?;
        Ok(())
    }
    fn command(
        &self,
        helper: &HelperInputs,
        literal: &[String],
        shell: bool,
        cap: Duration,
    ) -> Result<(Command, Vec<RawFd>), String> {
        need(
            !literal.is_empty() && !cap.is_zero() && cap <= COMMAND_CAP,
            "native UI fixed command budget differs",
        )?;
        self.verify()?;
        helper.verify()?;
        // Execute the held ELF itself. Its FD closes on exec and does not add
        // an eighth inherited namespace authority. argv[0] remains the fixed name.
        let mut command = droidloom_cpu_placement::command(format!(
            "/proc/self/fd/{}",
            helper.binary().as_raw_fd()
        ));
        command
            .arg0(helper.path())
            .env_clear()
            .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
            .env("LANG", "C.UTF-8");
        command
            .arg(format!("--parent-pid={}", std::process::id()))
            .arg(format!("--root-fd={}", self.root.as_raw_fd()));
        let mut inherit = vec![self.root.as_raw_fd()];
        for (flag, _, file) in &self.namespaces {
            command.arg(format!("--{flag}-fd={}", file.as_raw_fd()));
            inherit.push(file.as_raw_fd());
        }
        let user = self.user.metadata().map_err(|e| e.to_string())?;
        command
            .arg(format!("--expected-userns-device={}", user.dev()))
            .arg(format!("--expected-userns-inode={}", user.ino()))
            .arg(format!(
                "--expected-init-start-ticks={}",
                self.expected.init.start_ticks
            ))
            .arg("--")
            .arg("/system/bin/env")
            .arg("-i");
        for (key, value) in &self.environment {
            command.arg(format!("{key}={value}"));
        }
        if shell {
            command.args(["/system/xbin/su", "2000"]);
        }
        command
            .args(["/system/bin/timeout", "-k", "2"])
            .arg(cap.as_secs().saturating_sub(5).max(1).to_string())
            .args(literal);
        need(
            inherit.len() == 7
                && inherit.iter().copied().collect::<BTreeSet<_>>().len() == 7
                && inherit.iter().all(|fd| *fd >= 3),
            "native UI exact seven held authorities required",
        )?;
        Ok((command, inherit))
    }
}
struct WorkingJournalRoot {
    path: PathBuf,
    file: File,
    identity: [u64; 5],
}
impl WorkingJournalRoot {
    fn open(runtime: &Path) -> Result<Self, String> {
        let path = runtime.join(working_layout::WORKING_NATIVE_UI_DIRECTORY);
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&path)
            .map_err(|e| e.to_string())?;
        let identity = directory_identity(&file).map_err(|e| e.to_string())?;
        need(
            identity[2] == u64::from(libc::S_IFDIR | 0o700),
            "working native UI parent was not privately created by its real owner",
        )?;
        working_label(&file, working_layout::WORKING_NATIVE_UI_DIRECTORY_LABEL)?;
        let root = Self {
            path,
            file,
            identity,
        };
        root.verify()?;
        Ok(root)
    }
    fn verify(&self) -> Result<(), String> {
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&self.path)
            .map_err(|e| e.to_string())?;
        for file in [&self.file, &named] {
            need(
                directory_identity(file).map_err(|e| e.to_string())? == self.identity,
                "working native UI root changed",
            )?;
            working_label(file, working_layout::WORKING_NATIVE_UI_DIRECTORY_LABEL)?;
        }
        Ok(())
    }
}
struct Journal {
    path: PathBuf,
    directory: File,
    identity: [u64; 5],
    parents: Vec<Parent>,
    working_root: Option<WorkingJournalRoot>,
}
impl Journal {
    fn create(baseline: &NativeLeafBaselineObservation<'_>) -> Result<Self, String> {
        let runtime = if let Some(source) = baseline.working_source_custody() {
            Some(
                source
                    .runtime_evidence_directory()
                    .map_err(|e| e.to_string())?,
            )
        } else if let Some(owner) = baseline.preparation_owner() {
            Some(owner.runtime_evidence_directory()?)
        } else {
            None
        };
        let working_root = runtime.map(WorkingJournalRoot::open).transpose()?;
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(|_| "native UI journal clock unavailable")?
            .as_nanos();
        let name = format!(
            "native-ui-{}-{stamp}-{}",
            std::process::id(),
            NEXT_JOURNAL.fetch_add(1, Ordering::Relaxed)
        );
        let parent = working_root
            .as_ref()
            .map_or(Path::new(JOURNALS), |root| &root.path);
        let path = parent.join(&name);
        let parents = protected_parents(&path).map_err(|e| e.to_string())?;
        if let Some(root) = &working_root {
            root.verify()?;
            let leaf = CString::new(name).map_err(|e| e.to_string())?;
            if unsafe { libc::mkdirat(root.file.as_raw_fd(), leaf.as_ptr(), 0o700) } != 0 {
                return Err(io::Error::last_os_error().to_string());
            }
            root.file.sync_all().map_err(|e| e.to_string())?;
        } else {
            fs::create_dir(&path).map_err(|e| e.to_string())?;
            fs::set_permissions(&path, fs::Permissions::from_mode(0o700))
                .map_err(|e| e.to_string())?;
        }
        let directory = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&path)
            .map_err(|e| e.to_string())?;
        let identity = directory_identity(&directory).map_err(|e| e.to_string())?;
        let result = Self {
            path,
            directory,
            identity,
            parents,
            working_root,
        };
        result.verify()?;
        Ok(result)
    }
    fn verify(&self) -> Result<(), String> {
        verify_parents(&self.parents).map_err(|e| e.to_string())?;
        if let Some(root) = &self.working_root {
            root.verify()?;
            need(
                self.identity[2] == u64::from(libc::S_IFDIR | 0o700),
                "working native UI session directory mode differs",
            )?;
            working_label(
                &self.directory,
                working_layout::WORKING_NATIVE_UI_SESSION_DIRECTORY_LABEL,
            )?;
        }
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&self.path)
            .map_err(|e| e.to_string())?;
        need(
            directory_identity(&self.directory).map_err(|e| e.to_string())? == self.identity
                && directory_identity(&named).map_err(|e| e.to_string())? == self.identity,
            "native UI private journal replaced",
        )
    }
    fn write(&self, name: &str, bytes: &[u8]) -> Result<(), String> {
        self.verify()?;
        need(
            !name.is_empty()
                && name
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"-_.".contains(&b))
                && bytes.len() <= wire::WIRE_REPLY_BYTES.max(32 * 1024 * 1024),
            "native UI private record name or bound differs",
        )?;
        let name = CString::new(name).map_err(|_| "native UI record name invalid")?;
        let fd = unsafe {
            libc::openat(
                self.directory.as_raw_fd(),
                name.as_ptr(),
                libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                0o600,
            )
        };
        if fd < 0 {
            return Err(io::Error::last_os_error().to_string());
        }
        use std::os::fd::FromRawFd;
        let mut file = unsafe { File::from_raw_fd(fd) };
        if self.working_root.is_some() {
            working_label(&file, working_layout::WORKING_NATIVE_UI_RECORD_LABEL)?;
            let metadata = file.metadata().map_err(|e| e.to_string())?;
            need(
                metadata.mode() == libc::S_IFREG | 0o600
                    && metadata.uid() == 0
                    && metadata.gid() == 0
                    && metadata.nlink() == 1,
                "working native UI record metadata differs",
            )?;
        }
        file.write_all(bytes)
            .and_then(|_| file.sync_all())
            .and_then(|_| self.directory.sync_all())
            .map_err(|e| e.to_string())?;
        self.verify()
    }
    fn json(&self, name: &str, value: &impl Serialize) -> Result<(), String> {
        self.write(name, &serde_json::to_vec(value).map_err(|e| e.to_string())?)
    }
}
struct ActionLock {
    file: File,
    identity: Identity,
    parents: Vec<Parent>,
}
impl ActionLock {
    fn acquire() -> Result<Self, String> {
        let path = Path::new(ACTION_LOCK);
        let parents = protected_parents(path).map_err(|e| e.to_string())?;
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(path)
            .map_err(|e| e.to_string())?;
        let identity = Identity::of(&file.metadata().map_err(|e| e.to_string())?);
        need(
            identity.mode == libc::S_IFREG | 0o600
                && identity.uid == 0
                && identity.gid == 0
                && identity.links == 1,
            "native UI protected original action lock required",
        )?;
        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err("native UI original action lock is held by another invocation".into());
        }
        let result = Self {
            file,
            identity,
            parents,
        };
        result.verify()?;
        Ok(result)
    }
    fn verify(&self) -> Result<(), String> {
        verify_parents(&self.parents).map_err(|e| e.to_string())?;
        need(
            Identity::of(&self.file.metadata().map_err(|e| e.to_string())?) == self.identity
                && Identity::of(&fs::symlink_metadata(ACTION_LOCK).map_err(|e| e.to_string())?)
                    == self.identity,
            "native UI action lock changed",
        )
    }
}

/// One actually launched task, held under the original normal Main and deadline.
/// No Clone/Deserialize or caller task/PID/path constructor exists. Drop performs
/// no Android action: an uncertain operation is never followed by blind cleanup.
pub struct NativeUiSession<'a, 'b> {
    baseline: &'a mut NativeLeafBaselineObservation<'b>,
    target: Target,
    helper: HelperInputs,
    helper_pm: ActualApplicationObservation,
    lock: ActionLock,
    journal: Journal,
    opened_at: Instant,
    end: Instant,
    work_end: Instant,
    before_tasks: BTreeSet<u32>,
    before_task_tree: Option<tasks::Tasks>,
    task: Option<u32>,
    sequence: u32,
    poisoned: bool,
    android_actions: u32,
    engine: Option<crate::control::EngineMappingObservation>,
    cleanup_started: bool,
    stability_started: bool,
}
/// Finished actual UI/task transcript. It intentionally supplies no passed gate,
/// rendering assertion, account assertion, or full application qualification.
pub struct NativeUiTranscript {
    path: PathBuf,
    task: u32,
    operations: u32,
    actions: u32,
    engine: crate::control::EngineMappingObservation,
    journal_custody: Journal,
    original_end: Instant,
    opened_at: Instant,
    finished_at: Instant,
}
impl NativeUiTranscript {
    pub fn journal(&self) -> &Path {
        &self.path
    }
    pub fn task(&self) -> u32 {
        self.task
    }
    pub fn operations(&self) -> u32 {
        self.operations
    }
    pub fn actions(&self) -> u32 {
        self.actions
    }
    pub fn engine(&self) -> &crate::control::EngineMappingObservation {
        &self.engine
    }
}
impl<'a, 'b> NativeUiSession<'a, 'b> {
    pub fn open(
        inspector: &mut NativeApplicationInspector,
        baseline: &'a mut NativeLeafBaselineObservation<'b>,
        end: Instant,
    ) -> Result<Self, String> {
        let opened_at = Instant::now();
        need(
            unsafe { libc::geteuid() } == 0
                && baseline.application().user == 0
                && crate::engine_custody::selected_package(&baseline.application().package)
                && end <= baseline.deadline(),
            "native UI requires one actual selected user-0 baseline and original budget",
        )?;
        baseline
            .verify_local(inspector, end)
            .map_err(|e| e.to_string())?;
        let post =
            super::super::progress::response_timeout(&ControlRequest::InspectApplication {
                package: baseline.application().package.clone(),
                user: 0,
            }) + super::super::progress::response_timeout(&ControlRequest::ObserveRuntimeMain {
                expected_epoch: baseline.application().epoch.clone(),
            }) + super::super::progress::response_timeout(&ControlRequest::InspectApplication {
                package: wire::HELPER_PACKAGE.into(),
                user: 0,
            }) + super::super::progress::response_timeout(
                &ControlRequest::ObserveApplicationEngine {
                    package: baseline.application().package.clone(),
                    user: 0,
                    expected_epoch: baseline.application().epoch.clone(),
                },
            ) + CLEANUP_RESERVE;
        let work_end = end
            .checked_sub(post)
            .filter(|v| *v > Instant::now())
            .ok_or(
                "native UI original lease cannot cover cleanup and actual normal post observations",
            )?;
        let lock = ActionLock::acquire()?;
        let helper = HelperInputs::capture(baseline)?;
        let target = Target::capture(baseline)?;
        let helper_pm = inspector
            .inspect_observed_until(wire::HELPER_PACKAGE, 0, work_end)
            .map_err(|e| e.to_string())?;
        inspector
            .require_observations_local(baseline.main(), &helper_pm, work_end)
            .map_err(|e| e.to_string())?;
        let h = helper_pm.facts();
        need(
            h.package == wire::HELPER_PACKAGE
                && h.user == 0
                && h.uid == HELPER_UID
                && h.version_code == wire::HELPER_VERSION
                && h.apks.len() == 1
                && h.apks[0].name == "base.apk"
                && h.apks[0].bytes == wire::HELPER_APK_BYTES
                && h.apks[0].sha256 == wire::HELPER_APK_SHA256,
            "native UI actual helper complete installed identity differs",
        )?;
        let journal = Journal::create(baseline)?;
        journal.json("BASELINE.json", &serde_json::json!({"schema":"droidloom.native-ui-live.v1",
            "main":baseline.main().facts(),"application":baseline.application(),"helper":h,
            "automatic_retry":false,"production_ready":false,"comparison_documents_create_authority":false}))?;
        let mut session = Self {
            baseline,
            target,
            helper,
            helper_pm,
            lock,
            journal,
            opened_at,
            end,
            work_end,
            before_tasks: BTreeSet::new(),
            before_task_tree: None,
            task: None,
            sequence: 0,
            poisoned: false,
            android_actions: 0,
            engine: None,
            cleanup_started: false,
            stability_started: false,
        };
        session.qualify_entry(inspector)?;
        session.launch(inspector)?;
        let engine = inspector.observe_running_engine_until(
            session.baseline.main(),
            session.baseline.actual_application(),
            session.work_end,
        );
        match engine {
            Ok(engine) => {
                if let Err(error) = session.guard(inspector, session.work_end) {
                    return Err(session.observation_failure(inspector, error));
                }
                session.engine = Some(engine);
            }
            Err(error) => return Err(session.observation_failure(inspector, error.to_string())),
        }
        Ok(session)
    }
    fn guard(&self, inspector: &NativeApplicationInspector, end: Instant) -> Result<(), String> {
        before(end.min(self.end))?;
        self.baseline
            .verify_local(inspector, end.min(self.end))
            .map_err(|e| e.to_string())?;
        inspector
            .require_observations_local(self.baseline.main(), &self.helper_pm, end.min(self.end))
            .map_err(|e| e.to_string())?;
        self.target.verify()?;
        self.helper.verify()?;
        self.lock.verify()?;
        self.journal.verify()?;
        before(end.min(self.end))
    }
    fn run(
        &mut self,
        inspector: &NativeApplicationInspector,
        label: &str,
        literal: Vec<String>,
        shell: bool,
        mutation: bool,
        cap: Duration,
        limit: super::NativeUiOutput,
        until: Instant,
    ) -> Result<Output, String> {
        need(
            !self.poisoned && self.sequence < 512,
            "native UI session is poisoned or its fixed operation count is exhausted",
        )?;
        self.guard(inspector, until)?;
        self.sequence += 1;
        self.poisoned = true;
        let index = self.sequence;
        self.journal.json(&format!("{index:04}-INTENT.json"), &serde_json::json!({
            "label":label,"literal_sha256":format!("{:x}",Sha256::digest(serde_json::to_vec(&literal).map_err(|e|e.to_string())?)),
            "mutation":mutation,"automatic_retry":false,"comparison_only":true}))?;
        let result: Result<Output, String> = (|| {
            let command_end = (Instant::now() + cap).min(until);
            before(command_end)?;
            let (command, inherit) = self.target.command(
                &self.helper,
                &literal,
                shell,
                cap.min(command_end.saturating_duration_since(Instant::now())),
            )?;
            if mutation {
                self.android_actions += 1;
            }
            let mut guard = || self.guard(inspector, command_end);
            let output = super::run_owned_native_ui(
                command,
                &inherit,
                &[
                    self.target.init.pidfd.as_raw_fd(),
                    self.target.framework.pidfd.as_raw_fd(),
                ],
                command_end,
                limit,
                &mut guard,
            )?;
            self.journal
                .write(&format!("{index:04}-stdout.bin"), &output.stdout)?;
            self.journal
                .write(&format!("{index:04}-stderr.bin"), &output.stderr)?;
            self.journal.json(&format!("{index:04}-RESULT.json"), &serde_json::json!({
                "exit_code":output.status.code(),"host_invocation_retired":true,"automatic_retry":false,
                "android_mutation_attempted":mutation,"business_accepted":false}))?;
            self.guard(inspector, command_end)?;
            need(
                output.status.code() == Some(0) && output.stderr.is_empty(),
                "native UI fixed command failed; its actual raw output is retained",
            )?;
            Ok(output)
        })();
        match result {
            Ok(output) => {
                self.poisoned = false;
                Ok(output)
            }
            Err(error) => {
                let retained = self.journal.json(&format!("{index:04}-FAILED.json"),
                    &serde_json::json!({"error":error,"outcome_unknown":mutation,"automatic_retry":false}));
                Err(format!(
                    "{error}; native UI session remains poisoned; private history={}; failure_record={}",
                    self.journal.path.display(),
                    retained.is_ok()
                ))
            }
        }
    }
    fn qualify_entry(&mut self, inspector: &NativeApplicationInspector) -> Result<(), String> {
        for (name, args, expected) in [
            (
                "guest-uid",
                vec!["/system/bin/toybox", "id", "-u"],
                b"0\n".as_slice(),
            ),
            (
                "guest-gid",
                vec!["/system/bin/toybox", "id", "-g"],
                b"0\n".as_slice(),
            ),
            (
                "boot-completed",
                vec!["/system/bin/getprop", "sys.boot_completed"],
                b"1\n".as_slice(),
            ),
        ] {
            let out = self.run(
                inspector,
                name,
                args.into_iter().map(str::to_owned).collect(),
                false,
                false,
                Duration::from_secs(15),
                super::NativeUiOutput::Small,
                self.work_end,
            )?;
            if out.stdout != expected {
                self.poisoned = true;
                return Err(format!(
                    "native UI same-Main read-only entry check {name} differs; no retry"
                ));
            }
        }
        Ok(())
    }
    fn stacks(
        &mut self,
        inspector: &NativeApplicationInspector,
        end: Instant,
    ) -> Result<tasks::Tasks, String> {
        let out = self.run(
            inspector,
            "actual-task-list",
            ["/system/bin/cmd", "activity", "stack", "list"]
                .into_iter()
                .map(str::to_owned)
                .collect(),
            true,
            false,
            Duration::from_secs(15),
            super::NativeUiOutput::Small,
            end,
        )?;
        tasks::Tasks::parse(&out.stdout).inspect_err(|_| self.poisoned = true)
    }
    fn owner_reply(&self, reply: &crate::control::ControlResponse) -> Result<(), String> {
        need(
            reply.ok
                && reply.state == CellState::Running
                && reply.host_pid == Some(self.baseline.application().epoch.cell_host_pid),
            "native UI normal response belongs to another owner or failed",
        )
    }
    fn launch(&mut self, inspector: &mut NativeApplicationInspector) -> Result<(), String> {
        self.guard(inspector, self.work_end)?;
        let reply = inspector
            .request_fixed_until(
                &ControlRequest::ListApplications { user: 0 },
                Some(self.work_end),
            )
            .map_err(|e| e.to_string())?;
        self.owner_reply(&reply)?;
        let package = self.baseline.application().package.clone();
        let catalog = reply
            .applications
            .ok_or("native UI normal launcher catalog absent")?;
        let candidates = catalog
            .into_iter()
            .filter(|c| c.package == package)
            .map(|c| c.component)
            .collect::<BTreeSet<_>>();
        need(
            candidates.len() == 1,
            "native UI selected package has no unique normal MAIN/LAUNCHER component",
        )?;
        let component = candidates.into_iter().next().unwrap();
        crate::control::validate_component(&component).map_err(|e| e.to_string())?;
        let before = self.stacks(inspector, self.work_end)?;
        need(
            !before.contains_package(&package),
            "native UI preexisting target task must be preserved",
        )?;
        self.before_tasks = before.ids.clone();
        self.journal.json("LAUNCH-INTENT.json",&serde_json::json!({
            "package":package,"component":component,"before_task_ids":self.before_tasks,"automatic_retry":false}))?;
        self.poisoned = true;
        let reply = inspector
            .request_fixed_until(
                &ControlRequest::Launch {
                    spec: PathBuf::from(crate::control::DEFAULT_CELL_SPEC),
                    package: package.clone(),
                    component: Some(component),
                    resolution: None,
                    user: 0,
                },
                Some(self.work_end),
            )
            .map_err(|e| e.to_string())?;
        self.journal.json("LAUNCH-RESULT.json", &reply)?;
        self.owner_reply(&reply)?;
        need(
            reply.inspection.as_ref() == Some(self.baseline.application()),
            "native UI launch changed complete PM identity",
        )?;
        let task = tasks::launch_task(
            reply
                .launch
                .as_deref()
                .ok_or("native UI actual native launch binding absent")?,
        )?;
        need(
            !before.ids.contains(&task) && !before.roots.contains_key(&task),
            "native UI launch reused a preexisting task",
        )?;
        self.poisoned = false;
        let after = self.stacks(inspector, self.work_end)?;
        if !after.exact_leaf(task, &package)
            || !after.preserves_other_tasks(&self.before_tasks, task)
        {
            self.poisoned = true;
            return Err("native UI launch did not create exactly one new owned freeform leaf; no cleanup guessed".into());
        }
        self.task = Some(task);
        // Retain the actual complete pre-launch tree for a later strict pair
        // consumer. The existing single-task checks remain unchanged.
        self.before_task_tree = Some(before);
        self.journal.json(
            "OWNED-TASK.json",
            &serde_json::json!({"task":task,"package":package,
            "prelaunch_absent":true,"other_tasks_preserved":true,"business_accepted":false}),
        )?;
        self.guard(inspector, self.work_end)
    }
    fn owned_task(
        &mut self,
        inspector: &NativeApplicationInspector,
        end: Instant,
    ) -> Result<(), String> {
        let task = self.task.ok_or("native UI has no actual owned task")?;
        let package = self.baseline.application().package.clone();
        let current = self.stacks(inspector, end)?;
        if !current.exact_leaf(task, &package)
            || !current.preserves_other_tasks(&self.before_tasks, task)
        {
            self.poisoned = true;
            return Err("native UI task or preexisting task set changed".into());
        }
        Ok(())
    }
    fn ui(
        &mut self,
        inspector: &NativeApplicationInspector,
        operation: wire::Operation,
    ) -> Result<wire::Reply, String> {
        self.owned_task(inspector, self.work_end)?;
        let request = wire::Request::new(&self.baseline.application().package, operation)
            .map_err(|e| e.to_string())?;
        let out = self.run(
            inspector,
            request.operation(),
            request.arguments().map_err(|e| e.to_string())?,
            true,
            request.mutation(),
            COMMAND_CAP,
            super::NativeUiOutput::Helper,
            self.work_end,
        )?;
        let reply = wire::Reply::parse(&request, &out)
            .inspect_err(|_| self.poisoned = true)
            .map_err(|e| e.to_string())?;
        self.owned_task(inspector, self.work_end)?;
        Ok(reply)
    }
    pub fn meta(&mut self, inspector: &NativeApplicationInspector) -> Result<wire::Reply, String> {
        self.ui(inspector, wire::Operation::Meta)
    }
    pub fn dump(&mut self, inspector: &NativeApplicationInspector) -> Result<wire::Reply, String> {
        self.ui(inspector, wire::Operation::Dump)
    }
    pub fn find(
        &mut self,
        inspector: &NativeApplicationInspector,
        selector: wire::Selector,
    ) -> Result<wire::Reply, String> {
        self.ui(inspector, wire::Operation::Find(selector))
    }
    pub fn click(
        &mut self,
        inspector: &NativeApplicationInspector,
        selector: wire::Selector,
    ) -> Result<wire::Reply, String> {
        self.ui(inspector, wire::Operation::Click(selector))
    }
    pub fn set_text(
        &mut self,
        inspector: &NativeApplicationInspector,
        selector: wire::Selector,
        value: &str,
    ) -> Result<wire::Reply, String> {
        let found = self.find(inspector, selector.clone())?;
        let rows = found.body()["matches"]
            .as_array()
            .ok_or("native UI target matches absent")?;
        need(
            rows.len() == 1 && rows[0]["editable"] == true && rows[0]["password"] == false,
            "native UI text requires one actual non-password editable control",
        )?;
        self.ui(
            inspector,
            wire::Operation::SetText {
                selector,
                value: value.into(),
            },
        )
    }
    /// One explicit source-owned cleanup. This is available only while the
    /// original session is certain and the exact new task still compares equal.
    /// A normal read failure keeps its first error even if cleanup succeeds.
    fn close_known_task(&mut self, inspector: &NativeApplicationInspector) -> Result<(), String> {
        need(
            !self.poisoned && !self.cleanup_started,
            "native UI cleanup is uncertain or has already been attempted",
        )?;
        self.guard(inspector, self.end)?;
        let task = self.task.ok_or("native UI original owned task absent")?;
        let package = self.baseline.application().package.clone();
        self.cleanup_started = true;
        let current = self.stacks(inspector, self.end)?;
        need(
            current.preserves_other_tasks(&self.before_tasks, task),
            "native UI other tasks changed before cleanup",
        )?;
        if !current.absent(task) {
            need(
                current.exact_leaf(task, &package),
                "native UI cleanup target is no longer the exact new leaf",
            )?;
            self.journal.json(
                "CLEANUP-INTENT.json",
                &serde_json::json!({"task":task,"automatic_retry":false}),
            )?;
            self.run(
                inspector,
                "remove-one-owned-task",
                vec![
                    "/system/bin/cmd".into(),
                    "activity".into(),
                    "stack".into(),
                    "remove".into(),
                    task.to_string(),
                ],
                true,
                true,
                Duration::from_secs(20),
                super::NativeUiOutput::Small,
                self.end,
            )?;
            let until = (Instant::now() + Duration::from_secs(8)).min(self.end);
            let mut removed = false;
            for _ in 0..32 {
                before(until)?;
                std::thread::sleep(Duration::from_millis(100));
                let observed = self.stacks(inspector, until)?;
                need(
                    observed.preserves_other_tasks(&self.before_tasks, task),
                    "native UI other tasks changed during removal",
                )?;
                if observed.absent(task) {
                    removed = true;
                    break;
                }
                need(
                    observed.exact_leaf(task, &package) || observed.shrinking_leaf(task),
                    "native UI owned task changed during asynchronous removal",
                )?;
            }
            need(
                removed,
                "native UI task removal completion remains unknown; removal is not repeated",
            )?;
        }
        self.guard(inspector, self.end)?;
        self.journal.json(
            "CLEANUP-COMPLETE.json",
            &serde_json::json!({
            "task":task,"actual_owned_task_absent":true,"other_tasks_preserved":true,
            "automatic_retry":false,"business_accepted":false}),
        )?;
        Ok(())
    }
    fn observation_failure(
        &mut self,
        inspector: &NativeApplicationInspector,
        first: String,
    ) -> String {
        let recorded = self.journal.json("OBSERVATION-FAILURE.json", &serde_json::json!({
            "first_error":first,"observation_only":true,"automatic_retry":false,"business_accepted":false}));
        let cleanup = if recorded.is_ok()
            && !self.poisoned
            && !self.cleanup_started
            && self.task.is_some()
        {
            self.close_known_task(inspector)
        } else {
            Err("native UI first error retained; uncertain or already-attempted cleanup stays isolated".into())
        };
        self.poisoned = true;
        let after = self.journal.json("FAILED-CASE-CLEANUP.json", &serde_json::json!({
            "first_error":first,"known_task_cleanup_completed":cleanup.is_ok(),
            "cleanup_error":cleanup.as_ref().err(),"automatic_retry":false,"business_accepted":false}));
        format!(
            "{first}; retained first observation failure; known-task cleanup={}; final_record={}; history={}",
            cleanup
                .as_ref()
                .map(|_| "completed")
                .unwrap_or("not completed"),
            after.is_ok(),
            self.journal.path.display()
        )
    }
    pub fn finish(
        self,
        inspector: &mut NativeApplicationInspector,
    ) -> Result<NativeUiTranscript, String> {
        self.close_before_bookends(inspector)?
            .finish_bookends(inspector)
    }
    fn close_before_bookends(
        mut self,
        inspector: &mut NativeApplicationInspector,
    ) -> Result<Self, String> {
        need(
            !self.poisoned,
            "native UI uncertain action forbids automatic follow-up cleanup",
        )?;
        self.task.ok_or("native UI original owned task absent")?;
        if let Err(error) = inspector.revalidate_engine_until(
            self.baseline.main(),
            self.baseline.actual_application(),
            self.engine
                .as_ref()
                .ok_or("native UI original running Engine observation absent")?,
            self.end,
        ) {
            return Err(self.observation_failure(inspector, error.to_string()));
        }
        self.close_known_task(inspector)?;
        Ok(self)
    }
    fn finish_bookends(
        mut self,
        inspector: &mut NativeApplicationInspector,
    ) -> Result<NativeUiTranscript, String> {
        need(
            self.cleanup_started && !self.poisoned,
            "native UI final bookends require the successful original owned close",
        )?;
        let task = self.task.ok_or("native UI original owned task absent")?;
        let package = self.baseline.application().package.clone();
        let after_helper = inspector
            .inspect_observed_until(wire::HELPER_PACKAGE, 0, self.end)
            .map_err(|e| e.to_string())?;
        inspector
            .require_observations_local(self.baseline.main(), &after_helper, self.end)
            .map_err(|e| e.to_string())?;
        need(
            after_helper.facts() == self.helper_pm.facts(),
            "native UI helper complete PM identity changed",
        )?;
        let after_main = inspector
            .refresh_main_until(self.baseline.main(), self.end)
            .map_err(|e| e.to_string())?;
        let after_app = inspector
            .inspect_observed_until(&package, 0, self.end)
            .map_err(|e| e.to_string())?;
        self.baseline
            .finish_from_observed(inspector, &after_main, &after_app, self.end)
            .map_err(|e| e.to_string())?;
        self.helper.full()?;
        self.guard(inspector, self.end)?;
        self.journal.json("FINISHED.json",&serde_json::json!({"schema":"droidloom.native-ui-finished.v1",
            "task":task,"operations":self.sequence,"actions":self.android_actions,"owned_task_absent":true,
            "other_tasks_preserved":true,"actual_normal_PM_Main_bookends":true,"business_accepted":false,
            "production_ready":false,"automatic_retry":false}))?;
        let finished_at = Instant::now();
        before(self.end)?;
        Ok(NativeUiTranscript {
            path: self.journal.path.clone(),
            task,
            operations: self.sequence,
            actions: self.android_actions,
            engine: self
                .engine
                .take()
                .ok_or("native UI original running Engine observation absent")?,
            journal_custody: self.journal,
            original_end: self.end,
            opened_at: self.opened_at,
            finished_at,
        })
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn native_ui_environment_is_actual_closed_whitelist_with_no_host_or_duplicate_substitution() {
        let bytes = b"PATH=/system/bin\0BOOTCLASSPATH=/apex/art/core.jar\0DEX2OATBOOTCLASSPATH=/apex/art/core.jar\0ANDROID_ART_ROOT=/apex/com.android.art\0ANDROID_ROOT=/system\0ANDROID_DATA=/data\0SECRET=not exported\0";
        let env = environment(bytes).unwrap();
        assert_eq!(env.len(), 6);
        assert!(!env.contains_key("SECRET"));
        let mut duplicate = bytes.to_vec();
        duplicate.extend_from_slice(b"PATH=/host/bin\0");
        assert!(environment(&duplicate).is_err());
        assert!(environment(b"PATH=/system/bin\0").is_err());
        assert!(
            environment(
                &String::from_utf8_lossy(bytes)
                    .replace("ANDROID_DATA=/data", "ANDROID_DATA=/host")
                    .into_bytes()
            )
            .is_err()
        );
    }
}
