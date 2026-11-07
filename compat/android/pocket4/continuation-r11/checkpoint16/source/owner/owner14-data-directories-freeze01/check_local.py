"""Local, owned-child transport controls only. No image/debugfs/Hepta execution."""
import ast
import base64
import copy
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import types

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('owner14_fixed_directory_reader', HERE/'read_directories.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
rows = []


def case(name, body):
    started = time.monotonic()
    body()
    rows.append({'name':name, 'passed':True, 'seconds':time.monotonic()-started})


def child(code, seconds=2.0):
    process = subprocess.Popen([sys.executable,'-I','-B','-c',code],
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True)
    try:
        row = m.collect_owned(process,time.monotonic()+seconds)
        assert row['joined'] and process.returncode is not None
        assert process.stdout.closed and process.stderr.closed
        assert process.wait(timeout=0.1) == row['returncode']
        for name in ('stdout','stderr'):
            raw=base64.b64decode(row[name]['base64'],validate=True)
            assert len(raw)==row[name]['bytes']
            assert hashlib.sha256(raw).hexdigest()==row[name]['sha256']
        return row
    finally:
        if process.poll() is None:
            process.kill();process.wait(timeout=3)
        process.stdout.close();process.stderr.close()


def normal():
    r=child("import os; os.write(1,b'directory entries\\n'); os.write(2,b'debugfs banner\\n')")
    assert r['capture_complete'] and r['returncode']==0 and r['pidfd_held']
    assert not r['forced_kill'] and r['errors']==[]
    assert base64.b64decode(r['stdout']['base64'])==b'directory entries\n'
    assert base64.b64decode(r['stderr']['base64'])==b'debugfs banner\n'


def nonzero():
    r=child("import os; os.write(2,b'File not found by ext2_lookup\\n'); raise SystemExit(7)")
    assert r['capture_complete'] and r['returncode']==7 and not r['forced_kill']
    assert base64.b64decode(r['stderr']['base64'])==b'File not found by ext2_lookup\n'


def timeout():
    r=child("import os,time; os.write(1,b'prefix'); time.sleep(10)",0.15)
    assert not r['capture_complete'] and r['forced_kill'] and r['returncode']==-9
    assert 'deadline exceeded' in r['first_error']['error']
    assert base64.b64decode(r['stdout']['base64'])==b'prefix'


def overflow(name, fd, limit):
    r=child('import os; os.write('+str(fd)+",b'x'*"+str(limit+1)+')')
    assert not r['capture_complete'] and r['joined']
    assert name+' byte bound exceeded' in r['first_error']['error']
    assert base64.b64decode(r[name]['base64'])==b'x'*limit
    assert r[name]['eof'] is False


def pidfd_failure():
    original=m.os.pidfd_open
    def fail(pid,flags):raise OSError(24,'controlled pidfd allocation failure')
    m.os.pidfd_open=fail
    try:r=child('import time;time.sleep(10)')
    finally:m.os.pidfd_open=original
    assert not r['capture_complete'] and r['forced_kill'] and r['returncode']==-9
    assert not r['pidfd_held'] and 'controlled pidfd' in r['first_error']['error']


def selector_failure():
    original=m.selectors.DefaultSelector
    def fail():raise OSError(24,'controlled selector allocation failure')
    m.selectors.DefaultSelector=fail
    try:r=child('import time;time.sleep(10)')
    finally:m.selectors.DefaultSelector=original
    assert not r['capture_complete'] and r['forced_kill'] and r['returncode']==-9
    assert 'controlled selector' in r['first_error']['error']


def fixed_argv():
    for path in m.DIRECTORIES:
        argv,exe=m.directory_argv(10,11,path)
        assert argv==['/usr/sbin/debugfs','-R','ls -p '+path,'/proc/self/fd/11']
        assert exe=='/proc/self/fd/10' and '-w' not in argv
    for path in ('/data/tombstones','/etc/passwd','/tombstones;quit','/tombstones\nquit','/tombstones/../system'):
        try:m.directory_argv(10,11,path)
        except RuntimeError:pass
        else:raise AssertionError('non-fixed path admitted')
    for first,second in [(10,10),(1,11),(10,2),(True,11)]:
        try:m.directory_argv(first,second,'/tombstones')
        except RuntimeError:pass
        else:raise AssertionError('wrong authority descriptors admitted')


def actual_metadata():
    actual=json.loads(m.METADATA_RAW)
    m.observation_pin(actual['image'],actual['debugfs'],actual['binding'],actual['records'])
    for group,key,value in [('image','first_4096_sha256','0'*64),('image','ext4_needs_recovery',True),
                            ('debugfs','sha256','0'*64),('binding','invocation','0'*32)]:
        changed=copy.deepcopy(actual);changed[group][key]=value
        try:m.observation_pin(changed['image'],changed['debugfs'],changed['binding'],changed['records'])
        except RuntimeError:pass
        else:raise AssertionError('wrong actual metadata admitted')
    changed=copy.deepcopy(actual);changed['image']['identity']['inode']+=1
    try:m.observation_pin(changed['image'],changed['debugfs'],changed['binding'],changed['records'])
    except RuntimeError:pass
    else:raise AssertionError('wrong image inode admitted')


def wire_exact():
    sample={'collection_complete':False,'first_error':{'error':'original'},
            'stdout':m.stream_record(b'\xff\x00\n',True,32768)}
    output=io.BytesIO();original=m.sys
    m.sys=types.SimpleNamespace(stdout=types.SimpleNamespace(buffer=output))
    try:m.emit(sample)
    finally:m.sys=original
    envelope=json.loads(output.getvalue());compressed=base64.b64decode(envelope['gzip_base64'],validate=True)
    assert len(compressed)==envelope['gzip_bytes'] and hashlib.sha256(compressed).hexdigest()==envelope['gzip_sha256']
    raw=gzip.decompress(compressed)
    assert raw.endswith(b'\n') and len(raw)==envelope['bytes'] and hashlib.sha256(raw).hexdigest()==envelope['sha256']
    assert json.loads(raw)==sample and base64.b64decode(sample['stdout']['base64'])==b'\xff\x00\n'


if __name__=='__main__':
    before=len(os.listdir('/proc/self/fd'))
    case('real_owned_stdout_stderr_and_EOF_exact_exit',normal)
    case('real_owned_tool_nonzero_and_missing_text_retained',nonzero)
    case('real_owned_timeout_forced_exact_reap',timeout)
    case('real_owned_stdout_overflow_prefix_retained',lambda:overflow('stdout',1,m.STDOUT_LIMIT))
    case('real_owned_stderr_overflow_prefix_retained',lambda:overflow('stderr',2,m.STDERR_LIMIT))
    case('real_owned_child_pidfd_failure_seam_still_reaped',pidfd_failure)
    case('real_owned_child_selector_failure_seam_still_reaped',selector_failure)
    case('fixed_two_paths_and_authority_FDs_only',fixed_argv)
    case('actual_metadata_positive_and_five_binding_negatives',actual_metadata)
    case('gzip_and_binary_stream_exact_roundtrip',wire_exact)
    after=len(os.listdir('/proc/self/fd'));assert before==after
    raw=(HERE/'read_directories.py').read_bytes()
    print(json.dumps({'schema':1,'passed':True,'source_bytes':len(raw),
        'source_sha256':hashlib.sha256(raw).hexdigest(),'controls':rows,
        'parent_fd_count_before':before,'parent_fd_count_after':after,
        'real_owned_children':7,'explicit_syscall_failure_seams':['pidfd_open','DefaultSelector'],
        'device_executed':False,'debugfs_executed':False,'image_read_or_written':False,
        'Hepta_called':False,'Owner_qualification':False},sort_keys=True,indent=2))
