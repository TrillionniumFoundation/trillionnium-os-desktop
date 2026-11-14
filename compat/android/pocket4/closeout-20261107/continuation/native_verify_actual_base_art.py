from pathlib import Path
import os, stat, json, hashlib, zipfile, subprocess, time, sys, types, resource, struct, re

R = Path('/home/alex/work/pocket4-android-final/native')
B = R / 'offline/base-art-verified'
B.mkdir(mode=0o700)
os.umask(0o077)

def need(value, message):
    if not value:
        raise RuntimeError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def pin(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}

def put(path, raw):
    if isinstance(raw, str):
        raw = raw.encode()
    with path.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, 0o600)
    return pin(path)

def record(path, value):
    return put(path, json.dumps(value, indent=2, sort_keys=True) + '\n')

report = {'schema': 'pocket4-actual-installed-art-offline-v2', 'state': 'STARTING',
          'commands': [], 'Android_actions': 0, 'mount_actions': 0, 'production_actions': 0}
reaper = None

def cmd(label, argv, seconds=60):
    end = time.monotonic() + seconds
    bound = 128 * 1024 * 1024
    def factory(input_fd, stdout_fd, stderr_fd, output_bound):
        def limits():
            resource.setrlimit(resource.RLIMIT_FSIZE, (output_bound, output_bound))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        return subprocess.Popen(argv, stdin=input_fd, stdout=stdout_fd, stderr=stderr_fd,
            start_new_session=True, preexec_fn=limits, env={'PATH': '/usr/bin:/bin:/usr/sbin', 'LANG': 'C'})
    capture, stdout, stderr, first = life.invoke_owned(reaper, factory, b'', end, end + 15,
        output_bound=bound, retirement_grace=5)
    row = {'label': label, 'argv': argv, 'output_and_regular_file_limit_bytes': bound,
        'capture': capture, 'first_error': repr(first) if first else None,
        'stdout': put(B / (label + '.stdout'), stdout or b''),
        'stderr': put(B / (label + '.stderr'), stderr or b'')}
    row['receipt'] = record(B / (label + '.json'), row)
    report['commands'].append(row)
    need(first is None and capture['qualified_success'] and capture['returncode'] == 0 and
         capture['owned_tree_cleanup_complete'] and capture['child_reaped'] and
         capture['all_acquired_fds_closed'], 'actual base tool failed: ' + label)
    return stdout

