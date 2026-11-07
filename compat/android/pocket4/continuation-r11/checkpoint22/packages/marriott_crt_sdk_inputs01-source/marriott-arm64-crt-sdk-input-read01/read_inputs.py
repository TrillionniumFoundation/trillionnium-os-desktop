"""Read fixed ARM64 CRT and SDK link inputs. No build, child, device, or writes."""
import hashlib
import io
import json
import os
import re
import signal
import stat
import struct
import sys
import time
import zipfile

INPUTS = json.loads(r'''[{"role":"stl_selection_anchor","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/build/soong/cc/stl.go","maximum":65536,"expected_bytes":7171,"expected_sha256":"31b30a2c75457df7076aa588760cb2e64b73f1880e2b19092eb805e682daacea","format":"utf8"},{"role":"clang_layout_anchor","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/clang/host/linux-x86/soong/clangprebuilts.go","maximum":65536,"expected_bytes":29802,"expected_sha256":"7cc70c5060b2c1729c4406a5a27ae16774f9f80f25db1d55a37a1e170709ebef","format":"utf8"},{"role":"arm64_ndk_config_anchor","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/clang/host/linux-x86/clang-r584948b/android_libc++/ndk/aarch64/include/c++/v1/__config_site","maximum":65536,"expected_bytes":1805,"expected_sha256":"155023bfbc86f9f021ea5705822e52f13d6fca5d80ff1cce12ae279287b694c6","format":"utf8"},{"role":"ndkstubgen_source","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/build/soong/cc/ndkstubgen/__init__.py","maximum":65536,"expected_bytes":9242,"expected_sha256":"486342199742d0893480612fae142af96e5cae51d35f6d0171e29e73c7260fd8","format":"utf8"},{"role":"symbolfile_source","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/build/soong/cc/symbolfile/__init__.py","maximum":65536,"expected_bytes":15830,"expected_sha256":"f9cd1f2a3f8556bb8a063bcbc879e76bf0af1a4c2a0cb30090b6197bdda69c19","format":"utf8"},{"role":"api_levels_source","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/build/soong/android/api_levels.go","maximum":65536,"expected_bytes":18645,"expected_sha256":"39323b9e40d7aff6f482d8116c4410167345994352dfdab51ad60af00f4cbb7f","format":"utf8"},{"role":"libc_ndk_map","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/bionic/libc/libc.map.txt","maximum":65536,"expected_bytes":38678,"expected_sha256":"5831b40390f17a34536513c79735bc632aa3d3f4d81fc4ed5f5ea8ff6ed5107c","format":"utf8"},{"role":"libdl_ndk_map","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/bionic/libdl/libdl.map.txt","maximum":65536,"expected_bytes":1169,"expected_sha256":"066e6d3f7ea4a46134f53265fa29b1eaa78a2acdb8163c9d90f790e5544db80f","format":"utf8"},{"role":"libm_ndk_map","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/bionic/libm/libm.map.txt","maximum":65536,"expected_bytes":4751,"expected_sha256":"addb0e674222bb262646809f768328e27325266e122f569e80282216cf5c84c0","format":"utf8"},{"role":"liblog_ndk_map","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/system/logging/liblog/liblog.map.txt","maximum":65536,"expected_bytes":2787,"expected_sha256":"0f6863b6ac213350f96292402c0834c8fb89fa02042e960a80428304c0355019","format":"utf8"},{"role":"libz_ndk_map","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/external/zlib/libz.map.txt","maximum":65536,"expected_bytes":2493,"expected_sha256":"dc6b8f3a7f949eeb77b140fe394c2749126ce95850c14d118a41b870552d2005","format":"utf8"},{"role":"bionic_crtbegin_so_c","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/bionic/libc/arch-common/bionic/crtbegin_so.c","maximum":65536,"expected_bytes":2936,"expected_sha256":"7339e128550f8f90a254fef776c8a23b96a13190e93981cb20a588a2e6342bf3","format":"utf8"},{"role":"bionic_crtbrand_S","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/bionic/libc/arch-common/bionic/crtbrand.S","maximum":65536,"expected_bytes":1942,"expected_sha256":"27f3d6eda81ba614020871c8cc46fa0e92d9900413f38469fdb2081715cb3bb5","format":"utf8"},{"role":"bionic_crtend_so_S","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/bionic/libc/arch-common/bionic/crtend_so.S","maximum":65536,"expected_bytes":1668,"expected_sha256":"bb9e63f580f756b7cddb5a36e53c2545df7bcea681a248c647f090ee2c05ef29","format":"utf8"},{"role":"bionic___dso_handle_so_h","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/bionic/libc/arch-common/bionic/__dso_handle_so.h","maximum":65536,"expected_bytes":1930,"expected_sha256":"50b6bbb9aaa1692175e45839c0b90810a962449d0b9842960caf8119595bdc32","format":"utf8"},{"role":"bionic_atexit_h","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/bionic/libc/arch-common/bionic/atexit.h","maximum":65536,"expected_bytes":1797,"expected_sha256":"8671df24f92b375fe8ff233e88d5b55f01e91c608ee838045431444101bf70af","format":"utf8"},{"role":"bionic_pthread_atfork_h","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/bionic/libc/arch-common/bionic/pthread_atfork.h","maximum":65536,"expected_bytes":1327,"expected_sha256":"bdc11ac701a0847a51a7e93760bb0fe12389b8d25b36080f1e0d1fb7ba07e2b1","format":"utf8"},{"role":"bionic_asm_h","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/bionic/libc/private/bionic_asm.h","maximum":65536,"expected_bytes":4344,"expected_sha256":"6291935944e995c5111f913a34446fadb529b5dabf0c3d099eaffca6a550c819","format":"utf8"},{"role":"bionic_asm_arm64_h","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/bionic/libc/private/bionic_asm_arm64.h","maximum":65536,"expected_bytes":3097,"expected_sha256":"b6f66c98e064969b75e2af97481517ac5ce7fa0d89fa0052ea021fd30f1d8104","format":"utf8"},{"role":"bionic_asm_note_h","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/bionic/libc/private/bionic_asm_note.h","maximum":65536,"expected_bytes":1548,"expected_sha256":"57e505697ec2ab18ceda59187db33b7a9c829a9180a8721fea3afa24958b8cf1","format":"utf8"},{"role":"existing_soong_variables","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/android-composer-leaf-out-r14/soong/soong.variables","maximum":1048576,"format":"sdk_variables"},{"role":"existing_generated_api_map","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/android-composer-leaf-out-r14/soong/api_levels.json","maximum":65536,"format":"api_map"}]''')
RELEASED_APIS = json.loads(r'''{"G":9,"I":14,"J":16,"J-MR1":17,"J-MR2":18,"K":19,"L":21,"L-MR1":22,"M":23,"N":24,"N-MR1":25,"O":26,"O-MR1":27,"P":28,"Q":29,"R":30,"S":31,"S-V2":32,"Tiramisu":33,"UpsideDownCake":34,"VanillaIceCream":35,"Baklava":36,"CinnamonBun":37,"CANARY":10000}''')
KIND = 'p4-marriott-arm64-crt-sdk-input-read01'
MEMORY_MAX = 268435456
START = time.monotonic()
WORK_END = START + 40.0
END = START + 45.0
ACTIVE_END = WORK_END
EVENTS = []
ERRORS = []
MAX_TOTAL = 8388608
TOTAL_READ = 0

