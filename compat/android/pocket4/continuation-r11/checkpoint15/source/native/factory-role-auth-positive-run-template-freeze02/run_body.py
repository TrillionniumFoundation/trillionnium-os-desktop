ROOT=Path('/run/pocket4-role-authorization-positive-host-run-02-20261105')
HERE=ROOT/'control-source'
OUT=ROOT/'run01'
BUILD_ROOT=Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/role-authorization-positive-host-build-02-20261105')
SOURCE=BUILD_ROOT/'source'
BUILD_RESULT=BUILD_ROOT/'build01/result.json'
BUILD_RESULT_SHA='PENDING_ACTUAL_BUILD_RESULT_SHA256'
CASE_PLAN_SHA='PENDING_FROZEN_CASE_PLAN_SHA256'
SOURCE_MANIFEST_SHA='fda076982c0a26682eb3b6a596a6964e6645cf1eddc7b175e56d9b499c06fda2'
DEADLINE=None


def qualified_build(build):
    require(build['state']=='PASS_BUILD_ONLY' and build['source_manifest_sha256']==SOURCE_MANIFEST_SHA and
            build['registry_positive_executed'] is False and build['platform_policy_qualified'] is False and
            build['factory_service_started'] is False and build['snapshot_created'] is False and
            build['Main_actions']==0 and build['source_unchanged_after'] is True and
            build['artifacts_unchanged_after'] is True and not build['tool_changes'] and
            not build['dependency_changes'] and build['owned_resource_gate']['pass'] is True and
            not build['cleanup']['forced_cleanup'] and not build['cleanup']['remaining'] and
            not build['cleanup']['errors'] and set(build['artifacts'])=={'control'},
            'complete matching build-only authority required')
    labels=[row['label'] for row in build['commands']]
    require(len(labels)==len(set(labels)) and all(row['returncode']==0 and not row['timed_out']
            for row in build['commands']), 'matching build command failure or duplicate')
    for name in ['dependencies-authorization','dependencies-context','dependencies-control',
                 'compile-authorization','compile-context','compile-control','link-control',
                 'control-libraries','default-plan']:
        require(labels.count(name)==1, 'matching build omitted required command: '+name)
    require(set(build['objects'])=={'authorization','context','control'} and
            all(row['dependency_count']>0 for row in build['objects'].values()),
            'complete actual compiler dependency observations required')
    require(build['artifacts']['control']['default_plan']=={
        'state':'PLAN_ONLY','actual_role_registry':False,'owned_cases':10,
        'factory_service_started':False,'Main_actions':0}, 'matching default PLAN differs')


def root_scope():
    require(os.getuid()==0 and os.geteuid()==0 and os.getgid()==0 and os.getegid()==0,
            'root controller identity required')
    require(os.getpid()==int(Path('/proc/thread-self/status').read_text().split('Pid:\t',1)[1].splitlines()[0]),
            'root controller requires current proc PID view')
    require(signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL,
            'owned root controller requires default SIGCHLD')
    for path in [ROOT,HERE,OUT]:
        value=path.lstat()
        require(stat.S_ISDIR(value.st_mode) and value.st_uid==0 and value.st_gid==0 and
                stat.S_IMODE(value.st_mode)==0o700, 'root-private runtime directory differs: '+str(path))
    # Only this fixture UID/GID is used by owned children. No system account or
    # process is modified, and no search is made for alternative identities.
    import pwd,grp
    for lookup in [pwd.getpwuid,grp.getgrgid]:
        try:lookup(61179)
        except KeyError:continue
        raise RuntimeError('fixed fixture UID/GID is a configured system account')


def run_held(fd,path,env,libc):
    require(not children(), 'unreaped child before the owned registry harness')
    require(os.execve in os.supports_fd, 'Python fd-based exec unavailable')
    stdout=OUT/'registry.stdout';stderr=OUT/'registry.stderr'
    started=utc();parent=os.getpid();pid=-1;pidfd=-1;status=None;timed_out=False
    with stdout.open('xb') as out,stderr.open('xb') as err:
        pid=os.fork()
        if pid==0:
            try:
                require(os.getppid()==parent and libc.prctl(1,signal.SIGKILL,0,0,0)==0 and
                        os.getppid()==parent, 'exec child lost exact owned parent')
                os.setsid()
                null=os.open('/dev/null',os.O_RDONLY|os.O_CLOEXEC)
                os.dup2(null,0);os.dup2(out.fileno(),1);os.dup2(err.fileno(),2)
                if null>2:os.close(null)
                require(fcntl.fcntl(fd,fcntl.F_GETFD)&fcntl.FD_CLOEXEC,
                        'held ELF must close across exec')
                os.execve(fd,[str(path),'--execute-once'],env)
            except BaseException:
                os.write(2,b'owned held-ELF exec failed\n');os._exit(126)
        try:
            pidfd=os.pidfd_open(pid,0)
            until=min(time.monotonic()+45,DEADLINE)
            while time.monotonic()<until:
                got,value=os.waitpid(pid,os.WNOHANG)
                if got==pid:status=value;break
                time.sleep(0.02)
            if status is None:
                timed_out=True;signal.pidfd_send_signal(pidfd,signal.SIGKILL)
                until=time.monotonic()+3
                while time.monotonic()<until:
                    got,value=os.waitpid(pid,os.WNOHANG)
                    if got==pid:status=value;break
                    time.sleep(0.02)
                require(status is not None,'owned harness did not reap after exact pidfd kill')
        finally:
            if pidfd>=0:os.close(pidfd)
    raw,outpin=held(stdout,131072);_,errpin=held(stderr,32768)
    return {'held_elf_path':str(path),'fd_exec':True,'started_utc':started,'finished_utc':utc(),
            'child_pid':pid,'child_reaped':status is not None,'wait_status':status,
            'returncode':os.waitstatus_to_exitcode(status) if status is not None else None,
            'timed_out':timed_out,'stdout':outpin,'stderr':errpin},raw


