"""Derive a fresh Owner14 binder; no plan or device execution."""
from pathlib import Path
import ast
import difflib
import hashlib

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / 'owner13-normal-generator-freeze-01/freeze_normal13.py'
OUT = ROOT / 'owner14-normal-work-01/freeze_normal14.py'
s = OLD.read_text()
changes = [
    ('one fresh real Owner13', 'one fresh real Owner14'),
    ('HOST_PAIR = BASE / "retirement-terminal-drain-source-freeze-13"',
     'HOST_PAIR = BASE / "retirement-terminal-drain-source-freeze-13"\nFIXTURE = BASE / "retirement-fixture-repair-source-freeze-14"'),
    ('RUST = BASE / "producer13-retirement-controller-freeze-01"', 'RUST = BASE / "producer14-fixture-controller-freeze-01"'),
    ('OUT = BASE / "owner13-normal01-freeze-01"', 'OUT = BASE / "owner14-normal01-freeze-01"'),
    ('PREFIX = "p4-owner13-normal-20261105-01"', 'PREFIX = "p4-owner14-normal-20261105-01"'),
    ('rb["revision"] == "producer13-retirement-terminal-drain01"', 'rb["revision"] == "producer14-retirement-fixture-repair01"'),
    ('rr["revision"] == "producer13-retirement-terminal-drain01"', 'rr["revision"] == "producer14-retirement-fixture-repair01"'),
    ('/home/alex/work/pocket4-supervisor-lmkd-drain-r11-build-13-01/candidate', '/home/alex/work/pocket4-supervisor-lmkd-fixture-r11-build-14-01/candidate'),
    ('/home/alex/work/pocket4-supervisor-lmkd-drain-r11-build-13-01/target/debug/', '/home/alex/work/pocket4-supervisor-lmkd-fixture-r11-build-14-01/target/debug/'),
    ('owned-real-producer13-normal01-terminal-drain01', 'owned-real-producer14-normal01-fixture-repair01'),
    ('description="Pocket4 Owner13 ABI3 NORMAL01 "', 'description="Pocket4 Owner14 ABI3 NORMAL01 "'),
    ('61285', '61286'), ('20800000', '20900000'),
    ('p4-owner13-normal01-prepare01-', 'p4-owner14-normal01-prepare01-'),
    ('p4-owner13-normal01-runtime01-', 'p4-owner14-normal01-runtime01-'),
    ('tofile="normal13-01/source/"', 'tofile="normal14-01/source/"'),
    ('tofile="normal13-01/plan.json"', 'tofile="normal14-01/plan.json"'),
    ('write("freeze_normal13.py"', 'write("freeze_normal14.py"'),
    ('"owner13_normal01_source_binding"', '"owner14_normal01_source_binding"'),
    ('"owner13_normal01_frozen"', '"owner14_normal01_frozen"'),
]
for old, new in changes:
    assert old in s, old
    s = s.replace(old, new)
