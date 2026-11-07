
def checkpoint():
    require(time.monotonic() < DEADLINE, 'locked vendor preparation deadline exhausted')
    require(not CLEANUP_ERRORS, 'prior owned close error prevents further preparation')

def tracked_open(path, flags, mode=0o600):
    fd = os.open(path, flags|os.O_CLOEXEC|os.O_NOFOLLOW, mode)
    ACTIVE_FDS.add(fd)
    return fd

def close_tracked(fd, label):
    if fd not in ACTIVE_FDS:
        CLEANUP_ERRORS.append({'stage':label,'error':'attempt to close an unowned or already closed descriptor'})
        return
    ACTIVE_FDS.remove(fd)
    try:
        os.close(fd)
    except BaseException as error:
        # A failed Linux close is never retried against a possibly reused number.
        CLEANUP_ERRORS.append({'stage':label,'error':repr(error)})

def complete_write(fd, data):
    offset = 0
    while offset < len(data):
        checkpoint()
        written = os.write(fd, data[offset:])
        require(written > 0, 'short owned output write')
        offset += written

def owned_file(path, data, mode=0o444):
    require(path.is_relative_to(OUT) and '..' not in path.parts, 'owned output escaped attempt')
    real_directory(path.parent)
    fd = tracked_open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 1000 and
                before.st_gid == 1000 and before.st_nlink == 1 and before.st_size == 0,
                'create-only owned leaf identity differs')
        complete_write(fd, data)
        os.fchmod(fd, mode)
        os.fsync(fd)
        after = os.fstat(fd)
        require(after.st_size == len(data) and identity(after) == identity(path.lstat()),
                'created owned leaf changed before close')
    finally:
        close_tracked(fd, 'owned-file-close:'+str(path))
    checkpoint()
    row = hash_held(path, max(1,len(data)))
    require(row['bytes'] == len(data) and row['sha256'] == sha(data), 'owned bytes differ after close')
    return row

def locked_packages(lock_raw, rows_raw):
    require(len(lock_raw) == 51836 and sha(lock_raw) == LOCK_SHA, 'original workspace lock differs')
    lock = tomllib.loads(lock_raw.decode('utf-8'))
    require(len(lock['package']) == 221, 'original workspace package count differs')
    records = []
    for item in lock['package']:
        if 'source' not in item:
            continue
        require(item['source'] == 'registry+https://github.com/rust-lang/crates.io-index',
                'non-crates-io locked source is outside this fixed preparation')
        name, version, checksum = item['name'],item['version'],item.get('checksum','')
        require(re.fullmatch(r'[A-Za-z0-9_-]+',name) is not None and
                re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9_.+-]+)?',version) is not None and
                re.fullmatch(r'[0-9a-f]{64}',checksum) is not None,
                'noncanonical original locked package')
        records.append({'name':name,'version':version,'source':item['source'],'checksum':checksum})
    records.sort(key=lambda p:(p['name'],p['version']))
    require(len(records) == 193 and len({(p['name'],p['version']) for p in records}) == 193,
            'fixed 193 registry identities differ')
    plan = json.loads(rows_raw)
    require(sha(rows_raw) == REGISTRY_ROWS_SHA and plan ==
            {'schema':1,'lock_bytes':51836,'lock_sha256':LOCK_SHA,'packages':records},
            'explicit 193-package allowlist is not the exact original lock')
    return records

