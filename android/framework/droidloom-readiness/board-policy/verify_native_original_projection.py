"""Project the fixed original policy authority without candidate-derived expectations.

This module preserves every old form, including constraints and transitions.
Only declared new concrete types and authority with no old endpoint are projected
away. Each new component has its own complete raw/MLS/transition verifier.
The immutable projected commitments are generated once from the retained normal
334f binary export, never from a candidate.
"""
import hashlib
import json
from derive_native_uevent_policy import Membership
from derive_shared_payload_cgroup_policy import parse_expression

SCHEMA="droidloom.native-original-authority-projection.v2"
BASELINE_DERIVATION={"bytes":10323,"sha256":"4b4319b42ac436245e5f9f94ee1d5135a18766030bf55e20bce769e0fbe51bbc"}
BASELINE_CONTROLLER={"bytes":4637,"sha256":"faa6fd7d3f97aec2b5ad0bf4b870ff6e15519e8746370ae831afc9d4cf096fd8"}
# The exact reviewed component families are source-owned. Unknown additions alter
# the original concrete type commitment and are rejected.
ORIGINAL_ATTRIBUTES=frozenset(['adbd_common', 'apex_data_file_type', 'app_api_service', 'app_data_file_type', 'appdomain', 'artd_subprocess_type', 'automotive_display_service_server', 'binderservicedomain', 'bluetoothdomain', 'bpfdomain', 'bpffs_type', 'camera_service_server', 'charger_type', 'contextmount_type', 'core_data_file_type', 'core_property_type', 'coredomain', 'coredomain_hwservice', 'coredomain_socket', 'crosvm_domain', 'dalvik_config_prop_type', 'data_between_core_and_vendor_violators', 'data_file_type', 'debugfs_type', 'dev_type', 'display_service_server', 'dmabuf_heap_device_type', 'domain', 'droidloom_frontend_android_platform_clients', 'droidloom_other_proof_creators', 'droidloom_package_config_parents', 'droidloom_package_early_units', 'droidloom_package_native_units', 'droidloom_package_process_observations', 'droidloom_public_control_peers', 'droidloom_shutdown_other_props', 'droidloom_shutdown_protected_processes', 'droidloom_without_public_control', 'early_virtmgr_domain', 'ephemeral_app_api_service', 'exec_type', 'extended_core_property_type', 'file_type', 'fs_type', 'fusefs_type', 'gpu_sphal_domain', 'gsi_metadata_file_type', 'hal_allocator_server', 'hal_atrace_server', 'hal_audio_server', 'hal_audiocontrol_server', 'hal_authgraph_server', 'hal_authsecret_server', 'hal_automotive_socket_exemption', 'hal_bluetooth_lpp_server', 'hal_bluetooth_server', 'hal_bootctl_server', 'hal_broadcastradio_server', 'hal_camera_server', 'hal_can_bus_server', 'hal_can_controller_server', 'hal_cas_server', 'hal_codec2_server', 'hal_configstore_server', 'hal_confirmationui_server', 'hal_contexthub_server', 'hal_drm_server', 'hal_dumpstate_server', 'hal_evs_server', 'hal_face_server', 'hal_fastboot_server', 'hal_fingerprint_server', 'hal_gatekeeper_server', 'hal_gnss_server', 'hal_graphics_allocator_server', 'hal_graphics_composer_server', 'hal_health_server', 'hal_health_storage_server', 'hal_hwcrypto_server', 'hal_identity_server', 'hal_input_classifier_server', 'hal_input_processor_server', 'hal_ir_server', 'hal_ivn_server', 'hal_keymaster_server', 'hal_keymint_server', 'hal_lazy_test_server', 'hal_light_server', 'hal_lowpan_server', 'hal_macsec_server', 'hal_mediaquality_server', 'hal_memtrack_server', 'hal_motioncontext_server', 'hal_neuralnetworks_server', 'hal_nfc_server', 'hal_nlinterceptor_server', 'hal_npu_scheduling_server', 'hal_oemlock_server', 'hal_omx_server', 'hal_power_server', 'hal_power_stats_server', 'hal_rebootescrow_server', 'hal_remoteaccess_server', 'hal_remotelyprovisionedcomponent_avf_server', 'hal_secretkeeper_server', 'hal_secure_element_server', 'hal_sensors_server', 'hal_service_type', 'hal_telephony_server', 'hal_tetheroffload_server', 'hal_thermal_server', 'hal_threadnetwork_server', 'hal_tv_cec_server', 'hal_tv_hdmi_cec_server', 'hal_tv_hdmi_connection_server', 'hal_tv_hdmi_earc_server', 'hal_tv_input_server', 'hal_tv_tuner_server', 'hal_usb_gadget_server', 'hal_usb_server', 'hal_uwb_server', 'hal_uwb_vendor_server', 'hal_vehicle_server', 'hal_vibrator_server', 'hal_vm_capabilities_server', 'hal_vr_server', 'hal_weaver_server', 'hal_wifi_hostapd_server', 'hal_wifi_server', 'hal_wifi_supplicant_server', 'halserverdomain', 'hwservice_manager_type', 'isolated_app_all', 'isolated_compute_allowed_device', 'isolated_compute_allowed_service', 'log_property_type', 'mapper_sphal_domain', 'mlstrustedobject', 'mlstrustedsubject', 'mlsvendorcompat', 'netdomain', 'node_type', 'omapi_server', 'p4_additional_application_queries', 'p4_all_board_owned', 'p4_all_nonboard', 'p4_android_dirs_without_metadata_root', 'p4_android_dirs_without_query_traversal', 'p4_android_except_readiness', 'p4_android_files_without_query_copy', 'p4_android_files_without_query_originals', 'p4_android_files_without_shared_kernel_modules', 'p4_android_only_files', 'p4_android_other_than_device_init', 'p4_android_payload_objects', 'p4_android_userspace', 'p4_broker_frontend_dirs_without_metadata_root', 'p4_broker_frontend_image_dirs', 'p4_broker_frontend_image_files', 'p4_broker_frontend_image_files_without_query', 'p4_broker_frontend_proc_peers', 'p4_broker_query_original_files', 'p4_camera_revision_nonreaders', 'p4_cgroup_original_types', 'p4_closed_business_queries', 'p4_closed_cmd_queries', 'p4_closed_helpers_without_native_bus', 'p4_closed_runtime_queries', 'p4_console_nonboard_without_device', 'p4_console_preserved_0_0', 'p4_console_preserved_0_1', 'p4_console_preserved_0_2', 'p4_console_preserved_0_3', 'p4_console_preserved_0_4', 'p4_console_preserved_10_0', 'p4_console_preserved_10_1', 'p4_console_preserved_11_0', 'p4_console_preserved_11_1', 'p4_console_preserved_11_2', 'p4_console_preserved_11_3', 'p4_console_preserved_11_4', 'p4_console_preserved_11_5', 'p4_console_preserved_12_0', 'p4_console_preserved_12_1', 'p4_console_preserved_12_2', 'p4_console_preserved_13_0', 'p4_console_preserved_13_1', 'p4_console_preserved_1_0', 'p4_console_preserved_1_1', 'p4_console_preserved_1_2', 'p4_console_preserved_1_3', 'p4_console_preserved_2_0', 'p4_console_preserved_2_1', 'p4_console_preserved_2_2', 'p4_console_preserved_2_3', 'p4_console_preserved_3_0', 'p4_console_preserved_3_1', 'p4_console_preserved_3_2', 'p4_console_preserved_4_0', 'p4_console_preserved_4_1', 'p4_console_preserved_4_2', 'p4_console_preserved_5_0', 'p4_console_preserved_5_1', 'p4_console_preserved_5_2', 'p4_console_preserved_6_0', 'p4_console_preserved_6_1', 'p4_console_preserved_6_2', 'p4_console_preserved_7_0', 'p4_console_preserved_7_1', 'p4_console_preserved_7_2', 'p4_console_preserved_7_3', 'p4_console_preserved_7_4', 'p4_console_preserved_7_5', 'p4_console_preserved_8_0', 'p4_console_preserved_8_1', 'p4_console_preserved_9_0', 'p4_console_preserved_9_1', 'p4_cp3a_handle_ioctl_domains', 'p4_cp3a_handle_objects', 'p4_display_other_services', 'p4_early_nonboard_without_fixed_directories', 'p4_early_nonboard_without_fixed_reads', 'p4_factory_native_membership', 'p4_fixed_metadata_all_types', 'p4_fixed_metadata_executables', 'p4_fixed_metadata_tasks', 'p4_fixed_query_copies', 'p4_fixed_query_processes', 'p4_greeter_control_denied', 'p4_greeter_path_users', 'p4_greeter_private_data', 'p4_greeter_private_objects', 'p4_handle_owner', 'p4_hardware_foreign_proc_roles', 'p4_instance_host_readers', 'p4_linux_data', 'p4_linux_fixed_runtime_units', 'p4_linux_init_cgroup_inodes', 'p4_linux_journal_nonwriters', 'p4_linux_mac_fixed_kernel_read', 'p4_linux_mac_roles', 'p4_linux_mac_roles_without_package_helper', 'p4_linux_native_executables', 'p4_linux_native_processes', 'p4_linux_native_public_files', 'p4_linux_native_runtime', 'p4_linux_native_state', 'p4_linux_native_without_package_invoker', 'p4_linux_nonmac_without_native_selinux_queries', 'p4_linux_nonstop_data', 'p4_linux_not_payload_owner', 'p4_linux_not_pid1_manager', 'p4_linux_other_than_executor', 'p4_linux_other_than_mac', 'p4_linux_procs', 'p4_linux_public_launcher_all_types', 'p4_linux_public_launcher_readers', 'p4_linux_selected_release_readers', 'p4_linux_without_boot_commandline_reader', 'p4_linux_without_fresh_filesystem_labelers', 'p4_linux_without_frontend_metadata', 'p4_linux_without_namespace_executor', 'p4_linux_without_native_directory_relabel_actors', 'p4_linux_without_native_module_readers', 'p4_linux_without_native_mount_actors', 'p4_linux_without_query_owner', 'p4_logind_parent_preserved_0_0', 'p4_logind_parent_preserved_0_1', 'p4_logind_parent_preserved_0_2', 'p4_logind_parent_preserved_0_3', 'p4_logind_parent_preserved_0_4', 'p4_mac_roles_without_frontend_metadata', 'p4_maintenance_status_units', 'p4_native_activated_nonbus_services', 'p4_native_activated_unix_services', 'p4_native_auxiliary_listener_nodes', 'p4_native_boot_commandline_readers', 'p4_native_boot_log_writers', 'p4_native_boot_proc_files', 'p4_native_boot_proc_readers', 'p4_native_cgroup_nonroot_inodes', 'p4_native_credential_consumers', 'p4_native_credential_unit_dirs', 'p4_native_dbus_all_types', 'p4_native_desktop_socket_inodes', 'p4_native_dev_and_user_cgroup', 'p4_native_dev_only_without_user_cgroup', 'p4_native_dev_root_traversers', 'p4_native_device_directory_relabelers', 'p4_native_generator_directory_owners', 'p4_native_generator_directory_readers', 'p4_native_hardware_all_types', 'p4_native_hardware_dirs', 'p4_native_hardware_discovery', 'p4_native_hardware_nodes', 'p4_native_hardware_not_dirs', 'p4_native_hardware_not_nodes', 'p4_native_home_readers', 'p4_native_home_writers', 'p4_native_ipc_memory_creators', 'p4_native_ipc_memory_nonreaders', 'p4_native_ipc_memory_readers', 'p4_native_journal_cgroup_metadata', 'p4_native_login_home_readers', 'p4_native_maintenance_actors', 'p4_native_maintenance_inputs', 'p4_native_manager_child_metadata', 'p4_native_manager_metadata_readers', 'p4_native_manager_nonboard_without_public_dirs', 'p4_native_manager_nonboard_without_public_inputs', 'p4_native_module_readers', 'p4_native_mount_actors', 'p4_native_new_credential_unit_dirs', 'p4_native_nonjournal_boot_proc_inputs', 'p4_native_nonjournal_without_early_reads', 'p4_native_nonmac_without_executor_directory_open', 'p4_native_nonmac_without_module_dirs', 'p4_native_nontraversing_without_module_dirs', 'p4_native_other_shutdown_callers', 'p4_native_pam_roles', 'p4_native_pam_tty_types', 'p4_native_passive_audit_consumers', 'p4_native_pidfs_metadata_readers', 'p4_native_pipewire_clients', 'p4_native_pipewire_publishers', 'p4_native_private_dev_consumers', 'p4_native_private_storage', 'p4_native_render_clients', 'p4_native_runtime_acl_all_types', 'p4_native_runtime_acl_data', 'p4_native_runtime_acl_other_data', 'p4_native_runtime_acl_other_sockets', 'p4_native_runtime_acl_sockets', 'p4_native_runtime_directory_maintainers', 'p4_native_sandbox_filesystems', 'p4_native_sandbox_kernel_dirs', 'p4_native_sandbox_staging_dirs', 'p4_native_seat_metadata_readers', 'p4_native_self_fd_nonquery_readers', 'p4_native_self_fd_query_readers', 'p4_native_selinux_avc_clients', 'p4_native_selinux_label_readers', 'p4_native_selinux_metadata_clients', 'p4_native_selinux_nonmanager_clients', 'p4_native_selinux_query_clients', 'p4_native_service_cap_non_pam_subjects', 'p4_native_service_cap_non_pam_targets', 'p4_native_service_cap_subjects', 'p4_native_service_cap_targets', 'p4_native_session_bus_clients', 'p4_native_session_storage_actors', 'p4_native_shutdown_filesystems', 'p4_native_storage_control_denied', 'p4_native_sysfs_nonmodule_directory_readers', 'p4_native_sysfs_nonmodule_file_readers', 'p4_native_sysfs_nonmodule_traversers', 'p4_native_sysfs_readers', 'p4_native_system_bus_clients', 'p4_native_system_journal_consumers', 'p4_native_uevent_objects', 'p4_native_uevent_sources', 'p4_native_user_cgroup_directories', 'p4_native_user_cgroup_files', 'p4_native_user_cgroup_inodes', 'p4_native_user_cgroup_nonowners', 'p4_native_user_cgroup_path_actors', 'p4_native_user_cgroup_traversers', 'p4_native_user_manager_cgroup_dirs', 'p4_native_user_system_cgroup_dirs', 'p4_native_wayland_clients', 'p4_native_wayland_participants', 'p4_native_without_generator_directory_owners', 'p4_netplan_all_types', 'p4_netplan_nonnm_dirs', 'p4_netplan_nonoutput_files', 'p4_netplan_nonruntime_dirs', 'p4_netplan_nonstdio_devices', 'p4_netplan_other_entries', 'p4_netplan_other_sources', 'p4_netplan_preserved_0_0', 'p4_netplan_preserved_0_1', 'p4_netplan_preserved_0_2', 'p4_netplan_preserved_0_3', 'p4_netplan_preserved_1_0', 'p4_netplan_preserved_1_1', 'p4_netplan_preserved_2_0', 'p4_netplan_preserved_2_1', 'p4_netplan_preserved_3_0', 'p4_netplan_preserved_3_1', 'p4_netplan_preserved_3_2', 'p4_netplan_preserved_3_3', 'p4_netplan_preserved_4_0', 'p4_netplan_preserved_5_0', 'p4_netplan_preserved_5_1', 'p4_netplan_preserved_5_2', 'p4_netplan_preserved_6_0', 'p4_netplan_preserved_6_1', 'p4_netplan_preserved_7_0', 'p4_netplan_preserved_7_1', 'p4_netplan_preserved_7_2', 'p4_netplan_preserved_7_3', 'p4_netplan_preserved_8_0', 'p4_netplan_preserved_8_1', 'p4_netplan_preserved_8_2', 'p4_netplan_preserved_8_3', 'p4_netplan_preserved_9_0', 'p4_netplan_preserved_9_1', 'p4_netplan_unselected_nonboard_dirs', 'p4_non_early_linux', 'p4_non_kernel_cgroup_actor', 'p4_non_kernel_cgroup_nonexecutor', 'p4_nonboard_except_boot_proc_inputs', 'p4_nonboard_except_broker_metadata_root', 'p4_nonboard_except_broker_query_directories', 'p4_nonboard_except_broker_query_read', 'p4_nonboard_except_device_directory', 'p4_nonboard_except_executor_tmpfs_directory', 'p4_nonboard_except_generator_tmpfs_source', 'p4_nonboard_except_journal_native_directory', 'p4_nonboard_except_journal_uts_and_boot_id', 'p4_nonboard_except_kernel_cmdline_and_pidns_handle', 'p4_nonboard_except_mac_api', 'p4_nonboard_except_mac_directories', 'p4_nonboard_except_mac_read', 'p4_nonboard_except_native_manager_abi_dirs', 'p4_nonboard_except_native_self_fd_dirs', 'p4_nonboard_except_native_selinux_dirs', 'p4_nonboard_except_native_selinux_metadata_dirs', 'p4_nonboard_except_native_selinux_queries', 'p4_nonboard_except_native_selinux_read', 'p4_nonboard_except_presenter_hardware_directory', 'p4_nonboard_except_presenter_native_directory', 'p4_nonboard_except_query_fs_source', 'p4_nonboard_except_user_cgroup_path', 'p4_nonboard_user', 'p4_nonboard_without_fresh_sandbox_fs', 'p4_nonboard_without_generator_public_dirs', 'p4_nonboard_without_loader_inputs', 'p4_nonboard_without_maintenance_dirs', 'p4_nonboard_without_maintenance_files', 'p4_nonboard_without_native_module_dirs', 'p4_nonboard_without_native_sysfs', 'p4_nonboard_without_native_sysfs_or_cmdline', 'p4_nonboard_without_native_sysfs_or_device', 'p4_nonboard_without_sandbox_filesystems', 'p4_nonboard_without_sandbox_kernel_dirs', 'p4_nonboard_without_sandbox_tmpfs', 'p4_nonboard_without_shutdown_filesystems', 'p4_nonboard_without_udev_boot_inputs', 'p4_nonboard_without_udev_kernel_dirs', 'p4_nonbroker_system_bus_targets', 'p4_nonmanager_broker_senders', 'p4_not_handle_owner', 'p4_not_native_executor_key_owner', 'p4_not_native_task_migrator', 'p4_not_pidfs_metadata_reader', 'p4_not_service_executor', 'p4_not_ubuntu_pid1', 'p4_once_all_types', 'p4_once_foreign_processes', 'p4_once_immutable_files', 'p4_once_not_creator', 'p4_once_not_evidence', 'p4_once_not_executor', 'p4_once_not_kernel', 'p4_once_not_maintenance', 'p4_once_not_output_writer', 'p4_once_not_stdio', 'p4_once_other_nonboard_directories', 'p4_once_other_nonboard_files', 'p4_other_handoff_readers', 'p4_other_stop_readers', 'p4_payload_android_dir_0', 'p4_payload_android_dir_1', 'p4_payload_android_dir_2', 'p4_payload_android_dir_3', 'p4_payload_android_dir_4', 'p4_payload_android_dir_5', 'p4_payload_android_dir_6', 'p4_payload_android_dir_7', 'p4_payload_android_dir_8', 'p4_payload_android_dir_9', 'p4_payload_android_file_0', 'p4_payload_android_file_1', 'p4_payload_android_file_2', 'p4_payload_android_file_3', 'p4_payload_android_file_4', 'p4_payload_android_file_5', 'p4_payload_android_file_6', 'p4_payload_android_lnk_file_0', 'p4_payload_android_lnk_file_1', 'p4_payload_android_lnk_file_2', 'p4_payload_ioctl_dir_0', 'p4_payload_ioctl_file_0', 'p4_payload_ioctl_lnk_file_0', 'p4_presenter_clipboard_file_readers', 'p4_presenter_hardware_enumeration', 'p4_presenter_runtime_all_subjects', 'p4_presenter_runtime_creators', 'p4_presenter_runtime_retirement', 'p4_presenter_without_hardware_enumeration', 'p4_previous_namespace_ioctl_roles', 'p4_query_birth_no_binder_call', 'p4_query_birth_other_tasks', 'p4_query_original_dirs', 'p4_readiness_other_android_userspace', 'p4_readiness_other_peer', 'p4_remount_all_types', 'p4_remount_nonstdio_devices', 'p4_remount_other_entries', 'p4_remount_other_filesystems', 'p4_remount_other_helpers', 'p4_remount_other_sources', 'p4_remount_preserved_0_0', 'p4_remount_preserved_0_1', 'p4_remount_preserved_1_0', 'p4_remount_preserved_1_1', 'p4_remount_preserved_1_2', 'p4_remount_preserved_1_3', 'p4_remount_preserved_1_4', 'p4_remount_preserved_2_0', 'p4_remount_preserved_2_1', 'p4_remount_preserved_2_2', 'p4_remount_preserved_3_0', 'p4_remount_preserved_3_1', 'p4_remount_preserved_3_2', 'p4_remount_preserved_3_3', 'p4_remount_preserved_3_4', 'p4_remount_preserved_3_5', 'p4_remount_preserved_4_0', 'p4_remount_preserved_4_1', 'p4_remount_preserved_4_2', 'p4_remount_preserved_4_3', 'p4_remount_preserved_4_4', 'p4_remount_preserved_4_5', 'p4_shutdown_readonly_roles', 'p4_sysusers_preserved_0_0', 'p4_sysusers_preserved_0_1', 'p4_sysusers_preserved_0_2', 'p4_sysusers_preserved_0_3', 'p4_sysusers_preserved_0_4', 'p4_sysusers_preserved_1_0', 'p4_sysusers_preserved_1_1', 'p4_sysusers_preserved_1_2', 'p4_timezone_non_manager', 'p4_uevent_all_types', 'p4_uevent_android_0_dir_0', 'p4_uevent_android_0_dir_1', 'p4_uevent_android_0_dir_2', 'p4_uevent_android_0_dir_3', 'p4_uevent_android_0_dir_4', 'p4_uevent_android_0_dir_5', 'p4_uevent_android_0_dir_6', 'p4_uevent_android_0_dir_ioctl_0', 'p4_uevent_android_0_dir_ioctl_1', 'p4_uevent_android_0_file_0', 'p4_uevent_android_0_file_1', 'p4_uevent_android_0_file_2', 'p4_uevent_android_0_file_3', 'p4_uevent_android_0_file_4', 'p4_uevent_android_0_file_5', 'p4_uevent_android_0_file_6', 'p4_uevent_android_0_file_7', 'p4_uevent_android_0_file_ioctl_0', 'p4_uevent_android_0_lnk_file_0', 'p4_uevent_android_0_lnk_file_1', 'p4_uevent_android_0_lnk_file_2', 'p4_uevent_android_0_lnk_file_3', 'p4_uevent_android_0_lnk_file_ioctl_0', 'p4_uevent_android_1_dir_0', 'p4_uevent_android_1_dir_1', 'p4_uevent_android_1_dir_2', 'p4_uevent_android_1_dir_3', 'p4_uevent_android_1_dir_ioctl_0', 'p4_uevent_android_1_dir_ioctl_1', 'p4_uevent_android_1_file_0', 'p4_uevent_android_1_file_1', 'p4_uevent_android_1_file_2', 'p4_uevent_android_1_file_3', 'p4_uevent_android_1_file_ioctl_0', 'p4_uevent_android_1_lnk_file_0', 'p4_uevent_android_1_lnk_file_1', 'p4_uevent_android_1_lnk_file_2', 'p4_uevent_android_1_lnk_file_ioctl_0', 'p4_uevent_android_2_dir_0', 'p4_uevent_android_2_dir_1', 'p4_uevent_android_2_dir_2', 'p4_uevent_android_2_dir_3', 'p4_uevent_android_2_dir_4', 'p4_uevent_android_2_dir_5', 'p4_uevent_android_2_dir_ioctl_0', 'p4_uevent_android_2_dir_ioctl_1', 'p4_uevent_android_2_file_0', 'p4_uevent_android_2_file_1', 'p4_uevent_android_2_file_2', 'p4_uevent_android_2_file_3', 'p4_uevent_android_2_file_4', 'p4_uevent_android_2_file_ioctl_0', 'p4_uevent_android_2_lnk_file_0', 'p4_uevent_android_2_lnk_file_1', 'p4_uevent_android_2_lnk_file_2', 'p4_uevent_android_2_lnk_file_3', 'p4_uevent_android_2_lnk_file_4', 'p4_uevent_android_2_lnk_file_ioctl_0', 'p4_uevent_android_3_dir_0', 'p4_uevent_android_3_dir_1', 'p4_uevent_android_3_dir_2', 'p4_uevent_android_3_dir_3', 'p4_uevent_android_3_dir_4', 'p4_uevent_android_3_dir_5', 'p4_uevent_android_3_dir_ioctl_0', 'p4_uevent_android_3_dir_ioctl_1', 'p4_uevent_android_3_file_0', 'p4_uevent_android_3_file_1', 'p4_uevent_android_3_file_2', 'p4_uevent_android_3_file_3', 'p4_uevent_android_3_file_4', 'p4_uevent_android_3_file_5', 'p4_uevent_android_3_file_ioctl_0', 'p4_uevent_android_3_lnk_file_0', 'p4_uevent_android_3_lnk_file_1', 'p4_uevent_android_3_lnk_file_2', 'p4_uevent_android_3_lnk_file_3', 'p4_uevent_android_3_lnk_file_4', 'p4_uevent_android_3_lnk_file_ioctl_0', 'p4_uevent_android_4_dir_0', 'p4_uevent_android_4_dir_1', 'p4_uevent_android_4_dir_2', 'p4_uevent_android_4_dir_3', 'p4_uevent_android_4_dir_4', 'p4_uevent_android_4_dir_5', 'p4_uevent_android_4_dir_ioctl_0', 'p4_uevent_android_4_dir_ioctl_1', 'p4_uevent_android_4_file_0', 'p4_uevent_android_4_file_1', 'p4_uevent_android_4_file_2', 'p4_uevent_android_4_file_3', 'p4_uevent_android_4_file_4', 'p4_uevent_android_4_file_5', 'p4_uevent_android_4_file_ioctl_0', 'p4_uevent_android_4_lnk_file_0', 'p4_uevent_android_4_lnk_file_1', 'p4_uevent_android_4_lnk_file_2', 'p4_uevent_android_4_lnk_file_3', 'p4_uevent_android_4_lnk_file_4', 'p4_uevent_android_4_lnk_file_ioctl_0', 'p4_uevent_android_5_dir_0', 'p4_uevent_android_5_dir_1', 'p4_uevent_android_5_dir_2', 'p4_uevent_android_5_dir_3', 'p4_uevent_android_5_dir_4', 'p4_uevent_android_5_dir_5', 'p4_uevent_android_5_dir_ioctl_0', 'p4_uevent_android_5_dir_ioctl_1', 'p4_uevent_android_5_file_0', 'p4_uevent_android_5_file_1', 'p4_uevent_android_5_file_2', 'p4_uevent_android_5_file_3', 'p4_uevent_android_5_file_4', 'p4_uevent_android_5_file_ioctl_0', 'p4_uevent_android_5_lnk_file_0', 'p4_uevent_android_5_lnk_file_1', 'p4_uevent_android_5_lnk_file_2', 'p4_uevent_android_5_lnk_file_3', 'p4_uevent_android_5_lnk_file_4', 'p4_uevent_android_5_lnk_file_ioctl_0', 'p4_uevent_foreign_proc_roles', 'p4_uevent_native_0_0', 'p4_uevent_native_0_1', 'p4_uevent_native_0_2', 'p4_uevent_native_0_3', 'p4_uevent_native_1_0', 'p4_uevent_native_1_1', 'p4_uevent_native_1_2', 'p4_uevent_native_1_3', 'p4_uevent_native_2_0', 'p4_uevent_native_2_1', 'p4_uevent_native_2_2', 'p4_uevent_native_2_3', 'p4_uevent_native_3_0', 'p4_uevent_native_3_1', 'p4_uevent_native_3_2', 'p4_uevent_native_3_3', 'p4_uevent_native_4_0', 'p4_uevent_native_4_1', 'p4_uevent_native_4_2', 'p4_uevent_native_4_3', 'p4_uevent_native_5_0', 'p4_uevent_native_5_1', 'p4_uevent_native_5_2', 'p4_uevent_native_5_3', 'p4_uevent_nonboard_not_directories', 'p4_uevent_nonboard_not_sources', 'p4_uevent_nonboard_not_sysfs', 'p4_uevent_nonstdio_devices', 'p4_uevent_not_executor', 'p4_uevent_not_helper', 'p4_uevent_not_objects', 'p4_uevent_not_relabel_sources', 'p4_uevent_not_writer', 'p4_without_generator_tmp_inode', 'p4_without_generator_tmp_users', 'p4_without_generator_tmp_writer', 'p4_without_native_credential_retire', 'pdx_bufferhub_client_channel_socket_type', 'pdx_bufferhub_client_endpoint_dir_type', 'pdx_bufferhub_client_endpoint_socket_type', 'pdx_bufferhub_client_server_type', 'pdx_channel_socket_type', 'pdx_display_client_channel_socket_type', 'pdx_display_client_endpoint_dir_type', 'pdx_display_client_endpoint_socket_type', 'pdx_display_client_server_type', 'pdx_display_manager_channel_socket_type', 'pdx_display_manager_endpoint_dir_type', 'pdx_display_manager_endpoint_socket_type', 'pdx_display_manager_server_type', 'pdx_display_screenshot_channel_socket_type', 'pdx_display_screenshot_endpoint_socket_type', 'pdx_display_vsync_channel_socket_type', 'pdx_display_vsync_endpoint_dir_type', 'pdx_display_vsync_endpoint_socket_type', 'pdx_display_vsync_server_type', 'pdx_endpoint_socket_type', 'pdx_performance_client_channel_socket_type', 'pdx_performance_client_endpoint_dir_type', 'pdx_performance_client_endpoint_socket_type', 'pdx_performance_client_server_type', 'platform_app_all', 'port_type', 'priv_app_all', 'proc_type', 'property_type', 'protected_hwservice', 'protected_service', 'remote_provisioning_service_server', 'same_process_hwservice', 'scheduler_service_server', 'sdcard_type', 'sdk_sandbox_all', 'sdk_sandbox_current', 'sensor_service_server', 'service_manager_type', 'socket_between_core_and_vendor_violators', 'stats_service_server', 'super_block_device_type', 'sysfs_type', 'system_and_vendor_property_type', 'system_api_service', 'system_dlkm_file_type', 'system_executes_vendor_violators', 'system_file_type', 'system_internal_property_type', 'system_property_type', 'system_public_property_type', 'system_restricted_property_type', 'system_server_service', 'system_suspend_internal_server', 'system_suspend_server', 'system_writes_mnt_vendor_violators', 'system_writes_vendor_properties_violators', 'tmpfs_type', 'tracefs_type', 'treble_labeling_violators', 'unconstrained_vsock_violators', 'untrusted_app_all', 'untrusted_app_visible_halserver_violators', 'untrusted_app_visible_hwservice_violators', 'update_engine_common', 'update_provider', 'vendor_executes_system_violators', 'vendor_file_type', 'vendor_internal_property_type', 'vendor_property_type', 'vendor_public_property_type', 'vendor_restricted_property_type', 'virtualizationmanager_domain', 'vm_manager_device_type', 'vndservice_manager_type', 'wifi_keystore_service_server', 'wrapfd_hal_domain'])
NEW_TYPES=frozenset({
 "p4_linux_timesyncd_t","p4_linux_timesyncd_exec_t","p4_linux_timesyncd_run_t",
 "p4_linux_timesyncd_state_t","p4_linux_timesyncd_config_t","p4_linux_timesyncd_nsswitch_t",
 "p4_linux_timesyncd_netif_t","p4_linux_timesyncd_dns_port_t",
 "p4_linux_random_seed_t","p4_linux_random_seed_exec_t","p4_linux_random_seed_file_t",
 "p4_linux_ldconfig_t","p4_linux_ldconfig_exec_t","p4_linux_ldconfig_config_t",
 "p4_linux_ldconfig_config_dir_t","p4_linux_ldconfig_aux_dir_t","p4_linux_ldconfig_aux_t",
 "p4_linux_journal_catalog_dir_t","p4_linux_journal_catalog_file_t",
 "p4_linux_kmod_tmpfiles_dir_t","p4_linux_kmod_static_nodes_t",
    'p4_linux_update_done_t',
    'p4_linux_update_done_exec_t',
    'p4_linux_update_done_var_dir_t',
    'p4_linux_update_done_etc_file_t',
    'p4_linux_update_done_var_file_t',
})
AUDIT=frozenset({"auditallow","dontaudit","auditallowx","dontauditx"})
TYPE_OPERATIONS=frozenset({"type","typeattribute","typeattributeset","typealias","typealiasactual","expandtypeattribute"})
AV=frozenset({"allow","auditallow","dontaudit","allowx","auditallowx","dontauditx"})
TRANSITIONS=frozenset({"typetransition","typechange","typemember","roletransition"})
DNS_PORT=["portcon","tcp","53",["u","object_r","p4_linux_timesyncd_dns_port_t",[["s0"],["s0"]]]]
BASELINE_TYPES={"forms":2721,"unique_forms":2721,"sha256":"d1232a71a890c6d716691d8ddad9b2c0756db81841ae0e2b59c75758923020b8"}
BASELINE_PROJECTED={"non_audit":{"forms":57672,"unique_forms":57672,"sha256":"b035503f2603fc449ff8b92b2703423acaef7c37d4e68985ce06f24ffb171254"},"audit":{"forms":834,"unique_forms":834,"sha256":"f729165a8ab160310b156485df5922c83fc52906e3d386708ed5fea7d95ed748"},"type_membership":{"forms":4261,"unique_forms":4261,"sha256":"671818312dfb0bcd46ed769510e77ac9cbf4a5881a9fdcb151e97721959e2117"},"allow":{"forms":44569,"unique_forms":44569,"sha256":"dffd0f4d69c63bcb4b7c5ca89c8ddb462207ad47c8167e6fb8708036d9a6965b"},"allowx":{"forms":1991,"unique_forms":1991,"sha256":"2d69e92789d41c373bce63b89b983098572a173b25b4240bd392c306dab08075"}}

