"""Derive shared uevent labels without changing Android's effective access.

This is an extension of the normal strict policy linker, not a runtime policy
loader. Its only map is the source file compiled into the held-inode Rust
labeler. Original CIL, assertions, genfs rules and policy capabilities remain
inputs to every link. The aliases are shared sysfs objects, never Linux data.
"""
import ctypes
import hashlib
import json
import re
from collections import defaultdict

from derive_shared_payload_cgroup_policy import (
    Decision, Policy, format_xperms, original_declarations, original_xperms,
    parse_expression,
)


ROLE = "p4_linux_uevent_label_t"
EXEC = "p4_linux_uevent_label_exec_t"
LEVELS = ("s0", "s0:c0", "s0:c1,c512", "s0:c0.c1023")
CLASSES = ("file", "dir", "lnk_file")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ContextPolicy(Policy):
    def context_sid(self, context):
        if context not in self.sids:
            value = ctypes.c_uint32()
            raw = context.encode()
            if self.lib.sepol_context_to_sid(raw, len(raw) + 1, ctypes.byref(value)):
                raise ValueError("Invalid uevent comparison context: " + context)
            self.sids[context] = value.value
        return self.sids[context]

    def context_av(self, source, target, cls, names):
        number, permissions = self.permissions(cls, names)
        mask = sum(permissions.values())
        result = Decision()
        if self.lib.sepol_compute_av(self.context_sid(source), self.context_sid(target),
                                     number, mask, ctypes.byref(result)):
            raise ValueError("Cannot compute the shared uevent AV decision")
        return result.allowed & mask


class Membership:
    """Resolve concrete membership, including negative generated attributes."""
    def __init__(self, text):
        self.types = set(re.findall(r"\(type ([A-Za-z0-9_]+)\)", text))
        self.attributes = set(re.findall(r"\(typeattribute ([A-Za-z0-9_]+)\)", text))
        self.definitions = defaultdict(list)
        self.cache = {}
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith("(typeattributeset "):
                form = parse_expression(line)
                if len(form) != 3:
                    raise ValueError("Unsupported type membership in uevent inputs")
                self.definitions[form[1]].append(form[2])
        # Binary exports encode many attributes as flat concrete type lists.
        # Index only those exact unions; Boolean/nested/unknown expressions keep
        # the original evaluator and its short-circuit and error behavior.
        operators = {"all", "not", "and", "or", "xor"}
        self.concrete = {}
        for name, expressions in self.definitions.items():
            if all(isinstance(expr, list)
                   and all(isinstance(atom, str) and atom in self.types for atom in expr)
                   and (not expr or expr[0] not in operators)
                   for expr in expressions):
                self.concrete[name] = frozenset(
                    atom for expr in expressions for atom in expr)

    def member(self, name, selected, active=()):
        if isinstance(name, list):
            return self.evaluate(name, selected, active)
        if name in self.types:
            return name == selected
        if name == "self":
            return False
        key = (name, selected)
        if key in self.cache:
            return self.cache[key]
        if name in active or name not in self.attributes:
            raise ValueError("Unresolved/cyclic uevent type membership: " + name)
        if name in self.concrete:
            value = selected in self.concrete[name]
        else:
            value = any(self.evaluate(x, selected, (*active, name))
                        for x in self.definitions[name])
        self.cache[key] = value
        return value

    def evaluate(self, expression, selected, active=()):
        if isinstance(expression, str):
            return self.member(expression, selected, active)
        if not expression:
            return False
        operation, *args = expression
        if operation == "all":
            if args:
                raise ValueError("Invalid all membership")
            return True
        if operation == "not":
            if len(args) != 1:
                raise ValueError("Invalid not membership")
            return not self.evaluate(args[0], selected, active)
        if operation in ("and", "or"):
            values = [self.evaluate(x, selected, active) for x in args]
            return all(values) if operation == "and" else any(values)
        if operation == "xor":
            if len(args) != 2:
                raise ValueError("Invalid xor membership")
            return self.evaluate(args[0], selected, active) != self.evaluate(args[1], selected, active)
        return any(self.evaluate(x, selected, active) for x in expression)


def mapping(path):
    raw = json.loads(path.read_text())
    if set(raw) != {"schema", "labels"} or raw["schema"] != "droidloom.native-uevent-label-map.v1":
        raise ValueError("Unknown native uevent map schema")
    rows = raw["labels"]
    if len(rows) != 6:
        raise ValueError("The native uevent map is not the reviewed six-source map")
    seen = set()
    for row in rows:
        if (set(row) != {"source", "target"} or
                not re.fullmatch(r"sysfs[a-z_]*", row["source"]) or
                row["target"] != "p4_native_uevent_" + row["source"] or
                row["source"] in seen):
            raise ValueError("Invalid or repeated native uevent pair")
        seen.add(row["source"])
    return rows


