"""Fixed source/unit/input contract for the independent EMPTY diagnostic.

Its actual peer, empty-image whole-byte proof, ordinary PM transaction and
launch result belong to the normal runtime. These checks grant no runtime or
production qualification and never turn a serialized claim into authority.
"""
import hashlib
import json
import re

DIRECTORY = "/var/lib/droidloom-qualification/empty-meituan-diagnostic"
APK = DIRECTORY + "/official.apk"
UNIT = "packaging/systemd/system/droidloom-empty-meituan-diagnostic.service"
RUNTIME = "runtime/droidloom-supervisor/src/"
FIXTURE = "tools/droidloom-ubuntu-fixture/src/"
# Keep the admission and actual calls, not just the leaf implementations: the
# fresh-image capability must be obtained before any writable open and consumed
# by the same live installation authority. The fixture preserves ordinary boot,
# actual child retirement and source-attributed journal comparison separately.
# These are fixed reviewed source names, never discovered from a candidate's
# manifest. Generic dependencies remain covered by the normal build custody.
FILES = frozenset((
    UNIT,
    "tools/droidloom-update/src/early_boot_package.rs",
    *(RUNTIME + name for name in (
        "bin/droidloomctl.rs", "control.rs", "control_identity.rs",
        "control_identity_empty_meituan.rs", "control_progress.rs",
        "empty_meituan_contract.rs", "lib.rs", "main_custody.rs",
        "native_empty_meituan_install.rs", "production_application.rs",
        "production_application_empty_meituan.rs", "production_application_operation.rs",
        "production_early_application_control.rs", "production_early_main_custody.rs",
        "production_empty_meituan_peer.rs", "production_package.rs",
        "production_package_peer.rs", "production_persistent_data_backings.rs",
        "production_persistent_data_custody.rs", "production_persistent_data_fixture_backings.rs",
        "production_persistent_data_fresh.rs", "production_persistent_data_policy.rs",
        # run_budget() derives its one observation/shutdown allowance from
        # these actual normal units and UNIT above, without renewing a deadline.
        "droidloom-manager-label.service", "droidloom-instance-factory.service",
        "droidloom-instance-launcher.service", "droidloom-early-observer.service",
        "droidloom-production.service")),
    *(FIXTURE + name for name in (
        "main.rs", "boot.rs", "boot_release.rs", "boot_empty_meituan.rs",
        "boot_vm.rs", "boot_collect.rs", "boot_empty_meituan_capture.rs",
        "boot_empty_meituan_plan.rs", "boot_owned_evidence.rs")),
))
UNIT_VALUES = {
    "ConditionPathExists": APK, "Type": "exec", "User": "root", "Group": "root",
    "ExecStart": "/usr/bin/droidloomctl empty-meituan-diagnostic", "Restart": "no",
    "CapabilityBoundingSet": "CAP_SETUID CAP_SETGID CAP_SYS_PTRACE", "AmbientCapabilities": "",
    "NoNewPrivileges": "no", "RuntimeMaxSec": "780s", "UMask": "0077", "WorkingDirectory": "/",
    "SELinuxContext": "u:system_r:p4_linux_working_privateprep_t:s0",
    "AppArmorProfile": "droidloom-working-privateprep",
    "StandardOutput": "journal", "StandardError": "journal",
}


def source_inputs(here):
    root = here.parents[3]
    return [here / "empty-meituan-source.json", here / "verify_empty_meituan.py",
            here / "apparmor/droidloom-working-privateprep",
            here / "apparmor/droidloom-production-broker", *(root / name for name in sorted(FILES))]


def verify_unit(text):
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if line == "[Install]":
            raise ValueError("The independent EMPTY diagnostic must not be enabled by normal publication")
        if not line or line.startswith(("#", ";", "[")):
            continue
        if "=" not in line or line.endswith("\\"):
            raise ValueError("The EMPTY unit is not a literal source-owned recipe")
        key, value = line.split("=", 1)
        if key in UNIT_VALUES:
            if key in values:
                raise ValueError("Repeated EMPTY unit authority key")
            values[key] = value
    if values != UNIT_VALUES:
        raise ValueError("EMPTY diagnostic unit argv/actor/capabilities/input/output differ")


def verify_apparmor(profiles):
    wanted = {DIRECTORY + "/ r,", APK + " r,"}
    for name in ("droidloom-working-qualification", "droidloom-working-privateprep",
                 "droidloom-working-application", "droidloom-working-qualification-return"):
        rows = [line.strip() for line in profiles[name].splitlines()
                if DIRECTORY in line and not line.strip().startswith("#")]
        expected = wanted if name == "droidloom-working-privateprep" else set()
        if set(rows) != expected or len(rows) != len(expected):
            raise ValueError("EMPTY input AppArmor access escaped its sole preparation reader")
    prep = profiles["droidloom-working-privateprep"].splitlines()
    broker = profiles["droidloom-production-broker"].splitlines()
    if sum(line.strip() == "ptrace (readby) peer=droidloom-production-broker," for line in prep) != 1:
        raise ValueError("EMPTY actual peer readback lacks the exact readby boundary")
    for wanted in ("/usr/bin/droidloomctl r,", "ptrace (read) peer=droidloom-working-privateprep,"):
        if sum(line.strip() == wanted for line in broker) != 1:
            raise ValueError("EMPTY broker readback is not confined to the actual fixed peer")


def verify_sources(here):
    value = json.loads((here / "empty-meituan-source.json").read_bytes())
    if (set(value) != {"schema", "reviewed_runtime_commit", "runtime_qualified", "files"}
            or value["schema"] != "droidloom.empty-meituan-mac-source.v1"
            or value["runtime_qualified"] is not False
            or not re.fullmatch(r"[0-9a-f]{40}", value["reviewed_runtime_commit"])
            or set(value["files"]) != FILES):
        raise ValueError("EMPTY runtime causal source closure differs")
    root = here.parents[3]
    for name, pin in value["files"].items():
        body = (root / name).read_bytes()
        if pin != {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}:
            raise ValueError("Changed EMPTY runtime source: " + name)
    verify_unit((root / UNIT).read_text())
    verify_apparmor({name: (here / "apparmor" / name).read_text() for name in (
        "droidloom-working-qualification", "droidloom-working-privateprep",
        "droidloom-working-application", "droidloom-working-qualification-return",
        "droidloom-production-broker")})
    return value
