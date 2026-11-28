"""Permanent closed boundary for the normal one-shot running engine observer.

The expected table is source owned. Fixed alias providers mechanically preserve
only their declared source/class vectors; no final binary row becomes expected.
Original actor authority is independently retained by the normal compiler's
unchanged original-projection commitments before this verifier is called.
"""
import hashlib
import importlib
import json
import re
from pathlib import Path

from derive_native_uevent_policy import ContextPolicy, Membership, LEVELS
from derive_preserved_alias_policy import _classes, _roles, _context
from derive_shared_payload_cgroup_policy import parse_expression

ROLE = "droidloom_engine_observer"
BROKER = "droidloom_broker"
NS = "p4_kernel_ns_handle_t"
ENTRY = "droidloom_container_entry_exec_t"
CACHE = "p4_linux_console_ld_cache_native_config_t"
SCHEMA = "droidloom.native-engine-observer-proof.v2"
SOURCE_SCHEMA = "droidloom.native-engine-observer-source.v3"
CONTRACT = "native-engine-observer-source.json"
SELECTED_COUNT = 41
SELECTED_DOCUMENTS = {'selection': 'tools/droidloom-update/resources/working-preparation/apps41/SELECTED41.json',
 'signature_receipt': 'tools/droidloom-update/resources/working-preparation/apps41/SIGNATURE-HANDOFF.json'}
