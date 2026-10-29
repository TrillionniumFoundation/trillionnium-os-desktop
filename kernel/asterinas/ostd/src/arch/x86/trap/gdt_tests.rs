// SPDX-License-Identifier: MPL-2.0

//! CPUNODE descriptor encoding against Linux's observation ABI.

use super::*;
use crate::prelude::ktest;

#[ktest]
fn linux_cpunode_limit_keeps_exact_cpu_and_read_only_user_rights() {
    // Golden encodings from Linux setup_getcpu's explicit descriptor fields.
    // Neither a writable/executable bit nor page granularity may be added.
    for (cpu, expected) in [
        (0, 0x0040_f500_0000_0000),
        (1, 0x0040_f500_0000_0001),
        (123, 0x0040_f500_0000_007b),
        (4095, 0x0040_f500_0000_0fff),
    ] {
        assert_eq!(cpunode_descriptor(cpu), expected);
    }
}

#[ktest]
#[should_panic(expected = "CPU ID exceeds Linux vDSO CPUNODE field")]
fn linux_cpunode_refuses_to_alias_an_unrepresentable_cpu() {
    cpunode_descriptor(4096);
}
