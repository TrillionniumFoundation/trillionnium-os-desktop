#!/usr/bin/env python3
"""Derive only local BestBuy source from exact IHG actual-built inputs."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import types
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
BASE = WORK / 'owned-ihg-qa-r1-build01'
SOURCE = HERE / 'source'
REFERENCE = HERE / 'references'
BASE_SHA = 'ab971f5b361f1d97b8036c954a6b88734b7faedbeed6349b873ead85fa79d5f3'
MAPPING = [
    ('com\\\\.ihg\\\\.apps\\\\.android', 'com\\\\.bestbuy\\\\.android'),
    ('com\\.ihg\\.apps\\.android', 'com\\.bestbuy\\.android'),
    ('com.ihg.apps.android', 'com.bestbuy.android'),
    ('org/droidloom/qa/ihg/r1', 'org/droidloom/qa/bestbuy/r1'),
    ('org.droidloom.qa.ihg.r1', 'org.droidloom.qa.bestbuy.r1'),
    ('pocket4-owned-ihg-qa-v1', 'pocket4-owned-bestbuy-qa-v1'),
    ('owned-ihg-qa', 'owned-bestbuy-qa'),
    ('owned_ihg_qa', 'owned_bestbuy_qa'),
    ('Owned IHG QA', 'Owned BestBuy QA'),
    ('IHG', 'BESTBUY'),
    ('10137', '10130'),
]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()


def write(path, value):
    raw = value if isinstance(value, bytes) else value.encode() if isinstance(value, str) else encode(value)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.open('xb').write(raw)


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': sha(raw)}


def checked(path, size, digest):
    raw = path.read_bytes()
    assert len(raw) == size and sha(raw) == digest, path
    return raw


def load(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def literal(text):
    for old, new in MAPPING:
        text = text.replace(old, new)
    return text


def main():
    assert not SOURCE.exists() and not REFERENCE.exists()
    baseline_raw = checked(BASE / 'source/SOURCE_PINS.json', 1457, BASE_SHA)
    baseline = json.loads(baseline_raw)
    assert len(baseline['files']) == 10
    for name, row in baseline['files'].items():
        checked(BASE / 'source' / name, row['bytes'], row['sha256'])
    actual_dir = WORK / 'root-recovery-20261104-02/evidence/ihg-r1-static-build01'
    build_raw = checked(actual_dir / 'build-result.json', 17246,
        '26a45b337c5dad2bd98b18ce093b321b8c0805de7cb9d759d5dd4088be05a053')
    stage_raw = checked(actual_dir / 'stage-result.json', 1935,
        '94bfea341c50b648a2da13752044434cff04e74b7e7549c0d0e0b10c2ce77c41')
    build, stage = json.loads(build_raw), json.loads(stage_raw)
    adapter = load(BASE / 'source/qa_adapter.py', 'actual_ihg_adapter')
    builder = load(BASE / 'source/build_candidate.py', 'actual_ihg_builder')
    manifest = adapter.own_source(BASE_SHA)
    args = SimpleNamespace(build_receipt=actual_dir / 'build-result.json',
        build_receipt_sha256=sha(build_raw), source_manifest_sha256=BASE_SHA,
        apk_sha256=build['APK']['sha256'], signer_certificate_sha256=build['signer_certificate_sha256'])
    adapter.qualified_build(args, manifest, builder)
    assert stage['state'] == 'OWNED_QA_APK_STATIC_BUILD_PASS_ANDROID_UNRUN'
    assert stage['build_returncode'] == 0 and stage['error'] is None and stage['secondary_errors'] == []
    assert stage['build_result'] == {'path': '/home/alex/work/pocket4-owned-ihg-qa-r1-build-01/build-result.json',
        'bytes': len(build_raw), 'sha256': sha(build_raw)}
    helper_install_raw = checked(WORK / 'root-recovery-20261104-02/evidence/ihg-r1-install-read01/worker.json',
        11213, '2e62018b086bb5484648d07867e73a3b11efbbd3490aeb3f190d1bb24afe4179')
    helper_install = json.loads(helper_install_raw)
    assert helper_install['owned_package_uid'] == 10196 and helper_install['package'] == 'org.droidloom.qa.ihg.r1'
    assert helper_install['ok'] is True and helper_install['install_success_observed'] is True

    current = WORK / 'root-recovery-20261104-02/evidence/bestbuy-artifact-launcher-readonly01'
    worker_raw = checked(current / 'worker.reconstructed-from-actual-stdout.json', 10112,
        'bd394cac42b9ab536c3646c4c6e5c6e755658855c1a4525aa26b9b73cf80f073')
    read_stage_raw = checked(current / 'stage.reconstructed-from-actual-stdout.json', 1587,
        '424b8f32a7375b31928947b7d870d83bcc4848dc00e3d2fe4493a99aea165ecb')
    stdout_raw = checked(current / 'stdout.log', 9882,
        'b0934fb83617853f4cf34731ce5c570854a444e625d20a7c4f067352c0285f2c')
    worker, read_stage = json.loads(worker_raw), json.loads(read_stage_raw)
    lines = [json.loads(line) for line in stdout_raw.splitlines()]
    assert len(lines) == 2 and lines[0]['result'] == worker and lines[1]['stage'] == read_stage
    assert lines[0]['result_file']['bytes'] == len(worker_raw) and lines[0]['result_file']['sha256'] == sha(worker_raw)
    assert lines[1]['stage_result']['bytes'] == len(read_stage_raw) and lines[1]['stage_result']['sha256'] == sha(read_stage_raw)
    meta = {'package':'com.bestbuy.android','uid':10130,'user':0,'version_code':2012312321}
    assert worker['metadata_before'] == worker['metadata_after'] == meta
    assert worker['ok'] is True and worker['error'] is None and worker['secondary_errors'] == []
    assert worker['Main_before'] == worker['Main_after'] and worker['final_Main_guard_passed'] is True
    assert worker['Main_before']['resource_limits_match'] is True and worker['Main_before']['three_host_processes_match'] is True
    assert worker['held_binding_released'] is True and worker['action_lock_released'] is True
    assert worker['UI_actions'] == worker['App_launches'] == worker['instrumentation_calls'] == 0
    assert worker['signer_certificate_independently_verified'] is False
    assert worker['shared_helper']['whole_process_tree_cleanup_qualified'] is False
    assert worker['whole_app_production_ready'] is False
    rows = worker['command_observations']
    assert len(rows) == worker['package_read_commands_completed'] == 5
    assert all(row['returncode'] == 0 and row['joined'] is True and row['spawned'] is True and
        row['first_error'] is None and row['secondary_errors'] == [] and row['recorder_errors'] == [] and
        row['stderr_bytes'] == 0 and row['host_timed_out'] is False and row['Android_UI_action'] is False for row in rows)
    artifacts = worker['artifacts']
    expected = [
        ('base.apk',149277165,'74ff0f36a2fed0693960af8ec13ae18bef976b51df1433eec15ca195002339b3'),
        ('split_config.arm64_v8a.apk',93486949,'ee64286a30d9127fc74deb734f66aaa67c2d4f0ca168138977378719fe01c5a3'),
        ('split_config.xxhdpi.apk',2747579,'2b1574c80ab02b450ac2370067dc9bcfb828dcf1c3af8fb9d60f197d456f8f67'),
    ]
    assert len(artifacts) == 3 and [x['path'] for x in artifacts] == worker['apk_paths_before']
    assert [(Path(x['path']).name,x['held_file']['bytes'],x['sha256']) for x in artifacts] == expected
    assert sum(x['held_file']['bytes'] for x in artifacts) == worker['total_apk_bytes'] == 245511693
    assert worker['launcher_resolution']['component'] == 'com.bestbuy.android/.activity.SplashActivity'
    assert worker['launcher_resolution']['later_launch_requires_new_current_binding'] is True
    assert worker['launcher_resolution']['launch_performed'] is False

    SOURCE.mkdir(mode=0o700)
    REFERENCE.mkdir(mode=0o700)
    for name, raw in (
        ('prior-IHG-SOURCE_PINS.json', baseline_raw), ('actual-IHG-build-result.json', build_raw),
        ('actual-IHG-stage-result.json', stage_raw), ('bestbuy-worker-reconstructed.json', worker_raw),
        ('bestbuy-stage-reconstructed.json', read_stage_raw), ('bestbuy-readonly-actual.stdout', stdout_raw),
        ('actual-bili-r5-manifest.stdout', checked(BASE/'references/actual-bili-r5-manifest.stdout',
             (BASE/'references/actual-bili-r5-manifest.stdout').stat().st_size,
             '825a53459b0fc3406d328aad3350624f9b658b150a2fbf56f3a908f46de4185d')),
    ):
        write(REFERENCE / name, raw)

    original_text = {}
    derived_text = {}
    substitution_counts = {}
    residual = []
    python_changes = {}
    runtime_names = [n for n in baseline['files'] if n.endswith(('.py','.java','.xml'))]
    assert len(runtime_names) == 7
    for old_name in runtime_names:
        raw = (BASE / 'source' / old_name).read_bytes()
        old = raw.decode()
        new_name = literal(old_name)
        derived = old
        counts = {}
        for before, after in MAPPING:
            count = derived.count(before)
            if count:
                counts[before] = count
                derived = derived.replace(before, after)
        new = derived
        if old_name == 'qa_adapter.py':
            old_gate = '(10130,10121,10129,10117,10125,10164,10165,10166,10169,10170,10175,10184,10190)'
            assert new.count(old_gate) == 1
            new = new.replace(old_gate,old_gate[:-1]+',10137,10196)')
        elif old_name == 'qa_contract.py':
            old_gate = '(UID, 10121, 10129, 10117, 10125, 10164, 10165, 10166, 10169, 10170, 10175, 10184, 10190)'
            assert new.count(old_gate) == 1
            new = new.replace(old_gate,old_gate[:-1]+', 10137, 10196)')
        write(SOURCE / new_name, new)
        original_text[old_name] = old
        derived_text[new_name] = new
        substitution_counts[new_name] = counts
        residual.extend(difflib.unified_diff(derived.splitlines(True),new.splitlines(True),
            fromfile='fully-literal-derived/'+new_name,tofile='BestBuy/'+new_name))
        if old_name.endswith('.py'):
            a = ast.parse(derived); b = ast.parse(new)
            na = {getattr(n,'name',f'body_{i}'):ast.dump(n,include_attributes=False) for i,n in enumerate(a.body)}
            nb = {getattr(n,'name',f'body_{i}'):ast.dump(n,include_attributes=False) for i,n in enumerate(b.body)}
            assert set(na) == set(nb)
            python_changes[new_name] = [k for k in na if na[k] != nb[k]]
    assert python_changes == {'build_candidate.py':[], 'make_build_request.py':[],
        'qa_adapter.py':['Session'], 'qa_contract.py':['parse_completed'], 'stage_build.py':[]}
    assert derived_text['src/org/droidloom/qa/bestbuy/r1/ActionRunner.java'] == literal(original_text['src/org/droidloom/qa/ihg/r1/ActionRunner.java'])

    inputs = json.loads((BASE / 'source/build-input-reference.json').read_bytes())
    inputs['artifact'] = 'owned-bestbuy-qa-r1-pinned-tool-reference'
    inputs['IHG_build_qualification_inherited'] = False
    inputs['BestBuy_build_qualification_from_prior_receipts'] = False
    inputs['actual_IHG_r1_build_reference'] = {'bytes':len(build_raw),'sha256':sha(build_raw),
        'not_BestBuy_build_qualification':True,'tool_table_reused_without_changes':True}
    assert inputs['new_helper_compilation_performed'] is False
    write(SOURCE / 'build-input-reference.json', inputs)
    write(SOURCE / 'target-artifact-reference.json', {'schema':1,**meta,
        'actual_read_job':'1a1adfbdc24-fc05-5c5b','actual_read_result':{'bytes':len(worker_raw),'sha256':sha(worker_raw)},
        'actual_read_stage':{'bytes':len(read_stage_raw),'sha256':sha(read_stage_raw)},
        'actual_read_stdout':{'bytes':len(stdout_raw),'sha256':sha(stdout_raw)},
        'data_source':'Exact original full stdout reconstructed with original JSON writer shape; both result/stage emitted hashes matched. Not a second held remote file read.',
        'current_artifacts':artifacts,'current_APK_count':3,'current_total_APK_bytes':245511693,
        'current_launcher':worker['launcher_resolution'],'fresh_runtime_identity_revalidation_required':True,
        'fresh_launcher_resolution_before_any_future_launch_required':True,
        'commercial_signer_qualification':False,'helper_UID':None,'helper_APK':None,'helper_signer':None,
        'shared_helper_whole_process_tree_cleanup_qualified':False,'whole_app_production_ready':False})
    write(SOURCE / 'README.md', '''# Owned BestBuy QA helper R1: build-only candidate

The new self-instrumented package is org.droidloom.qa.bestbuy.r1. It binds only
com.bestbuy.android UID 10130 on user/display 0 and the pinned Main epoch.
The current read-only receipt observed version 2012312321, three exact APKs
totalling 245,511,693 bytes, and com.bestbuy.android/.activity.SplashActivity.
All base and split paths, hashes and held-file metadata are bound in the source
reference. These observations become historical inputs at runtime: the complete
artifact chain, target identity and launcher require fresh checks before launch.
Commercial signer qualification remains false.

This source derives from the actually built IHG R1 helper. Only target/self
package, UID, protocol, escaped scope/resource regex, labels, source/output paths
and known-prior-UID exclusions change. The exact original UiAutomation readiness
and cache policy, complete tree/window identity, fresh node validation and state
restoration remain. The manifest has no permissions, activities, services,
receivers or providers; instrumentation targets only self. Java and Python admit
state, inspect and source-bound ACTION_CLICK only. Inherited text code remains
unreachable. This build includes no click plan or UI authority.

No BestBuy helper installation, UID, APK hash or signer is assumed. A new real
11-command build must verify its signed bytes, self manifest, seven pinned tools
and output receipts before separate install/state admission. Prior IHG commercial
UID 10137 and actual IHG helper UID 10196 are additionally excluded from candidate
helper identity. Prior build, install and launch qualification never transfers to
BestBuy. The standalone adapter stays denied; a dedicated BestBuy held Main
artifact/task adapter and exact-owned-task cleanup must be separately bound.

The existing SDK31 / min31 / target33 build, 1 CPU, 512 MiB, swap0, 128 tasks,
create-only roots, joined-child/first-error handling and final input hashes are
unchanged. Local predicate controls do not qualify Java compilation or Android
behavior. No commercial UI tree, pixels, APK or private signing material is
included. Whole-app production readiness remains unqualified.
''')
    source_files = {p.relative_to(SOURCE).as_posix():pin(p) for p in sorted(SOURCE.rglob('*')) if p.is_file()}
    assert len(source_files) == 10
    write(SOURCE / 'SOURCE_PINS.json', {'schema':1,'files':source_files})
    write(HERE / 'derivation-substitutions.json', {'schema':1,'baseline_path':str(BASE/'source'),
        'baseline_manifest_sha256':BASE_SHA,'literal_substitutions':MAPPING,
        'per_source_counts':substitution_counts,'extra_helper_UID_exclusions':[10137,10196],
        'actual_IHG_helper_UID_source':{'path':'root-recovery-20261104-02/evidence/ihg-r1-install-read01/worker.json',
            'bytes':11213,'sha256':'2e62018b086bb5484648d07867e73a3b11efbbd3490aeb3f190d1bb24afe4179'},
        'source_only_not_dispatched':True})
    write(HERE / 'normalized-logic-residual.patch', ''.join(residual))
    full_diff = []
    for old_name in sorted(baseline['files']):
        new_name = literal(old_name)
        full_diff.extend(difflib.unified_diff((BASE/'source'/old_name).read_text().splitlines(True),
            (SOURCE/new_name).read_text().splitlines(True),fromfile='actual-IHG/'+old_name,tofile='BestBuy/'+new_name))
    write(HERE / 'ihg-r1-to-bestbuy-r1.patch', ''.join(full_diff))
    write(HERE / 'baseline-and-derivation-verification.json', {'schema':1,
        'baseline_source_path':str(BASE/'source'),'baseline_source_manifest':{'bytes':len(baseline_raw),'sha256':BASE_SHA},
        'baseline_actual_build':{'bytes':len(build_raw),'sha256':sha(build_raw)},
        'baseline_actual_stage':{'bytes':len(stage_raw),'sha256':sha(stage_raw)},
        'original_own_source_and_qualified_build_reexecuted_pure':True,
        'Python_changes_after_literal_normalization':python_changes,
        'Java_exact_literal_derivation_verified':True,'all_ten_source_files_verified':True,
        'all_three_target_APKs_bound_with_full_held_metadata':True,
        'actual_BestBuy_metadata_pin':{'bytes':len(worker_raw),'sha256':sha(worker_raw)},
        'helper_UID':None,'helper_APK':None,'helper_signer':None,
        'new_build_required':True,'BestBuy_qualification_inherited':False,
        'Java_compile_Android_Hepta_or_ref_actions':0})
    print(json.dumps({'state':'BESTBUY_LOCAL_SOURCE_DERIVED_NO_BUILD_OR_DISPATCH',
        'source_manifest':pin(SOURCE/'SOURCE_PINS.json'),'source_files':len(source_files),
        'Python_changes_after_literal_normalization':python_changes,
        'residual_diff':pin(HERE/'normalized-logic-residual.patch')},indent=2))


if __name__ == '__main__':
    main()
