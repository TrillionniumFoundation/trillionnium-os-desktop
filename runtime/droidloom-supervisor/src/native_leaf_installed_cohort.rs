//! Read-only custody of every installed output in the compiled native cohort.
//! This does not recover, install, relabel or execute any member. The input map,
//! collector path and root are source-owned; no caller supplies an allowlist.
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    ffi::CString,
    fs::{self, File},
    io::{Read, Seek, SeekFrom},
    os::{
        fd::{AsRawFd, FromRawFd},
        unix::{ffi::OsStrExt, fs::MetadataExt},
    },
    path::{Component, Path, PathBuf},
    time::Instant,
};
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
fn fail<T>(message: impl Into<String>) -> Result<T> {
    Err(message.into().into())
}
const ROOT: &str = "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2";
const RECIPE: &[u8] =
    include_bytes!("../../../android/manifest/native-application-leaf-cohort-r2.json");
const MAX_FILE: u64 = 2 * 1024 * 1024;
const FIXED_HELPER_BYTES: u64 = 3_972_024;
const FIXED_HELPER_SHA256: &str =
    "67cfd1c212e9f40ce3f0ff7be856a05f8189c674cbfa270757a672ea596a6c3f";
const MAX_TOTAL: u64 = 16 * 1024 * 1024;
const MAX_FILES: usize = 512;
const MAX_DIRS: usize = 256;
const MAX_DEPTH: usize = 16;
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Pin {
    path: String,
    bytes: u64,
    sha256: String,
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
    format!("{:x}", Sha256::digest(raw))
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
pub(crate) fn open_absolute_directory(path: &Path) -> Result<File> {
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
    crate::control::physical_qualification_channel::working_runtime::progress_reader(fd)
        .take(expected + 1).read_to_end(&mut raw)?;
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

fn installed_members_from(raw: &[u8]) -> Result<BTreeMap<String, Pin>> {
    let recipe: Value = serde_json::from_slice(raw)?;
    let members = recipe["members"]
        .as_array()
        .ok_or("compiled cohort members absent")?;
    if recipe["schema"] != "droidloom.native-leaf-cohort-source-recipe.v1"
        || recipe["cohort"] != "cp3a-20261126-apps-r2"
        || recipe["canonical_root"] != ROOT
        || recipe["output_file_count"] != 478
        || members.len() != 478
        || recipe["source_only"] != true
        || [
            "installation_authorized",
            "runtime_qualified",
            "Main_qualified",
            "whole_app_business_accepted",
            "production_ready",
        ]
        .iter()
        .any(|key| recipe[key] != false)
    {
        return fail("compiled installed cohort identity or scope differs");
    }
    let mut expected = BTreeMap::new();
    let mut total = 0u64;
    for member in members {
        let name = member["relative_path"]
            .as_str()
            .ok_or("compiled member name absent")?;
        relative(name)?;
        let pin: Pin = serde_json::from_value(member["output"].clone())?;
        let helper = name == "bin/held-namespace-entry";
        if pin.path != format!("{ROOT}/{name}")
            || !sha_shape(&pin.sha256)
            || (pin.bytes > MAX_FILE && !helper)
            || (helper && (pin.bytes != FIXED_HELPER_BYTES || pin.sha256 != FIXED_HELPER_SHA256))
            || member["fixed_binary_input"] != helper
            || member["historical_evidence_only"]
                != (name.starts_with("inputs/") || name.starts_with("evidence/"))
            || expected.insert(name.to_owned(), pin.clone()).is_some()
        {
            return fail("compiled installed member is not an exact unique bounded output");
        }
        total = total
            .checked_add(pin.bytes)
            .ok_or("compiled installed byte count overflow")?;
    }
    if total > MAX_TOTAL
        || recipe["output_bytes"] != total
        || !expected.contains_key("bin/held-namespace-entry")
        || !expected.contains_key("source/main/kernel_native_observation.py")
    {
        return fail("compiled installed output closure differs");
    }
    Ok(expected)
}
fn compiled_recipe_pin() -> Value {
    json!({"bytes": RECIPE.len(), "sha256": digest(RECIPE)})
}
pub(crate) struct InstalledCohort {
    tree: InputTree,
    files: BTreeMap<String, Held>,
}
fn before(end: Instant) -> Result<()> {
    crate::control::physical_qualification_channel::working_runtime::progress()?;
    if Instant::now() >= end {
        fail("installed cohort original budget expired")
    } else {
        Ok(())
    }
}
impl InstalledCohort {
    pub(crate) fn capture(end: Instant) -> Result<Self> {
        if unsafe { libc::getuid() } != 0
            || unsafe { libc::geteuid() } != 0
            || unsafe { libc::getgid() } != 0
            || unsafe { libc::getegid() } != 0
        {
            return fail("normal installed cohort observation requires the original root operator");
        }
        before(end)?;
        let expected = installed_members_from(RECIPE)?;
        let mut tree = InputTree::open(Path::new(ROOT))?;
        if tree.inventory()? != expected.keys().cloned().collect() {
            return fail("normal installed cohort has missing or extra members");
        }
        for fd in std::iter::once(&tree.root).chain(tree.directories.values().map(|v| &v.0)) {
            let m = fd.metadata()?;
            if m.uid() != 0 || m.gid() != 0 || m.mode() & 0o7777 != 0o755 {
                return fail("normal installed cohort directory owner or mode differs");
            }
        }
        let mut files = BTreeMap::new();
        for (name, pin) in expected {
            before(end)?;
            let file = Held::open(&tree.root, &name, &pin)?;
            let mode = if name == "bin/held-namespace-entry" {
                0o755
            } else {
                0o444
            };
            if file.before.uid != 0 || file.before.gid != 0 || file.before.mode & 0o7777 != mode {
                return fail("normal installed cohort member owner or mode differs");
            }
            files.insert(name, file);
        }
        tree.recheck()?;
        before(end)?;
        Ok(Self { tree, files })
    }
    pub(crate) fn recheck(&mut self, end: Instant) -> Result<()> {
        before(end)?;
        self.tree.recheck()?;
        for file in self.files.values_mut() {
            before(end)?;
            file.recheck(&self.tree.root)?;
        }
        self.tree.recheck()?;
        before(end)
    }
    pub(crate) fn recipe(&self) -> Value {
        compiled_recipe_pin()
    }
    pub(crate) fn collector(&self) -> Result<&Path> {
        const NAME: &str = "source/main/kernel_native_observation.py";
        let pin = &self
            .files
            .get(NAME)
            .ok_or("compiled normal baseline collector missing")?
            .pin;
        if pin.path != format!("{}/{NAME}", ROOT) {
            return fail("fixed baseline collector differs");
        }
        Ok(Path::new(&pin.path))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{PermissionsExt, symlink};
    #[test]
    fn installed_capture_requires_every_compiled_output_and_exact_recipe_pin() {
        let members = installed_members_from(RECIPE).unwrap();
        assert_eq!(members.len(), 478);
        let recipe: Value = serde_json::from_slice(RECIPE).unwrap();
        let total: u64 = members.values().map(|pin| pin.bytes).sum();
        assert_eq!(recipe["output_bytes"], total);
        assert_eq!(
            compiled_recipe_pin(),
            json!({"bytes": RECIPE.len(), "sha256": digest(RECIPE)})
        );
        for row in recipe["members"].as_array().unwrap() {
            let name = row["relative_path"].as_str().unwrap();
            assert_eq!(serde_json::to_value(&members[name]).unwrap(), row["output"]);
        }
        assert_eq!(
            members["bin/held-namespace-entry"].sha256,
            FIXED_HELPER_SHA256
        );
    }
    #[test]
    fn installed_capture_rejects_partial_duplicate_foreign_and_claimed_outputs() {
        let original: Value = serde_json::from_slice(RECIPE).unwrap();
        let reject = |value: &Value| {
            assert!(installed_members_from(&serde_json::to_vec(value).unwrap()).is_err())
        };
        let mut bad = original.clone();
        bad["members"].as_array_mut().unwrap().pop();
        reject(&bad);
        let mut bad = original.clone();
        bad["members"][1] = bad["members"][0].clone();
        reject(&bad);
        let mut bad = original.clone();
        bad["members"][0]["output"]["path"] = json!("/tmp/foreign");
        reject(&bad);
        let mut bad = original.clone();
        bad["members"][0]["output"]["caller_passed"] = json!(true);
        reject(&bad);
        let mut bad = original.clone();
        bad["members"][0]["output"]["sha256"] = json!("X".repeat(64));
        reject(&bad);
        let mut bad = original.clone();
        bad["output_bytes"] = json!(1);
        reject(&bad);
        for key in [
            "installation_authorized",
            "runtime_qualified",
            "Main_qualified",
            "whole_app_business_accepted",
            "production_ready",
        ] {
            let mut bad = original.clone();
            bad[key] = json!(true);
            reject(&bad);
        }
    }
    #[test]
    fn installed_held_readback_rejects_replacement_mutation_and_links() {
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("member.py");
        fs::write(&path, b"source\n").unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o444)).unwrap();
        let tree = InputTree::open(temp.path()).unwrap();
        let pin = Pin {
            path: path.to_string_lossy().into_owned(),
            bytes: 7,
            sha256: digest(b"source\n"),
        };
        let mut held = Held::open(&tree.root, "member.py", &pin).unwrap();
        held.recheck(&tree.root).unwrap();
        fs::rename(&path, temp.path().join("old.py")).unwrap();
        fs::write(&path, b"source\n").unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o444)).unwrap();
        assert!(held.recheck(&tree.root).is_err());
        let mut replacement = Held::open(&tree.root, "member.py", &pin).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        fs::write(&path, b"change\n").unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o444)).unwrap();
        assert!(replacement.recheck(&tree.root).is_err());
        fs::remove_file(&path).unwrap();
        symlink("old.py", &path).unwrap();
        assert!(Held::open(&tree.root, "member.py", &pin).is_err());
        fs::remove_file(&path).unwrap();
        fs::hard_link(temp.path().join("old.py"), &path).unwrap();
        assert!(Held::open(&tree.root, "member.py", &pin).is_err());
    }
}
