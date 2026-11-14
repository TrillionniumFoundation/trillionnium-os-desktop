//! Stage one unqualified vendor Audio APEX without projecting old system files.
use crate::util::Result;
use serde::de::{self, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer};
use serde_json::{Map, Number, Value, json};
use sha2::{Digest, Sha256};
use std::{
    ffi::{CString, OsStr},
    fmt,
    fs::{self, File, Metadata, OpenOptions, Permissions},
    io::{self, Read, Seek, SeekFrom, Write},
    mem::MaybeUninit,
    os::fd::{AsRawFd, FromRawFd, RawFd},
    os::unix::{
        ffi::OsStrExt,
        fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
    },
    path::{Component, Path},
};

const PACKAGE: &str = "com.android.hardware.audio.droidloom";
const VENDOR_PATH: &str = "vendor/apex/com.android.hardware.audio.droidloom.apex";
const MAX_TERMINAL: u64 = 4 * 1024 * 1024;
const MAX_APEX: u64 = 256 * 1024 * 1024;

fn need(condition: bool, message: &str) -> Result<()> {
    if condition {
        Ok(())
    } else {
        Err(message.into())
    }
}

fn nanos(seconds: i64, fraction: i64) -> Result<i64> {
    seconds
        .checked_mul(1_000_000_000)
        .and_then(|v| v.checked_add(fraction))
        .ok_or_else(|| "file timestamp outside supported range".into())
}

fn file_identity(meta: &Metadata) -> Result<Value> {
    Ok(json!([
        meta.dev(),
        meta.ino(),
        meta.mode(),
        meta.uid(),
        meta.gid(),
        meta.nlink(),
        meta.len(),
        nanos(meta.mtime(), meta.mtime_nsec())?,
        nanos(meta.ctime(), meta.ctime_nsec())?
    ]))
}

fn named_identity(st: &libc::stat) -> Result<Value> {
    Ok(json!([
        st.st_dev,
        st.st_ino,
        st.st_mode,
        st.st_uid,
        st.st_gid,
        st.st_nlink,
        st.st_size,
        nanos(st.st_mtime, st.st_mtime_nsec)?,
        nanos(st.st_ctime, st.st_ctime_nsec)?
    ]))
}

fn c_name(name: &OsStr) -> Result<CString> {
    Ok(CString::new(name.as_bytes())?)
}

