// SPDX-License-Identifier: Apache-2.0
#include <jni.h>
#include <cstdarg>
#include <cstdio>
#include "metadata_raw_cases.cc"

static char probe_result[65536];
static size_t result_used;
static bool result_overflow;
static void Append(const char* format,...) {
  if(result_overflow)return;
  va_list arguments;va_start(arguments,format);
  const int count=vsnprintf(probe_result+result_used,sizeof(probe_result)-result_used,format,arguments);
  va_end(arguments);
  if(count<0 || static_cast<size_t>(count)>=sizeof(probe_result)-result_used) {
    result_overflow=true;return;
  }
  result_used+=static_cast<size_t>(count);
}

static void AppendBytes(const void* address,size_t size) {
  const auto* bytes=static_cast<const unsigned char*>(address);
  Append("\"");
  for(size_t i=0;i<size;++i)Append("%02x",static_cast<unsigned>(bytes[i]));
  Append("\"");
}
static void AppendStatPair(const struct stat& native,const struct stat& raw) {
  Append("{");
#define PAIR_U(field) Append("\"" #field "\":[%llu,%llu],", \
  static_cast<unsigned long long>(native.field),static_cast<unsigned long long>(raw.field))
#define PAIR_S(field) Append("\"" #field "\":[%lld,%lld],", \
  static_cast<long long>(native.field),static_cast<long long>(raw.field))
  PAIR_U(st_dev);PAIR_U(st_ino);PAIR_U(st_nlink);PAIR_U(st_mode);PAIR_U(st_uid);
  PAIR_U(st_gid);PAIR_U(st_rdev);PAIR_S(st_size);PAIR_S(st_blksize);PAIR_S(st_blocks);
  PAIR_S(st_atim.tv_sec);PAIR_S(st_atim.tv_nsec);PAIR_S(st_mtim.tv_sec);
  PAIR_S(st_mtim.tv_nsec);PAIR_S(st_ctim.tv_sec);PAIR_S(st_ctim.tv_nsec);
#undef PAIR_U
#undef PAIR_S
  Append("\"native_bytes\":");AppendBytes(&native,sizeof(native));
  Append(",\"raw_bytes\":");AppendBytes(&raw,sizeof(raw));Append("}");
}
static void AppendFsPair(const struct statfs& native,const struct statfs& raw) {
  Append("{");
#define PAIR(field) Append("\"" #field "\":[%llu,%llu],", \
  static_cast<unsigned long long>(native.field),static_cast<unsigned long long>(raw.field))
  PAIR(f_type);PAIR(f_bsize);PAIR(f_blocks);PAIR(f_bfree);PAIR(f_bavail);
  PAIR(f_files);PAIR(f_ffree);PAIR(f_namelen);PAIR(f_frsize);PAIR(f_flags);
