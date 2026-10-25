// SPDX-License-Identifier: MPL-2.0

use ostd::prelude::ktest;

use super::*;

fn insn(code: u16, k: u32, jt: u8, jf: u8) -> Instruction {
    Instruction { code, k, jt, jf }
}

fn constant(action: u32) -> Program {
    Program::verify(vec![insn(0x06, action, 0, 0)]).unwrap()
}

fn data(number: u64) -> Data {
    Data::new(
        number,
        0xc000_003e,
        0x1234_5678_9abc_def0,
        [0, 1, 2, 3, 4, u64::MAX],
    )
}

#[ktest]
fn seccomp_data_has_independent_native_uapi_offsets_and_register_values() {
    let data = data(39);
    assert_eq!(data.words[0], 39);
    assert_eq!(data.words[1], 0xc000_003e);
    assert_eq!(&data.words[2..4], &[0x9abc_def0, 0x1234_5678]);
    assert_eq!(&data.words[14..16], &[u32::MAX, u32::MAX]);
    let program = Program::verify(vec![
        insn(0x20, 4, 0, 0),
        insn(0x15, 0xc000_003e, 1, 0),
        insn(0x06, KILL_PROCESS, 0, 0),
        insn(0x06, ALLOW, 0, 0),
    ])
    .unwrap();
    assert_eq!(program.evaluate(&data), Action::Allow);
    assert_eq!(
        program.evaluate(&Data::new(39, 0x4000_0003, 0, [0; 6])),
        Action::KillProcess
    );
}

#[ktest]
fn seccomp_classic_filter_denies_only_the_selected_syscall() {
    let program = Program::verify(vec![
        insn(0x20, 0, 0, 0),
        insn(0x15, 39, 0, 1),
        insn(0x06, ERRNO | 13, 0, 0),
        insn(0x06, ALLOW, 0, 0),
    ])
    .unwrap();
    assert_eq!(program.evaluate(&data(39)), Action::Errno(13));
    assert_eq!(program.evaluate(&data(110)), Action::Allow);
    assert_eq!(program.evaluate(&data(u64::MAX)), Action::Allow);
}

#[ktest]
fn seccomp_verifier_rejects_structural_and_arithmetic_hazards() {
    for instructions in [
        vec![],
        vec![insn(0x00, 0, 0, 0)],
        vec![insn(0x05, u32::MAX, 0, 0), insn(0x06, ALLOW, 0, 0)],
        vec![insn(0x15, 0, 255, 0), insn(0x06, ALLOW, 0, 0)],
        vec![insn(0x20, 1, 0, 0), insn(0x06, ALLOW, 0, 0)],
        vec![insn(0x20, 64, 0, 0), insn(0x06, ALLOW, 0, 0)],
        vec![insn(0x34, 0, 0, 0), insn(0x06, ALLOW, 0, 0)],
        vec![insn(0x94, 0, 0, 0), insn(0x06, ALLOW, 0, 0)],
        vec![insn(0x64, 32, 0, 0), insn(0x06, ALLOW, 0, 0)],
        vec![insn(0x02, 16, 0, 0), insn(0x06, ALLOW, 0, 0)],
        vec![insn(0xffff, 0, 0, 0), insn(0x06, ALLOW, 0, 0)],
    ] {
        assert!(Program::verify(instructions).is_err());
    }
    assert!(Program::verify(vec![insn(0x06, ALLOW, 0, 0); MAX_PROGRAM_INSNS + 1]).is_err());
}

#[ktest]
fn seccomp_scratch_requires_initialization_on_every_incoming_path() {
    assert!(Program::verify(vec![insn(0x60, 0, 0, 0), insn(0x06, ALLOW, 0, 0)]).is_err());
    assert!(
        Program::verify(vec![
            insn(0x15, 0, 0, 1),
            insn(0x02, 0, 0, 0),
            insn(0x60, 0, 0, 0),
            insn(0x06, ALLOW, 0, 0),
        ])
        .is_err()
    );
    let program = Program::verify(vec![
        insn(0x00, ALLOW, 0, 0),
        insn(0x02, 0, 0, 0),
        insn(0x60, 0, 0, 0),
        insn(0x16, 0, 0, 0),
    ])
    .unwrap();
    assert_eq!(program.evaluate(&data(39)), Action::Allow);
}

#[ktest]
fn seccomp_filter_stacking_cannot_relax_an_inherited_restriction() {
    let mut parent = Policy::default();
    parent.install_filter(constant(ERRNO | 1)).unwrap();
    let mut child = parent.clone();
    child.install_filter(constant(ALLOW)).unwrap();
    assert_eq!(child.evaluate(&data(39), true), Action::Errno(1));
    child.install_filter(constant(ERRNO | 13)).unwrap();
    assert_eq!(child.evaluate(&data(39), true), Action::Errno(13));
    assert_eq!(parent.evaluate(&data(39), true), Action::Errno(1));
    child.install_filter(constant(KILL_THREAD)).unwrap();
    child.install_filter(constant(KILL_PROCESS)).unwrap();
    assert_eq!(child.evaluate(&data(39), true), Action::KillProcess);
}

#[ktest]
fn seccomp_chain_capacity_failure_preserves_the_original_policy() {
    let mut policy = Policy::default();
    for _ in 0..7 {
        policy
            .install_filter(Program::verify(vec![insn(0x06, ALLOW, 0, 0); 4096]).unwrap())
            .unwrap();
    }
    assert!(
        policy
            .install_filter(Program::verify(vec![insn(0x06, KILL_PROCESS, 0, 0); 4096]).unwrap())
            .is_err()
    );
    assert_eq!(policy.evaluate(&data(39), true), Action::Allow);
}

#[ktest]
fn seccomp_strict_mode_is_irreversible_and_filters_do_not_disable_it() {
    let mut policy = Policy::default();
    policy.install_strict().unwrap();
    assert_eq!(policy.mode(), 1);
    assert_eq!(policy.evaluate(&data(0), true), Action::Allow);
    assert_eq!(policy.evaluate(&data(39), false), Action::KillThread);
    assert!(policy.install_filter(constant(ALLOW)).is_err());
}

#[ktest]
fn seccomp_unknown_dynamic_action_and_zero_register_division_fail_closed() {
    let dynamic =
        Program::verify(vec![insn(0x00, 0x1234_0000, 0, 0), insn(0x16, 0, 0, 0)]).unwrap();
    assert_eq!(dynamic.evaluate(&data(39)), Action::KillProcess);
    let zero_division =
        Program::verify(vec![insn(0x3c, 0, 0, 0), insn(0x06, ALLOW, 0, 0)]).unwrap();
    assert_eq!(zero_division.evaluate(&data(39)), Action::KillThread);
    let wrapping = Program::verify(vec![
        insn(0x00, u32::MAX, 0, 0),
        insn(0x04, 1, 0, 0),
        insn(0x16, 0, 0, 0),
    ])
    .unwrap();
    assert_eq!(wrapping.evaluate(&data(39)), Action::KillThread);
}

#[ktest]
fn seccomp_unimplemented_static_actions_are_not_accepted_as_supported() {
    for action in [0x0003_0000, 0x0007_0000, 0x7fc0_0000, 0x7ffc_0000] {
        assert_eq!(
            Program::verify(vec![insn(0x06, action, 0, 0)])
                .err()
                .unwrap()
                .error(),
            Errno::EOPNOTSUPP
        );
    }
    assert_eq!(
        constant(ERRNO | u16::MAX as u32).evaluate(&data(39)),
        Action::Errno(4095)
    );
    assert_eq!(constant(ERRNO).evaluate(&data(39)), Action::Errno(0));
}
