/* Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0 */
#ifndef DROIDLOOM_SDK_VISIBILITY_CORE_H
#define DROIDLOOM_SDK_VISIBILITY_CORE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define SDK_KEY_COUNT 4
#define SDK_VALUE_BYTES 92
#define SDK_GROUP_MAX 32
#define SDK_TARGET_ID 1069U
#define SDK_LIFETIME_MS 2000U
#define SDK_TOKEN_BYTES 128U
#define SDK_START_TOKEN "READ_ROOT_AND_1069:"
#define SDK_FINISH_TOKEN "OBSERVED:"
static const char *const sdk_keys[SDK_KEY_COUNT] = {
    "ro.build.version.sdk", "ro.build.version.sdk_full",
    "ro.system.build.version.sdk", "ro.system.build.version.sdk_full"
};

struct sdk_value {
    int result;
    int saved_errno;
    unsigned char bytes[SDK_VALUE_BYTES];
};
struct sdk_credentials {
    uint32_t uids[3], gids[3];
    uint32_t groups[SDK_GROUP_MAX];
    unsigned int group_count;
    uint64_t effective, permitted, inheritable, bounding, ambient;
    int no_new_privileges;
};
enum sdk_drop_step {
    SDK_NO_NEW_PRIVILEGES, SDK_CLEAR_KEEP_CAPS, SDK_CLEAR_AMBIENT,
    SDK_CLEAR_BOUNDING, SDK_CLEAR_GROUPS, SDK_SET_GIDS, SDK_SET_UIDS,
    SDK_CLEAR_CAPS, SDK_RESTORE_PARENT_DEATH, SDK_DROP_STEPS
};
struct sdk_backend {
    void *context;
    bool (*within_budget)(void *);
    int (*get)(void *, const char *, unsigned char *, int *);
    int (*drop)(void *, enum sdk_drop_step);
    int (*credentials)(void *, struct sdk_credentials *);
};
static bool sdk_root(const struct sdk_credentials *c) {
    for (unsigned int i = 0; i != 3; ++i)
        if (c->uids[i] != 0 || c->gids[i] != 0) return false;
    return c->group_count <= SDK_GROUP_MAX;
}
static bool sdk_lowered(const struct sdk_credentials *c) {
    for (unsigned int i = 0; i != 3; ++i)
        if (c->uids[i] != SDK_TARGET_ID || c->gids[i] != SDK_TARGET_ID) return false;
    return c->group_count == 0 && c->effective == 0 && c->permitted == 0 &&
        c->inheritable == 0 && c->bounding == 0 && c->ambient == 0 &&
        c->no_new_privileges == 1;
}
static int sdk_read_four(const struct sdk_backend *b, struct sdk_value values[SDK_KEY_COUNT],
                         unsigned int *completed) {
    *completed = 0;
    for (unsigned int i = 0; i != SDK_KEY_COUNT; ++i) {
        if (!b->within_budget(b->context)) return -1;
        memset(values[i].bytes, 0xa5, sizeof(values[i].bytes));
        values[i].saved_errno = 0;
        values[i].result = b->get(b->context, sdk_keys[i], values[i].bytes,
                                &values[i].saved_errno);
        if (!b->within_budget(b->context)) return -2;
        int n = values[i].result;
        if (n < 0 || n >= SDK_VALUE_BYTES || values[i].bytes[n] != 0) return -3;
        for (int j = 0; j < n; ++j)
            if (values[i].bytes[j] == 0) return -4;
        *completed = i + 1;
    }
    return 0;  /* Empty/missing values remain valid observations, not health. */
}
static int sdk_drop_permanently(const struct sdk_backend *b,
                                struct sdk_credentials *observed,
                                enum sdk_drop_step *failed_step) {
    for (unsigned int i = 0; i != SDK_DROP_STEPS; ++i) {
        *failed_step = (enum sdk_drop_step)i;
        if (!b->within_budget(b->context)) return -1;
        if (b->drop(b->context, (enum sdk_drop_step)i) != 0) return -2;
    }
    if (!b->within_budget(b->context)) return -3;
    if (b->credentials(b->context, observed) != 0) return -4;
    if (!sdk_lowered(observed)) return -5;
    *failed_step = SDK_DROP_STEPS;
    return 0;
}
#endif
