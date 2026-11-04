#!/usr/bin/env python3
# Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
"""Read-only admission for one host fixture, bound to the formal Main epoch.

The original r10 thresholds are imported by exact source hash. Every health
frame, including collection/identity errors, is durably saved before judgment.
"""
import hashlib
import json
import os
from pathlib import Path
import time
import types

ACTIVATION = Path(os.environ.get('P4_FORMAL_ACTIVATION', '/srv/pocket4-relay-inputs/activation-after.json'))
ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
EPOCH = Path(os.environ.get('P4_FRAMEWORK_EPOCH_MODULE', '/srv/pocket4-relay-inputs/framework_epoch.py'))
EPOCH_SHA = 'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'
EPOCH_ID = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
# Public path adaptation changes only the predecessor input-root literal.
ORIGINAL_PRIOR_SHA = 'f1fc129b862dc924969164638f606e11c49293338039cbe61952797d0c603daf'
PRIOR_SHA = '62243c0841577eaa1cca97deeffd7fcc0ced3d244a0fb83242bb504bd8ba92b8'
CG = Path('/sys/fs/cgroup/system.slice/droidloomd.service')
MIB = 1024 * 1024


class GuardFailure(RuntimeError):
    def __init__(self, message, scope, metric, value, comparison, limit):
        super().__init__(message)
        self.observation = {'scope': scope, 'metric': metric, 'value': value,
                            'required_comparison': comparison, 'limit': limit}


def compared(ok, message, scope, metric, value, comparison, limit):
    if not ok:
        raise GuardFailure(message, scope, metric, value, comparison, limit)


def check(value, message):
    if not value:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def load_module(path, expected, name):
    raw = Path(path).read_bytes()
    check(sha(raw) == expected, 'SOURCE_PIN_CHANGED:' + str(path))
    result = types.ModuleType(name)
    result.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), result.__dict__)
    return result


def directory_id(path):
    s = path.stat()
    return [s.st_dev, s.st_ino]


def scope_sample(paths, prior):
    sample = {}
    for name, path in paths.items():
        sample[name] = {
            'identity': directory_id(path),
            'limits': {key: (path / key).read_text().strip() for key in prior.LIMITS},
            'memory_current': int((path / 'memory.current').read_text()),
            'memory_events': prior.values(path / 'memory.events'),
            'memory_events_local': prior.values(path / 'memory.events.local'),
            'pids_events': prior.values(path / 'pids.events'),
            'memory_pressure': prior.psi(path / 'memory.pressure'),
        }
    return sample


def owned_guard(now, baseline):
    check(now.keys() == baseline.keys(), 'OWNED_SCOPE_SET_CHANGED')
    for name, item in now.items():
        old = baseline[name]
        for field in ('identity', 'limits'):
            compared(item[field] == old[field], 'OWNED_GENERATION_OR_BUDGET_CHANGED',
                     name, field, item[field], '==', old[field])
        for event in ('max', 'oom', 'oom_kill', 'oom_group_kill'):
            compared(item['memory_events'][event] == old['memory_events'][event],
                     'OWNED_MEMORY_EVENT_CHANGED', name, 'memory.events.' + event,
                     item['memory_events'][event], '==', old['memory_events'][event])
        compared(item['pids_events'] == old['pids_events'], 'OWNED_PID_EVENT_CHANGED',
                 name, 'pids.events', item['pids_events'], '==', old['pids_events'])
        if name != 'target':
            compared(item['memory_events_local'] == old['memory_events_local'],
                     'PRESSURE_OUTSIDE_OWNED_TARGET', name, 'memory.events.local',
                     item['memory_events_local'], '==', old['memory_events_local'])
    compared(now['target']['memory_current'] < 48 * MIB, 'OWNED_TARGET_CURRENT_ABORT_BOUND',
             'target', 'memory.current', now['target']['memory_current'], '<', 48 * MIB)


