// SPDX-License-Identifier: Apache-2.0
// Actual extracted native entry and production header. JNI exception handling
// and process credentials below are explicit seams, not Android authority.
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

#include "droidloom_app_zygote_spec.h"

struct JNIEnv {};
using jclass = void*;
using jint = int32_t;
using jboolean = uint8_t;
constexpr jboolean JNI_TRUE = 1;
static std::array<uint32_t, 4> credentials{};
static std::string exception_class, exception_message;
static unsigned exceptions = 0;
static uint32_t FixtureUid() { return credentials[0]; }
static uint32_t FixtureEuid() { return credentials[1]; }
static uint32_t FixtureGid() { return credentials[2]; }
static uint32_t FixtureEgid() { return credentials[3]; }
static int jniThrowException(JNIEnv*, const char* type, const char* message) {
    ++exceptions;
    exception_class = type;
    exception_message = message ? message : "";
    return 0;
}

#define getuid FixtureUid
#define geteuid FixtureEuid
#define getgid FixtureGid
#define getegid FixtureEgid
#include "actual_native_entry.inc"
#undef getuid
#undef geteuid
#undef getgid
#undef getegid

struct Input {
    int32_t uid = 61179, gid = 61179;
    jboolean child = JNI_TRUE;
    std::array<int32_t, 8> spec{{1, 1, 61179, 61179, 90200, 90231, 90200, 90231}};
    std::array<uint32_t, 4> owner{{0, 0, 0, 0}};
};
struct Case { const char* name; Input input; const char* expected; };

int main() {
    constexpr const char* unsupported = "java/lang/UnsupportedOperationException";
    constexpr const char* invalid = "java/lang/IllegalArgumentException";
    constexpr const char* denied = "java/lang/SecurityException";
    std::vector<Case> cases;
    auto add = [&](const char* name, const Input& value, const char* expected) {
        cases.push_back({name, value, expected});
    };
    Input value;
    add("valid_shape_root_is_still_unsupported", value, unsupported);
    value = {}; value.spec[0] = 2; add("wrong_version", value, invalid);
    value = {}; value.spec[1] = 2; add("wrong_kind", value, invalid);
    value = {}; value.spec[2] = 0; add("zero_initial_uid", value, invalid);
    value = {}; value.spec[3] = 0; add("zero_initial_gid", value, invalid);
    value = {}; value.spec[4] = 0; value.spec[6] = 0; add("zero_range_min", value, invalid);
    value = {}; value.spec[5] = 90199; value.spec[7] = 90199; add("inverted_range", value, invalid);
    value = {}; value.spec[6] = 90201; add("different_gid_min", value, invalid);
    value = {}; value.spec[7] = 90232; add("different_gid_max", value, invalid);
    value = {}; value.uid = 61180; add("target_uid_does_not_match_snapshot", value, invalid);
    value = {}; value.gid = 61180; add("target_gid_does_not_match_snapshot", value, invalid);
    value = {}; value.child = 0; add("not_child_zygote", value, invalid);
    value = {}; value.child = 2; add("noncanonical_jboolean", value, invalid);
    value = {}; value.uid = value.spec[2] = INT32_MIN; add("negative_initial_uid", value, invalid);
    value = {}; value.spec[5] = value.spec[7] = -1; add("negative_upper_bound", value, invalid);
    value = {}; value.spec[4] = value.spec[5] = value.spec[6] = value.spec[7] = INT32_MAX;
    add("int32_upper_boundary_still_unsupported", value, unsupported);
    value = {}; value.owner[0] = 1000; add("nonroot_real_uid", value, denied);
    value = {}; value.owner[1] = 1000; add("nonroot_effective_uid", value, denied);
    value = {}; value.owner[2] = 1000; add("nonroot_real_gid", value, denied);
    value = {}; value.owner[3] = 1000; add("nonroot_effective_gid", value, denied);

    unsigned assertions = 0;
    for (const auto& test : cases) {
        credentials = test.input.owner;
        exceptions = 0; exception_class.clear(); exception_message.clear();
        const auto& s = test.input.spec;
        com_android_internal_os_Zygote_nativeRequireDroidloomAppZygoteRoleV1(
                nullptr, nullptr, test.input.uid, test.input.gid, test.input.child,
                s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7]);
        if (exceptions != 1 || exception_class != test.expected || exception_message.empty()) {
            std::fprintf(stderr, "native entry control failed: %s\n", test.name);
            return 1;
        }
        assertions += 3;
        std::printf("{\"case\":\"%s\",\"state\":\"PASS\",\"exception\":\"%s\"}\n",
                    test.name, test.expected);
    }
    static_assert(!android::zygote::droidloom::kAppZygoteRoleAuthorizationEnabled);
    std::printf("{\"state\":\"PASS_TYPED_NATIVE_REJECTION_CONTROLS\",\"cases\":%zu,"
                "\"assertions\":%u,\"JNI_and_credentials_seams\":true,\"forks\":0,"
                "\"factory_grants\":0,\"Android_execution\":false}\n", cases.size(), assertions);
    return 0;
}
