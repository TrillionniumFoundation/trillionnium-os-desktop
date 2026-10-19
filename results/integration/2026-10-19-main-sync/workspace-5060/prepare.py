#!/usr/bin/env python3
"""Restore only the fixed private X11 capture dependencies and copy sealed R9 ELFs."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent / 'repo'
BUILD = ROOT.parent / 'r9-ui-verification/build-01/production-binaries.json'
OLD_PACKAGES = REPO / 'tests/ui/evidence/2026-10-17-original-hepta-shell/capture02-r5-passed/package-stage.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def usr_view(host, packages, output, relative=Path()):
    output.mkdir()
    names = set(p.name for p in host.iterdir()) if host.is_dir() else set()
    names |= set(p.name for p in packages.iterdir()) if packages.is_dir() else set()
    count = 0
    for name in sorted(names):
        old, new, rel = host / name, packages / name, relative / name
        if new.is_dir() and not new.is_symlink() and old.is_dir() and not old.is_symlink():
            count += usr_view(old, new, output / name, rel)
        elif new.exists() or new.is_symlink():
            (output / name).symlink_to(Path('/r9-sysroot/usr') / rel)
            count += 1
        else:
            (output / name).symlink_to(Path('/host/usr') / rel)
            count += 1
    return count


def main():
    ROOT.chmod(0o700)
    for name in ['binaries', 'packages', 'sysroot', 'receipts', 'view02']:
        (ROOT / name).mkdir(mode=0o700)
    report = {'schema': 'r9-private-x11-restoration-v1', 'started_unix': time.time(),
              'status': 'running', 'system_install_performed': False,
              'original_agentd_started': False, 'elf_rebuild_performed': False,
              'helper_sha256': digest(Path(__file__).read_bytes()), 'packages': [],
              'existing_build_record_sha256': digest(BUILD.read_bytes()), 'binaries': {}}
    try:
        build = json.loads(BUILD.read_text())
        assert build['source_equal'] is True
        source = build['source_before']
        observed = {}
        for name, expected in source['files'].items():
            raw = (REPO / name).read_bytes()
            observed[name] = {'sha256': digest(raw), 'bytes': len(raw)}
            assert observed[name] == expected, name
        report['compiled_source_inventory'] = source
        report['current_source_head'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
        report['current_source_tree'] = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=REPO, text=True).strip()
        report['current_source_status'] = subprocess.check_output(['git', 'status', '--porcelain'], cwd=REPO, text=True)
        assert not report['current_source_status']
        for name, entry in build['binaries'].items():
            raw = Path(entry['path']).read_bytes()
            assert digest(raw) == entry['sha256'] and len(raw) == entry['bytes']
            target = ROOT / 'binaries' / name
            target.write_bytes(raw)
            target.chmod(0o500)
            assert target.read_bytes() == raw
            report['binaries'][name] = {**entry, 'capture_copy_path': str(target), 'copy_byte_equal': True}
        write(ROOT / 'receipts/elf-source-binding.json', report)

        original = json.loads(OLD_PACKAGES.read_text())
        chosen = {'libxmuu1', 'xauth', 'libxfont2', 'x11-utils', 'x11-xkb-utils',
                  'xserver-common', 'xvfb', 'libxdo3', 'xdotool'}
        packages = [{k: row[k] for k in ['package', 'version', 'url', 'sha256', 'bytes']}
                    for row in original['items'] if row['package'] in chosen]
        assert len(packages) == len(chosen)
        report['previous_package_receipt_sha256'] = digest(OLD_PACKAGES.read_bytes())
        for name in ['libxkbfile1', 'fonts-noto-cjk']:
            raw = subprocess.check_output(['apt-cache', 'show', name], timeout=10)
            (ROOT / 'receipts' / (name + '.apt-cache.txt')).write_bytes(raw)
            fields = {}
            for line in raw.decode().split('\n\n')[0].splitlines():
                if ': ' in line and not line.startswith(' '):
                    key, value = line.split(': ', 1)
                    fields[key] = value
            packages.append({'package': name, 'version': fields['Version'],
                             'url': 'https://archive.ubuntu.com/ubuntu/' + fields['Filename'],
                             'sha256': fields['SHA256'], 'bytes': int(fields['Size'])})
        assert packages[-2]['sha256'] == '22ac5b7dca740e606261cebdfaf1a07738e92ad3d123570694374ddb4d5afea2'
        assert packages[-1]['sha256'] == '7d64b985f6fe128c99eae5610d5c047338e572bdcfb2bb09736be01b824a7f6c'
        write(ROOT / 'receipts/package-plan.json', packages)
        for item in packages:
            target = ROOT / 'packages' / (item['package'] + '.deb')
            command = ['curl', '--fail', '--location', '--connect-timeout', '10',
                       '--max-time', '50', '--proto', '=https', '--silent', '--show-error',
                       '--output', str(target), item['url']]
            start = time.time()
            value = subprocess.run(command, capture_output=True, timeout=55)
            (ROOT / 'receipts' / (item['package'] + '.download.stderr.log')).write_bytes(value.stderr)
            entry = {**item, 'command': command, 'returncode': value.returncode,
                     'started_unix': start, 'finished_unix': time.time()}
            report['packages'].append(entry)
            assert value.returncode == 0, item['package'] + ': ' + value.stderr.decode(errors='replace')
            raw = target.read_bytes()
            assert len(raw) == item['bytes'] and digest(raw) == item['sha256'], item['package']
            extract = subprocess.run(['dpkg-deb', '--extract', str(target), str(ROOT / 'sysroot')],
                                     capture_output=True, timeout=30)
            entry['extract_exit_code'] = extract.returncode
            assert extract.returncode == 0, extract.stderr.decode(errors='replace')
            print(json.dumps({'package': item['package'], 'verified': True, 'bytes': len(raw)}), flush=True)
        font = ROOT / 'sysroot/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
        raw = font.read_bytes()
        assert digest(raw) == 'b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a'
        report['font'] = {'path': str(font), 'sha256': digest(raw), 'bytes': len(raw)}
        assert Path('/usr/share/X11/xkb/rules/evdev').is_file()
        report['host_xkb_rules'] = {'path': '/usr/share/X11/xkb/rules/evdev',
                                   'sha256': digest(Path('/usr/share/X11/xkb/rules/evdev').read_bytes())}
        report['usr_view_symlinks'] = usr_view(Path('/usr'), ROOT / 'sysroot/usr', ROOT / 'view02/usr')
        report['status'] = 'passed'
    except BaseException as error:
        report['status'] = 'failed'
        report['failure'] = repr(error)
        raise
    finally:
        report['finished_unix'] = time.time()
        write(ROOT / 'receipts/environment-restoration.json', report)


if __name__ == '__main__':
    main()
