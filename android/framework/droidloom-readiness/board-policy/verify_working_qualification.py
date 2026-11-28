"""Verify the complete fixed working-qualification authority in the normal link.

The expected ACL below is a separately reviewed source table. It is never
learned from a candidate binary/export. Normal alias copies use the fixed
source/type/class roster and preserve only those independently stated vectors.
This verifier does not grant application, working-copy or boot qualification.
"""
import ctypes
import hashlib
import json
from collections import defaultdict
from functools import lru_cache

from derive_shared_payload_cgroup_policy import Decision, Policy, parse_expression

PARENT = "p4_linux_working_qualification_t"
PREP = "p4_linux_working_privateprep_t"
PHYSICAL = "p4_linux_working_application_t"
RETURN = "p4_linux_working_return_t"
LABELER = "p4_linux_working_watchdog_label_t"
BIRTH = "p4_linux_working_payload_birth_t"
HOSTS = frozenset((PARENT, PREP, PHYSICAL, RETURN))
CLIENTS = frozenset((PARENT, PREP, PHYSICAL))
CHILDREN = frozenset((PREP, PHYSICAL))
SUBJECTS = HOSTS | {LABELER, BIRTH}
DATA = frozenset(["p4_linux_working_config_t","p4_linux_working_unit_t","p4_linux_working_parent_t","p4_linux_working_evidence_t","p4_linux_working_output_root_t","p4_linux_working_plan_t","p4_linux_working_journal_t","p4_linux_working_comparison_t","p4_linux_working_current_dir_t","p4_linux_working_current_t","p4_linux_working_current_lock_t","p4_linux_native_leaf_source_t","p4_linux_native_leaf_layout_t","p4_linux_native_leaf_release_t","p4_linux_working_cgroup_t","p4_linux_working_limits_t","p4_linux_working_watchdog_t","p4_linux_working_apk_dir_t","p4_linux_working_apk_input_t"])
EMPTY_DIR = "p4_linux_empty_meituan_dir_t"
EMPTY_APK = "p4_linux_empty_meituan_apk_t"
EMPTY_DATA = frozenset((EMPTY_DIR, EMPTY_APK))
OWNED = SUBJECTS | DATA | EMPTY_DATA
DISK = DATA - {"p4_linux_working_comparison_t", "p4_linux_working_cgroup_t",
               "p4_linux_working_limits_t", "p4_linux_working_watchdog_t"}
GROUPS = {
    "p4_working_actors": HOSTS,
    "p4_working_clients": CLIENTS,
    "p4_working_children": CHILDREN,
    "p4_working_disk_types": DISK,
    "p4_working_data": DATA,
    "p4_working_main_proc_peers": frozenset(("droidloom_broker", "init", "system_server")),
    "p4_working_proc_peers": CLIENTS | {"droidloom_broker", "init", "system_server", "init_t"},
    "p4_working_android_traversal": frozenset(
        ("rootfs", "system_file", "system_data_root_file", "system_data_file")),
}
# These two source-only set aliases are used to derive retained groups.
# secilc omits them from the linked policy when no runtime rule names them.
# Their retained concrete anchors are still checked below; a present alias
# must retain its exact source-owned membership.
DERIVATION_ONLY_GROUPS = frozenset((
    "p4_working_data", "p4_working_main_proc_peers"))

