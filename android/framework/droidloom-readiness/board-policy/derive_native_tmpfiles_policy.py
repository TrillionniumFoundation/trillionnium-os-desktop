
"""Verify the source-bound normal tmpfiles consumer and its typed objects.

Normal source and rule readbacks are external admission inputs. This producer
checks complete binary permissions, all category pairs and the unchanged
ordinary/MLS/relabel constraints. It does not execute tmpfiles or label devices.
"""
import ctypes
import hashlib
import importlib
import json
import re
import stat

from derive_native_uevent_policy import ContextPolicy, LEVELS
from derive_native_random_seed_policy import RawPolicy, _bits, _context_role
from derive_preserved_alias_policy import (
    _context, derive_preserved_aliases, verify_preserved_aliases)
from derive_shared_payload_cgroup_policy import parse_expression, format_xperms
from derive_native_update_done_policy import (
    DIRECTORY_RELABEL_GUARD, DIRECTORY_RELABEL_GUARD_SHA256)

ROLE = 'p4_linux_tmpfiles_t'
ENTRY = 'p4_linux_tmpfiles_exec_t'
ALIASES = [{'source': 'p4_linux_setup_exec_t', 'target': 'p4_linux_tmpfiles_exec_t', 'class': 'file'}, {'source': 'p4_linux_runtime_lib_t', 'target': 'p4_linux_tmpfiles_usr_config_t', 'class': 'file'}, {'source': 'p4_linux_native_config_t', 'target': 'p4_linux_tmpfiles_etc_config_t', 'class': 'file'}, {'source': 'p4_linux_rootdir_t', 'target': 'p4_linux_tmpfiles_config_dir_t', 'class': 'dir'}, {'source': 'p4_linux_rootdir_t', 'target': 'p4_linux_tmpfiles_runtime_dir_t', 'class': 'dir'}, {'source': 'p4_linux_native_data_t', 'target': 'p4_linux_tmpfiles_nologin_t', 'class': 'file'}, {'source': 'p4_linux_usrmerge_link_t', 'target': 'p4_linux_tmpfiles_shm_link_t', 'class': 'lnk_file'}]
NEW_TYPES = {'p4_linux_tmpfiles_shm_link_t', 'p4_linux_tmpfiles_config_dir_t', 'p4_linux_tmpfiles_t', 'p4_linux_tmpfiles_static_node_t', 'p4_linux_tmpfiles_static_dir_t', 'p4_linux_tmpfiles_nologin_t', 'p4_linux_tmpfiles_exec_t', 'p4_linux_tmpfiles_etc_config_t', 'p4_linux_tmpfiles_usr_config_t', 'p4_linux_tmpfiles_runtime_dir_t'}
STAGE = 'kmod -> tmpfiles -> catalog -> update-done -> random-seed -> timesync -> ldconfig -> console'
KERNEL_BASENAME_CONFINEMENT = False
NORMAL_IMPLEMENTATION_CHANGED = False
NORMAL_UNIT_SUCCESS_STATUS_CHANGED = False
BASE_ROLE_ROWS = [['device', 'chr_file', ['getattr', 'relabelfrom', 'setattr']], ['device', 'dir', ['getattr', 'relabelfrom', 'search']], ['device', 'filesystem', ['getattr']], ['droidloom_public_apk_dir', 'dir', ['create', 'getattr', 'open', 'read', 'search', 'setattr']], ['droidloom_public_apk_root', 'dir', ['add_name', 'getattr', 'open', 'read', 'search', 'write']], ['droidloom_public_control_dir', 'dir', ['create', 'getattr', 'open', 'read', 'search', 'setattr']], ['init_t', 'process', ['sigchld']], ['labeledfs', 'filesystem', ['getattr']], ['null_device', 'chr_file', ['getattr', 'read', 'write']], ['p4_linux_board_selinux_config_t', 'file', ['getattr', 'open', 'read']], ['p4_linux_console_ld_cache_native_config_t', 'file', ['getattr', 'map', 'open', 'read']], ['p4_linux_elf_interpreter_t', 'file', ['execute', 'getattr', 'map', 'open', 'read']], ['p4_linux_etc_dir_t', 'dir', ['getattr', 'open', 'read', 'search']], ['p4_linux_journal_database_t', 'file', ['getattr', 'setattr']], ['p4_linux_journal_machine_t', 'dir', ['getattr', 'ioctl', 'open', 'read', 'search', 'setattr']], ['p4_linux_journal_store_t', 'dir', ['getattr', 'ioctl', 'open', 'read', 'search', 'setattr']], ['p4_linux_kmod_static_nodes_t', 'file', ['getattr', 'open', 'read']], ['p4_linux_kmod_tmpfiles_dir_t', 'dir', ['getattr', 'open', 'read', 'search']], ['p4_linux_log_root_t', 'dir', ['getattr', 'open', 'read', 'search', 'setattr']], ['p4_linux_logind_run_t', 'dir', ['create', 'getattr', 'open', 'read', 'search', 'setattr']], ['p4_linux_machine_id_t', 'file', ['getattr', 'open', 'read']], ['p4_linux_manager_ask_password_t', 'dir', ['getattr', 'open', 'read', 'search']], ['p4_linux_native_dev_root_t', 'dir', ['add_name', 'getattr', 'search', 'write']], ['p4_linux_public_accounts_t', 'file', ['getattr', 'open', 'read']], ['p4_linux_rootdir_t', 'dir', ['getattr', 'open', 'read', 'search']], ['p4_linux_run_t', 'dir', ['add_name', 'getattr', 'open', 'read', 'search', 'write']], ['p4_linux_runtime_lib_t', 'file', ['execute', 'getattr', 'map', 'open', 'read']], ['p4_linux_service_executor_t', 'fd', ['use']], ['p4_linux_service_executor_t', 'process', ['sigchld']], ['p4_linux_service_executor_t', 'unix_stream_socket', ['getattr', 'read', 'write']], ['p4_linux_setup_credentials_t', 'dir', ['getattr', 'search']], ['p4_linux_sshd_run_t', 'dir', ['create', 'getattr', 'open', 'read', 'search', 'setattr']], ['p4_linux_standardio_t', 'chr_file', ['getattr', 'read', 'write']], ['p4_linux_systemd_run_t', 'dir', ['add_name', 'getattr', 'open', 'read', 'search', 'write']], ['p4_linux_systemd_state_parent_t', 'dir', ['getattr', 'open', 'read', 'search']], ['p4_linux_sysusers_etc_root_t', 'dir', ['getattr', 'open', 'read', 'search']], ['p4_linux_timesyncd_exec_t', 'file', ['execute', 'getattr', 'map', 'open', 'read']], ['p4_linux_timesyncd_netif_t', 'dir', ['add_name', 'create', 'getattr', 'open', 'read', 'search', 'setattr', 'write']], ['p4_linux_timesyncd_nsswitch_t', 'file', ['getattr', 'open', 'read']], ['p4_linux_timesyncd_run_t', 'dir', ['getattr', 'open', 'read', 'search']], ['p4_linux_timesyncd_state_t', 'dir', ['getattr', 'open', 'read', 'search']], ['p4_linux_timezone_link_t', 'lnk_file', ['getattr', 'read']], ['p4_linux_tmp_t', 'dir', ['add_name', 'create', 'getattr', 'open', 'read', 'remove_name', 'rmdir', 'search', 'setattr', 'write']], ['p4_linux_tmp_t', 'fifo_file', ['getattr', 'unlink']], ['p4_linux_tmp_t', 'file', ['getattr', 'unlink']], ['p4_linux_tmp_t', 'lnk_file', ['getattr', 'read', 'unlink']], ['p4_linux_tmp_t', 'sock_file', ['getattr', 'unlink']], ['p4_linux_tmpfiles_config_dir_t', 'dir', ['getattr', 'open', 'read', 'search']], ['p4_linux_tmpfiles_etc_config_t', 'file', ['getattr', 'open', 'read']], ['p4_linux_tmpfiles_exec_t', 'file', ['entrypoint', 'execute', 'getattr', 'map', 'open', 'read']], ['p4_linux_tmpfiles_nologin_t', 'file', ['create', 'getattr', 'open', 'setattr', 'write']], ['p4_linux_tmpfiles_runtime_dir_t', 'dir', ['add_name', 'create', 'getattr', 'open', 'read', 'search', 'setattr', 'write']], ['p4_linux_tmpfiles_shm_link_t', 'lnk_file', ['create', 'getattr', 'read']], ['p4_linux_tmpfiles_static_dir_t', 'dir', ['add_name', 'create', 'getattr', 'open', 'read', 'relabelto', 'search', 'setattr', 'write']], ['p4_linux_tmpfiles_static_node_t', 'chr_file', ['create', 'getattr', 'relabelto', 'setattr']], ['p4_linux_tmpfiles_t', 'capability', ['chown', 'fowner', 'fsetid', 'mknod']], ['p4_linux_tmpfiles_t', 'dir', ['getattr', 'search']], ['p4_linux_tmpfiles_t', 'fd', ['use']], ['p4_linux_tmpfiles_t', 'lnk_file', ['getattr', 'read']], ['p4_linux_tmpfiles_t', 'process', ['getcap', 'setfscreate']], ['p4_linux_tmpfiles_usr_config_t', 'file', ['getattr', 'open', 'read']], ['p4_linux_user_home_t', 'dir', ['getattr', 'search']], ['p4_linux_user_run_t', 'dir', ['create', 'getattr', 'open', 'read', 'search', 'setattr']], ['p4_linux_usrmerge_link_t', 'lnk_file', ['getattr', 'read']], ['p4_linux_var_cache_t', 'dir', ['getattr', 'open', 'read', 'search']], ['p4_linux_var_spool_t', 'dir', ['getattr', 'open', 'read', 'search']], ['p4_linux_volatile_journal_database_t', 'file', ['getattr', 'setattr']], ['p4_linux_volatile_journal_machine_t', 'dir', ['getattr', 'open', 'read', 'search', 'setattr']], ['p4_linux_volatile_journal_store_t', 'dir', ['getattr', 'open', 'read', 'search', 'setattr']], ['p4_linux_volatile_log_root_t', 'dir', ['create', 'getattr', 'open', 'read', 'search', 'setattr']], ['proc', 'dir', ['search']], ['proc', 'filesystem', ['getattr']], ['proc', 'lnk_file', ['read']], ['proc_random', 'dir', ['search']], ['proc_random', 'file', ['getattr', 'open', 'read']], ['selinuxfs', 'dir', ['search']], ['selinuxfs', 'file', ['getattr', 'map', 'open', 'read']], ['selinuxfs', 'filesystem', ['getattr']], ['sysfs', 'dir', ['search']], ['tmpfs', 'filesystem', ['getattr']]]
FIXED_ALIAS_PROVIDERS = {'derive_native_kmod_static_policy': [{'source': 'p4_linux_rootdir_t', 'target': 'p4_linux_kmod_tmpfiles_dir_t', 'class': 'dir'}, {'source': 'p4_linux_native_data_t', 'target': 'p4_linux_kmod_static_nodes_t', 'class': 'file'}], 'derive_native_journal_catalog_policy': [{'source': 'p4_linux_rootdir_t', 'target': 'p4_linux_journal_catalog_dir_t', 'class': 'dir'}, {'source': 'p4_linux_native_data_t', 'target': 'p4_linux_journal_catalog_file_t', 'class': 'file'}], 'derive_native_update_done_policy': [{'source': 'p4_linux_setup_exec_t', 'target': 'p4_linux_update_done_exec_t', 'class': 'file'}, {'source': 'p4_linux_rootdir_t', 'target': 'p4_linux_update_done_var_dir_t', 'class': 'dir'}, {'source': 'p4_linux_native_config_t', 'target': 'p4_linux_update_done_etc_file_t', 'class': 'file'}, {'source': 'p4_linux_native_data_t', 'target': 'p4_linux_update_done_var_file_t', 'class': 'file'}], 'derive_native_random_seed_policy': [{'source': 'p4_linux_setup_exec_t', 'target': 'p4_linux_random_seed_exec_t', 'class': 'file'}, {'source': 'p4_linux_native_data_t', 'target': 'p4_linux_random_seed_file_t', 'class': 'file'}], 'derive_native_timesync_policy': [{'source': 'p4_linux_runtime_lib_t', 'target': 'p4_linux_timesyncd_exec_t', 'class': 'file'}, {'source': 'p4_linux_rootdir_t', 'target': 'p4_linux_timesyncd_run_t', 'class': 'dir'}, {'source': 'p4_linux_native_data_t', 'target': 'p4_linux_timesyncd_run_t', 'class': 'file'}, {'source': 'p4_linux_rootdir_t', 'target': 'p4_linux_timesyncd_state_t', 'class': 'dir'}, {'source': 'p4_linux_native_data_t', 'target': 'p4_linux_timesyncd_state_t', 'class': 'file'}, {'source': 'p4_linux_native_config_t', 'target': 'p4_linux_timesyncd_config_t', 'class': 'file'}, {'source': 'p4_linux_native_config_t', 'target': 'p4_linux_timesyncd_nsswitch_t', 'class': 'file'}, {'source': 'p4_linux_rootdir_t', 'target': 'p4_linux_timesyncd_netif_t', 'class': 'dir'}, {'source': 'p4_linux_native_data_t', 'target': 'p4_linux_timesyncd_netif_t', 'class': 'file'}], 'derive_native_ldconfig_policy': [{'source': 'p4_linux_setup_exec_t', 'target': 'p4_linux_ldconfig_exec_t', 'class': 'file'}, {'source': 'p4_linux_native_config_t', 'target': 'p4_linux_ldconfig_config_t', 'class': 'file'}, {'source': 'p4_linux_rootdir_t', 'target': 'p4_linux_ldconfig_config_dir_t', 'class': 'dir'}, {'source': 'p4_linux_rootdir_t', 'target': 'p4_linux_ldconfig_aux_dir_t', 'class': 'dir'}, {'source': 'p4_linux_native_data_t', 'target': 'p4_linux_ldconfig_aux_t', 'class': 'file'}], 'derive_native_remount_policy': [{'source': 'p4_linux_runtime_lib_t', 'target': 'p4_linux_remount_exec_t', 'class': 'file'}, {'source': 'p4_linux_native_bin_t', 'target': 'p4_linux_remount_mount_exec_t', 'class': 'file'}, {'source': 'p4_linux_native_config_t', 'target': 'p4_linux_remount_fstab_native_config_t', 'class': 'file'}, {'source': 'device', 'target': 'p4_linux_root_uuid_link_t', 'class': 'lnk_file'}, {'source': 'device', 'target': 'p4_linux_root_block_t', 'class': 'blk_file'}], 'derive_native_logind_state_policy': [{'source': 'p4_linux_rootdir_t', 'target': 'p4_linux_systemd_state_parent_t', 'class': 'dir'}], 'derive_native_netplan_policy': [{'source': 'p4_linux_native_bin_t', 'target': 'p4_linux_netplan_exec_t', 'class': 'file'}, {'source': 'p4_linux_runtime_lib_t', 'target': 'p4_linux_netplan_library_t', 'class': 'file'}, {'source': 'p4_linux_runtime_lib_t', 'target': 'p4_linux_netplan_yaml_t', 'class': 'file'}, {'source': 'p4_linux_rootdir_t', 'target': 'p4_linux_netplan_input_dir_t', 'class': 'dir'}, {'source': 'p4_linux_network_manager_run_t', 'target': 'p4_linux_netplan_output_t', 'class': 'file'}, {'source': 'p4_linux_native_config_t', 'target': 'p4_linux_netplan_private_config_t', 'class': 'file'}, {'source': 'p4_linux_network_manager_run_t', 'target': 'p4_linux_netplan_profiles_dir_t', 'class': 'dir'}, {'source': 'p4_linux_rootdir_t', 'target': 'p4_linux_netplan_link_dir_t', 'class': 'dir'}, {'source': 'p4_linux_rootdir_t', 'target': 'p4_linux_netplan_rule_dir_t', 'class': 'dir'}, {'source': 'p4_linux_native_data_t', 'target': 'p4_linux_netplan_link_rule_t', 'class': 'file'}], 'derive_native_sysusers_policy': [{'source': 'p4_linux_etc_dir_t', 'target': 'p4_linux_sysusers_etc_root_t', 'class': 'dir'}, {'source': 'p4_linux_native_config_t', 'target': 'p4_linux_sysusers_passwd_lock_t', 'class': 'file'}], 'derive_native_console_policy': [{'class': 'file', 'source': 'p4_linux_native_bin_t', 'target': 'p4_linux_console_helper_native_bin_t'}, {'class': 'file', 'source': 'p4_linux_native_bin_t', 'target': 'p4_linux_console_vtrgb_native_bin_t'}, {'class': 'file', 'source': 'p4_linux_native_config_t', 'target': 'p4_linux_console_cache_exec_native_config_t'}, {'class': 'file', 'source': 'p4_linux_native_config_t', 'target': 'p4_linux_console_cache_native_config_t'}, {'class': 'file', 'source': 'p4_linux_native_config_t', 'target': 'p4_linux_console_config_native_config_t'}, {'class': 'file', 'source': 'p4_linux_native_config_t', 'target': 'p4_linux_console_public_native_config_t'}, {'class': 'file', 'source': 'p4_linux_native_data_t', 'target': 'p4_linux_console_public_native_data_t'}, {'class': 'dir', 'source': 'p4_linux_rootdir_t', 'target': 'p4_linux_console_cache_dir_t'}, {'class': 'file', 'source': 'p4_linux_runtime_lib_t', 'target': 'p4_linux_console_entry_runtime_lib_t'}, {'class': 'file', 'source': 'p4_linux_runtime_lib_t', 'target': 'p4_linux_console_library_runtime_lib_t'}, {'class': 'file', 'source': 'p4_linux_runtime_lib_t', 'target': 'p4_linux_console_public_runtime_lib_t'}, {'class': 'file', 'source': 'p4_linux_native_bin_t', 'target': 'p4_linux_console_interpreter_native_bin_t'}, {'class': 'file', 'source': 'p4_linux_native_config_t', 'target': 'p4_linux_console_ld_cache_native_config_t'}, {'class': 'file', 'source': 'p4_linux_runtime_lib_t', 'target': 'p4_linux_console_locale_runtime_lib_t'}]}
FRESH_OBJECTS = {'dir': 'p4_linux_tmpfiles_static_dir_t', 'chr_file': 'p4_linux_tmpfiles_static_node_t'}
BIRTH_TRANSITIONS = [('p4_linux_run_t', 'dir', 'droidloom', 'droidloom_public_control_dir'), ('droidloom_public_apk_root', 'dir', 'u1000', 'droidloom_public_apk_dir'), ('p4_linux_run_t', 'file', 'nologin', 'p4_linux_tmpfiles_nologin_t'), ('p4_linux_run_t', 'lnk_file', 'shm', 'p4_linux_tmpfiles_shm_link_t'), ('p4_linux_run_t', 'dir', 'lock', 'p4_linux_tmpfiles_runtime_dir_t'), ('p4_linux_tmpfiles_runtime_dir_t', 'dir', 'subsys', 'p4_linux_tmpfiles_runtime_dir_t'), ('p4_linux_run_t', 'dir', 'sendsigs.omit.d', 'p4_linux_tmpfiles_runtime_dir_t'), ('p4_linux_run_t', 'dir', 'setrans', 'p4_linux_tmpfiles_runtime_dir_t'), ('p4_linux_run_t', 'dir', 'screen', 'p4_linux_tmpfiles_runtime_dir_t'), ('p4_linux_run_t', 'dir', 'spice-vdagentd', 'p4_linux_tmpfiles_runtime_dir_t'), ('p4_linux_run_t', 'dir', 'sudo', 'p4_linux_tmpfiles_runtime_dir_t'), ('p4_linux_run_t', 'dir', 'media', 'p4_linux_tmpfiles_runtime_dir_t'), ('p4_linux_systemd_run_t', 'dir', 'machines', 'p4_linux_tmpfiles_runtime_dir_t'), ('p4_linux_timesyncd_netif_t', 'dir', 'leases', 'p4_linux_tmpfiles_runtime_dir_t'), ('p4_linux_native_dev_root_t', 'dir', 'snd', 'p4_linux_tmpfiles_static_dir_t'), ('p4_linux_native_dev_root_t', 'dir', 'vfio', 'p4_linux_tmpfiles_static_dir_t'), ('p4_linux_native_dev_root_t', 'chr_file', 'cuse', 'p4_linux_tmpfiles_static_node_t'), ('p4_linux_native_dev_root_t', 'chr_file', 'autofs', 'p4_linux_tmpfiles_static_node_t'), ('p4_linux_native_dev_root_t', 'chr_file', 'btrfs-control', 'p4_linux_tmpfiles_static_node_t'), ('p4_linux_native_dev_root_t', 'chr_file', 'nvram', 'p4_linux_tmpfiles_static_node_t'), ('p4_linux_native_dev_root_t', 'chr_file', 'userio', 'p4_linux_tmpfiles_static_node_t'), ('p4_linux_native_dev_root_t', 'chr_file', 'uhid', 'p4_linux_tmpfiles_static_node_t'), ('p4_linux_tmpfiles_static_dir_t', 'chr_file', 'vfio', 'p4_linux_tmpfiles_static_node_t'), ('p4_linux_native_dev_root_t', 'chr_file', 'vhci', 'p4_linux_tmpfiles_static_node_t'), ('p4_linux_native_dev_root_t', 'chr_file', 'vhost-net', 'p4_linux_tmpfiles_static_node_t'), ('p4_linux_native_dev_root_t', 'chr_file', 'vhost-vsock', 'p4_linux_tmpfiles_static_node_t'), ('p4_linux_tmpfiles_static_dir_t', 'chr_file', 'timer', 'p4_linux_tmpfiles_static_node_t'), ('p4_linux_tmpfiles_static_dir_t', 'chr_file', 'seq', 'p4_linux_tmpfiles_static_node_t')]
CONTRACT_PIN = (40470, '3a0d3185dda2e645f2947c3ff73dbc1633a6de2a81b5888d043e9d9860451d6a')
SELECTED_DEVICE_NAMES = ['/dev/cuse', '/dev/autofs', '/dev/btrfs-control', '/dev/nvram', '/dev/userio', '/dev/uhid', '/dev/vfio/vfio', '/dev/vhci', '/dev/vhost-net', '/dev/vhost-vsock', '/dev/snd/timer', '/dev/snd/seq']
Z_ONLY_DEVICE_NAMES = ['/dev/loop-control', '/dev/net/tun', '/dev/fuse', '/dev/kvm']

