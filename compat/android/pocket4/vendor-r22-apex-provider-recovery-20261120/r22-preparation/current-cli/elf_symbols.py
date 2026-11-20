"""Parse complete readelf dynamic-symbol output without executing an ELF."""
import re


def dynamic_symbols(raw):
    text = raw.decode('utf-8', 'strict')
    headers = re.findall(r"^Symbol table '\.dynsym' contains ([0-9]+) entries:$", text, re.M)
    if len(headers) != 1:
        raise ValueError('exactly one complete dynamic symbol table is required')
    rows = []
    for line in text.splitlines():
        fields = line.split()
        if fields and re.fullmatch(r'[0-9]+:', fields[0]):
            if len(fields) < 7:
                raise ValueError('incomplete dynamic symbol row')
            rows.append(fields)
    if [int(r[0][:-1]) for r in rows] != list(range(int(headers[0]))):
        raise ValueError('dynamic symbol table is incomplete or duplicated')
    strong, weak, definitions = set(), set(), set()
    for row in rows:
        if len(row) < 8:
            continue
        bind, visibility, section, name = row[4:8]
        if section == 'UND':
            if bind == 'GLOBAL':
                strong.add(name)
            elif bind == 'WEAK':
                weak.add(name)
            else:
                raise ValueError('unexpected named undefined symbol binding: ' + bind)
        elif bind in ('GLOBAL', 'WEAK', 'UNIQUE') and visibility in ('DEFAULT', 'PROTECTED'):
            definitions.add(name.replace('@@', '@'))
            if '@@' in name:
                definitions.add(name.split('@@', 1)[0])
    return {'strong': sorted(strong), 'weak': sorted(weak), 'definitions': sorted(definitions),
            'dynamic_symbol_rows': len(rows)}


def executable_imports(raw):
    text = raw.decode('utf-8', 'strict')
    interpreters = re.findall(r'\[Requesting program interpreter: ([^\]]+)\]', text)
    needed = re.findall(r'\(NEEDED\)\s+Shared library: \[([^\]]+)\]', text)
    if len(interpreters) != 1 or interpreters[0] != '/lib64/ld-linux-x86-64.so.2':
        raise ValueError('the actual reviewed x86_64 interpreter is required')
    if not needed or len(needed) != len(set(needed)) or any('/' in n or '\\' in n for n in needed):
        raise ValueError('a distinct direct SONAME list is required')
    symbols = dynamic_symbols(raw)
    return {'interpreter': interpreters[0], 'needed': sorted(needed),
            'strong_imports': symbols['strong'], 'weak_imports': symbols['weak'],
            'dynamic_symbol_rows': symbols['dynamic_symbol_rows']}
