//! Reproduce the recovered public leaf source set without installing or executing it.
//!
//! The historical packet is a fixed source input, not an application qualification.
//! Missing current preparation/entry bytes remain missing; this command cannot repair
//! that difference by accepting a caller-supplied digest or by changing runtime gates.
pub(crate) mod cohort;
pub(crate) mod install;
pub(crate) mod installed;
mod package;

use crate::util::{Result, fail};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    ffi::CString,
    fs::{self, File},
    io::{Read, Seek, SeekFrom, Write},
    os::{
        fd::{AsRawFd, FromRawFd},
        unix::{ffi::OsStrExt, fs::MetadataExt},
    },
    path::{Component, Path, PathBuf},
};

const RECIPE: &str =
    include_str!("../../../android/manifest/native-application-leaf-recovery.json");
// Preserve the C93 historical commitment when the active consumer adopts r2.
const CURRENT_CATALOG: &str =
    include_str!("../resources/native-leaves/cp3a-20261120-apps-r1/leaf_sources.json");
const CURRENT_SELECTION: &str =
    include_str!("../resources/native-leaves/cp3a-20261120-apps-r1/selection-14.json");
const MAX_FILE: u64 = 2 * 1024 * 1024;
const FIXED_HELPER_BYTES: u64 = 3_972_024;
const FIXED_HELPER_SHA256: &str =
    "67cfd1c212e9f40ce3f0ff7be856a05f8189c674cbfa270757a672ea596a6c3f";