#undef PAIR
  Append("\"f_fsid_bytes\":[");AppendBytes(&native.f_fsid,sizeof(native.f_fsid));
  Append(",");AppendBytes(&raw.f_fsid,sizeof(raw.f_fsid));Append("],");
  Append("\"f_spare_bytes\":[");AppendBytes(&native.f_spare,sizeof(native.f_spare));
  Append(",");AppendBytes(&raw.f_spare,sizeof(raw.f_spare));Append("],");
  Append("\"native_bytes\":");AppendBytes(&native,sizeof(native));
  Append(",\"raw_bytes\":");AppendBytes(&raw,sizeof(raw));Append("}");
}
static void AppendDiagnostic(const MetadataDiagnostic& d) {
  Append(",\"diagnostic\":{\"captured\":%d,\"stage\":%d,\"raw_valid\":%d,"
         "\"tagged\":%d,\"same_stat\":%d,\"same_fs\":%d,"
         "\"native_fs_available\":%d,\"pair_order\":[\"native\",\"raw\"],\"stat\":",
         d.captured,d.stage,d.raw_valid,d.tagged,d.stat_equal,d.fs_equal,d.native_fs_available);
  AppendStatPair(d.native_stat,d.raw_stat);Append(",\"statfs\":");
  AppendFsPair(d.native_fs,d.raw_fs);Append("}");
}
static void AppendMetadataLayout() {
  Append("\"metadata_layout\":{\"stat_size\":%zu,\"stat_align\":%zu,"
         "\"statfs_size\":%zu,\"statfs_align\":%zu,\"snapshot_size\":%zu,"
         "\"stat_offsets\":{",sizeof(struct stat),alignof(struct stat),
         sizeof(struct statfs),alignof(struct statfs),sizeof(raw_owner::Snapshot));
#define STAT_OFFSET(field) Append("\"" #field "\":%zu,",offsetof(struct stat,field))
  STAT_OFFSET(st_dev);STAT_OFFSET(st_ino);STAT_OFFSET(st_nlink);STAT_OFFSET(st_mode);
  STAT_OFFSET(st_uid);STAT_OFFSET(st_gid);STAT_OFFSET(st_rdev);STAT_OFFSET(st_size);
  STAT_OFFSET(st_blksize);STAT_OFFSET(st_blocks);STAT_OFFSET(st_atim);
  STAT_OFFSET(st_mtim);
#undef STAT_OFFSET
  Append("\"st_ctim\":%zu},\"statfs_offsets\":{",offsetof(struct stat,st_ctim));
#define FS_OFFSET(field) Append("\"" #field "\":%zu,",offsetof(struct statfs,field))
  FS_OFFSET(f_type);FS_OFFSET(f_bsize);FS_OFFSET(f_blocks);FS_OFFSET(f_bfree);
  FS_OFFSET(f_bavail);FS_OFFSET(f_files);FS_OFFSET(f_ffree);FS_OFFSET(f_fsid);
  FS_OFFSET(f_namelen);FS_OFFSET(f_frsize);FS_OFFSET(f_flags);
#undef FS_OFFSET
  Append("\"f_spare\":%zu},\"field_sizes\":{\"f_type\":%zu,\"f_bsize\":%zu,"
         "\"f_blocks\":%zu,\"f_fsid\":%zu,\"f_namelen\":%zu,\"f_frsize\":%zu,"
         "\"f_flags\":%zu,\"f_spare\":%zu}},",offsetof(struct statfs,f_spare),
         sizeof(((struct statfs*)nullptr)->f_type),sizeof(((struct statfs*)nullptr)->f_bsize),
         sizeof(((struct statfs*)nullptr)->f_blocks),sizeof(((struct statfs*)nullptr)->f_fsid),
         sizeof(((struct statfs*)nullptr)->f_namelen),sizeof(((struct statfs*)nullptr)->f_frsize),
         sizeof(((struct statfs*)nullptr)->f_flags),sizeof(((struct statfs*)nullptr)->f_spare));
}

