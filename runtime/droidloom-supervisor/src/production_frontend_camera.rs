//! Optional camera bytes and endpoint belong to the original four-image cohort.
use super::{EarlyBoardResources, Listener, Seal, image_file, wire};
use crate::production_application::camera::CameraOwner;
use droidloom_contracts::system_ext::CameraDeclaration;
use sha2::{Digest, Sha256};
use std::ffi::CStr;
use std::fs::File;
use std::io;
use std::os::fd::AsFd;
use std::os::unix::fs::{FileExt, MetadataExt};

const MEMBERS: [(&[&CStr], bool); 4] = [
    (
        &[
            c"system",
            c"system_ext",
            c"framework",
            c"droidloom-camera-producer.jar",
        ],
        false,
    ),
    (
        &[
            c"system",
            c"system_ext",
            c"etc",
            c"init",
            c"droidloom-camera-producer.rc",
        ],
        false,
    ),
    (
        &[
            c"system",
            c"system_ext",
            c"bin",
            c"droidloom-virtual-camera",
        ],
        true,
    ),
    (
        &[
            c"system",
            c"system_ext",
            c"etc",
            c"init",
            c"droidloom-virtual-camera.rc",
        ],
        false,
    ),
];

struct ImageMember {
    original: File,
    expected: Seal,
}
impl ImageMember {
    fn acquire(root: &File, index: usize, digest: &str) -> io::Result<Self> {
        let (parts, executable) = MEMBERS[index];
        let original = image_file(root, parts, executable)?;
        let expected = Seal::of(&original)?;
        let mode = if executable { 0o755 } else { 0o644 };
        let m = original.metadata()?;
        wire::check(
            m.uid() == 0 && m.gid() == 0 && m.mode() == libc::S_IFREG | mode,
            "camera image member owner or exact mode differs",
        )?;
        let mut parent = root.try_clone()?;
        for part in &parts[..parts.len() - 1] {
            parent = wire::openat(&parent, part, libc::O_PATH | libc::O_DIRECTORY)?;
        }
        let body = wire::openat(&parent, parts[parts.len() - 1], libc::O_RDONLY)?;
        wire::check(
            Seal::of(&body)? == expected,
            "camera image body differs from its held original inode",
        )?;
        let mut hash = Sha256::new();
        let mut offset = 0u64;
        let mut page = [0u8; 65536];
        loop {
            let count = body.read_at(&mut page, offset)?;
            if count == 0 {
                break;
            }
            offset = offset
                .checked_add(count as u64)
                .filter(|n| *n <= expected.integers[4])
                .ok_or_else(|| io::Error::other("camera image grew during hashing"))?;
            hash.update(&page[..count]);
        }
        wire::check(
            offset == expected.integers[4]
                && format!("{:x}", hash.finalize()) == digest
                && Seal::of(&body)? == expected
                && Seal::of(&original)? == expected,
            "camera image bytes differ from the original selected cohort",
        )?;
        Ok(Self { original, expected })
    }
    fn revalidate(&self, root: &File, index: usize) -> io::Result<()> {
        let (parts, executable) = MEMBERS[index];
        let named = image_file(root, parts, executable)?;
        wire::check(
            Seal::of(&self.original)? == self.expected && Seal::of(&named)? == self.expected,
            "camera member lost its original immutable image identity",
        )
    }
}

pub(super) struct CameraLane {
    // The actual child is retired before its sole listener and source custody.
    capture: CameraOwner,
    epoch: crate::production_mac::CameraMacEpoch,
    endpoint: Listener,
    root: File,
    selected: CameraDeclaration,
    members: [ImageMember; 4],
    retired: bool,
}
impl CameraLane {
    pub(super) fn prepare(
        board: &EarlyBoardResources,
        owner: &crate::production_execution::RuntimeMacOwner,
        root: &File,
        directory: &File,
    ) -> io::Result<Option<Self>> {
        let Some(selected) = board.camera_declaration()? else {
            return Ok(None);
        };
        wire::check(selected.valid(), "invalid selected camera declaration")?;
        let (mac, selection) = owner.objects().map_err(io::Error::other)?;
        let epoch = mac.camera_epoch(selection).map_err(io::Error::other)?;
        let digests = [
            selected.jar_sha256.as_str(),
            selected.init_rc_sha256.as_str(),
            selected.provider_sha256.as_str(),
            selected.provider_init_rc_sha256.as_str(),
        ];
        let mut members = Vec::with_capacity(4);
        for (index, digest) in digests.into_iter().enumerate() {
            members.push(ImageMember::acquire(root, index, digest)?);
        }
        board.revalidate()?;
        let endpoint = Listener::bind(
            directory.try_clone()?,
            c"camera",
            board.selection().spec().subordinate_gids.start,
            0o620,
            libc::SOCK_STREAM,
        )?;
        let listener = File::from(endpoint.fd.as_fd().try_clone_to_owned()?);
        let capture = CameraOwner::start(
            &listener,
            board.pidfd(),
            board.selection().spec().subordinate_uids.start,
            board.selection().spec().subordinate_gids.start,
        )
        .map_err(io::Error::other)?;
        let value = Self {
            capture,
            epoch,
            endpoint,
            root: root.try_clone()?,
            selected,
            members: members
                .try_into()
                .map_err(|_| io::Error::other("four camera members required"))?,
            retired: false,
        };
        value.revalidate(board)?;
        Ok(Some(value))
    }
    pub(super) fn revalidate(&self, board: &EarlyBoardResources) -> io::Result<()> {
        wire::check(
            !self.retired && board.camera_declaration()?.as_ref() == Some(&self.selected),
            "camera lane differs from the original selected generation",
        )?;
        self.epoch.revalidate().map_err(io::Error::other)?;
        self.endpoint.revalidate()?;
        for (index, member) in self.members.iter().enumerate() {
            member.revalidate(&self.root, index)?;
        }
        Ok(())
    }
    pub(super) fn progress(&mut self, board: &EarlyBoardResources) -> io::Result<()> {
        self.revalidate(board)?;
        self.capture.progress().map_err(io::Error::other)?;
        self.revalidate(board)
    }
    pub(super) fn retire(&mut self) -> io::Result<()> {
        if self.retired {
            return Ok(());
        }
        self.epoch.revalidate().map_err(io::Error::other)?;
        self.capture.retire().map_err(io::Error::other)?;
        self.epoch.revalidate().map_err(io::Error::other)?;
        self.endpoint.unlink()?;
        self.retired = true;
        Ok(())
    }
}
impl Drop for CameraLane {
    fn drop(&mut self) {
        if let Err(error) = self.retire() {
            eprintln!("original camera retirement failed: {error}");
        }
    }
}
