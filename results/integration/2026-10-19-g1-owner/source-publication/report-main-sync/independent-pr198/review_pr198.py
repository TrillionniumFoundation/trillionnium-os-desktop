#!/usr/bin/env python3
"""Read frozen PR198 Git/Actions bytes; never build or execute product code."""
from pathlib import Path, PurePosixPath
import collections
import datetime
import gzip
import hashlib
import importlib.util
import io
import json
import re
import stat
import struct
import traceback
import zipfile

HERE = Path(__file__).resolve().parent
REPO = Path('/workspace/scratch/499c7902de8e/r10-g1-delivery-main-sync')
HEAD = 'dafa1eba79cb1e17f880b5f0c5d57a80510d5d68'
MERGED = '7e859b98c58053b88ea2baabc3e5f645fd38dca5'
TREE = '354adb549b064c78477932ca943309694eb54356'
BASE = '71ce079c3218a8692476e4113b60c9d2c0d2a172'
ZIP_SHA = 'bce2548f17c9b9d22bfc10e398999dacea07e2c8942f497a87435c3d38e76545'
PREFIX = 'results/compat/2026-10-19-scm-cloexec/'
SCENARIOS = ('plain_receive', 'cloexec_multifd', 'peek_cloexec_then_plain',
             'peek_plain_then_cloexec', 'truncated_control', 'discarded_control',
             'no_control_message', 'credentials_with_rights', 'exec_inheritance')
CASES = tuple(f'{kind}.{case}' for kind in ('stream', 'datagram', 'seqpacket') for case in SCENARIOS)
COMPLETE = 'SCM_CLOEXEC_COMPLETE total=27 passed=27 failed=0'
BOOT = 'TRILLIONNIUM_A01_BOOT_OK'
checks = 0


def need(ok, label):
    global checks
    if not ok:
        raise ValueError(label)
    checks += 1


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ident(data):
    return {'bytes': len(data), 'sha256': sha(data)}


def lines(data):
    return re.sub(r'\x1b\[[0-9;]*m', '', data.decode()).splitlines()


def cpio(data):
    data = gzip.decompress(data)
    cursor = 0
    entries = {}
    while True:
        need(data[cursor:cursor + 6] == b'070701', 'newc header')
        fields = [int(data[cursor + 6 + i * 8:cursor + 14 + i * 8], 16) for i in range(13)]
        cursor += 110
        name_bytes = data[cursor:cursor + fields[11]]
        need(name_bytes[-1:] == b'\0', 'terminated newc name')
        name = name_bytes[:-1].decode()
        cursor = (cursor + fields[11] + 3) & ~3
        body = data[cursor:cursor + fields[6]]
        need(len(body) == fields[6], 'complete newc payload')
        cursor = (cursor + fields[6] + 3) & ~3
        if name == 'TRAILER!!!':
            need(not any(data[cursor:]), 'newc padding only after trailer')
            return entries
        need(name not in entries, 'unique newc entry')
        entries[name] = (fields, body)


def observed_cases(data):
    serial = lines(data)
    selected = [line for line in serial if line.startswith('SCM_CLOEXEC_CASE')]
    pattern = re.compile(r'SCM_CLOEXEC_CASE name=(\S+) result=(PASS|FAIL) line=(\d+)')
    matches = [pattern.fullmatch(line) for line in selected]
    need(len(matches) == 27 and all(matches), '27 complete case records')
    parsed = [(m[1], m[2], int(m[3])) for m in matches]
    need(tuple(row[0] for row in parsed) == CASES, 'exact distinct ordered 27-case denominator')
    return serial, parsed


def api(name):
    record = json.loads((HERE / f'{name}-observation.json').read_bytes())
    return json.loads(record['response_json_text']), record['completed_at_utc']


