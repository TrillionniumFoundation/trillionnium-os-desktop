#define _GNU_SOURCE
#include <sepol/policydb/services.h>
#include <stdint.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* Only libsepol in-memory policy operations; no kernel policy API. */
#define H "u:r:droidloom_host:s0"
#define B "u:r:droidloom_broker:s0"
#define I "u:r:init:s0"
#define A "u:r:apexd:s0"
#define L "u:r:linkerconfig:s0"
#define Q "u:r:droidloom_query:s0"
#define K "u:r:kernel:s0"
#define HF "u:object_r:droidloom_host_file:s0"
#define IE "u:object_r:init_exec:s0"
#define AE "u:object_r:apexd_exec:s0"
#define LE "u:object_r:linkerconfig_exec:s0"
#define SF "u:object_r:droidloom_linkerconfig_socket:s0"
#define SM "u:r:servicemanager:s0"
#define SS "u:r:system_server:s0"
#define QE "u:object_r:droidloom_query_exec:s0"
#define MF "u:object_r:droidloom_manager_private_socket:s0"
#define TF "u:object_r:tmpfs:s0"
#define ND "u:object_r:null_device:s0"
struct av {const char *s,*t,*c,*p;int allow;};
static const struct av avs[]={
 {H,H,"dir","getattr search read open",1},
 {H,H,"file","getattr read write open",1},
 {H,H,"lnk_file","getattr read",1},
 {B,B,"file","getattr read write open",1},
 {H,K,"security","read_policy compute_av compute_create",1},
 {B,K,"security","read_policy compute_av compute_create",1},
 {H,K,"security","load_policy setenforce setbool setsecparam setcheckreqprot",0},
 {H,B,"process","getattr signull signal sigkill sigstop",1},
 {H,I,"process","getattr signull signal sigkill sigstop",1},
 {H,A,"process","getattr signull signal sigkill sigstop",1},
 {H,L,"process","getattr signull signal sigkill sigstop",1},
 {H,Q,"process","getattr signull signal sigkill sigstop",1},
 {B,"u:object_r:selinuxfs:s0","file","getattr read write open",1},
 {B,"u:object_r:securityfs:s0","file","getattr read open",1},
 {B,"u:object_r:securityfs:s0","file","write append create",0},
 {B,"u:object_r:droidloom_broker_private_file:s0","file","getattr read open map",1},
 {B,"u:object_r:droidloom_broker_private_file:s0","file","write append create relabelfrom relabelto",0},
 {B,I,"process","transition",1},{B,I,"process2","nnp_transition nosuid_transition",1},
 {B,IE,"file","getattr read open map execute",1},{I,IE,"file","entrypoint",1},
 {I,A,"process","transition",1},{I,A,"process2","nnp_transition nosuid_transition",1},
 {I,L,"process","transition",1},{I,L,"process2","nnp_transition nosuid_transition",1},
 {B,A,"process","transition",1},{B,A,"process2","nnp_transition nosuid_transition",1},
 {L,LE,"file","getattr read open map execute execute_no_trans",1},
 {B,B,"unix_stream_socket","create bind listen accept getattr read write getopt setopt shutdown",1},
 {B,SF,"sock_file","create getattr setattr write",1},{L,B,"unix_stream_socket","connectto",1},
 {L,SF,"sock_file","write",1},{L,B,"fd","use",1},
 {H,B,"unix_stream_socket","connectto",0},{H,SF,"sock_file","write",0},
 {H,I,"process","transition dyntransition",0},
 {I,H,"process","transition dyntransition ptrace sigkill signal",0},
 {I,B,"process","transition dyntransition ptrace sigkill signal",0},
 {A,H,"process","transition dyntransition ptrace sigkill signal",0},
 {L,H,"process","transition dyntransition ptrace sigkill signal",0},
 {I,HF,"file","read write append map execute open relabelfrom relabelto",0},
 {I,HF,"dir","read write search add_name remove_name relabelfrom relabelto",0},
 {Q,HF,"file","read write append map execute open relabelfrom relabelto",0},
 {I,K,"security","load_policy setenforce setbool setsecparam setcheckreqprot",0},
 {B,K,"security","load_policy setenforce setbool setsecparam setcheckreqprot",0},
 {Q,K,"security","load_policy setenforce setbool setsecparam setcheckreqprot",0},
 /* r5 source evidence: proc_self_host_actual_avc */
 {H,"u:object_r:proc:s0","lnk_file","read",1},
 /* r5 source evidence: proc_self_broker_owned_aliases */
 {B,"u:object_r:proc:s0","lnk_file","read",1},
 /* r5 source evidence: selinux_status_readonly_mapping */
 {B,"u:object_r:selinuxfs:s0","file","map",1},
 /* r5 source evidence: fixed_boot_id_readback */
 {B,"u:object_r:proc_random:s0","dir","getattr search read open",1},
 /* r5 source evidence: fixed_boot_id_readback */
 {B,"u:object_r:proc_random:s0","file","getattr read open",1},
 /* r5 source evidence: fixed_private_manager_connection */
 {B,B,"unix_stream_socket","connect",1},
 /* r5 source evidence: fixed_private_manager_connection */
 {B,H,"unix_stream_socket","connectto",1},
 /* r5 source evidence: manager_receives_original_broker_pidfd */
 {H,B,"fd","use",1},
 /* r5 source evidence: held_original_manager_identity */
 {B,H,"process","getattr",1},
 /* r5 source evidence: held_original_manager_identity */
 {B,H,"dir","getattr search read open",1},
 /* r5 source evidence: held_original_manager_identity */
 {B,H,"file","getattr read open",1},
 /* r5 source evidence: held_original_manager_identity */
 {B,H,"lnk_file","getattr read",1},
 /* r5 source evidence: manager_server_inode_label_is_separate_from_client */
 {B,MF,"sock_file","getattr write",1},
 /* r5 source evidence: two_original_query_inputs_are_read_only */
 {B,"u:object_r:system_file:s0","file","getattr read open",1},
 /* r5 source evidence: two_original_query_inputs_are_read_only */
 {B,"u:object_r:toolbox_exec:s0","file","getattr read open",1},
 /* r5 source evidence: new_query_tmpfs_sealed_superblock */
 {B,TF,"filesystem","mount remount getattr",1},
 /* r5 source evidence: new_query_tmpfs_root_and_two_files */
 {B,TF,"dir","getattr search read open write add_name relabelfrom",1},
 /* r5 source evidence: new_query_tmpfs_root_and_two_files */
 {B,TF,"file","create getattr read write open relabelfrom",1},
 /* r5 source evidence: new_query_inodes_relabel_then_chmod_only */
 {B,QE,"dir","relabelto getattr search read open setattr",1},
 /* r5 source evidence: new_query_inodes_relabel_then_chmod_only */
 {B,QE,"file","relabelto getattr read open map setattr execute",1},
 /* r5 source evidence: new_query_inodes_relabel_then_chmod_only */
 {QE,TF,"filesystem","associate",1},
 /* r5 source evidence: query_dedicated_entrypoint */
 {Q,QE,"dir","getattr search",1},
 /* r5 source evidence: query_dedicated_entrypoint */
 {Q,QE,"file","getattr read open map execute entrypoint",1},
 /* r5 source evidence: query_arms_fixed_explicit_exec_context */
 {B,B,"process","setexec",1},
 /* r5 source evidence: query_drops_all_capabilities_before_exec */
 {B,B,"process","setcap",1},
 /* r5 source evidence: query_arms_fixed_explicit_exec_context */
 {B,Q,"process","transition",1},
 /* r5 source evidence: query_arms_fixed_explicit_exec_context */
 {B,Q,"process2","nnp_transition nosuid_transition",1},
 /* r5 source evidence: original_wait_owner_seizes_parked_broker_child */
 {B,B,"process","ptrace",1},
 /* r5 source evidence: original_wait_owner_observes_query_exec_stop */
 {B,Q,"process","ptrace",1},
 /* r5 source evidence: fixed_query_owned_worker_creation_and_failure_retirement */
 {B,B,"process","fork sigkill",1},
 /* r5 source evidence: fixed_query_owned_worker_creation_and_failure_retirement */
 {B,Q,"process","sigkill",1},
 /* r5 source evidence: query_binder_threads_keep_syscall_process_fork_denied */
 {Q,Q,"process","fork",1},
 /* r5 source evidence: fixed_package_query_binder_driver */
 {Q,"u:object_r:binder_device:s0","chr_file","open read write getattr ioctl map",1},
 /* r5 source evidence: fixed_package_check_service */
 {Q,SM,"binder","call",1},
 /* r5 source evidence: fixed_package_handle_reply */
 {SM,Q,"binder","transfer",1},
 /* r5 source evidence: fixed_package_check_service */
 {Q,"u:object_r:package_service:s0","service_manager","find",1},
 /* r5 source evidence: fixed_package_shell_command_and_callbacks */
 {Q,SS,"binder","call transfer",1},
 /* r5 source evidence: fixed_package_result_receiver_callback */
 {SS,Q,"binder","call",1},
 /* r5 source evidence: query_uses_broker_created_stdio */
 {Q,B,"fd","use",1},
 /* r5 source evidence: package_server_receives_broker_created_stdio */
 {SS,B,"fd","use",1},
 /* r5 source evidence: query_uses_broker_created_stdio */
 {Q,B,"fifo_file","write getattr",1},
 /* r5 source evidence: package_server_receives_broker_created_stdio */
 {SS,B,"fifo_file","write getattr",1},
 /* r5 source evidence: query_stdin_is_owned_guest_null */
 {B,ND,"chr_file","getattr read open",1},
 /* r5 source evidence: query_stdin_is_owned_guest_null */
 {Q,ND,"chr_file","read",1},
 /* Original platform already allows server guest-null read; no duplicate allow. */
 {SS,ND,"chr_file","read",1},
 /* r5 boundary: no unproved expansion. */
 {H,"u:object_r:proc:s0","lnk_file","getattr",0},
 /* r5 boundary: no unproved expansion. */
 {B,"u:object_r:proc:s0","lnk_file","getattr",0},
 /* r5 boundary: no unproved expansion. */
 {B,"u:object_r:proc_random:s0","file","write append",0},
 /* r5 boundary: no unproved expansion. */
 {B,MF,"sock_file","create unlink relabelfrom relabelto",0},
 /* r5 boundary: no unproved expansion. */
 {H,MF,"sock_file","create write",0},
 /* r5 boundary: no unproved expansion. */
 {Q,MF,"sock_file","write",0},
 /* r5 boundary: no unproved expansion. */
 {I,MF,"sock_file","write",0},
 /* r5 boundary: no unproved expansion. */
 {A,MF,"sock_file","write",0},
 /* r5 boundary: no unproved expansion. */
 {L,MF,"sock_file","write",0},
 /* r5 boundary: no unproved expansion. */
 {Q,H,"unix_stream_socket","connectto",0},
 /* r5 boundary: no unproved expansion. */
 {B,H,"process","ptrace signal sigkill",0},
 /* r5 boundary: no unproved expansion. */
 {B,"u:object_r:system_file:s0","file","write execute entrypoint relabelfrom relabelto",0},
 /* r5 boundary: no unproved expansion. */
 {B,"u:object_r:toolbox_exec:s0","file","write execute entrypoint relabelfrom relabelto",0},
 /* r5 boundary: no unproved expansion. */
 {B,TF,"file","relabelto",0},
 /* r5 boundary: no unproved expansion. */
 {B,QE,"file","write append create entrypoint execute_no_trans",0},
 /* r5 boundary: no unproved expansion. */
 {B,QE,"dir","write add_name remove_name create relabelfrom",0},
 /* r5 boundary: no unproved expansion. */
 {Q,QE,"file","write append create relabelfrom relabelto execute_no_trans",0},
 /* r5 boundary: no unproved expansion. */
 {Q,QE,"dir","write add_name remove_name create relabelfrom relabelto",0},
 /* r5 boundary: no unproved expansion. */
 {Q,"u:object_r:system_file:s0","file","entrypoint",0},
 /* r5 boundary: no unproved expansion. */
 {Q,"u:object_r:toolbox_exec:s0","file","entrypoint",0},
 /* r5 boundary: no unproved expansion. */
 {Q,TF,"filesystem","mount remount",0},
 /* r5 boundary: no unproved expansion. */
 {Q,B,"process","ptrace transition dyntransition signal sigkill",0},
 /* r5 boundary: no unproved expansion. */
 {B,B,"process","setfscreate setsockcreate setcurrent dyntransition",0},
 /* r5 boundary: no unproved expansion. */
 {Q,Q,"process","setexec setfscreate setsockcreate setcurrent dyntransition",0},
 /* r5 boundary: no unproved expansion. */
 {Q,SM,"binder","transfer impersonate set_context_mgr",0},
 /* r5 boundary: no unproved expansion. */
 {SM,Q,"binder","call",0},
 /* r5 boundary: no unproved expansion. */
 {SS,Q,"binder","transfer",0},
 /* r5 boundary: no unproved expansion. */
 {Q,"u:object_r:package_service:s0","service_manager","add list",0},
 /* r5 boundary: no unproved expansion. */
 {Q,SM,"service_manager","list",0},
 /* r5 boundary: no unproved expansion. */
 {Q,"u:object_r:activity_service:s0","service_manager","find",0},
 /* r5 boundary: no unproved expansion. */
 {Q,"u:object_r:netd_service:s0","service_manager","find",0},
 /* r5 boundary: no unproved expansion. */
 {Q,"u:object_r:default_prop:s0","property_service","set",0},
 /* r5 boundary: no unproved expansion. */
 {Q,"u:object_r:hwbinder_device:s0","chr_file","open read write ioctl map",0},
 /* r5 boundary: no unproved expansion. */
 {Q,"u:object_r:vndbinder_device:s0","chr_file","open read write ioctl map",0},
 /* r5 boundary: no unproved expansion. */
 {Q,Q,"tcp_socket","create connect",0},
 /* r5 boundary: no unproved expansion. */
 {Q,Q,"udp_socket","create connect",0},
 /* r5 boundary: no unproved expansion. */
 {Q,Q,"rawip_socket","create",0},
 /* r5 boundary: no unproved expansion. */
 {Q,Q,"packet_socket","create",0},
 /* r6: observed host statfs of the original labeledfs root; no mount authority. */
 {H,"u:object_r:labeledfs:s0","filesystem","getattr",1},
 {H,"u:object_r:labeledfs:s0","filesystem","mount remount unmount relabelfrom relabelto associate quotamod quotaget watch",0},
 {B,"u:object_r:labeledfs:s0","filesystem","getattr",0},
 /* r8: existing selinuxfs discovery by the original libselinux constructor. */
 {H,"u:object_r:selinuxfs:s0","filesystem","getattr",1},
 /* r8: fstatfs of the held original systemd server inode on /run tmpfs. */
 {H,TF,"filesystem","getattr",1},
 /* Read-only observations do not grant filesystem administration. */
 {H,"u:object_r:selinuxfs:s0","filesystem","mount remount unmount relabelfrom relabelto associate quotamod quotaget watch",0},
 {H,TF,"filesystem","mount remount unmount relabelfrom relabelto associate quotamod quotaget watch",0},
 {H,H,"capability","sys_admin",0},
 /* r9: S01_original_cg_has_legacy_statfs */
 {"u:r:droidloom_host:s0","u:object_r:cgroup_v2:s0","filesystem","getattr",1},
 /* r9: S02_existing_observer_held_proc_fstatfs */
 {"u:r:droidloom_host:s0","u:object_r:proc:s0","filesystem","getattr",1},
 /* r9: S03_original_cg_create_attach_and_trim */
 {"u:r:droidloom_host:s0","u:object_r:cgroup_v2:s0","dir","create write add_name remove_name rmdir",1},
 /* r9: S04_original_cgroup_procs_and_inode_watch */
 {"u:r:droidloom_host:s0","u:object_r:cgroup_v2:s0","file","write watch",1},
 /* r9: S05_original_private_bus_and_same_host_observer */
 {"u:r:droidloom_host:s0","u:r:droidloom_host:s0","unix_stream_socket","create bind listen accept connect connectto getattr read write getopt setopt",1},
 /* r9: S06_original_notify_and_inherited_socketpairs */
 {"u:r:droidloom_host:s0","u:r:droidloom_host:s0","unix_dgram_socket","create bind read write getopt setopt sendto",1},
 /* r9: S07_original_label_aware_creation_and_clear */
 {"u:r:droidloom_host:s0","u:r:droidloom_host:s0","process","setfscreate",1},
 /* r9: S08_original_fixed_run_directories_and_atomic_entries */
 {"u:r:droidloom_host:s0","u:object_r:tmpfs:s0","dir","create write add_name remove_name",1},
 /* r9: S09_original_private_and_notify_path_inodes */
 {"u:r:droidloom_host:s0","u:object_r:tmpfs:s0","sock_file","create getattr setattr write unlink",1},
 /* r9: S10_original_fixed_unit_invocation_link */
 {"u:r:droidloom_host:s0","u:object_r:tmpfs:s0","lnk_file","create rename unlink",1},
 /* r9: S11_original_fixed_bookkeeping_and_serialization */
 {"u:r:droidloom_host:s0","u:object_r:tmpfs:s0","file","create write setattr",1},
 /* r9: N01_no_filesystem_administration */
 {"u:r:droidloom_host:s0","u:object_r:cgroup_v2:s0","filesystem","mount remount unmount relabelfrom relabelto associate quotamod quotaget watch",0},
 /* r9: N01_no_filesystem_administration */
 {"u:r:droidloom_host:s0","u:object_r:proc:s0","filesystem","mount remount unmount relabelfrom relabelto associate quotamod quotaget watch",0},
 /* r9: N02_cgroup_directory_scope */
 {"u:r:droidloom_host:s0","u:object_r:cgroup_v2:s0","dir","setattr relabelfrom relabelto rename reparent",0},
 /* r9: N03_existing_controls_only */
 {"u:r:droidloom_host:s0","u:object_r:cgroup_v2:s0","file","create append setattr unlink rename relabelfrom relabelto execute",0},
 /* r9: N04_no_Android_cgroup_mutation */
 {"u:r:droidloom_host:s0","u:object_r:cgroup_app:s0","dir","create write add_name remove_name rmdir",0},
 /* r9: N04_no_Android_cgroup_mutation */
 {"u:r:droidloom_host:s0","u:object_r:cgroup_app:s0","file","write watch",0},
 /* r9: N05_other_context_actions_denied */
 {"u:r:droidloom_host:s0","u:r:droidloom_host:s0","process","setexec setcurrent setsockcreate setkeycreate dyntransition",0},
 /* r9: N06_no_directory_relabel_or_admin */
 {"u:r:droidloom_host:s0","u:object_r:tmpfs:s0","dir","setattr rmdir rename reparent relabelfrom relabelto",0},
 /* r9: N07_no_unproved_regular_file_authority */
 {"u:r:droidloom_host:s0","u:object_r:tmpfs:s0","file","append unlink rename execute entrypoint relabelfrom relabelto",0},
 /* r9: N08_socket_inode_scope */
 {"u:r:droidloom_host:s0","u:object_r:tmpfs:s0","sock_file","read rename relabelfrom relabelto",0},
 /* r9: N09_invocation_link_scope */
 {"u:r:droidloom_host:s0","u:object_r:tmpfs:s0","lnk_file","getattr read write setattr relabelfrom relabelto",0},
 /* r9: N10_original_inputs_not_relabelled */
 {"u:r:droidloom_host:s0","u:object_r:droidloom_host_file:s0","file","relabelfrom relabelto entrypoint",0},
 /* r9: N11_no_Android_entrypoint_creation */
 {"u:r:droidloom_host:s0","u:object_r:init_exec:s0","file","create write entrypoint relabelfrom relabelto",0},
 /* r9: N12_no_unlabeled_fallback */
 {"u:r:droidloom_host:s0","u:object_r:unlabeled:s0","file","create write execute ioctl",0},
 /* r9: N13_unproved_socket_operations */
 {"u:r:droidloom_host:s0","u:r:droidloom_host:s0","unix_stream_socket","shutdown",0},
 /* r9: N13_unproved_socket_operations */
 {"u:r:droidloom_host:s0","u:r:droidloom_host:s0","unix_dgram_socket","getattr connect listen accept shutdown",0},
 /* r9: N14_no_network_authority */
 {"u:r:droidloom_host:s0","u:r:droidloom_host:s0","tcp_socket","create",0},
 /* r9: N14_no_network_authority */
 {"u:r:droidloom_host:s0","u:r:droidloom_host:s0","udp_socket","create",0},
 /* r9: N14_no_network_authority */
 {"u:r:droidloom_host:s0","u:r:droidloom_host:s0","rawip_socket","create",0},
 /* r9: N14_no_network_authority */
 {"u:r:droidloom_host:s0","u:r:droidloom_host:s0","packet_socket","create",0},
 /* r9: N14_no_network_authority */
 {"u:r:droidloom_host:s0","u:r:droidloom_host:s0","netlink_route_socket","create",0},
 /* r9: P01_original_self_association */
 {"u:object_r:tmpfs:s0","u:object_r:tmpfs:s0","filesystem","associate",1},
 /* r9: P01_original_self_association */
 {"u:object_r:cgroup_v2:s0","u:object_r:cgroup_v2:s0","filesystem","associate",1},
 /* r10: one necessary manager capability; all R9 object restrictions remain. */
 {H,H,"capability","dac_override",1},
 {B,B,"capability","dac_override",0},
 {"u:r:droidloom_policy_loader:s0","u:r:droidloom_policy_loader:s0","capability","dac_override",0},
 {Q,Q,"capability","dac_override",0},
 {H,H,"capability","dac_read_search fowner chown setpcap",0}};
