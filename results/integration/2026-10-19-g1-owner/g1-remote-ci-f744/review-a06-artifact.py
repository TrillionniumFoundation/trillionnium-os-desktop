#!/usr/bin/env python3
"""Read-only review of downloaded A06 CI bytes; never executes artifact programs."""
from pathlib import Path, PurePosixPath
import ast, collections, datetime, gzip, hashlib, json, re, stat, struct, subprocess, tomllib, zipfile

BASE = Path('/workspace/scratch/499c7902de8e/r10-evidence/g1-remote-ci')
REPO = Path('/workspace/scratch/499c7902de8e/r10-g1-queryabi')
LOCAL = '4e077aef4913179a68aa0d814018ce1a9d87cafc'
HEAD = 'f744fb248a6d264676d0b892d21d6c4582d72d0f'
TREE = '4e42c3833746cd2684d0a75020d73286820457e6'
ZIP = BASE / 'a06-exact-kernel-ktest-39193294713.zip'
ZSHA = 'bf5f89c4ef49d1be7c2e98240737982d9c38e5a3c787dc9428f475ae9f526135'
ANSI = re.compile(r'\x1b\[[0-9;]*m')
checks = []
def need(condition, label):
    if not condition:
        raise ValueError(label)
    checks.append(label)
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def git(*args, input=None):
    return subprocess.check_output(['git', '--no-optional-locks', '-C', str(REPO), *args], input=input)
def source(path):
    return git('show', LOCAL + ':' + path)
def clean(raw):
    return ANSI.sub('', raw.decode('utf-8')).replace('\r\n', '\n')
def cpio(raw):
    data = gzip.decompress(raw)
    offset = 0
    result = {}
    while True:
        header = data[offset:offset + 110]
        need(len(header) == 110 and header[:6] == b'070701', 'cpio header at ' + str(offset))
        fields = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        offset += 110
        name = data[offset:offset + fields[11]]
        need(name.endswith(b'\0'), 'cpio terminated filename')
        name = name[:-1].decode()
        offset = (offset + fields[11] + 3) & ~3
        payload = data[offset:offset + fields[6]]
        need(len(payload) == fields[6], 'cpio complete payload ' + name)
        offset = (offset + fields[6] + 3) & ~3
        if name == 'TRAILER!!!':
            need(not any(data[offset:]), 'cpio trailing zero padding')
            break
        path = PurePosixPath(name)
        need(not path.is_absolute() and '..' not in path.parts and name not in result, 'cpio safe unique path ' + name)
        result[name] = {'fields': fields, 'data': payload}
    return result
def cpio_changes(before, after, binary_name, binary, marker=None, vcpus=1):
    additions = set(after) - set(before)
    expected = {binary_name} | ({'.hepta-disposable-guest'} if marker else set())
    need(additions == expected and not (set(before) - set(after)), 'cpio exact added members')
    changed = []
    for name in before:
        a, b = before[name], after[name]
        if a['data'] != b['data']:
            changed.append(name)
        # File length can change for init; all other recorded fields must stay equal.
        af, bf = a['fields'][:], b['fields'][:]
        af[6] = bf[6] = 0
        need(af == bf, 'cpio retained metadata ' + name)
    need(changed == ['init'], 'cpio only existing init changes')
    need(after[binary_name]['data'] == binary, 'cpio embedded exact probe ELF')
    need(after[binary_name]['fields'][1] == 0o100755, 'cpio executable probe mode')
    if marker:
        need(after['.hepta-disposable-guest']['data'] == (marker + '\n').encode(), 'cpio disposable marker exact kernel digest')
    init = after['init']['data']
    original_init = before['init']['data']
    boot_marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    need(original_init.count(boot_marker) == 1, 'original init unique injection site')
    command = b'/bin/hos2-queryabi\n' if not marker else b'/bin/cpu-cap-probe --asterinas-disposable-guest\n'
    expected_init = original_init.replace(boot_marker, command + boot_marker)
    if vcpus == 2:
        need(expected_init.count(b'test "$cpu_count" -eq 1') == 1, 'original init unique CPU-count admission')
        expected_init = expected_init.replace(b'test "$cpu_count" -eq 1', b'test "$cpu_count" -eq 2')
    need(init == expected_init, 'cpio init exact fixed injection and CPU-count-only change')
    need(init.count(b'echo "TRILLIONNIUM_A01_BOOT_OK"') == 1, 'cpio one boot marker')
    need(b'test "$cpu_count" -eq ' + str(vcpus).encode() in init, 'cpio exact vcpu admission ' + str(vcpus))
    return {'before_members': len(before), 'after_members': len(after), 'added': sorted(additions), 'changed_existing': changed, 'init_sha256': sha(init)}

