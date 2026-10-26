"""Built into the original fixed helper; never a service or an effect owner.

This file is not executable on its own. build_receiver.py inserts it before the
original dispatch function and preserves the existing CLI and global lock.
"""


def _organ_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_JSON_FIELD')
        result[key] = value
    return result


def _organ_nonfinite(value):
    raise ControlError('NONFINITE_JSON')


def _organ_json(raw):
    require(isinstance(raw, bytes) and len(raw) <= 16384, 'ORGAN_PAYLOAD_TOO_LARGE')
    try:
        value = json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=_organ_pairs,
                           parse_constant=_organ_nonfinite)
        canonical = json.dumps(value, ensure_ascii=False, sort_keys=True,
                               separators=(',', ':'), allow_nan=False).encode('utf-8', 'strict')
    except ControlError:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise ControlError('INVALID_ORGAN_JSON') from None
    require(isinstance(value, dict) and raw == canonical, 'NONCANONICAL_ORGAN_JSON')
    return value


def _organ_start_ticks(path):
    # comm may contain spaces and closing parentheses. Field 22 follows the
    # final ')' and is field 19 in the remaining zero-based list.
    raw = open(path, encoding='ascii').read(8192)
    fields = raw.rsplit(')', 1)[1].split()
    require(len(fields) >= 20 and fields[19].isdigit(), 'INVALID_CELL_START_TIME')
    return fields[19]


def _organ_generation(init):
    boot = open('/proc/sys/kernel/random/boot_id', encoding='ascii').read(64).strip()
    require(bool(re.fullmatch('[0-9a-f-]{36}', boot)), 'INVALID_HOST_BOOT_ID')
    names = {name: os.readlink(f'/proc/{init}/ns/{name}') for name in ('mnt', 'pid', 'time')}
    # Android elapsedRealtime and the host's CLOCK_BOOTTIME are compared only
    # in this explicitly verified common time namespace.
    require(names['time'] == os.readlink('/proc/self/ns/time'), 'TIME_NAMESPACE_MISMATCH')
    return {'boot_id': boot, 'init_start_ticks': _organ_start_ticks(f'/proc/{init}/stat'),
            'mount_namespace': names['mnt'], 'pid_namespace': names['pid'],
            'time_namespace': names['time']}


class _OrganCell:
    """One discovered production cell, pinned namespace FDs, no retargeting."""

    def __init__(self):
        self.deadline = time.clock_gettime(time.CLOCK_BOOTTIME) + 55
        self.fds = {}
        self.init, self.env, _ = discover()
        self.generation = _organ_generation(self.init)
        try:
            for name in ('mnt', 'pid', 'uts', 'ipc'):
                self.fds[name] = os.open(f'/proc/{self.init}/ns/{name}', os.O_RDONLY | os.O_CLOEXEC)
            require(self.generation == _organ_generation(self.init), 'CELL_GENERATION_CHANGED')
            for name, key in [('mnt', 'mount_namespace'), ('pid', 'pid_namespace')]:
                require(os.readlink(f'/proc/self/fd/{self.fds[name]}') == self.generation[key],
                        'CELL_NAMESPACE_CHANGED')
        except BaseException:
            self.close()
            raise

    def close(self):
        for fd in self.fds.values():
            os.close(fd)
        self.fds.clear()

    def run(self, args, timeout=30):
        require(self.generation == _organ_generation(self.init), 'CELL_GENERATION_CHANGED')
        remaining = min(timeout, self.deadline - time.clock_gettime(time.CLOCK_BOOTTIME))
        require(remaining > 2, 'ORGAN_DEADLINE_EXCEEDED')
        switches = {'mnt': 'mount', 'pid': 'pid', 'uts': 'uts', 'ipc': 'ipc'}
        cmd = ['/usr/bin/nsenter'] + [
            '--' + switches[name] + '=/proc/self/fd/' + str(fd) for name, fd in self.fds.items()]
        cmd += ['/system/bin/env'] + [key + '=' + self.env[key] for key in sorted(self.env)]
        cmd += ['/system/xbin/su', '2000', '/system/bin/timeout', '-k', '1',
                str(max(1, remaining - 2))] + list(args)
        # Every namespace descriptor refers to the original cell even if its
        # numeric host PID is reused. No discover() call exists on this path.
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=remaining, env=HOST_ENV,
                                 pass_fds=tuple(self.fds.values()))
        require(process.returncode == 0, 'ORGAN_TRANSPORT_UNKNOWN',
                outcome_unknown=True, automatic_retry=False)
        require(self.generation == _organ_generation(self.init), 'CELL_GENERATION_CHANGED',
                outcome_unknown=True, automatic_retry=False)
        require(time.clock_gettime(time.CLOCK_BOOTTIME) < self.deadline,
                'ORGAN_DEADLINE_EXCEEDED', outcome_unknown=True, automatic_retry=False)
        return process.stdout


