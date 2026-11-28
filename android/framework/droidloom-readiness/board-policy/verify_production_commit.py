"""Close the live Complete handoff and fresh ordinary-boot activation actors.

The source-owned ACL, roles, named outputs and cross-profile blocks are
independent expectations. Full raw inbound/outbound AV, audits, ioctl ranges,
transitions and constrained vectors must agree. This is policy qualification;
it never establishes Complete, a normal shutdown, activation or app readiness.
"""
import ctypes
import hashlib
import json
import re
from collections import defaultdict
from pathlib import PurePosixPath

from derive_shared_payload_cgroup_policy import Decision, Policy
from verify_working_qualification import (
    _Index as CommonIndex, _forms, _atoms, _canonical, _hash, _xvalues,
    _fixed_aliases, FLOW_TAGS, TRANSITION_TAGS, CONTEXT_TAGS,
)

COMMIT = "p4_linux_production_commit_t"
VERIFY = "p4_linux_production_verify_t"
PARENT = "p4_linux_working_qualification_t"
SUBJECTS = frozenset((COMMIT, VERIFY))
OWNED = frozenset(["p4_linux_production_commit_t","p4_linux_production_verify_t","p4_linux_production_config_t","p4_linux_production_record_dir_t","p4_linux_production_record_t","p4_linux_production_activation_t","p4_linux_production_verify_unit_t"])
GROUPS = {"p4_production_commit_actors": SUBJECTS}
MAX_MATRIX_ROWS = 250000
CONTRACT_SHA256 = '0bd69cc3096661123034cc3bcadb5f9b1d10a41c6aa5d53503c6950f8a6edd92'
PROFILES = ("droidloom-production-commit", "droidloom-production-verify")
FILES = tuple(["runtime/droidloom-supervisor/src/production_commit.rs","runtime/droidloom-supervisor/src/production_commit_contract.rs","runtime/droidloom-supervisor/src/production_commit_io.rs","runtime/droidloom-supervisor/src/production_commit_records.rs","runtime/droidloom-supervisor/src/production_commit_source.rs","runtime/droidloom-supervisor/src/production_commit_verify.rs","runtime/droidloom-applications/src/main.rs","runtime/droidloom-applications/src/working_dispatch.rs","runtime/droidloom-supervisor/src/control_identity.rs","runtime/droidloom-supervisor/src/lib.rs","runtime/droidloom-supervisor/src/native_working_contract.rs","runtime/droidloom-supervisor/src/native_once_contract.rs","runtime/droidloom-supervisor/src/physical_qualification_capture.rs","runtime/droidloom-supervisor/src/physical_qualification_channel.rs","runtime/droidloom-supervisor/src/physical_qualification_owner.rs","runtime/droidloom-supervisor/src/production_mac_self_attr.rs","runtime/droidloom-supervisor/src/native_hardware_label.rs","runtime/droidloom-supervisor/src/working_qualification.rs","runtime/droidloom-supervisor/src/working_qualification_child_exec.rs","packaging/systemd/system/droidloom-working-qualification.service","packaging/systemd/system/droidloom-production-verify.service","packaging/systemd/system/droidloom-production-verify-return.service","runtime/droidloom-supervisor/src/droidloom-production.service","runtime/droidloom-supervisor/src/droidloom-early-observer.service","runtime/droidloom-supervisor/src/droidloom-instance-launcher.service","runtime/droidloom-supervisor/src/droidloom-instance-factory.service","runtime/droidloom-supervisor/src/droidloom-manager-label.service","android/framework/droidloom-readiness/board-policy/ubuntu-production-commit.cil","android/framework/droidloom-readiness/board-policy/linux-production-commit-file_contexts","android/framework/droidloom-readiness/board-policy/ubuntu-working-qualification.cil","android/framework/droidloom-readiness/board-policy/pack_pocket4_ubuntu_apparmor.py","android/framework/droidloom-readiness/board-policy/apparmor/droidloom-production-commit","android/framework/droidloom-readiness/board-policy/apparmor/droidloom-production-verify","android/framework/droidloom-readiness/board-policy/apparmor/droidloom-working-qualification","android/framework/droidloom-readiness/board-policy/apparmor/droidloom-production-broker","android/framework/droidloom-readiness/board-policy/apparmor/droidloom-ubuntu-journald"])
FILE_CONTEXTS = tuple(["/etc/droidloom/production-commit\\.json -- u:object_r:p4_linux_production_config_t:s0","/etc/droidloom/production-grub-prefix\\.cfg -- u:object_r:p4_linux_production_config_t:s0","/boot/grub/custom\\.cfg -- u:object_r:p4_linux_production_config_t:s0","/boot/droidloom/production/[0-9a-f]{64}/initrd\\.img -- u:object_r:p4_linux_production_config_t:s0","/usr/lib/systemd/system/droidloom-production-verify(-return)?\\.service -- u:object_r:p4_linux_production_verify_unit_t:s0","/usr/share/droidloom/production/droidloom-production-verify(-return)?\\.service -- u:object_r:p4_linux_production_verify_unit_t:s0","/var/lib/droidloom/qualification/production-commit-[0-9a-f]{64} -d u:object_r:p4_linux_production_record_dir_t:s0","/var/lib/droidloom/qualification/production-commit-[0-9a-f]{64}/(PLAN|SUMMARY|MAIN|COMMIT|TRIAL|REQUEST)\\.json -- u:object_r:p4_linux_production_record_t:s0","/var/lib/droidloom/qualification/production-commit-[0-9a-f]{64}/STDERR\\.log -- u:object_r:p4_linux_production_record_t:s0","/var/lib/droidloom/qualification/production-commit-[0-9a-f]{64}/ACTIVE\\.json -- u:object_r:p4_linux_production_activation_t:s0"])
RECIPROCAL_BLOCKS = {
  "droidloom-working-qualification": "  # BEGIN fixed production Complete handoff (closed by verify_production_commit.py)\n  /etc/droidloom/production-commit.json r,\n  change_profile /usr/bin/droidloom-applications -> droidloom-production-commit,\n  ptrace (read, readby) peer=droidloom-production-commit,\n  unix (send, receive) type=seqpacket peer=(label=droidloom-production-commit),\n  signal (send, receive) peer=droidloom-production-commit,\n  /var/lib/droidloom-qualification/physical-[0-9a-f]*/{applications.stdout,applications.stderr,MAIN-BINDING.json} rw,\n  # END fixed production Complete handoff\n",
  "droidloom-production-broker": "  # BEGIN fixed production verifier peer (closed by verify_production_commit.py)\n  ptrace (readby) peer=droidloom-production-verify,\n  unix (send, receive) type=stream peer=(label=droidloom-production-verify),\n  # END fixed production verifier peer\n",
  "droidloom-ubuntu-journald": "  # BEGIN fixed production commit journal (closed by verify_production_commit.py)\n  # Trusted unit/credentials come from proc metadata and kernel SCM_SECURITY.\n  # No executable read, ptrace capability, cmdline, environ, mem or maps.\n  /proc/[0-9]*/{cgroup,status,comm,loginuid,sessionid} r,\n  unix (receive) type=dgram peer=(label=droidloom-production-commit),\n  unix (send, receive) type=stream peer=(label=droidloom-production-commit),\n  unix (send, receive) type=stream peer=(label=droidloom-production-verify),\n  # END fixed production commit journal\n"
}

