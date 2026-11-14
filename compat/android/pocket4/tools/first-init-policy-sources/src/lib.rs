//! Readonly actual original CP3A policy sources. This cannot load policy or issue runtime authority.
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::fs::{self, File, OpenOptions};
use std::io::Write;
#[cfg(target_os = "linux")]
use std::os::fd::AsRawFd;
use std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt};
use std::path::{Component, Path, PathBuf};
pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
fn fail<T>(s: impl Into<String>) -> Result<T> {
    Err(s.into().into())
}
fn need(v: bool, s: &str) -> Result<()> {
    if v { Ok(()) } else { fail(s) }
}
const SYSTEM_SHA: &str = "dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4";
const DEBUGFS_SHA: &str = "864e1d7b445e7b5bfc831da78330dbcafc590fa82b89ea9de60b7527f989954f";
#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize)]
struct Identity {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    bytes: u64,
    mtime: i64,
    mtime_ns: i64,
    ctime: i64,
    ctime_ns: i64,
}
impl Identity {
    fn of(file: &File) -> Result<Self> {
        let s = file.metadata()?;
        Ok(Self {
            dev: s.dev(),
            ino: s.ino(),
            mode: s.mode(),
            uid: s.uid(),
            gid: s.gid(),
            links: s.nlink(),
            bytes: s.len(),
            mtime: s.mtime(),
            mtime_ns: s.mtime_nsec(),
            ctime: s.ctime(),
            ctime_ns: s.ctime_nsec(),
        })
    }
}
fn open_fixed(path: &Path) -> Result<File> {
    use std::os::fd::{AsRawFd, FromRawFd};
    if !path.is_absolute()
        || path.components().any(|part| {
            matches!(
                part,
                Component::CurDir | Component::ParentDir | Component::Prefix(_)
            )
        })
    {
        return fail("absolute fixed source path without aliases required");
    }
    let mut held = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open("/")?;
    let parts = path.components().collect::<Vec<_>>();
    for (index, part) in parts.iter().enumerate().skip(1) {
        let Component::Normal(name) = part else {
            return fail("fixed source component");
        };
        let name = std::ffi::CString::new(name.as_encoded_bytes())?;
        let flags = libc::O_RDONLY
            | libc::O_NOFOLLOW
            | libc::O_CLOEXEC
            | libc::O_NONBLOCK
            | if index + 1 < parts.len() {
                libc::O_DIRECTORY
            } else {
                0
            };
        let fd = unsafe { libc::openat(held.as_raw_fd(), name.as_ptr(), flags) };
        if fd < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        held = unsafe { File::from_raw_fd(fd) };
    }
    Ok(held)
}
struct HeldOutput {
    file: File,
    path: PathBuf,
    identity: Identity,
    sha256: String,
}
impl HeldOutput {
    fn capture(root: &Path, relative: &str, maximum: u64) -> Result<Self> {
        if !root.is_absolute()
            || relative.is_empty()
            || Path::new(relative)
                .components()
                .any(|part| !matches!(part, Component::Normal(_)))
        {
            return fail("fixed absolute artifact root and confined role required");
        }
        let path = root.join(relative);
        let directory = open_fixed(&path)?;
        let identity = Identity::of(&directory)?;
        if identity.mode & libc::S_IFMT as u32 != libc::S_IFREG as u32
            || identity.links != 1
            || identity.bytes == 0
            || identity.bytes > maximum
            || identity.mode & 0o6022 != 0
        {
            return fail(format!(
                "bounded single-link normal producer artifact required: {relative}"
            ));
        }
        let mut result = Self {
            file: directory,
            path,
            identity,
            sha256: String::new(),
        };
        result.sha256 = result.hash()?;
        result.revalidate()?;
        Ok(result)
    }
    fn hash(&self) -> Result<String> {
        let mut hash = Sha256::new();
        let mut offset = 0;
        let mut block = [0u8; 65536];
        while offset < self.identity.bytes {
            let n = self.file.read_at(&mut block, offset)?;
            if n == 0 {
                return fail("held output short read");
            }
            hash.update(&block[..n]);
            offset += n as u64;
        }
        if offset != self.identity.bytes {
            return fail("held output grew");
        }
        Ok(format!("{:x}", hash.finalize()))
    }
    fn revalidate(&self) -> Result<()> {
        if Identity::of(&self.file)? != self.identity || self.hash()? != self.sha256 {
            return fail("actual output descriptor changed");
        }
        let named = open_fixed(&self.path)?;
        if Identity::of(&named)? != self.identity {
            return fail("actual output pathname rebound");
        }
        Ok(())
    }
    fn bytes(&self, bound: u64) -> Result<Vec<u8>> {
        if self.identity.bytes > bound {
            return fail("artifact text/ELF bound");
        }
        let mut out = vec![0; self.identity.bytes as usize];
        self.file.read_exact_at(&mut out, 0)?;
        self.revalidate()?;
        Ok(out)
    }
    fn reference(&self) -> Value {
        json!({"path":self.path,"bytes":self.identity.bytes,"sha256":self.sha256,"identity":self.identity})
    }
}
fn create(path: &Path, value: &Value) -> Result<()> {
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .mode(0o600)
        .open(path)?;
    file.write_all(&serde_json::to_vec_pretty(value)?)?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    Ok(())
}
/// Structural CIL recognition only. Actual secilc/version compatibility and live
/// policy load remain separate required producers; balanced text grants nothing.
pub fn cil_shape(bytes: &[u8]) -> Result<Value> {
    need(
        !bytes.is_empty() && bytes.len() <= 64 * 1024 * 1024 && !bytes.contains(&0),
        "bounded nonempty CIL text required",
    )?;
    let text = std::str::from_utf8(bytes)?;
    let mut depth = 0u32;
    let mut maximum = 0;
    let mut forms = 0u64;
    let mut quoted = false;
    let mut escaped = false;
    let mut comment = false;
    for c in text.chars() {
        if comment {
            if c == '\n' {
                comment = false;
            }
            continue;
        }
        if quoted {
            if escaped {
                escaped = false;
            } else if c == '\\' {
                escaped = true;
            } else if c == '"' {
                quoted = false;
            }
            continue;
        }
        match c {
            ';' => comment = true,
            '"' => quoted = true,
            '(' => {
                if depth == 0 {
                    forms += 1;
                }
                depth = depth.checked_add(1).ok_or("CIL depth overflow")?;
                maximum = maximum.max(depth);
                need(maximum <= 2048, "bounded CIL nesting")?;
            }
            ')' => {
                need(depth > 0, "CIL unmatched closing parenthesis")?;
                depth -= 1;
            }
            v => need(
                !v.is_control() || matches!(v, '\n' | '\r' | '\t'),
                "CIL control character",
            )?,
        }
    }
    need(
        !quoted && !escaped && depth == 0 && forms > 0,
        "complete CIL forms without unterminated string or form required",
    )?;
    Ok(
        json!({"source_format":"CIL_TEXT_STRUCTURAL_ONLY","bytes":bytes.len(),"top_level_forms":forms,"maximum_depth":maximum,"secilc_compiled":false,"MAC_loaded_or_enforcing":false,"runtime_authority":false}),
    )
}
const FILES: [(&str, &str); 17] = [
    ("plat_sepolicy.cil", "/system/etc/selinux/plat_sepolicy.cil"),
    (
        "plat_sepolicy_genfs_202604.cil",
        "/system/etc/selinux/plat_sepolicy_genfs_202604.cil",
    ),
    (
        "plat_file_contexts",
        "/system/etc/selinux/plat_file_contexts",
    ),
    (
        "plat_property_contexts",
        "/system/etc/selinux/plat_property_contexts",
    ),
    (
        "plat_service_contexts",
        "/system/etc/selinux/plat_service_contexts",
    ),
    (
        "plat_hwservice_contexts",
        "/system/etc/selinux/plat_hwservice_contexts",
    ),
    (
        "plat_sepolicy_and_mapping.sha256",
        "/system/etc/selinux/plat_sepolicy_and_mapping.sha256",
    ),
    (
        "system_ext_sepolicy.cil",
        "/system/system_ext/etc/selinux/system_ext_sepolicy.cil",
    ),
    (
        "product_sepolicy.cil",
        "/system/product/etc/selinux/product_sepolicy.cil",
    ),
    ("original_system_init.rc", "/system/etc/init/hw/init.rc"),
    (
        "original_init.gsi.rc",
        "/system/system_ext/etc/init/init.gsi.rc",
    ),
    (
        "original_init.vndk-nodef.rc",
        "/system/system_ext/etc/gsi/init.vndk-nodef.rc",
    ),
    (
        "original_init.zygote64_32.rc",
        "/system/etc/init/hw/init.zygote64_32.rc",
    ),
    (
        "original_task_profiles.json",
        "/system/etc/task_profiles.json",
    ),
    ("original_cgroups.json", "/system/etc/cgroups.json"),
    ("original_system_build.prop", "/system/build.prop"),
    (
        "original_plat_seapp_contexts",
        "/system/etc/selinux/plat_seapp_contexts",
    ),
];
const DIRECTORIES: [(&str, &str); 3] = [
    ("plat_mapping_directory", "/system/etc/selinux/mapping"),
    (
        "system_ext_mapping_directory",
        "/system/system_ext/etc/selinux/mapping",
    ),
    (
        "product_mapping_directory",
        "/system/product/etc/selinux/mapping",
    ),
];
// These are the original compatibility mappings for the 202604 vendor policy
// version. The system_ext and product files in this exact image each contain
// one newline. Preserve those real files without treating empty policy input as
// a policy, or manufacturing a replacement for a missing image member.
const MAPPINGS: [(&str, &str, u64); 3] = [
    (
        "plat_mapping_202604.cil",
        "/system/etc/selinux/mapping/202604.cil",
        234191,
    ),
    (
        "system_ext_mapping_202604.cil",
        "/system/system_ext/etc/selinux/mapping/202604.cil",
        1,
    ),
    (
        "product_mapping_202604.cil",
        "/system/product/etc/selinux/mapping/202604.cil",
        1,
    ),
];
fn original_mapping_shape(name: &str, bytes: &[u8]) -> Result<Value> {
    let expected = MAPPINGS
        .iter()
        .find(|(role, _, _)| *role == name)
        .ok_or("fixed original mapping role required")?;
    need(
        bytes.len() as u64 == expected.2,
        "original mapping byte count differs",
    )?;
    if expected.2 == 1 {
        need(bytes == b"\n", "original blank mapping must be one newline")?;
        Ok(json!({"source_format":"ORIGINAL_BLANK_COMPATIBILITY_MAPPING","mapping_version":"202604","bytes":1,"top_level_forms":0,"secilc_compiled":false,"MAC_loaded_or_enforcing":false,"runtime_authority":false}))
    } else {
        cil_shape(bytes)
    }
}
#[cfg(target_os = "linux")]
fn ordinary_dump(
    tool: &HeldOutput,
    image: &HeldOutput,
    operation: &str,
    path: &str,
    output: &Path,
    name: &str,
) -> Result<()> {
    use std::os::fd::{FromRawFd, OwnedFd};
    use std::os::unix::process::CommandExt;
    use std::process::{Command, Stdio};
    need(
        unsafe { libc::getuid() } == 1000 && unsafe { libc::geteuid() } == 1000,
        "policy source extraction only as ordinary UID1000",
    )?;
    need(
        matches!(operation, "cat" | "ls -p")
            && path.starts_with("/system/")
            && !path.bytes().any(|b| b.is_ascii_whitespace() || b == b'\0'),
        "finite fixed original system policy operation",
    )?;
    need(
        Identity::of(&tool.file)? == tool.identity && Identity::of(&image.file)? == image.identity,
        "held tool/image identity changed",
    )?;
    let stdout = OpenOptions::new()
        .write(true)
        .create_new(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .mode(0o600)
        .open(output.join(name))?;
    let stderr = OpenOptions::new()
        .write(true)
        .create_new(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .mode(0o600)
        .open(output.join(format!("{name}.stderr")))?;
    let fd = image.file.as_raw_fd();
    let mut command = Command::new(format!("/proc/self/fd/{}", tool.file.as_raw_fd()));
    command
        .args([
            "-R",
            &format!("{operation} {path}"),
            &format!("/proc/self/fd/{fd}"),
        ])
        .env_clear()
        .env("LC_ALL", "C")
        .stdout(Stdio::from(stdout.try_clone()?))
        .stderr(Stdio::from(stderr.try_clone()?));
    unsafe {
        command.pre_exec(move || {
            if libc::setsid() < 0 {
                return Err(std::io::Error::last_os_error());
            }
            let flags = libc::fcntl(fd, libc::F_GETFD);
            if flags < 0 || libc::fcntl(fd, libc::F_SETFD, flags & !libc::FD_CLOEXEC) < 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
    create(
        &output.join(format!("{name}.command.json")),
        &json!({"state":"BEFORE_ORDINARY_FIXED_PUBLIC_POLICY_READ","program":tool.reference(),"image":image.reference(),"operation":operation,"member":path,"outer_owned_tree_timeout_resources_required":true,"MAC_policy_loads":0}),
    )?;
    let mut child = command.spawn()?;
    let pid = child.id();
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) } as i32;
    if raw < 0 {
        let e = std::io::Error::last_os_error();
        let _ = child.kill();
        let _ = child.wait();
        return Err(e.into());
    }
    let pidfd = unsafe { OwnedFd::from_raw_fd(raw) };
    // The fixed readonly reader is still owned on wait/IO failure. Signal only
    // this original PIDFD; the outer accepted owner also retires adopted tasks.
    let status = match child.wait() {
        Ok(status) => status,
        Err(error) => {
            unsafe {
                libc::syscall(
                    libc::SYS_pidfd_send_signal,
                    pidfd.as_raw_fd(),
                    libc::SIGKILL,
                    std::ptr::null::<libc::siginfo_t>(),
                    0,
                );
            }
            let _ = child.wait();
            return Err(error.into());
        }
    };
    let mut p = libc::pollfd {
        fd: pidfd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    let signalled = unsafe { libc::poll(&mut p, 1, 0) } == 1 && p.revents & libc::POLLIN != 0;
    let mut code = 0;
    let reaped = unsafe { libc::waitpid(pid as i32, &mut code, libc::WNOHANG) } < 0
        && std::io::Error::last_os_error().raw_os_error() == Some(libc::ECHILD);
    create(
        &output.join(format!("{name}.command-complete.json")),
        &json!({"state":"ORDINARY_POLICY_READER_RETIRED","pid":pid,"exit_code":status.code(),"same_PIDFD_exit":signalled,"direct_ECHILD":reaped,"outer_adopted_tree_retirement_still_required":true,"image":image.reference(),"member":path,"MAC_policy_loads":0}),
    )?;
    need(
        status.success() && signalled && reaped,
        "actual readonly fixed policy extractor exit/retirement failed",
    )?;
    stdout.sync_all()?;
    stderr.sync_all()?;
    need(
        stderr.metadata()?.len() <= 65536 && stdout.metadata()?.len() <= 64 * 1024 * 1024,
        "bounded policy reader output",
    )?;
    need(
        Identity::of(&tool.file)? == tool.identity && Identity::of(&image.file)? == image.identity,
        "held input changed while reading policy",
    )
}
#[cfg(not(target_os = "linux"))]
fn ordinary_dump(
    _: &HeldOutput,
    _: &HeldOutput,
    _: &str,
    _: &str,
    _: &Path,
    _: &str,
) -> Result<()> {
    fail("actual fixed public image policy extraction requires ordinary Linux")
}
pub fn inspect_original_platform_sources(input: &Path, output: &Path) -> Result<Value> {
    let image = HeldOutput::capture(input, "system.img", 2294853632)?;
    need(
        image.identity.bytes == 2294853632 && image.sha256 == SYSTEM_SHA,
        "exact public original CP3A system image required",
    )?;
    let tool = HeldOutput::capture(input, "debugfs", 231368)?;
    need(
        tool.identity.bytes == 231368
            && tool.sha256 == DEBUGFS_SHA
            && tool.identity.mode & 0o111 != 0,
        "exact public original readonly debugfs executable required",
    )?;
    need(
        output.is_absolute() && !output.exists(),
        "new policy-source output namespace only",
    )?;
    fs::create_dir(output)?;
    let mut files = Vec::new();
    for (name, path) in FILES
        .into_iter()
        .chain(DIRECTORIES)
        .chain(MAPPINGS.map(|(name, path, _)| (name, path)))
    {
        let directory = name.ends_with("_directory");
        ordinary_dump(
            &tool,
            &image,
            if directory { "ls -p" } else { "cat" },
            path,
            output,
            name,
        )?;
        let named = output.join(name);
        // Empty/missing members are explicit source gaps. Nonempty data is
        // parsed only from the same held output descriptor used by its receipt.
        let bytes = if fs::symlink_metadata(&named)?.len() == 0 {
            Vec::new()
        } else {
            HeldOutput::capture(output, name, 64 * 1024 * 1024)?.bytes(64 * 1024 * 1024)?
        };
        let errors = fs::read(output.join(format!("{name}.stderr")))?;
        if bytes.is_empty() {
            files.push(json!({"member":path,"state":"EXPLICIT_ACTUAL_IMAGE_MEMBER_MISSING_OR_EMPTY","stderr_utf8":String::from_utf8_lossy(&errors),"qualified":false}));
            continue;
        }
        let held = HeldOutput::capture(output, name, 64 * 1024 * 1024)?;
        let shape = if MAPPINGS.iter().any(|(role, _, _)| *role == name) {
            original_mapping_shape(name, &bytes)?
        } else if name.ends_with(".cil") {
            cil_shape(&bytes)?
        } else {
            need(
                !bytes.contains(&0) && std::str::from_utf8(&bytes).is_ok(),
                "actual policy context/mapping directory text required",
            )?;
            json!({"source_format":if directory{"DEBUGFS_DIRECTORY_LISTING"}else{"POLICY_METADATA_TEXT"},"bytes":bytes.len(),"semantic_or_runtime_qualification":false})
        };
        files.push(json!({"member":path,"actual_output":held.reference(),"shape":shape,"stderr_utf8":String::from_utf8_lossy(&errors)}));
    }
    image.revalidate()?;
    tool.revalidate()?;
    let report = json!({"schema":"actual_original_CP3A_platform_policy_sources_v3","state":"READONLY_ORIGINAL_PLATFORM_POLICY_SOURCES_ONLY","image":image.reference(),"extractor":tool.reference(),"files":files,"original_mapping_version":"202604","original_mapping_count":3,"original_genfs_labels_version":"202604","original_genfs_policy_member":"/system/etc/selinux/plat_sepolicy_genfs_202604.cil","selected_final_vendor_genfs_labels_version_verified":false,"selected_final_vendor_policy_version_verified":false,"required_real_normal_vendor_policy_inputs":["vendor/etc/selinux/vendor_sepolicy.cil","vendor/etc/selinux/plat_pub_versioned.cil","vendor/etc/selinux/plat_sepolicy_vers.txt matching the collected original mapping version","vendor/etc/selinux/precompiled_sepolicy and matching platform hashes if used","actual selected normal vendor VINTF and product artifact receipt"],"CP3A_GSI_contains_qualified_final_vendor":false,"secilc_policy_compile_passed":false,"guest_SELinux_active_loaded_enforcing":false,"MAC_policy_loads":0,"Android_starts":0,"ExecutionAdmission_issued":false,"production_ready":false});
    create(&output.join("POLICY-SOURCE-RECEIPT.json"), &report)?;
    Ok(report)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cil_comments_and_quoted_regex_preserve_structure() {
        let v = cil_shape(
            b"; a comment with (\n(type init)\n(filecon \"a(.*)\\\"z\" file (u r t ((s0)(s0))))\n",
        )
        .unwrap();
        assert_eq!(v["runtime_authority"], false);
        assert_eq!(v["top_level_forms"], 2);
    }
    #[test]
    fn malformed_or_binary_policy_cannot_be_reported_as_cil() {
        for value in [
            &b"(type x"[..],
            &b")"[..],
            &b"(a \"unterminated)"[..],
            &b"\x8c\xff\x7c\xf9\0"[..],
            &b";comment only"[..],
        ] {
            assert!(cil_shape(value).is_err());
        }
    }
    #[test]
    fn original_blank_mapping_cannot_substitute_for_policy_or_missing_input() {
        for role in [
            "system_ext_mapping_202604.cil",
            "product_mapping_202604.cil",
        ] {
            let shape = original_mapping_shape(role, b"\n").unwrap();
            assert_eq!(shape["top_level_forms"], 0);
            assert_eq!(shape["runtime_authority"], false);
            for invalid in [&b""[..], &b" "[..], &b"\r\n"[..], &b"\0"[..]] {
                assert!(original_mapping_shape(role, invalid).is_err());
            }
        }
        assert!(original_mapping_shape("plat_mapping_202604.cil", b"\n").is_err());
        assert!(original_mapping_shape("plat_sepolicy.cil", b"\n").is_err());
        assert!(cil_shape(b"\n").is_err());
    }
}
/// Produces a private-guest boot requirement from this actual kernel's complete
/// public build configuration. This is source data, never live MAC evidence.
pub fn selected_private_guest_selinux_requirements(root: &Path) -> Result<Value> {
    let config = HeldOutput::capture(root, "kernel-public.config", 308714)?;
    need(
        config.identity.bytes == 308714
            && config.sha256 == "85658dc84bd493671a4c533b2bc33e6a66d7032616c13ed57ebd28eade863e58",
        "exact actual ctx3 public build config required",
    )?;
    let bytes = config.bytes(308714)?;
    let text = std::str::from_utf8(&bytes)?;
    let mut values = std::collections::BTreeMap::new();
    for line in text.lines() {
        if let Some((key, value)) = line.split_once('=') {
            if key.starts_with("CONFIG_") {
                need(
                    values.insert(key, value).is_none(),
                    "duplicate actual kernel config key",
                )?;
            }
        }
    }
    need(
        values.get("CONFIG_LOCALVERSION") == Some(&"\"-p4ctx3\"")
            && [
                "CONFIG_SECURITY_SELINUX",
                "CONFIG_SECURITYFS",
                "CONFIG_AUDIT",
                "CONFIG_CGROUPS",
            ]
            .iter()
            .all(|key| values.get(key) == Some(&"y")),
        "actual selected ctx3 config capabilities required",
    )?;
    config.revalidate()?;
    Ok(
        json!({"schema":"source_only_private_guest_selinux_boot_requirements_v1","actual_config":config.reference(),"actual_default_CONFIG_LSM":values["CONFIG_LSM"],"explicit_new_private_guest_kernel_parameters":["lsm=landlock,lockdown,yama,integrity,selinux,bpf","selinux=1","enforcing=1"],"same_selected_kernel_bzImage_required":{"bytes":17138176,"sha256":"a91670a793380d629aaf82edffcdff11799e52cf26ff43db70030afe04d64d12"},"required_live_successor_witnesses":["same new VM bootID/PID1/owned original init PIDFD","actual securityfs lsm list includes selinux and expected major","real selinuxfs FD + policy load generation before/after","normal compiled policy artifact from original CP3A platform plus actual compatible final vendor inputs","actual enforcing=1 and expected actual parent/child MAC labels","real cgroup2 hierarchy/controller/delegation/task-profile application, since NNP component cgroup text was empty"],"Host_kernel_or_LSM_changes":false,"private_guest_boot_parameters_executed":false,"policy_loaded":false,"runtime_qualified":false,"ExecutionAdmission_issued":false,"production_ready":false}),
    )
}
