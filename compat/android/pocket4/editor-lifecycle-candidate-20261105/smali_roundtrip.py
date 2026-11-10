"""Narrow extension of the pinned same-toolchain IR for newly written methods.

Only add canonical register totals (.locals includes parameter words) and field
definition ordering. Method instructions, literal strings, annotations, payloads,
and per-instruction exception coverage remain compared by the existing IR.
"""
import re
import smali_ir_base as base


def parameter_words(head):
    signature = head.split()[-1]
    descriptor = signature[signature.index('(') + 1:signature.index(')')]
    words = 0 if 'static' in head.split()[:-1] else 1
    at = 0
    while at < len(descriptor):
        start = at
        while descriptor[at] == '[':
            at += 1
        if descriptor[at] == 'L':
            end = descriptor.index(';', at)
            at = end + 1
        else:
            if descriptor[at] not in 'ZBSCIJFD':
                raise ValueError('invalid parameter descriptor')
            at += 1
        item = descriptor[start:at]
        words += 2 if item in ('J', 'D') else 1
    return words


def canonical_registers(text):
    def replace(match):
        method = match.group()
        head = method.splitlines()[0]
        found = re.findall(r'^\s*\.(locals|registers)\s+(\d+)\s*$', method, re.M)
        if not found:
            if 'abstract' in head.split() or 'native' in head.split():
                return method
            raise ValueError('one register declaration required')
        if len(found) != 1:
            raise ValueError('ambiguous register declaration')
        kind, number = found[0]
        total = int(number) + (parameter_words(head) if kind == 'locals' else 0)
        return re.sub(r'^\s*\.(?:locals|registers)\s+\d+\s*$',
                      '    .registers ' + str(total), method, count=1, flags=re.M)
    return base.METHOD.sub(replace, text)


def class_ir(text):
    result = base.class_ir(canonical_registers(text))
    prefix, fields, current = [], {}, None
    for line in result['header']:
        if line.startswith('.field '):
            if line in fields:
                raise ValueError('duplicate field definition')
            current = line
            fields[current] = [line]
        elif current is None:
            prefix.append(line)
        else:
            # Field annotations stay attached to their exact field block.
            fields[current].append(line)
    result['header'] = {'class_metadata': prefix, 'fields': fields}
    return result


ir_sha256 = base.ir_sha256
