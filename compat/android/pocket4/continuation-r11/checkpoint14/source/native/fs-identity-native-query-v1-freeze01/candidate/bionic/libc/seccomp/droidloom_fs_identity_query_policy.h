/*
 * Copyright (C) 2026 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#pragma once

#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <stdint.h>

#include <vector>

namespace droidloom_seccomp {

// The architecture has already been checked by the enclosing base policy.
// The LP64 x86_64 syscall family uses 32-bit uid_t/gid_t. This prefix is
// appended only to the native architecture path, never to the i386 path.
// Compat *32, old16 and x32 numbers receive no new permission. UINT32_MAX is
// the invalid identity query: it returns the current fsuid/fsgid without
// changing credentials. Upper register bits are not part of that argument.
// Nonqueries and every other syscall fall through to the unchanged base
// table, whose accumulator is reloaded by ExamineSyscall immediately after
// this prefix. A later ALLOW cannot override a previously installed TRAP.
inline void AppendFsIdentityQueries(std::vector<sock_filter>& program,
                                    uint32_t setfsuid_nr, uint32_t setfsgid_nr) {
    static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__,
                  "The Android syscall argument layout must be little endian");
    program.push_back(BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                              offsetof(struct seccomp_data, nr)));
    program.push_back(BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, setfsuid_nr, 1, 0));
    program.push_back(BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, setfsgid_nr, 0, 3));
    program.push_back(BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                              offsetof(struct seccomp_data, args[0])));
    program.push_back(BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, UINT32_MAX, 0, 1));
    program.push_back(BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW));
}

}  // namespace droidloom_seccomp