EXECUTOR = "p4_linux_service_executor_t"
TRANSITIONS = ("(typetransition ", "(typechange ", "(typemember ", "(roletransition ")
CONSTRAINTS = ("(constrain ", "(mlsconstrain ", "(validatetrans ", "(mlsvalidatetrans ")
OLD_ENTRY = "(typetransition " + EXECUTOR + " p4_linux_setup_exec_t process p4_linux_setup_t)"
COPIED_ENTRY = "(typetransition " + EXECUTOR + " " + ENTRY + " process p4_linux_setup_t)"
SELECTED_ENTRY = "(typetransition " + EXECUTOR + " " + ENTRY + " process " + ROLE + ")"
KERNEL_DEVICE_FALLBACK = "(typetransition kernel p4_linux_tmpfiles_static_dir_t chr_file device)"
SELINUXFS_READ = {"getattr", "open", "read", "map"}
IOCTL_TARGETS = ("p4_linux_journal_store_t", "p4_linux_journal_machine_t")
IOCTL_MASK = (1 << 0x6601) | (1 << 0x6602)
NORMAL_METADATA_PREIMAGE = {
    (row["target"], actor, "dir"): {"getattr", "search"}
    for row in ALIASES if row["class"] != "dir"
    for actor in ("droidloom_metadata_observer", "droidloom_query_io")
}
DEVICE_VIEWS = [
    {"source": "device", "target": "p4_linux_tmpfiles_static_dir_t", "class": "dir"},
    {"source": "device", "target": "p4_linux_tmpfiles_static_node_t", "class": "chr_file"},
]
# This fixed birth child labels only the already held original watchdog inode.
# Its generic-device metadata grant is not an ordinary static-node consumer
# view. Preserve that original vector, while keeping both new object types
# completely inaccessible to the child. No other actor is excluded.
BIRTH_LABEL = "p4_linux_working_watchdog_label_t"
BIRTH_ROLE = "r"
BIRTH_DEVICE = "p4_linux_working_watchdog_t"
BIRTH_DEVICE_CONFINEMENT = {
    "actor": BIRTH_LABEL,
    "role": BIRTH_ROLE,
    "original_source": "device",
    "original_class": "chr_file",
    "original_permissions": ["getattr", "relabelfrom"],
    "original_filesystem_permissions": ["getattr"],
    "selected_device": BIRTH_DEVICE,
    "selected_permissions": ["getattr", "relabelto"],
    "zero_targets": sorted(FRESH_OBJECTS.values()),
    "zero_classes": "all",
    "zero_category_pairs": "all",
    "all_other_actor_vectors_preserved": True,
    "generic_device_permissions_changed": False,
    "kernel_runtime_qualified": False,
}
# Existing board label metadata readers already see these new labels at prelink.
# Their exact four dir-class keys use the old rootdir metadata view, separately
# from ordinary device preservation. The two original generic-device views
# differ and are both retained exactly, including every category decision.
FRESH_METADATA_REFERENCE = "p4_linux_rootdir_t"
FRESH_DEVICE_PREIMAGE = {
    "droidloom_metadata_observer": set(),
    "droidloom_query_io": {"getattr", "search"},
}
FRESH_METADATA_PREIMAGE = {
    (target, actor, "dir"): {"getattr", "search"}
    for target in ("p4_linux_tmpfiles_static_dir_t", "p4_linux_tmpfiles_static_node_t")
    for actor in ("droidloom_metadata_observer", "droidloom_query_io")
}