# Deliberately separate from the policy source and the candidate raw export.
FIXED_ACL = r"""
(allow p4_linux_working_qualification_t p4_linux_production_commit_t (process (transition siginh rlimitinh getattr signull signal sigkill)))
(allow p4_linux_production_commit_t p4_linux_working_qualification_t (process (sigchld)))
(auditallow p4_linux_working_qualification_t p4_linux_production_commit_t (process (transition)))
(allow p4_linux_service_executor_t p4_linux_production_verify_t (process (transition siginh rlimitinh)))
(auditallow p4_linux_service_executor_t p4_linux_production_verify_t (process (transition)))
(allow p4_production_commit_actors droidloom_public_control_client_exec (file (getattr open read execute map entrypoint)))
(allow p4_production_commit_actors self (process (fork getattr getcap setcap sigchld signull sigkill)))
(allow p4_production_commit_actors self (capability (sys_ptrace)))
(allow p4_production_commit_actors self (fd (use)))
(allow p4_production_commit_actors self (dir (getattr search)))
(allow p4_production_commit_actors self (file (getattr open read)))
(allow p4_production_commit_actors self (lnk_file (getattr read)))
(allow p4_production_commit_actors self (fifo_file (getattr read write)))
(allow p4_production_commit_actors self (unix_stream_socket (create connect getattr read write getopt setopt shutdown)))
(allow p4_production_commit_actors p4_linux_rootdir_t (dir (getattr search)))
(allow p4_production_commit_actors p4_linux_etc_dir_t (dir (getattr search)))
(allow p4_production_commit_actors p4_linux_product_store_t (dir (getattr search)))
(allow p4_production_commit_actors p4_linux_run_t (dir (getattr search)))
(allow p4_production_commit_actors p4_linux_once_parent_t (dir (getattr search)))
(allow p4_production_commit_actors p4_linux_once_config_t (dir (getattr search)))
(allow p4_production_commit_actors droidloom_package_config_dir (dir (getattr search)))
(allow p4_production_commit_actors droidloom_package_selection_dir (dir (getattr search)))
(allow p4_production_commit_actors p4_linux_early_handoff_dir_t (dir (getattr search)))
(allow p4_production_commit_actors p4_linux_native_dev_root_t (dir (getattr search)))
(allow p4_production_commit_actors p4_linux_runtime_lib_t (file (getattr open read execute map)))
(allow p4_production_commit_actors p4_linux_elf_interpreter_t (file (getattr open read execute map)))
(allow p4_production_commit_actors p4_linux_console_ld_cache_native_config_t (file (getattr open read map)))
(allow p4_production_commit_actors p4_linux_usrmerge_link_t (lnk_file (getattr read)))
(allow p4_production_commit_actors p4_linux_root_uuid_link_t (lnk_file (getattr read)))
(allow p4_production_commit_actors p4_linux_root_block_t (blk_file (getattr)))
(allow p4_production_commit_actors null_device (chr_file (getattr open read write)))
(allow p4_production_commit_actors proc (dir (getattr search)))
(allow p4_production_commit_actors proc_random (dir (getattr search)))
(allow p4_production_commit_actors sysfs (dir (getattr search)))
(allow p4_production_commit_actors selinuxfs (dir (getattr search)))
(allow p4_production_commit_actors device (dir (getattr search)))
(allow p4_production_commit_actors proc (lnk_file (getattr read)))
(allow p4_production_commit_actors proc (file (getattr open read)))
(allow p4_production_commit_actors proc_random (file (getattr open read)))
(allow p4_production_commit_actors proc_cmdline (file (getattr open read)))
(allow p4_production_commit_actors selinuxfs (file (getattr open read)))
(allow p4_production_commit_actors labeledfs (filesystem (getattr)))
(allow p4_production_commit_actors tmpfs (filesystem (getattr)))
(allow p4_production_commit_actors proc (filesystem (getattr)))
(allow p4_production_commit_actors p4_kernel_ns_handle_t (filesystem (getattr)))
(allow p4_production_commit_actors p4_kernel_pid_handle_t (filesystem (getattr)))
(allow p4_production_commit_actors p4_kernel_ns_handle_t (file (getattr open read ioctl)))
(allowx p4_production_commit_actors p4_kernel_ns_handle_t (ioctl file (0xb703)))
(allow p4_production_commit_actors p4_kernel_pid_handle_t (file (getattr ioctl)))
(allowx p4_production_commit_actors p4_kernel_pid_handle_t (ioctl file (0xff05 0xff09 0xff0b)))
(allow p4_production_commit_actors p4_linux_production_config_t (file (getattr open read)))
(allow p4_production_commit_actors p4_linux_working_config_t (file (getattr open read)))
(allow p4_production_commit_actors p4_linux_mac_release_input_t (file (getattr open read)))
(allow p4_production_commit_actors p4_linux_host_mount_identity_t (file (getattr open read)))
(allow p4_production_commit_actors p4_linux_maintenance_grubcfg_t (file (getattr open read)))
(allow p4_production_commit_actors p4_linux_maintenance_grubenv_t (file (getattr open read write ioctl)))
(allowx p4_production_commit_actors p4_linux_maintenance_grubenv_t (ioctl file (0x7601)))
(allow p4_production_commit_actors p4_linux_native_bin_t (file (getattr open read execute execute_no_trans map)))
(allow p4_production_commit_actors p4_linux_journalctl_exec_t (file (getattr open read)))
(allow p4_linux_production_verify_t p4_linux_journalctl_exec_t (file (execute execute_no_trans map)))
(allow p4_production_commit_actors p4_linux_systemd_run_t (dir (getattr search)))
(allow p4_production_commit_actors droidloom_manager_private_socket (sock_file (getattr write)))
(allow p4_production_commit_actors init_t (unix_stream_socket (connectto)))
(allow init_t p4_production_commit_actors (unix_stream_socket (getattr read write)))
(allow p4_production_commit_actors p4_linux_maintenance_reboot_unit_t (service (status start)))
(allow p4_production_commit_actors init_t (process (sigchld)))
(allow init_t p4_production_commit_actors (process (getattr signull signal sigkill sigstop)))
(allow p4_production_commit_actors p4_linux_service_executor_t (fd (use)))
(allow p4_production_commit_actors p4_linux_service_executor_t (unix_stream_socket (getattr read write)))
(allow p4_linux_journald_t p4_production_commit_actors (dir (getattr search)))
(allow p4_linux_journald_t p4_production_commit_actors (file (getattr open read)))
(allow p4_linux_journald_t p4_production_commit_actors (lnk_file (getattr read)))
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
(allow p4_linux_production_commit_t self (unix_dgram_socket (create getattr write)))
(allow p4_linux_production_commit_t p4_linux_journal_runtime_t (dir (getattr search)))
(allow p4_linux_production_commit_t p4_linux_journal_native_socket_t (sock_file (write)))
(allow p4_linux_production_commit_t p4_linux_journald_t (unix_dgram_socket (sendto)))
(allow p4_linux_production_verify_t droidloom_container_entry_exec_t (file (getattr open read)))
(allow p4_linux_production_verify_t droidloom_broker (dir (getattr search)))
(allow p4_linux_production_verify_t droidloom_broker (file (getattr open read)))
(allow p4_linux_production_verify_t droidloom_broker (lnk_file (getattr read)))
(allow p4_linux_production_verify_t droidloom_broker (fd (use)))
(allow p4_linux_production_verify_t droidloom_broker (unix_stream_socket (getattr read write getopt shutdown)))
(allow p4_linux_production_verify_t p4_linux_unit_directory_t (dir (getattr search)))
(allow p4_linux_production_verify_t p4_linux_production_verify_unit_t (file (getattr open read)))
(allow p4_linux_production_verify_t p4_linux_production_verify_unit_t (service (status)))
(allow init_t p4_linux_production_verify_unit_t (file (getattr open read map)))
(allow p4_linux_service_executor_t p4_linux_production_verify_unit_t (file (getattr open read)))
(allow p4_linux_production_verify_t p4_linux_log_root_t (dir (getattr search)))
(allow p4_linux_production_verify_t p4_linux_volatile_log_root_t (dir (getattr search)))
(allow p4_linux_production_verify_t p4_linux_journal_store_t (dir (getattr search open read)))
(allow p4_linux_production_verify_t p4_linux_journal_machine_t (dir (getattr search open read)))
(allow p4_linux_production_verify_t p4_linux_volatile_journal_store_t (dir (getattr search open read)))
(allow p4_linux_production_verify_t p4_linux_volatile_journal_machine_t (dir (getattr search open read)))
(allow p4_linux_production_verify_t p4_linux_journal_database_t (file (getattr open read map lock)))
(allow p4_linux_production_verify_t p4_linux_volatile_journal_database_t (file (getattr open read map lock)))
(allow p4_linux_production_verify_t p4_linux_public_accounts_t (file (getattr open read)))
(allow p4_linux_production_verify_t p4_linux_machine_id_t (file (getattr open read)))
(allow p4_production_commit_actors p4_linux_production_record_dir_t (dir (getattr search open read write add_name)))
(allow p4_linux_production_commit_t p4_linux_production_record_t (file (getattr create open read write)))
(allow p4_linux_production_verify_t p4_linux_production_record_t (file (getattr open read)))
(allow p4_linux_production_verify_t p4_linux_production_activation_t (file (getattr create open read write)))
(allow p4_linux_production_config_t labeledfs (filesystem (associate)))
(allow p4_linux_production_record_dir_t labeledfs (filesystem (associate)))
(allow p4_linux_production_record_t labeledfs (filesystem (associate)))
(allow p4_linux_production_activation_t labeledfs (filesystem (associate)))
(allow p4_linux_production_verify_unit_t labeledfs (filesystem (associate)))
(typetransition p4_linux_production_commit_t p4_linux_production_record_dir_t file "PLAN.json" p4_linux_production_record_t)
(typetransition p4_linux_production_commit_t p4_linux_production_record_dir_t file "SUMMARY.json" p4_linux_production_record_t)
(typetransition p4_linux_production_commit_t p4_linux_production_record_dir_t file "MAIN.json" p4_linux_production_record_t)
(typetransition p4_linux_production_commit_t p4_linux_production_record_dir_t file "STDERR.log" p4_linux_production_record_t)
(typetransition p4_linux_production_commit_t p4_linux_production_record_dir_t file "COMMIT.json" p4_linux_production_record_t)
(typetransition p4_linux_production_commit_t p4_linux_production_record_dir_t file "TRIAL.json" p4_linux_production_record_t)
(typetransition p4_linux_production_commit_t p4_linux_production_record_dir_t file "REQUEST.json" p4_linux_production_record_t)
(typetransition p4_linux_production_verify_t p4_linux_production_record_dir_t file "ACTIVE.json" p4_linux_production_activation_t)
(allow p4_linux_production_verify_t droidloom_public_control_dir (dir (getattr search)))
(allow p4_linux_production_verify_t droidloom_public_control_socket (sock_file (getattr write)))
(allow p4_linux_production_verify_t droidloom_broker (unix_stream_socket (connectto)))
(allow droidloom_broker p4_linux_production_verify_t (unix_stream_socket (read write)))
"""

