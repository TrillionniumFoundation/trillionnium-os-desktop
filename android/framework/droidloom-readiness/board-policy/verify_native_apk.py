"""Close the fixed helper creator, installed-APK reader and immutable copies.

The ACL and role tables are independent source expectations, never regenerated
from a candidate policy. Source/FC/AA admission is followed by full raw inbound
and outbound AV, ioctl, transition, context and constrained-vector readback.
Passing this verifier grants no Android installation or application readiness.
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

CREATOR = "droidloom_working_apk_payload_creator"
READER = "droidloom_native_leaf_apk_reader"
COPY = "droidloom_native_leaf_apk_copy"
SOURCE = "droidloom_native_helper_source"
BROKER = "droidloom_broker"
SUBJECTS = frozenset((CREATOR, READER))
OWNED = SUBJECTS | {COPY, SOURCE}
GROUPS = {"p4_native_apk_children": SUBJECTS}
ANCESTOR_PAIR = (BROKER, "p4_linux_native_leaf_source_t")
MAX_MATRIX_ROWS = 250000
CONTRACT_SHA256 = 'efb5ddc23b3ab7dd3d7583cbdb474b414344af50dd8803a211e4dd3bfd8beb53'
PROFILE = "droidloom-native-leaf-apk-reader"

# Reviewed operations of the two fixed children. This literal is deliberately
# separate from linux-native-apk.cil and the compiled candidate's projection.
FIXED_ACL = r"""
(allow droidloom_broker p4_native_apk_children (process (transition getattr sigkill)))
(allow droidloom_broker p4_native_apk_children (process2 (nnp_transition nosuid_transition)))
(allow p4_native_apk_children droidloom_container_entry_exec_t (file (getattr open read map execute entrypoint)))
(allow p4_native_apk_children p4_linux_elf_interpreter_t (file (getattr open read map execute)))
(allow p4_native_apk_children p4_linux_runtime_lib_t (file (getattr open read map execute)))
(allow p4_native_apk_children p4_linux_console_ld_cache_native_config_t (file (getattr open read map)))
(allow p4_native_apk_children p4_linux_rootdir_t (dir (getattr search)))
(allow p4_native_apk_children p4_linux_etc_dir_t (dir (getattr search)))
(allow p4_native_apk_children p4_linux_usrmerge_link_t (lnk_file (getattr read)))
(allow p4_native_apk_children self (process (getcap)))
(allow p4_native_apk_children droidloom_broker (process (getattr sigchld)))
(allow p4_native_apk_children droidloom_broker (fd (use)))
(allow droidloom_broker p4_native_apk_children (fd (use)))
(allow p4_native_apk_children droidloom_broker (fifo_file (getattr read)))
(allow p4_native_apk_children droidloom_broker (unix_stream_socket (getattr getopt read write)))
(allow p4_native_apk_children proc (dir (getattr search)))
(allow p4_native_apk_children proc (lnk_file (getattr read)))
(allow p4_native_apk_children proc (filesystem (getattr)))
(allow p4_native_apk_children self (dir (getattr search)))
(allow p4_native_apk_children self (file (getattr open read)))
(allow p4_native_apk_children self (lnk_file (getattr read)))
(allow p4_native_apk_children p4_kernel_pid_handle_t (file (getattr)))
(allow p4_native_apk_children tmpfs (filesystem (getattr)))
(allow droidloom_native_helper_source labeledfs (filesystem (associate)))
(allow droidloom_broker droidloom_native_helper_source (dir (getattr search open read)))
(allow droidloom_broker droidloom_native_helper_source (file (getattr open read)))
(allow droidloom_broker p4_linux_native_leaf_source_t (dir (getattr search)))
(allow droidloom_working_apk_payload_creator droidloom_native_helper_source (file (getattr read)))
(allow p4_linux_working_privateprep_t droidloom_native_helper_source (dir (getattr search open read)))
(allow p4_linux_working_privateprep_t droidloom_native_helper_source (file (getattr open read)))
(allow p4_linux_working_application_t droidloom_native_helper_source (dir (getattr search open read)))
(allow p4_linux_working_application_t droidloom_native_helper_source (file (getattr open read)))
(typetransition droidloom_working_apk_payload_creator tmpfs file droidloom_apk_payload)
(typetransition droidloom_working_apk_payload_creator tmpfs memfd_file droidloom_apk_payload)
(allow droidloom_working_apk_payload_creator droidloom_apk_payload (file (getattr open read write)))
(allow droidloom_working_apk_payload_creator droidloom_apk_payload (memfd_file (getattr open read write)))
(allow droidloom_native_leaf_apk_reader kernel (fd (use)))
(allow droidloom_native_leaf_apk_reader droidloom_metadata_observer (fd (use)))
(allow droidloom_native_leaf_apk_reader rootfs (dir (getattr read search)))
(allow droidloom_native_leaf_apk_reader system_file (dir (getattr search)))
(allow droidloom_native_leaf_apk_reader system_data_root_file (dir (getattr search)))
(allow droidloom_native_leaf_apk_reader system_data_file (dir (getattr search)))
(allow droidloom_native_leaf_apk_reader apk_data_file (dir (getattr search)))
(allow droidloom_native_leaf_apk_reader apex_mnt_dir (dir (getattr search)))
(allow droidloom_native_leaf_apk_reader rootfs (lnk_file (getattr read)))
(allow droidloom_native_leaf_apk_reader system_file (lnk_file (getattr read)))
(allow droidloom_native_leaf_apk_reader apex_mnt_dir (lnk_file (getattr read)))
(allow droidloom_native_leaf_apk_reader system_file (file (getattr open read)))
(allow droidloom_native_leaf_apk_reader apk_data_file (file (getattr open read)))
(allow droidloom_native_leaf_apk_copy tmpfs (filesystem (associate)))
(typetransition droidloom_native_leaf_apk_reader tmpfs file droidloom_native_leaf_apk_copy)
(typetransition droidloom_native_leaf_apk_reader tmpfs memfd_file droidloom_native_leaf_apk_copy)
(allow droidloom_native_leaf_apk_reader droidloom_native_leaf_apk_copy (file (getattr open read write setattr)))
(allow droidloom_native_leaf_apk_reader droidloom_native_leaf_apk_copy (memfd_file (getattr open read write setattr)))
(allow droidloom_broker droidloom_native_leaf_apk_copy (file (getattr read)))
(allow droidloom_broker droidloom_native_leaf_apk_copy (memfd_file (getattr read)))
(allow p4_linux_working_privateprep_t droidloom_native_leaf_apk_reader (fd (use)))
(allow p4_linux_working_application_t droidloom_native_leaf_apk_reader (fd (use)))
(allow p4_linux_working_privateprep_t droidloom_native_leaf_apk_copy (file (getattr read)))
(allow p4_linux_working_privateprep_t droidloom_native_leaf_apk_copy (memfd_file (getattr read)))
(allow p4_linux_working_application_t droidloom_native_leaf_apk_copy (file (getattr read)))
(allow p4_linux_working_application_t droidloom_native_leaf_apk_copy (memfd_file (getattr read)))
"""


class _Index(CommonIndex):
    def expected(self, expression):
        if isinstance(expression, str) and expression in GROUPS:
            return GROUPS[expression]
        if isinstance(expression, str) and expression in self.types:
            return frozenset((expression,))
        raise ValueError("Unreviewed native APK expectation: " + str(expression))


def _relevant(source, target):
    return source in OWNED or target in OWNED or (source, target) == ANCESTOR_PAIR


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
                raise ValueError("Unmodeled native APK raw rule")
            sources = resolve(f[1])
            targets = None if f[2] == "self" else resolve(f[2])
            relevant = bool(sources & OWNED or (targets is not None and targets & OWNED))
            relevant |= BROKER in sources and targets is not None and ANCESTOR_PAIR[1] in targets
            if not relevant:
                continue
            if tag.endswith("x"):
                if len(f[3]) != 3 or f[3][0] != "ioctl" or f[3][1] not in index.classes:
                    raise ValueError("Unmodeled native APK ioctl")
                kind, values = f[3][1], _xvalues(f[3][2])
            else:
                if len(f[3]) != 2 or f[3][0] not in index.classes:
                    raise ValueError("Unknown native APK class")
                kind, names = f[3]
                if not isinstance(names, list) or not set(names) <= index.classes[kind]:
                    raise ValueError("Unknown native APK permission")
                values = set(names)
            for source in sources:
                for target in ({source} if targets is None else targets):
                    if _relevant(source, target):
                        matrix[(tag, source, target, kind)].update(values)
                        if len(matrix) > MAX_MATRIX_ROWS:
                            raise ValueError("Native APK matrix exceeds its finite bound")
        elif tag in TRANSITION_TAGS:
            if len(f) not in (5, 6):
                raise ValueError("Unmodeled native APK transition")
            sources, targets = resolve(f[1]), resolve(f[2])
            output = f[-1]
            if sources & OWNED or targets & OWNED or _contains_owned(output):
                if tag != "typetransition" or output not in index.types:
                    raise ValueError("Unreviewed native APK transition kind")
                for source in sources:
                    for target in targets:
                        if source in OWNED or target in OWNED or output in OWNED:
                            transitions.add((tag, source, target, f[3], f[4] if len(f) == 6 else "", output))
        elif tag in ("typepermissive", "typebounds") and _contains_owned(f):
            raise ValueError("Native APK authority is permissive or bounded")
        elif tag in CONTEXT_TAGS and _contains_owned(f):
            contexts.add(_canonical(f))
        elif tag in ("constrain", "mlsconstrain", "validatetrans", "mlsvalidatetrans"):
            if _contains_owned(f) or any("p4_native_apk_" in t for t in _atoms(f)):
                raise ValueError("Native APK introduced a constraint exception")
        elif tag not in ("type", "typeattribute", "typeattributeset", "roletype",
                         "class", "common", "classcommon", "expandtypeattribute"):
            if any(t in OWNED or (t in index.definitions and index.members(t) & OWNED)
                   for t in _atoms(f)):
                raise ValueError("Unmodeled nested native APK authority")
    return {k: frozenset(v) for k, v in matrix.items() if v}, transitions, contexts


def _validate_membership(index):
    if not OWNED <= index.types or index.members("p4_native_apk_children") != SUBJECTS:
        raise ValueError("Native APK concrete type/child roster differs")
    if not OWNED <= index.members("p4_all_board_owned"):
        raise ValueError("Native APK escaped original Android board separation")
    for group in ("domain", "coredomain", "mlstrustedsubject", "mlstrustedobject", "netdomain",
                  "p4_linux_procs", "p4_linux_data", "p4_linux_native_processes", "p4_linux_mac_roles"):
        if index.members(group) & OWNED:
            raise ValueError("Native APK gained an inherited role: " + group)
    for name in OWNED:
        if index.roles[name] != ({"object_r", "r"} if name in SUBJECTS else {"object_r"}):
            raise ValueError("Native APK role binding differs: " + name)


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
            raise ValueError("Native APK " + label + " differs: " + repr(changed[:16]))


def _contract(here):
    raw = (here / "native-apk-source.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != CONTRACT_SHA256:
        raise ValueError("Native APK independent source contract differs")
    value = json.loads(raw)
    files = value["helper_source_files"]
    directories = value["helper_source_directories"]
    paths = [row["path"] for row in files]
    if (value["schema"] != "droidloom.native-apk-policy-source.v1" or value["runtime_qualified"] is not False
            or len(files) != 40 or len(set(paths)) != 40 or len(directories) != 30
            or len(set(directories)) != 30):
        raise ValueError("Native APK source roster differs")
    for row in files:
        path = PurePosixPath(row["path"])
        if (not path.is_absolute() or ".." in path.parts or str(path) != row["path"]
                or row["bytes"] <= 0 or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])):
            raise ValueError("Invalid fixed native helper source")
    if value.get("helper_source_ancestors") != [
            "/usr/libexec/droidloom/native-application-leaves/prebuilt-state-fixtures",
            "/usr/libexec/droidloom/native-application-leaves/prebuilt-state-fixtures/20261128-r1"]:
        raise ValueError("Fixed metadata-only helper ancestor roster differs")
    return value


def source_inputs(here):
    value = json.loads((here / "native-apk-source.json").read_text())
    return [here / "native-apk-source.json", *(here / "../../../.." / n for n in value["source_pins"]),
            *(here / "apparmor" / name for name in (PROFILE, "droidloom-production-broker", "droidloom-working-privateprep", "droidloom-working-application"))]


def _file_contexts(here, value):
    rows = []
    for name in ("ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts", "linux-service-file_contexts"):
        for raw in (here / name).read_text().splitlines():
            line = raw.split("#", 1)[0].strip()
            if any(":" + label + ":" in line for label in OWNED):
                rows.append(line)
    expected = [re.escape(p) + " -d u:object_r:" + SOURCE + ":s0"
                for p in value["helper_source_directories"]]
    expected += [re.escape(row["path"]) + " -- u:object_r:" + SOURCE + ":s0"
                 for row in value["helper_source_files"]]
    if sorted(rows) != sorted(expected):
        raise ValueError("Native helper source exact path/type closure differs")
    real_root = (here / "ubuntu-real-root-file_contexts").read_text().splitlines()
    for path in value["helper_source_ancestors"]:
        expected = re.escape(path) + " -d u:object_r:p4_linux_native_leaf_source_t:s0"
        if real_root.count(expected) != 1:
            raise ValueError("Native helper metadata ancestor label differs")


def _helper_apparmor(profile, text, value):
    start = "# BEGIN fixed native helper sources (closed by verify_native_apk.py)"
    end = "# END fixed native helper sources"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("Native helper AppArmor block is absent or repeated")
    actual = [line.strip() for line in text.split(start, 1)[1].split(end, 1)[0].splitlines() if line.strip()]
    if profile not in ("droidloom-production-broker", "droidloom-working-privateprep", "droidloom-working-application"):
        raise ValueError("Unreviewed native helper source reader")
    paths = [row["path"] for row in value["helper_source_files"]]
    directories = set()
    for path in paths:
        for parent in PurePosixPath(path).parents:
            if str(parent).startswith("/usr/libexec"):
                directories.add(str(parent) + "/")
    expected = sorted(p + " r," for p in [*directories, *paths])
    if sorted(actual) != expected:
        raise ValueError("Native helper AppArmor exact source closure differs: " + profile)


def verify_sources(here):
    value = _contract(here)
    checked = {}
    for name, expected in value["source_pins"].items():
        raw = (here / "../../../.." / name).read_bytes()
        actual = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        if actual != expected:
            raise ValueError("Changed native APK causal source: " + name)
        checked[name] = actual
    _file_contexts(here, value)
    for name in ("droidloom-production-broker", "droidloom-working-privateprep", "droidloom-working-application"):
        _helper_apparmor(name, (here / "apparmor" / name).read_text(), value)
    # The Reader's complete independent profile is pinned, not an inferred
    # subset of whichever permissions happen to appear in a current candidate.
    reader = (here / "apparmor" / PROFILE).read_bytes()
    if {"bytes": len(reader), "sha256": hashlib.sha256(reader).hexdigest()} != value["reader_apparmor"]:
        raise ValueError("Native APK reader AppArmor closure changed")
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
                raise ValueError("Invalid native APK linked context: " + value)
            sids[value] = number.value
        return sids[value]

    def exact(subject, target, kind, wanted):
        if kind not in classes:
            classes[kind] = policy.permissions(kind, sorted(index.classes[kind]))
        number, bits = classes[kind]
        result = Decision()
        if policy.lib.sepol_compute_av(sid(subject), sid(target), number,
                                      sum(bits.values()), ctypes.byref(result)):
            raise ValueError("Cannot query native APK constrained authority")
        allowed = frozenset(n for n, bit in bits.items() if result.allowed & bit)
        if allowed != frozenset(wanted):
            raise ValueError(f"Native APK constrained AV differs: {subject} -> {target} {kind}: {sorted(allowed)} != {sorted(wanted)}")
        checks.append([subject, target, kind, sorted(allowed)])

    for (tag, subject, target, kind), bits in sorted(expected[0].items()):
        if tag == "allow":
            exact(context(subject), context(target), kind, bits)
    for subject in SUBJECTS:
        for kind in ("capability", "capability2", "cap_userns", "cap2_userns"):
            exact(context(subject), context(subject), kind, ())
        for kind in ("binder", "security", "dbus"):
            exact(context(subject), context("kernel"), kind, ())
        for level in ("s0", "s0:c0", "s0:c1,c2", "s0:c512,c768", "s0:c0.c1023"):
            for kind in ("file", "dir"):
                exact(context(subject), context("app_data_file", level), kind, ())
    rows = [[*key, sorted(value)] for key, value in sorted(actual[0].items())]
    return {"schema": "droidloom.native-apk-policy-readback.v1",
            "concrete_types": 4, "fixed_children": 2, "helper_source_files": 40,
            "helper_source_directories": 30, "normal_aliases": len(aliases),
            "raw_authority_rows": len(rows), "raw_authority_sha256": _hash(rows),
            "transitions": len(actual[1]), "context_bindings": len(actual[2]),
            "constrained_vectors": len(checks), "constrained_sha256": _hash(checks),
            "source_contract_sha256": CONTRACT_SHA256, "source_files": sources,
            "runtime_qualified": False}
