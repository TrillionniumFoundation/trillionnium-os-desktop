//! Original fixed-path inode custody after explicit live persistent admission.
//! IdentityLease and its metadata-only HeldBackings stay unchanged.

use super::*;

fn same_mutable(left: FileIdentity, right: FileIdentity) -> bool {
    // Legitimate filesystem writes change mtime/ctime, never these identities.
    (left.dev, left.ino, left.mode, left.uid, left.gid, left.links, left.bytes)
        == (right.dev, right.ino, right.mode, right.uid, right.gid, right.links, right.bytes)
}

#[derive(Debug)]
pub(super) struct OriginalBackingPair {
    path: PathBuf,
    parent: File,
    parent_node: FileIdentity,
    pub(super) files: [File; 2],
    pub(super) nodes: [FileIdentity; 2],
    pub(super) policies: [PersistentImagePolicy; 2],
    pub(super) superblock_sha256: [String; 2],
}

impl OriginalBackingPair {
    pub(super) fn open(admission: &impl StorageAuthority) -> Result<Self> {
        admission.verify()?;
        let witness = admission.namespace();
        let selection = admission.selection();
        let policy = selection.persistent_data_policy()
            .map_err(|_| MountError::Rejected("explicit sealed persistent data policy required"))?;
        let path = selection.spec().data_dir.clone();
        require(path == PathBuf::from(format!("/var/lib/droidloom/users/{}/data", selection.spec().host_uid)),
            "only the exact selected original data directory is accepted")?;
        let lease = witness.identity_lease()?;
        let (uids, gids) = lease.broker_ranges();
        let policies = [policy.data.clone(), policy.metadata.clone()];
        for selected in &policies {
            selected.mapped_root(uids, gids).map_err(MountError::Rejected)?;
        }
        let parent = trusted_directory(&path, 0)?;
        let parent_node = FileIdentity::of(&parent.metadata()?);
        let probes = [
            open_leaf(&parent, c"data.img", libc::O_PATH)?,
            open_leaf(&parent, c"metadata.img", libc::O_PATH)?,
        ];
        // Metadata comparison still grants no body capability by itself.
        // The actual MAC/tree/selection prerequisites above are mandatory.
        lease.broker_verify_backing(&probes[0], &probes[1])?;
        let nodes = [FileIdentity::of(&probes[0].metadata()?), FileIdentity::of(&probes[1].metadata()?)];
        require((nodes[0].dev, nodes[0].ino) != (nodes[1].dev, nodes[1].ino),
            "distinct original data and metadata inodes required")?;
        for (node, selected) in nodes.iter().zip(&policies) {
            require(node.mode == libc::S_IFREG | 0o600 && node.uid == 0 && node.gid == 0
                && node.links == 1 && node.bytes == selected.image_bytes,
                "selected root-private single-link original backing identity required")?;
        }
        if let Some(copy) = &policy.original_copy {
            copy.verify_working(nodes.map(|node| [node.dev, node.ino, u64::from(node.mode),
                u64::from(node.uid), u64::from(node.gid), node.links, node.bytes]))
                .map_err(MountError::Rejected)?;
        }
        admission.verify()?;
        let readers = [
            open_leaf(&parent, c"data.img", libc::O_RDONLY | libc::O_NOATIME)?,
            open_leaf(&parent, c"metadata.img", libc::O_RDONLY | libc::O_NOATIME)?,
        ];
        lease.broker_verify_backing(&readers[0], &readers[1])?;
        let mut headers = [[0u8; 1024]; 2];
        for index in 0..2 {
            require(FileIdentity::of(&readers[index].metadata()?) == nodes[index],
                "original inode changed before readonly filesystem inspection")?;
            readers[index].read_exact_at(&mut headers[index], 1024)?;
            superblock::validate(&headers[index], &policies[index]).map_err(MountError::Rejected)?;
            require(FileIdentity::of(&readers[index].metadata()?) == nodes[index],
                "original inode changed during readonly filesystem inspection")?;
            admission.verify()?;
        }
        // A dirty, corrupt or unsupported filesystem has already failed before
        // any writable open, loop, journal replay or mount can occur.
        let files = [
            open_leaf(&parent, c"data.img", libc::O_RDWR | libc::O_NOATIME)?,
            open_leaf(&parent, c"metadata.img", libc::O_RDWR | libc::O_NOATIME)?,
        ];
        lease.broker_verify_backing(&files[0], &files[1])?;
        for index in 0..2 {
            require(FileIdentity::of(&files[index].metadata()?) == nodes[index],
                "writable open must retain the exact inspected original inode")?;
            // This original backing OFD lock supplements the durable identity
            // lease; it is never replaced by an asserted exclusivity boolean.
            zero_rc(unsafe { libc::flock(files[index].as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) })?;
            let mut after = [0u8; 1024];
            files[index].read_exact_at(&mut after, 1024)?;
            require(after == headers[index] && FileIdentity::of(&files[index].metadata()?) == nodes[index],
                "whole selected superblock and inode changed before mutable admission")?;
        }
        let value = Self {
            path, parent, parent_node, files, nodes, policies,
            superblock_sha256: headers.map(|header| format!("{:x}", Sha256::digest(header))),
        };
        value.revalidate(witness)?;
        admission.verify()?;
        Ok(value)
    }