class _Index(CommonIndex):
    def expected(self, expression):
        if isinstance(expression, str) and expression in GROUPS:
            return GROUPS[expression]
        if isinstance(expression, str) and expression in self.types:
            return frozenset((expression,))
        raise ValueError("Unreviewed production expectation: " + str(expression))


def _relevant(source, target):
    return source in OWNED or target in OWNED


def _contains_owned(value):
    return any(token in OWNED for token in _atoms(value))


def _project(forms, index, *, expected=False):
    resolve = index.expected if expected else index.members
    matrix = defaultdict(set)
    transitions, contexts = set(), set()
    for f in forms:
        tag = f[0]
        if tag in FLOW_TAGS:
            if len(f) != 4 or not isinstance(f[3], list):
                raise ValueError("Unmodeled production raw rule")
            sources = resolve(f[1])
            targets = None if f[2] == "self" else resolve(f[2])
            relevant = bool(sources & OWNED or (targets is not None and targets & OWNED))
            if not relevant:
                continue
            if tag.endswith("x"):
                if len(f[3]) != 3 or f[3][0] != "ioctl" or f[3][1] not in index.classes:
                    raise ValueError("Unmodeled production ioctl")
                kind, values = f[3][1], _xvalues(f[3][2])
            else:
                if len(f[3]) != 2 or f[3][0] not in index.classes:
                    raise ValueError("Unknown production class")
                kind, names = f[3]
                if not isinstance(names, list) or not set(names) <= index.classes[kind]:
                    raise ValueError("Unknown production permission")
                values = set(names)
            for source in sources:
                for target in ({source} if targets is None else targets):
                    if _relevant(source, target):
                        matrix[(tag, source, target, kind)].update(values)
                        if len(matrix) > MAX_MATRIX_ROWS:
                            raise ValueError("Production matrix exceeds its finite bound")
        elif tag in TRANSITION_TAGS:
            if len(f) not in (5, 6):
                raise ValueError("Unmodeled production transition")
            sources, targets = resolve(f[1]), resolve(f[2])
            output = f[-1]
            if sources & OWNED or targets & OWNED or _contains_owned(output):
                if tag != "typetransition" or output not in index.types:
                    raise ValueError("Unreviewed production transition kind")
                for source in sources:
                    for target in targets:
                        if source in OWNED or target in OWNED or output in OWNED:
                            transitions.add((tag, source, target, f[3], f[4] if len(f) == 6 else "", output))
        elif tag in ("typepermissive", "typebounds") and _contains_owned(f):
            raise ValueError("Production authority is permissive or bounded")
        elif tag in CONTEXT_TAGS and _contains_owned(f):
            contexts.add(_canonical(f))
        elif tag in ("constrain", "mlsconstrain", "validatetrans", "mlsvalidatetrans"):
            if _contains_owned(f) or any("p4_production_" in t for t in _atoms(f)):
                raise ValueError("Production introduced a constraint exception")
        elif tag not in ("type", "typeattribute", "typeattributeset", "roletype",
                         "class", "common", "classcommon", "expandtypeattribute"):
            if any(t in OWNED or (t in index.definitions and index.members(t) & OWNED)
                   for t in _atoms(f)):
                raise ValueError("Unmodeled nested production authority")
    return {k: frozenset(v) for k, v in matrix.items() if v}, transitions, contexts


