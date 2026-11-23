//! Compose the release-selected extension below the held original system mount.
//! All three filesystems remain detached until the existing base handoff.
use super::*;
use droidloom_contracts::system_ext::{ENGINE, HOST_MODULES, ORIGINAL_HAL, ORIGINAL_HAL_SHA256};
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::OsString;
use std::os::unix::ffi::OsStringExt;

fn directory(root: &File, name: &str) -> Result<File> {
    open_leaf(root, &text_name(name)?, libc::O_RDONLY | libc::O_DIRECTORY)
}
fn regular(root: &File, name: &str) -> Result<File> {
    let file = open_leaf(root, &text_name(name)?, libc::O_RDONLY)?;
    let stat = file.metadata()?;
    require(
        stat.is_file() && stat.nlink() == 1 && stat.len() <= MAX_IMAGE,
        "ordinary single-link library",
    )?;
    Ok(file)
}
fn children(dir: &File, names: impl IntoIterator<Item = String>) -> Result<()> {
    let mut expected: BTreeSet<OsString> = names.into_iter().map(OsString::from).collect();
    // The descriptor is held for the complete read of this immutable inode.
    for entry in std::fs::read_dir(format!("/proc/self/fd/{}", dir.as_raw_fd()))? {
        require(
            expected.remove(&entry?.file_name()),
            "unexpected system_ext library tree member",
        )?;
    }
    require(
        expected.is_empty(),
        "missing system_ext library tree member",
    )
}
fn fixed_children(dir: &File, names: &[&str]) -> Result<()> {
    children(dir, names.iter().map(|name| (*name).to_owned()))
}
fn image_attrs(file: &File) -> Result<BTreeMap<OsString, Vec<u8>>> {
    let mut names = vec![0u8; 65536];
    let n = unsafe { libc::flistxattr(file.as_raw_fd(), names.as_mut_ptr().cast(), names.len()) };
    if n < 0 {
        return Err(io::Error::last_os_error().into());
    }
    names.truncate(n as usize);
    let mut attrs = BTreeMap::new();
    for name in names
        .split(|byte| *byte == 0)
        .filter(|name| !name.is_empty())
    {
        let cname = CString::new(name).map_err(|_| MountError::Rejected("image xattr name"))?;
        let mut value = vec![0u8; 65536];
        let n = unsafe {
            libc::fgetxattr(
                file.as_raw_fd(),
                cname.as_ptr(),
                value.as_mut_ptr().cast(),
                value.len(),
            )
        };
        if n < 0 {
            return Err(io::Error::last_os_error().into());
        }
        value.truncate(n as usize);
        attrs.insert(OsString::from_vec(name.to_vec()), value);
    }
    Ok(attrs)
}
fn same_attributes(original: &File, selected: &File) -> Result<()> {
    let a = original.metadata()?;
    let b = selected.metadata()?;
    require(
        (a.uid(), a.gid(), a.mode()) == (b.uid(), b.gid(), b.mode())
            && image_attrs(original)? == image_attrs(selected)?,
        "original library directory or member ownership, mode or xattrs changed",
    )
}
fn digest(file: &File) -> Result<String> {
    let mut sha = Sha256::new();
    let mut offset = 0;
    let bytes = file.metadata()?.len();
    let mut buf = [0u8; 65536];
    while offset < bytes {
        let n = ((bytes - offset).min(buf.len() as u64)) as usize;
        file.read_exact_at(&mut buf[..n], offset)?;
        sha.update(&buf[..n]);
        offset += n as u64;
    }
    Ok(format!("{:x}", sha.finalize()))
}
fn system_lib64(system: &File) -> Result<File> {
    directory(
        &directory(&directory(system, "system")?, "system_ext")?,
        "lib64",
    )
}
fn vendor_libs(vendor: &File) -> Result<File> {
    directory(
        &directory(&directory(vendor, "lib64")?, "droidloom")?,
        "nativebridge",
    )
}
fn verify_members(original: &File, vendor: &File, ext: &File) -> Result<()> {
    fixed_children(original, &["hw"])?;
    fixed_children(ext, &["hw", "droidloom", "libberberis_arm64.so"])?;
    same_attributes(original, ext)?;
    let ohw = directory(original, "hw")?;
    let ehw = directory(ext, "hw")?;
    fixed_children(&ohw, &[ORIGINAL_HAL])?;
    fixed_children(&ehw, &[ORIGINAL_HAL])?;
    same_attributes(&ohw, &ehw)?;
    let of = regular(&ohw, ORIGINAL_HAL)?;
    let ef = regular(&ehw, ORIGINAL_HAL)?;
    preserve_original_file(&of, &ef, 37344, ORIGINAL_HAL_SHA256)?;
    verify_extension_tree(ext, vendor, &of)
}
fn preserve_original_file(
    original: &File,
    projected: &File,
    bytes: u64,
    sha256: &str,
) -> Result<()> {
    same_attributes(original, projected)?;
    require(
        original.metadata()?.len() == bytes
            && projected.metadata()?.len() == bytes
            && digest(original)? == sha256
            && digest(projected)? == sha256,
        "selected extension would hide or change the original CP3A memory HAL",
    )
}

