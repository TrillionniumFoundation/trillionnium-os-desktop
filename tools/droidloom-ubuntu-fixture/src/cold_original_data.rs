//! Cold custody and crash recovery for one entire original data directory.
//!
//! There is no mutating physical CLI or caller-supplied acceptance flag. The
//! qualification controller owns the sealed authority, public cell migration,
//! configuration/identity locks and boot selection. This module owns only the
//! two directory moves, atomic exchange, and last publication of selected.json.
use crate::{Result, boot_files::FilePin, ensure, fs, model::Identity};
use rustix::fs::{AtFlags, FileType, FlockOperation, Mode, OFlags, RenameFlags};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs::File,
    io::Write,
    os::fd::AsRawFd,
    os::unix::fs::FileExt,
    path::{Path, PathBuf},
};
#[path = "cold_original_labels.rs"]
pub(super) mod labels;
#[path = "cold_original_data_scan.rs"]
mod reference_scan;
#[path = "cold_original_returned_data.rs"]
mod returned_data;
pub(crate) use returned_data::ReturnedWorkingPair;

const IMAGES: [&str; 2] = ["data.img", "metadata.img"];
const ORIGINAL: &str = "/var/lib/droidloom/users/1000/data";
const WORKING: &str = "/var/lib/droidloom-qualification/p4-private-account-working-copy-516eec-r1";
const SELECTED: &str = "/etc/droidloom/production/selected.json";
const ROLLBACK: &str = "data-pair.rollback";
const PENDING: &str = "data-selection.pending";
const INTENT: &str = "DATA-EXCHANGE-INTENT.json";
const COMMITTED: &str = "DATA-EXCHANGED.json";
const RESTORED: &str = "ORIGINAL-DATA-RESTORED.json";
const COPY_SHA: &str = "d5864566bd978921b427f2ff70df218214fc512406f8e491d46f3fdd80a39a89";
const CLONE_SHA: &str = "3eda27b424c264102e609fbb87392b4d34e14ce8440d1ab40ab250131fc92ca0";
const WORKING_MEMBERS: [&str; 9] = [
    "COLD-CLONE-VERIFIED.json",
    "INTENT.json",
    "MEITUAN-CE-ALIAS-METADATA.json",
    "MEITUAN-STORAGE-METADATA.json",
    "WORKING-COPY.json",
    "data-COPY.json",
    "data.img",
    "metadata-COPY.json",
    "metadata.img",
];

fn inode(a: &Identity, b: &Identity) -> bool {
    a.dev == b.dev && a.ino == b.ino
}
fn stable(a: &Identity, b: &Identity) -> bool {
    inode(a, b)
        && (a.mode, a.uid, a.gid, a.nlink, a.size) == (b.mode, b.uid, b.gid, b.nlink, b.size)
}
fn same_pin(a: &FilePin, b: &FilePin) -> bool {
    a.path == b.path && a.bytes == b.bytes && a.sha256 == b.sha256
}
fn image(name: &str) -> bool {
    IMAGES.contains(&name)
}
fn named(parent: &File, name: &str) -> Result<Option<Identity>> {
    match rustix::fs::statat(parent, name, AtFlags::SYMLINK_NOFOLLOW) {
        Ok(s) => Ok(Some(fs::identity(&s))),
        Err(rustix::io::Errno::NOENT) => Ok(None),
        Err(e) => Err(e.into()),
    }
}
fn open_at(parent: &File, name: &str, directory: bool) -> Result<File> {
    let mut flags =
        OFlags::RDONLY | OFlags::CLOEXEC | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::NOATIME;
    if directory {
        flags |= OFlags::DIRECTORY;
    }
    Ok(File::from(rustix::fs::openat(
        parent,
        name,
        flags,
        Mode::empty(),
    )?))
}
fn read_small(file: &File, limit: u64) -> Result<Vec<u8>> {
    let before = fs::stat(file)?;
    ensure(
        FileType::from_raw_mode(before.mode) == FileType::RegularFile
            && before.nlink == 1
            && before.size > 0
            && before.size <= limit,
        "bounded single-link metadata file required",
    )?;
    let mut bytes = vec![0; before.size as usize];
    file.read_exact_at(&mut bytes, 0)?;
    let mut extra = [0; 1];
    ensure(
        file.read_at(&mut extra, before.size)? == 0 && fs::stat(file)? == before,
        "metadata file changed during descriptor readback",
    )?;
    Ok(bytes)
}
fn list(directory: &File) -> Result<Vec<String>> {
    let before = fs::stat(directory)?;
    let mut result = Vec::new();
    for entry in rustix::fs::Dir::read_from(directory)? {
        let entry = entry?;
        let name = entry.file_name().to_str()?;
        if name != "." && name != ".." {
            result.push(name.to_owned());
        }
        ensure(result.len() <= 16, "unexpected data directory members")?;
    }
    ensure(
        fs::stat(directory)? == before,
        "data directory changed during enumeration",
    )?;
    result.sort();
    Ok(result)
}
fn no_privilege_attributes(file: &File) -> Result<()> {
    ensure(
        fs::xattrs(file)?.is_empty(),
        "data custody inputs carry an ACL or capability",
    )
}

fn root_pin(pin: &FilePin, limit: u64) -> Result<Vec<u8>> {
    ensure(
        fs::valid_digest(&pin.sha256) && pin.bytes > 0 && pin.bytes <= limit,
        "bounded source metadata pin required",
    )?;
    let tree = fs::Tree::open("/", 0)?;
    let path = fs::absolute_string(&pin.path)?;
    let file = tree.file(&path)?;
    let before = fs::stat(&file)?;
    ensure(
        before.uid == 0 && before.gid == 0 && before.nlink == 1 && before.mode & 0o6022 == 0,
        "data transaction evidence must retain root custody",
    )?;
    no_privilege_attributes(&file)?;
    let bytes = read_small(&file, limit)?;
    ensure(
        bytes.len() as u64 == pin.bytes
            && fs::digest(&bytes) == pin.sha256
            && tree.identity(&path)? == before,
        "data transaction evidence changed or differs from its complete pin",
    )?;
    Ok(bytes)
}
fn as_f9(node: &Identity) -> Value {
    json!([
        node.dev,
        node.ino,
        node.mode,
        node.uid,
        node.gid,
        node.nlink,
        node.size,
        i128::from(node.mtime_sec) * 1_000_000_000 + i128::from(node.mtime_nsec),
        i128::from(node.ctime_sec) * 1_000_000_000 + i128::from(node.ctime_nsec)
    ])
}
fn copy_identity(node: &Identity) -> Value {
    json!({"device":node.dev,"inode":node.ino,"mode":node.mode&0o7777,"uid":node.uid,
        "gid":node.gid,"nlink":node.nlink,"size":node.size,
        "mtime_ns":i128::from(node.mtime_sec)*1_000_000_000+i128::from(node.mtime_nsec),
        "ctime_ns":i128::from(node.ctime_sec)*1_000_000_000+i128::from(node.ctime_nsec)})
}
fn capture_pair(parent: &File, name: &str, names: &[&str], owner: u32) -> Result<PairRecord> {
    let directory = open_at(parent, name, true)?;
    let id = fs::stat(&directory)?;
    ensure(
        id.uid == owner && id.gid == owner && id.mode & 0o7777 == 0o700,
        "root-private original pair directory required",
    )?;
    no_privilege_attributes(&directory)?;
    ensure(
        list(&directory)?
            .iter()
            .map(String::as_str)
            .eq(names.iter().copied()),
        "initial data directory scope differs",
    )?;
    let mut members = BTreeMap::new();
    for name in names {
        let file = open_at(&directory, name, false)?;
        let node = fs::stat(&file)?;
        ensure(
            FileType::from_raw_mode(node.mode) == FileType::RegularFile
                && node.uid == owner
                && node.gid == owner
                && node.nlink == 1
                && node.mode & 0o7777 == if image(name) { 0o600 } else { 0o400 },
            "initial root-private backing or proof member differs",
        )?;
        no_privilege_attributes(&file)?;
        let sha256 = if image(name) {
            None
        } else {
            Some(fs::digest(&read_small(&file, 64 * 1024)?))
        };
        ensure(
            fs::stat(&file)? == node && named(&directory, name)? == Some(node.clone()),
            "initial data member changed during snapshot",
        )?;
        members.insert(
            (*name).to_owned(),
            Member {
                label_identity: labels::data_snapshot(&file, &node)?,
                identity: node,
                sha256,
            },
        );
    }
    ensure(
        fs::stat(&directory)? == id && named(parent, name)? == Some(id.clone()),
        "initial data directory changed during snapshot",
    )?;
    Ok(PairRecord {
        directory_label_identity: labels::data_snapshot(&directory, &id)?,
        directory: id,
        members,
    })
}
fn lineage(copy: &Value, clone: &Value, original: &PairRecord, working: &PairRecord) -> Result<()> {
    ensure(
        copy["schema"] == "p4-real-userdata-independent-working-copy-v1"
            && clone["schema"] == "pocket4-original-data-cold-compatibility-clone-v1",
        "original independent-copy producer schema differs",
    )?;
    let rows = copy["images"].as_array().ok_or("copy images missing")?;
    let cold = clone["rows"]
        .as_array()
        .ok_or("cold clone image rows missing")?;
    ensure(
        rows.len() == 2 && cold.len() == 2,
        "exact original data/metadata lineage required",
    )?;
    for (index, name) in IMAGES.iter().enumerate() {
        let row = &rows[index];
        let prior = &cold[index];
        let old = &original.members[*name].identity;
        let new = &working.members[*name].identity;
        ensure(
            row["name"] == *name
                && prior["role"] == if index == 0 { "data" } else { "metadata" }
                && prior["source_path"] == format!("{ORIGINAL}/{name}")
                && row["working_path"] == format!("{WORKING}/{name}")
                && row["source_path"] == prior["clone_path"]
                && row["source_f9_before"] == prior["clone_f9"]
                && row["source_f9_after"] == prior["clone_f9"]
                && row["sha256"] == prior["sha256"]
                && row["sha256"].as_str().is_some_and(fs::valid_digest)
                && prior["source_f9_before"] == as_f9(old)
                && prior["source_f9_after"] == as_f9(old)
                && row["working_identity"] == copy_identity(new)
                && prior["bytes"] == old.size
                && new.size == old.size
                && !inode(old, new),
            "actual original/cold-clone/working-copy F9 chain differs",
        )?;
    }
    Ok(())
}