def _validate_membership(index):
    if not OWNED <= index.types or index.members("p4_production_commit_actors") != SUBJECTS:
        raise ValueError("Production concrete type/actor roster differs")
    if not OWNED <= index.members("p4_all_board_owned"):
        raise ValueError("Production escaped original Android board separation")
    for group in ("domain", "coredomain", "mlstrustedsubject", "mlstrustedobject", "netdomain",
                  "p4_linux_procs", "p4_linux_data", "p4_linux_native_processes",
                  "p4_linux_mac_roles", "p4_working_actors", "p4_working_children",
                  "p4_handle_owner"):
        if index.members(group) & OWNED:
            raise ValueError("Production gained an inherited role: " + group)
    if VERIFY not in index.members("droidloom_public_control_peers") or COMMIT in index.members("droidloom_public_control_peers"):
        raise ValueError("Only the fresh verifier may use the normal Main observer")
    for name in OWNED:
        if index.roles[name] != ({"object_r", "system_r"} if name in SUBJECTS else {"object_r"}):
            raise ValueError("Production role binding differs: " + name)


def _expectation(index, aliases):
    matrix, transitions, contexts = _project(_forms(FIXED_ACL), index, expected=True)
    expanded = defaultdict(set, {k: set(v) for k, v in matrix.items()})
    for row in aliases:
        for subject in SUBJECTS:
            values = matrix.get(("allow", subject, row["source"], row["class"]), ())
            expanded[("allow", subject, row["target"], row["class"])].update(values)
    return {k: frozenset(v) for k, v in expanded.items() if v}, transitions, contexts


