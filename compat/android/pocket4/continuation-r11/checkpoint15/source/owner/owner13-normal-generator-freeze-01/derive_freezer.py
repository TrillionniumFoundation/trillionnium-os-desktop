#!/usr/bin/env python3
"""Derive the reviewed Owner11 binder; no device or plan execution."""
from pathlib import Path
import ast
import difflib
import hashlib

ROOT = Path(__file__).resolve().parent.parent
old = ROOT / 'owner11-normal01-freeze-01/freeze_normal11.py'
out = ROOT / 'owner13-normal-work-01/freeze_normal13.py'
s = old.read_text()
replacements = [
    ('one fresh real Owner11', 'one fresh real Owner13'),
    ('OLD = BASE / "owner10-normal01-freeze-01"', 'OLD = BASE / "owner11-normal01-freeze-01"'),
    ('HOST_PAIR = BASE / "broker-retirement-cause-source-freeze-01"', 'HOST_PAIR = BASE / "retirement-terminal-drain-source-freeze-13"\nDIAGNOSTIC = BASE / "pinned-io-cause-source-freeze-12"'),
    ('producer11-retirement-controller-freeze-01', 'producer13-retirement-controller-freeze-01'),
    ('OUT = BASE / "owner11-normal01-freeze-01"', 'OUT = BASE / "owner13-normal01-freeze-01"'),
    ('PREFIX = "p4-owner11-normal-20261105-01"', 'PREFIX = "p4-owner13-normal-20261105-01"'),
    ('OLD_PREFIX = "p4-owner10-normal-20261105-01"', 'OLD_PREFIX = "p4-owner11-normal-20261105-01"'),
    ('producer11-retirement-cause01', 'producer13-retirement-terminal-drain01'),
    ('/home/alex/work/pocket4-supervisor-lmkd-cause-r11-build-11-01', '/home/alex/work/pocket4-supervisor-lmkd-drain-r11-build-13-01'),
    ('259154ae622c5c7ae5d29ca11b3a971dfc7e194ae6c9760b3b3de52e0b41a190', 'fab7226afa93d372a7ba7d025cd704ae4aba878f9fa5336490af72eca98e6593'),
    ('{"droidloom-pressure-relay": 30, "droidloom-supervisor": 122}', '{"droidloom-pressure-relay": 37, "droidloom-supervisor": 122}'),
    ('14f87c89b549d8a489ec58e953ac5eb2708857b90772779cc2e79be2e5ad1813', '1cc0ff739afbe642255103e035d1379ac686b77c8b8ac3d1849f56ff984ecb3e'),
    ('owned-real-producer11-normal01-retirement-cause01', 'owned-real-producer13-normal01-terminal-drain01'),
    ('REAL_OWNER_ABI3_RETAINED_CAUSE_FIRST_ACTIVE_ORIGINAL_RETIREMENT', 'REAL_OWNER_ABI3_PINNED_CAUSE_TERMINAL_DRAIN_FIRST_ACTIVE_ORIGINAL_RETIREMENT'),
    ('description="Pocket4 Owner11 ABI3 NORMAL01 "', 'description="Pocket4 Owner13 ABI3 NORMAL01 "'),
    ('61283', '61285'), ('20600000', '20800000'),
    ('root-recovery-20261104-02/evidence/owner10-normal01-runtime-read01/runtime-result.json', 'root-recovery-20261104-02/evidence/owner11-normal01-runtime-read01/runtime-result.json'),
    ('019d04a084f1cc7f028cfefc3277eb51e9dea6a89efc663c52daeff3e14b8190', 'a04dbc0f1073c5ffb5f7fdbd549618af4b316a98688d3ecfe0622d05ef98303d'),
    ('source_freeze = BASE / "owner11-normal-source-freeze-01"', 'source_freeze = BASE / "owner13-normal-source-freeze-01"'),
    ('5a086d10b2db9069ea9210843c27e9caa7bd016665c7ac794efae1a7b9bf8e5c', 'f6e40d2b37bebe430eda08a0ad7aff95cd5917d4431e6c42a10c816d6c78dd41'),
    ('fromfile="normal10-01/source/"', 'fromfile="normal11-01/source/"'),
    ('tofile="normal11-01/source/"', 'tofile="normal13-01/source/"'),
    ('p4-owner11-normal01-prepare01-', 'p4-owner13-normal01-prepare01-'),
    ('p4-owner11-normal01-runtime01-', 'p4-owner13-normal01-runtime01-'),
    ('fromfile="normal10-01/plan.json"', 'fromfile="normal11-01/plan.json"'),
    ('tofile="normal11-01/plan.json"', 'tofile="normal13-01/plan.json"'),
    ('evidence/predecessor-normal10-runtime-failed.json', 'evidence/predecessor-normal11-runtime-failed.json'),
    ('write("freeze_normal11.py"', 'write("freeze_normal13.py"'),
    ('"owner11_normal01_source_binding"', '"owner13_normal01_source_binding"'),
    ('"owner11_normal01_frozen"', '"owner13_normal01_frozen"'),
]
for before, after in replacements:
    assert before in s, before
    s = s.replace(before, after)