try:
    base = Path('/home/alex/work/pocket4-android-final/framework/current-installed/com.android.art.apex')
    need(pin(base)['sha256'] == '3a5b5d1fab9e4f3ca4a15da425a4d56c45548d137ee8289e34687fb5b60d6807', 'installed base APEX changed')
    report['base_apex'] = pin(base)
    prior = R / 'offline/base-art/libart.so'
    if prior.exists():
        report['preserved_prior_failed_partial'] = {**pin(prior), 'job': '1a1b50c3639-fc05-8b0e', 'used_as_input': False}
    with zipfile.ZipFile(base) as archive:
        for name in ('apex_payload.img', 'apex_pubkey'):
            need(archive.namelist().count(name) == 1, 'duplicate or missing APEX member')
        need(archive.getinfo('apex_payload.img').file_size <= 512 * 1024 * 1024, 'actual APEX payload bound')
        key = archive.read('apex_pubkey')
        payload = archive.read('apex_payload.img')
    need(len(key) == 1032 and sha(key) == '8dc1b7157b0b16dd8ec0240dd8b3e65ce2f91c6bb0933dc048decb91917b465d', 'base AVB key changed')
    report['apex_pubkey'] = put(B / 'apex_pubkey', key)
    report['payload'] = put(B / 'apex_payload.img', payload)
    filesystem = 'ext4' if payload[1080:1082] == b'\x53\xef' else 'erofs' if payload[1024:1028] == b'\xe2\xe1\xf5\xe0' else None
    need(filesystem is not None, 'base payload filesystem unsupported')
    report['filesystem'] = filesystem
    need(len(payload) >= 64, 'AVB footer absent')
    magic, major, minor, original_size, vbmeta_offset, vbmeta_size, reserved = struct.unpack('>4sIIQQQ28s', payload[-64:])
    need(magic == b'AVBf' and major == 1 and minor == 0 and reserved == bytes(28), 'base AVB footer format changed')
    need(256 <= vbmeta_size <= 1024 * 1024 and 0 < original_size <= vbmeta_offset and
         vbmeta_offset + vbmeta_size <= len(payload) - 64, 'base AVB extents invalid')
    vbmeta = payload[vbmeta_offset:vbmeta_offset + vbmeta_size]
    need(vbmeta[:4] == b'AVB0', 'base VBMeta header absent')
    authentication_size, auxiliary_size = struct.unpack_from('>QQ', vbmeta, 12)
    public_key_offset, public_key_size = struct.unpack_from('>QQ', vbmeta, 64)
    start = 256 + authentication_size + public_key_offset
    need(public_key_offset + public_key_size <= auxiliary_size and start + public_key_size <= len(vbmeta), 'VBMeta key extent invalid')
    need(vbmeta[start:start + public_key_size] == key, 'signed payload key differs from actual trusted outer APEX key')
    report['payload_key_binding'] = {'footer_major': major, 'vbmeta_offset': vbmeta_offset,
        'vbmeta_size': vbmeta_size, 'algorithm_type': struct.unpack_from('>I', vbmeta, 28)[0],
        'embedded_key_sha256': sha(vbmeta[start:start + public_key_size]), 'equals_apex_pubkey': True}
    del payload, vbmeta
    jar = Path('/usr/share/java/apksigner.jar').resolve(strict=True)
    java = R / 'work/aosp-source/prebuilts/jdk/jdk21/linux-x86/bin/java'
    avbtool = R / 'work/aosp-source/external/avb/avbtool.py'
    life_path = R / 'control-source/capture_lifecycle.py'
    need(pin(life_path)['sha256'] == '6a0ba9438b10740a593e2d90962420e04868465a0fb55c0ce2e03afdb835e877', 'capture lifecycle changed')
    life = types.ModuleType('base_art_fixed_capture')
    life.__file__ = str(life_path)
    sys.modules[life.__name__] = life
    exec(compile(life_path.read_bytes(), str(life_path), 'exec'), life.__dict__)
    reaper = life.OwnChildReaper()
    reaper.begin()
    report['tools'] = {'java': pin(java), 'apksigner': pin(jar), 'avbtool_source': pin(avbtool)}
    cert = cmd('apksigner-verify', [str(java), '-Xmx256m', '-jar', str(jar), 'verify', '--verbose', '--print-certs', str(base)])
    text = cert.decode('utf-8', 'strict')
    certificate = re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([0-9a-f]{64})$', text, re.M)
    need(certificate == ['0dda096be3af77ee9e6b403c2e49ea5c409d5b2aa6ab5c41e32ee4049d448110'], 'actual base outer signer changed')
    report['outer_certificate_sha256'] = certificate[0]
    cmd('avb-verify', ['/usr/bin/python3', '-B', str(avbtool), 'verify_image', '--image', str(B / 'apex_payload.img')], 90)
    report['complete_payload_avb_verification'] = True
    if filesystem == 'ext4':
        for library in ('libart', 'libnativebridge'):
            cmd('extract-' + library, ['/usr/sbin/debugfs', '-R', 'dump /lib64/' + library + '.so ' + str(B / (library + '.so')), str(B / 'apex_payload.img')])
    else:
        cmd('extract-erofs', ['/usr/bin/dump.erofs', '--extract=' + str(B / 'tree'), str(B / 'apex_payload.img')])
        for library in ('libart', 'libnativebridge'):
            put(B / (library + '.so'), (B / 'tree/lib64' / (library + '.so')).read_bytes())
    libraries = {}
    for library in ('libart', 'libnativebridge'):
        path = B / (library + '.so')
        with path.open('rb') as handle:
            header = handle.read(64)
        need(header[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<HH', header, 16) == (3, 62), 'base library is not x86_64 ET_DYN ELF')
        dynamic = cmd('elf-' + library, ['/usr/bin/readelf', '-h', '-l', '-d', str(path)])
        symbols = cmd('symbols-' + library, ['/usr/bin/readelf', '--dyn-syms', '--wide', str(path)])
        libraries[library] = {**pin(path), 'soname': re.findall(rb'\(SONAME\).*?\[(.*?)\]', dynamic)[0].decode(),
            'needed': [name.decode() for name in re.findall(rb'\(NEEDED\).*?\[(.*?)\]', dynamic)],
            'dynamic_symbols_receipt': pin(B / ('symbols-' + library + '.stdout'))}
    report['libraries'] = libraries
    report['base_apex_unchanged_after'] = pin(base) == report['base_apex']
    need(report['base_apex_unchanged_after'], 'base APEX changed during verification')
    report['state'] = 'PASS'
except BaseException as error:
    report['state'] = 'FAILED'
    report['error'] = repr(error)
    raise
finally:
    if reaper is not None:
        reaper.finish()
        report['owned_capture'] = reaper.record
        if not reaper.record['final_children_empty'] or not reaper.record['restored']:
            report['state'] = 'FAILED'
            report['retirement_failure'] = True
    report['finished_ns'] = time.time_ns()
    reference = record(B / 'qualification.json', report)
    print(json.dumps({'state': report['state'], 'result': reference,
        'libraries': report.get('libraries'), 'error': report.get('error')}), flush=True)
