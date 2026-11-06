#!/usr/bin/env python3
"""Prepare only fixed observed inputs for a new normal framework workspace."""
import datetime,hashlib,json,os,posixpath,signal,stat,sys,time
from pathlib import Path

def require(value, reason):
    if not value:
        raise RuntimeError(reason)

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def identity(st):
    return [st.st_dev,st.st_ino,st.st_mode,st.st_size,st.st_mtime_ns,st.st_ctime_ns]

def resource_text(directory_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        raw = os.read(fd, 32769)
        require(len(raw) <= 32768, 'owned resource observation exceeds bound')
        return raw.decode('ascii').strip()
    finally:
        os.close(fd)

def resource_events(text):
    rows = [line.split() for line in text.splitlines()]
    require(rows and all(len(row) == 2 and row[1].isdigit() for row in rows), 'malformed owned memory.events')
    events = {row[0]:int(row[1]) for row in rows}
    require(len(events) == len(rows) and all(k in events for k in ['oom','oom_kill','oom_group_kill']), 'incomplete or duplicate owned memory.events')
    return events

def resource_snapshot(directory_fd, membership):
    observed = Path('/proc/self/cgroup').read_text().strip()
    require(observed == membership, 'controller cgroup membership changed')
    path = Path('/sys/fs/cgroup')/membership[3:].lstrip('/')
    held_st = os.fstat(directory_fd)
    named_st = path.lstat()
    require(stat.S_ISDIR(held_st.st_mode) and stat.S_ISDIR(named_st.st_mode) and
            (held_st.st_dev,held_st.st_ino) == (named_st.st_dev,named_st.st_ino), 'owned invocation cgroup identity changed')
    fields = {name:resource_text(directory_fd,name) for name in [
        'cgroup.procs','memory.events','memory.current','memory.peak','memory.high','memory.max',
        'memory.swap.current','memory.swap.peak','memory.swap.max','cpu.max']}
    require(str(os.getpid()) in fields['cgroup.procs'].split(), 'controller is not in the held invocation')
    require(fields['memory.max'] == '268435456' and fields['cpu.max'] == '50000 100000', 'owned resource limits do not match the request')
    for key in ['memory.current','memory.peak','memory.swap.current','memory.swap.peak']:
        require(fields[key].isdigit(), 'invalid owned resource counter: '+key)
    return {'observed_utc':utc(), 'membership':membership, 'path':str(path),
            'directory_identity':[held_st.st_dev,held_st.st_ino],
            'controller_pid':os.getpid(), 'fields':fields, 'events':resource_events(fields['memory.events'])}

def begin_resources():
    membership = Path('/proc/self/cgroup').read_text().strip()
    require('\n' not in membership and membership.startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-'), 'not the exact owned user invocation')
    path = Path('/sys/fs/cgroup')/membership[3:].lstrip('/')
    require(path.name.startswith('hepta-runtime-job-') and path.name.endswith('.service') and '..' not in path.parts, 'unexpected owned unit path')
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = resource_snapshot(fd,membership)
        require(all(before['events'][k] == 0 for k in ['oom','oom_kill','oom_group_kill']), 'owned invocation already recorded OOM before the control')
        return fd,before
    except BaseException:
        os.close(fd)
        raise

def finish_resources(directory_fd, before, report):
    after = resource_snapshot(directory_fd,before['membership'])
    report['owned_resources_after'] = after
    report['owned_memory_peak'] = int(after['fields']['memory.peak'])
    report['owned_memory_swap_peak'] = int(after['fields']['memory.swap.peak'])
    require(after['directory_identity'] == before['directory_identity'], 'owned cgroup object replaced')
    require(set(before['events']) == set(after['events']), 'owned memory event fields changed')
    delta = {key:after['events'][key]-value for key,value in before['events'].items()}
    report['owned_memory_events_delta'] = delta
    require(all(value >= 0 for value in delta.values()), 'owned memory event counters went backwards')
    require(all(delta[key] == 0 for key in ['oom','oom_kill','oom_group_kill']), 'owned OOM event occurred; control is not qualified')
    require(all(before['fields'][key] == after['fields'][key] for key in ['memory.max','memory.high','memory.swap.max','cpu.max']), 'owned cgroup limits changed during control')
    return {'pass':True, 'before':before, 'after':after, 'memory_events_delta':delta,
            'memory_peak':int(after['fields']['memory.peak']), 'memory_swap_peak':int(after['fields']['memory.swap.peak']),
            'resource_settings_changed':False, 'swap_max_observed_only':after['fields']['memory.swap.max']}

def error_row(error):
    return {'type':type(error).__name__,'message':str(error),
            'errno':getattr(error,'errno',None),'filename':getattr(error,'filename',None)}

def note_error(report, phase, error, path=None):
    row={'phase':phase,'path':str(path) if path is not None else None,'error':error_row(error)}
    if report['first_error'] is None: report['first_error']=row
    else: report['secondary_errors'].append(row)
    report['state']='FAIL'

def full_identity(st):
    return [st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,
            st.st_size,st.st_mtime_ns,st.st_ctime_ns]

def directory_identity(st):
    return [st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid]

def check_deadline(state):
    require(time.monotonic()<state['deadline'],'fixed readonly observation deadline elapsed')

def directory(path, state):
    path=Path(path)
    require(path.is_absolute() and '..' not in path.parts and '.' not in path.parts,
            'fixed observation path is not absolute and normalized')
    key=str(path)
    if key in state['directories']: return state['directories'][key][0]
    check_deadline(state)
    parent_fd=None if path==Path('/') else directory(path.parent,state)
    fd=os.open('/' if parent_fd is None else path.name,
               os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,
               dir_fd=parent_fd)
    try:
        held=os.fstat(fd)
        named=os.stat('/' if parent_fd is None else path.name,
                      dir_fd=parent_fd,follow_symlinks=False)
        require(stat.S_ISDIR(held.st_mode) and full_identity(held)==full_identity(named),
                'fixed directory held/named identity differs')
        row={'path':key,'held_before':full_identity(held),'named_before':full_identity(named),
             'contents_enumerated':False,'recursive_bytes_measured':False}
        state['directories'][key]=(fd,row)
        return fd
    except BaseException:
        try: os.close(fd)
        except BaseException as error:
            state['early_close_errors'].append({'phase':'directory-setup-close','path':key,'error':error_row(error)})
        raise

def named_file(path, state):
    parent_fd=directory(path.parent,state)
    return os.stat(path.name,dir_fd=parent_fd,follow_symlinks=False)

def stop_signal(number, _frame):
    raise RuntimeError('readonly controller interrupted by signal '+str(number))

ROOT = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-framework-work-preparation-01-20261105')
HERE = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-framework-work-preparation-01-20261105/control-source')
OUT = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-framework-work-preparation-01-20261105/attempt01')
WORK = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-work-01-20261105')
MESA = Path('/home/alex/work/p4-nativebridge-repair-20261017-1428-work/mesa-source')
PYTHON = Path('/home/alex/work/m692-pinned-android17-build-inputs-20261015/python')
TETO_PARENT = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined07-go5-streaming-01')
TETO = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/full-build-combined07-go5-streaming-01/engine-working')
MISSING_TOOL_ROOT = Path('/home/alex/work/m692-pinned-android17-build-inputs-20261015/mesa-tools')
TETO_HEAD = 'a9496d886a85752ba407b76509952c06cd79ddb8'
ASSETS = [{'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libandroid.so', 'destination': 'base-system/system/lib64/libandroid.so', 'bytes': 335768, 'sha256': 'ce601e9536fb971a53bcdf17acd0bf25ee0ac54b1c4e03f83904514667bfb25e', 'identity': [66306, 69994378, 33188, 1000, 1000, 335768, 1230768000000000000, 1792078703732913242]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libandroid_runtime.so', 'destination': 'base-system/system/lib64/libandroid_runtime.so', 'bytes': 2951384, 'sha256': '58ceefe3fea774bb14e5e32c2eb174837c916ed423620be0f05d72eef76bf10e', 'identity': [66306, 69994388, 33188, 1000, 1000, 2951384, 1230768000000000000, 1792078703735913327]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libaaudio.so', 'destination': 'base-system/system/lib64/libaaudio.so', 'bytes': 85992, 'sha256': 'e25b7d7c106032b215f32fe4be1583d35b01bbf3c04996848ee71961b5ed9ebb', 'identity': [66306, 69994353, 33188, 1000, 1000, 85992, 1230768000000000000, 1792078703730913185]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libamidi.so', 'destination': 'base-system/system/lib64/libamidi.so', 'bytes': 52592, 'sha256': 'f7fb364792399e2e62a7cec35f7445cb4770b629c569a2ccf5c5c9d3ae69a7ce', 'identity': [66306, 69994377, 33188, 1000, 1000, 52592, 1230768000000000000, 1792078703732913242]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libbinder_ndk.so', 'destination': 'base-system/system/lib64/libbinder_ndk.so', 'bytes': 189200, 'sha256': 'a1e9160fe502d124f035d5c2547b55aed557b947dc96a0b7684378b2b9d23e53', 'identity': [66306, 69994444, 33188, 1000, 1000, 189200, 1230768000000000000, 1792078703747913668]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libcamera2ndk.so', 'destination': 'base-system/system/lib64/libcamera2ndk.so', 'bytes': 356128, 'sha256': '28512a7cc0c5de946a8a382f8844d3294e4732eabc93bd6cb297d91dc75deb13', 'identity': [66306, 69994472, 33188, 1000, 1000, 356128, 1230768000000000000, 1792078703750913754]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libEGL.so', 'destination': 'base-system/system/lib64/libEGL.so', 'bytes': 270536, 'sha256': '02f05b789b83c5fc59a5ec5500b10cda6dbe5bcc122d08c9b8c9d27f4b3a693a', 'identity': [66306, 69994333, 33188, 1000, 1000, 270536, 1230768000000000000, 1792078703713912702]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libGLESv1_CM.so', 'destination': 'base-system/system/lib64/libGLESv1_CM.so', 'bytes': 51768, 'sha256': 'd5879673edf21e3bdf772529c39fb9fc9734fc98a5eabb93436bd315a92ff259', 'identity': [66306, 69994337, 33188, 1000, 1000, 51768, 1230768000000000000, 1792078703713912702]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libGLESv2.so', 'destination': 'base-system/system/lib64/libGLESv2.so', 'bytes': 117144, 'sha256': '0ec7fbc886e2df223f54ca24447be2a22a42c453b8f9421f09df4b75004ed7d0', 'identity': [66306, 69994339, 33188, 1000, 1000, 117144, 1230768000000000000, 1792078703713912702]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libGLESv3.so', 'destination': 'base-system/system/lib64/libGLESv3.so', 'bytes': 117144, 'sha256': '920fe9288ea45e57df3841e6e6af04eb7a67865cf56b7aca76212ace62faaf34', 'identity': [66306, 69994341, 33188, 1000, 1000, 117144, 1230768000000000000, 1792078703717912816]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libjnigraphics.so', 'destination': 'base-system/system/lib64/libjnigraphics.so', 'bytes': 36392, 'sha256': 'f2ef58b01d3964d13ee60646f3e0a2dfa0ab749fe8134ed41d01d034ef9bdd5f', 'identity': [66306, 69994615, 33188, 1000, 1000, 36392, 1230768000000000000, 1792078703783914691]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libmediandk.so', 'destination': 'base-system/system/lib64/libmediandk.so', 'bytes': 306272, 'sha256': 'fe75eb23fd02bac9b0af11d44a0fe6a749d658850e44eb6109c10b33205c4ca3', 'identity': [66306, 69994673, 33188, 1000, 1000, 306272, 1230768000000000000, 1792078703795915032]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libnativewindow.so', 'destination': 'base-system/system/lib64/libnativewindow.so', 'bytes': 68248, 'sha256': '43c964a2905d62cf1832fc10700b11f6676ba004c5ad0c52e591ee7e781192f7', 'identity': [66306, 69994703, 33188, 1000, 1000, 68248, 1230768000000000000, 1792078703800915174]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libOpenMAXAL.so', 'destination': 'base-system/system/lib64/libOpenMAXAL.so', 'bytes': 35800, 'sha256': 'cca5b1217508415a6cd66f0be24612981dcf8aff1b33dc3731c89e17152c29d4', 'identity': [66306, 69994343, 33188, 1000, 1000, 35800, 1230768000000000000, 1792078703729913157]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libOpenSLES.so', 'destination': 'base-system/system/lib64/libOpenSLES.so', 'bytes': 35896, 'sha256': 'f8c1877067b741b4a8cf3e8692f63cf834d6b3a76481ba451f2edbec86556d6c', 'identity': [66306, 69994344, 33188, 1000, 1000, 35896, 1230768000000000000, 1792078703729913157]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libwebviewchromium_plat_support.so', 'destination': 'base-system/system/lib64/libwebviewchromium_plat_support.so', 'bytes': 52160, 'sha256': '4423fa39a911312f66a825b08501745cce934779791f698dac225a7ab60d6716', 'identity': [66306, 69994876, 33188, 1000, 1000, 52160, 1230768000000000000, 1792078703829915999]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/lib64/libvulkan.so', 'destination': 'base-system/system/lib64/libvulkan.so', 'bytes': 274360, 'sha256': 'b2968cfcadbd3d020991e2302a06dac5d5f850a13eb1394af7faf7bbec785195', 'identity': [66306, 69994874, 33188, 1000, 1000, 274360, 1230768000000000000, 1792078703829915999]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/apex/com.android.art.apex', 'destination': 'base-system/system/apex/com.android.art.apex', 'bytes': 33742848, 'sha256': '3a5b5d1fab9e4f3ca4a15da425a4d56c45548d137ee8289e34687fb5b60d6807', 'identity': [66306, 69992486, 33188, 1000, 1000, 33742848, 1230768000000000000, 1792078702302872609]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/base-system/system/apex/com.android.neuralnetworks.apex', 'destination': 'base-system/system/apex/com.android.neuralnetworks.apex', 'bytes': 5763072, 'sha256': '22f8fb7620121e4646135dc8525df9e1ab6390993fd286d9232d07d45f15b342', 'identity': [66306, 69992500, 33188, 1000, 1000, 5763072, 1230768000000000000, 1792078702899191838]}, {'source': '/home/alex/work/m692-pinned-android17-build-inputs-20261015/framework-res.apk', 'destination': 'framework-res.apk', 'bytes': 38012749, 'sha256': 'b5b5756e6d93680f1086417d764d18c9e67c8e884879cb894849bec12f20a9ec', 'identity': [66306, 69861651, 33188, 1000, 1000, 38012749, 1230768000000000000, 1792078703936919039]}]
MISSING_TOOLS = ['/home/alex/work/m692-pinned-android17-build-inputs-20261015/mesa-tools/src/compiler/clc/mesa_clc', '/home/alex/work/m692-pinned-android17-build-inputs-20261015/mesa-tools/src/compiler/spirv/vtn_bindgen2']
AUTHORITIES = {'canonical-inputs-read02-result.json': {'bytes': 61268, 'sha256': '7a9b20fd11db23094d78661dc58aa26215270464c1ab2f40ebe70dac0694ae06'}, 'candidate07-preparation.json': {'bytes': 118896, 'sha256': '0db7bdac207cab7bd800f6c9948d41b530da1d6ccb077897a508e641c7abee2c'}}
MAX_TOTAL_READ = 2 * 1024**3
MAX_TOTAL_COPY = 1024**3
MAX_SINGLE_FILE = 512 * 1024**2
MAX_TREE_ENTRIES = 20000
MAX_TREE_LOGICAL_BYTES = 512 * 1024**2

def close_owned(fd, report, phase, path=None):
    if fd is None or fd < 0:
        return
    primary = sys.exc_info()[1]
    try:
        os.close(fd)
    except BaseException as error:
        if primary is not None:
            report['secondary_errors'].append({'phase': phase, 'path': str(path) if path is not None else None,
                                               'error': error_row(error)})
            report['state'] = 'FAIL'
        else:
            note_error(report, phase, error, path)


def held_bytes(path, maximum, state):
    path = Path(path)
    parent = directory(path.parent, state)
    fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and not before.st_mode & 0o6000 and
                before.st_size <= maximum, 'authority is not a bounded regular file: ' + str(path))
        blocks = []
        total = 0
        while True:
            check_deadline(state)
            block = os.read(fd, min(65536, maximum + 1 - total))
            if not block:
                break
            blocks.append(block)
            total += len(block)
            require(total <= maximum, 'authority exceeded its fixed bound: ' + str(path))
        raw = b''.join(blocks)
        require(total == before.st_size and full_identity(before) == full_identity(os.fstat(fd)) ==
                full_identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)),
                'held authority changed: ' + str(path))
        return raw, {'path': str(path), 'bytes': total, 'sha256': sha(raw), 'identity': full_identity(before)}
    finally:
        close_owned(fd, state['report'], 'authority-close', path)