struct tr {const char *s,*e,*expected;};
static const struct tr trs[]={{B,IE,I},{H,IE,H},{B,HF,B},{B,AE,A},{I,AE,A},{I,LE,L},{L,LE,L},
 /* Query source writes a fixed exec SID. There is no added automatic transition. */
 {B,QE,B},{H,QE,H}};
struct cr {const char *s,*parent,*c,*expected;};
static const struct cr creates[]={{B,TF,"dir",TF},{B,TF,"file",TF}};
static void need(int ok,const char *why){if(!ok){fprintf(stderr,"offline query: %s errno=%d\n",why,errno);exit(2);}}
static sepol_security_id_t sid(const char *c){sepol_security_id_t v=0;need(sepol_context_to_sid(c,strlen(c)+1,&v)==0&&v!=0,c);return v;}
/* Separate from the two unchanged live query creation controls. */
static size_t systemd_creation_checks(void){
 static const struct cr host_creates[]={
  {H,TF,"dir",TF},{H,TF,"file",TF},{H,TF,"sock_file",TF},{H,TF,"lnk_file",TF},
  {H,"u:object_r:cgroup_v2:s0","dir","u:object_r:cgroup_v2:s0"}};
 size_t failed=0;printf("\"systemd_creation_labels\":[");
 for(size_t i=0;i<sizeof(host_creates)/sizeof(*host_creates);i++){
  const struct cr *v=&host_creates[i];sepol_security_class_t c=0;sepol_security_id_t out=0;
  sepol_security_context_t actual=NULL;size_t bytes=0;
  need(sepol_string_to_security_class(v->c,&c)==0&&c!=0,v->c);
  need(sepol_transition_sid(sid(v->s),sid(v->parent),c,&out)==0,"original host initial inode label");
  need(sepol_sid_to_context(out,&actual,&bytes)==0&&actual&&bytes,"whole actual host inode context");
  int ok=strcmp(actual,v->expected)==0;if(!ok)failed++;
  printf("%s{\"source\":\"%s\",\"parent\":\"%s\",\"class\":\"%s\",\"expected\":\"%s\",\"actual\":\"%s\",\"passed\":%s}",i?",":"",v->s,v->parent,v->c,v->expected,actual,ok?"true":"false");
  free(actual);
 }
 printf("],");return failed;
}
#define NL "u:r:droidloom_policy_loader:s0"
#define NF "u:object_r:droidloom_nsfs:s0"
#define UL "u:object_r:unlabeled:s0"
static const struct av ns_avs[]={
 {H,NF,"file","getattr read open ioctl",1},
 {B,NF,"file","getattr read open ioctl",1},
 {NL,NF,"file","getattr read open ioctl",1},
 {H,NF,"file","write append create setattr map execute entrypoint relabelfrom relabelto",0},
 {B,NF,"file","write append create setattr map execute entrypoint relabelfrom relabelto",0},
 {NL,NF,"file","write append create setattr map execute entrypoint relabelfrom relabelto",0},
 {H,UL,"file","ioctl",0},{B,UL,"file","ioctl",0},{NL,UL,"file","ioctl",0},
 {H,NF,"filesystem","getattr mount remount unmount relabelfrom relabelto associate",0},
 {B,NF,"filesystem","getattr mount remount unmount relabelfrom relabelto associate",0},
 {NL,NF,"filesystem","getattr mount remount unmount relabelfrom relabelto associate",0},
 {Q,NF,"file","getattr read open ioctl",0},{I,NF,"file","getattr read open ioctl",0}
};