start = s.index('    assert previous_audit["retirement_failure"] is None')
end = s.index('    assert plan["broker_bootstrap_source_manifest_sha256"]', start)
s = s[:start] + '''    assert previous_audit["retirement_failure"]["message"] == "rejected: lifecycle bootstrap disconnected"
    assert previous_audit["cleanup_failure"] is not None
    assert previous_audit["first_failure"]["message"] == "owned process generation is dead or changed"
    previous_details = {row["detail"]["event"]: row["detail"] for row in previous_audit["records"]}
    assert len(previous_details) == len(previous_audit["records"]) == 9
    assert list(previous_details) == ["prepared", "owner_attached", "init_hello", "broker_ready",
        "init_project_sent", "init_projected_accepted", "init_commit_sent", "init_done_accepted", "retiring"]
    assert previous_runtime["actor_result"]["latest_status"]["state"] == "cleanup_failed"
    cause_review_path = BASE / "owner11-retirement-cause-actual-review-01/report.json"
    cause_review_raw = cause_review_path.read_bytes()
    assert sha(cause_review_raw) == "79b248d4313baab3843a92e87fa06b61a47f9f7381947b80ea6979c1e96a747d"
    cause_review = json.loads(cause_review_raw)
    assert cause_review["original_runtime"]["sha256"] == sha(predecessor_raw)
    assert cause_review["original_Owner_retirement_completed"] is False
    assert cause_review["specific_relative_name_base_or_role_observed"] is False
    assert cause_review["missing_public_projection_proved"] is False
    assert cause_review["decoded_original_causes"] == {
        "relay_reason": "open relative pinned directory: No such file or directory (os error 2)",
        "lifecycle_error": "rejected: relay service retired; exact old cell requires lifecycle recovery"}
    previous_stderr = (BASE.parent / "root-recovery-20261104-02/evidence/owner11-normal01-logs01/files/evidence/daemon.stderr").read_bytes()
    assert len(previous_stderr) == 2017 and sha(previous_stderr) == "ba0e15b7b1b8992f9fd77169e3f4d17b2687a0aafca9b6d28d2344cfa39dd6c6"
    cause_lines = [line for line in previous_stderr.decode().splitlines()
                   if line.startswith("droidloom-psi-owner: retirement-cause-v1 ")]
    assert len(cause_lines) == 1
    actual_cause = json.loads(cause_lines[0].split("retirement-cause-v1 ", 1)[1])
    assert actual_cause == cause_review["retirement_cause_v1"]
    assert actual_cause["nonce"] == previous_audit["nonce"]
    assert actual_cause["granted"] is False and actual_cause["faulted"] is True
    plan["predecessor_failure"] = {
        "runtime_sha256": sha(predecessor_raw),
        "attempt_nonce": old_plan["attempt_nonce"], "replayed": False,
        "observed_boundary": "actual InitHello, BrokerReady, PROJECTED, COMMIT and DONE; failed before ACTIVE; original retirement incomplete",
        "old_owner_original_resource_retirement_passed": False,
        "old_owner_retirement_error": previous_audit["retirement_failure"]["message"],
        "outer_exact_cleanup_passed": True,
        "generic_pinned_openat_ENOENT_observed": True,
        "specific_relative_name_base_or_role_observed": False,
        "missing_public_projection_proved": False,
        "retirement_cause_review_sha256": sha(cause_review_raw),
        "original_daemon_stderr_sha256": sha(previous_stderr),
        "diagnostic_gap": "exact relative name, held base and validated caller role were omitted; error/process-death ordering is not proved",
        "old_failure_cause_not_inferred_from_blkio_cpuset_or_SIGHUP": True,
    }
''' + s[end:]

