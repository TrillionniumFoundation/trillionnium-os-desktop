// SPDX-License-Identifier: MPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define BASE "/sys/fs/cgroup/page-memory"
#define WORK BASE "/work"
#define RECOVER BASE "/recover"
#define RACE BASE "/race"
#define TABLE BASE "/page-table"
#define PAGE 4096UL
static int failures;
static int denied_file;
static void check(const char *name, int pass) {
    printf("{\"case\":\"%s\",\"passed\":%s}\n", name, pass ? "true" : "false");
    failures += !pass;
}
static int store(const char *path, const char *text) {
    int fd = open(path, O_WRONLY); if (fd < 0) return -1;
    size_t length = strlen(text); ssize_t count = write(fd, text, length);
    int saved = errno; close(fd); errno = saved;
    return count == (ssize_t)length ? 0 : -1;
}
static int join(const char *group) {
    char path[256], pid[32]; snprintf(path, sizeof(path), "%s/cgroup.procs", group);
    snprintf(pid, sizeof(pid), "%d", getpid()); return store(path, pid);
}
static unsigned long stat_value(const char *group, const char *key) {
    char path[256], data[512] = {0}; snprintf(path, sizeof(path), "%s/hepta.page.stat", group);
    int fd = open(path, O_RDONLY); if (fd < 0) return ~0UL;
    ssize_t count = read(fd, data, sizeof(data)-1); close(fd); if (count <= 0) return ~0UL;
    for (char *line = data; line; line = strchr(line, '\n')) {
        if (*line == '\n') line++;
        if (!strncmp(line, key, strlen(key)) && line[strlen(key)] == ' ')
            return strtoul(line + strlen(key) + 1, NULL, 10);
        if (!*line) break;
    }
    return ~0UL;
}
static unsigned long number(const char *group, const char *attr) {
    char path[256], data[128] = {0}; snprintf(path, sizeof(path), "%s/%s", group, attr);
    int fd = open(path, O_RDONLY); if (fd < 0) return ~0UL;
    ssize_t count = read(fd, data, sizeof(data)-1); close(fd); if (count <= 0) return ~0UL;
    return strtoul(data + (!strncmp(data,"max ",4) ? 4 : 0), NULL, 10);
}
static int set_max(const char *group, unsigned long value) {
    char path[256], data[64]; snprintf(path, sizeof(path), "%s/hepta.page.max", group);
    snprintf(data, sizeof(data), "%lu", value); return store(path, data);
}
static void delay(void) { struct timespec t = {0, 1000000}; nanosleep(&t, NULL); }
static unsigned long await_stat(const char *group, const char *kind, unsigned long ceiling) {
    unsigned long value = stat_value(group, kind); unsigned count = 0;
    while (value > ceiling && count++ < 1000) { delay(); value = stat_value(group, kind); }
    printf("{\"refund_kind\":\"%s\",\"value\":%lu,\"observations\":%u}\n", kind, value, count);
    return value;
}
static unsigned long await_total(const char *group, unsigned long ceiling) {
    unsigned long value = number(group, "hepta.page.current"); unsigned count = 0;
    while (value > ceiling && count++ < 1000) { delay(); value = number(group,"hepta.page.current"); }
    printf("{\"total\":%lu,\"private\":%lu,\"anonymous_vmo\":%lu,\"file_cache\":%lu,\"observations\":%u}\n",value,stat_value(group,"private"),stat_value(group,"anonymous_vmo"),stat_value(group,"file_cache"),count);
    return value;
}
/* Commit the inherited stack VMO from the observer before fork. Otherwise a
 * child can first populate shared backing retained by the observer itself. */