def save_new(path, raw, state):
    path = Path(path)
    parent = directory(path.parent, state)
    fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o400, dir_fd=parent)
    try:
        position = 0
        while position < len(raw):
            check_deadline(state)
            count = os.write(fd, raw[position:position + 65536])
            require(count > 0, 'short owned evidence write')
            position += count
        os.fsync(fd)
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size == len(raw) and
                full_identity(before) == full_identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)),
                'owned evidence named/held identity differs')
        return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw), 'identity': full_identity(before)}
    finally:
        close_owned(fd, state['report'], 'evidence-close', path)


def save_json(path, value, state):
    return save_new(path, (json.dumps(value, sort_keys=True, indent=2) + '\n').encode(), state)


def new_directory(path, state, mode=0o700):
    path = Path(path)
    parent = directory(path.parent, state)
    os.mkdir(path.name, mode=mode, dir_fd=parent)
    fd = directory(path, state)
    st = os.fstat(fd)
    require(st.st_uid == 1000 and st.st_gid == 1000 and stat.S_IMODE(st.st_mode) == mode,
            'new owned directory permissions differ: ' + str(path))
    return fd


def owned_descendant(parent, parts, state):
    path = Path(parent)
    for part in parts:
        require(part and part not in ('.', '..') and '/' not in part, 'invalid owned path component')
        path = path / part
        key = str(path)
        if key not in state['created_directories']:
            new_directory(path, state)
            state['created_directories'].add(key)
    return path


