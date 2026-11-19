"""Parse actual Gallery oatdump output without a historical byte-offset contract.

All class statuses come from one unfiltered --list-classes observation. The two
method windows come from two separate, fixed class-filter observations of the
same held oat/vdex/APK. Historical output can test this parser, never qualify a
current runtime. This module performs no I/O at import.
"""
import hashlib
import io
import re

APK_LOCATION = '/product/app/Gallery2/Gallery2.apk'
CLASS_COUNT = 2144
TABLE_SLOTS = 4096
MAX_SOURCE = 96 * 1024 * 1024
MAX_LINE = 262144
MAX_PROJECTION = 16 * 1024 * 1024
MAX_TARGET_CLASS = 2 * 1024 * 1024
TARGETS = {
    'Lcom/android/gallery3d/exif/ExifInterface;':
        r'boolean com\.android\.gallery3d\.exif\.ExifInterface\.rewriteExif\(java\.lang\.String,\s*java\.util\.Collection\)',
    'Lcom/android/gallery3d/ui/MenuExecutor$MediaOperation;':
        r'java\.lang\.Void com\.android\.gallery3d\.ui\.MenuExecutor\$MediaOperation\.run\(com\.android\.gallery3d\.util\.ThreadPool\$JobContext\)',
}
HEADER = re.compile(r'^(\d+): (L[^;\r\n]+;) \(offset=0x([0-9a-f]+)\) '
                    r'\(type_idx=(\d+)\) \(([^)\r\n]+)\) \(([^)\r\n]+)\)$')
BARE_HEADER = re.compile(r'^\d+: L')
TABLE_ROW = re.compile(r'^(\d+): (empty|L[^;\r\n]+;)$')
TABLE_START = re.compile(r'^type-table: 0x([0-9a-f]+)\.\.0x([0-9a-f]+)$')
METHOD = re.compile(r'^\s*\d+: ([^\r\n]+) \(dex_method_idx=\d+\)$', re.M)


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def expected_classes(names):
    need(type(names) is list and len(names) == len(set(names)) == CLASS_COUNT
         and all(type(n) is str and re.fullmatch(r'L[^;\r\n]+;', n) for n in names)
         and set(TARGETS) <= set(names), 'EXACT_2144_DEX_CLASS_NAMES_REQUIRED')
    return set(names)


