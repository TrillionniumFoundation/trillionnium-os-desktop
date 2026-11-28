//! Install only the compiled cohort into its fixed canonical root.
//!
//! This publishes immutable code/data. It does not select a runtime, execute a
//! leaf, create Main authority, start a service, or accept any application gate.
use super::*;
#[cfg(test)]
use std::os::unix::fs::PermissionsExt;

const PARENT: &str = "/usr/libexec/droidloom/native-application-leaves/cohorts";

fn errno_is(error: &(dyn std::error::Error + 'static), value: i32) -> bool {
    error
        .downcast_ref::<std::io::Error>()
        .and_then(|e| e.raw_os_error())
        == Some(value)
}
fn own_directory(fd: &File) -> Result<Node> {
    let m = fd.metadata()?;
    if !m.is_dir()
        || m.uid() != unsafe { libc::geteuid() }
        || m.gid() != unsafe { libc::getegid() }
        || m.mode() & 0o7022 != 0
    {
        return fail("cohort publication requires an owned, sealed ordinary directory");
    }
    node(&m)
}
fn chmod(fd: &File, mode: u32) -> Result<()> {
    if unsafe { libc::fchmod(fd.as_raw_fd(), mode) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    Ok(())
}
fn exact_parent() -> Result<File> {
    // Only the application-specific suffix can be created. Existing system
    // ancestors are inspected through held descriptors, never followed links.
    let mut current = File::open("/")?;
    own_directory(&current)?;
    for (index, part) in [
        "usr",
        "libexec",
        "droidloom",
        "native-application-leaves",
        "cohorts",
    ]
    .iter()
    .enumerate()
    {
        let next = match beneath(&current, part, true) {
            Ok(fd) => fd,
            Err(error) if index >= 2 && errno_is(error.as_ref(), libc::ENOENT) => {
                let fd = mkdir(&current, part)?;
                chmod(&fd, 0o755)?;
                fd.sync_all()?;
                current.sync_all()?;
                fd
            }
            Err(error) => return Err(error),
        };
        own_directory(&next)?;
        current = next;
    }
    let named = open_absolute_directory(Path::new(PARENT))?;
    if node(&named.metadata()?)? != node(&current.metadata()?)? {
        return fail("fixed cohort parent changed");
    }
    Ok(current)
}

struct Written {
    name: String,
    file: File,
    created: Node,
    complete: Option<Node>,
    pin: Pin,
    mode: u32,
}
struct Pending {
    parent: File,
    parent_path: PathBuf,
    parent_identity: Node,
    name: String,
    root: File,
    identity: Node,
    directories: BTreeMap<String, File>,
    files: Vec<Written>,
    published: bool,
}
impl Pending {
    fn create(parent: &File, path: &Path) -> Result<Self> {
        let parent_identity = own_directory(parent)?;
        match beneath(parent, cohort::COHORT, true) {
            Ok(_) => return fail("canonical cohort already exists; replacement is forbidden"),
            Err(error) if errno_is(error.as_ref(), libc::ENOENT) => {}
            Err(error) => return Err(error),
        }
        let mut random = [0u8; 16];
        let n = unsafe { libc::getrandom(random.as_mut_ptr().cast(), random.len(), 0) };
        if n != random.len() as isize {
            return fail("cohort staging random name unavailable");
        }
        let name = format!(".{}-staging-{}", cohort::COHORT, hex::encode(random));
        let root = mkdir(parent, &name)?;
        let identity = own_directory(&root)?;
        Ok(Self {
            parent: parent.try_clone()?,
            parent_path: path.into(),
            parent_identity,
            name,
            root,
            identity,
            directories: BTreeMap::new(),
            files: Vec::new(),
            published: false,
        })
    }
    fn guard(&self) -> Result<()> {
        let now = own_directory(&self.parent)?;
        if !same_identity(&now, &self.parent_identity)
            || !same_identity(
                &node(&open_absolute_directory(&self.parent_path)?.metadata()?)?,
                &self.parent_identity,
            )
        {
            return fail("cohort publication parent was replaced");
        }
        let name = if self.published {
            cohort::COHORT
        } else {
            &self.name
        };
        let named = beneath(&self.parent, name, true)?;
        if !same_identity(&node(&self.root.metadata()?)?, &self.identity)
            || !same_identity(&node(&named.metadata()?)?, &self.identity)
        {
            return fail("owned cohort staging root was replaced");
        }
        Ok(())
    }
    fn write(&mut self, name: &str, raw: &[u8], pin: &Pin) -> Result<()> {
        relative(name)?;
        check_bytes(raw, pin)?;
        self.guard()?;
        let parts: Vec<_> = name.split('/').collect();
        let mut parent = self.root.try_clone()?;
        let mut path = String::new();
        for part in &parts[..parts.len() - 1] {
            if !path.is_empty() {
                path.push('/');
            }
            path.push_str(part);
            parent = if let Some(fd) = self.directories.get(&path) {
                fd.try_clone()?
            } else {
                let next = mkdir(&parent, part)?;
                self.directories.insert(path.clone(), next.try_clone()?);
                next
            };
            own_directory(&parent)?;
        }
        let last = CString::new(*parts.last().ok_or("cohort member lacks basename")?)?;
        let fd = unsafe {
            libc::openat(
                parent.as_raw_fd(),
                last.as_ptr(),
                libc::O_RDWR | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_CREAT | libc::O_EXCL,
                0o400,
            )
        };
        if fd < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        let file = unsafe { File::from_raw_fd(fd) };
        let created = node(&file.metadata()?)?;
        let mode = if name == "bin/held-namespace-entry" {
            0o755
        } else {
            0o444
        };
        self.files.push(Written {
            name: name.into(),
            file,
            created,
            complete: None,
            pin: pin.clone(),
            mode,
        });
        let entry = self.files.last_mut().ok_or("owned output disappeared")?;
        entry.file.write_all(raw)?;
        chmod(&entry.file, mode)?;
        entry.file.sync_all()?;
        let complete = node(&entry.file.metadata()?)?;
        if complete.uid != unsafe { libc::geteuid() }
            || complete.gid != unsafe { libc::getegid() }
            || complete.links != 1
            || complete.mode & 0o7777 != mode
            || read_all(&mut entry.file, pin.bytes)? != raw
            || node(&entry.file.metadata()?)? != complete
            || node(&beneath(&self.root, name, false)?.metadata()?)? != complete
        {
            return fail("cohort staged member failed full held readback");
        }
        entry.complete = Some(complete);
        parent.sync_all()?;
        self.guard()
    }
    fn finish_modes(&mut self) -> Result<()> {
        for fd in self.directories.values() {
            chmod(fd, 0o755)?;
            fd.sync_all()?;
        }
        chmod(&self.root, 0o755)?;
        self.root.sync_all()?;
        self.identity = own_directory(&self.root)?;
        self.guard()
    }
    fn verify(&mut self, expected: &BTreeMap<String, Pin>) -> Result<Vec<Value>> {
        self.guard()?;
        if self.files.len() != expected.len() {
            return fail("cohort publication is incomplete");
        }
        let mut paths = BTreeSet::new();
        let mut pending = vec![(String::new(), self.root.try_clone()?, 0usize)];
        let mut directories = 0usize;
        while let Some((prefix, fd, depth)) = pending.pop() {
            if depth > MAX_DEPTH || directories > MAX_DIRS {
                return fail("cohort output inventory bound");
            }
            directories += 1;
            let m = fd.metadata()?;
            if m.uid() != unsafe { libc::geteuid() }
                || m.gid() != unsafe { libc::getegid() }
                || m.mode() & 0o7777 != 0o755
            {
                return fail("cohort directory mode or owner changed");
            }
            for ent in fs::read_dir(format!("/proc/self/fd/{}", fd.as_raw_fd()))? {
                let ent = ent?;
                let part = ent
                    .file_name()
                    .into_string()
                    .map_err(|_| "invalid output basename")?;
                relative(&part)?;
                let name = if prefix.is_empty() {
                    part
                } else {
                    format!("{prefix}/{part}")
                };
                if ent.file_type()?.is_dir() {
                    pending.push((name.clone(), beneath(&self.root, &name, true)?, depth + 1));
                } else if ent.file_type()?.is_file() {
                    if !paths.insert(name) {
                        return fail("duplicate output name");
                    }
                } else {
                    return fail("linked or special installed cohort member");
                }
            }
        }
        if paths != expected.keys().cloned().collect() {
            return fail("installed member set differs from compiled recipe");
        }
        let mut rows = Vec::new();
        for written in &mut self.files {
            let complete = written
                .complete
                .as_ref()
                .ok_or("incomplete owned cohort file")?;
            if node(&written.file.metadata()?)? != *complete
                || node(&beneath(&self.root, &written.name, false)?.metadata()?)? != *complete
                || digest(&read_all(&mut written.file, written.pin.bytes)?) != written.pin.sha256
                || node(&written.file.metadata()?)? != *complete
            {
                return fail("installed cohort full bytes or inode changed");
            }
            rows.push(json!({"relative_path":written.name,"pin":written.pin,"identity":complete,"mode":written.mode}));
        }
        self.guard()?;
        Ok(rows)
    }
    fn publish(&mut self) -> Result<()> {
        self.guard()?;
        let old = CString::new(self.name.as_str())?;
        let new = CString::new(cohort::COHORT)?;
        if unsafe {
            libc::syscall(
                libc::SYS_renameat2,
                self.parent.as_raw_fd(),
                old.as_ptr(),
                self.parent.as_raw_fd(),
                new.as_ptr(),
                libc::RENAME_NOREPLACE,
            )
        } != 0
        {
            return Err(std::io::Error::last_os_error().into());
        }
        self.published = true;
        // Rename changes the owned directory's ctime. Establish its new exact
        // state only after proving that this is still the same installed inode.
        let after = node(&self.root.metadata()?)?;
        if !same_identity(&after, &self.identity) {
            return fail("atomic publication replaced the owned inode");
        }
        self.identity = after;
        self.parent.sync_all()?;
        self.guard()
    }
    fn cleanup(&mut self) -> Vec<String> {
        if self.published {
            return Vec::new();
        }
        let mut errors = Vec::new();
        if let Err(e) = self.guard() {
            errors.push(format!("cleanup custody: {e}"));
            return errors;
        }
        for row in self.files.iter().rev() {
            let attempt = (|| -> Result<()> {
                let named = beneath(&self.root, &row.name, false)?;
                let held = node(&row.file.metadata()?)?;
                let current = node(&named.metadata()?)?;
                if (held.device, held.inode) != (row.created.device, row.created.inode)
                    || (current.device, current.inode) != (row.created.device, row.created.inode)
                {
                    return fail("refusing cleanup of an unowned file");
                }
                let n = CString::new(row.name.as_str())?;
                if unsafe { libc::unlinkat(self.root.as_raw_fd(), n.as_ptr(), 0) } != 0 {
                    return Err(std::io::Error::last_os_error().into());
                }
                Ok(())
            })();
            if let Err(e) = attempt {
                errors.push(format!("{}: {e}", row.name));
            }
        }
        let mut names: Vec<_> = self.directories.keys().cloned().collect();
        names.sort_by_key(|n| std::cmp::Reverse(n.split('/').count()));
        for name in names {
            let attempt = (|| -> Result<()> {
                let held = self
                    .directories
                    .get(&name)
                    .ok_or("owned directory missing")?;
                let named = beneath(&self.root, &name, true)?;
                if !same_identity(&node(&held.metadata()?)?, &node(&named.metadata()?)?) {
                    return fail("refusing cleanup of an unowned directory");
                }
                let n = CString::new(name.as_str())?;
                if unsafe { libc::unlinkat(self.root.as_raw_fd(), n.as_ptr(), libc::AT_REMOVEDIR) }
                    != 0
                {
                    return Err(std::io::Error::last_os_error().into());
                }
                Ok(())
            })();
            if let Err(e) = attempt {
                errors.push(format!("{name}: {e}"));
            }
        }
        if errors.is_empty() {
            let n = CString::new(self.name.as_str()).expect("generated staging basename");
            if unsafe { libc::unlinkat(self.parent.as_raw_fd(), n.as_ptr(), libc::AT_REMOVEDIR) }
                != 0
            {
                errors.push(format!("staging root: {}", std::io::Error::last_os_error()));
            }
        }
        if let Err(e) = self.parent.sync_all() {
            errors.push(format!("cleanup sync: {e}"));
        }
        errors
    }
}

fn publish_at(
    input: &Path,
    parent: &File,
    parent_path: &Path,
    expected: &BTreeMap<String, Pin>,
) -> Result<Value> {
    let mut source = InputTree::open(input)?;
    if source.inventory()? != expected.keys().cloned().collect() {
        return fail("cohort source inventory differs");
    }
    let mut held = BTreeMap::new();
    for (name, pin) in expected {
        held.insert(name.clone(), Held::open(&source.root, name, pin)?);
    }
    source.recheck()?;
    let mut pending = Pending::create(parent, parent_path)?;
    let operation = (|| -> Result<Value> {
        for (name, pin) in expected {
            let raw = held.get_mut(name).ok_or("unheld cohort source")?.bytes()?;
            pending.write(name, &raw, pin)?;
        }
        pending.finish_modes()?;
        pending.verify(expected)?;
        for file in held.values_mut() {
            file.recheck(&source.root)?;
        }
        source.recheck()?;
        pending.publish()?;
        let rows = pending.verify(expected)?;
        for file in held.values_mut() {
            file.recheck(&source.root)?;
        }
        source.recheck()?;
        Ok(
            json!({"schema":"droidloom.native-leaf-cohort-installation.v1",
            "cohort":cohort::COHORT,"canonical_root":cohort::ROOT,"source":input,
            "source_recipe":cohort::compiled_recipe_pin(),"installed_members":rows,
            "member_count":expected.len(),"source_full_bookends_equal":true,"installed_full_readback":true,
            "atomic_no_replace_publication":true,"installed":true,"leaf_executed":false,
            "service_enabled":false,"runtime_selected":false,"Main_qualified":false,
            "whole_app_business_accepted":false,"accepted_application_count":0,
            "runtime_qualified":false,"production_ready":false}),
        )
    })();
    match operation {
        Ok(result) => Ok(result),
        Err(error) => {
            let cleanup = pending.cleanup();
            fail(format!(
                "cohort publication failed: {error}; unpublished-owned cleanup errors: {cleanup:?}"
            ))
        }
    }
}

/// The production entry has no caller-selected destination, owner, mode or
/// member digest. Root may publish only this compiled immutable cohort.
pub(crate) fn install(input: &Path) -> Result<Value> {
    if unsafe { libc::getuid() } != 0
        || unsafe { libc::geteuid() } != 0
        || unsafe { libc::getgid() } != 0
        || unsafe { libc::getegid() } != 0
    {
        return fail("canonical cohort installation requires the original root operator");
    }
    absolute(input)?;
    let root = Path::new(cohort::ROOT);
    if input.starts_with(root) || root.starts_with(input) {
        return fail("independent cohort source required");
    }
    let expected = cohort::installed_members()?;
    let parent = exact_parent()?;
    publish_at(input, &parent, Path::new(PARENT), &expected)
}

fn publish_package_at(
    path: &Path,
    parent: &File,
    parent_path: &Path,
    expected: &BTreeMap<String, Pin>,
) -> Result<Value> {
    let mut archive = super::package::PublicArchive::open(path, expected)?;
    let rows = super::package::verify(&archive.raw, expected)?;
    let mut pending = Pending::create(parent, parent_path)?;
    let operation = (|| -> Result<Value> {
        for (name, range) in &rows {
            pending.write(
                name,
                &archive.raw[range.clone()],
                expected.get(name).ok_or("compiled member missing")?,
            )?;
        }
        pending.finish_modes()?;
        pending.verify(expected)?;
        archive.recheck()?;
        pending.publish()?;
        let installed = pending.verify(expected)?;
        archive.recheck()?;
        Ok(
            json!({"schema":"droidloom.native-leaf-cohort-installation.v1",
            "cohort":cohort::COHORT,"canonical_root":cohort::ROOT,"public_archive":archive.evidence(),
            "source_recipe":cohort::compiled_recipe_pin(),"installed_members":installed,
            "member_count":expected.len(),"source_full_bookends_equal":true,"installed_full_readback":true,
            "compiled_members_only":true,"root_owned_stage_verified_before_publication":true,
            "atomic_no_replace_publication":true,"installed":true,"leaf_executed":false,
            "service_enabled":false,"runtime_selected":false,"Main_qualified":false,
            "whole_app_business_accepted":false,"accepted_application_count":0,
            "runtime_qualified":false,"production_ready":false}),
        )
    })();
    match operation {
        Ok(value) => Ok(value),
        Err(error) => {
            let cleanup = pending.cleanup();
            fail(format!(
                "cohort package publication failed: {error}; unpublished-owned cleanup errors: {cleanup:?}"
            ))
        }
    }
}
/// A public archive can supply bytes, never its own authority table. Its entire
/// regular-only representation and every payload must match the compiled recipe.
pub(crate) fn install_package(path: &Path) -> Result<Value> {
    if unsafe { libc::getuid() } != 0
        || unsafe { libc::geteuid() } != 0
        || unsafe { libc::getgid() } != 0
        || unsafe { libc::getegid() } != 0
    {
        return fail("canonical cohort installation requires the original root operator");
    }
    absolute(path)?;
    if path.starts_with(cohort::ROOT) || Path::new(cohort::ROOT).starts_with(path) {
        return fail("independent public package required");
    }
    let expected = cohort::installed_members()?;
    // Reject malformed public bytes before even creating the fixed parent suffix.
    let mut admitted = super::package::PublicArchive::open(path, &expected)?;
    let parent = exact_parent()?;
    admitted.recheck()?;
    // The second held descriptor is independently checked; its accepted member
    // identity remains entirely source-owned. The first FD spans publication.
    let result = publish_package_at(path, &parent, Path::new(PARENT), &expected)?;
    admitted.recheck()?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;
    fn fixture() -> (tempfile::TempDir, PathBuf, PathBuf, BTreeMap<String, Pin>) {
        let tmp = tempfile::tempdir().unwrap();
        let source = tmp.path().join("source");
        let parent = tmp.path().join("cohorts");
        fs::create_dir(&source).unwrap();
        fs::create_dir(&parent).unwrap();
        fs::set_permissions(&source, fs::Permissions::from_mode(0o700)).unwrap();
        fs::set_permissions(&parent, fs::Permissions::from_mode(0o700)).unwrap();
        fs::create_dir(source.join("source")).unwrap();
        fs::set_permissions(source.join("source"), fs::Permissions::from_mode(0o700)).unwrap();
        let raw = b"reviewed source\n";
        fs::write(source.join("source/fixed.py"), raw).unwrap();
        fs::set_permissions(
            source.join("source/fixed.py"),
            fs::Permissions::from_mode(0o400),
        )
        .unwrap();
        let pins = BTreeMap::from([(
            "source/fixed.py".into(),
            Pin {
                path: format!("{}/source/fixed.py", cohort::ROOT),
                bytes: raw.len() as u64,
                sha256: digest(raw),
            },
        )]);
        (tmp, source, parent, pins)
    }
    #[test]
    fn atomic_publication_preserves_fixed_content_modes_and_existing_cohort() {
        let (_tmp, source, parent, pins) = fixture();
        let held = open_absolute_directory(&parent).unwrap();
        let result = publish_at(&source, &held, &parent, &pins).unwrap();
        assert_eq!(result["member_count"], 1);
        let installed = parent.join(cohort::COHORT).join("source/fixed.py");
        assert_eq!(fs::read(&installed).unwrap(), b"reviewed source\n");
        assert_eq!(
            fs::symlink_metadata(&installed)
                .unwrap()
                .permissions()
                .mode()
                & 0o7777,
            0o444
        );
        assert!(publish_at(&source, &held, &parent, &pins).is_err());
        assert_eq!(fs::read(&installed).unwrap(), b"reviewed source\n");
        assert_eq!(fs::read_dir(&parent).unwrap().count(), 1);
    }
    #[test]
    fn altered_linked_and_extra_sources_never_publish() {
        for case in 0..4 {
            let (_tmp, source, parent, pins) = fixture();
            let path = source.join("source/fixed.py");
            match case {
                0 => {
                    fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
                    fs::write(&path, b"changed source\n").unwrap();
                }
                1 => {
                    fs::rename(&path, source.join("kept")).unwrap();
                    symlink("../kept", &path).unwrap();
                }
                2 => {
                    fs::hard_link(&path, _tmp.path().join("linked")).unwrap();
                }
                _ => {
                    fs::write(source.join("extra"), b"extra").unwrap();
                }
            }
            let held = open_absolute_directory(&parent).unwrap();
            assert!(publish_at(&source, &held, &parent, &pins).is_err());
            assert_eq!(fs::read_dir(&parent).unwrap().count(), 0);
        }
    }
    #[test]
    fn failed_owned_staging_cleanup_preserves_unrelated_parent_files() {
        let (_tmp, _source, parent, _pins) = fixture();
        fs::write(parent.join("unrelated"), b"keep").unwrap();
        let held = open_absolute_directory(&parent).unwrap();
        let mut pending = Pending::create(&held, &parent).unwrap();
        let pin = Pin {
            path: format!("{}/source/a", cohort::ROOT),
            bytes: 1,
            sha256: digest(b"a"),
        };
        pending.write("source/a", b"a", &pin).unwrap();
        assert!(pending.write("source/a", b"a", &pin).is_err());
        assert!(pending.cleanup().is_empty());
        assert_eq!(fs::read(parent.join("unrelated")).unwrap(), b"keep");
        assert_eq!(fs::read_dir(&parent).unwrap().count(), 1);
    }

    #[test]
    fn cohort_package_import_publishes_only_compiled_members_and_preserves_conflicts() {
        for corrupt in [false, true] {
            let (_tmp, source, parent, pins) = fixture();
            let outputs = pins
                .keys()
                .map(|n| Ok((n.clone(), fs::read(source.join(n))?)))
                .collect::<Result<BTreeMap<String, Vec<u8>>>>()
                .unwrap();
            let mut raw = super::super::package::build(&outputs, &pins).unwrap();
            if corrupt {
                raw[512] ^= 1;
            }
            let path = _tmp.path().join("COHORT.tar");
            fs::write(&path, raw).unwrap();
            let held = open_absolute_directory(&parent).unwrap();
            let result = publish_package_at(&path, &held, &parent, &pins);
            if corrupt {
                assert!(result.is_err());
                assert_eq!(fs::read_dir(&parent).unwrap().count(), 0);
            } else {
                assert_eq!(result.unwrap()["compiled_members_only"], true);
                let installed = parent.join(cohort::COHORT).join("source/fixed.py");
                assert_eq!(fs::read(&installed).unwrap(), b"reviewed source\n");
                assert_eq!(fs::metadata(&installed).unwrap().uid(), unsafe {
                    libc::geteuid()
                });
                assert!(publish_package_at(&path, &held, &parent, &pins).is_err());
                assert_eq!(fs::read_dir(&parent).unwrap().count(), 1);
            }
        }
    }
}
