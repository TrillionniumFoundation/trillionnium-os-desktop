"""Exact linked AV, transitions and bounded paths for stock GDM greeter data."""
import ctypes
import hashlib
import json
import re
from derive_shared_payload_cgroup_policy import Decision, Policy, parse_expression

PREFIX = "p4_linux_greeter_"
ANCHOR, HOME, ENVIRONMENT, SEAT, DATA = [PREFIX + n + "_t" for n in
    ("home_parent", "home", "environment", "seat_parent", "seat_data")]
OBJECTS = (ANCHOR, HOME, ENVIRONMENT, SEAT, DATA)
WRITERS = {"p4_linux_" + n + "_t" for n in
           ("user_session", "compositor", "audio", "desktop_portal")}
READERS = WRITERS | {"p4_linux_" + n + "_t" for n in
                     ("user_manager", "user_executor", "user_dbus")}
GDM, WORKER = "p4_linux_gdm_t", "p4_linux_gdm_worker_t"
GS = {"getattr", "search"}
GOR = {"getattr", "open", "read"}
DIR_WRITER = GS | {"open", "read", "create", "write", "add_name", "remove_name", "setattr", "rename", "reparent", "rmdir"}
FILE_WRITER = GOR | {"write", "append", "create", "setattr", "lock", "map", "link", "rename", "unlink"}
LINK_WRITER = {"getattr", "read", "create", "write", "setattr", "link", "rename", "unlink"}
GDM_DIR = DIR_WRITER - {"rename", "reparent"}
GDM_FILE = GOR | {"write", "append", "create", "setattr", "rename", "unlink"}
NAMES = ["gdm-greeter", *(f"gdm-greeter-{i}" for i in range(2, 129))]


def expected(actor, target, kind):
    # Existing source-owned metadata observer can only traverse board data.
    # It receives no new body access and its fixed process selectors exclude GDM.
    if actor in {"droidloom_metadata_observer", "droidloom_query_io"} and kind == "dir":
        return GS
    if actor == GDM:
        if kind == "dir":
            return GDM_DIR | ({"rename"} if target == DATA else set())
        if target in (HOME, DATA):
            return {"file": GDM_FILE, "lnk_file": {"getattr", "read", "setattr", "unlink"} | ({"create", "write"} if target == DATA else set()),
                    "sock_file": {"getattr", "setattr", "unlink"},
                    "fifo_file": {"getattr", "setattr", "unlink"}}.get(kind, set())
        if target == ENVIRONMENT:
            return {"file": GDM_FILE - {"append"}, "lnk_file": {"getattr", "unlink"}}.get(kind, set())
    if actor == WORKER and kind == "dir" and target != ENVIRONMENT:
        return GS
    if actor in READERS:
        if target in (ANCHOR, SEAT):
            return GS if kind == "dir" else set()
        if target == ENVIRONMENT:
            return {"dir": GS | {"open", "read"}, "file": GOR}.get(kind, set())
        if actor in WRITERS:
            return {"dir": DIR_WRITER, "file": FILE_WRITER, "lnk_file": LINK_WRITER,
                    "sock_file": {"getattr", "create", "setattr", "write", "unlink"},
                    "fifo_file": GOR | {"create", "write", "append", "setattr", "lock", "unlink"}}.get(kind, set())
        return {"dir": GS | {"open", "read"}, "file": GOR | {"map", "lock"},
                "lnk_file": {"getattr", "read"}}.get(kind, set())
    return set()


