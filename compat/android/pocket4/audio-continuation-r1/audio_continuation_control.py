"""Portable validation primitives for an existing Audio continuation workflow.

These functions do not launch processes, access a device, mutate evidence, or
grant runtime readiness. Callers supply independently observed, pinned records.
"""
from dataclasses import dataclass
import re


class ContractError(ValueError):
    pass


def require(value, message):
    if not value:
        raise ContractError(message)


def file_pin(value):
    require(isinstance(value, dict), 'file reference must be a mapping')
    require(isinstance(value.get('path'), str) and value['path'], 'file reference needs its actual path')
    require(type(value.get('bytes')) is int and value['bytes'] > 0, 'file reference needs a positive byte count')
    require(isinstance(value.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', value['sha256']),
            'file reference needs an exact SHA-256 digest')
    return {key: value[key] for key in ('path', 'bytes', 'sha256')}


def reviewed_reference(actual, reviewed):
    """Check the actual pin, then retain the reviewed mapping's literal order.

    Dict equality does not compare insertion order, but repr(dict) does. A
    binder that embeds Python literals must retain the order reviewed by its
    local assembler, even after sorted-key JSON transport.
    """
    require(set(actual) == set(reviewed) == {'path', 'bytes', 'sha256'}, 'exact reference keys required')
    require(file_pin(actual) == file_pin(reviewed), 'actual input differs from the reviewed reference')
    return dict(reviewed)


def validate_raw_exit(exited, request, started, *, expected_exit_code,
                      expected_at_unix_ms, expected_stream_bytes):
    """Validate the durable on-disk terminal, not an API status wrapper.

    The raw terminal has no ``state`` or ``automatic_retry`` field. Bind its
    actual generation and complete durable streams instead of inventing those
    wrapper fields or accepting a terminal from another process generation.
    """
    require(all(type(record[field]) is str and record[field]
                for record in (request, started, exited) for field in ('job_id', 'launch_nonce')),
            'actual nonempty process-generation strings required')
    require(request['job_id'] == started['job_id'] == exited['job_id']
            and request['launch_nonce'] == started['launch_nonce'] == exited['launch_nonce'],
            'raw exit belongs to a different process generation')
    require(type(expected_exit_code) is int and type(exited['exit_code']) is int
            and exited['exit_code'] == expected_exit_code
            and type(expected_at_unix_ms) is int and expected_at_unix_ms > 0
            and type(exited['at_unix_ms']) is int and exited['at_unix_ms'] == expected_at_unix_ms,
            'raw exit code or completion time differs')
    require(exited['timed_out'] is False and exited['cancelled'] is False
            and exited['output_complete'] is True and exited['output_durable'] is True
            and type(exited['terminal_publication_protocol']) is int
            and exited['terminal_publication_protocol'] == 1,
            'raw terminal is cancelled, timed out, incomplete, or not durable')
    require(type(expected_stream_bytes) is dict and set(expected_stream_bytes) == {'stdout', 'stderr'}
            and all(type(size) is int and size >= 0 for size in expected_stream_bytes.values()),
            'both exact nonnegative stream lengths required')
    require(type(exited['log_bytes']) is dict and set(exited['log_bytes']) == {'stdout', 'stderr'}
            and all(type(row) is dict and set(row) == {'seen', 'stored'}
                    and all(type(size) is int and size >= 0 for size in row.values())
                    for row in exited['log_bytes'].values()),
            'actual stream byte counts must be exact nonnegative integers')
    require(exited['log_bytes'] == {name: {'seen': size, 'stored': size}
                                   for name, size in expected_stream_bytes.items()}
            and type(exited['log_synced']) is dict and set(exited['log_synced']) == {'stdout', 'stderr'}
            and all(value is True for value in exited['log_synced'].values())
            and type(exited['log_truncated']) is dict and set(exited['log_truncated']) == {'stdout', 'stderr'}
            and all(value is False for value in exited['log_truncated'].values())
            and type(exited['log_errors']) is dict and set(exited['log_errors']) == {'stdout', 'stderr'}
            and all(value is None for value in exited['log_errors'].values()),
            'raw terminal streams are incomplete, changed, truncated, or unsynchronized')


@dataclass(frozen=True)
class ResourceProfile:
    name: str
    build_memory_max_bytes: int
    host_reserve_bytes: int
    go_memory_limit_bytes: int
    cpu_quota_percent: int = 200
    cpu_affinity: tuple = (0, 1)
    memory_swap_max_bytes: int = 0

    def __post_init__(self):
        require(type(self.name) is str and self.name.strip() == self.name and self.name
                and type(self.build_memory_max_bytes) is int and self.build_memory_max_bytes > 0,
                'named positive build allocation required')
        require(type(self.host_reserve_bytes) is int and self.host_reserve_bytes > 0, 'positive host reserve required')
        require(type(self.go_memory_limit_bytes) is int
                and 0 < self.go_memory_limit_bytes < self.build_memory_max_bytes,
                'integer Go budget must fit within build allocation')
        require(type(self.cpu_quota_percent) is int and self.cpu_quota_percent == 200
                and type(self.cpu_affinity) is tuple and all(type(cpu) is int for cpu in self.cpu_affinity)
                and self.cpu_affinity == (0, 1)
                and type(self.memory_swap_max_bytes) is int and self.memory_swap_max_bytes == 0,
                'the qualified two-CPU, zero-swap contract must be preserved')

    @property
    def fresh_memavailable_minimum_bytes(self):
        return self.build_memory_max_bytes + self.host_reserve_bytes

    def record(self):
        return {'name': self.name, 'build_memory_max_bytes': self.build_memory_max_bytes,
                'host_reserve_bytes': self.host_reserve_bytes,
                'fresh_memavailable_minimum_bytes': self.fresh_memavailable_minimum_bytes,
                'memory_swap_max_bytes': self.memory_swap_max_bytes,
                'cpu_quota_percent': self.cpu_quota_percent, 'cpu_affinity': list(self.cpu_affinity),
                'go_memory_limit_bytes': self.go_memory_limit_bytes}

    def admit(self, available):
        require(type(available) is int and available >= self.fresh_memavailable_minimum_bytes,
                'fresh memory does not cover the build allocation and host reserve')

    def validate_request(self, request):
        require(type(request['memory_max_bytes']) is int and request['memory_max_bytes'] == self.build_memory_max_bytes
                and type(request['cpu_quota_percent']) is int and request['cpu_quota_percent'] == self.cpu_quota_percent,
                'outer request does not match the named resource profile')

    def validate_completed_build(self, build):
        profile = build['resource_profile']
        require(type(profile) is dict and profile == self.record()
                and type(profile['name']) is str
                and all(type(profile[field]) is int for field in (
                    'build_memory_max_bytes', 'host_reserve_bytes', 'fresh_memavailable_minimum_bytes',
                    'memory_swap_max_bytes', 'cpu_quota_percent', 'go_memory_limit_bytes'))
                and type(profile['cpu_affinity']) is list
                and all(type(cpu) is int for cpu in profile['cpu_affinity']),
                'observed build resource profile differs')
        budget, admission = build['budget'], build['admission']
        require(budget['memory.max'] == str(self.build_memory_max_bytes)
                and budget['memory.swap.max'] == '0' and budget['cpu.max'] == '200000 100000'
                and type(budget['affinity']) is list and all(type(cpu) is int for cpu in budget['affinity'])
                and budget['affinity'] == list(self.cpu_affinity), 'observed build cgroup budget differs')
        require(type(admission['hard_cap_bytes']) is int and admission['hard_cap_bytes'] == self.build_memory_max_bytes
                and type(admission['minimum_bytes']) is int
                and admission['minimum_bytes'] == self.fresh_memavailable_minimum_bytes,
                'recorded admission does not match the named resource profile')
        self.admit(admission['MemAvailable_bytes'])
        resources = build['resources_after']
        require(resources['memory.swap.current'] == '0'
                and type(resources['memory.peak']) is str and re.fullmatch(r'0|[1-9][0-9]*', resources['memory.peak'])
                and 0 <= int(resources['memory.peak']) <= self.build_memory_max_bytes,
                'build exceeded its allocation or used swap')
        require(all(type(build['resource_events_delta'][key]) is int and build['resource_events_delta'][key] == 0
                    for key in ('oom', 'oom_kill', 'oom_group_kill')),
                'build recorded an OOM event')
        require(build['owned_resource_gate_passed'] is True and build['owned_retirement_complete'] is True
                and build['input_after_qualified'] is True and build['source_projection_restored'] is True,
                'resource validation cannot replace complete process retirement and source restoration')


MEMORY8G_RESERVE5G = ResourceProfile(
    name='audio-full-memory8g-hostreserve5g-cpu2-noswap-v1',
    build_memory_max_bytes=8 * 1024**3, host_reserve_bytes=5 * 1024**3,
    go_memory_limit_bytes=5 * 1024**3)

CORE_PAYLOAD = 'bin/hw/android.hardware.audio.service-aidl.droidloom'
REQUIRED_BRIDGE_UNITS = {
    'hardware/interfaces/audio/aidl/default/Stream.cpp',
    'hardware/interfaces/audio/aidl/default/primary/StreamPrimary.cpp',
    'hardware/interfaces/audio/aidl/default/stub/DriverStubImpl.cpp',
}


def validate_complete_apex(qualification, expected_artifact, contents):
    """Reject partial crypto/parser results at the complete-APEX boundary."""
    require(qualification['schema'] == 'pocket4-audio-whole-apex-qualification-v1', 'wrong Audio qualifier schema')
    flags = ('normal_complete_audio_apex_build', 'signature_and_hashtree_verified',
             'payload_file_contents_verified', 'payload_membership_verified',
             'payload_contents_verified', 'complete_apex_qualified')
    require(all(qualification[name] is True for name in flags), 'complete whole-APEX qualification is still pending')
    require(qualification['runtime_qualified'] is False and qualification['production_deployment_performed'] is False,
            'offline evidence cannot claim runtime or deployment success')
    actual = file_pin(qualification['actual_apex'])
    require(actual == file_pin(expected_artifact) == file_pin(qualification['copy']['source']),
            'qualification refers to a different whole APEX')
    payload = qualification['payload_contents']
    require(payload['payload_membership_verified'] is True and payload['payload_file_contents_verified'] is True,
            'signed-payload membership and file verification are required')
    bridge = payload['compiled_bridge_binding']
    require(isinstance(bridge, dict) and bridge.get('schema') == 'pocket4-audio-compiled-bridge-binding-v1'
            and bridge.get('state') == 'PASS', 'actual compiled bridge evidence is required')
    require(file_pin(bridge['whole_apex']) == actual and bridge['core_payload_relative'] == CORE_PAYLOAD,
            'compiled bridge proof belongs to a different APEX or payload member')
    require(contents['schema'] == 'droidloom-audio-apex-file-contents-v1'
            and contents['payload_file_contents_match'] is True, 'actual contents inspection required')
    core, compiled = contents['files'][CORE_PAYLOAD], bridge['core_payload_file']
    require(all(type(row['bytes']) is int and row['bytes'] > 0
                and type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['sha256'])
                for row in (core, compiled))
            and core['bytes'] == compiled['bytes'] and core['sha256'] == compiled['sha256'],
            'compiled bridge ELF differs from the verified payload ELF')
    units = bridge['translation_units']
    require(len(units) == 3 and {row['source'] for row in units} == REQUIRED_BRIDGE_UNITS,
            'all three actual bridge translation units must be bound')
    require(bridge['actual_successful_ninja_commands_verified'] is True
            and bridge['actual_header_dependencies_verified'] is True
            and bridge['effective_source_input_window_verified'] is True,
            'declared source files alone cannot prove actual compilation')


def validate_stage_apex(witness, qualification, expected_artifact):
    """Read both exact evidence files before composing a deployment payload.

    ``witness.read`` must hold and verify the supplied path/length/digest pin,
    returning the parsed JSON document and its actual file reference. The
    caller continues to enforce its source-bound packet and artifact ownership.
    """
    payload = qualification['payload_contents']
    contents, contents_pin = witness.read(payload['actual_file_contents_result'], json=True)
    compiled, compiled_pin = witness.read(payload['compiled_bridge_binding_result'], json=True)
    require(compiled == payload['compiled_bridge_binding'],
            'embedded compiled evidence differs from the actual pinned result')
    validate_complete_apex(qualification, expected_artifact, contents)
    require(file_pin(contents_pin) == file_pin(payload['actual_file_contents_result'])
            and file_pin(compiled_pin) == file_pin(payload['compiled_bridge_binding_result']),
            'stage witness returned different evidence files')
    return {'contents': file_pin(contents_pin), 'compiled_bridge': file_pin(compiled_pin)}
