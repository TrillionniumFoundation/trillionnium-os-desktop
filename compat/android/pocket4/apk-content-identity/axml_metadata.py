"""Bounded Android binary XML structural metadata, without resource resolution."""
import struct
import hashlib
import xml.etree.ElementTree as ET

ANDROID = 'http://schemas.android.com/apk/res/android'
ET.register_namespace('android', ANDROID)


def decode_axml(data, noncanonical_headers=None):
    if len(data) > 1024 * 1024 or len(data) < 8:
        raise ValueError('Binary manifest size bound')
    kind, header, size = struct.unpack_from('<HHI', data)
    if kind != 3 or header != 8 or size != len(data):
        raise ValueError('Invalid binary XML header')
    strings, stack, root, namespaces = None, [], None, {}

    def string(index):
        if index == 0xffffffff:
            return None
        if strings is None or index >= len(strings):
            raise ValueError('Invalid XML string index')
        return strings[index]

    offset = header
    events = 0
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError('Truncated XML chunk')
        tag, head, length = struct.unpack_from('<HHI', data, offset)
        end = offset + length
        if head < 8 or length < head or end > len(data):
            raise ValueError('Invalid XML chunk bounds')
        events += 1
        if events > 20000:
            raise ValueError('XML event bound')
        if tag == 1:
            if strings is not None or head < 28:
                raise ValueError('Invalid/repeated XML string pool')
            count, styles, flags, begin, style_begin = struct.unpack_from('<IIIII', data, offset + 8)
            if count > 50000 or head + count * 4 > length or begin < head + (count + styles) * 4:
                raise ValueError('Invalid string pool dimensions')
            strings = []
            utf8 = bool(flags & 0x100)
            def sized(position, unit):
                if unit == 1:
                    if position >= end:
                        raise ValueError('Truncated UTF8 size')
                    v = data[position]
                    position += 1
                    if v & 0x80:
                        if position >= end:
                            raise ValueError('Truncated UTF8 size extension')
                        v = ((v & 0x7f) << 8) | data[position]
                        position += 1
                else:
                    if position + 2 > end:
                        raise ValueError('Truncated UTF16 size')
                    v = struct.unpack_from('<H', data, position)[0]
                    position += 2
                    if v & 0x8000:
                        if position + 2 > end:
                            raise ValueError('Truncated UTF16 size extension')
                        v = ((v & 0x7fff) << 16) | struct.unpack_from('<H', data, position)[0]
                        position += 2
                return v, position
            for i in range(count):
                item = struct.unpack_from('<I', data, offset + head + i * 4)[0]
                position = offset + begin + item
                utf16_count, position = sized(position, 1 if utf8 else 2)
                if utf8:
                    byte_count, position = sized(position, 1)
                else:
                    byte_count = utf16_count * 2
                if position + byte_count + (1 if utf8 else 2) > end:
                    raise ValueError('String exceeds pool')
                terminator = data[position + byte_count:position + byte_count + (1 if utf8 else 2)]
                if any(terminator):
                    raise ValueError('Missing string terminator')
                strings.append(data[position:position + byte_count].decode('utf-8' if utf8 else 'utf-16le'))
        elif tag == 0x180:
            if head != 8 or (length - head) % 4:
                raise ValueError('Invalid XML resource map')
        elif tag in (0x100, 0x101):
            if head != 16 or length < 24:
                raise ValueError('Invalid namespace chunk')
            prefix, uri = struct.unpack_from('<II', data, offset + head)
            if tag == 0x100:
                namespaces[string(uri)] = string(prefix)
        elif tag == 0x102:
            if head != 16 or length < 36:
                raise ValueError('Invalid start element')
            namespace, name, start, stride, count, id_index, class_index, style_index = struct.unpack_from('<IIHHHHHH', data, offset + head)
            name = string(name)
            uri = string(namespace)
            element = ET.Element('{' + uri + '}' + name if uri else name)
            attr_start = offset + head + start
            if stride < 20 or count > 2000 or attr_start + stride * count > end:
                raise ValueError('Invalid attribute dimensions')
            for i in range(count):
                position = attr_start + i * stride
                ns, key, raw, value_size, reserved, value_kind, value = struct.unpack_from('<IIIHBBI', data, position)
                if (value_size != 8 or reserved) and noncanonical_headers is not None:
                    # Android ResXMLParser reads the fixed attribute structure's dataType/data,
                    # not typedValue.size: ResourceTypes.cpp blob de9991a8be5e2919b49f2fc4a307999972855bc9.
                    # The full 20-byte attribute is already bounded by stride/count above.
                    noncanonical_headers.append({'offset': position, 'attribute': string(key),
                                                 'declared_value_size': value_size,
                                                 'reserved': reserved, 'data_type': value_kind})
                ns, key = string(ns), string(key)
                key = '{' + ns + '}' + key if ns else key
                if raw != 0xffffffff:
                    rendered = string(raw)
                elif value_kind == 3:
                    rendered = string(value)
                elif value_kind == 0x12:
                    rendered = 'true' if value else 'false'
                elif value_kind == 0x10:
                    rendered = str(value)
                elif value_kind == 0x11:
                    rendered = f'0x{value:x}'
                elif value_kind in (1, 2):
                    rendered = ('@' if value_kind == 1 else '?') + f'0x{value:08x}'
                else:
                    rendered = f'typed:{value_kind:02x}:0x{value:08x}'
                if key in element.attrib:
                    raise ValueError('Duplicate attribute')
                element.set(key, rendered)
            if stack:
                stack[-1].append(element)
            elif root is None:
                root = element
            else:
                raise ValueError('Multiple XML roots')
            stack.append(element)
            if len(stack) > 128:
                raise ValueError('XML depth bound')
        elif tag == 0x103:
            if head != 16 or length < 24 or not stack:
                raise ValueError('Invalid end element')
            ns, name = struct.unpack_from('<II', data, offset + head)
            ns, name = string(ns), string(name)
            expected = '{' + ns + '}' + name if ns else name
            if stack[-1].tag != expected:
                raise ValueError('Mismatched end element')
            stack.pop()
        elif tag == 0x104:
            if head != 16 or length < 28 or not stack:
                raise ValueError('Invalid XML text chunk')
            index = struct.unpack_from('<I', data, offset + head)[0]
            content = string(index)
            if len(stack[-1]):
                child = stack[-1][-1]
                child.tail = (child.tail or '') + content
            else:
                stack[-1].text = (stack[-1].text or '') + content
        else:
            raise ValueError(f'Unsupported XML chunk {tag:x}')
        offset = end
    if stack or root is None or root.tag != 'manifest':
        raise ValueError('Incomplete/invalid manifest')
    return root


