"""Verify normal secure-exec standard I/O and the executor's fixed logger."""
import hashlib
import json

from derive_shared_payload_cgroup_policy import parse_expression

SOURCE_PINS = {
    "runtime/droidloom-supervisor/src/droidloom-mac-calibration.service": (
        1373, "c75560036d34b1538fa01f607242c08701620689c55e2d45fffe159c75e8811b"),
    "runtime/droidloom-supervisor/src/droidloom-manager-label.service": (
        688, "950117ce47fbbc389de135d346f7c7c0e20e025565065a1f498e1f2b4d9d376c"),
}
ACTORS = (
    ("system_r", "p4_linux_journalctl_t"),
    ("r", "droidloom_policy_loader"),
)
SELF_STREAM = {"create", "getattr", "read", "write", "connect",
               "getopt", "setopt", "shutdown"}
EXECUTOR_LOG_SOCKET = {"create", "connect", "write", "getopt", "setopt"}


def source_inputs(here):
    return [here.parents[3] / name for name in SOURCE_PINS]


def verify_sources(here):
    root = here.parents[3]
    sources = {}
    for name, expected in SOURCE_PINS.items():
        body = (root / name).read_bytes()
        actual = (len(body), hashlib.sha256(body).hexdigest())
        if actual != expected:
            raise ValueError("Normal stdio unit source differs: " + name)
        sources[name] = {"bytes": actual[0], "sha256": actual[1]}
    # /dev/null's stock FC remains Android null_device. The admitted early
    # projector mounts the exact ext4 bank inode over it; do not grant the
    # kernel's distinct internal selinux_null fallback device.
    source = (root / "runtime/droidloom-early-boot/linux_run_label.c").read_text()
    expected = {
        '    { "/dev/null", "/usr/lib/droidloom/production/current/board-devices/null", 1, 3, 0666, 0666 },',
        '    { "/dev/full", "/usr/lib/droidloom/production/current/board-devices/full", 1, 7, 0666, 0666 },',
    }
    if not expected.issubset(set(source.splitlines())):
        raise ValueError("Exact normal standard-device projection changed")
    aliases = set()
    for path in here.glob("*file_contexts"):
        for line in path.read_text().splitlines():
            if not line.lstrip().startswith("#") and "u:object_r:p4_linux_standardio_t:s0" in line:
                aliases.add((path.name, line.strip()))
    wanted = {
        ("ubuntu-native-file_contexts", "/dev/full -c u:object_r:p4_linux_standardio_t:s0"),
        ("ubuntu-real-root-file_contexts",
         "/usr/lib/droidloom/production/current/board-devices/(null|full) -c u:object_r:p4_linux_standardio_t:s0"),
    }
    if aliases != wanted:
        raise ValueError("Normal standard-device source alias closure changed")
    logger_sources = {}
    for manifest, path, expected in (
        ("native-logind-state-source.json", "src/core/executor.c",
         (11487, "3cc97598a5d6bc2f0c78f971c5b9a5151ba47ace976ca01395a47453f99abafb")),
        ("native-timesync-source.json", "src/basic/log.c",
         (56820, "2d578efd6b1f5a1acb85f82ad88901e44b9a6845496f15c470fbbd153355fd42")),
    ):
        contract = json.loads((here / manifest).read_text())
        rows = [row for row in contract["source_documents"] if row["path"] == path]
        if len(rows) != 1 or (rows[0]["bytes"], rows[0]["sha256"]) != expected:
            raise ValueError("Original executor logger source differs: " + path)
        logger_sources[path] = {"bytes": expected[0], "sha256": expected[1]}
    return {"unit_sources": sources, "executor_logger_sources": logger_sources,
            "normal_device_aliases": sorted(aliases),
            "projected_paths": ["/dev/null", "/dev/full"],
            "kernel_internal_null_device_granted": False}