class Deadline(BaseException):
    pass

def alarm(signum, frame):
    raise Deadline('fixed input observation deadline')

def need(value, message):
    if not value:
        raise RuntimeError(message)

def tick():
    need(time.monotonic() < ACTIVE_END, 'fixed input phase deadline')

def error(stage, exc):
    item = {'stage':stage, 'type':type(exc).__name__, 'errno':getattr(exc, 'errno', None),
            'message':str(exc)[:1024]}
    ERRORS.append(item)
    return item

def take(fd, label):
    value = {'fd':fd, 'label':label, 'closed':False, 'close_attempted':False}
    EVENTS.append(value)
    return value

def close(value):
    if value is None or value['close_attempted']:
        return
    value['close_attempted'] = True
    try:
        os.close(value['fd'])
        value['closed'] = True
    except BaseException as exc:
        error('close:'+value['label'], exc)

def info(value):
    st = os.fstat(value['fd'])
    return {'device':st.st_dev,'inode':st.st_ino,'mode':st.st_mode,'nlink':st.st_nlink,
            'uid':st.st_uid,'gid':st.st_gid,'bytes':st.st_size,
            'mtime_ns':st.st_mtime_ns,'ctime_ns':st.st_ctime_ns}

def open_absolute(path, directory=False):
    tick()
    pieces = path.split('/')
    need(pieces[0] == '' and 2 <= len(pieces) <= 32 and
         all(x and x not in ('.','..') for x in pieces[1:]), 'fixed canonical path required')
    current = None
    try:
        current = take(os.open('/', os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW), 'root')
        for index, part in enumerate(pieces[1:]):
            tick()
            is_directory = directory or index < len(pieces)-2
            nxt = take(os.open(part, os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|
                        (os.O_DIRECTORY if is_directory else 0), dir_fd=current['fd']),
                       'component:'+part)
            previous = current
            current = nxt
            close(previous)
            need(previous['closed'], 'parent close failed')
        return current
    except BaseException:
        close(current)
        raise

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read_complete(value, maximum, retain=True):
    global TOTAL_READ
    tick()
    os.lseek(value['fd'], 0, os.SEEK_SET)
    chunks = [] if retain else None
    hasher = hashlib.sha256()
    count = 0
    while True:
        tick()
        part = os.read(value['fd'], min(65536, maximum+1-count))
        if not part:
            break
        count += len(part)
        need(count <= maximum, 'complete file bound')
        TOTAL_READ += len(part)
        need(TOTAL_READ <= MAX_TOTAL*2, 'total complete read bound')
        hasher.update(part)
        if retain:
            chunks.append(part)
    return (b''.join(chunks) if retain else None), count, hasher.hexdigest()

