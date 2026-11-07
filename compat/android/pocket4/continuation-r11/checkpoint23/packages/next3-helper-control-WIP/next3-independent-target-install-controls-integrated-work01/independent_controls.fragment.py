
def run_independent_target_controls(entry, context, transport, baseline, ref, files,
                                    expected_manifest, discovery_controls, legacy_source, host_manifest):
    """Real authority/open_context functions; filesystem/held-target I/O is explicit synthetic input."""
    import hashlib
    import os
    import time
    from pathlib import PurePosixPath
    rows = []
    authority = json.loads(files['actual-target-metadata.json'])
    artifact = json.loads(files['target-artifact-reference.json'])
    manifest = json.loads(files['SOURCE_PINS.json'])
    root = PurePosixPath('/pure-owned-source')
    original_baseline = copy.deepcopy(baseline)
    def add(name): rows.append({'name':name,'passed':True})
    def reject(name, code, call):
        try:call()
        except RuntimeError as error:
            entry.require(str(error) == code, 'INDEPENDENT_TARGET_CONTROL_WRONG_FIRST_ERROR:'+name)
        else:raise RuntimeError('INDEPENDENT_TARGET_NEGATIVE_ACCEPTED:'+name)
        add(name)
    reads = []
    def memory_read(path, maximum=1048576, expected=None, size=None):
        name = str(path.relative_to(root))
        data = files[name]
        entry.require(type(data) is bytes and len(data) <= maximum and
                      (expected is None or hashlib.sha256(data).hexdigest() == expected) and
                      (size is None or len(data) == size), 'EXACT_MEMORY_SOURCE_READ_REQUIRED')
        reads.append(name)
        return data
    util = types.SimpleNamespace(read=memory_read)
    observed = context.load_target_metadata(util,manifest,root)
    entry.require(observed == authority and reads == ['actual-target-metadata.json','target-artifact-reference.json'] and
                  context.baseline_scope(ref,baseline,observed) == context.current_scope() and
                  baseline == original_baseline, 'PINNED_INDEPENDENT_TARGET_AUTHORITY_POSITIVE')
    add('actual_metadata_loader_and_scope_preserve_original_baseline')
    wrong = copy.deepcopy(manifest);wrong['files']['actual-target-metadata.json']['sha256'] = '0'*64
    reads.clear()
    reject('metadata_source_pin_rejected_before_read','INDEPENDENT_TARGET_AUTHORITY_SOURCE_PINS_REQUIRED',
           lambda:context.load_target_metadata(util,wrong,root))
    entry.require(reads == [], 'UNPINNED_AUTHORITY_READ_ATTEMPTED')
    binding_row = host_manifest['files']['main_binding.py']
    real_binding = entry.module(entry.BASE_HOST_ROOT/'main_binding.py',binding_row['sha256'],
                                'independent_target_real_package_parser')
    def io_fixture(directory_drift=False):
        state = {'opened':[],'closed':[],'target_verify':0,'held_created':0,'held_closed':0,
                 'Main':0,'writes':[],'commands':0}
        records = {}; next_fd = [2000000000]
        def allocate(row):
            next_fd[0] += 1
            fd = next_fd[0];records[fd] = row;state['opened'].append(fd)
            return fd
        def close(fd):
            entry.require(fd in records and fd not in state['closed'], 'ONE_SYNTHETIC_FD_CLOSE')
            state['closed'].append(fd)
        def fstat(fd):
            entry.require(fd in records and fd not in state['closed'], 'LIVE_SYNTHETIC_DIRECTORY_FD')
            row = records[fd]
            return types.SimpleNamespace(st_dev=row['device'],st_ino=row['inode'],
                st_mode=row['mode'],st_uid=row['uid'],st_gid=row['gid'])
        fake_os = types.SimpleNamespace(**{k:v for k,v in vars(os).items()
                                          if k not in ('open','close','fstat')})
        fake_os.close=close;fake_os.fstat=fstat
        known = {r['path']:r for r in authority['data_directories_before']}
        class Target:
            def __init__(self, actual=None, helper_path=None, helper_sha=None):
                state['held_created'] += 1
                self.expected={'pid':baseline['framework_epoch']['binding']['processes']['init']['host_pid']}
                self.helper_sha256=transport.HELD_HELPER_SHA256
                self.record={'synthetic_held_target':True}
            def verify(self):state['target_verify'] += 1
            def read_file(self,path,maximum):
                entry.require(path == '/data/system/packages.list' and maximum == 1024*1024,
                              'ONE_PRIVATE_PACKAGE_LIST_IN_MEMORY')
                return (context.PACKAGE+' '+str(context.UID)+'\n').encode(),{}
            def open_root(self,path,flags):
                entry.require(path in known and flags == os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW,
                              'EXACT_TWO_TARGET_DIRECTORY_PATHS')
                row=copy.deepcopy(known[path])
                if directory_drift:row['inode'] += 1
                return allocate(row)
            def close(self):state['held_closed'] += 1
        namespace=dict(context.__dict__)
        namespace['os']=fake_os
        verify=types.FunctionType(context.verify_target_data.__code__,namespace)
        return state,records,allocate,fake_os,Target,namespace,verify
    state,records,allocate,fake_os,Target,namespace,verify=io_fixture()
    verify(Target(),authority,real_binding)
    entry.require(len(state['opened']) == 2 and state['closed'] == state['opened'] and
                  state['target_verify'] == 2, 'LIVE_FIXED_DIRECTORIES_AND_FD_CLOSURE')
    add('production_target_directory_revalidation_uses_real_package_parser')
    state,records,allocate,fake_os,Target,namespace,verify=io_fixture(True)
    reject('changed_live_target_directory_rejected_and_closed','CURRENT_TARGET_DATA_DIRECTORY_IDENTITY_CHANGED',
           lambda:verify(Target(),authority,real_binding))
    entry.require(len(state['opened']) == 1 and state['closed'] == state['opened'],
                  'REJECTED_DIRECTORY_DESCRIPTOR_NOT_CLOSED')
    def open_fixture(wrong_init=False, wrong_Main=False):
        f=discovery_controls.Fixture(baseline,files['current_discovery.py'],legacy_source)
        state,records,allocate,fake_os,Target,namespace,verify=io_fixture()
        expected=baseline['framework_epoch']['binding']['processes']['init']
        actual={'pid':expected['host_pid'],'start':str(expected['start_ticks']),
            'uid':[str(x) for x in expected['uids']],'ppid':expected['parent_host_pid'],
            'nspid':[str(x) for x in expected['namespace_pids']],
            'exe':expected['executable'],'cgroup':'\n'.join(expected['cgroup']),
            'ns':copy.deepcopy(expected['namespaces'])}
        def open_proc(path,flags):
            entry.require(path == '/proc/'+str(expected['host_pid']) and
                flags == os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                'ONLY_FIXED_CURRENT_INIT_PROC_OPEN')
            return allocate({'synthetic_proc':True})
        fake_os.open=open_proc
        def proc_identity_at(fd,pid,deadline):
            entry.require(fd in records and pid == expected['host_pid'], 'FIXED_INIT_HELD_IDENTITY_INPUT')
            return copy.deepcopy(actual)
        def forbidden(*args,**kwargs):
            state['commands'] += 1
            raise RuntimeError('INDEPENDENT_CONTEXT_ROUTE_CONTROL_COMMAND_FORBIDDEN')
        recorder=types.SimpleNamespace(APP='/pure/original/android_app.py',APP_SHA='a'*64,
            Flow=types.SimpleNamespace(command=forbidden),
            write_new=lambda path,value:state['writes'].append((path,value)))
        held=types.SimpleNamespace(proc_identity_at=proc_identity_at,HeldTarget=Target)
        def main_classpaths(held_module,target,epoch_record,epoch_module,guard):
            entry.require(held_module is held and epoch_record is baseline['framework_epoch'],
                          'ORIGINAL_TWO_ROOT_CLASSPATH_BOUNDARY')
            guard()
            return dict(f.environment),{'synthetic_classpaths':True}
        binding=types.SimpleNamespace(package_uids=real_binding.package_uids,
            same_epoch_identity=real_binding.same_epoch_identity,main_classpaths=main_classpaths)
        def contract_load(name,label):
            return {'recorder.py':recorder,'references/held_runtime_r5.py':held,'main_binding.py':binding}[name]
        contract=types.SimpleNamespace(sha256=context.SHARED_MANIFEST,load=contract_load,verify=lambda:None)
        source=types.SimpleNamespace(HELPER_PATH=PurePosixPath('/pure/held-helper'),
            HELPER_SHA=transport.HELD_HELPER_SHA256,HELPER_BYTES=7,
            verify_shared_helper=lambda:{'synthetic_qualification':True})
        def contract_constructor(path,expected_sha):
            entry.require(path == context.INSTALLED_SHARED/'source-manifest.json' and
                          expected_sha == context.SHARED_MANIFEST, 'ORIGINAL_R6_SOURCE_CONSTRUCTOR_ROUTE')
            return contract
        source.SourceContract=contract_constructor
        def source_verify(expected_sha):
            entry.require(expected_sha == expected_manifest, 'ORIGINAL_INSTALL_SOURCE_PIN_ROUTE')
            return manifest
        def module(path, expected_sha, name):
            if path == context.INSTALLED_SHARED/'source_contract.py':
                entry.require(expected_sha == context.CONTRACT_SHA, 'ORIGINAL_R6_CONTRACT_PIN_ROUTE')
                return source
            if path == context.Path(recorder.APP):
                entry.require(expected_sha == recorder.APP_SHA, 'ORIGINAL_ANDROID_APP_PIN_ROUTE')
                return f.app
            entry.require(path == root/'current_discovery.py' and
                          expected_sha == hashlib.sha256(files['current_discovery.py']).hexdigest(),
                          'ORIGINAL_CURRENT_DISCOVERY_PIN_ROUTE')
            if wrong_init:
                current=types.SimpleNamespace(**vars(f.current))
                original=f.current.discover_current
                def discover(*args):
                    init,env,status=original(*args)
                    return init+1,env,status
                current.discover_current=discover
                return current
            return f.current
        def read(path, maximum=1048576, expected=None, size=None):
            if path == source.HELPER_PATH:
                entry.require(maximum == size == source.HELPER_BYTES and expected == source.HELPER_SHA,
                              'ORIGINAL_SHARED_HELPER_PIN_ROUTE')
                return b'seam-io'
            return memory_read(path,maximum,expected,size)
        util=types.SimpleNamespace(module=module,read=read)
        def guard(baseline_value,epoch_value):
            entry.require(baseline_value is baseline and epoch_value is f.epoch,
                          'ORIGINAL_MAIN_GUARD_ARGUMENT_ROUTE')
            state['Main'] += 1
            value=copy.deepcopy(authority['Main_before'])
            if wrong_Main:value['seven_processes_match']=False
            return value
        ref_view=types.SimpleNamespace(EPOCH=context.CURRENT_EPOCH,BASELINE_SHA=context.BASELINE_SHA,
            QUALIFICATION_SHA=context.QUALIFICATION_SHA,current_baseline=lambda:baseline,
            EPOCH_SOURCE='/pure/original/framework_epoch.py',EPOCH_SOURCE_SHA='b'*64,
            read=lambda path,expected:b'pure-epoch',module=lambda raw,path,name:f.epoch,
            main_guard=guard,write_new=lambda path,value:state['writes'].append((path,value)))
        namespace['verify_target_data']=verify
        opened=types.FunctionType(context.open_context.__code__,namespace)
        result={};step=PurePosixPath('/pure-owned-step')
        def invoke():
            return opened(ref_view,util,expected_manifest,source_verify,root,step,
                          transport,[],result,time.monotonic()+1000)
        return f,state,result,invoke
    f,state,result,invoke=open_fixture()
    ctx,recorder,guard=invoke()
    entry.require(ctx.scope == context.current_scope() and state['held_created'] == 1 and
                  state['held_closed'] == 0 and f.status_calls == 1 and
                  len(f.identity_calls) == 8 and state['Main'] >= 4 and
                  len(state['writes']) == 1 and
                  state['writes'][0][1]['target_package'] == context.PACKAGE and
                  state['writes'][0][1]['target_uid'] == context.UID and
                  state['writes'][0][1]['independent_target_metadata_sha256'] == context.METADATA_RESULT_SHA and
                  state['commands'] == 0 and state['opened'] == state['closed'],
                  'PRODUCTION_INDEPENDENT_OPEN_CONTEXT_MUST_REACH_HELD_RECORD')
    ctx.close()
    entry.require(state['held_closed'] == 1, 'SUCCESSFUL_SYNTHETIC_HELD_TARGET_CLOSE')
    add('production_open_context_reaches_current_discovery_and_independent_held_record')
    f,state,result,invoke=open_fixture(wrong_init=True)
    reject('production_open_rejects_foreign_discovered_init_and_closes_held',
           'FIXED_MAIN_DISCOVERY_CHANGED',invoke)
    entry.require(state['held_created'] == state['held_closed'] == 1 and
                  state['opened'] == state['closed'] and state['commands'] == 0 and
                  state['writes'] == [], 'WRONG_DISCOVERED_INIT_CLOSURE_REQUIRED')
    f,state,result,invoke=open_fixture(wrong_Main=True)
    reject('production_open_rejects_current_Main_mismatch_before_held',
           'INDEPENDENT_METADATA_AND_CURRENT_MAIN_DIFFER',invoke)
    entry.require(state['held_created'] == 0 and state['opened'] == [] and
                  state['commands'] == 0 and state['writes'] == [] and baseline == original_baseline,
                  'MISMATCHED_MAIN_MUST_NOT_ENTER_OR_MUTATE_BASELINE')
    entry.require(len(rows) == 7,'EXACT_SEVEN_INDEPENDENT_TARGET_CONTROLS')
    return rows