    pub(super) fn revalidate(&self, witness: &impl early::BaseAuthority) -> Result<()> {
        witness.revalidate_live_admission()?;
        let lease = witness.identity_lease()?;
        lease.revalidate_for_broker()?;
        let fresh_parent = trusted_directory(&self.path, 0)?;
        require(self.parent_node.same_directory(FileIdentity::of(&self.parent.metadata()?))
            && self.parent_node.same_directory(FileIdentity::of(&fresh_parent.metadata()?)),
            "original held data directory replaced or changed authority")?;
        for (index, name) in [c"data.img", c"metadata.img"].iter().enumerate() {
            let fresh = open_leaf(&self.parent, name, libc::O_PATH)?;
            require(same_mutable(self.nodes[index], FileIdentity::of(&self.files[index].metadata()?))
                && same_mutable(self.nodes[index], FileIdentity::of(&fresh.metadata()?)),
                "original persistent backing role changed")?;
            let flags = unsafe { libc::fcntl(self.files[index].as_raw_fd(), libc::F_GETFL) };
            require(flags >= 0 && flags & libc::O_ACCMODE == libc::O_RDWR && flags & libc::O_PATH == 0,
                "held original writable backing descriptor changed")?;
        }
        lease.revalidate_for_broker()?;
        require(self.parent_node.same_directory(FileIdentity::of(&self.parent.metadata()?)),
            "original data parent authority changed across the bookend")
    }

    pub(super) fn durable_after_unbind(&self) -> Result<()> {
        for (file, node) in self.files.iter().zip(&self.nodes) {
            require(same_mutable(*node, FileIdentity::of(&file.metadata()?)),
                "retirement lost original mutable backing custody")?;
            file.sync_all()?;
            require(same_mutable(*node, FileIdentity::of(&file.metadata()?)),
                "retirement changed original backing identity")?;
        }
        Ok(())
    }
}

#[cfg(test)]
#[path = "production_persistent_data_fixture_backings.rs"]
pub(super) mod private_control;

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn mutable_backing_identity_allows_content_clocks_but_never_role_substitution() {
        let file = File::open("/dev/null").unwrap();
        let node = FileIdentity::of(&file.metadata().unwrap());
        let clock_only = FileIdentity { mtime: (9, 7), ctime: (10, 8), ..node };
        assert!(same_mutable(node, clock_only));
        for case in 0..7 {
            let mut changed = node;
            match case {
                0 => changed.dev ^= 1, 1 => changed.ino ^= 1,
                2 => changed.mode ^= 1, 3 => changed.uid ^= 1,
                4 => changed.gid ^= 1, 5 => changed.links += 1,
                _ => changed.bytes += 4096,
            }
            assert!(!same_mutable(node, changed));
        }
    }
}