def archive_facts(body):
    if body[:8] == b'!<thin>\n':
        return {'format':'thin_archive','external_members_followed':False,
                'architecture_qualified':False}
    need(body[:8] == b'!<arch>\n', 'fixed library is not a regular ar archive')
    offset = 8
    members = 0
    counts = {}
    bitcode = 0
    other = 0
    while offset < len(body):
        tick()
        need(offset+60 <= len(body), 'truncated ar member header')
        head = body[offset:offset+60]
        need(head[58:60] == b'\x60\n', 'invalid ar member trailer')
        raw_size = head[48:58].strip()
        need(raw_size and all(48 <= x <= 57 for x in raw_size), 'invalid ar member size')
        size = int(raw_size)
        begin = offset+60
        end = begin+size
        need(end <= len(body), 'ar member beyond file')
        name = head[:16].strip()
        if name not in (b'/', b'//', b'/SYM64/'):
            if name.startswith(b'#1/'):
                suffix = name[3:]
                need(suffix and all(48 <= x <= 57 for x in suffix), 'invalid BSD ar name size')
                begin += int(suffix)
                need(begin <= end, 'BSD ar name exceeds member')
            members += 1
            need(members <= 32768, 'ar member count bound')
            prefix = body[begin:min(begin+20, end)]
            if len(prefix) >= 20 and prefix[:4] == b'\x7fELF':
                need(prefix[4] in (1,2) and prefix[5] in (1,2), 'ELF member encoding')
                endian = '<' if prefix[5] == 1 else '>'
                elf_type, machine = struct.unpack_from(endian+'HH', prefix, 16)
                label = str(machine)+':'+str(elf_type)+':'+str(prefix[4])+':'+str(prefix[5])
                counts[label] = counts.get(label, 0)+1
            elif prefix[:4] in (b'BC\xc0\xde', b'\xde\xc0\x17\x0b'):
                bitcode += 1
            else:
                other += 1
        offset = end+(size&1)
        need(offset <= len(body), 'ar padding beyond file')
    need(offset == len(body) and members > 0, 'ar complete member set')
    return {'format':'regular_archive','members':members,'ELF_machine_type_class_data_counts':counts,
            'LLVM_bitcode_members':bitcode,'other_members':other,
            'all_members_ELF64_AARCH64_REL_LSB':counts == {'183:1:2:1':members},
            'architecture_qualified':counts == {'183:1:2:1':members},
            'external_members_followed':False}

def zip_facts(body, required):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        entries = archive.infolist()
        need(0 < len(entries) <= 32768, 'fixed jar entry bound')
        names = [x.filename for x in entries]
        need(len(names) == len(set(names)), 'duplicate fixed jar entry')
        selected = {}
        for name in required:
            row = {'present':name in names}
            if row['present']:
                item = archive.getinfo(name)
                need(not item.is_dir() and item.file_size <= 1048576 and
                     item.compress_size <= len(body) and not (item.flag_bits & 1),
                     'required class entry shape')
                with archive.open(item, 'r') as member:
                    data = member.read(1048577)
                need(len(data) == item.file_size and data[:4] == b'\xca\xfe\xba\xbe',
                     'required Java class bytes')
                row.update(bytes=len(data),sha256=digest(data))
            selected[name] = row
        return {'format':'zip','entries':len(entries),'required_classes':selected,
                'all_required_classes_present':all(x['present'] for x in selected.values()),
                'extracted_files':0,'class_bodies_exported':False}


