#!/usr/bin/env python3
"""Pure discovery-consumer controls; exact private baseline is memory-only."""
import hashlib,json,os,re,signal,stat,sys,time,types
from pathlib import Path
BASELINE_PATH=Path('/home/alex/work/pocket4-main-current-baseline-02/baseline.private.json')
BASELINE_BYTES=44959
BASELINE_SHA='633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364'
PACKET={"bytes":60832,"sha256":"ed68ae07605bbd66372c0aad7f86b4a34b137290530a29c14849b24b5c06809e"}
SOURCE_PINS={"current_discovery.py":{"bytes":8436,"sha256":"dfd1208793980d92664f55aab040042cdc4cdd5e0ec7e66f016e0140d87a58f5"},"check_readiness_discovery.py":{"bytes":13077,"sha256":"5f8ab4febf99a3fd15ecf79c5c6ccdbb17a0569b289bfed6a4910e6f8a64150f"},"references/android_app.py":{"bytes":37574,"sha256":"eb24b1b0eefb275025d10647ccf218f9395b1f74cf6d912aaabf384210d1aa66"}}
def need(value,code):
    if not value:raise RuntimeError(code)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def safe_error(error):
    result={'type':type(error).__name__}
    if isinstance(error,OSError):result['errno']=error.errno
    elif isinstance(error,(RuntimeError,TimeoutError)) and re.fullmatch('[A-Z0-9_]{1,96}',str(error)):
        result['code']=str(error)
    else:result['code']='UNEXPECTED_DIAGNOSTIC_ERROR'
    return result

def read_private_baseline(check,report):
    fds=[];primary=None;errors=[]
    report.update(acquired=0,close_attempts=0,closed=0,remaining=0,errors=[])
    def own(fd):
        if fd<3:
            try:os.close(fd)
            finally:raise RuntimeError('INPUT_FD_ALIASED_STANDARD_STREAM')
        fds.append(fd);report['acquired']+=1;return fd
    try:
        check();directory=own(os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC))
        for part in BASELINE_PATH.parts[1:-1]:
            check();directory=own(os.open(part,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory))
        fd=own(os.open(BASELINE_PATH.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory))
        first=os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_nlink==1 and first.st_uid==0 and
             first.st_size==BASELINE_BYTES,'EXACT_PRIVATE_BASELINE_REGULAR_FILE_REQUIRED')
        raw=b''
        while True:
            check();part=os.read(fd,min(16384,BASELINE_BYTES+1-len(raw)))
            if not part:break
            raw+=part;need(len(raw)<=BASELINE_BYTES,'PRIVATE_BASELINE_BYTE_BOUND')
        last=os.fstat(fd)
        fields=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
        need(all(getattr(first,k)==getattr(last,k) for k in fields) and
             len(raw)==BASELINE_BYTES and sha(raw)==BASELINE_SHA,'EXACT_CURRENT_BASELINE_BYTES_CHANGED')
        return raw
    except BaseException as error:primary=error;raise
    finally:
        for fd in reversed(fds):
            report['close_attempts']+=1
            try:os.close(fd);report['closed']+=1
            except BaseException as error:errors.append(safe_error(error))
        report['remaining']=report['acquired']-report['closed'];report['errors']=errors
        if errors:
            if primary is None:raise RuntimeError('DIAGNOSTIC_INPUT_FD_CLOSE_FAILED')
            primary.add_note('DIAGNOSTIC_INPUT_FD_CLOSE_FAILED')


def execute():
    start=time.monotonic()
    deadline=start+8
    result={'schema':1,'kind':'current-discovery-explicit-readiness-pure-controls',
            'state':'FAIL','controls':None,'first_error':None,'secondary_errors':[],
            'source_pins':SOURCE_PINS,'baseline_input':{'bytes':BASELINE_BYTES,'sha256':BASELINE_SHA},
            'input_fd_journal':{},'private_baseline_exported':False,
            'live_Main_observed':False,'Status_or_Readiness_RPC':0,'Android_actions':0,
            'new_children':0,'filesystem_writes':0,'nonce_consumption':False,
            'action_lock_acquired':False,'installed_binary_changed':False,
            'runtime_qualified':False,'Main_qualified':False}
    def check():
        need(time.monotonic()<deadline,'PURE_CONTROL_DEADLINE')
    def alarm(number,frame):
        raise RuntimeError('PURE_CONTROL_SELF_WATCHDOG')
    signal.signal(signal.SIGALRM,alarm)
    signal.alarm(10)
    try:
        need(os.getuid()==os.geteuid()==0,'FIXED_PRIVATE_BASELINE_READ_REQUIRES_ROOT')
        raw=sys.stdin.buffer.read(PACKET['bytes']+1)
        need(len(raw)==PACKET['bytes'] and sha(raw)==PACKET['sha256'],'EXACT_PURE_CONTROL_PACKET')
        packet=json.loads(raw)
        need(type(packet) is dict and set(packet)=={'schema','files'} and packet['schema']==1 and
             type(packet['files']) is dict and set(packet['files'])==set(SOURCE_PINS),
             'EXACT_THREE_CONTROL_SOURCE_FILES')
        sources={}
        for name,row in SOURCE_PINS.items():
            need(type(packet['files'][name]) is str,'SOURCE_STRING_REQUIRED')
            value=packet['files'][name].encode('utf-8')
            need(len(value)==row['bytes'] and sha(value)==row['sha256'],'PURE_SOURCE_PIN')
            sources[name]=value
        check()
        baseline_raw=read_private_baseline(check,result['input_fd_journal'])
        baseline=json.loads(baseline_raw)
        controls=types.ModuleType('fixed_readiness_discovery_controls')
        controls.__file__='<pure-readiness-discovery-controls>'
        exec(compile(sources['check_readiness_discovery.py'],controls.__file__,'exec'),controls.__dict__)
        report=controls.run_readiness_controls(sources['current_discovery.py'],baseline,
                                               sources['references/android_app.py'])
        check()
        need(report['count']==20 and len(report['cases'])==20 and
             len({x['name'] for x in report['cases']})==20 and
             all(x['passed'] is True for x in report['cases']) and
             report['real_children']==0 and report['Android_actions']==0 and
             report['private_baseline_exported'] is False,'EXACT_TWENTY_PRODUCTION_DISCOVERY_CONTROLS')
        result['controls']=report
        result['state']='PASS'
    except BaseException as error:
        result['first_error']=safe_error(error)
    finally:
        signal.alarm(0)
        result['elapsed_seconds']=time.monotonic()-start
        if result['elapsed_seconds']>=8:
            value={'code':'PURE_CONTROL_DEADLINE'}
            if result['first_error'] is None:result['first_error']=value
            else:result['secondary_errors'].append(value)
            result['state']='FAIL'
        journal=result['input_fd_journal']
        if journal and (journal['remaining'] or journal['errors']):
            result['state']='FAIL'
        result['all_acquired_input_fds_closed']=bool(journal) and journal['remaining']==0 and not journal['errors']
        print(json.dumps(result,sort_keys=True,separators=(',',':')),flush=True)
    return 0 if result['state']=='PASS' else 1

raise SystemExit(execute())
