#!/usr/bin/python3 -I
"""Two bounded real UI rounds of the installed, source-reviewed ProbeActivity."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, re, signal, time, types

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/alex/work/pocket4-qa-probe-ui-20261105-r12-02')
CONTACT = Path('/home/alex/work/pocket4-contacts-session-tools-20261105-r12-01')
PACKAGE = 'local.pocket4.fixture'
COMPONENT = PACKAGE + '/.ProbeActivity'
APK = '/data/app/~~7AyAiJrTjYxPxlzdUP7O9g==/local.pocket4.fixture-Rn2WJdjmmGRSmI5foe64RA==/base.apk'
APK_SHA = '91e352c25e7c6ef54aa53ce652931e40ad1437dfcd0ebad2529bc662558a3dd6'
UID = 10115
PINS = {
    str(CONTACT / 'ui_preflight04.py'): 'd02821d751736a9e3cf275ec0b27383852e24362928fd4257ebb6d3dee7f6a58',
    str(CONTACT / 'session_loop07.py'): 'c8cd713f3e323016dbfdce8e41a5c474ac58d365ebcd613dd539fc9568bb7784',
    str(HERE / 'diagnostics_source.py'): '93cf4567c19f6033dce0b120d068a7120a2b27952a4a1d0d4cfdd8b988ebfbcb',
}


def need(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def load(path, expected):
    raw = Path(path).read_bytes()
    need(hashlib.sha256(raw).hexdigest() == expected, 'SOURCE_CHANGED')
    module = types.ModuleType('probe_owned_' + Path(path).stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def expired(signum, frame):
    raise TimeoutError('PROBE_UI_LEASE_EXPIRED_NO_REPLAY')


def identity(session):
    raw, metadata = session.target.read_file(APK, 64 * 1024)
    need(len(raw) == 12713 and hashlib.sha256(raw).hexdigest() == APK_SHA, 'INSTALLED_PROBE_APK_CHANGED')
    paths = session.android(['/system/bin/pm', 'path', PACKAGE]).decode().splitlines()
    need(paths == ['package:' + APK], 'ACTIVE_PROBE_APK_CHANGED')
    dump = session.android(['/system/bin/dumpsys', 'package', PACKAGE]).decode('utf-8', 'strict')
    sections = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)', dump, re.M | re.S)
    need(len(sections) == 1, 'ACTIVE_PACKAGE_SECTION_REQUIRED')
    active = sections[0]
    def one(pattern):
        values = re.findall(pattern, active, re.M)
        need(len(values) == 1, 'PACKAGE_IDENTITY_FIELD_UNKNOWN')
        return values[0]
    value = {'uid': int(one(r'^    appId=(\d+)$')),
        'version': int(one(r'^    versionCode=(\d+)\b')),
        'data_dir': one(r'^      dataDir=(.*)$'),
        'first_install_time': one(r'^      firstInstallTime=(.*)$'),
        'apk_sha256': APK_SHA, 'apk_bytes': len(raw), 'android_user': 0,
        'epoch_sha256': session.epoch_sha256,
        'permission_lines': sorted(line.strip() for line in active.splitlines()
            if re.search(r'android\.permission\.[^:]+: granted=', line))}
    need(value['uid'] == UID and value['version'] == 0
         and value['data_dir'] == '/data/user/0/' + PACKAGE, 'PACKAGE_UID_VERSION_OR_DATA_CHANGED')
    session.guard()
    return value


class Flow:
    def __init__(self, trial, loop, result):
        self.t, self.loop, self.r = trial, loop, result
        self.c = loop.Continuation(trial, PACKAGE)
        self.owned, self.closed = [], []
        self.number = 0
        self.deadline = time.monotonic() + 240

    def node(self, name, expected=None, editable=False):
        found = [node for node in self.c.nodes if node.get('package') == PACKAGE
            and node.get('visible') is True and node.get('enabled') is True
            and node.get('resource-id') == PACKAGE + ':id/' + name]
        need(len(found) == 1, 'ONE_ACTUAL_FIXTURE_CONTROL_REQUIRED_' + name)
        node = found[0]
        if editable:
            need(node.get('editable') is True and node.get('password') is False,
                 'OWNED_PLAIN_TEXT_FIELD_REQUIRED')
        if expected is not None:
            need(node.get('text') == expected, 'EXACT_FIXTURE_READBACK_REQUIRED_' + name)
        return node

    def act(self, tag, operation, node, value=None):
        need(time.monotonic() < self.deadline and self.number < 12 and self.c.pending is None,
             'UI_ACTION_BUDGET_OR_PENDING')
        selector = {'id': node['resource-id'], 'class': node['class']}
        if node.get('text'):
            selector['text'] = node['text']
        request = {'id': 'p%02d-' % (self.number + 1) + tag, 'op': operation,
                   'observation': self.c.latest, 'selector': selector}
        if operation == 'set-text':
            request['value'] = value
            selector['editable'] = True
        else:
            need(operation == 'click' and node.get('clickable') is True,
                 'ACTUAL_CLICKABLE_CONFIRM_REQUIRED')
        self.number += 1
        self.c.step(request)
        need(time.monotonic() < self.deadline, 'UI_BUDGET_EXPIRED_AFTER_READBACK')

    def launch(self, index):
        need(self.t.owned is None and self.c.pending is None, 'PRIOR_TASK_OR_EFFECT_UNRESOLVED')
        self.c.pending = 'launch-' + str(index)
        self.t.launch()
        self.owned.append(self.t.owned[0])
        self.c.pending = None
        self.c.observe('launch-' + str(index))

    def close(self):
        if self.t.owned is None:
            return
        task = self.t.owned[0]
        count = self.t.removals
        self.t.close()
        need(self.t.removals == count + 1 and self.t.result.get('other_tasks_preserved') is True,
             'NORMAL_OWNED_CLOSE_NOT_VERIFIED')
        self.closed.append(task)

    def run(self):
        for index in range(2):
            self.launch(index)
            self.node('editor', '', True)
            self.node('other_editor', '', True)
            self.node('result', '尚未点击')
            self.node('confirm', '确认测试')
            value = 'Pocket4 QA r12 7d2ab6f9 round%d 中文 café 😀' % index
            second = 'Owned second field %d Ω' % index
            self.act('unicode', 'set-text', self.node('editor', '', True), value)
            self.node('editor', value, True)
            self.node('other_editor', '', True)
            self.act('second-field', 'set-text', self.node('other_editor', '', True), second)
            self.node('editor', value, True)
            self.node('other_editor', second, True)
            self.act('confirm-unicode', 'click', self.node('confirm', '确认测试'))
            self.node('result', '已点击：' + value)
            self.node('other_editor', second, True)
            self.act('clear-first', 'set-text', self.node('editor', value, True), '')
            self.node('editor', '', True)
            self.node('other_editor', second, True)
            self.act('confirm-empty', 'click', self.node('confirm', '确认测试'))
            self.node('result', '已点击：')
            self.act('clear-second', 'set-text', self.node('other_editor', second, True), '')
            self.node('editor', '', True)
            self.node('other_editor', '', True)
            self.r['rounds'].append({'round': index, 'task': self.t.owned[0],
                'unicode_readback': value, 'second_field_preserved': True,
                'confirm_uses_only_first_field': True, 'empty_input_result_verified': True,
                'owned_fields_cleared': True})
            self.close()
        self.r['functional_flow_verified'] = True


def execute():
    base, loop, diagnostic = [load(path, pin) for path, pin in PINS.items()]
    tx = base.load_session()
    base.PACKAGE, base.COMPONENT, base.ROOT = PACKAGE, COMPONENT, ROOT
    diagnostic.PACKAGE = PACKAGE
    loop.emit = lambda value: None
    result = {'schema': 'pocket4-probe-fixture-ui-v1', 'state': 'FAILED', 'rounds': [],
        'source_pins': PINS, 'automatic_retry': False, 'whole_app_production_ready': False,
        'functional_flow_verified': False, 'ui_business_and_diagnostics_verified': False,
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'lease_seconds': 240, 'cleanup_seconds': 35,
        'scope': 'Reviewed two-field and confirmation contract; fresh launch intentionally resets view state.'}
    trial = flow = None
    old = signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, 240)
        with tx.ui_lock():
            ROOT.mkdir(mode=0o700)
            with tx.CameraSession(ROOT / 'commands') as session:
                trial = base.Trial(session, tx)
                flow = Flow(trial, loop, result)
                diagnostics = diagnostic.Trial(session, tx, ROOT)
                try:
                    result['identity_before'] = identity(session)
                    before = diagnostics.diagnostics('diagnostics-before', UID)
                    diagnostic.exit_events(before['exits'])
                    flow.run()
                    after = diagnostics.diagnostics('diagnostics-after', UID)
                    result['diagnostics'] = diagnostic.fresh_crashes(before, after, UID, before['guest_seconds'])
                    need(result['diagnostics']['clear'], 'FRESH_PROBE_CRASH_ANR_OR_EXIT')
                    result['identity_after'] = identity(session)
                    need(result['identity_before'] == result['identity_after'], 'IDENTITY_OR_PERMISSIONS_CHANGED')
                    need(len(flow.closed) == len(set(flow.owned)) == 2 and flow.closed == flow.owned
                         and flow.c.pending is None and flow.c.actions == 12, 'UI_ACTION_OR_CLEANUP_COUNT_MISMATCH')
                    session.caller_status('probe-final-caller')
                    result.update(state='TWO_ROUND_UNICODE_CONFIRM_REOPEN_AND_CLEANUP_VERIFIED',
                                  ui_business_and_diagnostics_verified=True)
                except BaseException as exc:
                    result['error'] = type(exc).__name__ + ': ' + str(exc)
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 35)
                    flow.close()
    except BaseException as exc:
        result.update(state='FAILED', ui_business_and_diagnostics_verified=False,
                      terminal_error=type(exc).__name__ + ': ' + str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)
        result.update(ui_actions=flow.c.actions if flow else 0,
            pending_effect=flow.c.pending if flow else None,
            owned_tasks=flow.owned if flow else [], closed_tasks=flow.closed if flow else [],
            finished_utc=datetime.now(timezone.utc).isoformat())
        if ROOT.is_dir():
            tx.write_new(ROOT / 'result.json', result)
        tx.write_new(HERE / 'probe-ui02-result.json', result, alex_readable=True)
        print(json.dumps({key: result.get(key) for key in ('state','error','terminal_error',
            'ui_actions','pending_effect','owned_tasks','closed_tasks')}))
    return 0 if result['ui_business_and_diagnostics_verified'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    if parser.parse_args().execute:
        raise SystemExit(execute())
    print(json.dumps({'state': 'PLAN_ONLY', 'package': PACKAGE, 'ui_actions': 0,
        'planned_launches': 2, 'planned_inputs': 12, 'planned_normal_closes': 2,
        'package_changes': 0, 'account_operations': 0}))
