#!/usr/bin/python3
"""Compile one actual K0a object; never install, link a kernel, or load code."""
from pathlib import Path
import hashlib
import json
import os
import resource
import shlex
import signal
import stat
import subprocess
import time

ROOT=Path('/home/alex/work/p4-private-loop-k0a-compile-20261120-3b9d-r1')
SOURCE=ROOT/'source/linux-6.18.64'
OUT=ROOT/'out'
INPUT=ROOT/'inputs'
RESULT=ROOT/'OBJECT-COMPILE.json'
DEADLINE=None
OBS={'schema':'p4-k0a-matching-kernel-object-compile-v1','state':'PENDING','commands':[],
     'kernel_linked':False,'kernel_loaded':False,'kernel_installed':False,'VM_started':False,
     'Android_started':False,'kernel_runtime_tests_executed':False,
     'runtime_qualified':False,'production_ready':False,'Kbuild_configuration_selection_executed':False}

def need(ok,why):
    if not ok:raise RuntimeError(why)

def f9(s):
    return [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]

def ref(path,pin=None):
    need(path.resolve()==path,'canonical complete input')
    with path.open('rb') as stream:
        before=f9(os.fstat(stream.fileno()))
        need(stat.S_ISREG(before[2]) and before[5]==1,'regular complete input')
        h=hashlib.sha256()
        for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
        need(f9(os.fstat(stream.fileno()))==f9(path.lstat())==before,'complete body bookend')
    row={'path':str(path),'bytes':before[6],'sha256':h.hexdigest(),'identity':before}
    if pin is not None:need(row['bytes']==pin['bytes'] and row['sha256']==pin['sha256'],'exact pinned input: '+str(path))
    return row

def immutable(row):
    need(ref(Path(row['path']))==row,'original input identity changed: '+row['path'])