fn verify_extension_tree(ext: &File, vendor: &File, original_file: &File) -> Result<()> {
    fixed_children(ext, &["hw", "droidloom", "libberberis_arm64.so"])?;
    let hw = directory(ext, "hw")?;
    fixed_children(&hw, &[ORIGINAL_HAL])?;
    let original = ext;
    let of = original_file;
    let attrs = image_attrs(&of)?;
    let m = of.metadata()?;
    let dir = ext.metadata()?;
    require(
        m.mode() & 0o7777 == 0o644
            && dir.mode() & 0o7777 == 0o755
            && (m.uid(), m.gid()) == (dir.uid(), dir.gid()),
        "original CP3A file and directory modes and IDs",
    )?;
    require(
        attrs.len() == 1 && image_attrs(ext)? == attrs && image_attrs(&hw)? == attrs,
        "original platform library and directories must only carry the platform label",
    )?;
    let label = attrs
        .get(&OsString::from("security.selinux"))
        .ok_or(MountError::Rejected(
            "original CP3A library security label absent",
        ))?;
    require(
        label.strip_suffix(&[0]).unwrap_or(label) == b"u:object_r:system_lib_file:s0",
        "original platform library label",
    )?;
    let product = directory(ext, "droidloom")?;
    fixed_children(&product, &["nativebridge"])?;
    same_attributes(original, &product)?;
    let private = directory(&product, "nativebridge")?;
    same_attributes(original, &private)?;
    children(
        &private,
        HOST_MODULES
            .iter()
            .filter(|m| **m != ENGINE)
            .map(|m| format!("{m}.so")),
    )?;
    for module in HOST_MODULES {
        let name = format!("{module}.so");
        let source = regular(vendor, &name)?;
        let selected = regular(if *module == ENGINE { ext } else { &private }, &name)?;
        same_attributes(of, &selected)?;
        require(
            source.metadata()?.len() == selected.metadata()?.len()
                && digest(&source)? == digest(&selected)?,
            "system_ext library bytes differ from the actual selected vendor",
        )?;
    }
    Ok(())
}
pub(super) fn compose(resources: &MountResources) -> Result<()> {
    let mount = |i: usize| {
        resources.images[i]
            .mount
            .as_ref()
            .ok_or(MountError::Rejected("selected mount absent"))
    };
    let system = mount(0)?;
    let vendor = mount(1)?;
    let ext = mount(2)?;
    let target = system_lib64(system)?;
    require(
        mount_id(&target)? == mount_id(system)?,
        "original system_ext target has an intervening mount",
    )?;
    verify_members(&target, &vendor_libs(vendor)?, ext)?;
    let rc = unsafe {
        libc::syscall(
            libc::SYS_move_mount,
            ext.as_raw_fd(),
            c"".as_ptr(),
            target.as_raw_fd(),
            c"".as_ptr(),
            libc::MOVE_MOUNT_F_EMPTY_PATH | libc::MOVE_MOUNT_T_EMPTY_PATH,
        )
    };
    if rc != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let attached = system_lib64(system)?;
    require(
        mount_id(&attached)? == mount_id(ext)?
            && attached.metadata()?.dev() == ext.metadata()?.dev(),
        "selected library image must occupy only its fixed original target",
    )?;
    require_detached(system)?;
    require_detached(ext)?;
    Ok(())
}