/* The pinned libsepol has no public extended-permission decision routine.
 * Decode its actual loaded policydb without rewriting it. Include all matching
 * type attributes, rather than trusting a source-level/direct-key lookup.
 * Matching conditional grants are rejected: this fixed contract has none.
 */
static int type_matches(const policydb_t *p,uint16_t concrete,uint16_t key){
 need(concrete&&concrete<=p->p_types.nprim&&key&&key<=p->p_types.nprim,"bounded binary type identifier");
 return concrete==key||ebitmap_get_bit(&p->type_attr_map[concrete-1],key-1);
}
static unsigned bitmap_bit(const uint32_t bits[8],unsigned bit){
 return (bits[bit>>5]>>(bit&31))&1U;
}
static unsigned decode_ioctl_bitmap(const policydb_t *p,const avtab_t *table,
 uint16_t source,uint16_t target,uint16_t cls,unsigned char allowed[65536],int conditional){
 unsigned entries=0;
 for(uint32_t i=0;i<table->nslot;i++)for(const struct avtab_node *n=table->htable[i];n;n=n->next){
  if(n->key.target_class!=cls||!(n->key.specified&AVTAB_XPERMS_ALLOWED)||
     !type_matches(p,source,n->key.source_type)||!type_matches(p,target,n->key.target_type))continue;
  entries++;
  if(conditional)continue;
  const avtab_extended_perms_t *x=n->datum.xperms;need(x!=NULL,"actual ioctl bitmap required");
  if(x->specified==AVTAB_XPERMS_IOCTLFUNCTION){
   for(unsigned b=0;b<256;b++)if(bitmap_bit(x->perms,b))allowed[(unsigned)x->driver*256+b]=1;
  }else if(x->specified==AVTAB_XPERMS_IOCTLDRIVER){
   for(unsigned d=0;d<256;d++)if(bitmap_bit(x->perms,d))memset(allowed+d*256,1,256);
  }else need(0,"unsupported extended permission kind for namespace file");
 }
 return entries;
}
static size_t namespace_checks(const policydb_t *p){
 size_t failed=0;
 type_datum_t *ns=hashtab_search(p->p_types.table,"droidloom_nsfs");
 /* R6 is an intentional negative baseline: retain all 143 old decisions,
  * then report the exact missing fixed type, with no unknown-SID fallback. */
 if(!ns){
  printf("\"namespace\":{\"fixed_type_present\":false,\"checks_attempted\":1,\"failure\":\"required_droidloom_nsfs_type_absent\",\"passed\":false}");
  return 1;
 }
 need(ns->flavor!=TYPE_ATTRIB&&ns->s.value>0&&ns->s.value<=UINT16_MAX,"concrete fixed namespace type");
 printf("\"namespace\":{\"fixed_type_present\":true,\"access\":[");
 for(size_t i=0;i<sizeof(ns_avs)/sizeof(*ns_avs);i++){
  const struct av *a=&ns_avs[i];sepol_security_class_t c=0;sepol_access_vector_t mask=0;struct sepol_av_decision d={0};unsigned reason=0;
  need(sepol_string_to_security_class(a->c,&c)==0&&c!=0,a->c);char *names=strdup(a->p),*save=NULL;need(names!=NULL,"namespace permission buffer");
  for(char *name=strtok_r(names," ",&save);name;name=strtok_r(NULL," ",&save)){sepol_access_vector_t bit=0;need(sepol_string_to_av_perm(c,name,&bit)==0&&bit!=0,name);mask|=bit;}free(names);
  need(sepol_compute_av_reason(sid(a->s),sid(a->t),c,mask,&d,&reason)==0,"actual namespace access decision");
  int ok=a->allow?(d.allowed&mask)==mask:(d.allowed&mask)==0;if(!ok)failed++;
  printf("%s{\"source\":\"%s\",\"target\":\"%s\",\"class\":\"%s\",\"permissions\":\"%s\",\"expected_allow\":%s,\"requested\":%u,\"actual_allowed\":%u,\"denial_reason\":%u,\"passed\":%s}",i?",":"",a->s,a->t,a->c,a->p,a->allow?"true":"false",mask,d.allowed,reason,ok?"true":"false");
 }
 printf("],\"filesystem_labels\":[");
 for(unsigned i=0;i<2;i++){
  sepol_security_id_t out=0;unsigned behavior=0;sepol_security_class_t fc=0;
  int rc=i?sepol_string_to_security_class("file",&fc):0;
  need(rc==0,"namespace file class");
  rc=i?sepol_genfs_sid("nsfs","/",fc,&out):sepol_fs_use("nsfs",&behavior,&out);
  need(rc==0,"actual nsfs fixed label lookup");
  sepol_security_context_t context=NULL;size_t length=0;
  need(sepol_sid_to_context(out,&context,&length)==0&&context&&length,"actual nsfs label context");
  int ok=strcmp(context,NF)==0&&(i||behavior==SECURITY_FS_USE_GENFS);if(!ok)failed++;
  printf("%s{\"operation\":\"%s\",\"filesystem\":\"nsfs\",\"path\":\"/\",\"actual_behavior\":%u,\"actual_context\":\"%s\",\"expected_context\":\"%s\",\"passed\":%s}",i?",":"",i?"genfs_file_sid":"filesystem_label_behavior",behavior,context,NF,ok?"true":"false");free(context);
 }
 printf("],\"ioctl_bitmaps\":[");
 const char *sources[]={"droidloom_host","droidloom_broker","droidloom_policy_loader"};
 sepol_security_class_t fileclass=0;need(sepol_string_to_security_class("file",&fileclass)==0&&fileclass,"actual namespace file class");
 for(unsigned i=0;i<3;i++){
  type_datum_t *s=hashtab_search(p->p_types.table,sources[i]);need(s&&s->flavor!=TYPE_ATTRIB&&s->s.value<=UINT16_MAX,"fixed namespace observer type");
  unsigned char allowed[65536]={0};
  unsigned entries=decode_ioctl_bitmap(p,&p->te_avtab,s->s.value,ns->s.value,fileclass,allowed,0);
  unsigned conditional=decode_ioctl_bitmap(p,&p->te_cond_avtab,s->s.value,ns->s.value,fileclass,allowed,1);
  unsigned count=0,mismatch=0;
  for(unsigned command=0;command<65536;command++){count+=allowed[command];mismatch+=allowed[command]!=(command==0xb703||command==0xb70d);}
  int ok=entries>0&&conditional==0&&count==2&&mismatch==0;if(!ok)failed++;
  printf("%s{\"source_type\":\"%s\",\"target_type\":\"droidloom_nsfs\",\"examined_low16_commands\":65536,\"matching_unconditional_entries\":%u,\"matching_conditional_entries\":%u,\"actual_allowed_count\":%u,\"mismatches\":%u,\"expected_allowed\":[46851,46861],\"passed\":%s}",i?",":"",sources[i],entries,conditional,count,mismatch,ok?"true":"false");
 }
 printf("],\"checks_attempted\":19,\"failed\":%zu,\"passed\":%s}",failed,failed?"false":"true");
 return failed;
}