def strict_configuration_json(body):
    def unique_pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, 'duplicate fixed configuration JSON key')
            value[key] = item
        return value
    def reject_constant(_):
        raise RuntimeError('nonfinite fixed configuration JSON value')
    value = json.loads(body.decode('utf-8', 'strict'),
                       object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    need(type(value) is dict, 'fixed configuration object required')
    return value

def sdk_configuration_facts(body, kind):
    value = strict_configuration_json(body)
    def public_name(name):
        return type(name) is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,63}', name)
    if kind == 'api_map':
        need(0 < len(value) <= 128 and
             all(public_name(k) and type(v) is int and 0 < v <= 10000
                 for k, v in value.items()), 'fixed generated API map shape')
        return {'format':kind,'api_levels':value,'source_body_exported':False}
    need(kind == 'sdk_variables', 'unsupported SDK configuration format')
    sdk = value.get('Platform_sdk_version')
    need(type(sdk) is int and 21 <= sdk <= 10000,
         'fixed Platform_sdk_version integer required')
    key = 'Platform_version_all_preview_codenames'
    previews = value.get(key)
    need(previews is None or
         (type(previews) is list and len(previews) <= 64 and
          all(public_name(x) for x in previews) and len(previews) == len(set(previews))),
         'fixed preview codenames shape')
    selected = {'Platform_sdk_version':sdk}
    for field in ('Platform_sdk_final','Platform_sdk_codename',key):
        if field in value:
            selected[field] = value[field]
    if 'Platform_sdk_final' in selected:
        need(type(selected['Platform_sdk_final']) is bool,
             'fixed Platform_sdk_final boolean required')
    if 'Platform_sdk_codename' in selected:
        need(public_name(selected['Platform_sdk_codename']),
             'fixed Platform_sdk_codename shape')
    return {'format':kind,'public_values':selected,
            'preview_field_present':key in value,
            'unselected_field_count':len(value)-len(selected),
            'source_body_exported':False,'unselected_fields_exported':False}

def join_sdk_configuration(rows):
    by_role = {row['role']:row for row in rows}
    need(len(by_role) == len(INPUTS) and all(row['complete'] for row in rows),
         'all fixed SDK source and configuration inputs required')
    variables = by_role['existing_soong_variables']['format_facts']['public_values']
    actual_map = by_role['existing_generated_api_map']['format_facts']['api_levels']
    # A missing or JSON-null Go []string field is nil; the original Soong range
    # adds no previews. Record presence above rather than inventing a codename.
    previews = variables.get('Platform_version_all_preview_codenames')
    expected = dict(RELEASED_APIS)
    for index, codename in enumerate([] if previews is None else previews):
        expected[codename] = 9000 + index
    need(actual_map == expected,
         'fixed generated API map differs from original Soong source and variables')
    return {'qualified_for_fixed_build_input_binding':True,
            'Platform_sdk_version_observed':variables['Platform_sdk_version'],
            'CRT_brand_define_must_use_this_observed_value':True,
            'NDK_current_interface_api_from_original_generator':10000,
            'compiler_current_target_preserved':'aarch64-linux-android10000',
            'generated_api_map_matches_original_algorithm':True,
            'input_sha256':{name:by_role[name]['sha256'] for name in
                ('api_levels_source','symbolfile_source','existing_soong_variables',
                 'existing_generated_api_map')},
            'SDK_values_modified':False,'link_inputs_generated':False,
            'Android_or_Main_SDK_observed':False,'runtime_libraries_qualified':False}