def _probe_audit(lines, raw):
    selected = []
    wanted = {"p4_linux_tmpfiles_usr_config_t", "p4_linux_tmpfiles_etc_config_t",
              "p4_linux_kmod_static_nodes_t"}
    for line in lines:
        if not line.startswith("(dontauditx "):
            continue
        form = parse_expression(line)
        if len(form) != 4 or form[1] not in raw.members:
            raise ValueError("Malformed extended audit rule")
        subjects = raw.members[form[1]]
        if form[2] == "self":
            targets = subjects
        elif form[2] in raw.members:
            targets = raw.members[form[2]]
        else:
            raise ValueError("Unknown extended audit target")
        if not (subjects | targets) & NEW_TYPES:
            continue
        if (form[1] != ROLE or form[2] not in wanted
                or not isinstance(form[3], list) or len(form[3]) != 3
                or form[3][:2] != ["ioctl", "file"]
                or not isinstance(form[3][2], list)):
            raise ValueError("Tmpfiles acquired an unapproved audit suppression")
        commands = form[3][2]
        # Normal libsepol exports the singleton as ((0x542a)); retain the source
        # spelling (0x542a) as the same exact singleton, without accepting ranges.
        if len(commands) == 1 and isinstance(commands[0], list):
            commands = commands[0]
        if (len(commands) != 1 or not isinstance(commands[0], str)
                or int(commands[0], 0) != 0x542a):
            raise ValueError("Tmpfiles terminal probe is not the exact single command")
        if "ioctl" in raw.actor(ROLE).get((form[2], "file"), set()):
            raise ValueError("Tmpfiles terminal probe acquired a base ioctl grant")
        selected.append(form[2])
    if len(selected) != 3 or set(selected) != wanted:
        raise ValueError("Tmpfiles terminal-probe audit rules are not the exact three concrete pairs")
    return [[ROLE, target, "file", "0x542a"] for target in sorted(wanted)]


