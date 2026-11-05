"""Strict structural/behavioral IR for a same-toolchain smali round trip.

Labels resolve to instruction boundaries (and payload identities); catch coverage
is retained for every instruction. Only comments, debug line/local directives,
implicit boolean false field values and const-string/jumbo width are normalized.
"""
import hashlib
import json
import re

METHOD = re.compile(r'^\.method (.+)\n[\s\S]*?^\.end method$', re.M)
DEBUG = ('.line ', '.local ', '.end local ', '.restart local ', '.prologue', '.epilogue')
LABEL = re.compile(r':[A-Za-z_][A-Za-z_0-9]*')
CATCH = re.compile(r'^\.catch(?: (L[^;]+;)|all)\s+\{(:\w+)\s+\.\.\s+(:\w+)\}\s+(:\w+)$')


def outside_quotes(text, transform):
    """Transform unquoted spans; preserve literal string content and escapes."""
    result, start, i = [], 0, 0
    while i < len(text):
        if text[i] != '"':
            i += 1
            continue
        result.append(transform(text[start:i]))
        q = i
        i += 1
        while i < len(text):
            if text[i] == '\\':
                i += 2
            elif text[i] == '"':
                i += 1
                break
            else:
                i += 1
        else:
            raise ValueError('unterminated quoted string')
        result.append(text[q:i])
        start = i
    result.append(transform(text[start:]))
    return ''.join(result)


def strip_comment(line):
    quoted, escaped = False, False
    for i, c in enumerate(line):
        if quoted:
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
        elif c == '#':
            return line[:i].strip()
    return line.strip()


def header_ir(text):
    lines = []
    for raw in text.splitlines():
        line = strip_comment(raw)
        if not line:
            continue
        if line.startswith('.field ') and re.search(r':Z = false$', line):
            line = line[:-len(' = false')]
        lines.append(line)
    return lines


def method_ir(text):
    instructions, metadata, payloads, catches = [], [], [], []
    labels, pending = {}, []
    annotation_depth = 0
    payload = None

    def bind(payload_id=None):
        for name in pending:
            if name in labels:
                raise ValueError('duplicate label: ' + name)
            labels[name] = (len(instructions), payload_id)
        pending.clear()

    for raw in text.splitlines():
        line = strip_comment(raw)
        if not line:
            continue
        if payload is not None:
            payload['lines'].append(line)
            if line == '.end ' + payload['kind']:
                payload = None
            continue
        if annotation_depth:
            metadata.append(line)
            if re.search(r'(^|=\s*)\.subannotation\s', line):
                annotation_depth += 1
            elif line in ('.end annotation', '.end subannotation'):
                annotation_depth -= 1
            continue
        if line.startswith('.annotation '):
            annotation_depth = 1
            metadata.append(line)
        elif line.startswith(DEBUG):
            continue
        elif line.startswith(':'):
            if not re.fullmatch(r':[A-Za-z_][A-Za-z_0-9]*', line):
                raise ValueError('bad label declaration: ' + line)
            pending.append(line)
        elif line.startswith(('.packed-switch ', '.sparse-switch', '.array-data ')):
            bind(len(payloads))
            payload = {'kind': line.split()[0][1:], 'lines': [line]}
            payloads.append(payload)
        elif line.startswith('.catch'):
            m = CATCH.fullmatch(line)
            if not m:
                raise ValueError('unsupported catch syntax: ' + line)
            catches.append((m[1] or 'all', m[2], m[3], m[4]))
        elif line == '.end method':
            bind()
        elif line.startswith('.'):
            metadata.append(line)
        else:
            bind()
            if line.startswith('const-string/jumbo '):
                line = 'const-string ' + line[len('const-string/jumbo '):]
            instructions.append(line)
    if payload is not None or annotation_depth:
        raise ValueError('unterminated metadata/payload')
    bind()

    def resolve(text):
        def replace(match):
            name = match[0]
            if name not in labels:
                return name
            index, payload_id = labels[name]
            return '@instruction[' + str(index) + ']' if payload_id is None else (
                '@payload[' + str(payload_id) + ';boundary=' + str(index) + ']')
        return outside_quotes(text, lambda span: LABEL.sub(replace, span))

    coverage = [[] for _ in instructions]
    for typ, start, end, handler in catches:
        if any(name not in labels for name in (start, end, handler)):
            raise ValueError('unknown catch label')
        begin, finish, destination = labels[start][0], labels[end][0], labels[handler][0]
        if not 0 <= begin <= finish <= len(instructions):
            raise ValueError('invalid catch coverage')
        if labels[handler][1] is not None or not 0 <= destination < len(instructions):
            raise ValueError('invalid exception handler destination')
        for index in range(begin, finish):
            coverage[index].append([typ, destination])
    return dict(metadata=[resolve(x) for x in metadata],
                instructions=[resolve(x) for x in instructions],
                payloads=[dict(kind=p['kind'], lines=[resolve(x) for x in p['lines']])
                          for p in payloads], exception_coverage=coverage)


def class_ir(text):
    methods, outside, at = {}, [], 0
    for match in METHOD.finditer(text):
        signature = match[1]
        if signature in methods:
            raise ValueError('duplicate method signature')
        outside.append(text[at:match.start()])
        methods[signature] = method_ir(match[0])
        at = match.end()
    outside.append(text[at:])
    return dict(header=header_ir(''.join(outside)), methods=methods)


def ir_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
