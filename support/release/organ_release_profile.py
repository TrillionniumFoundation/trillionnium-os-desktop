#!/usr/bin/env python3
"""Pin and check one clean Hepta/OS source combination; never grant effects."""

from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile

HISTORY_OWNER = "995b6fb9ef73ada7c3348b01deb28940a2c4a2d1"
OS_ROLES = {
    "hepta_adapter", "notes_broker", "notes_core", "bootstrap_core",
    "session_entry", "session_bootstrap", "notes_app", "notes_app_target",
    "session_contract", "objective_contract", "history_contract", "cpu_contract",
    "notes_persistence", "session_ipc", "ui_workspace", "ui_lock",
    "kernel_capability", "kernel_unix_credential", "kernel_anon_budget",
    "kernel_vm_charge", "kernel_cpu_config", "kernel_credentials_edit", "kernel_rcu_idle",
}
HEPTA_ROLES = {
    "production_writer_host", "notes_channel", "notes_bootstrap", "notes_owner",
    "durable_writer", "lease_outbox", "final_use_authority", "final_use_control", "history_owner",
    "hepta_workspace", "hepta_lock", "hepta_toolchain", "production_composition",
    "protected_authority", "issuer_transport", "grant_worker",
    "notes_owner_impl", "notes_recovery", "notes_readback", "notes_first_composition",
}
GOLDEN_ROLES = {"notes_target", "notes_bootstrap", "notes_bootstrap_v2", "notes_recovery"}
OS_ROLES_V2 = OS_ROLES | {
    "desktop_core", "desktop_broker", "desktop_x11", "desktop_bootstrap",
    "objective_core", "objective_session", "objective_submission_store", "objective_panel",
    "kernel_page_budget", "kernel_page_table", "kernel_dma_domain",
    "kernel_seccomp", "kernel_seccomp_dispatch", "kernel_binder", "kernel_boot_id",
    "kernel_trusted_roles", "desktop_owner_fixture", "objective_owner_fixture",
}
HEPTA_ROLES_V2 = HEPTA_ROLES | {
    "desktop_wire", "desktop_owner", "desktop_channel", "desktop_bootstrap",
    "private_organ_owner", "agentd_entry", "hos2_device", "hos2_owner",
    "root_entry", "root_service", "root_runtime", "root_config", "root_writer",
    "root_checkpoint", "root_consumer_frontier", "root_issuer", "root_clock",
    "root_frontier", "cognitive_commit_gate", "cognitive_checkpoint",
    "sqlite_pool_guard", "protected_writer_host", "cognitive_checkpoint_bind",
}
GOLDEN_ROLES_V2 = GOLDEN_ROLES | {"desktop_x11"}
OS_ROLES_V3 = OS_ROLES_V2 | {
    'kernel_policy_authorization_contract',
    'kernel_policy_authorization_probe',
    'kernel_policy_authorization_runner',
    'kernel_policy_setattr',
    'kernel_policy_setparam',
    'kernel_policy_setscheduler',
    'kernel_policy_syscall_access',
    'kernel_affinity_contract',
    'kernel_affinity_owner',
    'kernel_affinity_probe',
    'kernel_affinity_runner',
    'session_development_contract',
    'session_observer_oracle',
    'session_reconnect_oracle',
    'hos2_control_owner',
    'hos2_native_dispatch',
    'hos2_wire',
    'kernel_android_development_entry',
    'kernel_binder_byte_probe',
    'kernel_binder_cleanup_probe',
    'kernel_binder_contract',
    'kernel_binder_death_owner',
    'kernel_binder_death_probe',
    'kernel_binder_development',
    'kernel_binder_file_owner',
    'kernel_binder_file_probe',
    'kernel_binder_object_owner',
    'kernel_binder_object_probe',
    'kernel_binder_object_runner',
    'kernel_binder_uapi',
    'kernel_boot_dispatch',
    'kernel_bounded_qemu_runner',
    'kernel_build_entry',
    'kernel_build_profile',
    'kernel_cgroup_page_exports',
    'kernel_clone_policy_publish',
    'kernel_credential_snapshot',
    'kernel_elf_aux_headers',
    'kernel_elf_profile_wiring',
    'kernel_ext2_directory_creation',
    'kernel_ext2_inode_initialization',
    'kernel_fair_runtime',
    'kernel_fair_runtime_contract',
    'kernel_fair_runtime_development',
    'kernel_fair_runtime_oracle',
    'kernel_fair_runtime_probe',
    'kernel_fair_runtime_runner',
    'kernel_futex_completion_queue',
    'kernel_futex_syscall_dispatch',
    'kernel_g2_build_profile_oracle',
    'kernel_g2_elf_profile',
    'kernel_g2_loader_contract',
    'kernel_group_stop_contract',
    'kernel_group_stop_probe',
    'kernel_group_stop_runner',
    'kernel_guest_archive_helpers',
    'kernel_guest_safety_runner',
    'kernel_guest_safety_runner_oracle',
    'kernel_hos2_device',
    'kernel_initial_image_seal',
    'kernel_inode_creation_exports',
    'kernel_inode_creation_owner',
    'kernel_inode_permission_dispatch',
    'kernel_inode_permission_transaction',
    'kernel_interruptible_group_stop',
    'kernel_ipc_memory_contract',
    'kernel_ipc_memory_probe',
    'kernel_ipc_memory_runner',
    'kernel_ipc_memory_test_contract',
    'kernel_ipc_ring_allocation',
    'kernel_ipc_source_profile_oracle',
    'kernel_ordinary_product_runner',
    'kernel_ordinary_product_runner_oracle',
    'kernel_owned_ext2_fixture',
    'kernel_page_budget_oracle',
    'kernel_page_memory_contract',
    'kernel_page_memory_probe',
    'kernel_page_memory_runner',
    'kernel_pending_signal_dispatch',
    'kernel_pipe_buffer_owner',
    'kernel_posix_signal_wait_state',
    'kernel_posix_task_builder',
    'kernel_prctl_no_new_privs',
    'kernel_private_signal_pending',
    'kernel_proc_credential_status',
    'kernel_proc_status_contract',
    'kernel_proc_status_probe',
    'kernel_proc_status_runner',
    'kernel_process_group_stop',
    'kernel_process_image',
    'kernel_product_boot_oracle',
    'kernel_profile_core_manifest',
    'kernel_profile_facade_manifest',
    'kernel_ramfs_inode_creation',
    'kernel_ring_storage',
    'kernel_scheduler_class_dispatch',
    'kernel_sgid_creation_contract',
    'kernel_sgid_creation_probe',
    'kernel_sgid_creation_runner',
    'kernel_signal_queue_dequeue',
    'kernel_source_derivation',
    'kernel_stack_admission',
    'kernel_stack_mapping',
    'kernel_stack_memory_contract',
    'kernel_supplementary_group_set',
    'kernel_sysv_semaphore_queue',
    'kernel_sysv_semaphore_wait',
    'kernel_task_stack_publish',
    'kernel_thread_fallible_preparation',
    'kernel_tmpfs_ramfs_wiring',
    'kernel_trusted_image_prepare',
    'kernel_trusted_initial_loader',
    'kernel_unix_socketpair_dispatch',
    'kernel_unix_stream_connection',
    'kernel_unix_stream_control_manifest',
    'kernel_unix_stream_initial_state',
    'kernel_unix_stream_listener',
    'kernel_unix_stream_oracle',
    'kernel_unix_stream_probe',
    'kernel_unix_stream_protocol',
    'kernel_unix_stream_race_fixed_control',
    'kernel_unix_stream_race_stale_control',
    'kernel_unix_stream_regression_contract',
    'kernel_unix_stream_runner_oracle',
    'kernel_unix_stream_socket',
    'kernel_unix_stream_zero_progress_control',
    'kernel_user_return_stop_loop',
    'kernel_wait_timeout',
    'kernel_waiter_notification',
    'ci_a02_acceptance_oracle',
    'ci_a02_acceptance_runner',
    'ci_a02_workflow',
    'ci_a05_effect_path_oracle',
    'ci_a06_accounting_source_oracle',
    'ci_a06_workflow',
    'kernel_entropy_device_memory',
    'kernel_entropy_getrandom',
    'kernel_entropy_source',
    'kernel_live_device_misc_mod',
    'kernel_live_fs_fs_impls_cgroupfs_controller_cpu_group_entity_regressions',
    'kernel_live_fs_fs_impls_cgroupfs_controller_cpu_max_config',
    'kernel_live_fs_fs_impls_cgroupfs_controller_cpu_native',
    'kernel_live_fs_fs_impls_cgroupfs_controller_cpu_native_trusted_control',
    'kernel_live_fs_fs_impls_cgroupfs_controller_cpu_scheduler_handoff_regressions',
    'kernel_live_fs_fs_impls_cgroupfs_controller_mod',
    'kernel_live_fs_fs_impls_procfs_pid_task_stat',
    'kernel_live_fs_utils_endpoint',
    'kernel_live_lib',
    'kernel_live_process_posix_thread_exit',
    'kernel_live_process_test_util',
    'kernel_live_sched_mod',
    'kernel_live_sched_nice',
    'kernel_live_sched_sched_class_administration',
    'kernel_live_sched_sched_class_administration_tests',
    'kernel_live_sched_sched_class_affinity',
    'kernel_live_sched_sched_class_capacity',
    'kernel_live_sched_sched_class_capacity_tests',
    'kernel_live_sched_sched_class_clock',
    'kernel_live_sched_sched_class_fair_group',
    'kernel_live_sched_sched_class_fair_group_capacity_tests',
    'kernel_live_sched_sched_class_fair_group_prepare',
    'kernel_live_sched_sched_class_idle',
    'kernel_live_sched_sched_class_policy',
    'kernel_live_sched_sched_class_real_time',
    'kernel_live_sched_sched_class_real_time_capacity_tests',
    'kernel_live_sched_sched_class_real_time_removal_tests',
    'kernel_live_sched_sched_class_request',
    'kernel_live_sched_sched_class_request_tests',
    'kernel_live_sched_sched_class_stop',
    'kernel_live_sched_sched_class_switch_tests',
    'kernel_live_sched_sched_class_time',
    'kernel_live_sched_sched_class_transfer',
    'kernel_live_sched_sched_class_transfer_tests',
    'kernel_live_sched_stats_loadavg',
    'kernel_live_sched_stats_mod',
    'kernel_live_sched_stats_scheduler_stats',
    'kernel_live_syscall_get_priority',
    'kernel_live_syscall_sched_getparam',
    'kernel_live_syscall_sched_getscheduler',
    'kernel_live_syscall_sched_permissions',
    'kernel_live_syscall_set_priority',
    'kernel_live_thread_mod',
    'kernel_permission_smp_oracle',
    'kernel_runtime_handoff_drop_tail_control',
    'kernel_runtime_handoff_eligibility_control',
    'kernel_runtime_negative_oracle',
    'kernel_runtime_negative_runner',
    'kernel_switch_dequeue_owner_control',
    'module_documentation_audit_json',
    'module_documentation_audit_markdown',
    'module_documentation_public_evidence',
    'ostd_live_irq_guard',
    'ostd_live_sync_guard',
    'ostd_live_sync_mutex',
    'ostd_live_sync_spin',
    'ostd_live_task_atomic_mode',
    'ostd_live_task_preempt_cpu_local',
    'ostd_live_task_preempt_guard',
    'ostd_live_task_processor',
    'ostd_live_task_scheduler_info',
    'ostd_live_task_scheduler_mod',
    'ostd_live_task_scheduler_switch_tests',
    'receiving_support_android_binder_threads_md',
    'receiving_support_kernel_safety_affinity_capacity_md',
    'receiving_support_kernel_safety_fair_group_entities_md',
    'receiving_support_kernel_safety_forced_affinity_md',
    'receiving_support_kernel_safety_scheduling_permissions_md',
    'receiving_support_kernel_safety_task_switch_handoff_md',
    'receiving_tests_kernel_binder_thread_fixture_h',
    'receiving_tests_kernel_binder_thread_lifetime_probe',
    'receiving_tests_kernel_binder_thread_probe',
    'receiving_tests_kernel_binder_thread_run',
    'receiving_tests_kernel_binder_thread_work_probe',
    'receiving_tests_kernel_forced_affinity_probe',
    'receiving_tests_kernel_forced_affinity_readme_md',
    'receiving_tests_kernel_forced_affinity_rt_admin_probe',
    'receiving_tests_kernel_forced_affinity_run',
    'receiving_tests_kernel_network_controls_ipc_memory_v1_source_json_gz',
    'receiving_tests_kernel_network_receiving_force_profile_md',
    'receiving_tests_kernel_network_run_unix_stream_receiving_guest',
    'receiving_tests_kernel_network_test_receiving_source_profile',
    'receiving_tests_kernel_priority_inheritance_probe',
    'receiving_tests_kernel_priority_inheritance_readme_md',
    'receiving_tests_kernel_priority_inheritance_run',
    'receiving_tests_kernel_sched_policy_limits_probe',
    'receiving_tests_kernel_sched_policy_limits_readme_md',
    'receiving_tests_kernel_sched_policy_limits_run',
    'receiving_tests_kernel_task_handoff_probe',
    'receiving_tests_kernel_task_handoff_readme_md',
    'receiving_tests_kernel_task_handoff_run',
    'ui_development_contract',
    'ci_a08_host_workflow',
    'kernel_android_source_audit_oracle',
}
HEPTA_ROLES_V3 = HEPTA_ROLES_V2 | {
    'agentd_recovered_writer_oracle',
    'agentd_arg0_dispatch',
    "root_launch", "root_writer_proof", "root_issuer_client", "cognitive_store_entry",
    "agent_protocol_entry", "agent_protocol_history", "learning_ledger_entry", "learning_run_start",
    'agentd_checkpoint_transport',
    'agentd_module_wiring',
    'cognitive_active_read_only_oracle',
    'cognitive_checkpoint_wire',
    'cognitive_current_publisher',
    'cognitive_read_only_recovery',
    'cognitive_recovery_anchor',
    'cognitive_wal_read_only_oracle',
    'native_build_receipt_oracle',
    'native_complete_oracle',
    'native_historical_observation_contract',
    'native_history_oracle',
    'native_history_runner',
    'native_owner_agent',
    'native_owner_boot',
    'native_owner_contract',
    'native_owner_entry',
    'native_owner_history',
    'native_owner_manifest',
    'native_owner_root',
    'native_owner_runner',
    'native_qualification_runner_contract',
    'native_root_composition_contract',
    'protected_current_publication',
    'protected_current_publication_oracle',
    'retained_historical_operation',
    'root_authority_session',
    'root_authority_session_oracle',
    'root_checkpoint_lane',
    'root_checkpoint_publisher',
    'root_checkpoint_state',
    'root_composition',
    'root_observation_cache',
    'root_observation_cache_oracle',
    'root_observation_diagnostic',
    'root_observation_stream',
    'root_observation_stream_oracle',
    'sqlite_cold_image',
    'sqlite_recovery_guard',
    'sqlite_recovery_image_oracle',
    'sqlite_wal_observer',
    'automation_converged_migration',
    'automation_destination_migration',
    'automation_dispatch_migration',
    'automation_integration_oracle',
    'automation_migration_0003',
    'automation_migration_0004',
    'automation_migration_0005',
    'automation_migration_0006',
    'automation_migration_0007',
    'automation_migration_0008',
    'automation_migration_0009',
    'automation_migration_0010',
    'automation_migration_0011',
    'automation_migration_0012',
    'automation_migration_0013',
    'automation_migration_0014',
    'automation_migration_0015',
    'automation_migration_0016',
    'automation_migration_convergence_oracle',
    'automation_original_v1_migration',
    'automation_store_owner',
    'automation_timer_migration',
    'fleet_immutable_release_owner',
    'fleet_release_copy_oracle',
    'git_process_fixture',
    'hepta_test_execution_policy',
    'memory_federation_fixture',
    'supervisor_intent_codec',
    'supervisor_intent_recovery_cli',
    'supervisor_manifest',
    'supervisor_owner',
    'supervisor_pairs_oracle',
    'supervisor_process_driver',
    'supervisor_process_recovery',
    'supervisor_protocol',
    'supervisor_protocol_gate',
    'supervisor_recovery_runbook',
    'supervisor_release_transaction',
    'supervisor_restart_budget_oracle',
    'supervisor_restart_recovery_oracle',
    'supervisor_signed_authority',
    'supervisor_signed_recovery_oracle',
    'supervisor_technical_contract',
    'deployment_issuer',
    'deployment_issuer_oracle',
    'deployment_issuer_root',
    'deployment_issuer_root_oracle',
    'production_authority_oracle',
    'root_owner_status_oracle',
    'root_owner_status_predicate',
    'root_clock_observation_oracle',
    'root_service_contract',
}
GOLDEN_ROLES_V3 = GOLDEN_ROLES_V2

