//! Descriptor-bound label changes. Source admission and the sealed once owner
//! are the only future callers of the mutation core; this module exposes no
//! physical mutation command and does not infer authority from a receipt flag.
use crate::{Result, ensure, fs, model::Identity};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, ffi::CString, fs::File, os::fd::AsRawFd};

const LABEL: &str = "security.selinux";
const MAX_NAMES: usize = 65_536;
const MAX_VALUE: usize = 65_536;
const MAX_TOTAL: usize = 8_388_608;

// The selected kernel's empty-path xattrat path rejects O_PATH. Its procfd
// magic link instead jumps directly to the held dentry, including a symlink,
// without following that symlink's target. Only this fixed current-process
// descriptor bridge is allowed; original pathnames never enter an xattr call.
struct DescriptorAlias<'a> {
    directory: File,
    file: &'a File,
    name: String,
    path: String,
}
impl<'a> DescriptorAlias<'a> {
    fn new(file: &'a File) -> Result<Self> {
        let directory = File::from(rustix::fs::open(
            "/proc/self/fd",
            rustix::fs::OFlags::RDONLY
                | rustix::fs::OFlags::DIRECTORY
                | rustix::fs::OFlags::CLOEXEC,
            rustix::fs::Mode::empty(),
        )?);
        ensure(
            rustix::fs::fstatfs(&directory)?.f_type as u64 == 0x9fa0,
            "descriptor bridge is not the actual proc filesystem",
        )?;
        let name = file.as_raw_fd().to_string();
        let value = Self {
            directory,
            file,
            path: format!("/proc/self/fd/{name}"),
            name,
        };
        value.validate()?;
        Ok(value)
    }
    fn validate(&self) -> Result<()> {
        let held = fs::stat(self.file)?;
        let named = fs::identity(&rustix::fs::statat(
            &self.directory,
            self.name.as_str(),
            rustix::fs::AtFlags::empty(),
        )?);
        let current = File::from(rustix::fs::open(
            "/proc/self/fd",
            rustix::fs::OFlags::RDONLY
                | rustix::fs::OFlags::DIRECTORY
                | rustix::fs::OFlags::CLOEXEC,
            rustix::fs::Mode::empty(),
        )?);
        let current_proc = fs::stat(&current)?;
        let held_proc = fs::stat(&self.directory)?;
        ensure(
            (
                current_proc.dev,
                current_proc.ino,
                current_proc.mode,
                current_proc.uid,
                current_proc.gid,
            ) == (
                held_proc.dev,
                held_proc.ino,
                held_proc.mode,
                held_proc.uid,
                held_proc.gid,
            ),
            "fixed procfd directory changed inode or custody",
        )?;
        ensure(
            named == held,
            &format!("fixed procfd target identity differs: held={held:?} named={named:?}"),
        )
    }
}
fn list(file: &File, value: &mut [u8]) -> Result<usize> {
    let alias = DescriptorAlias::new(file)?;
    let result = if value.is_empty() {
        rustix::fs::listxattr_query(alias.path.as_str())?
    } else {
        rustix::fs::listxattr(alias.path.as_str(), value)?
    };
    alias.validate()?;
    Ok(result)
}
fn get(file: &File, name: &str, value: &mut [u8]) -> Result<usize> {
    let alias = DescriptorAlias::new(file)?;
    let name = CString::new(name)?;
    let result = if value.is_empty() {
        rustix::fs::getxattr_query(alias.path.as_str(), name.as_c_str())?
    } else {
        rustix::fs::getxattr(alias.path.as_str(), name.as_c_str(), value)?
    };
    alias.validate()?;
    Ok(result)
}
fn set(file: &File, name: &str, value: Option<&[u8]>) -> Result<()> {
    let alias = DescriptorAlias::new(file)?;
    let name = CString::new(name)?;
    match value {
        Some(value) => rustix::fs::setxattr(
            alias.path.as_str(),
            name.as_c_str(),
            value,
            rustix::fs::XattrFlags::empty(),
        )?,
        None => rustix::fs::removexattr(alias.path.as_str(), name.as_c_str())?,
    }
    alias.validate()
}

