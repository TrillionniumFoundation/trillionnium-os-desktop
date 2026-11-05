#!/usr/bin/python3 -I
"""Decode the retained, hash-checked Android binary XML metadata locally."""
from pathlib import Path
import base64, hashlib, json, struct


def decode(data):
    def need(condition):
        if not condition: raise ValueError('UNRECOGNIZED_OR_TRUNCATED_AXML')
    def u16(offset): return struct.unpack_from('<H', data, offset)[0]
    def u32(offset): return struct.unpack_from('<I', data, offset)[0]
    need(len(data) >= 8 and u16(0) == 3 and u16(2) == 8 and u32(4) == len(data))
    strings, stack, elements = [], [], []
    def string(index):
        need(0 <= index < len(strings)); return strings[index]
    position = 8
    while position < len(data):
        kind, header, size = u16(position), u16(position + 2), u32(position + 4)
        end = position + size
        need(8 <= header <= size and end <= len(data))
        if kind == 1:
            need(not strings and header >= 28)
            count, style_count, flags, start = (u32(position + x) for x in (8, 12, 16, 20))
            need(count <= 4096 and style_count == 0 and header + 4 * count <= start < size)
            for i in range(count):
                at = position + start + u32(position + header + 4 * i)
                if flags & 0x100:
                    def length8(at):
                        first = data[at]; at += 1
                        return (((first & 0x7f) << 8) | data[at], at + 1) if first & 0x80 else (first, at)
                    chars, at = length8(at); length, at = length8(at)
                    need(at + length < end and data[at + length] == 0)
                    value = data[at:at + length].decode('utf-8')
                    need(len(value.encode('utf-16-le')) // 2 == chars)
                else:
                    length = u16(at); at += 2
                    if length & 0x8000: length = ((length & 0x7fff) << 16) | u16(at); at += 2
                    need(at + 2 * length + 2 <= end and u16(at + 2 * length) == 0)
                    value = data[at:at + 2 * length].decode('utf-16-le')
                strings.append(value)
        elif kind == 0x102:
            need(header == 16 and size >= 36)
            name = string(u32(position + 20))
            attribute_start, attribute_size, count = (u16(position + x) for x in (24, 26, 28))
            need(attribute_size == 20 and position + 16 + attribute_start + count * 20 <= end)
            attributes = {}
            for i in range(count):
                at = position + 16 + attribute_start + i * 20
                ns, key, raw = u32(at), string(u32(at + 4)), u32(at + 8)
                need(u16(at + 12) == 8 and data[at + 14] == 0)
                typ, value = data[at + 15], u32(at + 16)
                key = ('{' + string(ns) + '}' if ns != 0xffffffff else '') + key
                need(key not in attributes)
                if raw != 0xffffffff: value = string(raw)
                elif typ == 3: value = string(value)
                elif typ == 0x12: value = bool(value)
                elif typ == 1: value = '@0x%08x' % value
                elif typ == 0x11: value = '0x%08x' % value
                elif typ != 0x10: raise ValueError('UNSUPPORTED_ATTRIBUTE_TYPE:' + str(typ))
                attributes[key] = value
            elements.append({'path': '/'.join([*stack, name]), 'attributes': attributes})
            stack.append(name)
        elif kind == 0x103:
            need(stack and stack.pop() == string(u32(position + 20)))
        else:
            need(kind in (0x100, 0x101, 0x180))
        position = end
    need(not stack and position == len(data) and bool(elements))
    return elements


def main():
    root = Path(__file__).parent
    first = json.loads((root / 'read-only-preflight-result.json').read_text())
    finish = json.loads((root / 'read-only-finish-result.json').read_text())
    inputs = {'AndroidManifest.xml': first['packages']['org.chromium.webview_shell']['apks'][0]['manifest'],
              **finish['network_security_resources']}
    result = {}
    for name, record in inputs.items():
        data = base64.b64decode(record['base64'], validate=True)
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('RETAINED_BINARY_XML_HASH_MISMATCH')
        result[name] = {'sha256': record['sha256'], 'elements': decode(data)}
    output = root / 'decoded-manifest-and-network-security.json'
    with output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(json.dumps({name: record for name, record in result.items() if 'network' in name}, indent=2))


if __name__ == '__main__': main()