def contract(here):
    data = (here / "native-tmpfiles-source.json").read_bytes()
    if (len(data), hashlib.sha256(data).hexdigest()) != CONTRACT_PIN:
        raise ValueError("The fixed normal tmpfiles source contract changed")
    value = json.loads(data)
    if (value["schema"] != "droidloom.native-tmpfiles-source.v1"
            or value["role"] != ROLE or value["aliases"] != ALIASES
            or value["new_types"] != sorted(NEW_TYPES)
            or value["normal_implementation_changed"]
            or value["unit_success_status_changed"]
            or value["kernel_basename_confinement"]
            or value["kernel_runtime_qualified"]
            or value["production_qualified"]
            or value["label_lookup"]["validation_option"]
            or value["label_lookup"]["security_permissions"] != []
            or value["label_lookup"]["netlink_permissions"] != []
            or value["capabilities"] != ["chown", "fowner", "fsetid", "mknod"]
            or value["ioctls"] != [{"class": "dir", "commands": ["0x6601", "0x6602"],
                                    "target": t} for t in IOCTL_TARGETS]
            or value["selected_device_names"] != SELECTED_DEVICE_NAMES
            or value["z_only_device_names"] != Z_ONLY_DEVICE_NAMES
            or value["device_view_preservation"]["kernel_fallback_transition"] != KERNEL_DEVICE_FALLBACK
            or value["device_view_preservation"].get("fixed_board_birth_confinement") != BIRTH_DEVICE_CONFINEMENT
            or value["board_rules"]["source_path"] != "packaging/tmpfiles/droidloom-production.conf"):
        raise ValueError("The fixed normal tmpfiles execution boundary changed")
    _birth_source_boundary(here)
    board = here.parents[3] / value["board_rules"]["source_path"]
    body = board.read_bytes()
    if (len(body), hashlib.sha256(body).hexdigest()) != (
            value["board_rules"]["bytes"], value["board_rules"]["sha256"]):
        raise ValueError("The immutable board tmpfiles rules changed")
    return value


def source_inputs(here):
    value = contract(here)
    return [here / "native-tmpfiles-source.json",
            here / "ubuntu-working-qualification.cil",
            here.parents[3] / value["board_rules"]["source_path"]]


def _birth_source_boundary(here):
    text = (here / "ubuntu-working-qualification.cil").read_text()
    text = re.sub(r"\s+", " ", re.sub(r";[^\n]*", "", text)).strip()
    required = (
        f"(roletype {BIRTH_ROLE} {BIRTH_LABEL})",
        f"(allow {BIRTH_LABEL} device (chr_file (getattr relabelfrom)))",
        f"(allow {BIRTH_LABEL} {BIRTH_DEVICE} (chr_file (getattr relabelto)))",
        f"(typeattributeset p4_working_birth_other_devices (not (device {BIRTH_DEVICE})))",
        f"(neverallow {BIRTH_LABEL} device (chr_file (not (getattr relabelfrom))))",
        f"(neverallow {BIRTH_LABEL} {BIRTH_DEVICE} (chr_file (not (getattr relabelto))))",
        f"(neverallow {BIRTH_LABEL} p4_working_birth_other_devices (chr_file (all)))",
    )
    if any(text.count(rule) != 1 for rule in required):
        raise ValueError("The fixed working watchdog birth device source boundary changed")


def _birth_device_boundary(policy, raw, actors):
    original = {cls: names for (target, cls), names in raw.actor(BIRTH_LABEL).items()
                if target == "device"}
    selected = {cls: names for (target, cls), names in raw.actor(BIRTH_LABEL).items()
                if target == BIRTH_DEVICE}
    if ([role for role, actor in actors if actor == BIRTH_LABEL] != [BIRTH_ROLE]
            or original != {"chr_file": {"getattr", "relabelfrom"},
                            "filesystem": {"getattr"}}
            or selected != {"chr_file": {"getattr", "relabelto"}}
            or any(_device_xperms(raw, {BIRTH_LABEL}, target)
                   for target in ("device", BIRTH_DEVICE))):
        raise ValueError("The original working birth device preimage changed")
    checks = []
    for target in FRESH_OBJECTS.values():
        if any(actor == BIRTH_LABEL and names
               for (actor, _), names in raw.incoming(target).items()):
            raise ValueError("The working birth child acquired a static-device raw permission")
        if _device_xperms(raw, {BIRTH_LABEL}, target):
            raise ValueError("The working birth child acquired a static-device ioctl vector")
        for cls, names in sorted(raw.classes.items()):
            for a in LEVELS:
                for b in LEVELS:
                    got = policy.context_av(_context(BIRTH_ROLE, BIRTH_LABEL, a),
                        _context("object_r", target, b), cls, names)
                    if got:
                        raise ValueError("The working birth child acquired a static-device category decision")
                    checks.append([BIRTH_LABEL, target, cls, a, b, got])
    return checks


def _providers(here):
    result = []
    for module, fixed in FIXED_ALIAS_PROVIDERS.items():
        actual = importlib.import_module(module)
        rows = actual.contract(here)["aliases"] if module == "derive_native_console_policy" else actual.ALIASES
        if rows != fixed:
            raise ValueError("A fixed tmpfiles alias provider changed: " + module)
        result.extend(rows)
    keys = [(r["target"], r["class"]) for r in result]
    if len(keys) != len(set(keys)):
        raise ValueError("Overlapping fixed tmpfiles alias/class providers")
    return result


def _base_role(types):
    return {(target, cls): set(names) for target, cls, names in BASE_ROLE_ROWS if target in types}


def _role_map(here, types, final):
    result = _base_role(types)
    rows = FIXED_ALIAS_PROVIDERS["derive_native_kmod_static_policy"]
    if final:
        rows = _providers(here)
    for row in rows:
        if row["target"] not in types:
            continue
        source, target = (row["source"], row["class"]), (row["target"], row["class"])
        if source in result:
            result.setdefault(target, set()).update(result[source])
    return result


def _rows(table):
    return [[actor, cls, sorted(names)] for (actor, cls), names in sorted(table.items())]


def _table(rows):
    result = {}
    for actor, cls, names in rows:
        if (actor, cls) in result or names != sorted(set(names)) or not names:
            raise ValueError("Repeated, empty or noncanonical tmpfiles vector")
        result[(actor, cls)] = set(names)
    return result


def _delta(actual, wanted):
    return [[*key, sorted(actual.get(key, set())), sorted(wanted.get(key, set()))]
            for key in sorted(actual.keys() | wanted.keys())
            if actual.get(key, set()) != wanted.get(key, set())]


