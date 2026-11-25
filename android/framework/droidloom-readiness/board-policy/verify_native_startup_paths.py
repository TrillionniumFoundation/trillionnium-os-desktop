"""Exact native startup inode boundaries, measured from the linked policy."""
import hashlib
import json

GROUPS = (
    ("setup", "p4_linux_setup_t", (
        "systemd-tmpfiles-setup-dev-early.service",
        "systemd-tmpfiles-setup-dev.service", "systemd-tmpfiles-setup.service",
        "systemd-tmpfiles-clean.service", "systemd-sysusers.service")),
    ("sysctl", "p4_linux_sysctl_t", ("systemd-sysctl.service",)),
    ("udev", "p4_linux_udev_t", ("systemd-udev-load-credentials.service",)),
    ("resolved", "p4_linux_resolved_t", ("systemd-resolved.service",)),
    ("journal", "p4_linux_journald_t", ("systemd-journald.service",)),
)


def startup_file_context_cases(stat):
    cases = [
        ("/run/systemd/ask-password", stat.S_IFDIR, "p4_linux_systemd_run_t"),
        ("/run/systemd/ask-password-extra", stat.S_IFDIR, "p4_linux_rootdir_t"),
        ("/run/credentials", stat.S_IFDIR, "p4_linux_credentials_root_t"),
        ("/run/systemd/temporary-credentials", stat.S_IFDIR, "p4_linux_credential_staging_t"),
        ("/run/systemd/units/invocation:keyboard-setup.service", stat.S_IFLNK, "p4_linux_invocation_link_t"),
        ("/run/systemd/units/.#invocation:keyboard-setup.service0123456789abcdef", stat.S_IFLNK, "p4_linux_invocation_link_t"),
        ("/run/systemd/units/unselected-link", stat.S_IFLNK, "p4_linux_usrmerge_link_t"),
        ("/run/systemd/units/invocation:example.service", stat.S_IFREG, "p4_linux_native_data_t"),
        ("/bin", stat.S_IFLNK, "p4_linux_usrmerge_link_t"),
        ("/dev/kmsg", stat.S_IFCHR, "p4_linux_native_kmsg_t"),
        ("/dev/kmsg", stat.S_IFREG, "p4_linux_native_data_t"),
    ]
    for root in ("/run/credentials", "/run/systemd/temporary-credentials"):
        for short, _, units in GROUPS:
            directory = "p4_linux_" + short + "_credentials_t"
            payload = ("p4_linux_journal_credential_file_t"
                       if short == "journal" else directory)
            for unit in units:
                path = root + "/" + unit
                cases.extend([
                    (path, stat.S_IFDIR, directory),
                    (path + "/selected.credential", stat.S_IFREG, payload),
                    (path + "-unselected", stat.S_IFDIR, "p4_linux_rootdir_t"),
                    (path + "/unselected-directory", stat.S_IFDIR, "p4_linux_rootdir_t"),
                    (path + "/unselected-symlink", stat.S_IFLNK, "p4_linux_usrmerge_link_t"),
                ])
    return cases


