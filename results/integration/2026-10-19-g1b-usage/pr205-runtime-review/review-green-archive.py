#!/usr/bin/env python3
"""Independently read a fixed A06 archive. Never execute archive code or ELFs."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import argparse
import hashlib
import json
import lzma
import os
import re
import subprocess
import zipfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def stream_sha(handle):
    value = hashlib.sha256()
    size = 0
    header = b''
    for block in iter(lambda: handle.read(1024 * 1024), b''):
        if len(header) < 64:
            header += block[:64 - len(header)]
        value.update(block)
        size += len(block)
    return value.hexdigest(), size, header


def parse_tests(raw, crate):
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '', raw.decode()).replace('\r', '')
    assert len(re.findall(r'\[ktest runner\] running \d+ tests in \d+ crates', text)) == 1
    headers = list(re.finditer(r'^running (\d+) tests in crate "([^"]+)"$', text, re.M))
    target = [h for h in headers if h[2] == crate]
    assert len(target) == 1
    head = target[0]
    end = next((h.start() for h in headers if h.start() > head.start()), len(text))
    section = text[head.end():end]
    summaries = list(re.finditer(r'^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) filtered out\.$', section, re.M))
    assert len(summaries) == 1
    summary = summaries[0]
    body = section[:summary.start()]
    starts = list(re.finditer(r'^test ([\w:]+) \.\.\.', body, re.M))
    assert len(starts) == len({s[1] for s in starts}) == int(head[1])
    assert all(s[1].startswith(crate.replace('-', '_') + '::') for s in starts)
    tests = []
    for index, start in enumerate(starts):
        stop = starts[index + 1].start() if index + 1 < len(starts) else len(body)
        segment = body[start.end():stop]
        outcomes = re.findall(r' (ok|FAILED)\n', segment)
        terminal = re.search(r' (ok|FAILED)\n\n*\Z', segment)
        assert len(outcomes) == 1 and terminal is not None and outcomes[0] == terminal[1], start[1]
        tests.append({'name': start[1], 'outcome': terminal[1], 'soft_skip_reasons': re.findall(r'\[skipped: ([^\]]+)\]', segment)})
    status, passed, failed, filtered = summary.groups()
    passed, failed, filtered = int(passed), int(failed), int(filtered)
    assert passed == sum(t['outcome'] == 'ok' for t in tests)
    assert failed == sum(t['outcome'] == 'FAILED' for t in tests) and filtered == 0
    assert (status == 'ok') == (failed == 0)
    assert text.count('[ktest runner] All crates tested.') == int(status == 'ok')
    assert not any(marker in text for marker in ['An uncaught panic occurred:', 'Uncaught panic:', 'Non-resettable panic!', 'The panic handler panicked', 'Panicked in `PanicGuard`'])
    soft = sum(len(t['soft_skip_reasons']) for t in tests)
    return {'crate': crate, 'declared': int(head[1]), 'passed': passed, 'failed': failed,
            'filtered': filtered, 'soft_skipped': soft, 'exercised_passed_lower_bound': passed - soft,
            'soft_skip_tests': [t for t in tests if t['soft_skip_reasons']], 'tests': tests}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--tree', required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--independent-source-map', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    with args.archive.open('rb') as handle:
        archive_sha, archive_size, _ = stream_sha(handle)
    assert archive_sha == args.expected_sha256
    env = dict(os.environ, GIT_NO_LAZY_FETCH='1')
    tree = subprocess.check_output(['git', 'rev-parse', args.head + '^{tree}'], cwd=args.repo, env=env).decode().strip()
    assert tree == args.tree
    tree_files = {}
    for line in subprocess.check_output(['git', 'ls-tree', '-r', '-z', args.head], cwd=args.repo, env=env).split(b'\0'):
        if not line:
            continue
        info, path = line.split(b'\t', 1)
        mode, kind, blob = info.decode().split()
        assert kind == 'blob'
        tree_files[path.decode()] = {'mode': mode, 'git_blob': blob}
    derived_source = json.loads(args.independent_source_map.read_text()) if args.independent_source_map else None
    if derived_source:
        assert (derived_source['head'], derived_source['tree']) == (args.head, args.tree)
    with zipfile.ZipFile(args.archive) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        assert len(names) == len(set(names))
        for name in names:
            path = PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in name
        records = []

        def read(name, limit=16 * 1024 * 1024):
            info = archive.getinfo(name)
            assert info.file_size <= limit
            value = archive.read(name)
            assert len(value) == info.file_size
            records.append({'archive_member': name, 'bytes': len(value), 'sha256': sha(value)})
            return value

        def obj(name):
            return json.loads(read(name))

        def save_raw(name, data):
            dest = args.output / 'selected' / (name + '.xz')
            dest.parent.mkdir(parents=True, exist_ok=True)
            packed = lzma.compress(data, preset=6)
            assert lzma.decompress(packed) == data
            dest.write_bytes(packed)

        def kernel(name, expected_sha, expected_size):
            with archive.open(name) as handle:
                value, size, header = stream_sha(handle)
            assert (value, size) == (expected_sha, expected_size), name
            assert header[:6] == b'\x7fELF\x02\x01' and header[18:20] == b'\x03\x00', name
            return {'archive_member': name, 'bytes': size, 'sha256': value, 'elf_class': 64, 'endianness': 'little', 'e_machine': 3, 'purpose': 'OSDK QEMU multiboot marker for the x86_64 guest; not a claim of an i386 product.'}

        snapshots = []
        before = None
        for suffix in ['source-before.json', 'source-after-boot.json', 'source-after-guest.json']:
            name = '_temp/a06-queryabi-candidate/' + suffix
            data = read(name)
            snapshot = json.loads(data)
            assert (snapshot['head'], snapshot['tree']) == (args.head, args.tree)
            assert set(snapshot['files']) == set(tree_files)
            assert all({k: row[k] for k in ['mode', 'git_blob']} == tree_files[p] for p, row in snapshot['files'].items())
            if derived_source:
                assert snapshot['files'] == derived_source['files']
            if before is None:
                before = snapshot
                save_raw(name, data)
            else:
                assert snapshot == before
            snapshots.append({'member': name, 'sha256': sha(data), 'bytes': len(data), 'file_count': len(snapshot['files']), 'all_paths_modes_blobs_match_exact_git_tree': True, 'all_independent_sha256_size_matches': bool(derived_source)})

        crates, kernels = [], []
        for crate in ['aster-core', 'ostd']:
            prefix = '_temp/a06-ktest/' + crate
            qname = prefix + '/guests/guest-001/qemu.json'
            sname = prefix + '/guests/guest-001/serial.log'
            qraw, sraw = read(qname), read(sname)
            qemu = json.loads(qraw)
            assert qemu['serial_sha256'] == sha(sraw) and qemu['raw_exit_code'] == 33 and qemu['timed_out'] is False and qemu['crate'] == crate
            parsed = parse_tests(sraw, crate)
            assert parsed['failed'] == 0
            published = obj(prefix + '/result.json')['guests'][0]
            for key in ['declared', 'passed', 'failed', 'filtered', 'soft_skipped', 'exercised_passed_lower_bound']:
                assert parsed[key] == published[key]
            parsed.update(serial_member=sname, serial_sha256=sha(sraw), serial_bytes=len(sraw), qemu_member=qname, qemu_record_sha256=sha(qraw), raw_qemu_exit=33, timed_out=False, recorded_qemu_sha256=qemu['qemu_sha256'], recorded_profile=qemu['profile'])
            artifact = qemu['artifacts']['-kernel']
            if crate == 'aster-core':
                kname = '_temp/a06-owner-negative/green-core-kernel.elf'
            else:
                matched = [n for n in names if n.endswith('/kernel/asterinas/target/osdk/ostd/ostd-osdk-bin.elf')]
                assert len(matched) == 1
                kname = matched[0]
            kernels.append(kernel(kname, artifact['sha256'], artifact['size']))
            crates.append(parsed)
            save_raw(qname, qraw)
            save_raw(sname, sraw)

        result_raw = read('_temp/a06-queryabi-candidate/result.json')
        product = json.loads(result_raw)
        assert product['source_head'] == args.head and product['source_tree'] == args.tree
        assert product['passed'] is True and product['qemu_exit'] == 33 and product['timed_out'] is False
        product_member = '_temp/a06-queryabi-candidate/product-kernel.elf'
        kernels.append(kernel(product_member, product['kernel_elf_sha256'], archive.getinfo(product_member).file_size))
        product_serial = read('_temp/a06-queryabi-candidate/serial.log')
        assert sha(product_serial) == product['raw_serial_sha256'] and len(product_serial) == product['raw_serial_size']
        clean = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', product_serial.decode()).splitlines()
        assert all(clean.count(name) == 1 for name in product['marker_counts'])
        assert all(product[name] is False for name in ['hepta_durability', 'native_grants', 'native_resource_effects', 'production_ready', 'smp_qualification'])
        save_raw('_temp/a06-queryabi-candidate/result.json', result_raw)
        save_raw('_temp/a06-queryabi-candidate/serial.log', product_serial)
        report = {
            'schema': 1, 'reviewed_at_utc': datetime.now(timezone.utc).isoformat(),
            'kind': 'New independent read of original artifact bytes, not a product rerun and not restoration of lost old report bytes.',
            'archive': {'path': str(args.archive), 'sha256': archive_sha, 'bytes': archive_size, 'members': len(infos), 'uncompressed_bytes': sum(i.file_size for i in infos)},
            'head': args.head, 'tree': args.tree,
            'source_snapshots': snapshots, 'source_file_count': len(before['files']),
            'crates': crates,
            'reported_passed': sum(c['passed'] for c in crates),
            'soft_skipped': sum(c['soft_skipped'] for c in crates),
            'exercised_passed_lower_bound': sum(c['exercised_passed_lower_bound'] for c in crates),
            'kernels_independently_stream_hashed': kernels,
            'product_queryabi': {'receipt_sha256': sha(result_raw), 'kernel_sha256': product['kernel_elf_sha256'], 'raw_qemu_exit': 33, 'serial_sha256': sha(product_serial), 'each_recorded_marker_exactly_once': True, 'disabled_operations': 4, 'native_grants': False, 'native_resource_effects': False, 'hepta_durability': False},
            'reviewed_raw_member_identities': records,
            'scope_limits': ['This script independently reviews the complete green core/OSTD suites and ordinary QueryAbi source/ELF/serial binding. It does not by itself qualify all seven negative controls, full32, SCM_RIGHTS, RLIMIT_NOFILE or CPU timing.', 'QEMU executable identities are preserved in original records; the host QEMU executable is not present in this artifact and is not independently rehashed here.', 'No code or executable from the archive was run. No old lost review SHA is reused.'],
            'passed': True,
        }
        encoded = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode()
        (args.output / 'review.json').write_bytes(encoded)
        selected = []
        for path in sorted((args.output / 'selected').rglob('*')):
            if path.is_file():
                data = path.read_bytes()
                selected.append({'path': str(path.relative_to(args.output)), 'bytes': len(data), 'sha256': sha(data)})
        manifest = {'review': {'path': 'review.json', 'bytes': len(encoded), 'sha256': sha(encoded)}, 'selected': selected, 'scope': 'New selected byte copies, compressed losslessly; originals remain inside the fixed ZIP.'}
        (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print(json.dumps({'output': str(args.output), 'passed': True, 'reported_passed': report['reported_passed'], 'soft_skipped': report['soft_skipped'], 'exercised_passed_lower_bound': report['exercised_passed_lower_bound'], 'source_files': report['source_file_count'], 'review_sha256': sha(encoded), 'review_bytes': len(encoded), 'selected_files': len(selected)}))


if __name__ == '__main__':
    main()