def _check_role(raw, here, final):
    wanted = _role_map(here, raw.types, final)
    actual = raw.actor(ROLE)
    if actual != wanted:
        raise ValueError("Tmpfiles complete raw authority changed: " + repr(_delta(actual, wanted)))
    if actual.get(("selinuxfs", "file"), set()) != SELINUXFS_READ:
        raise ValueError("Tmpfiles SELinux status access is not read-only")
    if any(v for (target, cls), v in actual.items() if cls == "security" or cls.startswith("netlink_")):
        raise ValueError("Tmpfiles acquired a security query or netlink fallback")
    inbound = {
        ("init_t", "process"): {"getattr", "signull", "signal", "sigkill", "sigstop"},
        (EXECUTOR, "process"): {"transition", "siginh", "rlimitinh"},
        (EXECUTOR, "process2"): {"nnp_transition"},
        (ROLE, "process"): {"getcap", "setfscreate"},
        (ROLE, "dir"): {"getattr", "search"},
        (ROLE, "lnk_file"): {"getattr", "read"},
        (ROLE, "fd"): {"use"},
        (ROLE, "capability"): {"chown", "fowner", "fsetid", "mknod"},
    }
    if raw.incoming(ROLE) != inbound:
        raise ValueError("Tmpfiles incoming caller boundary changed: " + repr(_delta(raw.incoming(ROLE), inbound)))
    for target in FRESH_OBJECTS.values():
        if raw.actor(target) != {("device", "filesystem"): {"associate"}}:
            raise ValueError("Tmpfiles device identity acquired outgoing authority")
    for target in (ENTRY, "p4_linux_tmpfiles_usr_config_t", "p4_linux_tmpfiles_etc_config_t",
                   "p4_linux_tmpfiles_config_dir_t"):
        if raw.actor(target):
            raise ValueError("Tmpfiles immutable input acquired outgoing authority")
    for target in ("p4_linux_tmpfiles_runtime_dir_t", "p4_linux_tmpfiles_nologin_t", "p4_linux_tmpfiles_shm_link_t"):
        if raw.actor(target) != {("tmpfs", "filesystem"): {"associate"}}:
            raise ValueError("Tmpfiles runtime object acquired unrelated authority")
    return wanted


def _ioctls(exported, raw):
    """Expand the existing extended-permission forms once; absent keys are zero."""
    classes = {name for name, perms in raw.classes.items() if "ioctl" in perms}
    universe = (1 << 65536) - 1
    def numbers(value):
        if isinstance(value, str):
            n = int(value, 0)
            if not 0 <= n <= 65535:
                raise ValueError("Invalid tmpfiles ioctl command")
            return 1 << n
        if not isinstance(value, list):
            raise ValueError("Invalid tmpfiles ioctl expression")
        if value and value[0] == "range":
            if len(value) != 3:
                raise ValueError("Invalid tmpfiles ioctl range")
            lo, hi = (int(x, 0) for x in value[1:])
            if not 0 <= lo <= hi <= 65535:
                raise ValueError("Invalid tmpfiles ioctl range")
            return ((1 << (hi - lo + 1)) - 1) << lo
        if value and value[0] == "not":
            if len(value) != 2:
                raise ValueError("Invalid tmpfiles ioctl complement")
            return universe ^ numbers(value[1])
        mask = 0
        for child in value:
            mask |= numbers(child)
        return mask
    found = {}
    for form in raw.xperms:
        if (len(form) != 4 or form[0] != "allowx" or form[1] not in raw.members
                or not isinstance(form[3], list) or len(form[3]) != 3):
            raise ValueError("Unmodeled extended-permission form")
        subjects = raw.members[form[1]] & NEW_TYPES
        if not subjects:
            continue
        operation, cls, commands = form[3]
        if operation != "ioctl" or cls not in classes:
            raise ValueError("Unmodeled tmpfiles extended-permission class")
        mask = numbers(commands)
        if not mask:
            continue
        for actor in subjects:
            if form[2] == "self":
                targets = {actor}
            elif form[2] in raw.members:
                targets = raw.members[form[2]]
            else:
                raise ValueError("Unmodeled tmpfiles ioctl target")
            for target in targets:
                key = (actor, target, cls)
                found[key] = found.get(key, 0) | mask
    wanted = {(ROLE, target, "dir"): IOCTL_MASK for target in IOCTL_TARGETS}
    if found != wanted:
        raise ValueError("Tmpfiles complete ioctl command space changed")
    return {
        "nonzero_rows": [[ROLE, target, "dir", ["0x6601", "0x6602"]] for target in IOCTL_TARGETS],
        "complete_command_decisions": len(NEW_TYPES) * len(raw.types) * len(classes) * 65536,
    }


def _effective_role(policy, lines, table, classes):
    result = []
    for (target, cls), names in sorted(table.items()):
        role = _context_role(lines, target)
        for a in LEVELS:
            for b in LEVELS:
                got = policy.context_av(_context("system_r", ROLE, a),
                    _context(role, target, b), cls, classes[cls])
                if a == b == "s0" and got != _bits(policy, cls, names):
                    raise ValueError("The normal s0 tmpfiles vector is not effective: " + target + " " + cls)
                result.append([target, cls, a, b, got])
    return result


def _constraints(lines, raw):
    selected = sorted(line for line in lines if line.startswith(CONSTRAINTS))
    if (selected.count(DIRECTORY_RELABEL_GUARD) != 1
            or hashlib.sha256(DIRECTORY_RELABEL_GUARD.encode()).hexdigest() != DIRECTORY_RELABEL_GUARD_SHA256):
        raise ValueError("The complete original directory relabel guard changed")
    for line in selected:
        if line == DIRECTORY_RELABEL_GUARD:
            # The original hardware identity predicate is retained verbatim.
            # Only that actor takes its restricted branch; it has no relabel
            # gate on either member of these rootdir aliases.
            hardware = raw.actor("p4_linux_hardware_label_t")
            labels = {r[k] for r in ALIASES if r["class"] == "dir" for k in ("source", "target")}
            if any(hardware.get((label, "dir"), set()) & {"relabelfrom", "relabelto"} for label in labels):
                raise ValueError("Tmpfiles exposed the original directory identity-guard branch")
            continue
        form = parse_expression(line)
        if form[0] not in ("validatetrans", "mlsvalidatetrans"):
            continue
        for row in ALIASES:
            if row["class"] != form[1]:
                continue
            def substitute(expr, variable, label):
                if not isinstance(expr, list):
                    return expr
                if len(expr) == 3 and expr[0] in ("eq", "neq") and variable in expr[1:]:
                    other = expr[2] if expr[1] == variable else expr[1]
                    if not isinstance(other, str) or other in ("t1", "t2", "t3") or other not in raw.members:
                        raise ValueError("Unmodeled tmpfiles alias relabel identity predicate")
                    answer = label in raw.members[other]
                    return answer if expr[0] == "eq" else not answer
                return [substitute(child, variable, label) for child in expr]
            for variable in ("t1", "t2"):
                if substitute(form[2], variable, row["source"]) != substitute(form[2], variable, row["target"]):
                    raise ValueError("Tmpfiles alias changed an original relabel predicate")
    return selected


def _selected_transitions(lines):
    def atoms(value):
        if isinstance(value, str):
            return {value}
        return set().union(*(atoms(child) for child in value)) if value else set()
    return sorted(line for line in lines if line.startswith(TRANSITIONS)
                  and atoms(parse_expression(line)) & NEW_TYPES)


def _birth_forms():
    return {f'(typetransition {ROLE} {parent} {cls} "{name}" {target})'
            for parent, cls, name, target in BIRTH_TRANSITIONS} | {KERNEL_DEVICE_FALLBACK}


def _metadata_effective(policy, raw, actors):
    roles = {actor: role for role, actor in actors}
    if len(roles) != len(actors):
        raise ValueError("Ambiguous tmpfiles metadata actor roles")
    rows = []
    for (target, actor, cls), names in sorted(NORMAL_METADATA_PREIMAGE.items()):
        if actor not in roles or cls != "dir":
            raise ValueError("Unknown tmpfiles metadata reader")
        old = next(row["source"] for row in ALIASES if row["target"] == target)
        for label in (old, target):
            if raw.incoming(label).get((actor, cls), set()) != names:
                raise ValueError("Tmpfiles off-class metadata source preimage changed")
        for a in LEVELS:
            for b in LEVELS:
                source = _context(roles[actor], actor, a)
                before = policy.context_av(source, _context("object_r", old, b), cls, raw.classes[cls])
                after = policy.context_av(source, _context("object_r", target, b), cls, raw.classes[cls])
                if before != after:
                    raise ValueError("Tmpfiles changed an off-class metadata category decision")
                if a == b == "s0" and before != _bits(policy, cls, names):
                    raise ValueError("Tmpfiles off-class metadata is not the fixed s0 preimage")
                rows.append([roles[actor], actor, old, target, cls, a, b, before])
    return rows