def verify_startup_paths(lines, check, obj, role_types):
    checks = []
    def test(subject, target, kind, permissions, allowed):
        check(subject, target, kind, permissions, allowed)
        checks.extend([subject, target, kind, perm, allowed] for perm in permissions)

    manager = "u:system_r:init_t:s0"
    executor = "u:system_r:p4_linux_service_executor_t:s0"
    test(manager, obj("p4_linux_run_t"), "dir", ["read", "watch"], True)
    test(manager, obj("p4_linux_systemd_run_t"), "dir", ["create", "read", "watch"], True)
    test(manager, obj("p4_linux_rootdir_t"), "dir", ["create", "write", "add_name"], False)
    test(manager, obj("p4_linux_usrmerge_link_t"), "lnk_file", ["create", "write", "rename", "unlink"], False)
    test(manager, obj("p4_linux_cgroup_root_membership_t"), "file", ["write", "open", "read", "append"], False)
    test(manager, manager, "capability", ["dac_override", "dac_read_search"], False)
    for parent in ("p4_linux_credentials_root_t", "p4_linux_credential_staging_t"):
        test(manager, obj(parent), "dir", ["getattr", "search", "open", "read", "write", "remove_name"], True)
        test(manager, obj(parent), "dir", ["create", "setattr", "rename", "rmdir", "relabelto", "relabelfrom"], False)
    test(executor, obj("p4_linux_credentials_root_t"), "dir", ["mounton"], True)
    test(executor, obj("p4_linux_credentials_root_t"), "dir", ["create", "rename", "rmdir", "relabelto", "relabelfrom"], False)
    test(executor, obj("p4_linux_credential_staging_t"), "dir", ["mounton"], False)

    file_perms = (
        "getattr open read write append create setattr unlink link rename ioctl "
        "lock map execute execute_no_trans entrypoint relabelto relabelfrom mounton"
    ).split()
    dir_perms = (
        "getattr search open read create write add_name remove_name setattr rename "
        "reparent rmdir mounton relabelto relabelfrom"
    ).split()
    link_perms = (
        "getattr read create write setattr rename unlink link relabelto relabelfrom mounton"
    ).split()
    transitions = ['(typetransition init_t p4_linux_systemd_run_t dir "ask-password" p4_linux_systemd_run_t)']
    for short, reader, units in GROUPS:
        directory = "p4_linux_" + short + "_credentials_t"
        payload = "p4_linux_journal_credential_file_t" if short == "journal" else directory
        transitions.append(
            f"(typetransition p4_linux_service_executor_t {directory} file {payload})")
        for parent in ("p4_linux_credentials_root_t", "p4_linux_credential_staging_t"):
            for unit in units:
                transitions.append(
                    f'(typetransition p4_linux_service_executor_t {parent} dir "{unit}" {directory})')
        for role, actor in role_types:
            context = f"u:{role}:{actor}:s0"
            allowed = set()
            if actor == "p4_linux_service_executor_t":
                allowed = {"getattr", "open", "read", "create", "write", "setattr", "rename", "unlink"}
            elif actor == reader:
                allowed = {"getattr", "open", "read"}
            elif actor == "init_t":
                allowed = {"getattr", "unlink"}
            for perm in file_perms:
                test(context, obj(payload), "file", [perm], perm in allowed)
            # Journal directory access predates this component; do not silently
            # redefine the old metadata interface. Its new payload is checked
            # above for every actual process role just like the four new stores.
            if short == "journal":
                continue
            allowed_dir = set()
            if actor == "p4_linux_service_executor_t":
                allowed_dir = set(dir_perms) - {"relabelfrom"}
            elif actor == reader:
                allowed_dir = {"getattr", "search", "open", "read"}
            elif actor == "init_t":
                allowed_dir = {"getattr", "search", "open", "read", "write", "remove_name", "setattr", "rmdir"}
            for perm in dir_perms:
                test(context, obj(directory), "dir", [perm], perm in allowed_dir)

    for role, actor in role_types:
        context = f"u:{role}:{actor}:s0"
        for perm in link_perms:
            test(context, obj("p4_linux_invocation_link_t"), "lnk_file", [perm],
                 actor == "init_t" and perm in {"getattr", "read", "create", "rename", "unlink"})
        test(context, obj("p4_linux_credentials_root_t"), "dir", ["mounton"],
             actor == "p4_linux_service_executor_t")
    kmsg_perms = ("getattr open read write append create setattr ioctl map execute "
                  "execute_no_trans entrypoint lock link rename unlink relabelto relabelfrom mounton").split()
    for role, actor in role_types:
        allowed = {
            "kernel": {"getattr", "relabelto"},
            "init_t": {"getattr", "open", "write"},
            "p4_linux_service_executor_t": {"getattr", "open", "write", "mounton"},
            "p4_linux_generator_t": {"getattr", "open", "write"},
            "p4_linux_journald_t": {"getattr", "open", "read", "write"},
            "p4_linux_udev_t": {"getattr", "setattr"},
        }.get(actor, set())
        for perm in kmsg_perms:
            test(f"u:{role}:{actor}:s0", obj("p4_linux_native_kmsg_t"),
                 "chr_file", [perm], perm in allowed)
    missing = [entry for entry in transitions if entry not in lines]
    if missing:
        raise ValueError("Missing stock startup transitions: " + repr(missing))
    return {
        "process_role_types": len(role_types),
        "permission_checks": len(checks),
        "credential_owners": len(GROUPS),
        "exact_automatic_transitions": len(transitions),
        "access_matrix_sha256": hashlib.sha256(
            json.dumps(checks, separators=(",", ":")).encode()).hexdigest(),
        "runtime_qualified": False,
    }