# Source-owned literal rules. The only macro in the component has already been
# reviewed as this common HOSTS table; no candidate macro is interpreted here.
FIXED_ACL = r"""
(allow p4_working_disk_types labeledfs (filesystem (associate)))
(allow p4_linux_working_comparison_t tmpfs (filesystem (associate)))
(allow p4_linux_working_watchdog_t device (filesystem (associate)))
(allow init_t p4_linux_working_unit_t (file (getattr open read map)))
(allow p4_linux_service_executor_t p4_linux_working_unit_t (file (getattr open read)))
(allow p4_linux_service_executor_t droidloom_public_control_client_exec (file (getattr open read execute map)))
(allow p4_linux_service_executor_t p4_linux_working_qualification_t (process (transition siginh rlimitinh)))
(allow p4_linux_service_executor_t p4_linux_working_return_t (process (transition siginh rlimitinh)))
(allow p4_linux_working_qualification_t droidloom_public_control_client_exec (file (getattr open read execute map entrypoint)))
(allow p4_linux_working_return_t p4_linux_once_return_exec_t (file (getattr open read execute map entrypoint)))
(auditallow p4_linux_service_executor_t p4_linux_working_qualification_t (process (transition)))
(auditallow p4_linux_service_executor_t p4_linux_working_return_t (process (transition)))
(allow p4_linux_working_qualification_t self (process (setexec)))
(allow p4_linux_working_qualification_t self (file (write)))
(allow p4_linux_working_qualification_t p4_working_children (process (transition siginh rlimitinh)))
(allow p4_working_children droidloom_public_control_client_exec (file (getattr open read execute map entrypoint execute_no_trans)))
(allow p4_working_children p4_linux_working_qualification_t (process (sigchld)))
(allow p4_linux_working_qualification_t p4_working_children (process (getattr signull signal sigkill)))
(auditallow p4_linux_working_qualification_t p4_working_children (process (transition)))
(allow p4_working_clients p4_working_proc_peers (dir (getattr search)))
(allow p4_working_clients p4_working_proc_peers (file (getattr open read)))
(allow p4_working_clients p4_working_proc_peers (lnk_file (getattr read)))
(allow droidloom_broker p4_linux_working_application_t (dir (getattr search)))
(allow droidloom_broker p4_linux_working_application_t (file (getattr open read)))
(allow droidloom_broker p4_linux_working_application_t (lnk_file (getattr read)))
(allow p4_linux_working_qualification_t self (capability (setuid setgid sys_ptrace)))
(allow p4_working_children self (capability (setuid setgid sys_ptrace)))
(allow p4_working_clients self (cap_userns (sys_ptrace)))
(allow p4_working_clients p4_working_android_traversal (dir (getattr search)))
(allow p4_working_clients app_data_file (dir (getattr)))
(allow p4_working_clients zygote_exec (file (getattr)))
(allow p4_working_clients init_exec (file (getattr)))
(allow p4_working_clients self (unix_stream_socket (create connect getattr read write getopt setopt shutdown)))
(allow p4_working_clients self (unix_dgram_socket (create connect getattr read write sendto getopt setopt shutdown)))
(allow p4_working_clients droidloom_broker (fd (use)))
(allow p4_working_clients droidloom_broker (unix_stream_socket (getattr read write getopt shutdown)))
(allow p4_working_clients p4_working_clients (fd (use)))
(allow p4_working_clients p4_working_clients (unix_stream_socket (getattr read write getopt setopt shutdown)))
(allow p4_working_clients p4_working_clients (unix_dgram_socket (getattr read write sendto getopt setopt shutdown)))
(allow p4_working_clients p4_working_clients (fifo_file (getattr read write)))
(allow p4_working_children self (process (signull signal sigkill)))
(allow p4_working_clients droidloom_public_control_client_exec (file (getattr open read map)))
(allow p4_working_clients droidloom_container_entry_exec_t (file (getattr open read)))
(allow p4_working_clients droidloom_presenter_exec (file (getattr open read)))
(allow p4_working_clients init_exec_t (file (getattr open read)))
(allow p4_working_clients p4_linux_native_public_files (dir (getattr search)))
(allow p4_working_clients p4_linux_native_public_files (file (getattr open read)))
(allow p4_working_clients p4_linux_native_public_files (lnk_file (getattr read)))
(allow p4_working_clients p4_linux_public_accounts_t (file (getattr open read)))
(allow p4_working_clients p4_linux_machine_id_t (file (getattr open read)))
(allow p4_working_clients p4_linux_distribution_info_t (file (getattr open read)))
(allow p4_working_clients p4_linux_native_leaf_source_t (dir (getattr search open read)))
(allow p4_working_clients p4_linux_native_leaf_source_t (file (getattr open read)))
(allow p4_working_clients droidloom_public_apk_root (dir (getattr search)))
(allow p4_working_clients droidloom_public_apk_dir (dir (getattr search)))
(allow p4_working_clients droidloom_public_apk_input (file (getattr open read)))
(allow p4_linux_working_privateprep_t p4_linux_working_apk_dir_t (dir (getattr search open read)))
(allow p4_linux_working_privateprep_t p4_linux_working_apk_input_t (file (getattr open read)))
(allow p4_working_children p4_linux_native_bin_t (file (getattr open read execute execute_no_trans map)))
(typetransition p4_working_clients tmpfs file p4_linux_working_comparison_t)
(typetransition p4_working_clients tmpfs memfd_file p4_linux_working_comparison_t)
(allow p4_working_clients p4_linux_working_comparison_t (file (getattr create open read write setattr)))
(allow p4_working_clients p4_linux_working_comparison_t (memfd_file (getattr create open read write setattr)))
(allow p4_linux_working_qualification_t p4_linux_systemd_run_t (dir (getattr search)))
(allow p4_linux_working_qualification_t droidloom_manager_private_socket (sock_file (getattr write)))
(allow p4_linux_working_qualification_t init_t (unix_stream_socket (connectto)))
(allow init_t p4_linux_working_qualification_t (unix_stream_socket (getattr read write)))
(allow p4_linux_working_qualification_t p4_linux_working_unit_t (service (status)))
(allow p4_working_children p4_linux_systemd_run_t (dir (getattr search)))
(allow p4_working_children droidloom_manager_private_socket (sock_file (getattr write)))
(allow p4_working_children init_t (unix_stream_socket (connectto)))
(allow init_t p4_working_children (unix_stream_socket (getattr read write)))
(allow p4_working_children p4_linux_user_run_t (dir (getattr search)))
(allow p4_working_children p4_linux_user_run_t (sock_file (getattr write)))
(allow p4_working_children p4_linux_user_manager_t (unix_stream_socket (connectto)))
(allow p4_linux_user_manager_t p4_working_children (unix_stream_socket (getattr read write)))
(allow p4_working_children p4_linux_production_unit_file_t (service (status)))
(allow p4_working_actors p4_linux_service_executor_t (fd (use)))
(allow p4_working_actors p4_linux_service_executor_t (unix_stream_socket (read write)))
(allow p4_working_actors init_t (process (sigchld)))
(allow init_t p4_working_actors (process (getattr signull signal sigkill sigstop)))
(allow p4_working_actors p4_linux_apparmor_enabled_t (file (getattr open read)))
(genfscon cgroup2 "/system.slice/droidloom-working-qualification.service" (u object_r p4_linux_working_cgroup_t ((s0) (s0))))
(genfscon cgroup2 "/system.slice/droidloom-working-qualification.service/" (u object_r p4_linux_working_cgroup_t ((s0) (s0))))
(genfscon cgroup2 "/system.slice/droidloom-working-qualification.service/cpu.max" (u object_r p4_linux_working_limits_t ((s0) (s0))))
(genfscon cgroup2 "/system.slice/droidloom-working-qualification.service/memory.max" (u object_r p4_linux_working_limits_t ((s0) (s0))))
(genfscon cgroup2 "/system.slice/droidloom-working-qualification-return.service" (u object_r p4_linux_working_cgroup_t ((s0) (s0))))
(genfscon cgroup2 "/system.slice/droidloom-working-qualification-return.service/" (u object_r p4_linux_working_cgroup_t ((s0) (s0))))
(typetransition init_t p4_linux_system_slice_t dir "droidloom-working-qualification.service" p4_linux_working_cgroup_t)
(typetransition init_t p4_linux_system_slice_t dir "droidloom-working-qualification-return.service" p4_linux_working_cgroup_t)
(allow init_t p4_linux_working_cgroup_t (dir (getattr search open read create write add_name remove_name rmdir setattr)))
(allow init_t p4_linux_working_cgroup_t (file (getattr open read write create watch)))
(allow init_t p4_linux_working_limits_t (file (getattr open read write create watch)))
(allow p4_working_actors p4_linux_cgroup_root_t (dir (getattr search)))
(allow p4_working_actors p4_linux_system_slice_t (dir (getattr search)))
(allow p4_working_actors p4_linux_working_cgroup_t (dir (getattr search open read)))
(allow p4_working_actors p4_linux_working_cgroup_t (file (getattr open read)))
(allow p4_working_clients p4_linux_working_limits_t (file (getattr open read)))
(allow p4_linux_working_qualification_t p4_linux_working_limits_t (file (write)))
(allow p4_working_actors p4_linux_working_evidence_t (dir (getattr search open read)))
(allow p4_working_actors p4_linux_working_evidence_t (file (getattr open read)))
(allow p4_linux_working_qualification_t p4_linux_working_evidence_t (dir (write add_name)))
(allow p4_linux_working_return_t p4_linux_working_evidence_t (dir (write add_name)))
(typetransition p4_linux_working_qualification_t p4_linux_working_evidence_t file p4_linux_working_evidence_t)
(typetransition p4_linux_working_return_t p4_linux_working_evidence_t file p4_linux_working_evidence_t)
(allow p4_linux_working_qualification_t p4_linux_working_evidence_t (file (create write setattr lock)))
(allow p4_linux_working_return_t p4_linux_working_evidence_t (file (create write setattr lock)))
(allow p4_working_clients p4_linux_working_output_root_t (dir (getattr search)))
(allow p4_working_clients p4_linux_working_output_root_t (dir (write add_name)))
(typetransition p4_linux_working_qualification_t p4_linux_working_output_root_t dir p4_linux_working_plan_t)
(typetransition p4_working_children p4_linux_working_output_root_t dir p4_linux_working_journal_t)
(allow p4_working_clients p4_linux_working_plan_t (dir (getattr search open read)))
(allow p4_working_clients p4_linux_working_plan_t (file (getattr open read)))
(allow p4_linux_working_qualification_t p4_linux_working_plan_t (dir (create write add_name)))
(typetransition p4_linux_working_qualification_t p4_linux_working_plan_t file p4_linux_working_plan_t)
(allow p4_linux_working_qualification_t p4_linux_working_plan_t (file (getattr create open read write setattr lock)))
(allow p4_working_clients p4_linux_working_journal_t (dir (getattr search open read)))
(allow p4_working_clients p4_linux_working_journal_t (file (getattr open read)))
(allow p4_working_children p4_linux_working_journal_t (dir (create write add_name)))
(typetransition p4_working_children p4_linux_working_journal_t file p4_linux_working_journal_t)
(allow p4_working_children p4_linux_working_journal_t (file (getattr create open read write setattr lock)))
(allow p4_working_clients p4_linux_user_home_t (dir (getattr search)))
(allow p4_working_clients p4_linux_working_current_dir_t (dir (getattr search)))
(allow p4_working_clients p4_linux_working_current_t (file (getattr open read)))
(allow p4_linux_working_qualification_t p4_linux_working_current_lock_t (file (getattr open read lock)))
(allow p4_linux_working_qualification_t p4_linux_working_current_dir_t (dir (open read write add_name remove_name)))
(typetransition p4_linux_working_qualification_t p4_linux_working_current_dir_t file p4_linux_working_current_t)
(allow p4_linux_working_qualification_t p4_linux_working_current_t (file (getattr open read create write setattr rename unlink)))
(allow p4_working_clients p4_linux_native_leaf_layout_t (dir (getattr search)))
(allow p4_working_clients p4_linux_native_leaf_layout_t (file (getattr open read)))
(allow p4_working_clients p4_linux_native_leaf_release_t (file (getattr open read)))
(allow p4_linux_working_qualification_t p4_linux_native_leaf_layout_t (dir (write add_name)))
(typetransition p4_linux_working_qualification_t p4_linux_native_leaf_layout_t file p4_linux_native_leaf_release_t)
(allow p4_linux_working_qualification_t p4_linux_native_leaf_release_t (file (getattr open read create write setattr)))
(allow p4_linux_working_qualification_t p4_linux_working_watchdog_t (chr_file (getattr open write ioctl)))
(allowx p4_linux_working_qualification_t p4_linux_working_watchdog_t (ioctl chr_file (0x5705)))
(allow p4_linux_working_return_t p4_linux_maintenance_config_t (dir (getattr search)))
(allow p4_linux_working_return_t p4_linux_maintenance_config_t (file (getattr open read)))
(typetransition p4_linux_working_return_t p4_linux_maintenance_exec_t process p4_linux_maintenance_t)
(allow p4_linux_working_return_t p4_linux_maintenance_exec_t (file (getattr open read execute map)))
(allow p4_linux_working_return_t p4_linux_maintenance_t (process (transition siginh rlimitinh)))
(allow p4_linux_working_return_t p4_linux_maintenance_t (process2 (nnp_transition)))
(allow p4_linux_maintenance_t p4_linux_working_return_t (process (sigchld)))
(allow p4_linux_maintenance_t p4_linux_working_return_t (fd (use)))
(allow p4_linux_maintenance_t p4_linux_working_return_t (fifo_file (getattr read write)))
(allow p4_linux_maintenance_t p4_linux_working_evidence_t (file (getattr read write)))
(allow kernel p4_linux_working_watchdog_label_t (process (dyntransition getattr sigkill)))
(allow p4_linux_working_watchdog_label_t kernel (process (sigchld)))
(allow p4_linux_working_watchdog_label_t kernel (fd (use)))
(allow p4_linux_working_watchdog_label_t self (process (getattr getcap)))
(allow p4_linux_working_watchdog_label_t self (fd (use)))
(allow p4_linux_working_watchdog_label_t self (dir (getattr search)))
(allow p4_linux_working_watchdog_label_t self (file (getattr open read)))
(allow p4_linux_working_watchdog_label_t self (lnk_file (getattr read)))
(allow p4_linux_working_watchdog_label_t kernel (dir (getattr search)))
(allow p4_linux_working_watchdog_label_t kernel (file (getattr open read)))
(allow p4_linux_working_watchdog_label_t kernel (lnk_file (getattr read)))
(allow p4_linux_working_watchdog_label_t proc (dir (getattr search)))
(allow p4_linux_working_watchdog_label_t p4_linux_rootdir_t (dir (getattr search)))
(allow p4_linux_working_watchdog_label_t proc (filesystem (getattr)))
(allow p4_linux_working_watchdog_label_t device (filesystem (getattr)))
(allow p4_linux_working_watchdog_label_t device (chr_file (getattr relabelfrom)))
(allow p4_linux_working_watchdog_label_t p4_linux_working_watchdog_t (chr_file (getattr relabelto)))
(allow kernel p4_linux_working_watchdog_t (chr_file (getattr)))
(auditallow kernel p4_linux_working_watchdog_label_t (process (dyntransition)))
(auditallow p4_linux_working_watchdog_label_t p4_linux_working_watchdog_t (chr_file (relabelto)))
(allow p4_working_actors self (process (fork getattr getcap setcap getpgid setpgid getsession getsched sigchld)))
(allow p4_working_actors self (dir (getattr search open read)))
(allow p4_working_actors self (file (getattr open read)))
(allow p4_working_actors self (lnk_file (getattr read)))
(allow p4_working_actors self (fd (use)))
(allow p4_working_actors self (fifo_file (getattr read write)))
(allow p4_working_actors p4_linux_rootdir_t (dir (getattr search)))
(allow p4_working_actors p4_linux_etc_dir_t (dir (getattr search)))
(allow p4_working_actors p4_linux_product_store_t (dir (getattr search)))
(allow p4_working_actors p4_linux_var_lib_t (dir (getattr search)))
(allow p4_working_actors p4_linux_run_t (dir (getattr search)))
(allow p4_working_actors p4_linux_runtime_lib_t (file (getattr open read execute map)))
(allow p4_working_actors p4_linux_elf_interpreter_t (file (getattr open read execute map)))
(allow p4_working_actors p4_linux_usrmerge_link_t (lnk_file (getattr read)))
(allow p4_working_actors p4_linux_standardio_t (chr_file (getattr open read write)))
(allow p4_working_actors null_device (chr_file (getattr open read write)))
(allow p4_working_actors p4_linux_working_config_t (dir (getattr search)))
(allow p4_working_actors p4_linux_working_config_t (file (getattr open read)))
(allow p4_working_actors p4_linux_working_unit_t (file (getattr open read)))
(allow p4_working_actors p4_linux_once_config_t (dir (getattr search)))
(allow p4_working_actors p4_linux_once_parent_t (dir (getattr search)))
(allow p4_working_actors p4_linux_working_parent_t (dir (getattr search)))
(allow p4_working_actors droidloom_package_config_parents (dir (getattr search)))
(allow p4_working_actors p4_linux_mac_release_input_t (file (getattr open read)))
(allow p4_working_actors p4_linux_early_handoff_dir_t (dir (getattr search)))
(allow p4_working_actors p4_linux_host_mount_identity_t (file (getattr open read)))
(allow p4_working_actors p4_linux_native_dev_root_t (dir (getattr search)))
(allow p4_working_actors p4_linux_root_uuid_link_t (lnk_file (getattr read)))
(allow p4_working_actors p4_linux_root_block_t (blk_file (getattr)))
(allow p4_working_actors labeledfs (filesystem (getattr)))
(allow p4_working_actors tmpfs (filesystem (getattr)))
(allow p4_working_actors proc (filesystem (getattr)))
(allow p4_working_actors sysfs (filesystem (getattr)))
(allow p4_working_actors proc (dir (getattr search)))
(allow p4_working_actors proc (lnk_file (getattr read)))
(allow p4_working_actors proc (file (getattr open read)))
(allow p4_working_actors proc_random (dir (getattr search)))
(allow p4_working_actors proc_random (file (getattr open read)))
(allow p4_working_actors proc_cmdline (file (getattr open read)))
(allow p4_working_actors selinuxfs (dir (getattr search)))
(allow p4_working_actors selinuxfs (file (getattr open read)))
(allow p4_working_actors sysfs (dir (getattr search open read)))
(allow p4_working_actors sysfs (file (getattr open read)))
(allow p4_working_actors device (dir (getattr search)))
(allowx p4_working_actors p4_kernel_ns_handle_t (ioctl file (0xb703)))

"""

