#!/usr/bin/env python3
"""Read the observed compatibility wrapper, old init parent, and native owner.
No signal, namespace entry, owner claim, activation, restart, or App action.
"""
import base64, hashlib, json, os, stat, time, types, zlib
from pathlib import Path

SOURCE = Path('/home/alex/work/pocket4-cell-recovery-preflight-20261106-r1/source')
BASE = Path('/home/alex/work/pocket4-cell-successor-20261106-r1')


def read(path, maximum, expected=None):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
    try:
        a=os.fstat(fd);assert stat.S_ISREG(a.st_mode) and a.st_nlink==1 and 0<a.st_size<=maximum
        raw=bytearray();end=time.monotonic()+10
        while len(raw)<=maximum:
            assert time.monotonic()<end
            b=os.read(fd,min(65536,maximum+1-len(raw)))
            if not b:break
            raw.extend(b)
        b=os.fstat(fd);keys=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
        assert len(raw)==a.st_size and all(getattr(a,k)==getattr(b,k)==getattr(os.stat(path,follow_symlinks=False),k) for k in keys)
        sha=hashlib.sha256(raw).hexdigest();assert expected is None or sha==expected
        return bytes(raw),{'path':str(path),'bytes':len(raw),'sha256':sha,'stat':{k:getattr(a,k) for k in keys}}
    finally:os.close(fd)


def main():
    assert os.getuid()==os.geteuid()==0
    raw,_=read(SOURCE/'SOURCE_PINS.json',65536,'b97002660594ad0ef6e7b453927b8c5b19cba49a5873bc133199d790019b1f9f')
    pins=json.loads(raw)['files'];raw,_=read(SOURCE/'successor_runtime.py',65536,pins['successor_runtime.py']['sha256'])
    core=types.ModuleType('readonly_observed_wrapper_diagnostic');core.__file__=str(SOURCE/'successor_runtime.py');exec(compile(raw,core.__file__,'exec'),core.__dict__)
    core.configure(str(SOURCE),'b97002660594ad0ef6e7b453927b8c5b19cba49a5873bc133199d790019b1f9f')
    receipt_raw,receipt_pin=read(BASE/'native-restart-receipt.private.json',65536,'d329733b4073662320f2c8839d8ef43053e095a9429cd810865e7f44daec2733')
    receipt=json.loads(receipt_raw);owner=json.loads(receipt['stdout_utf8'])['host_pid'];assert owner==2747275
    old_raw,old_pin=read(BASE/'predecessor.private.json',1048576,'6b781af9d0d037e14d7f4b3174937f3a101ab4cf313b7c5c34fec1c13df9dec3')
    before=json.loads(old_raw)['runtime']['held']['process_snapshot']['binding'];assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==before['boot_id']
    old_init=before['processes']['android_init'];assert old_init['host_pid']==3588093 and old_init['parent_host_pid']==3588092
    candidates=core.role_candidates()
    exact_pids={'previous_init_parent':3588092,'previous_android_init':3588093,'actual_native_receipt_owner':owner}
    for role,values in candidates.items():
        for index,pid in enumerate(values):exact_pids['diagnostic_'+role+'_'+str(index)]=pid
    observations={}
    for label,pid in exact_pids.items():
        row={'host_pid':pid}
        try:
            first=core.E.process_identity(pid)
            row.update(identity=first,process_state=core.E._stat(pid)[3],process_group=os.getpgid(pid),session=os.getsid(pid),
                immediate_children=core.host_pseudo('/proc/'+str(pid)+'/task/'+str(pid)+'/children',65536).decode(),
                root_identity={'dev':os.stat('/proc/'+str(pid)+'/root').st_dev,'ino':os.stat('/proc/'+str(pid)+'/root').st_ino})
            assert core.E.process_identity(pid)==first
            if label=='previous_android_init':assert first==old_init
        except BaseException as error:row['error']={'type':type(error).__name__,'code':str(error)[:180]}
        observations[label]=row
    wrapper=Path('/usr/local/libexec/droidloom-compat/unshare')
    wrapper_raw,wrapper_pin=read(wrapper,1048576)
    supervisor,_=read('/usr/bin/droidloom-supervisor',32*1024*1024)
    status_out,status_err,status_cmd=core.bounded_child(core.native_argv('status'),10)
    out={'schema':'pocket4-compat-wrapper-and-retired-namespace-readonly-v1','observations':observations,
        'wrapper':{**wrapper_pin,'zlib_base64':base64.b64encode(zlib.compress(wrapper_raw)).decode()},
        'supervisor_path_sha256':hashlib.sha256(supervisor).hexdigest(),
        'actual_restart_receipt':receipt_pin,'original_predecessor':old_pin,
        'current_native_status':{'stdout':status_out.decode(),'stderr':status_err.decode(),'command':status_cmd},
        'read_only_role_candidates_not_runtime_qualification':candidates,
        'Android_commands':0,'namespace_entries':0,'signals':0,'restarts':0,'UI_actions':0,'installs':0,'guard_publication':False}
    read(wrapper,1048576,wrapper_pin['sha256']);read(BASE/'native-restart-receipt.private.json',65536,receipt_pin['sha256'])
    data=json.dumps(out,sort_keys=True,separators=(',',':')).encode();assert len(data)<=262144;print(data.decode(),flush=True)


if __name__=='__main__':main()
