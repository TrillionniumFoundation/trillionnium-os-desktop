"""Same-process Settings lease, real effective resource scope and owned tasks."""
import os
from pathlib import Path
import resource
import re
import time


def time_format_value(raw):
    """A list read distinguishes an absent key from the literal string null."""
    if (type(raw) is not bytes or not 0 < len(raw) <= 2 * 1024 * 1024
            or not raw.endswith(b'\n') or b'\0' in raw or b'\r' in raw):
        raise RuntimeError('BOUNDED_COMPLETE_SYSTEM_SETTINGS_READ_REQUIRED')
    text = raw.decode('utf-8', 'strict')
    rows = text.splitlines()
    if not rows or any(not re.fullmatch(r'[A-Za-z0-9_.-]+=.*', row) for row in rows):
        raise RuntimeError('SYSTEM_SETTINGS_LIST_GRAMMAR_CHANGED')
    names = [row.split('=', 1)[0] for row in rows]
    if len(names) != len(set(names)):
        raise RuntimeError('DUPLICATE_SYSTEM_SETTING_KEY')
    values = [row.split('=', 1)[1] for row in rows if row.startswith('time_12_24=')]
    if values and values[0] not in ('12', '24'):
        raise RuntimeError('UNSUPPORTED_EXISTING_TIME_FORMAT_PRESERVED')
    return values[0] if values else None


def resource_report(c, scope):
    # scope is a live object returned by the separately admitted native release
    # lease. The entry checks its exact class; no request can supply a report.
    value = scope.report()
    c.need(type(value) is dict and value.get('schema') == 'pocket4-held-effective-settings-resources-v1',
           'ACTUAL_HELD_SETTINGS_RESOURCE_SCOPE_REQUIRED')
    limits = value.get('limits')
    c.need(type(limits) is dict and set(limits) == {'cpu.max','memory.max','memory.swap.max','pids.max'}
           and limits['memory.max'] == '2147483648' and limits['memory.swap.max'] == '0'
           and limits['pids.max'] == '64', 'FIXED_SETTINGS_NATIVE_RESOURCE_LIMITS_REQUIRED')
    parts = limits['cpu.max'].split()
    c.need(len(parts) == 2 and all(p.isdecimal() for p in parts)
           and 0 < int(parts[0]) <= 2 * int(parts[1]) and int(parts[1]) > 0,
           'SETTINGS_CPU_MUST_BE_AT_MOST_TWO_CORES')
    events = value.get('memory_events')
    c.need(type(events) is dict and all(type(v) is int and v >= 0 for v in events.values())
           and all(events.get(k) == 0 for k in ('oom','oom_kill','oom_group_kill'))
           and type(value.get('swap_current_bytes')) is int and value['swap_current_bytes'] == 0
           and type(value.get('native_parent_pid')) is int and value['native_parent_pid'] > 0
           and type(value.get('native_parent_start_ticks')) is int and value['native_parent_start_ticks'] > 0,
           'SETTINGS_ACTUAL_NATIVE_OWNER_OR_OOM_STATE_CHANGED')
    c.need(type(value.get('affinity')) is list and value['affinity'] == sorted(os.sched_getaffinity(0))
           and bool(value['affinity']) and set(value['affinity']) <= {20,21}
           and resource.getrlimit(resource.RLIMIT_CORE) == (0,0),
           'SETTINGS_ACTUAL_AFFINITY_OR_CORE_LIMIT_CHANGED')
    return value


def create_lease(c, host, base_ref, base):
    start = time.monotonic_ns()
    value={'schema':'pocket4-settings-pages-lease-v1','base_plan':base_ref,
           'owner':host.process(c, os.getpid()),'boot_id':host.boot(),
           'started_monotonic_ns':start,'business_deadline_monotonic_ns':start+600*10**9,
           'cleanup_deadline_monotonic_ns':start+720*10**9,'automatic_retry':False}
    c.need(base['limits']['business_seconds'] == 600 and base['limits']['cleanup_seconds'] == 120,
           'SETTINGS_FIXED_600_PLUS_120_SECONDS')
    return c.write_new(Path(base['case_root'])/'lease.json', value, 0o400)