def validate_result(raw,plan):
    lines=raw.decode('ascii').splitlines()
    require(len(lines)==11 and all(lines),'exact ten case records and one terminal required')
    records=[json.loads(line) for line in lines]
    expected=plan['cases']
    require(len(expected)==10 and len({row['name'] for row in expected})==10,
            'exact frozen ten-case plan required')
    for wanted,seen in zip(expected,records[:-1]):
        require(seen=={'case':wanted['name'],'state':'PASS','actual_kernel_identity':True,
                       'production_platform_policy':False,'snapshot_created':False},
                'owned case failed or unexpected record: '+wanted['name'])
    result=records[-1]
    require(set(result)=={'state','cases','assertions','direct_children_reaped','nested_children_reaped',
                         'forced_cleanup','cleanup_unreaped','platform_policy_qualified','snapshot_created',
                         'Main_actions','factory_service_started'} and
            result['state']=='PASS_OWNED_REGISTRY_MECHANISM' and result['cases']==10 and
            isinstance(result['assertions'],int) and not isinstance(result['assertions'],bool) and
            result['assertions']>0 and result['direct_children_reaped']==10 and
            result['nested_children_reaped']==1 and result['forced_cleanup']==0 and
            result['cleanup_unreaped']==0 and result['platform_policy_qualified'] is False and
            result['snapshot_created'] is False and result['Main_actions']==0 and
            result['factory_service_started'] is False, 'owned registry aggregate failed')
    return {'cases':records[:-1],'summary':result}