def review():
    # Reuse only this reviewer's frozen, already-reviewed Git byte reader.
    dependency = HERE.parent / 'g1-delivery-final-review/attempt-001/receipt-reviewer.py'
    code = dependency.read_bytes()
    need(sha(code) == 'a84350580cea43831ac290716ed02ae12dd10d084abf8039e21bd0e156301cb9',
         'fixed independent Git-reader dependency')
    spec = importlib.util.spec_from_file_location('frozen_git_reader', dependency)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    obj = module.Objects(REPO)
    try:
        tree = obj.tree(MERGED)
        before = obj.tree(BASE)
        need(obj.git('rev-parse', MERGED + '^{tree}').decode().strip() == TREE and
             obj.git('rev-parse', HEAD + '^{tree}').decode().strip() == TREE, 'source head and merged tree identical')
        changed = sorted(p for p in set(before) | set(tree) if before.get(p) != tree.get(p))
        comparison, _ = api('compare71ce_7e')
        need(len(changed) == 37 and set(changed) == {x['filename'] for x in comparison['files']}, 'exact 37-path actual Git/API diff')
        for row in comparison['files']:
            need(tree[row['filename']]['git_blob'] == row['sha'], 'changed Git blob equals independent API')
        production = [p for p in changed if p.startswith('kernel/')]
        need(len(production) == 5 and all('/socket/' in p or p.endswith('/syscall/recvmsg.rs') or
                                        p.endswith('/util/net/socket.rs') for p in production), 'only five socket/recvmsg production paths')
        source_rows = [{ 'path': p, **obj.identity(tree, p)} for p in changed]
        helpers = ['kernel/asterinas/kernel/core/src/fs/file/file_table.rs',
                   'kernel/asterinas/kernel/core/src/process/execve.rs',
                   'tests/organ_backend/run_guest_probe.py']
        source_helpers = [{'path': p, **obj.identity(tree, p), 'unchanged_from_G1_base': before[p] == tree[p]} for p in helpers]
        need(all(x['unchanged_from_G1_base'] for x in source_helpers), 'original FileTable/exec/CPIO helpers unchanged')

        raw = (HERE / 'pr198-a06-39198594211.zip').read_bytes()
        need((len(raw), sha(raw)) == (23402372, ZIP_SHA), 'original official artifact bytes')
        content = {}
        members = []
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for member in archive.infolist():
                p = PurePosixPath(member.filename)
                need(not p.is_absolute() and '..' not in p.parts and '\\' not in member.filename and
                     str(p) == member.filename and member.filename not in content and not member.is_dir() and
                     not member.flag_bits & 1 and not stat.S_ISLNK(member.external_attr >> 16), 'safe unique regular ZIP member')
                data = archive.read(member)  # zipfile verifies this member's CRC.
                need(len(data) == member.file_size, 'complete actual ZIP member')
                content[member.filename] = data
                members.append({'path': member.filename, **ident(data), 'crc32': f'{member.CRC:08x}',
                                'compressed_bytes': member.compress_size})
        need(len(members) == 93 and sum(x['bytes'] for x in members) == 56623284, '93 actual members / uncompressed bytes')
        jd = lambda path: json.loads(content[path])
        product_dir = '_temp/a06-queryabi-candidate/'
        guest_dir = '_temp/a04-scm-guest/'
        linux_dir = '_temp/a04-scm-linux/'
        product = jd(product_dir + 'result.json')
        guest = jd(guest_dir + 'result.json')
        snapshots = [content[product_dir + p] for p in ('source-before.json', 'source-after-boot.json', 'source-after-guest.json')]
        need(snapshots[0] == snapshots[1] == snapshots[2], 'three exact source snapshot bytes')
        snapshot = json.loads(snapshots[0])
        need(snapshot['head'] == HEAD and snapshot['tree'] == TREE and
             set(snapshot['files']) == set(tree) and len(tree) == 6426, '6426 complete source paths bound to fixed source')
        for path, entry in snapshot['files'].items():
            actual = obj.identity(tree, path)
            need(entry == {'git_blob': actual['git_blob'], 'mode': actual['mode'],
                           'size': actual['bytes'], 'sha256': actual['sha256']}, 'full source entry bytes/mode/blob')
        need(obj.data(tree, 'README.md') == b'', 'root README remains empty')
        need(product['passed'] is True and product['stage'] == 'complete' and product['source_inputs_unchanged'] is True and
             product['source_head'] == HEAD and product['source_tree'] == TREE and product['source_file_count'] == 6426 and
             product['product_wrapper_exit'] == 0 and product['product_boot_raw_exit'] == product['qemu_exit'] == 33 and
             product['timed_out'] is False, 'ordinary build/boot and QueryAbi complete')
        need(sha(content[product_dir + 'serial.log']) == product['raw_serial_sha256'], 'raw QueryAbi serial binding')
        query_lines = lines(content[product_dir + 'serial.log'])
        need(len(product['marker_counts']) == 14 and all(n == 1 and query_lines.count(m) == 1
             for m, n in product['marker_counts'].items()), 'all fourteen raw QueryAbi markers exact once')
        need(product['native_grants'] is False and product['native_resource_effects'] is False and
             product['hepta_durability'] is False, 'closed effect boundaries preserved')

        probe = content[linux_dir + 'probe.elf']
        kernel = content[product_dir + 'product-kernel.elf']
        need(probe == content[guest_dir + 'probe.elf'] and sha(probe) == guest['probe_sha256'] ==
             '9b80de2bb994d86d32592f5c2a4824c8406b41c1aedc74df299755c807065fb1', 'identical frozen Linux and guest ELF bytes')
        need(probe[:6] == b'\x7fELF\x02\x01' and int.from_bytes(probe[18:20], 'little') == 62, 'probe is x86_64 ELF64 LE')
        phoff = int.from_bytes(probe[32:40], 'little'); phsize = int.from_bytes(probe[54:56], 'little'); phnum = int.from_bytes(probe[56:58], 'little')
        need(phsize >= 56 and phoff + phsize * phnum <= len(probe) and
             all(int.from_bytes(probe[phoff + i * phsize:phoff + i * phsize + 4], 'little') != 3 for i in range(phnum)),
             'no dynamic PT_INTERP in the actual probe')
        need(kernel == content[guest_dir + 'kernel.elf'] and sha(kernel) == guest['kernel_sha256'] ==
             product['kernel_elf_sha256'] == '1145311a1335b866196019dfeea5937a86d4cbc4ff1efb222e8a229137b3737b',
             'ordinary product and compatibility guest share actual kernel bytes')
        need(sha(content[product_dir + 'result.json']) == guest['product_receipt_sha256'], 'exact accepted product receipt binding')
        need(content[linux_dir + 'probe.sha256'].decode().split()[0] == sha(probe), 'pre-Linux frozen probe digest retained')
        inputs = [line.split() for line in content[linux_dir + 'inputs.sha256'].decode().splitlines()]
        need(inputs[0] == [sha(obj.data(tree, 'tests/workloads/linux/scm_rights_cloexec_probe.c')),
                           'tests/workloads/linux/scm_rights_cloexec_probe.c'] and inputs[1][0] == sha(probe),
             'Linux compiler input source and output identities')
        linux_lines, linux_cases = observed_cases(content[linux_dir + 'stdout.log'])
        expected = [f'SCM_CLOEXEC_CASE name={name} result=PASS line=0' for name in CASES] + [COMPLETE]
        need(linux_lines == expected and content[linux_dir + 'stderr.log'] == b'' and
             content[linux_dir + 'exit-code.txt'].strip() == b'0', 'real Linux 27/27, exit zero and no stderr')
        guest_lines, guest_cases = observed_cases(content[guest_dir + 'serial.log'])
        need(all(r == 'PASS' and n == 0 for _, r, n in guest_cases), 'all raw guest cases pass')
        need(guest['cases'] == [{'name': n, 'result': r, 'line': l} for n, r, l in guest_cases], 'receipt cases equal raw serial')
        marker_values = [COMPLETE, 'SCM_CLOEXEC_PROCESS_EXIT=0', BOOT]
        need(all(guest_lines.count(m) == 1 for m in marker_values) and
             sum(line.startswith('SCM_CLOEXEC_COMPLETE') for line in guest_lines) == 1 and
             sum(line.startswith('SCM_CLOEXEC_PROCESS_EXIT=') for line in guest_lines) == 1,
             'guest completion, real process status and boot exact once')
        indices = [guest_lines.index(m) for m in marker_values]
        need(indices == sorted(indices) and all(i < indices[0] for i, line in enumerate(guest_lines)
                                               if line.startswith('SCM_CLOEXEC_CASE')), 'complete ordering after every case')
        need(not re.search(r'(?i)kernel panic|panicked at|fatal exception', '\n'.join(guest_lines)) and
             not any(line.startswith('SCM_CLOEXEC_ASSERT') for line in guest_lines), 'raw guest no panic or assertion')
        need(guest['passed'] is True and guest['qemu_exit'] == 33 and type(guest['qemu_exit']) is int and
             guest['timed_out'] is False and guest['guest_inputs_unchanged'] is True and
             (guest['source_head'], guest['source_tree']) == (HEAD, TREE), 'real guest success and reviewed source identity')
        need(ident(content[guest_dir + 'serial.log']) == {'bytes': guest['serial_bytes'], 'sha256': guest['serial_sha256']}, 'actual guest serial receipt binding')
        need(sha(obj.data(tree, 'tests/workloads/linux/run_scm_rights_cloexec_guest.py')) == guest['runner_sha256'] and
             sha(obj.data(tree, 'tests/organ_backend/run_guest_probe.py')) == guest['cpio_helper_sha256'], 'runner and CPIO helper bind to Git')
        need(content[guest_dir + 'bios.bin'] == content[product_dir + 'bios.bin'] and
             sha(content[guest_dir + 'bios.bin']) == guest['bios_sha256'], 'actual shared BIOS binding')
        args = guest['qemu_argv']
        need(args[args.index('-smp') + 1] == '1' and args[args.index('-accel') + 1] == 'tcg' and
             args[args.index('-machine') + 1] == 'q35' and '-nodefaults' in args and
             not any(x in args for x in ('-drive', '-nic', '-netdev')), 'bounded single-vCPU guest argv, no disks/network')
        original = obj.data(tree, 'support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz')
        need(sha(original) == guest['original_initramfs_sha256'] and
             sha(content[guest_dir + 'initramfs.cpio.gz']) == guest['initramfs_sha256'], 'original and guest initramfs hashes')
        old_init = cpio(original); new_init = cpio(content[guest_dir + 'initramfs.cpio.gz'])
        need(set(new_init) == set(old_init) | {'bin/scm-rights-cloexec-probe'}, 'one added initramfs member only')
        for name, (fields, body) in old_init.items():
            actual_fields, actual_body = new_init[name]
            if name.lstrip('./') == 'init':
                injection = b'if /bin/scm-rights-cloexec-probe; then\n    scm_probe_exit=0\nelse\n    scm_probe_exit=$?\nfi\necho "SCM_CLOEXEC_PROCESS_EXIT=$scm_probe_exit"\n'
                marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
                need(body.count(marker) == 1 and actual_body == body.replace(marker, injection + marker), 'exact bounded init insertion')
                need(fields[:6] + fields[7:] == actual_fields[:6] + actual_fields[7:], 'init metadata preserved except payload length')
            else:
                need((fields, body) == new_init[name], 'original initramfs entry preserved')
        need(new_init['bin/scm-rights-cloexec-probe'][1] == probe and
             new_init['bin/scm-rights-cloexec-probe'][0][1] == 0o100755, 'injected actual Linux probe and executable mode')

        host_logs = []
        for name in ('runner-tests.log', 'runner-tests-optimized.log'):
            text = content[linux_dir + name].decode()
            cases = re.findall(r'(?m)^(test_\S+) .* \.\.\. ok$', text)
            need(len(cases) == len(set(cases)) == 8 and re.search(r'Ran 8 tests in .*\n\nOK\s*$', text), 'eight actual host regressions per mode')
            host_logs.append({'member': linux_dir + name, 'distinct_tests': len(cases), **ident(content[linux_dir + name])})
        ktests = []
        for crate, expected_total, expected_skips in [('aster-core', 179, 0), ('ostd', 221, 3)]:
            stem = f'_temp/a06-ktest/{crate}/'
            serial = content[stem + 'guests/guest-001/serial.log']
            text = '\n'.join(lines(serial))
            matches = list(re.finditer(r'(?m)^test (\S+) \.\.\.', text))
            summary_start = text.index(f'test result: ok. {expected_total} passed; 0 failed; 0 filtered out.')
            started = [(match[1], text[match.end():matches[i + 1].start() if i + 1 < len(matches) else summary_start].strip())
                       for i, match in enumerate(matches)]
            need(len(started) == len({x[0] for x in started}) == expected_total and
                 all(outcome.endswith('ok') for _, outcome in started), 'all actual ktest starts and OK endings')
            skipped = [x for x in started if '[skipped:' in x[1]]
            need(len(skipped) == expected_skips and
                 f'test result: ok. {expected_total} passed; 0 failed; 0 filtered out.' in text, 'actual ktest summary and soft skips')
            qemu = jd(stem + 'guests/guest-001/qemu.json')
            need(qemu['raw_exit_code'] == 33 and qemu['timed_out'] is False and qemu['serial_sha256'] == sha(serial), 'ktest raw QEMU/serial binding')
            elf_path = 'trillionnium-os-desktop/trillionnium-os-desktop/kernel/asterinas/target/osdk/' + crate + '/' + crate + '-osdk-bin.elf'
            need(sha(content[elf_path]) == qemu['artifacts']['-kernel']['sha256'], 'actual archived ktest ELF binding')
            if crate == 'aster-core':
                source = obj.data(tree, 'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native/tests.rs').decode()
                names = re.findall(r'#\[ktest\]\s*fn\s+(\w+)', source)
                need(len(names) == 10 and all(sum(n.endswith('::native::tests::' + name) for n, _ in started) == 1 for name in names),
                     'ten G1-a owner tests exact once in raw serial')
            ktests.append({'crate': crate, 'reported_passed': expected_total, 'soft_skips': skipped,
                           'executed_passed_lower_bound': expected_total - expected_skips, 'raw_exit': 33,
                           'serial': ident(serial), 'elf': ident(content[elf_path])})
        quota = []
        for kind in ('1vcpu', '2vcpu'):
            report = jd(f'_temp/a06-probe-{kind}/result.json')
            need(report['candidate_sha256'] == sha(kernel) and len(report['runs']) == 2 and
                 all(run['qemu_exit'] == 33 and run['guest_complete'] is True and run['panic'] is False for run in report['runs']),
                 'two bounded quota run receipts on current kernel')
            quota.append({'configured_vcpus': 1 if kind == '1vcpu' else 2,
                          'recorded_percentages': [run['cpu_percent'] for run in report['runs']],
                          'raw_serial_members': [f'_temp/a06-probe-{kind}/serial-{i}.log' for i in (1, 2)],
                          'scope': 'receipt and archived serial identities retained; no broader quota oracle rerun'})

        manifest = json.loads(obj.data(tree, PREFIX + 'MANIFEST.json'))
        for name, entry in manifest['files'].items():
            need(ident(obj.data(tree, PREFIX + name)) == entry, 'all historical RED manifest members retain original bytes')
        legacy_probe = gzip.decompress(obj.data(tree, PREFIX + 'probe.elf.gz'))
        legacy_kernel = gzip.decompress(obj.data(tree, PREFIX + 'kernel.elf.gz'))
        red_raw = gzip.decompress(obj.data(tree, PREFIX + 'red-serial.log.gz'))
        red = json.loads(obj.data(tree, PREFIX + 'red-result.json'))
        legacy_linux = json.loads(obj.data(tree, PREFIX + 'linux-reference-unrestricted.json'))
        need(sha(legacy_probe) == red['probe_sha256'] == legacy_linux['elf_sha256'] ==
             '0723be7d0ba01f6a94fd4766e4aaf98bc6590de4bbfe431455aefcba8e8eeb56', 'legacy Linux/RED same original ELF bytes')
        need(sha(legacy_kernel) == red['kernel_sha256'] == 'f8785d9371f27b1f5e9ccd40da66ea25823ca50bfc7c431a89f20f88a45c4681' and
             sha(red_raw) == red['serial_sha256'], 'legacy kernel and raw RED serial hashes')
        red_lines, red_cases = observed_cases(red_raw)
        need(collections.Counter(r for _, r, _ in red_cases) == {'PASS': 3, 'FAIL': 24} and red['passed'] is False and
             red['qemu_exit'] == 33 and red_lines.count('SCM_CLOEXEC_PROCESS_EXIT=1') == 1, 'real complete historical 3/24 failure preserved')
        legacy_lines, _ = observed_cases(obj.data(tree, PREFIX + 'linux-reference-unrestricted.stdout.log'))
        need(legacy_lines == expected and legacy_linux['exit'] == 0 and
             obj.data(tree, PREFIX + 'linux-reference-unrestricted.stderr.log') == b'', 'legacy Linux same-ELF 27/27 reference')

        run, run_time = api('a06_run'); jobs, jobs_time = api('a06_jobs'); statuses, statuses_time = api('head_checks')
        need(run['id'] == 39198594211 and run['head_sha'] == HEAD and run['conclusion'] == 'success' and run['run_attempt'] == 1,
             'original successful exact-head workflow run')
        job = next(row for row in jobs['jobs'] if row['id'] == 117886620994)
        need(job['head_sha'] == HEAD and job['conclusion'] == 'success' and len(job['steps']) == 14 and
             all(x['conclusion'] == 'success' for x in job['steps']), 'all fourteen actual job steps success')
        need(len(statuses['check_runs']) == 4 and all(row['head_sha'] == HEAD and row['conclusion'] == 'success'
                                                  for row in statuses['check_runs']), 'four observed exact-head checks success')
        return {
            'source': {'head': HEAD, 'merge': MERGED, 'tree': TREE, 'base': BASE, 'changed_paths': source_rows,
                       'production_paths': production, 'unchanged_helpers': source_helpers,
                       'all_source_files_bound_to_Git': 6426, 'all_source_tracked_bytes': sum(r['size'] for r in snapshot['files'].values()),
                       'three_snapshot_bytes_sha256': sha(snapshots[0]), 'root_README_bytes': 0,
                       'G1_cpu_controller_os_control_HOS2_unchanged': True},
            'ci': {'run': run['id'], 'attempt': 1, 'job': job['id'], 'started_at': job['started_at'],
                   'completed_at': job['completed_at'], 'steps': job['steps'], 'observed_exact_head_checks': 4,
                   'observation_times': {'run': run_time, 'jobs': jobs_time, 'checks': statuses_time}},
            'artifact': {'id': 12162813771, 'zip_bytes': len(raw), 'zip_sha256': sha(raw),
                         'members': len(members), 'uncompressed_bytes': sum(x['bytes'] for x in members),
                         'all_member_CRC_read_checks_passed': True},
            'SCM_CLOEXEC_current_CI': {'profile': 'three Unix socket types times nine fixed scenarios',
                                     'linux_version': content[linux_dir + 'linux-version.txt'].decode().strip(),
                                     'linux_cases': 27, 'guest_cases': 27, 'cases': list(CASES),
                                     'same_actual_probe': ident(probe), 'ordinary_kernel': ident(kernel),
                                     'raw_serial': ident(content[guest_dir + 'serial.log']),
                                     'probe_exit': 0, 'raw_QEMU_exit': 33, 'elapsed_seconds': guest['elapsed_seconds'],
                                     'QEMU_version': guest['qemu_version'], 'qemu_argv': guest['qemu_argv'],
                                     'original_initramfs_members': len(old_init), 'injected_initramfs_members': len(new_init),
                                     'unchanged_all_other_initramfs_members': True, 'runner_host_regressions': host_logs},
            'G1_regression_scope': {'ktests': ktests, 'reported_total': 400, 'soft_skip_count': 3,
                                    'executed_passed_lower_bound': 397, 'owner_tests': 10,
                                    'QueryAbi_exact_markers': 14, 'effect_operations_still_disabled': 4,
                                    'quota_receipts': quota, 'reported_guest_invocations': 9},
            'legacy_RED': {'original_manifest_members': len(manifest['files']), 'probe': ident(legacy_probe),
                           'kernel': ident(legacy_kernel), 'Linux_host': legacy_linux['host'],
                           'linux_passed': 27, 'old_kernel_passed': 3, 'old_kernel_failed': 24,
                           'old_kernel_probe_exit': 1, 'old_kernel_raw_QEMU_exit': 33,
                           'historical_new_kernel_status_retained': manifest['new_kernel_result'],
                           'PR_body_additional_0723_on_new_kernel_GREEN_independently_verified': False},
            'source_semantics': [
                {'path': 'kernel/asterinas/kernel/core/src/syscall/recvmsg.rs', 'lines': [21, 43, 55],
                 'finding': 'Recognized caller flags survive the socket receive and flow into ancillary writing after dropping the initial file-table borrow. Returned flags union original socket and control flags with only the caller CMSG_CLOEXEC bit.'},
                {'path': 'kernel/asterinas/kernel/core/src/net/socket/unix/ctrl_msg.rs', 'lines': [107, 147, 155],
                 'finding': 'SCM_RIGHTS stores file Arcs without sender descriptor flags. Receive chooses CLOEXEC or empty from this call and inserts each descriptor with final flags under the original table write guard.'},
                {'path': 'kernel/asterinas/kernel/core/src/fs/file/file_table.rs', 'lines': [190, 208, 373],
                 'finding': 'Existing insert constructs FileTableEntry including its AtomicU8 flags before table.put publishes it. close_files_on_exec selects CLOEXEC entries.'},
                {'path': 'kernel/asterinas/kernel/core/src/process/execve.rs', 'lines': [382, 388],
                 'finding': 'Existing exec unshares the file table and takes its write guard for close_files_on_exec. This supports atomic descriptor publication by code inspection; no concurrent-exec stress run is inferred.'}],
            'limits': [
                'The 27-case exec scenario checks fork/exec inheritance and cleanup; it is not a concurrent descriptor-install/exec race stress test.',
                'FileTable resource limits, FD reservation/failure rollback and copyout-fault semantics remain separate work; the five-path patch does not close RLIMIT_NOFILE.',
                'Three full source snapshots cover the ordinary-product/QueryAbi interval before the additional SCM guest. The SCM runner separately binds its source helpers and unchanged guest inputs; no full post-SCM Git snapshot is claimed.',
                'The current CI ELF is 9b80... on Linux 6.17.0-1022-azure and the new kernel. Historical 0723... Linux 6.18.55/old-kernel RED is separately preserved. Additional 0723... new-kernel GREEN is a PR-body claim not independently evidenced in this retrieved ZIP.',
                'No downloaded executable, product test, Cargo or QEMU was run in this review. Old source-qualified G1-a conclusions are retained under their original heads; this new CI is a separate fixed-source result.',
                'This does not grant general SMP/IRQ, native authority or HOS2 effect, fixed Debian13 four-ELF profile, full Linux compatibility, Hepta device-effect, ARM kernel or physical/mobile device qualification.'],
            'members_manifest': {'schema': 'r10.pr198.a06-zip-members.v1', 'archive': 'pr198-a06-39198594211.zip',
                                 'archive_sha256': sha(raw), 'archive_bytes': len(raw), 'source_head': HEAD, 'source_tree': TREE,
                                 'members': members},
        }
    finally:
        obj.close()


def main():
    result_path = HERE / 'pr198-source-artifact-review-02.json'
    need(not result_path.exists(), 'new immutable review receipt')
    record = {'schema': 'r10.pr198.source-artifact-independent-review.v1',
              'reviewer': '/root/r9_g1_contract', 'started_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'review_script_sha256': sha(Path(__file__).read_bytes())}
    code = 0
    try:
        result = review()
        members = result.pop('members_manifest')
        data = (json.dumps(members, indent=2) + '\n').encode()
        with (HERE / 'pr198-a06-members.json').open('xb') as stream:
            stream.write(data)
        record.update(result)
        record['member_manifest'] = {'path': 'pr198-a06-members.json', **ident(data)}
        record.update(status='passed', blocking_findings=[])
    except Exception as error:
        code = 1
        record.update(status='failed', blocking_findings=[str(error)], traceback=traceback.format_exc())
    record.update(completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), checks_completed=checks)
    with result_path.open('x') as stream:
        stream.write(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': record['status'], 'blocking_findings': record['blocking_findings'], 'receipt': str(result_path)}))
    raise SystemExit(code)


if __name__ == '__main__':
    main()