start = s.index('    plan["broker_retirement_diagnostic_source_manifest_sha256"] = sha(host_manifest)')
end = s.index('    plan["broker_bootstrap_source_contract"]', start)
s = s[:start] + '''    # Preserve the existing Producer11 diagnostic's own historical contract.
    assert plan["broker_retirement_diagnostic_source_manifest_sha256"] == "259154ae622c5c7ae5d29ca11b3a971dfc7e194ae6c9760b3b3de52e0b41a190"
    assert plan["retirement_diagnostic_contract"] == old_plan["retirement_diagnostic_contract"]
    diagnostic_manifest = (DIAGNOSTIC / "manifest.json").read_bytes()
    assert sha(diagnostic_manifest) == "963f7055854ba25ebc4fb9a9cd2dbf1e59d5a4200363d2fa1222003c341b6bfb"
    for row in json.loads(diagnostic_manifest)["files"]:
        body = (DIAGNOSTIC / row["path"]).read_bytes()
        assert len(body) == row["bytes"] and sha(body) == row["sha256"]
    for relative in ("runtime/droidloom-pressure-relay/src/lib.rs", "runtime/droidloom-pressure-relay/src/lifecycle_relay.rs"):
        assert (HOST_PAIR / "candidate" / relative).read_bytes() == (DIAGNOSTIC / "candidate" / relative).read_bytes()
    plan["pinned_io_diagnostic_source_manifest_sha256"] = sha(diagnostic_manifest)
    plan["pinned_io_diagnostic_contract"] = {
        "scope": "failure-only relative open name/flags/optional held base and validated caller context",
        "original_errno_preserved_before_optional_fstat": True,
        "retry_fallback_or_authority_change": False,
        "diagnostic_itself_qualifies_ACTIVE_or_enrollment": False}
    plan["terminal_drain_source_manifest_sha256"] = sha(host_manifest)
    plan["terminal_drain_contract"] = {
        "scope": "public LifecycleBroker.retire transaction",
        "existing_nonce_scope_AUDIT_status_and_exact_child_exit_required": True,
        "predrain_itself_qualifies_nothing": True,
        "one_request_only_and_original_maximum_two_seconds": True,
        "retirement_error_poison_is_sticky": True,
        "public_receive_progress_independent_error_global_poison_changed": False,
        "old_Owner11_failure_reclassified": False,
        "local_fixture_deterministic_send_race_branch_coverage_claimed": False}
''' + s[end:]
s = s.replace('    write("evidence/predecessor-normal11-runtime-failed.json", predecessor_raw)', '''    write("evidence/predecessor-normal11-runtime-failed.json", predecessor_raw)
    write("evidence/predecessor-normal11-cause-review.json", cause_review_raw)
    write("evidence/predecessor-normal11-daemon.stderr", previous_stderr)''')
s = s.replace('                  "broker_retirement_diagnostic_source_manifest_sha256": sha(host_manifest),', '''                  "pinned_io_diagnostic_source_manifest_sha256": sha(diagnostic_manifest),
                  "terminal_drain_source_manifest_sha256": sha(host_manifest),
                  "old_owner_original_retirement_still_failed": True,
                  "old_external_exact_cleanup_passed": True,''')
start = s.index('    write("README.md", """# Fresh real Owner11')
end = s.index('    rows = []', start)
s = s[:start] + '''    write("README.md", """# Fresh real Owner13 NORMAL01: pinned I/O cause and strict terminal drain

This plan requires the actual successful Producer13 matching compile and ordinary
receipts, including 37 relay / 122 supervisor library tests, two targeted public
retirement controls, seven IPC controls, worker-context and entry ABI3. The original
ABI3 Android DSO, LMKD r6, P4BOOT2/layout3 and cgroup mount mechanism remain fixed.

Diagnostic12 records the original failed relative open name/flags/held base and
validated caller role without retry or relaxed authorization. Combined13 adds
terminal-aware retirement: predrain only feeds the unchanged strict receiver;
a closed send can be discharged only by the complete validated AUDIT/status and
exact child exit. Bare HUP/death cannot qualify, retirement errors stay poisoned,
and the original two-second deadline and one-request contract remain.

Owner11 remains failed before ACTIVE. Its generic pinned-openat ENOENT is retained;
the precise relative path/role and error-versus-death order are not proved. Its
original resource retirement failed; later outer exact cleanup completed. The new
patch does not retroactively mark either the original run or its retirement green.
Blkio/cpuset/SIGHUP and external kernel lines are not used as causal evidence.

The runtime-script changes are only fresh profile/root/unit and labels.
qualify.py, owned.py and pinned_support.py are byte-identical to NORMAL11.
Required scope is actual init HELLO/PROJECTED/COMMIT/DONE, broker ACTIVE, original
public Stop, exact child deaths, joined retirement and domain removal. The typed
HELLO-matching init identity and three clocks remain mandatory.

Outer5GiB/inner4GiB, zero swap, CPU1, original deadlines, native 70/700ms PSI
defaults, one-shot claims, private dbus/sway/presenter, Main fences and exact cleanup
remain unchanged. Fresh UID61285 and subordinate range20800000+100000 must pass
live absence checks. No installed service, account/subid table or host network is
changed. Runtime requires the actual prepared SHA and Root dispatch.

RC/reinit WIP is excluded. Real pressure effects, property reload, installed
lifecycle and all-App readiness remain open. Ordinary controls are not actual
Owner qualification or deterministic coverage of every send-close scheduling race.
""")
''' + s[end:]
ast.parse(s)
compile(s, str(out), 'exec')
with out.open('x') as stream:
    stream.write(s)
delta = out.parent / 'freeze_normal11-to13.diff'
with delta.open('x') as stream:
    stream.write(''.join(difflib.unified_diff(old.read_text().splitlines(True), s.splitlines(True),
                                            fromfile='owner11/freeze_normal11.py', tofile='owner13/freeze_normal13.py')))
for path in (out, delta):
    raw = path.read_bytes()
    print(path, len(raw), hashlib.sha256(raw).hexdigest())