def read_or_copy_file(parent_fd, name, before, state, output_parent=None, output_name=None):
    require(stat.S_ISREG(before.st_mode) and not before.st_mode & 0o6000 and
            0 <= before.st_size <= MAX_SINGLE_FILE, 'invalid fixed regular source type/size')
    source_fd = output_fd = -1
    try:
        source_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
        require(full_identity(os.fstat(source_fd)) == full_identity(before), 'source changed before open')
        if output_parent is not None:
            output_fd = os.open(output_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                0o600, dir_fd=output_parent)
        digest = hashlib.sha256()
        count = 0
        while True:
            check_deadline(state)
            data = os.read(source_fd, min(65536, MAX_SINGLE_FILE + 1 - count))
            if not data:
                break
            count += len(data)
            state['bytes_read'] += len(data)
            require(count <= before.st_size and state['bytes_read'] <= MAX_TOTAL_READ,
                    'source grew or cumulative read bound exceeded')
            digest.update(data)
            if output_fd >= 0:
                position = 0
                while position < len(data):
                    written = os.write(output_fd, data[position:])
                    require(written > 0, 'short owned input write')
                    position += written
                state['bytes_copied'] += len(data)
                require(state['bytes_copied'] <= MAX_TOTAL_COPY, 'owned copy byte bound exceeded')
        require(count == before.st_size and full_identity(before) == full_identity(os.fstat(source_fd)) ==
                full_identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)),
                'held/named source changed during complete read')
        mode = stat.S_IMODE(before.st_mode)
        if output_fd >= 0:
            os.fchmod(output_fd, mode)
            os.fsync(output_fd)
            output_info = os.fstat(output_fd)
            require(output_info.st_uid == 1000 and output_info.st_gid == 1000 and
                    stat.S_ISREG(output_info.st_mode) and output_info.st_size == count and
                    stat.S_IMODE(output_info.st_mode) == mode and
                    full_identity(output_info) == full_identity(os.stat(output_name, dir_fd=output_parent, follow_symlinks=False)),
                    'owned copied file identity differs')
        return {'kind': 'file', 'bytes': count, 'sha256': digest.hexdigest(), 'mode': mode}
    finally:
        close_owned(output_fd, state['report'], 'copy-output-close', output_name)
        close_owned(source_fd, state['report'], 'copy-source-close', name)


