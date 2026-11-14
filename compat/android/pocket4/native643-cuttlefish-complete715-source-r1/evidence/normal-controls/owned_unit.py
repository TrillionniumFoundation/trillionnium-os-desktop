"""One fixed ordinary unit: nonce/invocation binding and bounded retirement.

An absent unit without a matching actual start witness is UNKNOWN, including
after the bound expires.  This code neither retries StartTransientUnit nor
stops an unbound unit.  The caller first reaps its direct Popen child (or records
that child's UNKNOWN state), then independently calls reconcile().
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

BASE = Path('/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/tools-build-cuttlefish643-20261113-takeover-r1')
ROLE = BASE
UNIT = 'p4-native643-cuttlefish-normal-20261113-takeover-r1.service'
CGROUP = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice') / UNIT
INTENT = ROLE / 'control/intent.json'
STARTED = ROLE / 'qualification/owned-unit-started.json'
BOOT = 'b1620269-aaef-43e7-bf47-bc6eb1c1a447'
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
          'st_size', 'st_mtime_ns', 'st_ctime_ns')
PROPERTIES = 'Id,Description,InvocationID,LoadState,ActiveState,SubState,MainPID,ControlGroup,Result,ExecMainCode,ExecMainStatus,Job'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def f9(st):
    return [getattr(st, key) for key in FIELDS]


def public_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == 1000
             and before.st_nlink == 1 and 0 < before.st_size < 65536,
             'bounded fixed ordinary unit receipt')
        data = bytearray()
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            data.extend(block)
            need(len(data) <= before.st_size, 'receipt grew while held')
        need(len(data) == before.st_size and f9(before) == f9(os.fstat(fd)) == f9(path.lstat()),
             'same complete held/named unit receipt')
        return json.loads(data), {'path': str(path), 'bytes': len(data),
                                  'sha256': hashlib.sha256(data).hexdigest(), 'identity': f9(before)}
    finally:
        os.close(fd)


def description(nonce, controller):
    need(re.fullmatch('[0-9a-f]{64}', nonce) is not None, 'fresh 256-bit unit nonce')
    need(controller['path'] == str(ROLE / 'control/build_normal_tools.py')
         and type(controller['bytes']) is int and controller['bytes'] > 0
         and re.fullmatch('[0-9a-f]{64}', controller['sha256']) is not None,
         'fixed controller role')
    return 'native604-ndk-ordinary:' + nonce + ':' + controller['sha256']


def receipt(intent, expected_controller):
    need(intent['unit'] == UNIT and intent['controller'] == expected_controller
         and intent['description'] == description(intent['nonce'], expected_controller)
         and intent['boot_id'] == BOOT and intent['automatic_retry'] is False,
         'this exact ordinary launch intent')
    return intent


def started_proof(value, intent):
    need(value['schema'] == 'native604-ndk-owned-unit-started-r1'
         and value['unit'] == UNIT and value['nonce'] == intent['nonce']
         and value['description'] == intent['description']
         and value['controller'] == intent['controller'] and value['boot_id'] == BOOT
         and value['cgroup'] == str(CGROUP)
         and type(value['pid']) is int and value['pid'] > 1
         and type(value['start_ticks']) is int and value['start_ticks'] > 0
         and re.fullmatch('[0-9a-f]{32}', value['invocation_id']) is not None
         and value['invocation_id'] != '0' * 32,
         'actual controller nonce/invocation/cgroup/generation proof')
    return value


def generation_present(proof):
    path = Path('/proc') / str(proof['pid'])
    try:
        proc = os.open(path, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return False
    try:
        fd = os.open('stat', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=proc)
        try:
            raw = os.read(fd, 8192)
            need(len(raw) < 8192 and raw.endswith(b'\n'), 'bounded complete current proc stat')
        finally:
            os.close(fd)
        fields = raw[raw.rfind(b')') + 2:].split()
        need(len(fields) > 19, 'complete proc generation fields')
        return int(fields[19]) == proof['start_ticks']
    except FileNotFoundError:
        return False
    finally:
        os.close(proc)


def reconcile(capture, env, save, expected_controller, phase, deadline_seconds=45):
    """Return actual retirement or UNKNOWN; save errors cannot bypass cleanup."""
    need(phase in ('launcher', 'entry') and deadline_seconds == 45, 'fixed reconciliation bound')
    report = {'schema': 'native604-ndk-owned-unit-reconciliation-r1', 'phase': phase,
              'unit': UNIT, 'expected_cgroup': str(CGROUP), 'retired': False,
              'state': 'UNKNOWN', 'errors': [], 'observations': [], 'stop_requests': [], 'attempts': [],
              'deadline_seconds': deadline_seconds, 'started_ns': time.time_ns(),
              'no_start_replay': True, 'no_unbound_stop': True}
    deadline = time.monotonic() + deadline_seconds
    intent = None
    invocation = None
    proof = None
    conflicted = False
    stopped = False

    def record_stream(name, data):
        try:
            return save(name, data)
        except BaseException as exc:
            report['errors'].append({'stage': 'save-' + name, 'type': type(exc).__name__, 'message': str(exc)})
            return {'unpersisted': True, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

    def command(argv, label, timeout):
        row, out, err = capture(argv, cwd=ROLE, env=env, timeout=timeout)
        record = {'process': row, 'stdout': record_stream(phase + '-' + label + '.stdout', out),
                  'stderr': record_stream(phase + '-' + label + '.stderr', err)}
        # Preserve this child's identity even when the retirement gate rejects it.
        report['attempts'].append(record)
        need(row['retirement_known'] and not row['timed_out'] and not row['forced_termination']
             and not row['errors'], 'unit query/stop child retirement is incomplete')
        return row, out, err, record

    try:
        need(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT, 'same host boot')
        try:
            raw_intent, intent_ref = public_json(INTENT)
            intent = receipt(raw_intent, expected_controller)
            report['intent'] = intent_ref
        except FileNotFoundError:
            report['intent_absent'] = True
        for sequence in range(24):
            # capture's bounded TERM/KILL/reap fallback may take a further ten
            # seconds, so leave explicit space before starting another query.
            if time.monotonic() + 12 >= deadline:
                break
            if intent is None:
                try:
                    raw_intent, intent_ref = public_json(INTENT)
                    intent = receipt(raw_intent, expected_controller)
                    report['intent'] = intent_ref
                except FileNotFoundError:
                    pass
            if intent is not None and proof is None:
                try:
                    value, start_ref = public_json(STARTED)
                    proof = started_proof(value, intent)
                    report['actual_started'] = start_ref
                    report['actual_started_value'] = proof
                    if invocation is not None and invocation != proof['invocation_id']:
                        conflicted = True
                        raise RuntimeError('controller receipt invocation drift')
                    invocation = proof['invocation_id']
                except FileNotFoundError:
                    pass
            row, out, err, record = command(
                ['/usr/bin/systemctl', '--user', 'show', UNIT, '--property=' + PROPERTIES],
                'show-%02d' % sequence, 2)
            report['observations'].append(record)
            need(row['returncode'] == 0 and not err, 'complete authoritative user-unit show')
            unit = dict(line.split('=', 1) for line in out.decode().splitlines())
            need(set(unit) == set(PROPERTIES.split(',')) and unit['Id'] == UNIT, 'complete exact unit properties')
            record['unit'] = unit
            exists = unit['LoadState'] != 'not-found'
            if exists:
                if intent is None or unit['Description'] != intent['description']:
                    conflicted = True
                    raise RuntimeError('unit Description is not this launch generation; no stop')
                observed = unit['InvocationID']
                if observed:
                    need(re.fullmatch('[0-9a-f]{32}', observed) is not None and observed != '0' * 32,
                         'actual nonzero unit invocation')
                    if invocation is not None and invocation != observed:
                        conflicted = True
                        raise RuntimeError('unit invocation changed; no stop')
                    invocation = observed
                    report['actual_invocation_id'] = invocation
                need(not unit['ControlGroup'] or '/sys/fs/cgroup' + unit['ControlGroup'] == str(CGROUP),
                     'owned unit remains in exact app.slice cgroup')
            gone = not CGROUP.exists()
            controller_gone = proof is None or not generation_present(proof)
            terminal = unit['MainPID'] == '0' and not unit['ControlGroup'] and not unit['Job']
            terminal = terminal and unit['ActiveState'] in ('inactive', 'failed')
            if invocation is not None and terminal and gone and controller_gone:
                report.update(retired=True, state='MATCHED_INVOCATION_RETIRED',
                              actual_invocation_id=invocation, final_unit=unit,
                              cgroup_absent=True, original_controller_generation_absent=controller_gone)
                break
            # A missing unit without a matched actual invocation is evidence of
            # neither acceptance nor nonacceptance.  Keep UNKNOWN and observe.
            if exists and invocation is not None and not stopped and time.monotonic() + 19 < deadline:
                need(intent is not None and unit['Description'] == intent['description']
                     and unit['InvocationID'] == invocation and not conflicted,
                     'immediately revalidated nonce and actual invocation before stop')
                stop, sout, serr, srecord = command(
                    ['/usr/bin/systemctl', '--user', 'stop', UNIT], 'stop', 8)
                report['stop_requests'].append(srecord)
                stopped = True
                need(stop['returncode'] == 0 and not serr, 'matching unit stop completion')
            time.sleep(0.1)
    except BaseException as exc:
        report['errors'].append({'stage': 'reconciliation', 'type': type(exc).__name__, 'message': str(exc)})
    finally:
        report['identity_conflict'] = conflicted
        report['finished_ns'] = time.time_ns()
        report['observed_cgroup_absent_at_return'] = not CGROUP.exists()
        if conflicted:
            report['retired'] = False
            report['state'] = 'UNKNOWN_IDENTITY_CONFLICT'
    return report