def verify_greeter_home(library, binary, exported, original, file_contexts):
    policy = Policy(library, binary)
    lines = exported.read_text().splitlines()
    roles = {tuple(parse_expression(l.strip())[1:]) for l in lines
             if l.strip().startswith("(roletype ")}
    subjects = sorted((role, actor) for role, actor in roles if role in ("r", "system_r"))
    if not set(original["subjects"]).issubset({name for role, name in subjects if role == "r"}):
        raise ValueError("Greeter gate lost original Android subjects")
    sids = {}
    def sid(role, name):
        key = role, name
        if key not in sids:
            raw = f"u:{role}:{name}:s0".encode(); value = ctypes.c_uint32()
            if policy.lib.sepol_context_to_sid(raw, len(raw) + 1, ctypes.byref(value)):
                raise ValueError("Invalid linked greeter context: " + raw.decode())
            sids[key] = value.value
        return sids[key]
    classes = dict(original["classes"])
    classes.update({k: ["getattr", "create", "open", "read", "write", "append", "setattr", "lock", "unlink", "link", "rename", "relabelfrom", "relabelto", "map"]
                    for k in ("fifo_file", "sock_file")})
    declarations = {k: policy.permissions(k, perms) for k, perms in classes.items()}
    decisions, mismatches = [], []
    for role, actor in subjects:
        for target in OBJECTS:
            for kind, (number, bits) in declarations.items():
                mask = sum(bits.values()); av = Decision()
                if policy.lib.sepol_compute_av(sid(role, actor), sid("object_r", target),
                                              number, mask, ctypes.byref(av)):
                    raise ValueError("Cannot read final greeter AV")
                actual = {p for p, bit in bits.items() if av.allowed & bit}
                wanted = expected(actor, target, kind)
                if actual != wanted:
                    mismatches.append([role, actor, target, kind, sorted(actual), sorted(wanted)])
                decisions.append([role, actor, target, kind, sorted(actual)])
    if mismatches:
        raise ValueError("Greeter boundary mismatches: " + json.dumps(mismatches[:100]) + f" (total {len(mismatches)})")
    neighbor_decisions = 0
    for actor in sorted(READERS | {WORKER}):
        for target in ("p4_linux_gdm_run_t", "p4_linux_gdm_state_t"):
            for kind, permissions in original["classes"].items():
                number, bits = policy.permissions(kind, permissions)
                av = Decision()
                if policy.lib.sepol_compute_av(sid("system_r", actor), sid("object_r", target),
                                              number, sum(bits.values()), ctypes.byref(av)):
                    raise ValueError("Cannot read neighboring GDM runtime AV")
                actual = {p for p, bit in bits.items() if av.allowed & bit}
                if actual != (GS if kind == "dir" else set()):
                    raise ValueError("Greeter reader gained general GDM runtime/state access")
                neighbor_decisions += len(bits)
    transitions = [parse_expression(l.strip()) for l in lines
                   if l.strip().startswith("(typetransition ")]
    actual_names = set()
    for form in transitions:
        if len(form) == 6 and form[1:4] == [GDM, ANCHOR, "dir"]:
            if form[5] != HOME:
                raise ValueError("Dynamic greeter name has an unexpected target")
            actual_names.add(form[4].strip('"'))
    if actual_names != set(NAMES):
        raise ValueError("Linked dynamic-home named transitions are not the exact 128 names")
    mandatory = [
        ["typetransition", GDM, "p4_linux_gdm_run_t", "dir", '"home"', ANCHOR],
        ["typetransition", GDM, "p4_linux_gdm_state_t", "dir", '"seat0"', SEAT],
        ["typetransition", GDM, HOME, "dir", '"environment.d"', ENVIRONMENT],
        *[["typetransition", GDM, SEAT, "dir", '"' + name + '"', DATA] for name in ("config", "state", ".config-handoff", ".state-handoff")],
    ]
    if any(form not in transitions for form in mandatory):
        raise ValueError("Linked greeter fixed-parent transition is missing")
    fc = []
    for line in file_contexts.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split()
        if len(fields) == 2 and any(t in fields[1] for t in OBJECTS):
            fc.append((fields[0], fields[1].split(":")[2]))
    if len(fc) != 5 or {target for _, target in fc} != set(OBJECTS):
        raise ValueError("Normal native file_contexts must contain the five exact greeter entries")
    entries = {target: re.compile(pattern) for pattern, target in fc}
    for name in NAMES:
        path = "/run/gdm3/home/" + name
        if not entries[HOME].fullmatch(path) or not entries[ENVIRONMENT].fullmatch(path + "/.config/environment.d/gdm.conf"):
            raise ValueError("Normal file_contexts lost a source-owned dynamic name")
    for name in ("config", "state", ".config-handoff", ".state-handoff"):
        if not entries[DATA].fullmatch("/var/lib/gdm3/seat0/" + name + "/retained-setting"):
            raise ValueError("Normal file_contexts lost an exact persistent publication name")
    for name in (".other-handoff", ".config-handoff-extra", ".state-handoff-extra", "other", "config-extra"):
        if entries[DATA].fullmatch("/var/lib/gdm3/seat0/" + name + "/setting"):
            raise ValueError("Persistent publication file_contexts widened beyond fixed names")
    for name in ("alex", "root", "gdm-greeter-1", "gdm-greeter-01", "gdm-greeter-129", "gdm-greeter-999", "gdm-greeter-2x"):
        if entries[HOME].fullmatch("/run/gdm3/home/" + name):
            raise ValueError("Greeter file_contexts accepts a non-source-owned account")
    return {"subjects": len(subjects), "original_android_subjects": len(original["subjects"]),
            "objects": list(OBJECTS), "av_permission_decisions": len(subjects) * len(OBJECTS) * sum(map(len, classes.values())),
            "neighbor_gdm_runtime_permission_decisions": neighbor_decisions,
            "exact_named_home_transitions": len(actual_names), "fixed_parent_transitions": len(mandatory),
            "file_contexts_sha256": hashlib.sha256(file_contexts.read_bytes()).hexdigest(),
            "matrix_sha256": hashlib.sha256(json.dumps(decisions, separators=(",", ":")).encode()).hexdigest(),
            "capabilities_added": [], "runtime_greeter_qualified": False}
