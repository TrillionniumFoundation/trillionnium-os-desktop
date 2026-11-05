#!/usr/bin/env python3
"""Deterministic, source-pinned Clock alarm dispatch patch; no device access."""
from pathlib import Path
import argparse
import difflib
import hashlib
import importlib.util
import json
import re

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'expired-text' / 'saved-audit01' / 'smali'
PACKAGE = Path('com/android/deskclock/alarms')
NAMES = ('AlarmStateManager$AlarmManagerStateChangeScheduler.smali',
         'AlarmStateManager$Companion.smali', 'AlarmStateManager.smali', 'AlarmService.smali')
METHOD = re.compile(r'^\.method (.+)\n[\s\S]*?^\.end method$', re.M)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def replace_method(source, signature, fragment):
    matches = [m for m in METHOD.finditer(source) if m[1] == signature]
    require(len(matches) == 1, 'EXACT_METHOD_REQUIRED:' + signature)
    match = matches[0]
    return source[:match.start()] + fragment.rstrip() + source[match.end():]


def fragment(name):
    raw = (ROOT / 'fragments' / name).read_text()
    def registers(match):
        value = match[0]
        signature = match[1]
        args = signature[signature.index('(') + 1:signature.index(')')]
        words = 0 if signature.startswith('static ') or ' static ' in signature else 1
        for arg in re.findall(r'\[*L[^;]+;|\[*[ZBSCIFJD]', args):
            words += 2 if arg in ('J', 'D') else 1
        return re.sub(r'(?m)^    \.locals (\d+)$',
                      lambda m: '    .registers ' + str(int(m[1]) + words), value)
    return METHOD.sub(registers, raw).replace('    goto :', '    goto/16 :')


