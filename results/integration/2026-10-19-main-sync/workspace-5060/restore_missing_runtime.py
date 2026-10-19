#!/usr/bin/env python3
"""Close the two actual loader gaps without changing attempt-01 records or harness."""
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import time

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('r9_environment', BASE / 'prepare.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main():
    original_path = BASE / 'receipts/environment-restoration.json'
    report = json.loads(original_path.read_text())
    report['parent_environment_receipt_sha256'] = module.digest(original_path.read_bytes())
    report['extension_helper_sha256'] = module.digest(Path(__file__).read_bytes())
    report['extension_started_unix'] = time.time()
    report['status'] = 'running'
    try:
        source = json.loads(module.OLD_PACKAGES.read_text())
        selected = [row for row in source['items'] if row['package'] in ('libxtst6', 'libxxf86dga1')]
        assert len(selected) == 2
        for row in selected:
            item = {key: row[key] for key in ['package', 'version', 'url', 'sha256', 'bytes']}
            path = BASE / 'packages' / (item['package'] + '.deb')
            assert not path.exists()
            cmd = ['curl', '--fail', '--location', '--connect-timeout', '10', '--max-time', '50',
                   '--proto', '=https', '--silent', '--show-error', '--output', str(path), item['url']]
            start = time.time()
            value = subprocess.run(cmd, capture_output=True, timeout=55)
            (BASE / 'receipts' / (item['package'] + '.download.stderr.log')).write_bytes(value.stderr)
            assert value.returncode == 0, value.stderr.decode(errors='replace')
            raw = path.read_bytes()
            assert len(raw) == item['bytes'] and module.digest(raw) == item['sha256']
            extract = subprocess.run(['dpkg-deb', '--extract', str(path), str(BASE / 'sysroot')],
                                     capture_output=True, timeout=30)
            assert extract.returncode == 0
            report['packages'].append({**item, 'command': cmd, 'returncode': 0,
                                       'extract_exit_code': 0, 'started_unix': start,
                                       'finished_unix': time.time(), 'reason': 'actual loader diagnostic capture-01'})
        (BASE / 'view03').mkdir(mode=0o700)
        report['usr_view_symlinks'] = module.usr_view(Path('/usr'), BASE / 'sysroot/usr', BASE / 'view03/usr')
        report['usr_view'] = 'view03/usr'
        report['status'] = 'passed'
    finally:
        report['extension_finished_unix'] = time.time()
        module.write(BASE / 'receipts/environment-restoration-02.json', report)

    shutil.copytree(BASE / 'harness', BASE / 'harness02')
    path = BASE / 'harness02/tests/ui/probe-chat-workspace.py'
    new = path.read_text().replace('environment-restoration.json', 'environment-restoration-02.json')
    new = new.replace('harness-derivation.json', 'harness-derivation-02.json').replace('view02/usr', 'view03/usr')
    path.write_text(new)
    compile(new, str(path), 'exec')
    old = (BASE / 'harness-origin/tests/ui/probe-chat-workspace.py').read_text()
    patch = ''.join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                       fromfile='tracked/tests/ui/probe-chat-workspace.py',
                                       tofile='r9-private-harness02/tests/ui/probe-chat-workspace.py'))
    (BASE / 'harness-02.patch').write_text(patch)
    manifest = json.loads((BASE / 'harness-derivation.json').read_text())
    manifest['parent_derivation_sha256'] = module.digest((BASE / 'harness-derivation.json').read_bytes())
    manifest['extension_script_sha256'] = module.digest(Path(__file__).read_bytes())
    manifest['patch_sha256'] = module.digest(patch.encode())
    manifest['derived_files'] = {name: {'sha256': module.digest((BASE / 'harness02' / name).read_bytes()),
                                      'bytes': (BASE / 'harness02' / name).stat().st_size}
                                for name in manifest['derived_files']}
    module.write(BASE / 'harness-derivation-02.json', manifest)
    print(json.dumps({'status': report['status'], 'packages': len(report['packages']),
                      'main_harness': manifest['derived_files']['tests/ui/probe-chat-workspace.py'],
                      'previous_attempt_preserved': True}, sort_keys=True))


if __name__ == '__main__':
    main()