const MAX_TOTAL: u64 = 16 * 1024 * 1024;
const MAX_FILES: usize = 512;
const MAX_DIRS: usize = 256;
const MAX_DEPTH: usize = 16;
const MANIFEST_NAME: &str = "NATIVE-LEAF-SOURCES.json";

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Pin {
    path: String,
    bytes: u64,
    sha256: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Recipe {
    schema: String,
    canonical_root: String,
    source_packet_provenance: Pin,
    source_manifest: Pin,
    validator: Pin,
    expected_files: usize,
    expected_bytes: u64,
    current_catalog: Pin,
    current_selection: Pin,
    behavior: Vec<Value>,
    source_only: bool,
    installation_authorized: bool,
    runtime_qualified: bool,
    whole_app_business_accepted: bool,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SourceManifest {
    #[serde(rename = "Android_actions")]
    android_actions: u64,
    #[serde(rename = "CURRENT_writes")]
    current_writes: u64,
    canonical_root: String,
    files: Vec<Pin>,
    native_helper_binary_deployed: bool,
    runtime_qualified: bool,
    schema: String,
    source_only: bool,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CurrentLeaf {
    entry: Pin,
    index: usize,
    preparation: Pin,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
struct Node {
    device: u64,
    inode: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    bytes: u64,
    mtime_ns: i64,
    ctime_ns: i64,
}
fn node(m: &fs::Metadata) -> Result<Node> {
    Ok(Node {
        device: m.dev(),
        inode: m.ino(),
        mode: m.mode(),
        uid: m.uid(),
        gid: m.gid(),
        links: m.nlink(),
        bytes: m.len(),
        mtime_ns: m
            .mtime()
            .checked_mul(1_000_000_000)
            .and_then(|s| s.checked_add(m.mtime_nsec()))
            .ok_or("mtime overflow")?,
        ctime_ns: m
            .ctime()
            .checked_mul(1_000_000_000)
            .and_then(|s| s.checked_add(m.ctime_nsec()))
            .ok_or("ctime overflow")?,
    })
}
fn digest(raw: &[u8]) -> String {
    hex::encode(Sha256::digest(raw))
}
fn sha_shape(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn relative(s: &str) -> Result<()> {
    if s.is_empty()
        || s.len() > 512
        || s.starts_with('/')
        || s.split('/').any(|p| p.is_empty() || p == "." || p == "..")
        || !s
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"/_.-".contains(&b))
    {
        return fail("invalid fixed leaf member name");
    }
    Ok(())
}
fn absolute(path: &Path) -> Result<()> {
    if !path.is_absolute()
        || path
            .components()
            .any(|c| !matches!(c, Component::RootDir | Component::Normal(_)))
        || path.as_os_str().as_bytes().contains(&0)
    {
        return fail("leaf source paths must be absolute without dot components");
    }
    Ok(())
}
fn trusted_owner(m: &fs::Metadata) -> bool {
    let uid = unsafe { libc::geteuid() };
    (m.uid() == uid || m.uid() == 0) && m.mode() & 0o7022 == 0
}

// openat2 keeps every lookup beneath the actual held directory and rejects
// symlinks in all components. There is no fallback to a path-following open.
#[repr(C)]
struct OpenHow {
    flags: u64,
    mode: u64,
    resolve: u64,
}
fn beneath(parent: &File, name: &str, directory: bool) -> Result<File> {
    relative(name)?;
    let name = CString::new(name)?;
    let how = OpenHow {
        flags: (libc::O_RDONLY
            | libc::O_CLOEXEC
            | libc::O_NOFOLLOW
            | if directory { libc::O_DIRECTORY } else { 0 }) as u64,
        mode: 0,
        resolve: 0x08 | 0x04 | 0x02, // BENEATH | NO_SYMLINKS | NO_MAGICLINKS
    };
    let fd = unsafe {
        libc::syscall(
            libc::SYS_openat2,
            parent.as_raw_fd(),
            name.as_ptr(),
            &how,
            std::mem::size_of::<OpenHow>(),
        )
    };
    if fd < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(fd as i32) })
}
fn open_absolute_directory(path: &Path) -> Result<File> {
    absolute(path)?;
    let root = File::open("/")?;
    if path == Path::new("/") {
        return Ok(root);
    }
    beneath(
        &root,
        path.strip_prefix("/")?
            .to_str()
            .ok_or("non-UTF8 directory")?,
        true,
    )
}
fn check_directory(fd: &File) -> Result<Node> {
    let m = fd.metadata()?;
    if !m.is_dir() || !trusted_owner(&m) {
        return fail("leaf source directory must have a trusted owner and no group/world writes");
    }
    node(&m)
}
fn read_all(fd: &mut File, expected: u64) -> Result<Vec<u8>> {
    if expected > MAX_FILE && expected != FIXED_HELPER_BYTES {
        return fail("leaf source file exceeds the fixed size bound");
    }
    fd.seek(SeekFrom::Start(0))?;
    let mut raw = Vec::with_capacity(expected as usize);
    fd.take(expected + 1).read_to_end(&mut raw)?;
    if raw.len() as u64 != expected {
        return fail("short or growing leaf source file");
    }
    Ok(raw)
}

struct Held {
    name: String,
    file: File,
    before: Node,
    pin: Pin,
}
impl Held {
    fn open(root: &File, name: &str, pin: &Pin) -> Result<Self> {
        if !sha_shape(&pin.sha256)
            || (pin.bytes > MAX_FILE
                && (pin.bytes != FIXED_HELPER_BYTES || pin.sha256 != FIXED_HELPER_SHA256))
        {
            return fail("invalid source-owned digest");
        }
        let mut file = beneath(root, name, false)?;
        let m = file.metadata()?;
        if !m.is_file() || m.nlink() != 1 || m.len() != pin.bytes || !trusted_owner(&m) {
            return fail(format!(
                "not an exact single-link regular leaf input: {name}"
            ));
        }
        let before = node(&m)?;
        let raw = read_all(&mut file, pin.bytes)?;
        if digest(&raw) != pin.sha256 {
            return fail(format!("fixed leaf source bytes differ: {name}"));
        }
        let mut held = Self {
            name: name.into(),
            file,
            before,
            pin: pin.clone(),
        };
        held.recheck(root)?;
        Ok(held)
    }
    fn recheck(&mut self, root: &File) -> Result<()> {
        let named = beneath(root, &self.name, false)?;
        if node(&self.file.metadata()?)? != self.before || node(&named.metadata()?)? != self.before
        {
            return fail(format!("held/named leaf source changed: {}", self.name));
        }
        let raw = read_all(&mut self.file, self.pin.bytes)?;
        if digest(&raw) != self.pin.sha256
            || node(&self.file.metadata()?)? != self.before
            || node(&beneath(root, &self.name, false)?.metadata()?)? != self.before
        {
            return fail(format!("leaf source readback changed: {}", self.name));
        }
        Ok(())
    }
    fn bytes(&mut self) -> Result<Vec<u8>> {
        let raw = read_all(&mut self.file, self.pin.bytes)?;
        if digest(&raw) != self.pin.sha256 || node(&self.file.metadata()?)? != self.before {
            return fail("held leaf source changed before staging");
        }
        Ok(raw)
    }
}
struct InputTree {
    root: File,
    before: Node,
    named_path: PathBuf,
    directories: BTreeMap<String, (File, Node)>,
}
impl InputTree {
    fn open(path: &Path) -> Result<Self> {
        let root = open_absolute_directory(path)?;
        let before = check_directory(&root)?;
        Ok(Self {
            root,
            before,
            named_path: path.into(),
            directories: BTreeMap::new(),
        })
    }
    fn inventory(&mut self) -> Result<BTreeSet<String>> {
        let mut paths = BTreeSet::new();
        let mut pending = vec![(String::new(), self.root.try_clone()?, 0)];
        while let Some((name, directory, depth)) = pending.pop() {
            if depth > MAX_DEPTH || self.directories.len() >= MAX_DIRS {
                return fail("leaf source directory bound exceeded");
            }
            let identity = check_directory(&directory)?;
            for entry in fs::read_dir(format!("/proc/self/fd/{}", directory.as_raw_fd()))? {
                let entry = entry?;
                let part = entry
                    .file_name()
                    .into_string()
                    .map_err(|_| "non-UTF8 leaf member")?;
                relative(&part)?;
                let child = if name.is_empty() {
                    part
                } else {
                    format!("{name}/{part}")
                };
                relative(&child)?;
                let kind = entry.file_type()?;
                if kind.is_dir() {
                    pending.push((child.clone(), beneath(&self.root, &child, true)?, depth + 1));
                } else if kind.is_file() {
                    if !paths.insert(child) || paths.len() > MAX_FILES {
                        return fail("duplicate or excess leaf source member");
                    }
                } else {
                    return fail("linked or special leaf source member");
                }
            }
            if node(&directory.metadata()?)? != identity {
                return fail("leaf source directory changed during enumeration");
            }
            if !name.is_empty() {
                self.directories.insert(name, (directory, identity));
            }
        }
        self.recheck()?;
        Ok(paths)
    }
    fn recheck(&self) -> Result<()> {
        if node(&self.root.metadata()?)? != self.before
            || node(&open_absolute_directory(&self.named_path)?.metadata()?)? != self.before
        {
            return fail("held leaf source root changed");
        }
        for (name, (fd, before)) in &self.directories {
            if node(&fd.metadata()?)? != *before
                || node(&beneath(&self.root, name, true)?.metadata()?)? != *before
            {
                return fail("held leaf source directory changed");
            }
        }
        Ok(())
    }
}

#[derive(Serialize)]
struct StagedFile {
    relative_path: String,
    bytes: u64,
    sha256: String,
    identity: Node,
}
struct OutputTree {
    parent: File,
    root: File,
    basename: String,
    path: PathBuf,
    identity: Node,
}
fn mkdir(parent: &File, name: &str) -> Result<File> {
    relative(name)?;
    if name.contains('/') {
        return fail("mkdir requires a single component");
    }
    let c = CString::new(name)?;
    if unsafe { libc::mkdirat(parent.as_raw_fd(), c.as_ptr(), 0o700) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    parent.sync_all()?;
    beneath(parent, name, true)
}
fn same_identity(a: &Node, b: &Node) -> bool {
    (a.device, a.inode, a.mode, a.uid, a.gid) == (b.device, b.inode, b.mode, b.uid, b.gid)
}
impl OutputTree {
    fn create(path: &Path) -> Result<Self> {
        absolute(path)?;
        let parent_path = path.parent().ok_or("leaf output has no parent")?;
        let parent = open_absolute_directory(parent_path)?;
        let m = parent.metadata()?;
        if m.uid() != unsafe { libc::geteuid() } || !trusted_owner(&m) {
            return fail("fresh leaf staging must be below an ordinary-user-owned private parent");
        }
        let basename = path
            .file_name()
            .and_then(|x| x.to_str())
            .ok_or("invalid output name")?;
        let root = mkdir(&parent, basename)?;
        let identity = node(&root.metadata()?)?;
        Ok(Self {
            parent,
            root,
            basename: basename.into(),
            path: path.into(),
            identity,
        })
    }
    fn guard(&self) -> Result<()> {
        let named = beneath(&self.parent, &self.basename, true)?;
        let by_path = open_absolute_directory(&self.path)?;
        if !same_identity(&node(&self.root.metadata()?)?, &self.identity)
            || !same_identity(&node(&named.metadata()?)?, &self.identity)
            || !same_identity(&node(&by_path.metadata()?)?, &self.identity)
        {
            return fail("leaf staging root changed");
        }
        Ok(())
    }
    fn write(&self, name: &str, raw: &[u8]) -> Result<StagedFile> {
        relative(name)?;
        if raw.len() as u64 > MAX_FILE
            && !(name == "cohort/bin/held-namespace-entry"
                && raw.len() as u64 == FIXED_HELPER_BYTES
                && digest(raw) == FIXED_HELPER_SHA256)
        {
            return fail("leaf staged file exceeds bound");
        }
        self.guard()?;
        let mut directory = self.root.try_clone()?;
        let parts: Vec<_> = name.split('/').collect();
        for part in &parts[..parts.len() - 1] {
            directory = match beneath(&directory, part, true) {
                Ok(fd) => fd,
                Err(e) => {
                    // Only ENOENT permits mkdir; collisions and all other failures
                    // remain failures. Existing staged parents must be ours.
                    if e.downcast_ref::<std::io::Error>()
                        .and_then(|e| e.raw_os_error())
                        != Some(libc::ENOENT)
                    {
                        return Err(e);
                    }
                    mkdir(&directory, part)?
                }
            };
            let m = directory.metadata()?;
            if m.uid() != unsafe { libc::geteuid() } || m.mode() & 0o7777 != 0o700 {
                return fail("staged parent ownership or mode changed");
            }
        }
        let name_c = CString::new(*parts.last().ok_or("missing staged filename")?)?;
        let fd = unsafe {
            libc::openat(
                directory.as_raw_fd(),
                name_c.as_ptr(),
                libc::O_RDWR | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_CREAT | libc::O_EXCL,
                0o400,
            )
        };
        if fd < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        let mut file = unsafe { File::from_raw_fd(fd) };
        file.write_all(raw)?;
        file.sync_all()?;
        let identity = node(&file.metadata()?)?;
        if identity.links != 1
            || identity.uid != unsafe { libc::geteuid() }
            || identity.mode & 0o7777 != 0o400
            || read_all(&mut file, raw.len() as u64)? != raw
            || node(&file.metadata()?)? != identity
            || node(&beneath(&self.root, name, false)?.metadata()?)? != identity
        {
            return fail("leaf staged file failed independent readback");
        }
        directory.sync_all()?;
        self.guard()?;
        Ok(StagedFile {
            relative_path: name.into(),
            bytes: raw.len() as u64,
            sha256: digest(raw),
            identity,
        })
    }
    fn recheck(&self, rows: &[StagedFile]) -> Result<()> {
        self.guard()?;
        for row in rows {
            let mut file = beneath(&self.root, &row.relative_path, false)?;
            if node(&file.metadata()?)? != row.identity
                || digest(&read_all(&mut file, row.bytes)?) != row.sha256
                || node(&file.metadata()?)? != row.identity
            {
                return fail("leaf output changed after staging");
            }
        }
        self.root.sync_all()?;
        self.guard()
    }
}

fn check_bytes(raw: &[u8], pin: &Pin) -> Result<()> {
    if raw.len() as u64 != pin.bytes || digest(raw) != pin.sha256 {
        return fail("source-owned leaf recipe no longer matches its compiled input");
    }
    Ok(())
}
fn recipe() -> Result<Recipe> {
    let r: Recipe = serde_json::from_str(RECIPE)?;
    if r.schema != "droidloom.native-leaf-source-recovery-recipe.v1"
        || !r.source_only
        || r.installation_authorized
        || r.runtime_qualified
        || r.whole_app_business_accepted
        || r.expected_files != 476
        || r.expected_bytes != 7_097_884
        || r.behavior.len() != 14
        || r.expected_bytes > MAX_TOTAL
    {
        return fail("invalid source-only leaf recovery recipe");
    }
    check_bytes(CURRENT_CATALOG.as_bytes(), &r.current_catalog)?;
    check_bytes(CURRENT_SELECTION.as_bytes(), &r.current_selection)?;
    Ok(r)
}
fn expected_files(r: &Recipe, source: &SourceManifest) -> Result<BTreeMap<String, Pin>> {
    if source.schema != "pocket4-canonical-source-control-manifest-v1"
        || source.canonical_root != r.canonical_root
        || source.files.len() != 474
        || source.android_actions != 0
        || source.current_writes != 0
        || !source.source_only
        || source.runtime_qualified
        || source.native_helper_binary_deployed
    {
        return fail("historical source manifest is not the reviewed source-only set");
    }
    let mut out = BTreeMap::new();
    out.insert(r.source_manifest.path.clone(), r.source_manifest.clone());
    out.insert(r.validator.path.clone(), r.validator.clone());
    let prefix = format!("{}/", r.canonical_root);
    for row in &source.files {
        let rel = row
            .path
            .strip_prefix(&prefix)
            .ok_or("source escaped fixed historical cohort")?;
        relative(rel)?;
        let name = format!("bundle/{rel}");
        if row.bytes > MAX_FILE
            || !sha_shape(&row.sha256)
            || out.insert(name, row.clone()).is_some()
        {
            return fail("invalid or duplicate fixed source member");
        }
    }
    if out.len() != r.expected_files
        || out.values().map(|p| p.bytes).sum::<u64>() != r.expected_bytes
    {
        return fail("fixed leaf source count or total bytes changed");
    }
    Ok(out)
}
fn current_comparison(r: &Recipe, expected: &BTreeMap<String, Pin>) -> Result<Value> {
    let current: Vec<CurrentLeaf> = serde_json::from_str(CURRENT_CATALOG)?;
    let selection: Value = serde_json::from_str(CURRENT_SELECTION)?;
    if current.len() != 14
        || selection["selected_preparations"].as_array().map(Vec::len) != Some(14)
    {
        return fail("fixed current leaf selection shape changed");
    }
    let prefix = format!("{}/", r.canonical_root);
    let mut entries = BTreeMap::new();
    let mut preparations = Vec::new();
    for (index, row) in current.iter().enumerate() {
        if row.index != index
            || serde_json::to_value(&row.preparation)? != selection["selected_preparations"][index]
        {
            return fail("current selector and leaf source catalog differ");
        }
        for (kind, required) in [("entry", &row.entry), ("preparation", &row.preparation)] {
            let rel = required
                .path
                .strip_prefix(&prefix)
                .ok_or("current contract has another cohort")?;
            relative(rel)?;
            let actual = expected
                .get(&format!("bundle/{rel}"))
                .ok_or("historical source member missing")?;
            let matched = required == actual;
            let item =
                json!({"required":required,"recovered":actual,"exact_current_bytes":matched});
            if kind == "entry" {
                entries.insert(required.path.clone(), item);
            } else {
                preparations.push(item);
            }
        }
    }
    let matched_entries = entries
        .values()
        .filter(|r| r["exact_current_bytes"] == true)
        .count();
    let matched_preparations = preparations
        .iter()
        .filter(|r| r["exact_current_bytes"] == true)
        .count();
    // This reviewed recovery set deliberately cannot become current qualification.
    if entries.len() != 10 || matched_entries != 6 || matched_preparations != 0 {
        return fail("recovery boundary changed: review a new source-owned recipe");
    }
    Ok(
        json!({"unique_entries":entries.len(),"matched_current_entries":matched_entries,
        "preparations":preparations,"entries":entries,
        "matched_current_preparations":matched_preparations,
        "complete_current_source_contract":false}),
    )
}

/// The caller supplies locations only. Every accepted source byte is committed
/// by the compiled recipe and its fixed original manifest, never a caller hash.
pub(crate) fn materialize(input: &Path, output: &Path) -> Result<Value> {
    if unsafe { libc::getuid() } == 0
        || unsafe { libc::geteuid() } == 0
        || unsafe { libc::getuid() } != unsafe { libc::geteuid() }
    {
        return fail("materialize leaf sources as the ordinary build user");
    }
    absolute(input)?;
    absolute(output)?;
    if input.starts_with(output) || output.starts_with(input) {
        return fail("leaf input and fresh staging must be independent trees");
    }
    let r = recipe()?;
    let mut source = InputTree::open(input)?;
    let mut manifest = Held::open(&source.root, &r.source_manifest.path, &r.source_manifest)?;
    let raw = manifest.bytes()?;
    let parsed: SourceManifest = serde_json::from_slice(&raw)?;
    let expected = expected_files(&r, &parsed)?;
    if source.inventory()? != expected.keys().cloned().collect::<BTreeSet<_>>() {
        return fail("leaf source tree contains a missing or unlisted member");
    }
    let mut held = Vec::with_capacity(expected.len());
    for (name, pin) in &expected {
        held.push(Held::open(&source.root, name, pin)?);
    }
    manifest.recheck(&source.root)?;
    let comparison = current_comparison(&r, &expected)?;
    let destination = OutputTree::create(output)?;
    let mut outputs = Vec::new();
    let mut input_rows = Vec::new();
    for file in &mut held {
        let raw = file.bytes()?;
        outputs.push(destination.write(&format!("recovered/{}", file.name), &raw)?);
        input_rows.push(json!({"relative_path":file.name,"pin":file.pin,"identity":file.before}));
    }
    outputs.push(destination.write(
        "expected/current-leaf-sources.json",
        CURRENT_CATALOG.as_bytes(),
    )?);
    outputs.push(destination.write(
        "expected/current-selection.json",
        CURRENT_SELECTION.as_bytes(),
    )?);
    outputs.push(destination.write("expected/recovery-recipe.json", RECIPE.as_bytes())?);
    for file in &mut held {
        file.recheck(&source.root)?;
    }
    source.recheck()?;
    destination.recheck(&outputs)?;
    let report = json!({
        "schema":"droidloom.native-leaf-source-materialization.v1",
        "state":"RECOVERED_PUBLIC_SOURCES_CURRENT_CONTRACT_INCOMPLETE",
        "input_root":input,"output_root":output,
        "source_packet_provenance":r.source_packet_provenance,
        "source_manifest":r.source_manifest,
        "source_recipe":{"bytes":RECIPE.len(),"sha256":digest(RECIPE.as_bytes())},
        "input_files":input_rows,"output_files":outputs,
        "current_contract":comparison,"behavior":r.behavior,
        "input_file_count":held.len(),"input_bytes":r.expected_bytes,
        "source_bookends_equal":true,"output_full_readback":true,
        "source_only":true,"installable":false,"installation_performed":false,
        "leaf_execution_performed":false,"native_helper_binary_deployed":false,
        "Main_qualified":false,"runtime_qualified":false,
        "whole_app_business_accepted":false,"accepted_application_count":0,
        "historical_runtime_authority_transferred":false,"production_ready":false
    });
    let mut body = serde_json::to_vec_pretty(&report)?;
    body.push(b'\n');
    let report_file = destination.write(MANIFEST_NAME, &body)?;
    destination.recheck(&[report_file])?;
    for file in &mut held {
        file.recheck(&source.root)?;
    }
    source.recheck()?;
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{PermissionsExt, symlink};

    fn private_temp() -> tempfile::TempDir {
        let t = tempfile::tempdir().unwrap();
        fs::set_permissions(t.path(), fs::Permissions::from_mode(0o700)).unwrap();
        t
    }
    fn pin(name: &str, bytes: &[u8]) -> Pin {
        Pin {
            path: name.into(),
            bytes: bytes.len() as u64,
            sha256: digest(bytes),
        }
    }
    #[test]
    fn compiled_recipe_keeps_missing_current_sources_unqualified() {
        let r = recipe().unwrap();
        assert!(r.source_only);
        assert!(
            !r.installation_authorized && !r.runtime_qualified && !r.whole_app_business_accepted
        );
        assert_eq!(r.behavior.len(), 14);
    }
    #[test]
    fn source_locations_cannot_supply_an_expected_digest() {
        let r = recipe().unwrap();
        assert!(check_bytes(b"{}", &r.source_manifest).is_err());
        assert!(relative("../file").is_err());
        assert!(relative("/file").is_err());
        assert!(relative("a//b").is_err());
    }
    #[test]
    fn held_source_detects_same_bytes_at_a_replaced_name() {
        let t = private_temp();
        let p = t.path().join("source");
        fs::write(&p, b"same").unwrap();
        let root = open_absolute_directory(t.path()).unwrap();
        let mut f = Held::open(&root, "source", &pin("source", b"same")).unwrap();
        fs::rename(&p, t.path().join("retained")).unwrap();
        fs::write(&p, b"same").unwrap();
        assert!(f.recheck(&root).is_err());
    }
    #[test]
    fn source_links_are_rejected_even_with_matching_bytes() {
        let t = private_temp();
        fs::write(t.path().join("source"), b"same").unwrap();
        fs::hard_link(t.path().join("source"), t.path().join("hard")).unwrap();
        symlink("source", t.path().join("symbolic")).unwrap();
        let root = open_absolute_directory(t.path()).unwrap();
        assert!(Held::open(&root, "source", &pin("source", b"same")).is_err());
        assert!(Held::open(&root, "symbolic", &pin("symbolic", b"same")).is_err());
        assert!(InputTree::open(t.path()).unwrap().inventory().is_err());
    }
    #[test]
    fn staged_files_are_independent_and_existing_output_is_not_replaced() {
        let t = private_temp();
        let out = t.path().join("fresh");
        let tree = OutputTree::create(&out).unwrap();
        let row = tree
            .write("nested/source.py", b"print('source only')\n")
            .unwrap();
        tree.recheck(&[row]).unwrap();
        assert!(tree.write("nested/source.py", b"different").is_err());
        assert!(OutputTree::create(&out).is_err());
        assert_eq!(
            fs::read(out.join("nested/source.py")).unwrap(),
            b"print('source only')\n"
        );
    }
    #[test]
    fn output_bookend_rejects_post_write_change() {
        let t = private_temp();
        let out = t.path().join("fresh");
        let tree = OutputTree::create(&out).unwrap();
        let row = tree.write("source", b"old").unwrap();
        fs::set_permissions(out.join("source"), fs::Permissions::from_mode(0o600)).unwrap();
        fs::write(out.join("source"), b"new").unwrap();
        assert!(tree.recheck(&[row]).is_err());
    }
}