def patch(sources):
    result = dict(sources)
    name = NAMES[0]
    result[name] = replace_method(result[name],
        'public cancelScheduledInstanceStateChange(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V',
        fragment('cancel-scheduled.smali'))
    result[name] = replace_method(result[name],
        'public scheduleInstanceStateChange(Landroid/content/Context;Ljava/util/Calendar;Lcom/android/deskclock/provider/AlarmInstance;I)V',
        fragment('schedule.smali'))
    name = NAMES[1]
    signature = 'public final handleIntent(Landroid/content/Context;Landroid/content/Intent;)V'
    method = next(m[0] for m in METHOD.finditer(result[name]) if m[1] == signature)
    anchor = '    :cond_57\n    sget-object v0, Lcom/android/deskclock/data/DataModel;->Companion:Lcom/android/deskclock/data/DataModel$Companion;'
    require(method.count(anchor) == 1, 'HANDLER_VALIDATION_INSERTION_POINT_CHANGED')
    hook = '''    :cond_57
    invoke-virtual {p0, p1, p2, v1}, Lcom/android/deskclock/alarms/AlarmStateManager$Companion;->isScheduledIntentCurrent(Landroid/content/Context;Landroid/content/Intent;Lcom/android/deskclock/provider/AlarmInstance;)Z
    move-result v0
    if-nez v0, :scheduled_accepted
    return-void
    :scheduled_accepted
    sget-object v0, Lcom/android/deskclock/data/DataModel;->Companion:Lcom/android/deskclock/data/DataModel$Companion;'''
    result[name] = replace_method(result[name], signature, method.replace(anchor, hook))
    result[name] += '\n' + fragment('validate-scheduled.smali')
    name = NAMES[2]
    result[name] = replace_method(result[name],
        'public static $r8$lambda$_knPXn4cJMDcun_XoalMIdqZCj0(Landroid/content/Context;Landroid/content/Intent;Landroid/content/BroadcastReceiver$PendingResult;Landroid/os/PowerManager$WakeLock;)Lkotlin/Unit;',
        fragment('receiver-dispatch.smali'))
    name = NAMES[3]
    signature = 'public onStartCommand(Landroid/content/Intent;II)I'
    method = next(m[0] for m in METHOD.finditer(result[name]) if m[1] == signature)
    anchor = '    .registers 9\n'
    require(method.count(anchor) == 1, 'SERVICE_REGISTER_PREIMAGE_CHANGED')
    hook = '''    .registers 9
    invoke-direct {p0, p1, p3}, Lcom/android/deskclock/alarms/AlarmService;->onScheduledStart(Landroid/content/Intent;I)Z
    move-result v0
    if-eqz v0, :scheduled_legacy
    const/4 v0, 0x2
    return v0
    :scheduled_legacy
'''
    result[name] = replace_method(result[name], signature, method.replace(anchor, hook))
    result[name] += '\n' + fragment('service-scheduled.smali')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    pins_path = ROOT / 'preimage-pins.json'
    pins = json.loads(pins_path.read_text())
    sources = {}
    for name in NAMES:
        raw = (BASE / PACKAGE / name).read_bytes()
        require(digest(raw) == pins[name]['sha256'] and len(raw) == pins[name]['bytes'], 'PREIMAGE_CHANGED:' + name)
        sources[name] = raw.decode()
    candidate = patch(sources)
    ir_path = ROOT.parent / 'expired-text' / 'smali_equivalence.py'
    require(digest(ir_path.read_bytes()) == 'a895a4e3963f958ea6a6ff45b9d0c51f6239118b3a10fddff6d0f17e22e25f9f', 'IR_COMPARATOR_CHANGED')
    spec = importlib.util.spec_from_file_location('clock_ir04', ir_path)
    ir = importlib.util.module_from_spec(spec); spec.loader.exec_module(ir)
    review = {'schema': 'pocket4-clock-alarm-source-delta-v1', 'installed': False, 'UI_actions': 0,
        'base_apk_sha256': 'e4ff4b46a651ff3ac77397705b7b749c7fbaaeb94fe1d00818debb31dea34172',
        'base_dex_sha256': 'c6721db34c21c5bab07712a6ddc3eaaf9c6617196856f9abf29741c18f956d22',
        'classes': {}}
    patch_lines = []
    for name in NAMES:
        before, after = sources[name], candidate[name]
        a, b = ir.class_ir(before), ir.class_ir(after)
        require(a['header'] == b['header'], 'CLASS_HEADER_CHANGED:' + name)
        require(a['methods'].keys() <= b['methods'].keys(), 'ORIGINAL_METHOD_REMOVED:' + name)
        changed = [key for key in a['methods'] if a['methods'][key] != b['methods'][key]]
        added = sorted(b['methods'].keys() - a['methods'].keys())
        review['classes'][name] = {'before_sha256': digest(before.encode()), 'after_sha256': digest(after.encode()),
            'before_bytes': len(before.encode()), 'after_bytes': len(after.encode()),
            'changed_original_methods': changed, 'added_methods': added,
            'unchanged_original_methods': len(a['methods']) - len(changed),
            'expected_ir_sha256': ir.ir_sha256(b)}
        patch_lines.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
            fromfile='a/' + str(PACKAGE / name), tofile='b/' + str(PACKAGE / name)))
        if args.write:
            for sub, text in (('original', before), ('candidate', after)):
                target = ROOT / sub / PACKAGE / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
    review['modified_original_method_count'] = sum(len(v['changed_original_methods']) for v in review['classes'].values())
    review['added_method_count'] = sum(len(v['added_methods']) for v in review['classes'].values())
    require(review['modified_original_method_count'] == 5 and review['added_method_count'] == 6, 'EXACT_CHANGE_SET_REQUIRED')
    if args.write:
        (ROOT / 'alarm-dispatch04.patch').write_text(''.join(patch_lines))
        (ROOT / 'source-change-proof.json').write_text(json.dumps(review, indent=2, sort_keys=True) + '\n')
    print(json.dumps(review, sort_keys=True))


if __name__ == '__main__':
    main()