# Schema4 is a new closed contract. Historical role sets/maps are unchanged.
OS_ROLES_V4 = OS_ROLES_V3 | {
    'release_current_pair_ci',
    'release_previous_current_v3_archive',
    'release_source_contract_ci',
    'kernel_cgroup_membership_tree',
    'kernel_cpu_bandwidth_contract',
    'kernel_cpu_scheduling_route',
    'kernel_vdso_cpu_identity_contract',
    'kernel_vdso_cpu_probe_contract',
    'kernel_vdso_cpu_probe_runner',
    'kernel_vdso_cpu_probe_source',
    'ostd_page_table_activation',
    'ostd_page_table_node_ownership',
    'ostd_vmspace_retirement_oracle',
    'ostd_x86_gdt',
    'ostd_x86_gdt_oracle',
    'release_development_contract',
    'release_pair_execution_oracle',
    'release_pair_execution_tool',
    'release_schema4_oracle',
    'release_source_map_v4',
    'release_source_profile_oracle',
    'release_source_profile_tool',
    'release_technical_contract',
    'unix_cpunode_fixture_exporter',
    'unix_cpunode_guest_runner',
    'unix_cpunode_historical_fixture',
    'unix_cpunode_profile_contract',
    'unix_cpunode_profile_oracle',
    'unix_post1138_fixture_exporter',
    'unix_post1138_guest_runner',
    'unix_post1138_historical_fixture',
    'unix_post1138_profile_oracle',
    'unix_receiving_fixture_exporter',
    'unix_receiving_historical_fixture',
    'unix_retirement_guest_runner',
    'unix_retirement_profile_contract',
    'unix_retirement_profile_oracle',
    'vmspace_retirement_contract',
}
HEPTA_ROLES_V4 = HEPTA_ROLES_V3 | {
    'agentd_checkpoint_unix_oracle',
    'agentd_mainline_convergence_contract',
    'agentd_runtime_task_wiring',
    'app_server_exports_experimental',
    'app_server_exports_stable',
    'app_server_protocol_schema_contract',
    'app_server_turn_recovery_wire',
    'bazel_dependency_lock',
    'cognitive_checkpoint_diagnostic',
    'cognitive_checkpoint_diagnostic_oracle',
    'cognitive_checkpoint_suite',
    'cognitive_memory_module_root',
    'core_plugins_startup_archive_oracle',
    'core_plugins_startup_archive_owner',
    'dependency_security_contract',
    'kernel_authority_boundary_contract',
    'kernel_authority_boundary_inventory',
    'kernel_authority_callers_oracle',
    'objective_sender_fixture_support',
    'rollout_compression_oracle',
    'rollout_fixture_contract',
    'rollout_fixture_support',
    'rollout_metadata_oracle',
    'rollout_module_root',
    'rollout_recorder_oracle',
    'rollout_reference_index_oracle',
    'rollout_reference_suite',
    'rollout_session_index_oracle',
    'rollout_state_db_oracle',
    'root_authority_progress_oracle',
    'root_host_checkpoint_clock_oracle',
    'root_observation_progress_oracle',
    'root_observation_progress_owner',
    'root_observation_task_label_oracle',
    'runtime_callers_inventory',
    'thread_store_archive_owner',
    'thread_store_delete_owner',
    'thread_store_development_contract',
    'thread_store_fixture_support',
    'thread_store_history_materialization_oracle',
    'thread_store_history_read_oracle',
    'thread_store_list_owner',
    'thread_store_local_module',
    'thread_store_metadata_update_owner',
    'thread_store_model_context_oracle',
    'thread_store_pending_metadata_oracle',
    'thread_store_read_owner',
    'thread_store_revert_oracle',
    'thread_store_rollout_lineage_oracle',
    'thread_store_rollout_migration_oracle',
    'thread_store_rollout_migration_startup_oracle',
    'thread_store_sections_oracle',
    'thread_store_unarchive_owner',
    'thread_store_writer_lock_oracle',
    'zstd_windows_include_patch',
}
GOLDEN_ROLES_V4 = GOLDEN_ROLES_V3
SOURCE_MAP_V4_SHA256 = '1cf6ecf0e6c3e715bef7f50f80cee25522c00dde1cab22ac52ed82bf1f1ae38d'



