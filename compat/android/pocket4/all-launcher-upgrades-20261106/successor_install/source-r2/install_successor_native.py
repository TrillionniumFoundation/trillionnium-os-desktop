#!/usr/bin/env python3
"""One explicitly scoped signed App upgrade on an actually qualified successor.

A new immutable request selects one reviewed public candidate.
Revision 2 additionally retains the exact reviewed JD base/split predecessor set. No UI, grants, launch, task claims, ADB, lifecycle or automatic retry.
The native daemon keeps its normal SO_PEERCRED and PackageManager checks.
The original Bili unknown evidence and Meituan location observations are retained.
"""
import sys
sys.dont_write_bytecode=True
import datetime, fcntl, hashlib, json, os, re, selectors, signal, stat, subprocess, time, types
from pathlib import Path
CLI_PATH='/usr/bin/droidloomctl'
CLI_SHA='f81e0223f6b256584d07a5e8fbc72f3f4c764ab53a88469b45b587c101e12c79'
DAEMON_PATH='/usr/bin/droidloomd'
DAEMON_SHA='4c57f3e9e92a39f2aef700d77b56c108a88d9ba3ba3cfe82b2613b363514ef30'
ENV={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TZ':'UTC'}
STAT=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
MAX_OUTPUT=1024*1024
DEPS_SHA='dfe1182d8e0da4d3d6e842736378539df33e03a87cf0ed9ab4bbe9ae1f26c041'
ALLOWED={
 'com.xunmeng.pinduoduo':('home-api.pinduoduo.com',),
 'com.jingdong.app.mall':('apk.360buyimg.com',),
 'com.taobao.taobao':('imtt.dd.qq.com',),
 'com.sdu.didi.psnger':('imtt.dd.qq.com',),
 'ctrip.android.view':('gdown.baidu.com',),
 'tv.danmaku.bili':('dl.hdslb.com',),
 'com.ss.android.ugc.aweme':('imtt.dd.qq.com',),
}
MEITUAN='com.sankuai.meituan.takeoutnew'
UNKNOWN_ROOT='/home/alex/work/pocket4-bilibili-owned-qa-r9-flow-474d7477074ea01fbc986e0d867924c1'
UNKNOWN_FILES={
 'scope.json':(1006,'ac6dea24873125a8ac322306786f9f5760fd20b0f1c8d06bc80a498e33eddc50'),
 'steps/launch-01/result.json':(5202,'037076b15c27611f83815ad243280a1ec8eae82416616c928c9106e17f7a12ca'),
 'steps/launch-01/command-004.stdout':(495,'2957db51935e4687990181acd1e9a395fb24326c4289725b67d2d48724024fc8'),
 'steps/launch-01/prelaunch-stacks.txt':(665,'4828128d5f155cfcbdd15b713ae6430eef36735163ca5ed53dd59a7409670e76'),
}

class Rejected(RuntimeError): pass
def need(value,code):
    if not value:raise Rejected(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def error_record(error):
    return {'code':str(error)[:160] if isinstance(error,Rejected) else type(error).__name__}
class Budget:
    def __init__(self):self.started=time.monotonic();self.deadline=self.started+700
    def check(self):need(time.monotonic()<self.deadline,'INSTALL_WORKER_DEADLINE')

NATIVE_FILE_METADATA = {
    "/usr/bin/droidloomctl": {
        "st_ctime_ns": 1793735282143426356,
        "st_dev": 66306,
        "st_gid": 1000,
        "st_ino": 108004277,
        "st_mode": 33261,
        "st_mtime_ns": 1789132464000000000,
        "st_nlink": 1,
        "st_size": 1705648,
        "st_uid": 1000
    },
    "/usr/bin/droidloomd": {
        "st_ctime_ns": 1793546009221331408,
        "st_dev": 66306,
        "st_gid": 0,
        "st_ino": 108005832,
        "st_mode": 33261,
        "st_mtime_ns": 1793546009220184891,
        "st_nlink": 1,
        "st_size": 1920440,
        "st_uid": 0
    }
}
NATIVE_PARENT_IDENTITIES = {
    "/usr": {
        "st_dev": 66306,
        "st_gid": 0,
        "st_ino": 108003329,
        "st_mode": 16877,
        "st_uid": 0
    },
    "/usr/bin": {
        "st_dev": 66306,
        "st_gid": 0,
        "st_ino": 108003330,
        "st_mode": 16877,
        "st_uid": 0
    }
}
SOCKET_PATH = "/run/droidloom/control.sock"

def read_bootstrap(pin, limit):
    """Read a root-owned, no-symlink request/guard before loading its typed API."""
    need(type(pin) is dict and set(pin) <= {"path", "sha256", "bytes"} and {"path", "sha256"} <= set(pin), "PIN_SCHEMA")
    path = pin["path"]
    need(type(path) is str and path.startswith("/") and all(x not in ("", ".", "..") for x in path[1:].split("/")), "ABSOLUTE_CANONICAL_PATH")
    need(re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]) is not None, "SHA256_REQUIRED")
    fds = []
    try:
        d = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC); fds.append(d)
        parts = path[1:].split("/")
        for part in parts[:-1]:
            d = os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d); fds.append(d)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d); fds.append(fd)
        a = os.fstat(fd)
        need(stat.S_ISREG(a.st_mode) and a.st_uid == 0 and a.st_nlink == 1 and 0 < a.st_size <= limit, "PINNED_ROOT_FILE_BOUND")
        raw, end = bytearray(), time.monotonic() + 10
        while len(raw) <= limit:
            need(time.monotonic() < end, "BOOTSTRAP_READ_DEADLINE")
            part = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        again = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d); fds.append(again)
        need(len(raw) == a.st_size and all(getattr(a, k) == getattr(os.fstat(fd), k) == getattr(os.fstat(again), k) for k in STAT), "BOOTSTRAP_FILE_CHANGED")
        need(sha(raw) == pin["sha256"] and ("bytes" not in pin or len(raw) == pin["bytes"]), "BOOTSTRAP_PIN_CHANGED")
        return bytes(raw)
    finally:
        errors = []
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                errors.append(fd)
        need(not errors, "BOOTSTRAP_FD_CLOSE_FAILED")