__attribute__((noinline)) static void prefault_observer_stack(void) {
    volatile char stack[256*1024];
    for(size_t i=0;i<sizeof(stack);i+=PAGE)stack[i]=1;
}
static void warm(void) {
    volatile char stack[65536]; for (size_t i=0;i<sizeof(stack);i+=PAGE) stack[i]=1;
    (void)number(WORK,"hepta.page.current"); (void)stat_value(WORK,"private"); delay();
    printf("{\"warm\":%zu}\n",sizeof(stack));
}
static void shared_and_memfd(void) {
    unsigned long initial = stat_value(WORK, "anonymous_vmo");
    volatile unsigned char *memory = mmap(NULL, 2*PAGE, PROT_READ|PROT_WRITE, MAP_ANONYMOUS|MAP_SHARED, -1, 0);
    check("shared_mapping_created", memory != MAP_FAILED); if (memory == MAP_FAILED) return;
    memory[0]=0x41; memory[PAGE]=0x42;
    check("shared_anonymous_two_actual_pages_charged", stat_value(WORK,"anonymous_vmo") == initial+2*PAGE);
    pid_t child=fork(); check("shared_reference_child_created",child>=0);
    if (!child) {
        int rc=join(RECOVER); unsigned long before=stat_value(RECOVER,"anonymous_vmo");
        int valid=memory[0]==0x41 && memory[PAGE]==0x42;
        memory[0]=0x43;
        valid=valid && stat_value(RECOVER,"anonymous_vmo")==before;
        _exit(rc || !valid ? 1 : 0);
    }
    if (child>0) { int status; waitpid(child,&status,0); check("shared_reader_other_group_not_double_charged", WIFEXITED(status)&&WEXITSTATUS(status)==0&&memory[0]==0x43); }
    check("shared_origin_charge_survives_other_group_access",stat_value(WORK,"anonymous_vmo")==initial+2*PAGE);
    check("shared_mapping_unmap",munmap((void*)memory,2*PAGE)==0);
    check("shared_last_reference_refund",await_stat(WORK,"anonymous_vmo",initial)==initial);

    int fd=memfd_create("page-budget",0); check("memfd_created",fd>=0); if(fd<0)return;
    check("memfd_resize",ftruncate(fd,2*PAGE)==0);
    char data[PAGE]; memset(data,0x52,sizeof(data));
    check("memfd_write_commits_two_pages",pwrite(fd,data,PAGE,0)==PAGE&&pwrite(fd,data,PAGE,PAGE)==PAGE);
    check("memfd_physical_pages_charged",stat_value(WORK,"anonymous_vmo")==initial+2*PAGE);
    memory=mmap(NULL,2*PAGE,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
    check("memfd_mapping_created",memory!=MAP_FAILED);
    if(memory!=MAP_FAILED) {
        check("memfd_mapping_reuses_pages",memory[0]==0x52&&memory[PAGE]==0x52&&stat_value(WORK,"anonymous_vmo")==initial+2*PAGE);
        close(fd); fd=-1;
        check("closing_fd_keeps_mapped_page_charge",stat_value(WORK,"anonymous_vmo")==initial+2*PAGE);
        munmap((void*)memory,2*PAGE);
    }
    if(fd>=0)close(fd);
    check("memfd_final_mapping_and_fd_release_refund",await_stat(WORK,"anonymous_vmo",initial)==initial);
}
static void backend_file(void) {
    unsigned long initial=stat_value(WORK,"file_cache");
    int fd=open("/page-cache/cold.bin",O_RDWR); check("real_ext2_file_open",fd>=0); if(fd<0)return;
    char buffer[PAGE];
    check("real_ext2_cold_read",pread(fd,buffer,PAGE,0)==PAGE&&buffer[0]==0x31);
    unsigned long one=stat_value(WORK,"file_cache");
    check("cold_read_cache_page_is_charged",one>=initial+PAGE);
    check("warm_read_reuses_cached_page",pread(fd,buffer,PAGE,0)==PAGE&&stat_value(WORK,"file_cache")==one);
    volatile unsigned char *map=mmap(NULL,PAGE,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
    check("real_ext2_shared_mapping",map!=MAP_FAILED);
    if(map!=MAP_FAILED) {
        map[0]=0x32;
        check("shared_file_mapping_reuses_cache_charge",stat_value(WORK,"file_cache")==one);
        check("real_ext2_sync",msync((void*)map,PAGE,MS_SYNC)==0);
        munmap((void*)map,PAGE);
    }
    check("real_ext2_cache_stays_owned_after_unmap",stat_value(WORK,"file_cache")>=one);
    check("real_ext2_truncate",ftruncate(fd,0)==0);
    check("real_ext2_truncate_refunds_data_pages",await_stat(WORK,"file_cache",one-PAGE)<=one-PAGE);
    close(fd);
}
/* Parent remains outside the capped workload. IPC and libc paths are warmed
 * before the exact ceiling is installed, so denial is caused by a new VMO page. */
static void mixed_work(void) {
    failures=0;
    check("join_workload",join(WORK)==0); warm(); shared_and_memfd(); backend_file();
    _exit(failures?1:0);
}
static void capped_writer(int mode) {
    failures=0;
    if(join(WORK))_exit(20);
    warm();
    int fd=-1;
    if(mode==0) { fd=memfd_create("denied",0); if(fd<0||ftruncate(fd,PAGE))_exit(21); }
    if(mode==1) { fd=dup(denied_file); if(fd<0)_exit(21); }
    volatile unsigned char *map=MAP_FAILED;
    if(mode==2) { map=mmap(NULL,PAGE,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_SHARED,-1,0); if(map==MAP_FAILED)_exit(21); }
    char buffer[PAGE]; memset(buffer,0x55,sizeof(buffer));
    unsigned long before=number(WORK,"hepta.page.current");
    if(set_max(WORK,before))_exit(22);
    if(mode==2) { map[0]=0x66; _exit(23); }
    errno=0; ssize_t rc=pwrite(fd,buffer,PAGE,0); int saved=errno;
    /* Raising the max needs no new private page: same stack and warmed path. */
    if(set_max(WORK,before+16*PAGE))_exit(24);
    check(mode==0?"memfd_budget_denies_real_pwrite":"file_cache_budget_denies_real_pwrite",rc==-1&&saved==ENOMEM);
    close(fd); _exit(failures?1:0);
}
/* Exercise actual simultaneous VMO commit/final-refund versus limit writes.
 * The low ceiling exceeds all 4*128*3 pages even if no RCU refund occurs
 * during the loop, plus each worker's private fault context;
 * denial behavior is covered separately by the exact-ceiling cases above. */
static void concurrent_frames(void) {
    enum { WORKERS=4, ITERATIONS=128, CEILING_PAGES=4096 };
    check("concurrent_group_created",mkdir(RACE,0755)==0&&set_max(RACE,CEILING_PAGES*PAGE)==0);
    _Atomic unsigned *ready=mmap(NULL,PAGE,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_SHARED,-1,0);
    check("observer_owned_concurrent_barrier",ready!=MAP_FAILED); if(ready==MAP_FAILED)return;
    for(unsigned i=0;i<WORKERS+1;i++)atomic_init(&ready[i],0);
    pid_t children[WORKERS];
    for(unsigned worker=0;worker<WORKERS;worker++) {
        children[worker]=fork();
        if(children[worker]==0) {
            if(join(RACE))_exit(40);
            warm();
            char data[PAGE]; memset(data,0x72,sizeof(data));
            atomic_store(&ready[worker],1);
            while(!atomic_load(&ready[WORKERS]))delay();
            for(unsigned iteration=0;iteration<ITERATIONS;iteration++) {
                void *sparse=(void*)((4UL<<39)+((unsigned long)worker<<32)+((unsigned long)iteration<<21));
                volatile unsigned char *map=mmap(sparse,2*PAGE,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
                if(map!=sparse)_exit(41);
                map[0]=0x71; map[PAGE]=0x73;
                int fd=memfd_create("concurrent-budget",0);
                if(fd<0||ftruncate(fd,PAGE)||pwrite(fd,data,PAGE,0)!=PAGE)_exit(42);
                if(close(fd)||munmap((void*)map,2*PAGE))_exit(43);
                if(iteration%8==0)delay();
            }
            _exit(0);
        }
        check("concurrent_worker_created",children[worker]>0);
    }
    int all_ready=0;
    for(unsigned attempt=0;attempt<5000;attempt++) {
        unsigned count=0;for(unsigned i=0;i<WORKERS;i++)count+=atomic_load(&ready[i]);
        if(count==WORKERS){all_ready=1;break;}delay();
    }
    check("all_workers_ready_before_concurrent_start",all_ready);
    atomic_store(&ready[WORKERS],1);
    int valid=1;
    for(unsigned iteration=0;iteration<256;iteration++) {
        unsigned long ceiling=(iteration%2?CEILING_PAGES:2*CEILING_PAGES)*PAGE;
        valid=valid&&set_max(RACE,ceiling)==0;
        valid=valid&&number(RACE,"hepta.page.current")<=ceiling;
        delay();
    }
    check("concurrent_live_limit_updates_and_bound",valid);
    for(unsigned i=0;i<WORKERS;i++) {
        int status=0; if(children[i]>0)waitpid(children[i],&status,0);
        check("concurrent_actual_page_worker_passed",children[i]>0&&WIFEXITED(status)&&WEXITSTATUS(status)==0);
    }
    check("concurrent_all_final_frame_references_refunded",await_total(RACE,0)==0);
    munmap((void*)ready,PAGE);
    check("concurrent_group_removed",rmdir(RACE)==0);
}
/* Sparse addresses occupy new PML4 branches. Each first resident base page
 * therefore needs three real user page-table frames on this x86_64 profile. */
static void page_table_transactions(void) {
    failures=0;
    if(join(TABLE))_exit(50);
    warm();
    unsigned long before=stat_value(TABLE,"page_table");
    volatile unsigned char *source=mmap((void*)(1UL<<39),PAGE,PROT_READ|PROT_WRITE,
        MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
    check("sparse_page_table_mapping_created",source==(void*)(1UL<<39));
    if(source==MAP_FAILED)_exit(51);
    source[0]=0x79;
    check("sparse_fault_charges_three_actual_table_frames",stat_value(TABLE,"page_table")==before+3*PAGE);
    unsigned long current=number(TABLE,"hepta.page.current");
    unsigned long events=number(TABLE,"hepta.page.events");
    if(set_max(TABLE,current))_exit(52);
    errno=0;pid_t child=fork();int saved=errno;
    if(child==0)_exit(99);
    if(set_max(TABLE,current+64*PAGE))_exit(53);
    check("fork_root_page_table_denied_with_ENOMEM",child==-1&&saved==ENOMEM);
    if(child>0){int status;waitpid(child,&status,0);}
    check("fork_page_table_denial_event",number(TABLE,"hepta.page.events")>events);
    check("fork_denial_preserves_existing_mapping",source[0]==0x79);

    before=stat_value(TABLE,"page_table");
    current=number(TABLE,"hepta.page.current");
    if(set_max(TABLE,current+2*PAGE))_exit(64);
    errno=0;child=fork();saved=errno;
    if(child==0)_exit(99);
    if(set_max(TABLE,current+64*PAGE))_exit(65);
    check("partial_fork_table_allocation_denied_with_ENOMEM",child==-1&&saved==ENOMEM);
    if(child>0){int status;waitpid(child,&status,0);}
    check("partial_fork_preserves_parent_data",source[0]==0x79);
    check("partial_fork_table_frames_refunded",await_stat(TABLE,"page_table",before)==before);

    current=number(TABLE,"hepta.page.current");events=number(TABLE,"hepta.page.events");
    char *args[]={"/bin/page-memory-probe","unexpected-exec",NULL};
    char *env[]={NULL};
    if(set_max(TABLE,current))_exit(54);
    errno=0;int rc=execve(args[0],args,env);saved=errno;
    if(set_max(TABLE,current+64*PAGE))_exit(55);
    check("exec_new_page_table_denied_with_ENOMEM",rc==-1&&saved==ENOMEM);
    check("exec_page_table_denial_event",number(TABLE,"hepta.page.events")>events);
    check("exec_denial_keeps_old_image_and_data",source[0]==0x79);

    current=number(TABLE,"hepta.page.current");events=number(TABLE,"hepta.page.events");
    before=stat_value(TABLE,"page_table");
    if(set_max(TABLE,current))_exit(56);
    errno=0;void *moved=mremap((void*)source,PAGE,PAGE,MREMAP_MAYMOVE|MREMAP_FIXED,(void*)(2UL<<39));saved=errno;
    if(set_max(TABLE,current+64*PAGE))_exit(57);
    check("mremap_table_preflight_denied_with_ENOMEM",moved==MAP_FAILED&&saved==ENOMEM);
    check("mremap_failure_preserves_source_bytes",source[0]==0x79);
    check("mremap_table_denial_event",number(TABLE,"hepta.page.events")>events);
    moved=mremap((void*)source,PAGE,PAGE,MREMAP_MAYMOVE|MREMAP_FIXED,(void*)(2UL<<39));
    check("mremap_retry_after_budget_increase_succeeds",moved==(void*)(2UL<<39));
    if(moved!=MAP_FAILED) {
        check("mremap_retry_preserves_actual_data",*(volatile unsigned char*)moved==0x79);
        check("mremap_new_branch_has_real_table_charge",stat_value(TABLE,"page_table")==before+3*PAGE);
        munmap(moved,PAGE);
    }
    before=stat_value(TABLE,"page_table");
    unsigned long other=stat_value(RECOVER,"page_table");
    check("page_table_migrate_to_new_owner",join(RECOVER)==0);
    volatile unsigned char *migrated=mmap((void*)(5UL<<39),PAGE,PROT_READ|PROT_WRITE,
        MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
    check("migrated_sparse_mapping_created",migrated==(void*)(5UL<<39));
    if(migrated!=MAP_FAILED) {
        migrated[0]=0x74;
        check("old_page_table_charge_stays_original_owner",stat_value(TABLE,"page_table")==before);
        check("new_page_table_nodes_charge_current_membership",stat_value(RECOVER,"page_table")==other+3*PAGE);
        check("page_table_migrate_back",join(TABLE)==0);
        munmap((void*)migrated,PAGE);
    }
    /* Existing mremap semantics shrink the source and truncate a fixed
     * destination before table admission. Test that precise failure boundary. */
    volatile unsigned char *shrunk=mmap((void*)(6UL<<39),2*PAGE,PROT_READ|PROT_WRITE,
        MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
    void *target=mmap((void*)(7UL<<39),PAGE,PROT_READ|PROT_WRITE,
        MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
    check("shrink_remap_source_and_empty_target_created",shrunk==(void*)(6UL<<39)&&target==(void*)(7UL<<39));
    if(shrunk!=MAP_FAILED&&target!=MAP_FAILED) {
        shrunk[0]=0x68;shrunk[PAGE]=0x69;
        check("fixed_remap_target_initially_has_mapping",mprotect(target,PAGE,PROT_READ)==0);
        current=number(TABLE,"hepta.page.current");
        if(set_max(TABLE,current))_exit(66);
        errno=0;moved=mremap((void*)shrunk,2*PAGE,PAGE,MREMAP_MAYMOVE|MREMAP_FIXED,target);saved=errno;
        if(set_max(TABLE,current+64*PAGE))_exit(67);
        check("shrinking_remap_target_preflight_denied",moved==MAP_FAILED&&saved==ENOMEM);
        check("shrinking_remap_failure_keeps_retained_source_data",shrunk[0]==0x68);
        errno=0;rc=mprotect((void*)(shrunk+PAGE),PAGE,PROT_READ);saved=errno;
        check("shrinking_remap_failure_has_existing_tail_unmap_side_effect",rc==-1&&saved==ENOMEM);
        errno=0;rc=mprotect(target,PAGE,PROT_READ);saved=errno;
        check("fixed_remap_failure_has_existing_target_truncate_side_effect",rc==-1&&saved==ENOMEM);
        munmap((void*)shrunk,2*PAGE);
    }
    _exit(failures?58:0);
}
static void page_tables(void) {
    check("page_table_group_created",mkdir(TABLE,0755)==0);
    pid_t child=fork();if(child==0)page_table_transactions();
    int status=0;if(child>0)waitpid(child,&status,0);
    check("page_table_real_transactions_child_passed",child>0&&WIFEXITED(status)&&WEXITSTATUS(status)==0);
    check("page_table_final_frame_reference_refund",await_stat(TABLE,"page_table",0)==0);
    check("page_table_process_account_refund",await_total(TABLE,0)==0);
    check("migrated_page_table_original_owner_refund",await_stat(RECOVER,"page_table",0)==0);
    check("migrated_page_table_process_charge_refund",await_total(RECOVER,0)==0);
    check("page_table_reset_budget",store(TABLE "/hepta.page.max","max")==0);
    /* The backing page belongs to the observer and already exists. The child's
     * denied read allocates no data page, so this specifically probes tables. */
    int fd=memfd_create("observer-owned-page",0);
    char data[PAGE];memset(data,0x67,sizeof(data));
    check("page_table_observer_commits_shared_backing",fd>=0&&ftruncate(fd,PAGE)==0&&pwrite(fd,data,PAGE,0)==PAGE);
    unsigned long events=number(TABLE,"hepta.page.events");
    child=fork();
    if(child==0) {
        if(join(TABLE))_exit(59);
        warm();
        volatile unsigned char *map=mmap((void*)(3UL<<39),PAGE,PROT_READ,MAP_SHARED|MAP_FIXED_NOREPLACE,fd,0);
        if(map==MAP_FAILED)_exit(60);
        unsigned long current=number(TABLE,"hepta.page.current");
        if(set_max(TABLE,current))_exit(61);
        unsigned char value=map[0];_exit(value==0x67?62:63);
    }
    if(child>0)waitpid(child,&status,0);
    check("existing_shared_page_table_fault_denied_with_SIGSEGV",child>0&&WIFSIGNALED(status)&&WTERMSIG(status)==SIGSEGV);
    check("existing_shared_page_table_denial_event",number(TABLE,"hepta.page.events")>events);
    check("faulted_process_page_tables_refund",await_stat(TABLE,"page_table",0)==0);
    check("faulted_process_all_charges_refund",await_total(TABLE,0)==0);
    if(fd>=0)close(fd);
    check("page_table_group_removed",rmdir(TABLE)==0);
}
int main(int argc, char **argv) {
    if(argc>1){(void)argv;return 99;}
    setvbuf(stdout,NULL,_IONBF,0);
    check("work_group_create",mkdir(BASE,0755)==0&&mkdir(WORK,0755)==0&&mkdir(RECOVER,0755)==0);
    check("test_mount_directory",mkdir("/page-cache",0755)==0);
    int mounted=mount("/dev/vda","/page-cache","ext2",0,NULL);
    if(mounted)printf("{\"mount_errno\":%d}\n",errno);
    check("real_ext2_fixture_mount",mounted==0);
    if(failures)return 1;
    prefault_observer_stack();
    pid_t child=fork(); if(child==0)mixed_work();
    int status=0; check("mixed_child_created",child>0); if(child>0)waitpid(child,&status,0);
    check("mixed_real_paths_child_passed",child>0&&WIFEXITED(status)&&WEXITSTATUS(status)==0);
    check("release_real_filesystem_cache",umount("/page-cache")==0);
    check("mixed_process_private_final_frames_refunded",await_stat(WORK,"private",0)==0);
    check("mixed_process_page_table_frames_refunded",await_stat(WORK,"page_table",0)==0);
    unsigned long retained=number(WORK,"hepta.page.current");
    printf("{\"retained_after_unmount\":%lu,\"anonymous_vmo\":%lu,\"file_cache\":%lu}\n",retained,stat_value(WORK,"anonymous_vmo"),stat_value(WORK,"file_cache"));
    check("retained_cache_pages_still_accounted",retained==stat_value(WORK,"anonymous_vmo")+stat_value(WORK,"file_cache"));
    check("remount_real_ext2_fixture",mount("/dev/vda","/page-cache","ext2",0,NULL)==0);
    denied_file=open("/page-cache/denied.bin",O_RDWR);
    check("observer_opens_negative_file_metadata",denied_file>=0);
    for(int mode=0;mode<3;mode++) {
        check("reset_unlimited_budget",store(WORK "/hepta.page.max","max")==0);
        unsigned long events=number(WORK,"hepta.page.events");
        unsigned long retained_before=number(WORK,"hepta.page.current");
        child=fork(); if(child==0)capped_writer(mode);
        check("ceiling_child_created",child>0); if(child>0)waitpid(child,&status,0);
        check(mode==2?"shared_fault_denied_with_SIGSEGV":"buffered_allocation_negative_child_passed",child>0&&(mode==2?(WIFSIGNALED(status)&&WTERMSIG(status)==SIGSEGV):(WIFEXITED(status)&&WEXITSTATUS(status)==0)));
        check("real_page_denial_event_increment",number(WORK,"hepta.page.events")>events);
        check("denied_child_refunds_new_physical_frames",await_total(WORK,retained_before)==retained_before);
        check("observer_outside_exhausted_subtree",number(RECOVER,"hepta.page.current")==0);
    }
    child=fork();
    if(child==0) {
        if(join(RECOVER))_exit(30);
        volatile unsigned char *private=mmap(NULL,4*PAGE,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
        volatile unsigned char *shared=mmap(NULL,4*PAGE,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);
        if(private==MAP_FAILED||shared==MAP_FAILED)_exit(31);
        for(size_t i=0;i<4;i++){private[i*PAGE]=0x61;shared[i*PAGE]=0x62;}
        int valid=stat_value(RECOVER,"private")>=4*PAGE&&stat_value(RECOVER,"anonymous_vmo")>=4*PAGE;
        munmap((void*)private,4*PAGE);munmap((void*)shared,4*PAGE);
        _exit(valid?0:32);
    }
    check("sibling_recovery_child_created",child>0); if(child>0)waitpid(child,&status,0);
    check("sibling_actual_private_and_shared_allocation_after_workload_denials",child>0&&WIFEXITED(status)&&WEXITSTATUS(status)==0);
    check("sibling_final_reference_refunds",await_total(RECOVER,0)==0);
    concurrent_frames();
    page_tables();
    close(denied_file);
    check("fixture_unmount",umount("/page-cache")==0);
    check("groups_removed",rmdir(WORK)==0&&rmdir(RECOVER)==0&&rmdir(BASE)==0);
    return failures?1:0;
}
