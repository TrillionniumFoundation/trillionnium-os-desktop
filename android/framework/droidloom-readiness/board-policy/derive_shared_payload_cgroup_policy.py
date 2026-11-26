"""Preserve stock Android access on the fixed, shared payload cgroup inodes.

The normal linker calls this only after independently reproducing the pinned
original Android binary. No original CIL or assertion is changed. The new
objects are shared cgroup control files, not Linux-private data. Android
userspace permissions are copied as effective AV decisions, with complementary
neverallows, and checked again against the final linked binary.
"""
import ctypes
import hashlib
import re
from collections import defaultdict


class Decision(ctypes.Structure):
    _fields_ = [
        ("allowed", ctypes.c_uint32), ("decided", ctypes.c_uint32),
        ("auditallow", ctypes.c_uint32), ("auditdeny", ctypes.c_uint32),
        ("seqno", ctypes.c_uint32),
    ]


class Policy:
    def __init__(self, library, binary):
        self.lib = ctypes.CDLL(str(library))
        self.libc = ctypes.CDLL(None)
        self.libc.fopen.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self.libc.fopen.restype = ctypes.c_void_p
        self.libc.fclose.argtypes = [ctypes.c_void_p]
        self.lib.sepol_set_policydb_from_file.argtypes = [ctypes.c_void_p]
        self.lib.sepol_set_policydb_from_file.restype = ctypes.c_int
        stream = self.libc.fopen(str(binary).encode(), b"rb")
        if not stream:
            raise ValueError("Cannot open the reproduced policy")
        try:
            if self.lib.sepol_set_policydb_from_file(stream) != 0:
                raise ValueError("Cannot load the reproduced policy")
        finally:
            self.libc.fclose(stream)
        self.lib.sepol_context_to_sid.argtypes = [
            ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_uint32)]
        self.lib.sepol_context_to_sid.restype = ctypes.c_int
        self.lib.sepol_string_to_security_class.argtypes = [
            ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint16)]
        self.lib.sepol_string_to_security_class.restype = ctypes.c_int
        self.lib.sepol_string_to_av_perm.argtypes = [
            ctypes.c_uint16, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32)]
        self.lib.sepol_string_to_av_perm.restype = ctypes.c_int
        self.lib.sepol_compute_av.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint16,
            ctypes.c_uint32, ctypes.POINTER(Decision)]
        self.lib.sepol_compute_av.restype = ctypes.c_int
        self.sids = {}

    def sid(self, name, object_role=False):
        context = "u:" + ("object_r" if object_role else "r") + ":" + name + ":s0"
        if context not in self.sids:
            value = ctypes.c_uint32()
            raw = context.encode()
            if self.lib.sepol_context_to_sid(raw, len(raw) + 1, ctypes.byref(value)) != 0:
                raise ValueError("Original CIL contains an invalid context: " + context)
            self.sids[context] = value.value
        return self.sids[context]

    def permissions(self, class_name, names):
        number = ctypes.c_uint16()
        if self.lib.sepol_string_to_security_class(class_name.encode(), ctypes.byref(number)) != 0:
            raise ValueError("Missing original class: " + class_name)
        permissions = {}
        for name in names:
            value = ctypes.c_uint32()
            if self.lib.sepol_string_to_av_perm(number, name.encode(), ctypes.byref(value)) != 0:
                raise ValueError("Missing original permission: " + class_name + "." + name)
            permissions[name] = value.value
        return number.value, permissions

    def av(self, subject, target, class_number, mask):
        decision = Decision()
        if self.lib.sepol_compute_av(
                self.sid(subject), self.sid(target, True), class_number, mask,
                ctypes.byref(decision)) != 0:
            raise ValueError("Cannot compute the fixed cgroup decision")
        return decision.allowed & mask