def _device_xperms(raw, actors, target):
    # Unlike the filesystem-only shared helper, inspect every actual class.
    # Preserve only source class vectors selected by DEVICE_VIEWS; all other
    # incoming extended-permission classes remain explicitly zero.
    universe = (1 << 65536) - 1
    def numbers(value):
        if isinstance(value, str):
            n = int(value, 0)
            if not 0 <= n <= 65535:
                raise ValueError("Invalid device ioctl command")
            return 1 << n
        if not isinstance(value, list):
            raise ValueError("Invalid device ioctl expression")
        if value and value[0] == "range":
            if len(value) != 3:
                raise ValueError("Invalid device ioctl range")
            lo, hi = (int(x, 0) for x in value[1:])
            if not 0 <= lo <= hi <= 65535:
                raise ValueError("Invalid device ioctl range")
            return ((1 << (hi - lo + 1)) - 1) << lo
        if value and value[0] == "not":
            if len(value) != 2:
                raise ValueError("Invalid device ioctl complement")
            return universe ^ numbers(value[1])
        mask = 0
        for child in value:
            mask |= numbers(child)
        return mask
    result = {}
    for form in raw.xperms:
        if (len(form) != 4 or form[0] != "allowx" or form[1] not in raw.members
                or not isinstance(form[3], list) or len(form[3]) != 3):
            raise ValueError("Malformed device extended-permission form")
        selected = raw.members[form[1]] & actors
        if not selected:
            continue
        if form[2] == "self":
            selected &= {target}
        elif form[2] not in raw.members:
            raise ValueError("Unknown device ioctl target")
        elif target not in raw.members[form[2]]:
            continue
        if not selected:
            continue
        operation, cls, commands = form[3]
        if operation != "ioctl" or cls not in raw.classes or "ioctl" not in raw.classes[cls]:
            raise ValueError("Unsupported device extended-permission operation")
        mask = numbers(commands)
        if mask:
            for actor in selected:
                key = (actor, cls)
                result[key] = result.get(key, 0) | mask
    return result


def _alias_xperms(raw, expected=None):
    subjects = raw.types - NEW_TYPES
    originals, targets = {}, {}
    for row in ALIASES:
        old = _device_xperms(raw, subjects, row["source"])
        actual = _device_xperms(raw, subjects, row["target"])
        wanted = {(actor, cls): mask for (actor, cls), mask in old.items()
                  if cls == row["class"]}
        if expected is None:
            if any(mask & ~wanted.get(key, 0) for key, mask in actual.items()):
                raise ValueError("Tmpfiles alias has an unapproved cross-class ioctl preimage")
        elif actual != wanted:
            raise ValueError("Tmpfiles alias changed the complete incoming ioctl class boundary")
        originals[row["source"]] = [[a, c, hex(mask)] for (a, c), mask in sorted(old.items())]
        targets[row["target"]] = [[a, c, hex(mask)] for (a, c), mask in sorted(wanted.items())]
    result = {"subjects": sorted(subjects), "original_sources": originals, "targets": targets}
    if expected is not None and result != expected:
        raise ValueError("Tmpfiles changed an original source or subject ioctl vector")
    return result


def _derive_devices(policy, raw, lines, exported, actors):
    roles = {actor: role for role, actor in actors}
    if len(roles) != len(actors) or ROLE in roles:
        raise ValueError("Invalid complete tmpfiles device consumer roster")
    old = raw.incoming("device")
    birth_checks = _birth_device_boundary(policy, raw, actors)
    targets, effective, metadata, generated = {}, [], [], []
    xsubjects = raw.types - NEW_TYPES
    old_x = _device_xperms(raw, xsubjects, "device")
    xrows = []
    for index, row in enumerate(DEVICE_VIEWS):
        target, cls = row["target"], row["class"]
        wanted = {key: set(names) for key, names in old.items()
                  if key[1] == cls and key[0] not in (ROLE, BIRTH_LABEL)}
        own = _base_role(raw.types).get((target, cls), set())
        if own:
            wanted[(ROLE, cls)] = own
        for (label, actor, other), names in FRESH_METADATA_PREIMAGE.items():
            if label != target:
                continue
            if (old.get((actor, other), set()) != FRESH_DEVICE_PREIMAGE[actor]
                    or raw.incoming(FRESH_METADATA_REFERENCE).get((actor, other), set()) != names
                    or raw.incoming(target).get((actor, other), set()) != names):
                raise ValueError("Fresh device metadata is not its fixed independent board preimage")
            wanted[(actor, other)] = names
            for a in LEVELS:
                for b in LEVELS:
                    source = _context(roles[actor], actor, a)
                    before = policy.context_av(source, _context("object_r", FRESH_METADATA_REFERENCE, b),
                                               other, raw.classes[other])
                    preimage = policy.context_av(source, _context("object_r", target, b),
                                                 other, raw.classes[other])
                    device_before = policy.context_av(source, _context("object_r", "device", b),
                                                       other, raw.classes[other])
                    if (before != preimage
                            or device_before != (before if FRESH_DEVICE_PREIMAGE[actor] else 0)):
                        raise ValueError("Fresh device metadata changed a fixed original category decision")
                    metadata.append([roles[actor], actor, FRESH_METADATA_REFERENCE,
                                     target, other, a, b, before, device_before])
        for key, names in raw.incoming(target).items():
            if not names.issubset(wanted.get(key, set())):
                raise ValueError("Unapproved tmpfiles device consumer preimage: " + repr((target, key, names)))
        if any(actor not in roles and actor != ROLE for actor, _ in wanted):
            raise ValueError("Unmodeled nonprocess tmpfiles device consumer")
        groups = {}
        for role, actor in actors:
            names = wanted.get((actor, cls), set())
            if names:
                groups.setdefault(tuple(sorted(names)), []).append(actor)
            for a in LEVELS:
                for b in LEVELS:
                    mask = policy.context_av(_context(role, actor, a),
                        _context("object_r", "device", b), cls, raw.classes[cls])
                    if a == b == "s0" and mask != _bits(policy, cls, old.get((actor, cls), set())):
                        raise ValueError("Original device raw/effective s0 views disagree")
                    effective.append([role, actor, target, cls, a, b, mask])
        for number, (names, members) in enumerate(sorted(groups.items())):
            attr = f"p4_tmpfiles_device_preserved_{index}_{number}"
            if attr in raw.members:
                raise ValueError("Repeated tmpfiles device preservation attribute")
            generated += [f"(typeattribute {attr})",
                          f"(typeattributeset {attr} ({' '.join(members)}))",
                          f"(allow {attr} {target} ({cls} ({' '.join(names)})))"]
        expected_x = {(actor, cls): mask for (actor, item), mask in old_x.items() if item == cls}
        actual_x = _device_xperms(raw, xsubjects, target)
        if any(mask & ~expected_x.get(key, 0) for key, mask in actual_x.items()):
            raise ValueError("Unapproved tmpfiles device ioctl preimage")
        for (actor, item), mask in sorted(expected_x.items()):
            generated.append(f"(allowx {actor} {target} (ioctl {item} {format_xperms(mask)}))")
            xrows.append([actor, target, item, hex(mask)])
        targets[target] = _rows(wanted)
    return {
        "original_device_complete_raw": _rows(old),
        "targets": targets, "effective": effective, "offclass_metadata": metadata,
        "xperms": xrows, "original_xperms": [[a, c, hex(m)] for (a, c), m in sorted(old_x.items())],
        "actors": actors, "views": DEVICE_VIEWS, "xperm_subjects": sorted(xsubjects),
        "fixed_board_birth_confinement": BIRTH_DEVICE_CONFINEMENT,
        "birth_zero_vectors": birth_checks,
        "hardware_identity_relabel_equivalence_claimed": False,
        "separate_board_metadata_keys": [[t, a, c, sorted(n)]
            for (t, a, c), n in sorted(FRESH_METADATA_PREIMAGE.items())],
        "board_metadata_reference": FRESH_METADATA_REFERENCE,
    }, generated