struct PublishedImage {
    source: SealedFile,
    mount: File,
    device: File,
    kernel_device: u64,
    node_identity: FileIdentity,
}
impl PublishedImage {
    fn open(
        parent: &Path,
        decl: &ImageDeclaration,
        mount: File,
        protected: &[(u64, u64); 2],
        ranges: (IdRange, IdRange),
    ) -> Result<Self> {
        let source = SealedFile::open_guarded(parent, &decl.file, 0, MAX_IMAGE, |file| {
            exclude_backings(file, protected)
        })?;
        let fs = Filesystem::detect(&source.file)?;
        verify_readonly_mount(&mount, fs, ranges.0, ranges.1, mount_id(&mount)?)?;
        let kernel_device = mount.metadata()?.dev();
        require(
            libc::major(kernel_device) == 7,
            "selected filesystem requires its owned loop device",
        )?;
        let index = libc::minor(kernel_device);
        let dev = trusted_directory(Path::new("/dev"), 0)?;
        let device = open_leaf(&dev, &text_name(&format!("loop{index}"))?, libc::O_RDONLY)?;
        let node_identity = FileIdentity::of(&device.metadata()?);
        let value = Self {
            source,
            mount,
            device,
            kernel_device,
            node_identity,
        };
        value.revalidate()?;
        value.source.verify_digest(decl.bytes, &decl.sha256)?;
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate(&self) -> Result<()> {
        self.source.revalidate()?;
        let m = self.device.metadata()?;
        require(
            same_block_node(self.node_identity, &m, self.kernel_device)
                && self.mount.metadata()?.dev() == self.kernel_device,
            "observed the exact selected block and filesystem descriptors",
        )?;
        let info = loop_status(&self.device)?
            .ok_or(MountError::Rejected("observed mount has no loop owner"))?;
        owned_loop_info(
            &info,
            self.source.identity,
            libc::minor(self.kernel_device),
            (0, 0),
        )
    }
}
fn exclude_backings(file: &File, protected: &[(u64, u64); 2]) -> Result<()> {
    let m = file.metadata()?;
    require(
        !protected.contains(&(m.dev(), m.ino())),
        "protected Android data inode cannot supply an immutable release",
    )
}
fn read_guest_root(guest: &File) -> Result<File> {
    // The already pidfd-bound proc directory owns this kernel magic link.
    syscall_fd(unsafe {
        libc::openat(
            guest.as_raw_fd(),
            c"root".as_ptr(),
            libc::O_DIRECTORY | libc::O_RDONLY | libc::O_CLOEXEC,
        )
    } as libc::c_long)
}
fn check_mount_graph(guest: &File, ext: &File) -> Result<()> {
    let id = mount_id(ext)?;
    let dev = ext.metadata()?.dev();
    let mut text = String::new();
    open_leaf(guest, c"mountinfo", libc::O_RDONLY)?
        .take(16 * 1024 * 1024 + 1)
        .read_to_string(&mut text)?;
    require(
        text.len() <= 16 * 1024 * 1024,
        "complete bounded guest mount graph",
    )?;
    validate_mountinfo(
        &text,
        &format!("{}:{}", libc::major(dev), libc::minor(dev)),
        &id.to_string(),
    )
}
fn validate_mountinfo(text: &str, dev: &str, id: &str) -> Result<()> {
    let mut seen = false;
    for line in text.lines() {
        let (left, right) = line
            .split_once(" - ")
            .ok_or(MountError::Rejected("incomplete guest mountinfo"))?;
        let a: Vec<_> = left.split_ascii_whitespace().collect();
        let b: Vec<_> = right.split_ascii_whitespace().collect();
        require(a.len() >= 6 && b.len() >= 3, "complete guest mount fields")?;
        if a[4] != droidloom_contracts::system_ext::TARGET && a[2] != dev {
            continue;
        }
        let flags: Vec<_> = a[5].split(',').collect();
        require(
            !seen
                && a[0] == id
                && a[2] == dev
                && a[3] == "/"
                && a[4] == droidloom_contracts::system_ext::TARGET
                && b[0] == "ext4"
                && ["ro", "nosuid", "nodev"]
                    .iter()
                    .all(|flag| flags.contains(flag))
                && !flags.contains(&"noexec")
                && b[2].split(',').any(|f| f == "ro"),
            "selected library mount changed location, identity or flags",
        )?;
        seen = true;
    }
    require(seen, "selected library mount absent from actual guest")
}
struct LiveMount {
    guest: File,
    system: PublishedImage,
    vendor: PublishedImage,
    ext: PublishedImage,
}
pub(crate) struct ObservedExtension {
    manifest: SealedFile,
    live: Option<LiveMount>,
}
impl ObservedExtension {
    pub(crate) fn from_guest(
        cohort: &str,
        guest: &File,
        protected: &[(u64, u64); 2],
        ranges: (IdRange, IdRange),
    ) -> Result<Self> {
        require(is_digest(cohort), "selected base manifest digest")?;
        let manifest = SealedFile::open_guarded(
            Path::new(MANIFEST_ROOT),
            &format!("{cohort}.json"),
            0,
            MAX_MANIFEST,
            |f| exclude_backings(f, protected),
        )?;
        let bytes = manifest.bounded_bytes(MAX_MANIFEST)?;
        require(
            format!("{:x}", Sha256::digest(&bytes)) == cohort,
            "selected exact base declaration bytes",
        )?;
        let decl: CohortDeclaration = serde_json::from_slice(&bytes)?;
        decl.validate()?;
        let Some(ext) = decl.system_ext_lib64 else {
            return Ok(Self {
                manifest,
                live: None,
            });
        };
        let root = read_guest_root(guest)?;
        let parent = Path::new(IMAGE_ROOT).join(cohort).join("images");
        let system = PublishedImage::open(
            &parent,
            &decl.system,
            directory(&root, "system")?,
            protected,
            ranges,
        )?;
        let vendor = PublishedImage::open(
            &parent,
            &decl.vendor,
            directory(&root, "vendor")?,
            protected,
            ranges,
        )?;
        let ext_mount = directory(&directory(&system.mount, "system_ext")?, "lib64")?;
        let ext = PublishedImage::open(
            &parent,
            &ImageDeclaration {
                file: ext.file,
                bytes: ext.bytes,
                sha256: ext.sha256,
            },
            ext_mount,
            protected,
            ranges,
        )?;
        require(
            system.kernel_device != vendor.kernel_device
                && system.kernel_device != ext.kernel_device
                && vendor.kernel_device != ext.kernel_device,
            "three distinct selected immutable mounts",
        )?;
        // The production preparer compares the original lower before grafting. An
        // independent OCI producer must preserve the very same pinned CP3A member.
        let hw = directory(&ext.mount, "hw")?;
        fixed_children(&hw, &[ORIGINAL_HAL])?;
        let original = regular(&hw, ORIGINAL_HAL)?;
        require(
            original.metadata()?.len() == 37344 && digest(&original)? == ORIGINAL_HAL_SHA256,
            "original CP3A memory HAL missing or changed in OCI guest",
        )?;
        verify_extension_tree(&ext.mount, &vendor_libs(&vendor.mount)?, &original)?;
        let value = Self {
            manifest,
            live: Some(LiveMount {
                guest: guest.try_clone()?,
                system,
                vendor,
                ext,
            }),
        };
        value.revalidate()?;
        Ok(value)
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.manifest.revalidate()?;
        if let Some(live) = &self.live {
            live.system.revalidate()?;
            live.vendor.revalidate()?;
            live.ext.revalidate()?;
            let root = read_guest_root(&live.guest)?;
            let system = directory(&root, "system")?;
            let vendor = directory(&root, "vendor")?;
            let effective = directory(&directory(&system, "system_ext")?, "lib64")?;
            for (actual, held) in [
                (&system, &live.system.mount),
                (&vendor, &live.vendor.mount),
                (&effective, &live.ext.mount),
            ] {
                require(
                    mount_id(actual)? == mount_id(held)?
                        && actual.metadata()?.ino() == held.metadata()?.ino(),
                    "effective selected guest mount was replaced",
                )?;
            }
            check_mount_graph(&live.guest, &effective)?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    #[test]
    fn system_ext_refuses_same_length_shadow_of_original_elf() {
        let mut original = tempfile::tempfile().unwrap();
        let mut selected = tempfile::tempfile().unwrap();
        original.write_all(b"original").unwrap();
        selected.write_all(b"original").unwrap();
        let expected = digest(&original).unwrap();
        preserve_original_file(&original, &selected, 8, &expected).unwrap();
        selected.write_all_at(b"replaced", 0).unwrap();
        assert!(preserve_original_file(&original, &selected, 8, &expected).is_err());
    }
    #[test]
    fn system_ext_refuses_added_or_absent_libs() {
        let dir = tempfile::tempdir().unwrap();
        let fd = File::open(dir.path()).unwrap();
        std::fs::write(dir.path().join("engine"), b"data").unwrap();
        fixed_children(&fd, &["engine"]).unwrap();
        assert!(fixed_children(&fd, &["different"]).is_err());
        std::fs::write(dir.path().join("unselected"), b"data").unwrap();
        assert!(fixed_children(&fd, &["engine"]).is_err());
    }
    #[test]
    fn system_ext_refuses_relocated_writable_or_alias_mount() {
        let valid =
            "318 300 7:13 / /system/system_ext/lib64 ro,nosuid,nodev - ext4 /dev/loop13 ro\n";
        validate_mountinfo(valid, "7:13", "318").unwrap();
        for invalid in [
            valid.replace("/system/system_ext/lib64", "/system/lib64"),
            valid.replace("7:13", "7:12"),
            valid.replace("318", "319"),
            valid.replace("ro,nosuid", "rw,nosuid"),
            valid.replace("nodev", "nodev,noexec"),
            valid.replace(" ext4 ", " overlay "),
            valid.replace("/dev/loop13 ro", "/dev/loop13 rw"),
            format!(
                "{valid}{}",
                valid.replace("/system/system_ext/lib64", "/unexpected")
            ),
        ] {
            assert!(validate_mountinfo(&invalid, "7:13", "318").is_err());
        }
    }
}

#[cfg(test)]
mod hardware {
    use super::*;
    use std::os::fd::FromRawFd;
    // The operator supplies six already-open, read-only descriptors in a
    // private namespace. This fixture has no mounting or selection authority.
    #[test]
    #[ignore = "requires original CP3A and selected raw vendor and library ext4 on three real idmapped loops"]
    fn actual_three_selected_loop_mounts_preserve_original_and_vendor_libraries() -> Result<()> {
        fn inherit(number: i32) -> Result<File> {
            let fd = unsafe { libc::fcntl(number, libc::F_DUPFD_CLOEXEC, 20) };
            if fd < 0 {
                return Err(io::Error::last_os_error().into());
            }
            Ok(unsafe { File::from_raw_fd(fd) })
        }
        let mut mounts = Vec::new();
        let manifest = inherit(9)?;
        let mut data = Vec::new();
        manifest.take(MAX_MANIFEST + 1).read_to_end(&mut data)?;
        require(
            data.len() as u64 <= MAX_MANIFEST,
            "bounded hardware fixture manifest",
        )?;
        let decl: CohortDeclaration = serde_json::from_slice(&data)?;
        decl.validate()?;
        let extension = decl
            .system_ext_lib64
            .ok_or(MountError::Rejected("actual v2 extension required"))?;
        for (index, (bytes, hash)) in [
            (decl.system.bytes, decl.system.sha256),
            (decl.vendor.bytes, decl.vendor.sha256),
            (extension.bytes, extension.sha256),
        ]
        .into_iter()
        .enumerate()
        {
            let raw = inherit(10 + index as i32)?;
            let mount = inherit(13 + index as i32)?;
            require(
                raw.metadata()?.is_file()
                    && raw.metadata()?.len() == bytes
                    && digest(&raw)? == hash,
                "actual whole raw image differs",
            )?;
            let dev = mount.metadata()?.dev();
            require(libc::major(dev) == 7, "actual kernel loop required")?;
            let device = File::open(format!("/dev/loop{}", libc::minor(dev)))?;
            require(
                device.metadata()?.rdev() == dev,
                "actual loop device matches mounted FS",
            )?;
            let status = loop_status(&device)?
                .ok_or(MountError::Rejected("actual loop is not configured"))?;
            owned_loop_info(
                &status,
                FileIdentity::of(&raw.metadata()?),
                libc::minor(dev),
                (0, 0),
            )?;
            let mut flags: libc::statvfs = unsafe { std::mem::zeroed() };
            zero_rc(unsafe { libc::fstatvfs(mount.as_raw_fd(), &mut flags) })?;
            require(
                flags.f_flag as u64 & READONLY_FLAGS == READONLY_FLAGS
                    && fs_type(&mount)? == Filesystem::Ext4.magic(),
                "real read-only nosuid nodev ext4",
            )?;
            mounts.push(mount);
        }
        require(
            mounts[0].metadata()?.dev() != mounts[1].metadata()?.dev()
                && mounts[0].metadata()?.dev() != mounts[2].metadata()?.dev()
                && mounts[1].metadata()?.dev() != mounts[2].metadata()?.dev(),
            "three different kernel block instances",
        )?;
        verify_members(
            &system_lib64(&mounts[0])?,
            &vendor_libs(&mounts[1])?,
            &mounts[2],
        )
    }
}
