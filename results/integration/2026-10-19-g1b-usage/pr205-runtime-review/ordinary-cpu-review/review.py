#!/usr/bin/env python3
"""Read fixed Git and original CI ZIP bytes. Never run archived programs/helpers."""
import ast
import base64
import datetime
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import subprocess
import zipfile

BASE = Path('/workspace/scratch/499c7902de8e')
REPO = BASE / 'r11-g1b-usage'
ROOT = BASE / 'r11-evidence/pr205-runtime-review'
OUT = ROOT / 'ordinary-cpu-review'
HEAD = '4d3011cf9f92e25fc1b0d7371e9cdbbd5a8b7930'
TREE = '8eb809136a402cc54ba049b1e40dd174308c923f'
ARCHIVE_SHA = 'ef5d93159c1663fb30d3cf8e39e969525bbfa03b4fedc4db10ef4c87b035d655'
INITRD_SHA = '86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3'
BIOS_SHA = '1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735'
P = '_temp/'
BOOT = 'TRILLIONNIUM_A01_BOOT_OK'
checks, identities, selected, git_sources = [], {}, {}, {}
started = datetime.datetime.now(datetime.timezone.utc).isoformat()

def sha(b):
    return hashlib.sha256(b).hexdigest()

def require(condition, message):
    if not condition:
        raise ValueError(message)

def complete(name, detail):
    checks.append({'name': name, 'passed': True, 'detail': detail})

def strict_json(b):
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, 'duplicate JSON key ' + k)
            result[k] = v
        return result
    return json.loads(b, object_pairs_hook=pairs)

def read(name, keep=None):
    info = z.getinfo(name)
    require(info.file_size <= 80 * 1024 * 1024, 'unexpected oversized selected member')
    raw = z.read(info)  # zipfile checks this member's original CRC.
    identities[name] = {'bytes': len(raw), 'sha256': sha(raw), 'zip_crc32': f'{info.CRC:08x}'}
    if keep is None:
        keep = name.endswith(('.json', '.log', '.txt', '.sha256', '.c', '.sh'))
    if keep:
        raw.decode('utf-8')
        selected['original-members/' + name] = raw
    return raw

def js(name, keep=None):
    return strict_json(read(name, keep))

def pin(name, digest, size=None, keep=None):
    raw = read(name, keep)
    require(sha(raw) == digest and (size is None or len(raw) == size), 'member digest/size ' + name)
    return raw

def source(path):
    if path not in git_sources:
        raw = subprocess.check_output(['git', 'show', HEAD + ':' + path], cwd=REPO)
        line = subprocess.check_output(['git', 'ls-tree', HEAD, '--', path], cwd=REPO).decode()
        mode, kind, blob_path = line.split(' ', 2)
        blob, listed_path = blob_path.strip().split('\t')
        require(kind == 'blob' and listed_path == path, 'fixed Git source identity')
        require(hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == blob,
                'Git blob bytes')
        entry = snapshot['files'][path]
        require(entry == {'git_blob': blob, 'mode': mode, 'sha256': sha(raw), 'size': len(raw)},
                'ordinary snapshot source ' + path)
        git_sources[path] = {'git_blob': blob, 'mode': mode, 'sha256': sha(raw), 'bytes': len(raw)}
        selected['fixed-source/' + path] = raw
    return selected['fixed-source/' + path]

def constants(path, names):
    result = {}
    for node in ast.parse(source(path)).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    result[target.id] = ast.literal_eval(node.value)
    require(set(result) == set(names), 'missing literal source constant')
    return result

def lines(raw):
    return re.sub(rb'\x1b\[[0-9;]*m', b'', raw).decode('utf-8').splitlines()

def no_panic(raw):
    require(not re.search(rb'(?i)kernel panic|panicked at|fatal exception|uncaught panic', raw),
            'panic marker in successful serial')

def exact_order(ls, values):
    require(all(ls.count(x) == 1 for x in values), 'missing or repeated exact completion')
    require([ls.index(x) for x in values] == sorted(ls.index(x) for x in values), 'completion order')

