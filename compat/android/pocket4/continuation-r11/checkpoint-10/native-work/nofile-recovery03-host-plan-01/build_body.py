ROOT=Path('/home/alex/work/pocket4-nofile-owner-recovery03-host-build-01-20261105')
SOURCE=ROOT/'source'
OUT=ROOT/'build01'
SOURCE_MANIFEST_SHA='baa504625fc51619824ef3023738b8b589008b9ef024fffdf6707ff726628aa3'
DEADLINE=None

def pin_tool(path):
    original=Path(path);resolved=original.resolve(strict=True)
    require(any(resolved.is_relative_to(root) for root in [Path('/usr/bin'),Path('/usr/lib'),Path('/usr/libexec/gcc')]),
            'tool/library outside fixed system roots: '+str(resolved))
    row=hash_held(resolved,128*1024*1024)
    row.update({'requested_path':str(original),'resolved_path':str(resolved)})
    require(original.resolve(strict=True)==resolved,'tool resolution changed')
    return row

def dependency_files(raw):
    text=raw.decode().replace(chr(92)+chr(10),' ')
    require(text.startswith('CONTROL:') and text.count('CONTROL:')==1,'unexpected compiler dependency format')
    words=shlex.split(text[len('CONTROL:'):]);require(0<len(words)<=1024,'compiler dependency bound exceeded')
    rows={}
    for name in words:
        requested=Path(os.path.abspath(str(SOURCE/name))) if not Path(name).is_absolute() else Path(name)
        resolved=requested.resolve(strict=True)
        require(any(resolved.is_relative_to(p) for p in [SOURCE,Path('/usr/include'),Path('/usr/lib/gcc')]),
                'compiler header escaped staged source/system include roots: '+str(resolved))
        row=hash_held(resolved,16*1024*1024)
        row.update({'requested_path':str(requested),'resolved_path':str(resolved)})
        rows[str(requested)]=row
    return rows

def entry_slice(path):
    raw,_=held(path,8*1024*1024);text=raw.decode();blocks=[];block=[];name=''
    def wanted(name):
        return name=='berberis_proc_metadata_raw_clone_x86_64' or ('raw_metadata_owner::' in name and
               ('::Start(' in name or '::Read(' in name or '::ReadInheritedAfterAllocationFailure(' in name))
    for line in text.splitlines(True):
        match=re.match(r'^\s*[0-9a-f]+ <(.+)>:',line)
        if match:
            if block and wanted(name):blocks.extend(block)
            block=[line];name=match[1]
        else:block.append(line)
    if block and wanted(name):blocks.extend(block)
    result=''.join(blocks).encode();require(0<len(result)<=65536,'bounded actual entry disassembly missing/too large')
    return result