def scan(stream, names, *, expected_checksum=None):
    """Consume every byte; validate the complete type table independently.

    The grammar follows the pinned current oatdump source: OatDexFile metadata,
    a full TypeLookupTable, then the selected class-status/method blocks. It
    never drops an unclassified line that resembles a class-status header.
    """
    expected = expected_classes(names)
    digest = hashlib.sha256(); size = 0; line_count = 0
    table_digest = hashlib.sha256(); table_rows = []; occupied = set(); empty = 0
    table_state = 0; table_count = 0; table_offsets = None; table_bytes = 0
    prefix = []; oat_sections = 0; headers = []; by_name = {}; unparsed = []
    target_blocks = {name: [] for name in TARGETS}; current = None; body = []
    body_size = 0; body_start = None; projection_size = 0

    def finish(end):
        nonlocal current, body, body_size, body_start
        if current is not None:
            raw = b''.join(body)
            target_blocks[current].append({'descriptor': current, 'start_byte': body_start,
                'end_byte': end, 'bytes': len(raw), 'sha256': sha(raw), 'raw': raw})
        current = None; body = []; body_size = 0; body_start = None

    while True:
        raw = stream.readline(MAX_LINE + 1)
        if not raw:
            break
        need(type(raw) is bytes and len(raw) <= MAX_LINE, 'OAT_LINE_BOUND')
        start = size; size += len(raw); line_count += 1
        need(size <= MAX_SOURCE, 'OAT_COMPLETE_SOURCE_BOUND')
        digest.update(raw)
        text = raw.decode('utf-8', 'strict')
        plain = text[:-1] if text.endswith('\n') else text
        need('\r' not in plain and '\0' not in plain, 'OAT_LINE_ENCODING')
        if plain == 'OatDexFile:':
            oat_sections += 1
            need(oat_sections == 1 and table_state == 0 and not headers,
                 'EXACT_SINGLE_DEX_SECTION_REQUIRED')
            prefix = [plain]
        elif prefix and table_state == 0:
            prefix.append(plain)
            need(len(prefix) <= 5, 'EXACT_OAT_DEX_METADATA_PREFIX')
            if len(prefix) == 2:
                need(plain == 'location: ' + APK_LOCATION, 'CANDIDATE_DEX_LOCATION')
            elif len(prefix) == 3:
                match = re.fullmatch(r'checksum: 0x([0-9a-f]+)', plain)
                need(match is not None and (expected_checksum is None
                     or int(match[1], 16) == expected_checksum), 'CANDIDATE_DEX_CHECKSUM')
            elif len(prefix) == 4:
                need(re.fullmatch(r'dex-file: 0x[0-9a-f]+\.\.0x[0-9a-f]+', plain)
                     is not None, 'COPIED_DEX_RANGE_REQUIRED')
            elif len(prefix) == 5:
                match = TABLE_START.fullmatch(plain)
                need(match is not None, 'EXACT_TYPE_TABLE_START')
                table_offsets = [int(match[1], 16), int(match[2], 16)]
                need(table_offsets[1] - table_offsets[0] + 1 == TABLE_SLOTS * 8,
                     'EXACT_CURRENT_TYPE_TABLE_STORAGE_SIZE')
                table_state = 1; table_count += 1
                table_digest.update(raw); table_bytes += len(raw)
                continue
        elif TABLE_START.fullmatch(plain):
            need(False, 'UNEXPECTED_OR_DUPLICATE_TYPE_TABLE')

        if table_state == 1:
            match = TABLE_ROW.fullmatch(plain)
            need(match is not None and int(match[1]) == len(table_rows),
                 'COMPLETE_CONTIGUOUS_TYPE_TABLE_SLOTS')
            descriptor = None if match[2] == 'empty' else match[2]
            if descriptor is None:
                empty += 1
            else:
                need(descriptor in expected and descriptor not in occupied,
                     'TYPE_TABLE_CLASS_SET_OR_DUPLICATE')
                occupied.add(descriptor)
            table_rows.append(descriptor); table_digest.update(raw); table_bytes += len(raw)
            need(len(table_rows) <= TABLE_SLOTS, 'TYPE_TABLE_SLOT_BOUND')
            if len(table_rows) == TABLE_SLOTS:
                need(occupied == expected and empty == TABLE_SLOTS - CLASS_COUNT,
                     'COMPLETE_TYPE_TABLE_DESCRIPTOR_SET')
                table_state = 2
            continue

        hit = HEADER.fullmatch(plain)
        candidate = BARE_HEADER.match(plain) is not None
        if hit:
            need(table_state == 2, 'CLASS_STATUS_BEFORE_COMPLETE_TYPE_TABLE')
            finish(start)
            row = {'class_def_index': int(hit[1]), 'descriptor': hit[2], 'offset': hit[3],
                'type_idx': int(hit[4]), 'status': hit[5], 'compilation_kind': hit[6],
                'header': plain, 'line': line_count, 'start_byte': start, 'end_byte': size}
            need(len(headers) < 8192 and row['class_def_index'] < CLASS_COUNT,
                 'CLASS_STATUS_HEADER_BOUND')
            headers.append(row); by_name.setdefault(hit[2], []).append(row)
            projection_size += len(raw)
            if hit[2] in TARGETS:
                current = hit[2]; body_start = start; body = [raw]; body_size = len(raw)
        elif candidate:
            finish(start)
            need(len(unparsed) < 8192 and len(plain) <= 2048, 'UNCLASSIFIED_HEADER_BOUND')
            unparsed.append({'line': line_count, 'start_byte': start, 'text': plain})
        elif current is not None:
            body_size += len(raw); projection_size += len(raw)
            need(body_size <= MAX_TARGET_CLASS, 'COMPLETE_TARGET_CLASS_BOUND')
            body.append(raw)
        need(projection_size <= MAX_PROJECTION, 'STATUS_AND_TARGET_PROJECTION_BOUND')

    finish(size)
    need(oat_sections == table_count == 1 and table_state == 2 and headers,
         'COMPLETE_SINGLE_OAT_DEX_OUTPUT_REQUIRED')
    return {'source_bytes': size, 'source_sha256': digest.hexdigest(), 'source_lines': line_count,
        'oat_dex_prefix': prefix, 'type_table': {'slots': len(table_rows),
            'occupied_descriptors': len(occupied), 'empty_slots': empty,
            'exact_expected_descriptor_set': occupied == expected, 'offsets': table_offsets,
            'bytes': table_bytes, 'sha256': table_digest.hexdigest()},
        'headers': headers, 'by_name': by_name, 'unparsed_header_candidates': unparsed,
        'target_blocks': target_blocks, 'all_bytes_scanned': True}


