"""Inspect exact current ELFs using bounded, owned readelf children only."""
from pathlib import Path
import ctypes
import hashlib
import importlib.util
import json
import os
import resource
import signal
import stat
import sys
import time

sys.dont_write_bytecode = True
ROOT=Path('/home/qq/work/current2367-cli-preparation-20261120-3b9d-r1')
HEAD='e69efd552c1732e8bb3bf92d191f95648b59e7d5'
CURRENT={'tree':'fd0ef624e436d1eb5c8d2c4083335088811a6a42','files':2367,'bytes':45262277}

def need(ok,message):
    if not ok:raise RuntimeError(message)

def f9(s):
    return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]

def read(path,cap=16*1024**2):
    path=Path(path);need(path.resolve()==path,'canonical source path')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=f9(os.fstat(fd));need(stat.S_ISREG(before[2]) and before[5]==1 and before[6]<=cap,'bounded regular file')
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(cap+1)
        need(len(raw)==before[6] and f9(os.fstat(fd))==f9(path.lstat())==before,'whole original identity')
        return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'identity':before},raw
    finally:os.close(fd)

def module(name,sha):
    path=ROOT/name;reference,raw=read(path);need(reference['sha256']==sha,'original helper hash')
    spec=importlib.util.spec_from_file_location('current_'+path.stem,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    need(read(path)[0]==reference,'helper input unchanged')
    return value,reference

def save(path,value):
    raw=(json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    with os.fdopen(fd,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
    return read(path)[0]

def main():
    need(os.getuid()==os.geteuid()==os.getgid()==1000,'ordinary target account')
    cpus=sorted(os.sched_getaffinity(0));need(18 in cpus and len(cpus)>=3,'reserve two CPUs')
    os.sched_setaffinity(0,{18})
    resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE,(8*1024**2,8*1024**2))
    resource.setrlimit(resource.RLIMIT_CPU,(60,60));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    parser,parser_ref=module('elf_symbols.py','ee7d12c317672046547a5ca7ebb90cd6e30fc3fb9cb3b925d038b21f2bd9cced')
    process,process_ref=module('owned_process.py','c045a56847ff90d8a72b0d72dbb1ee312a02d2a21e14b62ab213ce8a9f3e1d82')
    need(ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0,'owned subreaper')
    need(not process.owned_children(),'no inherited children')
    for signum in (signal.SIGTERM,signal.SIGINT,signal.SIGALRM):signal.signal(signum,process.interrupted)
    signal.alarm(120)
    extraction_ref,raw=read(ROOT/'RELEASE-EXTRACTION.json');extraction=json.loads(raw)
    ci_ref,raw=read(ROOT/'current-ci.json');ci=json.loads(raw)
    need(extraction['passed'] is True and extraction['report']==ci_ref and extraction['head']==HEAD
         and extraction['source']==CURRENT and ci['github_commit']==HEAD and ci['github_run_id']==44732433154,
         'original exact complete source and actual CI release')
    binaries=extraction['binaries'];need(len(binaries)==19 and set(binaries)==set(ci['fresh_release_binaries']),
                                          'nineteen exact original current releases')
    out=ROOT/'binary-inspection';out.mkdir(mode=0o700)
    report={'schema':'p4-current19-actual-static-import-inputs-v1','head':HEAD,'source':CURRENT,
        'binary_count':19,'binaries':[],'commands':[],'needed_sonames':[],
        'inputs':[extraction_ref,ci_ref,parser_ref,process_ref], 'passed':False,'errors':[],
        'started_ns':time.time_ns(),'target_binaries_executed':0,'all_original_children_reaped':False,
        'runtime_qualified':False,'production_ready':False}
    try:
        for name,reference in sorted(binaries.items()):
            got,body=read(ROOT/'bin'/name);need(got==reference,'exact original release binary')
            need(got['bytes']==ci['fresh_release_binaries'][name]['bytes']
                 and got['sha256']==ci['fresh_release_binaries'][name]['sha256']
                 and got['identity'][2]==stat.S_IFREG|0o755 and got['identity'][3:6]==[1000,1000,1],
                 'complete normal release bytes and staging ownership')
            argv=['/usr/bin/readelf','--wide','--program-headers','--dynamic','--dyn-syms',str(ROOT/'bin'/name)]
            stdout,stderr=out/(name+'.stdout'),out/(name+'.stderr');started=time.time_ns()
            with stdout.open('xb') as first,stderr.open('xb') as second:
                observed=process.execute_child(argv,ROOT,{'PATH':'/usr/bin:/bin','LC_ALL':'C','TZ':'UTC'},first,second,5)
            output_ref,output=read(stdout);error_ref,error=read(stderr)
            row={'name':name,'argv':argv,'started_ns':started,'finished_ns':time.time_ns(),
                 **observed,'stdout':output_ref,'stderr':error_ref}
            report['commands'].append(row);save(out/(name+'.command.json'),row)
            need(type(row['exit_code']) is int and row['exit_code']==0 and row['actual_child_reaped'] is True
                 and row['original_pidfd_held_until_reaped'] is True and row['error'] is None
                 and row['timed_out'] is False and not row['cleanup_errors']
                 and not row['owned_descendants_remaining'] and not row['retired_descendants'] and error==b'',
                 'actual readelf execution and original retirement')
            report['binaries'].append({'binary':name,'bytes':got['bytes'],'sha256':got['sha256'],
                                       **parser.executable_imports(output)})
            need(read(ROOT/'bin'/name)[0]==reference,'binary unchanged across original inspection')
        report['needed_sonames']=sorted(set().union(*(set(x['needed']) for x in report['binaries'])))
        need(len(report['needed_sonames'])==8,'same eight direct host library providers')
        for reference in report['inputs']+list(binaries.values()):need(read(Path(reference['path']))[0]==reference,'final input bookend')
        need(not process.owned_children(),'no remaining owned children')
        report['all_original_children_reaped']=report['passed']=True
    except BaseException as error:
        report['errors'].append({'type':type(error).__name__,'message':str(error)})
    finally:
        signal.alarm(0)
        try:
            retired=process.reap_descendants();report['final_retirement']=retired
            if retired or process.owned_children():
                report['passed']=report['all_original_children_reaped']=False
                report['errors'].append({'type':'RetirementError','message':'unexpected final descendant'})
        except BaseException as error:
            report['passed']=report['all_original_children_reaped']=False
            report['errors'].append({'type':type(error).__name__,'message':str(error)})
        report['finished_ns']=time.time_ns();reference=save(ROOT/'BINARY-IMPORTS.json',report)
    print(json.dumps({'passed':report['passed'],'report':reference,'errors':report['errors'],
                      'target_binaries_executed':0}),flush=True)
    return 0 if report['passed'] else 1

if __name__=='__main__':
    raise SystemExit(main())