def run_command(store, cli_fd, argv, name, seconds, budget, extra_fds=(), *, host_tool_path=None, output_limit=MAX_OUTPUT):
    """One owned host child; never signal Main, daemon, or an observed Android PID."""
    budget.check()
    row = {"name": name, "argv": list(argv), "executable": host_tool_path or CLI_PATH,
           "execution_from_held_cli_fd": host_tool_path is None, "started_utc": now(),
           "automatic_retry": False, "timeout_seconds": seconds,
           "spawned": False, "joined": False, "timed_out": False,
           "group_termination_requested": False, "native_daemon_worker_joined_by_this_client": False}
    proc, error = None, None
    selector, streams = selectors.DefaultSelector(), []
    output = {"stdout": bytearray(), "stderr": bytearray()}
    try:
        proc = subprocess.Popen(argv, executable="/proc/self/fd/" + str(cli_fd),
            pass_fds=(cli_fd, *extra_fds), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=ENV, close_fds=True, start_new_session=True)
        row["spawned"] = True
        row["client_pid"] = proc.pid
        streams = [proc.stdout, proc.stderr]
        for stream_name, stream in zip(("stdout", "stderr"), streams):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, stream_name)
        deadline = min(budget.deadline, time.monotonic() + seconds)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            need(remaining > 0, "NATIVE_CLIENT_TIMEOUT")
            for key, unused in selector.select(min(0.2, remaining)):
                raw = os.read(key.fileobj.fileno(), 65536)
                if not raw:
                    selector.unregister(key.fileobj)
                    continue
                need(len(output[key.data]) + len(raw) <= output_limit, "NATIVE_CLIENT_OUTPUT_BOUND")
                output[key.data].extend(raw)
        proc.wait(timeout=max(0.001, deadline - time.monotonic()))
    except BaseException as failure:
        error = failure
        row["timed_out"] = isinstance(failure, subprocess.TimeoutExpired) or str(failure) == "NATIVE_CLIENT_TIMEOUT"
        if proc is not None and proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
                row["group_termination_requested"] = True
            except ProcessLookupError:
                pass
            except OSError as failure2:
                row["termination_error"] = error_record(failure2)
            try:
                proc.wait(timeout=5)
            except BaseException as failure2:
                row["join_error"] = error_record(failure2)
    finally:
        selector.close()
        for stream in streams:
            stream.close()
        row["joined"] = bool(proc is not None and proc.returncode is not None)
        row["returncode"] = proc.returncode if proc is not None else None
        row["ended_utc"] = now()
        for stream_name, data in output.items():
            row[stream_name] = store.write(name + "." + stream_name, bytes(data))
        if error is not None:
            row["error"] = error_record(error)
        row["output_capture_complete"] = error is None
        store.json(name + ".json", row)
    return bytes(output["stdout"]), row