ENGINE = "/system/system_ext/lib64/libberberis_arm64.so"
APP_TYPES = ["gmscore_app","platform_app","platform_app_36","priv_app","priv_app_36","system_app","untrusted_app","untrusted_app_25","untrusted_app_27","untrusted_app_29","untrusted_app_30","untrusted_app_32","untrusted_app_34"]
FAMILIES = ["derive_native_kmod_static_policy","derive_native_tmpfiles_policy","derive_native_journal_catalog_policy","derive_native_update_done_policy","derive_native_random_seed_policy","derive_native_timesync_policy","derive_native_ldconfig_policy","derive_native_console_policy","derive_native_remount_policy","derive_native_logind_state_policy","derive_native_netplan_policy","derive_native_sysusers_policy","derive_observed_client_policy"]
ALIASES = [{"source":"p4_linux_rootdir_t","target":"p4_linux_kmod_tmpfiles_dir_t","class":"dir"},{"source":"p4_linux_native_data_t","target":"p4_linux_kmod_static_nodes_t","class":"file"},{"source":"p4_linux_setup_exec_t","target":"p4_linux_tmpfiles_exec_t","class":"file"},{"source":"p4_linux_runtime_lib_t","target":"p4_linux_tmpfiles_usr_config_t","class":"file"},{"source":"p4_linux_native_config_t","target":"p4_linux_tmpfiles_etc_config_t","class":"file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_tmpfiles_config_dir_t","class":"dir"},{"source":"p4_linux_rootdir_t","target":"p4_linux_tmpfiles_runtime_dir_t","class":"dir"},{"source":"p4_linux_native_data_t","target":"p4_linux_tmpfiles_nologin_t","class":"file"},{"source":"p4_linux_usrmerge_link_t","target":"p4_linux_tmpfiles_shm_link_t","class":"lnk_file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_journal_catalog_dir_t","class":"dir"},{"source":"p4_linux_native_data_t","target":"p4_linux_journal_catalog_file_t","class":"file"},{"source":"p4_linux_setup_exec_t","target":"p4_linux_update_done_exec_t","class":"file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_update_done_var_dir_t","class":"dir"},{"source":"p4_linux_native_config_t","target":"p4_linux_update_done_etc_file_t","class":"file"},{"source":"p4_linux_native_data_t","target":"p4_linux_update_done_var_file_t","class":"file"},{"source":"p4_linux_setup_exec_t","target":"p4_linux_random_seed_exec_t","class":"file"},{"source":"p4_linux_native_data_t","target":"p4_linux_random_seed_file_t","class":"file"},{"source":"p4_linux_runtime_lib_t","target":"p4_linux_timesyncd_exec_t","class":"file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_timesyncd_run_t","class":"dir"},{"source":"p4_linux_native_data_t","target":"p4_linux_timesyncd_run_t","class":"file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_timesyncd_state_t","class":"dir"},{"source":"p4_linux_native_data_t","target":"p4_linux_timesyncd_state_t","class":"file"},{"source":"p4_linux_native_config_t","target":"p4_linux_timesyncd_config_t","class":"file"},{"source":"p4_linux_native_config_t","target":"p4_linux_timesyncd_nsswitch_t","class":"file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_timesyncd_netif_t","class":"dir"},{"source":"p4_linux_native_data_t","target":"p4_linux_timesyncd_netif_t","class":"file"},{"source":"p4_linux_setup_exec_t","target":"p4_linux_ldconfig_exec_t","class":"file"},{"source":"p4_linux_native_config_t","target":"p4_linux_ldconfig_config_t","class":"file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_ldconfig_config_dir_t","class":"dir"},{"source":"p4_linux_rootdir_t","target":"p4_linux_ldconfig_aux_dir_t","class":"dir"},{"source":"p4_linux_native_data_t","target":"p4_linux_ldconfig_aux_t","class":"file"},{"class":"file","source":"p4_linux_native_bin_t","target":"p4_linux_console_helper_native_bin_t"},{"class":"file","source":"p4_linux_native_bin_t","target":"p4_linux_console_vtrgb_native_bin_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_console_cache_exec_native_config_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_console_cache_native_config_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_console_config_native_config_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_console_public_native_config_t"},{"class":"file","source":"p4_linux_native_data_t","target":"p4_linux_console_public_native_data_t"},{"class":"dir","source":"p4_linux_rootdir_t","target":"p4_linux_console_cache_dir_t"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_console_entry_runtime_lib_t"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_console_library_runtime_lib_t"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_console_public_runtime_lib_t"},{"class":"file","source":"p4_linux_native_bin_t","target":"p4_linux_console_interpreter_native_bin_t"},{"class":"file","source":"p4_linux_native_config_t","target":"p4_linux_console_ld_cache_native_config_t"},{"class":"file","source":"p4_linux_runtime_lib_t","target":"p4_linux_console_locale_runtime_lib_t"},{"source":"p4_linux_runtime_lib_t","target":"p4_linux_remount_exec_t","class":"file"},{"source":"p4_linux_native_bin_t","target":"p4_linux_remount_mount_exec_t","class":"file"},{"source":"p4_linux_native_config_t","target":"p4_linux_remount_fstab_native_config_t","class":"file"},{"source":"device","target":"p4_linux_root_uuid_link_t","class":"lnk_file"},{"source":"device","target":"p4_linux_root_block_t","class":"blk_file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_systemd_state_parent_t","class":"dir"},{"source":"p4_linux_native_bin_t","target":"p4_linux_netplan_exec_t","class":"file"},{"source":"p4_linux_runtime_lib_t","target":"p4_linux_netplan_library_t","class":"file"},{"source":"p4_linux_runtime_lib_t","target":"p4_linux_netplan_yaml_t","class":"file"},{"source":"p4_linux_rootdir_t","target":"p4_linux_netplan_input_dir_t","class":"dir"},{"source":"p4_linux_network_manager_run_t","target":"p4_linux_netplan_output_t","class":"file"},{"source":"p4_linux_native_config_t","target":"p4_linux_netplan_private_config_t","class":"file"},{"source":"p4_linux_network_manager_run_t","target":"p4_linux_netplan_profiles_dir_t","class":"dir"},{"source":"p4_linux_rootdir_t","target":"p4_linux_netplan_link_dir_t","class":"dir"},{"source":"p4_linux_rootdir_t","target":"p4_linux_netplan_rule_dir_t","class":"dir"},{"source":"p4_linux_native_data_t","target":"p4_linux_netplan_link_rule_t","class":"file"},{"source":"p4_linux_etc_dir_t","target":"p4_linux_sysusers_etc_root_t","class":"dir"},{"source":"p4_linux_native_config_t","target":"p4_linux_sysusers_passwd_lock_t","class":"file"},{"source":"droidloom_public_control_client_exec","target":"p4_linux_observed_client_exec_t","class":"file"},{"source":"droidloom_public_control_client_exec","target":"p4_linux_observed_client_exec_t","class":"dir"}]
SOURCE_DOCUMENTS = [{"admission":"selected-kernel-source","bytes":212133,"kind":"kernel","package":"linux","path":"security/selinux/hooks.c","sha256":"4fa2a20bff2788fffc1f6bc95d49af3e1145e6a679f69ff5aa2d5a1bd85272a0","version":"6.18.64-p4ctx6181-fusectl-aafs-peer-r1"},{"admission":"selected-kernel-source","bytes":44689,"kind":"kernel","package":"linux","path":"security/commoncap.c","sha256":"29b61388bc205bdf27d83d323fb770be514c5e6743bebe4ce6ab0d9fc8549788","version":"6.18.64-p4ctx6181-fusectl-aafs-peer-r1"},{"admission":"selected-kernel-source","bytes":41482,"kind":"kernel","package":"linux","path":"kernel/ptrace.c","sha256":"312d2cb4946694b907e7ee7cdd4020be3ff16ab3db9d64235d843fbce5dd12be","version":"6.18.64-p4ctx6181-fusectl-aafs-peer-r1"},{"admission":"selected-kernel-source","bytes":98852,"kind":"kernel","package":"linux","path":"fs/proc/base.c","sha256":"df7f8ac0998775fe6a3c6062ac8eaf666b0a17a1a17b3cc5bc8c49f1eb06b631","version":"6.18.64-p4ctx6181-fusectl-aafs-peer-r1"},{"admission":"selected-kernel-source","bytes":86881,"kind":"kernel","package":"linux","path":"fs/proc/task_mmu.c","sha256":"a2be94149acaacfc85bbdae0a5ed6d8d3de57044bd5881435a5b1d1ce14b5532","version":"6.18.64-p4ctx6181-fusectl-aafs-peer-r1"},{"admission":"selected-kernel-source","bytes":14991,"kind":"kernel","package":"linux","path":"fs/nsfs.c","sha256":"fb1366d38c672d0fdfa0925fb6f89a5f25c31e3bc3b84e5b558643c46174829f","version":"6.18.64-p4ctx6181-fusectl-aafs-peer-r1"},{"admission":"selected-kernel-source","bytes":29306,"kind":"kernel","package":"linux","path":"fs/pidfs.c","sha256":"e94f42e40118fb76c6e1f318bc51c988b84e1ba2fbabca96fd39a21bca387a09","version":"6.18.64-p4ctx6181-fusectl-aafs-peer-r1"},{"admission":"selected-kernel-source","bytes":36834,"kind":"kernel","package":"linux","path":"kernel/user_namespace.c","sha256":"921c4be164146fce51cce1382b18ba84a9d38c765679e4ca0d00e25df865bdf1","version":"6.18.64-p4ctx6181-fusectl-aafs-peer-r1"},{"admission":"selected-kernel-source","bytes":41015,"kind":"kernel","package":"linux","path":"fs/open.c","sha256":"a56d47d20ade4758344f21458c2e7bc5ff4fc3b0dccd064f3a96b070c2d8a6f6","version":"6.18.64-p4ctx6181-fusectl-aafs-peer-r1"},{"admission":"selected-kernel-source","bytes":26177,"kind":"kernel","package":"linux","path":"fs/seq_file.c","sha256":"5f72519c4a5e36d869c554b685bbdbb575da36e191bba09eade2a330c8a0e51e","version":"6.18.64-p4ctx6181-fusectl-aafs-peer-r1"},{"admission":"selected-kernel-source","bytes":11700,"kind":"kernel","package":"linux","path":"fs/d_path.c","sha256":"bf0f8ce9a7c42b51842ef91516b866ba00e4a30a2afdcbc67fef4281ea1c8c45","version":"6.18.64-p4ctx6181-fusectl-aafs-peer-r1"},{"admission":"selected-kernel-source","bytes":96491,"kind":"kernel","package":"linux","path":"security/selinux/ss/services.c","sha256":"a3dc132fceec9f42a8d1728cef1b45685d5d2e0f3b5dcb812bec4049c5c19f67","version":"6.18.64-p4ctx6181-fusectl-aafs-peer-r1"},{"admission":"selected-kernel-source","bytes":23118,"kind":"kernel","package":"linux","path":"fs/proc/array.c","sha256":"d7f9b0b88d5ea4bf2016b5f354cb4dc20ab273a1e218e72b7421446546b32846","version":"6.18.64-p4ctx6181-fusectl-aafs-peer-r1"},{"admission":"selected-kernel-source","bytes":9897,"kind":"kernel","package":"linux","path":"fs/statfs.c","sha256":"b211b13c420f2f07a0a06bc03b919ddd2cc6a44478d2490717ff4d3a3c7a5cbc","version":"6.18.64-p4ctx6181-fusectl-aafs-peer-r1"},{"admission":"selected-kernel-source","bytes":27519,"kind":"kernel","package":"linux","path":"fs/stat.c","sha256":"920cd3cdb2d6f167939dd79a86732a66a8ea7eb2954c31bdd4d1fa0796f89a17","version":"6.18.64-p4ctx6181-fusectl-aafs-peer-r1"},{"admission":"normal-signed-apt-quilt-source","bytes":1505,"kind":"glibc","package":"glibc","path":"sysdeps/unix/sysv/linux/fstatvfs64.c","sha256":"d351c94dbf52fa5c1ae0d54cfe7c6a56391ff61b93c35b0878159d8ce758fcd2","version":"2.43-2ubuntu2.7"},{"admission":"normal-signed-apt-quilt-source","bytes":4295,"kind":"glibc","package":"glibc","path":"sysdeps/unix/sysv/linux/internal_statvfs.c","sha256":"0af31f50f9b5c9a3aa32a72fcdc67ec8548f4dc6596e2dbf02518baa9b8a53e2","version":"2.43-2ubuntu2.7"},{"admission":"normal-signed-apt-quilt-source","bytes":1471,"kind":"glibc","package":"glibc","path":"sysdeps/unix/sysv/linux/fstatfs64.c","sha256":"e465783ec0e48f5663bb52e2b3f3bfa3bcb6c119b3be0e472857ba6ae3d3d815","version":"2.43-2ubuntu2.7"},{"admission":"normal-signed-apt-quilt-source","bytes":1006,"kind":"glibc","package":"glibc","path":"sysdeps/unix/sysv/linux/kernel_stat.h","sha256":"7063dbc01ca9039b3d773756a92a4b8f3b2948a4b9b472bf1da53960609fe8d3","version":"2.43-2ubuntu2.7"}]
FIXED_PUBLIC_INPUTS = {'selection': {'bytes': 592108, 'sha256': '4abd5c5d0a8ac89e739b2ba6dd508435a1d355b9ce975ba5ceacb50c1ee4a4a0'},
 'metadata_proof': {'bytes': 17382,
                    'sha256': '23aa9c83b561f1571598a58c75f5e3bbb99e38444a5c282d54b61e6434ac4972'},
 'conditional_rule_proof': {'bytes': 7847,
                            'sha256': '77f366c77eb1ee4fd2596f4cfd6c4568676f0f68e1faf249485e3ef8b7711a96'},
 'selected_system': {'bytes': 2294853632,
                     'sha256': 'dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4'},
 'platform': {'bytes': 5030, 'sha256': 'eb24be4624f15413dc51b49635087feff8c49aa7a1870d67488da36bd2364641'},
 'system_ext': {'bytes': 0, 'sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'},
 'product': {'bytes': 0, 'sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'},
 'signature_receipt': {'bytes': 309985,
                       'sha256': '1d44a6f5cb247de704bd64a0973226612672619545ecd328e4536bdda0236731'}}
ORIGINAL_CONSTRAINTS = {"commitment":{"forms":95,"sha256":"4fc553f9fc7bcf206adbcc7d2b92f9ef2697797a7db54e02306e5fd102f6050f"},"baseline_export":{"bytes":13329512,"sha256":"bde03fda4d120725bead55ed6d7627ae160b5c2ade445edf320bf90b435a1c4e"},"baseline_binary":{"bytes":1468180,"sha256":"fdb26ceb9f8cb7f235f9d7a5ed7d063632fcb4e6d31af32abc842e17d0a4d0e8"}}

NATIVE_RUNTIME_INPUTS = {"selected_system":{"bytes":2294853632,"sha256":"dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4"},"app_process64":{"path":"/system/bin/app_process64","bytes":51616,"sha256":"bcc150b9c7e2abcc9aef312ea04f5bbcba631dbb2e23cb1b240b7219df1229a2","mode":33261,"uid":0,"gid":2000,"label":"u:object_r:zygote_exec:s0","elf_class":64,"elf_machine":62},"art":{"name":"com.android.art","version":371899999,"container_file":"com.android.art.capex","container_bytes":20357120,"container_sha256":"5d0e18b7e2ff241989323c1d0d1695c97921ba85b617ba12e5aa69775b7bd5c0","original_apex_bytes":49065984,"original_apex_sha256":"5ace9ff8a8ab73aa64b63901fe18782028d5c61c452a35b8ad07fb0b711247d0","payload_bytes":48865280,"payload_sha256":"8dd4693cf110e6d69fdd34868c337cd94e4251151466b799d95762c7bf150bb4","filesystem":"ext4","member":"/lib64/libart.so","bytes":14884360,"sha256":"38849876d2101a7bac548d3438e3effff01e38f13f3b5740a2364b762fc229d3","mode":33188,"uid":1000,"gid":1000,"label":"u:object_r:system_lib_file:s0","open_path":"/apex/com.android.art/lib64/libart.so","mapping_paths":["/apex/com.android.art/lib64/libart.so","/apex/com.android.art@371899999/lib64/libart.so"],"elf_class":64,"elf_machine":62},"normal_apex_profile":{"bytes":22836,"sha256":"f3ab57e31c73ea963bd6cf4bed81779f49ebb052c68207582c75039b6fdc039f","count":38},"exact_elf_readback":{"path":"/home/qq/work/p4-application-engine-r14-4b91-r1/native-source-r1/RESULT.json","bytes":14198,"sha256":"775ef50059da0d35aed9c1827a4f7991b07cab144af5b7ed54ad5bf4521779f4"},"metadata_limit":"Independent app_process64 debugfs stat failed with EAGAIN; executable metadata comes from the already admitted fixed normal query-input profile, not that failed stat.","selected_abi_source":{"path":"/home/qq/work/p4-runtime-abi-selected-source-4b91-r3/SELECTED-SOURCE-PROOF-r1.json","bytes":58109,"sha256":"3f4df283943bc340ca93e56d02daf1870d750117d1f8cccf12ea396cf679c092"},"selected_abi_grammar":{"path":"/home/qq/work/p4-runtime-abi-query-4b91-r1/GRAMMAR-SOURCE-READBACK-r1.json","bytes":23689,"sha256":"490bc4e02258749d88e3096d96056cd8cd67e9d5e11425f054d74d58ea494f3d"},"framework_jar":{"bytes":49754098,"sha256":"bc8a175a95dcb50b5ae62a03a0ec2ba0fdea34169f83b2aab3c8bf2790707587"},"services_jar":{"bytes":25716529,"sha256":"bc5d11f4f09ec079c5804a01008e8317a0854231502550acaff89aa9f1083a86"}}

GIT_SOURCES = ['runtime/droidloom-supervisor/src/engine_custody.rs',
 'runtime/droidloom-supervisor/src/application_probe.rs',
 'runtime/droidloom-supervisor/src/production_engine_observer.rs',
 'runtime/droidloom-supervisor/src/production_mounts_engine_custody.rs',
 'runtime/droidloom-supervisor/src/production_early_engine_custody.rs',
 'runtime/droidloom-supervisor/src/production_application_engine.rs',
 'runtime/droidloom-supervisor/src/production_mounts.rs',
 'runtime/droidloom-supervisor/src/production_mounts_persistent_fixture.rs',
 'runtime/droidloom-supervisor/src/production_application_query_io.rs',
 'runtime/droidloom-supervisor/src/production_application_protocol.rs',
 'runtime/droidloom-supervisor/src/production_application.rs',
 'runtime/droidloom-supervisor/src/production_application_vintf.rs',
 'runtime/droidloom-supervisor/src/production_early_application.rs',
 'runtime/droidloom-supervisor/src/production_early_application_control.rs',
 'runtime/droidloom-supervisor/src/control.rs',
 'runtime/droidloom-supervisor/src/control_identity.rs',
 'runtime/droidloom-supervisor/src/control_progress.rs',
 'runtime/droidloom-supervisor/src/lib.rs',
 'runtime/droidloom-supervisor/src/main.rs',
 'runtime/droidloom-supervisor/src/bin/droidloomd.rs',
 'runtime/droidloom-supervisor/src/production_host_admission.rs',
 'runtime/droidloom-supervisor/src/production_mounts_custody.rs',
 'runtime/droidloom-supervisor/src/production_mounts_system_ext.rs',
 'runtime/droidloom-supervisor/src/production_native_engine_profile.rs',
 'runtime/droidloom-supervisor/src/runtime_abi.rs',
 'runtime/droidloom-supervisor/src/production_application_runtime_abi.rs',
 'runtime/droidloom-supervisor/src/production_application_operation.rs',
 'runtime/droidloom-supervisor/src/production_execution_profile.rs',
 'runtime/droidloom-supervisor/src/production_query_input_profile.rs',
 'runtime/droidloom-supervisor/src/production_apex_input_profile.rs',
 'runtime/droidloom-supervisor/src/production_apex_input_profile.json',
 'runtime/droidloom-supervisor/src/production_application_art_profile.rs',
 'runtime/droidloom-supervisor/src/production_mac.rs',
 'runtime/droidloom-supervisor/src/production_mac_observer_proc.rs',
 'runtime/droidloom-supervisor/src/production_mac_host_proc.rs',
 'runtime/droidloom-supervisor/src/production_mac_self_attr.rs']
# Fixed vectors before normal alias preservation. All absent class/target cells
# are zero, including private application bodies, every socket creation,
# capabilities in the initial USERNS, process mutation and execution paths.
READ = {"getattr", "open", "read"}
BASE = {
    (ENTRY, "file"): READ | {"map", "execute", "entrypoint"},
    ("p4_linux_elf_interpreter_t", "file"): READ | {"map", "execute"},
    ("p4_linux_runtime_lib_t", "file"): READ | {"map", "execute"},
    (CACHE, "file"): READ | {"map"},
    ("p4_linux_rootdir_t", "dir"): {"getattr", "search"},
    ("p4_linux_etc_dir_t", "dir"): {"getattr", "search"},
    ("p4_linux_usrmerge_link_t", "lnk_file"): {"getattr", "read"},
    ("p4_linux_timezone_link_t", "lnk_file"): {"getattr", "read"},
    (BROKER, "process"): {"getattr", "sigchld"},
    (BROKER, "fd"): {"use"},
    ("kernel", "fd"): {"use"},
    (BROKER, "file"): READ,
    (BROKER, "lnk_file"): {"getattr", "read"},
    (BROKER, "fifo_file"): {"getattr", "read"},
    (BROKER, "unix_stream_socket"): {"getattr", "getopt", "read", "write"},
    (ROLE, "cap_userns"): {"sys_admin", "sys_ptrace"},
    (ROLE, "process"): {"getcap", "setcap"},
    ("proc", "dir"): {"getattr", "search"},
    ("proc", "lnk_file"): {"getattr", "read"},
    (ROLE, "dir"): {"getattr", "search"},
    (ROLE, "file"): READ,
    (ROLE, "lnk_file"): {"getattr", "read"},
    ("rootfs", "dir"): READ | {"search"},
    ("system_file", "dir"): {"getattr", "search"},
    ("system_lib_file", "dir"): {"getattr", "search"},
    ("zygote_exec", "file"): READ,
    ("apex_mnt_dir", "dir"): {"search"},
    ("labeledfs", "filesystem"): {"getattr"},
    ("system_lib_file", "file"): READ,
    (NS, "file"): READ | {"ioctl"},
    (NS, "filesystem"): {"getattr"},
    ("p4_kernel_pid_handle_t", "file"): {"getattr"},
    ("proc", "filesystem"): {"getattr"},
}
for _target in APP_TYPES:
    BASE[(_target, "process")] = {"getattr"}
    BASE[(_target, "dir")] = READ | {"search"}
    BASE[(_target, "file")] = READ
    BASE[(_target, "lnk_file")] = {"getattr", "read"}
INCOMING = {
    (BROKER, "process"): {"transition", "getattr", "sigkill"},
    (BROKER, "process2"): {"nnp_transition", "nosuid_transition"},
}
CONSTRAINT_OPERATIONS = ("(constrain ", "(mlsconstrain ", "(validatetrans ", "(mlsvalidatetrans ")
TRANSITION_OPERATIONS = ("typetransition", "typechange", "typemember", "roletransition", "rangetransition")
EXPECTED_XPERMS = {(ROLE, NS, "ioctl", "file"): {0xb701, 0xb703}}
PROHIBITED_MEMBERSHIPS = (
    "domain", "coredomain", "p4_linux_procs", "p4_linux_data",
    "p4_linux_native_processes", "p4_fixed_metadata_tasks",
    "p4_native_selinux_query_clients", "p4_closed_runtime_queries",
)
SHAPE = {
    "actor": ROLE,
    "context": "u:r:" + ROLE + ":s0",
    "roletype": "r",
    "app_types": APP_TYPES,
    "app_types_are_conditional_candidates_only": True,
    "fixed_engine_path": ENGINE,
    "executable_witness": "proc/exe O_PATH plus native-only fixed source app_process64 full bytes",
    "runtime_routes": ["berberis_arm64", "native_x86_64"],
    "native_art_paths": NATIVE_RUNTIME_INPUTS["art"]["mapping_paths"],
    "native_files_full_sha256_reads": True,
    "native_files_readonly_ext4": True,
    "native_actual_executable_and_art_vmas_required": True,
    "native_apex_loop_owner_borrowed": False,
    "apex_vintf_avb_qualification_is_separate": True,
    "ams_pid_is_process_selector": False,
    "initial_namespace_capabilities": [],
    "borrowed_user_namespace_capabilities": ["sys_admin", "sys_ptrace"],
    "post_setns_capabilities": ["sys_ptrace"],
    "namespace_ioctl_commands": [0xb701, 0xb703],
    "parent": BROKER,
    "normal_broker_engine_body_access": False,
    "engine_request_full_apk_reads": 0,
    "engine_request_pm_metadata_commands": 4,
    "engine_request_ams_metadata_commands": 2,
    "ams_command": ["/system/bin/cmd", "activity", "dump", "processes", "<fixed41package>"],
    "ams_role": "droidloom_launch_read",
    "ams_record_join": "same actual PIDFD/NSpid/UID/name/epoch and two equal records including startSeq",
    "client_full_apk_binding": "borrowed ActualApplicationObservation from the normal inspector",
    "wire_caller_uid_or_apk_authority": False,
    "operation_work_seconds": 48,
    "retirement_reserve_seconds": 12,
    "client_cap_seconds": 70,
    "caller_absolute_deadline_preserved": True,
    "native_engine_inferred_from_missing_mapping": False,
    "unchanged_original_mls_constraints": True,
    "caller_selected_pid_path_label_engine_digest": False,
    "returned_descriptors": 0,
    "child_survival_permitted": False,
    "translation_business_qualified": False,
    "runtime_qualified": False,
}

def pin(path):
    body = path.read_bytes()
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}

def source_inputs(here):
    return [here / CONTRACT, *(here.parents[3] / path for path in GIT_SOURCES),
            *(here.parents[3] / path for path in SELECTED_DOCUMENTS.values())]

def aliases(here):
    result = []
    for name in FAMILIES:
        module = importlib.import_module(name)
        rows = module.contract(here)["aliases"] if name == "derive_native_console_policy" else module.ALIASES
        result.extend(rows)
    if result != ALIASES or len({(x["target"], x["class"]) for x in result}) != len(result):
        raise ValueError("Engine fixed normal alias provider interface changed")
    return result

def expected(here, types):
    result = {key: set(value) for key, value in BASE.items()}
    if not {ROLE, *APP_TYPES, *(target for target, _ in result)} <= types:
        raise ValueError("An engine source-owned type is absent")
    for row in aliases(here):
        if row["source"] not in types or row["target"] not in types:
            raise ValueError("A required normal engine alias is absent")
        source, target = (row["source"], row["class"]), (row["target"], row["class"])
        # This is the same source OR preimage composition used by the normal
        # producer. Explicit cache access remains its separately fixed vector.
        if source in result:
            result.setdefault(target, set()).update(result[source])
    return result


def _json_contents(value):
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _metadata_summary(selection, signatures, input_pins):
    """Join only pinned static declarations; this creates no live identity."""
    applications = selection.get("applications", [])
    receipts = signatures.get("rows", [])
    if (selection.get("schema") != "p4-selected41-static-launch-inputs-v1"
            or signatures.get("schema") != "p4-selected41-materials-and-original-signers-handoff-v1"
            or selection.get("package_count") != SELECTED_COUNT
            or len(applications) != SELECTED_COUNT or len(receipts) != SELECTED_COUNT):
        raise ValueError("Engine selected source document schema or count differs")
    names = [row["package"] for row in applications]
    signed = {row["package"]: row for row in receipts}
    if len(set(names)) != SELECTED_COUNT or len(signed) != SELECTED_COUNT or set(names) != set(signed):
        raise ValueError("Engine selected/signature package roster differs")
    rows = []
    for index, app in enumerate(sorted(applications, key=lambda row: row["package"])):
        receipt = signed[app["package"]]
        # Stock system APKs retain legacy targets while their minimum SDK
        # tracks the selected platform. These are independent declarations.
        if (app["role"] not in {"system", "third_party"}
                or any(type(app[key]) is not int or app[key] < 1
                       for key in ("min_sdk", "target_sdk", "version_code"))):
            raise ValueError("Engine static manifest declaration differs")
        if (any(app[key] != receipt[key] for key in
                ("role", "version_code", "version_name", "signer_certificates_sha256"))
                or receipt.get("all_file_signatures_and_hashes_verified") is not True):
            raise ValueError("Engine selected declaration and signature receipt differ")
        signers = app["signer_certificates_sha256"]
        if (not signers or len(set(signers)) != len(signers)
                or any(re.fullmatch("[0-9a-f]{64}", value) is None for value in signers)):
            raise ValueError("Engine static signer declaration differs")
        materials = sorted((row["bytes"], row["sha256"]) for row in app["material_files"])
        if (not materials or materials != sorted((row["bytes"], row["sha256"]) for row in receipt["files"])
                or any(type(size) is not int or size < 1
                       or re.fullmatch("[0-9a-f]{64}", digest) is None for size, digest in materials)):
            raise ValueError("Engine selected material and signature source bytes differ")
        rows.append({
            "index": index, "package": app["package"], "role": app["role"],
            "min_sdk": app["min_sdk"], "target_sdk": app["target_sdk"],
            "signer_certificates_sha256": signers, "version_code": app["version_code"],
            "material_count": len(materials),
            "actual_package_inspection": None, "runtime_accepted": False,
        })
    return {
        "schema": "droidloom.engine-selected41-static-metadata.v1",
        "sources": {key: {"path": relative, **input_pins[key]}
                    for key, relative in SELECTED_DOCUMENTS.items()},
        "selection_role_counts": {role: sum(row["role"] == role for row in rows)
                                  for role in ("system", "third_party")},
        "target_sdk_counts": {str(sdk): sum(row["target_sdk"] == sdk for row in rows)
                              for sdk in sorted({row["target_sdk"] for row in rows})},
        "material_count": sum(row["material_count"] for row in rows),
        "role_is_selection_classification_not_live_packagemanager_flag": True,
        "sdk_values_are_static_manifest_declarations": True,
        "actual_seapp_label_observed": False, "actual_engine_mapping_observed": False,
        "runtime_qualified": False, "rows": rows,
    }


def _conditional_summary(metadata, seapp):
    """Apply only the explicit ordinary-app scenario to the original rules."""
    rules = []
    allowed_fields = {"user", "domain", "type", "levelFrom", "minTargetSdkVersion"}
    for line in seapp["platform_contents"].splitlines():
        if not line or line.startswith("#"):
            continue
        entries = [word.split("=", 1) for word in line.split()]
        if any(len(entry) != 2 for entry in entries):
            raise ValueError("Engine original seapp syntax differs")
        fields = dict(entries)
        if fields.get("domain", "").startswith("untrusted_app"):
            if (len(fields) != len(entries) or not set(fields) <= allowed_fields
                    or fields.get("user") != "_app" or fields.get("type") != "app_data_file"
                    or fields.get("levelFrom") not in {"user", "all"}
                    or fields["domain"] not in APP_TYPES):
                raise ValueError("Engine ordinary seapp selector fields differ")
            minimum = int(fields.get("minTargetSdkVersion", "0"))
            if minimum < 0:
                raise ValueError("Engine ordinary seapp target SDK threshold differs")
            rules.append({"minimum_target_sdk": minimum, "domain": fields["domain"],
                          "level_from": fields["levelFrom"], "source_line": line})
    rules.sort(key=lambda row: row["minimum_target_sdk"], reverse=True)
    thresholds = [row["minimum_target_sdk"] for row in rules]
    if (not rules or thresholds[-1] != 0 or len(set(thresholds)) != len(thresholds)
            or {row["domain"] for row in rules} != {value for value in APP_TYPES if value.startswith("untrusted_app")}):
        raise ValueError("Engine original ordinary seapp rule roster differs")
    candidates = []
    for row in metadata["rows"]:
        if row["role"] == "third_party":
            rule = next(value for value in rules if row["target_sdk"] >= value["minimum_target_sdk"])
            candidates.append({"package": row["package"], "target_sdk": row["target_sdk"],
                               "conditional_domain": rule["domain"], "level_from": rule["level_from"]})
    return {
        "schema": "droidloom.engine-selected41-conditional-seapp-scope.v1",
        "selected_system": seapp["selected_system"], "platform": seapp["platform"],
        "system_ext": seapp["system_ext"], "product": seapp["product"],
        "conditional_process_type_candidates": APP_TYPES,
        "ordinary_app_conditions": {
            "user": "_app", "seinfo": "default", "isPrivApp": False,
            "isEphemeralApp": False, "fromRunAs": False,
        },
        "ordinary_source_rules": rules, "ordinary_default_candidate_rows": candidates,
        "selection_role_does_not_prove_conditions": True,
        "runtime_uid_seinfo_privilege_and_label_required": True,
        "actual_seapp_label_observed": False, "vendor_rule_inference": False,
        "process_type_set_extended": False, "runtime_qualified": False,
    }


def _verify_selected_documents(here, selected, seapp):
    documents = {}
    for key, relative in SELECTED_DOCUMENTS.items():
        source = here.parents[3] / relative
        if source.is_symlink() or not source.is_file() or pin(source) != FIXED_PUBLIC_INPUTS[key]:
            raise ValueError("Engine normal selected source document differs: " + key)
        documents[key] = json.loads(source.read_bytes())
    metadata = _metadata_summary(documents["selection"], documents["signature_receipt"], FIXED_PUBLIC_INPUTS)
    conditional = _conditional_summary(metadata, seapp)
    for key, value in (("metadata", metadata), ("conditional_rule", conditional)):
        contents = _json_contents(value)
        body = contents.encode()
        if (selected[key + "_contents"] != contents
                or {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()} != FIXED_PUBLIC_INPUTS[key + "_proof"]):
            raise ValueError("Engine static source proof differs: " + key)
    if [row["package"] for row in metadata["rows"]] != selected["packages"]:
        raise ValueError("Engine actual normal source roster and request selector differ")


def source_contract(here):
    path = here / CONTRACT
    body = path.read_bytes()
    data = json.loads(body)
    required = {"schema", "boundary", "git_sources", "component",
                "selected_public_inputs", "selected_seapp", "source_documents",
                "constraints", "apparmor_normal_admission_required", "native_runtime_inputs"}
    if set(data) != required or data["schema"] != SOURCE_SCHEMA or data["boundary"] != SHAPE:
        raise ValueError("Engine fixed source contract shape or semantics changed")
    if set(data["git_sources"]) != set(GIT_SOURCES):
        raise ValueError("Engine causal Git source roster changed")
    for relative, wanted in data["git_sources"].items():
        if pin(here.parents[3] / relative) != wanted:
            raise ValueError("Engine causal source bytes changed: " + relative)
    if pin(here / "linux-fixed-engine-observer.cil") != data["component"]:
        raise ValueError("Engine fixed component bytes changed")
    rust = (here.parents[3] / GIT_SOURCES[0]).read_text()
    fields = re.search(r"const APP_TYPES:.*?= &\[(.*?)\];", rust, re.S)
    if fields is None or re.findall(r'"([a-z0-9_]+)"', fields[1]) != APP_TYPES:
        raise ValueError("Rust and policy conditional process-label sets differ")
    names = re.search(r"const SELECTED_PACKAGES:.*?= &\[(.*?)\];", rust, re.S)
    selected = data["selected_public_inputs"]
    if (set(selected) != {"selection", "signature_receipt", "packages", "metadata_proof", "conditional_rule_proof", "metadata_contents", "conditional_rule_contents"}
            or not isinstance(selected["packages"], list)
            or len(selected["packages"]) != SELECTED_COUNT
            or names is None
            or re.findall(r'"([^"]+)"', names[1]) != sorted(selected["packages"])
            or len(set(selected["packages"])) != SELECTED_COUNT):
        raise ValueError("Engine fixed41 request roster changed")
    for key in ("selection", "signature_receipt", "metadata_proof", "conditional_rule_proof"):
        if selected[key] != FIXED_PUBLIC_INPUTS[key]:
            raise ValueError("Engine selected public input commitment changed: " + key)
    metadata_body = selected["metadata_contents"].encode()
    if {"bytes": len(metadata_body), "sha256": hashlib.sha256(metadata_body).hexdigest()} != FIXED_PUBLIC_INPUTS["metadata_proof"]:
        raise ValueError("Engine fixed41 source metadata bytes changed")
    metadata = json.loads(metadata_body)
    if (len(metadata["rows"]) != SELECTED_COUNT
            or sorted(row["package"] for row in metadata["rows"]) != selected["packages"]
            or any(row["actual_package_inspection"] is not None or row["runtime_accepted"] is not False
                   for row in metadata["rows"])
            or metadata["actual_seapp_label_observed"] is not False):
        raise ValueError("Static manifest/signature metadata was promoted to runtime identity")
    seapp = data["selected_seapp"]
    if (set(seapp) != {"selected_system", "platform", "system_ext", "product", "platform_contents",
                      "conditional_candidates", "runtime_label_observed", "vendor_rule_inference"}
            or seapp["conditional_candidates"] != APP_TYPES
            or seapp["runtime_label_observed"] is not False
            or seapp["vendor_rule_inference"] is not False
            or len(seapp["platform_contents"].encode()) != seapp["platform"]["bytes"]
            or hashlib.sha256(seapp["platform_contents"].encode()).hexdigest()
                != seapp["platform"]["sha256"]):
        raise ValueError("Engine selected seapp source comparison changed")
    if any(seapp[key] != FIXED_PUBLIC_INPUTS[key]
           for key in ("selected_system", "platform", "system_ext", "product")):
        raise ValueError("Engine actual selected-system rule inputs changed")
    _verify_selected_documents(here, selected, seapp)
    native = data["native_runtime_inputs"]
    if native != NATIVE_RUNTIME_INPUTS:
        raise ValueError("Native selected ELF/ART/AMS source inputs changed")
    abi = (here.parents[3] / "runtime/droidloom-supervisor/src/runtime_abi.rs").read_text()
    abi_names = re.search(r"const PACKAGES:.*?= \[(.*?)\];", abi, re.S)
    if abi_names is None or re.findall(r'"([^"]+)"', abi_names[1]) != selected["packages"]:
        raise ValueError("AMS and Engine fixed41 selectors differ")
    profile_path = here.parents[3] / "runtime/droidloom-supervisor/src/production_apex_input_profile.json"
    profile_pin = native["normal_apex_profile"]
    if pin(profile_path) != {key: profile_pin[key] for key in ("bytes", "sha256")}:
        raise ValueError("Native original APEX profile changed")
    profile = json.loads(profile_path.read_bytes())
    if (profile["source_system_bytes"] != native["selected_system"]["bytes"]
            or profile["source_system_sha256"] != native["selected_system"]["sha256"]
            or len(profile["apexes"]) != profile_pin["count"]):
        raise ValueError("Native source profile is not the exact selected system")
    art = [row for row in profile["apexes"] if row["input"]["name"] == "com.android.art"]
    if len(art) != 1 or art[0]["filesystem"] != "ext4":
        raise ValueError("Native ART fixed role or filesystem differs")
    for key in ("name", "version", "container_file", "container_bytes", "container_sha256",
                "original_apex_bytes", "original_apex_sha256", "payload_bytes", "payload_sha256"):
        if art[0]["input"][key] != native["art"][key]:
            raise ValueError("Native ART exact source lineage changed: " + key)
    if data["source_documents"] != SOURCE_DOCUMENTS or data["constraints"] != ORIGINAL_CONSTRAINTS:
        raise ValueError("Engine selected kernel/libc sources or original constraint commitment changed")
    if not data["source_documents"] or data["apparmor_normal_admission_required"] != {
        "profile": "board-policy/apparmor/droidloom-production-broker",
        "maps_rule": "@{PROC}/[0-9]*/maps r,",
        "engine_rule": "/{system,run/droidloom-early-slot/rootfs/system,.droidloom-kernel-apparmorfs/system}/system_ext/lib64/libberberis_arm64.so r,",
        "native_executable_rule": "/{system,run/droidloom-early-slot/rootfs/system,.droidloom-kernel-apparmorfs/system}/bin/app_process64 r,",
        "native_art_rule": "/{apex,run/droidloom-early-slot/rootfs/apex,.droidloom-kernel-apparmorfs/apex}/com.android.art{,@371899999}/lib64/libart.so r,",
        "normal_182_rebuild_required": True,
        "separate_old_archive_reuse_allowed": False,
    }:
        raise ValueError("Engine normal source or independent AppArmor admission is absent")
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), "contents": data}

