// SPDX-License-Identifier: MPL-2.0

mod elf_file;
mod load_elf;
#[cfg(all(
    feature = "g2-original-owner-a39-v1",
    feature = "g2-original-owner-publish-v1"
))]
compile_error!("select only one original-owner image version");
#[cfg(any(
    feature = "g2-original-owner-a39-v1",
    feature = "g2-original-owner-publish-v1"
))]
#[cfg_attr(
    feature = "g2-original-owner-publish-v1",
    path = "publication_owner_profile.rs"
)]
#[allow(dead_code)]
mod original_owner_profile;
mod relocate;
#[cfg(feature = "g1c-trusted-observe")]
mod trusted_initial;

pub(super) use elf_file::ElfHeaders;
pub(in crate::process) use load_elf::ElfLoadInfo;
pub(super) use load_elf::load_elf_to_vmar;
#[cfg(feature = "g1d-trusted-control")]
pub(in crate::process) use trusted_initial::TrustedInitialSnapshot;
#[cfg(feature = "g1c-trusted-observe")]
pub(in crate::process) use trusted_initial::{LoadedInitialImage, load_trusted_initial};