def paired_cache_namespace(registry, packages):
    require(registry['state'] == 'PASS' and registry['collection_complete'] is True and
            registry['all_45_archive_and_source_matches'] is True and
            registry['authorities_unchanged_after'] is True and
            registry['owned_resource_gate']['pass'] is True,
            'original 45-package authority is incomplete')
    authority = {(p['name'],p['version']):p for p in registry['packages']}
    require(len(authority) == len(registry['packages']) == 45, 'original authority package count differs')
    old = {(p['name'],p['version']):p for p in packages}
    source_roots = {str(Path(p['source_directory']).parent) for p in authority.values()}
    archive_roots = {str(Path(p['expected_archive_path']).parent) for p in authority.values()}
    require(len(source_roots) == len(archive_roots) == 1, 'original registry has multiple cache namespaces')
    source_root, archive_root = Path(next(iter(source_roots))),Path(next(iter(archive_roots)))
    require(source_root.parent == CARGO_HOME/'registry/src' and
            archive_root.parent == CARGO_HOME/'registry/cache' and
            source_root.name == archive_root.name and
            re.fullmatch(r'index\.crates\.io-[0-9a-f]+',source_root.name) is not None,
            'original authority is not the paired fixed Cargo namespace')
    real_directory(source_root)
    real_directory(archive_root)
    for key,row in authority.items():
        require(key in old and
                row['source_directory'] == str(source_root/(key[0]+'-'+key[1])) and
                row['expected_archive_path'] == str(archive_root/(key[0]+'-'+key[1]+'.crate')) and
                row['expected_lock_checksum'] == old[key]['checksum'] and
                row['comparison']['archive_matches_lock'] is True and
                row['comparison']['every_archive_file_matches_held_extracted_source'] is True,
                'original authority is not an exact subset of this workspace lock')
    return source_root,archive_root,authority

def fixed_archive_presence(packages, archive_root):
    # These are exactly 193 names derived from the already held original lock.
    # Do not enumerate the cache directory, discover packages, or rewrite it.
    observations, missing = {}, []
    for package in packages:
        checkpoint()
        leaf = package['name']+'-'+package['version']+'.crate'
        path = archive_root/leaf
        try:
            before = path.lstat()
        except FileNotFoundError:
            observations[leaf] = {'path':str(path),'absent':True}
            missing.append(package)
            continue
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_ARCHIVE_BYTES,
                'fixed cached archive is an alias, special file or oversized: '+leaf)
        observations[leaf] = {'path':str(path),'absent':False,'identity':identity(before)}
    return observations,missing

def copy_cached_archive(path, destination, package, presence):
    checkpoint()
    source_fd = tracked_open(path, os.O_RDONLY)
    output_fd = -1
    try:
        before = os.fstat(source_fd)
        require(identity(before) == presence['identity'] == identity(path.lstat()) and
                stat.S_ISREG(before.st_mode), 'fixed cached archive changed after presence observation')
        output_fd = tracked_open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
        digest,total = hashlib.sha256(),0
        while True:
            checkpoint()
            part = os.read(source_fd,65536)
            if not part:
                break
            total += len(part)
            require(total <= MAX_ARCHIVE_BYTES, 'cached archive exceeded fixed bound')
            digest.update(part)
            complete_write(output_fd,part)
        require(total == before.st_size and digest.hexdigest() == package['checksum'] and
                identity(before) == identity(os.fstat(source_fd)) == identity(path.lstat()),
                'cached archive does not match its original lock or changed while copying')
        os.fchmod(output_fd,0o444)
        os.fsync(output_fd)
        require(os.fstat(output_fd).st_size == total and
                identity(os.fstat(output_fd)) == identity(destination.lstat()),
                'private archive output changed')
        original = {'path':str(path),'bytes':total,'sha256':digest.hexdigest(),'identity':identity(before)}
    finally:
        if output_fd >= 0:
            close_tracked(output_fd,'private-archive-close')
        close_tracked(source_fd,'cached-archive-close')
    checkpoint()
    copied = hash_held(destination,MAX_ARCHIVE_BYTES)
    require(copied['sha256'] == package['checksum'] and copied['bytes'] == original['bytes'],
            'private cached archive copy differs')
    return copied,original

