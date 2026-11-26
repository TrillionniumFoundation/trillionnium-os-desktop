"""One source-owned, reversible user-0 font-scale transaction.

This module has no subprocess entry and accepts no caller-supplied command,
setting name, result, or success flag.  Its only transport is the existing
same-Main Flow and its original recorder/retirement boundary.  It leaves
unknown or externally changed state unqualified, and never retries a write.
"""
import hashlib
import math
import re
import struct
import time

READ_VALUE = ('/system/bin/settings', '--user', '0', 'get', 'system', 'font_scale')
READ_CONFIG = ('/system/bin/am', 'get-config', '--proto')
PREFIX = ('/system/bin/settings', '--user', '0')
MAX_SAMPLES = 12
EPSILON = 0.00001


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def provider_value(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 80 and raw.endswith(b'\n')
         and raw.count(b'\n') == 1, 'ONE_BOUNDED_FONT_SCALE_PROVIDER_VALUE')
    value = raw[:-1].decode('ascii', 'strict')
    if value == 'null':
        return {'present': False, 'text': None, 'effective': 1.0}
    need(re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]{1,8})?', value) is not None,
         'CANONICAL_FINITE_FONT_SCALE_VALUE')
    number = float(value)
    need(math.isfinite(number) and 0.5 <= number <= 2.0, 'FONT_SCALE_OUTSIDE_REVIEWED_RANGE')
    return {'present': True, 'text': value, 'effective': number}


def _varint(raw, offset):
    value = 0
    for shift in range(0, 70, 7):
        need(offset < len(raw), 'TRUNCATED_CONFIGURATION_VARINT')
        item = raw[offset]; offset += 1
        need(shift != 63 or item < 2, 'CONFIGURATION_VARINT_OVERFLOW')
        value |= (item & 127) << shift
        if item < 128:
            need(shift == 0 or item != 0, 'NONCANONICAL_CONFIGURATION_VARINT')
            return value, offset
    raise RuntimeError('UNBOUNDED_CONFIGURATION_VARINT')


def _fields(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 65536, 'BOUNDED_CONFIGURATION_PROTO_REQUIRED')
    result = []; offset = 0
    while offset < len(raw):
        start = offset; tag, offset = _varint(raw, offset)
        number, wire = tag >> 3, tag & 7
        need(0 < number < (1 << 29) and len(result) < 128, 'CONFIGURATION_FIELD_BOUND')
        if wire == 0:
            value, end = _varint(raw, offset)
            payload = raw[offset:end]; offset = end
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            need(offset + size <= len(raw), 'TRUNCATED_FIXED_CONFIGURATION_FIELD')
            payload = raw[offset:offset + size]; offset += size
        elif wire == 2:
            size, offset = _varint(raw, offset)
            need(size <= 65536 and offset + size <= len(raw), 'TRUNCATED_CONFIGURATION_MESSAGE')
            payload = raw[offset:offset + size]; offset += size
        else:
            raise RuntimeError('UNSUPPORTED_CONFIGURATION_WIRE_TYPE')
        result.append((number, wire, payload, raw[start:offset]))
    return result


def _one(rows, number, wire):
    found = [row for row in rows if row[0] == number]
    need(len(found) == 1 and found[0][1] == wire, 'ONE_TYPED_CONFIGURATION_FIELD_REQUIRED')
    return found[0][2]


def configuration(raw):
    # Selected normal AOSP: GlobalConfiguration.resources(1) ->
    # ResourcesConfiguration.configuration(1) -> Configuration.font_scale(1).
    global_rows = _fields(raw)
    need({row[0] for row in global_rows} == {1} and len(global_rows) == 1,
         'ONLY_REQUESTED_GLOBAL_RESOURCE_CONFIGURATION')
    resource_rows = _fields(_one(global_rows, 1, 2))
    need(all(row[0] in (1, 2, 3, 4) for row in resource_rows)
         and len(resource_rows) == len({row[0] for row in resource_rows}),
         'UNIQUE_NORMAL_RESOURCE_CONFIGURATION_FIELDS')
    config_rows = _fields(_one(resource_rows, 1, 2))
    need(all(1 <= row[0] <= 22 for row in config_rows)
         and len(config_rows) == len({row[0] for row in config_rows}),
         'EXACT_SELECTED_CONFIGURATION_SCHEMA')
    scale = struct.unpack('<f', _one(config_rows, 1, 5))[0]
    need(math.isfinite(scale) and 0.5 <= scale <= 2.0, 'ACTUAL_CONFIGURATION_FONT_SCALE_BOUND')
    complement = [row[3].hex() for row in config_rows if row[0] != 1]
    resource_complement = [row[3].hex() for row in resource_rows if row[0] != 1]
    return {'font_scale': scale,
            'other_configuration_fields': sorted(complement),
            'resource_fields': sorted(resource_complement),
            'raw_sha256': hashlib.sha256(raw).hexdigest()}


def same_other_configuration(before, after):
    need(before['other_configuration_fields'] == after['other_configuration_fields']
         and before['resource_fields'] == after['resource_fields'],
         'OTHER_FRAMEWORK_CONFIGURATION_CHANGED')


