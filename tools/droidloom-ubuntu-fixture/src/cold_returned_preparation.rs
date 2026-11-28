//! A consuming, cold-only transition from a Returned pair to two normal
//! preparation workspaces. It retains the same four read-only locked OFDs.
//! The old Returned guard is unchanged; only this exact successful operation
//! rebinds the qualification parent's complete current snapshot.
use super::*;
#[path = "cold_working_retention.rs"]
mod retention;
#[path = "cold_working_pair.rs"]
mod working;
use crate::boot_runtime::LabelTools;
use crate::cold_original_data::labels::OriginalLabelSources;
pub(crate) use working::{
    WorkingPairTransaction, WorkingSelectionProof, WorkingSelectionTransaction,
};

const QUALIFICATION: &str = "/var/lib/droidloom-qualification";
const MAX_PARENT_MEMBERS: usize = 4096;

struct Member {
    name: String,
    file: File,
    identity: Identity,
}
struct DirectoryInventory {
    members: Vec<Member>,
}
fn names(directory: &File) -> Result<Vec<String>> {
    let before = fs::stat(directory)?;
    let mut result = Vec::new();
    for entry in rustix::fs::Dir::read_from(directory)? {
        let entry = entry?;
        let name = entry.file_name().to_str()?;
        if name != "." && name != ".." {
            ensure(
                result.len() < MAX_PARENT_MEMBERS,
                "bounded preparation parent required",
            )?;
            result.push(name.to_owned());
        }
    }
    result.sort();
    ensure(
        result.windows(2).all(|pair| pair[0] != pair[1]) && fs::stat(directory)? == before,
        "preparation parent changed during its complete inventory",
    )?;
    Ok(result)
}
impl DirectoryInventory {
    fn capture(directory: &File) -> Result<Self> {
        let before = fs::stat(directory)?;
        let mut members = Vec::new();
        for name in names(directory)? {
            let identity = named(directory, &name)?.ok_or("parent member disappeared")?;
            let file = File::from(rustix::fs::openat(
                directory,
                name.as_str(),
                OFlags::PATH | OFlags::CLOEXEC | OFlags::NOFOLLOW,
                Mode::empty(),
            )?);
            ensure(
                fs::stat(&file)? == identity && named(directory, &name)? == Some(identity.clone()),
                "parent member was replaced before its held inventory",
            )?;
            members.push(Member {
                name,
                file,
                identity,
            });
        }
        let value = Self { members };
        value.verify(directory, &[])?;
        ensure(
            fs::stat(directory)? == before,
            "parent changed across held inventory",
        )?;
        Ok(value)
    }
    fn verify(&self, directory: &File, added: &[String]) -> Result<()> {
        let before = fs::stat(directory)?;
        let mut expected = self
            .members
            .iter()
            .map(|m| m.name.clone())
            .collect::<Vec<_>>();
        for name in added {
            ensure(
                !expected.contains(name),
                "preparation destination already existed",
            )?;
            expected.push(name.clone());
        }
        expected.sort();
        ensure(
            names(directory)? == expected,
            "preparation changed the exact parent member set",
        )?;
        for member in &self.members {
            ensure(
                fs::stat(&member.file)? == member.identity
                    && named(directory, &member.name)? == Some(member.identity.clone()),
                "an original preparation parent member was removed, replaced or changed",
            )?;
        }
        ensure(
            fs::stat(directory)? == before,
            "parent changed during closed-set verification",
        )
    }
    fn report(&self) -> Value {
        json!(
            self.members
                .iter()
                .map(|m| json!({
                    "name":m.name,"identity":m.identity
                }))
                .collect::<Vec<_>>()
        )
    }
}
fn work_name(candidate: &str) -> Result<String> {
    ensure(
        fs::valid_digest(candidate),
        "exact new qualification candidate required",
    )?;
    Ok(format!("working-qualification-{candidate}"))
}
fn source_name(candidate: &str, work_inode: u64) -> Result<String> {
    ensure(
        fs::valid_digest(candidate) && work_inode != 0,
        "actual new work inode required",
    )?;
    let name = format!(
        "original-initramfs-label-working-{}-{work_inode}",
        &candidate[..24]
    );
    ensure(
        name.len() <= 80,
        "normal source workspace name exceeds its original consumer",
    )?;
    Ok(name)
}
fn same_directory_inode(before: &Identity, after: &Identity) -> bool {
    (before.dev, before.ino, before.mode, before.uid, before.gid)
        == (after.dev, after.ino, after.mode, after.uid, after.gid)
        && FileType::from_raw_mode(after.mode) == FileType::Directory
}
fn verify_parent_births(before: &labels::Snapshot, after: &labels::Snapshot) -> Result<()> {
    let old = labels::snapshot_identity(before);
    let new = labels::snapshot_identity(after);
    ensure(
        same_directory_inode(old, new)
            && old.uid == 0
            && old.gid == 0
            && old.mode & 0o022 == 0
            && old.nlink.checked_add(2) == Some(new.nlink),
        "two fixed preparation births changed parent identity, ownership or link count",
    )?;
    // Unlike a working-image label transition this admits no xattr difference.
    labels::verify_data_snapshot(before, after, false)
}
struct NewDirectory {
    path: PathBuf,
    file: File,
    birth: labels::Snapshot,
}
impl NewDirectory {
    fn hold(path: PathBuf, parent: &File) -> Result<Self> {
        let name = path
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or("work basename absent")?;
        let file = open_at(parent, name, true)?;
        let birth = labels::snapshot(&file)?;
        let identity = labels::snapshot_identity(&birth);
        ensure(
            identity.mode == 0o40700
                && identity.uid == 0
                && identity.gid == 0
                && identity.dev == fs::stat(parent)?.dev
                && named(parent, name)? == Some(identity.clone()),
            "normal preparation workspace is not one private root directory on its held parent",
        )?;
        Ok(Self { path, file, birth })
    }
    fn guard(&self) -> Result<()> {
        let named = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(&self.path)?)?;
        let current = labels::snapshot(&self.file)?;
        ensure(
            labels::snapshot(&named)? == current
                && same_directory_inode(
                    labels::snapshot_identity(&self.birth),
                    labels::snapshot_identity(&current),
                ),
            "normal preparation workspace lost its held/named inode",
        )?;
        // Its normal producer may create nested files, but cannot change the
        // directory generation, permissions, ownership or any xattr.
        labels::verify_data_snapshot(&self.birth, &current, false)
    }
}
pub(crate) struct PreparedReturnedPair {
    pair: ReturnedWorkingPair,
    work: NewDirectory,
    source_work: NewDirectory,
    births: Value,
    recovery: Option<(NewDirectory, Value)>,
}
impl ReturnedWorkingPair {
    pub(crate) fn prepare_normal_sources(
        mut self,
        history: &ReturnedOnceHistory,
        candidate: &str,
        prepared: &FilePin,
        tools: &LabelTools,
    ) -> Result<(PreparedReturnedPair, OriginalLabelSources)> {
        self.guard(history)?;
        ensure(
            candidate != history.candidate(),
            "new preparation must not reuse the first once",
        )?;
        let parent_index = self
            .parents
            .iter()
            .position(|(p, _, _)| p == Path::new(QUALIFICATION))
            .ok_or("held qualification parent absent")?;
        let parent = self.parents[parent_index].1.try_clone()?;
        let before = self.parents[parent_index].2.clone();
        let inventory = DirectoryInventory::capture(&parent)?;
        let work_name = work_name(candidate)?;
        ensure(
            named(&parent, &work_name)?.is_none(),
            "new qualification work already exists",
        )?;
        let work_path = Path::new(QUALIFICATION).join(&work_name);
        crate::boot_files::private_dir(&work_path)?;
        let work = NewDirectory::hold(work_path, &parent)?;
        let source_name = source_name(candidate, fs::stat(&work.file)?.ino)?;
        ensure(
            named(&parent, &source_name)?.is_none(),
            "normal source work already exists",
        )?;
        inventory.verify(&parent, std::slice::from_ref(&work_name))?;
        let source_path = Path::new(QUALIFICATION).join(&source_name);
        // This is the original normal verifier, not a directory or success
        // callback supplied by the caller. It creates exactly source_path.
        let sources = OriginalLabelSources::admit(prepared, tools, &source_path)?;
        let source_work = NewDirectory::hold(source_path, &parent)?;
        ensure(
            fs::stat(&work.file)?.ino != fs::stat(&source_work.file)?.ino,
            "normal preparation directories alias",
        )?;
        work.guard()?;
        source_work.guard()?;
        inventory.verify(&parent, &[work_name.clone(), source_name.clone()])?;
        parent.sync_all()?;
        let after = labels::snapshot(&parent)?;
        verify_parent_births(&before, &after)?;
        let current_named = fs::Tree::open("/", 0)?.dir(QUALIFICATION)?;
        ensure(
            labels::snapshot(&current_named)? == after,
            "qualification parent name replaced",
        )?;
        sources.revalidate_custody()?;
        // Consume only this source-owned operation's two births. No parent
        // exemption is added to ReturnedWorkingPair::guard or its public reader.
        self.parents[parent_index].2 = after.clone();
        self.guard(history)?;
        inventory.verify(&parent, &[work_name.clone(), source_name.clone()])?;
        let births = json!({
            "schema":"droidloom.working-qualification-cold-workspaces.v1",
            "candidate_id":candidate,"parent":QUALIFICATION,
            "before":before,"after":after,"retained_members":inventory.report(),
            "added_directories":[
                {"name":work_name,"path":work.path,"birth":work.birth},
                {"name":source_name,"path":source_work.path,"birth":source_work.birth}
            ],
            "normal_source_record":sources.source_pin(),
            "same_four_backing_ofds_retained":true,
            "parent_snapshot_rebound_only_after_exact_two_births":true,
            "scope":"cold_material_preparation_only",
            "runtime_journal_births_admitted":false
        });
        let value = PreparedReturnedPair {
            pair: self,
            work,
            source_work,
            births,
            recovery: None,
        };
        value.guard(history)?;
        Ok((value, sources))
    }
}
impl PreparedReturnedPair {
    pub(crate) fn guard(&self, history: &ReturnedOnceHistory) -> Result<()> {
        self.pair.guard(history)?;
        self.work.guard()?;
        self.source_work.guard()?;
        if let Some((directory, _)) = &self.recovery {
            directory.guard()?;
        }
        self.pair.guard(history)
    }
    pub(crate) fn work(&self) -> &Path {
        &self.work.path
    }
    pub(crate) fn work_file(&self) -> &File {
        &self.work.file
    }
    pub(crate) fn summary(&self) -> Value {
        json!({"schema":"droidloom.prepared-returned-working-pair.v1",
            "returned_pair":self.pair.summary(),"normal_workspaces":self.births,
            "normal_recovery_workspace":self.recovery.as_ref().map(|(_, proof)|proof),
            "qualification_boot_authorized":false,"runtime_parent_freeze":false})
    }
}