def canonical(form):
 return json.dumps(form,ensure_ascii=True,separators=(",",":"))
def commitment(forms):
 rows=sorted(canonical(f) for f in forms)
 return {"forms":len(rows),"unique_forms":len(set(rows)),
         "sha256":hashlib.sha256("".join(x+"\n" for x in rows).encode("ascii")).hexdigest()}
def atoms(form):
 if isinstance(form,str):return {form}
 if not isinstance(form,list):raise ValueError("Non-CIL AST")
 out=set()
 for v in form:out.update(atoms(v))
 return out
def forms(text):
 out=[];seen=set()
 for number,line in enumerate(text.splitlines(),1):
  line=line.strip()
  if not line or line.startswith(";"):continue
  f=parse_expression(line)
  if not isinstance(f,list) or not f or not isinstance(f[0],str):raise ValueError("Invalid final CIL at "+str(number))
  token=canonical(f)
  if token in seen:raise ValueError("Duplicate final CIL form")
  seen.add(token);out.append(f)
 return out

class ConcreteSets:
 def __init__(self,m):
  self.m=m;self.all=m.types;self.cache={};self.active=set()
 def members(self,name):
  if isinstance(name,list):return self.evaluate(name)
  if name in self.all:return frozenset({name})
  if name=="self":raise ValueError("Self needs the concrete source set")
  if name in self.cache:return self.cache[name]
  if name not in self.m.attributes or name in self.active:raise ValueError("Unknown/cyclic type set "+name)
  self.active.add(name);out=set()
  for definition in self.m.definitions[name]:out.update(self.evaluate(definition))
  self.active.remove(name);value=frozenset(out);self.cache[name]=value
  return value
 def evaluate(self,expr):
  if isinstance(expr,str):return self.members(expr)
  if not isinstance(expr,list):raise ValueError("Invalid type-set AST")
  if not expr:return frozenset()
  op,*args=expr
  if op=="all":
   if args:raise ValueError("Invalid all type-set")
   return frozenset(self.all)
  if op=="not":
   if len(args)!=1:raise ValueError("Invalid not type-set")
   return self.all-self.evaluate(args[0])
  if op in ("and","or"):
   if not args:raise ValueError("Empty Boolean type-set")
   out=set(self.all) if op=="and" else set()
   for arg in args:
    if op=="and":out.intersection_update(self.evaluate(arg))
    else:out.update(self.evaluate(arg))
   return frozenset(out)
  if op=="xor":
   if len(args)!=2:raise ValueError("Invalid xor type-set")
   return self.evaluate(args[0])^self.evaluate(args[1])
  out=set()
  for arg in expr:out.update(self.evaluate(arg))
  return frozenset(out)

