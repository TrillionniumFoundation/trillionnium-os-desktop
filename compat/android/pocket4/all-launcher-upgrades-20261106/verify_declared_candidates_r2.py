#!/usr/bin/env python3
"""Verify an already downloaded official APK; never install or launch it.

Uses the existing pinned JDK/aapt/apksigner tools. The APK is held open across
both verification commands and its bytes and current pathname are rechecked.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
sys.dont_write_bytecode = True

ROOT = Path('/home/alex/work/pocket4-eight-apps-upgrade-20261106-r1')
CANDIDATES = {
    'com.rytong.ceair': {
        'bytes': 220804847,
        'sha256': 'a6da8d746f98cae884f6b0137b5c7e8412836adf75530b763dae1536c75522ce',
        'signer': 'b48f75514e956be6bd7d56f1701136c8d76f19459bd724ac52390a572bc0ecbf',
        'url': 'https://ecresource-app.ceair.com/apk/ceair_release_v9_5_16_20261105.apk',
        'latest_metadata_version': '9.5.16',
    },
    'com.lianjia.beike': {
        'bytes': 228933721,
        'sha256': 'c7985ed41b91c782af8acb04b1868419cca8bc1fc52862bf6c89fa86b65c81fb',
        'signer': '0b66624117621bb9bc3e7d12a1fe5436794cf8999b0253d9ff9bec71e0932178',
        'url': 'https://file.ljcdn.com/app-packages/shell/channel/20f1e58d/Android_ke_m.apk',
        'latest_metadata_version': '3.06.70',
    },
}

DEPS = Path('/home/alex/work/pocket4-app-identities-20261105-r12-01/dependencies.json')
DEPS_SHA = 'dfe1182d8e0da4d3d6e842736378539df33e03a87cf0ed9ab4bbe9ae1f26c041'
STAT = ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')

def require(value, reason):
    if not value:
        raise RuntimeError(reason)

def identity(fd):
    s = os.fstat(fd)
    return {k: getattr(s, k) for k in STAT}

def fd_digest(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    h = hashlib.sha256()
    for b in iter(lambda: os.read(fd, 1048576), b''):
        h.update(b)
    os.lseek(fd, 0, os.SEEK_SET)
    return h.hexdigest()

def file_check(path, expected_size, expected_sha):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = identity(fd)
        require(stat.S_ISREG(before['st_mode']) and before['st_nlink'] == 1 and
                before['st_size'] == expected_size, 'TOOL_FILE_METADATA_MISMATCH')
        require(fd_digest(fd) == expected_sha and identity(fd) == before, 'TOOL_BYTES_CHANGED')
        return before
    finally:
        os.close(fd)

def main():
    require(len(sys.argv) == 2 and sys.argv[1] in CANDIDATES, 'EXACT_DECLARED_CANDIDATE_REQUIRED')
    package = sys.argv[1]
    candidate = CANDIDATES[package]
    APK = ROOT / (package + '.apk')
    EXPECTED_BYTES = candidate['bytes']
    EXPECTED_SHA = candidate['sha256']
    CURRENT_SIGNER_REFERENCE = candidate['signer']
    require(os.geteuid() == 0, 'EXISTING_ROOT_AUTHORITY_FOR_PINNED_PRIVATE_DEPENDENCIES_REQUIRED')
    outdir = ROOT / (package + '-signature-verify-r1')
    outdir.mkdir(mode=0o700)
    out = {'schema':'pocket4-official-apk-verification-v1', 'package':package,
           'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'source_url':candidate['url'],
           'installs':0,'UI_actions':0,'automatic_retry':False,'signature_verified':False,
           'claimed_latest_usable':False,'production_ready':False,'commands':[]}
    fd = None
    try:
        raw = DEPS.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == DEPS_SHA, 'TOOL_DEPENDENCIES_CHANGED')
        deps = json.loads(raw)['files']
        tool_stats = {}
        for name, row in deps.items():
            tool_stats[name] = file_check(row['resolved_path'], row['bytes'], row['sha256'])
            require(str(Path(row['declared_path']).resolve()) == row['resolved_path'], 'TOOL_RESOLUTION_CHANGED')
        out['tool_dependencies_sha256'] = DEPS_SHA
        fd = os.open(APK, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = identity(fd)
        require(stat.S_ISREG(before['st_mode']) and before['st_nlink'] == 1 and
                before['st_size'] == EXPECTED_BYTES and fd_digest(fd) == EXPECTED_SHA, 'APK_BYTES_CHANGED')
        out['apk'] = {'path':str(APK),'bytes':EXPECTED_BYTES,'sha256':EXPECTED_SHA,'stat':before}
        source = '/proc/self/fd/' + str(fd)
        commands = [
            ('apksigner', [deps['java']['resolved_path'], '-Xmx256m', '-jar',
                          deps['apksigner_jar']['resolved_path'], 'verify', '--verbose', '--print-certs', source]),
            ('aapt-badging', [deps['aapt']['resolved_path'], 'dump', 'badging', source])]
        outputs = {}
        for name, argv in commands:
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                                    timeout=90, pass_fds=(fd,),
                                    env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'})
            require(len(result.stdout) <= 1048576 and len(result.stderr) <= 1048576, 'TOOL_OUTPUT_BOUND')
            for stream, data in (('stdout',result.stdout),('stderr',result.stderr)):
                with (outdir / (name + '.' + stream)).open('xb') as f:
                    f.write(data)
            outputs[name] = result.stdout.decode('utf-8','strict')
            out['commands'].append({'name':name,'returncode':result.returncode,'joined':True,'timed_out':False,
                'stdout_sha256':hashlib.sha256(result.stdout).hexdigest(),
                'stderr_sha256':hashlib.sha256(result.stderr).hexdigest()})
            require(result.returncode == 0, 'VERIFIER_FAILED_' + name)
        certs = re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([0-9a-f]{64})$', outputs['apksigner'], re.M)
        require(certs and len(certs) == len(set(certs)), 'EXACT_SIGNER_DIGESTS_REQUIRED')
        match = re.search(r"^package: name='([^']+)' versionCode='([0-9]+)' versionName='([^']*)'", outputs['aapt-badging'], re.M)
        require(match is not None and match[1] == package, 'APK_PACKAGE_ID_MISMATCH')
        out['manifest'] = {'package':match[1],'version_code':int(match[2]),'version_name':match[3]}
        for key, pattern in [('min_sdk',r"^sdkVersion:'([^']*)'"),('target_sdk',r"^targetSdkVersion:'([^']*)'")]:
            m = re.search(pattern, outputs['aapt-badging'], re.M)
            out['manifest'][key] = m[1] if m else None
        out['manifest']['native_abis'] = re.findall(r"'([^']+)'", next((x for x in outputs['aapt-badging'].splitlines() if x.startswith('native-code:')), ''))
        out['matches_latest_observed_store_version'] = match[3] == candidate['latest_metadata_version']
        out['signer_certificate_sha256'] = certs
        out['signer_matches_historical_installed_reference'] = certs == [CURRENT_SIGNER_REFERENCE]
        require(fd_digest(fd) == EXPECTED_SHA and identity(fd) == before, 'HELD_APK_CHANGED')
        check = os.open(APK, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            require(identity(check) == before, 'APK_PATH_REPLACED')
        finally:
            os.close(check)
        for name, row in deps.items():
            require(file_check(row['resolved_path'],row['bytes'],row['sha256']) == tool_stats[name], 'TOOL_IDENTITY_CHANGED')
        out.update(signature_verified=True, held_file_and_path_unchanged=True,
                   status='VERIFIED_OFFICIAL_CANDIDATE_NOT_INSTALLED')
    except BaseException as error:
        out.update(status='VERIFICATION_FAILED',error_type=type(error).__name__,error=str(error)[:512])
    finally:
        if fd is not None:
            os.close(fd)
        out['ended_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with (outdir/'result.json').open('x') as f:
            json.dump(out,f,indent=2); f.write('\n');f.flush();os.fsync(f.fileno())
    print(json.dumps(out),flush=True)
    return 0 if out['signature_verified'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