def original_declarations(inputs):
    text = "\n".join(path.read_text() for path in inputs)
    types = set(re.findall(r"\(type ([A-Za-z0-9_]+)\)", text))
    roles = set(re.findall(r"\(roletype r ([A-Za-z0-9_]+)\)", text))
    if roles != {"domain"}:
        raise ValueError("Original Android role declaration changed")
    # Public versioned Android attributes are positive unions of concrete
    # types. Resolve their actual pinned declarations; do not guess suffixes.
    assignments = defaultdict(list)
    for name, body in re.findall(r"\(typeattributeset ([A-Za-z0-9_]+) \(([^()]*)\)\)", text):
        assignments[name].append(body.split())
    counts = defaultdict(int)
    for line in text.splitlines():
        match = re.match(r"\(typeattributeset ([A-Za-z0-9_]+) ", line)
        if match:
            counts[match.group(1)] += 1
    def members(name, active=()):
        if name in types:
            return {name}
        if name in active or not assignments[name] or len(assignments[name]) != counts[name]:
            raise ValueError("Non-explicit/cyclic Android role membership: " + name)
        result = set()
        for values in assignments[name]:
            for child in values:
                result.update(members(child, (*active, name)))
        return result
    subjects = members("domain")
    if not subjects or subjects - types:
        raise ValueError("Original Android domain membership contains non-concrete types")
    # kernel is the boot factory, not Android userspace. Its fixed host-side
    # control permissions are reviewed separately in instance-factory-cgroup.cil.
    subjects.remove("kernel")
    common = {}
    classes = {}
    for name, body in re.findall(r"\(common ([A-Za-z0-9_]+) \(([^()]*)\)\)", text):
        common[name] = body.split()
    for name in ("dir", "file", "lnk_file"):
        declarations = re.findall(r"\(class " + name + r" \(([^()]*)\)\)", text)
        inheritance = re.findall(r"\(classcommon " + name + r" ([A-Za-z0-9_]+)\)", text)
        if not declarations or len(set(declarations)) != 1 or len(set(inheritance)) != 1:
            raise ValueError("Original cgroup class declaration changed: " + name)
        classes[name] = common[inheritance[0]] + declarations[0].split()
        if len(classes[name]) != len(set(classes[name])) or len(classes[name]) > 32:
            raise ValueError("Invalid original cgroup permission set")
    return sorted(subjects), classes


def parse_expression(text):
    tokens = re.findall(r"\(|\)|[^\s()]+", text)
    position = 0
    def take():
        nonlocal position
        if position >= len(tokens):
            raise ValueError("Truncated original CIL expression")
        token = tokens[position]
        position += 1
        if token != "(":
            if token == ")":
                raise ValueError("Unexpected original CIL closing parenthesis")
            return token
        result = []
        while position < len(tokens) and tokens[position] != ")":
            result.append(take())
        if position >= len(tokens):
            raise ValueError("Unclosed original CIL expression")
        position += 1
        return result
    result = take()
    if position != len(tokens):
        raise ValueError("Trailing original CIL expression")
    return result


def original_xperms(inputs, subjects, target_type="cgroup_v2", *,
                    class_names=("dir", "file", "lnk_file")):
    if (isinstance(class_names, str) or not class_names or
            len(set(class_names)) != len(class_names) or
            not set(class_names).issubset({"dir", "file", "lnk_file", "chr_file", "blk_file"})):
        raise ValueError("Explicit filesystem ioctl classes are required")
    text = "\n".join(path.read_text() for path in inputs)
    types = set(re.findall(r"\(type ([A-Za-z0-9_]+)\)", text))
    definitions = defaultdict(list)
    statements = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("(typeattributeset "):
            form = parse_expression(line)
            if len(form) != 3:
                raise ValueError("Unsupported original type membership declaration")
            definitions[form[1]].append(form[2])
        elif line.startswith("(allowx "):
            form = parse_expression(line)
            if len(form) != 4 or len(form[3]) != 3:
                raise ValueError("Unsupported original extended permission rule")
            statements.append(form)
    if len(statements) != text.count("(allowx "):
        raise ValueError("Original extended permissions are not unconditional CIL statements")
    cache = {}
    def member(name, selected, active=()):
        if name in types:
            return name == selected
        if name == "self":
            return False
        key = (name, selected)
        if key in cache:
            return cache[key]
        if name in active or name not in definitions:
            raise ValueError("Unresolved/cyclic original type membership: " + name)
        def evaluate(expression):
            if isinstance(expression, str):
                return member(expression, selected, (*active, name))
            if not expression:
                return False
            operation, *args = expression
            if operation == "all":
                if args:
                    raise ValueError("Invalid original all expression")
                return True
            if operation == "not":
                if len(args) != 1:
                    raise ValueError("Invalid original not expression")
                return not evaluate(args[0])
            if operation == "and":
                return all(evaluate(arg) for arg in args)
            if operation == "or":
                return any(evaluate(arg) for arg in args)
            if operation == "xor":
                if len(args) != 2:
                    raise ValueError("Invalid original xor expression")
                return evaluate(args[0]) != evaluate(args[1])
            return any(evaluate(arg) for arg in expression)
        value = any(evaluate(expression) for expression in definitions[name])
        cache[key] = value
        return value
    all_ioctl = (1 << 65536) - 1
    def numbers(expression):
        if isinstance(expression, str):
            value = int(expression, 0)
            if not 0 <= value <= 0xffff:
                raise ValueError("Original ioctl number outside the kernel ABI")
            return 1 << value
        if expression and expression[0] == "range":
            if len(expression) != 3:
                raise ValueError("Invalid original ioctl range")
            first, last = int(expression[1], 0), int(expression[2], 0)
            if not 0 <= first <= last <= 0xffff:
                raise ValueError("Invalid original ioctl range")
            return ((1 << (last - first + 1)) - 1) << first
        if expression and expression[0] == "not":
            if len(expression) != 2:
                raise ValueError("Invalid original ioctl complement")
            return all_ioctl ^ numbers(expression[1])
        result = 0
        for item in expression:
            result |= numbers(item)
        return result
    result = {name: {subject: 0 for subject in subjects}
              for name in class_names}
    for _, source, target, rule in statements:
        operation, class_name, values = rule
        if operation != "ioctl" or class_name not in result or not member(target, target_type):
            continue
        allowed = numbers(values)
        for subject in subjects:
            if member(source, subject):
                result[class_name][subject] |= allowed
    return result