class Store:
    def __init__(self,core,pool,root):
        core.path_parts(root)
        need(root.startswith('/home/alex/work/pocket4-successor-native-install-20261106-') and root.count('/')==4,
             'NEW_PRIVATE_INSTALL_ROOT_REQUIRED')
        core.create_private_root(root)
        self.core,self.pool,self.path=core,pool,root
        self.fd=core.open_host(pool,root,os.O_RDONLY|os.O_DIRECTORY)
        self.identity=core.metadata(self.fd)
        self.flow=pool.own(os.open('flow.lock',os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=self.fd))
        fcntl.flock(self.flow,fcntl.LOCK_EX|fcntl.LOCK_NB)
    def verify_path(self):
        fd=self.core.open_host(self.pool,self.path,os.O_PATH|os.O_DIRECTORY)
        try:
            current=self.core.metadata(fd)
            need(all(current[k]==self.identity[k]for k in ('st_dev','st_ino','st_mode','st_uid','st_gid')),
                 'OWNED_INSTALL_ROOT_REPLACED')
        finally:self.pool.close(fd)
    def write(self,name,raw):
        need(re.fullmatch(r'[A-Za-z0-9_.-]{1,120}',name) is not None and name not in ('.','..'),'CLOSED_OUTPUT_NAME')
        fd=self.pool.own(os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o400,dir_fd=self.fd))
        try:
            todo=memoryview(raw)
            while todo:
                n=os.write(fd,todo);need(n>0,'OUTPUT_WRITE_PROGRESS');todo=todo[n:]
            os.fsync(fd)
        finally:self.pool.close(fd)
        os.fsync(self.fd);pin={'path':self.path+'/'+name,'bytes':len(raw),'sha256':sha(raw)}
        need(self.core.pinned_record(pin,max(1,len(raw)))==raw,'OUTPUT_READBACK')
        return pin
    def json(self,name,value):return self.write(name,canonical(value)+b'\n')
    def copy(self,name,source,expected,budget):
        self.verify_path();before=self.core.metadata(source)
        need(before['st_size']==expected['bytes'],'COPY_SIZE_CHANGED')
        target=self.pool.own(os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o400,dir_fd=self.fd))
        h,count=hashlib.sha256(),0;os.lseek(source,0,os.SEEK_SET)
        try:
            while True:
                budget.check();block=os.read(source,65536)
                if not block:break
                count+=len(block);need(count<=expected['bytes'],'COPY_BYTE_BOUND');h.update(block)
                todo=memoryview(block)
                while todo:
                    n=os.write(target,todo);need(n>0,'APK_COPY_PROGRESS');todo=todo[n:]
            need(count==expected['bytes'] and h.hexdigest()==expected['sha256'] and self.core.metadata(source)==before,
                 'COPY_SOURCE_BYTES_OR_IDENTITY_CHANGED')
            os.fsync(target)
        finally:self.pool.close(target)
        os.fsync(self.fd)
        held=self.pool.own(os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.fd))
        value=self.core.hash_fd(held,512*1024*1024,min(budget.deadline,time.monotonic()+60))
        need(value['bytes']==expected['bytes'] and value['sha256']==expected['sha256'],'PRIVATE_APK_COPY_READBACK')
        return held,{'path':self.path+'/'+name,**value}

def original_unknown(core):
    for name,(size,digest)in UNKNOWN_FILES.items():
        core.pinned_record({'path':UNKNOWN_ROOT+'/'+name,'bytes':size,'sha256':digest})
    need(not any(os.path.lexists(UNKNOWN_ROOT+'/'+name)for name in
         ('launch-scope.json','reconciliations/launch-01.json')),'ORIGINAL_UNKNOWN_SCOPE_CHANGED')

def user_data_path(kind,package):
    need(kind in ('user','user_de'),'CLOSED_USER_DATA_KIND')
    need(package in ALLOWED,'REVIEWED_PACKAGE_REQUIRED')
    return '/data/'+kind+'/0/'+package

def protected_location(core,pool,held,apps):
    rows=[]
    for path in core.A.PERMISSION_PATHS:
        try:raw,_=core.guest_read(pool,held.roots['android_init'],path,2*1024*1024)
        except FileNotFoundError:
            rows.append({'path':path,'status':'ABSENT'});continue
        projection=core.A.permission_projection(core.A.parse_xml(raw),MEITUAN,apps[MEITUAN]['uid'])
        rows.append({'path':path,'coverage':projection['coverage'],'effective_grant_state':'UNKNOWN',
                     'entries':[x for x in projection['entries']if x['name']in core.A.LOCATION_PERMISSIONS]})
    return rows

def verifier(core,request):
    from urllib.parse import urlsplit
    ref=request['official_verifier'];value=core.parse(core.pinned_record(ref,131072))
    package=request['package'];u=urlsplit(value.get('source_url',''))
    need(u.scheme=='https' and u.hostname in ALLOWED[package] and not u.username,'REVIEWED_PUBLIC_SOURCE_REQUIRED')
    need(value.get('schema')=='pocket4-official-apk-verification-v1' and value.get('package')==package
         and value.get('signature_verified') is True and value.get('held_file_and_path_unchanged') is True
         and value.get('signer_matches_historical_installed_reference') is True
         and value.get('status')=='VERIFIED_OFFICIAL_CANDIDATE_NOT_INSTALLED'
         and value.get('tool_dependencies_sha256')==DEPS_SHA,'EXACT_OFFICIAL_VERIFIER_REQUIRED')
    manifest=value['manifest'];need(manifest['package']==package and type(manifest['version_code'])is int
        and 0<int(manifest['min_sdk'])<=37 and bool(manifest['version_name']),'EXACT_CANDIDATE_MANIFEST')
    need(type(value['signer_certificate_sha256'])is list and len(value['signer_certificate_sha256'])==1,
         'ONE_VERIFIED_SIGNER_REQUIRED')
    commands=value['commands'];need(len(commands)==2 and {c['name']for c in commands}=={'apksigner','aapt-badging'},
                                   'EXACT_VERIFIER_COMMANDS')
    outputs=[];directory=ref['path'].rsplit('/',1)[0]
    for cmd in commands:
        need(cmd['joined'] is True and cmd['returncode']==0 and cmd['timed_out'] is False,'VERIFIER_CHILD_FAILED')
        for stream in ('stdout','stderr'):
            p=directory+'/'+cmd['name']+'.'+stream
            data,_=core.host_read(p,1024*1024,cmd[stream+'_sha256'])
            outputs.append({'path':p,'bytes':len(data),'sha256':sha(data)})
    return value,outputs