def _organ_request(r):
    op = r.get('op')
    if op == 'organ-observe':
        require(set(r) == {'op', 'package', 'resource_id'}, 'UNKNOWN_ORGAN_ARGUMENT')
        pkg = package_name(r['package'])
        resource = r['resource_id']
        require(isinstance(resource, str) and bool(re.fullmatch(
            re.escape(pkg) + r':id/[A-Za-z_][A-Za-z0-9_]*', resource)), 'EXACT_RESOURCE_ID_REQUIRED')
        return {'op': 'find', 'expected_package': pkg, 'selector': {'id': resource, 'package': pkg},
                'display': 0, 'accessibility_mode': 'none',
                'organ': {'mode': 'observe', 'package': pkg, 'resource_id': resource}}
    require(op in ('organ-set-text', 'organ-readback'), 'UNSUPPORTED_ORGAN_ACTION')
    require(set(r) == {'op', 'payload_base64', 'payload_sha256'}, 'UNKNOWN_ORGAN_ARGUMENT')
    try:
        require(isinstance(r['payload_base64'], str) and len(r['payload_base64']) <= 22000,
                'ORGAN_PAYLOAD_TOO_LARGE')
        raw = base64.b64decode(r['payload_base64'], validate=True)
    except (ValueError, TypeError):
        raise ControlError('INVALID_ORGAN_ENCODING') from None
    payload = _organ_json(raw)
    require(hashlib.sha256(raw).hexdigest() == digest(r['payload_sha256']), 'ORGAN_PAYLOAD_HASH_MISMATCH')
    require(set(payload) == {'schema_version', 'action', 'operation_id', 'destination_id',
                             'observation', 'value', 'expires_elapsed_ms'}, 'INVALID_ORGAN_PAYLOAD')
    require(type(payload['schema_version']) is int and payload['schema_version'] == 1
            and payload['action'] == 'set_text', 'INVALID_ORGAN_PAYLOAD')
    operation = payload['operation_id']
    require(isinstance(operation, str) and bool(re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', operation)),
            'INVALID_ORGAN_OPERATION')
    value = payload['value']
    require(isinstance(value, str) and '\0' not in value and len(value.encode('utf-8')) <= 4096,
            'INVALID_ORGAN_TEXT')
    observation = payload['observation']
    require(isinstance(observation, dict) and isinstance(observation.get('window'), dict)
            and isinstance(observation.get('target'), dict), 'INVALID_ORGAN_OBSERVATION')
    pkg = package_name(observation['window'].get('package'))
    resource = observation['target'].get('resource_id')
    require(isinstance(resource, str) and bool(re.fullmatch(
        re.escape(pkg) + r':id/[A-Za-z_][A-Za-z0-9_]*', resource)), 'EXACT_RESOURCE_ID_REQUIRED')
    require(type(payload['expires_elapsed_ms']) is int and 0 < payload['expires_elapsed_ms'] < 2**53,
            'INVALID_ORGAN_DEADLINE')
    request = {'op': 'set-text' if op == 'organ-set-text' else 'find', 'expected_package': pkg,
               'selector': {'id': resource, 'package': pkg}, 'display': 0, 'accessibility_mode': 'none',
               'organ': {'mode': 'apply' if op == 'organ-set-text' else 'readback',
                         'payload_base64': r['payload_base64'], 'payload_sha256': r['payload_sha256']}}
    if op == 'organ-set-text':
        request['value'] = value
    return request


def _organ_dispatch(r):
    request = _organ_request(r)
    # No installed same-signer strict receiver is independently qualified in
    # this source profile. The old APK ignores the organ binding and can write
    # before the response protocol check below. Keep every strict effect closed
    # before cell discovery or ui(); caller fields cannot supply qualification.
    require(request['op'] != 'set-text', 'ORGAN_EFFECT_RECEIVER_NOT_QUALIFIED',
            action_taken=False, action_submitted=False, outcome_unknown=False,
            automatic_retry=False)
    cell = _OrganCell()
    original_arun = globals()['arun']
    submitted = False
    try:
        if request['organ']['mode'] != 'observe':
            raw = base64.b64decode(request['organ']['payload_base64'], validate=True)
            payload = _organ_json(raw)
            require(payload['observation'].get('generation') == cell.generation,
                    'CELL_GENERATION_CHANGED', action_taken=False)
            if request['organ']['mode'] == 'apply':
                require(time.clock_gettime(time.CLOCK_BOOTTIME) * 1000 < payload['expires_elapsed_ms'],
                        'ORGAN_DEADLINE_EXCEEDED', action_taken=False)
        request['organ']['host_generation'] = cell.generation
        request['organ']['transport_expires_elapsed_ms'] = int(cell.deadline * 1000)
        globals()['arun'] = cell.run
        submitted = True
        result = ui(request)
        # The actual instrumentation must return these fields. Never synthesize
        # a receiver binding, a readback proof or a success bit in this helper.
        require(result.get('organ_protocol') == 'pocket4-bound-text-v1'
                and result.get('receiver_generation') == cell.generation,
                'ORGAN_RECEIVER_UNQUALIFIED', outcome_unknown=request['op'] == 'set-text',
                automatic_retry=False)
        if request['organ']['mode'] != 'observe':
            require(result.get('operation_id') == payload['operation_id']
                    and result.get('payload_sha256') == request['organ']['payload_sha256'],
                    'ORGAN_RECEIPT_IDENTITY_MISMATCH', outcome_unknown=request['op'] == 'set-text',
                    automatic_retry=False)
        return result
    except ControlError as error:
        if submitted and request['op'] == 'set-text' and 'outcome_unknown' not in error.details:
            error.details.update(outcome_unknown=True, automatic_retry=False)
        raise
    except Exception:
        raise ControlError('ORGAN_RESULT_UNKNOWN', outcome_unknown=submitted and request['op'] == 'set-text',
                           automatic_retry=False) from None
    finally:
        globals()['arun'] = original_arun
        cell.close()
