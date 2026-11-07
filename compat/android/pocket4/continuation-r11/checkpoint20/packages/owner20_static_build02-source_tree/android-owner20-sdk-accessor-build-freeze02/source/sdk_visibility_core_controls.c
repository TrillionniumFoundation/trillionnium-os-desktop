/* Production core controls. Credential/property calls below are explicit seams.
 * No Android, credential change, namespace operation, fork, or device execution. */
#include "sdk_visibility_core.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>

struct fixture {
    unsigned int budget_calls, expire_at, gets, drops, credential_calls;
    int bad_value, failed_step, credential_error;
    struct sdk_credentials final;
};
static unsigned int assertions, cases;
static void check(bool value, const char *why) {
    ++assertions;
    if (!value) { fprintf(stderr, "assertion: %s\n", why); exit(1); }
}
static void passed(const char *name) {
    ++cases;
    printf("{\"name\":\"%s\",\"passed\":true}\n", name);
}
static void reset(struct fixture *f) {
    memset(f, 0, sizeof(*f));
    f->failed_step = -1;
    f->expire_at = 1000;
    for (unsigned int i = 0; i != 3; ++i)
        f->final.uids[i] = f->final.gids[i] = SDK_TARGET_ID;
    f->final.no_new_privileges = 1;
}
static bool clock_seam(void *context) {
    struct fixture *f = context;
    return f->budget_calls++ < f->expire_at;
}
static int get_seam(void *context, const char *key, unsigned char *buffer, int *saved_errno) {
    struct fixture *f = context;
    check(f->gets < SDK_KEY_COUNT * 2, "bounded total key calls");
    check(strcmp(key, sdk_keys[f->gets % SDK_KEY_COUNT]) == 0, "exact ordered fixed key");
    ++f->gets;
    *saved_errno = ENOENT; /* Recorded, not interpreted as the zero-value cause. */
    if (f->bad_value == 1) return SDK_VALUE_BYTES;
    if (f->bad_value == 2) { buffer[0] = '3'; buffer[1] = '7'; return 2; }
    if (f->bad_value == 3) { buffer[0] = '3'; buffer[1] = 0; buffer[2] = 0; return 2; }
    if (f->bad_value == 4) return -1;
    if (f->bad_value == 5) { buffer[0] = 0; return 0; }
    memcpy(buffer, "37.0", 5);
    return 4;
}
static int drop_seam(void *context, enum sdk_drop_step step) {
    struct fixture *f = context;
    check((unsigned int)step == f->drops, "exact irreversible drop order");
    ++f->drops;
    return (int)step == f->failed_step ? -1 : 0;
}
static int credentials_seam(void *context, struct sdk_credentials *out) {
    struct fixture *f = context;
    ++f->credential_calls;
    *out = f->final;
    return f->credential_error;
}
static struct sdk_backend backend(struct fixture *f) {
    struct sdk_backend b = {.context = f, .within_budget = clock_seam,
        .get = get_seam, .drop = drop_seam, .credentials = credentials_seam};
    return b;
}
int main(void) {
    struct fixture f;
    struct sdk_backend b;
    struct sdk_value values[SDK_KEY_COUNT];
    struct sdk_credentials actual, root;
    unsigned int completed;
    enum sdk_drop_step step;
    check(SDK_KEY_COUNT == 4 && SDK_TARGET_ID == 1069 && SDK_VALUE_BYTES == 92 &&
          SDK_LIFETIME_MS == 2000, "fixed limits and target");
    check(strlen(SDK_START_TOKEN) + 64 < SDK_TOKEN_BYTES &&
          strlen(SDK_FINISH_TOKEN) + 64 < SDK_TOKEN_BYTES, "actual token framing fits");
    check(strcmp(sdk_keys[0], "ro.build.version.sdk") == 0 &&
          strcmp(sdk_keys[1], "ro.build.version.sdk_full") == 0 &&
          strcmp(sdk_keys[2], "ro.system.build.version.sdk") == 0 &&
          strcmp(sdk_keys[3], "ro.system.build.version.sdk_full") == 0, "only four public keys");
    passed("fixed_keys_credentials_and_protocol_bounds");

    reset(&f); b = backend(&f);
    check(sdk_read_four(&b, values, &completed) == 0 && completed == 4 && f.gets == 4,
          "root reads complete");
    check(sdk_drop_permanently(&b, &actual, &step) == 0 && step == SDK_DROP_STEPS &&
          f.drops == SDK_DROP_STEPS && f.credential_calls == 1 && sdk_lowered(&actual),
          "all irreversible steps and verified final state");
    check(sdk_read_four(&b, values, &completed) == 0 && completed == 4 && f.gets == 8,
          "lower reads same keys once");
    check(values[0].saved_errno == ENOENT && values[0].result == 4,
          "errno observation not misused as value qualification");
    passed("root_then_verified_irreversible_drop_then_same_four_keys");

    reset(&f); b = backend(&f); f.bad_value = 5;
    check(sdk_read_four(&b, values, &completed) == 0 && completed == 4 &&
          values[3].result == 0, "empty values are observations");
    passed("missing_or_empty_values_are_retained_without_fake_sdk");

    const char *bad_names[] = {"oversized_getter_result", "missing_value_terminator",
        "embedded_nul_mismatch", "negative_getter_result"};
    for (int bad = 1; bad <= 4; ++bad) {
        reset(&f); b = backend(&f); f.bad_value = bad;
        check(sdk_read_four(&b, values, &completed) < 0 && completed == 0 &&
              f.gets == 1, "invalid result stops without more reads");
        passed(bad_names[bad - 1]);
    }
    reset(&f); b = backend(&f); f.expire_at = 0;
    check(sdk_read_four(&b, values, &completed) == -1 && completed == 0 &&
          f.gets == 0, "expired admission reads nothing");
    passed("expired_read_admission_calls_no_getter");
    reset(&f); b = backend(&f); f.expire_at = 1;
    check(sdk_read_four(&b, values, &completed) == -2 && completed == 0 &&
          f.gets == 1, "expired return cannot qualify");
    passed("getter_return_after_budget_is_failed_without_retry");

    const char *drop_names[SDK_DROP_STEPS] = {
        "no_new_privileges_failure_stops", "keepcaps_clear_failure_stops",
        "ambient_clear_failure_stops", "bounding_clear_failure_stops",
        "supplementary_groups_clear_failure_stops", "gid_drop_failure_stops",
        "uid_drop_failure_stops", "capability_zero_failure_stops",
        "parent_death_rearm_failure_stops"
    };
    for (unsigned int failed = 0; failed != SDK_DROP_STEPS; ++failed) {
        reset(&f); b = backend(&f); f.failed_step = (int)failed;
        check(sdk_drop_permanently(&b, &actual, &step) == -2 &&
              step == (enum sdk_drop_step)failed && f.drops == failed + 1 &&
              f.credential_calls == 0 && f.gets == 0, "first drop error retained");
        passed(drop_names[failed]);
    }
    reset(&f); b = backend(&f); f.expire_at = 0;
    check(sdk_drop_permanently(&b, &actual, &step) == -1 && f.drops == 0,
          "expired drop admission has no credential side effect");
    passed("expired_drop_admission_is_closed");

    reset(&f); b = backend(&f); f.credential_error = -1;
    check(sdk_drop_permanently(&b, &actual, &step) == -4 && f.gets == 0,
          "unreadable final credentials disallow lower reads");
    passed("final_credential_read_failure_is_closed");

    const char *cred_names[] = {"wrong_real_uid", "wrong_effective_uid", "wrong_saved_uid",
        "wrong_real_gid", "wrong_effective_gid", "wrong_saved_gid",
        "retained_supplementary_group", "retained_effective_capability",
        "retained_permitted_capability", "retained_inheritable_capability",
        "retained_bounding_capability", "retained_ambient_capability",
        "missing_no_new_privileges"};
    for (unsigned int bad = 0; bad != 13; ++bad) {
        reset(&f); b = backend(&f);
        if (bad < 3) f.final.uids[bad] = 0;
        else if (bad < 6) f.final.gids[bad - 3] = 0;
        else if (bad == 6) { f.final.group_count = 1; f.final.groups[0] = 0; }
        else if (bad == 7) f.final.effective = 1;
        else if (bad == 8) f.final.permitted = 1;
        else if (bad == 9) f.final.inheritable = 1;
        else if (bad == 10) f.final.bounding = 1;
        else if (bad == 11) f.final.ambient = 1;
        else f.final.no_new_privileges = 0;
        check(sdk_drop_permanently(&b, &actual, &step) == -5 && f.gets == 0,
              "residual privilege cannot authorize lower reads");
        passed(cred_names[bad]);
    }
    memset(&root, 0, sizeof(root));
    check(sdk_root(&root), "root initial snapshot positive");
    root.uids[2] = SDK_TARGET_ID;
    check(!sdk_root(&root), "nonroot saved uid refused");
    root.uids[2] = 0; root.group_count = SDK_GROUP_MAX + 1;
    check(!sdk_root(&root), "oversized root groups refused");
    passed("root_identity_gate_is_not_effective_uid_only");

    check(cases == 34, "exact declared case count");
    printf("{\"schema\":1,\"cases\":%u,\"assertions\":%u,\"all_passed\":true,"
           "\"property_and_credentials\":\"explicit backend seams\","
           "\"Android_calls\":0,\"credential_changes\":0,\"new_processes\":0}\n",
           cases, assertions);
    return 0;
}