REVIEWED_JD_OLD_APKS = {
    'base.apk': (112144038, 'd74313ab4c41e2a1dfde6ec3369636b4d5c3e3ee2dbc10667f539e10b103b622'),
    'split_config.arm64_v8a.apk': (182245069, '43d863966a005b885c5e70e36546b92f7ffde4125a651dcb067e2000baf4c3e7'),
}
DEPS_PATH = '/home/alex/work/pocket4-app-identities-20261105-r12-01/dependencies.json'


def reviewed_previous_apks(package, current):
    """The only additional old APK-set shape admitted by this revision is exact JD."""
    need(current['package'] == package and type(current['uid']) is int and
         10000 <= current['uid'] < 100000, 'REVIEWED_USER_ZERO_STANDALONE_APP_REQUIRED')
    apks = current['apks']
    need(type(apks) is list and len(apks) in (1, 2), 'REVIEWED_PREVIOUS_APK_SET_REQUIRED')
    names = [Path(apk['path']).name for apk in apks]
    need(len(set(names)) == len(names) and
         all(str(Path(apk['path']).parent) == current['code_path'] for apk in apks),
         'PREVIOUS_APK_SET_PATHS_DIFFER')
    if len(apks) == 1:
        need(names == ['base.apk'], 'REVIEWED_SINGLE_BASE_APK_REQUIRED')
    else:
        need(package == 'com.jingdong.app.mall' and current['uid'] == 10126 and
             current['version_code'] == 102810 and set(names) == set(REVIEWED_JD_OLD_APKS),
             'ONLY_EXACT_REVIEWED_JD_BASE_SPLIT_SET_ALLOWED')
        for apk, name in zip(apks, names):
            need((apk['bytes'], apk['sha256']) == REVIEWED_JD_OLD_APKS[name],
                 'REVIEWED_JD_PREVIOUS_APK_BYTES_DIFFER')
    return sorted(apks, key=lambda apk: Path(apk['path']).name)


def complete_single_apk_manifest(raw):
    """Read the existing aapt xmltree output; never infer completeness from badging."""
    text = raw.decode('utf-8', 'strict')
    lines = text.splitlines()
    elements = []
    for number, line in enumerate(lines):
        if line.lstrip().startswith('E:'):
            match = re.fullmatch(r'( *)E: ([A-Za-z_][A-Za-z0-9_.:-]*) \(line=\d+\)', line)
            need(match is not None, 'MANIFEST_ELEMENT_OUTPUT_NOT_DECODED')
            elements.append((number, len(match[1]), match[2]))
    need(elements and elements[0][2] == 'manifest' and
         all(depth > elements[0][1] for _, depth, _ in elements[1:]),
         'ONE_COMPLETE_MANIFEST_ROOT_REQUIRED')
    need(not any(name.rsplit(':', 1)[-1] == 'uses-split' for _, _, name in elements),
         'COMPLETE_CANDIDATE_MUST_NOT_REQUIRE_USES_SPLIT')
    end = elements[1][0] if len(elements) > 1 else len(lines)
    attributes = {}
    for line in lines[elements[0][0]+1:end]:
        if not line.lstrip().startswith('A:'):
            continue
        match = re.fullmatch(r'\s+A: ([A-Za-z_][A-Za-z0-9_.:-]*)(?:\(0x[0-9a-fA-F]+\))?=(.*)', line)
        need(match is not None, 'MANIFEST_ROOT_ATTRIBUTE_NOT_DECODED')
        name = match[1].rsplit(':', 1)[-1]
        need(name not in attributes, 'DUPLICATE_MANIFEST_ROOT_ATTRIBUTE')
        attributes[name] = match[2]
    need('package' in attributes and not {'split', 'configForSplit'} & set(attributes),
         'COMPLETE_CANDIDATE_MUST_NOT_BE_SPLIT')
    for flag in ('isFeatureSplit', 'isSplitRequired'):
        if flag in attributes:
            match = re.fullmatch(r'\(type 0x12\)0x([0-9a-fA-F]+)', attributes[flag])
            need(match is not None and int(match[1], 16) == 0,
                 'COMPLETE_CANDIDATE_MUST_NOT_REQUEST_SPLITS')
    return {'schema': 'pocket4-complete-single-apk-manifest-v1',
            'manifest_root_observed': True, 'split_marker_absent': True,
            'uses_split_element_absent': True, 'feature_split_not_requested': True,
            'required_splits_not_requested': True, 'element_count': len(elements),
            'root_attribute_names': sorted(attributes)}


def complete_manifest_command(raw, command):
    need(command['spawned'] and command['joined'] and command['returncode'] == 0 and
         not command['timed_out'] and command['output_capture_complete'] and 'error' not in command,
         'CANDIDATE_MANIFEST_TOOL_NOT_COMPLETE')
    return complete_single_apk_manifest(raw)