def join_expression(operator, expressions):
    if not expressions:
        raise ValueError("Empty uevent constraint")
    # Constraint bytecode is a bounded postfix stack (CEXPR_MAXDEPTH=5).
    # Left-fold a closed map instead of retaining twelve pending right arms.
    result = expressions[0]
    for expression in expressions[1:]:
        result = "(" + operator + " " + result + " " + expression + ")"
    return result


def constraint_stack_depth(expression):
    if not isinstance(expression, list) or not expression:
        raise ValueError("Invalid generated constraint expression")
    if expression[0] in ("eq", "neq") and len(expression) == 3:
        return 1
    if expression[0] in ("and", "or") and len(expression) == 3:
        return max(constraint_stack_depth(expression[1]),
                   1 + constraint_stack_depth(expression[2]))
    raise ValueError("Unexpected generated constraint operator")


def constraint_atoms(text, members, rows):
    """All target-type tests in the untouched original constraints must agree.

    The subject's role/type/user/range and the target's object role/user/s0
    range do not change. Therefore equality of these target-type atoms proves
    the constraints agree for every source MLS range, not only sampled MCS.
    """
    atoms = set()
    constraints = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith(("(constrain ", "(mlsconstrain ")):
            continue
        form = parse_expression(line)
        if len(form) != 3 or len(form[1]) != 2:
            raise ValueError("Unsupported original constraint declaration")
        if form[1][0] not in CLASSES:
            continue
        constraints.append(line)
        def visit(expression):
            if not isinstance(expression, list):
                return
            if len(expression) == 3 and expression[0] in ("eq", "neq") and "t2" in expression[1:]:
                other = expression[2] if expression[1] == "t2" else expression[1]
                if not isinstance(other, str) or other in ("t1", "t3", "t2"):
                    raise ValueError("Original constraint compares target type identity directly")
                atoms.add(other)
            for child in expression[1:]:
                visit(child)
        visit(form[2])
    values = {}
    lines = []
    for row in rows:
        values[row["source"]] = {}
        for atom in sorted(atoms):
            value = members.member(atom, row["source"])
            values[row["source"]][atom] = value
            if value:
                if atom not in members.attributes:
                    raise ValueError("A new uevent type cannot retain literal constraint identity")
                lines.append("(typeattributeset " + atom + " (" + row["target"] + "))")
    return lines, {"target_type_atoms": values, "original_constraints": sorted(constraints)}


def emit_groups(lines, prefix, target, cls, names, permission_bits, decisions):
    groups = defaultdict(list)
    for subject, allowed in decisions.items():
        groups[allowed].append(subject)
    for index, (allowed, subjects) in enumerate(sorted(groups.items())):
        attribute = prefix + "_" + str(index)
        lines += ["(typeattribute " + attribute + ")",
                  "(typeattributeset " + attribute + " (" + " ".join(sorted(subjects)) + "))"]
        for operation, choose in (("allow", True), ("neverallow", False)):
            selected = [n for n in names if bool(permission_bits[n] & allowed) == choose]
            if selected:
                lines.append("(" + operation + " " + attribute + " " + target +
                             " (" + cls + " (" + " ".join(selected) + ")))")


