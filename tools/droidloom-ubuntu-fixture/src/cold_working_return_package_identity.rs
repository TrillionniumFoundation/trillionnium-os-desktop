//! Narrow continuity of the actual PID1 image across a completed normal native
//! package inverse. No JSON, supplied identity or historical completion can
//! construct this proof. The running executable description is never replaced.
use super::CompletedPackageCommand;
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_qualification::{
        WorkingRecoverySources, WorkingReturnOwner, materials::Guard, owner::SealedInput,
    },
    ensure, fs,
    model::Identity,
};
use droidloom_descriptor_custody::Ext4Handle;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs::File,
    os::{fd::AsFd, unix::fs::FileExt},
    path::{Path, PathBuf},
    rc::Rc,
};

const SYSTEMD: &str = "/usr/lib/systemd/systemd";
const DELETED: &str = "/usr/lib/systemd/systemd (deleted)";
const MAX_IMAGE: u64 = 128 * 1024 * 1024;
const MAX_SNAPSHOT: u64 = 8 * 1024 * 1024;
const NATIVE_STATE: &str = "/var/lib/droidloom-maintenance/native-transactions";

fn same_pin(a: &FilePin, b: &FilePin) -> bool {
    a.path == b.path && a.bytes == b.bytes && a.sha256 == b.sha256
}
fn whole_hash(file: &File, size: u64) -> Result<String> {
    ensure(
        size > 0 && size <= MAX_IMAGE,
        "PID1 image exceeds its fixed bound",
    )?;
    let mut hash = Sha256::new();
    let mut buffer = [0_u8; 65536];
    let mut offset = 0_u64;
    while offset < size {
        let count = usize::try_from((size - offset).min(buffer.len() as u64))?;
        file.read_exact_at(&mut buffer[..count], offset)?;
        hash.update(&buffer[..count]);
        offset += count as u64;
    }
    ensure(
        file.read_at(&mut [0], size)? == 0,
        "PID1 image acquired trailing bytes",
    )?;
    Ok(format!("{:x}", hash.finalize()))
}
fn attributes(file: &File) -> Result<BTreeMap<String, String>> {
    let before = fs::stat(file)?;
    let mut names = vec![0_u8; 65536];
    let count = rustix::fs::flistxattr(file, names.as_mut_slice())?;
    names.truncate(count);
    ensure(
        names.is_empty() || names.last() == Some(&0),
        "PID1 xattr list is truncated",
    )?;
    let mut result = BTreeMap::new();
    let mut total = 0_usize;
    for name in names.split(|b| *b == 0).filter(|n| !n.is_empty()) {
        let name = std::str::from_utf8(name)?;
        let mut bytes = vec![0_u8; 65536];
        let count = rustix::fs::fgetxattr(file, name, bytes.as_mut_slice())?;
        total = total
            .checked_add(count)
            .ok_or("PID1 attribute size overflow")?;
        ensure(
            result.len() < 64
                && total <= 1024 * 1024
                && result
                    .insert(name.to_owned(), hex::encode(&bytes[..count]))
                    .is_none(),
            "PID1 attribute inventory is repeated or exceeds its bound",
        )?;
    }
    let mut again = vec![0_u8; 65536];
    let count = rustix::fs::flistxattr(file, again.as_mut_slice())?;
    ensure(
        count == names.len() && again[..count] == names && fs::stat(file)? == before,
        "PID1 inode or attributes changed while being captured",
    )?;
    Ok(result)
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct Executable {
    identity: Identity,
    handle: Ext4Handle,
    mount: i32,
    attributes: BTreeMap<String, String>,
    sha256: String,
}
impl Executable {
    fn capture(file: &File) -> Result<Self> {
        let identity = fs::stat(file)?;
        ensure(
            identity.mode == 0o100755
                && identity.uid == 0
                && identity.gid == 0
                && identity.nlink <= 1
                && identity.size > 0
                && identity.size <= MAX_IMAGE
                && rustix::fs::fstatfs(file)?.f_type as u64 == 0xef53,
            "PID1 package witness is not one held root-owned normal ext4 executable",
        )?;
        let (handle, mount) = Ext4Handle::capture(file.as_fd())?;
        ensure(
            u64::from(handle.inode_number()) == identity.ino,
            "PID1 inode number differs from its actual generation handle",
        )?;
        let attributes = attributes(file)?;
        let sha256 = whole_hash(file, identity.size)?;
        ensure(
            fs::stat(file)? == identity
                && Ext4Handle::capture(file.as_fd())? == (handle.clone(), mount)
                && self::attributes(file)? == attributes,
            "PID1 whole-file generation or metadata changed during readback",
        )?;
        Ok(Self {
            identity,
            handle,
            mount,
            attributes,
            sha256,
        })
    }
    fn evidence(&self) -> Value {
        json!({"identity":self.identity,"sha256":self.sha256,
            "inode_generation_handle":{"type":self.handle.handle_type(),
                "bytes":hex::encode(self.handle.bytes()),"mount_id":self.mount},
            "all_xattrs":self.attributes})
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum ImageChange {
    Unchanged,
    Unlinked,
}
fn image_change(
    before: &Executable,
    old_link: &Path,
    after: &Executable,
    new_link: &Path,
) -> Result<ImageChange> {
    ensure(
        before.handle == after.handle
            && before.mount == after.mount
            && before.attributes == after.attributes
            && before.sha256 == after.sha256,
        "normal package inverse changed the running image generation, body or attributes",
    )?;
    match old_link.to_str() {
        Some(DELETED) => {
            ensure(
                before.identity.nlink == 0 && after == before && new_link == old_link,
                "an already deleted PID1 image changed during native rollback",
            )?;
            Ok(ImageChange::Unchanged)
        }
        Some(SYSTEMD) => {
            ensure(
                before.identity.nlink == 1,
                "named original PID1 has another link count",
            )?;
            if new_link == old_link {
                ensure(
                    after == before,
                    "still-named PID1 changed during native rollback",
                )?;
                return Ok(ImageChange::Unchanged);
            }
            ensure(
                new_link == Path::new(DELETED) && after.identity.nlink == 0,
                "normal package inverse did not produce the exact kernel deleted link",
            )?;
            let mut comparable = after.identity.clone();
            comparable.nlink = before.identity.nlink;
            comparable.ctime_sec = before.identity.ctime_sec;
            comparable.ctime_nsec = before.identity.ctime_nsec;
            ensure(
                comparable == before.identity,
                "native unlink changed more than the original link count and ctime",
            )?;
            Ok(ImageChange::Unlinked)
        }
        _ => Err("PID1 package witness has another executable pathname".into()),
    }
}
fn native_snapshot(sources: &WorkingRecoverySources, pin: &FilePin) -> Result<Guard> {
    let release = sources.normal_materials()["native_release_id"]
        .as_str()
        .ok_or("normal native release ID absent")?;
    ensure(
        fs::valid_digest(release),
        "normal native release ID differs",
    )?;
    let parent = pin
        .path
        .parent()
        .ok_or("normal native snapshot parent absent")?;
    let attempt = parent
        .file_name()
        .and_then(|v| v.to_str())
        .ok_or("normal native attempt name")?;
    let suffix = attempt
        .strip_prefix(&format!("{release}-"))
        .ok_or("native attempt belongs to another release")?;
    ensure(
        pin.path.file_name().and_then(|v| v.to_str()) == Some("SNAPSHOT.json")
            && parent.parent() == Some(Path::new(NATIVE_STATE))
            && suffix.len() == 16
            && suffix
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            && pin.bytes > 0
            && pin.bytes <= MAX_SNAPSHOT,
        "native PID1 inverse requires the fixed preserved normal snapshot path",
    )?;
    let held = Guard::open(pin)?;
    ensure(
        held.identity().mode & 0o7777 == 0o400,
        "normal native snapshot lost its immutable mode",
    )?;
    let body: Value = serde_json::from_slice(&files::read_pin(pin, MAX_SNAPSHOT)?)?;
    let root = fs::stat(&fs::Tree::open("/", 0)?.root)?;
    ensure(
        body["schema"] == "droidloom-normal-native-snapshot-v1"
            && body["release_id"] == release
            && body["root_identity"] == json!([root.dev, root.ino]),
        "normal native snapshot has another source release or actual original root",
    )?;
    held.revalidate()?;
    Ok(held)
}

/// New live preimage for one specific normal native inverse. Constructor is
/// visible only to the actual package adapter, not arbitrary fixture callers.
pub(crate) struct PackageReplacementAttempt {
    sources: Rc<WorkingRecoverySources>,
    native_snapshot: Guard,
    held: File,
    before: Executable,
    link: PathBuf,
}
impl PackageReplacementAttempt {
    pub(super) fn begin(
        sources: Rc<WorkingRecoverySources>,
        snapshot: &FilePin,
    ) -> Result<Rc<Self>> {
        sources.revalidate()?;
        let native_snapshot = native_snapshot(&sources, snapshot)?;
        let (held, identity, sha256, link) = sources.owner().actual_pid1_for_package()?;
        let before = Executable::capture(&held)?;
        ensure(
            before.identity == identity && before.sha256 == sha256,
            "native package preimage differs from the fresh owner's actual held PID1",
        )?;
        image_change(&before, &link, &before, &link)?;
        let value = Rc::new(Self {
            sources,
            native_snapshot,
            held,
            before,
            link,
        });
        value.sources.revalidate()?;
        value.sources.owner().revalidate_package_custody(&value)?;
        Ok(value)
    }
    pub(super) fn require_sources(&self, sources: &Rc<WorkingRecoverySources>) -> Result<()> {
        ensure(
            Rc::ptr_eq(&self.sources, sources),
            "PID1 replacement has another fresh source owner",
        )?;
        self.sources.revalidate_normal_source_custody()?;
        self.native_snapshot.revalidate()
    }
    pub(crate) fn require_owner(&self, owner: &WorkingReturnOwner) -> Result<()> {
        ensure(
            std::ptr::eq(self.sources.owner().as_ref(), owner),
            "PID1 replacement has another actual fresh owner",
        )?;
        self.sources.revalidate_normal_source_custody()?;
        self.native_snapshot.revalidate()
    }
    pub(crate) fn require_current_pid1(&self, original: &File, sha256: &str) -> Result<()> {
        self.native_snapshot.revalidate()?;
        let link = std::fs::read_link("/proc/1/exe")?;
        let current = Executable::capture(&self.held)?;
        image_change(&self.before, &self.link, &current, &link)?;
        ensure(
            sha256 == self.before.sha256
                && Executable::capture(original)? == current
                && Executable::capture(&File::open("/proc/1/exe")?)? == current
                && std::fs::read_link("/proc/1/exe")? == link,
            "native package attempt no longer holds the actual running original PID1 image",
        )
    }
    pub(super) fn evidence(&self) -> Value {
        json!({"schema":"droidloom.working-pid1-package-attempt.v1",
            "candidate_id":self.sources.candidate(),"original_boot_id":self.sources.owner().boot_id(),
            "native_snapshot":self.native_snapshot.pin(),"before":self.before.evidence(),
            "kernel_executable_link":self.link,"actual_original_executable_fd_held":true,
            "completed":false})
    }
    pub(super) fn complete(
        self: Rc<Self>,
        command: CompletedPackageCommand,
    ) -> Result<WorkingPid1PackageReplacement> {
        command.require_attempt(&self)?;
        command.require_native_rollback_success()?;
        ensure(
            same_pin(command.native_snapshot(), self.native_snapshot.pin()),
            "normal package completion changed its original snapshot",
        )?;
        self.sources.owner().revalidate_package_custody(&self)?;
        let old = command.original_systemd_member();
        ensure(
            old.path == Path::new(SYSTEMD)
                && old.bytes > 0
                && old.bytes <= MAX_IMAGE
                && fs::valid_digest(&old.sha256),
            "normal package result does not identify the fixed original systemd member",
        )?;
        let named = fs::Tree::open("/", 0)?.file(SYSTEMD)?;
        let named_node = Executable::capture(&named)?;
        ensure(
            named_node.identity.nlink == 1
                && named_node.identity.dev == self.before.identity.dev
                && named_node.identity.size == old.bytes
                && named_node.sha256 == old.sha256,
            "actual named systemd is not the source-proven original package bytes",
        )?;
        let after = Executable::capture(&self.held)?;
        let link = std::fs::read_link("/proc/1/exe")?;
        let change = image_change(&self.before, &self.link, &after, &link)?;
        ensure(
            Executable::capture(&File::open("/proc/1/exe")?)? == after,
            "native package command replaced the running PID1 image",
        )?;
        if link == Path::new(DELETED) {
            ensure(
                (named_node.identity.dev, named_node.identity.ino)
                    != (after.identity.dev, after.identity.ino),
                "deleted running PID1 cannot also be the newly named package inode",
            )?;
        } else {
            ensure(
                named_node == after,
                "still-named PID1 differs from the actual named original package",
            )?;
        }
        command.revalidate_custody()?;
        self.sources.owner().revalidate_package_custody(&self)?;
        let value = json!({"schema":"droidloom.working-pid1-package-replacement.v1",
            "attempt":self.evidence(),"actual_native_command":command.result_pin(),
            "original_systemd_member":old,"named_original":named_node.evidence(),
            "after":after.evidence(),"kernel_executable_link":link,
            "old_held_inode_unlinked":change==ImageChange::Unlinked,
            "actual_running_image_replaced":false,"actual_normal_native_rollback":true,
            "public_packages_restored":false,"production_ready":false});
        let directory = command
            .result_pin()
            .path
            .parent()
            .ok_or("normal native result directory")?;
        ensure(
            directory.starts_with(self.sources.work())
                && directory.components().all(|c| {
                    matches!(
                        c,
                        std::path::Component::RootDir | std::path::Component::Normal(_)
                    )
                }),
            "PID1 completion record escaped its actual protected normal command root",
        )?;
        let path = directory.join("PID1-REPLACEMENT.json");
        files::write_new(&path, &serde_json::to_vec(&value)?, 0o400)?;
        File::open(directory)?.sync_all()?;
        let report = SealedInput::open(&files::pin_file(&path)?)?;
        let proof = WorkingPid1PackageReplacement {
            attempt: self,
            command,
            named,
            named_node,
            after,
            link,
            report,
            value,
        };
        proof.revalidate()?;
        Ok(proof)
    }
}

/// Completed normal native rollback plus independent actual inode/body
/// readbacks. Its only adoption capability concerns the retained PID1 image.
pub(crate) struct WorkingPid1PackageReplacement {
    attempt: Rc<PackageReplacementAttempt>,
    command: CompletedPackageCommand,
    named: File,
    named_node: Executable,
    after: Executable,
    link: PathBuf,
    report: SealedInput,
    value: Value,
}
impl WorkingPid1PackageReplacement {
    pub(crate) fn require_owner(&self, owner: &WorkingReturnOwner) -> Result<()> {
        self.attempt.require_owner(owner)?;
        self.command.require_attempt(&self.attempt)
    }
    pub(crate) fn attempt(&self) -> &PackageReplacementAttempt {
        &self.attempt
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.command.require_attempt(&self.attempt)?;
        self.command.require_native_rollback_success()?;
        self.attempt
            .sources
            .owner()
            .revalidate_package_custody(&self.attempt)?;
        ensure(
            Executable::capture(&self.attempt.held)? == self.after
                && Executable::capture(&File::open("/proc/1/exe")?)? == self.after
                && std::fs::read_link("/proc/1/exe")? == self.link
                && Executable::capture(&self.named)? == self.named_node
                && Executable::capture(&fs::Tree::open("/", 0)?.file(SYSTEMD)?)? == self.named_node,
            "completed PID1 native replacement lost its actual original or named generation",
        )?;
        self.report.revalidate()
    }
    pub(crate) fn require_held_transition(
        &self,
        file: &File,
        before: &Identity,
        link: &Path,
    ) -> Result<(Identity, PathBuf)> {
        self.revalidate()?;
        ensure(
            (before == &self.attempt.before.identity && link == self.attempt.link.as_path())
                || (before == &self.after.identity && link == self.link.as_path()),
            "PID1 package adoption is not this exact original or already-adopted checkpoint",
        )?;
        ensure(
            Executable::capture(file)? == self.after,
            "PID1 adoption supplied another held inode or generation",
        )?;
        Ok((self.after.identity.clone(), self.link.clone()))
    }
    pub(crate) fn report_pin(&self) -> &FilePin {
        self.report.pin()
    }
    pub(crate) fn evidence(&self) -> &Value {
        &self.value
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{io::Write, os::unix::fs::PermissionsExt, process::Command};

    fn original() -> Executable {
        Executable {
            identity: Identity {
                dev: 9,
                ino: 123,
                mode: 0o100755,
                uid: 0,
                gid: 0,
                nlink: 1,
                size: 4096,
                mtime_sec: 10,
                mtime_nsec: 20,
                ctime_sec: 30,
                ctime_nsec: 40,
            },
            handle: Ext4Handle::from_record(1, &[123, 0, 0, 0, 7, 0, 0, 0]).unwrap(),
            mount: 12,
            attributes: BTreeMap::from([("security.selinux".into(), "6162".into())]),
            sha256: "a".repeat(64),
        }
    }
    fn unlinked(before: &Executable) -> Executable {
        let mut after = before.clone();
        after.identity.nlink = 0;
        after.identity.ctime_sec += 1;
        after
    }
    #[test]
    fn native_unlink_only_adopts_nlink_and_ctime() {
        let before = original();
        let after = unlinked(&before);
        assert_eq!(
            image_change(&before, Path::new(SYSTEMD), &after, Path::new(DELETED)).unwrap(),
            ImageChange::Unlinked
        );
        let mut bad = after.clone();
        bad.identity.dev += 1;
        assert!(image_change(&before, Path::new(SYSTEMD), &bad, Path::new(DELETED)).is_err());
        let changes: [fn(&mut Identity); 9] = [
            |v| v.ino += 1,
            |v| v.mode ^= 0o100,
            |v| v.uid = 1,
            |v| v.gid = 1,
            |v| v.nlink = 2,
            |v| v.size += 1,
            |v| v.mtime_sec += 1,
            |v| v.mtime_nsec += 1,
            |v| v.mode |= 0o4000,
        ];
        for change in changes {
            let mut bad = after.clone();
            change(&mut bad.identity);
            assert!(image_change(&before, Path::new(SYSTEMD), &bad, Path::new(DELETED)).is_err());
        }
    }
    #[test]
    fn generation_mount_body_and_all_attributes_cannot_be_refreshed() {
        let before = original();
        let after = unlinked(&before);
        let mut values = Vec::new();
        let mut bad = after.clone();
        bad.handle = Ext4Handle::from_record(1, &[123, 0, 0, 0, 8, 0, 0, 0]).unwrap();
        values.push(bad);
        let mut bad = after.clone();
        bad.mount += 1;
        values.push(bad);
        let mut bad = after.clone();
        bad.sha256 = "b".repeat(64);
        values.push(bad);
        let mut bad = after.clone();
        bad.attributes.clear();
        values.push(bad);
        let mut bad = after.clone();
        bad.attributes
            .insert("security.capability".into(), "00".into());
        values.push(bad);
        for bad in values {
            assert!(image_change(&before, Path::new(SYSTEMD), &bad, Path::new(DELETED)).is_err());
        }
    }
    #[test]
    fn already_deleted_pid1_requires_complete_unchanged_identity() {
        let before = unlinked(&original());
        assert_eq!(
            image_change(&before, Path::new(DELETED), &before, Path::new(DELETED)).unwrap(),
            ImageChange::Unchanged
        );
        let changes: [fn(&mut Identity); 2] = [|v| v.ctime_sec += 1, |v| v.nlink = 1];
        for change in changes {
            let mut bad = before.clone();
            change(&mut bad.identity);
            assert!(image_change(&before, Path::new(DELETED), &bad, Path::new(DELETED)).is_err());
        }
        assert!(image_change(&before, Path::new(DELETED), &before, Path::new(SYSTEMD)).is_err());
    }
    #[test]
    fn no_named_checkpoint_can_hide_replacement_or_rename() {
        let before = original();
        assert_eq!(
            image_change(&before, Path::new(SYSTEMD), &before, Path::new(SYSTEMD)).unwrap(),
            ImageChange::Unchanged
        );
        let after = unlinked(&before);
        for name in [
            SYSTEMD,
            "/usr/lib/systemd/systemd.dpkg-old",
            "/usr/lib/systemd/other (deleted)",
            "/memfd:systemd (deleted)",
        ] {
            assert!(image_change(&before, Path::new(SYSTEMD), &after, Path::new(name)).is_err());
        }
        assert!(
            image_change(
                &before,
                Path::new("/tmp/systemd"),
                &after,
                Path::new(DELETED)
            )
            .is_err()
        );
        let mut bad = before.clone();
        bad.identity.ctime_sec += 1;
        assert!(image_change(&before, Path::new(SYSTEMD), &bad, Path::new(SYSTEMD)).is_err());
    }
    #[test]
    fn complete_hash_is_position_independent_and_rejects_suffix() -> Result<()> {
        let mut file = tempfile::tempfile()?;
        file.write_all(b"held actual original image")?;
        let hash = whole_hash(&file, 26)?;
        assert_eq!(hash, fs::digest(b"held actual original image"));
        assert_eq!(whole_hash(&file, 26)?, hash);
        assert!(whole_hash(&file, 25).is_err());
        assert!(whole_hash(&file, 27).is_err());
        assert!(whole_hash(&file, 0).is_err());
        Ok(())
    }
    #[test]
    #[ignore = "requires an explicitly created private root-owned ext4 fixture; never a live PID1 or systemd path"]
    fn real_private_ext4_running_image_survives_unlink_with_same_handle() -> Result<()> {
        ensure(
            rustix::process::geteuid().as_raw() == 0,
            "private ext4 fixture requires root",
        )?;
        let root = PathBuf::from(std::env::var("P4_TEST_PACKAGE_EXT4")?);
        let dir = fs::Tree::open(&fs::absolute_string(&root)?, 0)?.root;
        ensure(
            rustix::fs::fstatfs(&dir)?.f_type as u64 == 0xef53
                && fs::stat(&dir)?.mode & 0o7777 == 0o700,
            "new private root-only ext4 fixture required",
        )?;
        let work = tempfile::Builder::new()
            .prefix("pid1-unlink-")
            .tempdir_in(&root)?;
        let path = work.path().join("sleep");
        std::fs::copy("/usr/bin/sleep", &path)?;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755))?;
        let mut command = Command::new(&path);
        std::os::unix::process::CommandExt::arg0(&mut command, "sleep");
        command.arg("60");
        let mut child = crate::boot_child::OwnedChild::spawn(&mut command)?;
        let proc = PathBuf::from(format!("/proc/{}/exe", child.id()));
        let held = File::open(&proc)?;
        let before = Executable::capture(&held)?;
        ensure(
            std::fs::read_link(&proc)? == path,
            "actual private process does not execute its fixture inode",
        )?;
        let replacement = work.path().join("sleep.new");
        std::fs::copy("/usr/bin/sleep", &replacement)?;
        std::fs::set_permissions(&replacement, std::fs::Permissions::from_mode(0o755))?;
        File::open(&replacement)?.sync_all()?;
        std::fs::rename(&replacement, &path)?;
        File::open(work.path())?.sync_all()?;
        let after = Executable::capture(&held)?;
        ensure(
            std::fs::read_link(&proc)? == PathBuf::from(format!("{} (deleted)", path.display()))
                && Executable::capture(&File::open(&proc)?)? == after,
            "real private process did not retain its deleted original inode",
        )?;
        ensure(
            image_change(&before, Path::new(SYSTEMD), &after, Path::new(DELETED))?
                == ImageChange::Unlinked,
            "actual ext4 unlink does not match the narrow production transition",
        )?;
        let named = Executable::capture(&File::open(&path)?)?;
        ensure(
            named.sha256 == before.sha256
                && named.handle != before.handle
                && named.identity.nlink == 1,
            "same-byte replacement did not establish a distinct named original package inode",
        )?;
        ensure(
            image_change(
                &after,
                Path::new(DELETED),
                &Executable::capture(&held)?,
                Path::new(DELETED),
            )? == ImageChange::Unchanged,
            "already deleted held executable cannot retain its complete checkpoint",
        )?;
        let mut wrong = named.clone();
        wrong.identity.nlink = 0;
        ensure(
            image_change(&before, Path::new(SYSTEMD), &wrong, Path::new(DELETED)).is_err(),
            "same body on another actual ext4 generation was accepted",
        )?;
        child.stop_and_reap()?;
        ensure(
            Executable::capture(&held)? == after,
            "actual child retirement replaced its retained image",
        )?;
        Ok(())
    }
}
