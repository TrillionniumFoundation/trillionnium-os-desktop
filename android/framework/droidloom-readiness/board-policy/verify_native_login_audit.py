"""Binary admission for the selected stock PAM/OpenSSH audit messages."""
import ctypes
import hashlib
import json
from derive_shared_payload_cgroup_policy import Decision, Policy, parse_expression

PAM_MESSAGES = (1100, 1101, 1103, 1104, 1105, 1106, 1108, 1109, 1110)
LOGIN_AUDIT_MESSAGES = {
    "p4_linux_sshd_t": (*PAM_MESSAGES, 1112, 2300),
    "p4_linux_gdm_worker_t": (*PAM_MESSAGES, 2300),
    "p4_linux_service_executor_t": PAM_MESSAGES,
}
SOCKET_PERMISSIONS = (
    "ioctl", "read", "write", "create", "getattr", "setattr", "lock",
    "relabelfrom", "relabelto", "append", "map", "bind", "connect",
    "listen", "accept", "getopt", "setopt", "shutdown", "recvfrom",
    "sendto", "name_bind", "nlmsg_read", "nlmsg_write", "nlmsg_relay",
    "nlmsg_readpriv", "nlmsg_tty_audit", "nlmsg",
)
SOCKET_ALLOWED = {"create", "read", "write", "nlmsg"}

def verify_login_audit(library, binary, export, export_binary_policy):
    policy = Policy(library, binary)
    lines = export_binary_policy(policy, binary, export)
    if "(policycap netlink_xperm)" not in lines:
        raise ValueError("Selected shared kernel audit transport requires netlink_xperm")
    forms = [parse_expression(line) for line in lines
             if line.startswith(("(type ", "(typeattributeset ", "(allowx "))]
    types = {f[1] for f in forms if f[0] == "type"}
    definitions = {}
    for form in forms:
        if form[0] == "typeattributeset":
            definitions.setdefault(form[1], []).append(form[2])
    def members(expr, active=()):
        if isinstance(expr, str):
            if expr in types:
                return {expr}
            if expr in active or expr not in definitions:
                raise ValueError("Unresolved binary audit type expression: " + expr)
            return set().union(*(members(x, (*active, expr))
                                 for x in definitions[expr]))
        if expr and expr[0] == "all":
            return types
        if expr and expr[0] == "not":
            return types - members(expr[1], active)
        if expr and expr[0] == "and":
            return set.intersection(*(members(x, active) for x in expr[1:]))
        values = expr[1:] if expr and expr[0] == "or" else expr
        return set().union(*(members(x, active) for x in values))
    def values(expr):
        if isinstance(expr, str):
            n = int(expr, 0)
            if not 0 <= n <= 65535:
                raise ValueError("Audit message number outside u16")
            return {n}
        if expr and expr[0] == "range":
            lo, hi = (int(x, 0) for x in expr[1:])
            if not 0 <= lo <= hi <= 65535:
                raise ValueError("Invalid binary audit range")
            return set(range(lo, hi + 1))
        if expr and expr[0] == "not":
            return set(range(65536)) - values(expr[1])
        return set().union(*(values(x) for x in expr))
    checks = []
    sids = {}
    def sid(context):
        if context not in sids:
            raw = context.encode()
            value = ctypes.c_uint32()
            if policy.lib.sepol_context_to_sid(raw, len(raw) + 1, ctypes.byref(value)):
                raise ValueError("Invalid audit actor: " + context)
            sids[context] = value.value
        return sids[context]
    def observed(context, kind, permissions):
        number, bits = policy.permissions(kind, permissions)
        mask = 0
        for bit in bits.values():
            mask |= bit
        decision = Decision()
        if policy.lib.sepol_compute_av(sid(context), sid(context), number,
                                      mask, ctypes.byref(decision)):
            raise ValueError("Cannot read native login audit AV")
        return {p for p, bit in bits.items() if decision.allowed & bit}
    for actor, wanted in LOGIN_AUDIT_MESSAGES.items():
        context = "u:system_r:" + actor + ":s0"
        actual = observed(context, "netlink_audit_socket", SOCKET_PERMISSIONS)
        if actual != SOCKET_ALLOWED:
            raise ValueError(f"Login audit socket boundary differs for {actor}: {actual}")
        if observed(context, "capability", ["audit_write", "audit_control"]) != {"audit_write"}:
            raise ValueError("Login audit requires only AUDIT_WRITE: " + actor)
        if observed(context, "capability2", ["audit_read"]):
            raise ValueError("Login audit must not read the audit stream")
        messages = set()
        for form in forms:
            if form[0] != "allowx":
                continue
            source, target, permission = form[1:]
            if permission[:2] != ["nlmsg", "netlink_audit_socket"]:
                continue
            if actor in members(source) and (target == "self" or actor in members(target)):
                messages |= values(permission[2])
        if messages != set(wanted):
            raise ValueError(f"Linked login audit message set differs for {actor}: {sorted(messages)}")
        checks.append([actor, sorted(actual), sorted(messages)])
    for context in ("u:r:droidloom_broker:s0",
                    "u:system_r:droidloom_public_control_client:s0",
                    "u:system_r:p4_linux_user_session_t:s0"):
        if observed(context, "netlink_audit_socket", SOCKET_PERMISSIONS):
            raise ValueError("Public application role gained audit transport")
        checks.append([context, [], []])
    return {
        "actors": len(LOGIN_AUDIT_MESSAGES),
        "socket_permission_decisions": len(SOCKET_PERMISSIONS) * 6,
        "exact_u16_message_checks": 65536 * len(LOGIN_AUDIT_MESSAGES),
        "allowed_message_ids": LOGIN_AUDIT_MESSAGES,
        "audit_control_and_read_denied": True,
        "matrix_sha256": hashlib.sha256(json.dumps(checks, separators=(",", ":")).encode()).hexdigest(),
        "binary_export_sha256": hashlib.sha256(export.read_bytes()).hexdigest(),
    }