def fixed_asset(row, state, copy=False):
    source = Path(row['source'])
    source_parent = directory(source.parent, state)
    before = os.stat(source.name, dir_fd=source_parent, follow_symlinks=False)
    require(full_identity(before) == row['identity'], 'fixed canonical asset identity changed: ' + str(source))
    output_parent = None
    target = WORK / row['destination']
    if copy:
        parts = Path(row['destination']).parts
        require(parts and not Path(row['destination']).is_absolute() and all(p not in ('.', '..') for p in parts),
                'unsafe fixed work destination')
        parent = owned_descendant(WORK, parts[:-1], state)
        output_parent = directory(parent, state)
    actual = read_or_copy_file(source_parent, source.name, before, state, output_parent, target.name)
    require(actual['bytes'] == row['bytes'] and actual['sha256'] == row['sha256'],
            'fixed canonical asset content changed: ' + str(source))
    return actual


def tree_inventory(root, state, destination=None, skip_root_git=False):
    root = Path(root)
    root_fd = directory(root, state)
    output_root = None if destination is None else directory(destination, state)
    metadata_digest = hashlib.sha256()
    rows = {}
    counts = {'entries': 0, 'directories': 0, 'regular_files': 0, 'symlinks': 0, 'other': 0,
              'regular_logical_bytes': 0, 'regular_allocated_bytes_by_path': 0,
              'symlink_text_bytes': 0, 'lexically_external_symlinks': 0}
    ignored_git = None

    def add_metadata(relative, before, link_text=None):
        raw = json.dumps({'path': relative, 'identity': full_identity(before), 'nlink': before.st_nlink,
                          'allocated_bytes': before.st_blocks * 512, 'link_text': link_text},
                         ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode() + b'\n'
        metadata_digest.update(raw)

    def visit(fd, output_fd, relative, depth):
        nonlocal ignored_git
        check_deadline(state)
        require(depth <= 64, 'source tree depth bound exceeded')
        names = []
        with os.scandir(fd) as entries:
            for entry in entries:
                check_deadline(state)
                require(entry.name not in ('', '.', '..') and '/' not in entry.name, 'invalid source entry name')
                if skip_root_git and relative == '' and entry.name == '.git':
                    git_info = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                    require(stat.S_ISDIR(git_info.st_mode), 'Teto .git is not a real directory')
                    ignored_git = full_identity(git_info)
                    continue
                names.append(entry.name)
                require(len(names) + counts['entries'] <= MAX_TREE_ENTRIES, 'source tree entry bound exceeded')
        for name in sorted(names):
            check_deadline(state)
            child_relative = name if not relative else relative + '/' + name
            require(len(os.fsencode(child_relative)) <= 4096, 'source path bound exceeded')
            before = os.stat(name, dir_fd=fd, follow_symlinks=False)
            counts['entries'] += 1
            require(counts['entries'] <= MAX_TREE_ENTRIES and not before.st_mode & 0o6000,
                    'source entry count or set-ID mode differs')
            if stat.S_ISDIR(before.st_mode):
                counts['directories'] += 1
                mode = stat.S_IMODE(before.st_mode)
                rows[child_relative] = {'kind': 'directory', 'mode': mode}
                child_fd = output_child = -1
                try:
                    child_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
                    require(full_identity(os.fstat(child_fd)) == full_identity(before), 'tree directory changed before open')
                    add_metadata(child_relative, before)
                    if output_fd is not None:
                        os.mkdir(name, mode=0o700, dir_fd=output_fd)
                        output_child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                                               dir_fd=output_fd)
                    visit(child_fd, None if output_child < 0 else output_child, child_relative, depth + 1)
                    require(full_identity(os.fstat(child_fd)) == full_identity(before), 'tree directory changed during traversal')
                    if output_child >= 0:
                        os.fchmod(output_child, mode)
                        os.fsync(output_child)
                finally:
                    close_owned(output_child, state['report'], 'tree-copy-directory-close', child_relative)
                    close_owned(child_fd, state['report'], 'tree-source-directory-close', child_relative)
            elif stat.S_ISREG(before.st_mode):
                counts['regular_files'] += 1
                counts['regular_logical_bytes'] += before.st_size
                counts['regular_allocated_bytes_by_path'] += before.st_blocks * 512
                require(counts['regular_logical_bytes'] <= MAX_TREE_LOGICAL_BYTES, 'source logical byte bound exceeded')
                add_metadata(child_relative, before)
                rows[child_relative] = read_or_copy_file(fd, name, before, state, output_fd, name)
            elif stat.S_ISLNK(before.st_mode):
                counts['symlinks'] += 1
                require(0 < before.st_size <= 4096, 'source symlink length differs')
                raw = os.readlink(os.fsencode(name), dir_fd=fd)
                require(isinstance(raw, bytes) and len(raw) == before.st_size, 'source symlink changed')
                target = raw.decode('utf-8', 'strict')
                absolute = posixpath.normpath(target if target.startswith('/') else str((root / child_relative).parent) + '/' + target)
                inside = os.path.commonpath((str(root), absolute)) == str(root)
                counts['lexically_external_symlinks'] += int(not inside)
                counts['symlink_text_bytes'] += len(raw)
                require(inside and not target.startswith('/'), 'source symlink leaves its copied tree')
                rows[child_relative] = {'kind': 'symlink', 'target': target}
                add_metadata(child_relative, before, target)
                if output_fd is not None:
                    os.symlink(target, name, dir_fd=output_fd)
                    require(os.readlink(os.fsencode(name), dir_fd=output_fd) == raw, 'copied symlink text differs')
                require(os.readlink(os.fsencode(name), dir_fd=fd) == raw, 'source symlink changed during read')
            else:
                counts['other'] += 1
                raise RuntimeError('unsupported source object: ' + child_relative)
            require(full_identity(before) == full_identity(os.stat(name, dir_fd=fd, follow_symlinks=False)),
                    'named source entry changed: ' + child_relative)

    before = os.fstat(root_fd)
    add_metadata('', before)
    visit(root_fd, output_root, '', 0)
    require(full_identity(before) == full_identity(os.fstat(root_fd)) == full_identity(named_file(root, state)),
            'source root changed during complete inventory')
    return {'root': str(root), 'held_root': full_identity(before), 'metadata_sha256': metadata_digest.hexdigest(),
            'counts': counts, 'files': rows, 'ignored_root_git_identity': ignored_git}


