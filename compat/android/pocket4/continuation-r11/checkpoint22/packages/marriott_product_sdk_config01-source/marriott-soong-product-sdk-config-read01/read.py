"""Read fixed Soong product naming and one derived SDK configuration. No build or actions."""
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

INPUTS = json.loads(r'''[{"role":"api_levels_source","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/build/soong/android/api_levels.go","maximum":65536,"expected_bytes":18645,"expected_sha256":"39323b9e40d7aff6f482d8116c4410167345994352dfdab51ad60af00f4cbb7f","format":"utf8"},{"role":"symbolfile_source","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/build/soong/cc/symbolfile/__init__.py","maximum":65536,"expected_bytes":15830,"expected_sha256":"f9cd1f2a3f8556bb8a063bcbc879e76bf0af1a4c2a0cb30090b6197bdda69c19","format":"utf8"},{"role":"existing_generated_api_map","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/android-composer-leaf-out-r14/soong/api_levels.json","maximum":65536,"format":"api_map","expected_bytes":261,"expected_sha256":"57eb77fcc1525ed675f07601cce51fe9d9524271b3c6c6b53429a9beabdda87b"},{"role":"soong_ui_config","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/build/soong/ui/build/config.go","maximum":131072,"expected_bytes":68765,"expected_sha256":"b2719ca6a5335ac78af0f37e8a5f966c52932cd9673796929c230bb5c9bb99d5","format":"utf8"},{"role":"soong_ui_run","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/build/soong/ui/build/soong.go","maximum":131072,"expected_bytes":31627,"expected_sha256":"ab745182f4fba6ab4fbd1cea6fc4943b78e588b4187dfc735cd28826bbaa7027","format":"utf8"},{"role":"soong_environment_boolean","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/build/soong/ui/build/environment.go","maximum":131072,"expected_bytes":6244,"expected_sha256":"adee8346f56cbb9a8044444ee54224f50c3be37cdc14fe2bd13e66c439763f2d","format":"utf8"},{"role":"soong_environment_encoding","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/build/soong/shared/env.go","maximum":131072,"expected_bytes":3511,"expected_sha256":"f699e7238a9558548fbdf35df3d3b680ae482156e2273a0fd3112b14f571a701","format":"utf8"},{"role":"existing_available_environment","path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/android-composer-leaf-out-r14/soong/soong.environment.available","maximum":1048576,"format":"soong_available_env"}]''')
SOONG_DIR = "/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/android-composer-leaf-out-r14/soong"
ORIGINAL_SDK22 = {'bytes':79928,'sha256':'f952b570b665438b367f78fbef0a17232d78ced69463832b9d12b1316a700a83','job_id':'1a1b19b46a3-fc05-79d7','terminal_exit_code':1,'qualified_as_whole':False}
RELEASED_APIS = json.loads(r'''{"G":9,"I":14,"J":16,"J-MR1":17,"J-MR2":18,"K":19,"L":21,"L-MR1":22,"M":23,"N":24,"N-MR1":25,"O":26,"O-MR1":27,"P":28,"Q":29,"R":30,"S":31,"S-V2":32,"Tiramisu":33,"UpsideDownCake":34,"VanillaIceCream":35,"Baklava":36,"CinnamonBun":37,"CANARY":10000}''')
KIND = 'p4-marriott-soong-product-sdk-config-read01'
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

def available_environment_facts(body):
    # shared.EnvFileContents emits a sorted array of {Key,Value} strings.
    # Parse only in memory. No unselected key, value, or original body is emitted.
    def unique_pairs(items):
        value={}
        for key,item in items:
            need(key not in value,'duplicate environment JSON object key')
            value[key]=item
        return value
    def reject_constant(_):
        raise RuntimeError('nonfinite environment JSON value')
    records=json.loads(body.decode('utf-8','strict'),object_pairs_hook=unique_pairs,
                       parse_constant=reject_constant)
    need(type(records) is list and 0<len(records)<=4096,'fixed environment entry bound')
    names=[]
    selected={}
    for row in records:
        need(type(row) is dict and set(row)=={'Key','Value'} and
             type(row['Key']) is str and type(row['Value']) is str and
             0<len(row['Key'])<=256 and len(row['Value'].encode())<=65536,
             'fixed environment record shape')
        names.append(row['Key'])
        if row['Key'] in ('TARGET_PRODUCT','EMMA_INSTRUMENT'):
            selected[row['Key']]=row['Value']
    need(names==sorted(set(names)),'fixed environment sorted unique keys required')
    product=selected.get('TARGET_PRODUCT')
    need(type(product) is str and
         re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}',product) is not None,
         'one public TARGET_PRODUCT grammar required')
    coverage=selected.get('EMMA_INSTRUMENT') in ('1','y','yes','on','true')
    emma=selected.get('EMMA_INSTRUMENT')
    emma_projection={'present':emma is not None,'effective_true':coverage}
    if emma is not None:
        emma_projection.update(bytes=len(emma.encode()),sha256=digest(emma.encode()))
        if emma in ('','1','y','yes','on','true','0','n','no','off','false'):
            emma_projection['public_boolean_literal']=emma
    basename='soong.'+product+('.coverage' if coverage else '')+'.variables'
    return {'format':'soong_available_env','TARGET_PRODUCT':product,
            'EMMA_INSTRUMENT':emma_projection,'derived_basename':basename,
            'total_entries':len(records),'unselected_values_exported':False,
            'unselected_names_exported':False,'source_body_exported':False}


