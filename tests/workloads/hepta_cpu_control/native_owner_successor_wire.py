"""Decode the original kernel successor receipts without qualifying a scenario.

The source is the frozen OS HOS2LRES/HOS2LWDR protocol, not a replacement
producer. These helpers accept complete original byte arrays and preserve them.
No event handler, test-success record or userspace durability claim lives here.
"""
import struct

from native_owner_evidence import CAP_NS, PERIOD_NS, byte_id, integer, require


RECEIPT_BYTES = 128
U64_MAX = (1 << 64) - 1
MANAGER_LEASE_NS = 300_000_000_000
RECOVERY_GRACE_NS = 30_000_000_000


def exact_bytes(value, length, name):
    require(type(value) is list and len(value) == length
            and all(type(item) is int and 0 <= item <= 255 for item in value),
            name + " must preserve the complete original byte array")
    return bytes(value)


def word(raw, offset):
    return struct.unpack_from("<Q", raw, offset)[0]


def native_space(raw, boot_id, name):
    value = byte_id(list(raw), name)
    require(value[:8] == boot_id[:8], name + " does not belong to the original boot")
    return value


def launch_receipt(value, boot_id):
    """Decode one original Query/Advance/AckSaved receipt; infer no lifecycle."""
    boot_id = byte_id(boot_id, "actual native boot")
    raw = exact_bytes(value, RECEIPT_BYTES, "kernel launch receipt")
    require(raw[:8] == b"HOS2LRES" and word(raw, 8) == 1 and raw[112:] == bytes(16),
            "kernel launch receipt magic, version or reserved bytes differ")
    mode, generation = word(raw, 16), word(raw, 24)
    require(mode in (1, 2), "unknown original launcher mode")
    pids = dict(zip(("root", "workload", "manager", "recovery", "history"),
                    (word(raw, offset) for offset in (32, 40, 48, 56, 64))))
    require(pids["root"] == 1 and 0 < pids["workload"] < 1 << 31,
            "original Root or workload identity differs")
    if mode == 1:
        require(pids["history"] == 0
                and all(0 < pids[role] < 1 << 31 for role in ("manager", "recovery")),
                "pair receipt must name both actual privileged children")
        active = (pids["root"], pids["workload"], pids["manager"], pids["recovery"])
    else:
        require(generation > 0 and pids["manager"] == pids["recovery"] == 0
                and 0 < pids["history"] < 1 << 31,
                "history-only receipt must name one actual history child")
        active = (pids["root"], pids["workload"], pids["history"])
    require(len(set(active)) == len(active), "actual launched role PIDs alias")
    previous = word(raw, 72)
    require(previous == max(0, generation - 1), "original launch predecessor generation differs")
    spaces = [native_space(raw[80:96], boot_id, "launch Manager history"),
              native_space(raw[96:112], boot_id, "launch Recovery history")]
    require(spaces[0] != spaces[1], "the two original history namespaces alias")
    return {"raw": list(raw), "mode": mode, "generation": generation,
            "previous_generation": previous, "pids": pids, "history_spaces": spaces}


def retirement_receipt(value, boot_id):
    """Decode the immutable old policy cut, preserving time-presence and mode."""
    boot_id = byte_id(boot_id, "actual native boot")
    raw = exact_bytes(value, RECEIPT_BYTES, "kernel policy retirement receipt")
    require(raw[:8] == b"HOS2LWDR" and word(raw, 8) == 1 and word(raw, 16) > 0,
            "kernel retirement magic, version or generation differs")
    generation, status, evaluated, flags = (word(raw, offset) for offset in (16, 24, 32, 120))
    require(0 <= status <= 7 and flags in (0, 1, 3),
            "kernel retirement status or presence flags are unknown")
    has_policy, has_time = bool(flags & 1), bool(flags & 2)
    require(has_time or evaluated == 0, "absent retirement time has a fabricated value")
    spaces = [native_space(raw[88:104], boot_id, "retired Manager history"),
              native_space(raw[104:120], boot_id, "retired Recovery history")]
    require(spaces[0] != spaces[1], "retired original history namespaces alias")
    if not has_policy:
        require(status == 0 and raw[32:88] == bytes(56),
                "history-only launch cannot invent a retired CPU policy or watchdog effect")
    if status == 0:
        require(not has_time and evaluated == 0,
                "untriggered watchdog cannot contain an evaluated time")
    receipt = None
    if status == 1:
        require(has_policy and has_time, "Restored lacks an actual retired policy and time")
        stable_id = byte_id(list(raw[40:56]), "original watchdog stable CPU object")
        previous, revision, effective, consumed = (word(raw, offset) for offset in (56, 64, 72, 80))
        require(previous < U64_MAX and revision == previous + 1 and effective == evaluated
                and consumed <= effective % PERIOD_NS,
                "original watchdog revision/time/accounting receipt differs")
        receipt = {"stable_object_id": stable_id, "previous_revision": previous,
                   "revision": revision, "effective_ns": effective, "consumed_ns": consumed}
    else:
        require(raw[40:88] == bytes(48), "non-Restored retirement fabricated a CPU effect receipt")
    return {"raw": list(raw), "generation": generation, "status": status,
            "flags": flags, "policy_retired": has_policy,
            "evaluated_ns": evaluated if has_time else None,
            "history_spaces": spaces, "resource_receipt": receipt}


