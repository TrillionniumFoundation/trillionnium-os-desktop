// SPDX-License-Identifier: MPL-2.0

//! Immutable, bounded syscall filters. Installation never retains user memory.
//! Strict mode and ALLOW/ERRNO/TRAP/KILL filters are implemented; TSYNC,
//! tracing and notification are not advertised as supported.

use crate::prelude::*;

pub(crate) const MAX_PROGRAM_INSNS: usize = 4096;
const MAX_CHAIN_COST: usize = 32768;
pub(crate) const KILL_THREAD: u32 = 0;
pub(crate) const KILL_PROCESS: u32 = 0x8000_0000;
pub(crate) const TRAP: u32 = 0x0003_0000;
pub(crate) const ERRNO: u32 = 0x0005_0000;
pub(crate) const ALLOW: u32 = 0x7fff_0000;
const ACTION_MASK: u32 = 0xffff_0000;

#[repr(C)]
#[derive(Clone, Copy, Debug, Pod)]
pub(crate) struct Instruction {
    pub(crate) code: u16,
    pub(crate) jt: u8,
    pub(crate) jf: u8,
    pub(crate) k: u32,
}

/// Native seccomp_data layout: signed syscall number, audit architecture,
/// instruction pointer and six register arguments. Pointers are never followed.
pub(crate) struct Data {
    words: [u32; 16],
}