def format_xperms(mask):
    values = []
    start = 0
    while mask:
        low = (mask & -mask).bit_length() - 1
        high = low
        while mask & (1 << (high + 1)):
            high += 1
        values.append(hex(low) if low == high else "(range " + hex(low) + " " + hex(high) + ")")
        mask &= ~(((1 << (high - low + 1)) - 1) << low)
        start = high + 1
    if not values:
        raise ValueError("A stock ioctl-allowed subject has no original xperm rule")
    return "(" + " ".join(values) + ")"


def derive(library, original, inputs, output):
    subjects, classes = original_declarations(inputs)
    policy = Policy(library, original)
    xperms = original_xperms(inputs, subjects)
    xperm_checks = 0
    lines = [
        "; Derived by the normal shared-kernel linker from the reproduced",
        "; original Android policy. Original CIL/assertions are retained.",
        "; Userspace access to fixed payload control inodes is exactly stock.",
    ]
    decisions = {}
    for class_name, permission_names in classes.items():
        number, permissions = policy.permissions(class_name, permission_names)
        mask = sum(permissions.values())
        groups = defaultdict(list)
        decisions[class_name] = {}
        for subject in subjects:
            allowed = policy.av(subject, "cgroup_v2", number, mask)
            decisions[class_name][subject] = allowed
            groups[allowed].append(subject)
        for index, (allowed, members) in enumerate(sorted(groups.items())):
            attribute = "p4_payload_android_" + class_name + "_" + str(index)
            lines += [
                "(typeattribute " + attribute + ")",
                "(typeattributeset " + attribute + " (" + " ".join(members) + "))",
            ]
            yes = [name for name in permission_names if permissions[name] & allowed]
            no = [name for name in permission_names if not (permissions[name] & allowed)]
            if yes:
                lines.append("(allow " + attribute + " p4_android_payload_objects (" +
                             class_name + " (" + " ".join(yes) + ")))")
            if no:
                lines.append("(neverallow " + attribute + " p4_android_payload_objects (" +
                             class_name + " (" + " ".join(no) + ")))")
        # A base IOCTL AV permission does not describe the allowed commands.
        # Reproduce the original union and assert its full 16-bit complement.
        # The latter makes any extra inherited xperm a strict compile failure.
        ioctl_groups = defaultdict(list)
        for subject in subjects:
            if decisions[class_name][subject] & permissions["ioctl"]:
                ioctl_groups[xperms[class_name][subject]].append(subject)
        for index, (allowed, members) in enumerate(sorted(ioctl_groups.items())):
            attribute = "p4_payload_ioctl_" + class_name + "_" + str(index)
            values = format_xperms(allowed)
            lines += [
                "(typeattribute " + attribute + ")",
                "(typeattributeset " + attribute + " (" + " ".join(members) + "))",
                "(allowx " + attribute + " p4_android_payload_objects (ioctl " + class_name + " " + values + "))",
                "(neverallowx " + attribute + " p4_android_payload_objects (ioctl " + class_name + " (not " + values + ")))",
            ]
            xperm_checks += len(members) * 2
    output.write_text("\n".join(lines) + "\n")
    return {
        "subjects": subjects, "classes": classes, "decisions": decisions,
        "exact_ioctl_decisions": xperm_checks,
        "derived_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def verify(library, linked, contract):
    policy = Policy(library, linked)
    checked = 0
    for class_name, permission_names in contract["classes"].items():
        number, permissions = policy.permissions(class_name, permission_names)
        mask = sum(permissions.values())
        for subject, expected in contract["decisions"][class_name].items():
            for target in ("p4_android_payload_cgroup_t", "p4_android_payload_membership_t"):
                actual = policy.av(subject, target, number, mask)
                if actual != expected:
                    raise ValueError("Shared payload changed Android access: " +
                                     subject + " " + target + " " + class_name)
                checked += 1
    return {
        "android_userspace_subjects": len(contract["subjects"]),
        "equal_effective_access_decisions": checked,
        "strict_exact_ioctl_decisions": contract["exact_ioctl_decisions"],
        "derived_sha256": contract["derived_sha256"],
    }
