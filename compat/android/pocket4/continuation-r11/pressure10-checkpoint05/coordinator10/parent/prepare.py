"""Create-only staging for one explicitly selected revision09 owned cell."""
from pathlib import Path
import datetime, hashlib, json, os, re, stat, subprocess, sys, traceback, types

P = Path
SOURCE = 'c71f8aa93bb96f329177b7797a77d1b6f46238953450a9579b78547770f991b5'
BUILD = '087a22519b0619be5a38440549a4730305bbfede6a046bbac347516dea0e962b'
BASE = P('/home/alex/work/pocket4-lmkd-host-pressure-r11-source-09')
ACT = P('/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json')
HELPER = P('/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py')
ACT_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
HELPER_SHA = 'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'
BINS = {'actor':'e4a24055ff87b793cee0c8bfe11b1e9df48581cc0406024fbf93f2461b8cf06e',
        'driver':'a9de6becc67b03ccc877ed54b64ee7c3c1b3398f546fb6464d9b52f707ebe00b',
        'broker':'6ba22d7ba928a2e05dd71e76317252097526672530f43793ad6cdfdb26c93154',
        'android_lmkd':'bd794b7b59d1047523cea6174bcd230c75aa2eececd1900b23f3f33a86061dde'}
PROFILES = {'pressure':('p4-lmkd-relay-pressure-r11-03', 'pocket4-lmkd-pressure-r11-coordinator-04'),
            'stale':('p4-lmkd-relay-stale-r11-02', 'pocket4-lmkd-pressure-r11-coordinator-05')}

def need(value, message):
    if not value: raise RuntimeError(message)

