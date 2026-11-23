//! A complete normal product is the unit of image delivery.
//!
//! This module binds normal build inputs, installed files and complete partition
//! images. It does not qualify Android execution, signing, CVE semantics or a
//! different source release. In particular, a vendor-only build has no fallback
//! to an older system image on this path.
#[path = "coherent_official_base.rs"]
pub(crate) mod official_base;
#[path = "coherent_readiness.rs"]
pub(crate) mod readiness;
#[path = "coherent_system_ext.rs"]
pub(crate) mod system_ext;

use crate::util::*;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File, OpenOptions},
    io::{Read, Seek, SeekFrom, Write},
    os::unix::{
        ffi::OsStrExt,
        fs::{MetadataExt, OpenOptionsExt},
    },
    path::{Component, Path, PathBuf},
    process::{Command, Stdio},
};

#[path = "coherent_resources.rs"]
mod resources;

#[path = "coherent_product.rs"]
pub(crate) mod configuration;

pub(crate) const INPUTS: &str = "droidloom-coherent-product-inputs.json";
pub(crate) const NORMAL: &str = "droidloom-coherent-product-normal-result.json";
pub(crate) const PARTITIONS: [&str; 4] = ["system", "system_ext", "product", "vendor"];
pub(crate) const PROFILING_APEX_MEMBERS: [&str; 4] = [
    "etc/classpaths/bootclasspath.pb",
    "etc/classpaths/systemserverclasspath.pb",
    "javalib/framework-profiling.jar",
    "javalib/service-profiling.jar",
];
pub(crate) const IMAGE_TARGETS: [&str; 4] = [
    "systemimage",
    "system_extimage",
    "productimage",
    "vendorimage",
];
const PRODUCT: &str = "droidloom_x86_64";
const MAX_JSON: u64 = 64 * 1024 * 1024;
const MAX_IMAGE: u64 = 16 * 1024 * 1024 * 1024;
const MAX_MEMBERS: usize = 200_000;
const FULL_INPUT_SCHEMA: &str = "droidloom-production-full653-inputs-v1";
const FULL_SOURCE_SHA: &str = crate::android::PRODUCTION_SOURCE_LOCK_SHA;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct FileRef {
    path: PathBuf,
    bytes: u64,
    sha256: String,
    identity: [u64; 9],
}

fn identity(m: &fs::Metadata) -> Result<[u64; 9]> {
    let mtime: u64 =
        (i128::from(m.mtime()) * 1_000_000_000 + i128::from(m.mtime_nsec())).try_into()?;
    let ctime: u64 =
        (i128::from(m.ctime()) * 1_000_000_000 + i128::from(m.ctime_nsec())).try_into()?;
    Ok([
        m.dev(),
        m.ino(),
        u64::from(m.mode()),
        u64::from(m.uid()),
        u64::from(m.gid()),
        m.nlink(),
        m.len(),
        mtime,
        ctime,
    ])
}

fn ordinary_absolute(path: &Path, directory: bool) -> Result<()> {
    resources::checkpoint()?;
    let raw = path.as_os_str().as_bytes();
    if !path.is_absolute()
        || (raw != b"/"
            && raw[1..]
                .split(|b| *b == b'/')
                .any(|part| part.is_empty() || part == b"." || part == b".."))
    {
        return fail("coherent product paths must be absolute and unaliased");
    }
    for parent in path.ancestors().skip(usize::from(!directory)) {
        let m = fs::symlink_metadata(parent)?;
        if !m.is_dir() || m.file_type().is_symlink() {
            return fail("coherent product parents must be ordinary directories");
        }
    }
    resources::checkpoint()
}

fn pin(path: &Path, limit: u64) -> Result<FileRef> {
    ordinary_absolute(path, false)?;
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
        .open(path)?;
    let before = file.metadata()?;
    if !before.is_file() || before.nlink() != 1 || before.len() > limit {
        return fail(format!(
            "expected bounded single-link product file: {}",
            path.display()
        ));
    }
    let mut state = Sha256::new();
    let mut buffer = vec![0u8; 1024 * 1024];
    let mut count = 0u64;
    loop {
        resources::checkpoint()?;
        let n = file.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        count = count
            .checked_add(n as u64)
            .ok_or("product file length overflow")?;
        if count > before.len() {
            return fail("product file grew while hashing");
        }
        state.update(&buffer[..n]);
    }
    resources::checkpoint()?;
    let before_id = identity(&before)?;
    if count != before.len()
        || identity(&file.metadata()?)? != before_id
        || identity(&fs::symlink_metadata(path)?)? != before_id
    {
        return fail("product file changed while being bound");
    }
    ordinary_absolute(path, false)?;
    Ok(FileRef {
        path: path.to_owned(),
        bytes: count,
        sha256: hex::encode(state.finalize()),
        identity: before_id,
    })
}

fn recheck(reference: &FileRef, limit: u64) -> Result<()> {
    if pin(&reference.path, limit)? != *reference {
        return fail("coherent product original changed or was replaced");
    }
    Ok(())
}

fn bound_body(reference: &FileRef, limit: u64) -> Result<Vec<u8>> {
    if reference.bytes > limit {
        return fail("bounded original body exceeds its limit");
    }
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
        .open(&reference.path)?;
    if identity(&file.metadata()?)? != reference.identity {
        return fail("original body was replaced before reading");
    }
    let mut body = Vec::new();
    let cap = reference
        .bytes
        .checked_add(1)
        .ok_or("body length overflow")?;
    let mut buffer = [0u8; 64 * 1024];
    while (body.len() as u64) < cap {
        resources::checkpoint()?;
        let limit = usize::try_from((cap - body.len() as u64).min(buffer.len() as u64))?;
        let n = file.read(&mut buffer[..limit])?;
        if n == 0 {
            break;
        }
        body.extend_from_slice(&buffer[..n]);
    }
    resources::checkpoint()?;
    if body.len() as u64 != reference.bytes
        || hex::encode(Sha256::digest(&body)) != reference.sha256
        || identity(&file.metadata()?)? != reference.identity
        || identity(&fs::symlink_metadata(&reference.path)?)? != reference.identity
    {
        return fail("original body changed while being read");
    }
    Ok(body)
}

fn bound_header(reference: &FileRef, length: usize) -> Result<Vec<u8>> {
    resources::checkpoint()?;
    if length as u64 > reference.bytes {
        return fail("truncated original header");
    }
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
        .open(&reference.path)?;
    if identity(&file.metadata()?)? != reference.identity {
        return fail("original header inode changed");
    }
    let mut header = vec![0; length];
    file.read_exact(&mut header)?;
    resources::checkpoint()?;
    if identity(&file.metadata()?)? != reference.identity
        || identity(&fs::symlink_metadata(&reference.path)?)? != reference.identity
    {
        return fail("original header changed while being read");
    }
    Ok(header)
}

fn read_json(path: &Path) -> Result<(FileRef, Value)> {
    let reference = pin(path, MAX_JSON)?;
    let body = bound_body(&reference, MAX_JSON)?;
    if body.len() as u64 != reference.bytes
        || hex::encode(Sha256::digest(&body)) != reference.sha256
    {
        return fail("coherent JSON changed between binding and parsing");
    }
    let value = serde_json::from_slice(&body)?;
    recheck(&reference, MAX_JSON)?;
    Ok((reference, value))
}

fn save_new(path: &Path, value: &impl Serialize) -> Result<FileRef> {
    ordinary_absolute(path, false)?;
    let body = serde_json::to_vec_pretty(value)?;
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o444)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)?;
    file.write_all(&body)?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    File::open(path.parent().ok_or("product receipt has no parent")?)?.sync_all()?;
    pin(path, MAX_JSON)
}

pub(crate) fn validate_full_targets(targets: &[String]) -> Result<()> {
    let unique: BTreeSet<_> = targets.iter().map(String::as_str).collect();
    if unique.len() != targets.len()
        || targets.is_empty()
        || !IMAGE_TARGETS
            .iter()
            .chain(
                [
                    "services",
                    "framework-minus-apex",
                    "telephony-common",
                    "framework-res",
                    "module-info",
                    "IntentResolver",
                    "Settings",
                    "TelephonyProvider",
                    "DroidloomSystemUI",
                    "DroidloomIME",
                    "DroidloomHome",
                    "com.android.media.swcodec",
                    "com.android.art",
                    "com.android.virt",
                    "com.android.tethering",
                    "com.android.profiling",
                    "service-profiling",
                    "libfs_mgr",
                    "apexd",
                    "droidloom-native-bridge",
                    "ExternalStorageProvider",
                    "libandroidfw",
                    "libhwui",
                ]
                .iter(),
            )
            .all(|name| unique.contains(name))
    {
        return fail(
            "complete product request must include all images and actual runtime consumers",
        );
    }
    Ok(())
}

fn build_properties(path: &Path, partition: &str) -> Result<(FileRef, BTreeMap<String, String>)> {
    let reference = pin(path, 1024 * 1024)?;
    let text = String::from_utf8(bound_body(&reference, 1024 * 1024)?)?;
    let mut values = BTreeMap::new();
    for line in text
        .lines()
        .map(str::trim)
        .filter(|s| !s.is_empty() && !s.starts_with('#'))
    {
        let (key, value) = line
            .split_once('=')
            .ok_or("malformed actual build property")?;
        if values.insert(key.to_string(), value.to_string()).is_some() {
            return fail("duplicate actual build property");
        }
    }
    let prefix = format!("ro.{partition}.build");
    if values.get(&format!("{prefix}.type")).map(String::as_str) != Some("user") {
        return fail("actual complete partition must be a user build");
    }
    recheck(&reference, 1024 * 1024)?;
    Ok((reference, values))
}

// Original and extracted identities are separate: equal contents do not make
// an extracted inode the original output inode.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Member {
    kind: String,
    bytes: u64,
    sha256: Option<String>,
    link: Option<PathBuf>,
    identity: [u64; 9],
}
type Members = BTreeMap<PathBuf, Member>;

fn member_content_equal(a: &Member, b: &Member) -> bool {
    a.kind == b.kind && a.bytes == b.bytes && a.sha256 == b.sha256 && a.link == b.link
}

fn inventory(root: &Path, hash_bodies: bool) -> Result<Members> {
    ordinary_absolute(root, true)?;
    let mut pending = vec![PathBuf::new()];
    let mut members = BTreeMap::new();
    let mut total = 0u64;
    while let Some(relative) = pending.pop() {
        resources::checkpoint()?;
        if members.len() >= MAX_MEMBERS {
            return fail("product tree exceeds its member bound");
        }
        let path = root.join(&relative);
        let m = fs::symlink_metadata(&path)?;
        let before = identity(&m)?;
        let row = if m.file_type().is_symlink() {
            let target = fs::read_link(&path)?;
            if target.as_os_str().len() > 4096 {
                return fail("unbounded product symlink");
            }
            Member {
                kind: "symlink".into(),
                bytes: m.len(),
                sha256: None,
                link: Some(target),
                identity: before,
            }
        } else if m.is_dir() {
            let mut children = Vec::new();
            for entry in fs::read_dir(&path)? {
                resources::checkpoint()?;
                if children
                    .len()
                    .checked_add(members.len())
                    .and_then(|n| n.checked_add(pending.len()))
                    .is_none_or(|n| n >= MAX_MEMBERS)
                {
                    return fail("product directory exceeds its pending member bound");
                }
                children.push(entry?);
            }
            children.sort_by_key(|entry| entry.file_name());
            if children
                .len()
                .checked_add(members.len())
                .and_then(|n| n.checked_add(pending.len()))
                .is_none_or(|n| n > MAX_MEMBERS)
            {
                return fail("product tree exceeds its pending member bound");
            }
            pending.extend(
                children
                    .into_iter()
                    .rev()
                    .map(|entry| relative.join(entry.file_name())),
            );
            Member {
                kind: "directory".into(),
                bytes: 0,
                sha256: None,
                link: None,
                identity: before,
            }
        } else if m.is_file() {
            total = total
                .checked_add(m.len())
                .ok_or("product tree byte overflow")?;
            if total > resources::MAX_TREE {
                return fail("product tree exceeds its byte bound");
            }
            let body = if hash_bodies {
                Some(pin(&path, MAX_IMAGE)?.sha256)
            } else {
                None
            };
            Member {
                kind: "file".into(),
                bytes: m.len(),
                sha256: body,
                link: None,
                identity: before,
            }
        } else {
            return fail("installed product tree contains a special object");
        };
        if identity(&fs::symlink_metadata(&path)?)? != before {
            return fail("product tree member changed during traversal");
        }
        if members.insert(relative, row).is_some() {
            return fail("duplicate product member");
        }
    }
    Ok(members)
}