def execute():
    global DEADLINE
    require(os.getuid()==1000 and os.geteuid()==1000,'ordinary operator UID1000 required')
    require(Path(__file__).absolute()==SOURCE/'build_nofile.py','fixed staged controller required')
    real_directory(SOURCE);os.umask(0o077);OUT.mkdir(mode=0o700);(OUT/'tmp').mkdir(mode=0o700)
    DEADLINE=time.monotonic()+250
    require(ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0 and not children(),'owned subreaper required')
    allowed=sorted(os.sched_getaffinity(0));require(len(allowed)>=3,'cannot leave two logical CPUs free');os.sched_setaffinity(0,[allowed[-1]])
    report={'schema':1,'state':'RUNNING','scope':'matching host compilation, actual final ELF closure, default PLAN only',
      'started_utc':utc(),'Main_actions':0,'Main_identity_observed':False,'positive_26_execution':False,'Android_execution':False,
      'factory_service_started':False,'lost_harness_results_inherited':False,'commands':[],'artifacts':{},
      'source_manifest_sha256':SOURCE_MANIFEST_SHA,'selected_cpus':[allowed[-1]]}
    def interrupted(number,frame):raise RuntimeError('owned compiler interrupted by signal '+str(number))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    source_before={};tools={};dependencies={};resource_fd=-1;resource_before=None;artifact_pins={}
    try:
        resource_fd,resource_before=begin_resources();report['owned_resources_before']=resource_before
        raw,manifest_pin=held(SOURCE/'recovery03-source-pins.json',32768)
        require(sha(raw)==SOURCE_MANIFEST_SHA,'frozen recovery03 authority differs')
        frozen={p['path']:p for p in json.loads(raw)['files']}
        for name,pin in SOURCE_INPUTS.items():
            require(frozen[name]['sha256']==pin['sha256'] and frozen[name]['bytes']==pin['bytes'],'reviewed source binding differs')
        stage_raw,stage_pin=held(ROOT/'stage-receipt.json',32768);stage=json.loads(stage_raw)['files']
        source_before=regular_tree(SOURCE,32,1024*1024);require(set(source_before)==set(stage),'staged source membership differs')
        for name,pin in source_before.items():
            require(pin['bytes']==stage[name]['bytes'] and pin['sha256']==stage[name]['sha256'],'staged source pin mismatch')
        for name,pin in SOURCE_INPUTS.items():
            require(source_before[name]['sha256']==pin['sha256'] and source_before[name]['bytes']==pin['bytes'],'reviewed production input changed')
        report['source_inputs']=source_before;report['source_authority']=manifest_pin;report['stage_authority']=stage_pin
        env={'PATH':'/usr/bin:/bin','HOME':'/home/alex','LC_ALL':'C','LANG':'C','TMPDIR':str(OUT/'tmp')}
        report['environment']=env
        for path in ['/usr/bin/g++','/usr/bin/objdump','/usr/bin/ldd','/usr/bin/python3']:tools[path]=pin_tool(path)
        compiler='/usr/bin/g++'
        report['compiler_version']=command([compiler,'--version'],SOURCE,env,'compiler-version',report['commands'],10).decode()
        for name in ['cc1plus','collect2','as','ld']:
            raw=command([compiler,'-print-prog-name='+name],SOURCE,env,'resolve-'+name,report['commands'],10).decode().strip()
            p=Path(raw) if Path(raw).is_absolute() else Path('/usr/bin')/raw
            require(p.name==name or (name in ['as','ld'] and p.name.endswith('-'+name)),'unexpected compiler program name')
            tools[str(p)]=pin_tool(p)
        for name in ['crt1.o','crti.o','crtn.o','crtbeginS.o','crtendS.o','libgcc.a','libgcc_s.so','libstdc++.so','libc.so']:
            raw=command([compiler,'-print-file-name='+name],SOURCE,env,'resolve-file-'+name,report['commands'],10).decode().strip()
            require(Path(raw).is_absolute(),'compiler runtime file not resolved: '+name);tools[raw]=pin_tool(raw)
        for index,row in enumerate(list(tools.values())):
            p=Path(row['resolved_path'])
            with p.open('rb') as stream:magic=stream.read(4)
            if magic!=b'\x7fELF' or p.suffix=='.o' or p.name.endswith('.a'):continue
            raw=command(['/usr/bin/ldd',str(p)],SOURCE,env,'tool-libraries-'+str(index),report['commands'],10).decode()
            require('not found' not in raw,'compiler runtime library missing')
            for line in raw.splitlines():
                match=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
                if match:tools[match[1]]=pin_tool(match[1])
        flags=['-std=c++20','-O2','-Wall','-Wextra','-Werror','-pthread','-I'+str(SOURCE/'actual')]
        units=[('candidate',[str(SOURCE/'owned_nofile_controls.cc')],[]),
               ('preimage',[str(SOURCE/'owned_nofile_controls.cc')],['-DOWNED_USE_PREIMAGE=1']),
               ('wire',[str(SOURCE/'actual/proc_maps_factory_wire.cc')],[])]
        for label,unit,defines in units:
            raw=command([compiler,*flags,*defines,'-M','-MT','CONTROL',*unit],SOURCE,env,'dependencies-'+label,report['commands'],30)
            dependencies.update(dependency_files(raw))
        require(len(dependencies)<=1024,'complete include closure exceeds bound')
        report['dependency_inputs']=write_new(OUT/'dependency-inputs-before.json',dependencies)
        report['dependency_count']=len(dependencies)
        report['tool_inputs']=write_new(OUT/'tool-inputs-before.json',tools)
        for arm in ['preimage','candidate']:
            binary=OUT/arm;defines=['-DOWNED_USE_PREIMAGE=1'] if arm=='preimage' else []
            command([compiler,*flags,*defines,str(SOURCE/'owned_nofile_controls.cc'),str(SOURCE/'actual/proc_maps_factory_wire.cc'),'-o',str(binary)],
                    SOURCE,env,'compile-'+arm,report['commands'],75)
            artifact=hash_held(binary,8*1024*1024);artifact_pins[arm]=artifact
            require(binary.stat().st_mode&0o111,'output not executable')
            with binary.open('rb') as stream:require(stream.read(4)==b'\x7fELF','output not ELF')
            audit=OUT/(arm+'-worker-audit.json');auditor='audit_worker_binary.py' if arm=='preimage' else 'audit_two_workers.py'
            command(['/usr/bin/python3','-I','-B',str(SOURCE/auditor),str(binary),'--objdump','/usr/bin/objdump','--output',str(audit)],
                    SOURCE,env,'audit-'+arm,report['commands'],20)
            audit_raw,audit_pin=held(audit,32768);a=json.loads(audit_raw)
            require(a['qualified_worker_closure'] is True and a['elf_sha256']==artifact['sha256'] and not a['errors'],'actual ELF worker closure rejected')
            disasm=audit.with_suffix('.disassembly.txt');disasm_pin=hash_held(disasm,8*1024*1024)
            entry=write_new(OUT/(arm+'-entry-disassembly.txt'),entry_slice(disasm))
            plan=json.loads(command([str(binary)],SOURCE,env,'default-plan-'+arm,report['commands'],10))
            require(plan['mode']=='PLAN' and plan['case_count']==26 and plan['preimage']==(arm=='preimage') and
                    plan['lost_harness_results_inherited'] is False,'actual default entry mismatch')
            require(hash_held(binary,8*1024*1024)==artifact,'ELF changed while audited')
            report['artifacts'][arm]={'elf':artifact,'audit':audit_pin,'disassembly':disasm_pin,'entry_disassembly':entry,'default_plan':plan}
        report['state']='PASS'
    except Exception as error:report['state']='FAIL';report['error']={'type':type(error).__name__,'message':str(error),'filename':getattr(error,'filename',None)}
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT});report['cleanup']=cleanup_children()
        try:
            report['source_unchanged_after']=bool(source_before) and regular_tree(SOURCE,32,1024*1024)==source_before
            report['tool_changes']=verify_resolved(list(tools.values()));report['dependency_changes']=verify_resolved(list(dependencies.values()))
            report['ELF_unchanged_after']=all(hash_held(Path(row['path']),8*1024*1024)==row for row in artifact_pins.values())
            require(report['source_unchanged_after'] and not report['tool_changes'] and not report['dependency_changes'] and
                    report['ELF_unchanged_after'],'compiled input or output changed')
        except Exception as error:report['after_error']=repr(error);report['state']='FAIL'
        try:
            require(resource_fd>=0 and resource_before is not None,'missing owned cgroup before observation')
            report['owned_resource_gate']=finish_resources(resource_fd,resource_before,report)
        except Exception as error:report['resource_error']=repr(error);report['state']='FAIL'
        finally:
            if resource_fd>=0:os.close(resource_fd)
        if report['cleanup']['forced_cleanup'] or report['cleanup']['remaining'] or report['cleanup']['errors']:report['state']='FAIL'
    report['finished_utc']=utc();result=write_new(OUT/'result.json',report)
    print(json.dumps({'state':report['state'],'result':result}),flush=True);return 0 if report['state']=='PASS' else 1

if __name__=='__main__':
    if sys.argv[1:]!=['--execute-once']:
        print(json.dumps({'mode':'PLAN','build_root':str(ROOT),'source_count':len(SOURCE_INPUTS),'positive_26_execution':False,'Main_actions':0}))
    else:raise SystemExit(execute())
