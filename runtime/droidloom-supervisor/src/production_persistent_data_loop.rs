//! Separate writable whole-image loop owner for the live persistent provider.
//! The original read-only image/APEX loop implementation is not widened.

use super::*;

fn own_status(info: &LoopInfo64, source: FileIdentity, number: u32) -> Result<()> {
    require(
        info.device == source.dev && info.inode == source.ino && info.number == number
            && info.offset == 0 && info.size_limit == 0
            && info.flags == LO_FLAGS_AUTOCLEAR
            && info.encrypt_type == 0 && info.encrypt_key_size == 0
            && info.encrypt_key == [0; 32],
        "exact owned writable whole-image autoclear loop required",
    )
}

#[derive(Debug)]
pub(super) struct WritableLoop {
    file: Option<File>,
    node: FileIdentity,
    pub(super) device: u64,
    number: u32,
    source: FileIdentity,
}

impl WritableLoop {
    pub(super) fn attach(source: &File) -> Result<Self> {
        let source_node = FileIdentity::of(&source.metadata()?);
        require(source_node.mode == libc::S_IFREG | 0o600
            && source_node.uid == 0 && source_node.gid == 0 && source_node.links == 1,
            "root-private original writable backing inode required")?;
        let flags = unsafe { libc::fcntl(source.as_raw_fd(), libc::F_GETFL) };
        require(flags >= 0 && flags & libc::O_ACCMODE == libc::O_RDWR
            && flags & libc::O_PATH == 0, "actual writable body descriptor required")?;
        let control = std::fs::OpenOptions::new().read(true).write(true)
            .custom_flags(O_SAFE).open("/dev/loop-control")?;
        let cm = control.metadata()?;
        require(cm.mode() & libc::S_IFMT == libc::S_IFCHR && cm.uid() == 0
            && libc::major(cm.rdev()) == 10 && libc::minor(cm.rdev()) == 237,
            "actual loop-control character device required")?;
        for _ in 0..64 {
            let number = unsafe { libc::ioctl(control.as_raw_fd(), LOOP_CTL_GET_FREE, 0) };
            if number < 0 { return Err(io::Error::last_os_error().into()); }
            let number = u32::try_from(number).map_err(|_| MountError::Rejected("loop number"))?;
            require(number < 1_048_576, "bounded loop number")?;
            let path = PathBuf::from(format!("/dev/loop{number}"));
            let file = std::fs::OpenOptions::new().read(true).write(true)
                .custom_flags(O_SAFE).open(&path)?;
            let node = file.metadata()?;
            let mut raw = Vec::new();
            File::open(format!("/sys/block/loop{number}/dev"))?.take(129).read_to_end(&mut raw)?;
            require(raw.len() <= 128, "bounded actual loop sysfs identity")?;
            let text = std::str::from_utf8(&raw).map_err(|_| MountError::Rejected("loop sysfs encoding"))?;
            let (major, minor) = text.trim().split_once(':').ok_or(MountError::Rejected("loop sysfs device"))?;
            let major: u32 = major.parse().map_err(|_| MountError::Rejected("loop major"))?;
            let minor: u32 = minor.parse().map_err(|_| MountError::Rejected("loop minor"))?;
            require(node.mode() & libc::S_IFMT == libc::S_IFBLK && node.uid() == 0
                && node.mode() & 0o002 == 0 && major == 7
                && node.rdev() == libc::makedev(major, minor)
                && FileIdentity::of(&node) == FileIdentity::of(&std::fs::symlink_metadata(&path)?),
                "held actual writable loop node required")?;
            let mut config: LoopConfig = unsafe { std::mem::zeroed() };
            config.fd = u32::try_from(source.as_raw_fd()).map_err(|_| MountError::Rejected("backing descriptor"))?;
            config.info.flags = LO_FLAGS_AUTOCLEAR;
            // No offset, size window, encryption, readonly fallback or reused binding.
            let rc = unsafe { libc::ioctl(file.as_raw_fd(), LOOP_CONFIGURE, &config) };
            if rc < 0 {
                let error = io::Error::last_os_error();
                if error.raw_os_error() == Some(libc::EBUSY) { continue; }
                return Err(error.into());
            }
            let value = Self { file: Some(file), node: FileIdentity::of(&node),
                device: node.rdev(), number, source: source_node };
            // The outer resource owner must receive this object before any
            // fallible operation. Its Drop retains uncertain kernel custody.
            return Ok(value);
        }
        Err(MountError::Busy)
    }