/// The structural checker is also used by private mechanism tests. Only the
/// two normal admission paths below may add the fixed real-source comparison.
fn admitted_lineage(
    copy: &Value,
    clone: &Value,
    original: &PairRecord,
    working: &PairRecord,
) -> Result<()> {
    lineage(copy, clone, original, working)?;
    let stable_identity = |node: &Identity| -> [u64; 7] {
        [
            node.dev,
            node.ino,
            u64::from(node.mode),
            u64::from(node.uid),
            u64::from(node.gid),
            node.nlink,
            node.size,
        ]
    };
    crate::cold_original_once_recovery::contract::OriginalCopyPolicy::bind_cold_pairs(
        IMAGES.map(|name| stable_identity(&original.members[name].identity)),
        IMAGES.map(|name| stable_identity(&working.members[name].identity)),
    )?;
    Ok(())
}
fn initial_pair_sources(cold_clone: &FilePin) -> Result<(FilePin, PairRecord, PairRecord)> {
    ensure(
        cold_clone.bytes == 2843 && cold_clone.sha256 == CLONE_SHA,
        "exact retained original cold-clone proof required",
    )?;
    let cold_bytes = root_pin(cold_clone, 64 * 1024)?;
    let cold: Value = serde_json::from_slice(&cold_bytes)?;
    let working_copy = FilePin {
        path: Path::new(WORKING).join("WORKING-COPY.json"),
        bytes: 5217,
        sha256: COPY_SHA.into(),
    };
    let copy_bytes = root_pin(&working_copy, 64 * 1024)?;
    let copy: Value = serde_json::from_slice(&copy_bytes)?;
    ensure(
        copy["source_cold_clone_receipt"]["bytes"] == cold_clone.bytes
            && copy["source_cold_clone_receipt"]["sha256"] == cold_clone.sha256,
        "working copy lost its original clone proof",
    )?;
    let tree = fs::Tree::open("/", 0)?;
    let (old_parent, old_name) = tree.parent(ORIGINAL)?;
    let (new_parent, new_name) = tree.parent(WORKING)?;
    let original = capture_pair(&old_parent, &old_name, &IMAGES, 0)?;
    let working = capture_pair(&new_parent, &new_name, &WORKING_MEMBERS, 0)?;
    admitted_lineage(&copy, &cold, &original, &working)?;
    let new_dir = tree.dir(WORKING)?;
    for (index, name) in ["data-COPY.json", "metadata-COPY.json"].iter().enumerate() {
        let file = open_at(&new_dir, name, false)?;
        let value: Value = serde_json::from_slice(&read_small(&file, 64 * 1024)?)?;
        ensure(
            value == copy["images"][index],
            "individual copy producer receipt differs from its whole-pair record",
        )?;
    }
    ensure(
        original.members[IMAGES[0]].identity.size == 34_359_738_368
            && original.members[IMAGES[1]].identity.size == 134_217_728
            && working.members["WORKING-COPY.json"].sha256.as_deref() == Some(COPY_SHA)
            && working.members["COLD-CLONE-VERIFIED.json"].identity.size == cold_clone.bytes
            && working.members["COLD-CLONE-VERIFIED.json"]
                .sha256
                .as_deref()
                == Some(CLONE_SHA),
        "original Pocket4 backing sizes or copy proof differ",
    )?;
    ensure(
        root_pin(&working_copy, 64 * 1024)? == copy_bytes
            && root_pin(cold_clone, 64 * 1024)? == cold_bytes,
        "original copy evidence changed during metadata admission",
    )?;
    Ok((working_copy, original, working))
}
fn selection_input(cell: &FilePin, selection: &FilePin) -> Result<Vec<u8>> {
    ensure(
        cell.path == Path::new("/etc/droidloom/cell.json"),
        "selection must bind the actual fixed cell configuration",
    )?;
    let cell_bytes = root_pin(cell, 1024 * 1024)?;
    let spec: Value = serde_json::from_slice(&cell_bytes)?;
    let bytes = root_pin(selection, 16 * 1024)?;
    let selected: Value = serde_json::from_slice(&bytes)?;
    let object = selected
        .as_object()
        .ok_or("candidate selection is not an object")?;
    let mut fields = object.keys().map(String::as_str).collect::<Vec<_>>();
    fields.sort();
    ensure(
        fields
            == [
                "base_cohort_sha256",
                "cell_spec_bytes",
                "cell_spec_sha256",
                "host_uid",
                "launcher",
                "persistent_data",
                "runtime_manifest_sha256",
                "schema",
            ]
            && selected["schema"] == "droidloom-production-selection-v4"
            && selected["launcher"] == "early_boot_shared_kernel_v1"
            && selected["host_uid"] == 1000
            && selected["cell_spec_bytes"] == cell.bytes
            && selected["cell_spec_sha256"] == cell.sha256,
        "candidate selection is not the exact normal early-boot cell binding",
    )?;
    for field in ["base_cohort_sha256", "runtime_manifest_sha256"] {
        ensure(
            selected[field].as_str().is_some_and(fs::valid_digest),
            "selected normal public digest missing",
        )?;
    }
    let cohort = selected["base_cohort_sha256"].as_str().unwrap();
    ensure(
        spec["host_uid"] == 1000
            && spec["data_dir"] == ORIGINAL
            && spec["image_dir"] == format!("/var/lib/droidloom/cohorts/{cohort}/images")
            && spec["vendor_image"]
                == format!("/var/lib/droidloom/cohorts/{cohort}/images/vendor.img")
            && spec["android_init"].is_null()
            && spec["gapps_dir"].is_null(),
        "new cell must retain original data and normal cohort only",
    )?;
    for field in [
        "android_file_overrides",
        "android_runtime_directories",
        "shared_storage_directories",
    ] {
        ensure(
            spec[field].is_null() || spec[field].as_array().is_some_and(Vec::is_empty),
            "legacy cell overrides cannot authorize selected data",
        )?;
    }
    ensure(
        selected["persistent_data"]["mode"] == "original-ext4-v1"
            && selected["persistent_data"]["data"]["image_bytes"] == 34_359_738_368u64
            && selected["persistent_data"]["metadata"]["image_bytes"] == 134_217_728u64,
        "selection requires the actual original image pair policy",
    )?;
    // The sealed qualification authority verifies the remaining normal source,
    // ext4 policy and cohort fields. This publication rechecks its exact bytes.
    ensure(
        root_pin(cell, 1024 * 1024)? == cell_bytes,
        "cell changed across selection readback",
    )?;
    Ok(bytes)
}

