// SPDX-License-Identifier: MPL-2.0

mod elf_file;
mod load_elf;
mod relocate;
#[cfg(feature = "g1c-trusted-observe")]
mod trusted_initial;

pub(super) use elf_file::ElfHeaders;
pub(in crate::process) use load_elf::ElfLoadInfo;
pub(super) use load_elf::load_elf_to_vmar;
#[cfg(feature = "g1c-trusted-observe")]
pub(in crate::process) use trusted_initial::{LoadedInitialImage, load_trusted_initial};
