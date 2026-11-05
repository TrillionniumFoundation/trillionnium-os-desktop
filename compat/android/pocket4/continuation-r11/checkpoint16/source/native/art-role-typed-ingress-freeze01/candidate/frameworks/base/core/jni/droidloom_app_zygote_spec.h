/* SPDX-License-Identifier: Apache-2.0 */
#ifndef DROIDLOOM_APP_ZYGOTE_SPEC_H_
#define DROIDLOOM_APP_ZYGOTE_SPEC_H_

#include <stdint.h>

namespace android::zygote::droidloom {

inline constexpr int32_t kAppZygoteSpecVersion = 1;
inline constexpr int32_t kAppZygoteSpecKind = 1;

// This revision carries immutable launch data to the actual native fork
// entry. It installs no policy and issues no factory approval. Changing this
// constant alone must never enable a role: the native entry has a
// compile-time rejection until the early-policy and parent-approval path exists.
inline constexpr bool kAppZygoteRoleAuthorizationEnabled = false;

struct AppZygoteSpecV1 final {
    const int32_t version;
    const int32_t kind;
    const int32_t initial_uid;
    const int32_t initial_gid;
    const int32_t uid_min;
    const int32_t uid_max;
    const int32_t gid_min;
    const int32_t gid_max;

    // Only a structural check of the Java/JNI transport. The authenticated
    // Java ingress also applies Process.FIRST_APP_ZYGOTE_ISOLATED_UID. Neither
    // check proves a seccomp program, NNP, an immutable pair or a parent grant.
    constexpr bool Matches(int32_t uid, int32_t gid, bool child_zygote) const {
        return version == kAppZygoteSpecVersion && kind == kAppZygoteSpecKind &&
                child_zygote && initial_uid > 0 && initial_gid > 0 &&
                initial_uid == uid && initial_gid == gid && uid_min > 0 &&
                uid_min <= uid_max && gid_min == uid_min && gid_max == uid_max;
    }
};

static_assert(sizeof(AppZygoteSpecV1) == 8 * sizeof(int32_t));

}  // namespace android::zygote::droidloom
#endif
