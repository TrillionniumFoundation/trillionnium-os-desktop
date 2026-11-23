//! Read the installed release through its final root while Ubuntu still owns the initramfs.
//! The board parent obtains this digest before publishing its own clone pidfd.
use super::*;
use std::collections::BTreeSet;
use std::io::Read;

const FINAL_ROOT: &str = "/root";
const PUBLIC: &str = "/etc/droidloom/container-launcher.json";
const MANAGER: &str = "/usr/lib/droidloom/production/current/droidloomd";

#[derive(Clone, Copy)]
enum UbuntuRoot {
    MountedByInitramfs,
    AfterSwitchRoot,
}

impl UbuntuRoot {
    fn path(self, absolute: &str) -> PathBuf {
        match self {
            Self::MountedByInitramfs => {
                Path::new(FINAL_ROOT).join(absolute.trim_start_matches('/'))
            }
            Self::AfterSwitchRoot => PathBuf::from(absolute),
        }
    }
}

fn stream_hash(file: &File, bytes: u64) -> Result<String> {
    use std::os::unix::fs::FileExt;
    let mut buffer = vec![0; 1024 * 1024];
    let mut hash = Sha256::new();
    let mut offset = 0;
    while offset < bytes {
        let count = usize::try_from((bytes - offset).min(buffer.len() as u64)).expect("bounded");
        file.read_exact_at(&mut buffer[..count], offset)?;
        hash.update(&buffer[..count]);
        offset += count as u64;
    }
    Ok(format!("{:x}", hash.finalize()))
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct KernelFirstEntry {
    schema: u32,
    scope: String,
    base_cohort_sha256: String,
    source_system_sha256: String,
    init_path: String,
    init_bytes: u64,
    init_sha256: String,
    argv: Vec<String>,
}

fn validate_runtime_entry(bytes: &[u8], base: &str, system: &str) -> Result<()> {
    let doc: serde_json::Value = serde_json::from_slice(bytes)?;
    if doc["scope"] == "android_kernel_first_stage_v1" {
        let row: KernelFirstEntry = serde_json::from_slice(bytes)?;
        if row.schema != 1
            || row.scope != "android_kernel_first_stage_v1"
            || row.base_cohort_sha256 != base
            || row.source_system_sha256 != system
            || row.init_path != "/system/bin/init"
            || row.init_bytes != crate::production_cp3a_init_identity::INIT_BYTES
            || row.init_sha256 != crate::production_cp3a_init_identity::INIT_SHA256
            || row.argv != ["/system/bin/init", "second_stage"]
        {
            return Err(SelectionError::Rejected(
                "kernel-first runtime does not select the original init from this release",
            ));
        }
        return Ok(());
    }
    crate::production_runtime_assets::declared_boot_entry(bytes, base).map_err(io::Error::other)?;
    if doc["source_system"]["sha256"].as_str() != Some(system) {
        return Err(SelectionError::Rejected(
            "selected original runtime source image differs from the four-image release",
        ));
    }
    Ok(())
}

/// Check the original ELF on the very open descriptor that the board child will execute.
pub fn verify_original_init_for_boot(file: &File) -> io::Result<()> {
    let before = Node::from(&file.metadata()?);
    if before.mode & libc::S_IFMT != libc::S_IFREG
        || before.mode & 0o7777 != 0o755
        || before.bytes != crate::production_cp3a_init_identity::INIT_BYTES
        || stream_hash(file, before.bytes).map_err(io::Error::other)?
            != crate::production_cp3a_init_identity::INIT_SHA256
        || Node::from(&file.metadata()?) != before
    {
        return Err(io::Error::other(
            "prepared init ELF does not match the original CP3A executable",
        ));
    }
    Ok(())
}

/// Manifests and original image descriptors for one privately selected kernel-first boot.
pub(crate) struct EarlyReleaseMedia {
    manifest: SealedFile,
    runtime: SealedFile,
    images: Vec<(PathBuf, File, Node)>,
}

impl EarlyReleaseMedia {
    pub(crate) fn acquire(selection: &ProductionSelection) -> Result<Self> {
        selection.revalidate()?;
        if !selection.is_kernel_first() || selection.selected.node.mode & 0o7777 != 0o400 {
            return Err(SelectionError::Rejected(
                "private kernel-first selection required",
            ));
        }
        let media = Self::open(
            UbuntuRoot::AfterSwitchRoot,
            selection.base_cohort(),
            selection.runtime_manifest(),
        )?;
        selection.revalidate()?;
        Ok(media)
    }

    fn open(ubuntu: UbuntuRoot, base: &str, runtime: &str) -> Result<Self> {
        let (manifest, raw) = SealedFile::read(
            &ubuntu.path(&format!("/etc/droidloom/cohorts/{base}.json")),
            16 * 1024,
        )?;
        let (runtime_manifest, runtime_raw) = SealedFile::read(
            &ubuntu.path(&format!("/etc/droidloom/runtime-cohorts/{runtime}.json")),
            256 * 1024,
        )?;
        if manifest.sha256 != base
            || runtime_manifest.sha256 != runtime
            || manifest.node.mode & 0o7777 != 0o400
            || runtime_manifest.node.mode & 0o7777 != 0o400
        {
            return Err(SelectionError::Rejected(
                "early release base or runtime manifest differs from private selection",
            ));
        }
        let members =
            crate::production_mounts::early_base_members(&raw).map_err(io::Error::other)?;
        let source = &members[0].2;
        validate_runtime_entry(&runtime_raw, base, source)?;
        let images = ubuntu.path(&format!("/var/lib/droidloom/cohorts/{base}/images"));
        let mut original = BTreeSet::new();
        let mut held = Vec::new();
        for (role, size, sha) in members {
            let path = images.join(role);
            let file = open_root_trusted(&path)?;
            let node = Node::from(&file.metadata()?);
            require_public_regular(&node, size)?;
            require_no_capability(&file)?;
            if node.bytes != size
                || node.mode & 0o7777 != 0o400
                || !original.insert((node.device, node.inode))
                || stream_hash(&file, size)? != sha
            {
                return Err(SelectionError::Rejected(
                    "early raw image identity, size or complete digest differs",
                ));
            }
            held.push((path, file, node));
        }
        let value = Self {
            manifest,
            runtime: runtime_manifest,
            images: held,
        };
        value.revalidate()?;
        Ok(value)
    }

    pub(crate) fn revalidate(&self) -> Result<()> {
        self.manifest.revalidate_path()?;
        self.runtime.revalidate_path()?;
        for (path, file, original) in &self.images {
            if Node::from(&file.metadata()?) != *original
                || Node::from(&open_root_trusted(path)?.metadata()?) != *original
            {
                return Err(SelectionError::Changed);
            }
        }
        Ok(())
    }
}

fn intake(ubuntu: UbuntuRoot) -> Result<Option<(SealedFile, CellSpec, String)>> {
    let private = SealedFile::read(&ubuntu.path(SELECTION), SELECTION_LIMIT);
    let published = SealedFile::read(&ubuntu.path(PUBLIC), SELECTION_LIMIT);
    let optional = |r: Result<(SealedFile, Vec<u8>)>| match r {
        Ok(value) => Ok(Some(value)),
        Err(SelectionError::Io(e)) if e.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(other) => Err(other),
    };
    let public = optional(published)?;
    let uses_early = match &public {
        None => false,
        Some((_, raw)) => {
            serde_json::from_slice::<serde_json::Value>(raw)?["schema"]
                == "droidloom-public-early-launcher-v1"
        }
    };
    let Some((choice, raw)) = optional(private)? else {
        return if uses_early {
            Err(SelectionError::Rejected(
                "early public release lacks its private choice",
            ))
        } else {
            Ok(None)
        };
    };
    let record: Record = serde_json::from_slice(&raw)?;
    validate_record(&record)?;
    if record.schema != EARLY_SCHEMA {
        return if uses_early {
            Err(SelectionError::Rejected(
                "early public release has an older private choice",
            ))
        } else {
            Ok(None)
        };
    }
    if !uses_early || choice.node.mode & 0o7777 != 0o400 {
        return Err(SelectionError::Rejected(
            "private v4 early selection requires its root-only file and paired public release",
        ));
    }
    let (published, public_raw) =
        public.ok_or(SelectionError::Rejected("early public release missing"))?;
    let parsed = launcher::EarlyPublished::parse(&public_raw)?;
    let (selection_hash, program_hash, program_len) = parsed.owner();
    if !matches!(published.node.mode & 0o7777, 0o444 | 0o644) || selection_hash != choice.sha256 {
        return Err(SelectionError::Rejected(
            "early release does not match private selection",
        ));
    }
    let (spec, bytes) = SealedFile::read(&ubuntu.path(SPECIFICATION), SPEC_LIMIT)?;
    let cell: CellSpec = serde_json::from_slice(&bytes)?;
    if spec.node.bytes != record.cell_spec_bytes || spec.sha256 != record.cell_spec_sha256 {
        return Err(SelectionError::Rejected(
            "early cell configuration differs from the selected release",
        ));
    }
    validate_spec(&record, &cell)?;
    let (program, elf) = SealedFile::read(
        &ubuntu.path(MANAGER),
        crate::production_service_elf::MAX_SERVICE as u64,
    )?;
    crate::production_service_elf::inspect_container_service_elf(&elf)?;
    let running = File::open("/proc/self/exe")?;
    if program.node.mode & 0o7777 != 0o755
        || program.sha256 != program_hash
        || program.node.bytes != program_len
        || running.metadata()?.len() != program_len
        || stream_hash(&running, program_len)? != program_hash
    {
        return Err(SelectionError::Rejected(
            "initramfs and installed release must use the same selected manager ELF",
        ));
    }
    let base = &record.base_cohort_sha256;
    let media = EarlyReleaseMedia::open(ubuntu, base, &record.runtime_manifest_sha256)?;
    media.revalidate()?;
    for input in [&choice, &published, &spec, &program] {
        input.revalidate_path()?;
    }
    Ok(Some((choice, cell, base.clone())))
}

/// Check the private selection and all four raw files on the installed Ubuntu root.
/// After the board parent starts the original child, re-open both live kernel objects
/// before initramfs-tools moves /run and invokes run-init. Existing non-early releases
/// return None and never create an Android task.
pub fn verify_initramfs_release(switch_root: bool, emit_plan: bool) -> io::Result<Option<String>> {
    if unsafe { libc::geteuid() } != 0 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "root-selected initramfs release requires its boot owner",
        ));
    }
    let selected = intake(UbuntuRoot::MountedByInitramfs).map_err(io::Error::other)?;
    let Some((choice, cell, base)) = selected else {
        return Ok(None);
    };
    let mut mounts = String::new();
    File::open("/proc/self/mountinfo")?
        .take(4 * 1024 * 1024 + 1)
        .read_to_string(&mut mounts)?;
    if mounts.len() > 4 * 1024 * 1024
        || !mounts
            .lines()
            .any(|l| l.split_ascii_whitespace().nth(4) == Some(FINAL_ROOT))
    {
        return Err(io::Error::other(
            "the installed Ubuntu root is not mounted at the initramfs-tools root",
        ));
    }
    if switch_root {
        crate::production_selection::early_generation::verify_birth_before_switch(&choice.sha256)?;
    }
    choice.revalidate().map_err(io::Error::other)?;
    if emit_plan {
        return Ok(Some(board_plan(&choice, &cell, &base)));
    }
    Ok(Some(choice.sha256))
}