# Schema5 is a distinct fixed 396/261 contract. V1-V4 stay unchanged.
OS_ROLES_V5 = OS_ROLES_V4 | {
    'module_documentation_current_inventory',
    'module_documentation_current_technical_development',
    'oom_oom_prerequisite_00_oom_adjustment_rs',
    'oom_oom_prerequisite_01_tests_rs',
    'oom_oom_prerequisite_02_mod_rs',
    'oom_oom_prerequisite_04_mod_rs',
    'oom_oom_prerequisite_07_exit_rs',
    'oom_oom_prerequisite_08_execve_rs',
    'oom_oom_prerequisite_12_credentials_rs',
    'oom_oom_prerequisite_13_capabilities_rs',
    'oom_oom_prerequisite_14_c_types_rs',
    'oom_oom_prerequisite_15_user_rs',
    'oom_oom_prerequisite_16_user_ns_rs',
    'oom_oom_prerequisite_17_capability_rs',
    'oom_oom_prerequisite_19_mod_rs',
    'oom_oom_prerequisite_20_oom_score_adj_rs',
    'oom_oom_prerequisite_21_mod_rs',
    'oom_oom_prerequisite_22_mod_rs',
    'oom_oom_prerequisite_23_file_rs',
    'oom_oom_prerequisite_24_capget_rs',
    'oom_oom_prerequisite_25_capset_rs',
    'oom_oom_prerequisite_26_setresuid_rs',
    'oom_oom_prerequisite_27_setresgid_rs',
    'oom_oom_prerequisite_28_clone_rs',
    'oom_oom_prerequisite_29_fork_rs',
    'oom_oom_prerequisite_30_execve_rs',
    'oom_oom_prerequisite_31_exit_rs',
    'oom_oom_prerequisite_32_exit_group_rs',
    'oom_oom_prerequisite_34_pwrite64_rs',
    'oom_oom_prerequisite_35_pread64_rs',
    'oom_oom_prerequisite_36_oom_adjustment_md',
    'oom_oom_prerequisite_37_run_py',
    'oom_oom_prerequisite_38_check_py',
    'oom_oom_prerequisite_40_probe_c',
    'oom_oom_prerequisite_41_run_py',
    'oom_oom_prerequisite_42_test_run_py',
    'oom_oom_prerequisite_43_readme_md',
    'oom_oom_prerequisite_46_post1138_unix_signal_v2_source_json_gz',
    'oom_oom_prerequisite_47_test_oom_source_profile_py',
    'oom_oom_prerequisite_48_post1138_oom_adjustment_profile_md',
    'oom_oom_profile_wrapper',
    'release_previous_current_v4_archive',
    'release_schema5_oracle',
    'release_source_map_v5',
    'unix_signal_contract_compat_file_and_directory_operations_README_md',
    'unix_signal_contract_compat_file_and_directory_operations_fully_covered_scml',
    'unix_signal_contract_compat_networking_and_sockets_README_md',
    'unix_signal_contract_compat_networking_and_sockets_sendto_and_sendmsg_scml',
    'unix_signal_contract_unix_signal',
    'unix_signal_fixed_source_oracle',
    'unix_signal_fixed_source_wrapper',
    'unix_signal_oracle_unix_signal_README_md',
    'unix_signal_oracle_unix_signal_probe_c',
    'unix_signal_oracle_unix_signal_run_py',
    'unix_signal_oracle_unix_signal_test_run_py',
    'unix_signal_profile_technical_contract',
    'unix_signal_retirement_source_archive',
    'unix_signal_retirement_source_exporter',
    'unix_signal_unix_signal_dependency_current_thread_cast',
    'unix_signal_unix_signal_dependency_errno_conversion',
    'unix_signal_unix_signal_dependency_filelike_downcast',
    'unix_signal_unix_signal_dependency_send_flags',
    'unix_signal_unix_signal_dependency_sendmsg_entry',
    'unix_signal_unix_signal_dependency_sendto_entry',
    'unix_signal_unix_signal_dependency_socket_filelike_write',
    'unix_signal_unix_signal_dependency_unix_public_reexport',
    'unix_signal_unix_signal_dependency_unix_stream_reexport',
    'unix_signal_unix_signal_dependency_user_iovec',
    'unix_signal_unix_signal_module_c_types',
    'unix_signal_unix_signal_module_constants',
    'unix_signal_unix_signal_module_poll',
    'unix_signal_unix_signal_module_sig_action',
    'unix_signal_unix_signal_module_sig_disposition',
    'unix_signal_unix_signal_module_sig_mask',
    'unix_signal_unix_signal_module_sig_num',
    'unix_signal_unix_signal_module_sig_stack',
    'unix_signal_unix_signal_module_signals_fault',
    'unix_signal_unix_signal_module_signals_kernel',
    'unix_signal_unix_signal_module_signals_mod',
    'unix_signal_unix_signal_module_signals_raw',
    'unix_signal_unix_signal_module_signals_seccomp',
    'unix_signal_unix_signal_module_signals_user',
    'unix_signal_unix_signal_sendmmsg_entry',
    'unix_signal_unix_signal_writev_entry',
}
HEPTA_ROLES_V5 = HEPTA_ROLES_V4 | {
    'authority_lease_concurrency_contract',
    'authority_lease_entry_clock_oracles',
    'authority_lease_owner',
    'authority_lease_pair_boundary_owner',
    'authority_lease_shared_fence_oracles',
    'authority_lease_state_owner',
    'mcp_c37_profile_regression_baseline',
    'mcp_cli_protocol_runner',
    'mcp_cli_protocol_runner_oracles',
    'mcp_conformance_runbook',
    'mcp_execution_identity_contract',
    'mcp_oauth_reuse_negative',
    'mcp_official_adapter',
    'mcp_official_runner',
    'mcp_official_runner_oracles',
    'mcp_profile_development_contract',
    'mcp_profile_execution_verifier',
    'mcp_profile_reader',
    'mcp_profile_reader_oracles',
    'mcp_profile_regression_reviewer',
    'mcp_profile_verifier_oracles',
    'mcp_security_reference_patch',
    'mcp_upstream_descriptor',
    'mcp_upstream_package_lock',
    'mcp_vendor_cli_entrypoint',
    'mcp_vendor_development_contract',
    'mcp_vendor_execution_descriptor',
    'mcp_vendor_lock',
    'mcp_vendor_manifest',
    'mcp_vendor_source_verifier',
    'mcp_vendor_verifier_oracles',
    'rmcp_oauth_discovery_contract',
    'rmcp_oauth_discovery_http_client',
    'rmcp_oauth_http_challenge_adapter',
    'rmcp_oauth_login_route',
    'rmcp_oauth_registration_oracles',
    'rmcp_oauth_registration_owner',
    'root_failure_report',
    'root_observation_isolation_oracles',
    'root_observation_worker_owner',
    'sdk_child_lifecycle_contract',
    'sdk_ci_workflow',
    'sdk_exec_oracles',
    'sdk_exec_owner',
    'sdk_fixture_home_setup',
    'sdk_fixture_lifecycle_contract',
    'sdk_fixture_lifecycle_oracles',
    'sdk_mcp_conformance_oracles',
    'sdk_owned_child_lifecycle_oracles',
    'sdk_owned_home_owner',
    'sdk_peer_context_config',
    'sdk_peer_dependency_hook',
    'sdk_root_git_attributes',
    'sdk_typescript_manifest',
    'sdk_workspace_lock',
    'sdk_workspace_manifest',
    'sdk_workspace_members',
    'sqlite_startup_development_guide',
    'sqlite_startup_oracles',
    'sqlite_startup_runtime',
}
GOLDEN_ROLES_V5 = GOLDEN_ROLES_V4
SOURCE_MAP_V5_SHA256 = '00d8060c5e56e0d4f268f37fdb4bea53246dac122836b88b79cd11bc6dd9bc9c'