def prove_complete_candidate(core, pool, store, candidate_fd, candidate, budget, result):
    """One read-only host aapt call on the already held, verified private candidate."""
    deps_ref = {'path': DEPS_PATH, 'sha256': DEPS_SHA}
    deps = core.parse(core.pinned_record(deps_ref, 262144))
    pin = deps['files']['aapt']
    need(str(Path(pin['declared_path']).resolve()) == pin['resolved_path'],
         'EXISTING_AAPT_RESOLUTION_CHANGED')
    tool = core.open_host(pool, pin['resolved_path'])
    observed = core.hash_fd(tool, 32*1024*1024, min(budget.deadline, time.monotonic()+30))
    need(observed['bytes'] == pin['bytes'] and observed['sha256'] == pin['sha256'],
         'EXISTING_AAPT_BYTES_CHANGED')
    expected = {key: candidate[key] for key in ('bytes', 'sha256', 'file')}
    need(core.hash_fd(candidate_fd, 512*1024*1024, min(budget.deadline, time.monotonic()+60)) == expected,
         'PRIVATE_CANDIDATE_CHANGED_BEFORE_MANIFEST')
    argv = (pin['resolved_path'], 'dump', 'xmltree',
            '/proc/self/fd/'+str(candidate_fd), 'AndroidManifest.xml')
    raw, command = run_command(store, tool, argv, 'candidate-manifest', 60, budget,
        extra_fds=(candidate_fd,), host_tool_path=pin['resolved_path'], output_limit=4*1024*1024)
    result['commands'].append(command)
    need(core.hash_fd(tool, 32*1024*1024, min(budget.deadline, time.monotonic()+30)) == observed,
         'EXISTING_AAPT_CHANGED_DURING_MANIFEST')
    current = core.open_host(pool, pin['resolved_path'])
    try:
        need(core.metadata(current) == observed['file'], 'EXISTING_AAPT_PATH_CHANGED')
    finally:
        pool.close(current)
    need(str(Path(pin['declared_path']).resolve()) == pin['resolved_path'],
         'EXISTING_AAPT_RESOLUTION_CHANGED_AFTER_MANIFEST')
    core.pinned_record(deps_ref, 262144)
    need(core.hash_fd(candidate_fd, 512*1024*1024, min(budget.deadline, time.monotonic()+60)) == expected,
         'PRIVATE_CANDIDATE_CHANGED_DURING_MANIFEST')
    current = core.open_host(pool, candidate['path'])
    try:
        need(core.metadata(current) == expected['file'], 'PRIVATE_CANDIDATE_PATH_CHANGED')
    finally:
        pool.close(current)
    return {**complete_manifest_command(raw, command), 'tool_dependencies': deps_ref,
            'tool': {'pin': pin, 'observed': observed}, 'raw_stdout': command['stdout'],
            'raw_stderr': command['stderr'], 'candidate': candidate,
            'Android_commands': 0, 'candidate_bytes_and_path_unchanged': True}


def native_bind(core,pool,held):
    files={};pins={}
    for path in NATIVE_PARENT_IDENTITIES:
        fd=core.open_host(pool,path,os.O_PATH|os.O_DIRECTORY)
        try:need(all(core.metadata(fd)[k]==v for k,v in NATIVE_PARENT_IDENTITIES[path].items()),'NATIVE_PARENT_CHANGED')
        finally:pool.close(fd)
    for path in (CLI_PATH,DAEMON_PATH):
        fd=core.open_host(pool,path);files[path]=fd
        need(core.metadata(fd)==NATIVE_FILE_METADATA[path],'EXACT_MEASURED_NATIVE_METADATA_CHANGED')
        pins[path]=core.hash_fd(fd,32*1024*1024,time.monotonic()+15)
        need(pins[path]['sha256']==(CLI_SHA if path==CLI_PATH else DAEMON_SHA),'NATIVE_BINARY_CHANGED')
    need(core.metadata(held.exes['daemon'])==core.metadata(files[DAEMON_PATH]),'RUNNING_DAEMON_DIFFERS_FROM_PINNED_PATH')
    sock=core.open_host(pool,SOCKET_PATH,os.O_PATH);files[SOCKET_PATH]=sock
    meta=core.metadata(sock);need(stat.S_ISSOCK(meta['st_mode']) and meta['st_uid']==0,'ROOT_NATIVE_SOCKET_REQUIRED')
    pins[SOCKET_PATH]={'file':meta}
    return files,pins

def recheck_native(core,pool,held,files,pins):
    for path,fd in files.items():
        need(core.metadata(fd)==pins[path]['file'],'HELD_NATIVE_FILE_CHANGED')
        check=core.open_host(pool,path,os.O_PATH)
        try:need(core.metadata(check)==pins[path]['file'],'NATIVE_PATH_REPLACED')
        finally:pool.close(check)
    need(core.metadata(held.exes['daemon'])==pins[DAEMON_PATH]['file'],'DAEMON_EXECUTABLE_CHANGED')

def response(core,raw,command,owner):
    need(command['spawned'] and command['joined'] and command['returncode']==0 and not command['timed_out']
         and command['output_capture_complete'] and 'error'not in command,'NATIVE_COMMAND_NOT_COMPLETE')
    value=core.parse(raw);need(value.get('ok')is True and value.get('state')=='running'
         and value.get('host_pid')==owner and not value.get('outcome_unknown',False),'NATIVE_RESPONSE_OWNER_CHANGED')
    return value