def verify_tree_observation(actual, expected):
    require(actual['root'] == expected['root'] and actual['held_root'] == expected['before']['held_root_before'] and
            actual['metadata_sha256'] == expected['before']['metadata_sha256'] and
            actual['counts'] == expected['before']['counts'], 'source tree differs from the fixed actual metadata observation')
    links = {name: row['target'] for name, row in actual['files'].items() if row['kind'] == 'symlink'}
    require(links == {r['path']: r['text'] for r in expected['before']['symlinks']}, 'actual source symlink set changed')


def verify_teto(actual, preparation, modes):
    files = {name: row for name, row in actual['files'].items() if row['kind'] != 'directory'}
    require(len(files) == preparation['engine_file_count'] == 926 and set(files) == set(preparation['engine_files']) == set(modes),
            'Teto complete 926-file path set differs')
    require(all(row['kind'] == 'file' and row['sha256'] == preparation['engine_files'][name] and row['mode'] == modes[name]
                for name, row in files.items()), 'Teto source contents or original executable modes differ')


def load_authorities(state):
    rows = {}
    for name, wanted in AUTHORITIES.items():
        raw, observed = held_bytes(HERE / name, wanted['bytes'], state)
        require(observed['bytes'] == wanted['bytes'] and observed['sha256'] == wanted['sha256'],
                'staged input authority differs: ' + name)
        rows[name] = (raw, observed)
    canonical = json.loads(rows['canonical-inputs-read02-result.json'][0])
    require(canonical['state'] == 'FAIL' and canonical['all_five_aliases_revalidated'] is True and
            canonical['owned_resource_gate']['pass'] is True and
            canonical['source_or_workspace_writes'] == canonical['subprocesses'] == canonical['Main_actions'] == 0,
            'canonical observation scope differs')
    good = [r for r in canonical['files'] if r['error'] is None]
    bad = [r for r in canonical['files'] if r['error'] is not None]
    require(len(good) == 25 and len(bad) == 2 and
            {r['spec']['path'] for r in bad} == set(MISSING_TOOLS) and
            all(r['error']['errno'] == 2 and r['error']['filename'] == 'mesa-tools' for r in bad),
            'canonical original failure is not exactly the two unused-at-prepare tool paths')
    require(canonical['first_error']['phase'] == 'fixed-directory' and
            canonical['first_error']['path'] == str(MISSING_TOOL_ROOT) and
            canonical['first_error']['error']['errno'] == 2 and
            len(canonical['secondary_errors']) == 3 and
            all(r['error']['errno'] == 2 and r['path'] in [str(MISSING_TOOL_ROOT), *MISSING_TOOLS]
                for r in canonical['secondary_errors']), 'canonical prior failure details differ')
    for row in good:
        require(row['revalidated_unchanged'] is True and row['bytes'] == row['final_bytes'] and
                row['sha256'] == row['final_sha256'] and
                row['named_before'] == row['held_before'] == row['held_after_read'] == row['named_after_read'] == row['held_final'] == row['named_final'],
                'canonical successful file does not have complete held/named closure')
    wanted_rows = {r['spec']['path']: r for r in good}
    for asset in ASSETS:
        row = wanted_rows[asset['source']]
        require(row['bytes'] == asset['bytes'] and row['sha256'] == asset['sha256'] and row['held_before'] == asset['identity'],
                'fixed work asset was not observed exactly')
    trees = {r['root']: r for r in canonical['tree_metadata'] if r['complete']}
    require(set(trees) == {str(MESA), str(PYTHON)}, 'complete metadata tree set differs')
    for row in trees.values():
        require(row['before']['metadata_sha256'] == row['after_metadata_sha256'] and
                row['before']['held_root_before'] == row['before']['held_root_after'] == row['after_held_root'],
                'tree metadata observation lacks its stable second pass')
    preparation = json.loads(rows['candidate07-preparation.json'][0])
    require(preparation['state'] == 'PREPARED_NOT_BUILT' and preparation['engine_file_count'] == 926 and
            preparation['candidate_manifest_sha256'] == 'e10024548a5b2b5a391ecc9ddb3ea2f19b95a6fea3437f40207a0f4721745a93' and
            preparation['feature_default_enabled'] is False and preparation['normal_import_policy'] == 'checksum-no-times-v1' and
            preparation['git_head'] == TETO_HEAD and preparation['origin'] == 'https://github.com/denialwm/teto.git',
            'actual candidate07 Teto input authority differs')
    return rows, canonical, trees, preparation