def observe(spec):
    held = None
    named = None
    body = None
    row = {'role':spec['role'],'path':spec['path'],'complete':False,'full_reads':0,
           'prior_expected_bytes':spec.get('expected_bytes'),
           'prior_expected_sha256':spec.get('expected_sha256'),
           'expected_is_prior_actual':spec['role'].endswith('_anchor'),
           'error':None}
    try:
        held = open_absolute(spec['path'])
        before = info(held)
        row['before'] = before
        need(stat.S_ISREG(before['mode']) and 0 < before['bytes'] <= spec['maximum'],
             'bounded regular public input required')
        body, count, sha = read_complete(held, spec['maximum'])
        row.update(bytes=count,sha256=sha,full_reads=1)
        need(count == before['bytes'] and info(held) == before, 'first held read changed')
        # A second complete independent named open proves the same current file bytes.
        named = open_absolute(spec['path'])
        row['named_before'] = info(named)
        need(row['named_before'] == before, 'named input identity changed')
        _, count2, sha2 = read_complete(named, spec['maximum'], False)
        row['named_after'] = info(named)
        row['held_after'] = info(held)
        row['full_reads'] = 2
        need(count2 == count and sha2 == sha and row['named_after'] == before and
             row['held_after'] == before, 'second complete input read differs')
        row['whole_input_and_identity_unchanged'] = True
        row['expected_matches'] = (spec.get('expected_bytes', count) == count and
                                   spec.get('expected_sha256', sha) == sha)
        need(row['expected_matches'], 'fixed prior/reference content differs')
        if spec['format'] == 'utf8':
            text = body.decode('utf-8', 'strict')
            row['format_facts'] = {'format':'utf8','utf8_bytes':len(text.encode()),
                                   'source_body_exported':False}
        elif spec['format'] in ('sdk_variables','api_map'):
            row['format_facts'] = sdk_configuration_facts(body, spec['format'])
        elif spec['format'] == 'archive':
            row['format_facts'] = archive_facts(body)
        else:
            need(spec['format'] == 'zip', 'unsupported fixed input format')
            row['format_facts'] = zip_facts(body, spec['required_classes'])
            need(row['format_facts']['all_required_classes_present'],
                 'required official class missing from fixed jar')
        row['complete'] = True
    except BaseException as exc:
        row['error'] = error('input:'+spec['role'], exc)
    finally:
        body = None
        close(named)
        close(held)
    row['owned_leaf_FDs_closed'] = all(x is None or x['closed'] for x in (held, named))
    row['complete'] = row['complete'] and row['owned_leaf_FDs_closed']
    return row

def small_self(path, maximum=262144):
    tick()
    event = take(os.open(path, os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC), 'self-metadata')
    try:
        parts, count = [], 0
        while True:
            tick()
            part = os.read(event['fd'], min(8192, maximum+1-count))
            if not part:
                break
            count += len(part)
            need(count <= maximum, 'self metadata bound')
            parts.append(part)
        return b''.join(parts).decode('ascii')
    finally:
        close(event)

def at_text(directory, name):
    tick()
    event = take(os.open(name, os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,
                        dir_fd=directory['fd']), 'own-resource:'+name)
    try:
        parts, count = [], 0
        while True:
            tick()
            part = os.read(event['fd'], min(8192, 32769-count))
            if not part:
                break
            count += len(part)
            need(count <= 32768, 'resource leaf bound')
            parts.append(part)
        return b''.join(parts).decode('ascii').strip()
    finally:
        close(event)

def resource_snapshot():
    membership = small_self('/proc/self/cgroup', 4096)
    need(membership.startswith('0::/') and membership.endswith('\n') and
         membership.count('\n') == 1, 'own unified cgroup required')
    relative = membership[4:-1]
    need(relative and all(x not in ('','.','..') for x in relative.split('/')) and
         any(x.startswith('hepta-runtime-job-') and x.endswith('.service')
             for x in relative.split('/')), 'own job cgroup required')
    mounts = []
    for line in small_self('/proc/self/mountinfo').splitlines():
        fields = line.split()
        if len(fields)>6 and fields[4] == '/sys/fs/cgroup':
            pos = fields.index('-')
            need(fields[3] == '/' and fields[pos+1] == 'cgroup2', 'own cgroup mount type')
            mounts.append((fields[0],fields[1],fields[2],fields[3],fields[4],fields[pos+1]))
    need(len(mounts) == 1, 'unique own cgroup mount required')
    event = None
    try:
        event = open_absolute('/sys/fs/cgroup/'+relative, True)
        meta = info(event)
        need(mounts[0][2] == str(os.major(meta['device']))+':'+str(os.minor(meta['device'])),
             'held own cgroup device mismatch')
        limits = {x:at_text(event,x) for x in
                  ('memory.max','memory.high','memory.swap.max','cpu.max','pids.max')}
        cpu = limits['cpu.max'].split()
        need(limits['memory.max'] == str(MEMORY_MAX) and len(cpu) == 2 and
             cpu[0].isdecimal() and cpu[1].isdecimal() and int(cpu[0]) == int(cpu[1]) > 0,
             'own requested memory/CPU differ')
        counters = {}
        for line in at_text(event,'memory.events').splitlines():
            k, v = line.split()
            need(k not in counters and v.isdecimal(), 'memory events shape')
            counters[k] = int(v)
        need(all(k in counters for k in ('max','oom','oom_kill')) and
             all(counters.get(k,0)==0 for k in ('max','oom','oom_kill','oom_group_kill')),
             'own memory limit or OOM event')
        values = {x:at_text(event,x) for x in
                  ('memory.current','memory.peak','memory.swap.current','cgroup.procs')}
        need(all(values[k].isdecimal() for k in ('memory.current','memory.peak','memory.swap.current')) and
             int(values['memory.current']) <= MEMORY_MAX and int(values['memory.peak']) <= MEMORY_MAX,
             'own bounded memory observation differs')
        need(str(os.getpid()) in values['cgroup.procs'].splitlines(), 'own PID domain')
        need(small_self('/proc/self/task/'+str(os.getpid())+'/children',4096).strip() == '',
             'reader is not childless')
        return {'membership':membership,'mount':mounts[0],
                'identity':[meta[k] for k in ('device','inode','mode','uid','gid')],
                'limits':limits,'memory_events':counters,'values':values,
                'namespace':{n:[os.stat('/proc/self/ns/'+n).st_dev,os.stat('/proc/self/ns/'+n).st_ino]
                             for n in ('mnt','cgroup')}}
    finally:
        close(event)