fn prepare_intent(
    locations: Locations,
    candidate_id: &str,
    cell: &FilePin,
    selection: &FilePin,
    cold_clone: &FilePin,
) -> Result<DataTransaction> {
    locations.validate()?;
    ensure(
        locations.owner == 0 && fs::valid_digest(candidate_id),
        "physical data preparation requires original root custody",
    )?;
    for name in [INTENT, PENDING, ROLLBACK, COMMITTED, RESTORED] {
        ensure(
            named(&locations.work, name)?.is_none(),
            "data transaction work is create-only",
        )?;
    }
    let bytes = selection_input(cell, selection)?;
    let (working_copy, original, working) = initial_pair_sources(cold_clone)?;
    let old_selection =
        locations.public_file(&locations.selected_parent, &locations.selected_name)?;
    let mut pending = File::from(rustix::fs::openat(
        &locations.work,
        PENDING,
        OFlags::RDWR | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::from_raw_mode(0o444),
    )?);
    pending.write_all(&bytes)?;
    rustix::fs::fchmod(&pending, Mode::from_raw_mode(0o444))?;
    pending.sync_all()?;
    locations.work.sync_all()?;
    let new_selection = locations
        .public_file(&locations.work, PENDING)?
        .ok_or("prepared selected bytes disappeared")?;
    ensure(
        new_selection.sha256 == selection.sha256 && new_selection.identity.size == selection.bytes,
        "private selected-file staging differs from source-bound candidate",
    )?;
    let boot = std::fs::read_to_string("/proc/sys/kernel/random/boot_id")?
        .trim()
        .to_owned();
    let intent = Intent {
        schema: "droidloom.original-data-exchange-intent.v1".into(),
        candidate_id: candidate_id.into(),
        original_boot_id: boot,
        work: locations.work_path.clone(),
        expected_cell: cell.clone(),
        selection: selection.clone(),
        working_copy,
        cold_clone: cold_clone.clone(),
        original,
        working,
        old_selection,
        new_selection,
    };
    locations.write_json(INTENT, &intent)?;
    // No original path has changed. Reopen the durable record and acquire the
    // actual image OFD locks before the authority may request the first move.
    DataTransaction::reopen(locations)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InspectionPlan {
    schema: String,
    work_directory: PathBuf,
    cold_clone: FilePin,
}

fn reference_targets(original: &PairRecord, working: &PairRecord) -> Vec<Identity> {
    let mut result = vec![original.directory.clone(), working.directory.clone()];
    for pair in [original, working] {
        for name in IMAGES {
            result.push(pair.members[name].identity.clone());
        }
    }
    result
}
pub(super) fn inspect(config: &Path, expected: &str) -> Result<Value> {
    ensure(
        fs::valid_digest(expected),
        "invalid data inspection plan digest",
    )?;
    let input_tree = fs::Tree::open("/", 0)?;
    let input_file = input_tree.file(&fs::absolute_string(config)?)?;
    let raw = read_small(&input_file, 64 * 1024)?;
    let input = FilePin {
        path: config.to_owned(),
        bytes: raw.len() as u64,
        sha256: fs::digest(&raw),
    };
    ensure(
        input.sha256 == expected && root_pin(&input, 64 * 1024)? == raw,
        "original data inspection plan digest differs",
    )?;
    let plan: InspectionPlan = serde_json::from_slice(&raw)?;
    let name = plan
        .work_directory
        .file_name()
        .and_then(|s| s.to_str())
        .ok_or("inspection work name missing")?;
    ensure(
        plan.schema == "droidloom.original-data-inspection-plan.v1"
            && plan.work_directory.parent() == Some(Path::new("/var/lib/droidloom-qualification"))
            && name.starts_with("original-data-inspect-")
            && (24..=80).contains(&name.len())
            && name
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-'),
        "data inspection needs a create-only protected qualification child",
    )?;
    crate::cold_original_initramfs::original_context()?;
    crate::boot_files::private_dir(&plan.work_directory)?;
    let mut result = inspect_snapshot(&plan.cold_clone)?;
    ensure(
        root_pin(&input, 64 * 1024)? == raw,
        "inspection plan changed during the complete metadata observation",
    )?;
    result["input"] = serde_json::to_value(&input)?;
    let path = plan.work_directory.join("ORIGINAL-DATA-INSPECTED.json");
    crate::boot_files::write_new(&path, &serde_json::to_vec_pretty(&result)?, 0o400)?;
    fs::Tree::open("/", 0)?
        .dir(&fs::absolute_string(&plan.work_directory)?)?
        .sync_all()?;
    Ok(result)
}

fn inspect_snapshot(cold_clone: &FilePin) -> Result<Value> {
    let original_context = crate::cold_original_initramfs::original_context()?;
    let (working_copy, original, working) = initial_pair_sources(cold_clone)?;
    let tree = fs::Tree::open("/", 0)?;
    let mut locks = Vec::new();
    for (path, pair) in [(ORIGINAL, &original), (WORKING, &working)] {
        let directory = tree.dir(path)?;
        for name in IMAGES {
            let file = open_at(&directory, name, false)?;
            ensure(
                fs::stat(&file)? == pair.members[name].identity,
                "actual image changed before inspection lock",
            )?;
            rustix::fs::flock(&file, FlockOperation::NonBlockingLockExclusive)?;
            locks.push((file, pair.members[name].identity.clone()));
        }
    }
    let references =
        reference_scan::require_no_other_references(&reference_targets(&original, &working))?;
    for (file, old) in &locks {
        ensure(
            fs::stat(file)? == *old,
            "image changed during original data inspection",
        )?;
    }
    let (_, old_after, new_after) = initial_pair_sources(cold_clone)?;
    ensure(
        old_after == original
            && new_after == working
            && crate::cold_original_initramfs::original_context()? == original_context,
        "original host or complete pair metadata changed across inspection",
    )?;
    let result = json!({"schema":"droidloom.original-data-inspected.v1",
        "original_host":original_context,"original":original,"working_copy":working,
        "working_copy_receipt":working_copy,"cold_clone":cold_clone,"references":references,
        "image_descriptors_opened_readonly":locks.len(),"image_bodies_read":false,"image_bodies_written":false,
        "directories_exchanged":false,"selected_published":false,"qualification_boot_authorized":false,
        "runtime_or_migration_accepted":false,"production_ready":false});
    Ok(result)
}

/// Read-only owner fence. The enclosing controller owns the fixed global
/// locks; the data adapter retains its image OFDs. Do not reacquire those OFD
/// flocks here, because a second open in this process must not displace them.
pub(super) fn assert_initial_pair_retired(cold_clone: &FilePin) -> Result<Value> {
    let (copy, original, working) = initial_pair_sources(cold_clone)?;
    let references =
        reference_scan::require_no_other_references(&reference_targets(&original, &working))?;
    let (after_copy, after_original, after_working) = initial_pair_sources(cold_clone)?;
    ensure(
        same_pin(&copy, &after_copy) && original == after_original && working == after_working,
        "initial pair changed across its complete retirement observation",
    )?;
    Ok(
        json!({"schema":"droidloom.original-data-initial-retirement.v1",
        "working_copy_receipt":copy,"cold_clone":cold_clone,"original":original,
        "working_copy":working,"references":references,"image_bodies_read":false,
        "physical_mutation_authorized":false,"runtime_or_migration_accepted":false}),
    )
}

/// The original source chain stays historical after a working image has run or
/// received a source-bound host label. This only observes current references;
/// the sealed controller and data adapter verify the phase/label derivation.
pub(super) fn assert_prepared_pair_retired(pair_intent: &FilePin) -> Result<Value> {
    let raw = root_pin(pair_intent, 128 * 1024)?;
    let intent: Intent = serde_json::from_slice(&raw)?;
    ensure(
        pair_intent.path == intent.work.join(INTENT),
        "pair retirement must bind its actual immutable intent",
    )?;
    let tx = DataTransaction::observe_intent(Locations::physical(&intent.work)?)?;
    ensure(
        same_pin(pair_intent, &tx.intent_pin)
            && tx.intent.working_copy.sha256 == COPY_SHA
            && tx.intent.cold_clone.sha256 == CLONE_SHA,
        "retirement intent lost its original source pins",
    )?;
    let before = tx.observe(true)?;
    let (original, working) = tx.current_pairs(before.0)?;
    let new_place = match before.0 {
        Layout::Ready => Place::Working,
        Layout::Staged => Place::Rollback,
        Layout::Switched => Place::Original,
    };
    let (parent, name) = tx.locations.at(new_place);
    let new_dir = open_at(parent, name, true)?;
    let proof = read_small(&open_at(&new_dir, "WORKING-COPY.json", false)?, 64 * 1024)?;
    ensure(
        fs::digest(&proof) == COPY_SHA,
        "working pair's historical source proof differs",
    )?;
    let copy: Value = serde_json::from_slice(&proof)?;
    let clone: Value = serde_json::from_slice(&root_pin(&tx.intent.cold_clone, 64 * 1024)?)?;
    admitted_lineage(&copy, &clone, &tx.intent.original, &tx.intent.working)?;
    let references =
        reference_scan::require_no_other_references(&reference_targets(&original, &working))?;
    ensure(
        tx.observe(true)? == before
            && tx.current_pairs(before.0)? == (original.clone(), working.clone())
            && root_pin(pair_intent, 128 * 1024)? == raw,
        "prepared pair or its immutable source evidence changed during retirement readback",
    )?;
    let layout = match before.0 {
        Layout::Ready => "original",
        Layout::Staged => "working_staged",
        Layout::Switched => "working_selected",
    };
    Ok(
        json!({"schema":"droidloom.original-data-prepared-retirement.v1",
        "pair_intent":pair_intent,"candidate_id":tx.intent.candidate_id,"layout":layout,
        "original":original,"working_copy":working,"references":references,
        "image_bodies_read":false,"physical_mutation_authorized":false,
        "working_clock_changes_are_not_admission":true,"runtime_or_migration_accepted":false}),
    )
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Member {
    identity: Identity,
    sha256: Option<String>,
    label_identity: labels::Snapshot,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct PairRecord {
    directory: Identity,
    members: BTreeMap<String, Member>,
    directory_label_identity: labels::Snapshot,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct PublicFile {
    identity: Identity,
    sha256: String,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Intent {
    schema: String,
    candidate_id: String,
    original_boot_id: String,
    work: PathBuf,
    expected_cell: FilePin,
    selection: FilePin,
    working_copy: FilePin,
    cold_clone: FilePin,
    original: PairRecord,
    working: PairRecord,
    old_selection: Option<PublicFile>,
    new_selection: PublicFile,
}

struct Locations {
    anchor: fs::Tree,
    ancestors: BTreeMap<String, Identity>,
    parent_paths: [String; 4],
    original_parent: File,
    working_parent: File,
    work: File,
    selected_parent: File,
    original_name: String,
    working_name: String,
    selected_name: String,
    work_path: PathBuf,
    owner: u32,
}
impl Locations {
    fn physical(work: &Path) -> Result<Self> {
        ensure(
            work.is_absolute()
                && work != Path::new(WORKING)
                && !work.starts_with(ORIGINAL)
                && !work.starts_with(WORKING),
            "data recovery work cannot be inside either data directory",
        )?;
        let tree = fs::Tree::open("/", 0)?;
        let parent = |path: &str| tree.parent(path);
        let (original_parent, original_name) = parent(ORIGINAL)?;
        let (working_parent, working_name) = parent(WORKING)?;
        let (selected_parent, selected_name) = parent(SELECTED)?;
        let work_fd = tree.dir(&fs::absolute_string(work)?)?;
        let parent_paths = [
            Path::new(ORIGINAL)
                .parent()
                .unwrap()
                .to_str()
                .unwrap()
                .to_owned(),
            Path::new(WORKING)
                .parent()
                .unwrap()
                .to_str()
                .unwrap()
                .to_owned(),
            fs::absolute_string(work)?,
            Path::new(SELECTED)
                .parent()
                .unwrap()
                .to_str()
                .unwrap()
                .to_owned(),
        ];
        let ancestors = Self::ancestors(&tree, &parent_paths)?;
        let value = Self {
            anchor: tree,
            ancestors,
            parent_paths,
            original_parent,
            working_parent,
            work: work_fd,
            selected_parent,
            original_name,
            working_name,
            selected_name,
            work_path: work.to_owned(),
            owner: 0,
        };
        value.validate()?;
        Ok(value)
    }
    fn ancestors(tree: &fs::Tree, paths: &[String; 4]) -> Result<BTreeMap<String, Identity>> {
        let mut result = BTreeMap::new();
        for path in paths {
            let mut current = String::new();
            for name in path.split('/').filter(|p| !p.is_empty()) {
                current.push('/');
                current.push_str(name);
                result.insert(current.clone(), fs::stat(&tree.dir(&current)?)?);
            }
        }
        Ok(result)
    }
    fn validate(&self) -> Result<()> {
        let device = fs::stat(&self.original_parent)?.dev;
        for fd in [
            &self.original_parent,
            &self.working_parent,
            &self.work,
            &self.selected_parent,
        ] {
            let s = fs::stat(fd)?;
            ensure(
                FileType::from_raw_mode(s.mode) == FileType::Directory
                    && s.dev == device
                    && s.uid == self.owner
                    && s.gid == self.owner
                    && s.mode & 0o022 == 0,
                "data transaction requires protected same-filesystem parents",
            )?;
        }
        for (path, old) in &self.ancestors {
            let current = fs::stat(&self.anchor.dir(path)?)?;
            ensure(
                inode(&current, old)
                    && (current.mode, current.uid, current.gid) == (old.mode, old.uid, old.gid),
                "original data/configuration ancestor was replaced or changed authority",
            )?;
        }
        for (path, held) in self.parent_paths.iter().zip([
            &self.original_parent,
            &self.working_parent,
            &self.work,
            &self.selected_parent,
        ]) {
            ensure(
                fs::stat(&self.anchor.dir(path)?)? == fs::stat(held)?,
                "held data transaction parent is no longer its named inode",
            )?;
        }
        ensure(
            fs::stat(&self.work)?.mode & 0o7777 == 0o700,
            "data recovery work must be private",
        )
    }
    fn at(&self, place: Place) -> (&File, &str) {
        match place {
            Place::Original => (&self.original_parent, &self.original_name),
            Place::Working => (&self.working_parent, &self.working_name),
            Place::Rollback => (&self.work, ROLLBACK),
        }
    }
    fn pair(&self, place: Place, expected: &PairRecord, mutable: bool) -> Result<PairRecord> {
        let (parent, name) = self.at(place);
        let dir = open_at(parent, name, true)?;
        let before = fs::stat(&dir)?;
        ensure(
            stable(&before, &expected.directory)
                && before.uid == self.owner
                && before.gid == self.owner
                && before.mode & 0o7777 == 0o700,
            "selected data directory inode or authority changed",
        )?;
        let names = list(&dir)?;
        ensure(
            names == expected.members.keys().cloned().collect::<Vec<_>>(),
            "data directory member set changed",
        )?;
        no_privilege_attributes(&dir)?;
        let directory_label_identity = labels::data_snapshot(&dir, &before)?;
        labels::verify_data_snapshot(
            &expected.directory_label_identity,
            &directory_label_identity,
            mutable,
        )?;
        let mut members = BTreeMap::new();
        for name in names {
            let file = open_at(&dir, &name, false)?;
            let id = fs::stat(&file)?;
            let old = &expected.members[&name];
            ensure(
                FileType::from_raw_mode(id.mode) == FileType::RegularFile
                    && id.uid == self.owner
                    && id.gid == self.owner
                    && id.nlink == 1
                    && id.mode & 0o7777 == if image(&name) { 0o600 } else { 0o400 },
                "private data member ownership, links or mode changed",
            )?;
            ensure(
                if mutable {
                    if image(&name) {
                        stable(&id, &old.identity)
                    } else {
                        // This branch is only the current retirement observer.
                        // The immutable proof bytes, mtime and every field except
                        // ctime remain exact. Actual label admission separately
                        // consumes the opaque source-bound label derivation.
                        labels::only_ctime_changed(&old.identity, &id)
                    }
                } else {
                    id == old.identity
                },
                "original data member identity changed",
            )?;
            no_privilege_attributes(&file)?;
            let label_identity = labels::data_snapshot(&file, &id)?;
            labels::verify_data_snapshot(&old.label_identity, &label_identity, mutable)?;
            let sha256 = if image(&name) {
                None
            } else {
                Some(fs::digest(&read_small(&file, 64 * 1024)?))
            };
            ensure(
                sha256 == old.sha256
                    && fs::stat(&file)? == id
                    && named(&dir, &name)? == Some(id.clone()),
                "data proof member or named backing changed",
            )?;
            members.insert(
                name,
                Member {
                    identity: id,
                    sha256,
                    label_identity,
                },
            );
        }
        ensure(
            fs::stat(&dir)? == before && named(parent, name)? == Some(before.clone()),
            "held data directory changed across its complete member readback",
        )?;
        Ok(PairRecord {
            directory: before,
            members,
            directory_label_identity,
        })
    }
    fn public_file(&self, parent: &File, name: &str) -> Result<Option<PublicFile>> {
        if named(parent, name)?.is_none() {
            return Ok(None);
        }
        let file = open_at(parent, name, false)?;
        let id = fs::stat(&file)?;
        ensure(
            id.uid == self.owner && id.gid == self.owner && id.mode & 0o6022 == 0,
            "selection must be root-protected ordinary public configuration",
        )?;
        no_privilege_attributes(&file)?;
        let bytes = read_small(&file, 16 * 1024)?;
        ensure(
            named(parent, name)? == Some(id.clone()),
            "selection named inode changed",
        )?;
        Ok(Some(PublicFile {
            identity: id,
            sha256: fs::digest(&bytes),
        }))
    }
    fn write_json(&self, name: &str, value: &impl Serialize) -> Result<FilePin> {
        let bytes = serde_json::to_vec_pretty(value)?;
        ensure(
            !bytes.is_empty() && bytes.len() <= 128 * 1024,
            "bounded data transaction record",
        )?;
        let mut file = File::from(rustix::fs::openat(
            &self.work,
            name,
            OFlags::RDWR | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::from_raw_mode(0o400),
        )?);
        file.write_all(&bytes)?;
        rustix::fs::fchmod(&file, Mode::from_raw_mode(0o400))?;
        file.sync_all()?;
        self.work.sync_all()?;
        ensure(
            read_small(&file, 128 * 1024)? == bytes,
            "durable data transaction record readback differs",
        )?;
        Ok(FilePin {
            path: self.work_path.join(name),
            bytes: bytes.len() as u64,
            sha256: fs::digest(&bytes),
        })
    }
    fn move_pair(&self, from: Place, to: Place) -> Result<()> {
        let (source, old) = self.at(from);
        let (target, new) = self.at(to);
        rustix::fs::renameat_with(source, old, target, new, RenameFlags::NOREPLACE)?;
        source.sync_all()?;
        target.sync_all()?;
        Ok(())
    }
    fn exchange_pair(&self) -> Result<()> {
        rustix::fs::renameat_with(
            &self.original_parent,
            self.original_name.as_str(),
            &self.work,
            ROLLBACK,
            RenameFlags::EXCHANGE,
        )?;
        self.original_parent.sync_all()?;
        self.work.sync_all()?;
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Place {
    Original,
    Working,
    Rollback,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Layout {
    Ready,
    Staged,
    Switched,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum SelectionState {
    Original,
    Candidate,
}
fn matches_public(actual: Option<&PublicFile>, expected: Option<&PublicFile>) -> bool {
    match (actual, expected) {
        (None, None) => true,
        (Some(a), Some(b)) => stable(&a.identity, &b.identity) && a.sha256 == b.sha256,
        _ => false,
    }
}

/// The only cross-module data writer. Its constructor and each mutation take
/// the live once owner; no deserialized receipt or callback grants authority.
/// The original pair is never opened for writes. Later label/selection stages
/// must use this same four-descriptor custody after their source admission.
/// Actual current-process custody after both working backings were synchronized.
/// The once module may consume it to construct OriginalRetirement; a JSON
/// receipt or a caller boolean cannot create this object.
pub(super) struct WorkingDataRetired {
    candidate_id: String,
    pair_intent: FilePin,
    pid: u32,
    backings: std::cell::RefCell<Vec<(File, Identity)>>,
    snapshots: std::cell::RefCell<Vec<labels::Snapshot>>,
    names: Vec<String>,
    intent_file: File,
    intent_snapshot: labels::Snapshot,
    evidence: Value,
}
fn verify_retired_backings(backings: &[(File, Identity)]) -> Result<()> {
    ensure(
        backings.len() == 2,
        "both synchronized working backing descriptors are required",
    )?;
    for (file, expected) in backings {
        ensure(
            fs::stat(file)? == *expected,
            "synchronized working backing changed after retirement",
        )?;
        rustix::fs::flock(file, FlockOperation::NonBlockingLockExclusive)?;
    }
    Ok(())
}
impl WorkingDataRetired {
    pub(super) fn candidate_id(&self) -> &str {
        &self.candidate_id
    }
    pub(super) fn pair_intent(&self) -> &FilePin {
        &self.pair_intent
    }
    pub(super) fn evidence(&self) -> &Value {
        &self.evidence
    }
    pub(super) fn verify_working_identity(&self, identity: &Identity) -> Result<()> {
        self.revalidate()?;
        self.verify_working_identity_custody(identity)
    }
    pub(crate) fn verify_working_identity_custody(&self, identity: &Identity) -> Result<()> {
        self.revalidate_custody()?;
        let backings = self.backings.borrow();
        ensure(
            backings
                .iter()
                .filter(|(file, expected)| {
                    expected == identity && fs::stat(file).is_ok_and(|actual| actual == *identity)
                })
                .count()
                == 1,
            "current identity is not exactly one synchronized working backing",
        )?;
        verify_retired_backings(&backings)
    }
    pub(super) fn accept_label_restoration(
        &self,
        derivation: &labels::OriginalLabelRestoration,
    ) -> Result<()> {
        self.accept_label_restoration_custody(derivation)?;
        self.revalidate()
    }
    pub(crate) fn accept_label_restoration_custody(
        &self,
        derivation: &labels::OriginalLabelRestoration,
    ) -> Result<()> {
        ensure(
            std::process::id() == self.pid && derivation.candidate_id() == self.candidate_id,
            "working retirement restoration belongs to another owner or candidate",
        )?;
        derivation.revalidate()?;
        let Some(name) = derivation
            .path()
            .strip_prefix(ORIGINAL)
            .ok()
            .and_then(|p| p.to_str())
        else {
            return self.revalidate_custody();
        };
        if !IMAGES.contains(&name) {
            return self.revalidate_custody();
        }
        let mut backings = self.backings.borrow_mut();
        let mut snapshots = self.snapshots.borrow_mut();
        let mut matched = 0;
        for (index, (file, expected)) in backings.iter_mut().enumerate() {
            if inode(expected, derivation.before_identity()) {
                ensure(
                    (expected == derivation.before_identity()
                        || expected == derivation.after_identity())
                        && fs::stat(file)? == *derivation.after_identity(),
                    "working retirement ctime cannot be rebound from an unrelated restoration",
                )?;
                rustix::fs::flock(&*file, FlockOperation::NonBlockingLockExclusive)?;
                labels::accept_retired_snapshot(&mut snapshots[index], derivation)?;
                ensure(
                    labels::data_snapshot(file, derivation.after_identity())? == snapshots[index],
                    "restored working backing attributes or generation changed",
                )?;
                *expected = derivation.after_identity().clone();
                matched += 1;
            }
        }
        ensure(
            matched == 1,
            "working restoration does not identify exactly one synchronized backing",
        )?;
        verify_retired_backings(&backings)?;
        drop(snapshots);
        drop(backings);
        derivation.revalidate()?;
        self.revalidate_custody()
    }
    /// Metadata-only custody inside the real returned owner's bounded freeze
    /// window. This does not prove reference retirement or grant mutation.
    pub(crate) fn revalidate_custody(&self) -> Result<()> {
        ensure(
            std::process::id() == self.pid,
            "working retirement descriptor custody changed process",
        )?;
        ensure(
            labels::snapshot(&self.intent_file)? == self.intent_snapshot
                && fs::Tree::open("/", 0)?
                    .identity(&fs::absolute_string(&self.pair_intent.path)?)?
                    == fs::stat(&self.intent_file)?,
            "held immutable data intent custody changed",
        )?;
        let backings = self.backings.borrow();
        let snapshots = self.snapshots.borrow();
        verify_retired_backings(&backings)?;
        ensure(
            snapshots.len() == 2 && self.names.len() == 2,
            "complete retired snapshot/name custody required",
        )?;
        let work = self
            .pair_intent
            .path
            .parent()
            .ok_or("retired pair work missing")?;
        for (index, (file, expected)) in backings.iter().enumerate() {
            let path = std::fs::read_link(format!("/proc/self/fd/{}", file.as_raw_fd()))?;
            let allowed = [
                Path::new(ORIGINAL).join(&self.names[index]),
                Path::new(WORKING).join(&self.names[index]),
                work.join(ROLLBACK).join(&self.names[index]),
            ];
            ensure(
                allowed.contains(&path)
                    && fs::Tree::open("/", 0)?.identity(&fs::absolute_string(&path)?)? == *expected
                    && labels::data_snapshot(file, expected)? == snapshots[index]
                    && std::fs::read_link(format!("/proc/self/fd/{}", file.as_raw_fd()))? == path,
                "retired working descriptor lost its exact named inode, generation or attributes",
            )?;
        }
        verify_retired_backings(&backings)?;
        ensure(
            labels::snapshot(&self.intent_file)? == self.intent_snapshot,
            "retired intent changed during custody readback",
        )
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        ensure(
            std::process::id() == self.pid,
            "working retirement descriptor custody changed process",
        )?;
        self.revalidate_custody()?;
        let actual = assert_prepared_pair_retired(&self.pair_intent)?;
        ensure(
            actual["candidate_id"] == self.candidate_id,
            "retired working pair candidate changed",
        )?;
        self.revalidate_custody()
    }
}

pub(super) struct OriginalDataTransaction {
    transaction: DataTransaction,
}
impl OriginalDataTransaction {
    pub(super) fn prepare(
        authority: &crate::cold_original_qualification::OriginalQualificationAuthority,
        cold_clone: &FilePin,
    ) -> Result<Self> {
        use crate::cold_original_qualification::OriginalDataStep;
        authority.verify_data_step(OriginalDataStep::Prepare)?;
        let transaction = prepare_intent(
            Locations::physical(authority.work())?,
            authority.candidate_id(),
            authority.expected_cell(),
            authority.selection(),
            cold_clone,
        )?;
        let result = Self { transaction };
        result.binding(authority)?;
        authority.verify_data_step(OriginalDataStep::Prepare)?;
        Ok(result)
    }

    pub(super) fn resume(
        authority: &crate::cold_original_qualification::OriginalQualificationAuthority,
    ) -> Result<Self> {
        authority.verify_current_owner()?;
        let result = Self {
            transaction: DataTransaction::reopen(Locations::physical(authority.work())?)?,
        };
        result.binding(authority)?;
        authority.verify_current_owner()?;
        Ok(result)
    }

    pub(super) fn intent(&self) -> &FilePin {
        &self.transaction.intent_pin
    }

    pub(super) fn withdraw_selection(
        &self,
        authority: &crate::cold_original_qualification::OriginalQualificationAuthority,
    ) -> Result<Value> {
        use crate::cold_original_qualification::OriginalDataStep;
        self.fence(authority, OriginalDataStep::WithdrawSelection)?;
        let before = self.transaction.observe(true)?;
        let labeled = labels::withdraw_labeled_selection(authority, self)?;
        ensure(
            labeled.is_some() || before.1 == SelectionState::Original,
            "candidate selection lacks its actual durable source-bound rename history",
        )?;
        self.fence(authority, OriginalDataStep::WithdrawSelection)?;
        let after = self.transaction.observe(true)?;
        ensure(
            after.0 == before.0 && after.1 == SelectionState::Original,
            "actual selection withdrawal changed the data layout or retained candidate selection",
        )?;
        let actual = self.transaction.locations.public_file(
            &self.transaction.locations.selected_parent,
            &self.transaction.locations.selected_name,
        )?;
        let report = json!({"schema":"droidloom.original-selection-withdrawn.v1",
            "pair_intent":self.intent(),"candidate_id":authority.candidate_id(),
            "actual_original_selection":actual,"data_pair_restored":false,
            "working_backings_synchronized":false,"runtime_or_migration_accepted":false,
            "source_bound_label_evolution":labeled});
        const WITHDRAWN: &str = "DATA-SELECTION-WITHDRAWN.json";
        if named(&self.transaction.locations.work, WITHDRAWN)?.is_none() {
            self.transaction.locations.write_json(WITHDRAWN, &report)?;
        } else {
            let held = open_at(&self.transaction.locations.work, WITHDRAWN, false)?;
            let current: Value = serde_json::from_slice(&read_small(&held, 128 * 1024)?)?;
            ensure(
                current == report,
                "durable selection withdrawal record differs from actual readback",
            )?;
        }
        self.fence(authority, OriginalDataStep::WithdrawSelection)?;
        Ok(report)
    }

    pub(super) fn publish_selection(
        &self,
        authority: &crate::cold_original_qualification::OriginalQualificationAuthority,
        applied: &labels::OriginalLabelsApplied,
    ) -> Result<Value> {
        self.fence(
            authority,
            crate::cold_original_qualification::OriginalDataStep::PublishSelection,
        )?;
        let actual = applied.publish_selection(authority, self)?;
        self.fence(
            authority,
            crate::cold_original_qualification::OriginalDataStep::PublishSelection,
        )?;
        ensure(
            self.transaction.observe(true)? == (Layout::Switched, SelectionState::Candidate),
            "complete actual labeled selection was not published",
        )?;
        Ok(actual)
    }

    pub(super) fn retire_working(
        &self,
        authority: &crate::cold_original_qualification::OriginalQualificationAuthority,
    ) -> Result<WorkingDataRetired> {
        use crate::cold_original_qualification::OriginalDataStep;
        self.fence(authority, OriginalDataStep::RetireWorking)?;
        let before = self.transaction.observe(true)?;
        ensure(
            before.1 == SelectionState::Original,
            "working synchronization requires actual selected configuration withdrawal",
        )?;
        let first = assert_prepared_pair_retired(self.intent())?;
        let synchronization = self.transaction.sync_working_backings()?;
        self.fence(authority, OriginalDataStep::RetireWorking)?;
        ensure(
            self.transaction.observe(true)? == before,
            "working pair layout changed during retirement synchronization",
        )?;
        let second = assert_prepared_pair_retired(self.intent())?;
        let mut backings = Vec::new();
        for (file, _, working) in &self.transaction.images {
            if *working {
                backings.push((file.try_clone()?, fs::stat(file)?));
            }
        }
        verify_retired_backings(&backings)?;
        let mut snapshots = Vec::new();
        let mut names = Vec::new();
        for (file, id) in &backings {
            snapshots.push(labels::data_snapshot(file, id)?);
            let matches = IMAGES
                .iter()
                .filter(|name| {
                    inode(
                        id,
                        &self.transaction.intent.working.members[**name].identity,
                    )
                })
                .collect::<Vec<_>>();
            ensure(
                matches.len() == 1,
                "retired descriptor has no unique fixed working image name",
            )?;
            names.push((*matches[0]).to_owned());
        }
        let result = WorkingDataRetired {
            candidate_id: authority.candidate_id().to_owned(),
            pair_intent: self.intent().clone(),
            pid: std::process::id(),
            backings: std::cell::RefCell::new(backings),
            snapshots: std::cell::RefCell::new(snapshots),
            names,
            intent_file: self.transaction.intent_file.try_clone()?,
            intent_snapshot: labels::snapshot(&self.transaction.intent_file)?,
            evidence: json!({"schema":"droidloom.actual-working-data-retired.v1",
                "candidate_id":authority.candidate_id(),"pair_intent":self.intent(),
                "before_references":first,"actual_synchronization":synchronization,
                "after_references":second,"original_images_synchronized":false,
                "runtime_or_migration_accepted":false}),
        };
        result.revalidate()?;
        self.fence(authority, OriginalDataStep::RetireWorking)?;
        Ok(result)
    }
    pub(super) fn restore_pair(
        &self,
        retirement: &crate::cold_original_qualification::OriginalRetirement,
    ) -> Result<labels::OriginalPairRestored> {
        labels::restore_retired_pair(retirement, self)
    }

    fn binding(
        &self,
        authority: &crate::cold_original_qualification::OriginalQualificationAuthority,
    ) -> Result<()> {
        self.binding_custody(authority)?;
        self.transaction.validate_intent()?;
        // Actual fixed cell and immutable selection bytes are re-read at each
        // full phase fence. The bounded label window holds their exact custody
        // during its inode loop and re-reads complete bytes at both boundaries.
        selection_input(authority.expected_cell(), authority.selection())?;
        Ok(())
    }

    fn binding_custody(
        &self,
        authority: &crate::cold_original_qualification::OriginalQualificationAuthority,
    ) -> Result<()> {
        let tx = &self.transaction;
        tx.require_writer_locks()?;
        tx.validate_intent_custody()?;
        ensure(
            tx.intent.candidate_id == authority.candidate_id()
                && tx.intent.work == authority.work()
                && same_pin(&tx.intent.expected_cell, authority.expected_cell())
                && same_pin(&tx.intent.selection, authority.selection()),
            "data writer does not belong to the same sealed once owner",
        )?;
        Ok(())
    }

    fn fence(
        &self,
        authority: &crate::cold_original_qualification::OriginalQualificationAuthority,
        step: crate::cold_original_qualification::OriginalDataStep,
    ) -> Result<()> {
        authority.verify_data_step(step)?;
        self.binding(authority)?;
        Ok(())
    }

    pub(super) fn exchange(
        &self,
        authority: &crate::cold_original_qualification::OriginalQualificationAuthority,
    ) -> Result<Value> {
        use crate::cold_original_qualification::OriginalDataStep;
        let tx = &self.transaction;
        self.fence(authority, OriginalDataStep::Exchange)?;
        ensure(
            named(&tx.locations.work, RESTORED)?.is_none(),
            "restored data transaction cannot be exchanged again",
        )?;
        let (mut layout, selected) = tx.observe(false)?;
        ensure(
            selected == SelectionState::Original,
            "data exchange must precede selection publication",
        )?;
        if layout == Layout::Ready {
            tx.locations.move_pair(Place::Working, Place::Rollback)?;
            self.fence(authority, OriginalDataStep::Exchange)?;
            layout = tx.observe(false)?.0;
        }
        if layout == Layout::Staged {
            self.fence(authority, OriginalDataStep::Exchange)?;
            tx.locations.exchange_pair()?;
        }
        self.fence(authority, OriginalDataStep::Exchange)?;
        ensure(
            tx.observe(false)? == (Layout::Switched, SelectionState::Original),
            "atomic pair exchange did not retain the original selection",
        )?;
        let (original, working) = tx.current_pairs(Layout::Switched)?;
        Ok(json!({"schema":"droidloom.original-data-pair-exchanged.v1",
            "intent":tx.intent_pin,"candidate_id":tx.intent.candidate_id,
            "original":original,"working_copy":working,
            "selection_published":false,"labels_applied":false,
            "original_image_bodies_read":false,"original_image_bodies_written":false,
            "runtime_or_migration_accepted":false,"production_ready":false}))
    }
}

struct DataTransaction {
    locations: Locations,
    intent: Intent,
    intent_pin: FilePin,
    intent_file: File,
    intent_identity: Identity,
    // Read-only image descriptors carry the same flock protocol as the live
    // provider. Neither body is read or written by the directory transaction.
    images: Vec<(File, Identity, bool)>,
}
impl DataTransaction {
    fn observe_intent(locations: Locations) -> Result<Self> {
        locations.validate()?;
        let f = open_at(&locations.work, INTENT, false)?;
        let id = fs::stat(&f)?;
        ensure(
            id.uid == locations.owner && id.gid == locations.owner && id.mode & 0o7777 == 0o400,
            "original immutable data transaction intent custody",
        )?;
        let bytes = read_small(&f, 128 * 1024)?;
        no_privilege_attributes(&f)?;
        ensure(
            named(&locations.work, INTENT)? == Some(id.clone()),
            "immutable data intent pathname changed during admission",
        )?;
        let intent: Intent = serde_json::from_slice(&bytes)?;
        ensure(
            intent.schema == "droidloom.original-data-exchange-intent.v1"
                && fs::valid_digest(&intent.candidate_id)
                && intent.work == locations.work_path
                && intent.original.members.len() == 2
                && intent
                    .original
                    .members
                    .keys()
                    .map(String::as_str)
                    .eq(IMAGES)
                && intent
                    .working
                    .members
                    .keys()
                    .map(String::as_str)
                    .eq(WORKING_MEMBERS)
                && !inode(&intent.original.directory, &intent.working.directory),
            "closed original data transaction scope",
        )?;
        for record in [&intent.original, &intent.working] {
            labels::verify_snapshot_identity(&record.directory_label_identity, &record.directory)?;
            for member in record.members.values() {
                labels::verify_snapshot_identity(&member.label_identity, &member.identity)?;
            }
            ensure(
                record.directory.dev == fs::stat(&locations.work)?.dev,
                "data snapshot filesystem differs",
            )?;
            for name in IMAGES {
                let image = &record.members[name];
                ensure(
                    image.sha256.is_none() && image.identity.size > 0,
                    "data record cannot assert a newly verified image hash",
                )?;
            }
        }
        let mut distinct = std::collections::BTreeSet::new();
        for pair in [&intent.original, &intent.working] {
            for name in IMAGES {
                let n = &pair.members[name].identity;
                ensure(
                    distinct.insert((n.dev, n.ino)),
                    "all original and working backing roles require independent inodes",
                )?;
            }
        }
        let intent_pin = FilePin {
            path: locations.work_path.join(INTENT),
            bytes: bytes.len() as u64,
            sha256: fs::digest(&bytes),
        };
        let tx = Self {
            locations,
            intent,
            intent_pin,
            intent_file: f,
            intent_identity: id,
            images: Vec::new(),
        };
        tx.observe(true)?;
        Ok(tx)
    }
    fn reopen(locations: Locations) -> Result<Self> {
        let mut tx = Self::observe_intent(locations)?;
        let layout = tx.layout(true)?;
        let old = if layout == Layout::Switched {
            Place::Rollback
        } else {
            Place::Original
        };
        let new = match layout {
            Layout::Ready => Place::Working,
            Layout::Staged => Place::Rollback,
            Layout::Switched => Place::Original,
        };
        for (place, record, mutable) in [
            (old, &tx.intent.original, false),
            (new, &tx.intent.working, true),
        ] {
            let (parent, name) = tx.locations.at(place);
            let dir = open_at(parent, name, true)?;
            for name in IMAGES {
                let file = open_at(&dir, name, false)?;
                let node = fs::stat(&file)?;
                ensure(
                    if mutable {
                        stable(&node, &record.members[name].identity)
                    } else {
                        node == record.members[name].identity
                    },
                    "data backing changed before descriptor lock",
                )?;
                rustix::fs::flock(&file, FlockOperation::NonBlockingLockExclusive)?;
                tx.images
                    .push((file, record.members[name].identity.clone(), mutable));
            }
        }
        tx.observe(true)?;
        Ok(tx)
    }
    fn require_writer_locks(&self) -> Result<()> {
        ensure(
            self.images.len() == 4 && self.images.iter().filter(|row| row.2).count() == 2,
            "read-only data observation cannot perform a directory or selection mutation",
        )
    }
    fn current_pairs(&self, layout: Layout) -> Result<(PairRecord, PairRecord)> {
        let old = if layout == Layout::Switched {
            Place::Rollback
        } else {
            Place::Original
        };
        let new = match layout {
            Layout::Ready => Place::Working,
            Layout::Staged => Place::Rollback,
            Layout::Switched => Place::Original,
        };
        Ok((
            self.locations.pair(old, &self.intent.original, false)?,
            self.locations.pair(new, &self.intent.working, true)?,
        ))
    }
    fn validate_intent_custody(&self) -> Result<()> {
        ensure(
            fs::stat(&self.intent_file)? == self.intent_identity
                && named(&self.locations.work, INTENT)? == Some(self.intent_identity.clone()),
            "held immutable data intent was changed or replaced",
        )?;
        no_privilege_attributes(&self.intent_file)?;
        ensure(
            fs::stat(&self.intent_file)? == self.intent_identity,
            "immutable data intent changed during custody verification",
        )
    }
    fn validate_intent(&self) -> Result<()> {
        self.validate_intent_custody()?;
        let bytes = read_small(&self.intent_file, 128 * 1024)?;
        ensure(
            bytes.len() as u64 == self.intent_pin.bytes
                && fs::digest(&bytes) == self.intent_pin.sha256,
            "held immutable data intent bytes differ",
        )?;
        self.validate_intent_custody()
    }
    fn layout(&self, mutable: bool) -> Result<Layout> {
        let at = |place| {
            let (p, n) = self.locations.at(place);
            named(p, n)
        };
        let original = at(Place::Original)?.ok_or("fixed original data directory disappeared")?;
        let working = at(Place::Working)?;
        let rollback = at(Place::Rollback)?;
        let old = &self.intent.original;
        let new = &self.intent.working;
        let layout = if inode(&original, &old.directory)
            && working.as_ref().is_some_and(|i| inode(i, &new.directory))
            && rollback.is_none()
        {
            self.locations.pair(Place::Original, old, false)?;
            self.locations.pair(Place::Working, new, mutable)?;
            Layout::Ready
        } else if inode(&original, &old.directory)
            && working.is_none()
            && rollback.as_ref().is_some_and(|i| inode(i, &new.directory))
        {
            self.locations.pair(Place::Original, old, false)?;
            self.locations.pair(Place::Rollback, new, mutable)?;
            Layout::Staged
        } else if inode(&original, &new.directory)
            && working.is_none()
            && rollback.as_ref().is_some_and(|i| inode(i, &old.directory))
        {
            self.locations.pair(Place::Original, new, mutable)?;
            self.locations.pair(Place::Rollback, old, false)?;
            Layout::Switched
        } else {
            return Err(
                "unknown directory layout cannot be reconciled as an owned data exchange".into(),
            );
        };
        Ok(layout)
    }
    fn selection_state(&self) -> Result<SelectionState> {
        let current = self.locations.public_file(
            &self.locations.selected_parent,
            &self.locations.selected_name,
        )?;
        let pending = self.locations.public_file(&self.locations.work, PENDING)?;
        if matches_public(current.as_ref(), self.intent.old_selection.as_ref())
            && matches_public(pending.as_ref(), Some(&self.intent.new_selection))
        {
            return Ok(SelectionState::Original);
        }
        if matches_public(current.as_ref(), Some(&self.intent.new_selection))
            && matches_public(pending.as_ref(), self.intent.old_selection.as_ref())
        {
            return Ok(SelectionState::Candidate);
        }
        Err("selection or pending configuration is not an original owned inode".into())
    }
    fn observe(&self, mutable: bool) -> Result<(Layout, SelectionState)> {
        self.locations.validate()?;
        self.validate_intent()?;
        for (file, old, is_working) in &self.images {
            let now = fs::stat(file)?;
            ensure(
                if mutable && *is_working {
                    stable(&now, old)
                } else {
                    now == *old
                },
                "locked original backing changed",
            )?;
            rustix::fs::flock(file, FlockOperation::NonBlockingLockExclusive)?;
        }
        let layout = self.layout(mutable)?;
        let selection = self.selection_state()?;
        ensure(
            selection == SelectionState::Original || layout == Layout::Switched,
            "candidate selection cannot precede the atomic data exchange",
        )?;
        Ok((layout, selection))
    }
    fn publish_selection(&self) -> Result<()> {
        if self.intent.old_selection.is_some() {
            rustix::fs::renameat_with(
                &self.locations.work,
                PENDING,
                &self.locations.selected_parent,
                self.locations.selected_name.as_str(),
                RenameFlags::EXCHANGE,
            )?;
        } else {
            rustix::fs::renameat_with(
                &self.locations.work,
                PENDING,
                &self.locations.selected_parent,
                self.locations.selected_name.as_str(),
                RenameFlags::NOREPLACE,
            )?;
        }
        self.locations.work.sync_all()?;
        self.locations.selected_parent.sync_all()?;
        Ok(())
    }
    fn restore_selection(&self) -> Result<()> {
        if self.intent.old_selection.is_some() {
            self.publish_selection()
        } else {
            rustix::fs::renameat_with(
                &self.locations.selected_parent,
                self.locations.selected_name.as_str(),
                &self.locations.work,
                PENDING,
                RenameFlags::NOREPLACE,
            )?;
            self.locations.selected_parent.sync_all()?;
            self.locations.work.sync_all()?;
            Ok(())
        }
    }
    fn apply(
        &self,
        fence: &mut impl FnMut() -> Result<()>,
        checkpoint: &mut impl FnMut(&str) -> Result<()>,
    ) -> Result<Value> {
        self.require_writer_locks()?;
        ensure(
            named(&self.locations.work, RESTORED)?.is_none(),
            "restored one-shot data transaction cannot be reapplied",
        )?;
        fence()?;
        let (mut layout, mut selected) = self.observe(false)?;
        if layout == Layout::Ready {
            self.locations.move_pair(Place::Working, Place::Rollback)?;
            checkpoint("working-staged")?;
            fence()?;
            (layout, selected) = self.observe(false)?;
        }
        if layout == Layout::Staged {
            self.locations.exchange_pair()?;
            checkpoint("pair-exchanged")?;
            fence()?;
            (layout, selected) = self.observe(false)?;
        }
        ensure(layout == Layout::Switched, "working pair was not selected")?;
        if selected == SelectionState::Original {
            fence()?;
            self.observe(false)?;
            self.publish_selection()?;
            checkpoint("selection-published")?;
        }
        fence()?;
        ensure(
            self.observe(false)? == (Layout::Switched, SelectionState::Candidate),
            "selected data readback differs",
        )?;
        let report = self.report(false)?;
        if named(&self.locations.work, COMMITTED)?.is_none() {
            self.locations.write_json(COMMITTED, &report)?;
        }
        Ok(report)
    }
    fn restore(
        &self,
        fence: &mut impl FnMut() -> Result<()>,
        checkpoint: &mut impl FnMut(&str) -> Result<()>,
    ) -> Result<Value> {
        self.require_writer_locks()?;
        fence()?;
        let (mut layout, selected) = self.observe(true)?;
        // The sealed authority must first prove normal owned-runtime, mount
        // and loop retirement. Directory fsync alone cannot persist dirty
        // working-image data. Synchronize only the held working backings;
        // original image descriptors never receive a writeback operation.
        let synced = self.sync_working_backings()?;
        fence()?;
        self.observe(true)?;
        if selected == SelectionState::Candidate {
            self.restore_selection()?;
            checkpoint("selection-restored")?;
            fence()?;
            ensure(
                self.observe(true)?.1 == SelectionState::Original,
                "original selection readback differs",
            )?;
        }
        if layout == Layout::Switched {
            self.locations.exchange_pair()?;
            checkpoint("pair-restored")?;
            fence()?;
            layout = self.observe(true)?.0;
        }
        if layout == Layout::Staged {
            self.locations.move_pair(Place::Rollback, Place::Working)?;
            checkpoint("working-returned")?;
        }
        fence()?;
        ensure(
            self.observe(true)? == (Layout::Ready, SelectionState::Original),
            "original pair restoration differs",
        )?;
        let mut report = self.report(true)?;
        report["working_backing_sync"] = synced;
        if named(&self.locations.work, RESTORED)?.is_none() {
            self.locations.write_json(RESTORED, &report)?;
        }
        Ok(report)
    }
    fn sync_working_backings(&self) -> Result<Value> {
        let mut rows = Vec::new();
        for (file, expected, is_working) in &self.images {
            if !is_working {
                continue;
            }
            let before = fs::stat(file)?;
            ensure(
                stable(&before, expected),
                "working backing changed before recovery fsync",
            )?;
            rustix::fs::flock(file, FlockOperation::NonBlockingLockExclusive)?;
            file.sync_all()?;
            let after = fs::stat(file)?;
            ensure(
                before == after,
                "working backing identity changed across recovery fsync",
            )?;
            rows.push(json!({"before":before,"after":after,"fsync_completed":true}));
        }
        ensure(
            rows.len() == 2,
            "both working backings require actual recovery fsync",
        )?;
        Ok(
            json!({"schema":"droidloom.working-pair-recovery-fsync.v1","backings":rows,
            "normal_runtime_retirement_authority":"enclosing_original_qualification",
            "original_images_synchronized":false}),
        )
    }
    fn report(&self, restored: bool) -> Result<Value> {
        self.validate_intent()?;
        let old = if restored {
            Place::Original
        } else {
            Place::Rollback
        };
        let new = if restored {
            Place::Working
        } else {
            Place::Original
        };
        Ok(
            json!({"schema":"droidloom.original-data-directory-transaction.v1","intent":self.intent_pin,
            "candidate_id":self.intent.candidate_id,"original":self.locations.pair(old,&self.intent.original,false)?,
            "working_copy":self.locations.pair(new,&self.intent.working,restored)?,
            "original_pair_restored":restored,"working_pair_selected":!restored,
            "original_image_bodies_read":false,"original_image_bodies_written":false,
            "working_image_bodies_read":false,"working_image_bodies_written":false,
            "runtime_or_migration_accepted":false,"production_ready":false,
            "services_enabled":false,"default_boot_changed":false}),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    #[test]
    fn proof_ctime_is_only_a_retirement_observation_not_write_admission() {
        let area = Fixture::new(false);
        let transaction = area.open();
        let proof_path = area
            .root
            .path()
            .join("working-parent/working/WORKING-COPY.json");
        let proof = File::open(&proof_path).unwrap();
        let before = fs::stat(&proof).unwrap();
        rustix::fs::fchmod(&proof, Mode::from_raw_mode(before.mode & 0o7777)).unwrap();
        assert_ne!(before, fs::stat(&proof).unwrap());
        assert!(transaction.observe(true).is_ok());
        assert!(transaction.observe(false).is_err());
        // A real proof payload or mtime change is still refused by the
        // observer; only the actual label core can admit a ctime derivation.
        rustix::fs::fchmod(&proof, Mode::from_raw_mode(0o600)).unwrap();
        std::fs::write(&proof_path, b"changed proof").unwrap();
        rustix::fs::fchmod(&proof, Mode::from_raw_mode(0o400)).unwrap();
        assert!(transaction.observe(true).is_err());
    }

    #[test]
    fn actual_retired_working_backings_reject_a_post_sync_write() {
        let tmp = tempfile::tempdir().unwrap();
        let mut held = Vec::new();
        for name in ["working-data", "working-metadata"] {
            let path = tmp.path().join(name);
            std::fs::write(&path, b"isolated test working bytes").unwrap();
            let file = open_at(&File::open(tmp.path()).unwrap(), name, false).unwrap();
            rustix::fs::flock(&file, FlockOperation::NonBlockingLockExclusive).unwrap();
            file.sync_all().unwrap();
            let expected = fs::stat(&file).unwrap();
            held.push((file, expected));
        }
        verify_retired_backings(&held).unwrap();
        std::fs::write(tmp.path().join("working-data"), b"actual later write").unwrap();
        assert!(verify_retired_backings(&held).is_err());
    }

    #[test]
    #[ignore = "requires original Pocket4 and retained private-pair metadata; never writes or reads image bodies"]
    fn actual_original_device_complete_metadata_readback() {
        let cold_clone = FilePin {
            path: "/var/lib/droidloom-qualification/original-data-evidence-4b91-r1/COLD-CLONE-VERIFIED.json".into(),
            bytes: 2843,
            sha256: CLONE_SHA.into(),
        };
        let value = inspect_snapshot(&cold_clone).unwrap();
        println!(
            "{}",
            json!({"schema":"droidloom.original-data-metadata-readback-test.v1",
            "snapshot":value,"physical_mutation_executed":false})
        );
    }

    struct Fixture {
        root: tempfile::TempDir,
    }
    fn write(path: &Path, bytes: &[u8], mode: u32) {
        std::fs::write(path, bytes).unwrap();
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(mode)).unwrap();
    }
    fn record(path: &Path) -> PairRecord {
        let dir = File::open(path).unwrap();
        let mut members = BTreeMap::new();
        for name in list(&dir).unwrap() {
            let file = File::open(path.join(&name)).unwrap();
            members.insert(
                name.clone(),
                Member {
                    identity: fs::stat(&file).unwrap(),
                    label_identity: labels::snapshot(&file).unwrap(),
                    sha256: if image(&name) {
                        None
                    } else {
                        Some(fs::digest(&std::fs::read(path.join(&name)).unwrap()))
                    },
                },
            );
        }
        PairRecord {
            directory: fs::stat(&dir).unwrap(),
            members,
            directory_label_identity: labels::snapshot(&dir).unwrap(),
        }
    }
    fn public(path: &Path) -> PublicFile {
        PublicFile {
            identity: fs::stat(&File::open(path).unwrap()).unwrap(),
            sha256: fs::digest(&std::fs::read(path).unwrap()),
        }
    }
    impl Fixture {
        fn new(old_selection: bool) -> Self {
            let root = tempfile::Builder::new()
                .prefix(".p4-data-custody-")
                .tempdir_in(std::env::current_dir().unwrap())
                .unwrap();
            for p in [
                "original-parent",
                "working-parent",
                "work",
                "config",
                "original-parent/data",
                "working-parent/working",
            ] {
                let path = root.path().join(p);
                std::fs::create_dir(&path).unwrap();
                std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700)).unwrap();
            }
            for (base, byte) in [
                ("original-parent/data", b'o'),
                ("working-parent/working", b'w'),
            ] {
                for (index, name) in IMAGES.iter().enumerate() {
                    write(
                        &root.path().join(base).join(name),
                        &vec![byte + index as u8; 4096],
                        0o600,
                    );
                }
            }
            for name in WORKING_MEMBERS {
                if !image(name) {
                    write(
                        &root.path().join("working-parent/working").join(name),
                        b"{\"historical_proof\":true}\n",
                        0o400,
                    );
                }
            }
            if old_selection {
                write(
                    &root.path().join("config/selected.json"),
                    b"original public selection\n",
                    0o644,
                );
            }
            write(
                &root.path().join("work").join(PENDING),
                b"candidate public selection\n",
                0o444,
            );
            let fixture = Self { root };
            let l = fixture.locations();
            let dummy = FilePin {
                path: "/source-proof".into(),
                bytes: 1,
                sha256: "b".repeat(64),
            };
            let intent = Intent {
                schema: "droidloom.original-data-exchange-intent.v1".into(),
                candidate_id: "a".repeat(64),
                original_boot_id: "test-original-boot".into(),
                work: l.work_path.clone(),
                expected_cell: dummy.clone(),
                selection: dummy.clone(),
                working_copy: dummy.clone(),
                cold_clone: dummy,
                original: record(&fixture.root.path().join("original-parent/data")),
                working: record(&fixture.root.path().join("working-parent/working")),
                old_selection: if old_selection {
                    Some(public(&fixture.root.path().join("config/selected.json")))
                } else {
                    None
                },
                new_selection: public(&fixture.root.path().join("work").join(PENDING)),
            };
            l.write_json(INTENT, &intent).unwrap();
            fixture
        }
        fn locations(&self) -> Locations {
            let owner = rustix::process::getuid().as_raw();
            let anchor = fs::Tree::open(self.root.path().to_str().unwrap(), owner).unwrap();
            let parent_paths =
                ["/original-parent", "/working-parent", "/work", "/config"].map(str::to_owned);
            let ancestors = Locations::ancestors(&anchor, &parent_paths).unwrap();
            Locations {
                original_parent: anchor.dir(&parent_paths[0]).unwrap(),
                working_parent: anchor.dir(&parent_paths[1]).unwrap(),
                work: anchor.dir(&parent_paths[2]).unwrap(),
                selected_parent: anchor.dir(&parent_paths[3]).unwrap(),
                anchor,
                ancestors,
                parent_paths,
                original_name: "data".into(),
                working_name: "working".into(),
                selected_name: "selected.json".into(),
                work_path: self.root.path().join("work"),
                owner,
            }
        }
        fn open(&self) -> DataTransaction {
            DataTransaction::reopen(self.locations()).unwrap()
        }
        fn restored(&self, old: &PairRecord, new: &PairRecord, old_selection: bool) {
            let tx = self.open();
            assert_eq!(
                tx.observe(true).unwrap(),
                (Layout::Ready, SelectionState::Original)
            );
            let actual = record(&self.root.path().join("original-parent/data"));
            assert!(stable(&actual.directory, &old.directory));
            assert_eq!(actual.members, old.members);
            let actual = record(&self.root.path().join("working-parent/working"));
            assert!(stable(&actual.directory, &new.directory));
            for name in WORKING_MEMBERS {
                assert!(stable(
                    &actual.members[name].identity,
                    &new.members[name].identity
                ));
            }
            assert_eq!(
                self.root.path().join("config/selected.json").exists(),
                old_selection
            );
            for (i, name) in IMAGES.iter().enumerate() {
                assert_eq!(
                    std::fs::read(self.root.path().join("original-parent/data").join(name))
                        .unwrap(),
                    vec![b'o' + i as u8; 4096]
                );
            }
        }
    }
    fn okay() -> Result<()> {
        Ok(())
    }
    fn point(_: &str) -> Result<()> {
        Ok(())
    }

    #[test]
    fn original_rollback_directory_cannot_change_an_unrelated_xattr() {
        let fixture = Fixture::new(true);
        let tx = fixture.open();
        let (parent, name) = tx.locations.at(Place::Original);
        let directory = open_at(parent, name, true).unwrap();
        rustix::fs::fsetxattr(
            &directory,
            "user.unrelated",
            b"unreviewed",
            rustix::fs::XattrFlags::empty(),
        )
        .unwrap();
        assert!(tx.observe(true).is_err());
    }
    #[test]
    fn real_directory_exchange_and_selection_restore_preserve_original_images_and_mutated_copy() {
        for old_selection in [false, true] {
            let f = Fixture::new(old_selection);
            let tx = f.open();
            let old = tx.intent.original.clone();
            let new = tx.intent.working.clone();
            let report = tx.apply(&mut okay, &mut point).unwrap();
            assert_eq!(report["runtime_or_migration_accepted"], false);
            let path = f.root.path().join("original-parent/data/data.img");
            write(&path, &vec![b'z'; 4096], 0o600);
            drop(tx);
            let tx = f.open();
            let restored = tx.restore(&mut okay, &mut point).unwrap();
            let sync = &restored["working_backing_sync"];
            assert_eq!(sync["backings"].as_array().unwrap().len(), 2);
            assert_eq!(sync["original_images_synchronized"], false);
            for row in sync["backings"].as_array().unwrap() {
                assert_eq!(row["before"], row["after"]);
                assert_eq!(row["fsync_completed"], true);
            }
            drop(tx);
            f.restored(&old, &new, old_selection);
            assert_eq!(
                std::fs::read(f.root.path().join("working-parent/working/data.img")).unwrap(),
                vec![b'z'; 4096]
            );
        }
    }
    #[test]
    fn interruption_after_each_forward_atomic_operation_recovers_from_immutable_intent() {
        for old_selection in [false, true] {
            for stopped in ["working-staged", "pair-exchanged", "selection-published"] {
                let f = Fixture::new(old_selection);
                let tx = f.open();
                let old = tx.intent.original.clone();
                let new = tx.intent.working.clone();
                assert!(
                    tx.apply(&mut okay, &mut |stage| if stage == stopped {
                        Err("injected interruption".into())
                    } else {
                        Ok(())
                    })
                    .is_err()
                );
                drop(tx);
                let tx = f.open();
                tx.restore(&mut okay, &mut point).unwrap();
                drop(tx);
                f.restored(&old, &new, old_selection);
            }
        }
    }
    #[test]
    fn interruption_after_each_reverse_atomic_operation_is_resumable() {
        for old_selection in [false, true] {
            for stopped in ["selection-restored", "pair-restored", "working-returned"] {
                let f = Fixture::new(old_selection);
                let tx = f.open();
                let old = tx.intent.original.clone();
                let new = tx.intent.working.clone();
                tx.apply(&mut okay, &mut point).unwrap();
                assert!(
                    tx.restore(&mut okay, &mut |stage| if stage == stopped {
                        Err("injected interruption".into())
                    } else {
                        Ok(())
                    })
                    .is_err()
                );
                drop(tx);
                let tx = f.open();
                tx.restore(&mut okay, &mut point).unwrap();
                drop(tx);
                f.restored(&old, &new, old_selection);
            }
        }
    }
    #[test]
    fn changed_original_or_same_bytes_replacement_cannot_enter_exchange() {
        for replace in [false, true] {
            let f = Fixture::new(false);
            let path = f.root.path().join("original-parent/data/data.img");
            if replace {
                let new = path.with_extension("new");
                write(&new, &std::fs::read(&path).unwrap(), 0o600);
                std::fs::rename(new, &path).unwrap();
            } else {
                write(&path, &vec![b'x'; 4096], 0o600);
            }
            assert!(DataTransaction::reopen(f.locations()).is_err());
            assert!(f.root.path().join("working-parent/working").is_dir());
        }
    }
    #[test]
    fn held_intent_bytes_clocks_and_named_inode_are_required_before_every_move() {
        for case in 0..3 {
            let f = Fixture::new(false);
            let tx = f.open();
            tx.validate_intent_custody().unwrap();
            let original = record(&f.root.path().join("original-parent/data"));
            let path = f.root.path().join("work").join(INTENT);
            let bytes = std::fs::read(&path).unwrap();
            if case == 0 {
                let replacement = path.with_extension("replacement");
                write(&replacement, &bytes, 0o400);
                std::fs::rename(replacement, &path).unwrap();
            } else {
                std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
                if case == 1 {
                    let mut changed = bytes;
                    changed.push(b'\n');
                    std::fs::write(&path, changed).unwrap();
                }
                std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o400)).unwrap();
            }
            assert!(tx.validate_intent_custody().is_err());
            assert!(tx.apply(&mut okay, &mut point).is_err());
            assert_eq!(
                record(&f.root.path().join("original-parent/data")),
                original
            );
            assert!(f.root.path().join("working-parent/working").is_dir());
            assert!(!f.root.path().join("work").join(ROLLBACK).exists());
        }
    }
    #[test]
    fn retirement_observation_coexists_with_writer_ofds_but_cannot_mutate() {
        let f = Fixture::new(false);
        let writer = f.open();
        let observer = DataTransaction::observe_intent(f.locations()).unwrap();
        assert_eq!(
            observer.observe(true).unwrap(),
            writer.observe(true).unwrap()
        );
        assert_eq!(
            observer.current_pairs(Layout::Ready).unwrap(),
            writer.current_pairs(Layout::Ready).unwrap()
        );
        assert!(observer.apply(&mut okay, &mut point).is_err());
        assert!(observer.restore(&mut okay, &mut point).is_err());
        assert!(f.root.path().join("working-parent/working").is_dir());
        assert!(!f.root.path().join("work").join(ROLLBACK).exists());
    }
    #[test]
    fn unknown_alias_extra_entry_or_replaced_selection_is_never_removed() {
        use std::os::unix::fs::symlink;
        for case in 0..4 {
            let f = Fixture::new(false);
            match case {
                0 => {
                    let p = f.root.path().join("working-parent/working");
                    std::fs::rename(&p, p.with_file_name("saved")).unwrap();
                    symlink("saved", p).unwrap();
                }
                1 => write(
                    &f.root.path().join("working-parent/working/unlisted"),
                    b"unselected",
                    0o400,
                ),
                2 => {
                    let p = f.root.path().join("work").join(PENDING);
                    let q = p.with_extension("new");
                    write(&q, &std::fs::read(&p).unwrap(), 0o444);
                    std::fs::rename(q, p).unwrap();
                }
                _ => {
                    std::fs::create_dir(f.root.path().join("work").join(ROLLBACK)).unwrap();
                }
            }
            assert!(DataTransaction::reopen(f.locations()).is_err());
            assert!(f.root.path().join("original-parent/data").is_dir());
        }
    }
    #[test]
    fn competing_backing_lock_blocks_the_whole_transaction() {
        let f = Fixture::new(false);
        let held = File::open(f.root.path().join("working-parent/working/data.img")).unwrap();
        rustix::fs::flock(&held, FlockOperation::NonBlockingLockExclusive).unwrap();
        assert!(DataTransaction::reopen(f.locations()).is_err());
        assert!(f.root.path().join("working-parent/working").is_dir());
    }
    #[test]
    fn ancestor_replacement_and_failed_authority_fence_prevent_directory_changes() {
        let f = Fixture::new(false);
        let tx = f.open();
        assert!(
            tx.apply(&mut || Err("authority was revoked".into()), &mut point)
                .is_err()
        );
        let original = f.root.path().join("original-parent");
        let replacement = original.with_file_name("original-parent-old");
        std::fs::rename(&original, &replacement).unwrap();
        std::fs::create_dir(&original).unwrap();
        assert!(tx.apply(&mut okay, &mut point).is_err());
        assert!(replacement.join("data").is_dir());
        assert!(f.root.path().join("working-parent/working").is_dir());
    }

    #[test]
    fn source_lineage_checks_both_original_clocks_and_exact_working_inodes() {
        let f = Fixture::new(false);
        let tx = f.open();
        let original = &tx.intent.original;
        let working = &tx.intent.working;
        let mut copy = json!({"schema":"p4-real-userdata-independent-working-copy-v1","images":[]});
        let mut cold =
            json!({"schema":"pocket4-original-data-cold-compatibility-clone-v1","rows":[]});
        for (index, name) in IMAGES.iter().enumerate() {
            let prior = as_f9(&original.members[*name].identity);
            let clone = json!([10, 20 + index, 33152, 0, 0, 1, 4096, 50, 60]);
            let source = format!("/retained-clone/{name}");
            copy["images"].as_array_mut().unwrap().push(json!({"name":name,"working_path":format!("{WORKING}/{name}"),
                "source_path":source,"source_f9_before":clone,"source_f9_after":clone,
                "working_identity":copy_identity(&working.members[*name].identity),"sha256":"a".repeat(64)}));
            cold["rows"].as_array_mut().unwrap().push(json!({"role":if index==0{"data"}else{"metadata"},
                "source_path":format!("{ORIGINAL}/{name}"),"clone_path":source,"clone_f9":clone,
                "source_f9_before":prior,"source_f9_after":prior,"bytes":4096,"sha256":"a".repeat(64)}));
        }
        lineage(&copy, &cold, original, working).unwrap();
        // A structurally correct private fixture is never the admitted real pair.
        assert!(admitted_lineage(&copy, &cold, original, working).is_err());
        for mutation in 0..6 {
            let mut c = copy.clone();
            let mut p = cold.clone();
            match mutation {
                0 => p["rows"][0]["source_f9_after"][8] = json!(0),
                1 => c["images"][1]["working_identity"]["inode"] = json!(1),
                2 => c["images"][0]["source_f9_before"][1] = json!(1),
                3 => c["images"][0]["sha256"] = json!("b".repeat(64)),
                4 => p["rows"][1]["source_path"] = json!("/different/data.img"),
                _ => {
                    c["images"].as_array_mut().unwrap().reverse();
                }
            }
            assert!(lineage(&c, &p, original, working).is_err());
        }
    }
}
