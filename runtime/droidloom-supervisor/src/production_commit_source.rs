//! Production actor admission from a fixed normal configuration and this boot.
//! The two entry roles own different effects. Neither accepts a saved Complete.
use super::*;
use crate::{native_hardware_label as held, native_working_contract as working};
use std::collections::BTreeMap;
use std::ffi::{CString, OsString};
use std::os::unix::fs::MetadataExt;
const WITNESS: &str = "/run/droidloom-early/host-mount-identity.json";
#[derive(Clone, Copy, PartialEq, Eq)]
pub(super) enum Actor {
    Commit,
    Verify,
    Return,
}
impl Actor {
    fn role(self) -> &'static [u8] {
        if self == Self::Commit {
            b"u:system_r:p4_linux_production_commit_t:s0"
        } else {
            b"u:system_r:p4_linux_production_verify_t:s0"
        }
    }
    fn profile(self) -> &'static [u8] {
        if self == Self::Commit {
            b"droidloom-production-commit (enforce)"
        } else {
            b"droidloom-production-verify (enforce)"
        }
    }
    pub(super) fn mode(self) -> &'static str {
        match self {
            Self::Commit => c::COMMIT_MODE,
            Self::Verify => c::OBSERVE_MODE,
            Self::Return => c::RETURN_MODE,
        }
    }
    pub(super) fn unit(self) -> &'static str {
        match self {
            Self::Commit => working::PARENT_UNIT,
            Self::Verify => c::VERIFY_UNIT,
            Self::Return => c::RETURN_UNIT,
        }
    }
}
pub(super) fn text(path: &str, limit: usize) -> io::Result<String> {
    let f = File::open(path)?;
    let mut b = vec![0; limit + 1];
    let n = f.read_at(&mut b, 0)?;
    if n > limit {
        return Err(error("production observation exceeds its fixed bound"));
    }
    String::from_utf8(b[..n].to_vec())
        .map(|s| s.trim_end_matches(['\n', '\0']).into())
        .map_err(io::Error::other)
}
fn single<'a>(s: &'a str, key: &str) -> io::Result<&'a str> {
    let mut rows = s.lines().filter_map(|r| r.strip_prefix(key));
    let v = rows
        .next()
        .ok_or_else(|| error("actual status omitted required field"))?
        .trim();
    if rows.next().is_some() {
        return Err(error("duplicate actual status field"));
    }
    Ok(v)
}
const PTRACECAP: u64 = 1 << 19;
const PARENT_BOUND: u64 = (1 << 6) | (1 << 7) | PTRACECAP;
#[repr(C)]
struct CapHeader {
    version: u32,
    pid: i32,
}
#[repr(C)]
#[derive(Clone, Copy, Default)]
struct CapData {
    effective: u32,
    permitted: u32,
    inheritable: u32,
}
fn cap_values() -> io::Result<[u64; 3]> {
    let h = CapHeader {
        version: 0x20080522,
        pid: 0,
    };
    let mut d = [CapData::default(); 2];
    if unsafe { libc::syscall(libc::SYS_capget, &h, d.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok([
        u64::from(d[0].permitted) | (u64::from(d[1].permitted) << 32),
        u64::from(d[0].effective) | (u64::from(d[1].effective) << 32),
        u64::from(d[0].inheritable) | (u64::from(d[1].inheritable) << 32),
    ])
}
fn caps(actor: Actor, exe: &File, initial: bool) -> io::Result<()> {
    let bound = if actor == Actor::Commit {
        PARENT_BOUND
    } else {
        PTRACECAP
    };
    let raw = text("/proc/self/status", 16384)?;
    if single(&raw, "CapBnd:")? != format!("{bound:016x}")
        || single(&raw, "CapAmb:")? != "0000000000000000"
        || single(&raw, "TracerPid:")? != "0"
        || (initial && single(&raw, "Threads:")? != "1")
    {
        return Err(error(
            "production actor capability bound, tracer or initial thread differs",
        ));
    }
    let x = unsafe {
        libc::fgetxattr(
            exe.as_raw_fd(),
            c"security.capability".as_ptr(),
            std::ptr::null_mut(),
            0,
        )
    };
    if x != -1 || io::Error::last_os_error().raw_os_error() != Some(libc::ENODATA) {
        return Err(error("production executable has unknown file capabilities"));
    }
    if unsafe { libc::prctl(libc::PR_GET_SECUREBITS, 0, 0, 0, 0) } != 0 {
        return Err(error("production securebits differ"));
    }
    let current = cap_values()?;
    let nnp = unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) };
    if initial && current == [bound, bound, 0] && nnp == 0 {
        let h = CapHeader {
            version: 0x20080522,
            pid: 0,
        };
        let mut d = [CapData::default(); 2];
        d[0].permitted = PTRACECAP as u32;
        d[0].effective = PTRACECAP as u32;
        if unsafe { libc::syscall(libc::SYS_capset, &h, d.as_ptr()) } != 0
            || unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) } != 0
            || unsafe { libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0) } != 0
        {
            return Err(io::Error::last_os_error());
        }
    }
    if cap_values()? != [PTRACECAP, PTRACECAP, 0]
        || unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) } != 1
        || unsafe { libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0) } != 0
    {
        return Err(error(
            "production actor did not retain its exact sealed capability state",
        ));
    }
    Ok(())
}
fn command_line(
    raw: &str,
    actor: Actor,
    config: &c::BytesPin,
    source: &c::Configuration,
) -> io::Result<()> {
    let mut fields = BTreeMap::new();
    for part in raw.split_ascii_whitespace() {
        if let Some((k, v)) = part.split_once('=') {
            if actor == Actor::Commit && k == "systemd.mask" {
                continue;
            }
            if fields.insert(k, v).is_some() {
                return Err(error("production boot command line duplicates a key"));
            }
        }
    }
    for (k, v) in [
        ("root", format!("UUID={}", working::ROOT_UUID)),
        ("init", "/usr/lib/droidloom/board-init".into()),
        ("lsm", c::LSM_ORDER.into()),
        ("enforcing", "1".into()),
        ("selinux", "1".into()),
        ("audit", "1".into()),
        ("panic", "10".into()),
    ] {
        if fields.get(k).copied() != Some(v.as_str()) {
            return Err(error("production boot mandatory kernel argument differs"));
        }
    }
    if actor == Actor::Commit {
        let args = working::boot_arguments(raw)?;
        if args["droidloom.working"] != source.working_intent_sha256
            || args["droidloom.working.config"] != source.working_early_sha256
        {
            return Err(error("commit is not the admitted working boot"));
        }
    } else {
        if fields.get("droidloom.production").copied() != Some(source.candidate_id.as_str())
            || fields.get("droidloom.production.source").copied() != Some(config.sha256.as_str())
            || fields.get("systemd.wants").copied() != Some(c::VERIFY_UNIT)
            || fields
                .keys()
                .any(|k| k.starts_with("droidloom.working") || k.starts_with("droidloom.once"))
            || fields.contains_key("systemd.unit")
        {
            return Err(error(
                "normal production entry differs or is a qualification boot",
            ));
        }
    }
    Ok(())
}
pub(super) struct Sources {
    pub config: c::Configuration,
    pub config_input: pio::Input,
    pub boot_id: String,
    pub actor: Actor,
    pub application: pio::Input,
    pub cell: pio::Input,
    pub selection: pio::Input,
    pub grub: pio::Input,
    pub systemctl: pio::Input,
    pub journalctl: pio::Input,
    normal_initrd: pio::Input,
    grub_cfg: pio::Input,
    custom: pio::Input,
    prefix: pio::Input,
    returned: pio::Input,
    witness: pio::Input,
    root: File,
    root_identity: [u64; 5],
    pid: u32,
}
impl Sources {
    pub(super) fn open(actor: Actor, expected: Option<&c::BytesPin>) -> io::Result<Self> {
        let argv = std::env::args_os().collect::<Vec<OsString>>();
        if argv != [OsString::from(c::EXECUTABLE), OsString::from(actor.mode())]
            || unsafe {
                (
                    libc::getuid(),
                    libc::geteuid(),
                    libc::getgid(),
                    libc::getegid(),
                )
            } != (0, 0, 0, 0)
            || held::current(101)? != actor.role()
            || held::current(104)? != actor.profile()
        {
            return Err(error(
                "production actor requires its exact fixed argv/root/dual MAC",
            ));
        }
        let raw_cmdline = text("/proc/cmdline", 32768)?;
        let n = fs::symlink_metadata(c::CONFIG)?.len();
        if n == 0 || n > 65536 {
            return Err(error("production configuration size differs"));
        }
        let config_pin = if actor == Actor::Commit {
            expected
                .cloned()
                .ok_or_else(|| error("commit needs the actual private parent source"))?
        } else {
            if expected.is_some() {
                return Err(error("normal verifier cannot accept a caller source"));
            }
            let mut values = raw_cmdline
                .split_ascii_whitespace()
                .filter_map(|p| p.strip_prefix("droidloom.production.source="));
            let sha = values
                .next()
                .ok_or_else(|| error("normal boot has no source commitment"))?;
            if values.next().is_some() {
                return Err(error("duplicate normal source commitment"));
            }
            c::BytesPin {
                bytes: n,
                sha256: sha.into(),
            }
        };
        if config_pin.bytes != n {
            return Err(error("production config whole size differs"));
        }
        let config_input = pio::Input::open(
            Path::new(c::CONFIG),
            &config_pin,
            0o400,
            Some(b"u:object_r:p4_linux_production_config_t:s0"),
        )?;
        let config: c::Configuration = serde_json::from_slice(&config_input.bytes(65536)?)?;
        config.validate()?;
        command_line(&raw_cmdline, actor, &config_pin, &config)?;
        let application =
            pio::Input::open(Path::new(c::EXECUTABLE), &config.applications, 0o755, None)?;
        if f9(&File::open("/proc/self/exe")?)? != application.identity {
            return Err(error("production actor is not the actual normal held ELF"));
        }
        caps(actor, &application.file, true)?;
        let root = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open("/")?;
        held::directory(&root)?;
        held::namespaces(&root)?;
        let root_pin = f9(&root)?;
        let mut info = std::mem::MaybeUninit::<libc::statfs>::uninit();
        let block = fs::metadata(format!("/dev/disk/by-uuid/{}", working::ROOT_UUID))?;
        if unsafe { libc::fstatfs(root.as_raw_fd(), info.as_mut_ptr()) } != 0
            || unsafe { info.assume_init() }.f_type != 0xef53
            || root_pin[1] != 2
            || block.mode() & libc::S_IFMT != libc::S_IFBLK
            || block.rdev() != root_pin[0]
        {
            return Err(error("production is outside the original held ext4 root"));
        }
        let boot_id = text("/proc/sys/kernel/random/boot_id", 64)?;
        if !working::uuid(&boot_id) {
            return Err(error("production actual boot id differs"));
        }
        let cell = pio::Input::open(
            Path::new("/etc/droidloom/cell.json"),
            &config.cell,
            0o644,
            None,
        )?;
        let selection = pio::Input::open(
            Path::new("/etc/droidloom/production/selected.json"),
            &config.selection,
            0o400,
            None,
        )?;
        let normal_initrd =
            pio::Input::open(&config.initrd()?, &config.normal_initrd, 0o400, None)?;
        let grub_cfg = pio::Input::open(
            Path::new(c::CFG),
            &config.original_grub_cfg,
            config.original_grub_cfg_mode,
            None,
        )?;
        let prefix = pio::Input::open(
            Path::new(c::PREFIX),
            &config.original_custom,
            0o400,
            Some(b"u:object_r:p4_linux_production_config_t:s0"),
        )?;
        let return_bytes = fs::read(working::RETURN_CONFIG)?;
        if return_bytes.is_empty() || return_bytes.len() > 65536 {
            return Err(error("working source size differs"));
        }
        let return_pin = c::BytesPin {
            bytes: return_bytes.len() as u64,
            sha256: sha(&return_bytes),
        };
        let returned = pio::Input::open(
            Path::new(working::RETURN_CONFIG),
            &return_pin,
            0o400,
            Some(b"u:object_r:p4_linux_working_config_t:s0"),
        )?;
        let r: working::WorkingReturnConfiguration =
            serde_json::from_slice(&returned.bytes(65536)?)?;
        r.validate()?;
        let mut core = r.clone();
        core.production_commit = None;
        let body = serde_json::to_vec(&core)?;
        if (c::BytesPin {
            bytes: body.len() as u64,
            sha256: sha(&body),
        }) != config.working_return_core
            || r.production_commit.as_ref().map(|p| (&p.sha256, p.bytes))
                != Some((&config_pin.sha256, config_pin.bytes))
            || r.candidate_id != config.candidate_id
            || r.intent_sha256 != config.working_intent_sha256
            || r.early_config_sha256 != config.working_early_sha256
        {
            return Err(error(
                "normal working source core differs from fixed production source",
            ));
        }
        let mut expected_custom = prefix.bytes(1024 * 1024)?;
        expected_custom.extend_from_slice(
            c::working_entry(
                &r.candidate_id,
                &r.intent_sha256,
                &r.early_config_sha256,
                &return_pin.sha256,
            )?
            .as_bytes(),
        );
        expected_custom.extend_from_slice(
            c::ordinary_entry(&config.candidate_id, &config_pin.sha256)?.as_bytes(),
        );
        expected_custom.extend_from_slice(c::selector(&config.candidate_id)?.as_bytes());
        let custom = pio::Input::open(
            Path::new(c::CUSTOM),
            &c::BytesPin {
                bytes: expected_custom.len() as u64,
                sha256: sha(&expected_custom),
            },
            0o644,
            None,
        )?;
        let grub = pio::Input::open(Path::new(c::GRUB_TOOL), &config.grub_editenv, 0o755, None)?;
        let systemctl = pio::Input::open(Path::new(c::SYSTEMCTL), &config.systemctl, 0o755, None)?;
        let journalctl =
            pio::Input::open(Path::new(c::JOURNALCTL), &config.journalctl, 0o755, None)?;
        let witness_raw = fs::read(WITNESS)?;
        if witness_raw.is_empty() || witness_raw.len() > 512 {
            return Err(error("actual early mount witness bound differs"));
        }
        let witness = pio::Input::open(
            Path::new(WITNESS),
            &c::BytesPin {
                bytes: witness_raw.len() as u64,
                sha256: sha(&witness_raw),
            },
            0o400,
            Some(b"u:object_r:p4_linux_host_mount_identity_t:s0"),
        )?;
        let s = Self {
            config,
            config_input,
            boot_id,
            actor,
            application,
            cell,
            selection,
            grub,
            systemctl,
            journalctl,
            normal_initrd,
            grub_cfg,
            custom,
            prefix,
            returned,
            witness,
            root,
            root_identity: root_pin[..5].try_into().unwrap(),
            pid: std::process::id(),
        };
        s.guard()?;
        Ok(s)
    }
    pub(super) fn guard(&self) -> io::Result<()> {
        if std::process::id() != self.pid
            || held::current(101)? != self.actor.role()
            || held::current(104)? != self.actor.profile()
            || text("/proc/sys/kernel/random/boot_id", 64)? != self.boot_id
            || text("/proc/sys/kernel/osrelease", 256)? != working::KERNEL
            || text("/sys/fs/selinux/enforce", 8)? != "1"
            || text("/proc/self/cgroup", 4096)? != format!("0::/system.slice/{}", self.actor.unit())
        {
            return Err(error(
                "production actor left its fixed actual role/boot/unit",
            ));
        }
        caps(self.actor, &self.application.file, false)?;
        held::namespaces(&self.root)?;
        if f9(&self.root)?[..5] != self.root_identity
            || f9(&OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open("/")?)?[..5]
                != self.root_identity
            || f9(&File::open("/proc/self/exe")?)? != self.application.identity
        {
            return Err(error("production root or executing inode changed"));
        }
        for i in [
            &self.config_input,
            &self.application,
            &self.cell,
            &self.selection,
            &self.normal_initrd,
            &self.grub_cfg,
            &self.custom,
            &self.prefix,
            &self.returned,
            &self.grub,
            &self.systemctl,
            &self.journalctl,
            &self.witness,
        ] {
            i.guard()?;
        }
        let w: Value = serde_json::from_slice(&self.witness.bytes(512)?)?;
        let ns = File::open("/proc/self/ns/mnt")?;
        let m = ns.metadata()?;
        if w["schema"] != "droidloom.host-mount-identity.v1"
            || w["boot_id"] != self.boot_id
            || w["joint_policy_sha256"] != self.config.joint_policy_sha256
            || w["device"] != m.dev()
            || w["inode"] != m.ino()
            || unsafe { libc::ioctl(ns.as_raw_fd(), 0xb703 as libc::c_ulong, 0 as libc::c_ulong) }
                != libc::CLONE_NEWNS
        {
            return Err(error(
                "production original namespace lacks the current early witness",
            ));
        }
        Ok(())
    }
    pub(super) fn compare_main(
        &self,
        observed: &crate::control::MainCustodyObservation,
    ) -> io::Result<()> {
        self.guard()?;
        let m = observed.facts();
        let r: Value = serde_json::from_slice(&self.selection.bytes(128 * 1024 * 1024)?)?;
        let s = |k: &str| {
            r[k].as_str()
                .ok_or_else(|| error("normal selection omitted source field"))
        };
        let cohort = s("base_cohort_sha256")?;
        let runtime = s("runtime_manifest_sha256")?;
        let mut h = Sha256::new();
        h.update(b"droidloom-package-selection-v1\0");
        for f in [&self.selection, &self.cell] {
            let meta = f.file.metadata()?;
            for n in [
                meta.dev(),
                meta.ino(),
                u64::from(meta.mode()),
                u64::from(meta.uid()),
                u64::from(meta.gid()),
                meta.nlink(),
                meta.len(),
            ] {
                h.update(n.to_le_bytes());
            }
            for n in [
                meta.mtime(),
                meta.mtime_nsec(),
                meta.ctime(),
                meta.ctime_nsec(),
            ] {
                h.update(n.to_le_bytes());
            }
            h.update(f.pin.sha256.as_bytes());
        }
        h.update(cohort.as_bytes());
        h.update(runtime.as_bytes());
        let normal: crate::normal_host_release::NormalHostRelease =
            serde_json::from_value(r["normal_host_release"].clone())?;
        normal.validate().map_err(|e| error(&e.to_string()))?;
        let origin: crate::native_once_contract::OriginalCopyPolicy =
            serde_json::from_value(r["persistent_data"]["original_copy"].clone())?;
        origin.validate().map_err(|e| error(&e.to_string()))?;
        let actual = m
            .persistent_data
            .original_copy_origin
            .as_ref()
            .ok_or_else(|| error("production Main lacks the original copy lineage"))?;
        if m.epoch.boot_id != self.boot_id
            || m.owner.host_uid != 1000
            || r["host_uid"] != 1000
            || m.owner.base_cohort_sha256 != cohort
            || m.owner.runtime_manifest_sha256 != runtime
            || m.owner.selection_binding_sha256 != format!("{:x}", h.finalize())
            || r["cell_spec_bytes"] != self.cell.pin.bytes
            || r["cell_spec_sha256"] != self.cell.pin.sha256
            || m.normal_host_release != normal
            || actual.schema != origin.schema
            || actual.working_copy_sha256 != origin.working_copy_sha256
            || actual.cold_clone_sha256 != origin.cold_clone_sha256
            || actual.original != origin.original
            || actual.working != origin.working
            || m.persistent_data.fresh_diagnostic_origin.is_some()
            || [
                m.persistent_data.backings[0].backing.stable7(),
                m.persistent_data.backings[1].backing.stable7(),
            ] != origin.working
        {
            return Err(error(
                "fresh actual normal Main differs from the same accepted selection and working pair",
            ));
        }
        self.guard()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn production_commit_and_normal_boot_require_the_same_selected_scm_provider_order() {
        let pin = c::BytesPin {
            bytes: 1,
            sha256: "a".repeat(64),
        };
        let mut value = json!({"schema":"droidloom.production-commit-source.v1",
            "candidate_id":"b".repeat(64),"working_intent_sha256":"c".repeat(64),
            "working_early_sha256":"d".repeat(64),"joint_policy_sha256":"e".repeat(64),
            "source_commit":"f".repeat(40),"source_tree":"a".repeat(40),"original_grub_cfg_mode":420});
        for field in [
            "applications",
            "cell",
            "selection",
            "normal_initrd",
            "working_return_core",
            "original_grub_cfg",
            "original_custom",
            "grub_editenv",
            "systemctl",
            "journalctl",
        ] {
            value[field] = serde_json::to_value(&pin).unwrap();
        }
        let config: c::Configuration = serde_json::from_value(value).unwrap();
        config.validate().unwrap();
        let entry = c::working_entry(
            &config.candidate_id,
            &config.working_intent_sha256,
            &config.working_early_sha256,
            &"f".repeat(64),
        )
        .unwrap();
        let line = entry.lines().find(|l| l.starts_with("  linux ")).unwrap();
        let working = line.trim_start().splitn(3, ' ').nth(2).unwrap().to_owned();
        let normal = c::ordinary_arguments(&config.candidate_id, &pin.sha256).unwrap();
        for (actor, raw) in [
            (Actor::Commit, working),
            (Actor::Verify, normal.clone()),
            (Actor::Return, normal),
        ] {
            command_line(&raw, actor, &pin, &config).unwrap();
            for wrong in [
                c::LSM_ORDER.replace("selinux,apparmor", "apparmor,selinux"),
                c::LSM_ORDER.replace("selinux,", ""),
                format!("{},smack", c::LSM_ORDER),
            ] {
                assert!(
                    command_line(&raw.replace(c::LSM_ORDER, &wrong), actor, &pin, &config).is_err()
                );
            }
        }
    }
}