def _concrete(membership, name):
    if name == "self":
        raise ValueError("Engine self must be correlated with its concrete source")
    if name in membership.types:
        return {name}
    return {x for x in membership.types if membership.member(name, x)}

def raw_tables(text, wanted):
    lines = text.splitlines()
    if re.search(r"\((?:booleanif|tunableif)\b", text):
        raise ValueError("Engine boundary requires unconditional raw authority")
    members = Membership(text)
    classes = _classes(text)
    if ROLE not in members.types or not all(len(v) == len(set(v)) and len(v) <= 32 for v in classes.values()):
        raise ValueError("Engine concrete type or complete class vocabulary differs")
    role_rows = {(role, actor) for role, actor in _roles(lines) if actor == ROLE}
    if role_rows != {("r", ROLE)}:
        raise ValueError("Engine actor has an unreviewed role")
    for attribute in PROHIBITED_MEMBERSHIPS:
        if attribute in members.attributes and members.member(attribute, ROLE):
            raise ValueError("Engine inherited a broad execution/data attribute: " + attribute)
    for attribute in ("p4_all_board_owned", "mlstrustedsubject"):
        if not members.member(attribute, ROLE):
            raise ValueError("Engine lost its fixed board or MLS separation")
    if _concrete(members, "p4_fixed_engine_app_types") != set(APP_TYPES):
        raise ValueError("Engine target process-label attribute changed")
    actual_out, actual_in = {}, {}
    count = 0
    for line in lines:
        if not line.startswith("(allow "):
            continue
        count += 1
        form = parse_expression(line)
        if len(form) != 4 or not isinstance(form[3], list) or len(form[3]) != 2:
            raise ValueError("Unmodeled engine raw statement")
        source, target, (cls, names) = form[1:]
        if cls not in classes or not isinstance(names, list) or not set(names) <= set(classes[cls]):
            raise ValueError("Unmodeled engine class/permission")
        if members.member(source, ROLE):
            targets = {ROLE} if target == "self" else _concrete(members, target)
            for name in targets:
                actual_out.setdefault((name, cls), set()).update(names)
        if target == "self":
            sources = {ROLE} if members.member(source, ROLE) else set()
        else:
            sources = _concrete(members, source) if members.member(target, ROLE) else set()
        for name in sources:
            actual_in.setdefault((name, cls), set()).update(names)
    if count != text.count("(allow "):
        raise ValueError("Engine whole raw authority is incomplete")
    want_in = {key: set(value) for key, value in INCOMING.items()}
    for (target, cls), names in wanted.items():
        if target == ROLE:
            want_in[(ROLE, cls)] = set(names)
    for title, actual, desired in (("outbound", actual_out, wanted), ("inbound", actual_in, want_in)):
        if actual != desired:
            diff = [{"target_or_source": t, "class": c, "actual": sorted(actual.get((t,c), set())),
                     "expected": sorted(desired.get((t,c), set()))}
                    for t,c in sorted(actual.keys() | desired.keys())
                    if actual.get((t,c), set()) != desired.get((t,c), set())]
            raise ValueError("Engine whole " + title + " raw boundary differs: " + json.dumps(diff))
    return members, classes, want_in, count

