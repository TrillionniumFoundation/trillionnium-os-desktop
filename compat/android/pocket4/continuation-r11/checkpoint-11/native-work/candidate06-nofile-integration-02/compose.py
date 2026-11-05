#!/usr/bin/env python3
"""Create only candidate06 from candidate05 plus the three exact tested files."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

HERE = Path('/home/alex/work/pocket4-candidate06-nofile-composition-source-01-20261105')
OWNER = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01')
PARENT = OWNER / 'overlay-reconstruction-09/candidate-05'
PARENT_MANIFEST = PARENT.parent / 'candidate-05-source-manifest.json'
PARENT_SHA = '4e2f7f9ea09c6977afbe8d97c040fd2f1344772429f78fe0f16edc913dadc7ba'
ROOT = OWNER / 'overlay-reconstruction-10'
DESTINATION = ROOT / 'candidate-06'
MANIFEST_SHA = '3c780a398075f77d1f6b1c477c6ceaa35349de17b88e77896aa22820259c0376'
BASE_CONTRACT_SHA = 'edf9f49f9aa5b404eb49c4dd848c998efffc4929f38137a698ec77c0d1f48fc9'
ASSESSMENT_SHA = 'abd1195e47024b7ceed641ed40deb6e722155d8363413104604d87f99a095779'
ANDROID_SHA = 'fbc3ca4d6e861b50da8ee537c90908b5308249015a31220acdd2d09b00f42b13'
ANDROID_BUILD_SHA = 'f3617407f8c624357f4bf9a9cc53e1e78a217b3c0b8bc9a51448c09569e2ea06'
HOST_SHA = 'b0a03b1b95e3292131105dcb22fd59f4a767e63017197e29f4482036976a4ac2'
CASE_SHA = '5ad4e7985eee2d1c9a7dd1322a2c933e74d734a5c98a37d4bb0c5b88e101ee09'
ANCESTRY = 'NOFILE recovery03 exact production source; owned host and Android artifact proof receipts separately pinned by candidate06 composition'
DELTA = {
    'engine/kernel_api/proc_maps_raw_metadata_owner.cc':
        ('489264a8fcb8e0607a671b78363970caf17f0bb4589b46c12e77329daf17b818',
         '4400b1db44f3d7c46dd25136dba8599bc934f2ef28963c289cde1953960536a6', 25425),
    'engine/kernel_api/include/berberis/kernel_api/proc_maps_raw_metadata_owner.h':
        ('7e8ae5c660c783c8fb8f5db75c054e5359690275a2f4acc2a9fe1c9af7c11554',
         'b3c0fed34550a113c993808f31ee6eb3708b58b856530c0acf8cc7bfe22306cc', 2750),
    'engine/kernel_api/include/berberis/kernel_api/proc_maps_provenance.h':
        ('79e871b78d6fc2461f2fe103df070d6dc6504acf43ff6b64fcecec142eb618b0',
         'e21bc5dbe7b92893f52cd9a9d7d3ffe30cd813485aa4d2ebdadb435350e0fa68', 4330),
}


def need(value, why):
    if not value:
        raise RuntimeError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(path, expected, bound):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_size <= bound, 'regular source/bound mismatch')
        chunks = []
        size = 0
        while True:
            chunk = os.read(fd, min(32768, bound + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            need(size <= bound, 'source grew beyond bound')
        raw = b''.join(chunks)
        after = os.fstat(fd)
        named = Path(path).lstat()
        key = lambda x: (x.st_dev, x.st_ino, x.st_mode, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        need(key(before) == key(after) == key(named) and size == before.st_size and sha(raw) == expected,
             'held source bytes/identity changed: ' + str(path))
        return raw
    finally:
        os.close(fd)


def load_source(name, expected):
    path = HERE / name
    raw = pinned(path, expected, 65536)
    scope = {'__name__': 'frozen_source_contract_only', '__file__': str(path)}
    exec(compile(raw, str(path), 'exec'), scope, scope)
    return scope


def proof_contract():
    android = json.loads(pinned(HERE / 'proof/android-coordinator-result.json', ANDROID_SHA, 524288))
    host = json.loads(pinned(HERE / 'proof/host-result.json', HOST_SHA, 32768))
    build = json.loads(pinned(HERE / 'proof/android-build-result.json', ANDROID_BUILD_SHA, 65536))
    cases = json.loads(pinned(HERE / 'CASE_PLAN.json', CASE_SHA, 16384))['cases']
    assessment = load_source('references/runtime-coordinator.py', ASSESSMENT_SHA)
    need(android['state'] == 'PASS_OWNED_ANDROID_26CASE_PAIR' and not android['errors'] and
         not android['recording_errors'] and android['source_artifact_authority_unchanged_after'] is True and
         android['build_sha256'] == ANDROID_BUILD_SHA and
         android['entry_review_sha256'] == '2dbe0c31ec31733fab9bbfb851ab3642dc0c2d7aef3937165084d1fb11b9548c' and
         android['runner_sha256'] == 'c16015f7a51f857d114d92691dbf4ac4d0ccf758c2f99c7c541653ce1957ea62' and
         android['entry_qualification_sha256'] == '3e3dd5c9ae1b4e913d7a688bb338507162cbc211bb897658a539948ffb6f93e3',
         'actual Android source authority or completed result differs')
    need([a['arm'] for a in android['arms']] == ['preimage', 'candidate'], 'Android arm order differs')
    uids = []
    for arm in android['arms']:
        need(arm['native_pass'] is True and arm['transport_complete'] is True and
             arm['exact_owned_package_removed'] is True and len(arm['steps']) == 3,
             'Android arm did not finish native/transport/exact removal')
        need([s['phase'] for s in arm['steps']] == ['install', 'run', 'remove'] and
             all(s['returncode'] == 0 and s['report']['ok'] is True and
                 s['report']['outcome_unknown'] is False and
                 s['report']['framework_epoch_sha256'] == assessment['EPOCH_SHA'] for s in arm['steps']),
             'Android phase or Main epoch evidence differs')
        actual = assessment['assess_instrumentation'](arm['arm'], arm['steps'][1]['report'], cases)
        need(actual == arm['assessment'], 'full actual 26-case original assertions differ')
        uids.append(actual['uid'])
    need(len(set(uids)) == 2 and all(uid >= 10000 for uid in uids), 'fresh Android app identities differ')
    for name in ('own', 'Main'):
        need(all(android['resource_fences'][name]['memory_events_delta'][key] == 0
                 for key in ('oom', 'oom_kill', 'oom_group_kill')), 'Android OOM qualification differs')
    need(host['state'] == 'PASS' and host['source_unchanged_after'] is True and
         host['held_ELF_unchanged_after'] is True and host['authority_unchanged_after'] is True and
         not host['tool_changes'] and not host['library_changes'] and
         host['owned_resource_gate']['pass'] is True and not host['cleanup']['errors'] and
         not host['cleanup']['remaining'] and not host['cleanup']['forced_cleanup'],
         'actual host comparison qualification differs')
    need([a['arm'] for a in host['arms']] == ['preimage', 'candidate'] and
         [a['function_passed'] for a in host['arms']] == [15, 26] and
         all(a['case_count'] == 26 and a['matched_expected'] is True and a['returncode'] == 0 and
             a['child_reaped'] is True and a['direct_children_reaped'] == 26 and
             a['nested_children_reaped'] == 5 and not a['timed_out'] for a in host['arms']),
         'actual host 26-case comparison differs')
    need(build['state'] == 'PASS' and build['source_unchanged_after'] is True and
         build['APK_ELF_unchanged_after'] is True and build['authority_unchanged_after'] is True and
         build['original_26_case_assertions_unchanged'] is True and not build['tool_changes'] and
         all(a['APK_embedded_ELF_exact'] is True for a in build['arms'].values()),
         'actual Android build artifact/source qualification differs')
    return build


def derive(parent):
    need(set(parent) == {'schema', 'files', 'ancestry'} and parent['schema'] == 1 and
         len(parent['files']) == len(parent['ancestry']) == 948, 'parent manifest schema differs')
    value = json.loads(json.dumps(parent))
    for name, (before, after, size) in DELTA.items():
        need(value['files'][name] == before and value['ancestry'][name][-1]['sha256'] == before,
             'delta preimage/ancestry differs')
        value['files'][name] = after
        value['ancestry'][name].append({'source': ANCESTRY, 'prior_sha256': before, 'sha256': after})
    raw = (json.dumps(value, indent=2) + '\n').encode()
    need(sha(raw) == MANIFEST_SHA, 'derived candidate06 manifest differs')
    return value, raw


def verify_11_sources(manifest, build):
    rows = build['source_inputs']['candidate']
    actual = {name: row for name, row in rows.items() if name.startswith('actual/')}
    need(len(actual) == 11, 'tested production-source membership differs')
    for name, row in actual.items():
        rel = name[len('actual/'):]
        engine = 'engine/kernel_api/include/' + rel if rel.startswith('berberis/') else 'engine/kernel_api/' + rel
        need(manifest['files'][engine] == row['sha256'], 'tested production source differs: ' + name)
    return {name: row['sha256'] for name, row in actual.items()}


def execute():
    need(os.getuid() == 1000 and os.geteuid() == 1000 and Path(__file__).absolute() == HERE / 'compose.py',
         'explicit operator/staged source required')
    os.umask(0o077)
    base = load_source('references/base-source-contract.py', BASE_CONTRACT_SHA)
    base['no_alias'](HERE)
    base['no_alias'](ROOT)
    need(not ROOT.exists(), 'candidate06 root exists; reconcile, never overwrite or retry')
    # This exact unchanged function checks candidate05's 948 bytes, 925 engine
    # inputs, six signal files, actual builder450 and original matching gates.
    parent_files = base['source_contract']()[0]
    parent_raw = pinned(PARENT_MANIFEST, PARENT_SHA, 524288)
    parent = json.loads(parent_raw)
    need(parent['files'] == parent_files, 'parent manifest/source contract differs')
    manifest, manifest_raw = derive(parent)
    build = proof_contract()
    tested = verify_11_sources(manifest, build)
    overrides = {}
    for name, (before, after, size) in DELTA.items():
        value = pinned(HERE / 'delta' / name[len('engine/'):], after, size)
        need(len(value) == size, 'delta size differs')
        overrides[name] = value
    ROOT.mkdir(mode=0o700)
    base['save'](ROOT / 'claim.json', {'schema': 1, 'state': 'COMPOSING_CANDIDATE06',
                 'parent_manifest_sha256': PARENT_SHA, 'expected_manifest_sha256': MANIFEST_SHA,
                 'changes': sorted(DELTA), 'started_utc': base['utc'](), 'automatic_retry': False})
    try:
        DESTINATION.mkdir(mode=0o700)
        for name, expected in manifest['files'].items():
            base['relative'](name)
            destination = DESTINATION / name
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if name in overrides:
                raw = overrides[name]
            else:
                raw = pinned(PARENT / name, expected, 8388608)
            need(sha(raw) == expected, 'source-copy input differs')
            with destination.open('xb') as stream:
                need(stream.write(raw) == len(raw), 'short new source write')
                stream.flush()
                os.fsync(stream.fileno())
            destination.chmod(0o444)
        need(base['hashes'](DESTINATION) == manifest['files'], 'candidate06 exact full inventory differs')
        need(base['source_contract']()[0] == parent_files and
             pinned(PARENT_MANIFEST, PARENT_SHA, 524288) == parent_raw,
             'original candidate05 or source authority changed during copying')
        proof_contract()
        for name, (before, after, size) in DELTA.items():
            pinned(HERE / 'delta' / name[len('engine/'):], after, size)
        with (ROOT / 'candidate-06-source-manifest.json').open('xb') as stream:
            need(stream.write(manifest_raw) == len(manifest_raw), 'short manifest write')
            stream.flush()
            os.fsync(stream.fileno())
        (ROOT / 'candidate-06-source-manifest.json').chmod(0o444)
        result = {'schema': 1, 'state': 'CANDIDATE06_COMPOSED_SOURCE_NOT_BUILT',
                  'finished_utc': base['utc'](), 'candidate': str(DESTINATION),
                  'manifest': str(ROOT / 'candidate-06-source-manifest.json'),
                  'manifest_sha256': MANIFEST_SHA, 'parent_manifest_sha256': PARENT_SHA,
                  'source_files': 948, 'engine_files': 925, 'changed_files': sorted(DELTA),
                  'unchanged_total_files': 945, 'unchanged_engine_files': 922,
                  'parent_and_authority_unchanged_after': True,
                  'all_11_tested_production_inputs_exact': True, 'tested_production_input_hashes': tested,
                  'actual_Android_build_sha256': ANDROID_BUILD_SHA,
                  'actual_Android_runtime_sha256': ANDROID_SHA, 'actual_host_runtime_sha256': HOST_SHA,
                  'source_proof_files_root': str(HERE),
                  'original_candidate05_matched_gate_sha256': base['MATCHED_GATE_SHA'],
                  'matched_candidate05_gates_rerun_for06': False,
                  'feature_default_enabled': False, 'full_engine_built': False,
                  'ART_built': False, 'factory_built': False, 'installed': False,
                  'Main_actions': 0, 'Android_actions': 0, 'services_started': False, 'production_ready': False}
        base['save'](ROOT / 'candidate-06-composition-report.json', result)
        print(json.dumps({'state': result['state'], 'manifest_sha256': MANIFEST_SHA,
                          'report': str(ROOT / 'candidate-06-composition-report.json'),
                          'report_sha256': base['digest'](ROOT / 'candidate-06-composition-report.json')}), flush=True)
        return 0
    except BaseException as error:
        base['save'](ROOT / 'failure.json', {'state': 'COMPOSITION_FAILED', 'error': repr(error),
                     'source_copy_only': True, 'full_engine_built': False, 'Main_actions': 0})
        raise


if __name__ == '__main__':
    if sys.argv[1:] != ['--execute-once']:
        print(json.dumps({'state': 'PLAN_ONLY', 'root': str(ROOT), 'parent_manifest_sha256': PARENT_SHA,
                          'expected_manifest_sha256': MANIFEST_SHA, 'changes': sorted(DELTA),
                          'source_files': 948, 'engine_files': 925, 'actual_Android_runtime_sha256': ANDROID_SHA,
                          'full_build_started': False, 'Main_actions': 0, 'remote_actions': 0}))
    else:
        raise SystemExit(execute())