# Source-owned EMPTY diagnostic. The two inputs have no generic Linux-data
# membership. Its service entry is explicit; no new default transition exists.
EMPTY_ACL = r"""
(allow p4_linux_empty_meituan_dir_t labeledfs (filesystem (associate)))
(allow p4_linux_empty_meituan_apk_t labeledfs (filesystem (associate)))
(allow init_t p4_linux_working_output_root_t (dir (getattr search)))
(allow init_t p4_linux_empty_meituan_dir_t (dir (getattr search)))
(allow init_t p4_linux_empty_meituan_apk_t (file (getattr)))
(allow p4_linux_working_privateprep_t p4_linux_empty_meituan_dir_t (dir (getattr search)))
(allow p4_linux_working_privateprep_t p4_linux_empty_meituan_apk_t (file (getattr open read)))
(allow p4_linux_service_executor_t p4_linux_working_privateprep_t (process (transition siginh rlimitinh)))
(auditallow p4_linux_service_executor_t p4_linux_working_privateprep_t (process (transition)))
(allow droidloom_broker p4_linux_working_privateprep_t (dir (getattr search)))
(allow droidloom_broker p4_linux_working_privateprep_t (file (getattr open read)))
(allow droidloom_broker p4_linux_working_privateprep_t (lnk_file (getattr read)))
"""
# These are existing normal rules whose closed attributes gain the new types.
# No grant is inferred from a unit capability bounding set or an old JSON report.
INHERITED_ACL = r"""
(allow p4_working_actors p4_linux_timezone_link_t (lnk_file (getattr read)))
(allow p4_working_actors p4_kernel_ns_handle_t (file (getattr open read ioctl)))
(allow p4_working_actors p4_kernel_ns_handle_t (filesystem (getattr)))
(allow p4_working_actors p4_kernel_pid_handle_t (filesystem (getattr)))
(allow p4_working_clients droidloom_public_control_dir (dir (getattr search)))
(allow p4_working_clients droidloom_public_control_socket (sock_file (getattr write)))
(allow p4_working_clients droidloom_broker (unix_stream_socket (connectto)))
(allow droidloom_broker p4_working_clients (unix_stream_socket (read write)))
(allow droidloom_metadata_observer p4_working_data (dir (getattr search)))
(allow droidloom_query_io p4_working_data (dir (getattr search)))
(allow p4_linux_working_cgroup_t cgroup_v2 (filesystem (associate)))
(allow p4_linux_working_limits_t cgroup_v2 (filesystem (associate)))
"""
# Independently reviewed empty-inode birth and its original preparation peer.
# The selected shmem allocation does not pass through normal create/open hooks.
# F_GET/ADD_SEALS do not add a setattr or ioctl grant. SCM_RIGHTS does check the
# returned O_RDWR description, so the original parent alone receives RW body
# access and later opens its own held descriptor read-only after actual reap.
# The separate native-APK component supplies these concrete cross-component
# edges. Keep an independent expectation here because this verifier closes
# every incoming/outgoing edge of the working actors and source objects too.
# The parent, return and birth roles receive no helper/copy/Reader authority.
NATIVE_APK_CLIENT_ACL = r"""
(allow droidloom_broker p4_linux_native_leaf_source_t (dir (getattr search)))
(allow p4_linux_working_privateprep_t droidloom_native_helper_source (dir (getattr search open read)))
(allow p4_linux_working_privateprep_t droidloom_native_helper_source (file (getattr open read)))
(allow p4_linux_working_application_t droidloom_native_helper_source (dir (getattr search open read)))
(allow p4_linux_working_application_t droidloom_native_helper_source (file (getattr open read)))
(allow p4_linux_working_privateprep_t droidloom_native_leaf_apk_reader (fd (use)))
(allow p4_linux_working_application_t droidloom_native_leaf_apk_reader (fd (use)))
(allow p4_linux_working_privateprep_t droidloom_native_leaf_apk_copy (file (getattr read)))
(allow p4_linux_working_privateprep_t droidloom_native_leaf_apk_copy (memfd_file (getattr read)))
(allow p4_linux_working_application_t droidloom_native_leaf_apk_copy (file (getattr read)))
(allow p4_linux_working_application_t droidloom_native_leaf_apk_copy (memfd_file (getattr read)))
"""