def admit_all_classes(observation, names):
    expected = expected_classes(names); headers = observation['headers']
    actual = set(observation['by_name'])
    need(not observation['unparsed_header_candidates'], 'UNCLASSIFIED_CLASS_STATUS_HEADER')
    need(actual == expected and len(headers) == CLASS_COUNT
         and all(len(rows) == 1 for rows in observation['by_name'].values()),
         'ALL_2144_UNIQUE_CLASS_STATUSES_REQUIRED')
    need([row['class_def_index'] for row in headers] == list(range(CLASS_COUNT)),
         'ALL_CLASS_DEFINITION_INDICES_IN_ORDER_REQUIRED')
    need(all(row['status'] == 'Verified' for row in headers),
         'ALL_2144_STORED_CLASS_STATUSES_MUST_BE_VERIFIED')
    return {'expected_classes': CLASS_COUNT, 'parsed_classes': len(headers),
        'class_definition_indices_exact': True, 'all_stored_statuses_verified': True,
        'exact_class_set': True, 'unparsed_class_header_candidates': [],
        'all_output_bytes_scanned': True, 'source_bytes': observation['source_bytes'],
        'source_sha256': observation['source_sha256'], 'type_table': observation['type_table']}


def method_window(observation, descriptor, all_observation):
    need(descriptor in TARGETS and not observation['unparsed_header_candidates'],
         'EXACT_TARGET_METHOD_OBSERVATION')
    for name, rows in observation['by_name'].items():
        need(name in all_observation['by_name'] and len(rows) == 1,
             'FILTERED_OUTPUT_CLASS_NOT_IN_COMPLETE_OBSERVATION')
        need(rows[0]['header'] == all_observation['by_name'][name][0]['header'],
             'FILTERED_CLASS_STATUS_OR_OFFSET_CHANGED')
    rows = observation['target_blocks'][descriptor]
    need(len(rows) == 1, 'EXACT_SINGLE_COMPLETE_TARGET_CLASS')
    block = rows[0]; text = block['raw'].decode('utf-8', 'strict')
    header = observation['by_name'][descriptor][0]
    need(header['status'] == 'Verified', 'TARGET_CLASS_NOT_VERIFIED')
    methods = list(METHOD.finditer(text))
    chosen = [m for m in methods if re.fullmatch(TARGETS[descriptor], m[1])]
    need(len(chosen) == 1, 'EXACT_SINGLE_MODIFIED_METHOD_REQUIRED')
    method = chosen[0]
    end = next((m.start() for m in methods if m.start() > method.start()), len(text))
    window = (header['header'] + '\n' + text[method.start():end]).encode()
    need(0 < len(window) <= 131072, 'COMPLETE_METHOD_WINDOW_BOUND')
    return {'descriptor': descriptor, 'class_status': 'Verified', 'complete_window': True,
        'class_header_occurrences': 1, 'method_header_occurrences': 1,
        'window_bytes': len(window), 'window_sha256': sha(window),
        'source_class': {k: v for k, v in block.items() if k != 'raw'},
        'source_output_sha256': observation['source_sha256']}, window


def prove_parts(class_output, method_outputs, names, *, checksum):
    need(type(class_output) is bytes and len(class_output) <= MAX_PROJECTION
         and type(method_outputs) is dict and set(method_outputs) == set(TARGETS)
         and all(type(raw) is bytes and len(raw) <= MAX_PROJECTION
                 for raw in method_outputs.values()), 'BOUNDED_THREE_ACTUAL_OUTPUTS_REQUIRED')
    all_obs = scan(io.BytesIO(class_output), names, expected_checksum=checksum)
    all_proof = admit_all_classes(all_obs, names); windows = {}; methods = {}
    for descriptor, raw in method_outputs.items():
        obs = scan(io.BytesIO(raw), names, expected_checksum=checksum)
        proof, window = method_window(obs, descriptor, all_obs)
        methods[descriptor] = proof; windows[descriptor] = window
    return {'schema': 'pocket4-gallery-qpr1-art-class-status-v2',
        'complete_unfiltered_class_status': all_proof, 'modified_methods': methods,
        'all_2144_stored_statuses_verified': True,
        'both_modified_method_windows_verified': True,
        'same_oat_vdex_apk_identity_must_be_proved_by_caller': True,
        'Main_runtime_or_install_credit_from_parser_alone': False}, windows