old = '''    cfg = json.loads((RUST / "payload.json").read_bytes())
    assert cfg["source_manifest_sha256"] == sha(host_manifest)
    assert cfg["original_diff_sha256"] == sha((HOST_PAIR / "source.diff").read_bytes())
'''
new = '''    fixture_manifest = (FIXTURE / "manifest.json").read_bytes()
    assert sha(fixture_manifest) == "6ae91802b992dba1d48c725e99e51a7daade464f4c5006f78575050f759bcccb"
    for row in json.loads(fixture_manifest)["files"]:
        body = (FIXTURE / row["path"]).read_bytes()
        assert len(body) == row["bytes"] and sha(body) == row["sha256"]
    fixture_paths = {"runtime/droidloom-pressure-relay/src/lib.rs",
                     "runtime/droidloom-pressure-relay/src/lifecycle_bootstrap.rs"}
    for relative in fixture_paths:
        before = (FIXTURE / "preimage" / relative).read_bytes()
        after = (FIXTURE / "candidate" / relative).read_bytes()
        assert before == (HOST_PAIR / "candidate" / relative).read_bytes()
        marker = b"#[cfg(test)]\\nmod tests {"
        assert before.count(marker) == after.count(marker) == 1
        assert before.split(marker, 1)[0] == after.split(marker, 1)[0]
    cfg = json.loads((RUST / "payload.json").read_bytes())
    assert cfg["source_manifest_sha256"] == sha(fixture_manifest)
    assert cfg["original_diff_sha256"] == sha((FIXTURE / "source.diff").read_bytes())
    assert set(cfg["overlays"]) == fixture_paths
    for relative, row in cfg["overlays"].items():
        assert row["text"].encode() == (FIXTURE / "candidate" / relative).read_bytes()
'''
assert s.count(old) == 1
s = s.replace(old, new)
anchor = '    plan["broker_bootstrap_source_contract"] = '
point = s.index(anchor)
s = s[:point] + '''    prior_ordinary_raw = (FIXTURE / "evidence/actual-producer13-ordinary-failed.json").read_bytes()
    assert sha(prior_ordinary_raw) == "cc26182f01c5241d6766dfb356263fa6efc7b6499a05684e0447895935ad523e"
    prior_ordinary = json.loads(prior_ordinary_raw)
    assert prior_ordinary["success"] is False and len(prior_ordinary["commands"]) == 3
    assert [row["returncode"] for row in prior_ordinary["commands"]] == [0, 0, 101]
    assert prior_ordinary["external_compile_sha256"] == "9a2cf0087ff99b6834fc2b3a963e03629a14acc21af1a8d67f2b5081bbb22e8e"
    prior_stdout = (FIXTURE / "evidence/actual-producer13-relay-command.stdout").read_bytes()
    assert len(prior_stdout) == 4483 and sha(prior_stdout) == "8a8537257b6bea7e1ca04031cf7d5f40143812cd71e6f7d1fdfd5082e911d528"
    assert prior_ordinary["commands"][2]["stdout_pin"]["sha256"] == sha(prior_stdout)
    assert "test result: FAILED. 35 passed; 2 failed;" in prior_stdout.decode()
    plan["fixture_repair_source_manifest_sha256"] = sha(fixture_manifest)
    plan["fixture_repair_contract"] = {
        "production_prefixes_unchanged_from13": True,
        "only_two_test_fixtures_changed": True,
        "faulted_requires_incomplete_codec_not_changed": True,
        "dead_held_proc_errno_compared_with_raw_syscall": True,
        "prior_ordinary_failure_preserved": True,
        "prior_ordinary_receipt_sha256": sha(prior_ordinary_raw),
        "prior_relay_stdout_sha256": sha(prior_stdout),
        "prior_relay_passed": 35, "prior_relay_failed": 2,
        "prior_supervisor_IPC_executed": False,
        "NORMAL13_never_prepared_or_executed": True}
''' + s[point:]
start = s.index('    controls_raw = (WORK / "new-profile-controls.json").read_bytes()')
end = s.index('    payload = {}; source_diff = ""', start)
s = s[:start] + '''    source_freeze = BASE / "owner14-normal-source-freeze-01"
    assert sha((source_freeze / "manifest.json").read_bytes()) == "e2ae7182ce3d2bcd8c8aae249efd536999a9082c65d84ff8cf23cecb68e8b81b"
    for row in json.loads((source_freeze / "manifest.json").read_bytes())["files"]:
        raw = (source_freeze / row["path"]).read_bytes()
        assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
    controls_raw = (source_freeze / "source-review.json").read_bytes()
    controls = json.loads(controls_raw)
    assert controls["actual_runtime_executed"] is False and controls["plan_generated"] is False
    assert controls["fixed_profile_controls"] == [
        {"case": "new_profile", "accepted": True}, {"case": "new_paths", "accepted": True},
        {"case": "old_kind_rejected", "accepted": False}, {"case": "short_nonce_rejected", "accepted": False},
        {"case": "old_scope_rejected", "accepted": False}, {"case": "old_unit_rejected", "accepted": False},
        {"case": "old_package_rejected", "accepted": False}, {"case": "old_state_rejected", "accepted": False}]
    # Only profile literals changed. Retain the earlier source-level init
    # observation controls without claiming an additional execution of them.
    observer_base = BASE / "owner13-normal-source-freeze-01"
    observer_raw = (observer_base / "init-observation-controls.json").read_bytes()
    observer = json.loads(observer_raw)
    assert observer["success"] is True and observer["passed"] == 11
    for name, digest in observer["pins"].items():
        assert sha((observer_base / "source" / name).read_bytes()) == digest
    def function_ast(path, name):
        return ast.dump(next(n for n in ast.parse(path.read_text()).body
                             if isinstance(n, ast.FunctionDef) and n.name == name))
    assert function_ast(observer_base / "source/actor.py", "observe_init_hello") == function_ast(source_freeze / "source/actor.py", "observe_init_hello")
    assert (observer_base / "source/qualify.py").read_bytes() == (source_freeze / "source/qualify.py").read_bytes()
''' + s[end:]
s = s.replace('for path in sorted((WORK / "source").glob("*.py")):',
              'for path in sorted((source_freeze / "source").glob("*.py")):')