def fetch_locked_archive(destination, package, network):
    checkpoint()
    name,version = package['name'],package['version']
    relative = '/crates/'+name+'/'+name+'-'+version+'.crate'
    url = 'https://static.crates.io'+relative
    require(len(network) < MAX_MISSING_PACKAGES, 'fixed fetch count exhausted')
    row = {'name':name,'version':version,'url':url,'expected_sha256':package['checksum'],
           'http_requests':0,'automatic_retries':0,'redirects_followed':0,'complete':False,
           'response_closed':False,'connection_closed':False}
    network.append(row)
    connection,response,fd = None,None,-1
    try:
        # Direct HTTPS ignores all proxy/auth environment. No redirect or retry API is used.
        context = ssl.create_default_context()
        connection = http.client.HTTPSConnection('static.crates.io',443,
                    timeout=min(5,max(0.1,DEADLINE-time.monotonic())),context=context)
        row['http_requests'] = 1
        connection.request('GET',relative,headers={
            'User-Agent':'pocket4-fixed-locked-registry-prep/1',
            'Accept':'application/octet-stream','Accept-Encoding':'identity','Connection':'close'})
        response = connection.getresponse()
        row['status'] = response.status
        row['content_length'] = response.getheader('Content-Length')
        row['content_encoding'] = response.getheader('Content-Encoding')
        require(response.status == 200, 'fixed official crate GET did not return 200')
        require(row['content_encoding'] in (None,'identity'), 'unexpected HTTP content encoding')
        advertised = row['content_length']
        require(advertised is None or (advertised.isdecimal() and 0 < int(advertised) <= MAX_ARCHIVE_BYTES),
                'crate Content-Length exceeds bound')
        fd = tracked_open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
        digest,total = hashlib.sha256(),0
        while True:
            checkpoint()
            part = response.read1(65536)
            if not part:
                break
            total += len(part)
            row['received_bytes'] = total
            require(total <= MAX_ARCHIVE_BYTES and
                    sum(item.get('received_bytes',0) for item in network) <= MAX_NETWORK_BYTES,
                    'fixed per-archive or aggregate network byte bound exceeded')
            digest.update(part)
            complete_write(fd,part)
        require(total > 0 and (advertised is None or total == int(advertised)) and
                digest.hexdigest() == package['checksum'],
                'complete official crate bytes do not match original Cargo.lock')
        os.fchmod(fd,0o444)
        os.fsync(fd)
        require(os.fstat(fd).st_size == total and identity(os.fstat(fd)) == identity(destination.lstat()),
                'fetched private archive changed')
        row['sha256'] = digest.hexdigest()
        row['complete'] = True
    finally:
        if fd >= 0:
            close_tracked(fd,'fetched-archive-close')
        if response is not None:
            try:
                response.close()
                row['response_closed'] = True
            except BaseException as error:
                CLEANUP_ERRORS.append({'stage':'http-response-close','error':repr(error)})
        if connection is not None:
            try:
                connection.close()
                row['connection_closed'] = True
            except BaseException as error:
                CLEANUP_ERRORS.append({'stage':'https-connection-close','error':repr(error)})
    checkpoint()
    copied = hash_held(destination,MAX_ARCHIVE_BYTES)
    require(row['complete'] and row['response_closed'] and row['connection_closed'] and
            copied['sha256'] == package['checksum'] and copied['bytes'] == row['received_bytes'],
            'download has no complete closed checksum-qualified original')
    return copied

def vendor_directory(path):
    require(path.is_relative_to(VENDOR) and '..' not in path.parts, 'vendor directory escaped root')
    if path == VENDOR:
        real_directory(path)
        return
    vendor_directory(path.parent)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    current = path.lstat()
    require(stat.S_ISDIR(current.st_mode) and current.st_uid == 1000 and current.st_gid == 1000 and
            stat.S_IMODE(current.st_mode) == 0o700,
            'vendor parent is not this private real directory')