def class_permissions(lines, name):
    """Include the binary's inherited common vocabulary, not just local bits."""
    forms = [parse_expression(line) for line in lines
             if line.startswith(("(class ", "(common ", "(classcommon "))]
    declarations = [form[2] for form in forms if form[:2] == ["class", name]]
    inherited = [form[2] for form in forms if form[:2] == ["classcommon", name]]
    if len(declarations) != 1 or len(inherited) > 1:
        raise ValueError("Unexpected stdio class vocabulary: " + name)
    permissions = declarations[0][:]
    if inherited:
        common = [form[2] for form in forms
                  if form[:2] == ["common", inherited[0]]]
        if len(common) != 1:
            raise ValueError("Missing stdio common vocabulary: " + name)
        permissions = common[0] + permissions
    if (not permissions or len(set(permissions)) != len(permissions)
            or len(permissions) > 32 or any(not isinstance(p, str) for p in permissions)):
        raise ValueError("Invalid stdio permission vocabulary: " + name)
    return permissions


def verify_native_stdio(lines, check, obj, here):
    source = verify_sources(here)
    vocabulary = {kind: class_permissions(lines, kind)
                  for kind in ("chr_file", "unix_stream_socket", "unix_dgram_socket", "sock_file", "file")}
    executor = "u:system_r:p4_linux_service_executor_t:s0"
    count = 0

    def exact(actor, target, kind, expected):
        nonlocal count
        for permission in vocabulary[kind]:
            check(actor, target, kind, [permission], permission in expected)
            count += 1

    for role, name in ACTORS:
        actor = f"u:{role}:{name}:s0"
        exact(actor, obj("p4_linux_standardio_t"), "chr_file",
              ({"getattr", "read", "write"} if name == "p4_linux_journalctl_t"
               else {"read", "write"}))
        for target in ("null_device", "device"):
            exact(actor, obj(target), "chr_file", set())
        # systemd connect_logger_as() sockets retain FMODE_READ|FMODE_WRITE
        # after shutdown(SHUT_RD). Secure exec requires both access bits.
        exact(actor, executor, "unix_stream_socket",
              ({"getattr", "read", "write"} if name == "p4_linux_journalctl_t"
               else {"read", "write"}))
        check(actor, executor, "fd", ["use"], True)
        count += 1
        # These are the pre-existing Varlink/manager clients. Do not pretend
        # they never created sockets, nor broaden their inherited endpoint.
        exact(actor, actor, "unix_stream_socket", SELF_STREAM)
    # Calibration stdout is the existing O_WRONLY capture FD, never reopened.
    exact("u:r:droidloom_policy_loader:s0", obj("p4_linux_mac_capture_t"),
          "file", {"getattr", "write"})
    actors = sorted({(role, line[len(f"(roletype {role} "):-1])
                     for role in ("r", "system_r") for line in lines
                     if line.startswith(f"(roletype {role} ")})
    for role, actor in actors:
        target = f"u:{role}:{actor}:s0"
        wanted = (EXECUTOR_LOG_SOCKET if target == executor else
                  {"read", "write"} if target == "u:system_r:init_t:s0" else
                  {"getattr", "read", "write", "sendto"} if
                  target == "u:system_r:p4_linux_journald_t:s0" else set())
        exact(executor, target, "unix_dgram_socket", wanted)
    exact(executor, obj("p4_linux_journal_native_socket_t"), "sock_file", {"write"})
    transitions = (
        "(typetransition p4_linux_service_executor_t p4_linux_journalctl_exec_t process p4_linux_journalctl_t)",
        "(typetransition p4_linux_service_executor_t droidloom_policy_loader_exec process droidloom_policy_loader)",
        "(roletransition system_r droidloom_policy_loader_exec process r)",
    )
    if not set(transitions).issubset(lines):
        raise ValueError("Normal stdio executable transition changed")
    return {**source, "actors": [name for _, name in ACTORS],
            "binary_permission_checks": count, "new_te_permission_bits": 5,
            "standardio_permissions": {"p4_linux_journalctl_t": ["getattr", "read", "write"],
                                      "droidloom_policy_loader": ["read", "write"]},
            "inherited_executor_stream_permissions": {
                "p4_linux_journalctl_t": ["getattr", "read", "write"],
                "droidloom_policy_loader": ["read", "write"]},
            "existing_self_stream_permissions": sorted(SELF_STREAM),
            "executor_logger": {"self_socket_permissions": sorted(EXECUTOR_LOG_SOCKET),
                                "fixed_endpoint": "/run/systemd/journal/socket",
                                "new_datagram_peers": ["p4_linux_journald_t"],
                                "binding_or_receiving_granted": False},
            "capture_stdout_not_reopened": True,
            "device_ioctl_added": False, "runtime_qualified": False}