def elf(raw, machine=62, static_only=False):
    require(raw[:6] == b'\x7fELF\x02\x01', 'not ELF64 little-endian')
    require(struct.unpack_from('<H', raw, 18)[0] == machine, 'ELF machine mismatch')
    phoff = struct.unpack_from('<Q', raw, 32)[0]
    entsize, count = struct.unpack_from('<HH', raw, 54)
    require(entsize >= 56 and phoff + entsize * count <= len(raw), 'ELF program table bounds')
    interp = any(struct.unpack_from('<I', raw, phoff + i * entsize)[0] == 3 for i in range(count))
    require(not static_only or not interp, 'static probe has interpreter')
    return {'bytes': len(raw), 'sha256': sha(raw), 'elf_class': 64, 'machine': machine, 'has_interp': interp}

def cpio(compressed):
    raw = gzip.decompress(compressed)
    require(len(raw) < 100 * 1024 * 1024, 'cpio decompression bound')
    result, pos = {}, 0
    while True:
        require(raw[pos:pos + 6] == b'070701' and pos + 110 <= len(raw), 'newc header')
        fields = [int(raw[pos + 6 + i * 8:pos + 14 + i * 8], 16) for i in range(13)]
        size, nsize = fields[6], fields[11]
        require(0 < nsize <= 4096 and pos + 110 + nsize <= len(raw), 'newc name bounds')
        name_raw = raw[pos + 110:pos + 110 + nsize]
        require(name_raw[-1:] == b'\0', 'newc name terminator')
        name = name_raw[:-1].decode('utf-8')
        start = (pos + 110 + nsize + 3) & ~3
        require(start + size <= len(raw), 'newc contents bounds')
        if name == 'TRAILER!!!':
            require(size == 0, 'newc trailer')
            break
        require(not name.startswith('/') and '..' not in name.split('/'), 'unsafe newc path')
        name = PurePosixPath(name).as_posix()
        require(name not in result, 'duplicate canonical newc path')
        result[name] = (fields, raw[start:start + size])
        pos = (start + size + 3) & ~3
    return result

def original_injection(image, probe, probe_path, expected_added):
    cp = cpio(image)
    require(set(original) <= set(cp), 'original initrd entries removed')
    require(set(cp) - set(original) == set(expected_added), 'unexpected injected paths')
    for name, (fields, content) in original.items():
        if name != 'init':
            require(cp[name] == (fields, content), 'original initrd entry changed ' + name)
    require(cp[probe_path][1] == probe, 'injected probe differs')
    require(cp['init'][1].count(BOOT.encode()) == 1, 'original boot marker changed')
    return cp

def api(kind):
    path = ROOT / ('api/final-a06-' + kind + '-completed.json')
    raw = path.read_bytes()
    selected['api/' + path.name] = raw
    return strict_json(strict_json(raw)['result']['structuredContent']['content'])