def unpack_locked_archive(archive, package, expanded_before):
    checkpoint()
    name,version = package['name'],package['version']
    root = VENDOR/(name+'-'+version)
    root.mkdir(mode=0o700)
    files,explicit_directories,total = {},set(),0
    archive_fd = tracked_open(archive,os.O_RDONLY)
    stream = packed = None
    duplicate_fd = -1
    try:
        before = os.fstat(archive_fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 1000 and before.st_nlink == 1 and
                stat.S_IMODE(before.st_mode) == 0o444 and 0 < before.st_size <= MAX_ARCHIVE_BYTES,
                'private archive is not the newly owned immutable leaf')
        duplicate_fd = os.dup(archive_fd)
        ACTIVE_FDS.add(duplicate_fd)
        stream = os.fdopen(duplicate_fd,'rb',closefd=False)
        packed = tarfile.open(fileobj=stream,mode='r:gz')
        prefix = name+'-'+version+'/'
        for member in packed:
            checkpoint()
            if member.isdir() and member.name.rstrip('/') == name+'-'+version:
                require('' not in explicit_directories, 'duplicate archive root')
                explicit_directories.add('')
                continue
            require(member.name.startswith(prefix) and not member.name.startswith('/'),
                    'archive root does not match exact locked package')
            relative = member.name[len(prefix):]
            path = PurePosixPath(relative)
            require(relative and str(path) == relative.rstrip('/') and '..' not in path.parts and
                    not path.is_absolute() and '\\' not in relative and '\x00' not in relative,
                    'archive contains a noncanonical or escaping path')
            require(len(files)+len(explicit_directories) < 4096, 'archive member bound exceeded')
            if member.isdir():
                require(relative not in explicit_directories, 'duplicate archive directory')
                explicit_directories.add(relative)
                vendor_directory(root/path)
                continue
            require(member.isfile() and relative not in files and
                    relative not in ('.cargo-checksum.json','.cargo-ok'),
                    'archive contains alias/special/duplicate/reserved metadata')
            require(0 <= member.size <= 16*1024*1024 and total+member.size <= 64*1024*1024 and
                    expanded_before+total+member.size <= MAX_ALL_SOURCE_BYTES,
                    'archive per-file, per-package or aggregate expansion bound exceeded')
            vendor_directory((root/path).parent)
            reader = packed.extractfile(member)
            require(reader is not None, 'archive member is unreadable')
            chunks,size = [],0
            try:
                while True:
                    checkpoint()
                    part = reader.read(65536)
                    if not part:
                        break
                    size += len(part)
                    require(size <= member.size, 'archive member exceeds declared bytes')
                    chunks.append(part)
            finally:
                try:
                    reader.close()
                except BaseException as error:
                    CLEANUP_ERRORS.append({'stage':'tar-member-close','error':repr(error)})
            require(size == member.size, 'archive member is truncated')
            data = b''.join(chunks)
            mode = 0o555 if member.mode & 0o111 else 0o444
            files[relative] = owned_file(root/path,data,mode)
            total += size
        require(files and 'Cargo.toml' in files, 'archive has no actual package manifest')
        manifest_raw,manifest_pin = held(root/'Cargo.toml',1024*1024)
        manifest = tomllib.loads(manifest_raw.decode('utf-8'))['package']
        require(manifest['name'] == name and manifest['version'] == version and
                manifest_pin == files['Cargo.toml'], 'archive package identity differs from locked name/version')
        checksums = {'package':package['checksum'],
                     'files':{relative:row['sha256'] for relative,row in sorted(files.items())}}
        check_raw = (json.dumps(checksums,sort_keys=True,separators=(',',':'))+'\n').encode()
        checksum_pin = owned_file(root/'.cargo-checksum.json',check_raw)
        inventory = regular_tree(root,4096,64*1024*1024)
        require(set(inventory) == set(files)|{'.cargo-checksum.json'} and
                all(inventory[path] == row for path,row in files.items()) and
                inventory['.cargo-checksum.json'] == checksum_pin and
                identity(before) == identity(os.fstat(archive_fd)) == identity(archive.lstat()) and
                hash_held(archive,MAX_ARCHIVE_BYTES)['sha256'] == package['checksum'],
                'private archive/vendor complete mapping changed')
        return {'name':name,'version':version,'package_checksum':package['checksum'],
                'directory':str(root),'archive':hash_held(archive,MAX_ARCHIVE_BYTES),
                'source_files':len(files),'source_bytes':total,'checksum_metadata':checksum_pin,
                'files':inventory}
    finally:
        if packed is not None:
            try:
                packed.close()
            except BaseException as error:
                CLEANUP_ERRORS.append({'stage':'tar-close','error':repr(error)})
        if stream is not None:
            try:
                stream.close()
            except BaseException as error:
                CLEANUP_ERRORS.append({'stage':'tar-stream-close','error':repr(error)})
        if duplicate_fd >= 0:
            close_tracked(duplicate_fd,'tar-stream-descriptor-close')
        close_tracked(archive_fd,'private-unpack-archive-close')

def current_owned_children():
    path = Path('/proc/self/task')/str(os.getpid())/'children'
    fd = tracked_open(path,os.O_RDONLY)
    try:
        raw = os.read(fd,4097)
        require(len(raw) <= 4096 and os.read(fd,1) == b'', 'own children observation exceeded bound')
        require(raw.strip() == b'', 'unexpected own child in no-execution source preparation')
        return {'observed_empty':True,'path':str(path)}
    finally:
        close_tracked(fd,'own-children-observation-close')