def _compare(actual, wanted):
    for label, observed, expected in zip(("raw AV/ioctl", "transitions", "contexts"), actual, wanted):
        if observed != expected:
            changed = ([list(k) for k in sorted(set(observed) | set(expected))
                        if observed.get(k, frozenset()) != expected.get(k, frozenset())]
                       if isinstance(observed, dict) else sorted(observed ^ expected))
            raise ValueError("Production " + label + " differs: " + repr(changed[:16]))


def _contract(here):
    raw = (here / "production-commit-source.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != CONTRACT_SHA256:
        raise ValueError("Production independent source contract differs")
    value = json.loads(raw)
    if (value.get("schema") != "droidloom.production-commit-policy-source.v1"
            or value.get("runtime_qualified") is not False
            or value.get("normal_apparmor_profiles") != 182
            or value.get("normal_board_profiles") != 17
            or set(value.get("source_pins", ())) != set(FILES)
            or set(value.get("apparmor_profiles", ())) != set(PROFILES)):
        raise ValueError("Production causal source or profile roster differs")
    return value


def source_inputs(here):
    return [here / "production-commit-source.json",
            *(here / "../../../.." / name for name in FILES)]


def _file_contexts(here):
    rows = []
    for name in ("ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts",
                 "linux-service-file_contexts", "linux-initial-calibration-file_contexts",
                 "linux-production-commit-file_contexts"):
        for raw in (here / name).read_text().splitlines():
            line = raw.split("#", 1)[0].strip()
            if any(":" + label + ":" in line for label in OWNED):
                rows.append(line)
    if sorted(rows) != sorted(FILE_CONTEXTS):
        raise ValueError("Production exact file-context closure differs")


def _reciprocal(profile, text):
    wanted = RECIPROCAL_BLOCKS[profile]
    lines = wanted.splitlines()
    start, end = lines[0].strip(), lines[-1].strip()
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("Production reciprocal AppArmor block is absent or repeated")
    actual = text.split(start, 1)[1].split(end, 1)[0].strip()
    expected = "\n".join(lines[1:-1]).strip()
    if actual != expected:
        raise ValueError("Production reciprocal AppArmor closure differs: " + profile)


def verify_sources(here):
    value = _contract(here)
    checked = {}
    for name in FILES:
        raw = (here / "../../../.." / name).read_bytes()
        actual = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        if actual != value["source_pins"][name]:
            raise ValueError("Changed production causal source: " + name)
        checked[name] = actual
    _file_contexts(here)
    for name in PROFILES:
        raw = (here / "apparmor" / name).read_bytes()
        if {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()} != value["apparmor_profiles"][name]:
            raise ValueError("Production complete AppArmor profile differs: " + name)
    for name in RECIPROCAL_BLOCKS:
        _reciprocal(name, (here / "apparmor" / name).read_text())
    return checked


def verify(library, binary, exported, here):
    sources = verify_sources(here)
    forms = _forms(exported.read_text())
    index = _Index(forms)
    _validate_membership(index)
    aliases = _fixed_aliases(here)
    expected = _expectation(index, aliases)
    actual = _project(forms, index)
    _compare(actual, expected)
    policy = Policy(library, binary)
    sids, classes, checks = {}, {}, []

    def context(name, level="s0"):
        roles = index.roles[name]
        role = "r" if "r" in roles else "system_r" if "system_r" in roles else "object_r"
        return f"u:{role}:{name}:{level}"

    def sid(value):
        if value not in sids:
            number = ctypes.c_uint32()
            raw = value.encode()
            if policy.lib.sepol_context_to_sid(raw, len(raw) + 1, ctypes.byref(number)):
                raise ValueError("Invalid production linked context: " + value)
            sids[value] = number.value
        return sids[value]

    def exact(subject, target, kind, wanted):
        if kind not in classes:
            classes[kind] = policy.permissions(kind, sorted(index.classes[kind]))
        number, bits = classes[kind]
        result = Decision()
        if policy.lib.sepol_compute_av(sid(subject), sid(target), number,
                                      sum(bits.values()), ctypes.byref(result)):
            raise ValueError("Cannot query production constrained authority")
        allowed = frozenset(n for n, bit in bits.items() if result.allowed & bit)
        if allowed != frozenset(wanted):
            raise ValueError(f"Production constrained AV differs: {subject} -> {target} {kind}: {sorted(allowed)} != {sorted(wanted)}")
        checks.append([subject, target, kind, sorted(allowed)])

    for (tag, subject, target, kind), bits in sorted(expected[0].items()):
        if tag == "allow":
            exact(context(subject), context(target), kind, bits)
    for subject in SUBJECTS:
        exact(context(subject), context(subject), "capability", ("sys_ptrace",))
        for kind in ("capability2", "cap_userns", "cap2_userns"):
            exact(context(subject), context(subject), kind, ())
        exact(context(subject), context("p4_linux_maintenance_grubenv_t"), "file",
              ("getattr", "open", "read", "write", "ioctl"))
        for target in ("p4_linux_working_watchdog_t", "kmsg_device", "device"):
            exact(context(subject), context(target), "chr_file", ())
        for target in ("droidloom_apk_payload", "p4_linux_working_comparison_t"):
            exact(context(subject), context(target), "memfd_file", ())
        for kind in ("binder", "security", "dbus"):
            exact(context(subject), context("kernel"), kind, ())
        for level in ("s0", "s0:c0", "s0:c1,c2", "s0:c512,c768", "s0:c0.c1023"):
            for kind in ("file", "dir"):
                exact(context(subject), context("app_data_file", level), kind, ())
    exact(context(COMMIT), context("droidloom_public_control_socket"), "sock_file", ())
    exact(context(COMMIT), context("p4_linux_production_activation_t"), "file", ())
    exact(context(VERIFY), context("p4_linux_production_record_t"), "file", ("getattr", "open", "read"))
    rows = [[*key, sorted(value)] for key, value in sorted(actual[0].items())]
    return {"schema": "droidloom.production-commit-policy-readback.v1",
            "concrete_types": 7, "fixed_actors": 2, "named_output_transitions": 8,
            "normal_apparmor_profiles": 182, "normal_aliases": len(aliases),
            "raw_authority_rows": len(rows), "raw_authority_sha256": _hash(rows),
            "transitions": len(actual[1]), "context_bindings": len(actual[2]),
            "constrained_vectors": len(checks), "constrained_sha256": _hash(checks),
            "source_contract_sha256": CONTRACT_SHA256, "source_files": sources,
            "runtime_qualified": False}