def execute():
    global DEADLINE
    require(Path(__file__).absolute()==HERE/'run_registry.py','fixed staged root runner required')
    require(re.fullmatch(r'[0-9a-f]{64}',BUILD_RESULT_SHA) is not None,
            'actual matching build receipt has not been bound')
    real_directory(HERE);os.umask(0o077);OUT.mkdir(mode=0o700);DEADLINE=time.monotonic()+90
    libc=ctypes.CDLL(None,use_errno=True)
    require(libc.prctl(36,1,0,0,0)==0 and not children(),'owned root subreaper required')
    allowed=sorted(os.sched_getaffinity(0));require(len(allowed)>=3,'cannot leave two logical CPUs free')
    os.sched_setaffinity(0,[allowed[-1]])
    report={'schema':1,'state':'RUNNING','started_utc':utc(),
            'scope':'fixed root / owned role child kernel authorization mechanism only',
            'Main_actions':0,'Main_identity_observed':False,'Android_execution':False,
            'factory_service_started':False,'snapshot_created':False,'platform_policy_qualified':False,
            'production_source_changed':False,'selected_cpus':[allowed[-1]],'commands':[]}
    def interrupted(number,frame):raise RuntimeError('owned runtime interrupted by signal '+str(number))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    resource_fd=-1;resource_before=None;source_before={};elf_fd=-1;elf_pin=None
    libraries={};tool_rows=[];authority={}
    try:
        resource_fd,resource_before=begin_resources();report['owned_resources_before']=resource_before
        root_scope()
        raw,build_pin=held(BUILD_RESULT,262144)
        require(sha(raw)==BUILD_RESULT_SHA,'actual build receipt changed')
        staged,staged_pin=held(HERE/'actual-build-result.json',262144)
        require(staged==raw,'staged build receipt differs from actual matching receipt')
        build=json.loads(raw);qualified_build(build)
        plan_raw,plan_pin=held(HERE/'CASE_PLAN.json',32768)
        require(sha(plan_raw)==CASE_PLAN_SHA,'frozen ten-case plan changed')
        plan=json.loads(plan_raw)
        require(plan['production_source_manifest_sha256']==SOURCE_MANIFEST_SHA,
                'case plan is not bound to reviewed source')
        source_before=regular_tree(SOURCE,12,512*1024)
        require(source_before==build['source_inputs'],'actual built source changed before runtime')
        authority={str(BUILD_RESULT):build_pin,str(HERE/'actual-build-result.json'):staged_pin,
                   str(HERE/'CASE_PLAN.json'):plan_pin}
        report['actual_build_receipt']=build_pin;report['source_authority']=build['source_authority']
        tools_path=BUILD_ROOT/'build01/tool-inputs-before.json'
        require(build['tool_inputs']['path']==str(tools_path),'build tool inventory path escaped')
        tools_raw,tools_pin=held(tools_path,262144)
        require({key:tools_pin[key]for key in ['path','bytes','sha256']}==build['tool_inputs'],
                'matching tool inventory changed')
        authority[str(tools_path)]=tools_pin
        tools=json.loads(tools_raw);tool_rows=[tools['/usr/bin/python3'],tools['/usr/bin/ldd']]
        require(not verify_rows(tool_rows),'runtime tools changed after matching build')
        path=BUILD_ROOT/'build01/registry_controls';artifact=build['artifacts']['control']['elf']
        require(artifact['path']==str(path),'actual control ELF path escaped matching build')
        elf_fd,elf_pin=held_executable(path,artifact)
        env={'PATH':'/usr/bin:/bin','HOME':'/root','LC_ALL':'C','LANG':'C'}
        raw=command(['/usr/bin/ldd','/proc/self/fd/'+str(elf_fd)],SOURCE,env,
                    'runtime-libraries',report['commands'],10,pass_fds=(elf_fd,)).decode()
        require('not found'not in raw,'actual runtime library missing')
        for line in raw.splitlines():
            match=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
            if match:
                requested=Path(match[1]);resolved=requested.resolve(strict=True)
                require(resolved.is_relative_to('/usr/lib')or resolved.is_relative_to('/lib'),
                        'runtime library outside system roots')
                row=hash_held(resolved,128*1024*1024)
                row.update({'requested_path':str(requested),'resolved_path':str(resolved)})
                libraries[str(requested)]=row
        require(libraries and libraries==build['runtime_libraries'],
                'runtime library closure differs from actual matching build')
        report['runtime_libraries']=write_new(OUT/'runtime-libraries-before.json',libraries)
        row,raw=run_held(elf_fd,path,env,libc);report['execution']=row
        require(row['returncode']==0 and row['child_reaped'] and not row['timed_out'] and
                row['stderr']['bytes']==0,'owned registry process failed')
        report['assessment']=validate_result(raw,plan)
        require(not children(),'owned registry harness left adopted children')
        report['state']='PASS_OWNED_REGISTRY_MECHANISM'
    except Exception as error:
        report['state']='FAIL';report['error']={'type':type(error).__name__,'message':str(error),
                                               'filename':getattr(error,'filename',None)}
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
        report['cleanup']=cleanup_children()
        try:
            report['source_unchanged_after']=bool(source_before)and regular_tree(SOURCE,12,512*1024)==source_before
            report['authority_unchanged_after']=bool(authority)and all(hash_held(Path(path))==pin
                                                                       for path,pin in authority.items())
            report['library_changes']=verify_rows(list(libraries.values()))
            report['tool_changes']=verify_rows(tool_rows)
            report['held_ELF_unchanged_after']=(elf_pin is not None and elf_fd>=0 and
                hash_held(Path(elf_pin['path']),8*1024*1024)==elf_pin and
                identity(os.fstat(elf_fd))==elf_pin['identity'])
            require(report['source_unchanged_after']and report['authority_unchanged_after']and
                    not report['library_changes']and not report['tool_changes']and
                    report['held_ELF_unchanged_after'],'runtime source or authority changed')
        except Exception as error:report['after_error']=str(error);report['state']='FAIL'
        if elf_fd>=0:os.close(elf_fd)
        try:
            require(resource_fd>=0 and resource_before is not None,'missing owned cgroup before observation')
            report['owned_resource_gate']=finish_resources(resource_fd,resource_before,report)
        except Exception as error:report['resource_error']=str(error);report['state']='FAIL'
        finally:
            if resource_fd>=0:os.close(resource_fd)
        if report['cleanup']['forced_cleanup']or report['cleanup']['remaining']or report['cleanup']['errors']:
            report['state']='FAIL'
    report['finished_utc']=utc();pin=write_new(OUT/'result.json',report)
    print(json.dumps({'state':report['state'],'result':pin}),flush=True)
    return 0 if report['state']=='PASS_OWNED_REGISTRY_MECHANISM'else 1


if __name__=='__main__':
    if sys.argv[1:]!=['--execute-once']:
        print(json.dumps({'state':'PLAN_ONLY','requires_actual_matching_build':True,'owned_cases':10,
                          'root_execution':False,'factory_service_started':False,'Main_actions':0}))
    else:raise SystemExit(execute())