fn attributes(file: &File) -> Result<BTreeMap<String, Vec<u8>>> {
    let before = fs::stat(file)?;
    let count = list(file, &mut [])?;
    ensure(count <= MAX_NAMES, "inode has too many xattr name bytes")?;
    let mut names = vec![0; count];
    ensure(
        list(file, &mut names)? == count,
        "xattr name inventory changed",
    )?;
    ensure(
        names.is_empty() || names.last() == Some(&0),
        "unterminated xattr name",
    )?;
    let mut rows = BTreeMap::new();
    let mut total = 0usize;
    for raw in names.split(|v| *v == 0).filter(|v| !v.is_empty()) {
        let name = std::str::from_utf8(raw)?.to_owned();
        let count = get(file, &name, &mut [])?;
        ensure(count <= MAX_VALUE, "inode xattr exceeds the Linux bound")?;
        total = total.checked_add(count).ok_or("xattr size overflow")?;
        ensure(
            total <= MAX_TOTAL,
            "inode xattr inventory exceeds eight MiB",
        )?;
        let mut value = vec![0; count];
        ensure(
            get(file, &name, &mut value)? == count,
            "inode xattr value changed",
        )?;
        ensure(rows.insert(name, value).is_none(), "duplicate xattr name")?;
    }
    let mut again = vec![0; names.len()];
    ensure(
        list(file, &mut again)? == names.len() && again == names && fs::stat(file)? == before,
        "inode identity or xattr names changed during the descriptor readback",
    )?;
    Ok(rows)
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Snapshot {
    identity: Identity,
    attributes: BTreeMap<String, Vec<u8>>,
}
fn snapshot(file: &File) -> Result<Snapshot> {
    let identity = fs::stat(file)?;
    let attributes = attributes(file)?;
    ensure(fs::stat(file)? == identity, "label snapshot inode changed")?;
    Ok(Snapshot {
        identity,
        attributes,
    })
}
fn only_ctime_changed(a: &Identity, b: &Identity) -> bool {
    let mut actual = b.clone();
    actual.ctime_sec = a.ctime_sec;
    actual.ctime_nsec = a.ctime_nsec;
    actual == *a
}

// This is deliberately not Deserialize/Clone and has no public constructor.
// Once wiring adds its source-bound scope, a reference to this actual held
// inode derivation can rebind an owner's exact lock ctime without weakening
// inode/mode/owner/size/mtime or any other extended attribute.
pub(super) struct LabelDerivation {
    file: File,
    before: Snapshot,
    after: Snapshot,
}
impl LabelDerivation {
    fn revalidate(&self) -> Result<()> {
        ensure(
            snapshot(&self.file)? == self.after,
            "applied label derivation changed",
        )
    }
}

fn apply_one(file: File, before: &Snapshot, desired: &[u8], name: &str) -> Result<LabelDerivation> {
    ensure(
        name == LABEL || cfg!(test),
        "only the source-bound SELinux xattr may change",
    )?;
    ensure(
        snapshot(&file)? == *before,
        "label preimage identity or xattrs changed",
    )?;
    ensure(
        !desired.is_empty() && desired.len() <= 4096,
        "bounded raw label required",
    )?;
    let mut expected = before.attributes.clone();
    expected.insert(name.to_owned(), desired.to_vec());
    if before.attributes.get(name).map(Vec::as_slice) != Some(desired) {
        set(&file, name, Some(desired))?;
    }
    let after = snapshot(&file)?;
    ensure(
        only_ctime_changed(&before.identity, &after.identity) && after.attributes == expected,
        "label mutation changed another inode field or extended attribute",
    )?;
    Ok(LabelDerivation {
        file,
        before: before.clone(),
        after,
    })
}
fn restore_one(step: &LabelDerivation, name: &str) -> Result<Snapshot> {
    ensure(
        name == LABEL || cfg!(test),
        "only the recorded SELinux xattr may be restored",
    )?;
    step.revalidate()?;
    if step.before.attributes.get(name) != step.after.attributes.get(name) {
        set(
            &step.file,
            name,
            step.before.attributes.get(name).map(Vec::as_slice),
        )?;
    }
    let restored = snapshot(&step.file)?;
    ensure(
        only_ctime_changed(&step.before.identity, &restored.identity)
            && restored.attributes == step.before.attributes,
        "label rollback changed an unrelated inode field or xattr",
    )?;
    Ok(restored)
}

#[cfg(test)]
mod tests {
    use super::*;
    use rustix::fs::{Mode, OFlags};
    use std::os::unix::fs::symlink;

    fn path_inode(path: &std::path::Path) -> File {
        File::from(
            rustix::fs::open(
                path,
                OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
                Mode::empty(),
            )
            .unwrap(),
        )
    }
    #[test]
    fn actual_descriptor_label_and_rollback_preserve_other_xattrs_and_mtime() {
        let area = tempfile::tempdir().unwrap();
        let path = area.path().join("target");
        std::fs::write(&path, b"unchanged ordinary content").unwrap();
        let file = path_inode(&path);
        set(&file, "user.droidloom.unrelated", Some(b"preserved")).unwrap();
        let before = snapshot(&file).unwrap();
        let step = apply_one(
            file,
            &before,
            b"u:object_r:p4_linux_product_store_t:s0",
            "user.droidloom.testlabel",
        )
        .unwrap();
        step.revalidate().unwrap();
        let restored = restore_one(&step, "user.droidloom.testlabel").unwrap();
        assert_eq!(restored.attributes, before.attributes);
        assert!(only_ctime_changed(&before.identity, &restored.identity));
        assert_eq!(std::fs::read(&path).unwrap(), b"unchanged ordinary content");
    }
    #[test]
    fn held_inode_does_not_retarget_a_replaced_final_path_or_follow_symlinks() {
        let area = tempfile::tempdir().unwrap();
        let path = area.path().join("target");
        let old = area.path().join("old");
        std::fs::write(&path, b"old").unwrap();
        let held = path_inode(&path);
        std::fs::rename(&path, &old).unwrap();
        std::fs::write(&path, b"new").unwrap();
        set(&held, "user.droidloom.testlabel", Some(b"old inode only")).unwrap();
        assert!(
            !attributes(&path_inode(&path))
                .unwrap()
                .contains_key("user.droidloom.testlabel")
        );
        assert!(
            attributes(&path_inode(&old))
                .unwrap()
                .contains_key("user.droidloom.testlabel")
        );
        let link = area.path().join("link");
        symlink(&old, &link).unwrap();
        assert!(
            !attributes(&path_inode(&link))
                .unwrap()
                .contains_key("user.droidloom.testlabel")
        );
    }
    #[test]
    fn intervening_identity_or_xattr_change_prevents_apply_and_restore() {
        let area = tempfile::tempdir().unwrap();
        let path = area.path().join("target");
        std::fs::write(&path, b"original").unwrap();
        let file = path_inode(&path);
        let before = snapshot(&file).unwrap();
        set(&file, "user.droidloom.unrelated", Some(b"external change")).unwrap();
        assert!(apply_one(file, &before, b"label", "user.droidloom.testlabel").is_err());
        let file = path_inode(&path);
        let before = snapshot(&file).unwrap();
        let step = apply_one(file, &before, b"label", "user.droidloom.testlabel").unwrap();
        set(
            &step.file,
            "user.droidloom.unrelated",
            Some(b"changed again"),
        )
        .unwrap();
        assert!(restore_one(&step, "user.droidloom.testlabel").is_err());
    }

    #[test]
    #[ignore = "requires root; changes only newly created isolated symlink test inodes"]
    fn actual_security_label_targets_held_symlink_after_its_name_is_replaced() {
        ensure(
            rustix::process::getuid().as_raw() == 0,
            "root-only isolated test",
        )
        .unwrap();
        let area = tempfile::Builder::new()
            .prefix("p4-label-inode-test-")
            .tempdir_in("/var/lib/droidloom-qualification")
            .unwrap();
        let first = area.path().join("first-target");
        let second = area.path().join("second-target");
        std::fs::write(&first, b"first independent test target").unwrap();
        std::fs::write(&second, b"second independent test target").unwrap();
        let first_fd = path_inode(&first);
        let second_fd = path_inode(&second);
        set(
            &first_fd,
            "user.droidloom.target",
            Some(b"first target only"),
        )
        .unwrap();
        set(
            &second_fd,
            "user.droidloom.target",
            Some(b"second target only"),
        )
        .unwrap();
        let first_before = snapshot(&first_fd).unwrap();
        let second_before = snapshot(&second_fd).unwrap();
        let path = area.path().join("link");
        let retained = area.path().join("retained-link");
        symlink(&first, &path).unwrap();
        let held = path_inode(&path);
        std::fs::rename(&path, &retained).unwrap();
        symlink(&second, &path).unwrap();
        let replacement_fd = path_inode(&path);
        let replacement_before = snapshot(&replacement_fd).unwrap();
        let before = snapshot(&held).unwrap();
        let raw = b"u:object_r:p4_linux_product_store_t:s0\0";
        let step = apply_one(held, &before, raw, LABEL).unwrap();
        assert_eq!(snapshot(&path_inode(&retained)).unwrap(), step.after);
        assert_eq!(snapshot(&replacement_fd).unwrap(), replacement_before);
        assert_eq!(snapshot(&first_fd).unwrap(), first_before);
        assert_eq!(snapshot(&second_fd).unwrap(), second_before);
        let restored = restore_one(&step, LABEL).unwrap();
        assert_eq!(restored.attributes, before.attributes);
        assert!(only_ctime_changed(&before.identity, &restored.identity));
        assert_eq!(snapshot(&replacement_fd).unwrap(), replacement_before);
        assert_eq!(snapshot(&first_fd).unwrap(), first_before);
        assert_eq!(snapshot(&second_fd).unwrap(), second_before);
        println!(
            "{}",
            serde_json::json!({"schema":"droidloom.private-symlink-label-replacement-test.v1",
            "held_before":before,"held_after":step.after,"held_restored":restored,
            "replacement_before":replacement_before,"replacement_after":snapshot(&replacement_fd).unwrap(),
            "first_target_before":first_before,"first_target_after":snapshot(&first_fd).unwrap(),
            "second_target_before":second_before,"second_target_after":snapshot(&second_fd).unwrap(),
            "original_host_or_data_modified":false})
        );
    }
}
