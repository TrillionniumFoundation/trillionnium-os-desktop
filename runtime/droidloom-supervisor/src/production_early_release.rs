//! Read the installed release through its final root while Ubuntu still owns the initramfs.
//! The board parent obtains this digest before publishing its own clone pidfd.
use super::*;
use std::collections::BTreeSet;
use std::io::Read;

const FINAL_ROOT: &str = "/root";
const PUBLIC: &str = "/etc/droidloom/container-launcher.json";
const MANAGER: &str = "/usr/lib/droidloom/production/current/droidloomd";

fn in_root(absolute: &str) -> PathBuf {
    Path::new(FINAL_ROOT).join(absolute.trim_start_matches('/'))
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

fn intake() -> Result<Option<SealedFile>> {
    let private = SealedFile::read(&in_root(SELECTION), SELECTION_LIMIT);
    let published = SealedFile::read(&in_root(PUBLIC), SELECTION_LIMIT);
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
    let (spec, bytes) = SealedFile::read(&in_root(SPECIFICATION), SPEC_LIMIT)?;
    let cell: CellSpec = serde_json::from_slice(&bytes)?;
    if spec.node.bytes != record.cell_spec_bytes || spec.sha256 != record.cell_spec_sha256 {
        return Err(SelectionError::Rejected(
            "early cell configuration differs from the selected release",
        ));
    }
    validate_spec(&record, &cell)?;
    let (program, elf) = SealedFile::read(
        &in_root(MANAGER),
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
    let (manifest, raw) = SealedFile::read(
        &in_root(&format!("/etc/droidloom/cohorts/{base}.json")),
        16 * 1024,
    )?;
    let runtime = &record.runtime_manifest_sha256;
    let (runtime_manifest, _) = SealedFile::read(
        &in_root(&format!("/etc/droidloom/runtime-cohorts/{runtime}.json")),
        256 * 1024,
    )?;
    if manifest.sha256 != *base
        || runtime_manifest.sha256 != *runtime
        || manifest.node.mode & 0o7777 != 0o400
        || runtime_manifest.node.mode & 0o7777 != 0o400
    {
        return Err(SelectionError::Rejected(
            "early release base or runtime manifest differs from private selection",
        ));
    }
    let members = crate::production_mounts::early_base_members(&raw).map_err(io::Error::other)?;
    let images = in_root(&format!("/var/lib/droidloom/cohorts/{base}/images"));
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
    for (path, file, node) in held {
        if Node::from(&file.metadata()?) != node
            || Node::from(&open_root_trusted(&path)?.metadata()?) != node
        {
            return Err(SelectionError::Changed);
        }
    }
    for input in [
        &choice,
        &published,
        &spec,
        &program,
        &manifest,
        &runtime_manifest,
    ] {
        input.revalidate_path()?;
    }
    Ok(Some(choice))
}

/// Check the private selection and all four raw files on the installed Ubuntu root.
/// After the board parent starts the original child, re-open both live kernel objects
/// before initramfs-tools moves /run and invokes run-init. Existing non-early releases
/// return None and never create an Android task.
pub fn verify_initramfs_release(switch_root: bool) -> io::Result<Option<String>> {
    if unsafe { libc::geteuid() } != 0 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "root-selected initramfs release requires its boot owner",
        ));
    }
    let selected = intake().map_err(io::Error::other)?;
    let Some(choice) = selected else {
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
    Ok(Some(choice.sha256))
}
