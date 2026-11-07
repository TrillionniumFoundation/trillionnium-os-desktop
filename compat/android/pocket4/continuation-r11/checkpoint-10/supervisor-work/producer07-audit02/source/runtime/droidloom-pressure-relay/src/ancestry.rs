//! Held-directory ancestry proof. No pathname prefix grants authority.
use super::*;

pub(super) struct CgroupAncestry {
    files: Vec<File>,
    ids: Vec<FileId>,
    mount: u64,
    filesystem: libc::c_long,
}
fn mount_id(file: &File) -> Result<u64> {
    // thread-self also remains correct if an unrelated caller has a private
    // descriptor table. The selected descriptor stays owned throughout.
    let info = open_dir(Path::new("/proc/thread-self/fdinfo"))?;
    require_fs(&info, PROC_MAGIC)?;
    let text = read_at(&info, &file.as_raw_fd().to_string(), MAX_PROC_BYTES)?;
    let mut values = text.lines().filter_map(|line| line.strip_prefix("mnt_id:"));
    let value = values.next().ok_or(Error::Reject("descriptor mount ID missing"))?.trim();
    if values.next().is_some() { return Err(Error::Reject("descriptor mount ID repeated")); }
    numeric(value)
}
fn live_directory(file: &File, filesystem: libc::c_long, mount: u64, device: u64) -> Result<FileId> {
    require_fs(file, filesystem)?;
    let metadata = file.metadata().map_err(|e| io_err("stat cgroup ancestry", e))?;
    if !metadata.is_dir() || metadata.nlink() == 0 || metadata.dev() != device || mount_id(file)? != mount {
        return Err(Error::Reject("cgroup ancestor type/device/mount/generation differs"));
    }
    Ok(FileId { device: metadata.dev(), inode: metadata.ino() })
}
impl CgroupAncestry {
    pub(super) fn capture(root: &File, member: &File) -> Result<Self> {
        Self::capture_on_filesystem(root, member, CGROUP2_MAGIC)
    }
    fn capture_on_filesystem(root: &File, member: &File, filesystem: libc::c_long) -> Result<Self> {
        require_fs(root, filesystem)?;
        require_fs(member, filesystem)?;
        let expected = FileId::of(root)?;
        let mount = mount_id(root)?;
        let mut current = File::from(duplicate(member.as_raw_fd())?);
        let mut files = Vec::new();
        let mut ids = Vec::new();
        for _ in 0..128 {
            let id = live_directory(&current, filesystem, mount, expected.device)?;
            if ids.contains(&id) { return Err(Error::Reject("cgroup ancestry cycle/ancestor outside domain")); }
            ids.push(id);
            files.push(current);
            if id == expected {
                let proof = Self { files, ids, mount, filesystem };
                proof.validate()?;
                return Ok(proof);
            }
            current = open_at(files.last().expect("just pushed"), "..",
                libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW)?;
        }
        Err(Error::Reject("cgroup descendant ancestry exceeded its bound"))
    }
    pub(super) fn same_as(&self, other: &Self) -> bool {
        self.ids == other.ids && self.mount == other.mount && self.filesystem == other.filesystem
    }
    pub(super) fn validate(&self) -> Result<()> {
        if self.files.is_empty() || self.files.len() != self.ids.len() {
            return Err(Error::Reject("missing held cgroup ancestry"));
        }
        let device = self.ids[0].device;
        for (index, file) in self.files.iter().enumerate() {
            if live_directory(file, self.filesystem, self.mount, device)? != self.ids[index] {
                return Err(Error::Reject("held cgroup ancestor identity changed"));
            }
            if index + 1 < self.files.len() {
                let parent = open_at(file, "..", libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW)?;
                if live_directory(&parent, self.filesystem, self.mount, device)? != self.ids[index + 1] {
                    return Err(Error::Reject("cgroup moved outside its pinned ancestor chain"));
                }
            }
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn filesystem(file: &File) -> libc::c_long {
        let mut value: libc::statfs = unsafe { zeroed() };
        assert_eq!(unsafe { libc::fstatfs(file.as_raw_fd(), &mut value) }, 0);
        value.f_type
    }
    struct Fixture { path: PathBuf, root: File, child: File, sibling: File, parent: File }
    impl Fixture {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!("p4-cgroup-ancestry-{}-{}", unsafe { libc::getpid() },
                std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()));
            fs::create_dir(&path).unwrap();
            fs::create_dir(path.join("root")).unwrap();
            fs::create_dir(path.join("root/child")).unwrap();
            fs::create_dir(path.join("sibling")).unwrap();
            Self { root: open_dir(&path.join("root")).unwrap(), child: open_dir(&path.join("root/child")).unwrap(),
                sibling: open_dir(&path.join("sibling")).unwrap(), parent: open_dir(&path).unwrap(), path }
        }
    }
    impl Drop for Fixture { fn drop(&mut self) { let _ = fs::remove_dir_all(&self.path); } }
    // Ordinary filesystem seam exercises the identical FD ancestry algorithm.
    // Production capture always requires cgroup2 and has no caller-selected mode.
    #[test]
    fn held_ancestry_accepts_only_root_and_real_descendants() {
        let fixture = Fixture::new(); let kind = filesystem(&fixture.root);
        assert!(CgroupAncestry::capture(&fixture.root, &fixture.child).is_err());
        assert!(CgroupAncestry::capture_on_filesystem(&fixture.root, &fixture.root, kind).is_ok());
        assert!(CgroupAncestry::capture_on_filesystem(&fixture.root, &fixture.child, kind).is_ok());
        assert!(CgroupAncestry::capture_on_filesystem(&fixture.root, &fixture.sibling, kind).is_err());
        assert!(CgroupAncestry::capture_on_filesystem(&fixture.root, &fixture.parent, kind).is_err());
    }
    #[test]
    fn moving_an_owned_directory_revokes_a_previously_held_chain() {
        let fixture = Fixture::new(); let kind = filesystem(&fixture.root);
        let proof = CgroupAncestry::capture_on_filesystem(&fixture.root, &fixture.child, kind).unwrap();
        fs::rename(fixture.path.join("root/child"), fixture.path.join("sibling/moved")).unwrap();
        assert!(proof.validate().is_err());
        assert!(CgroupAncestry::capture_on_filesystem(&fixture.root, &fixture.child, kind).is_err());
    }
    #[test]
    fn replacing_the_same_name_does_not_replace_a_held_generation() {
        let fixture = Fixture::new(); let kind = filesystem(&fixture.root);
        let proof = CgroupAncestry::capture_on_filesystem(&fixture.root, &fixture.child, kind).unwrap();
        fs::remove_dir(fixture.path.join("root/child")).unwrap();
        fs::create_dir(fixture.path.join("root/child")).unwrap();
        let replacement = open_dir(&fixture.path.join("root/child")).unwrap();
        let new_proof = CgroupAncestry::capture_on_filesystem(&fixture.root, &replacement, kind).unwrap();
        assert!(!proof.same_as(&new_proof));
        assert!(proof.validate().is_err());
    }
}
