"""Finite original-kernel lifecycle samples, never a continuous peak or reserve."""

import re

PREFIX = "[hepta-g2-memory]"
LINE = re.compile(
    r"^\[hepta-g2-memory\] schema=1 sample=([0-9]+) stage=([a-z_]+) generation=([0-9]+) "
    r"role=([a-z]+) pid=([0-9]+) ordinary_free_bytes=([0-9]+) sampled_min_free_bytes=([0-9]+) "
    r"slab_backing_bytes=([0-9]+) account_present=(true|false) selected_user_pages=([0-9]+) "
    r"selected_user_limit_pages=([0-9]+) complete_peak=false global_memory_reserve=false$")
FIELDS = ("sample", "stage", "generation", "role", "pid", "ordinary_free_bytes",
          "sampled_min_free_bytes", "slab_backing_bytes", "account_present",
          "selected_user_pages", "selected_user_limit_pages")


def require(condition, message):
    if not condition:
        raise ValueError("memory samples: " + message)


def evaluate(lines, role_pids, image_indices, activation_index, first_owner_event_index):
    records = []
    minimum = 512 * 1024**2
    for index, line in enumerate(lines):
        if not line.startswith(PREFIX):
            continue
        match = LINE.fullmatch(line)
        require(match is not None, "unknown schema, field, or qualification claim")
        value = dict(zip(FIELDS, match.groups()))
        for name in FIELDS:
            if name not in ("stage", "role", "account_present"):
                value[name] = int(value[name])
                require(value[name] < 1 << 64, "integer exceeds the original word bound")
        value["account_present"] = value["account_present"] == "true"
        require(value["sample"] == len(records) + 1 <= 64, "missing, reordered, or excessive record")
        require(value["ordinary_free_bytes"] <= 512 * 1024**2
                and value["slab_backing_bytes"] <= 512 * 1024**2,
                "observation exceeds the fixed guest memory")
        minimum = min(minimum, value["ordinary_free_bytes"])
        require(value["sampled_min_free_bytes"] == minimum, "minimum differs from retained samples")
        if value["role"] == "none":
            require(value["pid"] == 0, "system sample names a process")
        else:
            require(value["role"] in ("root", "manager", "workload", "recovery", "history")
                    and 0 < value["pid"] < 1 << 31, "invalid process role or PID")
        if value["role"] == "workload":
            require(value["account_present"] and value["selected_user_limit_pages"] == 16_384
                    and value["selected_user_pages"] <= value["selected_user_limit_pages"],
                    "original workload account differs from its unchanged selected-frame bound")
        else:
            require(not value["account_present"] and value["selected_user_pages"] == 0
                    and value["selected_user_limit_pages"] == 0,
                    "unaccounted original role was relabelled as having a fixed account")
        value["serial_line_index"] = index
        records.append(value)
    require(7 <= len(records) <= 64, "initial lifecycle observations are incomplete")
    initial = [("before_snapshot", "none"), ("snapshot_retained", "none")]
    initial += [("initial_image_prepared", role) for role in ("root", "manager", "workload", "recovery")]
    initial += [("initial_roles_ready", "none")]
    for record, (stage, role) in zip(records, initial):
        require((record["stage"], record["role"], record["generation"]) == (stage, role, 0),
                "initial lifecycle or role order differs")
        if role != "none":
            require(record["pid"] == role_pids[role], "sample differs from actual initial Process")
    positions = [record["serial_line_index"] for record in records[:7]]
    require(len(image_indices) == 4 and positions[1] < image_indices[0]
            and all(image_indices[i] < positions[i + 2] for i in range(4))
            and all(positions[i + 2] < image_indices[i + 1] for i in range(3))
            and positions[5] < activation_index < positions[6] < first_owner_event_index,
            "samples do not bracket original image loading and first execution")
    cursor, generation = 7, 0
    while cursor < len(records):
        generation += 1
        if records[cursor]["stage"] == "successor_before_images":
            expected = [("successor_before_images", "none"), ("successor_image_prepared", "manager"),
                        ("successor_image_prepared", "recovery"), ("successor_roles_ready", "none")]
        else:
            expected = [("history_before_image", "none"), ("history_image_prepared", "history"),
                        ("history_role_ready", "none")]
        group = records[cursor:cursor + len(expected)]
        require(len(group) == len(expected), "incomplete successor lifecycle")
        for record, (stage, role) in zip(group, expected):
            require((record["stage"], record["role"], record["generation"]) == (stage, role, generation),
                    "successor lifecycle or generation order differs")
        cursor += len(expected)
    return {"schema": "hepta.original-owner-lifecycle-memory.v1", "samples": records,
            "sampled_min_ordinary_free_bytes": minimum,
            "scope": "finite lifecycle points; approximate ordinary allocator free and slab backing",
            "continuous_peak_verified": False, "global_memory_reserve": False,
            "whole_process_tree_memory_verified": False}