def validate_lease(c, host, ref, active, *, cleanup=False, child=False):
    value=c.parse(c.read_ref(ref))
    c.need(set(value) == {'schema','base_plan','owner','boot_id','started_monotonic_ns',
                         'business_deadline_monotonic_ns','cleanup_deadline_monotonic_ns','automatic_retry'}
           and value['schema'] == 'pocket4-settings-pages-lease-v1'
           and value['base_plan'] == active['base_plan'] and ref == active['lease']
           and value['boot_id'] == host.boot() and value['automatic_retry'] is False,
           'SETTINGS_ACTUAL_OWNER_AND_FRESH_LEASE_REQUIRED')
    start=value['started_monotonic_ns']; business=value['business_deadline_monotonic_ns']; end=value['cleanup_deadline_monotonic_ns']
    c.need(type(start) is type(business) is type(end) is int
           and business == start+600*10**9 and end == start+720*10**9
           and start <= time.monotonic_ns() < (end if cleanup else business),
           'SETTINGS_ORIGINAL_ABSOLUTE_LEASE_EXPIRED_OR_CHANGED')
    if child:
        host.descendant(c, value['owner'])
        c.need(os.getpid() != value['owner']['pid'], 'UI_GUARD_MUST_BE_AN_ACTUAL_CHILD')
    else:
        c.need(host.process(c, os.getpid()) == value['owner'], 'SETTINGS_SAME_CASE_PROCESS_REQUIRED')
    return value