def run(name,argv,maximum=90):
    out=ROOT/'logs'/(name+'.stdout');err=ROOT/'logs'/(name+'.stderr')
    started=time.monotonic_ns()
    timeout=min(maximum,DEADLINE-time.monotonic())
    need(timeout>0,'single original compile deadline')
    with out.open('xb') as stdout,err.open('xb') as stderr:
        child=subprocess.Popen(argv,cwd=OUT,stdout=stdout,stderr=stderr,start_new_session=True,
            env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
        pidfd=None
        try:
            pidfd=os.pidfd_open(child.pid)
            code=child.wait(timeout=timeout)
        except BaseException:
            # No wait/poll before signalling this still-unreaped original leader.
            try:os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            time.sleep(0.1)
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            child.wait(timeout=10)
            raise
        finally:
            if pidfd is not None:os.close(pidfd)
    row={'name':name,'argv':argv,'pid':child.pid,'exit_code':code,'actual_direct_child_reaped':True,
         'original_pidfd_held_until_reaped':True,'started_ns':started,'finished_ns':time.monotonic_ns(),
         'stdout':ref(out),'stderr':ref(err)}
    OBS['commands'].append(row)
    need(code==0,'actual command failed: '+name)
    return row

def dependencies(path):
    text=path.read_text().replace('\\\n',' ')
    need(':' in text,'actual GCC dependency target')
    words=shlex.split(text.split(':',1)[1])
    values=[]
    for word in words:
        p=Path(word);p=p if p.is_absolute() else OUT/p
        p=p.resolve()
        need(p.is_relative_to(SOURCE) or p.is_relative_to(OUT),'dependency escaped exact matching tree')
        values.append(p)
    need(len(values)>100,'actual complete kernel dependency closure')
    return sorted(set(values))

def timeout(signum,frame):
    raise TimeoutError('bounded object compile expired')

def main():
    global DEADLINE
    need(os.getuid()==os.geteuid()==os.getgid()==1000,'ordinary nonprivileged Pocket4 compile')
    need(ROOT.resolve()==ROOT and not RESULT.exists(),'fresh independent compile receipt')
    os.sched_setaffinity(0,{23});os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU,(180,180))
    resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    signal.signal(signal.SIGALRM,timeout);signal.alarm(240)
    DEADLINE=time.monotonic()+220
    report=ref(ROOT/'TREE-PREPARATION.json',{'bytes':23008,'sha256':'232793bb6e70cfdd0aba664c1a0be17f2a623d465cc2507a884582f65f18b243'})
    preparation=json.loads((ROOT/'TREE-PREPARATION.json').read_bytes())
    need(preparation['state']=='EXACT_MATCHING_SOURCE_AND_C_HEADERS_PREPARED'
         and preparation['compiler_executed'] is False and preparation['configuration_changed'] is False,
         'actual complete original matching preparation')
    for row in preparation['input_refs'].values():immutable(row)
    config=ref(OUT/'.config',{'bytes':304072,'sha256':'bccb147083a909408e25dc63f1dd58cf465ee19bcabc660916a1fa28cc67a3e1'})
    for row in preparation['generated_C_headers']:ref(OUT/row['path'],row)
    for row in preparation['k0a_postimages']:ref(SOURCE/row['path'],row['after'])
    compiler=ref(Path('/usr/bin/x86_64-linux-gnu-gcc-15'),
                 {'bytes':1305304,'sha256':'b5f1b773a7c733738352000c92a077dc5852a1a2fc6d836b1e411be1e9ec5f88'})
    linker=ref(Path('/usr/bin/x86_64-linux-gnu-ld.bfd'))
    commands=json.loads((INPUT/'COMPILE-COMMAND-SOURCE.json').read_bytes())
    need(commands[1]['active_config_differences']==[
        {'key':'CONFIG_LOCK_DOWN_IN_SECURE_BOOT','tu':None,'full':'y'},
        {'key':'CONFIG_SECURITY_PERF_EVENTS_RESTRICT','tu':None,'full':'y'}],
        'only the two recorded security additions distinguish the old TU configuration')
    raw=commands[0]['command']
    prefix='savedcmd_kernel/p4_guest_mntns.o := '
    need(raw.startswith(prefix) and raw.count(' ; ')==1,'complete original saved compiler and objtool commands')
    original_compile,original_objtool=raw[len(prefix):].split(' ; ')
    old_source='/home/qq/work/p4-kernel-6.18.64-cp3a-20261118-r1/source/linux-6.18.64'
    args=shlex.split(original_compile)
    need(args[0]==compiler['path'],'actual original fixed GCC')
    translated=[]
    for arg in args:
        arg=arg.replace(old_source,str(SOURCE))
        arg=arg.replace('kernel/.p4_guest_mntns.o.d','block/.p4_private_loop_actor.o.d')
        arg=arg.replace('kernel/p4_guest_mntns','block/p4_private_loop_actor')
        arg=arg.replace('p4_guest_mntns','p4_private_loop_actor')
        if arg=='-Ikernel':arg='-Iblock'
        if arg=='-I'+str(SOURCE/'kernel'):arg='-I'+str(SOURCE/'block')
        translated.append(arg)
    target=OUT/'block/p4_private_loop_actor.o'
    need(not target.exists() and translated[-1]==str(SOURCE/'block/p4_private_loop_actor.c'),
         'one fresh exact C object')
    compile_source=ref(SOURCE/'block/p4_private_loop_actor.c',
        {'bytes':6103,'sha256':'910c7ef5480e2b0cdf8ba3cd0676698dfa0da1445537167275455df4de353641'})
    dependency_path=OUT/'block/p4_private_loop_actor.preflight.d'
    index=translated.index('-c')
    need(translated[index:index+3]==['-c','-o','block/p4_private_loop_actor.o'],'original compile output shape')
    dep_args=[x for x in translated[:index] if not x.startswith('-Wp,-MMD,')]
    dep_args+=['-M','-MF',str(dependency_path),translated[-1]]
    OBS.update(state='REAL_GCC_DEPENDENCY_SCAN',affinity=[23],jobs=1,
        preparation=report,compiler=compiler,linker=linker,configuration=config,
        compile_source=compile_source,original_saved_command=commands[0],
        fixed_compile_argv=translated,configuration_changed=False)
    run('gcc-version',[compiler['path'],'--version'])
    run('gcc-dependencies',dep_args)
    before={str(p):ref(p) for p in dependencies(dependency_path)}
    OBS['dependency_count']=len(before)
    OBS['dependency_refs']=list(before.values())
    OBS['state']='REAL_GCC_OBJECT_COMPILE'
    compiled=run('gcc-object',translated)
    need(compiled['stderr']['bytes']==0,'actual compiler emitted diagnostics requiring review')
    need(set(map(str,dependencies(OUT/'block/.p4_private_loop_actor.o.d')))==set(before),
         'same actual complete dependency closure in scan and compile')
    for row in before.values():immutable(row)
    gcc_object=ref(target);OBS['gcc_object']=gcc_object
    OBS['C_compiler_passed']=True
    tool=ref(INPUT/'objtool-original',{'bytes':979400,
             'sha256':'2453a7416b1f9aa1799ee6c900ef5dba6641182f99f5a8b50b604c106959e3ba'})
    staged=ROOT/'objtool-staged'
    with staged.open('xb') as stream:stream.write((INPUT/'objtool-original').read_bytes())
    os.chmod(staged,0o700);ref(staged,tool)
    args=shlex.split(original_objtool)
    need(args[0]=='./tools/objtool/objtool' and args[-1]=='kernel/p4_guest_mntns.o','original objtool scope')
    args[0]=str(staged);args[-1]='block/p4_private_loop_actor.o'
    run('objtool-elf-header',['/usr/bin/readelf','-h',str(staged)])
    OBS['state']='REAL_ORIGINAL_OBJTOOL_CHECK'
    checked=run('objtool',args)
    need(checked['stderr']['bytes']==0,'actual objtool emitted diagnostics requiring review')
    run('object-elf-header',['/usr/bin/readelf','-h',str(target)])
    run('object-defined-symbols',['/usr/bin/nm','--defined-only',str(target)])
    symbols=(ROOT/'logs/object-defined-symbols.stdout').read_text()
    for name in ['capture','get','put','check_task']:
        need(' T p4_private_loop_actor_'+name+'\n' in symbols,'actual expected compiled symbol')
    for row in before.values():immutable(row)
    immutable(config);immutable(compiler);immutable(linker);immutable(compile_source);immutable(report);immutable(tool)
    for row in preparation['input_refs'].values():immutable(row)
    OBS.update(state='MATCHING_KERNEL_C_OBJECT_AND_ORIGINAL_OBJTOOL_PASSED',
        objtool_passed=True,objtool_input=tool,object=ref(target),actual_source_and_header_bookends_equal=True,
        actual_C_dependency_closure_equal=True,target_kernel_object_compiled=True,
        full_kernel_built=False,live_actor_or_private_loop_issued=False)

if __name__=='__main__':
    try:main()
    except BaseException as error:
        OBS.update(state='FAILED',error=type(error).__name__+': '+str(error))
        raise
    finally:
        raw=(json.dumps(OBS,sort_keys=True,indent=2)+'\n').encode()
        with RESULT.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        print(json.dumps({'state':OBS['state'],'receipt':str(RESULT),'bytes':len(raw),
            'sha256':hashlib.sha256(raw).hexdigest(),'runtime_qualified':False,'production_ready':False}),flush=True)
