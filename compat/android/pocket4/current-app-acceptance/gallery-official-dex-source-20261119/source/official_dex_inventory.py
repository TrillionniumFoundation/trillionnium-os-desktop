#!/usr/bin/env python3
"""Read the retained official Gallery APK; inventory DEX source, never execute it.

The parser follows https://source.android.com/docs/core/runtime/dex-format .
It deliberately reports static table and instruction-byte identity only. It is
not an ART verifier, instruction decoder, behavioral proof or install adapter.
"""
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import resource
import stat
import struct
import sys
import time
import zipfile
import zlib

ROOT = Path('/home/qq/work/p4-gallery-official-source-5cd1-20261119-r1')
SOURCE = Path('/home/qq/work/p4-remaining-app-inputs-20261118-162b-r1/gsi-system-apks-source-20261119-r2')
APK = (SOURCE / 'apks/com.android.gallery3d.apk', 7390425,
       '835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439')
RECEIPT = (SOURCE / 'receipts/com.android.gallery3d.json', 326611,
           'e0326b9a0f8acc599cf7ef1190cc03c967a5578e34efcdba55cc0f3f46f932ad')
DEX = (1857660, '725ac7153e9ab4a9742672c238fc140bda311e6c940daf9e1d10a2b26c33e829')
GSI = (2294853632, 'dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4')
SIGNER = 'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc'
TARGETS = {
    'Lcom/android/gallery3d/exif/ExifInterface;':
        'rewriteExif(Ljava/lang/String;Ljava/util/Collection;)Z',
    'Lcom/android/gallery3d/ui/MenuExecutor$MediaOperation;':
        'run(Lcom/android/gallery3d/util/ThreadPool$JobContext;)Ljava/lang/Void;',
}


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(body):
    return hashlib.sha256(body).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode('ascii')