PAYLOAD_BIRTH_ACL = r"""
(allow p4_linux_working_privateprep_t self (process (setexec)))
(allow p4_linux_working_privateprep_t p4_linux_working_payload_birth_t (process (transition siginh rlimitinh getattr sigkill)))
(allow p4_linux_working_privateprep_t p4_linux_working_payload_birth_t (process2 (nnp_transition)))
(auditallow p4_linux_working_privateprep_t p4_linux_working_payload_birth_t (process (transition)))
(allow p4_linux_working_payload_birth_t p4_linux_working_privateprep_t (process (sigchld)))
(allow p4_linux_working_payload_birth_t self (process (getattr getcap)))
(allow p4_linux_working_payload_birth_t p4_linux_working_privateprep_t (fd (use)))
(allow p4_linux_working_payload_birth_t p4_linux_working_privateprep_t (fifo_file (getattr read)))
(allow p4_linux_working_payload_birth_t p4_linux_working_privateprep_t (unix_stream_socket (getattr getopt read write)))
(allow p4_linux_working_payload_birth_t droidloom_public_control_client_exec (file (getattr open read execute map entrypoint)))
(allow p4_linux_working_payload_birth_t p4_linux_elf_interpreter_t (file (getattr open read execute map)))
(allow p4_linux_working_payload_birth_t p4_linux_runtime_lib_t (file (getattr open read execute map)))
(allow p4_linux_working_payload_birth_t p4_linux_console_ld_cache_native_config_t (file (getattr open read map)))
(allow p4_linux_working_payload_birth_t p4_linux_rootdir_t (dir (getattr search)))
(allow p4_linux_working_payload_birth_t p4_linux_etc_dir_t (dir (getattr search)))
(allow p4_linux_working_payload_birth_t p4_linux_usrmerge_link_t (lnk_file (getattr read)))
(allow p4_linux_working_payload_birth_t proc (dir (getattr search)))
(allow p4_linux_working_payload_birth_t proc (lnk_file (getattr read)))
(allow p4_linux_working_payload_birth_t proc (filesystem (getattr)))
(allow p4_linux_working_payload_birth_t self (dir (getattr search)))
(allow p4_linux_working_payload_birth_t self (file (getattr open read)))
(allow p4_linux_working_payload_birth_t self (lnk_file (getattr read)))
(allow p4_linux_working_payload_birth_t tmpfs (filesystem (getattr)))
(allow p4_linux_working_privateprep_t p4_kernel_pid_handle_t (file (getattr ioctl)))
(allowx p4_linux_working_privateprep_t p4_kernel_pid_handle_t (ioctl file (0xff0b)))
(allow p4_linux_working_payload_birth_t p4_kernel_pid_handle_t (file (getattr ioctl)))
(allowx p4_linux_working_payload_birth_t p4_kernel_pid_handle_t (ioctl file (0xff0b)))
(typetransition p4_linux_working_payload_birth_t tmpfs file droidloom_apk_payload)
(typetransition p4_linux_working_payload_birth_t tmpfs memfd_file droidloom_apk_payload)
(allow p4_linux_working_payload_birth_t droidloom_apk_payload (file (getattr)))
(allow p4_linux_working_payload_birth_t droidloom_apk_payload (memfd_file (getattr)))
(allow p4_linux_working_privateprep_t p4_linux_working_payload_birth_t (fd (use)))
(allow p4_linux_working_privateprep_t droidloom_apk_payload (file (getattr open read write)))
(allow p4_linux_working_privateprep_t droidloom_apk_payload (memfd_file (getattr open read write)))
"""
# These are fixed normal producer aliases, not names discovered in a final
# policy. The original-return verifier independently checks the first 32 rows;
# the remaining exact provider rows are checked again below.
FIXED_ALIASES = [{"source":"p4_linux_setup_exec_t","target":"p4_linux_tmpfiles_exec_t","class":"file"},{"source":"p4_linux_runtime_lib_t","target":"p4_linux_tmpfiles_usr_config_t","class":"file"},{"source":"p4_linux_native_config_t","target":"p4_linux_tmpfiles_etc_config_t","class":"file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_tmpfiles_config_dir_t","class":"dir"},{"source":"p4_linux_rootdir_t","target":"p4_linux_tmpfiles_runtime_dir_t","class":"dir"},{"source":"p4_linux_native_data_t","target":"p4_linux_tmpfiles_nologin_t","class":"file"},{"source":"p4_linux_usrmerge_link_t","target":"p4_linux_tmpfiles_shm_link_t","class":"lnk_file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_kmod_tmpfiles_dir_t","class":"dir"},{"source":"p4_linux_native_data_t","target":"p4_linux_kmod_static_nodes_t","class":"file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_journal_catalog_dir_t","class":"dir"},{"source":"p4_linux_native_data_t","target":"p4_linux_journal_catalog_file_t","class":"file"},{"source":"p4_linux_setup_exec_t","target":"p4_linux_random_seed_exec_t","class":"file"},{"source":"p4_linux_native_data_t","target":"p4_linux_random_seed_file_t","class":"file"},{"source":"p4_linux_runtime_lib_t","target":"p4_linux_timesyncd_exec_t","class":"file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_timesyncd_run_t","class":"dir"},{"source":"p4_linux_native_data_t","target":"p4_linux_timesyncd_run_t","class":"file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_timesyncd_state_t","class":"dir"},{"source":"p4_linux_native_data_t","target":"p4_linux_timesyncd_state_t","class":"file"},{"source":"p4_linux_native_config_t","target":"p4_linux_timesyncd_config_t","class":"file"},{"source":"p4_linux_native_config_t","target":"p4_linux_timesyncd_nsswitch_t","class":"file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_timesyncd_netif_t","class":"dir"},{"source":"p4_linux_native_data_t","target":"p4_linux_timesyncd_netif_t","class":"file"},{"source":"port","target":"p4_linux_timesyncd_dns_port_t","class":"tcp_socket"},{"source":"p4_linux_setup_exec_t","target":"p4_linux_ldconfig_exec_t","class":"file"},{"source":"p4_linux_native_config_t","target":"p4_linux_ldconfig_config_t","class":"file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_ldconfig_config_dir_t","class":"dir"},{"source":"p4_linux_rootdir_t","target":"p4_linux_ldconfig_aux_dir_t","class":"dir"},{"source":"p4_linux_native_data_t","target":"p4_linux_ldconfig_aux_t","class":"file"},{"source":"p4_linux_setup_exec_t","target":"p4_linux_update_done_exec_t","class":"file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_update_done_var_dir_t","class":"dir"},{"source":"p4_linux_native_config_t","target":"p4_linux_update_done_etc_file_t","class":"file"},{"source":"p4_linux_native_data_t","target":"p4_linux_update_done_var_file_t","class":"file"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_remount_exec_t"},{"class":"file","source":"p4_linux_native_bin_t","target":"p4_linux_remount_mount_exec_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_remount_fstab_native_config_t"},{"class":"lnk_file","source":"device","target":"p4_linux_root_uuid_link_t"},{"class":"blk_file","source":"device","target":"p4_linux_root_block_t"},{"class":"dir","source":"p4_linux_rootdir_t","target":"p4_linux_systemd_state_parent_t"},{"class":"file","source":"p4_linux_native_bin_t","target":"p4_linux_netplan_exec_t"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_netplan_library_t"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_netplan_yaml_t"},{"class":"dir","source":"p4_linux_rootdir_t","target":"p4_linux_netplan_input_dir_t"},{"class":"file","source":"p4_linux_network_manager_run_t","target":"p4_linux_netplan_output_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_netplan_private_config_t"},{"class":"dir","source":"p4_linux_network_manager_run_t","target":"p4_linux_netplan_profiles_dir_t"},{"class":"dir","source":"p4_linux_rootdir_t","target":"p4_linux_netplan_link_dir_t"},{"class":"dir","source":"p4_linux_rootdir_t","target":"p4_linux_netplan_rule_dir_t"},{"class":"file","source":"p4_linux_native_data_t","target":"p4_linux_netplan_link_rule_t"},{"class":"dir","source":"p4_linux_etc_dir_t","target":"p4_linux_sysusers_etc_root_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_sysusers_passwd_lock_t"},{"class":"file","source":"p4_linux_native_bin_t","target":"p4_linux_console_helper_native_bin_t"},{"class":"file","source":"p4_linux_native_bin_t","target":"p4_linux_console_vtrgb_native_bin_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_console_cache_exec_native_config_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_console_cache_native_config_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_console_config_native_config_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_console_public_native_config_t"},{"class":"file","source":"p4_linux_native_data_t","target":"p4_linux_console_public_native_data_t"},{"class":"dir","source":"p4_linux_rootdir_t","target":"p4_linux_console_cache_dir_t"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_console_entry_runtime_lib_t"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_console_library_runtime_lib_t"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_console_public_runtime_lib_t"},{"class":"file","source":"p4_linux_native_bin_t","target":"p4_linux_console_interpreter_native_bin_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_console_ld_cache_native_config_t"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_console_locale_runtime_lib_t"}]
EXTRA_ALIAS_PROVIDERS = {"derive_native_remount_policy.py":[{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_remount_exec_t"},{"class":"file","source":"p4_linux_native_bin_t","target":"p4_linux_remount_mount_exec_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_remount_fstab_native_config_t"},{"class":"lnk_file","source":"device","target":"p4_linux_root_uuid_link_t"},{"class":"blk_file","source":"device","target":"p4_linux_root_block_t"}],"derive_native_logind_state_policy.py":[{"class":"dir","source":"p4_linux_rootdir_t","target":"p4_linux_systemd_state_parent_t"}],"derive_native_netplan_policy.py":[{"class":"file","source":"p4_linux_native_bin_t","target":"p4_linux_netplan_exec_t"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_netplan_library_t"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_netplan_yaml_t"},{"class":"dir","source":"p4_linux_rootdir_t","target":"p4_linux_netplan_input_dir_t"},{"class":"file","source":"p4_linux_network_manager_run_t","target":"p4_linux_netplan_output_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_netplan_private_config_t"},{"class":"dir","source":"p4_linux_network_manager_run_t","target":"p4_linux_netplan_profiles_dir_t"},{"class":"dir","source":"p4_linux_rootdir_t","target":"p4_linux_netplan_link_dir_t"},{"class":"dir","source":"p4_linux_rootdir_t","target":"p4_linux_netplan_rule_dir_t"},{"class":"file","source":"p4_linux_native_data_t","target":"p4_linux_netplan_link_rule_t"}],"derive_native_sysusers_policy.py":[{"class":"dir","source":"p4_linux_etc_dir_t","target":"p4_linux_sysusers_etc_root_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_sysusers_passwd_lock_t"}],"native-console-setup.json":[{"class":"file","source":"p4_linux_native_bin_t","target":"p4_linux_console_helper_native_bin_t"},{"class":"file","source":"p4_linux_native_bin_t","target":"p4_linux_console_vtrgb_native_bin_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_console_cache_exec_native_config_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_console_cache_native_config_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_console_config_native_config_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_console_public_native_config_t"},{"class":"file","source":"p4_linux_native_data_t","target":"p4_linux_console_public_native_data_t"},{"class":"dir","source":"p4_linux_rootdir_t","target":"p4_linux_console_cache_dir_t"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_console_entry_runtime_lib_t"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_console_library_runtime_lib_t"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_console_public_runtime_lib_t"},{"class":"file","source":"p4_linux_native_bin_t","target":"p4_linux_console_interpreter_native_bin_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_console_ld_cache_native_config_t"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_console_locale_runtime_lib_t"}]}
FIXED_FILE_CONTEXTS = r"""

# Fixed working-copy qualification roles, published inputs and output partitions.
/usr/lib/systemd/system/droidloom-working-qualification(-return)?\.service -- u:object_r:p4_linux_working_unit_t:s0
/etc/droidloom/qualification/working-(early|return)\.json -- u:object_r:p4_linux_working_config_t:s0
/var/lib/droidloom/qualification/working-qualification-[0-9a-f]{64} -d u:object_r:p4_linux_working_parent_t:s0
/var/lib/droidloom/qualification/working-qualification-[0-9a-f]{64}/runtime-evidence -d u:object_r:p4_linux_working_evidence_t:s0
/var/lib/droidloom/qualification/working-qualification-[0-9a-f]{64}/runtime-evidence/[A-Za-z0-9_.-]+ -- u:object_r:p4_linux_working_evidence_t:s0
/var/lib/droidloom-qualification -d u:object_r:p4_linux_working_output_root_t:s0
/var/lib/droidloom-qualification/empty-meituan-diagnostic -d u:object_r:p4_linux_empty_meituan_dir_t:s0
/var/lib/droidloom-qualification/empty-meituan-diagnostic/official\.apk -- u:object_r:p4_linux_empty_meituan_apk_t:s0
/var/lib/droidloom-qualification/physical-[0-9a-f]{64} -d u:object_r:p4_linux_working_plan_t:s0
/var/lib/droidloom-qualification/physical-[0-9a-f]{64}/PLAN\.json -- u:object_r:p4_linux_working_plan_t:s0
/var/lib/droidloom-qualification/native-ui-[0-9]+-[0-9]+-[0-9]+ -d u:object_r:p4_linux_working_journal_t:s0
/var/lib/droidloom-qualification/native-ui-[0-9]+-[0-9]+-[0-9]+/[A-Za-z0-9_.-]+ -- u:object_r:p4_linux_working_journal_t:s0
/usr/libexec/droidloom/native-application-leaves(/cohorts(/cp3a-20261126-apps-r2(/.*)?)?)? -d u:object_r:p4_linux_native_leaf_source_t:s0
/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2(/.*)? -- u:object_r:p4_linux_native_leaf_source_t:s0
/usr/libexec/droidloom/native-application-leaves/materials(/apps41)? -d u:object_r:p4_linux_native_leaf_source_t:s0
/usr/libexec/droidloom/native-application-leaves/materials/apps41/(SELECTED41|SIGNATURE-HANDOFF|IMPORT|NORMAL-INPUT-VERIFICATION|APP-RELEASE-GATES)\.json -- u:object_r:p4_linux_native_leaf_source_t:s0
/usr/libexec/droidloom/native\-application\-leaves/prebuilt\-state\-fixtures -d u:object_r:p4_linux_native_leaf_source_t:s0
/usr/libexec/droidloom/native\-application\-leaves/prebuilt\-state\-fixtures/20261128\-r1 -d u:object_r:p4_linux_native_leaf_source_t:s0
/etc/droidloom/native-application-leaves(/(catalogs|current-preimages|releases))? -d u:object_r:p4_linux_native_leaf_layout_t:s0
/etc/droidloom/native-application-leaves/(catalogs|current-preimages|releases)/\.layout -- u:object_r:p4_linux_native_leaf_layout_t:s0
/etc/droidloom/native-application-leaves/(catalogs|current-preimages|releases)/[0-9a-f]{64}\.json -- u:object_r:p4_linux_native_leaf_release_t:s0
/home/alex/work/pocket4-android-final -d u:object_r:p4_linux_working_current_dir_t:s0
/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT\.json -- u:object_r:p4_linux_working_current_t:s0
/home/alex/work/pocket4-android-final/\.working-native-source-[0-9]+-[0-9a-f]{64}\.new -- u:object_r:p4_linux_working_current_t:s0
/home/alex/work/pocket4-android-final/(\.CONTINUATION_CURRENT\.lock|\.qpr1-kernel-control-8b88\.lock) -- u:object_r:p4_linux_working_current_lock_t:s0

"""
PERMANENT_HANDOFF_ACL = r"""
(allow p4_linux_working_qualification_t p4_linux_production_commit_t (process (transition siginh rlimitinh getattr signull signal sigkill)))
(allow p4_linux_production_commit_t p4_linux_working_qualification_t (process (sigchld)))
(auditallow p4_linux_working_qualification_t p4_linux_production_commit_t (process (transition)))
(allow p4_linux_production_commit_t p4_linux_working_config_t (file (getattr open read)))
(allow p4_linux_production_verify_t p4_linux_working_config_t (file (getattr open read)))
(allow p4_linux_working_qualification_t p4_linux_production_config_t (file (getattr open read)))
(allow p4_linux_production_commit_t p4_linux_working_qualification_t (fd (use)))
(allow p4_linux_production_commit_t p4_linux_working_qualification_t (unix_stream_socket (getattr read write getopt setopt shutdown)))
(allow p4_linux_working_qualification_t p4_linux_production_commit_t (dir (getattr search)))
(allow p4_linux_working_qualification_t p4_linux_production_commit_t (file (getattr open read)))
(allow p4_linux_working_qualification_t p4_linux_production_commit_t (lnk_file (getattr read)))
(allow p4_linux_production_commit_t p4_linux_working_qualification_t (dir (getattr search)))
(allow p4_linux_production_commit_t p4_linux_working_qualification_t (file (getattr open read)))
(allow p4_linux_production_commit_t p4_linux_working_qualification_t (lnk_file (getattr read)))
(allow p4_linux_production_commit_t p4_linux_working_plan_t (file (getattr read)))
"""

SOURCE_PINS = {'../../../../packaging/systemd/system/droidloom-physical-qualification@.service': {'bytes': 722,
                                                                                    'sha256': 'e1b8b441af24612cb6124037cc551a69803dfc92ac8e2dbc9f313d08963fac44'},
 '../../../../packaging/systemd/system/droidloom-working-qualification.service': {'bytes': 1170,
                                                                                  'sha256': '7722518edaa13638b917184d225bbf7c8be9139c24a08188aee78cd96fb66dc9'},
 '../../../../runtime/droidloom-applications/src/clock_timer.rs': {'bytes': 73682,
                                                                   'sha256': '0f19c1541c4270bc0caee84a76df8bde013a6ee42391cedeaddfecb847b5057d'},
 '../../../../runtime/droidloom-applications/src/family_collaboration.rs': {'bytes': 50897,
                                                                            'sha256': 'f16b5f19015c770477724e5efe29857ff1665897aa83557a00b4415b52943a68'},
 '../../../../runtime/droidloom-applications/src/family_collaboration_case.rs': {'bytes': 11789,
                                                                                 'sha256': '32d575b199416d4e3716bf166b9f017d70648ddb9352df2afd1b5301565b144d'},
 '../../../../runtime/droidloom-applications/src/family_collaboration_document.rs': {'bytes': 23936,
                                                                                     'sha256': 'a1d73f1f47c8872a809001ff3b93baaa162ad20e382ba446498a3f6ea0ad46e5'},
 '../../../../runtime/droidloom-applications/src/family_housing.rs': {'bytes': 99587,
                                                                      'sha256': '6c8f91946f80b218e40aae45c7733b5977c1c629822420a0b88d20531c840f92'},
 '../../../../runtime/droidloom-applications/src/family_housing_case.rs': {'bytes': 11009,
                                                                           'sha256': '5e410c2be18ac32b21af01328c3f0197e9b69463c56f929d5da9a7b887385bdd'},
 '../../../../runtime/droidloom-applications/src/family_news.rs': {'bytes': 60737,
                                                                   'sha256': '9a7905c403ce2dfefa5b46b77da624def7bbd89b354e609e33d2b2da22d3e730'},
 '../../../../runtime/droidloom-applications/src/family_news_case.rs': {'bytes': 10786,
                                                                        'sha256': 'b2198596ce713058348649f5c335425c86d9dd59bfaffab166b7396c8f3b8338'},
 '../../../../runtime/droidloom-applications/src/family_observation.rs': {'bytes': 31469,
                                                                          'sha256': 'c7841276cf53499b5d8988953870251e98c3d153927ec178c5befd805901a440'},
 '../../../../runtime/droidloom-applications/src/family_travel.rs': {'bytes': 127567,
                                                                     'sha256': '2ac070e5a707c9a8c7729e6b80fcb74a93691d823f8b89da6c303e9ce7ea1ca8'},
 '../../../../runtime/droidloom-applications/src/family_travel_case.rs': {'bytes': 12010,
                                                                          'sha256': 'e6413db07b154393c4c773d556bf764a104b87733d4ddfd6855980339e33c285'},
 '../../../../runtime/droidloom-applications/src/family_travel_sources.rs': {'bytes': 12910,
                                                                             'sha256': '13fb90ac9bdf622e751b444e8641f6a4fcdfb30c4ff5de45e0cc81204567090b'},
 '../../../../runtime/droidloom-applications/src/leaf_release.rs': {'bytes': 37965,
                                                                    'sha256': '73faf73fef47411bd500855600e5aad4372364ac189b4508207fcaff35c7012e'},
 '../../../../runtime/droidloom-applications/src/main.rs': {'bytes': 30219,
                                                            'sha256': 'ebf627df7f820be53d4fdcc070ec0b17a17c30940393f0a64a0b2e3b643acb6e'},
 '../../../../runtime/droidloom-applications/src/physical_acceptance.rs': {'bytes': 92696,
                                                                           'sha256': '27bd974ad0add346b336832d96dd8a668905451b24214b782ea239b1bb8ed481'},
 '../../../../runtime/droidloom-applications/src/runtime_identity_admissions.json': {'bytes': 3058,
                                                                                     'sha256': '21e8bce8a585453176de945adc3b569d2874c8da15c208e34f003eafd5e2c7d4'},
 '../../../../runtime/droidloom-applications/src/working_dispatch.rs': {'bytes': 5632,
                                                                        'sha256': '4e533582a778a7e33ae36719ad730cf2f931de8d0f74043bed16584d31875f93'},
 '../../../../runtime/droidloom-applications/src/working_install.rs': {'bytes': 7065,
                                                                       'sha256': '7e504e63c95240048eded1dacb561b5f3686f0e7a2da832207a71fc852797603'},
 '../../../../runtime/droidloom-early-boot/board_policy.c': {'bytes': 58619,
                                                             'sha256': 'feb5ad943565e5ee8f716c8c86ee3d9bd874d433959636c271100faf207daa43'},
 '../../../../runtime/droidloom-supervisor/src/apk_payload.rs': {'bytes': 19270,
                                                                 'sha256': 'afd57bee123fcc843f649e731cb4a8ce9591e33608784dc4bb8f0a488e2cf61a'},
 '../../../../runtime/droidloom-supervisor/src/application_account_state.rs': {'bytes': 17233,
                                                                               'sha256': '9bc63152929a49ba86512d7c7f1c4b66e82f05b860ff68e1cfff765d0544337c'},
 '../../../../runtime/droidloom-supervisor/src/application_permission_state.rs': {'bytes': 45814,
                                                                                  'sha256': 'cd07717a379271ed12ddf4db46d0255011303b9705b12e5c4e85aa5b5c7c52b5'},
 '../../../../runtime/droidloom-supervisor/src/control.rs': {'bytes': 98089,
                                                             'sha256': '2dc34c9cf3ceccf159f579c9f6863c6abef3ed18c425700b1a854d9b188eaa1c'},
 '../../../../runtime/droidloom-supervisor/src/control_identity_working_install.rs': {'bytes': 6216,
                                                                                      'sha256': 'd4c6f0360bcbcad02b555e1dd9e8420cc5a5b82e504b0871bcde95987c189ea2'},
 '../../../../runtime/droidloom-supervisor/src/native_application_ui_common.rs': {'bytes': 36806,
                                                                                  'sha256': '9b98c89487bc1e0b7ccd90c718f79f4c90a0abd8e2be1fed4159f709e9884b77'},
 '../../../../runtime/droidloom-supervisor/src/native_application_ui_entry.rs': {'bytes': 44283,
                                                                                 'sha256': '643629e96121c25f77d8a55bd72fba2b0a64123fcebb6a1cb6177d7e66876c41'},
 '../../../../runtime/droidloom-supervisor/src/native_application_ui_family.rs': {'bytes': 32318,
                                                                                  'sha256': 'd88aea249fbd5c2d24ae40117b306a5b43f44caeab1a722a426d5fe8778129db'},
 '../../../../runtime/droidloom-supervisor/src/native_application_ui_gateway.rs': {'bytes': 62825,
                                                                                   'sha256': '8a06b7fcace7e28c84989e457d8f39feaf7cb8887e62abfdfb316e498170f909'},
 '../../../../runtime/droidloom-supervisor/src/native_application_ui_permissions.rs': {'bytes': 42411,
                                                                                       'sha256': '8e3ed9ea57497f3a110f46d02de2703245c78c780e5d62fd8895877cbc151b2c'},
 '../../../../runtime/droidloom-supervisor/src/native_application_ui_protocol.rs': {'bytes': 45639,
                                                                                    'sha256': 'd5971a00119bb41f1ab7e37cc2d8401676abd1d1035e54f71ccef05a99de78dd'},
 '../../../../runtime/droidloom-supervisor/src/native_feishu_readonly_contract.rs': {'bytes': 6712,
                                                                                     'sha256': '83c7093557bab3512e6fbd42cce42872cbad5cd35982ac822ca9ad1bf05638ee'},
 '../../../../runtime/droidloom-supervisor/src/native_gms_identity.rs': {'bytes': 16637,
                                                                         'sha256': 'f749e149be7852d3b211483ef90f0f8c213e06e320a9a4f4b93c67408b394294'},
 '../../../../runtime/droidloom-supervisor/src/native_gms_identity_manifest.json': {'bytes': 50103,
                                                                                    'sha256': 'dc2db8a8e380e2a3e569a772c8f8db4bf22abf2617ea60b39103ce341c84b862'},
 '../../../../runtime/droidloom-supervisor/src/native_leaf_apk_protocol.rs': {'bytes': 29451,
                                                                              'sha256': '8d0838110d5d6da7412f77463dab1cc8948ba1ac2f670fb50db12cb87cc2780c'},
 '../../../../runtime/droidloom-supervisor/src/native_leaf_engine.rs': {'bytes': 6754,
                                                                        'sha256': 'ee74aa0f3c00ad1c7a3753b0fdde659df5c8576a523480958b9fc10b1797eeb9'},
 '../../../../runtime/droidloom-supervisor/src/native_source_files.rs': {'bytes': 20552,
                                                                         'sha256': '8a003bc4deaab783669822612f604199edf2cf791d6d0b4aed4998ce8bc1c55e'},
 '../../../../runtime/droidloom-supervisor/src/native_working_contract.rs': {'bytes': 23284,
                                                                             'sha256': '874033cacb571fc1e41289dc8cd03defb0d596075b3718cbd9a691c109f275f4'},
 '../../../../runtime/droidloom-supervisor/src/native_working_install.rs': {'bytes': 17010,
                                                                            'sha256': 'e15a74145983fcf731786f62b2eeb8d5a7978617bbcfa88007514e8464a2717d'},
 '../../../../runtime/droidloom-supervisor/src/physical_qualification_budget.rs': {'bytes': 10872,
                                                                                   'sha256': 'd1edd0ad02a37b41a0737b51a2bdb89b33ab73146006d253698b7cf3cab1bc01'},
 '../../../../runtime/droidloom-supervisor/src/physical_qualification_channel.rs': {'bytes': 35316,
                                                                                    'sha256': '86cce9f071642e7b6402a4438b7c0811ba2bf03b713a67a6246496ab4dc61fd3'},
 '../../../../runtime/droidloom-supervisor/src/physical_qualification_owner.rs': {'bytes': 48270,
                                                                                  'sha256': 'ba10079c91a9153a8cd6979e1739904f6cbcc3617ee3e3311cde0e336e0c1dfb'},
 '../../../../runtime/droidloom-supervisor/src/physical_qualification_resources.rs': {'bytes': 3718,
                                                                                      'sha256': 'c8915999b3c13674f6bee6317a512dc535e21f9b6ed4422dd5c75009b3be71fc'},
 '../../../../runtime/droidloom-supervisor/src/production_application.rs': {'bytes': 36750,
                                                                            'sha256': 'a2c8e8087aa19ef859dc0251eaf7f67fbb6fd287465c1026c7eca2086a1346d2'},
 '../../../../runtime/droidloom-supervisor/src/production_application_query_io.rs': {'bytes': 81504,
                                                                                     'sha256': 'e13c10a14a9e86cc7212f6d9ad74a69d17d45116421461a8911dd6565627539f'},
 '../../../../runtime/droidloom-supervisor/src/production_application_worker.rs': {'bytes': 27850,
                                                                                   'sha256': '284459988af121149f1145b438e438c702ad2f5f83a0ac48f9634004b249288d'},
 '../../../../runtime/droidloom-supervisor/src/production_application_working_install.rs': {'bytes': 2290,
                                                                                            'sha256': 'aa45e938590a445f44f8e93ac1f83fcffcd2496365d43fd9376e830f7c18c83e'},
 '../../../../runtime/droidloom-supervisor/src/production_host_admission.rs': {'bytes': 191923,
                                                                               'sha256': '238897166d3506d16c967824c868d7fc64a0d85c9fe182c241413dcca6c28df5'},
 '../../../../runtime/droidloom-supervisor/src/production_mac_self_attr.rs': {'bytes': 11858,
                                                                              'sha256': '4b09da80158464f3d6c1e07304795c02e0d865f9a435f0a87daabc63ec402adc'},
 '../../../../runtime/droidloom-supervisor/src/production_native_leaf_apk_io.rs': {'bytes': 7399,
                                                                                   'sha256': '799267dd0312ef21e437d935fd56fa58b1f6de22ffaad29207b551ae74419fae'},
 '../../../../runtime/droidloom-supervisor/src/production_working_payload_birth.rs': {'bytes': 25734,
                                                                                      'sha256': '406d20940cee8ca3827993890d00d4cd33a51b3ddc0f6c95fa35d93271c3e209'},
 '../../../../runtime/droidloom-supervisor/src/working_qualification.rs': {'bytes': 22975,
                                                                           'sha256': '1c680e97b64af7182f00bfd9e3f9bd8b0a8f99a273393f61060f03d5de8081e3'},
 '../../../../runtime/droidloom-supervisor/src/working_qualification_preparation_channel.rs': {'bytes': 14549,
                                                                                               'sha256': '2b42c4e0143658f6fa471190a2e4116ae5448d11b683269a24df2eef0928e3fe'},
 '../../../../runtime/droidloom-supervisor/src/working_qualification_witness.rs': {'bytes': 5657,
                                                                                   'sha256': 'd5e07d57d4bff216a736d24902ba4b51112857ff108f87e0a4833a45336c352d'},
 '../../../../tools/droidloom-ubuntu-fixture/src/cold_working_materials.rs': {'bytes': 22894,
                                                                              'sha256': '9418a84a58865319e5b313db4dfc153f6a32d47ff007ca6b80a1bb1dad78a8af'},
 '../../../../tools/droidloom-update/resources/working-preparation/apps41/NORMAL-INPUT-VERIFICATION.json': {'bytes': 129840,
                                                                                                            'sha256': '78a512d9cf3465613b2f4ccd79de656a4280dee37311e8c6958a6136f2bf2513'},
 '../../../../tools/droidloom-update/resources/working-preparation/apps41/SELECTED41.json': {'bytes': 592108,
                                                                                             'sha256': '4abd5c5d0a8ac89e739b2ba6dd508435a1d355b9ce975ba5ceacb50c1ee4a4a0'},
 '../../../../tools/droidloom-update/src/working_preparation_apks.rs': {'bytes': 15340,
                                                                        'sha256': 'c01f3395a5affe189d837483301e5f72c35f237651110ce8fb2dc41885f93294'},
 '../../../../tools/droidloom-update/src/working_preparation_materials.rs': {'bytes': 13778,
                                                                             'sha256': '3b7de07cafe00ad29ff7cf424a8cd47eba80111e1fc84b257f103f08ab77b92c'},
 'apparmor/droidloom-working-application': {'bytes': 15815,
                                            'sha256': '750e770bed5cde89e45d848c158f2e14f2344fa57738dc5d1fed0c756058f067'},
 'apparmor/droidloom-working-privateprep': {'bytes': 27646,
                                            'sha256': 'ed078ca329f8ae86982906c472f94b549e3059d98f515ccea4d7fec265dc7e76'},
 'apparmor/droidloom-working-qualification': {'bytes': 8428,
                                              'sha256': '11ad279abf4dd3aab2f74dc0cf5ddba8e28d769566d850eda9802a237040ffc1'},
 'apparmor/droidloom-working-qualification-return': {'bytes': 3906,
                                                     'sha256': 'f55df8787c44ccfb79243949696ec6ca37c4c3b6afb50546c2da2d3659989e6a'},
 'linux-native-apk.cil': {'bytes': 9697,
                          'sha256': 'c61ba1a38073472cf17812116f96bbe5ddba5bab1e65ce3e675fa57783e6c1a5'},
 'linux-service-file_contexts': {'bytes': 2557,
                                 'sha256': 'cf5afe7e4c668760a54ed6cd06ffec58d42856e1f028f8832fc29b9b9416d814'},
 'native-apk-source.json': {'bytes': 29478,
                            'sha256': 'f53deeb95f054c0c1267137f95e0049ff5c97c2ecad1330c642121d65e5df73b'},
 'pocket4-linux-board.cil': {'bytes': 20393,
                             'sha256': '59fa17d6774e388d530d203d5fa14b55034418c799329641c6a04f3628359969'},
 'ubuntu-systemd-unit-status.cil': {'bytes': 2228,
                                    'sha256': '5d6cbabec2063cf885b42cf796e7eb2e80a19c9eec08c02d48a1626d864d49e5'},
 'ubuntu-working-qualification.cil': {'bytes': 50515,
                                      'sha256': 'a2f1530db9c9c0abba3add6db3d59da651ac11f71548b3f67b572cec9741e1b1'}}
LEVELS = ("s0", "s0:c0", "s0:c1,c512", "s0:c0.c1023")
FLOW_TAGS = frozenset(("allow", "auditallow", "dontaudit", "allowx",
                       "auditallowx", "dontauditx"))
TRANSITION_TAGS = frozenset(("typetransition", "typechange", "typemember", "rangetransition"))
CONTEXT_TAGS = frozenset(("genfscon", "filecon", "portcon", "nodecon", "netifcon",
                         "fsuse", "pirqcon", "iomemcon", "ioportcon", "pcidevicecon",
                         "devicetreecon", "sidcontext"))
MAX_MATRIX_ROWS = 250000


def _forms(text):
    result = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith(";"):
            form = parse_expression(line)
            if not isinstance(form, list) or not form:
                raise ValueError("Malformed working policy export")
            result.append(form)
    return result


def _canonical(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _hash(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


class _Index:
    """Strict concrete expansion for a binary export, including negative sets."""
    def __init__(self, forms):
        self.types = {f[1] for f in forms if f[0] == "type" and len(f) == 2}
        self.attributes = {f[1] for f in forms if f[0] == "typeattribute" and len(f) == 2}
        self.definitions = defaultdict(list)
        self.roles = defaultdict(set)
        self.classes = {}
        common, inherited = {}, {}
        for f in forms:
            if f[0] == "typeattributeset":
                if len(f) != 3:
                    raise ValueError("Malformed working type membership")
                self.definitions[f[1]].append(f[2])
            elif f[0] == "roletype":
                if len(f) != 3 or f[2] not in self.types:
                    raise ValueError("Nonconcrete working role binding")
                self.roles[f[2]].add(f[1])
            elif f[0] in ("common", "class"):
                if len(f) != 3 or not isinstance(f[2], list) or any(
                        not isinstance(n, str) for n in f[2]):
                    raise ValueError("Malformed working class declaration")
                (common if f[0] == "common" else self.classes)[f[1]] = set(f[2])
            elif f[0] == "classcommon":
                if len(f) != 3:
                    raise ValueError("Malformed working common class")
                inherited[f[1]] = f[2]
        for name, base in inherited.items():
            if name not in self.classes or base not in common:
                raise ValueError("Unknown working inherited class")
            self.classes[name].update(common[base])
        self._cache = {}

    def members(self, expression, active=()):
        if isinstance(expression, str):
            if expression in self.types:
                return frozenset((expression,))
            if expression in self._cache:
                return self._cache[expression]
            if expression in active or expression not in self.definitions:
                raise ValueError("Unknown/cyclic working attribute: " + expression)
            result = frozenset().union(*(
                self.members(v, (*active, expression))
                for v in self.definitions[expression]))
            self._cache[expression] = result
            return result
        if not isinstance(expression, list):
            raise ValueError("Invalid working membership")
        if not expression:
            return frozenset()
        op, *args = expression
        if op == "all":
            if args:
                raise ValueError("Invalid working all set")
            return frozenset(self.types)
        if op == "not":
            if len(args) != 1:
                raise ValueError("Invalid working complement")
            return frozenset(self.types) - self.members(args[0], active)
        if op in ("and", "or", "xor"):
            if not args or (op == "xor" and len(args) != 2):
                raise ValueError("Invalid working Boolean set")
            values = [self.members(v, active) for v in args]
            if op == "and":
                return frozenset.intersection(*values)
            if op == "xor":
                return values[0] ^ values[1]
            return frozenset().union(*values)
        return frozenset().union(*(self.members(v, active) for v in expression))

    def expected(self, expression):
        if isinstance(expression, str) and expression in GROUPS:
            return GROUPS[expression]
        # The two pre-existing public attributes retain their old projected
        # membership. They cannot silently acquire any of this component's types.
        if expression in ("p4_linux_native_public_files", "droidloom_package_config_parents"):
            result = self.members(expression)
            if result & OWNED:
                raise ValueError("Working types entered an old public file attribute")
            return result
        if isinstance(expression, str) and expression in self.types:
            return frozenset((expression,))
        raise ValueError("Unreviewed expected working attribute: " + str(expression))


def _contains_owned(value):
    if isinstance(value, list):
        return any(_contains_owned(x) for x in value)
    return value in OWNED


def _xvalues(expr):
    if isinstance(expr, str):
        n = int(expr, 0)
        if not 0 <= n <= 65535:
            raise ValueError("Working ioctl exceeds the selected u16 ABI")
        return {n}
    if not isinstance(expr, list) or not expr:
        raise ValueError("Invalid working ioctl expression")
    if expr[0] == "range":
        if len(expr) != 3:
            raise ValueError("Invalid working ioctl range")
        lo, hi = (int(n, 0) for n in expr[1:])
        if not 0 <= lo <= hi <= 65535:
            raise ValueError("Invalid working ioctl bounds")
        return set(range(lo, hi + 1))
    if expr[0] == "not":
        if len(expr) != 2:
            raise ValueError("Invalid working ioctl complement")
        return set(range(65536)) - _xvalues(expr[1])
    return set().union(*(_xvalues(v) for v in expr))


def _project(forms, index, *, expected=False):
    """All raw authority with any owned endpoint, not just selected positives."""
    resolve = index.expected if expected else index.members
    matrix = defaultdict(set)
    transitions, contexts = set(), set()
    for f in forms:
        tag = f[0]
        if tag in FLOW_TAGS:
            if len(f) != 4 or not isinstance(f[3], list):
                raise ValueError("Unmodeled working raw rule")
            sources = resolve(f[1])
            targets = None if f[2] == "self" else resolve(f[2])
            if not (sources & OWNED) and not (targets is not None and targets & OWNED):
                continue
            if tag.endswith("x"):
                if len(f[3]) != 3 or f[3][0] != "ioctl" or f[3][1] not in index.classes:
                    raise ValueError("Unmodeled working extended permission")
                kind, values = f[3][1], _xvalues(f[3][2])
            else:
                if len(f[3]) != 2 or f[3][0] not in index.classes:
                    raise ValueError("Unknown working permission class")
                kind, names = f[3]
                if not isinstance(names, list) or not set(names) <= index.classes[kind]:
                    raise ValueError("Unknown working permission")
                values = set(names)
            for source in sources:
                for target in ({source} if targets is None else targets):
                    if source in OWNED or target in OWNED:
                        matrix[(tag, source, target, kind)].update(values)
                        if len(matrix) > MAX_MATRIX_ROWS:
                            raise ValueError("Working authority matrix exceeds its bound")
        elif tag in TRANSITION_TAGS:
            if len(f) not in (5, 6):
                raise ValueError("Unmodeled working transition")
            sources, targets = resolve(f[1]), resolve(f[2])
            output = f[-1]
            if sources & OWNED or targets & OWNED or _contains_owned(output):
                if tag != "typetransition" or not isinstance(output, str) or output not in index.types:
                    raise ValueError("Working actor gained an unreviewed transition")
                for source in sources:
                    for target in targets:
                        if source in OWNED or target in OWNED or output in OWNED:
                            transitions.add((tag, source, target, f[3],
                                             f[4] if len(f) == 6 else "", output))
        elif tag in ("typepermissive", "typebounds") and _contains_owned(f):
            raise ValueError("Working authority became permissive or unreviewed bounded")
        elif tag in CONTEXT_TAGS and _contains_owned(f):
            contexts.add(_canonical(f))
        elif tag in ("constrain", "mlsconstrain", "validatetrans", "mlsvalidatetrans"):
            if _contains_owned(f) or any(
                    ("p4_working_" in token)
                    for token in _atoms(f)):
                raise ValueError("Working policy introduced a private constraint exception")
        elif tag not in ("type", "typeattribute", "typeattributeset", "roletype",
                         "class", "common", "classcommon", "expandtypeattribute"):
            # A conditional or another wrapper can contain an owned allow without
            # naming its endpoint at the top level. Reject the whole unmodeled
            # statement; never silently omit its nested authority from the matrix.
            if any(token in OWNED or
                   (token in index.definitions and index.members(token) & OWNED)
                   for token in _atoms(f)):
                raise ValueError("Unmodeled statement contains working authority")
    return {k: frozenset(v) for k, v in matrix.items() if v}, transitions, contexts


def _atoms(value):
    if isinstance(value, list):
        for item in value:
            yield from _atoms(item)
    else:
        yield value


def _validate_membership(index):
    if len(OWNED) != 27 or not OWNED <= index.types:
        raise ValueError("The fixed 27-type working authority is incomplete")
    for group, expected in GROUPS.items():
        if (group in DERIVATION_ONLY_GROUPS and
                group not in index.attributes and group not in index.definitions and
                group not in index.types):
            continue
        if index.members(group) != expected:
            raise ValueError("Working closed membership differs: " + group)
    if index.members("p4_linux_procs") & OWNED != HOSTS:
        raise ValueError("Working Linux process membership differs")
    if index.members("p4_linux_data") & OWNED != DATA:
        raise ValueError("Working Linux object membership differs")
    if index.members("p4_handle_owner") & OWNED != HOSTS:
        raise ValueError("Working namespace handle ownership differs")
    # This source-only boundary can be omitted by the normal link after its
    # neverallows are checked. A retained group must contain exactly the old
    # hosts/objects and the new empty-payload role, never the r-role label child.
    board = "p4_all_board_owned"
    if (board in index.attributes or board in index.definitions or board in index.types):
        if index.members(board) & OWNED != HOSTS | DATA | EMPTY_DATA | {BIRTH}:
            raise ValueError("Working board-owned boundary differs")
    for group in ("domain", "coredomain", "mlstrustedsubject", "mlstrustedobject",
                  "netdomain", "p4_linux_native_processes", "p4_linux_mac_roles"):
        if index.members(group) & OWNED:
            raise ValueError("Working authority inherited a forbidden group: " + group)
    for name in OWNED:
        # The normal binary binds object_r to every concrete type, including
        # process types. Its process-role membership remains independently fixed.
        expected = {"object_r"}
        if name in SUBJECTS:
            expected.add("r" if name == LABELER else "system_r")
        if index.roles[name] != expected:
            raise ValueError("Working type has an unreviewed role: " + name)


def _fixed_aliases(here):
    from verify_original_once import fixed_native_aliases
    from derive_native_remount_policy import ALIASES as remount
    from derive_native_logind_state_policy import ALIASES as logind
    from derive_native_netplan_policy import ALIASES as netplan
    from derive_native_sysusers_policy import ALIASES as sysusers
    from derive_observed_client_policy import ALIASES as observed_client
    current = {
        "derive_native_remount_policy.py": remount,
        "derive_native_logind_state_policy.py": logind,
        "derive_native_netplan_policy.py": netplan,
        "derive_native_sysusers_policy.py": sysusers,
        "native-console-setup.json": json.loads(
            (here / "native-console-setup.json").read_text())["aliases"],
    }
    if current != EXTRA_ALIAS_PROVIDERS:
        raise ValueError("Working fixed normal alias providers changed")
    rows = [*fixed_native_aliases(), *(r for group in current.values() for r in group)]
    if rows != FIXED_ALIASES or len(rows) != 64:
        raise ValueError("Working fixed normal alias roster differs")
    keys = {(r["target"], r["class"]) for r in rows}
    if len(keys) != len(rows) or any((r["source"], r["class"]) in keys for r in rows):
        raise ValueError("Working aliases are repeated, cyclic or chained")
    if observed_client != [{"source": "droidloom_public_control_client_exec",
                            "target": "p4_linux_observed_client_exec_t", "class": kind}
                           for kind in ("file", "dir")]:
        raise ValueError("Working public-client object alias differs")
    return [*rows, *observed_client]


def _expectation(index, aliases):
    matrix, transitions, contexts = _project(
        _forms(FIXED_ACL + INHERITED_ACL + NATIVE_APK_CLIENT_ACL + PAYLOAD_BIRTH_ACL + EMPTY_ACL + PERMANENT_HANDOFF_ACL),
        index, expected=True)
    matrix = defaultdict(set, {k: set(v) for k, v in matrix.items()})
    base = {k: frozenset(v) for k, v in matrix.items()}
    for row in aliases:
        for subject in SUBJECTS:
            values = base.get(("allow", subject, row["source"], row["class"]), ())
            matrix[("allow", subject, row["target"], row["class"])].update(values)
    # The original normal console producer gives actual dynamic-loader clients
    # this one immutable loader cache. Its independent source/type is fixed above.
    for subject in HOSTS | {BIRTH}:
        matrix[("allow", subject, "p4_linux_console_ld_cache_native_config_t", "file")].update(
            ("getattr", "open", "read", "map"))
    return {k: frozenset(v) for k, v in matrix.items() if v}, transitions, contexts


def _compare(actual, wanted):
    for label, observed, expected in zip(("raw authority", "transitions", "contexts"), actual, wanted):
        if observed != expected:
            if isinstance(observed, dict):
                changed = [list(k) for k in sorted(set(observed) | set(expected))
                           if observed.get(k, frozenset()) != expected.get(k, frozenset())]
            else:
                changed = sorted(observed ^ expected)
            raise ValueError("Working " + label + " differs: " + repr(changed[:12]))



# The one new edge between pre-existing types is independently fixed here.
# Do not copy a candidate's observed permissions into the expected table.
UNIT_READER_PAIR = ("p4_linux_user_manager_t", "p4_linux_production_unit_file_t")
UNIT_READER_ACL = "(allow p4_linux_user_manager_t p4_linux_production_unit_file_t (file (getattr open read)))"
UNIT_FILE_CONTEXTS = (
    r"/etc/systemd/system/droidloom-production\.service -- u:object_r:p4_linux_production_unit_file_t:s0",
    r"/usr/lib/systemd/user/droidloom-production-desktop\.service -- u:object_r:p4_linux_production_unit_file_t:s0",
)


def _unit_file_contexts(text):
    lines = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line and ":p4_linux_production_unit_file_t:" in line:
            lines.append(line)
    if sorted(lines) != sorted(UNIT_FILE_CONTEXTS):
        raise ValueError("Fixed system/desktop unit file contexts differ")
    return lines


def _unit_reader_projection(forms, index, *, expected=False):
    resolve = index.expected if expected else index.members
    matrix = defaultdict(set)
    wanted_source, wanted_target = UNIT_READER_PAIR

    def inspect(form, nested=False):
        if not isinstance(form, list) or not form:
            return
        tag = form[0]
        if not isinstance(tag, str):
            for child in form:
                if isinstance(child, list):
                    inspect(child, True)
            return
        if tag in FLOW_TAGS or tag in TRANSITION_TAGS:
            if len(form) < 4:
                raise ValueError("Unmodeled fixed unit-reader rule")
            sources = resolve(form[1])
            targets = sources if form[2] == "self" else resolve(form[2])
            if wanted_source not in sources or wanted_target not in targets:
                return
            if nested or tag in TRANSITION_TAGS:
                raise ValueError("Unmodeled fixed unit-reader authority")
            if len(form) != 4 or not isinstance(form[3], list):
                raise ValueError("Unmodeled fixed unit-reader permission")
            if tag.endswith("x"):
                if len(form[3]) != 3 or form[3][0] != "ioctl" or form[3][1] not in index.classes:
                    raise ValueError("Unmodeled fixed unit-reader ioctl")
                kind, values = form[3][1], _xvalues(form[3][2])
            else:
                if len(form[3]) != 2 or form[3][0] not in index.classes:
                    raise ValueError("Unknown fixed unit-reader class")
                kind, names = form[3]
                if not isinstance(names, list) or not set(names) <= index.classes[kind]:
                    raise ValueError("Unknown fixed unit-reader permission")
                values = set(names)
            matrix[(tag, wanted_source, wanted_target, kind)].update(values)
        else:
            for child in form[1:]:
                if isinstance(child, list):
                    inspect(child, True)

    for form in forms:
        inspect(form)
    return {key: frozenset(value) for key, value in matrix.items() if value}


def source_inputs(here):
    return [here / name for name in SOURCE_PINS]


APK_SELECTION = "../../../../tools/droidloom-update/resources/working-preparation/apps41/SELECTED41.json"
APK_SELECTION_SHA256 = "4abd5c5d0a8ac89e739b2ba6dd508435a1d355b9ce975ba5ceacb50c1ee4a4a0"
APK_ROOT = "/var/lib/droidloom-public-apks/" + APK_SELECTION_SHA256


def _apk_paths(here):
    # This is the independently fixed original-publisher source, never a list
    # learned from a linked policy, installed directory, or runtime receipt.
    raw = (here / APK_SELECTION).read_bytes()
    if len(raw) != 592108 or hashlib.sha256(raw).hexdigest() != APK_SELECTION_SHA256:
        raise ValueError("Fixed original APK source selection changed")
    source = json.loads(raw)
    rows = source["applications"]
    apks = [item for row in rows for item in row["material_files"]]
    hashes = {item["sha256"] for item in apks}
    if (len(rows) != 41 or len(apks) != 67 or len(hashes) != 67
            or sum(item["bytes"] for item in apks) != 5192131867
            or any(len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
                   for value in hashes)):
        raise ValueError("Fixed original APK source roster differs")
    return tuple(APK_ROOT + "/" + value + ".apk" for value in sorted(hashes))


def _apk_file_contexts(here):
    return [APK_ROOT + " -d u:object_r:p4_linux_working_apk_dir_t:s0", *(
        path.replace(".apk", r"\.apk") + " -- u:object_r:p4_linux_working_apk_input_t:s0"
        for path in _apk_paths(here))]


def _apk_apparmor(here, profiles):
    expected = ["/var/lib/droidloom-public-apks/ r,", APK_ROOT + "/ r,",
                *(path + " r," for path in _apk_paths(here))]
    for profile, body in profiles.items():
        actual = [line.split("#", 1)[0].strip() for line in body.splitlines()
                  if "/var/lib/droidloom-public-apks" in line.split("#", 1)[0]]
        wanted = expected if profile == "droidloom-working-privateprep" else []
        if sorted(actual) != sorted(wanted):
            raise ValueError("Working original APK AppArmor paths differ: " + profile)
    if set(profiles) != {"droidloom-working-qualification", "droidloom-working-privateprep",
                         "droidloom-working-application", "droidloom-working-qualification-return"}:
        raise ValueError("Working original APK profile roster differs")



def _current_apparmor(profiles):
    # These existing CURRENT paths are independent of the linked policy. Only
    # the parent performs the fixed-directory O_RDONLY open and fsync for CAS.
    root = "/home/alex/work/pocket4-android-final/"
    read_current = root + "CONTINUATION_CURRENT.json r,"
    ancestors = "/home/{,alex/,alex/work/,alex/work/pocket4-android-final/} r,"
    expected = {
        "droidloom-working-qualification": [
            ancestors, read_current,
            root + " rw,",
            root + "{.CONTINUATION_CURRENT.lock,.qpr1-kernel-control-8b88.lock} rk,",
            root + "{CONTINUATION_CURRENT.json,.working-native-source-[0-9]*-[0-9a-f]*.new} rwk,",
        ],
        "droidloom-working-privateprep": [ancestors, read_current],
        "droidloom-working-application": [ancestors, read_current],
        "droidloom-working-qualification-return": [],
    }
    if set(profiles) != set(expected):
        raise ValueError("Working CURRENT AppArmor profile roster differs")
    for name, body in profiles.items():
        actual = [line.split("#", 1)[0].strip() for line in body.splitlines()
                  if "pocket4-android-final" in line.split("#", 1)[0]]
        if sorted(actual) != sorted(expected[name]):
            raise ValueError("Working CURRENT AppArmor paths differ: " + name)


def verify_sources(here):
    result = {}
    for name, pin in SOURCE_PINS.items():
        body = (here / name).read_bytes()
        actual = {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        if actual != pin:
            raise ValueError("Changed working authority source: " + name)
        result[name] = actual
    lines = []
    for name in ("ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts"):
        for raw in (here / name).read_text().splitlines():
            line = raw.split("#", 1)[0].strip()
            if line and any(":" + label + ":" in line for label in OWNED):
                lines.append(line)
    expected = [line for line in FIXED_FILE_CONTEXTS.splitlines()
                if line and not line.startswith("#")]
    expected.extend(_apk_file_contexts(here))
    if sorted(lines) != sorted(expected):
        raise ValueError("Working published path/type roster differs")
    profiles = {name: (here / "apparmor" / name).read_text() for name in (
        "droidloom-working-qualification", "droidloom-working-privateprep",
        "droidloom-working-application", "droidloom-working-qualification-return")}
    _apk_apparmor(here, profiles)
    _current_apparmor(profiles)
    _unit_file_contexts((here / "linux-service-file_contexts").read_text())
    return result


def verify(library, binary, exported, here):
    sources = verify_sources(here)
    text = exported.read_text()
    forms = _forms(text)
    index = _Index(forms)
    _validate_membership(index)
    aliases = _fixed_aliases(here)
    expected = _expectation(index, aliases)
    actual = _project(forms, index)
    _compare(actual, expected)
    unit_expected = _unit_reader_projection(_forms(UNIT_READER_ACL), index, expected=True)
    unit_actual = _unit_reader_projection(forms, index)
    if unit_actual != unit_expected:
        raise ValueError("Fixed user-manager production-unit raw authority differs")
    policy = Policy(library, binary)
    sids, classes, checks = {}, {}, []
    def context(name, level="s0"):
        roles = index.roles[name]
        role = "system_r" if name in HOSTS else "r" if "r" in roles else "system_r" if "system_r" in roles else "object_r"
        return f"u:{role}:{name}:{level}"
    def sid(value):
        if value not in sids:
            number = ctypes.c_uint32()
            raw = value.encode()
            if policy.lib.sepol_context_to_sid(raw, len(raw) + 1, ctypes.byref(number)):
                raise ValueError("Invalid working linked context: " + value)
            sids[value] = number.value
        return sids[value]
    def vector(subject, target, kind):
        if kind not in classes:
            names = sorted(index.classes[kind])
            classes[kind] = policy.permissions(kind, names)
        number, bits = classes[kind]
        mask = sum(bits.values())
        result = Decision()
        if policy.lib.sepol_compute_av(sid(subject), sid(target), number, mask, ctypes.byref(result)):
            raise ValueError("Cannot query working linked authority")
        return frozenset(n for n, bit in bits.items() if result.allowed & bit)
    def exact(subject, target, kind, wanted):
        observed = vector(subject, target, kind)
        if observed != frozenset(wanted):
            raise ValueError(f"Working constrained authority differs: {subject} -> {target} {kind}: {sorted(observed)} != {sorted(wanted)}")
        checks.append([subject, target, kind, sorted(observed)])
    # Complete s0 vectors for every allowed row. Raw closure above also proves
    # every missing row has no permission, independently of MLS constraints.
    for (tag, subject, target, kind), permissions in sorted(expected[0].items()):
        if tag == "allow":
            exact(context(subject), context(target), kind, permissions)
    for (tag, subject, target, kind), permissions in sorted(unit_expected.items()):
        exact(context(subject), context(target), kind, permissions)
    for subject in SUBJECTS:
        own = context(subject)
        for kind in ("capability", "capability2", "cap_userns", "cap2_userns"):
            exact(own, own, kind, expected[0].get(("allow", subject, subject, kind), ()))
        for kind in ("binder", "security"):
            exact(own, context("kernel"), kind, ())
        # Actual actor ranges cannot silently read Android private bodies at
        # another MCS. Metadata getattr remains distinct from body/execute.
        for level in LEVELS:
            target = context("app_data_file", level)
            for kind in ("file", "dir"):
                permitted = expected[0].get(("allow", subject, "app_data_file", kind), ())
                exact(own, target, kind, permitted)
    # The old normal query birth already owns kernel:self setcurrent. Verify
    # that actual existing bit and the sole new destination without adding it.
    if "setcurrent" not in vector(context("kernel"), context("kernel"), "process"):
        raise ValueError("Existing normal PID 1 setcurrent is absent")
    exact(context("kernel"), context(LABELER), "process", ("dyntransition", "getattr", "sigkill"))
    for level in LEVELS[1:]:
        for target in ("device", "p4_linux_working_watchdog_t"):
            observed = vector(context(LABELER), context(target, level), "chr_file")
            if observed & {"relabelfrom", "relabelto"}:
                raise ValueError("Working label child can relabel another MLS range")
            checks.append([context(LABELER), context(target, level), "chr_file", sorted(observed)])
    raw_rows = [[*key, sorted(value)] for key, value in sorted(actual[0].items())]
    return {
        "schema": "droidloom.working-qualification-policy-readback.v1",
        "concrete_types": len(OWNED), "host_roles": len(HOSTS),
        "private_birth_roles": 2, "normal_aliases": len(aliases),
        "raw_authority_rows": len(raw_rows),
        "raw_authority_sha256": _hash(raw_rows),
        "transitions": len(actual[1]), "context_bindings": len(actual[2]),
        "constrained_vectors": len(checks), "constrained_sha256": _hash(checks),
        "fixed_unit_reader_rows": len(unit_actual), "fixed_unit_file_contexts": len(UNIT_FILE_CONTEXTS),
        "watchdog_ioctl_u16_space": 65536, "watchdog_ioctl": 0x5705,
        "source_files": sources, "runtime_qualified": False,
    }