class Session:
    def __init__(self, c, active_ref, active, profile, release, resources):
        self.c=c; self.active_ref=active_ref; self.active=active; self.profile=profile
        self.release=release; self.resources=resources; self.lease_ref=active['lease']
        self.root=Path(active['case_root']); self.pending_route=None; self.cleanup_admission=None
        self.current_ui_context=None; self.page_route_count=0; self.observation_count=0
        self.pending_setting=None; self.pending_native=None; self.roundtrip=None; self.setting_write_count=0
        self.task_claims=[]; self.closed_claims=[]; self.before_tasks=None; self.retirement_unknown=False
        self.host=None; self.closed=False

    def bind_host(self, host):
        self.c.need(self.host is None, 'SETTINGS_HOST_RUNTIME_SINGLE_BIND')
        self.host=host

    def guard(self, flow=None):
        self.c.need(not self.closed and not self.retirement_unknown and self.host is not None,
                    'SETTINGS_SESSION_CLOSED_OR_UNKNOWN')
        self.release.guard(); resource_report(self.c, self.resources)
        self.c.read_ref(self.active_ref)
        cleanup=flow is not None and flow.phase=='cleanup'
        lease=validate_lease(self.c, self.host, self.lease_ref, self.active, cleanup=cleanup)
        if flow is not None:
            expected=lease['cleanup_deadline_monotonic_ns' if cleanup else 'business_deadline_monotonic_ns']/10**9
            self.c.need(flow.deadline==expected and flow.scope['phase_plan']==self.active_ref,
                        'SETTINGS_FLOW_ABSOLUTE_DEADLINE_OR_PLAN_CHANGED')
        return lease

    def require_owned_task(self, flow):
        flow.guard(); claim,ref=flow.scope_module.load_owned_task(flow.bound)
        raw,roots,tasks=flow.stacks()
        self.c.need(flow.tasks.exact_leaf(roots,claim['task'],self.profile.PACKAGE)
                    and tasks==set(claim['prelaunch_task_ids'])|{claim['task']},
                    'SETTINGS_OWNED_TASK_OR_PREEXISTING_TASK_SET_CHANGED')
        return claim,ref

    def begin_route(self, flow, page, argv):
        self.c.need(self.pending_route is None and self.current_ui_context is None
                    and self.pending_setting is None
                    and self.page_route_count < len(self.profile.ROUTE_SEQUENCE)
                    and page==self.profile.ROUTE_SEQUENCE[self.page_route_count],
                    'SETTINGS_FIXED_ONCE_ONLY_PAGE_ORDER_REQUIRED')
        self.require_owned_task(flow); self.page_route_count+=1
        ref=self.c.write_new(self.root/('page-%02d.intent.json'%self.page_route_count),
            {'schema':'pocket4-settings-page-route-intent-v1','scope':flow.scope_ref,'lease':self.lease_ref,
             'page':page,'argv':argv,'setting_writes':0,'automatic_retry':False},0o400)
        self.pending_route={'page':page,'intent':ref,'scope':flow.scope_ref,'sent':False}
        return ref

    def end_route(self, flow, page, intent, raw, ack):
        self.c.need(self.pending_route is not None and self.pending_route['intent']==intent
                    and self.pending_route['page']==page and self.pending_route['sent'] is True,
                    'SETTINGS_ROUTE_RESULT_WITHOUT_ITS_ACTUAL_INTENT')
        claim,_=self.require_owned_task(flow)
        evidence=self.c.write_new(self.root/('page-%02d.stdout.txt'%self.page_route_count),raw)
        self.c.write_new(self.root/('page-%02d.result.json'%self.page_route_count),
            {'schema':'pocket4-settings-page-route-ack-v1','intent':intent,'stdout':evidence,
             'ack':ack,'owned_task':claim,'business_success_verified':False,'automatic_retry':False})
        self.pending_route=None

    def ui_context(self, flow, page):
        self.c.need(self.pending_route is None and self.current_ui_context is None
                    and self.pending_setting is None
                    and self.observation_count < self.profile.LIMITS['maximum_observations'],
                    'SETTINGS_FRESH_READONLY_OBSERVATION_BUDGET')
        _,claim=self.require_owned_task(flow); self.observation_count+=1
        self.current_ui_context={'schema':'pocket4-settings-pages-ui-context-v1',
            'scope':flow.scope_ref,'lease':self.lease_ref,'owned_claim':claim,
            'observation_number':self.observation_count,'page':page,'automatic_retry':False}
        return self.current_ui_context

    def observation_finished(self):
        self.c.need(self.current_ui_context is not None, 'SETTINGS_NO_CURRENT_OBSERVATION')
        self.current_ui_context=None

    def no_unknown(self):
        self.c.need(not self.retirement_unknown and self.pending_route is None
                    and self.current_ui_context is None and self.pending_setting is None
                    and self.pending_native is None and self.cleanup_admission is None,
                    'SETTINGS_UNKNOWN_EFFECT_NO_AUTOMATIC_CLEANUP')

    def recorded_prefix(self, flow):
        """Every dispatched command must have an actual complete host terminal."""
        logical=sorted((flow.root/'steps').glob('*/command-*.logical.json'))
        self.c.need(0<len(logical)<=256,'SETTINGS_BOUNDED_RECORDED_COMMAND_PREFIX')
        for path in logical:
            ref=self.c.regular(path,contents=False);self.c.read_ref(ref)
            result=self.c.parse(self.c.regular(path.with_name(path.name.replace('.logical.json','.result.json')))[0])
            self.c.need(result.get('host_retirement_proved') is True
                and result.get('evidence_complete') is True and result.get('returncode')==0
                and result.get('timed_out') is False and result.get('errors')==[]
                and result.get('first_error') is None,'SETTINGS_COMMAND_PREFIX_NOT_FULLY_RETIRED')

    def enter_cleanup(self, flow):
        self.no_unknown(); self.recorded_prefix(flow)
        # Enter the original absolute cleanup reserve before guarded reads.
        # Ownership is still proved by the old claim and fresh exact stacks;
        # expiry never creates permission to remove an unclaimed task.
        lease=validate_lease(self.c,self.host,self.lease_ref,self.active,cleanup=True)
        flow.phase='cleanup'; flow.deadline=lease['cleanup_deadline_monotonic_ns']/10**9
        flow.guard()

    def read_setting(self, flow):
        return time_format_value(flow.android(self.profile.SETTINGS_READ, 20))

    def prepare_setting(self, flow, before_state, observation):
        self.c.need(self.roundtrip is None and type(before_state) is dict
                    and set(before_state) == {'use_24hour', 'locale_default'}
                    and all(type(value) is bool for value in before_state.values()),
                    'ONCE_ONLY_ACTUAL_TIME_FORMAT_BASELINE_REQUIRED')
        self.no_unknown(); self.require_owned_task(flow)
        original = self.read_setting(flow)
        before_effect = before_state['use_24hour']
        self.c.need(original is None or before_effect is (original == '24'),
                    'TIME_FORMAT_PROVIDER_AND_NATIVE_STATE_DISAGREE')
        self.c.need(before_state['locale_default'] is (original is None),
                    'TIME_FORMAT_LOCALE_DEFAULT_AND_PROVIDER_DISAGREE')
        original_ref = self.c.write_new(self.root/'setting-original.json', {
            'schema': 'pocket4-settings-roundtrip-original-v1',
            'contract': self.active['business_contract'], 'lease': self.lease_ref,
            'scope': flow.scope_ref, 'original': original, 'before_ui_state': dict(before_state),
            'observation': observation, 'automatic_retry': False}, 0o400)
        self.roundtrip = {'original': original, 'original_ref': original_ref,
            'before_ui_state': dict(before_state), 'test_value': '12' if before_effect else '24',
            'apply_attempted': False, 'apply_readback_verified': False,
            'restore_attempted': False, 'restore_readback_verified': False,
            'effect_verified': False, 'reopen_persistence_verified': False,
            'restored_effect_verified': False}

    def write_setting(self, flow, *, restore=False):
        """Once-only journaled write with fresh conflict checks and exact readback.

        A complete, retired write can be restored after a later content failure.
        Missing command retirement, changed Main, or another value forbids any
        automatic write. An absent original is restored by deletion, never by
        storing the string 'null'.
        """
        self.no_unknown(); self.recorded_prefix(flow)
        state = self.roundtrip
        self.c.need(state is not None and flow.phase in ('inspect', 'cleanup')
                    and (restore or flow.phase == 'inspect'), 'CURRENT_SELECTED_SETTING_TRANSACTION_REQUIRED')
        original = self.c.parse(self.c.read_ref(state['original_ref']))
        self.c.need(original['original'] == state['original']
                    and original['lease'] == self.lease_ref
                    and original['contract'] == self.active['business_contract'],
                    'IMMUTABLE_ORIGINAL_SETTING_CHANGED')
        attempted = 'restore_attempted' if restore else 'apply_attempted'
        self.c.need(not state[attempted] and self.setting_write_count < 2,
                    'SETTING_WRITE_OR_RESTORE_MUST_NOT_BE_REPLAYED')
        self.c.need((restore and state['apply_attempted'] and self.setting_write_count == 1)
                    or (not restore and self.setting_write_count == 0),
                    'SETTING_RESTORE_REQUIRES_OWN_PREVIOUS_WRITE')
        desired = state['original'] if restore else state['test_value']
        expected = state['test_value'] if restore else state['original']
        with self.c.locked('/run/lock/android-digitalis-actions.lock'):
            actual = self.read_setting(flow)
            if restore and actual == state['original']:
                # No mutation when a failed write left the original unchanged.
                # This cannot satisfy the successful round-trip gate by itself.
                state['restore_readback_verified'] = True
                self.c.write_new(self.root/'setting-already-original.json', {
                    'original': state['original_ref'], 'scope': flow.scope_ref,
                    'readback': actual, 'write_performed': False}, 0o400)
                return
            self.c.need(actual == expected, 'SETTING_CHANGED_OUTSIDE_OWNED_TRANSACTION_NO_OVERWRITE')
            state[attempted] = True; self.setting_write_count += 1
            argv = self.profile.setting_write_argv(desired)
            intent = self.c.write_new(self.root/('setting-%02d.intent.json' % self.setting_write_count), {
                'schema': 'pocket4-settings-roundtrip-write-v1', 'scope': flow.scope_ref,
                'lease': self.lease_ref, 'original': state['original_ref'],
                'before': actual, 'desired': desired, 'restore': restore,
                'argv': argv, 'automatic_retry': False}, 0o400)
            self.pending_setting = {'scope': flow.scope_ref, 'intent': intent,
                'argv': argv, 'sent': False, 'restore': restore}
            raw = flow.android(argv, 20, mutation=True)
            self.recorded_prefix(flow)
            self.c.need(self.pending_setting['sent'] is True, 'SETTING_RESULT_WITHOUT_ADMITTED_WRITE')
            self.c.write_new(self.root/('setting-%02d.retired.json' % self.setting_write_count), {
                'intent': intent, 'stdout': self.c.write_new(
                    self.root/('setting-%02d.stdout' % self.setting_write_count), raw, 0o400),
                'command_retirement_verified': True, 'business_success_verified': False}, 0o400)
            self.pending_setting = None
            self.c.need(raw == (b'Deleted 1 rows\n' if desired is None else b''),
                        'SETTING_COMMAND_ACKNOWLEDGEMENT_CHANGED')
            readback = self.read_setting(flow)
            self.c.need(readback == desired, 'SETTING_WRITE_READBACK_MISMATCH')
            state['restore_readback_verified' if restore else 'apply_readback_verified'] = True
            self.c.write_new(self.root/('setting-%02d.readback.json' % self.setting_write_count), {
                'intent': intent, 'readback': readback, 'exact_value_verified': True}, 0o400)

    def restore_known_setting(self, flow):
        state = self.roundtrip
        if state is None or not state['apply_attempted'] or state['restore_readback_verified']:
            return False
        self.enter_cleanup(flow)
        self.write_setting(flow, restore=True)
        return True

    def normal_close(self, flow):
        self.enter_cleanup(flow)
        flow._new_step('normal-close','phase',None,False); flow._bridge(); flow.guard()
        claim,ref=self.require_owned_task(flow)
        self.cleanup_admission=(flow.scope_ref,claim['task'])
        value=flow.cleanup()
        self.c.need(value.get('other_tasks_preserved') is True
                    and value.get('task_ids_after')==claim['prelaunch_task_ids'],
                    'SETTINGS_OWNED_CLOSE_NOT_COMPLETELY_OBSERVED')
        self.closed_claims.append(ref); self.cleanup_admission=None
        self.recorded_prefix(flow)
        return value

    def close(self):
        self.closed=True