def match_transition(previous, current, retirement):
    """Match original receipt identities; callers still need reap/Current proof."""
    require(previous["generation"] < U64_MAX
            and current["generation"] == previous["generation"] + 1
            and current["previous_generation"] == previous["generation"]
            and retirement["generation"] == current["generation"],
            "actual successful launch/retirement generation chain differs")
    require(all(current["pids"][role] == previous["pids"][role] for role in ("root", "workload"))
            and retirement["history_spaces"] == previous["history_spaces"],
            "successor changed original Root/workload or retired another history pair")
    if current["mode"] == 2:
        require(current["history_spaces"] == previous["history_spaces"]
                and retirement["flags"] == 0,
                "history-only launch reset history or falsely retired the CPU policy")
    else:
        require(retirement["policy_retired"]
                and not any(space in previous["history_spaces"] for space in current["history_spaces"]),
                "fresh pair reused a predecessor effect namespace or lacks the original policy cut")


def successor_bootstrap(value, boot_id, launched):
    """Decode the actual meaningful 240 bytes read by that successor image.

    This does not claim that the unreported rest of the 4096-byte page was
    independently observed, or that the original Host completed activation.
    """
    boot_id = byte_id(boot_id, "actual native boot")
    raw = exact_bytes(value, 240, "actual successor bootstrap bytes")
    require(raw[:8] == b"HOS2BOOT" and word(raw, 8) == 4 and word(raw, 24) == 240
            and word(raw, 232) == 0 and list(raw[96:112]) == boot_id,
            "successor bootstrap magic, version, size, boot or reserved word differs")
    role = word(raw, 16)
    require(role in (1, 3, 5) and (role == 5) == (launched["mode"] == 2),
            "actual successor role differs from the original launch mode")
    expected_handles = {
        1: (1, 1, 2, 1, 3, 1, 0, 0),
        3: (1, 1, 2, 1, 3, 1, 4, 1),
        5: (0, 0, 0, 0, 3, 1, 4, 1),
    }[role]
    require(tuple(word(raw, offset) for offset in range(32, 96, 8)) == expected_handles,
            "actual successor bootstrap changed its original handle allocation")
    spaces = [native_space(raw[112:128], boot_id, "bootstrap Manager history"),
              native_space(raw[128:144], boot_id, "bootstrap Recovery history")]
    require(spaces == launched["history_spaces"], "bootstrap substituted another original history pair")
    pids = launched["pids"]
    require((word(raw, 144), word(raw, 152), word(raw, 160), word(raw, 192))
            == (pids["manager"], pids["workload"], pids["recovery"], pids["root"]),
            "bootstrap changed the actual launched role identities")
    role_name = {1: "manager", 3: "recovery", 5: "history"}[role]
    own_pid, generation = word(raw, 200), word(raw, 224)
    require(own_pid == pids[role_name] and generation > 0 and generation == launched["generation"],
            "bootstrap is not bound to this actual Process and generation")
    require(word(raw, 168) == (0 if role == 5 else CAP_NS)
            and word(raw, 176) == PERIOD_NS
            and word(raw, 184) == (0 if role == 5 else MANAGER_LEASE_NS),
            "successor bootstrap changed the original bounded CPU profile")
    local = native_space(raw[208:224], boot_id, "successor actual local CapSpace")
    require((local not in spaces) if role == 5 else local == spaces[0 if role == 1 else 1],
            "successor local CapSpace aliases retained history or differs from its new role")
    return {"raw": list(raw), "role": role, "pid": own_pid, "generation": generation,
            "local_space": local, "history_spaces": spaces,
            "observe_handle": list(expected_handles[:2]),
            "manage_handle": list(expected_handles[2:4])}


def initial_bootstrap(value, boot_id, role, role_pids, spaces):
    """Check the actual initial Host page without constructing a launch reply."""
    raw = exact_bytes(value, 200, "actual original bootstrap bytes")
    require(role in ("manager", "recovery") and raw[:8] == b"HOS2BOOT"
            and word(raw, 8) == 3 and word(raw, 24) == 200
            and word(raw, 16) == {"manager": 1, "recovery": 3}[role]
            and list(raw[96:112]) == byte_id(boot_id, "actual initial boot"),
            "initial Host bootstrap identity differs")
    expected = (1, 1, 2, 1, 3, 1, 0, 0) if role == "manager" else (1, 1, 2, 1, 3, 1, 4, 1)
    require(tuple(word(raw, offset) for offset in range(32, 96, 8)) == expected
            and list(raw[112:128]) == spaces["manager"] and list(raw[128:144]) == spaces["recovery"]
            and (word(raw, 144), word(raw, 152), word(raw, 160), word(raw, 192))
                == (role_pids["manager"], role_pids["workload"], role_pids["recovery"], role_pids["root"])
            and (word(raw, 168), word(raw, 176), word(raw, 184)) == (CAP_NS, PERIOD_NS, MANAGER_LEASE_NS),
            "initial Host changed its actual handles, namespaces, processes or finite profile")
    return {"raw": list(raw), "role": {"manager": 1, "recovery": 3}[role], "pid": role_pids[role],
            "generation": 0, "local_space": spaces[role], "history_spaces": [spaces["manager"], spaces["recovery"]],
            "observe_handle": list(expected[:2]), "manage_handle": list(expected[2:4])}


def initial_expiry_upper_bound(initial_manager_sample_ns, include_recovery=False):
    """Use a real initial Manager ReadUsage sample, never a role-5 clock value.

    ReadUsage settles the same clock and requires sample >= issued. This is a
    conservative bound, not an observation of an exact private grant expiry.
    """
    sample = integer(initial_manager_sample_ns, "initial Manager actual usage sample")
    require(type(include_recovery) is bool, "grant scope must be explicit")
    duration = MANAGER_LEASE_NS + (RECOVERY_GRACE_NS if include_recovery else 0)
    require(sample <= U64_MAX - duration, "original finite-grant time bound overflow")
    return sample + duration
