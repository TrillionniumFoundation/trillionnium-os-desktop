#!/usr/bin/env python3
"""Build the reviewed DEX fixture with an installed SDK; never contact ADB.

This is an SDK-built Android application, not the pinned AOSP/Soong product.
The task-local signing key is a disposable test identity, not a release key.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = 'tests/workloads/android/apk-smoke'
SOURCE_FILES = (
    'Android.bp', 'app/build.gradle', 'build.gradle', 'settings.gradle',
    'app/src/main/AndroidManifest.xml',
    'app/src/main/java/org/trillionnium/a08smoke/MainActivity.java',
    'app/src/main/res/values/ids.xml',
)
ORIGINAL_SOURCE_SHA256 = '94d550360d7b36fe69b054472d46f8e8f01b50b0618ba8f335b25e7ef34fa5da'
PROFILE = 'a08_original_dex_installed_sdk'


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(data)
    return digest.hexdigest()


def source_digest(inventory):
    return hashlib.sha256(json.dumps(inventory, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


class Recorder:
    def __init__(self, out):
        self.out = Path(out)
        self.commands = []

    def run(self, args, timeout=120):
        args = [str(arg) for arg in args]
        number = len(self.commands) + 1
        record = {'argv': args, 'timeout_seconds': timeout}
        self.commands.append(record)
        start = time.monotonic()
        try:
            result = subprocess.run(args, capture_output=True, timeout=timeout,
                                    check=False)
            stdout, stderr = result.stdout, result.stderr
            record['returncode'] = result.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr = exc.stdout or b'', exc.stderr or b''
            record['error'] = 'timeout'
            record['returncode'] = None
        record['elapsed_seconds'] = round(time.monotonic() - start, 3)
        for label, data in (('stdout', stdout), ('stderr', stderr)):
            path = self.out / f'{number:03d}-{label}.log'
            path.write_bytes(data)
            record[label] = {'file': path.name, 'sha256': checksum(path)}
        (self.out / 'commands.json').write_text(json.dumps(self.commands, indent=2) + '\n')
        if record['returncode'] != 0:
            raise RuntimeError(f'command {number} failed; see {self.out}/commands.json')
        return stdout.decode('utf-8', errors='replace')


def source_inventory(repo, commit):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args])
    # Full object IDs only; never interpret an arbitrary option/ref expression.
    import re
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('source commit must be a full lowercase Git SHA')
    resolved = git('rev-parse', commit + '^{commit}').decode().strip()
    tree = git('rev-parse', commit + '^{tree}').decode().strip()
    blobs = {name: git('show', f'{resolved}:{FIXTURE}/{name}') for name in SOURCE_FILES}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in blobs.items()}
    if source_digest(hashes) != ORIGINAL_SOURCE_SHA256:
        raise ValueError('fixture differs from the reviewed original DEX sources')
    return resolved, tree, hashes, blobs


def build(args):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    recorder = Recorder(out)
    report = {'kind': PROFILE, 'status': 'failed',
              'native_asterinas_qualified': False, 'production_owner_qualified': False,
              'mobile_organ_qualified': False, 'aosp_soong_build': False}
    try:
        commit, tree, hashes, blobs = source_inventory(args.repo, args.source_commit)
        report['source'] = {'commit': commit, 'tree': tree, 'files': hashes,
                            'inventory_sha256': source_digest(hashes)}
        for name, data in blobs.items():
            path = out / 'source' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        sdk = args.sdk_root.resolve()
        bt = sdk / 'build-tools' / args.build_tools
        platform = sdk / 'platforms/android-35/android.jar'
        paths = {name: bt / name for name in ('aapt2', 'd8', 'zipalign', 'apksigner')}
        for name in ('javac', 'java', 'keytool'):
            location = shutil.which(name)
            if not location:
                raise ValueError(f'missing installed JDK tool: {name}')
            paths[name] = Path(location).resolve()
        paths['android.jar'] = platform
        # Hash wrapper payloads too, not just their small launch scripts.
        paths['d8.jar'] = bt / 'lib/d8.jar'
        paths['apksigner.jar'] = bt / 'lib/apksigner.jar'
        report['tools'] = {name: {'path': str(path), 'sha256': checksum(path)}
                           for name, path in paths.items()}
        report['builder_sha256'] = checksum(__file__)
        for name, option in (('aapt2', 'version'), ('d8', '--version'),
                             ('apksigner', 'version'), ('javac', '-version'),
                             ('java', '-version')):
            recorder.run([paths[name], option])
        main = out / 'source/app/src/main'
        generated, classes, dex = (out / name for name in ('generated', 'classes', 'dex'))
        for directory in (generated, classes, dex):
            directory.mkdir()
        recorder.run([paths['aapt2'], 'compile', '--dir', main / 'res',
                      '-o', out / 'compiled-res.zip'])
        recorder.run([paths['aapt2'], 'link', '-I', platform, '--manifest',
                      main / 'AndroidManifest.xml', '--java', generated,
                      '-o', out / 'resources.apk', out / 'compiled-res.zip'])
        sources = sorted((main / 'java').rglob('*.java')) + sorted(generated.rglob('*.java'))
        recorder.run([paths['javac'], '--release', '8', '-classpath', platform,
                      '-d', classes, *sources])
        recorder.run([paths['d8'], '--lib', platform, '--min-api', '28',
                      '--output', dex, *sorted(classes.rglob('*.class'))])
        unsigned = out / 'unsigned.apk'
        shutil.copyfile(out / 'resources.apk', unsigned)
        with zipfile.ZipFile(unsigned, 'a', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(dex / 'classes.dex', 'classes.dex')
        recorder.run([paths['zipalign'], '-f', '4', unsigned, out / 'aligned.apk'])
        # Public, disposable fixture password; this key is never a production identity.
        recorder.run([paths['keytool'], '-genkeypair', '-keystore', out / 'fixture-key.p12',
                      '-storetype', 'PKCS12', '-storepass', 'android', '-keypass', 'android',
                      '-alias', 'a08-fixture', '-keyalg', 'RSA', '-keysize', '2048',
                      '-validity', '3650', '-dname', 'CN=A08 Local Test,OU=Fixture,O=Trillionnium,C=US'])
        (out / 'fixture-key.p12').chmod(0o600)
        apk = out / 'A08Smoke.apk'
        recorder.run([paths['apksigner'], 'sign', '--ks', out / 'fixture-key.p12',
                      '--ks-key-alias', 'a08-fixture', '--ks-pass', 'pass:android',
                      '--key-pass', 'pass:android', '--out', apk, out / 'aligned.apk'])
        signature = recorder.run([paths['apksigner'], 'verify', '--verbose', '--print-certs', apk])
        import re
        certificates = re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([0-9a-f]{64})$',
                                  signature, re.MULTILINE)
        if len(certificates) != 1:
            raise ValueError('APK must have exactly one verified signing certificate')
        recorder.run([paths['zipalign'], '-c', '-v', '4', apk])
        recorder.run([paths['aapt2'], 'dump', 'badging', apk])
        recorder.run([paths['aapt2'], 'dump', 'xmltree', apk, '--file', 'AndroidManifest.xml'])
        report['apk'] = {'file': apk.name, 'sha256': checksum(apk),
                         'bytes': apk.stat().st_size,
                         'certificate_sha256': certificates[0]}
        report['status'] = 'built_not_executed'
    except Exception as exc:
        report['error'] = str(exc)
    (out / 'build.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report['status'] == 'built_not_executed' else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--sdk-root', type=Path, required=True)
    parser.add_argument('--build-tools', default='35.0.1')
    parser.add_argument('--out', type=Path, required=True)
    return build(parser.parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())