def validate_request(request):
    need(type(request)is dict,'REQUEST_OBJECT_REQUIRED')
    need(set(request)=={'schema','guard','app_scope','package','official_verifier','verifier_terminal',
         'output_root','coordination'},'CLOSED_INSTALL_REQUEST')
    need(request['schema']=='pocket4-successor-single-native-upgrade-v1' and request['package']in ALLOWED,
         'REVIEWED_PACKAGE_REQUIRED')
    need(request['coordination']=={'unresolved_native_install_jobs':[],'single_coordinator':True},
         'NO_UNSETTLED_NATIVE_INSTALL_ALLOWED')

def run(request):
    validate_request(request);need(os.getuid()==os.geteuid()==0,'ROOT_REQUIRED')
    raw=read_bootstrap(request['guard'],65536);guard=types.ModuleType('actual_successor_install_guard')
    guard.__file__=request['guard']['path'];exec(compile(raw,guard.__file__,'exec'),guard.__dict__)
    core=guard._core();pool,leases=core.FDs(),core.FDs();budget=Budget()
    result={'schema':'pocket4-successor-native-upgrade-result-v1','package':request['package'],'started_utc':now(),
        'install_verified':False,'action_attempted':False,'outcome_unknown':False,'automatic_retry':False,
        'UI_actions':0,'permission_grants':0,'ADB_commands':0,'lifecycle_commands':0,
        'business_data_content_reads':0,'business_ready':False,'production_ready':False,'commands':[],'errors':[]}
    store=held=None;phase='qualified_runtime'
    try:
        core.acquire_lock(leases,core.ACTION_LOCK)
        result['guard_before']=guard.current_guard();need(result['guard_before']['schema']=='pocket4-successor-main-guard-v1',
                                                        'TYPED_SUCCESSOR_GUARD_REQUIRED')
        baseline=guard.current_baseline();expected=baseline['runtime']['held']['process_snapshot']['binding']
        held=core.HeldProcesses(pool,{name:row['host_pid']for name,row in expected['processes'].items()})
        need(held.before['binding']==expected,'EXACT_SUCCESSOR_PROCESS_BINDING')
        core.verify_runtime(pool,held,baseline['runtime']);original_unknown(core)
        scope=core.parse(core.pinned_record(request['app_scope']))
        need(scope['schema']=='pocket4-versioned-app-scope-v1' and scope['runtime_epoch_sha256']==baseline['runtime_epoch_sha256']
             and request['package']in scope['apps'] and MEITUAN in scope['apps'] and len(scope['apps'])==46,
             'CURRENT_COMPLETE_REVIEWED_APP_SCOPE_REQUIRED')
        packages=sorted(scope['apps']);guard.check_app_scope(request['app_scope'],packages)
        before=core.app_scope(pool,held,packages);need(core.app_bytes(before)==core.app_bytes(scope['apps']),'APP_CONTENT_CHANGED')
        package=request['package'];current=before[package];candidate,logs=verifier(core,request)
        terminal=core.parse(core.pinned_record(request['verifier_terminal'],65536))
        need(terminal.get('state')=='succeeded' and terminal.get('exit_code')==0
             and all(terminal.get(k)is True for k in ('output_complete','output_durable','terminal_publication_confirmed')),
             'ACTUAL_VERIFIER_TERMINAL_REQUIRED')
        need(candidate['manifest']['version_code']>current['version_code'],'STRICTLY_NEWER_OFFICIAL_CANDIDATE_REQUIRED')
        need(current['package_manager_certificate_sha256']==candidate['signer_certificate_sha256'],
             'CURRENT_OFFICIAL_SIGNER_MISMATCH_NO_UNINSTALL_OR_RESIGN')
        previous_apks=reviewed_previous_apks(package,current)
        candidate_fd=core.open_host(pool,candidate['apk']['path'])
        need(core.metadata(candidate_fd)==candidate['apk']['stat'],'VERIFIED_CANDIDATE_STAT_CHANGED')
        cbytes=core.hash_fd(candidate_fd,512*1024*1024,min(budget.deadline,time.monotonic()+60))
        need(all(cbytes[k]==candidate['apk'][k]for k in ('bytes','sha256')),'VERIFIED_CANDIDATE_BYTES_CHANGED')
        data={}
        for kind,identity in current['data_directories'].items():
            need(identity['status']=='PRESENT','EXISTING_APP_DATA_DIRECTORY_REQUIRED')
            path=user_data_path(kind,package);fd=pool.own(core.H.open_in_root(held.roots['android_init'],path,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW))
            st=os.fstat(fd);row={k:getattr(st,k)for k in ('st_dev','st_ino','st_mode','st_uid','st_gid')}
            need((row['st_dev'],row['st_ino'],row['st_uid'],row['st_gid'])==
                 (identity['device'],identity['inode'],identity['uid'],identity['gid']),'CURRENT_DATA_IDENTITY_CHANGED')
            data[kind]={'path':path,'fd':fd,'stat':row}
        def recheck_data():
            for kind,row in data.items():
                current_meta=core.metadata(row['fd']);need(all(current_meta[k]==v for k,v in row['stat'].items()),'HELD_APP_DATA_CHANGED')
                pathfd=pool.own(core.H.open_in_root(held.roots['android_init'],row['path'],os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW))
                try:need(all(core.metadata(pathfd)[k]==v for k,v in row['stat'].items()),'APP_DATA_PATH_REPLACED')
                finally:pool.close(pathfd)
        location=protected_location(core,pool,held,before)
        native,native_pins=native_bind(core,pool,held);owner=expected['processes']['launcher']['host_pid']
        phase='immutable_install_scope'
        store=Store(core,leases,request['output_root'])
        result['request_artifact']=store.json('request.json',request)
        source_raw=core.host_read(str(Path(__file__).resolve()),131072)[0]
        result['worker_source']=store.write('worker-source.py',source_raw)
        previous_bytes=sum(apk['bytes']for apk in previous_apks)
        available=os.fstatvfs(store.fd);need(available.f_bavail*available.f_frsize>=previous_bytes+candidate['apk']['bytes']+32*1024*1024,
                                         'SPACE_FOR_COMPLETE_OLD_AND_NEW_APK_SET_REQUIRED')
        result['previous_apks_retained']=[]
        for apk in previous_apks:
            old_fd=pool.own(core.H.open_in_root(held.roots['android_init'],apk['path'],os.O_RDONLY|os.O_NOFOLLOW))
            need(core.metadata(old_fd)==apk['file'],'PREVIOUS_APK_HELD_STAT_CHANGED')
            old_copy,retained=store.copy('previous-'+Path(apk['path']).name,old_fd,apk,budget)
            result['previous_apks_retained'].append({'original':apk,'retained':retained})
            leases.close(old_copy)
        result['previous_complete_APK_set_retained']=len(result['previous_apks_retained'])==len(current['apks'])
        result['previous_complete_APK_set_bytes']=previous_bytes
        staged,result['private_candidate_apk']=store.copy('candidate-base.apk',candidate_fd,candidate['apk'],budget)
        result['complete_candidate_manifest']=prove_complete_candidate(core,pool,store,staged,result['private_candidate_apk'],budget,result)
        result['before']=current;result['data_before']={k:v['stat']for k,v in data.items()}
        result['official_verifier']=request['official_verifier'];result['verifier_outputs']=logs
        result['meituan_location_before']=location
        for label,argv,seconds in (
             ('native-install-help',(CLI_PATH,'install','--help'),10),
             ('native-status-before',(CLI_PATH,'--socket',SOCKET_PATH,'--json','status'),15)):
            raw,cmd=run_command(store,native[CLI_PATH],argv,label,seconds,budget);result['commands'].append(cmd)
            if label=='native-install-help':
                need(cmd['joined'] and cmd['returncode']==0 and cmd['output_capture_complete'] and b'<APK>'in raw and b'--user'in raw,'LIVE_INSTALL_INTERFACE_REQUIRED')
            else:result['native_before']=response(core,raw,cmd,owner)
        guard.check_app_scope(request['app_scope'],packages);recheck_data();recheck_native(core,pool,held,native,native_pins)
        need(guard.current_guard()==result['guard_before'],'PRE_INSTALL_GUARD_CHANGED')
        original_unknown(core);store.verify_path()
        install_scope={'schema':'pocket4-successor-explicit-install-scope-v2','runtime_epoch_sha256':baseline['runtime_epoch_sha256'],
            'framework_epoch_sha256':baseline['framework_epoch']['sha256'],'guard':request['guard'],'parent_app_scope':request['app_scope'],
            'package':package,'android_user':0,'uid':current['uid'],'from_version_code':current['version_code'],
            'to_version_code':candidate['manifest']['version_code'],'old_apks':previous_apks,
            'retained_old_apks':result['previous_apks_retained'],'complete_candidate_manifest':result['complete_candidate_manifest'],
            'candidate':result['private_candidate_apk'],'official_verifier':request['official_verifier'],
            'native_artifacts':native_pins,'data_directories':result['data_before'],
            'only_mutation':'one_normal_native_signed_package_update','UI_admitted':False,'permission_grants_admitted':False,
            'lifecycle_actions_admitted':False,'old_unknown_launch_replayed':False}
        result['scope']=store.json('scope.json',install_scope)
        argv=(CLI_PATH,'--socket',SOCKET_PATH,'--json','install','/proc/self/fd/'+str(staged),'--user','0')
        store.json('intent.json',{'scope':result['scope'],'argv':list(argv),'automatic_retry':False,'created_utc':now(),
                                 'may_have_been_attempted_if_final_receipt_missing':True})
        phase='single_native_install';result['action_attempted']=result['outcome_unknown']=True
        raw,cmd=run_command(store,native[CLI_PATH],argv,'native-install',260,budget,extra_fds=(staged,))
        result['commands'].append(cmd);result['native_install_response']=response(core,raw,cmd,owner)
        phase='fresh_installed_readback'
        need(guard.current_guard(action_attempted=True)==result['guard_before'],'POST_INSTALL_RUNTIME_CHANGED')
        held.verify();recheck_data();recheck_native(core,pool,held,native,native_pins)
        after=core.app_scope(pool,held,packages);updated=after[package]
        need(updated['uid']==current['uid'] and updated['version_code']==candidate['manifest']['version_code']
             and updated['package_manager_certificate_sha256']==candidate['signer_certificate_sha256']
             and updated['data_directories']==current['data_directories'] and len(updated['apks'])==1,
             'POST_INSTALL_PACKAGE_OR_DATA_IDENTITY_DIFFERS')
        need(all(updated['apks'][0][k]==candidate['apk'][k]for k in ('bytes','sha256')),'INSTALLED_OFFICIAL_BYTES_DIFFER')
        before_others={k:v for k,v in before.items()if k!=package};after_others={k:v for k,v in after.items()if k!=package}
        need(core.app_bytes(before_others)==core.app_bytes(after_others),'NON_TARGET_APP_IDENTITY_CHANGED')
        after_location=protected_location(core,pool,held,after);need(after_location==location,'MEITUAN_LOCATION_OBSERVATION_CHANGED')
        need(core.hash_fd(staged,512*1024*1024,min(budget.deadline,time.monotonic()+60))==
             {k:result['private_candidate_apk'][k]for k in ('bytes','sha256','file')},'PRIVATE_CANDIDATE_CHANGED')
        recheck_data();held.verify();original_unknown(core)
        result['guard_after']=guard.current_guard(action_attempted=True)
        need(result['guard_after']==result['guard_before'],'FINAL_RUNTIME_GUARD_CHANGED')
        next_scope={'schema':'pocket4-versioned-app-scope-v1','kind':'actual-single-native-signed-update',
            'runtime_epoch_sha256':baseline['runtime_epoch_sha256'],'apps':after,'parent_app_scope':request['app_scope'],
            'install_scope':result['scope'],'UI_or_install_runtime_admitted':False,'fresh_signature_verification_performed':True}
        result['next_app_scope']=store.json('app-scope-after.private.json',next_scope)
        guard.check_app_scope(result['next_app_scope'],packages)
        result.update(after=updated,data_after={k:v['stat']for k,v in data.items()},meituan_location_after=after_location,
            data_directory_identity_retained=True,non_target_packages_unchanged=True,
            new_installed_bytes_readback_verified=True,native_artifacts_unchanged=True,
            old_unknown_evidence_preserved=True,install_verified=True,outcome_unknown=False)
    except BaseException as error:
        result['errors'].append({'phase':phase,**error_record(error)});result['install_verified']=False
        result['outcome_unknown']=result['action_attempted']
    finally:
        if store is not None:
            try:store.json('operation-result.json',result)
            except BaseException as error:
                result['errors'].append({'phase':'operation_receipt',**error_record(error)});result['install_verified']=False
        for label,group in (('observation_fds',pool),('lease_fds',leases)):
            try:group.close_all()
            except BaseException as error:
                result['errors'].append({'phase':label,**error_record(error)});result['install_verified']=False
            result[label]=group.summary()
        result['outcome_unknown']=bool(result['action_attempted'] and not result['install_verified'])
        result['ended_utc']=now()
        result['status']='INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING' if result['install_verified'] else (
            'INSTALL_OUTCOME_UNKNOWN_NO_RETRY' if result['action_attempted'] else 'REJECTED_BEFORE_INSTALL')
    return publish_final_receipt(core,store,result)

