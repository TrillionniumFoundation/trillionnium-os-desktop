#!/usr/bin/env python3
"""Check a frozen three-policy measurement contract; never execute an effect.

This is preparation for an actual collector/runner. A JSON contract passing is
not native execution, owner authentication, or permission to rank performance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ARMS = ("fixed", "feedback", "hepta")
STATES = ("cold", "warm")
POLICY_RULES = {"interval_ns": 1_000_000_000, "maximum_age_ns": 2_000_000_000,
                "slew_denominator": 10, "same_direction_samples": 2}
CPU_PARTS = ("workload", "policy", "observation", "install", "recovery", "local_inference")
MAX_JSON = 16 * 1024 * 1024
U64 = (1 << 64) - 1
RUNTIME_BLOCKERS = (
    "original-owner three-policy executable and final-consumer freshness gate are not wired",
    "native demand/cost collector with replayable raw measurement verification is not implemented",
    "actual Hepta controller/model profile and its full inference-cost measurements are not supplied",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pairs(items):
    value = {}
    for key, item in items:
        require(key not in value, "duplicate JSON key: " + key)
        value[key] = item
    return value


def read_json(path):
    with Path(path).open("rb") as source:
        raw = source.read(MAX_JSON + 1)
    require(len(raw) <= MAX_JSON, "JSON input exceeds 16 MiB")
    def bad_constant(value):
        raise ValueError("non-finite JSON number: " + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(value, name):
    require(type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None,
            name + " must be an explicit SHA-256")
    return value


def integer(value, name, low=0, high=U64):
    require(type(value) is int and low <= value <= high, name + " must be an exact bounded integer")
    return value


def label(value, name):
    require(type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}", value),
            name + " must be a bounded label")
    return value


def object_(value, name):
    require(type(value) is dict, name + " is missing or is not an object")
    return value


def source(value, name):
    object_(value, name)
    for field in ("head", "tree"):
        require(type(value.get(field)) is str and re.fullmatch("[0-9a-f]{40}", value[field]),
                name + "." + field + " must be a frozen Git object")


def artifact(root, value, name, limit=64 * 1024 * 1024):
    """Check retained bytes, without interpreting a hash as authenticity."""
    object_(value, name)
    relative = Path(value["path"])
    require(not relative.is_absolute() and relative.parts and ".." not in relative.parts,
            name + " must use a contained relative path")
    base = Path(root).resolve(strict=True)
    path = base
    for part in relative.parts:
        path = path / part
        require(not path.is_symlink(), name + " cannot traverse a symlink")
    require(path.is_file() and path.resolve().is_relative_to(base), name + " is not a retained file")
    size = integer(value["bytes"], name + " bytes", 1, limit)
    require(path.stat().st_size == size, name + " size changed")
    sha(value["sha256"], name + " sha256")
    require(hashlib.sha256(path.read_bytes()).hexdigest() == value["sha256"], name + " bytes changed")


def validate_plan(plan):
    object_(plan, "plan")
    require(plan.get("schema") == "hepta.cpu-three-policy-plan.v1", "unsupported plan schema")
    label(plan.get("experiment_id"), "experiment_id")
    common = object_(plan.get("common"), "common inputs")
    for repository in ("desktop", "hepta"):
        source(common["sources"][repository], repository)
    workload = object_(common.get("workload"), "workload")
    for field in ("code_sha256", "data_sha256"):
        sha(workload.get(field), "workload." + field)
    tasks = workload.get("task_ids")
    require(type(tasks) is list and 1 <= len(tasks) <= 4096, "workload task denominator is missing")
    for task in tasks:
        label(task, "task_id")
    require(len(set(tasks)) == len(tasks), "workload task IDs repeat")
    native = object_(common.get("native"), "native inputs")
    require(native.get("mode") == "native-control" and native.get("cpu_profile") == "N0-single-cpu",
            "this experiment requires the original N0 profile; SMP2/Linux are separate comparisons")
    for field in ("kernel_sha256", "rootfs_sha256"):
        sha(native.get(field), "native." + field)
    budget = object_(common.get("budget"), "resource envelope")
    require(type(budget.get("period_ns")) is int and budget["period_ns"] == 100_000_000,
            "original HOS2 period differs")
    maximum = integer(budget.get("maximum_cap_ns"), "maximum cap", 10, budget["period_ns"])
    integer(budget.get("initial_cap_ns"), "initial cap", 0, maximum)
    integer(budget.get("local_cpu_cores"), "whole-arm host CPU ceiling", 1, 256)
    integer(budget.get("local_memory_bytes"), "whole-arm memory ceiling", 1)
    sha(budget.get("external_envelope_sha256"), "external/no-external resource ceiling declaration")
    faults = object_(common.get("faults"), "faults")
    label(faults.get("profile"), "fault profile")
    sha(faults.get("schedule_sha256"), "fault schedule")
    environment = object_(common.get("environment"), "environment")
    for field in ("hardware_sha256", "background_sha256"):
        sha(environment.get(field), field)
    lo = integer(environment.get("min_temperature_millicelsius"), "temperature minimum", -100_000, 200_000)
    integer(environment.get("max_temperature_millicelsius"), "temperature maximum", lo, 200_000)
    collector = object_(common.get("collector"), "collector")
    sha(collector.get("source_sha256"), "actual collector source")
    require(collector.get("clock") == "continuous-observer-monotonic-ns",
            "elapsed time needs one continuous independent observer across guest/owner restarts")
    require(collector.get("scope") == "whole-arm-local-and-external",
            "all workload, control, inference, observation, install and recovery costs are required")
    policies = object_(plan.get("policies"), "three policies")
    require(set(policies) == set(ARMS), "fixed, feedback and actual Hepta arms are all required")
    for arm in ARMS:
        policy = object_(policies[arm], arm)
        sha(policy.get("source_sha256"), arm + " actual algorithm source")
        sha(policy.get("entry_elf_sha256"), arm + " original-owner executable")
        sha(policy.get("configuration_sha256"), arm + " frozen configuration")
        require(policy.get("effect_path") == "original-writer/grant-provider/ProductionHos2Target",
                arm + " must use the original effect path")
        require(policy.get("rules") == POLICY_RULES, arm + " differs from the common bounded policy rules")
        require(policy.get("inference_location") in ("none", "local", "external"), arm + " inference location missing")
        if arm == "fixed":
            integer(policy.get("target_cap_ns"), "fixed target", 0, maximum)
        if arm != "hepta":
            require(policy["inference_location"] == "none", "non-AI baselines cannot hide model calls")
        else:
            require(policy["inference_location"] != "none", "the third arm needs actual Hepta inference")
            sha(policy.get("model_configuration_sha256"), "actual Hepta/model configuration")
    rounds = object_(plan.get("rounds"), "rounds")
    integer(rounds.get("count"), "predeclared repeats", 1, 1000)
    integer(rounds.get("seed"), "predeclared order seed")
    require(rounds.get("states") == list(STATES), "cold and warm trials must remain separate")


def schedule(plan):
    """Frozen SHA-256 ordering; no post-result choice or Python RNG dependency."""
    result = []
    for state in STATES:
        for repetition in range(plan["rounds"]["count"]):
            ordered = sorted(ARMS, key=lambda arm: digest([plan["rounds"]["seed"], state, repetition, arm]))
            result.extend({"trial_id": f"{state}/{repetition}/{arm}", "state": state,
                           "repetition": repetition, "arm": arm} for arm in ordered)
    return result


def energy(value, name):
    object_(value, name)
    integer(value.get("microjoules"), name + " measured energy")
    require(value.get("attribution") == "exclusive-trial-system",
            name + ": shared/package RAPL or estimated per-task attribution cannot rank energy")
    sha(value.get("meter_profile_sha256"), name + " meter and exclusive-domain evidence")


def validate_trial(plan, expected, trial):
    object_(trial, "trial")
    require(trial.get("schema") == "hepta.cpu-policy-trial.v1", "unsupported trial schema")
    require(all(type(trial.get(key)) is type(value) and trial.get(key) == value for key, value in expected.items()),
            "trial ID/arm/state/repetition differs")
    require(trial.get("plan_sha256") == digest(plan), "trial used another frozen plan")
    common = plan["common"]
    policy = plan["policies"][expected["arm"]]
    require(trial.get("common_sha256") == digest(common) and trial.get("budget") == common["budget"],
            "workload/kernel/fault/environment/source or budget drift")
    require(trial.get("policy_sha256") == digest(policy), "policy source/configuration drift")
    begin = integer(trial.get("started_ns"), "trial start")
    end = integer(trial.get("ended_ns"), "trial end", begin + 1)
    environment = common["environment"]
    for field in ("temperature_before_millicelsius", "temperature_after_millicelsius"):
        integer(trial.get(field), field, environment["min_temperature_millicelsius"],
                environment["max_temperature_millicelsius"])
    tasks = trial.get("tasks")
    require(type(tasks) is list and len(tasks) == len(common["workload"]["task_ids"]),
            "task denominator lost failures/timeouts or added tasks")
    seen = set()
    for task in tasks:
        object_(task, "task")
        task_id = task.get("task_id")
        require(task_id in common["workload"]["task_ids"] and task_id not in seen, "task ID missing/duplicate/foreign")
        seen.add(task_id)
        require(task.get("status") in ("success", "failure", "timeout"), "skipped/unsupported work cannot become a complete trial")
        start = integer(task.get("started_ns"), "task start", begin, end)
        integer(task.get("ended_ns"), "task terminal/censoring time", start, end)
        sha(task.get("completion_evidence_sha256"), "actual completion/failure/timeout observation")
    costs = object_(trial.get("costs"), "whole-arm costs")
    cpu = object_(costs.get("local_cpu_ns"), "local CPU")
    require(set(cpu) == set(CPU_PARTS), "CPU costs must be disjoint complete categories, including inference")
    for name in CPU_PARTS:
        integer(cpu[name], "CPU " + name)
    if policy["inference_location"] != "local":
        require(cpu["local_inference"] == 0, "local inference contradicts the frozen inference location")
    peak = object_(costs.get("local_memory"), "local memory")
    require(peak.get("scope") == "owned-subtree-peak", "one-process RSS is not whole-subtree peak memory")
    integer(peak.get("peak_bytes"), "local peak memory", 1, common["budget"]["local_memory_bytes"])
    energy(costs.get("local_energy"), "local energy")
    external = costs.get("external_inference")
    if policy["inference_location"] == "external":
        object_(external, "external inference costs (unknown is not zero)")
        integer(external.get("cpu_ns"), "external inference CPU")
        integer(external.get("peak_bytes"), "external inference memory", 1)
        energy(external.get("energy"), "external inference energy")
        sha(external.get("provider_measurement_sha256"), "provider attributable measurements")
    else:
        require(external is None, "no-external arm cannot silently change the inference location")
    recovery = object_(costs.get("recovery"), "recovery costs")
    require(recovery.get("status") in ("not-needed", "recovered", "failed"), "recovery status missing")
    integer(recovery.get("elapsed_ns"), "recovery elapsed/censored time", 0, end - begin)
    integer(recovery.get("lost_work_units"), "observed lost work")
    if common["faults"]["profile"] == "none":
        require(recovery["status"] == "not-needed", "unexpected fault changes the common experiment")
    else:
        require(recovery["status"] != "not-needed", "planned fault and recovery observation missing")
    sha(trial.get("raw_measurement_sha256"), "raw collector record")
    sha(trial.get("original_owner_evidence_sha256"), "original K/D/effect evidence")


def assess(plan, trials):
    """Contract checks only. No self-reported passed flag can admit a runtime."""
    errors, counts = [], {}
    try:
        validate_plan(plan)
        require(type(trials) is list, "trials must be a list")
        expected = schedule(plan)
        require(len(trials) == len(expected), "all predeclared trials of all three arms are required")
        previous_end, raw_records = 0, set()
        # Retain actual randomized order; sorting partial results cannot hide selection.
        for item, trial in zip(expected, trials):
            try:
                validate_trial(plan, item, trial)
                require(trial["started_ns"] >= previous_end, "trials overlap or independent-observer time regressed")
                require(trial["raw_measurement_sha256"] not in raw_records, "one raw trial record was reused as another repetition/arm")
                previous_end = trial["ended_ns"]
                raw_records.add(trial["raw_measurement_sha256"])
            except (ValueError, TypeError, KeyError) as error:
                errors.append(item["trial_id"] + ": " + str(error))
        if not errors:
            for arm in ARMS:
                counts[arm] = {status: sum(task["status"] == status for trial in trials
                                           if trial["arm"] == arm for task in trial["tasks"])
                              for status in ("success", "failure", "timeout")}
    except (ValueError, TypeError, KeyError) as error:
        errors.append(str(error))
    return {"schema": "hepta.cpu-three-policy-contract-result.v1", "plan_sha256": digest(plan),
            "contract_complete": not errors, "contract_errors": errors, "reported_denominators": counts,
            "native_measurements_verified": False, "comparison_complete": False,
            "ranking_allowed": False, "benefit_claim": None, "runtime_blockers": list(RUNTIME_BLOCKERS),
            "scope": "input/measurement contract only; not execution or remote attestation"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--trials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = assess(read_json(args.plan), read_json(args.trials))
    except (OSError, ValueError, TypeError) as error:
        result = {"contract_complete": False, "comparison_complete": False, "ranking_allowed": False,
                  "error": str(error), "runtime_blockers": list(RUNTIME_BLOCKERS)}
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))
    # Even a complete contract must not be mistaken for an actual comparison pass.
    return 2


if __name__ == "__main__":
    sys.exit(main())