def derive_android(library, original, inputs, map_path, output):
    rows = mapping(map_path)
    subjects, classes = original_declarations(inputs)
    subjects = sorted([*subjects, "kernel"])
    original_text = "\n".join(p.read_text() for p in inputs)
    members = Membership(original_text)
    if any(row["source"] not in members.types or
           not members.member("sysfs_type", row["source"]) for row in rows):
        raise ValueError("A selected uevent source is not an original concrete sysfs type")
    policy = ContextPolicy(library, original)
    lines = ["; Generated from the reproduced original policy and the compiled Rust map.",
             "; These regular sysfs inodes remain shared with the original Android roles.",
             "(typeattribute p4_native_uevent_sources)",
             "(typeattribute p4_native_uevent_objects)"]
    for row in rows:
        target = row["target"]
        lines += ["(type " + target + ")", "(roletype object_r " + target + ")"]
    lines += ["(typeattributeset p4_native_uevent_sources (" + " ".join(r["source"] for r in rows) + "))",
              "(typeattributeset p4_native_uevent_objects (" + " ".join(r["target"] for r in rows) + "))",
              "(typeattributeset p4_all_board_owned (p4_native_uevent_objects))",
              "(allow p4_native_uevent_objects sysfs (filesystem (associate)))"]
    mls_lines, constraints = constraint_atoms(original_text, members, rows)
    lines += mls_lines
    pairs = []
    for row in rows:
        target = row["target"]
        pairs += ["(and (eq t1 " + row["source"] + ") (eq t2 " + target + "))",
                  "(and (eq t1 " + target + ") (eq t2 " + target + "))"]
    transition = "(validatetrans file (or (neq t3 " + ROLE + ") " + join_expression("or", pairs) + "))"
    if constraint_stack_depth(parse_expression(transition)[2]) > 5:
        raise ValueError("Generated uevent constraint exceeds the kernel postfix stack")
    lines.append(transition)
    decisions = {}
    samples = {}
    xperm_decisions = {}
    for index, row in enumerate(rows):
        source, target = row["source"], row["target"]
        decisions[source], samples[source], xperm_decisions[source] = {}, {}, {}
        xperms = original_xperms(inputs, subjects, source)
        for cls, names in classes.items():
            _, bits = policy.permissions(cls, names)
            choices = {}
            samples[source][cls] = {}
            for subject in subjects:
                values = []
                for level in LEVELS:
                    values.append(policy.context_av("u:r:" + subject + ":" + level,
                                                    "u:object_r:" + source + ":s0", cls, names))
                choices[subject] = values[0]
                samples[source][cls][subject] = values
            decisions[source][cls] = choices
            prefix = "p4_uevent_android_" + str(index) + "_" + cls
            emit_groups(lines, prefix, target, cls, names, bits, choices)
            ioctl_groups = defaultdict(list)
            xperm_decisions[source][cls] = {}
            for subject in subjects:
                if choices[subject] & bits["ioctl"]:
                    allowed = xperms[cls][subject]
                    ioctl_groups[allowed].append(subject)
                    xperm_decisions[source][cls][subject] = allowed
            for group, (allowed, actors) in enumerate(sorted(ioctl_groups.items())):
                attribute = prefix + "_ioctl_" + str(group)
                values = format_xperms(allowed)
                lines += ["(typeattribute " + attribute + ")",
                          "(typeattributeset " + attribute + " (" + " ".join(actors) + "))",
                          "(allowx " + attribute + " " + target + " (ioctl " + cls + " " + values + "))",
                          "(neverallowx " + attribute + " " + target + " (ioctl " + cls + " (not " + values + ")))"]
    output.write_text("\n".join(lines) + "\n")
    return {"rows": rows, "subjects": subjects, "classes": classes,
            "decisions": decisions, "samples": samples, "xperms": xperm_decisions,
            "constraints": constraints, "map_sha256": digest(map_path),
            "android_derived_sha256": digest(output)}


def derive_native(library, baseline, baseline_cil, contract, output, export):
    policy = ContextPolicy(library, baseline)
    lines = export(policy, baseline, baseline_cil)
    roles = sorted(line[len("(roletype system_r "):-1] for line in lines
                   if line.startswith("(roletype system_r "))
    if ROLE not in roles or "p4_linux_udev_t" not in roles:
        raise ValueError("Native uevent helper/udev roles are absent")
    names = contract["classes"]["file"]
    _, bits = policy.permissions("file", names)
    readonly = sum(bits[p] for p in ("getattr", "open", "read"))
    body = sum(bits[p] for p in ("open", "read"))
    generated = ["; Preserve each current native source's exact read-only uevent access.",
                 "; Mutation belongs only to the sealed labeler and original native udev."]
    native = {}
    for index, row in enumerate(contract["rows"]):
        source, target = row["source"], row["target"]
        choices = {}
        native[source] = {}
        for actor in roles:
            actual = policy.context_av("u:system_r:" + actor + ":s0",
                                       "u:object_r:" + source + ":s0", "file", names)
            permitted = readonly | (bits["relabelfrom"] if actor == ROLE else 0)
            if actual & ~permitted or (actor == ROLE and actual & body):
                raise ValueError("Native source has unreviewed uevent access: " + actor + " " + source)
            native[source][actor] = actual
            choices[actor] = actual
            if actor == ROLE:
                choices[actor] |= bits["relabelto"]
            if actor == "p4_linux_udev_t":
                choices[actor] |= bits["write"]
        emit_groups(generated, "p4_uevent_native_" + str(index), target,
                    "file", names, bits, choices)
    output.write_text("\n".join(generated) + "\n")
    contract.update(native=native, native_roles=roles, native_derived_sha256=digest(output),
                    baseline_metadata=sorted(x for x in lines if
                      x.startswith(("(genfscon ", "(policycap ", "(mlsconstrain ", "(constrain "))))