def _verify_devices(policy, raw, lines, exported, expected):
    if (expected["views"] != DEVICE_VIEWS
            or expected["hardware_identity_relabel_equivalence_claimed"] is not False
            or expected["board_metadata_reference"] != FRESH_METADATA_REFERENCE
            or expected.get("fixed_board_birth_confinement") != BIRTH_DEVICE_CONFINEMENT
            or expected["separate_board_metadata_keys"] != [[t, a, c, sorted(n)]
                for (t, a, c), n in sorted(FRESH_METADATA_PREIMAGE.items())]):
        raise ValueError("Tmpfiles device view contract changed")
    birth_checks = _birth_device_boundary(policy, raw, expected["actors"])
    if birth_checks != expected.get("birth_zero_vectors"):
        raise ValueError("Tmpfiles changed a fixed working birth zero vector")
    if raw.incoming("device") != _table(expected["original_device_complete_raw"]):
        raise ValueError("Tmpfiles changed the complete original generic device permissions")
    for target, rows in expected["targets"].items():
        if raw.incoming(target) != _table(rows):
            raise ValueError("Tmpfiles changed a complete device target/class boundary")
    checks = []
    for role, actor, target, cls, a, b, wanted in expected["effective"]:
        labels = ("device",) if (target, actor, cls) in FRESH_METADATA_PREIMAGE else ("device", target)
        for label in labels:
            got = policy.context_av(_context(role, actor, a), _context("object_r", label, b),
                                    cls, raw.classes[cls])
            selected = 0 if actor == BIRTH_LABEL and label == target else wanted
            if got != selected:
                raise ValueError("Tmpfiles changed an ordinary device category vector: " +
                                 repr((actor, label, cls, a, b, got, wanted)))
        checks.append([role, actor, target, cls, a, b, wanted])
    for role, actor, reference, target, cls, a, b, wanted, device_wanted in expected["offclass_metadata"]:
        names = FRESH_METADATA_PREIMAGE.get((target, actor, cls))
        if (reference != FRESH_METADATA_REFERENCE or names is None
                or raw.incoming("device").get((actor, cls), set()) != FRESH_DEVICE_PREIMAGE[actor]
                or any(raw.incoming(label).get((actor, cls), set()) != names
                       for label in (reference, target))):
            raise ValueError("Tmpfiles independent board metadata preimage changed")
        device_got = policy.context_av(_context(role, actor, a), _context("object_r", "device", b),
                                       cls, raw.classes[cls])
        if (device_got != device_wanted
                or device_wanted != (wanted if FRESH_DEVICE_PREIMAGE[actor] else 0)):
            raise ValueError("Tmpfiles changed the exact original device metadata category vector")
        for label in (reference, target):
            got = policy.context_av(_context(role, actor, a), _context("object_r", label, b),
                                    cls, raw.classes[cls])
            if got != wanted:
                raise ValueError("Tmpfiles changed a fresh off-class metadata vector")
        checks.append([role, actor, target, cls, a, b, wanted])
    actors = raw.types - NEW_TYPES
    if sorted(actors) != expected["xperm_subjects"]:
        raise ValueError("Tmpfiles device ioctl subject set changed")
    old_x = _device_xperms(raw, actors, "device")
    if [[a, c, hex(m)] for (a, c), m in sorted(old_x.items())] != expected["original_xperms"]:
        raise ValueError("Tmpfiles changed an original generic device ioctl vector")
    wanted_x = {(a, t, c): int(m, 16) for a, t, c, m in expected["xperms"]}
    actual_x = {(a, row["target"], c): m for row in DEVICE_VIEWS
                for (a, c), m in _device_xperms(raw, actors, row["target"]).items()}
    if actual_x != wanted_x:
        raise ValueError("Tmpfiles changed a device consumer's complete ioctl boundary")
    return checks + birth_checks