old = '''    write("new-profile-controls.json", controls_raw)
    write("check_new_profile.py", (WORK / "check_new_profile.py").read_bytes())
    write("check_init_observation.py", (WORK / "check_init_observation.py").read_bytes())
    write("init-observation-controls.json", observer_raw)
'''
new = '''    write("source-profile-review.json", controls_raw)
    write("derive_sources14.py", (source_freeze / "derive_sources14.py").read_bytes())
    write("evidence/prior-init-observation-controls.json", observer_raw)
    write("evidence/producer13-ordinary-failed.json", prior_ordinary_raw)
    write("evidence/producer13-relay-command.stdout", prior_stdout)
'''
assert s.count(old) == 1
s = s.replace(old, new)
s = s.replace('"new_ABI_and_profile_controls_passed": 19,',
              '"new_profile_controls_passed": 8, "init_observation_controls_retained_not_rerun": 11,')
s = s.replace('"terminal_drain_source_manifest_sha256": sha(host_manifest),\n                  "old_owner',
              '"terminal_drain_source_manifest_sha256": sha(host_manifest),\n                  "fixture_repair_source_manifest_sha256": sha(fixture_manifest),\n                  "producer13_ordinary_failure_still_preserved": True,\n                  "old_owner')
s = s.replace('# Fresh real Owner13 NORMAL01:', '# Fresh real Owner14 NORMAL01:')
s = s.replace('actual successful Producer13 matching compile and ordinary',
              'actual successful Producer14 matching compile and ordinary')
needle = '''the original two-second deadline and one-request contract remain.
'''
assert s.count(needle) == 1
s = s.replace(needle, needle + '''
Producer14 changes only two test fixtures after the original producer13 ordinary
run failed 35/37 relay tests. That failure remains fixed evidence; its supervisor
and IPC stages did not run. Production13 diagnostics and retirement remain
unchanged. No NORMAL13 prepare or runtime was executed. The new expected suite
must actually pass before this plan can be created.
''')
ast.parse(s)
compile(s, str(OUT), 'exec')
with OUT.open('x') as stream:
    stream.write(s)
delta = OUT.parent / 'freeze_normal13-to14.diff'
with delta.open('x') as stream:
    stream.write(''.join(difflib.unified_diff(OLD.read_text().splitlines(True), s.splitlines(True),
        fromfile='owner13/freeze_normal13.py', tofile='owner14/freeze_normal14.py')))
for p in (OUT, delta):
    b = p.read_bytes()
    print(p, len(b), hashlib.sha256(b).hexdigest())