    pub(super) fn file(&self) -> Result<&File> {
        self.file.as_ref().ok_or(MountError::Rejected("writable loop already retired"))
    }
    pub(super) fn verify(&self) -> Result<()> {
        let file = self.file()?;
        require(same_block_node(self.node, &file.metadata()?, self.device), "held writable loop node changed")?;
        let status = loop_status(file)?.ok_or(MountError::Rejected("writable loop unexpectedly unbound"))?;
        own_status(&status, self.source, self.number)
    }
    /// Android init selects writable partitions for orderly unmount using the
    /// /dev/block prefix recorded by Linux. Resolve only udev's canonical
    /// major:minor entry for the loop whose backing file is still leased.
    pub(super) fn android_block_source(&self) -> Result<CString> {
        self.verify()?;
        let directory = crate::production_selection::open_root_trusted_directory(Path::new("/dev/block"))
            .map_err(io::Error::other)?;
        require(directory.metadata()?.dev() == self.node.dev,
            "udev block directory must share the held device filesystem")?;
        let name = format!("{}:{}", libc::major(self.device), libc::minor(self.device));
        let anchored = PathBuf::from(format!("/proc/self/fd/{}", directory.as_raw_fd())).join(&name);
        let link = std::fs::symlink_metadata(&anchored)?;
        let expected = PathBuf::from(format!("../loop{}", self.number));
        require(link.is_symlink() && link.uid() == 0 && link.gid() == 0
            && std::fs::read_link(&anchored)? == expected
            && same_block_node(self.node, &std::fs::metadata(&anchored)?, self.device),
            "canonical root-owned udev alias must name the exact held writable loop inode")?;
        text_name(&format!("/dev/block/{name}"))
    }

    pub(super) fn is_bound(&self) -> bool { self.file.is_some() }
    pub(super) fn retire(&mut self) -> Result<u64> {
        let file = self.file()?;
        require(same_block_node(self.node, &file.metadata()?, self.device), "retire only the original held writable loop")?;
        if let Some(status) = loop_status(file)? {
            own_status(&status, self.source, self.number)?;
            zero_rc(unsafe { libc::ioctl(file.as_raw_fd(), LOOP_CLR_FD, 0) })?;
        }
        if loop_status(file)?.is_some() { return Err(MountError::Busy); }
        drop(self.file.take());
        Ok(self.device)
    }
}

impl Drop for WritableLoop {
    fn drop(&mut self) {
        if let Some(file) = self.file.take() { std::mem::forget(file); }
    }
}

