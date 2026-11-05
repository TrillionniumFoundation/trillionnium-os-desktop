ROOT=Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/role-authorization-positive-host-build-01-20261105')
SOURCE=ROOT/'source'
OUT=ROOT/'build01'
SOURCE_MANIFEST_SHA='d400255a4318ec5856692254cff062280021aeea5bf80662eb939a00d7586aa2'
DEADLINE=None


def execute():
    global DEADLINE
    require(os.getuid()==1000 and os.geteuid()==1000,'ordinary operator UID1000 required')
    require(Path(__file__).absolute()==SOURCE/'build_registry.py','fixed staged controller required')
    real_directory(SOURCE);os.umask(0o077);OUT.mkdir(mode=0o700);(OUT/'tmp').mkdir(mode=0o700)
    DEADLINE=time.monotonic()+180
    require(ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0 and not children(),'owned subreaper required')
    allowed=sorted(os.sched_getaffinity(0));require(len(allowed)>=3,'cannot leave two logical CPUs free')
    os.sched_setaffinity(0,[allowed[-1]])
    report={'schema':1,'state':'RUNNING','scope':'matching registry mechanism compile and default PLAN only',
            'started_utc':utc(),'Main_actions':0,'Main_identity_observed':False,
            'registry_positive_executed':False,'platform_policy_qualified':False,
            'factory_service_started':False,'snapshot_created':False,
            'source_manifest_sha256':SOURCE_MANIFEST_SHA,'selected_cpus':[allowed[-1]],
            'commands':[],'objects':{},'artifacts':{}}
    def interrupted(number,frame):raise RuntimeError('owned compiler interrupted by signal '+str(number))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    source_before={};tools={};dependencies={};resource_fd=-1;resource_before=None;artifact_pins={}
    try:
        resource_fd,resource_before=begin_resources();report['owned_resources_before']=resource_before
        authority,authority_pin=held(SOURCE/'role-source-pins.json',32768)
        require(sha(authority)==SOURCE_MANIFEST_SHA,'positive fixture source authority differs')
        frozen={row['path']:row for row in json.loads(authority)['files']}
        require(len(SOURCE_INPUTS)==5,'reviewed exact five compile inputs required')
        for name,pin in SOURCE_INPUTS.items():
            require(all(frozen[name][key]==pin[key] for key in ['bytes','sha256']),
                    'reviewed compile input not bound by source authority: '+name)
        stage_raw,stage_pin=held(ROOT/'stage-receipt.json',32768);stage=json.loads(stage_raw)['files']
        source_before=regular_tree(SOURCE,12,512*1024)
        require(set(source_before)==set(stage),'staged source membership differs')
        for name,pin in source_before.items():
            require(pin['bytes']==stage[name]['bytes'] and pin['sha256']==stage[name]['sha256'],
                    'staged source pin mismatch: '+name)
        for name,pin in SOURCE_INPUTS.items():
            require(source_before[name]['bytes']==pin['bytes'] and source_before[name]['sha256']==pin['sha256'],
                    'reviewed input changed: '+name)
        report['source_inputs']=source_before;report['source_authority']=authority_pin;report['stage_authority']=stage_pin
        env={'PATH':'/usr/bin:/bin','HOME':'/home/alex','LC_ALL':'C','LANG':'C','TMPDIR':str(OUT/'tmp')}
        report['environment']=env
        for path in ['/usr/bin/g++','/usr/bin/ldd','/usr/bin/python3']:tools[path]=pin_tool(path)
        compiler='/usr/bin/g++'
        report['compiler_version']=command([compiler,'--version'],SOURCE,env,'compiler-version',report['commands'],10).decode()
        for name in ['cc1plus','collect2','as','ld']:
            raw=command([compiler,'-print-prog-name='+name],SOURCE,env,'resolve-'+name,report['commands'],10).decode().strip()
            path=Path(raw) if Path(raw).is_absolute() else Path('/usr/bin')/raw
            require(path.name==name or(name in ['as','ld']and path.name.endswith('-'+name)),
                    'unexpected compiler program name')
            tools[str(path)]=pin_tool(path)
        for name in ['crt1.o','crti.o','crtn.o','crtbeginS.o','crtendS.o','libgcc.a','libgcc_s.so','libstdc++.so','libc.so']:
            raw=command([compiler,'-print-file-name='+name],SOURCE,env,'resolve-file-'+name,report['commands'],10).decode().strip()
            require(Path(raw).is_absolute(),'compiler runtime file not resolved: '+name);tools[raw]=pin_tool(raw)
        for index,row in enumerate(list(tools.values())):
            path=Path(row['resolved_path'])
            with path.open('rb')as stream:magic=stream.read(4)
            if magic!=b'\x7fELF' or path.suffix=='.o' or path.name.endswith('.a'):continue
            raw=command(['/usr/bin/ldd',str(path)],SOURCE,env,'tool-libraries-'+str(index),report['commands'],10).decode()
            require('not found'not in raw,'compiler runtime library missing')
            for line in raw.splitlines():
                match=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
                if match:tools[match[1]]=pin_tool(match[1])
        flags=['-std=c++17','-O2','-Wall','-Wextra','-Werror','-I'+str(SOURCE/'source')]
        units=[('authorization','source/role_authorization.cc'),('context','source/factory_context.cc'),
               ('control','controls/registry_controls.cc')]
        before_units={}
        for label,name in units:
            raw=command([compiler,*flags,'-M','-MT','CONTROL',str(SOURCE/name)],SOURCE,env,
                        'dependencies-'+label,report['commands'],30)
            before_units[label]=dependency_files(raw);dependencies.update(before_units[label])
        require(0<len(dependencies)<=1024,'complete dependency closure out of bound')
        report['dependency_inputs']=write_new(OUT/'dependency-inputs-before.json',dependencies)
        report['dependency_count']=len(dependencies)
        objects=[]
        for label,name in units:
            target=OUT/(label+'.o');md=OUT/(label+'.d')
            command([compiler,*flags,'-MD','-MF',str(md),'-MT','CONTROL','-c',str(SOURCE/name),'-o',str(target)],
                    SOURCE,env,'compile-'+label,report['commands'],45)
            raw,md_pin=held(md,256*1024)
            require(dependency_files(raw)==before_units[label],
                    'actual compiler dependency bytes/identities differ: '+label)
            artifact_pins[label]=hash_held(target,8*1024*1024)
            report['objects'][label]={'object':artifact_pins[label],'actual_md':md_pin,
                                      'dependency_count':len(before_units[label])}
            objects.append(str(target))
        binary=OUT/'registry_controls'
        command([compiler,*flags,*objects,'-o',str(binary)],SOURCE,env,'link-control',report['commands'],30)
        artifact=hash_held(binary,8*1024*1024);artifact_pins['control']=artifact
        with binary.open('rb')as stream:require(stream.read(4)==b'\x7fELF','actual result is not ELF')
        require(binary.stat().st_mode&0o111,'actual ELF not executable')
        raw=command(['/usr/bin/ldd',str(binary)],SOURCE,env,'control-libraries',report['commands'],10).decode()
        require('not found'not in raw,'actual control runtime missing')
        runtime={}
        for line in raw.splitlines():
            match=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
            if match:runtime[match[1]]=pin_tool(match[1]);tools[match[1]]=runtime[match[1]]
        require(runtime,'actual control library closure empty')
        report['runtime_libraries']=runtime
        plan=json.loads(command([str(binary)],SOURCE,env,'default-plan',report['commands'],10))
        require(plan=={'state':'PLAN_ONLY','actual_role_registry':False,'owned_cases':10,
                       'factory_service_started':False,'Main_actions':0},'default PLAN contract differs')
        report['artifacts']['control']={'elf':artifact,'default_plan':plan}
        report['tool_inputs']=write_new(OUT/'tool-inputs-before.json',tools)
        report['state']='PASS_BUILD_ONLY'
    except Exception as error:
        report['state']='FAIL';report['error']={'type':type(error).__name__,'message':str(error),
                                               'filename':getattr(error,'filename',None)}
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
        report['cleanup']=cleanup_children()
        try:
            report['source_unchanged_after']=bool(source_before)and regular_tree(SOURCE,12,512*1024)==source_before
            report['tool_changes']=verify_resolved(list(tools.values()))
            report['dependency_changes']=verify_resolved(list(dependencies.values()))
            report['artifacts_unchanged_after']=all(hash_held(Path(row['path']),8*1024*1024)==row for row in artifact_pins.values())
            require(report['source_unchanged_after']and not report['tool_changes']and
                    not report['dependency_changes']and report['artifacts_unchanged_after'],
                    'compiled input or output changed')
        except Exception as error:report['after_error']=repr(error);report['state']='FAIL'
        try:
            require(resource_fd>=0 and resource_before is not None,'missing before resource observation')
            report['owned_resource_gate']=finish_resources(resource_fd,resource_before,report)
        except Exception as error:report['resource_error']=repr(error);report['state']='FAIL'
        finally:
            if resource_fd>=0:os.close(resource_fd)
        if report['cleanup']['forced_cleanup']or report['cleanup']['remaining']or report['cleanup']['errors']:
            report['state']='FAIL'
    report['finished_utc']=utc();result=write_new(OUT/'result.json',report)
    print(json.dumps({'state':report['state'],'result':result}),flush=True)
    return 0 if report['state']=='PASS_BUILD_ONLY'else 1


if __name__=='__main__':
    if sys.argv[1:]!=['--execute-once']:
        print(json.dumps({'state':'PLAN_ONLY','build_root':str(ROOT),'source_count':len(SOURCE_INPUTS),
                          'registry_positive_executed':False,'Main_actions':0}))
    else:raise SystemExit(execute())
