"""Complete original ProbeActivity03 two-round business state machine."""
import hashlib, re, time, types

def make_case(session, trial, loop, result):
    PACKAGE = 'local.pocket4.fixture'
    COMPONENT = PACKAGE + '/.ProbeActivity'
    UID = 10115
    APK_SHA = '91e352c25e7c6ef54aa53ce652931e40ad1437dfcd0ebad2529bc662558a3dd6'
    APK = session.identities[0]['artifacts'][0]['guest_path']
    def need(condition, reason):
        if not condition:
            raise RuntimeError(reason)

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
                # The actual Android 17 tree reports TextView's visible hint in text.
                # Do not rewrite that node. The empty first-field value is proved
                # separately by ProbeActivity's own getText() -> confirmation result.
                hints = {'editor': '中文与 Unicode 输入',
                         'other_editor': '第二个输入框：验证歧义拒绝'}
                observed_hint = (editable and expected == '' and name in hints
                    and node.get('hint') == node.get('text') == hints[name])
                need(node.get('text') == expected or observed_hint,
                     'EXACT_FIXTURE_READBACK_REQUIRED_' + name)
            return node

        def act(self, tag, operation, node, value=None):
            need(time.monotonic() < self.deadline and self.number < 14 and self.c.pending is None,
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
                self.act('confirm-initial-empty', 'click', self.node('confirm', '确认测试'))
                self.node('result', '已点击：')
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
    return types.SimpleNamespace(flow=Flow(trial, loop, result), identity=identity)