static int RunOwnedMetadata() {
  struct sigaction action{};
  if(sigaction(SIGCHLD,nullptr,&action)<0 || action.sa_handler!=SIG_DFL ||
     (action.sa_flags&SA_NOCLDWAIT)!=0)return 80;
  details=static_cast<MetadataDetails*>(mmap(nullptr,sizeof(MetadataDetails),PROT_READ|PROT_WRITE,
                                           MAP_SHARED|MAP_ANONYMOUS,-1,0));
  if(details==MAP_FAILED)return 81;
  constexpr unsigned expected=sizeof(kMetadataCases)/sizeof(kMetadataCases[0]);
  unsigned observed=0,started=0,reaped_count=0,nested_started=0,nested_reaped=0;
  uint64_t observed_mask=0;
  bool all=true,any_timeout=false,total_timeout=false;
  const int64_t began=Now();if(began<0)return 82;
  result_used=0;result_overflow=false;
  Append("{\"probe\":\"owned_real_metadata_r20_bionic_statfs_fix\",");
  AppendMetadataLayout();
  Append("\"cases\":[");
  for(const MetadataCase& test:kMetadataCases) {
    const int64_t now=Now();
    if(now<0 || now-began>=15000){all=false;total_timeout=true;break;}
    *details=MetadataDetails{};
    const pid_t parent=getpid(),child=fork();
    if(child<0){all=false;break;}
    if(child==0)_exit(Guard(parent) && test.function()?0:1);
    ++started;int status=0;bool timeout=false;
    const bool reaped=WaitOwned(child,3000,&status,&timeout);
    if(reaped)++reaped_count;
    const bool passed=reaped && !timeout && WIFEXITED(status) && WEXITSTATUS(status)==0;
    const MetadataDetails& d=*details;
    nested_started+=d.nested_started?1:0;
    nested_reaped+=d.nested_started&&d.child_reaped?1:0;
    if(passed)observed_mask|=UINT64_C(1)<<observed;
    Append("%s{\"case\":\"%s\",\"expected_behavior_observed\":%s,\"known_production_red\":%s,"
           "\"direct_child_reaped\":%s,\"timeout\":%s,\"signal\":%d,\"exit\":%d,\"setup\":%d,"
           "\"start\":%d,\"start_errno\":%d,\"read\":%d,\"read_errno\":%d,\"stop\":%d,"
           "\"native_stat\":%d,\"native_fs\":%d,\"projected_stat\":%d,\"projected_fs\":%d,"
           "\"lookup\":%d,\"errno_preserved\":%d,\"mask_preserved\":%d,\"ordinary_tag_rejected\":%d,"
           "\"caller_uid\":%d,\"worker_uid\":%d,\"worker_tid\":%d,\"worker_tid_cleared\":%d,"
           "\"same_namespace\":%d,\"inherited_stack\":%d,\"child_finished\":%d,"
           "\"nested_child_started\":%d,\"nested_child_reaped\":%d,\"nested_timeout\":%d,"
           "\"nested_status\":%d,\"parent_read\":%d,\"parent_stop\":%d,\"parent_fd_survived\":%d,"
           "\"rounds\":%d,\"quiesce\":%d,\"restart\":%d,\"restart_errno\":%d,"
           "\"thread_error\":%d,\"thread_fdtable_checked\":%d,\"shared_vm_rejected\":%d",
           observed?",":"",test.name,passed?"true":"false",test.known_red?"true":"false",
           reaped?"true":"false",timeout?"true":"false",
           reaped&&WIFSIGNALED(status)?WTERMSIG(status):0,
           reaped&&WIFEXITED(status)?WEXITSTATUS(status):-1,d.setup,d.start,d.start_error,
           d.read,d.read_error,d.stop,d.native_stat,d.native_fs,d.projected_stat,d.projected_fs,
           d.lookup,d.errno_preserved,d.mask_preserved,d.ordinary_tag_rejected,
           d.caller_uid,d.worker_uid,d.worker_tid,d.worker_tid_cleared,d.same_namespace,
           d.inherited_stack,d.child_finished,d.nested_started,d.child_reaped,d.child_timeout,
           d.child_status,d.parent_read,d.parent_stop,d.parent_fd_survived,d.rounds,d.quiesce,
           d.restart,d.restart_error,d.thread_error,d.thread_fdtable_checked,d.shared_vm_rejected);
    AppendDiagnostic(d.diagnostic);Append("}");
    ++observed;all=all&&passed;any_timeout=any_timeout||timeout||d.child_timeout;
    if(timeout || !reaped)break;
  }
  const bool passed=all && observed==expected && observed_mask==((UINT64_C(1)<<expected)-1);
  const bool children_reaped=started==reaped_count && nested_started==nested_reaped && !any_timeout;
  Append("],\"pass\":%s,\"child_reaped\":%s,\"direct_children_started\":%u,"
         "\"direct_children_reaped\":%u,\"nested_children_started\":%u,\"nested_children_reaped\":%u,"
         "\"expected_cases\":%u,\"observed_cases\":%u,\"expected_behavior_mask\":\"0x%016llx\","
         "\"timeout\":%s,\"application_uid\":%u,",
         passed?"true":"false",children_reaped?"true":"false",started,reaped_count,
         nested_started,nested_reaped,expected,observed,static_cast<unsigned long long>(observed_mask),
         (any_timeout||total_timeout)?"true":"false",static_cast<unsigned>(getuid()));
  Append("\"scope\":\"real metadata wrappers with explicit qualified raw owner\","
         "\"worker_arbitrary_callback\":false,\"identity_seam\":false,\"host_copy_seam\":false,"
         "\"fault_injections\":[],\"source_default_raw_feature_enabled\":false,"
         "\"owned_probe_raw_feature_enabled\":true,\"runtime_hooks_installed\":false,"
         "\"candidate_production_ready\":false,\"broker_positive_identity_tested\":false,"
         "\"positive_root_owned_O_PATH_reopen_tested\":false,"
         "\"application_owned_Fstat_QueryOrigin_use_native_negative_filter\":true,"
         "\"credential_namespace_transition_guarantee\":false,"
         "\"known_reds\":[\"NOFILE0 remains EMFILE\",\"task-count and kernel resources remain\","
         "\"ART app-generation and retirement hooks absent\","
         "\"host-native credential root mount transitions not gated\","
         "\"positive trusted factory tag and O_PATH reopen not exercised\","
         "\"pathname owner resource and alias-admission race unresolved\"]}");
  munmap(details,sizeof(MetadataDetails));details=nullptr;
  if(result_overflow)return 83;
  return passed?0:1;
}
extern "C" JNIEXPORT jstring JNICALL
Java_local_pocket4_fdownerprobe_ProbeInstrumentation_runProbe(JNIEnv* env,jclass) {
  probe_result[0]=0;const int result=RunOwnedMetadata();
  if(result_overflow || probe_result[0]==0)
    snprintf(probe_result,sizeof(probe_result),"{\"probe\":\"owned_real_metadata_r20_bionic_statfs_fix\",\"pass\":false,\"early_rc\":%d}",result);
  return env->NewStringUTF(probe_result);
}
