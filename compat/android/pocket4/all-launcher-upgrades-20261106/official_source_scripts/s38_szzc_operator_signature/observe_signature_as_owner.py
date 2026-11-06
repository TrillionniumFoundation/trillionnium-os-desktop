#!/usr/bin/env python3
"""Observe one downloaded APK signature as the existing ordinary tool owner."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

ROOT = Path('/home/alex/work/pocket4-szzc-operator-signature-20261106-s38-r2')
FIELDS = ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"}
MAX_TOOL_OUTPUT = 4 * 1024 * 1024
SAVED_PM_SIGNER = 'd85bed4d2a7c08e1b6b5f0097d6c66a79a5b12b58d97e794d3b5c5bff2aeaf44'
TOOL_BINDINGS = {'aapt': {'observed': {'bytes': 30680, 'file': {'st_ctime_ns': 1791415705179294996, 'st_dev': 66306, 'st_gid': 0, 'st_ino': 108138269, 'st_mode': 33261, 'st_mtime_ns': 1757926427000000000, 'st_nlink': 1, 'st_size': 30680, 'st_uid': 0}, 'sha256': 'd9c0d90fc4bcf03d57cbf4fe19ca66c80280ac760c53245c8678b9837844b972'}, 'pin': {'bytes': 30680, 'declared_path': '/usr/lib/android-sdk/build-tools/debian/aapt', 'resolved_path': '/usr/lib/android-sdk/build-tools/debian/aapt', 'sha256': 'd9c0d90fc4bcf03d57cbf4fe19ca66c80280ac760c53245c8678b9837844b972'}}, 'apksigner_jar': {'observed': {'bytes': 521108, 'file': {'st_ctime_ns': 1791415705147294650, 'st_dev': 66306, 'st_gid': 0, 'st_ino': 108005159, 'st_mode': 33188, 'st_mtime_ns': 1741954421000000000, 'st_nlink': 1, 'st_size': 521108, 'st_uid': 0}, 'sha256': '98346a3200d6030e247ccba0e47b354b6113ec2068dcea6c43558b01fe5885c2'}, 'pin': {'bytes': 521108, 'declared_path': '/usr/share/java/apksigner.jar', 'resolved_path': '/usr/share/java/apksigner-35.0.2.jar', 'sha256': '98346a3200d6030e247ccba0e47b354b6113ec2068dcea6c43558b01fe5885c2'}}, 'java': {'observed': {'bytes': 8528, 'file': {'st_ctime_ns': 1792770278197673619, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40663514, 'st_mode': 33277, 'st_mtime_ns': 1792770278197673619, 'st_nlink': 1, 'st_size': 8528, 'st_uid': 1000}, 'sha256': 'cfa21aeadd00925925c9e1287f5c08f3e04ee7f26a9e23d9dbfb16149153d842'}, 'pin': {'bytes': 8528, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/bin/java', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/bin/java', 'sha256': 'cfa21aeadd00925925c9e1287f5c08f3e04ee7f26a9e23d9dbfb16149153d842'}}, 'java_security': {'observed': {'bytes': 64249, 'file': {'st_ctime_ns': 1792770278199673482, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40663555, 'st_mode': 33204, 'st_mtime_ns': 1792770278199673482, 'st_nlink': 1, 'st_size': 64249, 'st_uid': 1000}, 'sha256': '78f06ea1ce6fe10c188c99f6e4ca5631060e6e1b193ae598c0dfc6f3c3b6ac75'}, 'pin': {'bytes': 64249, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/conf/security/java.security', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/conf/security/java.security', 'sha256': '78f06ea1ce6fe10c188c99f6e4ca5631060e6e1b193ae598c0dfc6f3c3b6ac75'}}, 'jdk_modules': {'observed': {'bytes': 141608978, 'file': {'st_ctime_ns': 1792770278872627336, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40664004, 'st_mode': 33204, 'st_mtime_ns': 1792770278872627336, 'st_nlink': 1, 'st_size': 141608978, 'st_uid': 1000}, 'sha256': '4bddbec43a2fbf497528b9b0227a285e80c015c825921dc7a4181bdb4176ad36'}, 'pin': {'bytes': 141608978, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/modules', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/modules', 'sha256': '4bddbec43a2fbf497528b9b0227a285e80c015c825921dc7a4181bdb4176ad36'}}, 'jdk_release': {'observed': {'bytes': 1246, 'file': {'st_ctime_ns': 1792770279240602138, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40664019, 'st_mode': 33204, 'st_mtime_ns': 1792770279240602138, 'st_nlink': 1, 'st_size': 1246, 'st_uid': 1000}, 'sha256': 'd6854c41e3ef131089538dc4362452517b16061ebabb1931f2d287bf7ea78c3c'}, 'pin': {'bytes': 1246, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/release', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/release', 'sha256': 'd6854c41e3ef131089538dc4362452517b16061ebabb1931f2d287bf7ea78c3c'}}, 'jvm_cfg': {'observed': {'bytes': 29, 'file': {'st_ctime_ns': 1792770278329664568, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40663966, 'st_mode': 33204, 'st_mtime_ns': 1792770278329664568, 'st_nlink': 1, 'st_size': 29, 'st_uid': 1000}, 'sha256': 'aa9efb969444c1484e29adecab55a122458090616e766b2f1230ef05bc3867e0'}, 'pin': {'bytes': 29, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/jvm.cfg', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/jvm.cfg', 'sha256': 'aa9efb969444c1484e29adecab55a122458090616e766b2f1230ef05bc3867e0'}}, 'libjava': {'observed': {'bytes': 163840, 'file': {'st_ctime_ns': 1792770278348663265, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40663979, 'st_mode': 33204, 'st_mtime_ns': 1792770278348663265, 'st_nlink': 1, 'st_size': 163840, 'st_uid': 1000}, 'sha256': '39638b30e207d063cfe2c5bd19d36707f80843fe30481c8723f68e427ee4b331'}, 'pin': {'bytes': 163840, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/libjava.so', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/libjava.so', 'sha256': '39638b30e207d063cfe2c5bd19d36707f80843fe30481c8723f68e427ee4b331'}}, 'libjimage': {'observed': {'bytes': 142408, 'file': {'st_ctime_ns': 1792770278352916149, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40663983, 'st_mode': 33204, 'st_mtime_ns': 1792770278352916149, 'st_nlink': 1, 'st_size': 142408, 'st_uid': 1000}, 'sha256': 'acbf04054075e886aa29fe24fb26e35c857ce5c7fc6b48ef2ffe7683c229e87e'}, 'pin': {'bytes': 142408, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/libjimage.so', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/libjimage.so', 'sha256': 'acbf04054075e886aa29fe24fb26e35c857ce5c7fc6b48ef2ffe7683c229e87e'}}, 'libjli': {'observed': {'bytes': 93096, 'file': {'st_ctime_ns': 1792770278353662922, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40663984, 'st_mode': 33204, 'st_mtime_ns': 1792770278353662922, 'st_nlink': 1, 'st_size': 93096, 'st_uid': 1000}, 'sha256': '0c59fc8823cf5c8d25f12516b8ca38cab8e83b9695715775fcfdd5fea1df75f1'}, 'pin': {'bytes': 93096, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/libjli.so', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/libjli.so', 'sha256': '0c59fc8823cf5c8d25f12516b8ca38cab8e83b9695715775fcfdd5fea1df75f1'}}, 'libjvm': {'observed': {'bytes': 26010448, 'file': {'st_ctime_ns': 1792770279072613632, 'st_dev': 66306, 'st_gid': 1000, 'st_ino': 40664016, 'st_mode': 33204, 'st_mtime_ns': 1792770279072613632, 'st_nlink': 1, 'st_size': 26010448, 'st_uid': 1000}, 'sha256': '53aebc862cb667bae382a429af95e06bd269b27ce3ddb0d7e39b922049156f16'}, 'pin': {'bytes': 26010448, 'declared_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/server/libjvm.so', 'resolved_path': '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/lib/server/libjvm.so', 'sha256': '53aebc862cb667bae382a429af95e06bd269b27ce3ddb0d7e39b922049156f16'}}, 'signer_companion_apksig-0.9.jar': {'observed': {'bytes': 489902, 'file': {'st_ctime_ns': 1791415705113294282, 'st_dev': 66306, 'st_gid': 0, 'st_ino': 108005156, 'st_mode': 33188, 'st_mtime_ns': 1741954421000000000, 'st_nlink': 1, 'st_size': 489902, 'st_uid': 0}, 'sha256': '61186f715a98cf2473544a4bbb1fae06ab84600cf2cd6adfa7ad50f4b0e2375e'}, 'pin': {'bytes': 489902, 'declared_path': '/usr/share/java/apksig.jar', 'resolved_path': '/usr/share/java/apksig-0.9.jar', 'sha256': '61186f715a98cf2473544a4bbb1fae06ab84600cf2cd6adfa7ad50f4b0e2375e'}}}
EXPECTED_TOOL_NAMES = {'aapt', 'apksigner_jar', 'java', 'java_security', 'jdk_modules', 'jdk_release', 'jvm_cfg', 'libjava', 'libjimage', 'libjli', 'libjvm', 'signer_companion_apksig-0.9.jar'}
TOOL_EVIDENCE = {'bytes': 132796, 'sha256': 'd2df2ac82742d7cbc69b43df878af8372e2df617113492e2e8ab25c69bbc0605', 'schema': 'pocket4-successor-installed-apk-audit-v1', 'kind': 'prior actual successful batch04 tool bindings; full current identity recheck required'}
RUNNER_EVIDENCE = {'bytes': 29242, 'sha256': 'faff199c1f6218b3c01d87e44be610d6fa211de396b5e8c862c188dec59d284a', 'copied_functions_unchanged': ['now', 'run_tool']}
APK_PIN = {'declared_path': '/home/alex/work/pocket4-szzc-finite-tail-20261106-s36/com.szzc_327.apk', 'resolved_path': '/home/alex/work/pocket4-szzc-finite-tail-20261106-s36/com.szzc_327.apk', 'bytes': 220579134, 'sha256': '6c796f5073658d6f541ebbae5723d80645e6fbf6060ca816def6c3ec173e31d6'}
APK_IDENTITY = {'st_ctime_ns': '1793992371864608450', 'st_dev': '66306', 'st_gid': '1000', 'st_ino': '38803085', 'st_mode': '33024', 'st_mtime_ns': '1793992371532573018', 'st_nlink': '1', 'st_size': '220579134', 'st_uid': '1000'}

def need(value, code):
    if not value:
        raise RuntimeError(code)

def ident(fd):
    s = os.fstat(fd)
    return {k: str(getattr(s,k)) for k in FIELDS}

def digest_fd(fd, limit, deadline):
    size = os.fstat(fd).st_size
    need(0 < size <= limit, 'BOUNDED_FILE_SIZE')
    offset, digest = 0, hashlib.sha256()
    while offset < size:
        need(time.monotonic() < deadline, 'FULL_FILE_HASH_DEADLINE')
        block = os.pread(fd, min(1024*1024,size-offset),offset)
        need(bool(block), 'FULL_FILE_HASH_PROGRESS')
        offset += len(block); digest.update(block)
    return digest.hexdigest()

def census():
    result={}
    for name in os.listdir('/proc/self/fd'):
        try:
            fd=int(name);s=os.fstat(fd)
            result[name]=[os.readlink('/proc/self/fd/'+name),s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,
                          fcntl.fcntl(fd,fcntl.F_GETFD),fcntl.fcntl(fd,fcntl.F_GETFL)]
        except OSError as e:
            if e.errno not in (2,9):raise
    return result

def save(name,body):
    need(name in ('apksigner.stdout','apksigner.stderr','result.json'), 'CLOSED_EVIDENCE_NAME')
    with (ROOT/name).open('xb') as stream:
        stream.write(body);stream.flush();os.fsync(stream.fileno())
    return {'path':str(ROOT/name),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def run_tool(argv, pass_fds, receipt, end):
    """Bounded host child; retire only its own process group and keep raw output."""
    receipt.update(argv=argv, started_utc=now(), spawned=False, joined=False, timed_out=False,
                   output_capture_complete=False, automatic_retry=False, pipes_closed=False)
    proc, sel = None, selectors.DefaultSelector()
    streams, output = [], {"stdout": bytearray(), "stderr": bytearray()}
    deadline, killed = min(end, time.monotonic() + 90), False
    failure = None
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                pass_fds=tuple(pass_fds), close_fds=True, start_new_session=True, env=ENV)
        receipt.update(spawned=True, pid=proc.pid)
        streams = [proc.stdout, proc.stderr]
        for name, stream in zip(("stdout", "stderr"), streams):
            os.set_blocking(stream.fileno(), False); sel.register(stream, selectors.EVENT_READ, name)
        while sel.get_map():
            if time.monotonic() >= deadline:
                receipt["timed_out"] = True
                break
            for key, unused in sel.select(min(.2, max(0, deadline - time.monotonic()))):
                part = os.read(key.fileobj.fileno(), 65536)
                if not part:
                    sel.unregister(key.fileobj)
                    continue
                room = MAX_TOOL_OUTPUT - len(output[key.data])
                output[key.data].extend(part[:room])
                if len(part) > room:
                    receipt["output_truncated"] = True
                    raise RuntimeError("TOOL_OUTPUT_BOUND")
        if receipt["timed_out"]:
            os.killpg(proc.pid, signal.SIGKILL); killed = True
        proc.wait(timeout=5)
        receipt.update(joined=True, returncode=proc.returncode, output_capture_complete=not bool(sel.get_map()))
    except BaseException as error:
        failure = error
        receipt["error"] = {"type": type(error).__name__, "reason": str(error)[:160]}
    finally:
        try:
            if proc is not None and (proc.poll() is None or failure is not None):
                try:
                    os.killpg(proc.pid, signal.SIGKILL); killed = True
                except ProcessLookupError:
                    pass
                proc.wait(timeout=5)
            if proc is not None:
                receipt.update(joined=proc.poll() is not None, returncode=proc.returncode)
        except BaseException as error:
            receipt["retirement_error"] = {"type": type(error).__name__, "reason": str(error)[:160]}
        finally:
            for stream in streams:
                stream.close()
            sel.close()
            receipt.update(ended_utc=now(), own_group_kill_requested=killed, pipes_closed=all(x.closed for x in streams))
    return {key: bytes(value) for key, value in output.items()}

def hold_exact(name, pin, expected, held, deadline):
    path = pin['resolved_path']
    need(Path(path).is_absolute() and Path(path).resolve(strict=True).as_posix() == path,
         'EXACT_NONALIAS_INPUT_PATH:' + name)
    need(Path(pin['declared_path']).resolve(strict=True).as_posix() == path,
         'DECLARED_INPUT_ALIAS_CHANGED:' + name)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(fd); observed = ident(fd)
        need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and
             observed == {k: str(expected[k]) for k in FIELDS} and s.st_size == pin['bytes'],
             'EXACT_PREVIOUSLY_OBSERVED_FILE_IDENTITY_REQUIRED:' + name)
        need(digest_fd(fd, pin['bytes'], deadline) == pin['sha256'] and ident(fd) == observed,
             'FULL_PINNED_FILE_BYTES_CHANGED:' + name)
    except BaseException:
        os.close(fd); raise
    held.append({'name': name, 'fd': fd, 'path': path, 'declared_path': pin['declared_path'],
                 'bytes': pin['bytes'], 'sha256': pin['sha256'], 'identity': observed})
    return fd


def recheck_exact(held, deadline):
    for row in held:
        need(ident(row['fd']) == row['identity'] and
             digest_fd(row['fd'], row['bytes'], deadline) == row['sha256'],
             'HELD_INPUT_CHANGED:' + row['name'])
        fresh = os.open(row['path'], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            need(ident(fresh) == row['identity'] and
                 Path(row['path']).resolve(strict=True).as_posix() == row['path'] and
                 Path(row['declared_path']).resolve(strict=True).as_posix() == row['path'],
                 'INPUT_PATH_REPLACED:' + row['name'])
        finally:
            os.close(fresh)


def main():
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000 and
         sys.argv[1:] == ['--observe-signature-as-existing-owner-once'],
         'EXACT_UNPRIVILEGED_EXISTING_TOOL_OWNER_ENTRY')
    need(ROOT.parent.resolve() == ROOT.parent, 'FIXED_PRIVATE_PARENT')
    os.umask(0o077); before = census(); ROOT.mkdir(mode=0o700)
    held, deadline = [], time.monotonic() + 170
    result = {'schema': 'pocket4-szzc-operator-signature-observation-v1', 'ok': False, 'errors': [],
        'actual_uid': os.getuid(), 'actual_euid': os.geteuid(), 'root_execution': False,
        'Android_commands': 0, 'Main_actions': 0, 'installs': 0, 'UI_actions': 0,
        'permission_changes': 0, 'automatic_retry': False, 'production_ready': False,
        's37_failed_root_owner_assumption_preserved': True,
        'root_private_dependency_files_opened': False, 'old_files_modified_or_deleted': False,
        'current_manifest_verified': False, 'candidate_manifest_verified': False,
        'newer_version_claimed': False, 'commands': [],
        'tool_identity_basis': TOOL_EVIDENCE, 'runner_source_basis': RUNNER_EVIDENCE,
        'installed_signature_reference_kind': 'saved PackageManager certificate digest; not current APK cryptographic verification',
        'installed_signer_reference': SAVED_PM_SIGNER}
    try:
        need(len(TOOL_BINDINGS) == 12 and set(TOOL_BINDINGS) == EXPECTED_TOOL_NAMES,
             'EXACT_PRIOR_TWELVE_TOOL_INPUTS')
        for name, row in TOOL_BINDINGS.items():
            hold_exact(name, row['pin'], row['observed']['file'], held, deadline)
        af = hold_exact('complete_s36_APK', APK_PIN, APK_IDENTITY, held, deadline)
        result['candidate'] = {k: v for k, v in held[-1].items() if k != 'fd'}
        recheck_exact(held, deadline)
        argv = [TOOL_BINDINGS['java']['pin']['resolved_path'], '-Xmx256m', '-jar',
                TOOL_BINDINGS['apksigner_jar']['pin']['resolved_path'], 'verify', '--verbose',
                '--print-certs', '/proc/self/fd/' + str(af)]
        command = {'name': 'apksigner-verify', 'purpose': 'cryptographic signature observation only',
                   'execution_uid': 1000}
        result['commands'].append(command)
        need(time.monotonic() + 5 < deadline, 'SIGNATURE_DEADLINE_BEFORE_SPAWN')
        outputs = run_tool(argv, (af,), command, deadline)
        for stream, raw in outputs.items():
            command[stream] = save('apksigner.' + stream, raw)
            if len(raw) <= 32768:
                command[stream + '_original_utf8'] = raw.decode('utf-8', 'strict')
        need(command.get('returncode') == 0 and command.get('joined') is True and
             command.get('pipes_closed') is True and command.get('output_capture_complete') is True and
             command.get('timed_out') is False and command.get('own_group_kill_requested') is False and
             not command.get('error') and not command.get('retirement_error') and
             not command.get('output_truncated'), 'COMPLETE_NORMAL_SIGNATURE_VERIFIER_EXIT_REQUIRED')
        certs = re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([0-9a-f]{64})$',
                           outputs['stdout'].decode('utf-8', 'strict'), re.M)
        need(certs and len(certs) == len(set(certs)), 'EXACT_UNIQUE_SIGNER_DIGESTS')
        recheck_exact(held, deadline)
        result.update(ok=True, signature_verified=True, signer_certificate_sha256=certs,
            signer_matches_saved_PM_reference=certs == [SAVED_PM_SIGNER],
            all_held_files_full_identity_and_hash_unchanged=True,
            held_input_bindings=[{k: v for k, v in row.items() if k != 'fd'} for row in held],
            update_eligibility='NOT_ASSESSED_PENDING_MANIFEST_CURRENT_SCOPE_AND_VERSION')
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
    finally:
        close_errors = []
        for row in reversed(held):
            try:
                os.close(row['fd'])
            except OSError as error:
                close_errors.append({'name': row['name'], 'errno': error.errno})
        result['held_files'] = {'acquired': len(held), 'closed': len(held) - len(close_errors), 'errors': close_errors}
        if close_errors:
            result['ok'] = False
    result['original_descriptor_identities_restored'] = census() == before
    result['ok'] = result['ok'] and result['original_descriptor_identities_restored']
    result['status'] = 'SIGNATURE_OBSERVED_NOT_INSTALLED' if result['ok'] else 'SIGNATURE_OBSERVATION_FAILED'
    raw = (json.dumps(result, sort_keys=True) + '\n').encode()
    save('result.json', raw); print(raw.decode(), end='', flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