impl Data {
    pub(crate) fn new(number: u64, arch: u32, ip: u64, args: [u64; 6]) -> Self {
        let mut words = [0; 16];
        words[0] = number as u32;
        words[1] = arch;
        for (index, value) in core::iter::once(ip).chain(args).enumerate() {
            words[index * 2 + 2] = value as u32;
            words[index * 2 + 3] = (value >> 32) as u32;
        }
        Self { words }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum Action {
    Allow,
    Errno(u16),
    Trap(u16),
    KillThread,
    KillProcess,
}

impl Action {
    fn from_raw(raw: u32) -> Self {
        match raw & ACTION_MASK {
            KILL_THREAD => Self::KillThread,
            KILL_PROCESS => Self::KillProcess,
            ERRNO => Self::Errno((raw as u16).min(4095)),
            TRAP => Self::Trap(raw as u16),
            ALLOW => Self::Allow,
            // Linux treats unknown actions as KILL_PROCESS. A dynamic RET A
            // cannot turn an unsupported or malformed result into permission.
            _ => Self::KillProcess,
        }
    }

    fn precedence(self) -> u8 {
        match self {
            Self::KillProcess => 0,
            Self::KillThread => 1,
            Self::Trap(_) => 2,
            Self::Errno(_) => 3,
            Self::Allow => 4,
        }
    }
}

pub(crate) struct Program {
    insns: Vec<Instruction>,
}

impl Program {
    pub(crate) fn verify(insns: Vec<Instruction>) -> Result<Self> {
        if insns.is_empty() || insns.len() > MAX_PROGRAM_INSNS {
            return_errno_with_message!(Errno::EINVAL, "invalid seccomp program length");
        }
        if !matches!(insns.last().unwrap().code, 0x06 | 0x16) {
            return_errno_with_message!(Errno::EINVAL, "seccomp program must end with RET");
        }
        // Forward-only control flow allows a single ascending dataflow pass.
        // A scratch word must have been initialized on every incoming path.
        let mut incoming: Vec<Option<u16>> = vec![None; insns.len()];
        incoming[0] = Some(0);
        for (pc, instruction) in insns.iter().enumerate() {
            let Instruction { code, jt, jf, k } = *instruction;
            let mut initialized = incoming[pc];
            let mut successors = [None, None];
            match code {
                0x00 | 0x01 | 0x80 | 0x81 | 0x07 | 0x87 => {}
                0x20 if k % 4 == 0 && k < 64 => {}
                0x60 | 0x61 if k < 16 => {
                    if initialized.is_some_and(|mask| mask & (1 << k) == 0) {
                        return_errno_with_message!(Errno::EINVAL, "uninitialized BPF scratch read");
                    }
                }
                0x02 | 0x03 if k < 16 => {
                    initialized = initialized.map(|mask| mask | (1 << k));
                }
                // Unsigned 32-bit classic BPF ALU. Register shifts are
                // deliberately rejected until their compatibility is qualified.
                0x04 | 0x0c | 0x14 | 0x1c | 0x24 | 0x2c | 0x3c | 0x44 | 0x4c | 0x54 | 0x5c
                | 0x84 | 0x9c | 0xa4 | 0xac => {}
                0x34 | 0x94 if k != 0 => {}
                0x64 | 0x74 if k < 32 => {}
                0x05 => {
                    let next = (pc + 1).checked_add(k as usize);
                    if next.is_none_or(|next| next >= insns.len()) {
                        return_errno_with_message!(Errno::EINVAL, "BPF jump outside program");
                    }
                    successors[0] = next;
                }
                0x15 | 0x1d | 0x25 | 0x2d | 0x35 | 0x3d | 0x45 | 0x4d => {
                    let yes = pc + 1 + jt as usize;
                    let no = pc + 1 + jf as usize;
                    if yes >= insns.len() || no >= insns.len() {
                        return_errno_with_message!(Errno::EINVAL, "BPF branch outside program");
                    }
                    successors = [Some(yes), Some(no)];
                }
                0x06 => {
                    if matches!(k & ACTION_MASK, 0x0007_0000 | 0x7fc0_0000 | 0x7ffc_0000) {
                        return_errno_with_message!(
                            Errno::EOPNOTSUPP,
                            "seccomp action not implemented"
                        );
                    }
                    continue;
                }
                0x16 => continue,
                _ => return_errno_with_message!(Errno::EINVAL, "unsupported BPF instruction"),
            }
            if code & 7 != 5 {
                successors[0] = Some(pc + 1);
            }
            for next in successors.into_iter().flatten() {
                if let Some(mask) = initialized {
                    incoming[next] = Some(incoming[next].map_or(mask, |old| old & mask));
                }
            }
        }
        Ok(Self { insns })
    }

    fn evaluate(&self, data: &Data) -> Action {
        let (mut a, mut x) = (0u32, 0u32);
        let mut scratch = [0u32; 16];
        let mut pc = 0usize;
        while let Some(instruction) = self.insns.get(pc) {
            let Instruction { code, jt, jf, k } = *instruction;
            pc += 1;
            let value = if code & 8 == 0 { k } else { x };
            match code {
                0x00 => a = k,
                0x01 => x = k,
                0x20 => a = data.words[k as usize / 4],
                0x60 => a = scratch[k as usize],
                0x61 => x = scratch[k as usize],
                0x80 => a = 64,
                0x81 => x = 64,
                0x02 => scratch[k as usize] = a,
                0x03 => scratch[k as usize] = x,
                0x07 => x = a,
                0x87 => a = x,
                0x04 | 0x0c => a = a.wrapping_add(value),
                0x14 | 0x1c => a = a.wrapping_sub(value),
                0x24 | 0x2c => a = a.wrapping_mul(value),
                0x34 | 0x3c => {
                    let Some(result) = a.checked_div(value) else {
                        return Action::KillThread;
                    };
                    a = result;
                }
                0x44 | 0x4c => a |= value,
                0x54 | 0x5c => a &= value,
                0x64 => a <<= k,
                0x74 => a >>= k,
                0x84 => a = a.wrapping_neg(),
                0x94 | 0x9c => {
                    let Some(result) = a.checked_rem(value) else {
                        return Action::KillThread;
                    };
                    a = result;
                }
                0xa4 | 0xac => a ^= value,
                0x05 => pc += k as usize,
                0x15 | 0x1d | 0x25 | 0x2d | 0x35 | 0x3d | 0x45 | 0x4d => {
                    let condition = match code & 0xf0 {
                        0x10 => a == value,
                        0x20 => a > value,
                        0x30 => a >= value,
                        0x40 => a & value != 0,
                        _ => return Action::KillProcess,
                    };
                    pc += if condition { jt } else { jf } as usize;
                }
                0x06 => return Action::from_raw(k),
                0x16 => return Action::from_raw(a),
                _ => return Action::KillProcess,
            }
        }
        // Structural validation makes fall-through unreachable. Fail closed
        // rather than permitting a syscall if that invariant ever regresses.
        Action::KillProcess
    }
}

#[derive(Clone, Default)]
pub(crate) enum Policy {
    #[default]
    Disabled,
    Strict,
    Filters(Arc<Vec<Arc<Program>>>),
}

impl Policy {
    pub(crate) fn mode(&self) -> usize {
        match self {
            Self::Disabled => 0,
            Self::Strict => 1,
            Self::Filters(_) => 2,
        }
    }

    pub(crate) fn install_strict(&mut self) -> Result<()> {
        if !matches!(self, Self::Disabled) {
            return_errno_with_message!(Errno::EINVAL, "seccomp mode cannot be changed");
        }
        *self = Self::Strict;
        Ok(())
    }

    pub(crate) fn install_filter(&mut self, program: Program) -> Result<()> {
        let previous = match self {
            Self::Disabled => &[][..],
            Self::Strict => {
                return_errno_with_message!(Errno::EINVAL, "strict seccomp is irreversible")
            }
            Self::Filters(filters) => filters.as_slice(),
        };
        let cost = previous.iter().map(|p| p.insns.len() + 4).sum::<usize>() + program.insns.len();
        if cost > MAX_CHAIN_COST {
            return_errno_with_message!(Errno::ENOMEM, "seccomp filter chain limit");
        }
        let mut filters = Vec::with_capacity(previous.len() + 1);
        filters.extend(previous.iter().cloned());
        filters.push(Arc::new(program));
        // A flat immutable vector avoids recursively dropping a long chain.
        *self = Self::Filters(Arc::new(filters));
        Ok(())
    }

    pub(crate) fn evaluate(&self, data: &Data, strict_allowed: bool) -> Action {
        match self {
            Self::Disabled => Action::Allow,
            Self::Strict => {
                if strict_allowed {
                    Action::Allow
                } else {
                    Action::KillThread
                }
            }
            Self::Filters(filters) => {
                let mut result = Action::Allow;
                // Equal-precedence data belongs to the newest filter.
                for program in filters.iter().rev() {
                    let candidate = program.evaluate(data);
                    if candidate.precedence() < result.precedence() {
                        result = candidate;
                    }
                }
                result
            }
        }
    }
}

#[cfg(ktest)]
mod tests;