def _numbers(value):
    if not isinstance(value, list) or not value:
        raise ValueError("Engine extended-command shape")
    if len(value) == 3 and value[0] == "range":
        first, last = int(value[1], 0), int(value[2], 0)
        if not 0 <= first <= last <= 65535:
            raise ValueError("Engine extended-command range")
        return set(range(first, last + 1))
    result = set()
    for item in value:
        if isinstance(item, list):
            result.update(_numbers(item))
        elif isinstance(item, str):
            number = int(item, 0)
            if not 0 <= number <= 65535:
                raise ValueError("Engine extended-command value")
            result.add(number)
        else:
            raise ValueError("Engine extended-command value type")
    return result

def extended_boundary(text, members, classes):
    actual = {}
    counts = {"allowx": 0, "auditallow": 0, "dontaudit": 0, "auditallowx": 0, "dontauditx": 0}
    for line in text.splitlines():
        if not any(line.startswith("(" + op + " ") for op in counts):
            continue
        form = parse_expression(line)
        op = form[0]
        counts[op] += 1
        if len(form) != 4:
            raise ValueError("Unmodeled engine audit/extended statement")
        source, target = form[1:3]
        outgoing = members.member(source, ROLE)
        incoming = outgoing if target == "self" else members.member(target, ROLE)
        if not outgoing and not incoming:
            continue
        if op != "allowx":
            raise ValueError("Engine acquired unreviewed audit masking or audit authorization")
        if not isinstance(form[3], list) or len(form[3]) != 3:
            raise ValueError("Unmodeled engine allowx")
        kind, cls, values = form[3]
        if kind not in ("ioctl", "nlmsg") or cls not in classes:
            raise ValueError("Unknown engine extended class or operation")
        commands = _numbers(values)
        sources = _concrete(members, source)
        for s in sources:
            targets = {s} if target == "self" else _concrete(members, target)
            for t in targets:
                if ROLE in (s, t):
                    actual.setdefault((s,t,kind,cls), set()).update(commands)
    for op, count in counts.items():
        if count != text.count("(" + op + " "):
            raise ValueError("Engine extended/audit closure is incomplete")
    if actual != EXPECTED_XPERMS:
        raise ValueError("Engine complete ioctl/nlmsg boundary differs")
    return counts

