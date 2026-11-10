#!/usr/bin/python3 -I
"""Three owned Probe rounds; real ambiguity rejection and bounded live evidence.

No account, provider, package or permission mutation. Native ACTION_SET_TEXT
does not require two identical caret pixels; actual focused window and complete
semantic nodes are checked before every input. Unknown input or task removal
blocks every subsequent input/close. Inert without --execute.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, copy, hashlib, json, re, signal, time, types

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/alex/work/pocket4-probe-completion-20261105-r12-04')
PUBLIC = HERE / 'probe-completion04-result.json'
PACKAGE = 'local.pocket4.fixture'
COMPONENT = PACKAGE + '/.ProbeActivity'
TX_PATH = Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
TX_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
NATIVE_APK = '/data/app/~~VquA6bMTTcqJR9oO6Bn2cg==/local.pocket4.actions.v2-RP5LXAm7yJWXCBcnEc7YkA==/base.apk'
NATIVE_SHA = 'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'
PINS = {
    'base': ('/home/alex/work/pocket4-contacts-session-tools-20261105-r12-01/ui_preflight04.py',
             'd02821d751736a9e3cf275ec0b27383852e24362928fd4257ebb6d3dee7f6a58'),
    'legacy': (str(HERE / 'probe_ui03_legacy.py'), '033843839399b602687bfc890652cffba886ed1b628c689d348cd0af4e45a646'),
    'runtime': (str(HERE / 'runtime_probe03.py'), '60440e7807bd7d3cde7057bb42dec901da09a20ce1aba420067404ba299dc1cb'),
    'diagnostics': (str(HERE / 'diagnostics_probe03.py'), '2fb7c1c72a0c7c4a0a10545bf2dc8b7d9eb6a731468f5e22a7d250b992a03ccd'),
    'evidence': (str(HERE / 'probe_evidence04.py'), '6b8c461b2cb4b15b758ca991bdb5086741a89869148ee7eae4607772ed4f7a25'),
}
VALUE = 'Pocket4 QA r12 6ea71c49 中文 café 😀'
SECOND = 'Owned Probe second field 6ea71c49 Ω'
NEGATIVE = 'Owned Probe ambiguity 6ea71c49'
HINTS = {'editor': '中文与 Unicode 输入', 'other_editor': '第二个输入框：验证歧义拒绝'}


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path, pin):
    raw = Path(path).read_bytes()
    need(sha(raw) == pin, 'PROBE_DEPENDENCY_CHANGED')
    module = types.ModuleType('probe_completion_' + Path(path).stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def expired(signum, frame):
    raise TimeoutError('PROBE_BOUNDED_LEASE_EXPIRED_NO_REPLAY')


def native_identity(session):
    raw, _ = session.target.read_file(NATIVE_APK, 64 * 1024)
    need(len(raw) == 20847 and sha(raw) == NATIVE_SHA, 'ACTUAL_NATIVE_ACTION_APK_CHANGED')
    paths = session.android(['/system/bin/pm', 'path', 'local.pocket4.actions.v2']).decode().splitlines()
    need(paths == ['package:' + NATIVE_APK], 'ACTIVE_NATIVE_ACTION_APK_CHANGED')
    session.guard()
    return {'apk_sha256': NATIVE_SHA, 'bytes': len(raw), 'guest_path': NATIVE_APK}


def stable_nodes(nodes):
    # window_id is local to each accessibility connection. WM token and full
    # native context are independently required, never replaced by this filter.
    return [{k: v for k, v in n.items() if k != 'window_id'} for n in nodes]


class Flow:
    def __init__(self, trial, base, runtime, result, evidence, diagnostics):
        self.t, self.base, self.runtime, self.r = trial, base, runtime, result
        self.evidence, self.diag = evidence, diagnostics
        self.round_index = None
        self.pending = self.launch_pending = self.close_pending = None
        self.owned, self.closed = [], []
        self.nodes, self.focus = [], None
        self.actions = self.successful_inputs = self.sequence = 0
        self.deadline = time.monotonic() + 300
        self.round_started = None
        self.live_seconds = 0.0
        self.baseline = None
        self.last_state = None

    def clear(self):
        need(self.pending is None and self.launch_pending is None and self.close_pending is None,
             'UNKNOWN_PROBE_INPUT_LAUNCH_OR_CLOSE_RETAINED')

    def scope(self, label):
        need(self.t.owned is not None, 'PROBE_OWNED_TASK_REQUIRED')
        focus = self.t.ready_focus(allow_permission=False)
        need(focus['package'] == PACKAGE and focus['task'] == self.t.owned[0]
             and focus['activity'] in ('.ProbeActivity', PACKAGE + '.ProbeActivity')
             and focus['focused_activity'] in ('.ProbeActivity', PACKAGE + '.ProbeActivity'),
             'EXACT_PROBE_ACTIVITY_REQUIRED')
        roots, tasks = self.t.stacks(label + '-tasks')
        need(self.base.exact_leaf(roots, self.t.owned[0])
             and tasks == self.t.owned[1] | {self.t.owned[0]}, 'PROBE_TASK_TOPOLOGY_CHANGED')
        if self.baseline is not None:
            need({k: v for k, v in roots.items() if k != self.t.owned[0]} == self.baseline,
                 'PREEXISTING_TASK_STRUCTURE_CHANGED')
        return focus

    def observe(self, label):
        need(time.monotonic() < self.deadline, 'PROBE_OBSERVATION_DEADLINE')
        self.sequence += 1
        label = 'o%03d-' % self.sequence + label
        focus = self.scope(label)
        nodes = self.t.observe(label, focus)
        complete = self.evidence.complete_observation(self.t.last_observation, focus)
        need(nodes == complete, 'PROBE_NATIVE_NODE_SET_DIFFERS')
        need(self.scope(label + '-after') == focus, 'PROBE_WINDOW_CHANGED_DURING_OBSERVATION')
        self.nodes, self.focus = nodes, focus
        return nodes

    def node(self, name, expected=None, editable=False):
        found = [n for n in self.nodes if n.get('package') == PACKAGE
                 and n.get('visible') is True and n.get('enabled') is True
                 and n.get('resource-id') == PACKAGE + ':id/' + name]
        need(len(found) == 1, 'ONE_PROBE_CONTROL_REQUIRED_' + name)
        node = found[0]
        if editable:
            need(node.get('class') == 'android.widget.EditText' and node.get('editable') is True
                 and node.get('password') is False, 'EXACT_NONPASSWORD_EDITOR_REQUIRED')
        if expected is not None:
            hint = editable and expected == '' and node.get('hint') == node.get('text') == HINTS.get(name)
            need(node.get('text') == expected or hint, 'PROBE_READBACK_DIFFERS_' + name)
        return node

    def state(self, expected):
        first, second, result = expected
        self.node('editor', first, True)
        self.node('other_editor', second, True)
        self.node('result', result)
        button = self.node('confirm', '确认测试')
        need(button.get('clickable') is True and button.get('password') is False,
             'ACTUAL_CONFIRM_CONTROL_REQUIRED')
        actual = {'editor': first, 'other_editor': second, 'result': result}
        self.last_state = actual
        return actual

    def launch(self, index):
        self.clear()
        need(time.monotonic() < self.deadline and self.t.owned is None
             and self.t.launches < 3, 'PROBE_LAUNCH_BOUND')
        roots, tasks = self.t.stacks('round-%d-baseline' % index)
        if self.baseline is None:
            self.baseline = copy.deepcopy(roots)
        need(roots == self.baseline, 'TASK_BASELINE_NOT_RESTORED_BEFORE_LAUNCH')
        self.launch_pending = {'round': index, 'automatic_retry': False}
        self.t.record('probe-launch-intent-%d' % index, self.launch_pending)
        self.t.launch()
        self.owned.append(self.t.owned[0])
        # Trial.launch returned only after the exact new task receipt/topology.
        # A later read-only observation failure is not an unknown launch.
        self.t.record('probe-launch-receipt-%d' % index, {'owned_task': self.t.owned[0],
            'exact_native_launch_and_task_topology_verified': True})
        self.launch_pending = None
        self.round_index = index
        self.observe('round-%d-open' % index)
        self.state(('', '', '尚未点击'))
        self.t.record('probe-launch-readback-%d' % index, {'owned_task': self.t.owned[0], 'default_fields': True})
        self.launch_pending = None
        self.round_started = time.monotonic()
        self.runtime.phase_changed('probe-round-%d' % index)
        self.diag.checkpoint('after-launch-%d' % index, force=True)

    def native(self, tag, op, name, value, before, after):
        self.clear()
        need(self.actions < 18 and time.monotonic() < self.deadline, 'PROBE_INPUT_BUDGET')
        self.diag.checkpoint('before-' + tag)
        self.observe('fresh-' + tag)
        self.state(before)
        node = self.node(name, before[0 if name == 'editor' else 1] if op == 'set-text' else '确认测试', op == 'set-text')
        selector = {'id': node['resource-id'], 'class': node['class'], 'package': PACKAGE,
                    'enabled': True}
        if op == 'set-text':
            selector['editable'] = True
            selector['text'] = node.get('text', '')
        else:
            need(op == 'click' and name == 'confirm', 'PROBE_INPUT_OPERATION_NOT_ALLOWED')
            selector.update(clickable=True, text='确认测试')
        request = {'op': op, 'expected_package': PACKAGE, 'display': 0,
                   'accessibility_mode': 'none', 'selector': selector}
        if op == 'set-text':
            request['value'] = value
        self.actions += 1
        ident = 'p%02d-' % self.actions + tag
        self.pending = {'id': ident, 'request': request, 'before': before, 'expected': after,
                        'owned_task': self.t.owned[0], 'automatic_retry': False}
        self.t.record('intent-' + ident, copy.deepcopy(self.pending))
        need(self.scope(ident + '-preinput') == self.focus, 'PREINPUT_PROBE_FOCUS_CHANGED')
        self.t.s.guard()
        try:
            reply = self.t.s.helper.ui(request)
        except BaseException as exc:
            details = getattr(exc, 'details', {})
            self.t.record('exception-' + ident, {'error': str(exc), 'details': details})
            if self.evidence.no_input_error(exc, self.t.s.helper):
                self.t.s.guard()
                self.t.record('explicit-no-effect-' + ident, copy.deepcopy(self.pending))
                self.pending = None
            raise
        self.t.s.guard()
        self.t.record('reply-' + ident, reply)
        need(reply.get('ok') is True and reply.get('performed') == op
             and reply.get('outcome_unknown') is not True
             and reply.get('accessibility_mode_restoration_verified') is True,
             'NATIVE_PROBE_INPUT_ACK_UNKNOWN')
        if op == 'set-text':
            need(reply.get('password') is False and reply.get('readback_verified') is True
                 and reply.get('characters') == len(value),
                 'NATIVE_EXACT_TEXT_READBACK_REQUIRED')
        else:
            target = reply.get('actual_target', {})
            need(self.evidence.actual_target_matches(target, selector),
                 'CONFIRM_ACTUAL_TARGET_DIFFERS')
        self.pending['native_acknowledged'] = True
        self.observe('after-' + tag)
        actual = self.state(after)
        self.t.record('effect-' + ident, {'intent': self.pending, 'actual_state': actual, 'action_replayed': False})
        self.pending = None
        self.successful_inputs += 1
        self.diag.checkpoint('after-' + tag)

    def ambiguity(self):
        self.clear()
        need(self.actions == 0 and self.t.owned is not None, 'ONE_FIRST_AMBIGUITY_DECISION_REQUIRED')
        self.observe('ambiguity-before')
        self.state(('', '', '尚未点击'))
        fields = [n for n in self.nodes if n.get('package') == PACKAGE and n.get('visible') is True
            and n.get('enabled') is True and n.get('class') == 'android.widget.EditText'
            and n.get('editable') is True and n.get('password') is False]
        need(len(fields) == 2 and {n['resource-id'] for n in fields} ==
            {PACKAGE + ':id/editor', PACKAGE + ':id/other_editor'}, 'TWO_ACTUAL_MATCHES_REQUIRED')
        original = stable_nodes(self.nodes)
        focus = copy.deepcopy(self.focus)
        request = {'op': 'set-text', 'expected_package': PACKAGE, 'display': 0,
            'accessibility_mode': 'none', 'value': NEGATIVE,
            'selector': {'class': 'android.widget.EditText', 'editable': True,
                         'enabled': True, 'package': PACKAGE}}
        self.actions += 1
        self.pending = {'id': 'p01-ambiguity', 'request': request, 'expected_error': 'AMBIGUOUS_MATCH',
                        'owned_task': self.t.owned[0], 'automatic_retry': False}
        self.t.record('intent-p01-ambiguity', copy.deepcopy(self.pending))
        need(self.scope('ambiguity-preinput') == focus, 'AMBIGUITY_FOCUS_CHANGED')
        self.t.s.guard()
        try:
            reply = self.t.s.helper.ui(request)
        except BaseException as exc:
            detail = getattr(exc, 'details', {})
            self.t.record('reply-p01-ambiguity', {'error': str(exc), 'details': detail})
            need(str(exc) == 'AMBIGUOUS_MATCH' and self.evidence.no_input_error(exc, self.t.s.helper),
                 'AMBIGUITY_OUTCOME_NOT_DEFINITE_NO_EFFECT')
        else:
            self.t.record('unexpected-reply-p01-ambiguity', reply)
            raise RuntimeError('AMBIGUITY_UNEXPECTED_SUCCESS_RETAIN_PENDING')
        self.t.s.guard()
        self.observe('ambiguity-after')
        self.state(('', '', '尚未点击'))
        need(self.focus == focus and stable_nodes(self.nodes) == original,
             'AMBIGUITY_FULL_NODE_READBACK_CHANGED')
        self.r['ambiguity_rejection'] = {'error': 'AMBIGUOUS_MATCH', 'native_outcome_unknown': False,
            'accessibility_mode_restoration_verified': True, 'automatic_retry': False,
            'full_semantic_tree_unchanged': True, 'same_owned_window': True,
            'successful_input_credit': 0, 'native_action_taken_field_not_invented': True}
        self.t.record('effect-p01-ambiguity', self.r['ambiguity_rejection'])
        self.pending = None
        self.diag.checkpoint('after-ambiguity', force=True)

    def live(self, index):
        self.clear()
        need(self.round_started is not None, 'OWNED_LIVE_START_REQUIRED')
        checks = 0
        while time.monotonic() - self.round_started < 30:
            need(self.deadline - time.monotonic() > 15, 'LIVE_WINDOW_OUTSIDE_WORK_BUDGET')
            time.sleep(2)
            self.observe('round-%d-live-%d' % (index, checks))
            self.state(('', '', '已点击：'))
            self.diag.checkpoint('live-round-%d-check-%d' % (index, checks))
            checks += 1
        elapsed = time.monotonic() - self.round_started
        self.live_seconds += elapsed
        self.r['rounds'].append({'round': index, 'task': self.t.owned[0],
            'live_seconds': elapsed, 'read_only_live_checks': checks,
            'both_fields_empty': True, 'actual_empty_confirmation': True})

    def close(self):
        self.clear()
        if self.t.owned is None:
            return
        task = self.t.owned[0]
        need(self.t.removals < 3, 'PROBE_NORMAL_CLOSE_LIMIT')
        # Account for any existing exit before authorizing this normal close.
        # Do not treat an unrelated USER REQUESTED exit as our task cleanup.
        self.runtime.phase_changed('closing-round-%d' % self.round_index)
        if not self.diag.failed:
            self.diag.checkpoint('before-close-%d' % task, force=True)
        self.scope('preclose-exact-owned-task')
        raw_pid = self.t.s.android(['/system/bin/pidof', PACKAGE], 8).decode().strip()
        need(re.fullmatch(r'[1-9][0-9]*', raw_pid), 'ONE_EXACT_PROBE_GUEST_PID_REQUIRED')
        guest_pid = int(raw_pid)
        before = self.t.removals
        self.close_pending = {'task': task, 'guest_pid': guest_pid, 'automatic_retry': False}
        self.t.record('probe-normal-close-intent-%d' % task, self.close_pending)
        self.t.close()
        need(self.t.removals == before + 1 and self.t.result.get('other_tasks_preserved') is True,
             'PROBE_NORMAL_CLOSE_NOT_VERIFIED')
        roots, _ = self.t.stacks('probe-normal-close-readback-%d' % task)
        need(roots == self.baseline, 'PROBE_TASK_BASELINE_NOT_RESTORED')
        self.closed.append(task)
        self.close_pending = None
        if not self.diag.failed:
            self.diag.after_close(task, guest_pid)

    def run(self):
        self.launch(1)
        self.ambiguity()
        self.native('confirm-empty-initial', 'click', 'confirm', None, ('', '', '尚未点击'), ('', '', '已点击：'))
        self.native('unicode', 'set-text', 'editor', VALUE, ('', '', '已点击：'), (VALUE, '', '已点击：'))
        self.native('second-field', 'set-text', 'other_editor', SECOND, (VALUE, '', '已点击：'), (VALUE, SECOND, '已点击：'))
        self.native('confirm-unicode', 'click', 'confirm', None, (VALUE, SECOND, '已点击：'), (VALUE, SECOND, '已点击：' + VALUE))
        self.native('clear-first', 'set-text', 'editor', '', (VALUE, SECOND, '已点击：' + VALUE), ('', SECOND, '已点击：' + VALUE))
        self.native('confirm-cleared', 'click', 'confirm', None, ('', SECOND, '已点击：' + VALUE), ('', SECOND, '已点击：'))
        self.native('clear-second', 'set-text', 'other_editor', '', ('', SECOND, '已点击：'), ('', '', '已点击：'))
        self.live(1)
        self.close()
        for index in (2, 3):
            self.launch(index)
            self.native('reopen-empty-%d' % index, 'click', 'confirm', None, ('', '', '尚未点击'), ('', '', '已点击：'))
            self.live(index)
            self.close()
        need(self.actions == 10 and self.successful_inputs == 9 and self.live_seconds >= 90
             and len(self.owned) == len(set(self.owned)) == len(self.closed) == 3
             and self.owned == self.closed, 'THREE_ROUNDS_AND_BOUNDED_LIVE_SCOPE_REQUIRED')
        self.r['controls_and_isolation_completed'] = True


def execute():
    modules = {k: load(*v) for k, v in PINS.items()}
    base, legacy, runtime_module, diagnostic, evidence = [modules[k]
        for k in ('base', 'legacy', 'runtime', 'diagnostics', 'evidence')]
    need(base.SOURCE == TX_PATH and base.SOURCE_SHA == TX_SHA, 'ORIGINAL_PROBE_TRANSPORT_REQUIRED')
    tx = base.load_session()
    need(tx.ACTIVATION_SHA == ACTIVATION_SHA, 'ORIGINAL_12288_PROFILE_REQUIRED')
    base.PACKAGE, base.COMPONENT, base.ROOT = PACKAGE, COMPONENT, ROOT
    result = {'schema': 'pocket4-probe-common-completion-v4', 'state': 'FAILED', 'rounds': [],
        'started_utc': datetime.now(timezone.utc).isoformat(), 'source_pins': PINS,
        'transport_sha256': TX_SHA, 'activation_sha256': ACTIVATION_SHA,
        'business_success_verified': False, 'controls_and_isolation_completed': False,
        'whole_app_production_ready': False, 'automatic_retry': False,
        'lease_seconds': 300, 'cleanup_budget_seconds': 45, 'minimum_live_seconds': 90,
        'package_changes': 0, 'provider_writes': 0, 'account_actions': 0,
        'permission_changes': 0, 'release_scope_requires_independent_review': True,
        'reviewed_resource_budget': evidence.RESOURCE_BUDGET}
    trial = flow = runtime = diagnostics = None
    cleanup_until = None
    prior = signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, 300)
        with tx.ui_lock():
            ROOT.mkdir(mode=0o700)
            with tx.CameraSession(ROOT / 'commands') as session:
                trial = base.Trial(session, tx)
                runtime = runtime_module.RuntimeEvidence(session, tx, ROOT / 'runtime-private',
                                                          'Pocket4_Probe_r12_6ea71c49ad03b285')
                diagnostics = evidence.Diagnostics(session, diagnostic, trial.record)
                flow = Flow(trial, base, runtime, result, evidence, diagnostics)
                try:
                    result['guard_before'] = session.guard()
                    result['identity_before'] = legacy.identity(session)
                    result['protected_data_before'] = evidence.protected_data(session)
                    result['native_before'] = native_identity(session)
                    result['uid_census'] = diagnostic.uid_census(session, trial.record, 'probe-only-uid')
                    diagnostics.start()
                    runtime.start()
                    flow.run()
                    result['diagnostics'] = diagnostics.finish()
                except BaseException as exc:
                    result['error'] = type(exc).__name__ + ': ' + str(exc)
                finally:
                    cleanup_until = time.monotonic() + 45
                    signal.setitimer(signal.ITIMER_REAL, 45)
                    try:
                        if flow.pending is None and flow.launch_pending is None and flow.close_pending is None:
                            flow.close()
                        else:
                            result['unknown_retained_without_cleanup_input'] = True
                    except BaseException as exc:
                        result['cleanup_error'] = type(exc).__name__ + ': ' + str(exc)
                    try:
                        result['runtime'] = runtime.stop()
                    except BaseException as exc:
                        result['runtime_error'] = type(exc).__name__ + ': ' + str(exc)
                    need(time.monotonic() < cleanup_until, 'SINGLE_PROBE_CLEANUP_DEADLINE_EXPIRED')
                    result['identity_after'] = legacy.identity(session)
                    result['protected_data_after'] = evidence.protected_data(session)
                    result['native_after'] = native_identity(session)
                    roots, tasks = trial.stacks('probe-final-tasks')
                    result['task_set_restored'] = flow.baseline is not None and roots == flow.baseline
                    result['guard_after'] = session.guard()
                    session.caller_status('probe-completion-final-caller')
        need(not any(result.get(k) for k in ('error', 'cleanup_error', 'runtime_error')),
             'PROBE_SCOPE_OR_CLEANUP_FAILED')
        flow.clear()
        need(result['controls_and_isolation_completed'] and result['task_set_restored']
             and trial.owned is None and flow.owned == flow.closed and trial.removals == 3
             and result['identity_before'] == result['identity_after']
             and result['native_before'] == result['native_after']
             and result['protected_data_before'] == result['protected_data_after']
             and result['guard_before'] == result['guard_after'], 'PROBE_COMPLETION_OR_IDENTITY_INCOMPLETE')
        sample = result['runtime']
        need(sample['thread_joined'] and not sample['errors'] and sample['scan_error_count'] == 0
             and PACKAGE in sample['processes_observed'], 'PROBE_RUNTIME_CAPTURE_INCOMPLETE')
        result['runtime_resource_review'] = evidence.runtime_budget(runtime)
        result.update(state='THREE_OWNED_ROUNDS_AMBIGUITY_AND_BOUNDED_LIVE_VERIFIED_CLEAN',
                      business_success_verified=True)
    except BaseException as exc:
        result.update(state='FAILED', business_success_verified=False,
                      terminal_error=type(exc).__name__ + ': ' + str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prior)
        result['diagnostic_segments_completed'] = diagnostics.proofs if diagnostics else []
        result['diagnostic_chain_failed'] = diagnostics.failed if diagnostics else None
        result.update(input_decisions=flow.actions if flow else 0,
            successful_native_inputs=flow.successful_inputs if flow else 0,
            live_observation_seconds=flow.live_seconds if flow else 0,
            pending_effect=flow.pending if flow else None,
            launch_pending=flow.launch_pending if flow else None,
            close_pending=flow.close_pending if flow else None,
            owned_tasks=flow.owned if flow else [], closed_tasks=flow.closed if flow else [],
            owned_task_remaining=trial.owned if trial else None,
            native_launch_calls=trial.launches if trial else 0,
            normal_remove_calls=trial.removals if trial else 0,
            finished_utc=datetime.now(timezone.utc).isoformat())
        if ROOT.is_dir():
            tx.write_new(ROOT / 'result.json', result)
        tx.write_new(PUBLIC, result, alex_readable=True)
        print(json.dumps({k: result.get(k) for k in ('state', 'error', 'terminal_error',
            'business_success_verified', 'input_decisions', 'pending_effect', 'launch_pending',
            'close_pending', 'owned_tasks', 'closed_tasks', 'owned_task_remaining')}))
    return 0 if result['business_success_verified'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    if parser.parse_args().execute:
        raise SystemExit(execute())
    print(json.dumps({'state': 'PLAN_ONLY', 'UI_actions': 0, 'package_changes': 0,
        'planned_launches': 3, 'planned_normal_closes': 3, 'planned_input_decisions': 10,
        'minimum_owned_live_seconds': 90, 'transport_sha256': TX_SHA}))