class DexTables:
    """Bounded table reader for one little-endian, pre-container DEX file."""
    def __init__(self, raw):
        self.raw = raw
        need(112 <= len(raw) <= 4 * 1024 * 1024, 'bounded DEX input')
        need(re.fullmatch(rb'dex\n0(?:35|37|38|39|40)\x00', raw[:8]) is not None,
             'supported standalone DEX magic')
        need(self.u32(32) == len(raw) and self.u32(36) == 112 and
             self.u32(40) == 0x12345678, 'DEX header size/length/endianness')
        need(self.u32(8) == zlib.adler32(raw[12:]) & 0xffffffff, 'DEX Adler32 checksum')
        need(raw[12:32] == hashlib.sha1(raw[32:]).digest(), 'DEX SHA1 content signature')
        self.data_size, self.data_off = self.u32(104), self.u32(108)
        need(self.data_off >= 112 and self.data_off % 4 == 0 and
             self.data_size % 4 == 0 and self.data_off + self.data_size == len(raw),
             'complete standalone DEX data range')
        self.tables = {}
        spans = []
        for name, header, width in [('strings', 56, 4), ('types', 64, 4),
                                    ('protos', 72, 12), ('fields', 80, 8),
                                    ('methods', 88, 8), ('classes', 96, 32)]:
            count, offset = self.u32(header), self.u32(header + 4)
            need(0 < count <= 100000 and offset >= 112 and offset % 4 == 0 and
                 offset + count * width <= self.data_off, 'fixed DEX table range: ' + name)
            if name in ('types', 'protos'):
                need(count <= 65535, 'DEX short table index range')
            spans.append((offset, offset + count * width))
            self.tables[name] = (count, offset, width)
        ordered = sorted(spans)
        need(all(a[1] <= b[0] for a, b in zip(ordered, ordered[1:])), 'overlapping DEX tables')
        self.string_cache = {}

    def span(self, offset, size):
        need(isinstance(offset, int) and isinstance(size, int) and 0 <= size and
             0 <= offset <= len(self.raw) and size <= len(self.raw) - offset, 'DEX read bounds')
        return self.raw[offset:offset + size]

    def u16(self, offset):
        return struct.unpack('<H', self.span(offset, 2))[0]

    def u32(self, offset):
        return struct.unpack('<I', self.span(offset, 4))[0]

    def data(self, offset, size=1, alignment=1):
        need(offset >= self.data_off and offset % alignment == 0, 'DEX data offset/alignment')
        return self.span(offset, size)

    def row(self, name, index):
        count, offset, width = self.tables[name]
        need(0 <= index < count, 'DEX ' + name + ' index')
        return offset + index * width

    def uleb(self, offset):
        start, value = offset, 0
        for shift in range(0, 35, 7):
            byte = self.data(offset)[0]
            offset += 1
            if shift == 28:
                need(byte < 16, 'DEX ULEB128 overflow')
            value |= (byte & 127) << shift
            if byte < 128:
                need(offset - start == 1 or byte != 0, 'noncanonical DEX ULEB128')
                return value, offset
        raise ValueError('unterminated DEX ULEB128')

    def string(self, index):
        if index in self.string_cache:
            return self.string_cache[index]
        offset = self.u32(self.row('strings', index))
        units, offset = self.uleb(offset)
        need(units <= 65536, 'bounded DEX string')
        decoded = []
        while True:
            first = self.data(offset)[0]
            offset += 1
            if first == 0:
                break
            if first < 128:
                code = first
            elif 0xc0 <= first <= 0xdf:
                second = self.data(offset)[0]
                offset += 1
                need(second & 0xc0 == 0x80, 'MUTF8 continuation')
                code = ((first & 31) << 6) | (second & 63)
                need(code >= 128 or (first, second) == (0xc0, 0x80), 'MUTF8 overlong pair')
            elif 0xe0 <= first <= 0xef:
                second, third = self.data(offset, 2)
                offset += 2
                need(second & 0xc0 == third & 0xc0 == 0x80, 'MUTF8 continuations')
                code = ((first & 15) << 12) | ((second & 63) << 6) | (third & 63)
                need(code >= 2048, 'MUTF8 overlong triple')
            else:
                raise ValueError('unsupported MUTF8 lead byte')
            decoded.append(code)
            need(len(decoded) <= units, 'MUTF8 declared length exceeded')
        need(len(decoded) == units, 'MUTF8 UTF16 length mismatch')
        value = b''.join(struct.pack('<H', code) for code in decoded).decode('utf-16-le', 'surrogatepass')
        self.string_cache[index] = value
        return value

    def typename(self, index):
        name = self.string(self.u32(self.row('types', index)))
        need(name and len(name) <= 4096 and '\x00' not in name, 'type descriptor bound')
        return name

    def prototype(self, index):
        offset = self.row('protos', index)
        shorty = self.string(self.u32(offset))
        returns = self.typename(self.u32(offset + 4))
        parameters = self.u32(offset + 8)
        names = []
        if parameters:
            self.data(parameters, 4, 4)
            count = self.u32(parameters)
            need(count <= 255, 'bounded method parameters')
            self.data(parameters + 4, count * 2)
            names = [self.typename(self.u16(parameters + 4 + i * 2)) for i in range(count)]
            need('V' not in names, 'void method parameter')
        shorten = lambda name: 'L' if name[0] in ('L', '[') else name
        need(shorty == shorten(returns) + ''.join(map(shorten, names)), 'method shorty mismatch')
        return '(' + ''.join(names) + ')' + returns

    def method(self, index):
        offset = self.row('methods', index)
        return (self.u16(offset), self.string(self.u32(offset + 4)) +
                self.prototype(self.u16(offset + 2)))

    def target_method(self, class_index, class_data, selector):
        self.data(class_data)
        position = class_data
        counts = []
        for unused in range(4):
            value, position = self.uleb(position)
            counts.append(value)
        need(sum(counts[:2]) <= self.tables['fields'][0] and
             sum(counts[2:]) <= self.tables['methods'][0], 'bounded class data counts')
        for count in counts[:2]:
            index = 0
            for ordinal in range(count):
                delta, position = self.uleb(position)
                flags, position = self.uleb(position)
                need(ordinal == 0 or delta > 0, 'duplicate encoded field')
                index += delta
                need(self.u16(self.row('fields', index)) == class_index, 'field class mismatch')
        found, seen = [], set()
        for count in counts[2:]:
            index = 0
            for ordinal in range(count):
                delta, position = self.uleb(position)
                flags, position = self.uleb(position)
                code, position = self.uleb(position)
                need(ordinal == 0 or delta > 0, 'duplicate encoded method delta')
                index += delta
                need(index not in seen, 'direct/virtual method duplicate')
                seen.add(index)
                owner, name = self.method(index)
                need(owner == class_index, 'method class mismatch')
                if name == selector:
                    need(flags & 1 and not flags & (0x100 | 0x400) and code != 0,
                         'selected public method must contain DEX instructions')
                    self.data(code, 16, 4)
                    registers, incoming, outgoing, tries, debug, units = struct.unpack(
                        '<HHHHII', self.span(code, 16))
                    need(incoming <= registers, 'incoming register bound')
                    if debug:
                        self.data(debug)
                    instructions = self.data(code + 16, units * 2)
                    found.append({'selector': self.typename(owner) + '->' + name,
                        'method_id': index, 'access_flags': flags, 'code_item_offset': code,
                        'registers': registers, 'incoming_registers': incoming,
                        'outgoing_registers': outgoing, 'try_items': tries,
                        'debug_info_offset': debug, 'instruction_code_units': units,
                        'instruction_bytes': len(instructions),
                        'instruction_array_sha256': sha(instructions),
                        'header_and_instruction_bytes': 16 + len(instructions),
                        'header_and_instructions_sha256': sha(self.span(code, 16 + len(instructions))),
                        'exceptions_debug_and_annotations_included_in_method_hash': False,
                        'instructions_disassembled_or_executed': False,
                        'ART_or_method_behavior_qualified': False})
        need(len(found) == 1, 'exact single selected defined method required')
        return found[0]


