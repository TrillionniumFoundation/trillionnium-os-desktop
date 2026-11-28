// SPDX-License-Identifier: GPL-3.0-or-later
// Test closed selectors and inode/deadline gates without PID 1 or device access.
#include "board_policy.c"
#include <assert.h>

static unsigned selector_checks, inode_checks, context_checks, deadline_checks, self_attribute_checks;
static int select_line(const char *input)
{
    char line[1024], digest[65] = {0};
    assert(strlen(input) < sizeof(line));
    strcpy(line, input);
    ++selector_checks;
    return working_selector(line, digest);
}

static void typed_self_checks(void)
{
    const char *expected = WORKING_WATCHDOG_LABELER;
    _Alignas(struct lsm_ctx) unsigned char bytes[256] = {0};
    struct lsm_ctx *context = (struct lsm_ctx *)bytes;
    size_t n = strlen(expected) + 1;
    uint32_t size = (uint32_t)((sizeof(*context) + n + 7) & ~(size_t)7);
    context->id = LSM_ID_SELINUX;
    context->len = size;
    context->ctx_len = n;
    memcpy(context->ctx, expected, n);
    assert(working_self_record(context, 1, size, sizeof(bytes), expected) == 0);
    ++self_attribute_checks;
    for (unsigned mutation = 0; mutation < 11; ++mutation) {
        _Alignas(struct lsm_ctx) unsigned char bad[256];
        memcpy(bad, bytes, sizeof(bad));
        struct lsm_ctx *value = (struct lsm_ctx *)bad;
        uint32_t actual_size = size;
        long count = 1;
        switch (mutation) {
        case 0: value->id = LSM_ID_APPARMOR; break;
        case 1: value->flags = 1; break;
        case 2: value->len += 8; break;
        case 3: --value->ctx_len; break;
        case 4: ++actual_size; break;
        case 5: count = 0; break;
        case 6: count = 2; break;
        case 7: value->ctx[n - 1] = '\n'; break;
        case 8: value->ctx[0] = 'x'; break;
        case 9: value->ctx_len = UINT64_MAX; break;
        case 10: value->ctx[n] = 1; break;
        }
        assert(working_self_record(value, count, actual_size, sizeof(bad), expected) == -1);
        ++self_attribute_checks;
    }
    assert(working_self_record(context, 1, size, sizeof(*context), expected) == -1);
    ++self_attribute_checks;
    assert(working_self_record(context, -1, size, sizeof(bytes), expected) == -1);
    ++self_attribute_checks;
    assert(working_self_record(context, 1, size, sizeof(bytes), "u:r:kernel:s0") == -1);
    ++self_attribute_checks;
}

int main(void)
{
    typed_self_checks();
    const char *sha = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    char valid[512], value[1024];
    snprintf(valid, sizeof(valid), "quiet droidloom.working=%s droidloom.working.config=%s droidloom.working.return=%s", sha, sha, sha);
    assert(select_line("root=UUID=ordinary quiet") == 0);
    assert(select_line(valid) == 1);
    snprintf(value, sizeof(value), "%s droidloom.working=%s", valid, sha);
    assert(select_line(value) == -1);
    snprintf(value, sizeof(value), "%s droidloom.once=anything", valid);
    assert(select_line(value) == -1);
    snprintf(value, sizeof(value), "%s droidloom.working.extra=ignored", valid);
    assert(select_line(value) == -1);
    assert(select_line("droidloom.working") == -1);
    assert(select_line("droidloom.working=") == -1);
    snprintf(value, sizeof(value), "droidloom.working=%s droidloom.working.return=%s", sha, sha);
    assert(select_line(value) == -1);
    snprintf(value, sizeof(value), "droidloom.working=%s droidloom.working.config=%s", sha, sha);
    assert(select_line(value) == -1);
    snprintf(value, sizeof(value), "droidloom.working.config=%s droidloom.working.return=%s", sha, sha);
    assert(select_line(value) == -1);
    strcpy(value, valid); value[strlen(value)-1] = 'F';
    assert(select_line(value) == -1);
    for (const char *const *p=(const char *const[]){"watchdog0","watchdog1","watchdog999",NULL}; *p; ++p)
        assert(working_watchdog_name(*p) == 0);
    for (const char *const *p=(const char *const[]){"watchdog","watchdog01","watchdog1000","watchdog-1","watchdog1/x","../watchdog0",NULL}; *p; ++p)
        assert(working_watchdog_name(*p) == -1);

    struct stat a = {.st_dev=1,.st_ino=2,.st_mode=S_IFCHR|0600,
        .st_uid=0,.st_gid=0,.st_nlink=1,.st_size=0,.st_rdev=makedev(10,130),
        .st_mtim={3,4},.st_ctim={5,6}};
    struct stat b=a;
    assert(working_same_inode(&a,&b,1)); ++inode_checks;
    b.st_atim.tv_sec=99;
    assert(working_same_inode(&a,&b,1)); ++inode_checks;
    b=a; ++b.st_ctim.tv_nsec;
    assert(!working_same_inode(&a,&b,1) && working_same_inode(&a,&b,0)); ++inode_checks;
    for (unsigned n=0;n<10;++n) {
        b=a;
        switch(n) {
        case 0: ++b.st_dev; break; case 1: ++b.st_ino; break;
        case 2: b.st_mode|=0020; break; case 3: ++b.st_uid; break;
        case 4: ++b.st_gid; break; case 5: ++b.st_nlink; break;
        case 6: ++b.st_size; break; case 7: ++b.st_rdev; break;
        case 8: ++b.st_mtim.tv_sec; break; case 9: ++b.st_mtim.tv_nsec; break;
        }
        assert(!working_same_inode(&a,&b,0)); ++inode_checks;
    }
    const char *ctx=WORKING_WATCHDOG_OLD_CONTEXT;
    const size_t len=strlen(ctx);
    assert(working_context_bytes(ctx,(ssize_t)len,ctx)); ++context_checks;
    assert(working_context_bytes(ctx,(ssize_t)len+1,ctx)); ++context_checks;
    snprintf(value,sizeof(value),"%s\n",ctx);
    assert(working_context_bytes(value,(ssize_t)len+1,ctx)); ++context_checks;
    value[len]='x';
    assert(!working_context_bytes(value,(ssize_t)len+1,ctx)); ++context_checks;
    assert(!working_context_bytes(ctx,(ssize_t)len-1,ctx)); ++context_checks;
    assert(!working_context_bytes(WORKING_WATCHDOG_CONTEXT,strlen(WORKING_WATCHDOG_CONTEXT),ctx)); ++context_checks;
    uint64_t now;
    assert(working_now(&now)==0 && now>0);
    assert(working_before(0)==-1 && errno==ETIMEDOUT); ++deadline_checks;
    assert(working_before(UINT64_MAX)==0); ++deadline_checks;
    struct working_watchdog_birth held={.device=-1,.directory=-1,.proc_fds=-1};
    assert(getpid()!=1);
    assert(working_watchdog_hold(&held)==-1 && errno==EINVAL); ++deadline_checks;
    held.selected=1;
    assert(working_watchdog_label(&held)==-1 && errno==EACCES); ++deadline_checks;
    printf("{\"selector_checks\":%u,\"inode_checks\":%u,\"context_checks\":%u,\"deadline_checks\":%u,\"self_attribute_checks\":%u,\"runtime_qualified\":false}\n",
        selector_checks,inode_checks,context_checks,deadline_checks,self_attribute_checks);
    return 0;
}