def main():
    global ACTIVE_END
    result = {'kind':KIND,'schema':1,'collection_complete':False,'inputs':[],
              'Main_actions':0,'Android_actions':0,'children_started':0,'files_written':0,
              'directory_enumerations':0,'network_calls':0,'tool_or_library_executions':0,
              'build_or_runtime_qualification_asserted':False,
              'fixed_candidate_absence_has_no_fallback':True,
              'input_binary_bodies_exported':False}
    old_handler = signal.signal(signal.SIGALRM,alarm)
    old_timer = signal.setitimer(signal.ITIMER_REAL,45.0)
    try:
        need(old_timer == (0.0,0.0), 'unexpected inherited alarm')
        need(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==1000,
             'ordinary UID/GID1000 required')
        result['resource_before'] = resource_snapshot()
        for index, spec in enumerate(INPUTS):
            tick()
            row = observe(spec)
            result['inputs'].append(row)
            if index < 3 and not row['complete']:
                raise RuntimeError('prior actual input anchor failed')
            if time.monotonic() >= WORK_END:
                raise Deadline('fixed input work deadline')
        if all(row['complete'] for row in result['inputs']):
            result['sdk_configuration_join'] = join_sdk_configuration(result['inputs'])
    except BaseException as exc:
        error('collection',exc)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0.0)
        ACTIVE_END = END
        if 'resource_before' in result:
            try:
                result['resource_after'] = resource_snapshot()
                before = result['resource_before']
                after = result['resource_after']
                need(all(before[k] == after[k] for k in
                     ('membership','mount','identity','limits','namespace')),
                     'own resource identity or limits changed')
                result['own_resource_interval_qualified'] = True
            except BaseException as exc:
                error('resource_final',exc)
        for value in reversed(EVENTS):
            close(value)
        signal.signal(signal.SIGALRM,old_handler)
    result['fd_events'] = EVENTS
    result['all_tracked_owned_FDs_closed'] = all(x['closed'] for x in EVENTS)
    result['global_ambient_FD_equality_asserted'] = False
    result['control_deadline_met'] = time.monotonic() <= END
    result['elapsed_seconds'] = time.monotonic()-START
    result['complete_bytes_read'] = TOTAL_READ
    result['errors'] = ERRORS
    result['first_error'] = ERRORS[0] if ERRORS else None
    result['collection_complete'] = bool(not ERRORS and len(result['inputs']) == len(INPUTS) and
        all(x['complete'] for x in result['inputs']) and result['all_tracked_owned_FDs_closed'] and
        result['control_deadline_met'] and result.get('own_resource_interval_qualified') and
        result.get('sdk_configuration_join',{}).get('qualified_for_fixed_build_input_binding') is True)
    raw = (json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode()
    need(len(raw) <= 1048576,'fixed input metadata report bound')
    sys.stdout.buffer.write(raw)
    return 0 if result['collection_complete'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