def execute():
    global DEADLINE
    require(os.getuid() == 1000 and os.geteuid() == 1000, 'ordinary operator UID1000 required')
    require(Path(__file__).absolute() == HERE/'prepare_vendor.py', 'exact staged preparation source required')
    real_directory(HERE)
    require(not OUT.exists() and not OUT.is_symlink(), 'create-only preparation attempt already exists')
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    ARCHIVES.mkdir(mode=0o700)
    VENDOR.mkdir(mode=0o700)
    DEADLINE = time.monotonic()+WORK_SECONDS
    report = {'schema':1,'state':'RUNNING','phase':'RESOURCE_ADMISSION','started_utc':utc(),
        'scope':'fixed original-lock registry archive preparation into an independent vendor source',
        'Main_actions':0,'Main_identity_observed':False,'Android_or_Soong_executed':False,
        'Cargo_executed':False,'crate_code_executed':False,'shared_cache_writes':0,
        'workspace_or_lock_modified':False,'production_sources_modified':False,
        'metadata_or_compile_qualified':False,'production_ready':False,'collection_complete':False,
        'commands_executed':0,'new_controls':0,'downloads':[],'packages':[],'secondary_errors':[],
        'network_policy':{'host':'static.crates.io','method':'GET','automatic_retries':0,
            'redirects_allowed':False,'maximum_missing_packages':MAX_MISSING_PACKAGES,
            'maximum_download_bytes':MAX_NETWORK_BYTES,'maximum_archive_bytes':MAX_ARCHIVE_BYTES,
            'only_exact_original_lock_name_version_checksum':True}}
    def interrupted(number,frame):
        OBSERVED_SIGNALS.append(number)
        raise RuntimeError('owned preparation interrupted by signal '+str(number))
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGINT,interrupted)
    signal.signal(signal.SIGALRM,interrupted)
    signal.setitimer(signal.ITIMER_REAL,WORK_SECONDS)
    resource_fd,resource_before = -1,None
    authority_rows,cached_rows,prior_source_rows = {},{},{}
    vendor_rows,archive_rows,prepared_packages = {},{},[]
    presence,archive_root = {},None
    vendor_manifest_pin,config_pin = None,None
    def secondary(stage,error):
        report['state'] = 'FAIL'
        report['secondary_errors'].append({'stage':stage,'error':repr(error)})
    try:
        resource_fd,resource_before = begin_resources()
        report['owned_resources_before'] = resource_before
        fresh_host_memory_admission(report)
        report['own_children_before'] = current_owned_children()
        report['phase'] = 'FIXED_LOCK_AND_ACTUAL_AUTHORITY'
        lock_raw,lock_pin = pinned_packet('original-Cargo.lock',LOCK_SHA)
        rows_raw,rows_pin = pinned_packet('locked-registry-packages.json',REGISTRY_ROWS_SHA)
        packages = locked_packages(lock_raw,rows_raw)
        original_raw,original_pin = pinned_packet('parent469-manifest.json',
                    '88dc3c8020c436009862800ffdc5af97f50f6ae7efff832562c2784d66794701')
        original = json.loads(original_raw)
        require(len(original) == 499 and original['Cargo.lock']['kind'] == 'file' and
                original['Cargo.lock']['bytes'] == 51836 and original['Cargo.lock']['sha256'] == LOCK_SHA,
                'actual 499 source manifest does not bind this original Cargo.lock')
        parent_raw,parent_pin = pinned_packet('parent469-result.json',
                    '3636057b9a20fc895657064da3fb66d8ded7e69ebfa5a5b92072a51b33f29fd5')
        parent = json.loads(parent_raw)
        require(parent['state'] == 'PASS' and parent['copied_manifest']['sha256'] == original_pin['sha256'] and
                parent['source_delta']['actual_source_file_count'] == 499 and
                parent['original_source_unchanged_after'] is True and
                parent['copied_source_unchanged_after'] is True and
                parent['owned_resource_gate']['pass'] is True and
                not parent['cleanup']['errors'] and not parent['cleanup']['remaining'] and
                parent['cleanup']['forced_cleanup'] is False,
                'actual469 source authority is incomplete')
        failure_raw,failure_pin = pinned_packet('wayland01-metadata.stderr',
                    '78702e8a0954bbeffd0d1704a8fdbc87719b80009f616d9c2dbd5f1338117200')
        require(failure_raw == b'error: failed to download \x60flate2 v1.1.9\x60\n\nCaused by:\n  attempting to make an HTTP request, but --offline was specified\n',
                'original offline metadata failure differs')
        registry_raw,registry_pin = pinned_packet('registry-result.json',
                    'b7f723a9898e6db5abd181cafb02afc3d9a6e2e2c2ec0119b7c20c82ebd62993')
        registry = json.loads(registry_raw)
        source_root,archive_root,prior = paired_cache_namespace(registry,packages)
        for row in [lock_pin,rows_pin,original_pin,parent_pin,failure_pin,registry_pin]:
            authority_rows[row['path']] = row
        stage_raw,stage_pin = held(ROOT/'stage-receipt.json',1024*1024)
        stage = json.loads(stage_raw)
        expected_staged = {'prepare_vendor.py','locked-registry-packages.json','original-Cargo.lock',
                           'parent469-manifest.json','parent469-result.json','wayland01-metadata.stderr',
                           'registry-result.json'}
        require(stage['schema'] == 1 and set(stage['files']) == expected_staged and
                stage['transferred_source_files'] == 2 and stage['reused_fixed_authority_files'] == 5 and
                stage['Main_actions'] == 0 and stage['only_owned_root_written'] is True,
                'fixed preparation staging receipt shape differs')
        self_raw,self_pin = held(HERE/'prepare_vendor.py',128*1024)
        require(stage['files']['prepare_vendor.py'] ==
                    {'bytes':self_pin['bytes'],'sha256':self_pin['sha256']} and
                all(stage['files'][Path(row['path']).name] ==
                    {'bytes':row['bytes'],'sha256':row['sha256']} for row in authority_rows.values()),
                'staging receipt does not bind the complete preparation source')
        authority_rows[stage_pin['path']] = stage_pin
        authority_rows[self_pin['path']] = self_pin
        report['authorities'] = list(authority_rows.values())
        report['fixed_registry_packages'] = len(packages)
        report['shared_cache_namespace'] = {'archive_root':str(archive_root),'source_root':str(source_root)}
        report['phase'] = 'FIXED_193_ARCHIVE_PRESENCE'
        presence,missing = fixed_archive_presence(packages,archive_root)
        report['cache_presence'] = write_new(OUT/'fixed-cache-presence.json',presence)
        report['missing_locked_packages'] = missing
        require(len(missing) <= MAX_MISSING_PACKAGES,
                'missing archive count exceeds the fixed original lock; no network requests were sent')
        report['phase'] = 'ORIGINAL_45_ARCHIVE_AND_SOURCE_GATE'
        by_key = {(p['name'],p['version']):p for p in packages}
        prior_summaries = []
        for key,known in sorted(prior.items()):
            checkpoint()
            item = by_key[key]
            comparison,files,archive_pin = qualify_cached_archive(
                Path(known['expected_archive_path']),Path(known['source_directory']),
                key[0],key[1],item['checksum'])
            require(archive_pin['sha256'] == known['comparison']['archive']['sha256'],
                    'one of the prior 45 archive contents differs')
            cached_rows[archive_pin['path']] = archive_pin
            prior_source_rows.update({row['path']:row for row in files.values()})
            prior_summaries.append({'name':key[0],'version':key[1],
                'archive':archive_pin,'source_inventory':comparison['source_inventory'],
                'every_archive_file_matches_held_extracted_source':True})
        report['original_45_requalification'] = prior_summaries
        report['phase'] = 'COPY_OR_FETCH_EXACT_LOCKED_ARCHIVES'
        all_archive_bytes = 0
        for package in packages:
            checkpoint()
            leaf = package['name']+'-'+package['version']+'.crate'
            destination = ARCHIVES/leaf
            old = presence[leaf]
            if old['absent']:
                copied = fetch_locked_archive(destination,package,report['downloads'])
                origin = 'single-official-GET-missing-cache-leaf'
            else:
                copied,original_cached = copy_cached_archive(
                    Path(old['path']),destination,package,old)
                cached_rows[original_cached['path']] = original_cached
                origin = 'fixed-cache-complete-checksum-copy'
            all_archive_bytes += copied['bytes']
            require(all_archive_bytes <= MAX_ALL_ARCHIVE_BYTES,
                    'aggregate original archive bytes exceed bound')
            archive_rows[str(destination)] = copied
            report['packages'].append({'name':package['name'],'version':package['version'],
                'lock_checksum':package['checksum'],'archive':copied,'origin':origin})
        report['archive_bytes'] = all_archive_bytes
        report['phase'] = 'SAFE_COMPLETE_ARCHIVE_TO_VENDOR_MAPPING'
        expanded = 0
        for package in packages:
            checkpoint()
            archive = ARCHIVES/(package['name']+'-'+package['version']+'.crate')
            prepared = unpack_locked_archive(archive,package,expanded)
            checkpoint()
            expanded += prepared['source_bytes']+prepared['checksum_metadata']['bytes']
            require(expanded <= MAX_ALL_SOURCE_BYTES, 'aggregate vendor bytes exceed bound')
            prepared_packages.append(prepared)
            vendor_rows.update({row['path']:row for row in prepared['files'].values()})
        report['vendor_source_bytes'] = expanded
        report['vendor_file_count'] = len(vendor_rows)
        config = ('[source.crates-io]\nreplace-with = "pocket4-locked-vendor"\n\n'
                  '[source.pocket4-locked-vendor]\ndirectory = '+json.dumps(str(VENDOR))+
                  '\n\n[net]\noffline = true\n').encode()
        config_pin = owned_file(OUT/'vendor-config.toml',config)
        manifest = {'schema':1,'source':'exact-crates-io-original-workspace-lock',
            'original_lock':{'bytes':51836,'sha256':LOCK_SHA},
            'registry_allowlist':{'bytes':rows_pin['bytes'],'sha256':rows_pin['sha256']},
            'vendor_root':str(VENDOR),'archive_root':str(ARCHIVES),
            'registry_packages':193,'source_config':config_pin,
            'packages':prepared_packages,'metadata_or_compilation_executed':False}
        manifest_raw = (json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
        require(len(manifest_raw) <= 32*1024*1024, 'complete vendor manifest exceeds bound')
        vendor_manifest_pin = owned_file(OUT/'vendor-manifest.json',manifest_raw)
        report['vendor_manifest'] = vendor_manifest_pin
        report['source_config'] = config_pin
        require(len(prepared_packages) == 193 and len(archive_rows) == 193,
                'fixed original lock was not completely prepared')
        report['phase'] = 'FINAL_INPUT_CLEANUP_AND_RESOURCE_GATES'
        report['state'] = 'PASS'
    except Exception as error:
        report['state'] = 'FAIL'
        report['error'] = repr(error)
        report['error_detail'] = {'type':type(error).__name__,'message':str(error),
            'errno':getattr(error,'errno',None),'filename':getattr(error,'filename',None)}
    finally:
        # The independent outer 360s ceiling remains in force during final housekeeping.
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT,signal.SIGALRM})
        report['observed_signals'] = OBSERVED_SIGNALS
        for fd in sorted(list(ACTIVE_FDS)):
            close_tracked(fd,'final-explicit-owned-fd-close')
        for label,rows in [('authorities',authority_rows),('original_cached_archives',cached_rows),
                           ('original_45_sources',prior_source_rows),('private_archives',archive_rows),
                           ('vendor_sources',vendor_rows)]:
            changes = []
            for path,before in rows.items():
                try:
                    require(time.monotonic() < DEADLINE, 'final source verification deadline exhausted')
                    if hash_held(Path(path)) != before:
                        changes.append(path)
                except Exception as error:
                    changes.append({'path':path,'error':repr(error)})
                    if time.monotonic() >= DEADLINE:
                        break
            report[label+'_changes'] = changes
            if changes:
                secondary(label+'_after',RuntimeError('fixed input/output changed or verification incomplete'))
        try:
            if presence:
                after,unused_missing = fixed_archive_presence(packages,archive_root)
                report['shared_cache_presence_unchanged'] = after == presence
                require(after == presence, 'fixed shared cache presence changed during preparation')
            else:
                report['shared_cache_presence_unchanged'] = None
            if report['state'] == 'PASS':
                require(report['shared_cache_presence_unchanged'] is True and
                        len(authority_rows) == 8 and len(prepared_packages) == 193 and len(archive_rows) == 193 and
                        bool(prior_source_rows) and bool(vendor_rows),
                        'successful preparation lacks its complete input/output baseline')
                for package in prepared_packages:
                    require(regular_tree(Path(package['directory']),4096,64*1024*1024) == package['files'],
                            'private vendor gained/lost an unqualified member')
                require(hash_held(Path(vendor_manifest_pin['path'])) == vendor_manifest_pin and
                        hash_held(Path(config_pin['path'])) == config_pin,
                        'private complete manifest or explicit source config changed')
        except Exception as error:
            secondary('fixed_presence_or_vendor_namespace_after',error)
        try:
            report['own_children_after'] = current_owned_children()
        except Exception as error:
            secondary('unexpected_own_children',error)
        try:
            require(resource_fd >= 0 and resource_before is not None, 'owned resource admission was not established')
            report['owned_resource_gate'] = finish_resources(resource_fd,resource_before,report)
        except Exception as error:
            report['owned_resource_gate'] = {'pass':False,'error':repr(error)}
            secondary('owned_resources_after',error)
        finally:
            if resource_fd >= 0:
                try:
                    os.close(resource_fd)
                    report['owned_resource_fd_closed'] = True
                except Exception as error:
                    report['owned_resource_fd_closed'] = False
                    secondary('owned_resource_fd_close',error)
        report['explicit_owned_descriptor_journal'] = {
            'remaining':sorted(ACTIVE_FDS),'close_errors':CLEANUP_ERRORS,
            'scope':'explicit preparation descriptors, not an audit of every Python runtime descriptor'}
        if ACTIVE_FDS or CLEANUP_ERRORS:
            secondary('explicit_owned_fds',RuntimeError('created or held descriptor cleanup is incomplete'))
        if time.monotonic() >= DEADLINE:
            secondary('work_deadline',TimeoutError('preparation or final qualification exceeded 300 seconds'))
        require(report['state'] in ('PASS','FAIL'), 'invalid terminal state')
        report['collection_complete'] = report['state'] == 'PASS'
        report['offline_vendor_prepared_qualified'] = report['state'] == 'PASS'
        report['finished_utc'] = utc()
        result = write_new(OUT/'result.json',report)
        print(json.dumps({'state':report['state'],'phase':report['phase'],'result':result,
            'collection_complete':report['collection_complete'],
            'offline_vendor_prepared_qualified':report['offline_vendor_prepared_qualified'],
            'original_lock_sha256':LOCK_SHA,'fixed_registry_packages':193,
            'prepared_packages':len(prepared_packages),'http_requests':sum(x['http_requests'] for x in report['downloads']),
            'download_bytes':sum(x.get('received_bytes',0) for x in report['downloads']),
            'missing_locked_packages':report.get('missing_locked_packages'),
            'vendor_manifest':report.get('vendor_manifest'),'source_config':report.get('source_config'),
            'Main_actions':0,'Cargo_executed':False,'crate_code_executed':False,
            'shared_cache_writes':0,'production_ready':False,
            'owned_resource_gate':{k:report.get('owned_resource_gate',{}).get(k) for k in
                                  ['pass','memory_peak','memory_swap_peak','memory_events_delta','swap_max_observed_only']},
            'own_children_after':report.get('own_children_after'),
            'explicit_owned_descriptor_journal':report['explicit_owned_descriptor_journal'],
            'error':report.get('error'),'secondary_errors':report['secondary_errors']}),flush=True)
    return 0 if report['state'] == 'PASS' else 1

if __name__ == '__main__':
    if sys.argv[1:] == []:
        print(json.dumps({'mode':'PLAN','root':str(ROOT),'fixed_registry_packages':193,
            'original_lock_sha256':LOCK_SHA,'requires_execute_once':True,
            'maximum_missing_packages':MAX_MISSING_PACKAGES,'maximum_network_bytes':MAX_NETWORK_BYTES,
            'shared_cache_writes':0,'Cargo_or_crate_execution':False,'Main_actions':0}))
    elif sys.argv[1:] == ['--execute-once']:
        raise SystemExit(execute())
    else:
        raise SystemExit('usage: prepare_vendor.py [--execute-once]')