fn recovery_name(candidate: &str, work_inode: u64) -> Result<String> {
    ensure(
        fs::valid_digest(candidate) && work_inode != 0,
        "actual new working candidate and held workspace inode required",
    )?;
    let name = format!(
        "original-initramfs-working-{}-{work_inode}",
        &candidate[..24]
    );
    ensure(
        name.len() <= 80,
        "normal recovery workspace exceeds original producer name bound",
    )?;
    Ok(name)
}

fn recovery_directory_for_work(candidate: &str, work: &Path, work_inode: u64) -> Result<PathBuf> {
    ensure(
        work == Path::new(QUALIFICATION).join(work_name(candidate)?),
        "normal recovery candidate differs from its actual private work",
    )?;
    Ok(Path::new(QUALIFICATION).join(recovery_name(candidate, work_inode)?))
}

impl PreparedReturnedPair {
    pub(crate) fn recovery_directory(&self, candidate: &str) -> Result<PathBuf> {
        let id = fs::stat(&self.work.file)?;
        recovery_directory_for_work(candidate, &self.work.path, id.ino)
    }

    /// A second cold-only operation, after the first two births. The actual
    /// normal producer is invoked here while every pre-existing BASE member and
    /// the same four original/working image OFDs remain held. The source-derived
    /// single new directory is the only permitted namespace change.
    pub(crate) fn prepare_recovery(
        &mut self,
        history: &ReturnedOnceHistory,
        candidate: &str,
        normal_plan: &FilePin,
    ) -> Result<FilePin> {
        self.guard(history)?;
        ensure(
            self.recovery.is_none(),
            "normal working recovery was already prepared",
        )?;
        let directory = self.recovery_directory(candidate)?;
        ensure(
            normal_plan.path == self.work.path.join("RECOVERY-PRODUCER.json"),
            "normal working recovery input is not its own fixed private source",
        )?;
        let (input, input_identity) = crate::boot_files::open_pin(normal_plan)?;
        let raw: Value =
            serde_json::from_slice(&crate::boot_files::read_pin(normal_plan, 16 * 1024 * 1024)?)?;
        ensure(
            raw["schema"] == "droidloom.original-host-initramfs-plan.v1"
                && raw["work_directory"] == serde_json::to_value(&directory)?
                && raw["recovery_recipe"].is_object(),
            "normal working recovery plan changes its actual derived destination",
        )?;
        let parent_index = self
            .pair
            .parents
            .iter()
            .position(|(p, _, _)| p == Path::new(QUALIFICATION))
            .ok_or("held qualification parent absent")?;
        let parent = self.pair.parents[parent_index].1.try_clone()?;
        let before = self.pair.parents[parent_index].2.clone();
        let inventory = DirectoryInventory::capture(&parent)?;
        let name = directory
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or("normal recovery basename absent")?
            .to_owned();
        ensure(
            named(&parent, &name)?.is_none(),
            "normal working recovery workspace already exists",
        )?;
        // The unchanged normal CLI implementation owns its real private build,
        // source admission, namespace, output readback, and full tool custody.
        // No success callback or prepared receipt supplied by a caller is used.
        crate::cold_original_initramfs::prepare(&normal_plan.path, &normal_plan.sha256)?;
        ensure(
            fs::stat(&input)? == input_identity
                && fs::hash(&input)? == normal_plan.sha256
                && fs::stat(&input)? == input_identity
                && fs::Tree::open("/", 0)?.identity(&fs::absolute_string(&normal_plan.path)?)?
                    == input_identity,
            "normal recovery input changed across its actual producer",
        )?;
        let recovery = NewDirectory::hold(directory, &parent)?;
        recovery.guard()?;
        inventory.verify(&parent, std::slice::from_ref(&name))?;
        let receipt =
            crate::boot_files::pin_file(&recovery.path.join("ORIGINAL-INITRAMFS-PREPARED.json"))?;
        let result: Value =
            serde_json::from_slice(&crate::boot_files::read_pin(&receipt, 16 * 1024 * 1024)?)?;
        ensure(
            result["schema"] == "droidloom.original-host-initramfs-prepared.v1"
                && result["input"] == serde_json::to_value(normal_plan)?
                && result["recovery_recipe_input"] == raw["recovery_recipe"]
                && result["recovery_image_readback"]["schema"]
                    == "droidloom.working-qualification-recovery-image-readback.v1",
            "actual normal producer did not retain this working recovery recipe",
        )?;
        self.work.guard()?;
        self.source_work.guard()?;
        parent.sync_all()?;
        let after = labels::snapshot(&parent)?;
        let old = labels::snapshot_identity(&before);
        let new = labels::snapshot_identity(&after);
        ensure(
            same_directory_inode(old, new)
                && old.uid == 0
                && old.gid == 0
                && old.mode & 0o022 == 0
                && old.nlink.checked_add(1) == Some(new.nlink),
            "normal recovery birth changed parent ownership or an additional child",
        )?;
        labels::verify_data_snapshot(&before, &after, false)?;
        let named_parent = fs::Tree::open("/", 0)?.dir(QUALIFICATION)?;
        ensure(
            labels::snapshot(&named_parent)? == after,
            "normal recovery parent name was replaced",
        )?;
        inventory.verify(&parent, std::slice::from_ref(&name))?;
        self.pair.parents[parent_index].2 = after.clone();
        self.pair.guard(history)?;
        let proof = json!({
            "schema":"droidloom.working-qualification-cold-recovery-workspace.v1",
            "candidate_id":candidate,"parent":QUALIFICATION,"before":before,"after":after,
            "retained_members":inventory.report(),
            "added_directory":{"name":name,"path":recovery.path,"birth":recovery.birth},
            "normal_input":normal_plan,"normal_prepared":receipt,
            "same_four_backing_ofds_retained":true,
            "parent_snapshot_rebound_only_after_exact_one_normal_birth":true,
            "scope":"cold_normal_initramfs_preparation_only",
            "runtime_journal_births_admitted":false
        });
        self.recovery = Some((recovery, proof));
        self.guard(history)?;
        Ok(receipt)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT: AtomicU64 = AtomicU64::new(0);
    struct Temporary(PathBuf);
    impl Temporary {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "working-parent-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            std::fs::create_dir(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for Temporary {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }
    #[test]
    fn working_preparation_preserves_existing_member_ofd_and_closed_two_births() {
        let root = Temporary::new();
        std::fs::write(root.0.join("retained"), b"original source").unwrap();
        let directory = File::open(&root.0).unwrap();
        let inventory = DirectoryInventory::capture(&directory).unwrap();
        std::fs::create_dir(root.0.join("first")).unwrap();
        inventory.verify(&directory, &["first".into()]).unwrap();
        std::fs::create_dir(root.0.join("second")).unwrap();
        inventory
            .verify(&directory, &["first".into(), "second".into()])
            .unwrap();
        std::fs::create_dir(root.0.join("unreviewed")).unwrap();
        assert!(
            inventory
                .verify(&directory, &["first".into(), "second".into()])
                .is_err()
        );
    }
    #[test]
    fn working_preparation_rejects_same_bytes_replaced_old_member() {
        let root = Temporary::new();
        std::fs::write(root.0.join("retained"), b"original source").unwrap();
        let directory = File::open(&root.0).unwrap();
        let inventory = DirectoryInventory::capture(&directory).unwrap();
        std::fs::write(root.0.join("replacement"), b"original source").unwrap();
        std::fs::rename(root.0.join("replacement"), root.0.join("retained")).unwrap();
        assert!(inventory.verify(&directory, &[]).is_err());
    }
    #[test]
    fn working_preparation_names_bind_complete_candidate_and_actual_work_inode() {
        let candidate = "a".repeat(64);
        assert_eq!(
            work_name(&candidate).unwrap(),
            format!("working-qualification-{candidate}")
        );
        assert_ne!(
            source_name(&candidate, 41).unwrap(),
            source_name(&candidate, 42).unwrap()
        );
        assert!(source_name(&candidate, u64::MAX).unwrap().len() <= 80);
        assert!(source_name(&candidate, 0).is_err());
        assert!(work_name("../candidate").is_err());
        assert!(source_name(&"A".repeat(64), 41).is_err());
    }
    #[test]
    fn working_recovery_workspace_joins_full_candidate_and_actual_inode() {
        let candidate = "a".repeat(64);
        let work = Path::new(QUALIFICATION).join(work_name(&candidate).unwrap());
        let first = recovery_directory_for_work(&candidate, &work, 11).unwrap();
        let second = recovery_directory_for_work(&candidate, &work, 12).unwrap();
        assert_ne!(first, second);
        assert_eq!(first.parent(), Some(Path::new(QUALIFICATION)));
        assert!(first.file_name().unwrap().len() <= 80);
        let collision = format!("{}{}", "a".repeat(24), "b".repeat(40));
        assert!(recovery_directory_for_work(&collision, &work, 11).is_err());
        assert!(recovery_directory_for_work(&candidate, &work, 0).is_err());
        assert!(recovery_directory_for_work(&candidate, &work.join("alias"), 11).is_err());
        assert!(recovery_directory_for_work("../other", &work, 11).is_err());
    }
    #[test]
    fn working_recovery_birth_keeps_all_preexisting_member_inodes() {
        let root = Temporary::new();
        std::fs::write(root.0.join("old"), b"retained cold source").unwrap();
        let directory = File::open(&root.0).unwrap();
        let held = DirectoryInventory::capture(&directory).unwrap();
        std::fs::create_dir(root.0.join("normal-recovery")).unwrap();
        held.verify(&directory, &["normal-recovery".into()])
            .unwrap();
        std::fs::create_dir(root.0.join("extra")).unwrap();
        assert!(
            held.verify(&directory, &["normal-recovery".into()])
                .is_err()
        );
        std::fs::remove_dir(root.0.join("extra")).unwrap();
        held.verify(&directory, &["normal-recovery".into()])
            .unwrap();
        std::fs::write(root.0.join("replacement"), b"retained cold source").unwrap();
        std::fs::rename(root.0.join("replacement"), root.0.join("old")).unwrap();
        assert!(
            held.verify(&directory, &["normal-recovery".into()])
                .is_err()
        );
    }
}