def sha(path):
    with P(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()

def write(path, value):
    raw = (json.dumps(value, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())

def predecessor(pin):
    need(re.fullmatch('[0-9a-f]{64}', pin) is not None, 'stale requires externally pinned completed positive receipt')
    path = P('/home/alex/work/pocket4-lmkd-pressure-r11-coordinator-04/02-pressure-once/result.json')
    need(sha(path) == pin, 'positive predecessor receipt pin changed')
    r = json.loads(path.read_text())
    need(r.get('phase') == 'pressure' and r.get('source_manifest_sha256') == SOURCE and r.get('matching_build_receipt_sha256') == BUILD,
         'positive predecessor source/phase mismatch')
    need(all(r.get(k) is True for k in ('ok', 'external_unit_binding_verified', 'exact_owned_cleanup_verified', 'main_epoch_unchanged_after_cleanup'))
         and r.get('outcome_unknown') is False and r.get('forced_teardown') is False,
         'positive predecessor did not complete exact normal cleanup and Main fence')
    need(r.get('pressure_qualified') is True or r.get('partial_medium_only') is True, 'positive predecessor is rejected/inconclusive')
    return {'path':str(path), 'sha256':pin, 'partial_medium_only':r.get('partial_medium_only', False)}

def main():
    out = None
    report = {'schema':1, 'ok':False, 'scope':'revision09 owned staging only',
              'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'pressure_executed':False, 'installed_files_changed':False}
    try:
        need(len(sys.argv) in (2,3) and sys.argv[1] in PROFILES, 'usage: prepare.py pressure | stale POSITIVE_RECEIPT_SHA256')
        phase = sys.argv[1]
        need(len(sys.argv) == (2 if phase == 'pressure' else 3), 'exact phase argument shape required')
        stem, coordinator = PROFILES[phase]
        root = P('/home/alex/work') / coordinator; state = P('/run') / stem; stage = P('/opt') / stem; unit = stem + '.service'
        report.update(phase=phase, unit=unit, coordinator_root=str(root), state=str(state), stage=str(stage),
                      source_manifest_sha256=SOURCE, matching_build_receipt_sha256=BUILD, binaries_sha256=BINS)
        need(os.geteuid() == 0, 'owned mountpoint/device staging requires root')
        os.umask(0o077)
        if phase == 'stale': report['positive_predecessor'] = predecessor(sys.argv[2])
        need(sha(ACT) == ACT_SHA and sha(HELPER) == HELPER_SHA, 'Main epoch helper/activation pin changed')
        act = json.loads(ACT.read_text()); epoch = types.ModuleType('epoch'); epoch.__file__ = str(HELPER)
        exec(compile(HELPER.read_bytes(), str(HELPER), 'exec'), epoch.__dict__)
        epoch.require_unchanged(act['framework_epoch'], action_attempted=False)
        need(sha(BASE/'source-manifest.json') == SOURCE and sha(BASE/'build-result.json') == BUILD, 'revision09 source/build receipt changed')
        manifest = json.loads((BASE/'source-manifest.json').read_text())
        need(len(manifest['files']) == 36, 'exact revision09 payload count required')
        for name, row in manifest['files'].items():
            path = BASE/name; metadata = path.lstat()
            need(stat.S_ISREG(metadata.st_mode) and metadata.st_size == row['bytes'] and sha(path) == row['sha256'], 'frozen source differs: '+name)
        build = json.loads((BASE/'build-result.json').read_text())
        need(build['success'] and build['rust_tests_passed'] == 20 and build['ordinary_ipc_passed'] == 7 and
             build['synthetic_python_tests_passed'] == 23 and not build['pressure_executed'], 'matching build/control gate failed')
        for row in build['binaries']:
            need(sha(row['path']) == row['sha256'], 'matching output changed: '+row['path'])
        for relative, role in [('target/debug/owned-relay-canary','driver'), ('target/debug/droidloom-psi-owner','broker'), ('owned-relay/fixture-init','actor')]:
            need(sha(BASE/relative) == BINS[role], 'fixed revision09 binary pin differs: '+role)
        need(not root.exists() and not state.exists() and not stage.exists(), 'fresh root/state/stage only; no same-cell retry')
        shown = subprocess.run(['/usr/bin/systemctl','show',unit,'--property=LoadState'], capture_output=True, text=True, timeout=10)
        need(shown.returncode == 0 and 'LoadState=not-found' in shown.stdout, 'owned unit must be absent before staging')
        available = int(next(line.split()[1] for line in P('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))) * 1024
        need(available > 3 * 1024**3, 'minimum 3 GiB free host admission failed')
        root.mkdir(mode=0o700); out = root/'01-prepare'; out.mkdir(mode=0o700)
        report.update(main_epoch_sha256=act['framework_epoch']['sha256'], available_memory_bytes=available)
        write(out/'claim.json', report)
        argv = [str(BASE/'target/debug/owned-relay-canary'), 'prepare', str(stage/'root'), str(state), unit,
                str(BASE/'owned-relay/fixture-init'), BINS['actor'],
                '/home/alex/work/pocket4-lmkd-enrollment-r6-android-build-01/link/lmkd-cgroup', BINS['android_lmkd']]
        run = subprocess.run(argv, capture_output=True, text=True, timeout=40)
        report.update(argv=argv, returncode=run.returncode, stdout=run.stdout, stderr=run.stderr)
        need(run.returncode == 0, 'owned revision09 staging failed')
        path = state/'evidence/staging-result.json'; staged = json.loads(path.read_text())
        need(staged['ok'] and staged['all_source_and_copied_hashes_matched'] and staged['actor_sha256'] == BINS['actor'] and staged['lmkd_sha256'] == BINS['android_lmkd'], 'staging pin/receipt gate failed')
        report.update(staging_result_sha256=sha(path), staging_result=staged)
        epoch.require_unchanged(act['framework_epoch'], action_attempted=False)
        report.update(ok=True, main_epoch_unchanged=True)
    except Exception as error:
        report.update(ok=False, error=type(error).__name__+': '+str(error), traceback=traceback.format_exc())
    finally:
        report['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if out is not None: write(out/'result.json', report)
        print(json.dumps({'report':str(out/'result.json') if out is not None else None,
                          'sha256':sha(out/'result.json') if out is not None else None, **report}), flush=True)
    return 0 if report['ok'] else 1

if __name__ == '__main__': sys.exit(main())