def inventory(dex):
    reader = DexTables(dex)
    classes, methods = [], []
    seen = set()
    for i in range(reader.tables['classes'][0]):
        row = reader.row('classes', i)
        class_index = reader.u32(row)
        name = reader.typename(class_index)
        need(name.startswith('L') and name.endswith(';') and name not in seen,
             'unique defined class descriptor')
        seen.add(name)
        classes.append(name)
        if name in TARGETS:
            methods.append(reader.target_method(class_index, reader.u32(row + 24), TARGETS[name]))
    need(len(methods) == len(TARGETS) == 2, 'both selected official class methods required')
    classes.sort()
    names = encode(classes)
    return {'schema': 'pocket4-official-gallery-static-dex-inventory-v1',
        'dex': {'bytes': len(dex), 'sha256': sha(dex), 'magic_hex': dex[:8].hex(),
                'adler32': reader.u32(8), 'content_sha1': dex[12:32].hex()},
        'table_counts': {name: row[0] for name, row in reader.tables.items()},
        'class_definition_count': len(classes), 'all_class_descriptors': classes,
        'sorted_class_list_json': {'bytes': len(names), 'sha256': sha(names)},
        'selected_methods': sorted(methods, key=lambda row: row['selector']),
        'static_class_table_complete': True, 'ART_qualified': False,
        'method_behavior_qualified': False, 'installed': False,
        'runtime_qualified': False, 'business_qualified': False, 'production_ready': False}


def negative_controls(dex):
    def repaired(raw):
        value = bytearray(raw)
        value[12:32] = hashlib.sha1(value[32:]).digest()
        struct.pack_into('<I', value, 8, zlib.adler32(value[12:]) & 0xffffffff)
        return bytes(value)
    wrong_checksum = bytearray(dex); wrong_checksum[8] ^= 1
    wrong_sha = bytearray(dex); wrong_sha[12] ^= 1
    struct.pack_into('<I', wrong_sha, 8, zlib.adler32(wrong_sha[12:]) & 0xffffffff)
    bad_range = bytearray(dex); struct.pack_into('<I', bad_range, 100, len(dex) - 4)
    duplicate = bytearray(dex)
    classes = struct.unpack_from('<I', dex, 100)[0]
    duplicate[classes + 32:classes + 36] = duplicate[classes:classes + 4]
    result = []
    for name, raw, reason in [
        ('truncated_dex', dex[:-1], 'DEX header size/length/endianness'),
        ('wrong_adler32', bytes(wrong_checksum), 'DEX Adler32 checksum'),
        ('wrong_content_sha1', bytes(wrong_sha), 'DEX SHA1 content signature'),
        ('class_table_outside_fixed_region', repaired(bad_range), 'fixed DEX table range: classes'),
        ('duplicate_class_definition', repaired(duplicate), 'unique defined class descriptor')]:
        try:
            inventory(raw)
        except ValueError as error:
            need(str(error) == reason, 'unexpected negative-control rejection: ' + name)
            result.append({'name': name, 'rejected': True, 'reason': str(error)})
        else:
            raise ValueError('negative control accepted: ' + name)
    return result


def f9(info):
    return [str(value) for value in (info.st_dev, info.st_ino, info.st_mode,
        info.st_uid, info.st_gid, info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)]


def read_pinned(path, expected, opened):
    need(path.resolve() == path, 'canonical ordinary input path')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    opened.append(fd)
    info = os.fstat(fd)
    need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() == 1000 and
         info.st_nlink == 1 and 0 < info.st_size <= 8 * 1024 * 1024, 'bounded owned input')
    raw = os.pread(fd, info.st_size + 1, 0)
    need(len(raw) == info.st_size and (expected is None or (len(raw), sha(raw)) == expected),
         'complete source size/SHA mismatch')
    identity = f9(info)
    need(identity == f9(os.fstat(fd)) == f9(path.lstat()), 'input F9 changed')
    return raw, fd, {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw), 'identity': identity}