try:
    archive_path = ROOT / 'original.zip'
    with archive_path.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    require(archive_path.stat().st_size == 154979607 and digest == ARCHIVE_SHA, 'official ZIP identity')
    z = zipfile.ZipFile(archive_path)
    names = z.namelist()
    require(len(names) == len(set(names)) == 1172, 'ZIP duplicate/count')
    for info in z.infolist():
        require(not info.filename.startswith('/') and '..' not in info.filename.split('/'), 'ZIP path')
        require(stat.S_IFMT(info.external_attr >> 16) != stat.S_IFLNK, 'ZIP symlink')
    run, jobs, artifacts = api('run'), api('jobs'), api('artifacts')
    job = jobs['jobs'][0]
    artifact = next(a for a in artifacts['artifacts'] if a['id'] == 12182038203)
    require(run['id'] == 39240728276 and run['head_sha'] == HEAD and run['conclusion'] == 'success', 'run identity')
    require(job['id'] == 118020615962 and job['head_sha'] == HEAD and job['conclusion'] == 'success', 'job identity')
    require(artifact['digest'] == 'sha256:' + ARCHIVE_SHA and artifact['size_in_bytes'] == 154979607, 'artifact API')
    complete('official_archive_and_api_identity', {'run': run['id'], 'attempt': run['run_attempt'], 'job': job['id'],
             'started_at': job['started_at'], 'completed_at': job['completed_at'], 'members': 1172,
             'uncompressed_bytes': sum(i.file_size for i in z.infolist())})

    product = js(P + 'a06-queryabi-candidate/result.json')
    snap_raw = read(P + 'a06-queryabi-candidate/source-before.json', False)
    snapshot = strict_json(snap_raw)
    require(snapshot == js(P + 'a06-queryabi-candidate/source-after-boot.json', False)
            == js(P + 'a06-queryabi-candidate/source-after-guest.json', False), 'source snapshots changed')
    require((snapshot['head'], snapshot['tree'], len(snapshot['files'])) == (HEAD, TREE, 7054), 'snapshot head/tree/count')
    require(product['passed'] and product['source_inputs_unchanged'] and product['stage'] == 'complete'
            and product['product_wrapper_exit'] == 0 and product['product_boot_raw_exit'] == 33
            and product['qemu_exit'] == 33 and product['timed_out'] is False, 'ordinary product gate')
    kernel = pin(P + 'a06-queryabi-candidate/product-kernel.elf', product['kernel_elf_sha256'])
    kernel_id = elf(kernel, 3)
    require(pin(P + 'a06-target/osdk/asterinas/asterinas-osdk-bin.elf', sha(kernel)) == kernel, 'SMP-build ELF differs')
    product_sha = sha(read(P + 'a06-queryabi-candidate/result.json'))
    base_image = pin(P + 'a04-full-bundle/original-initramfs.cpio.gz', INITRD_SHA)
    original = cpio(base_image)
    bios = pin(P + 'a06-queryabi-candidate/bios.bin', BIOS_SHA)
    complete('ordinary_product_identity_and_three_snapshots', {'kernel': kernel_id, 'source_files': 7054,
             'full_git_inventory_review': 'sibling source/green review', 'native_effects': product['native_resource_effects']})

    scm_constants = constants('tests/workloads/linux/run_scm_rights_cloexec_guest.py', ['SCENARIOS'])
    scm_names = [s + '.' + c for s in ('stream', 'datagram', 'seqpacket') for c in scm_constants['SCENARIOS']]
    nofile_names = list(constants('tests/workloads/linux/run_rlimit_nofile_guest.py', ['CASE_ORDER'])['CASE_ORDER'])
    case_profiles = {}
    for tag, label, expected in (('scm', 'SCM_CLOEXEC', scm_names), ('nofile', 'NOFILE', nofile_names)):
        d = P + 'a04-' + tag + '-guest/'
        r = js(d + 'result.json')
        require(r['source_head'] == HEAD and r['source_tree'] == TREE and r['product_receipt_sha256'] == product_sha,
                tag + ' product binding')
        require(r['qemu_exit'] == 33 and r['timed_out'] is False and r['passed'] and r['guest_inputs_unchanged'], tag + ' guest result')
        require(pin(d + 'kernel.elf', r['kernel_sha256']) == kernel and pin(d + 'bios.bin', r['bios_sha256']) == bios, tag + ' boot input')
        probe = pin(d + 'probe.elf', r['probe_sha256'])
        elf_id = elf(probe, static_only=True)
        reference = P + 'a04-' + tag + '-linux/'
        require(pin(reference + 'probe.elf', sha(probe)) == probe, tag + ' Linux/guest ELF')
        stdout, stderr = read(reference + 'stdout.log'), read(reference + 'stderr.log')
        summary = f'{label}_COMPLETE total={len(expected)} passed={len(expected)} failed=0'
        expected_lines = [f'{label}_CASE name={name} result=PASS line=0' for name in expected] + [summary]
        require(stdout == ('\n'.join(expected_lines) + '\n').encode() and stderr == b''
                and read(reference + 'exit-code.txt') == b'0\n', tag + ' original Linux output')
        raw = pin(d + 'serial.log', r['serial_sha256'], r['serial_bytes']); ls = lines(raw); no_panic(raw)
        case_lines = [l for l in ls if l.startswith(label + '_CASE')]
        require(case_lines == expected_lines[:-1], tag + ' exact serial cases')
        exact_order(ls, [summary, label + '_PROCESS_EXIT=0', BOOT])
        require(ls.index(expected_lines[-2]) < ls.index(summary), tag + ' case order')
        require(not any(l.startswith((label + '_ASSERT', label + '_SETUP')) for l in ls), tag + ' failure marker')
        require(r['cases'] == [{'name': name, 'result': 'PASS', 'line': 0} for name in expected], tag + ' parsed result cases')
        require(r['original_initramfs_sha256'] == INITRD_SHA, tag + ' original image')
        image = pin(d + 'initramfs.cpio.gz', r['initramfs_sha256'])
        cp = cpio(image); probe_path = next(n for n,(f,b) in cp.items() if b == probe)
        original_injection(image, probe, probe_path, [probe_path])
        source_path = 'tests/workloads/linux/run_' + ('scm_rights_cloexec' if tag == 'scm' else 'rlimit_nofile') + '_guest.py'
        require(r['runner_sha256'] == sha(source(source_path)), tag + ' runner source')
        require(r['cpio_helper_sha256'] == sha(source('tests/organ_backend/run_guest_probe.py')), tag + ' cpio helper')
        source('tests/workloads/linux/' + ('scm_rights_cloexec' if tag == 'scm' else 'rlimit_nofile') + '_probe.c')
        if tag == 'nofile':
            lr = js(reference + 'result.json')
            require(sha(read(reference + 'input.json')) == lr['frozen_input_sha256'] and lr['process_exit'] == 0
                    and lr['timed_out'] is False and lr['process_group_cleanup_completed'] and lr['probe_inputs_unchanged'], 'NOFILE reference lifecycle')
            require(r['linux_reference_receipt_sha256'] == sha(read(reference + 'result.json')), 'NOFILE reference receipt')
            require(r['process_group_helper_sha256'] == sha(source('tests/integration/hepta/run_original_agentd.py')), 'process group helper')
            require(pin(P + 'a04-nofile-build/probe.elf', sha(probe)) == probe, 'NOFILE build ELF')
        case_profiles[tag] = {'cases': expected, 'count': len(expected), 'linux_process_exit': 0,
                              'guest_raw_qemu_exit': 33, 'identical_probe_elf': elf_id, 'stdout_sha256': sha(stdout),
                              'serial_sha256': sha(raw), 'serial_bytes': len(raw), 'guest_elapsed_seconds': r['elapsed_seconds']}
        complete(tag + '_same_elf_linux_and_exact_guest_cases', case_profiles[tag])

    bundle = P + 'a04-full-bundle/'
    bi = js(bundle + 'inputs.json'); contract_raw = pin(bundle + 'contract.json', bi['contract_sha256'])
    contract = strict_json(contract_raw)
    require(contract_raw == source('compat/linux/profiles/ubuntu24.04-x86_64-20261019.json'), 'full32 fixed contract')
    expected_names = list(constants('tests/workloads/linux/run_full_ubuntu_profile.py', ['CASE_ORDER'])['CASE_ORDER'])
    require([c['id'] for c in contract['cases']] == expected_names and len(expected_names) == 32, 'full32 complete fixed profile')
    for path, digest in bi['sources'].items():
        require(sha(source(path)) == digest, 'full32 source dependency ' + path)
    require((bi['source_head'], bi['source_tree']) == (HEAD, TREE), 'full32 bundle source')
    image = pin(bundle + 'full-initramfs.cpio.gz', bi['image_sha256'])
    require(pin(P + 'a04-full-guest/full-initramfs.cpio.gz', bi['image_sha256']) == image, 'full32 guest image')
    cp = cpio(image); rm = js(bundle + 'runtime-manifest.json')
    require(sha(read(bundle + 'runtime-manifest.json')) == bi['runtime_manifest_sha256'], 'runtime manifest input')
    require(rm['file_count'] == len(rm['files']) == 673 and len(rm['elf']) == 79, 'runtime file/ELF denominator')
    runtime_bytes = 0
    for item in rm['files']:
        fields, data = cp[item['path'].lstrip('/')]
        require(len(data) == item['bytes'] and sha(data) == item['sha256'] and fields[1] & 0o7777 == item['mode'],
                'runtime member input ' + item['path'])
        runtime_bytes += len(data)
    require(runtime_bytes == rm['regular_bytes'] == 43204445, 'runtime regular bytes')
    for path, item in rm['elf'].items():
        raw = cp[path.lstrip('/')][1]
        require(sha(raw) == item['sha256'], 'runtime ELF ' + path); elf(raw)
    workload_elfs = {}
    for name, item in bi['probe_elf'].items():
        raw = cp['usr/local/bin/a04/' + name][1]
        require(sha(raw) == item['sha256'] and len(raw) == item['bytes'], 'workload ELF')
        workload_elfs[name] = elf(raw)
        candidate = bundle + 'build/' + name
        if candidate in names:
            require(read(candidate) == raw, 'built and injected workload ELF')
    require(len(workload_elfs) == 5, 'five actual workload ELF')
    script = pin(bundle + 'full_guest.sh', bi['guest_script_sha256'])
    require(sum(b == script for _,b in cp.values()) == 1, 'injected full guest script')
    for case in contract['cases']:
        require(script.count(('echo A04_FULL_BEGIN=' + case['id'] + '\n').encode()) == 1, 'full32 script case')
    lr, gr = js(P + 'a04-full-linux/result.json'), js(P + 'a04-full-guest/result.json')
    require(gr['linux_reference_receipt_sha256'] == sha(read(P + 'a04-full-linux/result.json'))
            and gr['product_receipt_sha256'] == product_sha, 'full32 linked receipts')
    for r in (lr, gr):
        require(r['passed'] and r['image_sha256'] == sha(image) and r['input_sha256'] == sha(read(bundle + 'inputs.json'))
                and r['source_head'] == HEAD and r['source_tree'] == TREE and r['source_inputs_unchanged'], 'full32 result identity')
        require(r['pinned_debian13_qualification'] is False and r['original_hepta_w1_qualification'] is False
                and r['storage_power_loss_qualification'] is False, 'full32 qualification flags')
    require(lr['frozen_reference_input_sha256'] == sha(read(P + 'a04-full-linux/input.json')), 'Linux frozen input')
    require(gr['qemu_exit'] == 33 and gr['timed_out'] is False and gr['process_exit'] == 0, 'full32 QEMU result')
    require(pin(P + 'a04-full-guest/kernel.elf', gr['kernel_sha256']) == kernel, 'full32 ordinary kernel')
    full_raw = pin(P + 'a04-full-guest/serial.log', gr['serial_sha256'], gr['serial_bytes'])
    no_panic(full_raw); ls = lines(full_raw)
    active = None; streams = {}; actual = []; full_rows = []
    for line in ls:
        if line.startswith('A04_FULL_BEGIN='):
            name = line.split('=', 1)[1]
            require(active is None and len(actual) < 32 and name == expected_names[len(actual)], 'full32 begin order')
            active, streams = name, {'STDOUT': [], 'STDERR': []}
        elif line.startswith(('A04_FULL_STDOUT=', 'A04_FULL_STDERR=')):
            match = re.fullmatch(r'A04_FULL_(STDOUT|STDERR)=([a-z0-9_.]+):([A-Za-z0-9+/=]+)', line)
            require(match is not None and match[2] == active, 'full32 byte frame')
            streams[match[1]].append(match[3])
        elif line.startswith('A04_FULL_END='):
            match = re.fullmatch(r'A04_FULL_END=([a-z0-9_.]+):(\d+):(\d+):([a-f0-9]{64}):(\d+):([a-f0-9]{64})', line)
            require(match is not None and match[1] == active, 'full32 end frame')
            out = base64.b64decode(''.join(streams['STDOUT']), validate=True)
            err = base64.b64decode(''.join(streams['STDERR']), validate=True)
            require((int(match[2]),len(out),sha(out),len(err),sha(err)) == (0,int(match[3]),match[4],int(match[5]),match[6]), 'full32 output byte identity')
            ref = P + 'a04-full-linux/cases/' + active + '/'
            rr = js(ref + 'result.json'); ci = js(ref + 'input.json')
            require(read(ref + 'stdout.log') == out and read(ref + 'stderr.log') == err == b'', 'full32 Linux/guest stdout exact equality')
            expected = contract['cases'][len(actual)]
            require(len(out.decode().splitlines()) == 1 and strict_json(out) == expected['expected_facts'], 'full32 application facts')
            require(rr['passed'] and rr['process_exit'] == 0 and rr['timed_out'] is False and rr['process_group_cleanup_completed'], 'full32 original Linux case')
            require(rr['frozen_case_input_sha256'] == sha(read(ref + 'input.json')) and ci['profile_argv'] == expected['argv'], 'full32 original Linux frozen invocation')
            require(rr['stdout_sha256'] == sha(out) and rr['stderr_sha256'] == sha(err), 'full32 result stdout identities')
            require('--userspec=65534:65534' in ci['argv'], 'full32 Linux unprivileged reference')
            full_rows.append({'name': active, 'stdout_bytes': len(out), 'stdout_sha256': sha(out), 'stderr_bytes': 0,
                              'linux_process_exit': 0, 'guest_process_exit': 0, 'facts': strict_json(out)})
            actual.append(active); active = None
    require(actual == expected_names and active is None, 'full32 complete32')
    exact_order(ls, ['A04_FULL_COMPLETE=32:0', 'A04_FULL_PROCESS_EXIT=0', BOOT])
    require(ls.index(next(l for l in ls if l.startswith('A04_FULL_END=uds_path:'))) < ls.index('A04_FULL_COMPLETE=32:0'), 'full32 completion after finalcase')
    complete('full32_original_linux_and_guest_bytes', {'cases': 32, 'all_stdout_byte_identical': True,
             'all_stderr_empty': True, 'linux_kernel': lr['linux_kernel'], 'linux_uid': 65534,
             'raw_qemu': 33, 'elapsed_seconds': gr['elapsed_seconds'], 'runtime_files': 673,
             'runtime_bytes': runtime_bytes, 'runtime_ELFs': 79, 'workload_ELFs': workload_elfs})

    cpu_rows = []
    for period in (100000, 2000):
        for mode in ('read-only', 'same-value'):
            d = P + f'a06-cpu-config-{period}-{mode}/'
            r = js(d + 'result.json'); inp = js(d + 'inputs.json')
            require(inp == r['inputs'] and sha(read(d + 'inputs.json')) == r['input_receipt']['sha256'], 'CPU before/result input')
            bound = 1.2 if period == 100000 else 52.0
            require((inp['period_us'],inp['mode'],inp['quota_us'],inp['duration_seconds'],inp['max_cpu_percent'])
                    == (period,mode,1000,4,bound), 'CPU unchanged thresholds')
            require(inp['minimum_unlimited_percent'] == 70 and inp['kernel_sha256'] == sha(kernel)
                    and inp['original_initramfs_sha256'] == INITRD_SHA and inp['bios_sha256'] == BIOS_SHA, 'CPU original inputs')
            require(inp['argv'][inp['argv'].index('-smp')+1] == '1' and '-accel' in inp['argv'], 'CPU QEMU shape')
            require(r['qemu_exit'] == 33 and not r['timed_out'] and r['inputs_unchanged'] and r['changed_inputs'] == {}, 'CPU execution/immutability')
            raw = pin(d + 'serial.log', r['serial_sha256'], r['serial_bytes']); no_panic(raw); ls = lines(raw)
            events, samples = [], []
            markers = {f'CPU_CONFIG_PARAMETERS quota_us=1000 period_us={period} mode={mode} seconds=4':'parameters',
                       'CPU_CONFIG_STAT':'stat','CPU_CONFIG_COMPLETE':'complete','CPU_CONFIG_PROCESS_EXIT status=0':'exit0',BOOT:'boot'}
            for line in ls:
                mat = re.fullmatch(r'CPU_CONFIG_SAMPLE label=(unlimited|read-only|same-value) wall_ns=(\d+) cpu_ns=(\d+) operations=(\d+) checksum=(\d+)',line)
                if mat:
                    label,wall,cpu,ops,checksum = mat.groups();wall,cpu,ops,checksum=map(int,(wall,cpu,ops,checksum))
                    require(all(0 < v < 2**64 for v in (wall,cpu,ops)) and checksum < 2**64, 'CPU measurement range')
                    samples.append({'label':label,'wall_ns':wall,'cpu_ns':cpu,'operations':ops,'checksum':checksum,'cpu_percent':100*cpu/wall})
                    events.append('sample:'+label)
                elif line in markers:events.append(markers[line])
                elif 'CPU_CONFIG_' in line or BOOT in line:raise ValueError('malformed CPU marker')
            require(events == ['sample:unlimited','parameters','sample:'+mode,'stat','complete','exit0','boot'], 'CPU exact eventorder')
            require(samples == r['samples'] and samples[0]['wall_ns'] >= 250000000 and samples[1]['wall_ns'] >= 4000000000,
                    'CPU recomputed samples/duration')
            require(samples[0]['cpu_percent'] >= 70 and samples[1]['cpu_percent'] <= bound and r['passed'], 'CPU timing bound')
            require(read(d + 'probe.c') == source('tests/organ_backend/cpu_config_settlement_probe.c').replace(b'__KERNEL_SHA__',sha(kernel).encode()), 'CPU compiledsource derivation')
            probe = pin(d + 'probe',inp['probe_sha256']);elf(probe,static_only=True)
            image = pin(d + 'initramfs.cpio.gz',inp['initramfs_sha256']);cp = cpio(image)
            pp = next(n for n,(f,b) in cp.items() if b == probe)
            original_injection(image,probe,pp,[pp,'.hepta-disposable-guest'])
            require(cp['.hepta-disposable-guest'][1] == (sha(kernel)+'\n').encode(), 'CPU guest kernel marker')
            for key,path in (('runner','tests/organ_backend/run_cpu_config_settlement.py'),('archive_helper','tests/organ_backend/run_guest_probe.py'),('probe_source','tests/organ_backend/cpu_config_settlement_probe.c')):
                require(inp['input_files'][key]['sha256'] == sha(source(path)), 'CPU helper source')
            cpu_rows.append({'period_us':period,'mode':mode,'original_limit_percent':bound,'unlimited_percent':samples[0]['cpu_percent'],
                             'wall_ns':samples[1]['wall_ns'],'cpu_ns':samples[1]['cpu_ns'],'cpu_percent':samples[1]['cpu_percent'],
                             'raw_qemu':33,'probe_sha256':sha(probe),'serial_sha256':sha(raw)})
    complete('four_cpu_configurations_recomputed_from_serial',cpu_rows)

    quota_rows = []
    for cpus in (1,2):
        d = P + f'a06-probe-{cpus}vcpu/';r = js(d+'result.json')
        require((r['mode'],r['quota_us'],r['period_us'],r['duration_seconds'],r['max_cpu_percent']) == ('leaf',1000,100000,1,3.0), 'quota original args')
        require(r['candidate_sha256'] == sha(kernel) and r['source_pin'] == INITRD_SHA
                and not r['smp_qualified'] and not r['hepta_hos2_qualified'], 'quota identity and scope')
        require(read(d+'candidate_kernel.sha256') == (sha(kernel)+'\n').encode(), 'quota frozen kernel identity')
        probe = read(d+'probe');elf(probe,static_only=True)
        image = pin(d+'initramfs.cpio.gz',r['initramfs_sha256']);cp = cpio(image)
        if cpus==1:
            original_injection(image,probe,'bin/cpu-cap-probe',['bin/cpu-cap-probe','.hepta-disposable-guest'])
        else:
            require(cp['bin/cpu-cap-probe'][1] == probe and b'test "$cpu_count" -eq 2' in cp['init'][1], '2CPU guest init')
            require(r['parallel_pthreads']==2 and r['configured_vcpus']==2, '2CPU declaration')
        require(cp['.hepta-disposable-guest'][1] == (sha(kernel)+'\n').encode(), 'quota guest kernel marker')
        source_path='tests/organ_backend/'+('cpu_cap_probe.c' if cpus==1 else 'smp2/parallel_cpu_probe.c')
        expected=source(source_path).replace(b'e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63',sha(kernel).encode())
        require(read(d+'probe.c') == expected, 'leaf quota derived source')
        source('tests/organ_backend/'+('run_candidate_matrix.py' if cpus==1 else 'smp2/run_parallel_candidate.py'))
        require(len(r['runs'])==2,'two complete quota repetitions')
        for i, rr in enumerate(r['runs'],1):
            raw=read(d+f'serial-{i}.log');no_panic(raw);ls=lines(raw)
            mats=re.findall(r'ORGAN_CPU_SAMPLE label=(\S+) wall_ns=(\d+) cpu_ns=(\d+) iterations=(\d+)', '\n'.join(ls))
            samples=[{'label':a,'wall_ns':int(b),'cpu_ns':int(c),'iterations':int(e)} for a,b,c,e in mats]
            require(len(samples)==2 and samples==rr['samples'] and samples[0]['label']=='unlimited'
                    and samples[1]['label']=='one-percent-configured','quota actual samples')
            percent=round(100*samples[1]['cpu_ns']/samples[1]['wall_ns'],3)
            require(percent==rr['cpu_percent'] and percent<=3 and rr['qemu_exit']==33 and not rr['panic'], 'quota original bound')
            exact_order(ls,['ORGAN_PROBE_COMPLETE',BOOT])
            if cpus==2:require(100*samples[0]['cpu_ns']>145*samples[0]['wall_ns'], '2CPU required unlimited baseline')
            quota_rows.append({'vcpus':cpus,'repeat':i,'samples':samples,'original_limit_percent':3.0,'cpu_percent':percent,
                               'unlimited_percent':100*samples[0]['cpu_ns']/samples[0]['wall_ns'],'raw_qemu':33,'serial_sha256':sha(raw)})
    complete('bounded_quota_one_and_two_cpu_serial',quota_rows)
    complete('same_actual_kernel_across_ordinary_and_quota',{'sha256':sha(kernel),'bytes':len(kernel),
             'note':'SMP=2 build invocation is separate; in this artifact its ELF bytes equal the saved ordinary kernel. Do not copy the older203 different-ELF description.'})
    source('.github/workflows/a06-kernel.yml')
    report={'schema_version':1,'kind':'independent_original_artifact_ordinary_and_cpu_review','reviewer':'/root/r9_g1_contract',
            'started_at_utc':started,'completed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'head':HEAD,'tree':TREE,'archive':{'file':'../original.zip','bytes':154979607,'sha256':ARCHIVE_SHA,'artifact_id':12182038203,
            'run_id':39240728276,'job_id':118020615962},'checks':checks,'blocking':[],'case_profiles':case_profiles,
            'full32_cases':full_rows,'cpu_configurations':cpu_rows,'quota_runs':quota_rows,'source_inputs':git_sources,
            'read_member_identities':identities,'scope_limits':[
              'Read original records and fixed Git only; no Cargo/QEMU/ELF/archived helper execution or new product run.',
              'Complete7054 Git inventory,220core/221OSTD and seven negative controls belong to the sibling independent review; only relatedsource subset and the three stored snapshots were checked here.',
              'This proves fixed Ubuntu24.04 x86_64 Linux/guest cases, not original Debian13 restoration, original HeptaW1, Android, GUI or block-device crash/power-loss recovery.',
              'One/two-vCPU quota results pass original gross-non-enforcement thresholds. They do not qualify fullSMP, physical-switch atomicity, RT scheduling, strict1percentSLA or nativeHOS2 effects.',
              'Host QEMU/compiler executable hashes are original recorded identities; those host executables are not supplied in this ZIP and were not independently rehashed.',
              'Historical WIP and older203 artifacts were not used as this run results.'],
            'actual_run_ordinary_step_times':[s for s in job['steps'] if any(w in s['name'] for w in ('SCM','NOFILE','ordinary','Ubuntu','quota','cpu.max','CPU configuration'))],
            'activities':{'archive_programs_executed':0,'cargo_or_qemu_runs':0,'product_mutations':0,'additional_downloads':0}}
    out_bytes=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode()
    require(not (OUT/'review.json').exists(),'refuse overwrite frozen report')
    (OUT/'review.json').write_bytes(out_bytes)
    selected['review.py']=Path(__file__).read_bytes()
    manifest={'schema_version':1,'archive_sha256':ARCHIVE_SHA,'head':HEAD,'tree':TREE,'files':[
        {'path':name,'bytes':len(raw),'sha256':sha(raw)} for name,raw in sorted(selected.items())]}
    manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    (OUT/'selected-evidence-manifest.json').write_bytes(manifest_bytes)
    with zipfile.ZipFile(OUT/'selected-evidence.zip','x',zipfile.ZIP_DEFLATED,compresslevel=9) as pack:
        for name,raw in sorted(selected.items()):pack.writestr(name,raw)
        pack.writestr('selected-evidence-manifest.json',manifest_bytes)
    with zipfile.ZipFile(OUT/'selected-evidence.zip') as pack:
        require(pack.testzip() is None,'new selected package CRC')
        for name,raw in selected.items():require(pack.read(name)==raw,'selected package exact bytes')
    print(json.dumps({'passed':True,'checks':len(checks),'report_bytes':len(out_bytes),'report_sha256':sha(out_bytes),
          'selected_files':len(selected),'selected_uncompressed_bytes':sum(map(len,selected.values())),
          'selected_zip_bytes':(OUT/'selected-evidence.zip').stat().st_size,
          'selected_zip_sha256':sha((OUT/'selected-evidence.zip').read_bytes()),'source_inputs':len(git_sources)}))
except Exception as error:
    failure={'kind':'independent_review_helper_incomplete','started_at_utc':started,
             'failed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'error':str(error),
             'completed_checks':checks,'not_a_product_rerun':True}
    index=1
    while (OUT/f'helper-attempt-{index:02}.json').exists():index+=1
    (OUT/f'helper-attempt-{index:02}.json').write_text(json.dumps(failure,ensure_ascii=False,indent=2)+'\n')
    raise