class Roundtrip:
    def __init__(self, session):
        self.session = session
        self.sequence = 0
        self.pending_command = None
        self.original = None
        self.original_configuration = None
        self.selected = None
        self.state = 'not_started'
        self.write_count = 0
        self.read_count = 0
        self.commands = []
        self.snapshots = []
        self.apply_claim = None
        self.reopen_claim = None
        self.applied = False
        self.reopened = False
        self.restored = False

    def admit(self, flow, argv, timeout, mutation):
        expected = self.pending_command
        need(expected is not None and expected['flow'] is flow
             and expected['argv'] == argv and expected['mutation'] is mutation
             and timeout == 20 and not expected['sent']
             and flow.session is self.session and flow.phase in ('inspect', 'cleanup'),
             'ONLY_THIS_LIVE_SOURCE_OWNED_FONT_SCALE_OPERATION')
        if mutation:
            need(self.original is not None and self.selected in ('1.0', '1.15')
                 and self.write_count < 2, 'TWO_FIXED_SETTING_WRITES_ONLY')
            apply = list(PREFIX + ('put', 'system', 'font_scale', self.selected))
            restore = list(PREFIX + (('put', 'system', 'font_scale', self.original['text'])
                                    if self.original['present'] else
                                    ('delete', 'system', 'font_scale')))
            need((self.write_count == 0 and self.state == 'apply_intent' and argv == apply)
                 or (self.write_count == 1 and self.state == 'restore_intent' and argv == restore),
                 'ONLY_ORIGINAL_STRING_OR_ABSENCE_CAN_BE_RESTORED')
            self.write_count += 1
        else:
            need(tuple(argv) in (READ_VALUE, READ_CONFIG) and self.read_count < 96,
                 'ONLY_BOUNDED_FONT_SCALE_AND_CONFIGURATION_READS')
            self.read_count += 1
        expected['sent'] = True

    def _command(self, flow, argv, *, mutation=False, label):
        self.session.guard(flow)
        need(self.pending_command is None and self.sequence < 100,
             'SETTING_COMMAND_PENDING_OR_BUDGET_EXHAUSTED')
        self.sequence += 1
        previous = (flow.step, flow.bridge, flow.command_index)
        name = 'font-scale-%03d-%s' % (self.sequence, label)
        flow._new_step(name, 'fixed-font-scale', {'argv': argv}, mutation)
        flow._bridge()
        self.pending_command = {'flow': flow, 'argv': list(argv), 'mutation': mutation,
                                'sent': False, 'step': str(flow.step)}
        step = flow.step
        try:
            raw = flow.android(list(argv), 20, mutation=mutation)
            result_ref = flow.c.regular(step / 'command-001.result.json', contents=False)
            result = flow.c.parse(flow.c.read_ref(result_ref))
            need(result.get('host_retirement_proved') is True
                 and result.get('evidence_complete') is True
                 and result.get('returncode') == 0 and result.get('timed_out') is False
                 and result.get('errors') == [] and result.get('first_error') is None
                 and type(result.get('argv')) is list
                 and result['argv'][-len(argv):] == list(argv)
                 and self.pending_command['sent'] is True,
                 'ACTUAL_FIXED_SETTING_COMMAND_NOT_FULLY_RETIRED')
            need(flow.c.read_ref(result['stdout']) == raw, 'SETTING_STDOUT_RECEIPT_DIFFERS')
            flow.c.read_ref(result['stderr'])
            self.commands.append({'operation': label, 'argv': list(argv), 'mutation': mutation,
                                  'result': result_ref, 'stdout': result['stdout'],
                                  'stderr': result['stderr']})
            self.pending_command = None
            flow.guard()
            return raw
        except BaseException:
            # The original BoundArun/RecorderBridge poison remains authoritative.
            # No fresh Flow or new command is manufactured to evade that poison.
            if mutation and self.pending_command is not None and self.pending_command['sent']:
                self.state = 'dispatch_or_postguard_unknown'
            raise
        finally:
            flow.step, flow.bridge, flow.command_index = previous

    def _read(self, flow, phase):
        raw = self._command(flow, list(READ_VALUE), label=phase + '-value')
        value = provider_value(raw)
        config_raw = self._command(flow, list(READ_CONFIG), label=phase + '-config')
        config = configuration(config_raw)
        snapshot = {'phase': phase, 'provider': value, 'configuration': config,
                    'provider_command': self.commands[-2], 'configuration_command': self.commands[-1],
                    'scope': flow.scope_ref}
        self.snapshots.append(snapshot)
        return value, config

    def _settle(self, flow, expected, phase):
        for attempt in range(MAX_SAMPLES):
            value, config = self._read(flow, phase + '-%02d' % attempt)
            need(value == expected, 'FONT_SCALE_CHANGED_OUTSIDE_THIS_TRANSACTION')
            same_other_configuration(self.original_configuration, config)
            if abs(config['font_scale'] - expected['effective']) <= EPSILON:
                return value, config
            self.session.guard(flow)
            need(time.monotonic() + 0.25 < flow.deadline, 'NO_FONT_SCALE_OBSERVATION_BUDGET')
            time.sleep(0.25)
        raise RuntimeError('FONT_SCALE_EFFECT_NOT_OBSERVED_WITHIN_BOUND')

    def apply(self, flow):
        need(self.state == 'not_started' and self.original is None, 'FONT_SCALE_APPLY_IS_ONCE_ONLY')
        claim, claim_ref = self.session.require_owned_task(flow)
        self.apply_claim = claim_ref
        with flow.c.locked('/run/lock/android-digitalis-actions.lock'):
            original, config = self._read(flow, 'original')
            need(abs(original['effective'] - config['font_scale']) <= EPSILON,
                 'ORIGINAL_PROVIDER_AND_FRAMEWORK_CONFIGURATION_DISAGREE')
            self.original = original
            self.original_configuration = config
            self.selected = '1.0' if abs(original['effective'] - 1.15) <= EPSILON else '1.15'
            self.session.require_owned_task(flow)
            second, second_config = self._read(flow, 'before-apply')
            need(second == original, 'ORIGINAL_SETTING_CHANGED_BEFORE_APPLY')
            same_other_configuration(config, second_config)
            need(abs(second_config['font_scale'] - original['effective']) <= EPSILON,
                 'ORIGINAL_EFFECT_CHANGED_BEFORE_APPLY')
            self.state = 'apply_intent'
            raw = self._command(flow, list(PREFIX + ('put', 'system', 'font_scale', self.selected)),
                                mutation=True, label='apply')
            self.state = 'applied_awaiting_effect'
            need(raw == b'', 'UNEXPECTED_SETTING_PUT_OUTPUT')
            expected = {'present': True, 'text': self.selected, 'effective': float(self.selected)}
            self._settle(flow, expected, 'applied')
            self.applied = True
            self.state = 'applied_verified'

    def verify_reopened(self, flow):
        need(self.state == 'applied_verified' and self.applied and not self.reopened,
             'REOPEN_REQUIRES_THIS_OBSERVED_APPLY')
        _, claim = self.session.require_owned_task(flow)
        need(claim != self.apply_claim and self.apply_claim in self.session.closed_claims,
             'A_DISTINCT_NORMAL_REOPEN_AFTER_FIRST_TASK_CLOSE_REQUIRED')
        expected = {'present': True, 'text': self.selected, 'effective': float(self.selected)}
        self._settle(flow, expected, 'reopened')
        self.reopen_claim = claim
        self.reopened = True

    def restore(self, flow, *, failure_cleanup=False):
        need(self.original is not None and self.write_count == 1 and not self.restored
             and self.pending_command is None
             and self.state in ('applied_awaiting_effect', 'applied_verified'),
             'RESTORE_REQUIRES_KNOWN_RETIRED_OWNED_APPLY')
        need(failure_cleanup or self.reopened, 'NORMAL_REOPEN_MUST_PRECEDE_NORMAL_RESTORE')
        # This is a compare-before-write under the shared normal action lock,
        # not a claim that SettingsProvider implements compare-and-swap.
        with flow.c.locked('/run/lock/android-digitalis-actions.lock'):
            value, config = self._read(flow, 'before-restore')
            expected = {'present': True, 'text': self.selected, 'effective': float(self.selected)}
            need(value == expected, 'THIRD_PARTY_SETTING_VALUE_MUST_NOT_BE_OVERWRITTEN')
            same_other_configuration(self.original_configuration, config)
            self.state = 'restore_intent'
            suffix = (('put', 'system', 'font_scale', self.original['text'])
                      if self.original['present'] else ('delete', 'system', 'font_scale'))
            raw = self._command(flow, list(PREFIX + suffix), mutation=True, label='restore')
            self.state = 'restored_awaiting_effect'
            need(raw == (b'' if self.original['present'] else b'Deleted 1 rows\n'),
                 'UNEXPECTED_ORIGINAL_SETTING_RESTORE_OUTPUT')
            self._settle(flow, self.original, 'restored')
            self.restored = True
            self.state = 'restored_verified'

    def may_restore(self):
        return (self.original is not None and self.write_count == 1
                and self.pending_command is None
                and self.state in ('applied_awaiting_effect', 'applied_verified'))

    def report(self):
        pending = self.pending_command
        return {'schema': 'pocket4-settings-font-scale-facts-v1',
                'namespace': 'system', 'key': 'font_scale', 'user': 0,
                'original': self.original, 'selected': self.selected, 'state': self.state,
                'apply_observed': self.applied, 'reopen_observed': self.reopened,
                'restore_observed': self.restored,
                'apply_claim': self.apply_claim, 'reopen_claim': self.reopen_claim,
                'provider_writes': self.write_count, 'readonly_commands': self.read_count,
                'commands': self.commands, 'snapshots': self.snapshots,
                'pending_command': None if pending is None else
                    {key: value for key, value in pending.items() if key != 'flow'},
                'automatic_write_retry': False,
                'compare_and_swap_claimed': False,
                'permission_or_account_write_authorized': False,
                'whole_app_business_accepted': False}