def _constraint_commitment(text):
    forms = sorted(line for line in text.splitlines() if line.startswith(CONSTRAINT_OPERATIONS))
    return {"forms": len(forms),
            "sha256": hashlib.sha256(("\n".join(forms) + "\n").encode()).hexdigest()}

def _no_transitions(text, members):
    count = 0
    for line in text.splitlines():
        if not any(line.startswith("(" + op + " ") for op in TRANSITION_OPERATIONS):
            continue
        form = parse_expression(line)
        count += 1
        # No computed transition, type change/member or range may select or
        # originate in this actor. Its only entry is the fixed pending context
        # set by the already-held broker, with the original MLS check.
        names = []
        def walk(x):
            if isinstance(x, str):
                names.append(x)
            elif isinstance(x, list):
                for item in x:
                    walk(item)
        walk(form[1:])
        for name in names:
            if name in members.types | members.attributes and members.member(name, ROLE):
                raise ValueError("Engine gained an implicit type/role/range transition")
    return count

def verify_native_engine_observer(library, binary, exported, here):
    source = source_contract(here)
    text = exported.read_text()
    if "(fsuse xattr ext4 (u object_r labeledfs ((s0) (s0))))" not in text.splitlines():
        raise ValueError("Native readonly ext4 filesystem uses an unreviewed SID")
    preliminary = Membership(text)
    wanted = expected(here, preliminary.types)
    members, classes, inbound, raw_rules = raw_tables(text, wanted)
    xcounts = extended_boundary(text, members, classes)
    transition_count = _no_transitions(text, members)
    constraints = _constraint_commitment(text)
    if constraints != source["contents"]["constraints"]["commitment"]:
        raise ValueError("Engine changed the complete original ordinary/MLS/relabel constraints")
    policy = ContextPolicy(library, binary)
    roles = dict((actor, role) for role, actor in _roles(text.splitlines()))
    roles[ROLE] = "r"
    roles[BROKER] = "r"
    for app in APP_TYPES:
        if ("r", app) not in _roles(text.splitlines()):
            raise ValueError("An engine target lacks its actual Android role")
        roles[app] = "r"
    rows = []
    def context(actor, cls, level, source=False):
        role = roles.get(actor, "object_r") if source or cls in (
            "process", "process2", "capability", "capability2", "cap_userns", "cap2_userns") else "object_r"
        return _context(role, actor, level)
    def check(s, t, cls, names, sl, tl, required):
        vocab = classes[cls]
        _, bits = policy.permissions(cls, vocab)
        want = sum(bits[x] for x in names)
        got = policy.context_av(context(s, cls, sl, True), context(t, cls, tl), cls, vocab)
        if got & ~want or (required and got != want):
            raise ValueError("Engine category/class boundary differs: " + repr((s,t,cls,sl,tl,got,want)))
        rows.append([s,t,cls,sl,tl,got])
    for sl in LEVELS:
        for tl in LEVELS:
            # Trusted read-only actor must actually cross the selected category
            # pairs for every fixed App proc witness, not merely have raw allows.
            for (t, cls), names in sorted(wanted.items()):
                required = (sl == tl == "s0") or t in APP_TYPES
                check(ROLE, t, cls, names, sl, tl, required)
            # Complete own-self class complements include every socket,
            # capability, security, IPC and future class with a fixed zero.
            for cls in sorted(classes):
                if (ROLE, cls) not in wanted:
                    check(ROLE, ROLE, cls, set(), sl, tl, True)
            for (s, cls), names in sorted(inbound.items()):
                check(s, ROLE, cls, names, sl, tl, sl == tl == "s0")
            # Initial namespace capability and all private body sentinels are
            # independently queried in addition to the full raw zero matrix.
            for t in ("app_data_file", "privapp_data_file", "system_app_data_file", "appdomain_tmpfs"):
                for cls in ("file", "dir", "lnk_file"):
                    check(ROLE, t, cls, set(), sl, tl, True)
    return {
        "schema": SCHEMA, "source": source,
        "actor": ROLE, "actor_role": "r", "app_types": APP_TYPES,
        "runtime_routes": SHAPE["runtime_routes"],
        "native_runtime_inputs": NATIVE_RUNTIME_INPUTS,
        "native_apex_loop_owner_borrowed": False,
        "concrete_types": len(members.types), "classes": len(classes),
        "raw_rules_checked": raw_rules,
        "whole_raw_outbound_vectors": len(members.types) * len(classes),
        "whole_raw_inbound_vectors": len(members.types) * len(classes),
        "nonzero_outbound_vectors": [[t,c,sorted(v)] for (t,c),v in sorted(wanted.items())],
        "nonzero_inbound_vectors": [[s,c,sorted(v)] for (s,c),v in sorted(inbound.items())],
        "fixed_alias_families": FAMILIES, "fixed_alias_count": len(ALIASES),
        "category_pairs": len(LEVELS) ** 2,
        "effective_vectors_checked": len(rows),
        "matrix_sha256": hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest(),
        "extended_rule_inventory": xcounts,
        "extended_commands": [["ioctl", "file", NS, [0xb701, 0xb703]]],
        "extended_all_concrete_sources_and_targets_scanned": True,
        "extended_all_classes_and_both_operations_scanned": True,
        "extended_command_queries_executed": 0,
        "extended_fixed_authorized_commands": 2,
        "transition_forms_checked": transition_count,
        "new_computed_transitions": 0,
        "constraints": constraints,
        "all_zero_raw_cells_have_no_mls_grant_source": True,
        "zero_raw_cells_individually_queried": False,
        "normal_original_actor_projection_required": True,
        "source_bound_readback_required": True,
        "normal_apparmor_admission_required": True,
        "runtime_qualified": False,
        "translation_business_qualified": False,
    }
