#!/usr/bin/env python3
"""Execute the real builder suffix symbolically; old pre-N text is the localization oracle.

This is not an Android, desktop-notification, or audio acceptance test. Resources
remain opaque (resource ID plus format arguments), so no English string is invented.
"""
from pathlib import Path
import hashlib, json, re

ROOT = Path(__file__).resolve().parent
PINS = {'TimerNotificationBuilder.original.smali': '6df1845e689b0219908a051b679e39707e08e680a0db3f36f85c2d6be8e81dbd',
        'TimerNotificationBuilder.smali': 'd618e064ffc6719312a8a5b79b8e585ae9cbcda6ab2a42fd8cd94c00117e8bf1'}
METHOD = 'public final buildHeadsUp(Landroid/content/Context;Ljava/util/List;)Landroid/app/Notification;'


def suffix(name):
    raw = (ROOT / name).read_bytes(); assert hashlib.sha256(raw).hexdigest() == PINS[name]
    matches = [m[0] for m in re.finditer(r'^\.method (.+)\n[\s\S]*?^\.end method$', raw.decode(), re.M) if m[1] == METHOD]
    assert len(matches) == 1
    method = matches[0]; start = method.index('    :cond_135\n')
    return [line.strip() for line in method[start:].splitlines()
            if line.strip() and not line.strip().startswith(('#', '.'))]


def execute(program, n_or_later, count, title):
    assert count > 0
    builder = {'prefix_untouched': ('actions', 'flags', 'channel', 'pending_intents')}
    registers = {'v0': 'context', 'v2': count, 'v3': builder, 'v8': 0x7f1202cd, 'v9': 0x7f1202e6,
        'v11': 1, 'v14': 'com.android.deskclock', 'v15': ('base-long', 123456), 'v16': 'wide-high',
        'v18': title, 'p0': 'renderer'}
    labels = {line: index for index, line in enumerate(program) if line.startswith(':')}
    pc, result = 0, None
    for _ in range(200):
        line = program[pc]; pc += 1
        if line.startswith(':'):
            continue
        op, arguments = line.split(' ', 1)
        if op.startswith('move-result'):
            registers[arguments] = result
        elif op.startswith('move-object'):
            target, source = arguments.split(', '); registers[target] = registers[source]
        elif op.startswith('const'):
            target, value = arguments.split(', '); registers[target] = int(value, 0)
        elif op == 'sget-object':
            target, field = arguments.split(', '); assert field.endswith('Utils;->INSTANCE:Lcom/android/deskclock/Utils;')
            registers[target] = 'utils'
        elif op in ('if-eqz', 'if-ne'):
            terms = arguments.split(', ')
            jump = registers[terms[0]] == 0 if op == 'if-eqz' else registers[terms[0]] != registers[terms[1]]
            if jump:
                pc = labels[terms[-1]]
        elif op == 'goto':
            pc = labels[arguments]
        elif op.startswith('invoke-') or op == 'filled-new-array':
            match = re.fullmatch(r'\{([^}]*)\}, (.+)', arguments); assert match, line
            names, target = match.groups()
            if ' .. ' in names:
                first, last = names.split(' .. '); assert first[0] == last[0] == 'v'
                names = ', '.join('v' + str(n) for n in range(int(first[1:]), int(last[1:]) + 1))
            values = [registers[n] for n in names.split(', ')] if names else []
            if op == 'filled-new-array':
                assert target == '[Ljava/lang/Object;'; result = tuple(values)
            elif 'Utils;->isNOrLater()Z' in target:
                assert values == ['utils']; result = n_or_later
            elif 'Context;->getString(' in target:
                assert values[0] == 'context'; result = ('localized', values[1], tuple(values[2]) if len(values) == 3 else ())
            elif 'Integer;->valueOf(I)' in target:
                result = values[0]
            elif 'Object;->getClass()' in target:
                assert values[0] is not None; result = 'class'
            elif 'TimerNotificationBuilder;->buildChronometer(' in target:
                assert values[0] == 'renderer'; result = ('custom-view', tuple(values[1:]))
            elif 'NotificationCompat$Builder;->setContentTitle(' in target:
                assert values[0] is builder; builder['title'] = values[1]; result = builder
            elif 'NotificationCompat$Builder;->setContentText(' in target:
                assert values[0] is builder; builder['text'] = values[1]; result = builder
            elif 'NotificationCompat$Builder;->setCustomContentView(' in target:
                assert values[0] is builder; builder['custom_view'] = values[1]; result = builder
            elif 'NotificationCompat$Builder;->build()' in target:
                assert values[0] is builder; result = dict(builder)
            else:
                raise AssertionError('UNHANDLED_ACTUAL_INVOKE:' + target)
        elif op == 'return-object':
            return registers[arguments]
        else:
            raise AssertionError('UNHANDLED_ACTUAL_OPCODE:' + line)
    raise AssertionError('SYMBOLIC_EXECUTION_BUDGET')


def main():
    old = suffix('TimerNotificationBuilder.original.smali'); new = suffix('TimerNotificationBuilder.smali')
    cases = [(1, ('localized', 0x7f1202e6, ())), (1, 'Owned timer Ω 😀'),
        (2, ('localized', 0x7f1202cd, (2,))), (3, ('localized', 0x7f1202cd, (3,))),
        (17, ('localized', 0x7f1202cd, (17,)))]
    rows = []
    for count, title in cases:
        oracle = execute(old, False, count, title)
        before = execute(old, True, count, title)
        after = execute(new, True, count, title)
        legacy_after = execute(new, False, count, title)
        expected = {k: oracle[k] for k in ('title', 'text')}
        assert 'title' not in before and 'text' not in before, 'ORIGINAL_N_PATH_MUST_EXPOSE_MISSING_METADATA'
        assert {k: after[k] for k in ('title', 'text')} == expected, 'NEW_N_METADATA_DIFFERS_FROM_OLD_LOCALIZED_ORACLE'
        assert legacy_after == oracle, 'LEGACY_BRANCH_CHANGED'
        assert {k: v for k, v in after.items() if k not in ('title', 'text')} == before, 'CUSTOM_VIEW_OR_PREFIX_CHANGED'
        rows.append({'expired_count': count, 'expected_standard_text': expected,
            'old_N_contract_pass': False, 'new_N_contract_pass': True, 'pre_N_unchanged': True,
            'custom_view_and_other_prefix_fields_unchanged': True})
    result = {'state': 'ACTUAL_BUILDER_SUFFIX_SYMBOLIC_EQUIVALENCE_PASS', 'cases': rows, 'count': len(rows),
        'negative_control_old_N_missing_text': len(rows), 'new_N_pass': len(rows),
        'oracle': 'Unmodified original buildHeadsUp pre-N branch, opaque localized resource ID/format arguments.',
        'entry_state_scope': 'Unchanged prefix has resolved title, expired count, Context, Builder and chronometer inputs; only the real suffix is executed.',
        'runtime_Android_Notify_or_audio_verified': False, 'source_pins': PINS}
    raw = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode()
    (ROOT / 'text-semantics-validation.json').write_bytes(raw)
    print(json.dumps({'state': result['state'], 'negative_control_failures': len(rows), 'new_cases_passed': len(rows),
        'result_sha256': hashlib.sha256(raw).hexdigest()}, sort_keys=True))


if __name__ == '__main__':
    main()