/* New finite browser role; all original R10 arrays and decisions are retained. */
#define BA "u:r:droidloom_browser_action:s0"
#define BE "u:object_r:droidloom_browser_action_exec:s0"
static size_t browser_checks(const policydb_t *p){
 size_t failed=0;
 type_datum_t *domain=hashtab_search(p->p_types.table,"droidloom_browser_action");
 type_datum_t *executable=hashtab_search(p->p_types.table,"droidloom_browser_action_exec");
 if(!domain||!executable){
  printf("\"browser_action\":{\"fixed_types_present\":false,\"checks_attempted\":1,\"failure\":\"required_browser_action_role_absent\",\"passed\":false}");
  return 1;
 }
 need(domain->flavor!=TYPE_ATTRIB&&executable->flavor!=TYPE_ATTRIB,"concrete browser input roles");
 static const struct av browser_avs[]={
 {H,BA,"process","getattr signull signal sigkill sigstop",1},
 {B,BA,"dir","getattr search read open",1},
 {B,BA,"file","getattr read open",1},
 {B,BA,"lnk_file","getattr read",1},
 {B,BA,"process","getattr transition ptrace sigkill",1},
 {B,BA,"process2","nnp_transition nosuid_transition",1},
 {B,BE,"dir","relabelto getattr search read open setattr",1},
 {B,BE,"file","relabelto getattr read open map setattr execute",1},
 {BE,TF,"filesystem","associate",1},
 {BA,BE,"dir","getattr search",1},
 {BA,BE,"file","getattr read open map execute entrypoint",1},
 {BA,BA,"process","fork",1},
 {BA,"u:object_r:binder_device:s0","chr_file","open read write getattr ioctl map",1},
 {BA,SM,"binder","call",1},
 {SM,BA,"binder","transfer",1},
 {BA,"u:object_r:package_service:s0","service_manager","find",1},
 {BA,"u:object_r:activity_service:s0","service_manager","find",1},
 {BA,SS,"binder","call transfer",1},
 {SS,BA,"binder","call",1},
 {BA,B,"fd","use",1},
 {BA,B,"fifo_file","write getattr",1},
 {BA,ND,"chr_file","read",1},
 {Q,"u:object_r:activity_service:s0","service_manager","find",0},
 {Q,BE,"file","execute execute_no_trans entrypoint",0},
 {BA,QE,"file","execute execute_no_trans entrypoint",0},
 {B,BE,"file","write append create entrypoint execute_no_trans",0},
 {BA,BE,"file","write append create relabelfrom relabelto execute_no_trans",0},
 {BA,BE,"dir","write add_name remove_name create relabelfrom relabelto",0},
 {BA,"u:object_r:netd_service:s0","service_manager","find",0},
 {BA,"u:object_r:default_android_service:s0","service_manager","find",0},
 {BA,"u:object_r:package_service:s0","service_manager","add list",0},
 {BA,"u:object_r:activity_service:s0","service_manager","add list",0},
 {BA,SM,"service_manager","list",0},
 {BA,SM,"binder","transfer impersonate set_context_mgr",0},
 {SM,BA,"binder","call",0},
 {SS,BA,"binder","transfer",0},
 {BA,HF,"file","read write append map execute open relabelfrom relabelto",0},
 {BA,HF,"dir","read write search add_name remove_name relabelfrom relabelto",0},
 {BA,H,"fd","use",0},
 {BA,H,"unix_stream_socket","connectto",0},
 {BA,MF,"sock_file","write",0},
 {BA,K,"security","load_policy setenforce setbool setsecparam setcheckreqprot",0},
 {BA,B,"process","transition dyntransition ptrace signal sigkill",0},
 {BA,BA,"process","setexec setfscreate setsockcreate setcurrent dyntransition",0},
 {BA,BA,"capability","sys_admin sys_ptrace setuid setgid dac_override dac_read_search net_admin net_raw sys_module",0},
 {BA,NF,"file","getattr read open ioctl",0},
 {BA,TF,"filesystem","mount remount",0},
 {BA,"u:object_r:system_file:s0","file","entrypoint",0},
 {BA,"u:object_r:toolbox_exec:s0","file","entrypoint",0},
 {BA,"u:object_r:default_prop:s0","property_service","set",0},
 {BA,BA,"tcp_socket","create connect",0},
 {BA,BA,"udp_socket","create connect",0},
 {BA,BA,"rawip_socket","create",0},
 {BA,BA,"packet_socket","create",0},
 {BA,"u:object_r:hwbinder_device:s0","chr_file","open read write ioctl map",0},
 {BA,"u:object_r:vndbinder_device:s0","chr_file","open read write ioctl map",0},
 };
 printf("\"browser_action\":{\"fixed_types_present\":true,\"access\":[");
 for(size_t i=0;i<sizeof(browser_avs)/sizeof(*browser_avs);i++){
  const struct av *a=&browser_avs[i];sepol_security_class_t c=0;sepol_access_vector_t mask=0;struct sepol_av_decision d={0};unsigned reason=0;
  need(sepol_string_to_security_class(a->c,&c)==0&&c!=0,a->c);char *names=strdup(a->p),*save=NULL;need(names!=NULL,"browser permission buffer");
  for(char *name=strtok_r(names," ",&save);name;name=strtok_r(NULL," ",&save)){sepol_access_vector_t bit=0;need(sepol_string_to_av_perm(c,name,&bit)==0&&bit!=0,name);mask|=bit;}free(names);
  need(sepol_compute_av_reason(sid(a->s),sid(a->t),c,mask,&d,&reason)==0,"actual browser access decision");
  int ok=a->allow?(d.allowed&mask)==mask:(d.allowed&mask)==0;if(!ok)failed++;
  printf("%s{\"source\":\"%s\",\"target\":\"%s\",\"class\":\"%s\",\"permissions\":\"%s\",\"expected_allow\":%s,\"requested\":%u,\"actual_allowed\":%u,\"denial_reason\":%u,\"passed\":%s}",i?",":"",a->s,a->t,a->c,a->p,a->allow?"true":"false",mask,d.allowed,reason,ok?"true":"false");
 }
 printf("],\"automatic_transitions\":[");
 static const struct tr browser_trs[]={{B,BE,B},{H,BE,H}};
 sepol_security_class_t pc=0;need(sepol_string_to_security_class("process",&pc)==0&&pc,"browser process class");
 for(size_t i=0;i<sizeof(browser_trs)/sizeof(*browser_trs);i++){
  const struct tr *t=&browser_trs[i];sepol_security_id_t out=0;sepol_security_context_t context=NULL;size_t bytes=0;
  need(sepol_transition_sid(sid(t->s),sid(t->e),pc,&out)==0,"actual browser transition");
  need(sepol_sid_to_context(out,&context,&bytes)==0&&context&&bytes,"actual browser transition output");
  int ok=strcmp(context,t->expected)==0;if(!ok)failed++;
  printf("%s{\"source\":\"%s\",\"executable\":\"%s\",\"expected\":\"%s\",\"actual\":\"%s\",\"passed\":%s}",i?",":"",t->s,t->e,t->expected,context,ok?"true":"false");free(context);
 }
 printf("],\"checks_attempted\":%zu,\"failed\":%zu,\"passed\":%s}",sizeof(browser_avs)/sizeof(*browser_avs)+sizeof(browser_trs)/sizeof(*browser_trs),failed,failed?"false":"true");
 return failed;
}