/// Reject observed aliases; this inventory is not a kernel exclusivity grant.
/// The actual original durable lease separately excludes another cooperative
/// Droidloom writer. An unrelated root administrator is not a sandbox peer.
pub(super) fn reject_aliases(sources: &[FileIdentity; 2], owned: &[MountedData]) -> Result<()> {
    let root = trusted_directory(Path::new("/sys/devices/virtual/block"), 0)?;
    require(fs_type(&root)? == 0x6265_6572, "actual held kernel sysfs inventory required")?;
    let read_names = || -> Result<Vec<String>> {
        let mut names = Vec::new();
        for (count, entry) in std::fs::read_dir(format!("/proc/self/fd/{}", root.as_raw_fd()))?.enumerate() {
            require(count < 4096, "complete bounded kernel block inventory")?;
            let name = entry?.file_name();
            let name = name.to_str().ok_or(MountError::Rejected("block inventory encoding"))?;
            if let Some(suffix) = name.strip_prefix("loop") {
                require(!suffix.is_empty() && suffix.bytes().all(|b| b.is_ascii_digit()), "canonical loop inventory name")?;
                names.push(name.to_owned());
            }
        }
        names.sort();
        Ok(names)
    };
    let before = read_names()?;
    for name in &before {
        let number: u32 = name[4..].parse().map_err(|_| MountError::Rejected("loop inventory number"))?;
        let kernel = open_leaf(&root, &text_name(name)?, libc::O_RDONLY | libc::O_DIRECTORY)?;
        let mut raw = Vec::new();
        open_leaf(&kernel, c"dev", libc::O_RDONLY)?.take(129).read_to_end(&mut raw)?;
        require(raw.len() <= 128, "bounded actual sysfs loop device")?;
        let text = std::str::from_utf8(&raw).map_err(|_| MountError::Rejected("loop identity encoding"))?;
        let (major, minor) = text.trim().split_once(':').ok_or(MountError::Rejected("loop identity fields"))?;
        let major: u32 = major.parse().map_err(|_| MountError::Rejected("loop identity major"))?;
        let minor: u32 = minor.parse().map_err(|_| MountError::Rejected("loop identity minor"))?;
        let file = std::fs::OpenOptions::new().read(true).custom_flags(O_SAFE).open(format!("/dev/{name}"))?;
        let metadata = file.metadata()?;
        require(major == 7 && metadata.mode() & libc::S_IFMT == libc::S_IFBLK
            && metadata.uid() == 0 && metadata.rdev() == libc::makedev(major, minor),
            "observed loop descriptor must match actual kernel device")?;
        if let Some(status) = loop_status(&file)? {
            if sources.iter().any(|source| status.device == source.dev && status.inode == source.ino) {
                let expected = owned.iter().find(|row| row.binding.number == number)
                    .ok_or(MountError::Rejected("original data already has a foreign loop alias"))?;
                expected.binding.verify()?;
                require(metadata.rdev() == expected.binding.device, "owned data alias device changed")?;
                own_status(&status, expected.binding.source, expected.binding.number)?;
            }
        }
    }
    require(before == read_names()?, "kernel loop inventory changed during original data admission")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "requires a private mount namespace, a writable temporary backing, and real Linux loop devices"]
    fn actual_ubuntu_udev_source_names_the_leased_writable_loop() {
        assert_eq!(unsafe { libc::geteuid() }, 0);
        assert_ne!(std::fs::metadata("/proc/self/ns/mnt").unwrap().ino(),
                   std::fs::metadata("/proc/1/ns/mnt").unwrap().ino());
        let private = tempfile::tempdir().unwrap();
        let backing = std::fs::OpenOptions::new().read(true).write(true).create_new(true)
            .mode(0o600).open(private.path().join("data.img")).unwrap();
        backing.set_len(32 * 1024 * 1024).unwrap();
        let mut owned = WritableLoop::attach(&backing).unwrap();
        let result = owned.android_block_source().and_then(|name| {
            let path = Path::new(name.to_str().unwrap());
            require(path.starts_with("/dev/block") &&
                    same_block_node(owned.node, &std::fs::metadata(path)?, owned.device),
                    "Android source and the still-held leased block device must match")
        });
        let retired = owned.retire();
        assert!(retired.is_ok(), "{retired:?}");
        assert!(result.is_ok(), "{result:?}");
    }

    #[test]
    fn writable_data_loop_cannot_accept_readonly_window_or_foreign_source() {
        let file = File::open("/dev/null").unwrap();
        let source = FileIdentity::of(&file.metadata().unwrap());
        let mut status: LoopInfo64 = unsafe { std::mem::zeroed() };
        status.device = source.dev; status.inode = source.ino; status.number = 19;
        status.flags = LO_FLAGS_AUTOCLEAR;
        own_status(&status, source, 19).unwrap();
        for case in 0..8 {
            let mut changed = LoopInfo64 { ..status };
            match case {
                0 => changed.flags |= LO_FLAGS_READ_ONLY,
                1 => changed.flags = 0,
                2 => changed.offset = 4096,
                3 => changed.size_limit = 4096,
                4 => changed.inode ^= 1,
                5 => changed.number += 1,
                6 => changed.encrypt_type = 1,
                _ => changed.encrypt_key[0] = 1,
            }
            assert!(own_status(&changed, source, 19).is_err());
        }
    }
}
