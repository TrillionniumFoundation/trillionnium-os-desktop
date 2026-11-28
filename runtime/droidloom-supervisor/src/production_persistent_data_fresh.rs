//! Positive, single-generation EMPTY proof. Only the original storage factory
//! can construct it, from complete readonly images before its first O_RDWR.
use super::*;
use crate::empty_meituan_contract::{self as contract, Origin};
use std::cell::Cell;

#[derive(Debug)]
pub(in super::super) struct FreshDiagnosticPair {
    readers: [File; 2],
    initial: [FileIdentity; 2],
    installation_attempted: Cell<bool>,
}
fn stable(node: FileIdentity) -> [u64; 7] {
    [
        node.dev,
        node.ino,
        u64::from(node.mode),
        u64::from(node.uid),
        u64::from(node.gid),
        node.links,
        node.bytes,
    ]
}
impl FreshDiagnosticPair {
    pub(in super::super) fn admit(
        readers: [File; 2],
        nodes: [FileIdentity; 2],
        admission: &impl StorageAuthority,
    ) -> Result<Self> {
        admission.verify()?;
        require(
            admission
                .selection()
                .persistent_data_policy()
                .map_err(io::Error::other)?
                .fresh_diagnostic
                .is_some(),
            "explicit fixed EMPTY diagnostic request required",
        )?;
        for index in 0..2 {
            let flags = unsafe { libc::fcntl(readers[index].as_raw_fd(), libc::F_GETFL) };
            require(
                flags >= 0
                    && flags & libc::O_ACCMODE == libc::O_RDONLY
                    && flags & libc::O_PATH == 0,
                "EMPTY admission requires original readonly descriptors before writable open",
            )?;
            require(
                FileIdentity::of(&readers[index].metadata()?) == nodes[index],
                "EMPTY initial readonly inode differs before complete verification",
            )?;
            contract::verify_initial_image(&readers[index], index, || {
                admission.verify().map_err(io::Error::other)
            })?;
            require(
                FileIdentity::of(&readers[index].metadata()?) == nodes[index],
                "EMPTY initial readonly inode differs after complete verification",
            )?;
        }
        admission.verify()?;
        Ok(Self {
            readers,
            initial: nodes,
            installation_attempted: Cell::new(false),
        })
    }
    pub(in super::super) fn comparison(&self, files: &[File; 2]) -> Result<Origin> {
        for index in 0..2 {
            require(
                same_mutable(
                    self.initial[index],
                    FileIdentity::of(&self.readers[index].metadata()?),
                ) && same_mutable(
                    self.initial[index],
                    FileIdentity::of(&files[index].metadata()?),
                ),
                "EMPTY origin lost its actual initial readonly and mutable backing inodes",
            )?;
        }
        let origin = Origin {
            schema: contract::SCHEMA.into(),
            initial_sha256: contract::IMAGES.map(|v| v.sha256.into()),
            backings: self.initial.map(stable),
        };
        origin
            .validate(origin.backings)
            .map_err(MountError::Rejected)?;
        Ok(origin)
    }
    pub(in super::super) fn claim_installation(&self, files: &[File; 2]) -> Result<()> {
        self.comparison(files)?;
        require(
            !self.installation_attempted.replace(true),
            "this independent EMPTY generation already attempted its single normal installation",
        )
    }
}
