//! The three fixed native-v2 input roles inside the authenticated runtime image.
//! These witnesses describe input bytes, not C++ ABI or successful execution.
use super::*;
#[path = "production_native_build_evidence.rs"]
mod build_evidence;

const MAX_LIBRARY: u64 = 4 * 1024 * 1024;
const MAX_POLICY: u64 = 1024 * 1024;
#[derive(Clone, Copy, Debug)]
enum NativeLabel {
    Library,
    Policy,
}
impl NativeLabel {
    fn check(self, file: &File) -> Result<()> {
        match self {
            Self::Library => require_exact_xattr(
                file,
                c"security.selinux",
                b"u:object_r:system_lib_file:s0\0",
            ),
            Self::Policy => {
                require_exact_xattr(file, c"security.selinux", b"u:object_r:system_file:s0\0")
            }
        }
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct NativeDeclaration {
    scope: String,
    source_system_sha256: String,
    original_elf_sha256: String,
    original_elf_bytes: u64,
    original_build_id: String,
    derived_build_id: String,
    library: ImageDeclaration,
    original_setup_elf_sha256: String,
    original_setup_elf_bytes: u64,
    original_setup_build_id: String,
    derived_setup_build_id: String,
    setup_library: ImageDeclaration,
    policy: ImageDeclaration,
    source_provenance_sha256: String,
    effective_inputs_sha256: String,
    abi_surface_sha256: String,
    source_basis: String,
    native_execution_qualified: bool,
    build_evidence: build_evidence::Receipt,
    unsupported_effective_profiles: Vec<String>,
    unsupported_rc_actions: Vec<String>,
}
impl NativeDeclaration {
    pub(super) fn validate(&self, runtime: &RuntimeDeclaration) -> Result<()> {
        require(
            self.scope == "droidloom-native-cgroup-v2-inputs-v2"
                && self.source_system_sha256 == runtime.source_system.sha256
                && self.library.file == "lib64/libprocessgroup.so"
                && (64..=MAX_LIBRARY).contains(&self.library.bytes)
                && self.setup_library.file == "lib64/libprocessgroup_setup.so"
                && (64..=MAX_LIBRARY).contains(&self.setup_library.bytes)
                && self.policy.file == "rc/cgroup-v2-policy.json"
                && (1..=MAX_POLICY).contains(&self.policy.bytes)
                && (64..=MAX_LIBRARY).contains(&self.original_elf_bytes)
                && (64..=MAX_LIBRARY).contains(&self.original_setup_elf_bytes)
                && !self.native_execution_qualified,
            "fixed native input roles cannot assert execution qualification",
        )?;
        for hash in [
            &self.source_system_sha256,
            &self.original_elf_sha256,
            &self.library.sha256,
            &self.original_setup_elf_sha256,
            &self.setup_library.sha256,
            &self.policy.sha256,
            &self.source_provenance_sha256,
            &self.effective_inputs_sha256,
            &self.abi_surface_sha256,
        ] {
            require(is_digest(hash), "whole native-input provenance digest")?;
        }
        for id in [
            &self.original_build_id,
            &self.derived_build_id,
            &self.original_setup_build_id,
            &self.derived_setup_build_id,
        ] {
            require(
                (32..=128).contains(&id.len())
                    && id.len() % 2 == 0
                    && id
                        .bytes()
                        .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
                "complete original/derived Build ID",
            )?;
        }
        require(
            self.source_basis == "public-reference-not-source-equivalent"
                && self.unsupported_effective_profiles.len() <= 512
                && self
                    .unsupported_effective_profiles
                    .windows(2)
                    .all(|w| w[0] < w[1])
                && self.unsupported_effective_profiles.iter().all(|s| {
                    !s.is_empty()
                        && s.len() <= 128
                        && s.bytes()
                            .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
                })
                && self.unsupported_rc_actions.windows(2).all(|w| w[0] < w[1])
                && self.unsupported_rc_actions.iter().all(|s| {
                    matches!(
                        s.as_str(),
                        "nnapi_latency_sensitive_hint" | "v1_memory_pressure_level_interface"
                    )
                }),
            "explicit source basis and unresolved effective profile catalog",
        )?;
        self.validated_build()?;
        Ok(())
    }
    fn validated_build(&self) -> Result<build_evidence::ValidatedBuild> {
        let artifact = |bytes: u64, sha256: &str, build_id: &str| build_evidence::Artifact {
            file: build_evidence::Pin {
                bytes,
                sha256: sha256.to_owned(),
            },
            build_id: build_id.to_owned(),
        };
        let pairs = build_evidence::Pairs {
            original_main: artifact(
                self.original_elf_bytes,
                &self.original_elf_sha256,
                &self.original_build_id,
            ),
            derived_main: artifact(
                self.library.bytes,
                &self.library.sha256,
                &self.derived_build_id,
            ),
            original_setup: artifact(
                self.original_setup_elf_bytes,
                &self.original_setup_elf_sha256,
                &self.original_setup_build_id,
            ),
            derived_setup: artifact(
                self.setup_library.bytes,
                &self.setup_library.sha256,
                &self.derived_setup_build_id,
            ),
        };
        self.build_evidence
            .validate(&build_evidence::Bindings {
                source_system_sha256: &self.source_system_sha256,
                source_basis: &self.source_basis,
                pairs: &pairs,
            })
            .map_err(MountError::Rejected)
    }
}

#[derive(Debug)]
struct Role {
    file: File,
    identity: FileIdentity,
    label: NativeLabel,
}
fn opened(parent: &File, name: &CStr, directory: bool) -> Result<File> {
    syscall_fd(unsafe {
        libc::syscall(
            libc::SYS_openat,
            parent.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY
                | libc::O_NOFOLLOW
                | libc::O_CLOEXEC
                | libc::O_NONBLOCK
                | if directory { libc::O_DIRECTORY } else { 0 },
            0,
        )
    })
}
fn digest_file(file: &File, bytes: u64) -> Result<String> {
    let mut hash = Sha256::new();
    let mut offset = 0;
    let mut buffer = [0u8; 16384];
    while offset < bytes {
        let n = usize::try_from((bytes - offset).min(buffer.len() as u64)).unwrap();
        file.read_exact_at(&mut buffer[..n], offset)?;
        hash.update(&buffer[..n]);
        offset += n as u64;
    }
    Ok(format!("{:x}", hash.finalize()))
}
fn library_build_id(file: &File, bytes: u64) -> Result<String> {
    let mut header = [0u8; 64];
    file.read_exact_at(&mut header, 0)?;
    let u16_at = |n| u16::from_le_bytes(header[n..n + 2].try_into().unwrap());
    let u64_at = |n| u64::from_le_bytes(header[n..n + 8].try_into().unwrap());
    require(
        &header[..7] == b"\x7fELF\x02\x01\x01"
            && u16_at(16) == 3
            && u16_at(18) == 62
            && u16_at(52) == 64
            && u16_at(54) == 56,
        "actual fixed x86_64 DSO header",
    )?;
    let offset = u64_at(32);
    let count = u16_at(56) as u64;
    require(
        (1..=128).contains(&count)
            && offset >= 64
            && offset.checked_add(count * 56).is_some_and(|v| v <= bytes),
        "bounded DSO program table",
    )?;
    let mut id = None;
    let mut executable = false;
    let mut stack = false;
    for index in 0..count {
        let mut ph = [0u8; 56];
        file.read_exact_at(&mut ph, offset + index * 56)?;
        let kind = u32::from_le_bytes(ph[..4].try_into().unwrap());
        let flags = u32::from_le_bytes(ph[4..8].try_into().unwrap());
        let start = u64::from_le_bytes(ph[8..16].try_into().unwrap());
        let size = u64::from_le_bytes(ph[32..40].try_into().unwrap());
        let memory = u64::from_le_bytes(ph[40..48].try_into().unwrap());
        require(
            start.checked_add(size).is_some_and(|v| v <= bytes) && kind != 3,
            "complete DSO segments without interpreter",
        )?;
        if kind == 1 {
            require(size <= memory && flags & 3 != 3, "non-WX DSO load segment")?;
            executable |= flags & 1 != 0 && size > 0;
        }
        if kind == 0x6474e551 {
            require(!stack && flags & 1 == 0, "unique NX stack")?;
            stack = true;
        }
        if kind == 4 {
            require(size <= 65536, "bounded native notes")?;
            let mut notes = vec![0u8; size as usize];
            file.read_exact_at(&mut notes, start)?;
            let mut at = 0usize;
            while at < notes.len() {
                require(notes.len() - at >= 12, "complete native note header")?;
                let name = u32::from_le_bytes(notes[at..at + 4].try_into().unwrap()) as usize;
                let len = u32::from_le_bytes(notes[at + 4..at + 8].try_into().unwrap()) as usize;
                let ty = u32::from_le_bytes(notes[at + 8..at + 12].try_into().unwrap());
                let begin = at + 12;
                let value = begin
                    .checked_add((name + 3) & !3)
                    .ok_or(MountError::Rejected("native note overflow"))?;
                let end = value
                    .checked_add((len + 3) & !3)
                    .ok_or(MountError::Rejected("native note overflow"))?;
                require(end <= notes.len(), "complete native note")?;
                if name == 4 && &notes[begin..begin + 4] == b"GNU\0" && ty == 3 {
                    require(
                        id.is_none() && (16..=64).contains(&len),
                        "one actual native Build ID",
                    )?;
                    id = Some(
                        notes[value..value + len]
                            .iter()
                            .map(|b| format!("{b:02x}"))
                            .collect::<String>(),
                    );
                }
                at = end;
            }
        }
    }
    require(executable && stack, "actual executable DSO and NX stack")?;
    id.ok_or(MountError::Rejected("native Build ID missing"))
}
fn role(
    root: &File,
    parent: &CStr,
    name: &CStr,
    decl: &ImageDeclaration,
    label: NativeLabel,
    uids: IdRange,
    gids: IdRange,
) -> Result<Role> {
    let directory = opened(root, parent, true)?;
    let file = opened(&directory, name, false)?;
    let identity = FileIdentity::of(&file.metadata()?);
    require(
        identity.mode == libc::S_IFREG | 0o444
            && identity.uid == uids.start
            && identity.gid == gids.start
            && identity.links == 1
            && identity.bytes == decl.bytes,
        "actual native input inode and mapped ownership",
    )?;
    let mut vfs: libc::statvfs = unsafe { std::mem::zeroed() };
    zero_rc(unsafe { libc::fstatvfs(file.as_raw_fd(), &mut vfs) })?;
    require(
        vfs.f_flag as u64 & READONLY_FLAGS == READONLY_FLAGS
            && vfs.f_flag as u64 & MOUNT_ATTR_NOEXEC == 0,
        "native input on the owned readonly executable runtime filesystem",
    )?;
    label.check(&file)?;
    require_absent_xattr(&file, c"security.capability")?;
    require(
        digest_file(&file, decl.bytes)? == decl.sha256
            && FileIdentity::of(&file.metadata()?) == identity,
        "whole native role bytes and stable inode",
    )?;
    Ok(Role {
        file,
        identity,
        label,
    })
}

#[derive(Debug)]
pub(super) struct NativeResources {
    library: Role,
    setup_library: Role,
    policy: Role,
    _build: build_evidence::ValidatedBuild,
}
impl NativeResources {
    pub(super) fn prepare(
        root: &File,
        decl: &NativeDeclaration,
        uids: IdRange,
        gids: IdRange,
    ) -> Result<Self> {
        // The input producer may report an unresolved original boot action;
        // that report cannot authorize executing an RC with the action removed.
        // Optional named profiles are checked by the native backend when called.
        require(
            decl.unsupported_rc_actions.is_empty(),
            "original boot RC still has an unresolved resource action",
        )?;
        let library = role(
            root,
            c"lib64",
            c"libprocessgroup.so",
            &decl.library,
            NativeLabel::Library,
            uids,
            gids,
        )?;
        let setup_library = role(
            root,
            c"lib64",
            c"libprocessgroup_setup.so",
            &decl.setup_library,
            NativeLabel::Library,
            uids,
            gids,
        )?;
        let policy = role(
            root,
            c"rc",
            c"cgroup-v2-policy.json",
            &decl.policy,
            NativeLabel::Policy,
            uids,
            gids,
        )?;
        require(
            library_build_id(&library.file, decl.library.bytes)? == decl.derived_build_id,
            "actual derived Build ID",
        )?;
        require(
            library_build_id(&setup_library.file, decl.setup_library.bytes)?
                == decl.derived_setup_build_id,
            "actual derived setup Build ID",
        )?;
        let mut raw = vec![0u8; decl.policy.bytes as usize];
        policy.file.read_exact_at(&mut raw, 0)?;
        let value: serde_json::Value = serde_json::from_slice(&raw)?;
        require(
            value.get("schema").and_then(|v| v.as_u64()) == Some(1)
                && value.get("backend").and_then(|v| v.as_str()) == Some("droidloom-native-v2")
                && value.get("root_cpus").and_then(|v| v.as_str()) == Some("2-23")
                && value
                    .get("uclamp_latency_sensitive")
                    .and_then(|v| v.as_str())
                    == Some("reject-unimplemented"),
            "actual fixed v2 policy without invented latency actuator",
        )?;
        // Construct the retained build witness only after the two held DSO
        // bodies/Build IDs and the root-selected declaration have matched.
        // Its type still cannot stand in for an executed init/Ready witness.
        let build = decl.validated_build()?;
        let result = Self {
            library,
            setup_library,
            policy,
            _build: build,
        };
        result.revalidate()?;
        Ok(result)
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        for role in [&self.library, &self.setup_library, &self.policy] {
            require(
                FileIdentity::of(&role.file.metadata()?) == role.identity,
                "held native input unchanged",
            )?;
            role.label.check(&role.file)?;
            require_absent_xattr(&role.file, c"security.capability")?;
        }
        Ok(())
    }
}
