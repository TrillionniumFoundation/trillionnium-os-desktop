"""Read thirteen fixed public APK build inputs. No build, child, device, or writes."""
import hashlib
import io
import json
import os
import signal
import stat
import struct
import sys
import time
import zipfile

INPUTS = json.loads(r'''[{"expected_bytes":3388,"expected_sha256":"477d0c399a4a2a0a04f70ec00a5c67a686b0ed8f159762e4333d84105e2cf498","format":"utf8","maximum":65536,"path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/external/googletest/googletest/Android.bp","role":"gtest_android_bp_anchor"},{"expected_bytes":1805,"expected_sha256":"155023bfbc86f9f021ea5705822e52f13d6fca5d80ff1cce12ae279287b694c6","format":"utf8","maximum":65536,"path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/clang/host/linux-x86/clang-r584948b/android_libc++/ndk/aarch64/include/c++/v1/__config_site","role":"arm64_ndk_config_anchor"},{"expected_bytes":21998949,"expected_sha256":"2e71327d66d43cb85a6ac11029376c19067ccc0f15e73c90f2f6777f3be70fb5","format":"zip","maximum":33554432,"path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/sdk/31/public/android.jar","required_classes":["android/os/Bundle.class","android/app/Activity.class"],"role":"android_jar31_anchor"},{"format":"archive","maximum":67108864,"path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/clang/host/linux-x86/clang-r584948b/android_libc++/ndk/aarch64/lib/libc++_static.a","role":"ndk_libcxx_static","expected_bytes":24613594,"expected_sha256":"b5503d3e2b52e541f73025feb6a16088290fd8091ac57ce568e02012f01a5251"},{"format":"archive","maximum":33554432,"path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/clang/host/linux-x86/clang-r584948b/android_libc++/ndk/aarch64/lib/libc++abi.a","role":"ndk_libcxxabi","expected_bytes":4930052,"expected_sha256":"c0520f2e83ab27bd14c5079bc3b8629d07d234ef4b9f0bbf73647c51cfe7e865"},{"format":"archive","maximum":16777216,"path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/clang/host/linux-x86/clang-r584948b/lib/clang/22/lib/linux/aarch64/libunwind.a","role":"arm64_unwind","expected_bytes":98856,"expected_sha256":"b24d66e5a6871fc843ced3176c8e7305684ef80e56c496b2ddd92a182abcb86f"},{"format":"archive","maximum":16777216,"path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/clang/host/linux-x86/clang-r584948b/lib/clang/22/lib/linux/libclang_rt.builtins-aarch64-android.a","role":"arm64_builtins","expected_bytes":519610,"expected_sha256":"1184a30e94d6aaa4c122e7eaf363861a61cf7a013f86e1b093b66027bbb9f2e5"},{"expected_bytes":2354,"expected_sha256":"736b4710cdcc7ce96816966a109c97b3553de44e082f73f76229f3af483518f0","format":"utf8","maximum":65536,"path":"/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-03-20261106/source/prebuilts/ndk/Android.bp","role":"ndk_cpufeatures_provider"},{"expected_bytes":39503,"expected_sha256":"e8992a9c2b044cab53df1e49c6910e92b21b084f7a834f63b46f4610b50ef044","format":"utf8","maximum":1048576,"path":"/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-03-20261106/source/prebuilts/ndk/current/sources/android/cpufeatures/cpu-features.c","role":"ndk_cpufeatures_source"},{"expected_bytes":11689,"expected_sha256":"122f6c71a49c553cd0a7e943f7db414eef4487e2e9f346117a141d5df3a7da74","format":"utf8","maximum":65536,"path":"/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-03-20261106/source/prebuilts/ndk/current/sources/android/cpufeatures/cpu-features.h","role":"ndk_cpufeatures_header"},{"format":"zip","maximum":16777216,"path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/sdk/31/public/android.test.runner.jar","required_classes":["android/test/InstrumentationTestRunner.class"],"role":"android_test_runner31","expected_bytes":25881,"expected_sha256":"7bc39e415d8c8390709ba79e579aa110005e3e9d3971c618551d0af30f02abb6"},{"format":"zip","maximum":16777216,"path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/sdk/31/public/android.test.base.jar","required_classes":["junit/framework/TestCase.class","junit/framework/Assert.class","android/test/InstrumentationTestCase.class"],"role":"android_test_base31","expected_bytes":15873,"expected_sha256":"a6e13d093428824b51f194a392af6ce0de92744f2a8ed3f7dd92c1145f433dcb"},{"format":"zip","maximum":16777216,"path":"/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/sdk/31/public/android.test.mock.jar","required_classes":["android/test/mock/MockContext.class"],"role":"android_test_mock31","expected_bytes":16410,"expected_sha256":"b84c31f415cbccec029ee467d2ac0b3b021081161b6b924a1f9733e667a317e2"}]''')
KIND = 'p4-marriott-real-arm64-ndk-apk-build03-inputs'
MEMORY_MAX = 268435456
START = time.monotonic()
WORK_END = START + 40.0
END = START + 45.0
ACTIVE_END = WORK_END
EVENTS = []
ERRORS = []
MAX_TOTAL = 230686720
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
        result['control_deadline_met'] and result.get('own_resource_interval_qualified'))
    raw = (json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode()
    need(len(raw) <= 1048576,'fixed input metadata report bound')
    sys.stdout.buffer.write(raw)
    return 0 if result['collection_complete'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