def main():
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    need(ZIP.stat().st_size == 18333821 and sha(ZIP.read_bytes()) == ZSHA, 'GitHub archive digest and size')
    need(git('rev-parse', LOCAL + '^{tree}').decode().strip() == TREE, 'local immutable Git tree equals remote tree')
    first = json.loads((BASE / 'observation-001-031046.json').read_text())
    commit = next(x['response_json'] for x in first['observations'] if x['key'] == 'commit')
    need(commit['sha'] == HEAD and commit['tree']['sha'] == TREE, 'GitHub commit API exact head and tree')
    job_observation = json.loads((BASE / 'observation-004-0317-a06.json').read_text())
    job = job_observation['observations'][0]['response_json']['jobs'][0]
    need(job['id'] == 117870536573 and job['head_sha'] == HEAD and job['conclusion'] == 'success', 'exact A06 job terminal identity')
    need(len(job['steps']) == 12 and all(s['conclusion'] == 'success' for s in job['steps']), 'all twelve recorded A06 job steps succeed')
    job_log = (BASE / 'a06-job-117870536573.log').read_bytes()
    need(HEAD.encode() in job_log and b'##[error]' not in job_log, 'full A06 decoded log binds head and has no error annotation')
    with zipfile.ZipFile(ZIP) as z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        need(len(names) == len(set(names)) == 76, '76 unique ZIP members')
        for i in infos:
            p = PurePosixPath(i.filename)
            need(not p.is_absolute() and '..' not in p.parts and '\\' not in i.filename and not (i.flag_bits & 1) and not stat.S_ISLNK(i.external_attr >> 16), 'safe ZIP member ' + i.filename)
        need(z.testzip() is None, 'all ZIP CRC values correct')
        rows = {n: {'sha256': sha(z.read(n)), 'bytes': z.getinfo(n).file_size} for n in names}
        need(sum(v['bytes'] for v in rows.values()) == 44268904, 'exact total uncompressed bytes')
        read = z.read
        def obj(n):
            return json.loads(read(n))
        qp = '_temp/a06-queryabi-candidate/'
        snapnames = [qp + 'source-' + s + '.json' for s in ('before', 'after-boot', 'after-guest')]
        snaps = [obj(n) for n in snapnames]
        need(read(snapnames[0]) == read(snapnames[1]) == read(snapnames[2]), 'three source snapshot byte streams identical')
        need(all(s['head'] == HEAD and s['tree'] == TREE and len(s['files']) == 5851 for s in snaps), 'three snapshots exact remote head tree and 5851 files')
        tree = {}
        for row in git('ls-tree', '-rz', LOCAL).split(b'\0'):
            if not row: continue
            fields, path = row.split(b'\t', 1)
            mode, kind, oid = fields.decode().split()
            need(kind == 'blob', 'Git tracked item is a blob')
            tree[path.decode()] = {'mode': mode, 'oid': oid}
        need(set(tree) == set(snaps[0]['files']), 'complete tracked Git file set matches snapshot')
        oids = sorted({v['oid'] for v in tree.values()})
        stream = git('cat-file', '--batch', input=('\n'.join(oids) + '\n').encode())
        cursor = 0
        blobs = {}
        for oid in oids:
            end = stream.index(b'\n', cursor)
            got, kind, size = stream[cursor:end].decode().split()
            size = int(size)
            cursor = end + 1
            data = stream[cursor:cursor + size]
            need(got == oid and kind == 'blob' and len(data) == size and stream[cursor + size:cursor + size + 1] == b'\n', 'complete raw Git batch blob')
            need(hashlib.sha1(b'blob ' + str(size).encode() + b'\0' + data).hexdigest() == oid, 'raw Git blob object hash')
            blobs[oid] = {'sha256': sha(data), 'size': size}
            cursor += size + 1
        need(cursor == len(stream), 'Git batch stream consumed exactly')
        total = 0
        for name, v in tree.items():
            entry = snaps[0]['files'][name]
            b = blobs[v['oid']]
            need(entry == {'mode': v['mode'], 'git_blob': v['oid'], 'size': b['size'], 'sha256': b['sha256']}, 'source file identity ' + name)
            total += b['size']
        env = obj('_temp/a06-ktest/environment.json')
        need(env['git_head'] == HEAD and env['git_status'] == '' and env['test_name'] is None, 'ktest clean exact head and no test name filter')
        for path, digest in env['build_inputs_sha256'].items():
            need(sha(source(path)) == digest, 'ktest build input ' + path)
        lock_review = {}
        for crate, count in [('ostd', 97), ('aster-core', 200)]:
            paths = ['_temp/a06-ktest/' + crate + '/generated.Cargo.lock',
                     '_temp/a06-prepared-locks/' + crate + '.Cargo.lock',
                     'trillionnium-os-desktop/trillionnium-os-desktop/support/build/ktest/locks/' + crate + '.Cargo.lock']
            expected = source('support/build/ktest/locks/' + crate + '.Cargo.lock')
            need(all(read(n) == expected for n in paths), 'generated prepared archived and Git locks exact ' + crate)
            need(len(tomllib.loads(expected.decode())['package']) == count, 'package count ' + crate)
            reports = ['_temp/a06-prepared-locks/' + crate + '.json',
                       'trillionnium-os-desktop/trillionnium-os-desktop/support/build/ktest/locks/' + crate + '.json']
            need(all(read(n) == source('support/build/ktest/locks/' + crate + '.json') for n in reports), 'prepared lock reports equal frozen Git ' + crate)
            lock_review[crate] = {'sha256': sha(expected), 'package_count': count, 'raw_copies': paths}
        for p in ['_temp/a06-ktest/source-inputs.json', qp + 'product-boot/source-inputs.json', '_temp/a06-kernel-build/source-inputs.json']:
            pin = obj(p)
            need(pin['passed'] is True and pin['errors'] == [], 'upstream source gate passes ' + p)
            for path, digest in pin['input_sha256'].items():
                need(sha(source('kernel/asterinas/' + path)) == digest, 'source gate measured exact Git input ' + path)
        elf_entries = []
        for path in names:
            raw = read(path)
            if not raw.startswith(b'\x7fELF'): continue
            need(raw[4:6] == b'\x02\x01', 'ELF64 little-endian ' + path)
            etype, machine = struct.unpack_from('<HH', raw, 16)
            need(etype == 2 and machine in (3, 62), 'expected static executable ELF header ' + path)
            phoff = struct.unpack_from('<Q', raw, 32)[0]
            phentsize, phnum = struct.unpack_from('<HH', raw, 54)
            need(phentsize >= 56 and phoff + phentsize * phnum <= len(raw), 'complete ELF program headers ' + path)
            ph_types = [struct.unpack_from('<I', raw, phoff + phentsize * i)[0] for i in range(phnum)]
            need(3 not in ph_types, 'ELF has no PT_INTERP dynamic loader ' + path)
            elf_entries.append({'path': path, **rows[path], 'elf_class': 64, 'e_type': etype, 'e_machine': machine, 'entry': hex(struct.unpack_from('<Q', raw, 24)[0])})
        need(len(elf_entries) == 7 and len({v['sha256'] for v in elf_entries}) == 6, 'seven ELF members with six byte identities')
        kr = {}
        ktest_report = obj('_temp/a06-ktest/result.json')
        need(ktest_report['passed'] is True, 'ktest aggregate passed')
        native_source = source('kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native/tests.rs').decode()
        new_names = re.findall(r'#\[ktest\]\s*fn\s+(\w+)', native_source)
        need(len(new_names) == 10 and len(set(new_names)) == 10, 'ten named G1 tests in frozen source')
        for crate, expected, soft in [('ostd', 221, 3), ('aster-core', 179, 0)]:
            base = '_temp/a06-ktest/' + crate + '/'
            raw = read(base + 'guests/guest-001/serial.log')
            text = clean(raw)
            starts = re.findall(r'^test ([\w:]+) \.\.\.', text, re.M)
            summary = re.findall(r'^test result: ok\. (\d+) passed; (\d+) failed; (\d+) filtered out\.$', text, re.M)
            need(summary == [(str(expected), '0', '0')], 'actual serial final counts ' + crate)
            need(len(starts) == len(set(starts)) == expected, 'actual unique test starts ' + crate)
            skips = re.findall(r'\[skipped: ([^\]]+)\]', text)
            need(len(skips) == soft, 'actual soft skip count ' + crate)
            need(text.count('running ' + str(expected) + ' tests in crate "' + crate + '"') == 1, 'actual selected crate declaration ' + crate)
            record = obj(base + 'guests/guest-001/qemu.json')
            need(record['raw_exit_code'] == 33 and not record['timed_out'] and record['serial_sha256'] == sha(raw), 'actual recorded QEMU serial binding ' + crate)
            need(record['profile'] == {'arch': 'x86_64', 'machine': 'q35', 'accel': 'tcg', 'cpu': 'max', 'vcpus': 1, 'memory_mib': 512, 'network': False, 'data_disks': False}, 'actual minimal TCG profile ' + crate)
            kp = record['artifacts']['-kernel']
            member = 'trillionnium-os-desktop/trillionnium-os-desktop/kernel/asterinas/target/osdk/' + crate + '/' + crate + '-osdk-bin.elf'
            need(rows[member] == {'bytes': kp['size'], 'sha256': kp['sha256']}, 'actual archived ktest ELF binding ' + crate)
            observed = next(c['guests'][0] for c in ktest_report['crates'] if c['guests'][0]['crate'] == crate)
            need(observed['passed'] == expected and observed['observed_test_starts'] == expected and observed['soft_skipped'] == soft and observed['exercised_passed_lower_bound'] == expected - soft, 'actual serial and ktest report agree ' + crate)
            if crate == 'aster-core':
                prefix = 'aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::tests::'
                native_hits = [prefix + n for n in new_names]
                need(all(starts.count(n) == 1 and re.search(r'^test ' + re.escape(n) + r' \.\.\. ok$', text, re.M) for n in native_hits), 'ten new G1 tests each exactly once and ok')
            else:
                native_hits = []
            kr[crate] = {'declared': expected, 'raw_passed': expected, 'failed': 0, 'filtered': 0, 'soft_skip_reasons': skips, 'executed_lower_bound': expected - soft, 'global_graph_line': next(l for l in text.splitlines() if '[ktest runner] running ' in l), 'test_names': starts, 'new_g1_test_names': native_hits, 'raw_qemu_exit': 33, 'duration_seconds': record['duration_seconds'], 'serial_member': base + 'guests/guest-001/serial.log', 'serial_sha256': sha(raw), 'elf_member': member}
        result = obj(qp + 'result.json')
        qraw = read(qp + 'serial.log')
        lines = clean(qraw).splitlines()
        need(result['passed'] is True and result['stage'] == 'complete' and result['qemu_exit'] == 33 and not result['timed_out'], 'candidate guest complete raw33')
        need(result['source_head'] == HEAD and result['source_tree'] == TREE and result['source_file_count'] == 5851 and result['source_inputs_unchanged'], 'candidate source receipt binding')
        need(result['raw_serial_sha256'] == sha(qraw) and result['raw_serial_size'] == len(qraw), 'candidate raw serial identity')
        expected_constants = {}
        for path in ['tests/kernel/control/run_queryabi_guest.py', 'tests/kernel/control/run_queryabi_candidate_guest.py']:
            for node in ast.parse(source(path).decode()).body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ['REQUIRED_SECURITY_MARKERS', 'EXPECTED_SUCCESS', 'OP_MARKERS', 'CANDIDATE_MARKER', 'FINAL_BOOT_MARKER']:
                    expected_constants[node.targets[0].id] = ast.literal_eval(node.value)
        expected_markers = (*expected_constants['REQUIRED_SECURITY_MARKERS'], *expected_constants['OP_MARKERS'], expected_constants['EXPECTED_SUCCESS'], expected_constants['CANDIDATE_MARKER'], expected_constants['FINAL_BOOT_MARKER'])
        need(set(result['marker_counts']) == set(expected_markers), 'candidate marker set equals independently read fixed Git constants')
        need(len(result['marker_counts']) == 14 and all(v == 1 and lines.count(k) == 1 for k, v in result['marker_counts'].items()), 'fourteen candidate markers exact lines exactly once')
        order = ['HEPTA_QUERYABI_OK ops=QueryAbi_only, process_bound_session=yes, denied_invalid=yes', 'HEPTA_DISABLED_READ_USAGE_OK', 'HEPTA_DISABLED_INSTALL_BUDGET_OK', 'HEPTA_DISABLED_QUERY_DELIVERY_OK', 'HEPTA_DISABLED_RETIRE_THROUGH_OK', 'HEPTA_QUERYABI_CANDIDATE_OK disabled_operations=4', 'TRILLIONNIUM_A01_BOOT_OK']
        need([lines.index(k) for k in order] == sorted(lines.index(k) for k in order), 'root QueryAbi disabled ops candidate completion boot order')
        need(not any(k in clean(qraw) for k in ['HEPTA_QUERYABI_FAIL', 'HEPTA_CANDIDATE_FAIL', 'panicked at', 'Uncaught panic:', 'TRILLIONNIUM_A01_BOOT_FAIL']), 'no guest failure markers')
        for field in ['native_grants', 'native_resource_effects', 'production_ready', 'smp_qualification', 'hepta_durability']:
            need(result[field] is False, 'candidate bounded claim ' + field)
        product = read(qp + 'product-kernel.elf')
        need(sha(product) == result['kernel_elf_sha256'] and product == read('_temp/a06-target/osdk/asterinas/asterinas-osdk-bin.elf'), 'ordinary copied ELF equals later SMP2 archive ELF')
        need(read('_temp/a06-kernel.sha256').decode().split()[0] == sha(product), 'workflow final kernel SHA receipt binds artifact')
        boot = obj(qp + 'product-boot/qemu.json')
        need(boot['raw_exit_code'] == 33 and not boot['timed_out'] and boot['artifacts']['-kernel']['sha256'] == sha(product), 'ordinary boot raw33 with same product ELF')
        need(sha(read(qp + 'product-boot/serial.log')) == boot['serial_sha256'], 'ordinary raw serial hash')
        need(clean(read(qp + 'product-boot/serial.log')).splitlines().count('TRILLIONNIUM_A01_BOOT_OK') == 1, 'ordinary exact boot marker')
        need(sha(read(qp + 'bios.bin')) == result['bios_sha256'] == boot['artifacts']['-bios']['sha256'], 'ordinary and candidate BIOS bytes bound')
        need(sha(read(qp + 'hos2-queryabi')) == result['probe_sha256'], 'candidate user ELF digest')
        need(sha(read(qp + 'product-boot/initramfs.cpio.gz')) == result['original_initramfs_sha256'], 'original initramfs digest')
        need(sha(read(qp + 'initramfs.cpio.gz')) == result['injected_initramfs_sha256'], 'injected initramfs digest')
        original = cpio(read(qp + 'product-boot/initramfs.cpio.gz'))
        changed = cpio_changes(original, cpio(read(qp + 'initramfs.cpio.gz')), 'bin/hos2-queryabi', read(qp + 'hos2-queryabi'))
        minlock = source('support/build/minimal/Cargo.lock')
        need(sha(minlock) == result['minimal_generated_lock_sha256'] and len(tomllib.loads(minlock.decode())['package']) == result['minimal_generated_package_count'] == 204, 'minimal generated lock report binds fixed Git lock')
        # No independently saved generated minimal raw lock is included in this workflow.
        probes = {}
        for cpus in [1, 2]:
            pp = '_temp/a06-probe-' + str(cpus) + 'vcpu/'
            p = obj(pp + 'result.json')
            need(p['candidate_sha256'] == sha(product) and read(pp + 'candidate_kernel.sha256') == (sha(product) + '\n').encode(), 'quota probe exact candidate ELF ' + str(cpus))
            need(p['source_pin'] == result['original_initramfs_sha256'] and p['initramfs_sha256'] == sha(read(pp + 'initramfs.cpio.gz')), 'quota probe initramfs hashes ' + str(cpus))
            need(p['mode'] == 'leaf' and p['quota_us'] == 1000 and p['period_us'] == 100000 and p['duration_seconds'] == 1 and p['max_cpu_percent'] == 3.0, 'bounded leaf quota parameters ' + str(cpus))
            need(not p['smp_qualified'] and not p['hepta_hos2_qualified'] and not p['host_cgroup_modified'] and p['guest_only'], 'bounded probe product claim ' + str(cpus))
            need(len(p['runs']) == 2, 'two actual quota runs ' + str(cpus))
            runs = []
            for r in p['runs']:
                raw = read(pp + 'serial-' + str(r['index']) + '.log')
                txt = clean(raw)
                samples = [{'label': a, 'wall_ns': int(b), 'cpu_ns': int(c), 'iterations': int(d)} for a, b, c, d in re.findall(r'ORGAN_CPU_SAMPLE label=(\S+) wall_ns=(\d+) cpu_ns=(\d+) iterations=(\d+)', txt)]
                need(samples == r['samples'] and len(samples) == 2 and [s['label'] for s in samples] == ['unlimited', 'one-percent-configured'], 'quota actual raw sample identity ' + str(cpus) + ':' + str(r['index']))
                need(txt.splitlines().count('ORGAN_PROBE_COMPLETE') == 1 and txt.splitlines().count('TRILLIONNIUM_A01_BOOT_OK') == 1, 'quota completion and clean boot exact once')
                need(txt.splitlines().count('TRILLIONNIUM_A01_CPU_COUNT=' + str(cpus)) == 1, 'actual guest reports admitted CPU count ' + str(cpus))
                need(r['qemu_exit'] == 33 and r['guest_complete'] and not r['panic'] and not r['policy_rt'] and not any(s in txt for s in ['panicked at', 'Uncaught panic:', 'ORGAN_PROBE_FAIL']), 'quota raw completion with no panic')
                percent = round(samples[1]['cpu_ns'] * 100 / samples[1]['wall_ns'], 3)
                need(percent == r['cpu_percent'] and percent <= 3, 'quota calculated ratio and explicit ceiling')
                unlimited = samples[0]['cpu_ns'] * 100 / samples[0]['wall_ns']
                if cpus == 2:
                    need(unlimited > 145 and p['configured_vcpus'] == p['parallel_pthreads'] == 2, 'two pthread actual parallel CPU baseline')
                runs.append({**r, 'unlimited_cpu_percent_recomputed': unlimited, 'raw_serial_sha256': sha(raw), 'raw_serial_member': pp + 'serial-' + str(r['index']) + '.log'})
            init_change = cpio_changes(original, cpio(read(pp + 'initramfs.cpio.gz')), 'bin/cpu-cap-probe', read(pp + 'probe'), sha(product), cpus)
            source_path = 'tests/organ_backend/' + ('cpu_cap_probe.c' if cpus == 1 else 'smp2/parallel_cpu_probe.c')
            expected_c = source(source_path).replace(b'e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63', sha(product).encode())
            need(read(pp + 'probe.c') == expected_c, 'actual bounded leaf probe C equals fixed Git source with only kernel SHA replacement ' + str(cpus))
            probes[str(cpus)] = {'runs': runs, 'initramfs_changes': init_change, 'candidate_sha256': p['candidate_sha256'], 'source_member': pp + 'probe.c', 'source_sha256': rows[pp + 'probe.c']['sha256']}
        workflow = source('.github/workflows/a06-kernel.yml').decode()
        need('ref: ${{ github.event.pull_request.head.sha || github.sha }}' in workflow, 'A06 checkout explicitly binds PR head')
        need('cmp "$prepared/ostd.Cargo.lock" support/build/ktest/locks/ostd.Cargo.lock' in workflow and 'cmp "$prepared/aster-core.Cargo.lock" support/build/ktest/locks/aster-core.Cargo.lock' in workflow, 'workflow compares both external prepare outputs')
        candidate_source = source('tests/kernel/control/run_queryabi_candidate_guest.py').decode()
        need('require(not git("status", "--porcelain", "--untracked-files=all")' in candidate_source, 'candidate full source snapshots require clean tracked and untracked status')
        output = {
            'schema': 'r10.g1-pr197.a06-ci-artifact-review.v1',
            'review_started_at_utc': started,
            'review_completed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'reviewer': '/root/r9_g1_contract', 'blocking_findings': [],
            'repository': 'TrillionniumFoundation/trillionnium-os-desktop',
            'source': {'remote_head': HEAD, 'tree': TREE, 'same_tree_local_commit': LOCAL, 'tracked_files_rehashed': len(tree), 'unique_git_blobs_rehashed': len(blobs), 'tracked_bytes': total, 'snapshot_members': snapnames, 'snapshot_sha256': sha(read(snapnames[0])), 'all_three_snapshots_equal': True, 'ktest_build_inputs_rehashed': len(env['build_inputs_sha256'])},
            'run': {'run_id': 39193294713, 'attempt': 1, 'job_id': job['id'], 'started_at': job['started_at'], 'completed_at': job['completed_at'], 'observed_at_utc': job_observation['finished_at_utc'], 'steps': job['steps']},
            'archive': {'name': ZIP.name, 'artifact_id': 12161280823, 'bytes': ZIP.stat().st_size, 'sha256': ZSHA, 'entries': 76, 'uncompressed_bytes': 44268904, 'manifest': 'a06-artifact-members.json', 'crc_and_path_checks': True},
            'job_log': {'file': 'a06-job-117870536573.log', 'bytes': len(job_log), 'sha256': sha(job_log)},
            'ktest': kr, 'locks': lock_review, 'elf_members': elf_entries,
            'queryabi': {'result_member': qp + 'result.json', 'result': result, 'initramfs_changes': changed, 'ordinary_boot_duration_seconds': boot['duration_seconds'], 'ordinary_boot_serial_sha256': boot['serial_sha256']},
            'quota_probes': probes,
            'counts': {'reported_ktest_passes': 400, 'ktest_soft_skipped': 3, 'ktest_execution_lower_bound': 397, 'new_g1_ktests': 10, 'queryabi_exact_markers': 14, 'quota_guests': 4, 'total_guest_invocations': 8, 'elf_members': 7, 'unique_elf_bytes': 6},
            'scope_and_limits': [
                'This is the actual ordinary GitHub A06 execution at f744, independently reviewed from downloaded bytes; no Rust/Cargo/QEMU or downloaded ELF was executed by this reviewer.',
                '179 aster-core plus 221 OSTD reported passes contain 3 explicit VMX/EPT soft skips; at least 397 test bodies exercised. Global graph totals 542/240 are not executed-test denominators.',
                'Ten G1-a tests exercise the existing controller seam; this result does not establish G1-b, complete SMP clock/accounting semantics, production grants, NativeBudget ioctl effects, or Hepta runtime durability.',
                'The QueryAbi guest contains all original security checks and four valid-shaped disabled operations rejected with EOPNOTSUPP. It does not grant authority or install resource limits through HOS2.',
                'Three full 5851-file clean-source snapshots bound the ordinary product and QueryAbi interval after ktest. They are not full snapshots around each ktest or after the later four quota guests. Post-checkout Actions cleanup success is not a separate final Git-clean measurement.',
                'Generated ktest locks are retained as raw bytes and equal prepared/committed copies. Ordinary minimal generated lock is represented by the fixed runner measurement and 204-package Git comparison; its generated raw file is not a separate ZIP member.',
                'The four short legacy quota guests are leaf-only, two repetitions at each of one and two configured vCPUs; two-vCPU parallel baseline and 3-percent ceiling are verified. They are not broad SMP qualification, sustained-load evidence, or new Hepta authorization tests.',
                'The GitHub QueryAbi interval did not reproduce the local untracked OSDK residue. Its successful clean gate does not identify the unknown local writer or invalidate the retained local failures.',
                'Other original-head gates G0 and A03 failed separately. A06 success does not imply PR197 all-gates acceptance or authorization to merge.'
            ],
            'checks_completed': len(checks)
        }
    (BASE / 'a06-artifact-review.json').write_text(json.dumps(output, indent=2) + '\n')
    (BASE / 'a06-review-checks.json').write_text(json.dumps({'schema': 'r10.g1-pr197.a06-ci-review-checks.v1', 'checks': checks}, indent=2) + '\n')
    print(json.dumps({'blocking_findings': [], 'checks_completed': len(checks), 'review': str(BASE / 'a06-artifact-review.json'), 'counts': output['counts'], 'source': output['source']}, indent=2))

if __name__ == '__main__':
    main()