def roles_for_version(version):
    if type(version) is not int or version not in (1, 2, 3, 4, 5):
        raise ProfileError("unsupported source map schema_version")
    if version == 5:
        return OS_ROLES_V5, HEPTA_ROLES_V5, GOLDEN_ROLES_V5
    if version == 4:
        return OS_ROLES_V4, HEPTA_ROLES_V4, GOLDEN_ROLES_V4
    if version == 3:
        return OS_ROLES_V3, HEPTA_ROLES_V3, GOLDEN_ROLES_V3
    if version == 2:
        return OS_ROLES_V2, HEPTA_ROLES_V2, GOLDEN_ROLES_V2
    return OS_ROLES, HEPTA_ROLES, GOLDEN_ROLES


def source_map_name(version):
    roles_for_version(version)
    return {1: "organ_source_map.json", 2: "organ_source_map_v2.json",
            3: "organ_source_map_v3.json", 4: "organ_source_map_v4.json",
            5: "organ_source_map_v5.json"}[version]

PRODUCTION = {
    "activation": "disabled",
    "effects_authorized": False,
    "unconfigured": [
        "production_grant_provider",
        "protected_authority_clock",
        "external_authority_frontier_store",
        "trusted_issuer_keyring",
        "revocation_head",
        "recovered_writer_configuration",
        "current_cut_authorization_state",
    ],
}