def metadata(data):
    headers = []
    root = decode_axml(data, headers)
    app = root.find('application')
    sdk = root.find('uses-sdk')
    get = lambda element, key: element.get('{' + ANDROID + '}' + key) if element is not None else None
    return {'package': root.get('package'), 'version_code': int(get(root, 'versionCode') or '0', 0),
            'version_name': get(root, 'versionName'), 'shared_user_id_name': get(root, 'sharedUserId'),
            'version_code_major': int(get(root, 'versionCodeMajor') or '0', 0),
            'split_name': root.get('split'),
            'min_sdk_version': get(sdk, 'minSdkVersion'), 'target_sdk_version': get(sdk, 'targetSdkVersion'),
            'version_code_attribute_present': get(root, 'versionCode') is not None,
            'axml_noncanonical_typed_header_count': len(headers),
            'axml_noncanonical_typed_header_examples': headers[:16],
            'manifest_flags': {k: get(app, k) for k in ('debuggable', 'testOnly', 'allowBackup')},
            'xml': ET.tostring(root, encoding='unicode')}


def signing_block_certificates(path):
    """Read public certificate bytes tied to this APK; cryptographic verify is separate."""
    with open(path, 'rb') as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 65557))
        tail = f.read()
        eocd = tail.rfind(b'PK\x05\x06')
        if eocd < 0 or eocd + 22 > len(tail):
            raise ValueError('ZIP EOCD missing')
        comment = struct.unpack_from('<H', tail, eocd + 20)[0]
        if eocd + 22 + comment != len(tail):
            raise ValueError('ZIP EOCD boundary invalid')
        central = struct.unpack_from('<I', tail, eocd + 16)[0]
        if central < 32 or central > size:
            raise ValueError('ZIP central directory offset invalid')
        f.seek(central - 24)
        footer = f.read(24)
        if footer[8:] != b'APK Sig Block 42':
            return {'signing_block_present': False, 'certificate_sha256': []}
        block_size = struct.unpack_from('<Q', footer)[0]
        if block_size < 24 or block_size > 8 * 1024 * 1024 or block_size + 8 > central:
            raise ValueError('APK signing block size bound')
        f.seek(central - block_size - 8)
        block = f.read(block_size + 8)
    if struct.unpack_from('<Q', block)[0] != block_size:
        raise ValueError('APK signing block length mismatch')
    def part(data, position=0):
        if position + 4 > len(data):
            raise ValueError('Truncated signing length')
        length = struct.unpack_from('<I', data, position)[0]
        start, end = position + 4, position + 4 + length
        if end > len(data):
            raise ValueError('Truncated signing field')
        return data[start:end], end
    certificates, schemes, scheme_certificates = [], [], {}
    position, limit = 8, len(block) - 24
    while position < limit:
        if position + 12 > limit:
            raise ValueError('Truncated signing pair')
        length, identifier = struct.unpack_from('<QI', block, position)
        if length < 4 or position + 8 + length > limit:
            raise ValueError('Invalid signing pair')
        value = block[position + 12:position + 8 + length]
        position += 8 + length
        if identifier not in (0x7109871a, 0xf05368c0, 0x1b93ad61):
            continue
        schemes.append(f'0x{identifier:08x}')
        selected = scheme_certificates.setdefault(f'0x{identifier:08x}', [])
        signers, consumed = part(value)
        if consumed != len(value):
            raise ValueError('Trailing signing sequence')
        next_signer = 0
        while next_signer < len(signers):
            signer, next_signer = part(signers, next_signer)
            signed, ignored = part(signer)
            digests, cert_offset = part(signed)
            cert_sequence, ignored = part(signed, cert_offset)
            cert_position = 0
            if cert_sequence:
                certificate, cert_position = part(cert_sequence)
                certificate_sha = hashlib.sha256(certificate).hexdigest()
                certificates.append(certificate_sha)
                selected.append(certificate_sha)
    if position != limit:
        raise ValueError('APK signing pairs incomplete')
    return {'signing_block_present': True, 'block_sha256': hashlib.sha256(block).hexdigest(),
            'scheme_ids': schemes, 'certificate_sha256': sorted(set(certificates)),
            'certificate_sha256_by_scheme': {k: sorted(set(v)) for k, v in scheme_certificates.items()},
            'cryptographic_verification_by_this_parser': False}


def verified_scheme_certificates(output, block):
    """Bind to the strongest scheme actually verified; keep other platform ranges distinct."""
    import re
    schemes = {kind: value == 'true' for kind, value in re.findall(r'Verified using (v[\d.]+) scheme[^:]*:\s*(true|false)', output)}
    if schemes.get('v3.2'):
        raise ValueError('APK v3.2 signer selection requires an explicitly implemented verifier mapping')
    for name, identifier in [('v3.1', '0x1b93ad61'), ('v3', '0xf05368c0'), ('v2', '0x7109871a')]:
        if schemes.get(name):
            if identifier not in block.get('certificate_sha256_by_scheme', {}):
                raise ValueError('Verified signing scheme absent from actual APK signing block')
            return {'scheme': name, 'certificate_sha256': block['certificate_sha256_by_scheme'][identifier]}
    raise ValueError('No supported APK block scheme was cryptographically verified')