def derive(library, baseline, exported, here, output, export):
    contract(here)
    expected = derive_preserved_aliases(
        library, baseline, exported, ALIASES, output, export,
        prefix="p4_tmpfiles_preserved", isolated_roles={ROLE}, extra_permissions={},
        # Complete raw/all-category and fixed relabel proofs below supplement
        # the unchanged common category-independent gate for old actors.
        preamble=("; Preserve every other actor's full original tmpfiles input/output view.",
                  "; Only the normal tmpfiles entry transition selects the new consumer."))
    policy = ContextPolicy(library, baseline)
    lines = exported.read_text().splitlines()
    raw = RawPolicy(lines)
    base = _check_role(raw, here, False)
    expected["role_before"] = _effective_role(policy, lines, base, raw.classes)
    expected["complete_constraints"] = _constraints(lines, raw)
    expected["normal_metadata_effective"] = _metadata_effective(policy, raw, expected["actors"])
    expected["device_preservation"], device_policy = _derive_devices(policy, raw, lines, exported, expected["actors"])
    expected["ioctl_boundary"] = _ioctls(exported, raw)
    expected["normal_probe_dontauditx"] = _probe_audit(lines, raw)
    expected["complete_alias_xperms"] = _alias_xperms(raw)
    if (lines.count(OLD_ENTRY) != 1 or lines.count(SELECTED_ENTRY) != 1
            or expected["transitions"].count(COPIED_ENTRY) != 1):
        raise ValueError("The exact normal tmpfiles entry replacement is absent")
    generated = output.read_text().splitlines()
    if generated.count(COPIED_ENTRY) != 1:
        raise ValueError("Ambiguous copied setup entry transition")
    generated.remove(COPIED_ENTRY)
    generated.extend(device_policy)
    expected["transitions"].remove(COPIED_ENTRY)
    output.write_text("\n".join(generated) + "\n")
    expected["derived_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    expected["entry_replacement"] = [OLD_ENTRY, COPIED_ENTRY, SELECTED_ENTRY]
    expected["selected_transitions"] = sorted(set(expected["transitions"]) | {SELECTED_ENTRY} | _birth_forms())
    source_raw, final_targets, raw_rows, effective = {}, {}, [], []
    actors = {actor for _, actor in expected["actors"]}
    for row in ALIASES:
        old = raw.incoming(row["source"])
        source_raw[row["source"]] = _rows(old)
        wanted = {key: names for key, names in old.items() if key[1] == row["class"] and key[0] != ROLE}
        own = base.get((row["target"], row["class"]), set())
        if own:
            wanted[(ROLE, row["class"])] = own
        for (target, actor, cls), names in NORMAL_METADATA_PREIMAGE.items():
            if target == row["target"]:
                if old.get((actor, cls), set()) != names:
                    raise ValueError("Tmpfiles changed the fixed metadata preimage")
                wanted[(actor, cls)] = names
        final_targets[row["target"]] = _rows(wanted)
        for key, names in raw.incoming(row["target"]).items():
            if not names.issubset(wanted.get(key, set())):
                raise ValueError("Tmpfiles alias has an unapproved actor/class preimage")
        for role, actor in expected["actors"]:
            before = old.get((actor, row["class"]), set())
            got = policy.context_av(_context(role, actor), _context("object_r", row["source"]),
                row["class"], raw.classes[row["class"]])
            if got != _bits(policy, row["class"], before):
                raise ValueError("Tmpfiles source raw vector cannot be reconstructed at s0")
            raw_rows.append([role, actor, row["source"], row["target"], row["class"], sorted(before)])
            for a in LEVELS:
                for b in LEVELS:
                    got = policy.context_av(_context(role, actor, a), _context("object_r", row["source"], b),
                        row["class"], raw.classes[row["class"]])
                    effective.append([role, actor, row["source"], row["target"], row["class"], a, b, got])
        if any(actor not in actors and actor != ROLE for actor, cls in wanted):
            raise ValueError("Tmpfiles alias has an unmodeled non-actor permission")
    expected["complete_old_source_raw"] = source_raw
    expected["complete_new_target_raw"] = final_targets
    expected["complete_alias_raw"] = raw_rows
    expected["complete_alias_effective"] = effective
    expected["fixed_alias_providers"] = _providers(here)
    expected["contract_sha256"] = CONTRACT_PIN[1]
    return expected


def verify(library, binary, exported, here, expected, export):
    value = contract(here)
    if (expected["contract_sha256"] != CONTRACT_PIN[1]
            or expected["entry_replacement"] != [OLD_ENTRY, COPIED_ENTRY, SELECTED_ENTRY]
            or expected["fixed_alias_providers"] != _providers(here)):
        raise ValueError("Tmpfiles source/derivation lineage changed")
    policy = ContextPolicy(library, binary)
    lines = export(policy, binary, exported)
    raw = RawPolicy(lines)
    if _constraints(lines, raw) != expected["complete_constraints"]:
        raise ValueError("Tmpfiles changed complete ordinary/MLS/relabel constraints")
    checks = verify_preserved_aliases(policy, exported, ALIASES, expected)
    if (_selected_transitions(lines) != expected["selected_transitions"]
            or OLD_ENTRY not in lines or COPIED_ENTRY in lines):
        raise ValueError("Tmpfiles changed an entry or birth transition")
    for label, rows in expected["complete_old_source_raw"].items():
        if raw.incoming(label) != _table(rows):
            raise ValueError("Tmpfiles changed a complete old source class vector")
    for label, rows in expected["complete_new_target_raw"].items():
        if raw.incoming(label) != _table(rows):
            raise ValueError("Tmpfiles changed a complete new target class vector")
    incoming = {label: raw.incoming(label) for row in ALIASES for label in (row["source"], row["target"])}
    for role, actor, old, new, cls, names in expected["complete_alias_raw"]:
        if any(incoming[label].get((actor, cls), set()) != set(names) for label in (old, new)):
            raise ValueError("Tmpfiles changed a complete old actor raw vector")
    for role, actor, old, new, cls, a, b, wanted in expected["complete_alias_effective"]:
        for target in (old, new):
            got = policy.context_av(_context(role, actor, a), _context("object_r", target, b),
                cls, raw.classes[cls])
            if got != wanted:
                raise ValueError("Tmpfiles changed an old constrained alias vector")
        checks.append([role, actor, old, new, cls, a, b, wanted])
    alias_xperms = _alias_xperms(raw, expected["complete_alias_xperms"])
    final = _check_role(raw, here, True)
    own = _effective_role(policy, lines, final, raw.classes)
    before = {(target, cls, a, b): mask for target, cls, a, b, mask in expected["role_before"]}
    wanted = dict(before)
    for row in expected["fixed_alias_providers"]:
        if row["target"] not in raw.types:
            continue
        for a in LEVELS:
            for b in LEVELS:
                key = (row["source"], row["class"], a, b)
                new = (row["target"], row["class"], a, b)
                if key in wanted and new not in before:
                    wanted[new] = wanted.get(new, 0) | wanted[key]
    if {(target, cls, a, b): mask for target, cls, a, b, mask in own} != wanted:
        raise ValueError("Tmpfiles successor changed a complete constrained role vector")
    metadata = _metadata_effective(policy, raw, expected["actors"])
    fresh = _verify_devices(policy, raw, lines, exported, expected["device_preservation"])
    if metadata != expected["normal_metadata_effective"]:
        raise ValueError("Tmpfiles fixed metadata category matrix changed after derivation")
    ioctls = _ioctls(exported, raw)
    probes = _probe_audit(lines, raw)
    if probes != expected["normal_probe_dontauditx"]:
        raise ValueError("Tmpfiles terminal-probe audit boundary changed")
    if ioctls != expected["ioctl_boundary"]:
        raise ValueError("Tmpfiles ioctl boundary changed after derivation")
    checks.extend(metadata); checks.extend(fresh); checks.extend(own)
    return {
        "schema": "droidloom.native-tmpfiles-policy-proof.v1",
        "source": {"bytes": CONTRACT_PIN[0], "sha256": CONTRACT_PIN[1], "contents": value},
        "source_bound_readback_required": True,
        "derived_alias_policy_sha256": expected["derived_sha256"],
        "preserved_actor_object_vectors": len(expected["samples"]),
        "preserved_raw_vectors": 2 * len(expected["complete_alias_raw"]),
        "preserved_effective_vectors": 2 * len(expected["complete_alias_effective"]),
        "complete_new_target_raw_class_object_pairs": 9 * len(raw.types) * len(raw.classes),
        "role_raw_class_object_pairs": len(raw.types) * len(raw.classes),
        "role_raw_nonzero_vectors": _rows(final),
        "role_effective_vectors": len(own), "category_pairs": len(LEVELS) ** 2,
        "metadata_effective_vectors": len(metadata), "fresh_device_effective_vectors": len(fresh),
        "device_views": DEVICE_VIEWS,
        "fixed_board_birth_device_confinement": BIRTH_DEVICE_CONFINEMENT,
        "hardware_identity_relabel_equivalence_claimed": False,
        "preserved_device_raw": expected["device_preservation"]["targets"],
        "separate_board_metadata": {
            "reference": FRESH_METADATA_REFERENCE,
            "fixed_keys": expected["device_preservation"]["separate_board_metadata_keys"],
            "effective_vectors": len(expected["device_preservation"]["offclass_metadata"]),
            "original_device_vectors_preserved": True,
            "original_generic_device_permissions": {
                actor: sorted(names) for actor, names in sorted(FRESH_DEVICE_PREIMAGE.items())},
        },
        "metadata_source_and_target_comparisons": 2 * len(metadata),
        "normal_metadata_preimage": [[target, actor, cls, sorted(names)]
            for (target, actor, cls), names in sorted(NORMAL_METADATA_PREIMAGE.items())],
        "entry_transition_replacement": expected["entry_replacement"],
        "fixed_alias_providers": expected["fixed_alias_providers"],
        "absent_fixed_alias_targets": sorted({r["target"] for r in expected["fixed_alias_providers"]} - raw.types),
        "ioctls": ioctls, "normal_probe_dontauditx": probes,
        "complete_alias_xperms": alias_xperms,
        "kernel_device_fallback_transition": KERNEL_DEVICE_FALLBACK,
        "kernel_device_creation_grants_added": False,
        "security_permissions": [], "netlink_permissions": [],
        "generic_device_body_permissions": [], "selinuxfs_file_permissions": sorted(SELINUXFS_READ),
        "normal_implementation_changed": False, "unit_success_status_changed": False,
        "kernel_basename_confinement": False,
        "file_contexts": verify_file_contexts(here, exported.parent),
        "matrix_sha256": hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest(),
        "kernel_runtime_qualified": False, "production_qualified": False,
    }


def verify_file_contexts(here, work):
    value = contract(here)
    names = ("ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts",
             "linux-service-file_contexts", "linux-initial-calibration-file_contexts")
    data = b"".join((here / name).read_bytes() for name in names)
    seen = {}
    for line in data.decode().splitlines():
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        if len(parts) not in (2, 3):
            raise ValueError("Invalid composed file-context syntax")
        key = (parts[0], parts[1] if len(parts) == 3 else None)
        if key in seen and seen[key] != parts[-1]:
            raise ValueError("Conflicting exact file-context preimages")
        seen[key] = parts[-1]
    path = work / "tmpfiles-file-contexts"
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("Tmpfiles matcher input changed")
    else:
        with path.open("xb") as f:
            f.write(data)
    class Option(ctypes.Structure):
        _fields_ = [("type", ctypes.c_int), ("value", ctypes.c_char_p)]
    lib = ctypes.CDLL("libselinux.so.1", use_errno=True)
    lib.selabel_open.argtypes = [ctypes.c_uint, ctypes.POINTER(Option), ctypes.c_uint]
    lib.selabel_open.restype = ctypes.c_void_p
    lib.selabel_lookup_raw.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p), ctypes.c_char_p, ctypes.c_int]
    lib.selabel_lookup_raw.restype = ctypes.c_int
    lib.selabel_close.argtypes = [ctypes.c_void_p]
    lib.freecon.argtypes = [ctypes.c_void_p]
    handle = lib.selabel_open(0, ctypes.byref(Option(3, str(path).encode())), 1)
    if not handle:
        raise ValueError("Normal class-aware tmpfiles contexts cannot be opened")
    kind = {"--": stat.S_IFREG, "-d": stat.S_IFDIR, "-l": stat.S_IFLNK, "-c": stat.S_IFCHR}
    cases = []
    for name, mode, target in value["file_context_cases"]:
        cases.append((name, kind[mode], target))
        cases.extend((name, other, None) for other in kind.values() if other != kind[mode])
        cases.extend((name + suffix, kind[mode], None) for suffix in ("-other", ".old", "/child"))
    cases.extend((name, stat.S_IFCHR, None) for name in Z_ONLY_DEVICE_NAMES)
    cases += [("/usr/bin/systemd-sysusers", stat.S_IFREG, "p4_linux_setup_exec_t"),
              ("/run", stat.S_IFDIR, "p4_linux_run_t"),
              ("/dev", stat.S_IFDIR, "p4_linux_native_dev_root_t"),
              ("/tmp", stat.S_IFDIR, "p4_linux_tmp_t")]
    rows = []
    try:
        for name, mode, wanted in cases:
            out = ctypes.c_char_p()
            rc = lib.selabel_lookup_raw(handle, ctypes.byref(out), name.encode(), mode)
            context = None
            if rc == 0:
                try:
                    context = out.value.decode()
                finally:
                    lib.freecon(out)
            elif ctypes.get_errno() != 2:
                raise ValueError("Tmpfiles class-aware lookup failed")
            actual = context.split(":")[2] if context else None
            if wanted is not None and actual != wanted or wanted is None and actual in NEW_TYPES:
                raise ValueError("Tmpfiles exact/adjacent file-context boundary changed: " + name)
            rows.append([name, mode, context])
    finally:
        lib.selabel_close(handle)
    return {"cases": len(rows), "rows": rows, "composed_sha256": hashlib.sha256(data).hexdigest()}
