//! cfg(test) typed factory for exactly newly formatted private inodes.
//! Production constructors and complete MAC/prepared gates stay unchanged.
use super::*;

pub(in crate::production_mounts::persistent_data) fn open_fixture(
    fixture: &crate::production_identity::tests::persistent_fixture::PersistentFixture<'_>,
    witness: &OwnedNamespaceWitness<'_>,
) -> Result<OriginalBackingPair> {
        fixture.verify_lease(witness.identity_lease()?)?;
        witness.revalidate_live_admission()?;
        let path = fixture.backings_path().to_path_buf();
        fixture.verify()?;
        let lease = witness.identity_lease()?;
        let (uids, gids) = lease.broker_ranges();
        let selected = |role: crate::production_identity::tests::persistent_fixture::ImageRole| PersistentImagePolicy {
            image_bytes: role.bytes(), filesystem_uuid: role.uuid().into(),
            feature_compat: 0x3c, feature_incompat: 0x22c2, feature_ro_compat: 0x46b,
            guest_root_uid: 0, guest_root_gid: 0, guest_root_mode: 0o755,
        };
        use crate::production_identity::tests::persistent_fixture::ImageRole;
        let policies = [selected(ImageRole::Data), selected(ImageRole::Metadata)];
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
        // Only this cfg(test) typed newly-formatted fixture admits its bodies.
        lease.broker_verify_backing(&probes[0], &probes[1])?;
        let nodes = [FileIdentity::of(&probes[0].metadata()?), FileIdentity::of(&probes[1].metadata()?)];
        require((nodes[0].dev, nodes[0].ino) != (nodes[1].dev, nodes[1].ino),
            "distinct original data and metadata inodes required")?;
        for (node, selected) in nodes.iter().zip(&policies) {
            require(node.mode == libc::S_IFREG | 0o600 && node.uid == 0 && node.gid == 0
                && node.links == 1 && node.bytes == selected.image_bytes,
                "selected root-private single-link original backing identity required")?;
        }
        fixture.verify_lease(witness.identity_lease()?)?;
        witness.revalidate_live_admission()?;
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
            fixture.verify_lease(witness.identity_lease()?)?;
        witness.revalidate_live_admission()?;
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
        let value = OriginalBackingPair {
            path, parent, parent_node, files, nodes, policies,
            superblock_sha256: headers.map(|header| format!("{:x}", Sha256::digest(header))),
        };
        value.revalidate(witness)?;
        fixture.verify_lease(witness.identity_lease()?)?;
        witness.revalidate_live_admission()?;
        Ok(value)
    }