int main(int argc,char **argv){
 need(argc==2,"one explicit offline policy path");int fd=open(argv[1],O_RDONLY|O_NOFOLLOW|O_CLOEXEC);need(fd>=0,"open policy");
 struct stat st,end;need(fstat(fd,&st)==0&&S_ISREG(st.st_mode)&&st.st_nlink==1&&st.st_uid==getuid()&&st.st_size>0&&st.st_size<=16777216,"bounded owned policy");
 size_t len=(size_t)st.st_size,n=0;void *data=malloc(len);need(data!=NULL,"allocate");
 while(n<len){ssize_t k=read(fd,(char*)data+n,len-n);if(k<0&&errno==EINTR)continue;need(k>0,"complete read");n+=(size_t)k;}
 char extra;need(read(fd,&extra,1)==0&&fstat(fd,&end)==0&&st.st_size==end.st_size&&st.st_mtim.tv_sec==end.st_mtim.tv_sec&&st.st_mtim.tv_nsec==end.st_mtim.tv_nsec&&st.st_ctim.tv_sec==end.st_ctim.tv_sec&&st.st_ctim.tv_nsec==end.st_ctim.tv_nsec,"stable held policy");need(close(fd)==0,"close policy");
 policydb_t decoded;need(policydb_init(&decoded)==0,"initialize separate readonly policydb");
 need(policydb_from_image(NULL,data,len,&decoded)==0,"decode identical full policy for exact ioctl bitmaps");
 need(sepol_load_policy(data,len)==0,"parse only private libsepol in-memory policy");free(data);size_t failed=0;
 printf("{\"schema\":\"p4-offline-policy-decisions-v2\",\"kernel_policy_operations\":0,\"runtime_qualified\":false,\"production_ready\":false,\"access\":[");
 for(size_t i=0;i<sizeof(avs)/sizeof(*avs);i++){
  const struct av *a=&avs[i];sepol_security_class_t c=0;sepol_access_vector_t mask=0;struct sepol_av_decision d={0};unsigned int reason=0;
  need(sepol_string_to_security_class(a->c,&c)==0&&c!=0,a->c);char *p=strdup(a->p),*save=NULL;need(p!=NULL,"permission buffer");
  for(char *name=strtok_r(p," ",&save);name;name=strtok_r(NULL," ",&save)){sepol_access_vector_t bit=0;need(sepol_string_to_av_perm(c,name,&bit)==0&&bit!=0,name);mask|=bit;}free(p);
  need(sepol_compute_av_reason(sid(a->s),sid(a->t),c,mask,&d,&reason)==0,"actual libsepol decision");int ok=a->allow?(d.allowed&mask)==mask:(d.allowed&mask)==0;if(!ok)failed++;
  printf("%s{\"source\":\"%s\",\"target\":\"%s\",\"class\":\"%s\",\"permissions\":\"%s\",\"expected_allow\":%s,\"requested\":%u,\"actual_allowed\":%u,\"denial_reason\":%u,\"passed\":%s}",i?",":"",a->s,a->t,a->c,a->p,a->allow?"true":"false",mask,d.allowed,reason,ok?"true":"false");
 }
 printf("],\"transitions\":[");sepol_security_class_t pc=0;need(sepol_string_to_security_class("process",&pc)==0,"process class");
 for(size_t i=0;i<sizeof(trs)/sizeof(*trs);i++){
  const struct tr *t=&trs[i];sepol_security_id_t out=0;sepol_security_context_t context=NULL;size_t count=0;
  need(sepol_transition_sid(sid(t->s),sid(t->e),pc,&out)==0,"actual libsepol transition");need(sepol_sid_to_context(out,&context,&count)==0&&context!=NULL&&count>0,"actual output context");int ok=strcmp(context,t->expected)==0;if(!ok)failed++;
  printf("%s{\"source\":\"%s\",\"executable\":\"%s\",\"expected\":\"%s\",\"actual\":\"%s\",\"passed\":%s}",i?",":"",t->s,t->e,t->expected,context,ok?"true":"false");free(context);
 }
 printf("],\"creation_labels\":[");
 for(size_t i=0;i<sizeof(creates)/sizeof(*creates);i++){
  const struct cr *v=&creates[i];sepol_security_class_t c=0;sepol_security_id_t out=0;sepol_security_context_t context=NULL;size_t count=0;
  need(sepol_string_to_security_class(v->c,&c)==0&&c!=0,v->c);
  need(sepol_transition_sid(sid(v->s),sid(v->parent),c,&out)==0,"actual libsepol fixed initial inode label");
  need(sepol_sid_to_context(out,&context,&count)==0&&context!=NULL&&count>0,"actual creation context");int ok=strcmp(context,v->expected)==0;if(!ok)failed++;
  printf("%s{\"source\":\"%s\",\"parent\":\"%s\",\"class\":\"%s\",\"expected\":\"%s\",\"actual\":\"%s\",\"passed\":%s}",i?",":"",v->s,v->parent,v->c,v->expected,context,ok?"true":"false");free(context);
 }
 printf("],");failed+=systemd_creation_checks();failed+=namespace_checks(&decoded);printf(",");failed+=browser_checks(&decoded);policydb_destroy(&decoded);
 printf(",\"failed\":%zu,\"passed\":%s}\n",failed,failed?"false":"true");need(fflush(stdout)==0,"full result flush");return failed?1:0;
}
