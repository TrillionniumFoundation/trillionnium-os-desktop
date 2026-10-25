// SPDX-License-Identifier: MPL-2.0

mod elf_file;
#[cfg(any(feature = "g2-native-agentd", ktest))]
#[cfg_attr(ktest, allow(dead_code))]
mod g2_profile;
mod load_elf;
mod relocate;
#[cfg(feature = "g1c-trusted-observe")]
mod trusted_initial;

pub(super) use elf_file::ElfHeaders;
pub(in crate::process) use load_elf::ElfLoadInfo;
pub(super) use load_elf::load_elf_to_vmar;
#[cfg(feature = "g1c-trusted-observe")]
pub(in crate::process) use trusted_initial::{LoadedInitialImage, load_trusted_initial};
#[cfg(feature = "g1d-trusted-control")]
pub(in crate::process) use trusted_initial::TrustedInitialSnapshot;