def normalise_allow(items):
 merged={};out=[]
 for f in items:
  if f[0]!="allow":out.append(f);continue
  if len(f)!=4 or not isinstance(f[3],list) or len(f[3])!=2:raise ValueError("Unknown raw allow shape")
  k=(f[1],f[2],f[3][0]);ps=f[3][1]
  if any(not isinstance(x,str) for x in k) or not isinstance(ps,list) or any(not isinstance(x,str) for x in ps):raise ValueError("Unexpanded raw allow")
  merged.setdefault(k,set()).update(ps)
 out.extend(["allow",a,b,[c,sorted(ps)]] for (a,b,c),ps in sorted(merged.items()) if ps)
 return out


INTERPRETER_ATTRIBUTE="p4_linux_dynamic_interpreter_clients"
INTERPRETER_ORIGINAL="p4_linux_procs"
INTERPRETER_TARGET="p4_linux_elf_interpreter_t"
STATIC_LDCONFIG="p4_linux_ldconfig_t"
INTERPRETER_PERMISSIONS=["execute","getattr","map","open","read"]

def project_interpreter_source(items,membership,sets,old):
 """Normalize only the reviewed interpreter allow after exact member proof."""
 items=normalise_allow(items)
 if INTERPRETER_ATTRIBUTE not in membership.attributes:
  return items,{"present":False,"normalized_allow_rules":0}
 if STATIC_LDCONFIG not in membership.types:
  raise ValueError("Interpreter source projection requires the fixed static ldconfig type")
 original=sets.members(INTERPRETER_ORIGINAL)
 if STATIC_LDCONFIG not in original:
  raise ValueError("Static ldconfig lost its declared native guard membership")
 selected=sets.members(INTERPRETER_ATTRIBUTE)
 if selected!=original-{STATIC_LDCONFIG} or selected&old!=original&old:
  raise ValueError("Interpreter clients differ from exactly native processes minus static ldconfig")
 wanted=["allow",INTERPRETER_ATTRIBUTE,INTERPRETER_TARGET,["file",INTERPRETER_PERMISSIONS]]
 definitions=declarations=rewrites=0
 out=[]
 for f in items:
  if INTERPRETER_ATTRIBUTE in atoms(f):
   if f[0]=="typeattribute" and f==["typeattribute",INTERPRETER_ATTRIBUTE]:
    declarations+=1
   elif f[0]=="typeattributeset" and len(f)==3 and f[1]==INTERPRETER_ATTRIBUTE:
    definitions+=1
   elif f==wanted:
    f=["allow",INTERPRETER_ORIGINAL,INTERPRETER_TARGET,["file",list(INTERPRETER_PERMISSIONS)]]
    rewrites+=1
   else:
    raise ValueError("Interpreter attribute appears outside its single reviewed source allow")
  elif (f[0]=="allow" and len(f)==4 and f[1]==INTERPRETER_ORIGINAL
        and f[2]==INTERPRETER_TARGET and f[3][0]=="file"):
   raise ValueError("Original interpreter source allow remains beside the reviewed replacement")
  out.append(f)
 if (declarations,definitions,rewrites)!=(1,1,1):
  raise ValueError("Interpreter source replacement is missing or repeated")
 return out,{
  "present":True,"exact_source_attribute_rewrite":True,"normalized_allow_rules":1,
  "source_attribute":INTERPRETER_ATTRIBUTE,"original_source_attribute":INTERPRETER_ORIGINAL,
  "excluded_new_type":STATIC_LDCONFIG,"target":INTERPRETER_TARGET,
  "class":"file","permissions":list(INTERPRETER_PERMISSIONS),
  "all_old_members_equal":True,
  "old_members":commitment(["type",t] for t in sorted(original&old)),
 }

