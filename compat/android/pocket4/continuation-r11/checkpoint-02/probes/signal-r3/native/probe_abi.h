/* Copyright 2026 Droidloom contributors. SPDX-License-Identifier: Apache-2.0 */
#ifndef DROIDLOOM_OWNED_SIGNAL_PROBE_ABI_H
#define DROIDLOOM_OWNED_SIGNAL_PROBE_ABI_H

/* This is our own result record, not a replacement for any system ABI. */
#define P4_AFTER_X0 0
#define P4_AFTER_X1 8
#define P4_AFTER_X8 16
#define P4_AFTER_X9 24
#define P4_AFTER_X10 32
#define P4_AFTER_SP 40
#define P4_AFTER_RESUME_PC 48
#define P4_AFTER_COOKIE 56
#define P4_AFTER_NZCV 64
#define P4_AFTER_SIZE 72

#define P4_BEFORE_X0 0x1111
#define P4_BEFORE_X1 0x2222
#define P4_BEFORE_X9 0x9999
#define P4_BEFORE_X10 0xaaaa
#define P4_RESTORED_X0 0x5a01
#define P4_RESTORED_X1 0x5a02
#define P4_RESTORED_X8 0x5a08
#define P4_RESTORED_X9 0x5a09
#define P4_RESTORED_X10 0x5a0a
#define P4_COOKIE 0x4f4b
#define P4_NZCV_MASK 0xf0000000
#define P4_BEFORE_NZCV 0x80000000
#define P4_RESTORED_NZCV 0x60000000

#ifndef __ASSEMBLER__
#include <stddef.h>
#include <stdint.h>
struct p4_after {
    uint64_t x0, x1, x8, x9, x10, sp, resume_pc, cookie, nzcv;
};
_Static_assert(offsetof(struct p4_after, x0) == P4_AFTER_X0, "x0 offset");
_Static_assert(offsetof(struct p4_after, x1) == P4_AFTER_X1, "x1 offset");
_Static_assert(offsetof(struct p4_after, x8) == P4_AFTER_X8, "x8 offset");
_Static_assert(offsetof(struct p4_after, x9) == P4_AFTER_X9, "x9 offset");
_Static_assert(offsetof(struct p4_after, x10) == P4_AFTER_X10, "x10 offset");
_Static_assert(offsetof(struct p4_after, sp) == P4_AFTER_SP, "sp offset");
_Static_assert(offsetof(struct p4_after, resume_pc) == P4_AFTER_RESUME_PC, "pc offset");
_Static_assert(offsetof(struct p4_after, cookie) == P4_AFTER_COOKIE, "cookie offset");
_Static_assert(offsetof(struct p4_after, nzcv) == P4_AFTER_NZCV, "NZCV offset");
_Static_assert(sizeof(struct p4_after) == P4_AFTER_SIZE, "after size");

uint64_t p4_probe_svc(struct p4_after* after);
uint64_t p4_probe_smc(struct p4_after* after);
extern const unsigned char p4_svc_fault[], p4_svc_resume[];
extern const unsigned char p4_smc_fault[], p4_smc_resume[];
#endif
#endif