fn board_plan(choice: &SealedFile, cell: &CellSpec, base: &str) -> String {
    format!(
        "{} {} {} {} {} {} {}",
        choice.sha256,
        base,
        cell.host_uid,
        cell.subordinate_uids.start,
        cell.subordinate_uids.count,
        cell.subordinate_gids.start,
        cell.subordinate_gids.count
    )
}

fn check_linux_board_parent() -> io::Result<()> {
    if unsafe { libc::geteuid() } != 0 || unsafe { libc::getppid() } != 1 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "post-switch release check requires the Linux board PID 1 parent",
        ));
    }
    let installed = open_root_trusted(Path::new(
        "/usr/lib/droidloom/production/current/droidloom-board-init",
    ))
    .map_err(io::Error::other)?;
    let expected = installed.metadata()?;
    let running = std::fs::metadata("/proc/1/exe")?;
    if !expected.is_file()
        || expected.uid() != 0
        || expected.gid() != 0
        || expected.mode() & 0o7777 != 0o755
        || (expected.dev(), expected.ino()) != (running.dev(), running.ino())
    {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "Linux PID 1 is not the installed board entry",
        ));
    }
    Ok(())
}

/// Re-open the same complete immutable release after Ubuntu moved the root.
/// Only the original Linux board PID 1 can consume this verifier's output on its child pipe.
pub fn verify_post_switch_board_plan() -> io::Result<Option<String>> {
    check_linux_board_parent()?;
    let selected = intake(UbuntuRoot::AfterSwitchRoot).map_err(io::Error::other)?;
    let Some((choice, cell, base)) = selected else {
        return Ok(None);
    };
    super::early_generation::verify_birth_before_switch(&choice.sha256)?;
    let android =
        open_root_trusted(Path::new("/run/droidloom-early/pidns")).map_err(io::Error::other)?;
    // linux/nsfs.h: NS_GET_PARENT returns a fresh descriptor opened by the caller.
    const NS_GET_PARENT: libc::c_ulong = 0xb702;
    let raw = unsafe { libc::ioctl(android.as_raw_fd(), NS_GET_PARENT) };
    if raw < 0 {
        return Err(io::Error::last_os_error());
    }
    let parent = unsafe { File::from_raw_fd(raw) }.metadata()?;
    let linux = std::fs::metadata("/proc/1/ns/pid")?;
    let current = std::fs::metadata("/proc/self/ns/pid")?;
    if (parent.dev(), parent.ino()) != (linux.dev(), linux.ino())
        || (current.dev(), current.ino()) != (linux.dev(), linux.ino())
    {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "board PID 1 does not own the pinned Android PID namespace",
        ));
    }
    choice.revalidate().map_err(io::Error::other)?;
    check_linux_board_parent()?;
    Ok(Some(board_plan(&choice, &cell, &base)))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn kernel_first_manifest_rejects_changed_parent_command_and_body() {
        let base = "1".repeat(64);
        let system = "2".repeat(64);
        let known = serde_json::json!({"schema":1,"scope":"android_kernel_first_stage_v1","base_cohort_sha256":base,
          "source_system_sha256":system,"init_path":"/system/bin/init","init_bytes":crate::production_cp3a_init_identity::INIT_BYTES,
          "init_sha256":crate::production_cp3a_init_identity::INIT_SHA256,"argv":["/system/bin/init","second_stage"]});
        let check = |v: &serde_json::Value| {
            validate_runtime_entry(&serde_json::to_vec(v).unwrap(), &base, &system)
        };
        check(&known).unwrap();
        for (field, wrong) in [
            ("base_cohort_sha256", serde_json::json!(system)),
            ("source_system_sha256", serde_json::json!(base)),
            ("init_path", serde_json::json!("/init")),
            ("init_bytes", serde_json::json!(100)),
            ("init_sha256", serde_json::json!(base)),
            (
                "argv",
                serde_json::json!(["/system/bin/init", "first_stage"]),
            ),
            ("loader", serde_json::json!("wrapper")),
        ] {
            let mut changed = known.clone();
            changed[field] = wrong;
            assert!(check(&changed).is_err(), "{field}");
        }
    }
}