def plan():
    return {'mode': 'PLAN', 'new_work': str(WORK), 'new_evidence_root': str(OUT),
            'fixed_asset_copies': len(ASSETS), 'source_trees_copied': [str(MESA), str(PYTHON)],
            'Teto_source_read_only': str(TETO), 'Teto_source_files': 926,
            'materialize_or_build_invoked': False, 'Main_actions': 0, 'commands_started': 0,
            'missing_mesa_tools_fabricated': False, 'normal_Strict_targets_changed': False,
            'requires_explicit_execute_once': True, 'CPUQuota_percent': 50, 'MemoryMax': 268435456,
            'timeout_seconds': 240, 'full_framework_qualification': False}


def execute():
    require(os.getuid() == os.geteuid() == 1000, 'ordinary operator UID1000 required')
    require(Path(__file__).absolute() == HERE / 'prepare_work.py', 'exact staged source required')
    os.umask(0o077)
    report = {'schema': 1, 'state': 'RUNNING', 'started_utc': utc(), 'first_error': None, 'secondary_errors': [],
              'Main_actions': 0, 'Main_identity_observed': False, 'commands_started': 0,
              'materialize_invoked': False, 'Soong_invoked': False, 'builder_invoked': False,
              'framework_Java_and_Android_TU_qualified': False, 'runtime_authorization_enabled': False,
              'old_source_modified': False, 'partial_owned_inputs_preserved_on_failure': True,
              'old_canonical_read02_still_failed': True, 'missing_tool_paths_not_qualified': list(MISSING_TOOLS),
              'Mesa_archive_lock_reproducibility_claimed': False, 'Python_archive_lock_reproducibility_claimed': False,
              'Teto_origin_and_ancestor_rechecked_by_this_prepare': False,
              'Teto_normal_import_still_requires_builder_git_checks': True}
    state = {'report': report, 'deadline': time.monotonic() + 220, 'bytes_read': 0, 'bytes_copied': 0,
             'directories': {}, 'early_close_errors': [], 'created_directories': set()}
    parent_fd = directory(WORK.parent, state)
    require(directory_identity(os.fstat(parent_fd)) == [66306, 34351895, 16832, 1000, 1000],
            'fixed strict owned parent identity differs')
    # Claim the evidence directory before the fallible input checks. A reused
    # attempt fails before touching its old evidence; a new input failure has
    # its own durable result directory.
    new_directory(OUT, state)
    resource_fd = -1
    resource_before = None
    authorities = {}
    authority_inputs = {}
    source_trees = {}
    fixed_rows = {}
    teto_before = None
    modes = None
    preparation = None
    work_created = False
    source_checks_completed = False
    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    try:
        resource_fd, resource_before = begin_resources()
        report['owned_resources_before'] = resource_before
        child_path = Path('/proc/self/task') / str(os.getpid()) / 'children'
        require(child_path.read_text().strip() == '', 'controller has unexpected initial children')
        parent_info = os.fstat(parent_fd)
        require(directory_identity(parent_info) == [66306, 34351895, 16832, 1000, 1000],
                'fixed strict owned parent identity differs')
        for path in (WORK,):
            try:
                os.stat(path.name, dir_fd=parent_fd if path.parent == WORK.parent else directory(path.parent, state), follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise RuntimeError('create-only path already exists: ' + str(path))
        authorities, canonical, trees, preparation = load_authorities(state)
        authority_inputs = {name: row for name, (_, row) in authorities.items()}
        report['input_authorities'] = authority_inputs
        capacity = os.fstatvfs(parent_fd)
        report['filesystem_available_before'] = capacity.f_bavail * capacity.f_frsize
        require(report['filesystem_available_before'] >= 2 * 1024**3, 'less than the bounded asset-copy space allowance')
        require(len(ASSETS) == 20 and len({r['source'] for r in ASSETS}) == len(ASSETS), 'fixed asset map changed')
        modes_raw, mode_pin = held_bytes(TETO_PARENT / 'engine-working-mode-manifest.json', 65536, state)
        require(mode_pin['sha256'] == preparation['engine_modes_sha256'], 'Teto mode authority changed')
        modes = json.loads(modes_raw)
        head_raw, head_pin = held_bytes(TETO / '.git/HEAD', 128, state)
        require(head_raw == (TETO_HEAD + '\n').encode(), 'Teto held HEAD differs')
        report['Teto_mode_authority'] = mode_pin
        report['Teto_HEAD_authority'] = head_pin
        new_directory(WORK, state)
        state['created_directories'].add(str(WORK))
        work_created = True
        for asset in ASSETS:
            fixed_rows[asset['destination']] = fixed_asset(asset, state, copy=True)
        report['fixed_assets_copied'] = len(fixed_rows)
        for source, name in ((MESA, 'mesa-source'), (PYTHON, 'python')):
            target = WORK / name
            new_directory(target, state)
            inventory = tree_inventory(source, state, target)
            verify_tree_observation(inventory, trees[str(source)])
            source_trees[name] = inventory
            report[name + '_observed_content_manifest'] = save_json(OUT / (name + '-source-manifest.json'), inventory, state)
            print(json.dumps({'phase': 'COPIED_AND_HASHED_TREE', 'name': name, 'counts': inventory['counts']}), flush=True)
        cross = source_trees['mesa-source']['files']['android/mesa3d_cross.mk']
        cross_observed = next(r for r in canonical['files'] if r['spec']['category'] == 'mesa_projection_input')
        require(cross['bytes'] == cross_observed['bytes'] and cross['sha256'] == cross_observed['sha256'],
                'Mesa cross-file prerequisite changed')
        teto_before = tree_inventory(TETO, state, skip_root_git=True)
        verify_teto(teto_before, preparation, modes)
        report['Teto_observed_content_manifest'] = save_json(OUT / 'Teto-source-manifest.json', teto_before, state)
        report['Teto_all_926_files_and_modes_match'] = True
        source_checks_completed = True
        report['state'] = 'PREPARED_INPUTS_NOT_MATERIALIZED_OR_BUILT'
    except BaseException as error:
        note_error(report, 'prepare-work', error)
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        for name, (raw, original_pin) in authorities.items():
            try:
                again, observed = held_bytes(HERE / name, len(raw), state)
                require(again == raw and observed == original_pin, 'staged authority changed')
            except BaseException as error:
                note_error(report, 'staged-authority-after', error, HERE / name)
        if work_created:
            try:
                for asset in ASSETS:
                    expected = fixed_rows.get(asset['destination'])
                    require(expected is not None, 'asset copy did not complete')
                    require(fixed_asset(asset, state) == expected, 'canonical asset changed after copy')
                    path = WORK / asset['destination']
                    parent = directory(path.parent, state)
                    before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                    require(read_or_copy_file(parent, path.name, before, state) == expected, 'copied asset differs after preparation')
                report['fixed_assets_source_and_copy_unchanged_after'] = True
            except BaseException as error:
                note_error(report, 'fixed-assets-after', error)
            for source, name in ((MESA, 'mesa-source'), (PYTHON, 'python')):
                try:
                    require(name in source_trees, 'source tree copy did not complete')
                    again = tree_inventory(source, state)
                    original = source_trees[name]
                    require(again == original, 'full source content or identity changed after copy')
                    copied = tree_inventory(WORK / name, state)
                    require(copied['files'] == original['files'], 'copied source tree content/path/mode set differs')
                    report[name + '_source_and_copy_unchanged_after'] = True
                    report[name + '_copied_content_manifest'] = save_json(OUT / (name + '-copied-manifest.json'), copied, state)
                except BaseException as error:
                    note_error(report, 'source-tree-after', error, source)
            try:
                require(source_checks_completed and teto_before is not None and modes is not None, 'Teto source observation incomplete')
                again = tree_inventory(TETO, state, skip_root_git=True)
                require(again == teto_before, 'Teto source contents or identities changed during input copy')
                verify_teto(again, preparation, modes)
                modes_after, mode_pin_after = held_bytes(TETO_PARENT / 'engine-working-mode-manifest.json', 65536, state)
                head_after, head_pin_after = held_bytes(TETO / '.git/HEAD', 128, state)
                require(mode_pin_after == report['Teto_mode_authority'] and head_pin_after == report['Teto_HEAD_authority'] and
                        json.loads(modes_after) == modes and head_after == (TETO_HEAD + '\n').encode(), 'Teto HEAD/modes authority changed')
                report['Teto_source_and_authorities_unchanged_after'] = True
            except BaseException as error:
                note_error(report, 'Teto-after', error)
            try:
                names = set(os.listdir(directory(WORK, state)))
                require(names == {'base-system', 'framework-res.apk', 'mesa-source', 'python'},
                        'new work contains an unexpected entry or fake materialization')
                report['new_work_exact_top_level'] = sorted(names)
                report['new_work_identity'] = full_identity(os.fstat(directory(WORK, state)))
                report['filesystem_available_after'] = os.fstatvfs(directory(WORK, state)).f_bavail * os.fstatvfs(directory(WORK, state)).f_frsize
            except BaseException as error:
                note_error(report, 'work-after', error)
        try:
            remaining = (Path('/proc/self/task') / str(os.getpid()) / 'children').read_text().strip()
            report['cleanup'] = {'subprocesses_started': 0, 'remaining_children': remaining, 'forced_cleanup': False}
            require(remaining == '', 'unexpected child appeared in copy-only controller')
        except BaseException as error:
            note_error(report, 'child-after', error)
        try:
            require(resource_fd >= 0 and resource_before is not None, 'owned resources not admitted')
            report['owned_resource_gate'] = finish_resources(resource_fd, resource_before, report)
        except BaseException as error:
            report['owned_resource_gate'] = {'pass': False, 'error': error_row(error)}
            note_error(report, 'owned-resources-after', error)
        close_owned(resource_fd, report, 'owned-resource-close')
        for path, (fd, row) in reversed(list(state['directories'].items())):
            try:
                require(directory_identity(os.fstat(fd)) == row['held_before'][:5] == directory_identity(Path(path).lstat()),
                        'held parent identity changed: ' + path)
            except BaseException as error:
                note_error(report, 'directory-after', error, path)
            close_owned(fd, report, 'directory-close', path)
        state['directories'].clear()
        for error in state['early_close_errors']:
            report['secondary_errors'].append(error)
            report['state'] = 'FAIL'
        if report['first_error'] is not None or report['secondary_errors']:
            report['state'] = 'FAIL'
        report['bytes_read_including_copy_checks'] = state['bytes_read']
        report['bytes_copied'] = state['bytes_copied']
        report['finished_utc'] = utc()
        # The result is outside the prepared work. Preserve partial work on failure.
        raw = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
        require(len(raw) <= 1048576, 'preparation result exceeded its fixed bound')
        result_fd = os.open(OUT / 'result.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400)
        try:
            with os.fdopen(result_fd, 'wb', closefd=False) as stream:
                require(stream.write(raw) == len(raw), 'short final preparation write')
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(result_fd)
        print(json.dumps({'state': report['state'], 'result': {'path': str(OUT / 'result.json'), 'bytes': len(raw), 'sha256': sha(raw)},
                          'new_work': str(WORK), 'Main_actions': 0, 'materialize_or_build_invoked': False}), flush=True)
    return 0 if report['state'] == 'PREPARED_INPUTS_NOT_MATERIALIZED_OR_BUILT' else 1


if __name__ == '__main__':
    if sys.argv[1:] == []:
        print(json.dumps(plan()))
    elif sys.argv[1:] == ['--execute-once']:
        sys.exit(execute())
    else:
        raise SystemExit('only default PLAN or exact --execute-once is accepted')
