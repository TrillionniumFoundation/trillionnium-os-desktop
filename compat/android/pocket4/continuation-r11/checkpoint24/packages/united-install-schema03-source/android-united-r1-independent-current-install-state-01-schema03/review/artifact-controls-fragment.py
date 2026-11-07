
def run_artifact_reference_controls(entry, context, files, artifact, open_fixture):
    """Real methods and exact frozen reference; synthetic I/O never qualifies installed APKs."""
    import hashlib
    import os
    import time
    rows = []
    tag = entry.SELF.split('.')[3].upper()
    exact = {key:artifact[key] for key in ('package','uid','user','version_code')}
    original = copy.deepcopy(artifact)
    parser = types.ModuleType('actual_fixed_target_metadata_parser')
    exec(compile(files['references/target_metadata_parsers.py'],'<fixed-target-parser>','exec'),parser.__dict__)
    metadata_raw = ('package:'+context.PACKAGE+' versionCode:'+str(context.VERSION)+
                    ' uid:'+str(context.UID)+'\n').encode()
    paths_raw = ''.join('package:'+row['path']+'\n' for row in artifact['current_artifacts']).encode()
    def add(name): rows.append({'name':name,'passed':True})
    def reject(name, code, call):
        try:call()
        except RuntimeError as error:
            entry.require(str(error) == code, 'ARTIFACT_CONTROL_WRONG_FIRST_ERROR:'+name)
        else:raise RuntimeError('ARTIFACT_CONTROL_NEGATIVE_ACCEPTED:'+name)
        add(name)
    # Extend the exact production open_context path past the former KeyError.
    f,state,result,invoke = open_fixture()
    ctx = owned = None
    try:
        ctx,recorder,guard = invoke()
        owned = context.ArtifactSet(ctx,artifact,parser)
        entry.require(owned.expected is artifact and owned.metadata == exact and
                      owned._metadata(metadata_raw) == exact and
                      owned._paths(paths_raw) == sorted(row['path'] for row in artifact['current_artifacts']) and
                      len(state['writes']) == 1 and
                      state['writes'][0][1]['target'] == ctx.target.record and
                      state['writes'][0][1]['current_target_scope'] == context.current_scope() and
                      state['writes'][0][1]['target_package'] == context.PACKAGE and
                      state['commands'] == 0 and state['opened'] == state['closed'],
                      'REAL_OPEN_HELD_RECORD_AND_FROZEN_ARTIFACT_ROUTE')
    finally:
        if owned is not None:owned.close()
        if ctx is not None:ctx.close()
    entry.require(state['held_created'] == state['held_closed'] == 1 and
                  artifact == original, 'REAL_OPEN_ARTIFACT_ROUTE_CLOSE_AND_NO_REFERENCE_MUTATION')
    add('real_open_context_held_record_then_actual_artifact_reference')
    dummy = types.SimpleNamespace(artifacts=None)
    wrong = copy.deepcopy(artifact);wrong['uid'] += 1;wrong['target'] = exact
    reject('actual_top_level_identity_cannot_be_shadowed_by_legacy_target',
           'ACTUAL_'+tag+'_METADATA_REFERENCE_REQUIRED',
           lambda:context.ArtifactSet(dummy,wrong,parser))
    wrong = copy.deepcopy(artifact);wrong['artifacts'] = wrong.pop('current_artifacts')
    reject('legacy_artifacts_cannot_replace_current_artifacts',
           'ACTUAL_'+tag+'_ARTIFACT_REFERENCE_REQUIRED',
           lambda:context.ArtifactSet(dummy,wrong,parser))
    wrong = copy.deepcopy(artifact);wrong['current_APK_count'] += 1
    reject('actual_reference_count_mismatch_rejected',
           'ACTUAL_'+tag+'_ARTIFACT_REFERENCE_REQUIRED',
           lambda:context.ArtifactSet(dummy,wrong,parser))
    wrong = copy.deepcopy(artifact);wrong['current_total_APK_bytes'] += 1
    reject('actual_reference_total_bytes_mismatch_rejected',
           'ACTUAL_'+tag+'_ARTIFACT_REFERENCE_REQUIRED',
           lambda:context.ArtifactSet(dummy,wrong,parser))
    def fd_fixture():
        state = {'opened':[],'closed':[],'read':0,'seek':0,'hash_routes':[],'commands':[]}
        records = {};contents = {};offsets = {};counter = [1900000000]
        def allocate(row, data=b''):
            counter[0] += 1;fd = counter[0]
            records[fd] = copy.deepcopy(row);contents[fd] = data;offsets[fd] = 0
            state['opened'].append(fd)
            return fd
        def live(fd):
            entry.require(fd in records and fd not in state['closed'], 'LIVE_ARTIFACT_MEMORY_FD_REQUIRED')
        def fstat(fd):
            live(fd);row = records[fd]
            return types.SimpleNamespace(st_dev=row['device'],st_ino=row['inode'],st_mode=row['mode'],
                st_uid=row['uid'],st_gid=row['gid'],st_nlink=row['nlink'],st_size=row['bytes'],
                st_mtime_ns=row['mtime_ns'],st_ctime_ns=row['ctime_ns'])
        def close(fd):
            live(fd);state['closed'].append(fd)
        def lseek(fd, offset, whence):
            live(fd);entry.require(offset == 0 and whence == os.SEEK_SET, 'FIXED_ARTIFACT_STREAM_REWIND')
            offsets[fd] = 0;state['seek'] += 1
            return 0
        def read(fd, count):
            live(fd);entry.require(type(count) is int and 0 < count <= 65536, 'BOUNDED_ARTIFACT_MEMORY_READ')
            state['read'] += 1;start = offsets[fd];raw = contents[fd][start:start+count]
            offsets[fd] += len(raw);return raw
        fake_os = types.SimpleNamespace(**{key:value for key,value in vars(os).items()
            if key not in ('fstat','close','lseek','read')})
        fake_os.fstat=fstat;fake_os.close=close;fake_os.lseek=lseek;fake_os.read=read
        namespace = dict(context.__dict__);namespace['os'] = fake_os
        namespace['identity'] = types.FunctionType(context.identity.__code__,namespace)
        methods = {name:types.FunctionType(method.__code__,namespace,name,method.__defaults__)
                   for name,method in vars(context.ArtifactSet).items()
                   if isinstance(method,types.FunctionType)}
        Production = type('ProductionArtifactSetWithMemoryOS',(),methods)
        return state,records,allocate,fake_os,Production
    # Only hashing is a declared return-value seam here, because actual APK bytes
    # are not part of pure controls. All before/after/held/named/close bodies run.
    def stream_route(named_drift=False):
        state,records,allocate,fake_os,Production = fd_fixture()
        known = {row['path']:row for row in artifact['current_artifacts']}
        opens = {}
        def open_root(path,flags):
            entry.require(path in known and flags == os.O_RDONLY|os.O_NOFOLLOW, 'ONLY_FROZEN_APK_MEMORY_OPEN')
            opens[path] = opens.get(path,0)+1
            identity = copy.deepcopy(known[path]['held_file'])
            if named_drift and opens[path] == 2:identity['inode'] += 1
            return allocate(identity)
        def android(argv,timeout):
            expected = [context.LIST,context.PATHS,context.PATHS,context.LIST]
            index = len(state['commands'])
            entry.require(index < len(expected) and list(argv) == expected[index] and timeout == 15,
                          'EXACT_FOUR_ARTIFACT_METADATA_MEMORY_COMMANDS')
            state['commands'].append(list(argv))
            return metadata_raw if argv == context.LIST else paths_raw
        def hash_boundary(self,fd,row,deadline):
            entry.require(records[fd] == row['held_file'] and fd not in state['closed'] and
                          row == known[row['path']], 'ACTUAL_HELD_FILE_MAPPING_TO_HASH_BOUNDARY')
            state['hash_routes'].append(row['path'])
            return copy.deepcopy(row)
        Route = type('ProductionArtifactRouteWithHashBoundary',(Production,),{'_hash':hash_boundary})
        ctx = types.SimpleNamespace(target=types.SimpleNamespace(open_root=open_root),android=android,
                                    deadline=time.monotonic()+1000,artifacts=None)
        held = Route(ctx,artifact,parser)
        try:
            before = held.before()
            entry.require(before == {'metadata':exact,'artifacts':artifact['current_artifacts'],
                'fresh_streaming_hashes':True,'signer_independently_verified':False},
                'REAL_ARTIFACT_BEFORE_FIXED_REFERENCE_MAPPING')
            if named_drift:
                try:held.after()
                except RuntimeError as error:
                    entry.require(str(error) == tag+'_APK_NAMED_PATH_CHANGED', 'NAMED_DRIFT_FIRST_ERROR')
                else:raise RuntimeError('NAMED_ARTIFACT_DRIFT_ACCEPTED')
            else:
                after = held.after()
                entry.require(before == after and
                              state['hash_routes'] == [row['path'] for row in artifact['current_artifacts']]*2,
                              'REAL_ARTIFACT_AFTER_FIXED_REFERENCE_MAPPING')
        finally:
            closed = held.close()
        entry.require(sorted(state['opened']) == sorted(state['closed']) and
                      len(set(state['closed'])) == len(state['closed']) and ctx.artifacts is None and
                      closed['held_APK_FDs_closed'] == context.APK_COUNT and
                      len(state['commands']) == 4 and artifact == original,
                      'ARTIFACT_ROUTE_COMPLETE_MEMORY_FD_CLOSURE')
        return state
    stream_route()
    add('production_before_after_routes_current_artifacts_and_exact_held_file')
    stream_route(True)
    add('production_named_identity_drift_rejected_and_all_memory_FDs_closed')
    # Exercise the original hash implementation separately with a small, explicit
    # byte fixture. Its identity schema is copied from the actual held_file row.
    data = b'fixed-original-hash-method-control\n'*2200
    row = copy.deepcopy(artifact['current_artifacts'][0])
    row['held_file']['bytes'] = len(data);row['sha256'] = hashlib.sha256(data).hexdigest()
    def hash_case(identity_drift=False, wrong_sha=False):
        state,records,allocate,fake_os,Production = fd_fixture()
        observed = copy.deepcopy(row['held_file'])
        if identity_drift:observed['mtime_ns'] += 1
        fd = allocate(observed,data)
        expected = copy.deepcopy(row)
        if wrong_sha:expected['sha256'] = '0'*64
        held = Production(types.SimpleNamespace(artifacts=None),artifact,parser)
        try:
            if identity_drift:
                try:held._hash(fd,expected,time.monotonic()+5)
                except RuntimeError as error:
                    entry.require(str(error) == 'ACTUAL_'+tag+'_APK_IDENTITY_CHANGED', 'HASH_IDENTITY_FIRST_ERROR')
                else:raise RuntimeError('HASH_IDENTITY_DRIFT_ACCEPTED')
                entry.require(state['read'] == state['seek'] == 0, 'IDENTITY_DRIFT_READ_BEFORE_REJECTION')
            elif wrong_sha:
                try:held._hash(fd,expected,time.monotonic()+5)
                except RuntimeError as error:
                    entry.require(str(error) == 'ACTUAL_'+tag+'_APK_CONTENT_CHANGED', 'HASH_CONTENT_FIRST_ERROR')
                else:raise RuntimeError('WRONG_ARTIFACT_HASH_ACCEPTED')
            else:
                result = held._hash(fd,expected,time.monotonic()+5)
                entry.require(result == row and state['read'] >= 3 and state['seek'] == 1,
                              'REAL_ARTIFACT_STREAM_HASH_AND_HELD_RECORD_SCHEMA')
        finally:
            fake_os.close(fd);held.close()
        entry.require(state['opened'] == state['closed'], 'HASH_CONTROL_MEMORY_FD_CLOSURE')
    hash_case()
    add('original_stream_hash_method_accepts_small_bytes_with_actual_held_file_schema')
    hash_case(identity_drift=True)
    add('original_stream_hash_method_rejects_held_ns_drift_before_read')
    hash_case(wrong_sha=True)
    add('original_stream_hash_method_rejects_wrong_content_sha')
    entry.require(len(rows) == 10 and artifact == original, 'EXACT_TEN_ARTIFACT_SCHEMA_CONTROLS')
    return rows
