//! Fixed runtime masks for one cold working package transaction.
//! The prepared symlink inode is held before its public rename. These tmpfs
//! resources are deliberately process-owned; they are not reboot recovery.
use super::{Identity, attrs};
use crate::{Result, ensure, fs};
use rustix::fs::{FileType, Mode, OFlags, RenameFlags};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    fs::File,
    os::fd::AsRawFd,
    path::{Path, PathBuf},
};

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
struct Link {
    identity: Identity,
    attributes: BTreeMap<String, String>,
    target: String,
}
fn link(file: &File) -> Result<Link> {
    let identity = fs::stat(file)?;
    ensure(
        FileType::from_raw_mode(identity.mode) == FileType::Symlink
            && identity.uid == 0
            && identity.gid == 0
            && identity.nlink == 1,
        "runtime package mask is not its held root symlink",
    )?;
    let target = rustix::fs::readlinkat(file, "", Vec::new())?;
    let target = std::str::from_utf8(target.to_bytes())?.to_owned();
    ensure(
        target == "/dev/null",
        "runtime package mask points outside the fixed null target",
    )?;
    let attributes = attrs(file)?;
    ensure(
        fs::stat(file)? == identity,
        "runtime mask changed during complete readback",
    )?;
    Ok(Link {
        identity,
        attributes,
        target,
    })
}
fn open_at(parent: &File, name: &str) -> Result<Option<File>> {
    match rustix::fs::openat(
        parent,
        name,
        OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    ) {
        Ok(fd) => Ok(Some(File::from(fd))),
        Err(rustix::io::Errno::NOENT) => Ok(None),
        Err(error) => Err(error.into()),
    }
}
fn named(parent: &File, name: &str) -> Result<Option<Link>> {
    open_at(parent, name)?.as_ref().map(link).transpose()
}
fn rename_identity(before: &Link, after: &Link) -> bool {
    let mut comparable = after.clone();
    comparable.identity.ctime_sec = before.identity.ctime_sec;
    comparable.identity.ctime_nsec = before.identity.ctime_nsec;
    comparable == *before
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
struct Directory {
    identity: Identity,
    attributes: BTreeMap<String, String>,
    members: BTreeMap<String, Identity>,
}
fn directory(file: &File) -> Result<Directory> {
    let identity = fs::stat(file)?;
    ensure(
        FileType::from_raw_mode(identity.mode) == FileType::Directory
            && identity.uid == 0
            && identity.gid == 0
            && identity.mode & 0o022 == 0,
        "runtime mask parent lost root ownership",
    )?;
    let attributes = attrs(file)?;
    let mut members = BTreeMap::new();
    for item in std::fs::read_dir(format!("/proc/self/fd/{}", file.as_raw_fd()))? {
        let name = item?
            .file_name()
            .into_string()
            .map_err(|_| "runtime mask parent has nonUTF8 member")?;
        ensure(
            !name.is_empty() && !name.contains('/') && name.len() <= 255 && members.len() < 65536,
            "bounded runtime mask parent membership required",
        )?;
        let held = open_at(file, &name)?.ok_or("runtime parent member disappeared")?;
        ensure(
            members.insert(name, fs::stat(&held)?).is_none(),
            "duplicate runtime parent member",
        )?;
    }
    ensure(
        fs::stat(file)? == identity && attrs(file)? == attributes,
        "runtime mask parent changed during complete inventory",
    )?;
    Ok(Directory {
        identity,
        attributes,
        members,
    })
}
fn parent_delta(
    before: &Directory,
    after: &Directory,
    name: &str,
    value: Option<&Identity>,
) -> Result<()> {
    let mut expected = before.clone();
    expected.identity.size = after.identity.size;
    expected.identity.mtime_sec = after.identity.mtime_sec;
    expected.identity.mtime_nsec = after.identity.mtime_nsec;
    expected.identity.ctime_sec = after.identity.ctime_sec;
    expected.identity.ctime_nsec = after.identity.ctime_nsec;
    match value {
        Some(value) => {
            expected.members.insert(name.into(), value.clone());
        }
        None => {
            expected.members.remove(name);
        }
    }
    ensure(
        expected == *after,
        "runtime mask rename changed another parent member or field",
    )
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Phase {
    Prepared,
    Publishing,
    Published,
    Restoring,
    Restored,
}
struct Step {
    name: String,
    file: File,
    checkpoint: Link,
    phase: Phase,
}
pub(in crate::cold_original_qualification) struct WorkingPackageMasks {
    public_path: PathBuf,
    public: File,
    public_state: Directory,
    private_path: PathBuf,
    private: File,
    private_state: Directory,
    preserved: Vec<(String, File, Link)>,
    steps: Vec<Step>,
}
impl WorkingPackageMasks {
    /// A new boot has no old /run inode authority. On the same actual boot,
    /// the fresh original owner may retire only the exact source-created null
    /// links from its fixed private comparison; all preexisting masks remain.
    pub(in crate::cold_original_qualification) fn retire_returned(
        sources: &super::super::WorkingRecoverySources,
        comparison: &crate::boot_files::FilePin,
        boot_id: &str,
        expected_private: &Path,
    ) -> Result<()> {
        sources.revalidate_custody()?;
        let input = super::SealedInput::open(comparison)?;
        let value: serde_json::Value = serde_json::from_slice(&input.read()?)?;
        let expected_public = Path::new("/run/systemd/system");
        ensure(
            value["schema"] == "droidloom.working-runtime-package-masks.v1"
                && value["public"] == crate::fs::absolute_string(expected_public)?
                && value["private"] == crate::fs::absolute_string(expected_private)?,
            "returned mask comparison escaped its fixed source locations",
        )?;
        let units = crate::cold_working_recovery::contract::PACKAGE_WRITERS
            .iter()
            .chain(crate::cold_working_recovery::contract::SUSPEND_TARGETS.iter())
            .copied()
            .collect::<Vec<_>>();
        if boot_id != sources.owner().boot_id() {
            ensure(
                std::fs::symlink_metadata(expected_private)
                    .err()
                    .is_some_and(|e| e.kind() == std::io::ErrorKind::NotFound),
                "an old-boot private mask name unexpectedly exists in the current /run",
            )?;
        } else {
            let mut owner =
                Self::reopen_comparison(expected_public, expected_private, &units, &value)?;
            owner.restore()?;
        }
        input.revalidate()?;
        sources.revalidate_custody()
    }
    pub(in crate::cold_original_qualification) fn prepare_returned(
        sources: &super::super::WorkingRecoverySources,
        ordinal: usize,
    ) -> Result<Self> {
        sources.revalidate_custody()?;
        ensure(
            ordinal < 32,
            "returned mask epoch exceeds its finite source bound",
        )?;
        let path = Path::new("/run").join(format!(
            "droidloom-working-return-packages-{}-{}-{ordinal:02}",
            sources.candidate(),
            sources.owner().boot_id()
        ));
        let units = crate::cold_working_recovery::contract::PACKAGE_WRITERS
            .iter()
            .chain(crate::cold_working_recovery::contract::SUSPEND_TARGETS.iter())
            .copied()
            .collect::<Vec<_>>();
        let value = Self::prepare_at(Path::new("/run/systemd/system"), &path, &units)?;
        sources.revalidate_custody()?;
        Ok(value)
    }
    fn reopen_comparison(
        public_path: &Path,
        private_path: &Path,
        units: &[&str],
        value: &serde_json::Value,
    ) -> Result<Self> {
        let public = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(public_path)?)?;
        let private = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(private_path)?)?;
        let public_state = directory(&public)?;
        let private_state = directory(&private)?;
        let old_public: Directory = serde_json::from_value(value["public_preimage"].clone())?;
        let old_private: Directory = serde_json::from_value(value["private_preimage"].clone())?;
        let fixed = |a: &Directory, b: &Directory| {
            (
                a.identity.dev,
                a.identity.ino,
                a.identity.mode,
                a.identity.uid,
                a.identity.gid,
                a.identity.nlink,
                &a.attributes,
            ) == (
                b.identity.dev,
                b.identity.ino,
                b.identity.mode,
                b.identity.uid,
                b.identity.gid,
                b.identity.nlink,
                &b.attributes,
            )
        };
        ensure(
            fixed(&old_public, &public_state) && fixed(&old_private, &private_state),
            "returned same-boot masks lost an actual original directory inode",
        )?;
        let mut preserved = Vec::new();
        let mut steps = Vec::new();
        let mut names = std::collections::BTreeSet::new();
        for (field, retain) in [("preserved", true), ("prepared", false)] {
            let rows = value[field]
                .as_array()
                .ok_or("returned mask roster missing")?;
            ensure(
                rows.len() <= 32,
                "returned mask roster exceeds its fixed unit bound",
            )?;
            for row in rows {
                let name = row["name"].as_str().ok_or("returned mask unit name")?;
                ensure(
                    units.contains(&name) && names.insert(name.to_owned()),
                    "returned masks changed a fixed unit role",
                )?;
                let expected: Link = serde_json::from_value(row["node"].clone())?;
                let a = open_at(&public, name)?;
                let b = open_at(&private, name)?;
                if retain {
                    ensure(
                        b.is_none(),
                        "original mask also appeared under a candidate private name",
                    )?;
                    let file = a.ok_or("preserved original mask disappeared")?;
                    ensure(
                        link(&file)? == expected,
                        "preexisting mask changed outside the actual candidate transaction",
                    )?;
                    preserved.push((name.into(), file, expected));
                } else {
                    let (file, phase) = match (a, b) {
                        (Some(f), None) => (f, Phase::Published),
                        (None, Some(f)) => (f, Phase::Restored),
                        _ => {
                            return Err(
                                "returned prepared mask has no unique actual current role".into()
                            );
                        }
                    };
                    let checkpoint = link(&file)?;
                    ensure(
                        rename_identity(&expected, &checkpoint),
                        "returned null mask is a different actual inode or source",
                    )?;
                    steps.push(Step {
                        name: name.into(),
                        file,
                        checkpoint,
                        phase,
                    });
                }
            }
        }
        ensure(
            names == units.iter().map(|s| s.to_string()).collect()
                && private_state.members.keys().all(|name| {
                    steps
                        .iter()
                        .any(|s| s.name == *name && s.phase == Phase::Restored)
                }),
            "returned mask closure omitted a unit or gained a foreign private member",
        )?;
        let value = Self {
            public_path: public_path.into(),
            public,
            public_state,
            private_path: private_path.into(),
            private,
            private_state,
            preserved,
            steps,
        };
        value.guard()?;
        Ok(value)
    }
    pub(in crate::cold_original_qualification) fn prepare(
        candidate: &str,
        units: &[&str],
    ) -> Result<Self> {
        ensure(
            fs::valid_digest(candidate),
            "one complete working package candidate required",
        )?;
        let path = Path::new("/run").join(format!("droidloom-working-packages-{candidate}"));
        Self::prepare_at(Path::new("/run/systemd/system"), &path, units)
    }
    fn prepare_at(public_path: &Path, private_path: &Path, units: &[&str]) -> Result<Self> {
        ensure(
            rustix::process::geteuid().as_raw() == 0 && !units.is_empty() && units.len() <= 32,
            "fixed cold package masks require actual root",
        )?;
        let public = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(public_path)?)?;
        let public_state = directory(&public)?;
        let mut seen = std::collections::BTreeSet::new();
        let mut preserved = Vec::new();
        let mut missing = Vec::new();
        for name in units {
            ensure(
                seen.insert(*name)
                    && !name.is_empty()
                    && name.len() <= 128
                    && name.bytes().all(|b| {
                        b.is_ascii_lowercase() || b.is_ascii_digit() || b"-._@".contains(&b)
                    }),
                "fixed unique package mask unit required",
            )?;
            if let Some(file) = open_at(&public, name)? {
                let actual = link(&file)?;
                preserved.push(((*name).into(), file, actual));
            } else {
                missing.push((*name).to_owned());
            }
        }
        // Stage outside systemd's unit search directory. Every public target
        // has already been admitted before this private create-only work.
        crate::boot_files::private_dir(private_path)?;
        let private = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(private_path)?)?;
        ensure(
            fs::stat(&public)?.dev == fs::stat(&private)?.dev,
            "runtime mask staging must use the same mounted filesystem",
        )?;
        let mut steps = Vec::new();
        for name in missing {
            rustix::fs::symlinkat("/dev/null", &private, name.as_str())?;
            let file = open_at(&private, &name)?.ok_or("prepared runtime mask absent")?;
            let checkpoint = link(&file)?;
            steps.push(Step {
                name,
                file,
                checkpoint,
                phase: Phase::Prepared,
            });
        }
        private.sync_all()?;
        let private_state = directory(&private)?;
        let value = Self {
            public_path: public_path.into(),
            public,
            public_state,
            private_path: private_path.into(),
            private,
            private_state,
            preserved,
            steps,
        };
        value.guard()?;
        Ok(value)
    }
    pub(in crate::cold_original_qualification) fn comparison(&self) -> serde_json::Value {
        serde_json::json!({"schema":"droidloom.working-runtime-package-masks.v1",
            "public":self.public_path,"public_preimage":self.public_state,
            "private":self.private_path,"private_preimage":self.private_state,
            "preserved":self.preserved.iter().map(|(name,_,node)| serde_json::json!({"name":name,"node":node})).collect::<Vec<_>>(),
            "prepared":self.steps.iter().map(|step| serde_json::json!({"name":step.name,"node":step.checkpoint})).collect::<Vec<_>>()})
    }
    fn guard_parents(&self) -> Result<()> {
        for (path, file, state) in [
            (&self.public_path, &self.public, &self.public_state),
            (&self.private_path, &self.private, &self.private_state),
        ] {
            let actual = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(path)?)?;
            ensure(
                fs::stat(&actual)? == fs::stat(file)? && directory(file)? == *state,
                "runtime package mask parent changed outside the fixed rename",
            )?;
        }
        for (name, file, expected) in &self.preserved {
            ensure(
                link(file)? == *expected && named(&self.public, name)?.as_ref() == Some(expected),
                "preexisting runtime mask changed",
            )?;
        }
        Ok(())
    }
    pub(in crate::cold_original_qualification) fn guard(&self) -> Result<()> {
        self.guard_parents()?;
        for step in &self.steps {
            let (home, other) = match step.phase {
                Phase::Prepared | Phase::Restored => (&self.private, &self.public),
                Phase::Published => (&self.public, &self.private),
                Phase::Publishing | Phase::Restoring => {
                    return Err("runtime mask rename requires reconciliation".into());
                }
            };
            ensure(
                link(&step.file)? == step.checkpoint
                    && named(home, &step.name)?.as_ref() == Some(&step.checkpoint)
                    && named(other, &step.name)?.is_none(),
                "runtime mask lost its actual continuously held symlink",
            )?;
        }
        self.guard_parents()
    }
    fn reconcile(&mut self, index: usize) -> Result<()> {
        let step = &self.steps[index];
        let forward = match step.phase {
            Phase::Publishing => true,
            Phase::Restoring => false,
            _ => return Ok(()),
        };
        let (from, to, from_state, to_state) = if forward {
            (
                &self.private,
                &self.public,
                &self.private_state,
                &self.public_state,
            )
        } else {
            (
                &self.public,
                &self.private,
                &self.public_state,
                &self.private_state,
            )
        };
        let before = named(from, &step.name)?;
        let after = named(to, &step.name)?;
        let observed = link(&step.file)?;
        let from_now = directory(from)?;
        let to_now = directory(to)?;
        let moved = match (before, after) {
            (Some(old), None) if old == step.checkpoint && observed == old => {
                ensure(
                    from_now == *from_state && to_now == *to_state,
                    "unmoved runtime mask parent changed",
                )?;
                false
            }
            (None, Some(new)) if new == observed && rename_identity(&step.checkpoint, &new) => {
                parent_delta(from_state, &from_now, &step.name, None)?;
                parent_delta(to_state, &to_now, &step.name, Some(&new.identity))?;
                true
            }
            _ => {
                return Err(
                    "runtime mask has an unknown effect; retain both actual parents and inode"
                        .into(),
                );
            }
        };
        from.sync_all()?;
        to.sync_all()?;
        ensure(
            directory(from)? == from_now && directory(to)? == to_now,
            "runtime mask changed across its synchronization barrier",
        )?;
        if forward {
            self.private_state = from_now;
            self.public_state = to_now;
        } else {
            self.public_state = from_now;
            self.private_state = to_now;
        }
        let step = &mut self.steps[index];
        step.checkpoint = observed;
        step.phase = match (forward, moved) {
            (true, true) => Phase::Published,
            (true, false) => Phase::Prepared,
            (false, true) => Phase::Restored,
            (false, false) => Phase::Published,
        };
        self.guard()
    }
    fn move_one(&mut self, index: usize, forward: bool) -> Result<()> {
        self.guard()?;
        let step = &mut self.steps[index];
        ensure(
            step.phase
                == if forward {
                    Phase::Prepared
                } else {
                    Phase::Published
                },
            "runtime mask operation cannot replay this phase",
        )?;
        step.phase = if forward {
            Phase::Publishing
        } else {
            Phase::Restoring
        };
        let (from, to) = if forward {
            (&self.private, &self.public)
        } else {
            (&self.public, &self.private)
        };
        let result = rustix::fs::renameat_with(
            from,
            step.name.as_str(),
            to,
            step.name.as_str(),
            RenameFlags::NOREPLACE,
        );
        // Even a failed syscall leaves a pending state until the actual held
        // inode and both complete directory inventories classify the outcome.
        let reconciliation = self.reconcile(index);
        result?;
        reconciliation
    }
    pub(in crate::cold_original_qualification) fn publish(&mut self) -> Result<()> {
        for index in 0..self.steps.len() {
            self.move_one(index, true)?;
        }
        self.guard()
    }
    pub(in crate::cold_original_qualification) fn restore(&mut self) -> Result<()> {
        for index in 0..self.steps.len() {
            if matches!(
                self.steps[index].phase,
                Phase::Publishing | Phase::Restoring
            ) {
                self.reconcile(index)?;
            }
        }
        for index in (0..self.steps.len()).rev() {
            if self.steps[index].phase == Phase::Published {
                self.move_one(index, false)?;
            }
        }
        ensure(
            self.steps
                .iter()
                .all(|s| matches!(s.phase, Phase::Prepared | Phase::Restored)),
            "runtime package masks have not restored their original absence",
        )?;
        self.guard()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn actual() -> (tempfile::TempDir, PathBuf, PathBuf) {
        assert_eq!(rustix::process::geteuid().as_raw(), 0);
        let root = tempfile::Builder::new()
            .prefix(".p4-package-masks-")
            .tempdir_in("/run")
            .unwrap();
        let public = root.path().join("units");
        std::fs::create_dir(&public).unwrap();
        let private = root.path().join("private");
        (root, public, private)
    }
    #[test]
    fn returned_masks_reopen_actual_same_boot_links_and_keep_preexisting_null_masks() {
        let (_root, public, private) = actual();
        std::os::unix::fs::symlink("/dev/null", public.join("old.service")).unwrap();
        let original = std::fs::symlink_metadata(public.join("old.service")).unwrap();
        let mut forward =
            WorkingPackageMasks::prepare_at(&public, &private, &["old.service", "new.timer"])
                .unwrap();
        let comparison = forward.comparison();
        forward.publish().unwrap();
        drop(forward);
        let mut returned = WorkingPackageMasks::reopen_comparison(
            &public,
            &private,
            &["old.service", "new.timer"],
            &comparison,
        )
        .unwrap();
        returned.restore().unwrap();
        drop(returned);
        assert!(!public.join("new.timer").exists());
        use std::os::unix::fs::MetadataExt;
        assert_eq!(
            std::fs::symlink_metadata(public.join("old.service"))
                .unwrap()
                .ino(),
            original.ino()
        );
        let again = WorkingPackageMasks::reopen_comparison(
            &public,
            &private,
            &["old.service", "new.timer"],
            &comparison,
        )
        .unwrap();
        again.guard().unwrap();
        std::fs::remove_file(private.join("new.timer")).unwrap();
        std::os::unix::fs::symlink("/dev/null", private.join("new.timer")).unwrap();
        assert!(
            WorkingPackageMasks::reopen_comparison(
                &public,
                &private,
                &["old.service", "new.timer"],
                &comparison
            )
            .is_err()
        );
    }
    #[test]
    fn package_masks_move_the_same_actual_symlink_and_preserve_existing_masks() {
        let (_root, public, private) = actual();
        std::os::unix::fs::symlink("/dev/null", public.join("old.service")).unwrap();
        let mut tx =
            WorkingPackageMasks::prepare_at(&public, &private, &["old.service", "new.timer"])
                .unwrap();
        let before = tx.steps[0].checkpoint.clone();
        let old = tx.preserved[0].2.clone();
        tx.publish().unwrap();
        assert!(rename_identity(&before, &link(&tx.steps[0].file).unwrap()));
        assert!(!private.join("new.timer").exists());
        tx.restore().unwrap();
        assert!(std::fs::symlink_metadata(public.join("new.timer")).is_err());
        assert_eq!(named(&tx.public, "old.service").unwrap(), Some(old));
        assert!(rename_identity(&before, &link(&tx.steps[0].file).unwrap()));
        tx.restore().unwrap();
    }
    #[test]
    fn package_masks_reconcile_an_actual_rename_before_restoring_without_forward_replay() {
        let (_root, public, private) = actual();
        let mut tx = WorkingPackageMasks::prepare_at(&public, &private, &["new.timer"]).unwrap();
        tx.steps[0].phase = Phase::Publishing;
        rustix::fs::renameat_with(
            &tx.private,
            "new.timer",
            &tx.public,
            "new.timer",
            RenameFlags::NOREPLACE,
        )
        .unwrap();
        tx.restore().unwrap();
        assert!(std::fs::symlink_metadata(public.join("new.timer")).is_err());
        assert_eq!(tx.steps[0].phase, Phase::Restored);
    }
    #[test]
    fn package_masks_reject_foreign_birth_without_removing_it_or_losing_the_prepared_inode() {
        let (_root, public, private) = actual();
        let mut tx = WorkingPackageMasks::prepare_at(&public, &private, &["new.timer"]).unwrap();
        let before = link(&tx.steps[0].file).unwrap();
        std::os::unix::fs::symlink("/dev/null", public.join("foreign.service")).unwrap();
        assert!(tx.publish().is_err());
        assert!(std::fs::symlink_metadata(public.join("foreign.service")).is_ok());
        assert_eq!(link(&tx.steps[0].file).unwrap(), before);
        assert!(std::fs::symlink_metadata(private.join("new.timer")).is_ok());
    }
}