def product_configuration_facts(body):
    facts=sdk_configuration_facts(body,'sdk_variables')
    value=strict_configuration_json(body)
    product=value.get('DeviceProduct')
    suffix=value.get('Make_suffix')
    need(type(product) is str and
         re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}',product) is not None,
         'actual DeviceProduct grammar required')
    need(type(suffix) is str and len(suffix)<=139,'actual Make_suffix shape required')
    # These two selected public fields must equal the observed filename producer.
    facts['public_product_identity']={'DeviceProduct':product,'Make_suffix':suffix}
    facts['unselected_field_count']-=2
    return facts


def join_sdk_configuration(rows):
    by_role = {row['role']:row for row in rows}
    need(len(by_role) == len(INPUTS)+1 and all(row['complete'] for row in rows),
         'all fixed SDK source and configuration inputs required')
    environment=by_role['existing_available_environment']['format_facts']
    product=environment['TARGET_PRODUCT']
    suffix='.coverage' if environment['EMMA_INSTRUMENT']['effective_true'] else ''
    variable=by_role['existing_soong_variables']
    need(variable['path']==SOONG_DIR+'/soong.'+product+suffix+'.variables',
         'actual single product configuration path differs')
    need(variable['format_facts']['public_product_identity']==
         {'DeviceProduct':product,'Make_suffix':'-'+product+suffix},
         'actual configuration product/coverage does not match observed producer')
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
            'product_path_derived_from_fixed_observed_environment':True,
            'observed_product':product,'observed_coverage_suffix':suffix,
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
        need(stat.S_ISREG(before['mode']) and before['nlink']==1 and
             0 < before['bytes'] <= spec['maximum'],
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
        elif spec['format']=='soong_available_env':
            row['format_facts']=available_environment_facts(body)
        elif spec['format']=='product_sdk_variables':
            row['format_facts']=product_configuration_facts(body)
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
              'input_binary_bodies_exported':False,
              'original_failed_sdk22':ORIGINAL_SDK22,
              'derived_candidate_read_attempts':0,'candidate_fallbacks':0}
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
            if not row['complete']:
                raise RuntimeError('fixed producer/configuration prerequisite failed')
            if time.monotonic() >= WORK_END:
                raise Deadline('fixed input work deadline')
        environment=result['inputs'][-1]['format_facts']
        basename=environment['derived_basename']
        need('/' not in basename and basename.startswith('soong.') and
             basename.endswith('.variables') and len(basename)<=153,
             'single derived configuration basename grammar')
        derived={'role':'existing_soong_variables','path':SOONG_DIR+'/'+basename,
                 'maximum':1048576,'format':'product_sdk_variables'}
        result['derived_specification']=derived
        result['derived_candidate_read_attempts']=1
        result['inputs'].append(observe(derived))
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
    result['collection_complete'] = bool(not ERRORS and len(result['inputs']) == len(INPUTS)+1 and
        all(x['complete'] for x in result['inputs']) and result['all_tracked_owned_FDs_closed'] and
        result['control_deadline_met'] and result.get('own_resource_interval_qualified') and
        result.get('sdk_configuration_join',{}).get('qualified_for_fixed_build_input_binding') is True)
    raw = (json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode()
    need(len(raw) <= 1048576,'fixed input metadata report bound')
    sys.stdout.buffer.write(raw)
    return 0 if result['collection_complete'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
