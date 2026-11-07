/* Copyright 2026 Droidloom contributors. SPDX-License-Identifier: Apache-2.0 */
#if !defined(__aarch64__)
#error This payload must be compiled for AArch64, never the host ISA.
#endif
#include <asm/unistd.h>
#include "probe_abi.h"

.text
.p2align 2

/* x19 retains our output pointer; x19 and x20 are restored for the C caller.
 * The first instruction at each resume label records x0/x1. Skipping an
 * additional instruction after signal restoration therefore fails the probe.
 */
.macro P4_BODY name, fault, resume, opcode, before_x0
.global \name
.hidden \name
.type \name, %function
\name:
    .cfi_startproc
    stp x19, x20, [sp, #-16]!
    .cfi_def_cfa_offset 16
    .cfi_offset x19, -16
    .cfi_offset x20, -8
    mov x19, x0
    mov x0, #\before_x0
    mov x1, #P4_BEFORE_X1
    mov x8, #__NR_getpid
    mov x9, #P4_BEFORE_X9
    mov x10, #P4_BEFORE_X10
    cmp x0, x1
.global \fault
.hidden \fault
\fault:
    .inst \opcode
.global \resume
.hidden \resume
\resume:
    stp x0, x1, [x19, #P4_AFTER_X0]
    stp x8, x9, [x19, #P4_AFTER_X8]
    str x10, [x19, #P4_AFTER_X10]
    mov x11, sp
    str x11, [x19, #P4_AFTER_SP]
    adr x11, \resume
    str x11, [x19, #P4_AFTER_RESUME_PC]
    mov x11, #P4_COOKIE
    str x11, [x19, #P4_AFTER_COOKIE]
    mrs x11, nzcv
    str x11, [x19, #P4_AFTER_NZCV]
    ldp x19, x20, [sp], #16
    .cfi_def_cfa_offset 0
    .cfi_restore x19
    .cfi_restore x20
    ret
    .cfi_endproc
.size \name, .-\name
.endm

/* -1 cannot equal any successful getpid result, so treating SVC as NOP
 * cannot pass even when a process PID happens to equal a small sentinel.
 */
P4_BODY p4_probe_svc, p4_svc_fault, p4_svc_resume, 0xd4000001, -1
P4_BODY p4_probe_smc, p4_smc_fault, p4_smc_resume, 0xd4000003, P4_BEFORE_X0

.section .note.GNU-stack,"",%progbits