def save(path, value):
    raw = encode(value)
    need(len(raw) <= 512 * 1024, 'bounded source evidence output')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def main():
    resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (512 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    need(os.sched_getaffinity(0) == {31}, 'single CPU31 affinity required')
    need(Path(__file__).resolve() == ROOT / 'official_dex_inventory.py', 'fixed reviewed worker path')
    opened, sources = [], []
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    began = time.monotonic()
    work = ROOT / 'work'
    work.mkdir(mode=0o700, exist_ok=False)
    try:
        source_raw, source_fd, source_pin = read_pinned(Path(__file__), None, opened)
        sources.append((Path(__file__), source_fd, source_pin))
        raw, apk_fd, apk_pin = read_pinned(APK[0], APK[1:], opened)
        sources.append((APK[0], apk_fd, apk_pin))
        receipt_raw, receipt_fd, receipt_pin = read_pinned(RECEIPT[0], RECEIPT[1:], opened)
        sources.append((RECEIPT[0], receipt_fd, receipt_pin))
        receipt = json.loads(receipt_raw)
        need(receipt['apk'] == apk_pin and receipt['package'] == 'com.android.gallery3d' and
             receipt['version_code'] == 40030 and receipt['version_name_sdk_resolved'] == '1.1.40030',
             'original source receipt APK identity')
        need(receipt['source_identity_verified'] is True and receipt['signature_verified_for_api'] == 37 and
             receipt['signer_certificate_sha256'] == [SIGNER] and
             receipt['independent_APK_crc_and_all_member_hashes_verified'] is True,
             'original API37 source qualification required')
        need((receipt['source_image']['bytes'], receipt['source_image']['sha256']) == GSI and
             receipt['original_image_path'] == '/system/product/app/Gallery2/Gallery2.apk' and
             receipt['original_image_inode'] == 3477, 'original whole GSI/member binding')
        need(all(receipt[key] is False for key in ('installed', 'runtime_qualified',
             'native_execution_qualified', 'production_ready')), 'no source receipt runtime credit')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            need(len(names) == len(set(names)) == 944 and
                 [name for name in names if re.fullmatch(r'classes(?:[2-9][0-9]*)?\.dex', name)] == ['classes.dex'],
                 'complete original singleton DEX container inventory')
            info = archive.getinfo('classes.dex')
            need(info.file_size == DEX[0] and info.flag_bits & 1 == 0, 'bounded unencrypted selected DEX')
            with archive.open(info) as member:
                dex = member.read(DEX[0] + 1)
            need((len(dex), sha(dex)) == DEX, 'complete selected official DEX pin')
        members = receipt['zip_members']
        matches = [row for row in members if row['name'] == 'classes.dex']
        need(len(matches) == 1 and (matches[0]['bytes'], matches[0]['sha256']) == DEX,
             'DEX agrees with original all-member source receipt')
        value = inventory(dex)
        controls = negative_controls(dex)
        class_ref = save(work / 'CLASS-DESCRIPTORS.json', value['all_class_descriptors'])
        inventory_ref = save(work / 'DEX-SOURCE-INVENTORY.json', value)
        bookends = []
        for path, fd, pin in sources:
            after = os.pread(fd, pin['bytes'] + 1, 0)
            need(f9(os.fstat(fd)) == f9(path.lstat()) == pin['identity'] and
                 len(after) == pin['bytes'] and sha(after) == pin['sha256'], 'final input F9/SHA mismatch')
            bookends.append({'input': pin, 'F9_and_SHA_equal': True})
        result = {'schema': 'pocket4-official-gallery-dex-source-run-v1', 'success': True,
            'state': 'OFFICIAL_DEX_SOURCE_INVENTORIED_ART_AND_BUSINESS_PENDING',
            'started_utc': started, 'finished_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'elapsed_seconds': time.monotonic() - began, 'uid': os.getuid(), 'cpu_affinity': [31],
            'address_space_limit_bytes': 128 * 1024 * 1024, 'source_worker': source_pin,
            'original_source_receipt': receipt_pin, 'APK': apk_pin,
            'full_GSI': receipt['source_image'], 'full_GSI_body_reopened_by_this_worker': False,
            'source_GSI_binding_basis': 'original complete API37 APK source receipt retained unchanged',
            'DEX': {'name': 'classes.dex', 'bytes': DEX[0], 'sha256': DEX[1]},
            'class_descriptors': class_ref, 'source_inventory': inventory_ref,
            'class_definition_count': value['class_definition_count'], 'selected_method_count': 2,
            'input_bookends': bookends, 'actual_negative_controls': controls,
            'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            'new_APK_or_DEX_copies_written': 0, 'SDK_commands': 0, 'child_processes_spawned': 0,
            'Android_actions': 0, 'user_data_reads': 0,
            'old_modified_APK_ART_or_method_credit_transferred': False,
            'ART_qualified': False, 'method_behavior_qualified': False, 'installed': False,
            'runtime_qualified': False, 'business_qualified': False, 'production_ready': False}
        result_ref = save(work / 'RESULT.json', result)
        print(json.dumps({'state': result['state'], 'result': result_ref,
                          'class_definition_count': value['class_definition_count'],
                          'source_inventory': inventory_ref, 'class_descriptors': class_ref}, sort_keys=True))
    finally:
        for fd in opened:
            os.close(fd)


if __name__ == '__main__':
    main()