def project(items,membership):
 """Return old-only symbolic authority; never discard an unmodeled statement."""
 sets=ConcreteSets(membership)
 new=membership.types&NEW_TYPES
 old=membership.types-new
 items,interpreter_projection=project_interpreter_source(items,membership,sets,old)
 selected={"kernel","init_t","p4_linux_service_executor_t","p4_linux_netplan_t"}&old
 for name in sorted(membership.attributes):
  value=sets.members(name)
  for actor in selected:
   if (actor in value)!=membership.member(name,actor):raise ValueError("Set evaluator differs from normal concrete membership")
 out=[];decls={};definitions={};removed=[]
 for f in items:
  op=f[0];a=atoms(f)
  if op=="type" and f[1] in new:removed.append(f);continue
  if op=="roletype" and f[2] in new:removed.append(f);continue
  if op=="typeattribute":
   if len(f)!=2 or f[1] in decls:raise ValueError("Duplicate attribute declaration")
   decls[f[1]]=f;continue
  if op=="typeattributeset":
   if len(f)!=3:raise ValueError("Unknown type set shape")
   definitions[f[1]]=["typeattributeset",f[1],sorted(sets.members(f[1])&old)]
   continue
  if op in AV:
   if len(f)!=4:raise ValueError("Unknown AV statement")
   left=sets.members(f[1]);right=left if f[2]=="self" else sets.members(f[2])
   if not left&old or not right&old:removed.append(f);continue
  elif op in TRANSITIONS:
   if a&new:removed.append(f);continue
  elif op=="portcon":
   if f!=DNS_PORT:raise ValueError("Unreviewed port context")
   removed.append(f);continue
  elif a&new:
   raise ValueError("Unmodeled new-type authority: "+canonical(f))
  out.append(f)
 used=set()
 for f in out:used.update(atoms(f)&membership.attributes)
 if not used<=decls.keys():raise ValueError("Referenced type attribute lacks a declaration")
 if not ORIGINAL_ATTRIBUTES<=decls.keys():raise ValueError("An original attribute declaration disappeared")
 retained=used|ORIGINAL_ATTRIBUTES
 for name in sorted(retained):
  out.append(decls[name])
  if name in definitions:out.append(definitions[name])
 return normalise_allow(out),{
  "reviewed_interpreter_source_attribute":interpreter_projection,
  "original_concrete_types":commitment(["type",x] for x in sorted(old)),
  "new_types":sorted(new),
  "removed_new_type_authority_forms":len(removed),
  "removed_new_type_authority":commitment(removed),
  "unreferenced_attribute_declarations":sorted(membership.attributes-retained),
  "all_original_attribute_declarations_retained":True,
  "original_attribute_declarations":len(ORIGINAL_ATTRIBUTES),
  "membership_equivalence_vectors":len(membership.attributes)*len(selected),
 }

def walk(f):
 yield f
 for v in f:
  if isinstance(v,list):yield from walk(v)
def summaries(items):
 items=normalise_allow(items)
 flat=[f for top in items for f in walk(top) if f and isinstance(f[0],str)]
 return {
  "non_audit":commitment(f for f in items if f[0] not in AUDIT),
  "audit":commitment(f for f in items if f[0] in AUDIT),
  "type_membership":commitment(f for f in items if f[0] in TYPE_OPERATIONS),
  "allow":commitment(f for f in flat if f[0]=="allow"),
  "allowx":commitment(f for f in flat if f[0]=="allowx"),
 }
def verify_projection(items,membership):
 if BASELINE_TYPES is None or BASELINE_PROJECTED is None:raise ValueError("Original projection is not bound")
 projected,proof=project(items,membership)
 if proof["original_concrete_types"]!=BASELINE_TYPES:raise ValueError("Original concrete type inventory changed")
 actual=summaries(projected)
 if actual!=BASELINE_PROJECTED:raise ValueError("Original policy authority changed outside reviewed native grants")
 proof.update(schema=SCHEMA,canonical_original_commitments=actual,
              all_original_authority_preserved=True,runtime_qualified=False)
 return proof
