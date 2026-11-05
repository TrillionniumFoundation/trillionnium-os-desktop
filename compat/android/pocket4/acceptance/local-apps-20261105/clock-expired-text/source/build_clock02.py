#!/usr/bin/python3 -I
"""Build the sole expired-notification text fallback; never install or execute the APK."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, copy, hashlib, io, json, os, re, shutil, signal, stat
import struct, subprocess, time, types, zipfile, zlib

ROOT = Path('/home/alex/work/pocket4-clock-expired-text-20261105-r12-02')
FROZEN = ROOT / 'frozen'
OUT = ROOT / 'build'
CLOCK = Path('/home/alex/work/pocket4-clock-session-tools-20261105-r12-01')
MODEL_SHA = '5591b37c256f1e8927f34cd1d7f89e6489add4bdde714198cf3f6d872c72b89e'
INSPECTOR_SHA = '4fe7333255ccbcd6df22a4c89d40c669603f7817eae3d0071c7e5f930a6b424f'
PINS_SHA = '20b2752edb6c820577c3467bd38b8386f88825fc18ae66f3394302ae3a630b24'
IR_SHA = 'a895a4e3963f958ea6a6ff45b9d0c51f6239118b3a10fddff6d0f17e22e25f9f'
OLD_CLASS_SHA = '6df1845e689b0219908a051b679e39707e08e680a0db3f36f85c2d6be8e81dbd'
NEW_CLASS_SHA = 'd618e064ffc6719312a8a5b79b8e585ae9cbcda6ab2a42fd8cd94c00117e8bf1'
DEX_SHA = '8b7f0094b816a758d86599ba9c19866314dbb37cf78f57187a8602c2f3e3b77b'
CERT = 'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc'
SIGNER_SHA = '52947059a664b85f0475bcdc3dbbe6089b50f8f59e3aa051e6e74cf0ba7db70f'
ALIGN_SHA = 'fd9663d5f0ac858ccbd6a2aa414536dc878266748de2e6afa9a5146c72950758'
RECEIPT = Path('/home/alex/work/pocket4-camera-source-20261104/camera-hotplug-candidate-03/apk-release-07/result.json')
RECEIPT_SHA = '6da344e2624fcc728e046a13c92cdb9b4e999f3808ea4844fb948e821fecc90c'
REL = 'com/android/deskclock/data/TimerNotificationBuilder.smali'
METHOD = 'public final buildHeadsUp(Landroid/content/Context;Ljava/util/List;)Landroid/app/Notification;'
FRAGMENT_SHA = '3f8bd230d9ac92c8aa0e1ff4254c0e690f53a117194b1e646188ca2976a4c0c3'
ANCHOR = '    if-eqz v1, :cond_149\n\n    const/16 v17, 0x1'
PREFS = '/data/user_de/0/com.android.deskclock/shared_prefs/com.android.deskclock_preferences.xml'
ALARM_DIGEST = '655c545ee9487dc380100d6300376d0bb82d0d12beddd96f283ab7814ff19fea'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
       'JAVA_TOOL_OPTIONS': '-Xmx1024m -XX:ActiveProcessorCount=2 -XX:+UseSerialGC'}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path, expected):
    raw = Path(path).read_bytes()
    require(sha(raw) == expected, 'FROZEN_SOURCE_CHANGED:' + Path(path).name)
    module = types.ModuleType('clock_candidate_' + Path(path).stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def write(path, value, public=False):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        if public:
            os.fchown(fd, 0, 1000); os.fchmod(fd, 0o640)
        with os.fdopen(os.dup(fd), 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    finally:
        os.close(fd)


def run(result, label, argv, timeout=90):
    started = time.monotonic()
    with (OUT / (label + '.stdout')).open('xb') as out, (OUT / (label + '.stderr')).open('xb') as err:
        process = subprocess.Popen(argv, stdout=out, stderr=err, env=ENV, start_new_session=True)
        timed_out = False
        try:
            process.wait(timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(10)
    # Signing selectors and key paths are deliberately absent from the receipt.
    record = {'label': label, 'rc': process.returncode, 'timed_out': timed_out,
        'leader_joined': True, 'elapsed_seconds': time.monotonic() - started,
        'executable_sha256': file_sha(Path(argv[0]).resolve()),
        'stdout_sha256': file_sha(OUT / (label + '.stdout')),
        'stderr_sha256': file_sha(OUT / (label + '.stderr'))}
    result['commands'].append(record)
    require(record['rc'] == 0 and not timed_out, 'BUILD_COMMAND_FAILED:' + label)
    return (OUT / (label + '.stdout')).read_text(errors='replace')


def limits():
    require(os.geteuid() == 0, 'ROOT_HELD_READ_REQUIRED')
    affinity = sorted(os.sched_getaffinity(0))
    require(affinity and set(affinity) <= {20, 21}, 'BUILD_CPU_SCOPE_CHANGED')
    rows = [x[3:] for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::/')]
    require(len(rows) == 1, 'UNIFIED_OWNED_CGROUP_REQUIRED')
    cg = Path('/sys/fs/cgroup') / rows[0].lstrip('/')
    memory = (cg / 'memory.max').read_text().strip()
    swap = (cg / 'memory.swap.max').read_text().strip()
    cpu = (cg / 'cpu.max').read_text().split()
    require(memory.isdecimal() and int(memory) <= 2 * 1024 ** 3 and swap == '0', 'BUILD_MEMORY_SCOPE_CHANGED')
    require(len(cpu) == 2 and all(x.isdecimal() for x in cpu) and int(cpu[0]) <= 2 * int(cpu[1]),
            'BUILD_CPU_QUOTA_CHANGED')
    return {'cpu_affinity': affinity, 'memory_max_bytes': int(memory), 'memory_swap_max_bytes': 0,
            'cpu_max': cpu, 'own_cgroup': str(cg), 'runtime_max_seconds_requested': 480}


def clock_snapshot(session, model):
    identity = model.identity(session)
    require(identity['notifications_granted'], 'CLOCK_NOTIFICATION_REPAIR_NOT_PRESENT')
    state = model.state(session)
    model.verify_before(state)
    require(model.baseline_ids(state) == {1, 2}, 'ORIGINAL_ALARM_SET_CHANGED')
    script = ('set -o pipefail; /system/bin/sqlite3 -readonly -json ' + model.DB
        + " 'PRAGMA query_only=ON;BEGIN;SELECT * FROM alarm_templates ORDER BY _id;ROLLBACK;'"
        + ' | /system/bin/sha256sum')
    argv = ['/system/bin/env', '-i'] + [k + '=' + session.environment[k] for k in sorted(session.environment)]
    argv += ['/system/bin/timeout', '-k', '2', '12', '/system/bin/sh', '-c', script]
    with session.target.entry(argv) as (command, descriptors):
        value = session.run_host('clock-build-alarm-digest', command, 16, descriptors)
    digest = value['stdout'].decode().strip()
    require(value['rc'] == 0 and value['joined'] and not value['timed_out']
        and digest == ALARM_DIGEST + '  -', 'ORIGINAL_ALARM_CONTENT_CHANGED')
    prefs, _ = session.target.read_file(PREFS, 2 * 1024 * 1024)
    session.guard()
    return {'identity': identity, 'state': state, 'alarm_content_sha256': ALARM_DIGEST,
            'preferences_sha256': sha(prefs), 'epoch_sha256': session.epoch_sha256}


def tree(path, count):
    result = {}
    for entry in path.rglob('*'):
        require(not entry.is_symlink(), 'SOURCE_TREE_SYMLINK')
        if entry.is_file():
            require(entry.suffix == '.smali', 'NON_SMALI_SOURCE')
            result[str(entry.relative_to(path))] = entry
    require(len(result) == count, 'DEX_CLASS_COUNT_CHANGED')
    return result


def signature_entry(name):
    return name.upper() == 'META-INF/MANIFEST.MF' or re.fullmatch(r'META-INF/[^/]+\.(SF|RSA|DSA|EC)', name, re.I) is not None


def payload_proof(original, candidate, dex):
    with zipfile.ZipFile(original) as old, zipfile.ZipFile(candidate) as new:
        require(new.testzip() is None and len(new.namelist()) == len(set(new.namelist())), 'CANDIDATE_ZIP_INVALID')
        names = {n for n in old.namelist() if not signature_entry(n)}
        require(names == {n for n in new.namelist() if not signature_entry(n)}, 'APK_PAYLOAD_SET_CHANGED')
        rows = {}
        for name in sorted(names):
            before, after = old.read(name), new.read(name)
            require(after == (dex if name == 'classes.dex' else before), 'APK_NON_TARGET_PAYLOAD_CHANGED:' + name)
            rows[name] = {'before_sha256': sha(before), 'after_sha256': sha(after),
                          'before_bytes': len(before), 'after_bytes': len(after), 'payload_equal': before == after}
        require([n for n, row in rows.items() if not row['payload_equal']] == ['classes.dex'], 'DEX_CHANGE_REQUIRED')
        return rows


def build(result):
    result['resources'] = limits()
    model = load(CLOCK / 'read_clock_foreground01.py', MODEL_SHA)
    inspector = load(CLOCK / 'inspect_clock_dex01.py', INSPECTOR_SHA)
    tx = model.load_session()
    ir = load(FROZEN / 'smali_equivalence.py', IR_SHA)
    pins = json.loads(tx.read_regular(CLOCK / 'baksmali-pins.json', PINS_SHA))
    checked = [*pins['jre'].values(), *pins['jars'].values()]
    for pin in checked:
        inspector.check_tool(pin)
    original_class = tx.read_regular(FROZEN / 'TimerNotificationBuilder.original.smali', OLD_CLASS_SHA).decode()
    reviewed = tx.read_regular(FROZEN / 'TimerNotificationBuilder.smali', NEW_CLASS_SHA).decode()
    original_ir, expected_ir = ir.class_ir(original_class), ir.class_ir(reviewed)
    require(original_ir['header'] == expected_ir['header']
        and original_ir['methods'].keys() == expected_ir['methods'].keys(), 'REVIEWED_CLASS_METADATA_CHANGED')
    require([n for n in original_ir['methods'] if original_ir['methods'][n] != expected_ir['methods'][n]] == [METHOD],
            'REVIEWED_NON_TARGET_METHOD_CHANGED')
    fragment = tx.read_regular(FROZEN / 'metadata-fragment.smali', FRAGMENT_SHA).decode()
    matches = list(re.finditer(r'^\.method ' + re.escape(METHOD) + r'\n[\s\S]*?^\.end method$', original_class, re.M))
    require(len(matches) == 1 and matches[0][0].count(ANCHOR) == 1, 'EXACT_EXPIRED_METHOD_INSERTION_POINT_CHANGED')
    match = matches[0]
    expected_text = original_class[:match.start()] + match[0].replace(ANCHOR,
        '    if-eqz v1, :cond_149\n\n' + fragment + '    const/16 v17, 0x1', 1) + original_class[match.end():]
    require(reviewed == expected_text, 'ONLY_REVIEWED_EXPIRED_METADATA_INSERTION_ALLOWED')
    a, b = original_ir['methods'][METHOD], expected_ir['methods'][METHOD]
    added_instructions = len(b['instructions']) - len(a['instructions'])
    require(added_instructions == 13, 'REVIEWED_METADATA_INSTRUCTION_COUNT_CHANGED')
    history = json.loads(tx.read_regular(RECEIPT, RECEIPT_SHA, 1024 * 1024))
    commands = {c['label']: c['argv'] for c in history['commands']}
    sign = list(commands['sign']); verify = list(commands['signature-verify']); align_check = list(commands['alignment-verify'])
    require(sign[:2] == ['/usr/bin/apksigner', 'sign'] and verify[:2] == ['/usr/bin/apksigner', 'verify'], 'SIGNING_COMMAND_IDENTITY_CHANGED')
    require('--ks-pass' not in sign and '--key-pass' not in sign and sign[sign.index('--min-sdk-version') + 1] == '37',
            'SIGNING_COMMAND_SCOPE_CHANGED')
    require(align_check[1:-1] == ['-c', '-P', '16', '4'], 'ALIGNMENT_COMMAND_CHANGED')
    sign_tool, align_tool = Path(sign[0]).resolve(), Path(align_check[0]).resolve()
    require(file_sha(sign_tool) == SIGNER_SHA and file_sha(align_tool) == ALIGN_SHA, 'PACKAGING_TOOL_CHANGED')
    java = pins['jre']['bin/java']['canonical']
    cp = ':'.join(pins['jars'][name]['canonical'] for name in sorted(pins['jars']))
    def command(tool):
        return [java, '-Xmx1024m', '-XX:ActiveProcessorCount=2', '-cp', cp, 'org.jf.' + tool + '.Main']
    with tx.CameraSession(OUT / 'held-read-journal') as session:
        result['clock_before'] = clock_snapshot(session, model)
        apk, _ = session.target.read_file(model.APK_PATH, 16 * 1024 * 1024)
        require(len(apk) == model.APK_BYTES and sha(apk) == model.APK_SHA, 'INSTALLED_APK_CHANGED')
        original = OUT / 'DeskClock.original.apk'; write(original, apk)
        original_verify = list(verify); original_verify[-1] = str(original)
        text = run(result, 'original-signature-verify', original_verify, 30)
        require(re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([0-9a-f]+)$', text, re.M) == [CERT],
                'ORIGINAL_CLOCK_CERTIFICATE_DIFFERS_FROM_AVAILABLE_SIGNING_IDENTITY')
        result['original_certificate_sha256'] = CERT
        with zipfile.ZipFile(io.BytesIO(apk)) as archive:
            require(len(archive.namelist()) == len(set(archive.namelist())) and archive.testzip() is None, 'INSTALLED_APK_ZIP_INVALID')
            require([n for n in archive.namelist() if re.fullmatch(r'classes(?:[2-9][0-9]*)?\.dex', n)] == ['classes.dex'],
                    'CLOCK_DEX_SET_CHANGED')
            old_dex = archive.read('classes.dex')
        require(len(old_dex) == 3021920 and sha(old_dex) == DEX_SHA and old_dex[:8] == b'dex\n039\0', 'INSTALLED_DEX_CHANGED')
        class_count = struct.unpack_from('<I', old_dex, 96)[0]
        source_dex = OUT / 'classes.original.dex'; write(source_dex, old_dex)
        run(result, 'disassemble-original', command('baksmali') + ['disassemble', '--jobs', '2', '--api', '35',
            '--output', str(OUT / 'original-smali'), str(source_dex)], 90)
        before_files = tree(OUT / 'original-smali', class_count)
        require(ir.class_ir(before_files[REL].read_text()) == original_ir, 'EXACT_INSTALLED_TARGET_IR_CHANGED')
        shutil.copytree(OUT / 'original-smali', OUT / 'source')
        (OUT / 'source' / REL).write_text(reviewed)
        candidate_dex = OUT / 'classes.expired-text.dex'
        run(result, 'assemble', command('smali') + ['assemble', '--jobs', '2', '--api', '35',
            '--output', str(candidate_dex), str(OUT / 'source')], 90)
        dex = candidate_dex.read_bytes()
        require(dex[:8] == old_dex[:8] and struct.unpack_from('<I', dex, 32)[0] == len(dex)
            and hashlib.sha1(dex[32:]).digest() == dex[12:32]
            and zlib.adler32(dex[12:]) & 0xffffffff == struct.unpack_from('<I', dex, 8)[0]
            and struct.unpack_from('<I', dex, 96)[0] == class_count, 'ASSEMBLED_DEX_HEADER_INVALID')
        run(result, 'disassemble-candidate', command('baksmali') + ['disassemble', '--jobs', '2', '--api', '35',
            '--output', str(OUT / 'roundtrip-smali'), str(candidate_dex)], 90)
        after_files = tree(OUT / 'roundtrip-smali', class_count)
        require(before_files.keys() == after_files.keys(), 'CANDIDATE_CLASS_SET_CHANGED')
        differences, records, method_count = [], {}, 0
        for relative in sorted(before_files):
            old = ir.class_ir(before_files[relative].read_text()); new = ir.class_ir(after_files[relative].read_text())
            require(old['header'] == new['header'] and old['methods'].keys() == new['methods'].keys(),
                    'CLASS_METADATA_OR_METHOD_SET_CHANGED:' + relative)
            for name in old['methods']:
                method_count += 1
                if old['methods'][name] != new['methods'][name]:
                    differences.append({'class': relative, 'method': name})
                    require(relative == REL and name == METHOD and new['methods'][name] == expected_ir['methods'][METHOD],
                            'UNREVIEWED_METHOD_CHANGE:' + relative + ':' + name)
            records[relative] = {'before_sha256': file_sha(before_files[relative]), 'after_sha256': file_sha(after_files[relative]),
                'before_ir_sha256': ir.ir_sha256(old), 'after_ir_sha256': ir.ir_sha256(new), 'method_count': len(old['methods'])}
        require(differences == [{'class': REL, 'method': METHOD}], 'EXACT_METHOD_DIFFERENCE_REQUIRED')
        write(OUT / 'all-class-semantic-proof.json', records)
        result['semantic_verification'] = {'classes': class_count, 'methods': method_count, 'differences': differences,
            'metadata_instructions_added': added_instructions, 'non_target_semantic_changes': 0,
            'outside_reviewed_N_or_later_metadata_insertion_unchanged': True, 'reviewed_target_ir_equal': True,
            'channels_pending_intents_timer_state_and_ringer_unchanged': True,
            'proof_sha256': file_sha(OUT / 'all-class-semantic-proof.json'), 'comparator_sha256': IR_SHA}
        unaligned = OUT / 'DeskClock-unsigned.apk'
        with zipfile.ZipFile(original) as src, zipfile.ZipFile(unaligned, 'x') as dst:
            dst.comment = src.comment
            for info in src.infolist():
                if not signature_entry(info.filename):
                    dst.writestr(copy.copy(info), dex if info.filename == 'classes.dex' else src.read(info.filename))
        payload_proof(original, unaligned, dex)
        aligned = OUT / 'DeskClock-aligned-unsigned.apk'
        run(result, 'zipalign', [align_check[0], '-P', '16', '-f', '4', str(unaligned), str(aligned)], 20)
        target = OUT / 'DeskClock-pocket4-expired-text.apk'
        sign[sign.index('--out') + 1] = str(target); sign[-1] = str(aligned)
        run(result, 'sign', sign, 60)
        verify[-1] = str(target)
        signed = run(result, 'candidate-signature-verify', verify, 30)
        require(re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([0-9a-f]+)$', signed, re.M) == [CERT]
            and 'Verified using v3 scheme (APK Signature Scheme v3): true' in signed, 'CANDIDATE_SIGNATURE_NOT_VERIFIED')
        align_check[-1] = str(target); run(result, 'alignment-verify', align_check, 20)
        proof = payload_proof(original, target, dex); write(OUT / 'apk-payload-proof.json', proof)
        require(payload_proof(original, aligned, dex) == proof, 'SIGNING_CHANGED_PAYLOADS')
        result['payload_verification'] = {'members': len(proof), 'only_changed_payload': 'classes.dex',
            'signature_v3_verified': True, 'same_certificate_verified': True, 'alignment_16k_verified': True,
            'proof_sha256': file_sha(OUT / 'apk-payload-proof.json')}
        for pin in checked:
            inspector.check_tool(pin)
        require(file_sha(sign_tool) == SIGNER_SHA and file_sha(align_tool) == ALIGN_SHA
            and file_sha(RECEIPT) == RECEIPT_SHA and file_sha(original) == model.APK_SHA, 'INPUT_OR_TOOL_CHANGED_DURING_BUILD')
        result['clock_after'] = clock_snapshot(session, model)
        require(result['clock_before'] == result['clock_after'], 'CLOCK_STATE_CHANGED_DURING_OFFLINE_BUILD')
        session.caller_status('clock-candidate-final-caller')
        os.chown(target, 0, 1000); os.chmod(target, 0o640)
        result['candidate_apk'] = {'path': str(target), 'bytes': target.stat().st_size, 'sha256': file_sha(target),
                                   'certificate_sha256': CERT}
        result['candidate_dex'] = {'bytes': len(dex), 'sha256': sha(dex), 'format': '039', 'header_verified': True}
        result['original_apk_sha256'] = model.APK_SHA
        result['original_dex_sha256'] = DEX_SHA
        result['original_target_sha256'] = OLD_CLASS_SHA
        result['reviewed_target_sha256'] = NEW_CLASS_SHA
        result['inputs_tools_and_clock_state_unchanged'] = True
        result['state'] = 'SIGNED_OFFLINE_CANDIDATE_VERIFIED'


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--build', action='store_true')
    if not parser.parse_args().build:
        print(json.dumps({'state': 'PLAN_ONLY', 'installed': False, 'UI_actions': 0, 'changes': 'expired custom-view notification text metadata'}))
        return 0
    OUT.mkdir(mode=0o750); os.chown(OUT, 0, 1000); os.chmod(OUT, 0o750)
    result = {'started_utc': datetime.now(timezone.utc).isoformat(), 'state': 'STARTED', 'commands': [],
        'installed': False, 'UI_actions': 0, 'app_state_writes': 0, 'new_signing_identity_created': False,
        'android_art_verifier_run': False, 'runtime_expiry_pass': False, 'production_ready': False}
    rc = 0
    try:
        build(result)
    except BaseException as error:
        result['state'] = 'FAILED'; result['error'] = type(error).__name__ + ':' + str(error); rc = 2
    result['finished_utc'] = datetime.now(timezone.utc).isoformat()
    write(OUT / 'result.json', result, public=True)
    print(json.dumps(result, sort_keys=True)); return rc


if __name__ == '__main__':
    raise SystemExit(main())
