//! Metadata-only custody of the two original reserved backing inodes.
//!
//! These O_PATH descriptors cannot read or write an image body. They keep the
//! original inodes alive and connect the durable reservation to its current
//! trusted directory entries. They do not authorize a writable loop, mount,
//! filesystem inspection, migration, or Android data continuity.

use super::{
    BackingIdentity, IdentityError, Result, check_directory, open_at, trusted_directory,
    trusted_file,
};
use std::fs::{File, Metadata};
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};

// Content writes may legitimately change mtime and ctime. Those clocks and
// image bytes are deliberately not part of this lifetime identity check.
// Keep authority/registry seals in the parent module strictly unchanged.
fn same_backing(left: &Metadata, right: &Metadata) -> bool {
    left.dev() == right.dev()
        && left.ino() == right.ino()
        && left.mode() == right.mode()
        && left.uid() == right.uid()
        && left.gid() == right.gid()
        && left.nlink() == right.nlink()
        && left.len() == right.len()
}

fn same_parent(left: &Metadata, right: &Metadata) -> bool {
    left.dev() == right.dev()
        && left.ino() == right.ino()
        && left.mode() == right.mode()
        && left.uid() == right.uid()
        && left.gid() == right.gid()
}

fn distinct(data: &Metadata, metadata: &Metadata) -> Result<()> {
    if (data.dev(), data.ino()) == (metadata.dev(), metadata.ino()) {
        return Err(IdentityError::UnsafeCustody(
            "data and metadata require distinct original backing inodes".into(),
        ));
    }
    Ok(())
}

fn identity(meta: &Metadata) -> BackingIdentity {
    BackingIdentity {
        device: meta.dev(),
        inode: meta.ino(),
        bytes: meta.len(),
    }
}

/// Held by the existing IdentityLease; there is no serialized constructor,
/// body-opening method, mount capability, or custom Drop implementation.
#[derive(Debug)]
pub(super) struct HeldBackings {
    path: PathBuf,
    owner: u32,
    parent: File,
    parent_metadata: Metadata,
    data: File,
    data_metadata: Metadata,
    metadata: File,
    metadata_metadata: Metadata,
}

impl HeldBackings {
    pub(super) fn open(path: &Path, owner: u32) -> Result<Self> {
        let parent = trusted_directory(path, owner, false)?;
        let parent_metadata = parent.metadata()?;
        let data = open_at(&parent, "data.img", libc::O_PATH, 0)?;
        let data_metadata = data.metadata()?;
        trusted_file(&data_metadata, owner, u64::MAX)?;
        let metadata = open_at(&parent, "metadata.img", libc::O_PATH, 0)?;
        let metadata_metadata = metadata.metadata()?;
        trusted_file(&metadata_metadata, owner, u64::MAX)?;
        distinct(&data_metadata, &metadata_metadata)?;
        let value = Self {
            path: path.to_path_buf(),
            owner,
            parent,
            parent_metadata,
            data,
            data_metadata,
            metadata,
            metadata_metadata,
        };
        value.revalidate(owner)?;
        Ok(value)
    }

    pub(super) fn identities(&self) -> (BackingIdentity, BackingIdentity) {
        (
            identity(&self.data_metadata),
            identity(&self.metadata_metadata),
        )
    }

    pub(super) fn verify_record(
        &self,
        data: &BackingIdentity,
        metadata: &BackingIdentity,
    ) -> Result<()> {
        if &identity(&self.data_metadata) != data || &identity(&self.metadata_metadata) != metadata
        {
            return Err(IdentityError::BindingConflict);
        }
        Ok(())
    }

    fn revalidate_parent(&self, owner: u32) -> Result<()> {
        let held = self.parent.metadata()?;
        check_directory(&held, owner, false)?;
        let named = trusted_directory(&self.path, owner, false)?;
        if !same_parent(&self.parent_metadata, &held)
            || !same_parent(&self.parent_metadata, &named.metadata()?)
        {
            return Err(IdentityError::AuthorityChanged);
        }
        Ok(())
    }

    pub(super) fn revalidate(&self, owner: u32) -> Result<()> {
        if owner != self.owner {
            return Err(IdentityError::BindingConflict);
        }
        self.revalidate_parent(owner)?;
        distinct(&self.data_metadata, &self.metadata_metadata)?;
        for (name, file, admitted) in [
            ("data.img", &self.data, &self.data_metadata),
            ("metadata.img", &self.metadata, &self.metadata_metadata),
        ] {
            let held = file.metadata()?;
            trusted_file(&held, owner, u64::MAX)?;
            if !same_backing(admitted, &held) {
                return Err(IdentityError::AuthorityChanged);
            }
            let named = open_at(&self.parent, name, libc::O_PATH, 0)?;
            let current = named.metadata()?;
            trusted_file(&current, owner, u64::MAX)?;
            if !same_backing(admitted, &current) {
                return Err(IdentityError::AuthorityChanged);
            }
        }
        self.revalidate_parent(owner)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs::{self, OpenOptions};
    use std::os::fd::AsRawFd;
    use std::os::unix::fs::{FileExt, OpenOptionsExt, PermissionsExt};

    #[test]
    fn metadata_only_backings_keep_original_handles_and_reject_same_inode_roles() {
        fn assert_send_sync<T: Send + Sync>() {}
        assert_send_sync::<HeldBackings>();
        assert_send_sync::<super::super::IdentityLease>();
        let root = tempfile::tempdir().unwrap();
        fs::set_permissions(root.path(), fs::Permissions::from_mode(0o700)).unwrap();
        for name in ["data.img", "metadata.img"] {
            OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(0o600)
                .open(root.path().join(name))
                .unwrap()
                .set_len(4096)
                .unwrap();
        }
        // SAFETY: read-only effective UID query for this private fixture.
        let owner = unsafe { libc::geteuid() };
        let held = HeldBackings::open(root.path(), owner).unwrap();
        for file in [&held.data, &held.metadata] {
            // SAFETY: this fcntl command only inspects this live owned FD.
            let status = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
            // SAFETY: this fcntl command only inspects this live owned FD.
            let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFD) };
            assert!(status >= 0 && status & libc::O_PATH != 0);
            assert!(flags >= 0 && flags & libc::FD_CLOEXEC != 0);
            let mut byte = [0];
            assert_eq!(
                file.read_at(&mut byte, 0).unwrap_err().raw_os_error(),
                Some(libc::EBADF)
            );
        }
        let same_inode = held.data.try_clone().unwrap();
        assert!(
            distinct(&held.data.metadata().unwrap(), &same_inode.metadata().unwrap()).is_err()
        );
        fs::rename(
            root.path().join("data.img"),
            root.path().join("saved-data.img"),
        )
        .unwrap();
        fs::write(root.path().join("data.img"), vec![0; 4096]).unwrap();
        assert_eq!(
            held.data.metadata().unwrap().ino(),
            same_inode.metadata().unwrap().ino()
        );
        assert!(held.revalidate(owner).is_err());
    }
}