class MainGuard:
    def __init__(self, prior_path, output):
        self.prior = load_module(prior_path, PRIOR_SHA, 'p4_event_prior_guards')
        self.epoch = load_module(EPOCH, EPOCH_SHA, 'p4_event_epoch')
        self.output = output
        self.index = 0
        self.baseline = None
        self.scope_baseline = None
        self.paths = None
        self.attempted = False
        raw = self.prior.read_regular(ACTIVATION)
        check(sha(raw) == ACTIVATION_SHA, 'FORMAL_ACTIVATION_CHANGED')
        self.activation = json.loads(raw)
        check(self.activation['framework_epoch']['sha256'] == EPOCH_ID, 'FORMAL_EPOCH_ID_DIFFERS')
        self.formal_guard()
        processes = self.activation['framework_epoch']['binding']['processes']
        self.pin = self.prior.main_pin(self.activation['launcher_process']['host_pid'],
                                       processes['init']['host_pid'], query_status=False)
        check(self.pin['cgroup'] == str(CG) and self.pin['limits'] == self.activation['limits'],
              'FORMAL_MAIN_BOUNDARY_DIFFERS')
        check(self.pin['invocation_id'] == self.activation['daemon_unit']['InvocationID'],
              'FORMAL_MAIN_UNIT_GENERATION_DIFFERS')
        self.formal_guard()
        save(output / 'main-pin.json', self.pin)
        save(output / 'source-authority.json', {'activation_sha256': ACTIVATION_SHA,
             'framework_epoch_sha256': EPOCH_ID, 'epoch_module_sha256': EPOCH_SHA,
             'prior_guard_source_sha256': PRIOR_SHA, 'replaced_epoch_accepted': False})

    def formal_guard(self):
        check(sha(self.prior.read_regular(ACTIVATION)) == ACTIVATION_SHA, 'FORMAL_ACTIVATION_CHANGED')
        self.epoch.require_unchanged(self.activation['framework_epoch'], action_attempted=self.attempted)
        for field in ('daemon_process', 'launcher_process', 'presenter_process'):
            pin = self.activation[field]
            check(self.epoch.process_identity(pin['host_pid']) == pin, 'FORMAL_HOST_PROCESS_CHANGED:' + field)
        check({key: (CG / key).read_text().strip() for key in self.activation['limits']} == self.activation['limits'],
              'FORMAL_MAIN_LIMITS_CHANGED')
        if hasattr(self, 'pin'):
            check(directory_id(CG) == self.pin['cgroup_identity'], 'MAIN_CGROUP_GENERATION_CHANGED')
            check(sha(self.prior.read_regular('/etc/droidloom/cell.json', 1024 * 1024)) == self.pin['config_sha256'],
                  'MAIN_CONFIGURATION_CHANGED')
        self.epoch.require_unchanged(self.activation['framework_epoch'], action_attempted=self.attempted)

    def bind_owned_scope(self, paths):
        check(self.paths is None and not self.attempted, 'OWNED_SCOPE_ALREADY_BOUND')
        self.paths = paths
        self.scope_baseline = scope_sample(paths, self.prior)
        check(self.scope_baseline['target']['limits']['memory.high'] == str(24 * MIB) and
              self.scope_baseline['target']['limits']['memory.max'] == str(64 * MIB) and
              self.scope_baseline['target']['limits']['memory.swap.max'] == '0', 'OWNED_TARGET_CONTRACT_DIFFERS')
        save(self.output / 'owned-baseline.json', self.scope_baseline)

    def sample(self, label):
        started = time.monotonic_ns()
        frame = {'label': label, 'at_unix_ns': time.time_ns(), 'started_monotonic_ns': started,
                 'action_attempted': self.attempted}
        errors = []
        current = None
        try:
            current = self.prior.health(self.pin)
            frame['health'] = current
        except Exception as error:
            errors.append(error)
            frame['health_collection_error'] = repr(error)
        try:
            self.formal_guard()
            frame['formal_main_epoch_preserved'] = True
        except Exception as error:
            errors.append(error)
            frame['formal_identity_error'] = repr(error)
        if self.paths is not None:
            try:
                frame['owned_scope'] = scope_sample(self.paths, self.prior)
            except Exception as error:
                errors.append(error)
                frame['owned_collection_error'] = repr(error)
        frame['completed_monotonic_ns'] = time.monotonic_ns()
        path = self.output / ('health-%04d.json' % self.index)
        self.index += 1
        # No threshold or identity failure can discard the sampled frame.
        save(path, frame)
        try:
            if errors:
                raise errors[0]
            # Include persistence time in the completion bound, while the
            # already-fsynced frame remains the exact sampled decision input.
            elapsed = time.monotonic_ns() - started
            compared(0 <= elapsed < 100_000_000, 'HEALTH_COLLECTION_EXCEEDED_100MS',
                     'health-collector', 'collection_and_persistence_ns', elapsed, '<', 100_000_000)
            self.prior.guard_admission(self.pin, current)
            if self.baseline is not None:
                self.prior.guard_health(current, self.baseline)
            if self.paths is not None:
                owned_guard(frame['owned_scope'], self.scope_baseline)
            if self.baseline is None:
                self.baseline = current
        except Exception as error:
            error.evidence = str(path)
            error.event_frame = frame
            raise
        return frame

    def finish(self):
        self.formal_guard()
        processes = self.activation['framework_epoch']['binding']['processes']
        after = self.prior.main_pin(self.activation['launcher_process']['host_pid'],
                                    processes['init']['host_pid'], query_status=False)
        save(self.output / 'main-pin-after.json', after)
        check(after == self.pin, 'MAIN_COMPLETE_BOUNDARY_CHANGED')
        self.formal_guard()
        return True
