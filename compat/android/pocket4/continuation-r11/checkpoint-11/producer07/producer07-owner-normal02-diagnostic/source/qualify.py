"""Strict first enrollment/normal retirement qualifier; no App/reload qualification."""
from pinned_support import need

EVENTS = ['prepared', 'owner_attached', 'init_hello', 'broker_ready', 'init_project_sent',
          'init_projected_accepted', 'init_commit_sent', 'init_done_accepted', 'broker_active',
          'retiring', 'broker_retired', 'processes_dead', 'domain_empty', 'retired',
          'resources_removed', 'claim_released']


def hex64(value):
    return isinstance(value, str) and len(value) == 64 and value != '0' * 64 and all(c in '0123456789abcdef' for c in value)


def qualify_lifecycle(plan, actual):
    active = actual['active_response']; stopped = actual['stop_response']
    need(active['ok'] is True and active['state'] == 'running' and stopped['ok'] is True and stopped['state'] == 'stopped', 'public lifecycle state failed')
    a, b = active['relay_lifecycle'], stopped['relay_lifecycle']
    for value, events, retained in ((a, EVENTS[:9], False), (b, EVENTS, True)):
        need(value['schema'] == 1 and value['retained_after_exit'] is retained and
             value['recording_incomplete'] is False and value['recording_error'] is None and
             value['first_failure'] is None and value['retirement_failure'] is None and value['cleanup_failure'] is None,
             'audit failure/gap/retention differs')
        need(value['host_uid'] == plan['spec']['host_uid'] and value['canonical_spec_sha256'] == plan['canonical_spec_sha256'] and hex64(value['nonce']), 'actual generation/spec binding differs')
        need([r['sequence'] for r in value['records']] == list(range(1, len(events) + 1)) and
             [r['detail']['event'] for r in value['records']] == events, 'actual event sequence is incomplete or reordered')
        times = [r['observed_monotonic_ns'] for r in value['records']]
        need(all(type(x) is int and x > 0 for x in times) and times == sorted(times) and
             actual['start_requested_monotonic_ns'] <= times[0] and times[-1] <= actual['stop_returned_monotonic_ns'],
             'actual audit time binding differs')
        for key in ('memory_max_bytes', 'memory_high_bytes', 'memory_swap_max_bytes', 'cpu_quota_us', 'cpu_period_us', 'tasks_max'):
            need(value[key] == plan['spec']['pressure_relay'][key], 'actual immutable budget differs: ' + key)
    need(a['records'] == b['records'][:9] and a['nonce'] == b['nonce'] == actual['actual_generation_nonce'], 'active and retirement use different generation')
    need(a['producer'] == b['producer'], 'retired producer identity changed')
    producer = actual['producer']
    for key in ('process', 'namespaces', 'executable', 'executable_sha256'):
        need(a['producer'][key] == producer[key], 'producer audit is not externally held actual daemon: ' + key)
    need(producer['executable_sha256'] == plan['artifacts']['droidloomd']['sha256'], 'producer ELF differs from actual compile')
    detail = {r['detail']['event']: r['detail'] for r in b['records']}
    for role, record in (('owner', detail['owner_attached']['process']), ('init', detail['init_hello']['init']['process']), ('broker', detail['broker_ready']['process'])):
        need(record == actual['observed_processes'][role]['process'], 'held actual process differs: ' + role)
    init = detail['init_hello']['init']; observed_init = actual['observed_processes']['init']
    need(init['namespaces'] == observed_init['namespaces'] and init['executable'] == observed_init['executable'] and
         init['executable_sha256'] == observed_init['executable_sha256'] == plan['spec']['pressure_relay']['init_sha256'], 'actual paired init identity differs')
    need(init['root'] == actual['init_root_identity'] and init['cgroup'] == actual['init_projected_cgroup_identity'] == detail['prepared']['domain'], 'actual init root/cgroup projection differs')
    need(init['linker_sha256'] == plan['spec']['pressure_relay']['init_linker_sha256'] and
         init['compat_sha256'] == plan['spec']['pressure_relay']['compat_preload_sha256'], 'actual init loader/preload pairing differs')
    need(len(init['hello_wire_hex']) == 256 and all(len(detail[key]['wire_hex']) == 256 for key in
        ('init_project_sent', 'init_projected_accepted', 'init_commit_sent', 'init_done_accepted')), 'real init protocol records missing')
    native = actual['native_lmkd']
    need(native['fixed_inherited_slots_absent'] is True and native['snapshot']['executable_sha256'] == plan['artifacts']['lmkd']['sha256'] and
         native['snapshot']['identity']['uids'] == [1069] * 4 and native['snapshot']['namespaces'][0] == init['namespaces'][0], 'actual native LMKD executable/role/namespace differs')
    ready, granted, retired = (detail['broker_ready']['status'], detail['broker_active']['status'], detail['broker_retired']['receipt'])
    final_status = retired['status']
    for status, state, grant in ((ready, 1, False), (granted, 2, True), (final_status, 3, True)):
        need(status['state'] == state and status['granted'] is grant and status['faulted'] is False,
             'actual broker READY/ACTIVE/RETIRED state failed')
        need(status['nonce'] == b['nonce'] and hex64(status['generation']) and hex64(status['budget']), 'broker generation binding differs')
        for key in ('nonce', 'generation', 'budget', 'endpoint', 'cgroup'):
            need(status[key] == ready[key], 'broker binding changed across retirement: ' + key)
    need(ready['cgroup'] == detail['prepared']['domain'] == actual['generation_domain_before_stop']['identity'] and
         ready['endpoint'] == actual['endpoint_identity'], 'externally held cgroup/endpoint differs')
    need(retired['granted'] is True and retired['faulted'] is False and retired['incomplete'] is False and
         retired['event_overflow'] is False and retired['cgroup'] == ready['cgroup'] and retired['budget'] == ready['budget'], 'joined broker retirement audit failed')
    need(retired['authority_generation'] == ready['generation'] and hex64(retired['lease_generation']), 'retirement authority/lease generation differs')
    need(retired['observations'] == retired['packets_queued'] == retired['event_records'] and retired['stop_reason'] == 1, 'joined pressure audit is incomplete')
    registrations = retired['registrations']
    need(len(registrations) == 2 and [r['level'] for r in registrations] == [1, 2], 'actual native registrations missing')
    for r, stall, kind in zip(registrations, (70000, 700000), ('some', 'full')):
        need(r['window_us'] == 1000000 and r['stall_us'] == stall and r['trigger'].strip() == f'{kind} {stall} 1000000' and
             r['bytes_written'] == len(r['trigger'].encode()) and 0 < r['write_started_ns'] <= r['write_completed_ns'] <= retired['retired_monotonic_ns'], 'actual native PSI default registration differs')
    claim = actual['generation_claim']
    need(claim['host_uid'] == plan['spec']['host_uid'] and claim['nonce'] == b['nonce'] and
         claim['canonical_spec_sha256'] == plan['canonical_spec_sha256'] and claim['domain_name'] == 'g-' + b['nonce'] and
         claim['pressure_relay'] == plan['spec']['pressure_relay'], 'actual durable claim differs')
    need(actual['held_generation_processes_dead'] == {'owner': True, 'init': True, 'broker': True, 'lmkd': True}, 'actual held generation process survives')
    need(len(actual['runtime_claim_domain_absent']) == 3 and actual['retained_status']['relay_lifecycle'] == b, 'retained normal cleanup proof differs')
    return True