def verify(library, linked, contract, binary_cil, export):
    policy = ContextPolicy(library, linked)
    lines = export(policy, linked, binary_cil)
    metadata = sorted(x for x in lines if x.startswith(("(genfscon ", "(policycap ", "(mlsconstrain ", "(constrain ")))
    if metadata != contract["baseline_metadata"]:
        raise ValueError("Uevent derivation changed existing genfs/capability/constraint rules")
    # The binary exporter expands constraint type sets. Replacing just the
    # target-type atoms must produce the same symbolic expression for each
    # source and alias. This covers every MLS range and every original actor.
    memberships = Membership(binary_cil.read_text())
    constraint_checks = 0
    def target_atoms(expression, selected):
        if not isinstance(expression, list):
            return expression
        if len(expression) == 3 and expression[0] in ("eq", "neq") and "t2" in expression[1:]:
            other = expression[2] if expression[1] == "t2" else expression[1]
            if isinstance(other, str) and other in ("t1", "t2", "t3"):
                raise ValueError("Linked uevent constraint has a type-identity comparison")
            value = memberships.member(other, selected)
            return value if expression[0] == "eq" else not value
        return [target_atoms(x, selected) for x in expression]
    for line in metadata:
        if not line.startswith(("(mlsconstrain ", "(constrain ")):
            continue
        form = parse_expression(line)
        if form[1][0] not in CLASSES:
            continue
        for row in contract["rows"]:
            if target_atoms(form[2], row["source"]) != target_atoms(form[2], row["target"]):
                raise ValueError("Linked uevent target changed a complete MLS constraint")
            constraint_checks += 1
    checks = 0
    ioctl_checks = 0
    for row in contract["rows"]:
        source, target = row["source"], row["target"]
        final_xperms = original_xperms([binary_cil], contract["subjects"], target)
        for cls, names in contract["classes"].items():
            for subject in contract["subjects"]:
                for level, expected in zip(LEVELS, contract["samples"][source][cls][subject]):
                    for object_type in (source, target):
                        actual = policy.context_av("u:r:" + subject + ":" + level,
                                                   "u:object_r:" + object_type + ":s0", cls, names)
                        if actual != expected:
                            raise ValueError("Uevent changed Android AV/MLS: " + subject + " " + object_type + " " + cls + " " + level)
                        checks += 1
                expected_ioctl = contract["xperms"][source][cls].get(subject)
                if expected_ioctl is not None:
                    if final_xperms[cls][subject] != expected_ioctl:
                        raise ValueError("Uevent changed exact Android ioctl permissions")
                    ioctl_checks += 1
    names = contract["classes"]["file"]
    _, bits = policy.permissions("file", names)
    native_checks = 0
    for row in contract["rows"]:
        source, target = row["source"], row["target"]
        for actor in contract["native_roles"]:
            original = contract["native"][source][actor]
            expected = original
            if actor == ROLE:
                expected |= bits["relabelto"]
            if actor == "p4_linux_udev_t":
                expected |= bits["write"]
            for object_type, wanted in ((source, original), (target, expected)):
                actual = policy.context_av("u:system_r:" + actor + ":s0",
                                           "u:object_r:" + object_type + ":s0", "file", names)
                if actual != wanted:
                    raise ValueError("Uevent changed native AV boundary: " + actor + " " + object_type)
                native_checks += len(names)
    helper = "u:system_r:" + ROLE + ":s0"
    objects = sorted(x[len("(roletype object_r "):-1] for x in lines if x.startswith("(roletype object_r "))
    sources = {r["source"] for r in contract["rows"]}
    targets = {r["target"] for r in contract["rows"]}
    boundary = 0
    def exact(subject, target, cls, permissions, expected):
        nonlocal boundary
        _, values = policy.permissions(cls, permissions)
        actual = policy.context_av(subject, target, cls, permissions)
        wanted = sum(values[x] for x in expected)
        if actual != wanted:
            raise ValueError("Native uevent boundary mismatch: " + subject + " " + target + " " + cls + " " + str(permissions))
        boundary += len(permissions)
    for target in objects:
        context = "u:object_r:" + target + ":s0"
        expected = (["relabelfrom"] if target in sources else []) + (["relabelfrom", "relabelto"] if target in targets else [])
        exact(helper, context, "file", ["relabelfrom", "relabelto"], expected)
        exact(helper, context, "dir", ["create", "write", "add_name", "remove_name", "rmdir", "setattr", "mounton", "relabelfrom", "relabelto"], [])
    def class_permissions(cls):
        raw = next(x for x in lines if x.startswith("(class " + cls + " "))
        permissions = list(parse_expression(raw)[2])
        inherited = [parse_expression(x)[2] for x in lines
                     if x.startswith("(classcommon " + cls + " ")]
        for common in inherited:
            declaration = next(x for x in lines if x.startswith("(common " + common + " "))
            permissions = parse_expression(declaration)[2] + permissions
        if not permissions or len(permissions) != len(set(permissions)):
            raise ValueError("Invalid inherited class permissions in uevent verifier")
        return permissions
    for cls in ("capability", "capability2", "cap_userns", "cap2_userns"):
        permissions = class_permissions(cls)
        if len(permissions) > 32:
            raise ValueError("Invalid inherited capability permissions")
        exact(helper, helper, cls, permissions, [])
    for target in objects:
        wanted = {
            "p4_linux_standardio_t": ["getattr", "read", "write"],
            "null_device": ["getattr", "open", "read", "write"],
        }.get(target, [])
        exact(helper, "u:object_r:" + target + ":s0", "chr_file",
              class_permissions("chr_file"), wanted)
    for target in ("device", "p4_linux_native_dev_root_t"):
        exact(helper, "u:object_r:" + target + ":s0", "dir",
              ["getattr", "search", "open", "read", "write", "add_name", "remove_name"],
              ["getattr", "search"])
    for role in contract["native_roles"]:
        subject = "u:system_r:" + role + ":s0"
        allowed = ["transition"] if role == "p4_linux_service_executor_t" else []
        exact(subject, helper, "process", ["transition", "dyntransition", "ptrace", "setexec", "setcurrent"], allowed)
    exact(helper, "u:system_r:p4_linux_service_executor_t:s0", "unix_stream_socket",
          ["getattr", "read", "write", "create", "connect", "connectto", "bind", "listen", "accept"],
          ["getattr", "read", "write"])
    exact(helper, helper, "process", ["fork", "setexec", "setcurrent", "setfscreate", "setsockcreate", "setkeycreate"], [])
    transition = policy.lib.sepol_validate_transition_reason_buffer
    transition.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                           ctypes.c_uint16, ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint]
    transition.restype = ctypes.c_int
    policy.libc.free.argtypes = [ctypes.c_void_p]
    file_class, _ = policy.permissions("file", names)
    pairs = {(r["source"], r["target"]) for r in contract["rows"]}
    pairs.update((r["target"], r["target"]) for r in contract["rows"])
    transition_checks = 0
    for old in sorted(sources | targets | {"proc", "p4_linux_native_data_t"}):
        for new in sorted(sources | targets):
            reason = ctypes.c_void_p()
            try:
                rc = transition(policy.context_sid("u:object_r:" + old + ":s0"),
                                policy.context_sid("u:object_r:" + new + ":s0"),
                                policy.context_sid(helper), file_class, ctypes.byref(reason), 0)
                expected = 0 if (old, new) in pairs else -1  # -EPERM
                if rc != expected:
                    raise ValueError("Linked uevent pair constraint differs: " + old + " -> " + new)
            finally:
                if reason.value:
                    policy.libc.free(reason)
            transition_checks += 1
    return {"map_sha256": contract["map_sha256"], "pairs": contract["rows"],
            "android_userspace_subjects": len(contract["subjects"]) - 1,
            "original_kernel_access_preserved": True,
            "equal_android_av_mcs_decisions": checks, "mcs_samples": list(LEVELS),
            "exact_android_ioctl_decisions": ioctl_checks,
            "unchanged_target_constraint_atoms": contract["constraints"],
            "all_ranges_equal_linked_target_constraint_expressions": constraint_checks,
            "native_role_types": len(contract["native_roles"]), "native_permission_checks": native_checks,
            "helper_boundary_permission_checks": boundary,
            "linked_exact_pair_validatetrans_checks": transition_checks,
            "unchanged_genfs_entries": sum(x.startswith("(genfscon ") for x in metadata),
            "unchanged_policy_capabilities": sum(x.startswith("(policycap ") for x in metadata),
            "android_derived_sha256": contract["android_derived_sha256"],
            "native_derived_sha256": contract["native_derived_sha256"],
            "capabilities_added": [], "runtime_qualified": False}