fn unchanged_tree(root: &Path, before: &Members) -> Result<()> {
    let after = inventory(root, false)?;
    if before.len() != after.len()
        || before.iter().any(|(name, old)| {
            after.get(name).is_none_or(|now| {
                old.identity != now.identity
                    || old.kind != now.kind
                    || old.bytes != now.bytes
                    || old.link != now.link
            })
        })
    {
        return fail("product tree changed or was replaced after complete binding");
    }
    Ok(())
}

fn compare_members(installed: &Members, image: &Members) -> Result<()> {
    if installed.len() != image.len()
        || installed.iter().any(|(name, old)| {
            image
                .get(name)
                .is_none_or(|now| !member_content_equal(old, now))
        })
    {
        return fail("normal partition contents differ from this product's installed tree");
    }
    Ok(())
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct BuildIdentity {
    id: String,
    uuid: String,
    incremental: String,
    sdk: String,
    sdk_full: String,
    release: String,
    variant: String,
}

fn property_identity(values: &BTreeMap<String, String>, partition: &str) -> Result<BuildIdentity> {
    let property = |suffix: &str| -> Result<String> {
        values
            .get(&format!("ro.{partition}.build.{suffix}"))
            .filter(|value| !value.is_empty())
            .cloned()
            .ok_or_else(|| format!("missing actual {partition} build property {suffix}").into())
    };
    let result = BuildIdentity {
        id: property("id")?,
        uuid: property("uuid")?,
        incremental: property("version.incremental")?,
        sdk: property("version.sdk")?,
        sdk_full: property("version.sdk_full")?,
        release: property("version.release")?,
        variant: property("type")?,
    };
    if result.variant != "user" {
        return fail("complete product must retain the strict user variant");
    }
    Ok(result)
}

fn property_path(product: &Path, partition: &str) -> PathBuf {
    product
        .join(partition)
        .join(if matches!(partition, "product" | "system_ext") {
            "etc/build.prop"
        } else {
            "build.prop"
        })
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct RecipeEvidence {
    relative: PathBuf,
    bytes: u64,
    sha256: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct ReleaseMap {
    schema: String,
    source_lock_sha256: String,
    selected_gsi_lock_sha256: String,
    selected_build_id: String,
    source_build_id: String,
    target_product: String,
    target_release: String,
    source_identity_evidence: RecipeEvidence,
    art_apex_abi_evidence: RecipeEvidence,
}

// Decode the identity fields from the same bounded bytes as the selected lock
// hash. The remaining CI fields use the existing image producer's lock type;
// other top-level recipe fields remain covered by the whole-file hash.
#[derive(Deserialize)]
struct SelectedLockIdentity {
    schema_version: u32,
    architecture: String,
    aosp_ci_base: droidloom_image::CiBaseLock,
}

fn require_selected_lock_identity(body: &[u8], expected_build_id: &str) -> Result<()> {
    // Deserialize the original body, not a Value: duplicate identity fields must
    // fail even when a last-value-wins JSON view would match the expected build.
    let selected: SelectedLockIdentity = serde_json::from_slice(body)?;
    if selected.schema_version != 1
        || selected.architecture != "x86_64"
        || selected.aosp_ci_base.cpu_abi != "x86_64"
        || selected.aosp_ci_base.build_id != expected_build_id
    {
        return fail("selected GSI lock body differs from the mapped build and architecture");
    }
    Ok(())
}

// No such mapping is fabricated by this producer. It must be added to the
// reviewed recipe only after the source and ART/APEX ABI evidence exists.
// Matching an editable BUILD_ID string is not that evidence.
fn release_map(repo: &Path, source_lock: &FileRef) -> Result<(FileRef, ReleaseMap)> {
    let (record, raw) = read_json(
        &repo.join("android/manifest/source-runtime-coherence-x86_64.json"),
    )
    .map_err(|error| {
        format!("selected CP3A delivery lacks its exact source/ART/APEX identity input: {error}")
    })?;
    let map: ReleaseMap = serde_json::from_value(raw)?;
    let selected = pin(
        &repo.join("android/manifest/source-lock-x86_64.json"),
        MAX_JSON,
    )?;
    if map.schema != "droidloom-source-runtime-coherence-v1"
        || map.source_lock_sha256 != source_lock.sha256
        || map.selected_gsi_lock_sha256 != selected.sha256
        || map.selected_build_id != "CP3A.260905.010"
        || map.source_build_id != map.selected_build_id
        || map.target_product != PRODUCT
        || map.target_release.is_empty()
    {
        return fail(
            "source/runtime mapping differs from the selected release and actual source lock",
        );
    }
    require_selected_lock_identity(&bound_body(&selected, MAX_JSON)?, &map.selected_build_id)?;
    for evidence in [&map.source_identity_evidence, &map.art_apex_abi_evidence] {
        if evidence.relative.is_absolute()
            || evidence
                .relative
                .components()
                .any(|part| !matches!(part, Component::Normal(_)))
            || !evidence
                .relative
                .starts_with("android/manifest/runtime-coherence-evidence")
        {
            return fail("identity evidence must be a confined reviewed recipe member");
        }
        let actual = pin(&repo.join(&evidence.relative), MAX_JSON)?;
        if actual.bytes == 0 || actual.bytes != evidence.bytes || actual.sha256 != evidence.sha256 {
            return fail("source/runtime identity evidence differs from its reviewed bytes");
        }
    }
    recheck(&selected, MAX_JSON)?;
    Ok((record, map))
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct BuildInputs {
    schema: String,
    source: PathBuf,
    out: PathBuf,
    product: PathBuf,
    source_lock: FileRef,
    source_manifest: FileRef,
    source_build_id: FileRef,
    image_builder: FileRef,
    source_receipt: FileRef,
    product_configuration: FileRef,
    release_map: FileRef,
    selected_release: ReleaseMap,
    release_evidence: Vec<FileRef>,
    requested_targets: Vec<String>,
    command_program: PathBuf,
    command_executable: FileRef,
    command_cwd: PathBuf,
    command_args: Vec<String>,
    command_environment: BTreeMap<String, Option<String>>,
}

pub(crate) struct SuccessfulBuild {
    inputs: BuildInputs,
    reference: FileRef,
    actual_command_environment: BTreeMap<String, Option<String>>,
}

fn recorded_environment(command: &Command) -> Result<BTreeMap<String, Option<String>>> {
    command
        .get_envs()
        .map(|(key, value)| {
            Ok((
                key.to_str()
                    .ok_or("non-UTF8 build environment key")?
                    .to_owned(),
                value
                    .map(|s| {
                        s.to_str()
                            .map(str::to_owned)
                            .ok_or("non-UTF8 build environment value")
                    })
                    .transpose()?,
            ))
        })
        .collect()
}

fn validate_full_source_header(original: &Value, requested_targets: &[String]) -> Result<()> {
    if original["schema"] != FULL_INPUT_SCHEMA
        || original["source_lock"]["sha256"] != FULL_SOURCE_SHA
        || original["strict_allow_missing_dependencies"] != "false"
        || original["selinux_ignore_neverallows"] != "false"
        || original["requested_targets"] != json!(requested_targets)
    {
        return fail(
            "complete product needs the actual strict source/projection receipt and targets",
        );
    }
    Ok(())
}

/// Wrap only the real, strict complete-product command. Its successful return
/// produces an unforgeable-in-the-call-chain token; a parsed receipt or a vendor
/// command cannot create this token. The existing source verifier and projection
/// execute before this function, and their complete input receipt is retained.
pub(crate) fn run_normal(
    repo: &Path,
    source: &Path,
    out: &Path,
    work: &Path,
    product: &str,
    targets: &[&str],
    command: &mut Command,
) -> Result<SuccessfulBuild> {
    if product != PRODUCT {
        return fail("unexpected complete product");
    }
    for path in [repo, source, out] {
        ordinary_absolute(path, true)?;
    }
    let requested_targets: Vec<String> = targets.iter().map(|s| (*s).to_string()).collect();
    validate_full_targets(&requested_targets)?;
    let (source_receipt, original) =
        read_json(&out.join("droidloom-production-full653-inputs.json"))?;
    validate_full_source_header(&original, &requested_targets)?;
    let source_lock = pin(
        &repo.join(crate::android::PRODUCTION_SOURCE_LOCK_PATH),
        MAX_JSON,
    )?;
    if source_lock.sha256 != FULL_SOURCE_SHA {
        return fail("unrecognized full source profile");
    }
    let source_manifest = pin(&source.join(".droidloom-source-manifest.json"), MAX_JSON)?;
    let (release_ref, selected_release) = release_map(repo, &source_lock)?;
    if original["source_lock"]["path"] != json!(source_lock.path)
        || original["source_lock"]["bytes"] != source_lock.bytes
        || original["source_manifest"]["path"] != json!(source_manifest.path)
        || original["source_manifest"]["sha256"] != source_manifest.sha256
    {
        return fail("normal input receipt has a different source lock or materialized manifest");
    }
    let source_build_id = pin(&source.join("build/make/core/build_id.mk"), 1024 * 1024)?;
    let build_id_body = String::from_utf8(bound_body(&source_build_id, 1024 * 1024)?)?;
    let declarations: Vec<_> = build_id_body
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .filter_map(|line| line.strip_prefix("BUILD_ID").map(str::trim))
        .map(|tail| {
            tail.strip_prefix(":=")
                .or_else(|| tail.strip_prefix('='))
                .map(str::trim)
                .map(str::to_owned)
                .ok_or("unsupported BUILD_ID source declaration")
        })
        .collect::<std::result::Result<_, _>>()?;
    if declarations != [selected_release.source_build_id.clone()] {
        return fail(
            "the pinned source BUILD_ID does not match the selected CP3A identity; no relabeling is allowed",
        );
    }
    let image_builder = pin(
        &source.join("build/make/tools/releasetools/build_image.py"),
        1024 * 1024,
    )?;
    if image_builder.sha256 != "e8c387d9887b07219cbc8b30076195b56d4a3f304006367b562bea861075ef6a" {
        return fail("normal filesystem-root merge producer differs from the reviewed source");
    }
    let release_evidence: Vec<_> = [
        &selected_release.source_identity_evidence,
        &selected_release.art_apex_abi_evidence,
    ]
    .into_iter()
    .map(|e| pin(&repo.join(&e.relative), MAX_JSON))
    .collect::<Result<_>>()?;
    let command_args: Vec<String> = command
        .get_args()
        .map(|s| {
            s.to_str()
                .map(str::to_owned)
                .ok_or("non-UTF8 normal product argument")
        })
        .collect::<std::result::Result<_, _>>()?;
    if Path::new(command.get_program()) != out.join("soong_ui")
        || command.get_current_dir() != Some(source)
    {
        return fail(
            "complete product must use the actual bootstrapped Soong command and source cwd",
        );
    }
    let command_executable = pin(&out.join("soong_ui"), 512 * 1024 * 1024)?;
    if command_executable.identity[2] & 0o111 == 0 {
        return fail("Soong command is not executable");
    }
    let command_environment = recorded_environment(command)?;
    for (key, expected) in [
        ("TARGET_PRODUCT", product),
        ("TARGET_BUILD_VARIANT", "user"),
        ("ALLOW_MISSING_DEPENDENCIES", "false"),
        ("SELINUX_IGNORE_NEVERALLOWS", "false"),
        ("TARGET_RELEASE", selected_release.target_release.as_str()),
    ] {
        if command_environment.get(key).and_then(Option::as_deref) != Some(expected) {
            return fail(format!(
                "complete normal command has no exact {key} binding"
            ));
        }
    }
    for (key, expected) in [("TOP", source), ("OUT_DIR", out), ("ORIGINAL_PWD", source)] {
        if command_environment
            .get(key)
            .and_then(Option::as_deref)
            .map(Path::new)
            != Some(expected)
        {
            return fail("complete normal command has a foreign source or output directory");
        }
    }
    if ["BUILD_ID", "BUILD_NUMBER"].iter().any(|key| {
        command_environment.get(*key).is_some_and(Option::is_some)
            || (!command_environment.contains_key(*key) && std::env::var_os(key).is_some())
    }) || !command_args.iter().any(|arg| arg == "--make-mode")
        || !requested_targets
            .iter()
            .all(|target| command_args.iter().any(|arg| arg == target))
    {
        return fail("complete product command must build every image without release relabeling");
    }
    let product_configuration =
        configuration::input_receipt(repo, source, out, work, &original["effective_projection"])?;
    let inputs = BuildInputs {
        schema: "droidloom-coherent-product-inputs-v2".into(),
        source: source.to_owned(),
        out: out.to_owned(),
        product: out.join("target/product").join(product),
        source_lock,
        source_manifest,
        source_build_id,
        image_builder,
        source_receipt,
        product_configuration,
        release_map: release_ref,
        selected_release,
        release_evidence,
        requested_targets,
        command_program: PathBuf::from(command.get_program()),
        command_executable,
        command_cwd: source.to_owned(),
        command_args,
        command_environment,
    };
    let reference = save_new(&out.join(INPUTS), &inputs)?;
    run_build(command)?;
    let actual_command_environment = recorded_environment(command)?;
    configuration::verify_live(&inputs.product_configuration, repo, source, out)?;
    for original in [
        &inputs.source_lock,
        &inputs.source_manifest,
        &inputs.source_build_id,
        &inputs.image_builder,
        &inputs.source_receipt,
        &inputs.product_configuration,
        &inputs.release_map,
    ]
    .into_iter()
    .chain(inputs.release_evidence.iter())
    {
        recheck(original, MAX_JSON)?;
    }
    recheck(&reference, MAX_JSON)?;
    recheck(&inputs.command_executable, 512 * 1024 * 1024)?;
    Ok(SuccessfulBuild {
        inputs,
        reference,
        actual_command_environment,
    })
}

const INSTALLED: &[(&str, &str, &str)] = &[
    (
        "services",
        "frameworks/base/services",
        "system/framework/services.jar",
    ),
    (
        "framework-minus-apex",
        "frameworks/base",
        "system/framework/framework.jar",
    ),
    (
        "telephony-common",
        "frameworks/opt/telephony",
        "system/framework/telephony-common.jar",
    ),
    (
        "framework-res",
        "frameworks/base/core/res",
        "system/framework/framework-res.apk",
    ),
    (
        "IntentResolver",
        "packages/modules/IntentResolver",
        "system/priv-app/IntentResolver/IntentResolver.apk",
    ),
    (
        "Settings",
        "packages/apps/Settings",
        "system_ext/priv-app/Settings/Settings.apk",
    ),
    (
        "TelephonyProvider",
        "packages/providers/TelephonyProvider",
        "system/priv-app/TelephonyProvider/TelephonyProvider.apk",
    ),
    (
        "DroidloomSystemUI",
        "vendor/droidloom",
        "system_ext/priv-app/DroidloomSystemUI/DroidloomSystemUI.apk",
    ),
    (
        "DroidloomIME",
        "vendor/droidloom",
        "system/app/DroidloomIME/DroidloomIME.apk",
    ),
    (
        "DroidloomHome",
        "vendor/droidloom",
        "system/app/DroidloomHome/DroidloomHome.apk",
    ),
    ("libfs_mgr", "system/fs/fs_mgr", "system/lib64/libfs_mgr.so"),
    ("apexd", "system/apex/apexd", "system/bin/apexd"),
    (
        "ExternalStorageProvider",
        "frameworks/base/packages/ExternalStorageProvider",
        "system/priv-app/ExternalStorageProvider/ExternalStorageProvider.apk",
    ),
    // The pinned libandroidfw Android.bp statically links external/libpng.
    (
        "libandroidfw",
        "frameworks/base/libs/androidfw",
        "system/lib64/libandroidfw.so",
    ),
    (
        "libhwui",
        "frameworks/base/libs/hwui",
        "system/lib64/libhwui.so",
    ),
];

fn installed_file(
    info: &Value,
    product: &Path,
    module: &str,
    provider: &str,
    relative: &str,
) -> Result<FileRef> {
    let row = info
        .get(module)
        .ok_or("required runtime module absent from module-info")?;
    if row["path"] != json!([provider]) {
        return fail("runtime module has a foreign or ambiguous source provider");
    }
    let installed = row["installed"]
        .as_array()
        .ok_or("runtime module has no installed paths")?;
    let expected = product.join(relative);
    let mut seen = BTreeSet::new();
    let mut count = 0;
    for value in installed {
        let path = Path::new(value.as_str().ok_or("invalid installed module path")?);
        if !path.is_absolute()
            || path
                .components()
                .any(|c| matches!(c, Component::ParentDir | Component::CurDir))
            || !seen.insert(path.to_path_buf())
        {
            return fail("aliased or duplicate installed module path");
        }
        if path == expected {
            count += 1;
        }
    }
    if count != 1 {
        return fail(format!(
            "normal {module} does not install its selected runtime artifact"
        ));
    }
    let reference = pin(&expected, 2 * 1024 * 1024 * 1024)?;
    if reference.bytes == 0 {
        return fail("empty installed runtime artifact");
    }
    Ok(reference)
}

fn reader_tool(name: &str) -> Result<FileRef> {
    let path = std::env::var_os("PATH").ok_or("image reader PATH is absent")?;
    for directory in std::env::split_paths(&path) {
        if !directory.is_absolute() {
            continue;
        }
        let candidate = directory.join(name);
        if candidate.is_file() {
            let actual = fs::canonicalize(candidate)?;
            let reference = pin(&actual, 256 * 1024 * 1024)?;
            if reference.identity[2] & 0o111 == 0 {
                return fail("image reader is not executable");
            }
            return Ok(reference);
        }
    }
    fail(format!("normal image reader unavailable: {name}"))
}

fn checked_tool(tool: &FileRef, command: &mut Command) -> Result<()> {
    recheck(tool, 256 * 1024 * 1024)?;
    let result = resources::run_reader(command);
    let unchanged = recheck(tool, 256 * 1024 * 1024);
    match (result, unchanged) {
        (Err(error), Err(check)) => fail(format!("{error}; image reader binding recheck: {check}")),
        (Err(error), _) => Err(error),
        (Ok(()), check) => check,
    }
}

fn filesystem_tree(image: &FileRef, destination: &Path) -> Result<FileRef> {
    let header = bound_header(image, 1082)?;
    fs::create_dir(destination)?;
    let tool = if header[1024..1028] == [0xe2, 0xe1, 0xf5, 0xe0] {
        let tool = reader_tool("fsck.erofs")?;
        checked_tool(
            &tool,
            Command::new(&tool.path)
                .arg(format!("--extract={}", destination.display()))
                .arg(&image.path),
        )?;
        tool
    } else if header[1080..1082] == [0x53, 0xef] {
        let target = destination
            .to_str()
            .ok_or("non-UTF8 image extraction path")?;
        if !target
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"/._-".contains(&b))
        {
            return fail("debugfs readback destination contains command syntax");
        }
        let tool = reader_tool("debugfs")?;
        // No -w: this command only reads the original image. Writes go to the
        // newly created owned extraction directory.
        checked_tool(
            &tool,
            Command::new(&tool.path)
                .args(["-R", &format!("rdump / {target}")])
                .arg(&image.path),
        )?;
        tool
    } else {
        return fail("complete delivery requires a decoded normal EROFS/ext4 image");
    };
    recheck(image, MAX_IMAGE)?;
    Ok(tool)
}

/// Inspect the delivered raw image with the same read-only format detector used
/// by normal product verification. No image bytes are changed or mounted.
pub(crate) fn extract_normal_filesystem(image: &Path, destination: &Path) -> Result<()> {
    let _scope = resources::Scope::writing(
        &resources::output_ancestor(destination)?,
        resources::MAX_TREE,
    )?;
    let original = pin(image, MAX_IMAGE)?;
    filesystem_tree(&original, destination)?;
    recheck(&original, MAX_IMAGE)
}

/// Bind the two installed graphics HAL ELFs to the bytes and labels in vendor.img.
pub(crate) fn verify_vendor_graphics_hal_entries(
    product_out: &Path,
) -> Result<BTreeMap<String, String>> {
    let image = product_out.join("vendor.img");
    let _scope = resources::Scope::writing(product_out, resources::GIB)?;
    let temp = tempfile::Builder::new()
        .prefix("graphics-hal-readback-")
        .tempdir_in(product_out)?;
    let original = pin(&image, MAX_IMAGE)?;
    let (decoded, _) = decode_image(&original, &temp.path().join("vendor.raw.img"))?;
    let debugfs = reader_tool("debugfs")?;
    let mut observed = BTreeMap::new();
    for (index, (name, label)) in [
        (
            "android.hardware.graphics.allocator-service.minigbm",
            "u:object_r:hal_graphics_allocator_default_exec:s0",
        ),
        (
            "android.hardware.graphics.composer3-service.droidloom",
            "u:object_r:hal_graphics_composer_default_exec:s0",
        ),
    ]
    .into_iter()
    .enumerate()
    {
        let inside = format!("/bin/hw/{name}");
        let contents = format!("hal-{index}");
        let attribute = format!("label-{index}");
        for command in [
            format!("dump {inside} {contents}"),
            format!("ea_get -f {attribute} {inside} security.selinux"),
        ] {
            checked_tool(
                &debugfs,
                Command::new(&debugfs.path)
                    .current_dir(temp.path())
                    .args(["-R", &command])
                    .arg(&decoded.path),
            )?;
        }
        let installed = pin(&product_out.join("vendor/bin/hw").join(name), MAX_IMAGE)?;
        let delivered = pin(&temp.path().join(contents), MAX_IMAGE)?;
        let header = bound_header(&delivered, 20)?;
        if !header.starts_with(b"\x7fELF\x02\x01")
            || header[18..20] != 62u16.to_le_bytes()
            || delivered.sha256 != installed.sha256
        {
            return fail(format!(
                "vendor graphics HAL is not the installed x86_64 ELF: {inside}"
            ));
        }
        let actual = fs::read(temp.path().join(attribute))?;
        if actual.strip_suffix(&[0]) != Some(label.as_bytes()) {
            return fail(format!(
                "vendor graphics HAL has the wrong SELinux entrypoint: {inside}"
            ));
        }
        observed.insert(format!("/vendor{inside}"), label.to_owned());
    }
    recheck(&decoded, MAX_IMAGE)?;
    recheck(&original, MAX_IMAGE)?;
    Ok(observed)
}

fn image_root<'a>(partition: &str, extracted: &'a Path) -> Result<PathBuf> {
    if partition != "system" {
        return Ok(extracted.to_owned());
    }
    let direct = extracted.join("build.prop").is_file();
    let nested = extracted.join("system/build.prop").is_file();
    match (direct, nested) {
        (true, false) => Ok(extracted.to_owned()),
        (false, true) => Ok(extracted.join("system")),
        _ => fail("system image has an absent or ambiguous normal system root"),
    }
}

fn exclude_empty_fs_directory(members: &mut Members) -> Result<()> {
    let name = Path::new("lost+found");
    if let Some(row) = members.get(name) {
        if row.kind != "directory" || members.keys().any(|p| p != name && p.starts_with(name)) {
            return fail("unexpected nonempty filesystem-generated directory");
        }
        members.remove(name);
    }
    Ok(())
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Partition {
    name: String,
    image: FileRef,
    source_is_sparse: bool,
    delivered_bytes: u64,
    delivered_sha256: String,
    sparse_converter: Option<FileRef>,
    properties: FileRef,
    build_identity: BuildIdentity,
    installed_members: Members,
    system_root_members: Option<Members>,
    expected_image_members: Members,
    image_members: Members,
    image_content_root: String,
    reader: FileRef,
}

fn complete_partition(product: &Path, name: &str, scratch: &Path) -> Result<Partition> {
    resources::checkpoint()?;
    let temporary = tempfile::Builder::new()
        .prefix("partition-readback-")
        .tempdir_in(scratch)?;
    let scratch = temporary.path();
    let image = pin(&product.join(format!("{name}.img")), MAX_IMAGE)?;
    let (decoded, sparse_converter) =
        decode_image(&image, &scratch.join(format!("{name}.raw.img")))?;
    let (properties, values) = build_properties(&property_path(product, name), name)?;
    let build_identity = property_identity(&values, name)?;
    let installed_members = inventory(&product.join(name), true)?;
    let system_root_members = if name == "system" {
        Some(inventory(&product.join("root"), true)?)
    } else {
        None
    };
    let expected_image_members =
        expected_partition_members(name, &installed_members, system_root_members.as_ref())?;
    let extracted = scratch.join(name);
    let reader = filesystem_tree(&decoded, &extracted)?;
    let content_root = image_root(name, &extracted)?;
    if name == "system" && content_root != extracted.join("system") {
        return fail(
            "normal system image does not use the pinned build_image.py root/system layout",
        );
    }
    let all_image_members = inventory(&extracted, true)?;
    let mut image_members = all_image_members.clone();
    exclude_empty_fs_directory(&mut image_members)?;
    compare_members(&expected_image_members, &image_members)?;
    unchanged_tree(&product.join(name), &installed_members)?;
    if let Some(root) = &system_root_members {
        unchanged_tree(&product.join("root"), root)?;
    }
    unchanged_tree(&extracted, &all_image_members)?;
    let image_content_root = content_root
        .strip_prefix(&extracted)?
        .to_str()
        .ok_or("invalid image root")?
        .to_owned();
    recheck(&decoded, MAX_IMAGE)?;
    let partition = Partition {
        name: name.into(),
        source_is_sparse: sparse_converter.is_some(),
        delivered_bytes: decoded.bytes,
        delivered_sha256: decoded.sha256,
        sparse_converter,
        image,
        properties,
        build_identity,
        installed_members,
        system_root_members,
        expected_image_members,
        image_members,
        image_content_root,
        reader,
    };
    temporary.close()?;
    resources::checkpoint()?;
    Ok(partition)
}

fn expected_partition_members(
    name: &str,
    installed: &Members,
    root: Option<&Members>,
) -> Result<Members> {
    if name != "system" {
        if root.is_some() {
            return fail("only system.img has a normal root merge");
        }
        return Ok(installed.clone());
    }
    let root = root.ok_or("normal system image lacks its complete PRODUCT_OUT/root inventory")?;
    if root
        .get(Path::new("system"))
        .is_some_and(|m| m.kind != "directory")
    {
        return fail("normal root/system is not an ordinary directory before image assembly");
    }
    // Exact build/make/tools/releasetools/build_image.py semantics: copy root,
    // remove its system subtree, then copy the complete installed system tree.
    let mut result: Members = root
        .iter()
        .filter(|(p, _)| !p.starts_with("system"))
        .map(|(p, m)| (p.clone(), m.clone()))
        .collect();
    for (path, member) in installed {
        if result
            .insert(Path::new("system").join(path), member.clone())
            .is_some()
        {
            return fail("normal system merge has an ambiguous member");
        }
    }
    Ok(result)
}

fn decode_image(image: &FileRef, destination: &Path) -> Result<(FileRef, Option<FileRef>)> {
    recheck(image, MAX_IMAGE)?;
    let magic = bound_header(image, 4)?;
    if magic != [0x3a, 0xff, 0x26, 0xed] {
        return Ok((image.clone(), None));
    }
    // Conversion preserves the complete normal filesystem. Its new inode and
    // whole hash are recorded separately from the original sparse output.
    if destination.symlink_metadata().is_ok() {
        return fail("sparse conversion destination already exists");
    }
    let converter = reader_tool("simg2img")?;
    checked_tool(
        &converter,
        Command::new(&converter.path)
            .arg(&image.path)
            .arg(destination),
    )?;
    let decoded = pin(destination, MAX_IMAGE)?;
    if decoded.bytes == 0 {
        return fail("empty decoded normal partition");
    }
    recheck(image, MAX_IMAGE)?;
    Ok((decoded, Some(converter)))
}

fn unzip_member(archive: &FileRef, member: &str, destination: &Path) -> Result<FileRef> {
    use std::os::unix::process::CommandExt;
    let tool = reader_tool("unzip")?;
    recheck(archive, MAX_IMAGE)?;
    let expected_bytes = zip_member_size(&archive.path, member)?;
    let destination_file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(destination)?;
    let mut command = Command::new(&tool.path);
    command
        .args(["-p"])
        .arg(&archive.path)
        .arg(member)
        .stdout(Stdio::from(destination_file));
    let output_limit = libc::rlimit {
        rlim_cur: expected_bytes as libc::rlim_t,
        rlim_max: expected_bytes as libc::rlim_t,
    };
    // Only the fixed child receives the file bound. No allocation or lock is
    // performed between fork and exec; even a dishonest ZIP size cannot cause
    // the selected member to grow beyond its declared finite size.
    unsafe {
        command.pre_exec(move || {
            if libc::setrlimit(libc::RLIMIT_FSIZE, &output_limit) != 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
    checked_tool(&tool, &mut command)?;
    let result = pin(destination, MAX_IMAGE)?;
    if result.bytes != expected_bytes {
        return fail("selected APEX member differs from its complete ZIP directory");
    }
    recheck(archive, MAX_IMAGE)?;
    Ok(result)
}

// Read the bounded ZIP directory before extraction. A whole buffered `unzip -Z`
// stdout would not itself be a size guard. ZIP64 and multidisk are rejected.
fn zip_member_size(path: &Path, member: &str) -> Result<u64> {
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
        .open(path)?;
    let before = file.metadata()?;
    if !before.is_file() || before.nlink() != 1 || before.len() > MAX_IMAGE {
        return fail("APEX ZIP must be a bounded regular original");
    }
    resources::checkpoint()?;
    let before_id = identity(&before)?;
    let bytes = before.len();
    if bytes < 22 {
        return fail("truncated APEX ZIP");
    }
    let tail_len = bytes.min(22 + 65535) as usize;
    file.seek(SeekFrom::End(-(tail_len as i64)))?;
    let mut tail = vec![0; tail_len];
    file.read_exact(&mut tail)?;
    let u16_at = |b: &[u8], n: usize| u16::from_le_bytes([b[n], b[n + 1]]);
    let u32_at = |b: &[u8], n: usize| u32::from_le_bytes([b[n], b[n + 1], b[n + 2], b[n + 3]]);
    let candidates: Vec<_> = (0..=tail.len() - 22)
        .filter(|n| {
            tail[*n..*n + 4] == *b"PK\x05\x06"
                && *n + 22 + usize::from(u16_at(&tail[*n..], 20)) == tail.len()
        })
        .collect();
    if candidates.len() != 1 {
        return fail("ambiguous or absent APEX ZIP end record");
    }
    let end = &tail[candidates[0]..];
    let count = usize::from(u16_at(end, 10));
    let length = u64::from(u32_at(end, 12));
    let offset = u64::from(u32_at(end, 16));
    let end_offset = bytes - tail_len as u64 + candidates[0] as u64;
    if u16_at(end, 4) != 0
        || u16_at(end, 6) != 0
        || u16_at(end, 8) != u16_at(end, 10)
        || count == 0
        || count == 65535
        || length > 16 * 1024 * 1024
        || offset.checked_add(length) != Some(end_offset)
    {
        return fail("unbounded, ZIP64, multidisk or noncontiguous APEX ZIP directory");
    }
    file.seek(SeekFrom::Start(offset))?;
    let mut central = vec![0; usize::try_from(length)?];
    file.read_exact(&mut central)?;
    let mut cursor = 0usize;
    let mut selected = Vec::new();
    let mut names = BTreeSet::new();
    for _ in 0..count {
        let header = central
            .get(cursor..cursor.checked_add(46).ok_or("ZIP offset overflow")?)
            .ok_or("truncated APEX ZIP central header")?;
        if &header[..4] != b"PK\x01\x02" || u16_at(header, 34) != 0 {
            return fail("invalid APEX ZIP central header");
        }
        let name_len = usize::from(u16_at(header, 28));
        let next = cursor
            .checked_add(46)
            .and_then(|v| v.checked_add(name_len))
            .and_then(|v| v.checked_add(usize::from(u16_at(header, 30))))
            .and_then(|v| v.checked_add(usize::from(u16_at(header, 32))))
            .ok_or("ZIP offset overflow")?;
        if next > central.len() {
            return fail("truncated APEX ZIP central member");
        }
        let name = std::str::from_utf8(&central[cursor + 46..cursor + 46 + name_len])?;
        if name.len() > 4096 || !names.insert(name.to_owned()) {
            return fail("duplicate or unbounded APEX ZIP member name");
        }
        if name == member {
            let size = u64::from(u32_at(header, 24));
            if u16_at(header, 8) & 1 != 0
                || size == 0
                || size == u64::from(u32::MAX)
                || size > MAX_IMAGE
            {
                return fail("unsupported or empty selected APEX ZIP member");
            }
            selected.push(size);
        }
        cursor = next;
    }
    if cursor != central.len() || selected.len() != 1 {
        return fail("APEX ZIP must contain exactly one complete selected member");
    }
    if identity(&file.metadata()?)? != before_id
        || identity(&fs::symlink_metadata(path)?)? != before_id
    {
        return fail("APEX ZIP directory changed while reading");
    }
    resources::checkpoint()?;
    Ok(selected[0])
}

fn elf_needed(path: &Path) -> Result<BTreeSet<String>> {
    let reference = pin(path, 512 * 1024 * 1024)?;
    let body = bound_body(&reference, 512 * 1024 * 1024)?;
    if body.len() < 64
        || &body[..7] != b"\x7fELF\x02\x01\x01"
        || ![2, 3].contains(&u16::from_le_bytes(body[16..18].try_into()?))
        || u16::from_le_bytes(body[18..20].try_into()?) != 62
        || u32::from_le_bytes(body[20..24].try_into()?) != 1
        || u16::from_le_bytes(body[52..54].try_into()?) != 64
    {
        return fail("runtime consumer is not an x86_64 little-endian ELF64");
    }
    let u64_at = |offset: usize| -> Result<u64> {
        Ok(u64::from_le_bytes(
            body.get(offset..offset.checked_add(8).ok_or("ELF offset overflow")?)
                .ok_or("truncated ELF integer")?
                .try_into()?,
        ))
    };
    let phoff: usize = u64_at(32)?.try_into()?;
    let phsize = usize::from(u16::from_le_bytes(body[54..56].try_into()?));
    let phnum = usize::from(u16::from_le_bytes(body[56..58].try_into()?));
    if phsize != 56 || phnum == 0 || phnum > 128 {
        return fail("unbounded ELF program headers");
    }
    let mut loads = Vec::new();
    let mut dynamic = None;
    for n in 0..phnum {
        let offset = phoff
            .checked_add(n.checked_mul(phsize).ok_or("ELF offset overflow")?)
            .ok_or("ELF offset overflow")?;
        let header = body
            .get(offset..offset.checked_add(phsize).ok_or("ELF offset overflow")?)
            .ok_or("truncated ELF program header")?;
        let kind = u32::from_le_bytes(header[..4].try_into()?);
        let file_offset = u64_at(offset + 8)?;
        let virtual_address = u64_at(offset + 16)?;
        let bytes = u64_at(offset + 32)?;
        if file_offset
            .checked_add(bytes)
            .is_none_or(|end| end > body.len() as u64)
        {
            return fail("ELF segment escapes its complete file");
        }
        if kind == 1 {
            loads.push((virtual_address, file_offset, bytes));
        }
        if kind == 2 && dynamic.replace((file_offset, bytes)).is_some() {
            return fail("ambiguous ELF dynamic segment");
        }
    }
    let (offset, bytes) = dynamic.ok_or("runtime consumer has no dynamic segment")?;
    if bytes == 0 || bytes > 2 * 1024 * 1024 || bytes % 16 != 0 {
        return fail("invalid dynamic segment size");
    }
    let mut table = None;
    let mut size = None;
    let mut needed = Vec::new();
    let mut ended = false;
    for row in body[offset as usize..(offset + bytes) as usize].chunks_exact(16) {
        let tag = u64::from_le_bytes(row[..8].try_into()?);
        let value = u64::from_le_bytes(row[8..].try_into()?);
        match tag {
            0 => {
                ended = true;
                break;
            }
            1 => needed.push(value),
            5 if table.replace(value).is_some() => return fail("duplicate dynamic string table"),
            10 if size.replace(value).is_some() => return fail("duplicate dynamic string size"),
            _ => (),
        }
    }
    if !ended || needed.len() > 256 {
        return fail("unterminated or unbounded dynamic dependencies");
    }
    let table = table.ok_or("missing dynamic string table")?;
    let size = size
        .filter(|n| *n > 0 && *n <= 1024 * 1024)
        .ok_or("unbounded dynamic string table")?;
    let offsets: Vec<_> = loads
        .iter()
        .filter_map(|(va, start, bytes)| {
            table
                .checked_sub(*va)
                .filter(|delta| delta.checked_add(size).is_some_and(|n| n <= *bytes))
                .and_then(|delta| start.checked_add(delta))
        })
        .collect();
    if offsets.len() != 1 {
        return fail("ambiguous ELF virtual-to-file string mapping");
    }
    let strings = &body[offsets[0] as usize..(offsets[0] + size) as usize];
    let mut result = BTreeSet::new();
    for n in needed {
        let rest = strings
            .get(usize::try_from(n)?..)
            .ok_or("dynamic dependency outside string table")?;
        let end = rest
            .iter()
            .position(|b| *b == 0)
            .ok_or("unterminated dynamic dependency")?;
        let name = std::str::from_utf8(&rest[..end])?;
        if name.is_empty() || name.contains('/') || !result.insert(name.to_owned()) {
            return fail("invalid or duplicate dynamic dependency");
        }
    }
    recheck(&reference, 512 * 1024 * 1024)?;
    Ok(result)
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct ApexRecord {
    module: String,
    installed_container: FileRef,
    uncompressed_sha256: String,
    payload_sha256: String,
    payload_members: Members,
    required_member_hashes: BTreeMap<PathBuf, String>,
    extracted_temporary_retired: bool,
}

fn complete_apex(
    info: &Value,
    product: &Path,
    module: &str,
    provider: &str,
    required: &[&str],
    scratch: &Path,
) -> Result<ApexRecord> {
    let row = info.get(module).ok_or("selected APEX module is absent")?;
    let candidates: Vec<_> = ["apex", "capex"]
        .iter()
        .filter_map(|suffix| {
            let relative = format!("system/apex/{module}.{suffix}");
            row["installed"].as_array().and_then(|paths| {
                paths
                    .iter()
                    .any(|p| {
                        p.as_str()
                            .is_some_and(|s| Path::new(s) == product.join(&relative))
                    })
                    .then_some(relative)
            })
        })
        .collect();
    if candidates.len() != 1 {
        return fail("selected APEX container is absent or ambiguous");
    }
    let installed = installed_file(info, product, module, provider, &candidates[0])?;
    let temporary = tempfile::Builder::new()
        .prefix("apex-readback-")
        .tempdir_in(scratch)?;
    let apex = if candidates[0].ends_with(".capex") {
        unzip_member(
            &installed,
            "original_apex",
            &temporary.path().join("original.apex"),
        )?
    } else {
        installed.clone()
    };
    let payload = unzip_member(
        &apex,
        "apex_payload.img",
        &temporary.path().join("payload.img"),
    )?;
    let tree = temporary.path().join("tree");
    filesystem_tree(&payload, &tree)?;
    let payload_members = inventory(&tree, true)?;
    let mut hashes = BTreeMap::new();
    for relative in required {
        let row = payload_members
            .get(Path::new(relative))
            .ok_or("required actual APEX member is absent")?;
        if row.kind != "file" || row.bytes == 0 {
            return fail("required APEX member is not a complete regular file");
        }
        if relative.ends_with(".so") {
            elf_needed(&tree.join(relative))?;
        }
        hashes.insert(
            PathBuf::from(relative),
            row.sha256.clone().ok_or("APEX member has no whole hash")?,
        );
    }
    if module == "com.android.media.swcodec"
        && !elf_needed(&tree.join("lib64/libcodec2_soft_aacdec.so"))?
            .contains("libFraunhoferAAC.so")
    {
        return fail("actual selected AAC decoder does not depend on the repaired C++ AAC library");
    }
    unchanged_tree(&tree, &payload_members)?;
    recheck(&installed, MAX_IMAGE)?;
    let record = ApexRecord {
        module: module.into(),
        installed_container: installed,
        uncompressed_sha256: apex.sha256,
        payload_sha256: payload.sha256,
        payload_members,
        required_member_hashes: hashes,
        extracted_temporary_retired: true,
    };
    temporary.close()?;
    resources::checkpoint()?;
    Ok(record)
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Cohort {
    schema: String,
    inputs: FileRef,
    build_inputs: BuildInputs,
    normal_command_exit_code: i32,
    actual_command_environment: BTreeMap<String, Option<String>>,
    module_info: FileRef,
    partitions: Vec<Partition>,
    installed_runtime_artifacts: BTreeMap<String, FileRef>,
    apexes: Vec<ApexRecord>,
    compiled_native_generation_enabled: bool,
    normal_images_match_complete_installed_trees: bool,
    image_readback_temporaries_retired: bool,
    android_execution_qualified: bool,
    production_signing_qualified: bool,
    binary_security_semantics_qualified: bool,
}

fn actual_provider(info: &Value, module: &str, allowed_project: &str) -> Result<String> {
    let paths = info[module]["path"]
        .as_array()
        .ok_or("APEX source provider metadata missing")?;
    if paths.len() != 1 {
        return fail("APEX source provider is ambiguous");
    }
    let provider = paths[0].as_str().ok_or("invalid APEX source provider")?;
    let path = Path::new(provider);
    if !path.starts_with(allowed_project)
        || path
            .components()
            .any(|c| !matches!(c, Component::Normal(_)))
    {
        return fail("APEX does not have its required normal source provider");
    }
    Ok(provider.to_owned())
}

pub(crate) fn complete_normal(success: SuccessfulBuild) -> Result<PathBuf> {
    // Every partition/APEX retires its scratch before the next starts.
    // Peak: optional original APEX + payload image + one extracted tree.
    let _scope =
        resources::Scope::writing(&success.inputs.out, 2 * MAX_IMAGE + resources::MAX_TREE)?;
    let inputs = success.inputs;
    recheck(&success.reference, MAX_JSON)?;
    let product = &inputs.product;
    ordinary_absolute(product, true)?;
    let (module_info, info) = read_json(&product.join("module-info.json"))?;
    let scratch = tempfile::Builder::new()
        .prefix("coherent-image-readback-")
        .tempdir_in(&inputs.out)?;
    let mut partitions = Vec::new();
    for partition in PARTITIONS {
        partitions.push(complete_partition(product, partition, scratch.path())?);
    }
    let common = &partitions[0].build_identity;
    if common.id != inputs.selected_release.source_build_id
        || partitions.iter().any(|p| &p.build_identity != common)
    {
        return fail(
            "complete partitions have a different source/build generation or selected release",
        );
    }
    let mut artifacts = BTreeMap::new();
    for (module, provider, relative) in INSTALLED {
        let artifact = installed_file(&info, product, module, provider, relative)?;
        if relative.ends_with(".so") || *module == "apexd" {
            elf_needed(&artifact.path)?;
        }
        artifacts.insert((*module).into(), artifact);
    }
    let apexes = vec![
        complete_apex(
            &info,
            product,
            "com.android.media.swcodec",
            "frameworks/av/apex",
            &[
                "lib64/libFraunhoferAAC.so",
                "lib64/libcodec2_soft_aacdec.so",
            ],
            scratch.path(),
        )?,
        complete_apex(
            &info,
            product,
            "com.android.art",
            &actual_provider(&info, "com.android.art", "art")?,
            &["lib64/libart.so", "lib64/libnativebridge.so"],
            scratch.path(),
        )?,
        complete_apex(
            &info,
            product,
            "com.android.virt",
            &actual_provider(&info, "com.android.virt", "packages/modules/Virtualization")?,
            &[
                "etc/classpaths/bootclasspath.pb",
                "etc/classpaths/systemserverclasspath.pb",
                "javalib/framework-virtualization.jar",
                "javalib/service-virtualization.jar",
            ],
            scratch.path(),
        )?,
        complete_apex(
            &info,
            product,
            "com.android.tethering",
            &actual_provider(
                &info,
                "com.android.tethering",
                "packages/modules/Connectivity",
            )?,
            &[
                "bin/netbpfload",
                "lib64/libservice-connectivity.so",
                "lib64/libnetd_updatable.so",
                "lib64/libandroid_net_connectivity_com_android_net_module_util_jni.so",
            ],
            scratch.path(),
        )?,
        complete_apex(
            &info,
            product,
            "com.android.profiling",
            "packages/modules/Profiling/apex",
            &PROFILING_APEX_MEMBERS,
            scratch.path(),
        )?,
    ];
    // Whole normal system tree already contains the engine and whole ART APEX.
    // Keep the existing actual compiled-role protocol check; do not replace the
    // APEX or add a pairing record after an image has been produced.
    let compiled_native_generation_enabled = crate::native_generation::verify_tree(product)?;
    for p in &partitions {
        unchanged_tree(&product.join(&p.name), &p.installed_members)?;
        if let Some(root) = &p.system_root_members {
            unchanged_tree(&product.join("root"), root)?;
        }
        recheck(&p.image, MAX_IMAGE)?;
        recheck(&p.properties, 1024 * 1024)?;
    }
    for artifact in artifacts.values() {
        recheck(artifact, 2 * 1024 * 1024 * 1024)?;
    }
    for apex in &apexes {
        recheck(&apex.installed_container, MAX_IMAGE)?;
    }
    for source in [
        &inputs.source_lock,
        &inputs.source_manifest,
        &inputs.source_build_id,
        &inputs.image_builder,
        &inputs.source_receipt,
        &inputs.product_configuration,
        &inputs.release_map,
        &module_info,
        &success.reference,
    ]
    .into_iter()
    .chain(inputs.release_evidence.iter())
    {
        recheck(source, MAX_JSON)?;
    }
    scratch.close()?;
    let result = Cohort {
        schema: "droidloom-coherent-product-normal-result-v2".into(),
        inputs: success.reference,
        build_inputs: inputs,
        normal_command_exit_code: 0,
        actual_command_environment: success.actual_command_environment,
        module_info,
        partitions,
        installed_runtime_artifacts: artifacts,
        apexes,
        compiled_native_generation_enabled,
        normal_images_match_complete_installed_trees: true,
        image_readback_temporaries_retired: true,
        android_execution_qualified: false,
        production_signing_qualified: false,
        binary_security_semantics_qualified: false,
    };
    let path = result.build_inputs.out.join(NORMAL);
    save_new(&path, &result)?;
    Ok(path)
}

fn verify_cohort_shape(cohort: &Cohort, product: &Path) -> Result<()> {
    if cohort.schema != "droidloom-coherent-product-normal-result-v2"
        || cohort.build_inputs.schema != "droidloom-coherent-product-inputs-v2"
        || cohort.build_inputs.product != product
        || cohort.normal_command_exit_code != 0
        || !cohort.normal_images_match_complete_installed_trees
        || !cohort.image_readback_temporaries_retired
        || cohort.android_execution_qualified
        || cohort.production_signing_qualified
        || cohort.binary_security_semantics_qualified
        || cohort
            .partitions
            .iter()
            .map(|p| p.name.as_str())
            .collect::<Vec<_>>()
            != PARTITIONS
    {
        return fail("missing complete normal product receipt or unsupported qualification claim");
    }
    validate_full_targets(&cohort.build_inputs.requested_targets)?;
    let mut planned = cohort.build_inputs.command_environment.clone();
    let mut actual = cohort.actual_command_environment.clone();
    // util::run_build may reserve compiler CPUs and append this one fixed
    // variable. Preserve the actual value instead of claiming the original
    // pre-run Command environment was necessarily the executed one.
    let before_cpu = planned.remove("DROIDLOOM_COMPILER_CPUS_RESERVED");
    let after_cpu = actual.remove("DROIDLOOM_COMPILER_CPUS_RESERVED");
    if actual != planned || (after_cpu != before_cpu && after_cpu != Some(Some("1".into()))) {
        return fail("normal command environment changed beyond its existing CPU reservation");
    }
    let out = &cohort.build_inputs.out;
    if product != out.join("target/product").join(PRODUCT)
        || cohort.inputs.path != out.join(INPUTS)
        || cohort.module_info.path != product.join("module-info.json")
        || cohort.build_inputs.source_manifest.path
            != cohort
                .build_inputs
                .source
                .join(".droidloom-source-manifest.json")
        || cohort.build_inputs.source_build_id.path
            != cohort
                .build_inputs
                .source
                .join("build/make/core/build_id.mk")
        || cohort.build_inputs.image_builder.path
            != cohort
                .build_inputs
                .source
                .join("build/make/tools/releasetools/build_image.py")
        || cohort.build_inputs.source_receipt.path
            != out.join("droidloom-production-full653-inputs.json")
        || cohort.build_inputs.product_configuration.path != out.join(configuration::RECEIPT)
        || cohort.build_inputs.command_program != out.join("soong_ui")
        || cohort.build_inputs.command_executable.path != out.join("soong_ui")
        || cohort.build_inputs.command_cwd != cohort.build_inputs.source
    {
        return fail("complete product receipt redirects an input or output to a foreign location");
    }
    if cohort.partitions.iter().any(|p| {
        p.build_identity != cohort.partitions[0].build_identity
            || p.image.path != product.join(format!("{}.img", p.name))
            || p.properties.path != property_path(product, &p.name)
            || p.source_is_sparse != p.sparse_converter.is_some()
            || (!p.source_is_sparse
                && (p.delivered_bytes != p.image.bytes || p.delivered_sha256 != p.image.sha256))
    }) {
        return fail("partition belongs to another product generation or output root");
    }
    if cohort.partitions[0].build_identity.id
        != cohort.build_inputs.selected_release.source_build_id
    {
        return fail("actual normal output does not match the reviewed selected release mapping");
    }
    let required: BTreeSet<_> = INSTALLED.iter().map(|(module, _, _)| *module).collect();
    if cohort
        .installed_runtime_artifacts
        .keys()
        .map(String::as_str)
        .collect::<BTreeSet<_>>()
        != required
        || cohort
            .apexes
            .iter()
            .map(|a| a.module.as_str())
            .collect::<Vec<_>>()
            != [
                "com.android.media.swcodec",
                "com.android.art",
                "com.android.virt",
                "com.android.tethering",
                "com.android.profiling",
            ]
    {
        return fail("normal complete product is missing a required actual runtime consumer");
    }
    for (module, _, relative) in INSTALLED {
        let artifact = &cohort.installed_runtime_artifacts[*module];
        let (partition, name) = relative
            .split_once('/')
            .ok_or("invalid fixed installed path")?;
        let member = cohort
            .partitions
            .iter()
            .find(|p| p.name == partition)
            .and_then(|p| p.installed_members.get(Path::new(name)))
            .ok_or("runtime artifact is absent from its complete partition inventory")?;
        if artifact.path != product.join(relative)
            || !override_identical(member, artifact)
            || artifact.identity != member.identity
        {
            return fail("runtime artifact belongs to a different installed product path");
        }
    }
    for apex in &cohort.apexes {
        if !apex.extracted_temporary_retired
            || !["apex", "capex"].iter().any(|suffix| {
                apex.installed_container.path
                    == product.join(format!("system/apex/{}.{}", apex.module, suffix))
            })
        {
            return fail("APEX belongs to a different product path or has an unretired temporary");
        }
        let required: &[&str] = match apex.module.as_str() {
            "com.android.media.swcodec" => &[
                "lib64/libFraunhoferAAC.so",
                "lib64/libcodec2_soft_aacdec.so",
            ],
            "com.android.art" => &["lib64/libart.so", "lib64/libnativebridge.so"],
            "com.android.virt" => &[
                "etc/classpaths/bootclasspath.pb",
                "etc/classpaths/systemserverclasspath.pb",
                "javalib/framework-virtualization.jar",
                "javalib/service-virtualization.jar",
            ],
            "com.android.tethering" => &[
                "bin/netbpfload",
                "lib64/libservice-connectivity.so",
                "lib64/libnetd_updatable.so",
                "lib64/libandroid_net_connectivity_com_android_net_module_util_jni.so",
            ],
            "com.android.profiling" => &PROFILING_APEX_MEMBERS,
            _ => return fail("unexpected complete-product APEX"),
        };
        let container = apex
            .installed_container
            .path
            .strip_prefix(product.join("system"))?;
        let actual_container = cohort.partitions[0]
            .installed_members
            .get(container)
            .ok_or("APEX container is absent from the complete system inventory")?;
        if !override_identical(actual_container, &apex.installed_container)
            || actual_container.identity != apex.installed_container.identity
            || apex
                .required_member_hashes
                .keys()
                .map(PathBuf::as_path)
                .collect::<BTreeSet<_>>()
                != required.iter().map(Path::new).collect()
            || apex.required_member_hashes.iter().any(|(name, sha)| {
                apex.payload_members.get(name).is_none_or(|m| {
                    m.kind != "file" || m.bytes == 0 || m.sha256.as_ref() != Some(sha)
                })
            })
        {
            return fail(
                "APEX selected-member receipt differs from its complete payload inventory",
            );
        }
    }
    for partition in &cohort.partitions {
        let expected = expected_partition_members(
            &partition.name,
            &partition.installed_members,
            partition.system_root_members.as_ref(),
        )?;
        if expected != partition.expected_image_members {
            return fail("image merge recipe differs from its normal roots");
        }
        compare_members(&expected, &partition.image_members)?;
    }
    Ok(())
}

pub(crate) struct CompleteProduct {
    normal: FileRef,
    cohort: Cohort,
}

pub(crate) fn require_complete_product(repo: &Path, product: &Path) -> Result<CompleteProduct> {
    let _scope = resources::Scope::read_only()?;
    let (normal, cohort) = load_cohort(repo, product)?;
    Ok(CompleteProduct { normal, cohort })
}

fn load_cohort(repo: &Path, product: &Path) -> Result<(FileRef, Cohort)> {
    ordinary_absolute(product, true)?;
    let out = product
        .parent()
        .and_then(Path::parent)
        .and_then(Path::parent)
        .ok_or("product does not have its normal OUT/target/product parent")?;
    if product != out.join("target/product").join(PRODUCT) {
        return fail("coherent product must have its exact normal output location");
    }
    let (reference, value) = read_json(&out.join(NORMAL))?;
    let cohort: Cohort = serde_json::from_value(value)?;
    verify_cohort_shape(&cohort, product)?;
    if cohort.build_inputs.source_lock.path
        != repo.join(crate::android::PRODUCTION_SOURCE_LOCK_PATH)
        || cohort.build_inputs.release_map.path
            != repo.join("android/manifest/source-runtime-coherence-x86_64.json")
    {
        return fail("normal product belongs to another reviewed recipe");
    }
    let (map_ref, mapping) = release_map(repo, &cohort.build_inputs.source_lock)?;
    if map_ref != cohort.build_inputs.release_map || mapping != cohort.build_inputs.selected_release
    {
        return fail("source/runtime identity mapping changed since the normal build");
    }
    let expected_evidence: Vec<_> = [
        &mapping.source_identity_evidence,
        &mapping.art_apex_abi_evidence,
    ]
    .into_iter()
    .map(|e| pin(&repo.join(&e.relative), MAX_JSON))
    .collect::<Result<_>>()?;
    if expected_evidence != cohort.build_inputs.release_evidence {
        return fail("normal product source or ART/APEX evidence was replaced");
    }
    let (_, inputs) = read_json(&cohort.inputs.path)?;
    if inputs != serde_json::to_value(&cohort.build_inputs)? {
        return fail("normal build input body differs");
    }
    for original in [
        &cohort.inputs,
        &cohort.build_inputs.source_lock,
        &cohort.build_inputs.source_manifest,
        &cohort.build_inputs.source_build_id,
        &cohort.build_inputs.image_builder,
        &cohort.build_inputs.source_receipt,
        &cohort.build_inputs.release_map,
        &cohort.build_inputs.product_configuration,
        &cohort.module_info,
    ]
    .into_iter()
    .chain(cohort.build_inputs.release_evidence.iter())
    {
        recheck(original, MAX_JSON)?;
    }
    configuration::verify_restored_record(
        &cohort.build_inputs.product_configuration,
        repo,
        &cohort.build_inputs.source,
        out,
    )?;
    recheck(&cohort.build_inputs.command_executable, 512 * 1024 * 1024)?;
    for partition in &cohort.partitions {
        recheck(&partition.image, MAX_IMAGE)?;
        recheck(&partition.properties, 1024 * 1024)?;
        unchanged_tree(&product.join(&partition.name), &partition.installed_members)?;
        if let Some(root) = &partition.system_root_members {
            unchanged_tree(&product.join("root"), root)?;
        }
    }
    for artifact in cohort.installed_runtime_artifacts.values() {
        recheck(artifact, 2 * 1024 * 1024 * 1024)?;
    }
    for apex in &cohort.apexes {
        recheck(&apex.installed_container, MAX_IMAGE)?;
    }
    Ok((reference, cohort))
}

/// Fail before downloads/builds when the selected release has no reviewed source
/// identity mapping. This does not create or infer that missing mapping.
pub(crate) fn preflight_selection(repo: &Path) -> Result<()> {
    let _scope = resources::Scope::read_only()?;
    let source_lock = pin(
        &repo.join(crate::android::PRODUCTION_SOURCE_LOCK_PATH),
        MAX_JSON,
    )?;
    if source_lock.sha256 != FULL_SOURCE_SHA {
        return fail("unrecognized complete source profile");
    }
    release_map(repo, &source_lock).map(|_| ())
}

pub(crate) fn reject_legacy_mutation(product: &Path) -> Result<()> {
    let _scope = resources::Scope::read_only()?;
    if let Some(out) = product
        .parent()
        .and_then(Path::parent)
        .and_then(Path::parent)
    {
        for name in [INPUTS, NORMAL] {
            match out.join(name).symlink_metadata() {
                Ok(_) => {
                    return fail(
                        "a complete product cannot be rewritten by the legacy base-image derivation path",
                    );
                }
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
                Err(error) => return Err(error.into()),
            }
        }
    }
    resources::checkpoint()
}

fn copy_bound(source: &FileRef, destination: &Path) -> Result<FileRef> {
    recheck(source, MAX_IMAGE)?;
    let parent = destination.parent().ok_or("staged file lacks parent")?;
    resources::prepare_output_directory(parent)?;
    let mut input = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
        .open(&source.path)?;
    if identity(&input.metadata()?)? != source.identity {
        return fail("copy source was replaced");
    }
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o444)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(destination)?;
    let mut remaining = source.bytes;
    let mut buffer = vec![0u8; 1024 * 1024];
    while remaining > 0 {
        resources::checkpoint()?;
        let cap = usize::try_from(remaining.min(buffer.len() as u64))?;
        let n = input.read(&mut buffer[..cap])?;
        if n == 0 {
            return fail("truncated complete-product copy");
        }
        output.write_all(&buffer[..n])?;
        remaining -= n as u64;
        resources::checkpoint()?;
    }
    if input.read(&mut buffer[..1])? != 0 || identity(&input.metadata()?)? != source.identity {
        return fail("copy source changed during complete-product staging");
    }
    output.sync_all()?;
    File::open(parent)?.sync_all()?;
    let copied = pin(destination, MAX_IMAGE)?;
    if copied.bytes != source.bytes || copied.sha256 != source.sha256 {
        return fail("staged complete product file differs from its normal output");
    }
    recheck(source, MAX_IMAGE)?;
    Ok(copied)
}

/// Stage every partition from the same normal output. Sparse decoding is the
/// only transformation, and must reproduce the already inspected raw hash.
/// Neither NativeBridge derivation nor legacy VNDK pruning occurs here.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct RuntimeProjection {
    target: String,
    copied_relative: PathBuf,
    bytes: u64,
    sha256: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "kind", deny_unknown_fields)]
enum AuxiliaryOrigin {
    Partition { partition: String, member: PathBuf },
    Apex { module: String, member: PathBuf },
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct AuxiliaryProjection {
    origin: AuxiliaryOrigin,
    copied_relative: PathBuf,
    staged_file: FileRef,
}

fn auxiliary_layout() -> Vec<(AuxiliaryOrigin, PathBuf)> {
    let mut rows = vec![];
    for (partition, member, copied) in [
        ("system", "bin/init", "bin/droidloom-android-init"),
        (
            "system",
            "app/DroidloomIME/DroidloomIME.apk",
            "ime/DroidloomIME.apk",
        ),
        (
            "system",
            "app/DroidloomHome/DroidloomHome.apk",
            "ime/DroidloomHome.apk",
        ),
        (
            "vendor",
            "framework/droidloom-input-bridge.jar",
            "ime/droidloom-input-bridge.jar",
        ),
        (
            "vendor",
            "bin/droidloom-classpath-wrapper",
            "compat/classpath-compat/bin/droidloom-classpath-wrapper",
        ),
    ] {
        rows.push((
            AuxiliaryOrigin::Partition {
                partition: partition.into(),
                member: member.into(),
            },
            PathBuf::from("usr/lib/droidloom/runtime").join(copied),
        ));
    }
    for (module, prefix, members) in [
        (
            "com.android.virt",
            "apex/com.android.virt",
            &[
                "etc/classpaths/bootclasspath.pb",
                "etc/classpaths/systemserverclasspath.pb",
                "javalib/framework-virtualization.jar",
                "javalib/service-virtualization.jar",
            ][..],
        ),
        (
            "com.android.tethering",
            "",
            &[
                "bin/netbpfload",
                "lib64/libservice-connectivity.so",
                "lib64/libnetd_updatable.so",
                "lib64/libandroid_net_connectivity_com_android_net_module_util_jni.so",
            ][..],
        ),
    ] {
        for member in members {
            rows.push((
                AuxiliaryOrigin::Apex {
                    module: module.into(),
                    member: (*member).into(),
                },
                PathBuf::from("usr/lib/droidloom/runtime/compat/classpath-compat")
                    .join(prefix)
                    .join(member),
            ));
        }
    }
    rows
}

fn auxiliary_member<'a>(cohort: &'a Cohort, origin: &AuxiliaryOrigin) -> Result<&'a Member> {
    match origin {
        AuxiliaryOrigin::Partition { partition, member } => cohort
            .partitions
            .iter()
            .find(|p| &p.name == partition)
            .and_then(|p| p.installed_members.get(member)),
        AuxiliaryOrigin::Apex { module, member } => cohort
            .apexes
            .iter()
            .find(|a| &a.module == module)
            .and_then(|a| a.payload_members.get(member)),
    }
    .ok_or_else(|| "runtime auxiliary file is absent from the complete normal product".into())
}

fn validate_auxiliary_layout(rows: &[AuxiliaryProjection]) -> Result<()> {
    let expected = auxiliary_layout();
    if rows.len() != expected.len()
        || rows
            .iter()
            .zip(expected)
            .any(|(row, (origin, path))| row.origin != origin || row.copied_relative != path)
    {
        return fail(
            "runtime auxiliary paths or source roles differ from the fixed normal product closure",
        );
    }
    Ok(())
}

fn validate_classpath_namespace(root: &Path) -> Result<()> {
    let prefix = Path::new("usr/lib/droidloom/runtime/compat/classpath-compat");
    let files: BTreeSet<_> = auxiliary_layout()
        .into_iter()
        .filter_map(|(_, path)| path.strip_prefix(prefix).ok().map(Path::to_owned))
        .collect();
    let mut expected = files.clone();
    expected.insert(PathBuf::new());
    for file in &files {
        let mut parent = file.parent();
        while let Some(path) = parent {
            expected.insert(path.into());
            parent = path.parent();
        }
    }
    let actual = inventory(&root.join(prefix), true)?;
    if actual.keys().cloned().collect::<BTreeSet<_>>() != expected
        || actual.iter().any(|(path, member)| {
            member.kind
                != if files.contains(path) {
                    "file"
                } else {
                    "directory"
                }
        })
    {
        return fail("runtime classpath directory contains a missing, extra or aliased member");
    }
    Ok(())
}

fn collect_auxiliary(verified: &CompleteProduct, root: &Path) -> Result<Vec<AuxiliaryProjection>> {
    validate_classpath_namespace(root)?;
    auxiliary_layout()
        .into_iter()
        .map(|(origin, copied_relative)| {
            let staged_file = pin(&root.join(&copied_relative), 2 * 1024 * 1024 * 1024)?;
            if !override_identical(auxiliary_member(&verified.cohort, &origin)?, &staged_file) {
                return fail(
                    "runtime auxiliary member differs from its complete normal partition or APEX",
                );
            }
            Ok(AuxiliaryProjection {
                origin,
                copied_relative,
                staged_file,
            })
        })
        .collect()
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Delivery {
    schema: String,
    normal_product_original: FileRef,
    normal_result_copy: FileRef,
    selected_build_id: String,
    source_lock: FileRef,
    partition_copies: BTreeMap<String, FileRef>,
    runtime_projections: Vec<RuntimeProjection>,
    auxiliary_projections: Vec<AuxiliaryProjection>,
    complete_partition_delivery: bool,
    jar_override_repair_used: bool,
    old_base_partition_used: bool,
    android_execution_qualified: bool,
    production_signing_qualified: bool,
    binary_security_semantics_qualified: bool,
}

pub(crate) fn stage_images(
    verified: &CompleteProduct,
    repo: &Path,
    payload: &Path,
    destination: &Path,
) -> Result<()> {
    let normal = &verified.normal;
    let cohort = &verified.cohort;
    let copies_bytes = cohort.partitions.iter().try_fold(0u64, |total, p| {
        total
            .checked_add(p.delivered_bytes)
            .ok_or("aggregate partition copy size overflow")
    })?;
    let scratch_bytes = cohort
        .partitions
        .iter()
        .filter(|p| p.source_is_sparse)
        .map(|p| p.delivered_bytes)
        .max()
        .unwrap_or(0);
    let required = copies_bytes
        .checked_add(scratch_bytes)
        .and_then(|n| n.checked_add(2 * MAX_JSON))
        .ok_or("aggregate partition staging size overflow")?;
    let _scope = resources::Scope::writing(&resources::output_ancestor(destination)?, required)?;
    resources::prepare_output_directory(destination)?;
    let scratch = tempfile::Builder::new()
        .prefix("coherent-stage-")
        .tempdir_in(destination)?;
    let runtime_projections = validate_overrides(verified, repo, payload)?;
    let auxiliary_projections = collect_auxiliary(verified, payload)?;
    let normal_result_copy = copy_bound(normal, &destination.join("normal-product.json"))?;
    let mut copies = BTreeMap::new();
    for partition in &cohort.partitions {
        resources::checkpoint()?;
        let decoded = tempfile::Builder::new()
            .prefix("one-partition-")
            .tempdir_in(scratch.path())?;
        let (raw, converter) = decode_image(
            &partition.image,
            &decoded.path().join(format!("{}.raw.img", partition.name)),
        )?;
        if raw.bytes != partition.delivered_bytes
            || raw.sha256 != partition.delivered_sha256
            || converter != partition.sparse_converter
        {
            return fail("normal partition decoding differs from the verified complete image");
        }
        let filename = if partition.name == "vendor" {
            "vendor.raw.img".to_string()
        } else {
            format!("{}.img", partition.name)
        };
        copies.insert(
            partition.name.clone(),
            copy_bound(&raw, &destination.join(filename))?,
        );
        decoded.close()?;
        resources::checkpoint()?;
    }
    scratch.close()?;
    recheck(&normal, MAX_JSON)?;
    for partition in &cohort.partitions {
        recheck(&partition.image, MAX_IMAGE)?;
    }
    save_new(
        &destination.join("coherent-product-delivery.json"),
        &Delivery {
            schema: "droidloom-coherent-product-delivery-v2".into(),
            normal_product_original: normal.clone(),
            normal_result_copy,
            selected_build_id: cohort
                .build_inputs
                .selected_release
                .selected_build_id
                .clone(),
            source_lock: cohort.build_inputs.source_lock.clone(),
            partition_copies: copies,
            runtime_projections,
            auxiliary_projections,
            complete_partition_delivery: true,
            jar_override_repair_used: false,
            old_base_partition_used: false,
            android_execution_qualified: false,
            production_signing_qualified: false,
            binary_security_semantics_qualified: false,
        },
    )?;
    Ok(())
}

/// Runtime compatibility projections use the same inspected whole Virt APEX.
/// Their hashes are checked against its payload, never against a cached base.
fn stage_apex_members(verified: &CompleteProduct, module: &str, destination: &Path) -> Result<()> {
    let cohort = &verified.cohort;
    let apex = cohort
        .apexes
        .iter()
        .find(|a| a.module == module)
        .ok_or("normal runtime APEX absent")?;
    resources::prepare_output_directory(destination)?;
    let scratch = tempfile::Builder::new()
        .prefix("virt-normal-")
        .tempdir_in(destination)?;
    let archive = if apex
        .installed_container
        .path
        .extension()
        .is_some_and(|e| e == "capex")
    {
        unzip_member(
            &apex.installed_container,
            "original_apex",
            &scratch.path().join("original.apex"),
        )?
    } else {
        apex.installed_container.clone()
    };
    if archive.sha256 != apex.uncompressed_sha256 {
        return fail("Virt APEX differs from its normal receipt");
    }
    let payload = unzip_member(
        &archive,
        "apex_payload.img",
        &scratch.path().join("payload.img"),
    )?;
    if payload.sha256 != apex.payload_sha256 {
        return fail("Virt payload differs from its normal receipt");
    }
    let tree = scratch.path().join("tree");
    filesystem_tree(&payload, &tree)?;
    let observed = inventory(&tree, true)?;
    compare_members(&apex.payload_members, &observed)?;
    for (relative, expected) in &apex.required_member_hashes {
        let source = pin(&tree.join(relative), MAX_IMAGE)?;
        if &source.sha256 != expected {
            return fail("Virt runtime projection differs from its inspected member");
        }
        copy_bound(&source, &destination.join(relative))?;
    }
    unchanged_tree(&tree, &observed)?;
    recheck(&apex.installed_container, MAX_IMAGE)?;
    scratch.close()?;
    resources::checkpoint()
}

pub(crate) fn stage_runtime_apexes(verified: &CompleteProduct, destination: &Path) -> Result<()> {
    let copied_bytes = verified
        .cohort
        .apexes
        .iter()
        .filter(|a| {
            matches!(
                a.module.as_str(),
                "com.android.virt" | "com.android.tethering"
            )
        })
        .try_fold(0u64, |total, apex| {
            apex.required_member_hashes
                .keys()
                .try_fold(total, |total, path| {
                    let bytes = apex
                        .payload_members
                        .get(path)
                        .ok_or("required APEX copy has no inspected size")?
                        .bytes;
                    total.checked_add(bytes).ok_or_else(|| {
                        Box::<dyn std::error::Error>::from("aggregate APEX copy size overflow")
                    })
                })
        })?;
    let required = copied_bytes
        .checked_add(2 * MAX_IMAGE + resources::MAX_TREE)
        .ok_or("aggregate APEX staging size overflow")?;
    let _scope = resources::Scope::writing(&resources::output_ancestor(destination)?, required)?;
    stage_apex_members(
        verified,
        "com.android.virt",
        &destination.join("apex/com.android.virt"),
    )?;
    stage_apex_members(verified, "com.android.tethering", destination)
}

// A post-build bind mount is allowed only when it is byte-identical to this
// complete image. Required RC/property changes must be projected before Soong
// builds the image; this check cannot turn a different JAR/ART epoch into one.
fn validate_overrides(
    verified: &CompleteProduct,
    repo: &Path,
    payload: &Path,
) -> Result<Vec<RuntimeProjection>> {
    let cohort = &verified.cohort;
    let (_, spec) = read_json(&repo.join("packaging/cell-spec-x86_64-u1000.json"))?;
    let mut result = Vec::new();
    for (target, source) in projection_paths(&spec)? {
        let relative = target
            .strip_prefix('/')
            .ok_or("runtime override is not absolute")?;
        let (partition, name) = relative
            .split_once('/')
            .ok_or("runtime override lacks partition")?;
        let members = &cohort
            .partitions
            .iter()
            .find(|p| p.name == partition)
            .ok_or("runtime override escapes the four complete partitions")?
            .installed_members;
        let member = members
            .get(Path::new(name))
            .ok_or("runtime override target is absent from the normal image")?;
        let actual = payload.join(source);
        let copied = pin(&actual, 2 * 1024 * 1024 * 1024)?;
        if !override_identical(member, &copied) {
            return fail(format!(
                "runtime override differs from the complete normal image: {target}"
            ));
        }
        result.push(RuntimeProjection {
            target: target.into(),
            copied_relative: actual.strip_prefix(payload)?.to_owned(),
            bytes: copied.bytes,
            sha256: copied.sha256,
        });
    }
    Ok(result)
}

fn projection_paths(spec: &Value) -> Result<BTreeMap<String, PathBuf>> {
    let mut result = BTreeMap::new();
    for row in spec["android_file_overrides"]
        .as_array()
        .ok_or("runtime override list absent")?
    {
        let target = row["target"].as_str().ok_or("override target absent")?;
        let source = row["source"].as_str().ok_or("override source absent")?;
        for name in [target, source] {
            if !name.starts_with('/')
                || name[1..]
                    .split('/')
                    .any(|p| p.is_empty() || p == "." || p == "..")
            {
                return fail("runtime projection uses an aliased path");
            }
        }
        let relative = if let Some(name) = source.strip_prefix("/usr/lib/droidloom/current/") {
            Path::new("usr/lib/droidloom/runtime").join(name)
        } else if let Some(name) = source.strip_prefix("/usr/lib/droidloom/storage/") {
            Path::new("usr/lib/droidloom/storage").join(name)
        } else {
            return fail("runtime override source escapes the staged product");
        };
        if result.insert(target.into(), relative).is_some() {
            return fail("duplicate runtime override target");
        }
    }
    Ok(result)
}

/// Rebind copied bytes on the installation host; producer and destination F9s
/// are intentionally different. No producer absolute path is opened here.
pub(crate) fn verify_staged_bundle(root: &Path) -> Result<()> {
    let _scope = resources::Scope::read_only()?;
    let images = root.join("var/lib/droidloom/images/images");
    match images.symlink_metadata() {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(e) => return Err(e.into()),
        _ => (),
    }
    let (spec_ref, spec) = read_json(&root.join("etc/droidloom/cell.json"))?;
    verify_delivery_at(root, &images, &spec)?;
    recheck(&spec_ref, MAX_JSON)
}

/// The portable layout relocates whole images and runtime data together. Its
/// separate actual template has the same override bindings and is read back
/// before that private staging tree becomes the package output.
pub(crate) fn verify_portable_package(stage: &Path) -> Result<()> {
    let _scope = resources::Scope::read_only()?;
    let root = stage.join("image");
    let images = root.join("usr/lib/droidloom/images/images");
    let (spec_ref, spec) =
        read_json(&stage.join("runtime/usr/share/droidloom/cell-template.json"))?;
    verify_delivery_at(&root, &images, &spec)?;
    crate::native_generation::verify_image(&images.join("system.img"))?;
    recheck(&spec_ref, MAX_JSON)
}

fn verify_delivery_at(root: &Path, images: &Path, spec: &Value) -> Result<()> {
    ordinary_absolute(&images, true)?;
    let (delivery_ref, raw) = read_json(&images.join("coherent-product-delivery.json"))?;
    let delivery: Delivery = serde_json::from_value(raw)?;
    let (normal_copy, raw) = read_json(&images.join("normal-product.json"))?;
    let normal: Cohort = serde_json::from_value(raw)?;
    let actual_projections = projection_paths(spec)?;
    verify_cohort_shape(&normal, &normal.build_inputs.product)?;
    validate_auxiliary_layout(&delivery.auxiliary_projections)?;
    validate_classpath_namespace(root)?;
    if delivery.schema != "droidloom-coherent-product-delivery-v2"
        || !delivery.complete_partition_delivery
        || delivery.jar_override_repair_used
        || delivery.old_base_partition_used
        || delivery.android_execution_qualified
        || delivery.production_signing_qualified
        || delivery.binary_security_semantics_qualified
        || normal_copy.bytes != delivery.normal_result_copy.bytes
        || normal_copy.sha256 != delivery.normal_result_copy.sha256
        || normal_copy.bytes != delivery.normal_product_original.bytes
        || normal_copy.sha256 != delivery.normal_product_original.sha256
        || delivery.selected_build_id != normal.build_inputs.selected_release.selected_build_id
        || delivery.source_lock != normal.build_inputs.source_lock
        || delivery
            .partition_copies
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>()
            != PARTITIONS.into_iter().collect()
    {
        return fail("copied normal-product or delivery identities disagree");
    }
    for partition in &normal.partitions {
        let filename = if partition.name == "vendor" {
            "vendor.raw.img".to_string()
        } else {
            format!("{}.img", partition.name)
        };
        let actual = pin(&images.join(filename), MAX_IMAGE)?;
        let declared = &delivery.partition_copies[&partition.name];
        if actual.bytes != declared.bytes
            || actual.sha256 != declared.sha256
            || actual.bytes != partition.delivered_bytes
            || actual.sha256 != partition.delivered_sha256
        {
            return fail("staged partition no longer matches its complete normal product");
        }
    }
    let mut targets = BTreeSet::new();
    for projection in &delivery.runtime_projections {
        if !targets.insert(&projection.target)
            || projection.copied_relative.is_absolute()
            || projection
                .copied_relative
                .components()
                .any(|p| !matches!(p, Component::Normal(_)))
            || actual_projections.get(&projection.target) != Some(&projection.copied_relative)
        {
            return fail("invalid staged runtime projection path");
        }
        let (partition, member) = projection
            .target
            .strip_prefix('/')
            .and_then(|p| p.split_once('/'))
            .ok_or("invalid staged target")?;
        let expected = normal
            .partitions
            .iter()
            .find(|p| p.name == partition)
            .and_then(|p| p.installed_members.get(Path::new(member)))
            .ok_or("projection is absent from normal image")?;
        let actual = pin(
            &root.join(&projection.copied_relative),
            2 * 1024 * 1024 * 1024,
        )?;
        if actual.bytes != projection.bytes
            || actual.sha256 != projection.sha256
            || !override_identical(expected, &actual)
        {
            return fail("staged runtime projection differs from its normal image bytes");
        }
    }
    if targets.len() != actual_projections.len() {
        return fail("staged spec adds or removes a normal-image projection");
    }
    for auxiliary in &delivery.auxiliary_projections {
        let current = pin(
            &root.join(&auxiliary.copied_relative),
            2 * 1024 * 1024 * 1024,
        )?;
        if current.bytes != auxiliary.staged_file.bytes
            || current.sha256 != auxiliary.staged_file.sha256
            || !override_identical(auxiliary_member(&normal, &auxiliary.origin)?, &current)
        {
            return fail(
                "final runtime auxiliary projection differs from the normal product member",
            );
        }
    }
    recheck(&delivery_ref, MAX_JSON)?;
    recheck(&normal_copy, MAX_JSON)?;
    Ok(())
}

fn override_identical(member: &Member, copied: &FileRef) -> bool {
    member.kind == "file"
        && member.bytes == copied.bytes
        && member.sha256.as_ref() == Some(&copied.sha256)
}

#[cfg(test)]
#[path = "coherent_images_tests.rs"]
mod tests;