def publish_final_receipt(core,store,result):
    """A late receipt failure retains possible mutation; never becomes entry rejection."""
    if store is not None:
        try:
            result['final_receipt']=core.write_new(store.path+'/result.json',canonical(result)+b'\n')
        except BaseException as error:
            result['errors'].append({'phase':'final_receipt',**error_record(error)})
            result['install_verified']=False
            result['outcome_unknown']=bool(result['action_attempted'])
            result['status']='INSTALL_OUTCOME_UNKNOWN_NO_RETRY' if result['action_attempted'] else 'REJECTED_BEFORE_INSTALL'
    return result

def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',required=True);parser.add_argument('--request-sha256',required=True);args=parser.parse_args()
    os.umask(0o077)
    entered=False
    try:
        raw=read_bootstrap({'path':args.request,'sha256':args.request_sha256},262144)
        def pairs(items):
            result={}
            for k,v in items:
                need(k not in result,'DUPLICATE_REQUEST_KEY');result[k]=v
            return result
        def invalid(value):raise Rejected('NONFINITE_REQUEST_NUMBER')
        request=json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)
        validate_request(request);entered=True;result=run(request)
    except BaseException as error:
        result={'schema':'pocket4-successor-install-entry-rejection-v1','install_verified':False,
            'action_attempted':None if entered else False,'action_may_have_been_attempted':entered,
            'outcome_unknown':entered,'automatic_retry':False,'error':error_record(error)}
    print(json.dumps(result,sort_keys=True,separators=(',',':')),flush=True)
    return 0 if result.get('install_verified') else 1
if __name__=='__main__':raise SystemExit(main())
