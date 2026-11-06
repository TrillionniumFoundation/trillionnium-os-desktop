"""One fresh owned-helper install and no-UiAutomation state check on R5.

PLAN_ONLY unless --install-once is explicit. The target App is not installed,
started, clicked, granted permissions, or instrumented. No automatic retry,
replacement, uninstall or residual deletion is implemented.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types

HERE = Path(__file__).resolve().parent
SELF = 'org.droidloom.qa.successor.p8f89f253350ba2fa.r2'
RECORDER_MANIFEST_SHA = '646f6e4c7d931bf005ada01a84202a891c95e99e93bbde7a561f3307527008a4'


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, maximum=1048576):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        a = os.fstat(fd)
        need(stat.S_ISREG(a.st_mode) and a.st_nlink == 1 and 0 <= a.st_size <= maximum, 'BOUNDED_SINGLE_INPUT')
        raw = bytearray()
        while len(raw) <= maximum:
            block = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
        def meta(s):
            return tuple(getattr(s, k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))
        need(len(raw) == a.st_size and meta(a) == meta(os.fstat(fd)) == meta(os.stat(path, follow_symlinks=False)), 'HELD_INPUT_CHANGED')
        return bytes(raw)
    finally:
        os.close(fd)


def load(path, pin, name):
    raw = read(path)
    need(sha(raw) == pin, 'MODULE_SOURCE_PIN')
    value = types.ModuleType(name)
    value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def command(flow, argv, timeout=8, mutation=False):
    before = flow.command_index
    raw = flow.android(argv, timeout, mutation=mutation)
    need(flow.command_index == before + 1, 'ONE_HELD_COMMAND_REQUIRED')
    stem = flow.step / ('command-%03d' % flow.command_index)
    receipt = json.loads(read(str(stem) + '.result.json', 65536))
    stderr = read(str(stem) + '.stderr')
    need(receipt['returncode'] == 0 and receipt['spawned'] is True and
         receipt['owned_command_joined'] is True and receipt['timed_out'] is False and
         receipt['errors'] == [] and receipt['stdout_sha256'] == sha(raw) and
         receipt['stderr_sha256'] == sha(stderr) and stderr == b'', 'JOINED_QUIET_HELD_COMMAND_REQUIRED')
    return raw


class Stage:
    def __init__(self, target, nonce):
        self.target = target
        self.fds = []
        self.name = 'pocket4-successor-owned-qa-' + nonce
        self.path = '/data/local/tmp/' + self.name + '/owned-qa.apk'

    def stage(self, data, expected):
        need(sha(data) == expected and 0 < len(data) <= 2097152, 'ACTUAL_NEW_HELPER_APK')
        self.parent = self.target.open_root('/data/local/tmp', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.fds.append(self.parent)
        os.mkdir(self.name, 0o711, dir_fd=self.parent)
        self.directory = os.open(self.name, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=self.parent)
        self.fds.append(self.directory)
        os.fchmod(self.directory, 0o711)
        self.file = os.open('owned-qa.apk', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600, dir_fd=self.directory)
        self.fds.append(self.file)
        rest = memoryview(data)
        while rest:
            n = os.write(self.file, rest)
            need(n > 0, 'OWNED_APK_WRITE_PROGRESS')
            rest = rest[n:]
        os.fchmod(self.file, 0o444)
        os.fsync(self.file)
        os.fsync(self.directory)
        os.fsync(self.parent)
        actual, metadata = self.target.read_file(self.path, len(data), single_link=True)
        held = os.fstat(self.file)
        need(sha(actual) == expected and held.st_uid == 0 and held.st_nlink == 1 and
             (metadata['device'],metadata['inode'],metadata['bytes']) == (held.st_dev,held.st_ino,len(data)), 'OWNED_GUEST_APK_IDENTITY')
        self.record = {'path':self.path,'bytes':len(data),'sha256':expected,'device':held.st_dev,'inode':held.st_ino,
                       'retained_until_reviewed_production_cleanup':True}

    def close(self):
        errors = []
        for fd in reversed(self.fds):
            try:
                os.close(fd)
            except OSError:
                errors.append(fd)
        self.fds = []
        need(not errors, 'OWNED_STAGE_FD_CLOSE_FAILED')


def execute(args):
    need(os.getuid() == os.geteuid() == 0, 'ROOT_HELD_INSTALL_REQUIRED')
    need(re.fullmatch(r'/home/alex/work/pocket4-successor-qa-flow-[0-9a-f]{32}', str(args.flow_dir)) and
         args.flow_dir.resolve() == args.flow_dir and args.recorder_root.resolve() == args.recorder_root and
         re.fullmatch('[0-9a-f]{32}', args.state_nonce), 'NEW_CANONICAL_FLOW_AND_STATE_NONCE')
    source_raw = read(HERE/'SOURCE_PINS.json', 131072)
    need(sha(source_raw) == args.source_manifest_sha256, 'EXTERNAL_HELPER_SOURCE_PIN')
    source = json.loads(source_raw)
    adapter = load(HERE/'qa_adapter.py', source['files']['qa_adapter.py']['sha256'], 'successor_install_adapter')
    source = adapter.own_source(args.source_manifest_sha256)
    qa = adapter.load(HERE/'qa_contract.py',source['files']['qa_contract.py']['sha256'],'successor_install_contract')
    builder = adapter.load(HERE/'build_candidate.py',source['files']['build_candidate.py']['sha256'],'successor_install_build')
    proof = adapter.qualified_build(args,source,builder)
    apk = adapter.pinned(Path(proof['APK']['path']), args.apk_sha256, 2097152)
    need(len(apk) == proof['APK']['bytes'], 'ACTUAL_BUILD_APK_SIZE')
    recorder_source = adapter.pinned(args.recorder_root/'source-manifest.json', RECORDER_MANIFEST_SHA, 131072)
    recorder_manifest = json.loads(recorder_source)
    recorder = load(args.recorder_root/'recorder.py',recorder_manifest['files']['recorder.py']['sha256'],'successor_install_recorder')
    flow_args = types.SimpleNamespace(operation='owned-helper-install', adapter_manifest_sha256=RECORDER_MANIFEST_SHA,
        flow_dir=args.flow_dir, epoch_module=args.recorder_root/'references/framework_epoch.py',
        task_source=args.recorder_root/'references/task_scope_baseline.py', step=args.step,
        request={'package':SELF,'build':proof,'state_nonce':args.state_nonce,'replacement':False},
        unknown_step=None,observation_step=None,postcondition=None)
    result = {'schema':'pocket4-successor-owned-helper-install-v1','ok':False,'package':SELF,'build':proof,
        'install_attempted':False,'install_success_observed':False,'state_attempted':False,
        'UI_actions':0,'permission_grants':0,'App_launches':0,'old_v2_helper_called':False,
        'automatic_retry':False,'production_ready':False,'errors':[]}
    flow = stage = lock = None
    try:
        flow = recorder.Flow(flow_args)
        flow.begin(flow_args, mutation=True)
        lock = recorder.lock_file(recorder.ACTION_LOCK)
        flow.guard()
        held = flow.bind()
        absence = command(flow,['/system/bin/cmd','package','list','packages','-u','-U','--user','all',SELF])
        need(absence == b'', 'NEW_HELPER_OR_RETAINED_PACKAGE_ALREADY_EXISTS')
        stage = Stage(held.target,args.state_nonce)
        stage.stage(apk,args.apk_sha256)
        result['guest_stage'] = stage.record
        del apk
        result['install_attempted'] = True
        output = command(flow,['/system/bin/cmd','package','install','-R','-t','--user','0','--pkg',SELF,stage.path],40,True)
        need(output == b'Success\n','EXACT_NEW_HELPER_INSTALL_SUCCESS_REQUIRED')
        result['install_success_observed'] = True
        uid_raw = command(flow,['/system/bin/cmd','package','list','packages','-U','--user','0',SELF]).decode('utf-8','strict')
        match = re.fullmatch(re.escape('package:'+SELF+' uid:')+r'([0-9]+)\n',uid_raw)
        need(match is not None,'EXACT_INSTALLED_HELPER_UID')
        uid = int(match[1])
        session = adapter.Session(flow,recorder,qa,proof,uid)
        result['installed_before_state'] = session.installed()
        result['state_attempted'] = True
        result['state'] = session.instrument({'protocol':qa.PROTOCOL,'nonce':args.state_nonce,'op':'state'})
        need(result['state']['helper']['ui_automation_connected'] is False,'STATE_MUST_NOT_CONNECT_UIAUTOMATION')
        result['installed_after_state'] = session.installed()
        need(result['installed_after_state'] == result['installed_before_state'],'HELPER_CHANGED_DURING_STATE')
        need(command(flow,['/system/bin/cmd','package','list','packages','-U','--user','all',SELF]).decode('utf-8','strict') == uid_raw,
             'OTHER_USER_OR_UID_APPEARED')
        result.update(ok=True,helper_uid=uid,helper_retained=True)
    except BaseException as error:
        result['errors'].append({'phase':'install_or_state','type':type(error).__name__,'code':str(error)[:256]})
    finally:
        if stage is not None:
            try:
                stage.close()
            except BaseException as error:
                result['errors'].append({'phase':'stage_fd_close','type':type(error).__name__})
        if flow is not None:
            for phase, operation in (('final_runtime_and_app_guard',lambda:flow.guard(attempted=flow.action_attempted)),('held_binding_close',flow.close)):
                try:
                    operation()
                except BaseException as error:
                    result['errors'].append({'phase':phase,'type':type(error).__name__})
        if result['errors']:
            result['ok'] = False
        result['action_attempted'] = bool(flow is not None and flow.action_attempted)
        result['outcome_unknown'] = result['action_attempted'] and not result['ok']
        result['ended_utc'] = recorder.now()
        result['action_lock_held_through_durable_result'] = lock is not None
        try:
            if flow is not None and flow.step is not None:
                recorder.write_new(flow.step/'result.json',result)
        finally:
            if lock is not None:
                os.close(lock)
    print(json.dumps(result,sort_keys=True,ensure_ascii=True),flush=True)
    return 0 if result['ok'] else 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--install-once',action='store_true')
    for name in ('source-manifest-sha256','build-receipt-sha256','apk-sha256','signer-certificate-sha256','state-nonce','step'):
        p.add_argument('--'+name)
    for name in ('build-receipt','recorder-root','flow-dir'):
        p.add_argument('--'+name,type=Path)
    args = p.parse_args()
    if not args.install_once:
        print(json.dumps({'status':'PLAN_ONLY','package':SELF,'replacement':False,'UiAutomation_connection_requested':False}))
        return 0
    os.umask(0o077)
    return execute(args)


if __name__ == '__main__':
    raise SystemExit(main())
