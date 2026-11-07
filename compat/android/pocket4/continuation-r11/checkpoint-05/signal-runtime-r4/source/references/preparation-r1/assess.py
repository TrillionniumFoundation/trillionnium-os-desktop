"""Pure assessment of frozen owned probes; no device or filesystem actions."""
import json
import re

REQUIRED = {"svc": 0x7e001, "smc-handler": 0x7fffe,
            "smc-default": 0xfc0000, "smc-mask-edit": 0x707fffe}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def read_json(raw):
    return json.loads(raw, object_pairs_hook=unique_object)


def package_identities(raw):
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "strict")
    rows = {}
    for line in raw.splitlines():
        match = re.fullmatch(r"package:([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*) versionCode:(\d+) uid:(\d+)", line)
        need(match is not None, "unparsed package identity")
        name = match[1]
        need(name not in rows, "duplicate package identity")
        rows[name] = {"version_code": int(match[2]), "uid": int(match[3])}
    need(bool(rows), "empty package registry")
    return rows


def instrumentation_document(raw):
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "strict")
    lines = raw.splitlines()
    documents = [line.split("=", 1)[1] for line in lines
                 if line.startswith("INSTRUMENTATION_RESULT: evidence_json=")]
    codes = [line.split(":", 1)[1].strip() for line in lines
             if line.startswith("INSTRUMENTATION_CODE:")]
    need(len(documents) == 1 and len(codes) == 1, "one completed instrumentation result required")
    return read_json(documents[0]), codes[0]


def assess_case(raw_output, final_json, claim_bytes, package, case, nonce, returncode):
    need(case in REQUIRED, "unknown owned case")
    need(returncode == 0, "instrumentation transport did not complete")
    wire, code = instrumentation_document(raw_output)
    final = read_json(final_json)
    need(wire == final, "instrumentation and durable final result differ")
    need(code == "-1" and final.get("phase") == "PASS", "owned case did not pass")
    need(final.get("schema") == 1 and final.get("package") == package and
         final.get("case") == case and final.get("nonce") == nonce, "case/nonce/package binding differs")
    need(final.get("target_sdk") == 33 and final.get("java_process_is_64_bit") is True,
         "wrong probe process profile")
    pid = final.get("java_pid")
    need(type(pid) is int and pid > 1, "invalid owned guest PID")
    expected_claim = ("case=" + case + "\nnonce=" + nonce + "\npid=" + str(pid) + "\n").encode()
    need(claim_bytes == expected_claim, "durable nonce claim does not identify this invocation")
    native = final["native"]
    need(native.get("schema") == 1 and native.get("status") == "PASS" and
         native.get("case") == case and native.get("pid") == pid and
         native.get("guest_isa") == "aarch64", "native result identity differs")
    checks = int(native["checks"], 16)
    required = int(native["required_checks"], 16)
    need(required == REQUIRED[case] and checks & required == required,
         "native required checks are missing or weakened")
    need(native["reason"] == 0 and native["errno"] == 0, "native reason/errno reports failure")
    word = "0xd4000001" if case == "svc" else "0xd4000003"
    need(native["instruction"]["word_before"] == word and
         native["instruction"]["word_after"] == word, "instruction bytes differ")
    signal = native["signal"]
    if case == "svc":
        need(signal["count"] == 0 and signal["precise_siginfo_observed"] is False, "SVC raised a signal")
        need(int(native["after"]["return_value"], 16) == pid, "SVC getpid return differs")
    elif case == "smc-default":
        child = native["child"]
        need(signal["precise_siginfo_observed"] is False, "default control cannot claim precise siginfo")
        need(child["pid"] > 1 and child["pid"] == child["recorded_pid"] and
             child["recorded_ppid"] == pid and child["pdeathsig"] == 9,
             "default child ownership differs")
        need(child["reaped"] is True and child["wait_observed"] is True and
             child["wifsignaled"] is True and child["termination_signal"] == 4 and
             child["timed_out"] is False, "default child did not terminate/reap by SIGILL")
        need(all(int(value, 16) == 0 for value in native["after"].values()),
             "default child partially returned after SMC")
    else:
        need(signal["precise_siginfo_observed"] is True and signal["count"] == 1 and
             signal["unexpected"] == 0 and signal["signo"] == signal["info_signo"] == 4 and
             signal["si_code"] == 1 and signal["si_errno"] == 0, "precise SIGILL identity differs")
        need(signal["si_addr"] == signal["guest_pc"] == native["instruction"]["fault_pc"],
             "SIGILL fault instruction differs")
    if case == "smc-mask-edit":
        edit = native["mask_edit"]
        entered = int(edit["entered_kernel_mask"], 16)
        expected = (entered & ~(1 << 9)) | (1 << 11)
        unblockable = (1 << 8) | (1 << 18)
        need(edit["requested"] is True and int(edit["context_kernel_mask"], 16) == entered,
             "guest ucontext did not preserve interrupted mask")
        need(int(edit["expected_resume_mask"], 16) == expected and
             int(edit["requested_context_mask"], 16) == (expected | unblockable),
             "handler requested mask differs")
        need(edit["live_after_edit_rc"] == 0 and
             edit["live_after_edit"] == signal["handler_kernel_mask"],
             "editing ucontext changed live mask inside handler")
        need(edit["sampled_before_harness_restore"] is True and edit["post_handler_query_rc"] == 0 and
             int(edit["post_handler_kernel_mask"], 16) == expected and expected & unblockable == 0,
             "sigreturn did not apply the edited mask before cleanup")
    return {"status": "PASS", "case": case, "nonce": nonce, "package": package,
            "guest_pid": pid, "checks": native["checks"], "required_checks": native["required_checks"],
            "precise_siginfo_observed": signal["precise_siginfo_observed"],
            "commercial_app_claim": False}