fn open_at(parent: RawFd, name: &OsStr, flags: i32, mode: libc::mode_t) -> Result<File> {
    let name = c_name(name)?;
    // SAFETY: the CString is terminated and parent is retained by an owned File.
    let fd = unsafe {
        libc::openat(
            parent,
            name.as_ptr(),
            flags | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            mode,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    // SAFETY: openat returned a new descriptor exclusively owned by this File.
    Ok(unsafe { File::from_raw_fd(fd) })
}

fn stat_at(parent: RawFd, name: &OsStr) -> Result<libc::stat> {
    let name = c_name(name)?;
    let mut value = MaybeUninit::<libc::stat>::uninit();
    // SAFETY: output storage is valid; the owned parent descriptor stays live.
    let rc = unsafe {
        libc::fstatat(
            parent,
            name.as_ptr(),
            value.as_mut_ptr(),
            libc::AT_SYMLINK_NOFOLLOW,
        )
    };
    if rc != 0 {
        return Err(io::Error::last_os_error().into());
    }
    // SAFETY: successful fstatat initialized the stat structure.
    Ok(unsafe { value.assume_init() })
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct DirectoryIdentity(u64, u64, u32, u32, u32);
impl DirectoryIdentity {
    fn from_meta(meta: &Metadata) -> Self {
        Self(meta.dev(), meta.ino(), meta.mode(), meta.uid(), meta.gid())
    }
    fn from_stat(st: &libc::stat) -> Self {
        Self(st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid)
    }
}

struct HeldDirectory {
    file: File,
    parent: Option<usize>,
    name: CString,
    identity: DirectoryIdentity,
}

struct DirectoryChain(Vec<HeldDirectory>);
impl DirectoryChain {
    fn parent(destination: &Path) -> Result<Self> {
        let root = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW)
            .open("/")?;
        let root_meta = root.metadata()?;
        let mut chain = Self(vec![HeldDirectory {
            file: root,
            parent: None,
            name: CString::new("/")?,
            identity: DirectoryIdentity::from_meta(&root_meta),
        }]);
        let parent = destination
            .parent()
            .ok_or("staging destination has no parent")?;
        for component in parent.components() {
            match component {
                Component::RootDir => {}
                Component::Normal(name) => {
                    chain.retain(name, chain.0.len() - 1)?;
                }
                _ => return Err("noncanonical staging parent".into()),
            }
        }
        let meta = chain.0.last().unwrap().file.metadata()?;
        // SAFETY: geteuid has no memory or descriptor preconditions.
        let uid = unsafe { libc::geteuid() };
        need(
            meta.uid() == uid && meta.mode() & 0o022 == 0,
            "staging parent must be caller-owned and not group/other writable",
        )?;
        chain.verify()?;
        Ok(chain)
    }

    fn retain(&mut self, name: &OsStr, parent: usize) -> Result<usize> {
        let file = open_at(self.fd(parent), name, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
        let meta = file.metadata()?;
        need(meta.is_dir(), "not a directory")?;
        self.0.push(HeldDirectory {
            file,
            parent: Some(parent),
            name: c_name(name)?,
            identity: DirectoryIdentity::from_meta(&meta),
        });
        Ok(self.0.len() - 1)
    }

    fn create(&mut self, name: &OsStr, parent: usize) -> Result<usize> {
        let name_c = c_name(name)?;
        // SAFETY: CString and retained parent are valid for the complete call.
        if unsafe { libc::mkdirat(self.fd(parent), name_c.as_ptr(), 0o700) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
        let index = self.retain(name, parent)?;
        let meta = self.0[index].file.metadata()?;
        // SAFETY: geteuid has no memory or descriptor preconditions.
        let uid = unsafe { libc::geteuid() };
        need(
            meta.uid() == uid && meta.mode() & 0o7777 == 0o700,
            "new directory ownership or mode differs",
        )?;
        Ok(index)
    }

    fn fd(&self, index: usize) -> RawFd {
        self.0[index].file.as_raw_fd()
    }

    fn verify(&self) -> Result<()> {
        for held in &self.0 {
            let actual = if let Some(parent) = held.parent {
                DirectoryIdentity::from_stat(&stat_at(
                    self.fd(parent),
                    OsStr::from_bytes(held.name.as_bytes()),
                )?)
            } else {
                DirectoryIdentity::from_meta(&fs::symlink_metadata("/")?)
            };
            need(
                actual == held.identity
                    && DirectoryIdentity::from_meta(&held.file.metadata()?) == held.identity,
                "staging directory identity changed",
            )?;
        }
        Ok(())
    }
}

struct UniqueJson(Value);
impl<'de> Deserialize<'de> for UniqueJson {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> std::result::Result<Self, D::Error> {
        struct UniqueVisitor;
        impl<'de> Visitor<'de> for UniqueVisitor {
            type Value = UniqueJson;
            fn expecting(&self, out: &mut fmt::Formatter) -> fmt::Result {
                out.write_str("JSON without duplicate object keys")
            }
            fn visit_bool<E: de::Error>(self, value: bool) -> std::result::Result<Self::Value, E> {
                Ok(UniqueJson(json!(value)))
            }
            fn visit_i64<E: de::Error>(self, value: i64) -> std::result::Result<Self::Value, E> {
                Ok(UniqueJson(json!(value)))
            }
            fn visit_u64<E: de::Error>(self, value: u64) -> std::result::Result<Self::Value, E> {
                Ok(UniqueJson(json!(value)))
            }
            fn visit_f64<E: de::Error>(self, value: f64) -> std::result::Result<Self::Value, E> {
                Number::from_f64(value)
                    .map(|v| UniqueJson(Value::Number(v)))
                    .ok_or_else(|| E::custom("nonfinite JSON number"))
            }
            fn visit_str<E: de::Error>(self, value: &str) -> std::result::Result<Self::Value, E> {
                Ok(UniqueJson(json!(value)))
            }
            fn visit_string<E: de::Error>(
                self,
                value: String,
            ) -> std::result::Result<Self::Value, E> {
                Ok(UniqueJson(json!(value)))
            }
            fn visit_unit<E: de::Error>(self) -> std::result::Result<Self::Value, E> {
                Ok(UniqueJson(Value::Null))
            }
            fn visit_none<E: de::Error>(self) -> std::result::Result<Self::Value, E> {
                Ok(UniqueJson(Value::Null))
            }
            fn visit_seq<A: SeqAccess<'de>>(
                self,
                mut access: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut array = Vec::new();
                while let Some(UniqueJson(value)) = access.next_element()? {
                    array.push(value);
                }
                Ok(UniqueJson(Value::Array(array)))
            }
            fn visit_map<A: MapAccess<'de>>(
                self,
                mut access: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut object = Map::new();
                while let Some(key) = access.next_key::<String>()? {
                    if object.contains_key(&key) {
                        return Err(de::Error::custom(format!("duplicate JSON key: {key}")));
                    }
                    let UniqueJson(value) = access.next_value()?;
                    object.insert(key, value);
                }
                Ok(UniqueJson(Value::Object(object)))
            }
        }
        deserializer.deserialize_any(UniqueVisitor)
    }
}

fn sha_valid(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

fn read_terminal(path: &Path, expected: &str) -> Result<(Value, Value)> {
    need(sha_valid(expected), "expected terminal digest required")?;
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)?;
    let before = file.metadata()?;
    need(
        before.is_file() && before.nlink() == 1 && before.len() > 0 && before.len() <= MAX_TERMINAL,
        "invalid or oversized terminal file",
    )?;
    let identity = file_identity(&before)?;
    let mut raw = Vec::with_capacity(before.len() as usize);
    Read::by_ref(&mut file)
        .take(before.len() + 1)
        .read_to_end(&mut raw)?;
    need(
        raw.len() as u64 == before.len()
            && file_identity(&file.metadata()?)? == identity
            && file_identity(&fs::symlink_metadata(path)?)? == identity,
        "terminal changed during read",
    )?;
    let hash = hex::encode(Sha256::digest(&raw));
    need(hash == expected, "terminal SHA256 mismatch")?;
    let UniqueJson(terminal) = serde_json::from_slice(&raw)?;
    need(
        terminal.is_object()
            && terminal["schema"] == "pocket4-audio-desktop-normal-full-build-v1"
            && terminal["state"] == "BUILT_PENDING_PAYLOAD_AND_COMPILED_QUALIFICATION",
        "only the successful normal full-build terminal is accepted",
    )?;
    for key in [
        "build_success",
        "owned_retirement_complete",
        "input_after_qualified",
        "source_projection_restored",
        "resource_gate_passed",
        "owned_work_budget_passed",
    ] {
        need(
            terminal[key].as_bool() == Some(true),
            &format!("full terminal is missing exact true: {key}"),
        )?;
    }
    need(
        terminal["errors"] == json!([])
            && terminal["signals"] == json!([])
            && (terminal.get("pending_signals_at_commit").is_none()
                || terminal["pending_signals_at_commit"] == json!([])),
        "full terminal has errors or pending signals",
    )?;
    need(
        terminal["source_project_count"].as_u64() == Some(430),
        "unexpected source project closure",
    )?;
    let normal = &terminal["normal_build"];
    need(
        normal.is_object()
            && normal["name"] == "normal-full-audio-apex"
            && normal["owned_retirement_complete"].as_bool() == Some(true)
            && normal["errors"] == json!([])
            && normal["lifecycle"]["returncode"].as_i64() == Some(0),
        "normal full command did not succeed",
    )?;
    let argv = terminal["argv"]
        .as_array()
        .ok_or("unexpected full build command")?;
    need(
        normal["argv"] == terminal["argv"],
        "normal command and terminal argv differ",
    )?;
    need(
        argv.len() == 7
            && argv[1] == "--source"
            && argv[3] == "-j6"
            && argv[4] == "audio-apex-build"
            && argv[5] == "--work",
        "unexpected full build command",
    )?;
    need(
        Path::new(argv[0].as_str().ok_or("missing update executable")?).file_name()
            == Some(OsStr::new("droidloom-update")),
        "unexpected full build executable",
    )?;
    let work = Path::new(argv[6].as_str().ok_or("missing build workspace")?);
    let artifact = &terminal["whole_apex"];
    let artifact_path = Path::new(
        artifact["path"]
            .as_str()
            .ok_or("whole APEX reference absent")?,
    );
    need(
        work.is_absolute()
            && !work
                .components()
                .any(|v| matches!(v, Component::ParentDir | Component::CurDir))
            && artifact_path
                == work
                    .join("android-audio-closure-out/target/product/droidloom_x86_64")
                    .join(VENDOR_PATH),
        "whole APEX is not the selected normal build output",
    )?;
    need(
        artifact["bytes"]
            .as_u64()
            .is_some_and(|n| n > 0 && n <= MAX_APEX)
            && artifact["sha256"].as_str().is_some_and(sha_valid)
            && artifact["identity"]
                .as_array()
                .is_some_and(|v| v.len() == 9),
        "invalid whole APEX frozen reference",
    )?;
    for name in [
        "configuration",
        "source_qualification",
        "materialized_manifest_before",
        "materialized_manifest_after",
    ] {
        let reference = &terminal[name];
        let path = reference["path"]
            .as_str()
            .ok_or("full input reference is absent")?;
        need(
            Path::new(path).is_absolute()
                && !Path::new(path)
                    .components()
                    .any(|v| matches!(v, Component::ParentDir | Component::CurDir))
                && reference["bytes"].as_u64().is_some_and(|n| n > 0)
                && reference["sha256"].as_str().is_some_and(sha_valid),
            "invalid full input frozen reference",
        )?;
    }
    let terminal_ref =
        json!({"path": path, "bytes": raw.len(), "sha256": hash, "identity": identity});
    Ok((terminal, terminal_ref))
}

/// Copy one normal-build artifact into a new, unqualified vendor-only candidate.
pub fn stage(terminal: &Path, expected_sha256: &str, destination: &Path) -> Result<Value> {
    stage_inner(terminal, expected_sha256, destination, |_| Ok(()))
}

fn stage_inner(
    terminal_path: &Path,
    expected_sha256: &str,
    destination: &Path,
    before_publish: impl FnOnce(&Path) -> Result<()>,
) -> Result<Value> {
    need(
        destination.is_absolute()
            && !destination
                .components()
                .any(|v| matches!(v, Component::ParentDir | Component::CurDir)),
        "absolute canonical new staging path required",
    )?;
    match fs::symlink_metadata(destination) {
        Ok(_) => return Err("staging destination already exists".into()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(error) => return Err(error.into()),
    }
    let (terminal, terminal_ref) = read_terminal(terminal_path, expected_sha256)?;
    let artifact = &terminal["whole_apex"];
    let source = Path::new(artifact["path"].as_str().unwrap());
    let bytes = artifact["bytes"].as_u64().unwrap();
    let expected_hash = artifact["sha256"].as_str().unwrap();
    let mut chain = DirectoryChain::parent(destination)?;
    let parent = chain.0.len() - 1;
    let mut input = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(source)?;
    let before = input.metadata()?;
    need(
        before.is_file()
            && before.nlink() == 1
            && before.len() == bytes
            && file_identity(&before)? == artifact["identity"],
        "source APEX identity changed",
    )?;
    let stage_dir = chain.create(
        destination.file_name().ok_or("staging name missing")?,
        parent,
    )?;
    let mut artifact_dir = stage_dir;
    for name in ["payload", "vendor", "apex"] {
        artifact_dir = chain.create(OsStr::new(name), artifact_dir)?;
    }
    let target_name = format!("{PACKAGE}.apex");
    let mut output = open_at(
        chain.fd(artifact_dir),
        OsStr::new(&target_name),
        libc::O_RDWR | libc::O_CREAT | libc::O_EXCL,
        0o600,
    )?;
    let mut digest = Sha256::new();
    let mut total = 0u64;
    let mut buffer = vec![0u8; 1024 * 1024];
    loop {
        let limit = buffer.len().min((bytes - total + 1) as usize);
        let read = input.read(&mut buffer[..limit])?;
        if read == 0 {
            break;
        }
        total += read as u64;
        need(total <= bytes, "source APEX grew during copy")?;
        digest.update(&buffer[..read]);
        output.write_all(&buffer[..read])?;
    }
    output.sync_all()?;
    let digest = hex::encode(digest.finalize());
    need(
        total == bytes && digest == expected_hash,
        "source APEX content mismatch",
    )?;
    need(
        file_identity(&input.metadata()?)? == artifact["identity"]
            && file_identity(&fs::symlink_metadata(source)?)? == artifact["identity"],
        "source APEX changed during copy",
    )?;
    output.set_permissions(Permissions::from_mode(0o400))?;
    output.sync_all()?;
    let target_identity = file_identity(&output.metadata()?)?;
    output.seek(SeekFrom::Start(0))?;
    let mut readback = Sha256::new();
    let mut readback_bytes = 0u64;
    loop {
        let read = output.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        readback_bytes += read as u64;
        need(readback_bytes <= bytes, "staged APEX grew during readback")?;
        readback.update(&buffer[..read]);
    }
    need(
        readback_bytes == bytes && hex::encode(readback.finalize()) == digest,
        "staged APEX byte readback differs",
    )?;
    let apex = crate::audio_vendor_zip::inspect(&mut output)?;
    before_publish(destination)?;
    chain.verify()?;
    need(
        file_identity(&output.metadata()?)? == target_identity
            && named_identity(&stat_at(chain.fd(artifact_dir), OsStr::new(&target_name))?)?
                == target_identity,
        "staged APEX pathname or identity changed",
    )?;
    let report = json!({
        "schema": "pocket4-qpr1-audio-vendor-candidate-v1", "state": "UNQUALIFIED_VENDOR_AUDIO_CANDIDATE",
        "selected_official_base": {"build_id": "CP3A.260905.010", "build_number": "16176746",
            "system_img_bytes": 2294853632u64,
            "system_img_sha256": "dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4"},
        "base_image_reverified_by_this_tool": false, "normal_full_terminal": terminal_ref,
        "normal_full_H_terminal_reverified_by_this_tool": false, "source_apex": artifact,
        "recorded_normal_full_inputs": {
            "argv": terminal["argv"], "configuration": terminal["configuration"],
            "source_qualification": terminal["source_qualification"],
            "materialized_manifest_before": terminal["materialized_manifest_before"],
            "materialized_manifest_after": terminal["materialized_manifest_after"],
            "referenced_input_files_reverified_by_this_tool": false,
        },
        "files": [{"path": VENDOR_PATH, "bytes": total, "sha256": digest, "staging_mode": "0400",
            "intended_install_mode": "0644", "intended_install_uid": 0, "intended_install_gid": 0}],
        "apex": apex, "system_overrides": [], "system_ext_overrides": [], "product_overrides": [],
        "images_written": 0, "deployments": 0, "cell_actions": 0,
        "complete_apex_qualified": false, "compiled_elf_qualified": false, "apex_signatures_qualified": false,
        "vintf_qualified": false, "runtime_qualified": false, "production_ready": false,
    });
    let mut manifest = open_at(
        chain.fd(stage_dir),
        OsStr::new("CANDIDATE.json"),
        libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL,
        0o600,
    )?;
    serde_json::to_writer_pretty(&mut manifest, &report)?;
    manifest.write_all(b"\n")?;
    manifest.sync_all()?;
    manifest.set_permissions(Permissions::from_mode(0o400))?;
    manifest.sync_all()?;
    let manifest_identity = file_identity(&manifest.metadata()?)?;
    chain.verify()?;
    need(
        named_identity(&stat_at(chain.fd(stage_dir), OsStr::new("CANDIDATE.json"))?)?
            == manifest_identity,
        "candidate manifest pathname replaced",
    )?;
    // Persist each newly created directory entry before its containing entry.
    for held in chain.0[stage_dir..].iter().rev() {
        held.file.sync_all()?;
    }
    chain.0[parent].file.sync_all()?;
    chain.verify()?;
    need(
        file_identity(&output.metadata()?)? == target_identity
            && named_identity(&stat_at(chain.fd(artifact_dir), OsStr::new(&target_name))?)?
                == target_identity
            && file_identity(&manifest.metadata()?)? == manifest_identity
            && named_identity(&stat_at(chain.fd(stage_dir), OsStr::new("CANDIDATE.json"))?)?
                == manifest_identity,
        "staged files changed during durable publication",
    )?;
    Ok(report)
}

#[cfg(test)]
mod tests;