class ProfileError(Exception):
    """An input or source check did not establish a qualified combination."""


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def full_oid(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ProfileError(f"{label} must be a full lowercase 40-hex Git identity")
    return value


def json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProfileError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json_bytes(data, label):
    try:
        return json.loads(data, object_pairs_hook=json_object)
    except ValueError as exc:
        raise ProfileError(f"cannot parse JSON {label}: {exc}") from exc


def load_json(path):
    try:
        return load_json_bytes(Path(path).read_bytes(), path)
    except OSError as exc:
        raise ProfileError(f"cannot read JSON {path}: {exc}") from exc


def source_path(value, label):
    if not isinstance(value, str) or not value:
        raise ProfileError(f"source map unresolved: {label}")
    path = PurePosixPath(value)
    if (path.is_absolute() or ".." in path.parts or str(path) != value
            or "\\" in value or ":" in value or "\x00" in value):
        raise ProfileError(f"invalid repository-relative source path for {label}: {value!r}")
    return value


def check_map(mapping):
    if not isinstance(mapping, dict) or set(mapping) != {"schema_version", "sources", "goldens"}:
        raise ProfileError("source map requires schema_version, sources, and goldens only")
    os_roles, hepta_roles, golden_roles = roles_for_version(mapping["schema_version"])
    sources = mapping["sources"]
    if not isinstance(sources, dict) or set(sources) != {"os", "hepta"}:
        raise ProfileError("source map requires both os and hepta sources")
    for name, roles in (("os", os_roles), ("hepta", hepta_roles)):
        entries = sources[name]
        if not isinstance(entries, dict) or set(entries) != roles:
            if mapping["schema_version"] == 5:
                raise ProfileError(f"unsupported source map: schema5 requires exactly these {name} roles: {sorted(roles)}")
            raise ProfileError(f"source map requires exactly these {name} roles: {sorted(roles)}")
        for role, path in entries.items():
            source_path(path, f"{name}.{role}")
        if len(set(entries.values())) != len(entries):
            raise ProfileError(f"{name} source roles must name distinct files")
    goldens = mapping["goldens"]
    if not isinstance(goldens, dict) or set(goldens) != golden_roles:
        raise ProfileError(f"source map requires exactly these golden roles: {sorted(golden_roles)}")
    for role, paths in goldens.items():
        if not isinstance(paths, dict) or set(paths) != {"os", "hepta"}:
            raise ProfileError(f"golden {role} requires os and hepta paths")
        for name, path in paths.items():
            source_path(path, f"{role}.{name}")
    for name in ("os", "hepta"):
        if len({paths[name] for paths in goldens.values()}) != len(golden_roles):
            raise ProfileError(f"{name} golden roles must name distinct files")
    if mapping["schema_version"] == 4 and sha256(canonical(mapping)) != SOURCE_MAP_V4_SHA256:
        raise ProfileError("schema4 source map differs from the code-owned literal path contract")

    if mapping["schema_version"] == 5 and sha256(canonical(mapping)) != SOURCE_MAP_V5_SHA256:
        raise ProfileError("schema5 source map differs from the code-owned literal path contract")


def check_current_contract(manifest, mapping):
    """Check the current V4 declaration before selecting its Hepta checkout.

    This gate returns the declared pin, not a source qualification. Actual
    repository bytes, clean identities and original ancestry still require
    verify_manifest with both repositories.
    """
    check_map(mapping)
    if mapping["schema_version"] != 4:
        raise ProfileError("current contract requires the fixed schema4 map")
    expected_keys = {"schema_version", "qualification", "os_identity_binding", "hepta",
                     "original_history_owner", "source_map_sha256", "production", "sources", "goldens"}
    if not isinstance(manifest, dict) or set(manifest) != expected_keys:
        raise ProfileError("current contract requires the exact source-manifest fields")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 4:
        raise ProfileError("current contract requires schema4; historical profiles need an explicit historical path")
    if (manifest["qualification"] != "source-only"
            or manifest["os_identity_binding"] != "explicit_caller_head_and_tree_in_verification_receipt"
            or manifest["original_history_owner"] != HISTORY_OWNER
            or manifest["source_map_sha256"] != SOURCE_MAP_V4_SHA256):
        raise ProfileError("current contract identity, history owner or map seal differs")
    if canonical(manifest["production"]) != canonical(PRODUCTION):
        raise ProfileError("current contract must retain all seven disabled production inputs")
    hepta = manifest["hepta"]
    if not isinstance(hepta, dict) or set(hepta) != {"commit", "tree"}:
        raise ProfileError("current contract requires one exact Hepta commit/tree")
    for kind in ("commit", "tree"):
        full_oid(hepta[kind], f"current Hepta {kind}")

    def digest_and_size(row, label):
        if not isinstance(row["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise ProfileError(f"current contract has an invalid {label} SHA256")
        if type(row["bytes"]) is not int or row["bytes"] < 0:
            raise ProfileError(f"current contract has an invalid {label} size")

    sources = manifest["sources"]
    if not isinstance(sources, dict) or set(sources) != {"os", "hepta"}:
        raise ProfileError("current contract requires both source role sets")
    for side in ("os", "hepta"):
        rows = sources[side]
        if not isinstance(rows, list) or len(rows) != len(mapping["sources"][side]):
            raise ProfileError(f"current contract has an incomplete {side} role set")
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"role", "path", "git_blob", "sha256", "bytes"}:
                raise ProfileError(f"current contract has invalid {side} source fields")
            role = row["role"]
            if not isinstance(role, str) or role in seen or role not in mapping["sources"][side]:
                raise ProfileError(f"current contract has an unknown or duplicate {side} role")
            seen.add(role)
            if row["path"] != mapping["sources"][side][role]:
                raise ProfileError(f"current contract changes the reviewed {side}.{role} path")
            full_oid(row["git_blob"], f"current {side}.{role} blob")
            digest_and_size(row, f"{side}.{role}")
    rows = manifest["goldens"]
    if not isinstance(rows, list) or len(rows) != len(mapping["goldens"]):
        raise ProfileError("current contract requires all five golden pairs")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"role", "os_path", "hepta_path", "sha256", "bytes"}:
            raise ProfileError("current contract has invalid golden fields")
        role = row["role"]
        if not isinstance(role, str) or role in seen or role not in mapping["goldens"]:
            raise ProfileError("current contract has an unknown or duplicate golden role")
        seen.add(role)
        if any(row[f"{side}_path"] != mapping["goldens"][role][side] for side in ("os", "hepta")):
            raise ProfileError(f"current contract changes golden {role} paths")
        digest_and_size(row, role)
    return hepta["commit"]


def check_current_contract_v5(manifest, mapping):
    """Check the current V5 declaration before selecting its Hepta checkout.

    This gate returns the declared pin, not a source qualification. Actual
    repository bytes, clean identities and original ancestry still require
    verify_manifest with both repositories.
    """
    check_map(mapping)
    if mapping["schema_version"] != 5:
        raise ProfileError("current contract requires the fixed schema5 map")
    expected_keys = {"schema_version", "qualification", "os_identity_binding", "hepta",
                     "original_history_owner", "source_map_sha256", "production", "sources", "goldens"}
    if not isinstance(manifest, dict) or set(manifest) != expected_keys:
        raise ProfileError("current contract requires the exact source-manifest fields")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 5:
        raise ProfileError("current contract requires schema5; historical profiles need an explicit historical path")
    if (manifest["qualification"] != "source-only"
            or manifest["os_identity_binding"] != "explicit_caller_head_and_tree_in_verification_receipt"
            or manifest["original_history_owner"] != HISTORY_OWNER
            or manifest["source_map_sha256"] != SOURCE_MAP_V5_SHA256):
        raise ProfileError("current contract identity, history owner or map seal differs")
    if canonical(manifest["production"]) != canonical(PRODUCTION):
        raise ProfileError("current contract must retain all seven disabled production inputs")
    hepta = manifest["hepta"]
    if not isinstance(hepta, dict) or set(hepta) != {"commit", "tree"}:
        raise ProfileError("current contract requires one exact Hepta commit/tree")
    for kind in ("commit", "tree"):
        full_oid(hepta[kind], f"current Hepta {kind}")

    def digest_and_size(row, label):
        if not isinstance(row["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise ProfileError(f"current contract has an invalid {label} SHA256")
        if type(row["bytes"]) is not int or row["bytes"] < 0:
            raise ProfileError(f"current contract has an invalid {label} size")

    sources = manifest["sources"]
    if not isinstance(sources, dict) or set(sources) != {"os", "hepta"}:
        raise ProfileError("current contract requires both source role sets")
    for side in ("os", "hepta"):
        rows = sources[side]
        if not isinstance(rows, list) or len(rows) != len(mapping["sources"][side]):
            raise ProfileError(f"current contract has an incomplete {side} role set")
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"role", "path", "git_blob", "sha256", "bytes"}:
                raise ProfileError(f"current contract has invalid {side} source fields")
            role = row["role"]
            if not isinstance(role, str) or role in seen or role not in mapping["sources"][side]:
                raise ProfileError(f"current contract has an unknown or duplicate {side} role")
            seen.add(role)
            if row["path"] != mapping["sources"][side][role]:
                raise ProfileError(f"current contract changes the reviewed {side}.{role} path")
            full_oid(row["git_blob"], f"current {side}.{role} blob")
            digest_and_size(row, f"{side}.{role}")
    rows = manifest["goldens"]
    if not isinstance(rows, list) or len(rows) != len(mapping["goldens"]):
        raise ProfileError("current contract requires all five golden pairs")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"role", "os_path", "hepta_path", "sha256", "bytes"}:
            raise ProfileError("current contract has invalid golden fields")
        role = row["role"]
        if not isinstance(role, str) or role in seen or role not in mapping["goldens"]:
            raise ProfileError("current contract has an unknown or duplicate golden role")
        seen.add(role)
        if any(row[f"{side}_path"] != mapping["goldens"][role][side] for side in ("os", "hepta")):
            raise ProfileError(f"current contract changes golden {role} paths")
        digest_and_size(row, role)
    return hepta["commit"]

class _TreeEntryStream:
    """Decode bounded tree headers; retain typed edges, never tree/blob bodies."""

    HEADER_LIMIT = 1024 * 1024
    MODES = {b"40000": "tree", b"100644": "blob", b"100755": "blob",
             b"120000": "blob", b"160000": "commit"}

    def __init__(self):
        self.pending = bytearray()
        self.edges = []

    def feed(self, chunk):
        self.pending.extend(chunk)
        offset = 0
        while True:
            boundary = self.pending.find(b"\0", offset)
            if boundary < 0:
                break
            if boundary - offset > self.HEADER_LIMIT:
                raise ValueError("tree entry header budget exceeded")
            if len(self.pending) < boundary + 21:
                break  # The 20-byte raw object ID may cross a read boundary.
            header = self.pending[offset:boundary]
            mode, separator, name = header.partition(b" ")
            expected = self.MODES.get(bytes(mode))
            if not separator or expected is None or not name or name in (b".", b"..") or b"/" in name:
                raise ValueError("invalid tree entry mode/name framing")
            self.edges.append({"mode": mode.decode("ascii"), "expected_type": expected,
                               "oid": bytes(self.pending[boundary + 1:boundary + 21]).hex()})
            offset = boundary + 21
        if offset:
            del self.pending[:offset]
        if len(self.pending) > self.HEADER_LIMIT + 21:
            raise ValueError("tree entry header budget exceeded")

    def finish(self):
        if self.pending:
            raise ValueError("truncated tree entry mode/name/object ID")
        return self.edges


class Repository:
    def __init__(self, path, name, *, local_objects_only=False):
        self.path = Path(path).resolve()
        self.name = name
        self.local_objects_only = local_objects_only
        if local_objects_only:
            version = re.match(rb"git version (\d+)\.(\d+)", self.git("--version"))
            if not version or tuple(map(int, version.groups())) < (2, 43):
                raise ProfileError("current local-only source proof requires Git 2.43 or newer")
        top = Path(self.git("rev-parse", "--show-toplevel").decode().strip()).resolve()
        if self.path != top:
            raise ProfileError(f"{name}: specify the repository root, not a subdirectory")
        grafts = Path(self.git("rev-parse", "--git-path", "info/grafts").decode().strip())
        if not grafts.is_absolute():
            grafts = self.path / grafts
        if grafts.exists() and grafts.stat().st_size:
            raise ProfileError(f"{name}: legacy Git grafts prevent original-history proof")
        if local_objects_only:
            # Explicit current-only policy; historical readers merely disable
            # replacements and keep their original graft handling above.
            if grafts.exists() or grafts.is_symlink():
                raise ProfileError(f"{name}: current source proof rejects a graft file")
            if self.git("for-each-ref", "refs/replace/"):
                raise ProfileError(f"{name}: current source proof rejects replacement refs")

    def run(self, *args, input_bytes=None):
        env = dict(os.environ, GIT_NO_REPLACE_OBJECTS="1", GIT_TERMINAL_PROMPT="0",
                   GIT_OPTIONAL_LOCKS="0")
        if self.local_objects_only:
            env["GIT_NO_LAZY_FETCH"] = "1"
        try:
            return subprocess.run(
                ["git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
                 "-C", str(self.path), *args], input=input_bytes, capture_output=True, env=env, check=False,
            )
        except OSError as exc:
            raise ProfileError(f"{self.name}: cannot run git: {exc}") from exc

    def git(self, *args):
        result = self.run(*args)
        if result.returncode:
            detail = result.stderr.decode(errors="replace").strip()
            raise ProfileError(f"{self.name}: git {' '.join(args)} failed: {detail}")
        return result.stdout

    def check(self, head, tree):
        full_oid(head, f"{self.name} HEAD")
        full_oid(tree, f"{self.name} tree")
        actual_head = self.git("rev-parse", "--verify", "HEAD^{commit}").decode().strip()
        actual_tree = self.git("rev-parse", "--verify", "HEAD^{tree}").decode().strip()
        if actual_head != head:
            raise ProfileError(f"{self.name}: HEAD mismatch: expected {head}, found {actual_head}")
        if actual_tree != tree:
            raise ProfileError(f"{self.name}: tree mismatch: expected {tree}, found {actual_tree}")
        status = self.git("status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none")
        if status:
            raise ProfileError(f"{self.name}: dirty checkout (tracked or nonignored untracked files)")
        # These flags can hide changes from status; do not call that a clean checkout.
        flags = self.git("ls-files", "-v", "-z").split(b"\x00")
        if any(item and (item[:1].islower() or item[:1] == b"S") for item in flags):
            raise ProfileError(f"{self.name}: assume-unchanged or skip-worktree flags prevent clean proof")
        return {"commit": head, "tree": tree}

    def file(self, path):
        source_path(path, self.name)
        location = self.path / path
        if not location.is_file() or location.is_symlink() or not location.resolve().is_relative_to(self.path):
            raise ProfileError(f"{self.name}: required regular source file missing: {path}")
        entry = self.git("ls-tree", "HEAD", "--", path).decode().strip()
        fields = entry.split(None, 3)
        if len(fields) != 4 or fields[0] not in {"100644", "100755"} or fields[1] != "blob":
            raise ProfileError(f"{self.name}: required source must be a tracked regular blob: {path}")
        data = location.read_bytes()
        if data != self.git("cat-file", "blob", fields[2]):
            raise ProfileError(f"{self.name}: worktree bytes differ from HEAD blob: {path}")
        return data, {"path": path, "git_blob": fields[2], "sha256": sha256(data), "bytes": len(data)}

    def prove_history(self):
        if self.run("cat-file", "-e", f"{HISTORY_OWNER}^{{commit}}").returncode:
            raise ProfileError("hepta: original history owner object missing; ancestry unproven")
        proof = self.run("merge-base", "--is-ancestor", HISTORY_OWNER, "HEAD")
        if proof.returncode:
            raise ProfileError("hepta: original history owner ancestry unproven or nonancestor; "
                               "obtain sufficient original history, do not waive this check")
        return {"commit": HISTORY_OWNER, "method": "git merge-base --is-ancestor",
                "shallow_repository": self.git("rev-parse", "--is-shallow-repository").strip() == b"true"}

    def _typed_batch(self, objects, types, *, missing_ok=False, commit_headers=False, tree_edges=False):
        """Stream typed Git bodies and verify identities without retaining blobs."""
        env = dict(os.environ, GIT_NO_REPLACE_OBJECTS="1", GIT_TERMINAL_PROMPT="0",
                   GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1")
        command = ["git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
                   "-C", str(self.path), "cat-file", "--batch"]
        records = {}
        process = None
        try:
            with tempfile.TemporaryFile() as errors:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=errors, env=env)
                process.stdin.write("".join(oid + "\n" for oid in objects).encode())
                process.stdin.close()
                for oid in objects:
                    line = process.stdout.readline(512)
                    if not line.endswith(b"\n"):
                        raise ValueError("invalid object batch framing " + oid)
                    fields = line.split()
                    if line == oid.encode() + b" missing\n" and missing_ok:
                        records[oid] = None
                        continue
                    if (len(fields) != 3 or fields[0] != oid.encode()
                            or fields[1] not in types or not fields[2].isdigit()):
                        raise ValueError("missing or wrong type object " + oid)
                    kind, size = fields[1], int(fields[2])
                    if line != oid.encode() + b" " + kind + b" " + str(size).encode() + b"\n":
                        raise ValueError("noncanonical object batch framing " + oid)
                    value = hashlib.sha1(kind + b" " + str(size).encode() + b"\0")
                    remaining, prefix, header = size, bytearray(), None
                    tree = _TreeEntryStream() if tree_edges and kind == b"tree" else None
                    while remaining:
                        chunk = process.stdout.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError("truncated object " + oid)
                        remaining -= len(chunk)
                        value.update(chunk)
                        if tree is not None:
                            tree.feed(chunk)
                        if commit_headers and header is None:
                            prefix.extend(chunk)
                            boundary = prefix.find(b"\n\n")
                            if boundary >= 0:
                                if boundary > 1024 * 1024:
                                    raise ValueError("commit header budget exceeded " + oid)
                                header = bytes(prefix[:boundary])
                                prefix.clear()
                            elif len(prefix) > 1024 * 1024:
                                raise ValueError("commit header budget exceeded " + oid)
                    if process.stdout.read(1) != b"\n":
                        raise ValueError("invalid object body framing " + oid)
                    if value.hexdigest() != oid:
                        raise ValueError("object identity differs " + oid)
                    if commit_headers and header is None:
                        raise ValueError("commit header separator absent " + oid)
                    records[oid] = header if commit_headers else {"type": kind.decode(), "bytes": size}
                    if tree is not None:
                        records[oid]["tree_edges"] = tree.finish()
                if process.stdout.read(1):
                    raise ValueError("unexpected object batch suffix")
                if process.wait():
                    raise ValueError("Git object batch failed")
        except (OSError, ValueError) as exc:
            raise ProfileError(f"{self.name}: verified object read failed: {exc}") from exc
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                if process.stdout is not None:
                    process.stdout.close()
                if process.stdin is not None and not process.stdin.closed:
                    process.stdin.close()
        return records

    def _commit_batch(self, commits):
        raw = self._typed_batch(commits, {b"commit"}, missing_ok=True, commit_headers=True)
        records = {}
        for oid, header in raw.items():
            if header is None:
                records[oid] = None
                continue
            try:
                # Git commit structure uses LF only. splitlines() would turn
                # a bare CR inside a SHA-correct malformed body into fake edges.
                lines = header.split(b"\n")
                if not lines or not lines[0].startswith(b"tree "):
                    raise ValueError("commit tree header absent")
                tree = full_oid(lines[0][5:].decode("ascii"), "owner path tree")
                parents, index = [], 1
                # Git's real graph ends the parent block at the first other
                # header. A late parent line must never invent a proof edge.
                while index < len(lines) and lines[index].startswith(b"parent "):
                    parents.append(full_oid(lines[index][7:].decode("ascii"), "owner path parent"))
                    index += 1
                if any(line.startswith((b"parent ", b"tree ")) for line in lines[index:]):
                    raise ValueError("late parent or duplicate tree commit header")
                records[oid] = {"tree": tree, "parents": parents}
            except (ValueError, UnicodeError) as exc:
                raise ProfileError(f"{self.name}: invalid owner path commit header {oid}: {exc}") from exc
        return records

    def _owner_path(self, head, owner):
        pending, via, records = deque([head]), {head: None}, {}
        limit = 16384
        while pending and len(records) < limit:
            batch = []
            while pending and len(batch) < min(64, limit - len(records)):
                batch.append(pending.popleft())
            rows = self._commit_batch(batch)
            records.update(rows)  # Missing side objects do not discard a valid owner in the same batch.
            if owner in records and records[owner] is not None:
                path = [owner]
                while path[-1] != head:
                    path.append(via[path[-1]])
                edges, unselected = [], []
                for parent, child in zip(path, path[1:]):
                    parents = records[child]["parents"]
                    chosen = parents.index(parent)
                    edges.append({"child": child, "parent": parent, "parent_index": chosen})
                    for index, other in enumerate(parents):
                        if index == chosen:
                            continue
                        observed = ("not_read" if other not in records else
                                    "missing" if records[other] is None else "available")
                        unselected.append({"commit": child, "selected_parent": parent,
                                           "parent": other, "parent_index": index,
                                           "verification": "not_verified",
                                           "local_object_observation": observed,
                                           "tree_blob_history": "not_verified"})
                return path, edges, unselected, records, limit
            for oid, row in rows.items():
                if row is None:
                    continue
                for parent in row["parents"]:
                    if parent not in via:
                        via[parent] = oid
                        pending.append(parent)
        reason = "search budget exhausted" if pending else "no fully verified ancestry chain"
        raise ProfileError(f"{self.name}: original owner path is unproven: {reason}")

    def prove_object_closure(self, owner=None):
        """Verify one real owner path; other merge histories remain unverified."""
        if not self.local_objects_only:
            raise ProfileError("object closure requires local-only Git reads")
        if self.git("rev-parse", "--is-shallow-repository").strip() != b"false":
            raise ProfileError(f"{self.name}: current source proof requires a nonshallow repository")
        head = self.git("rev-parse", "--verify", "HEAD^{commit}").decode().strip()
        path, edges, unselected, records, limit = [], [], [], {}, None
        trees = {self.git("rev-parse", "--verify", "HEAD^{tree}").decode().strip()}
        if owner:
            path, edges, unselected, records, limit = self._owner_path(head, owner)
            trees.update(records[oid]["tree"] for oid in path)
        # Do not search another path if the first deterministic selected chain
        # has a missing tree/blob. Tree roots never walk unselected ancestry.
        objects = self.run("rev-list", "--objects", "--no-object-names", "--missing=print", "--stdin",
                           input_bytes="".join(tree + "\n" for tree in sorted(trees)).encode())
        lines = objects.stdout.splitlines()
        if objects.returncode or objects.stderr or not lines or any(line.startswith(b"?") for line in lines):
            raise ProfileError(f"{self.name}: incomplete tree/blob closure; required Git objects are unavailable")
        object_ids = sorted({full_oid(line.decode("ascii"), "tree/blob closure object") for line in lines})
        expected, actual, gitlinks, tree_edges = {oid: "tree" for oid in trees}, {}, [], 0
        for offset in range(0, len(object_ids), 64):
            rows = self._typed_batch(object_ids[offset:offset + 64], {b"tree", b"blob"}, tree_edges=True)
            for oid, row in rows.items():
                actual[oid] = row["type"]
                for index, edge in enumerate(row.get("tree_edges", [])):
                    if edge["mode"] == "160000":
                        # A submodule commit belongs to another object store.
                        # Record the opaque edge, not a proof of its target.
                        gitlinks.append({"tree": oid, "entry_index": index,
                                         "commit": edge["oid"], "verification": "not_verified"})
                        continue
                    tree_edges += 1
                    previous = expected.setdefault(edge["oid"], edge["expected_type"])
                    if previous != edge["expected_type"]:
                        raise ProfileError(f"{self.name}: conflicting tree entry object kinds")
        if set(expected) != set(object_ids):
            raise ProfileError(f"{self.name}: incomplete typed tree entry closure")
        if any(actual[oid] != kind for oid, kind in expected.items()):
            raise ProfileError(f"{self.name}: tree entry object kind mismatch")
        return {"scope": "selected_owner_ancestry_path" if owner else "current_tree", "proof_version": 2,
                "commit": head, "owner": owner, "path_commit_count": len(path),
                "path_commits_owner_to_head": path, "path_edges": edges,
                "path_edges_sha256": sha256(canonical(edges)),
                "path_records_sha256": sha256(canonical({oid: records[oid] for oid in path})),
                "unselected_merge_parents": unselected, "all_parent_graph_verified": False,
                "owner_earlier_parents": records[owner]["parents"] if owner else [],
                "owner_earlier_history": "not_verified", "search_header_count": len(records),
                "unverified_search_missing_commits": sorted(oid for oid, row in records.items() if row is None),
                "search_header_limit": limit, "tree_roots": len(trees),
                "object_count": len(object_ids), "object_list_sha256": sha256(canonical(sorted(object_ids))),
                "missing_objects": 0, "object_sha1_verified": True,
                "tree_blob_entry_types_verified": True, "tree_blob_entry_count": tree_edges,
                "gitlink_edge_count": len(gitlinks), "gitlink_edges_sha256": sha256(canonical(gitlinks)),
                "gitlink_target_objects_verified": False, "gitlink_subrepository_history": "not_verified",
                "shallow_repository": False, "lazy_fetch": "disabled", "replacement_refs": "rejected",
                "whole_repository_history_complete": None, "earlier_history": "not_verified"}

    def snapshot_current_source(self):
        """Bind every current tree/index path to actual file modes and bytes."""
        if not self.local_objects_only:
            raise ProfileError("current source proof requires local-only Git reads")
        head_entries, index_entries = {}, {}
        try:
            for row in filter(None, self.git("ls-tree", "-r", "-z", "--full-tree", "HEAD").split(b"\0")):
                meta, raw_name = row.split(b"\t", 1)
                mode, kind, oid = meta.decode().split()
                if kind != "blob" or mode not in {"100644", "100755", "120000"}:
                    raise ValueError("unsupported current source mode")
                head_entries[os.fsdecode(raw_name)] = {"mode": mode, "git_blob": full_oid(oid, "current blob")}
            for row in filter(None, self.git("ls-files", "-s", "-z").split(b"\0")):
                meta, raw_name = row.split(b"\t", 1)
                mode, oid, stage = meta.decode().split()
                if stage != "0" or os.fsdecode(raw_name) in index_entries:
                    raise ValueError("unmerged or duplicate current source index path")
                index_entries[os.fsdecode(raw_name)] = {"mode": mode, "git_blob": oid}
            flags = self.git("ls-files", "-v", "-z").split(b"\0")
            if head_entries != index_entries or any(row[:1] != b"H" for row in flags if row):
                raise ValueError("current source tree/index/flags differ")
            files, checked_parents, symlinks = {}, {self.path}, 0
            for name, entry in sorted(head_entries.items()):
                relative = PurePosixPath(name)
                if relative.is_absolute() or ".." in relative.parts or str(relative) != name:
                    raise ValueError("invalid current source path")
                parent = self.path
                for part in relative.parts[:-1]:
                    parent = parent / part
                    if parent not in checked_parents:
                        if not stat.S_ISDIR(parent.lstat().st_mode):
                            raise ValueError("current source parent is not a real directory: " + name)
                        checked_parents.add(parent)
                location = self.path / name
                info = location.lstat()
                if entry["mode"] == "120000":
                    if not stat.S_ISLNK(info.st_mode):
                        raise ValueError("current source symlink mode mismatch: " + name)
                    data = os.fsencode(os.readlink(location))
                    size = len(data)
                    blob = hashlib.sha1(f"blob {size}\0".encode() + data)
                    content = hashlib.sha256(data)
                    symlinks += 1
                else:
                    mode = "100755" if info.st_mode & stat.S_IXUSR else "100644"
                    if not stat.S_ISREG(info.st_mode) or mode != entry["mode"]:
                        raise ValueError("current source file mode mismatch: " + name)
                    size = info.st_size
                    blob, content, total = hashlib.sha1(f"blob {size}\0".encode()), hashlib.sha256(), 0
                    with location.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            total += len(chunk)
                            blob.update(chunk)
                            content.update(chunk)
                    if total != size:
                        raise ValueError("current source bytes changed during read: " + name)
                if blob.hexdigest() != entry["git_blob"]:
                    raise ValueError("current source byte mismatch: " + name)
                files[name] = dict(entry, bytes=size, sha256=content.hexdigest())
            return {"file_count": len(files), "symlink_count": symlinks,
                    "snapshot_sha256": sha256(canonical(files)), "index_flags": "H"}
        except (OSError, ValueError, UnicodeError) as exc:
            raise ProfileError(f"{self.name}: current source proof failed: {exc}") from exc


def create_manifest(os_repo, hepta_repo, os_head, os_tree, hepta_head, hepta_tree, mapping):
    check_map(mapping)
    if mapping["schema_version"] in (4, 5):
        # Keep V1-V3 readers and receipts unchanged. Current reads cannot fetch
        # missing objects as a side effect of verifying a supposedly frozen pair.
        os_repo = Repository(os_repo.path, os_repo.name, local_objects_only=True)
        hepta_repo = Repository(hepta_repo.path, hepta_repo.name, local_objects_only=True)
    os_identity = os_repo.check(os_head, os_tree)
    hepta_identity = hepta_repo.check(hepta_head, hepta_tree)
    if mapping["schema_version"] in (4, 5):
        # The fixed map is itself a tracked OS source, not an operator-selected
        # replacement. It contains paths, never its own source/manifest hash.
        stored_bytes, _ = os_repo.file("support/release/" + source_map_name(mapping["schema_version"]))
        stored_map = load_json_bytes(stored_bytes, f"checked-in schema{mapping['schema_version']} source map")
        if canonical(stored_map) != canonical(mapping):
            raise ProfileError(f"checked-in schema{mapping['schema_version']} map differs from the reviewed map")
    object_closure = None
    current_sources = None
    if mapping["schema_version"] in (4, 5):
        object_closure = {"os": os_repo.prove_object_closure(),
                          "hepta": hepta_repo.prove_object_closure(HISTORY_OWNER)}
        # A real verified parent path is the V4 ancestor proof. Git merge-base
        # may inspect unrelated, unavailable history and is kept only by V1-3.
        proof = {"commit": HISTORY_OWNER, "method": "verified_sha1_parent_path",
                 "shallow_repository": False, "scope": "selected_owner_ancestry_path",
                 "path_edges_sha256": object_closure["hepta"]["path_edges_sha256"]}
        current_sources = {"os": os_repo.snapshot_current_source(),
                           "hepta": hepta_repo.snapshot_current_source()}
    else:
        proof = hepta_repo.prove_history()
    sources = {}
    for name, repo in (("os", os_repo), ("hepta", hepta_repo)):
        sources[name] = []
        for role, path in sorted(mapping["sources"][name].items()):
            _, record = repo.file(path)
            sources[name].append(dict(role=role, **record))
    goldens = []
    for role, paths in sorted(mapping["goldens"].items()):
        os_data, _ = os_repo.file(paths["os"])
        hepta_data, _ = hepta_repo.file(paths["hepta"])
        if os_data != hepta_data:
            raise ProfileError(f"golden byte mismatch: {role}")
        goldens.append({"role": role, "os_path": paths["os"], "hepta_path": paths["hepta"],
                        "sha256": sha256(os_data), "bytes": len(os_data)})
    # Detect checkout changes during the preceding reads.
    os_repo.check(os_head, os_tree)
    hepta_repo.check(hepta_head, hepta_tree)
    if current_sources is not None:
        after = {"os": os_repo.snapshot_current_source(), "hepta": hepta_repo.snapshot_current_source()}
        if after != current_sources:
            raise ProfileError("current source byte/mode/index proof changed during verification")
        os_repo.check(os_head, os_tree)
        hepta_repo.check(hepta_head, hepta_tree)
    manifest = {
        "schema_version": mapping["schema_version"],
        "qualification": "source-only",
        "os_identity_binding": "explicit_caller_head_and_tree_in_verification_receipt",
        "hepta": hepta_identity,
        "original_history_owner": HISTORY_OWNER,
        "source_map_sha256": sha256(canonical(mapping)),
        "production": PRODUCTION,
        "sources": sources,
        "goldens": goldens,
    }
    receipt = {
        "schema_version": mapping["schema_version"], "qualification": "source-only", "source_checks": "passed",
        "os": os_identity, "hepta": hepta_identity,
        "original_history_proof": proof, "production": PRODUCTION,
        "runtime_tests": "not_run_by_this_tool",
    }
    if object_closure is not None:
        receipt["git_object_closure"] = object_closure
        receipt["current_source_proof"] = current_sources
    return manifest, receipt


def verify_manifest(manifest, os_repo, hepta_repo, os_head, os_tree, mapping):
    if not isinstance(manifest, dict) or not isinstance(manifest.get("hepta"), dict):
        raise ProfileError("invalid manifest: missing single hepta commit/tree")
    hepta = manifest["hepta"]
    expected, receipt = create_manifest(os_repo, hepta_repo, os_head, os_tree,
                                        hepta.get("commit"), hepta.get("tree"), mapping)
    if canonical(manifest) != canonical(expected):
        raise ProfileError("manifest mismatch: schema, source identities, goldens, or disabled production boundary changed")
    return receipt


def write_new_outside(path, data, repositories):
    target = Path(path).resolve()
    if any(target.is_relative_to(repo.path) for repo in repositories):
        raise ProfileError("generated output must be outside both source repositories; review it before committing")
    try:
        with target.open("xb") as stream:
            stream.write(data)
    except OSError as exc:
        raise ProfileError(f"cannot create output {target}: {exc}") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "verify"):
        sub = subcommands.add_parser(command)
        sub.add_argument("--os-repo", required=True)
        sub.add_argument("--hepta-repo", required=True)
        sub.add_argument("--os-head", required=True)
        sub.add_argument("--os-tree", required=True)
        sub.add_argument("--source-map", default=str(Path(__file__).with_name("organ_source_map.json")))
        sub.add_argument("--receipt", help="new output path outside both repositories; otherwise print receipt")
        if command == "build":
            sub.add_argument("--hepta-head", required=True)
            sub.add_argument("--hepta-tree", required=True)
            sub.add_argument("--output", required=True, help="new manifest path outside both repositories")
        else:
            sub.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        os_repo = Repository(args.os_repo, "os")
        hepta_repo = Repository(args.hepta_repo, "hepta")
        if os_repo.path == hepta_repo.path:
            raise ProfileError("os and hepta must be distinct repository roots")
        mapping = load_json(args.source_map)
        if args.command == "build":
            manifest, receipt = create_manifest(os_repo, hepta_repo, args.os_head, args.os_tree,
                                                 args.hepta_head, args.hepta_tree, mapping)
            raw_manifest = canonical(manifest)
            write_new_outside(args.output, raw_manifest, (os_repo, hepta_repo))
        else:
            raw_manifest = Path(args.manifest).read_bytes()
            manifest = load_json_bytes(raw_manifest, args.manifest)
            receipt = verify_manifest(manifest, os_repo, hepta_repo, args.os_head, args.os_tree, mapping)
        receipt["manifest_sha256"] = sha256(raw_manifest)
        data = canonical(receipt)
        if args.receipt:
            write_new_outside(args.receipt, data, (os_repo, hepta_repo))
        else:
            sys.stdout.buffer.write(data)
        return 0
    except (ProfileError, OSError) as exc:
        print(f"organ release profile: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
