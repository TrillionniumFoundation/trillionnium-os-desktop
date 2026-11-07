ROOT=Path('/home/alex/work/pocket4-blueprint-streaming-builder-registry-readonly-01-20261105')
SOURCE=Path('/home/alex/work/pocket4-blueprint-streaming-builder-450-compile-02-20261105/builder-source')
LOCK=SOURCE/'Cargo.lock'
TREE=SOURCE.parent/'control-source/selected-build.stdout'
SOURCE_ROOT=Path('/home/alex/.cargo/registry/src')
CACHE_ROOT=Path('/home/alex/.cargo/registry/cache')
LOCK_SHA='c1dfa6f13f789cf40435d0d72973d029d0e264b27bd833eabb5a727492127f62'
TREE_SHA='82ad8aefece0dedb3a992db45b5de4097ebbb2c0fd02ed00ffe50c401bd4dd0d'
DEADLINE=None

def error_detail(error):
    return {'type':type(error).__name__,'message':str(error),
            'errno':getattr(error,'errno',None),'filename':str(getattr(error,'filename',None))}

def observe_file(path,maximum,include_text=False):
    try:
        raw,row=held(path,maximum)
        if include_text:row['text']=raw.decode('utf-8')
        return row
    except OSError as error:return {'path':str(path),'error':error_detail(error)}

def archive_source_comparison(archive,directory,name,version,expected):
    fd=os.open(archive,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0<before.st_size<=32*1024*1024,'archive type/size outside bound')
        digest=hashlib.sha256();size=0
        while True:
            chunk=os.read(fd,65536)
            if not chunk:break
            size+=len(chunk);require(size<=32*1024*1024,'archive grew beyond bound');digest.update(chunk)
        archive_pin={'path':str(archive),'bytes':size,'sha256':digest.hexdigest(),'identity':identity(before)}
        require(size==before.st_size and digest.hexdigest()==expected,'existing archive checksum differs from original Cargo.lock')
        source_before=regular_tree(directory,4096,64*1024*1024)
        os.lseek(fd,0,os.SEEK_SET)
        files={};directories=set();total=0;prefix=name+'-'+version+'/'
        with os.fdopen(os.dup(fd),'rb') as stream,tarfile.open(fileobj=stream,mode='r:gz') as packed:
            for member in packed:
                require(time.monotonic()<DEADLINE,'bounded registry observation deadline exhausted')
                if member.isdir() and member.name.rstrip('/')==name+'-'+version:
                    require('' not in directories,'duplicate archive root directory')
                    directories.add('');continue
                require(member.name.startswith(prefix) and not member.name.startswith('/'),'unexpected archive root')
                relative=member.name[len(prefix):]
                path=PurePosixPath(relative)
                require(relative and '..' not in path.parts and str(path)==relative.rstrip('/'),'noncanonical archive member')
                require(len(files)+len(directories)<4096,'archive member count exceeds bound')
                if member.isdir():
                    require(relative not in directories,'duplicate archive directory')
                    directories.add(relative);continue
                require(member.isfile() and relative not in files,'archive alias, special file or duplicate rejected')
                require(0<=member.size<=16*1024*1024 and total+member.size<=64*1024*1024,'archive expansion exceeds bound')
                reader=packed.extractfile(member);require(reader is not None,'archive regular member unreadable')
                member_hash=hashlib.sha256();member_size=0
                while True:
                    chunk=reader.read(65536)
                    if not chunk:break
                    member_size+=len(chunk);require(member_size<=member.size,'archive member exceeded declared size');member_hash.update(chunk)
                require(member_size==member.size,'archive member truncated')
                total+=member_size
                require(relative in source_before and source_before[relative]['bytes']==member_size and
                        source_before[relative]['sha256']==member_hash.hexdigest(),'extracted source differs from locked archive: '+str(directory/relative))
                files[relative]={'bytes':member_size,'sha256':member_hash.hexdigest(),'extracted':source_before[relative]}
        require(files,'empty source archive')
        extra={name:row for name,row in source_before.items() if name not in files}
        require(regular_tree(directory,4096,64*1024*1024)==source_before,'extracted source changed during archive comparison')
        require(identity(before)==identity(os.fstat(fd))==identity(archive.lstat()),'archive changed during comparison')
        return {'archive':archive_pin,'archive_matches_lock':True,'archive_files':len(files),'archive_bytes':total,
                'every_archive_file_matches_held_extracted_source':True,'extra_extracted_files':extra,
                'extra_files_are_only_cargo_marker':set(extra)<=set(['.cargo-ok']),
                'source_inventory':write_new(ROOT/(name+'-'+version+'-source.json'),{'archive_files':files,'extras':extra}),
                'source_unchanged_after':True}
    finally:os.close(fd)

def execute():
    global DEADLINE
    require(os.getuid()==1000 and os.geteuid()==1000,'ordinary operator UID1000 required')
    real_directory(ROOT.parent);os.umask(0o077);ROOT.mkdir(mode=0o700);DEADLINE=time.monotonic()+80
    allowed=sorted(os.sched_getaffinity(0));require(len(allowed)>=3,'cannot leave two logical CPUs free');os.sched_setaffinity(0,[allowed[-1]])
    result={'schema':1,'state':'RUNNING','started_utc':utc(),'scope':'fixed selected 45 existing registry packages; no Cargo execution or source writes',
            'Main_actions':0,'builds_started':0,'network_fetches':0,'packages':[],'selected_cpus':[allowed[-1]],'collection_complete':False}
    def interrupted(number,frame):raise RuntimeError('registry read interrupted by signal '+str(number))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    resource_fd=-1;resource_before=None;authorities={}
    try:
        resource_fd,resource_before=begin_resources();result['owned_resources_before']=resource_before
        lock_raw,lock_pin=held(LOCK,65536);tree_raw,tree_pin=held(TREE,4096)
        require(sha(lock_raw)==LOCK_SHA and sha(tree_raw)==TREE_SHA,'fixed dependency authority changed')
        authorities={str(LOCK):lock_pin,str(TREE):tree_pin};result['authority']=authorities
        packages={}
        for line in tree_raw.decode().splitlines():
            match=re.fullmatch(r'([A-Za-z0-9_-]+) v([0-9][A-Za-z0-9.+-]*)(?: \(proc-macro\))?(?: \((/[^()\n]+)\))?(?: \(\*\))?',line)
            require(match is not None,'unrecognized actual selected tree')
            name,version,path=match.groups()
            if path is None:packages[(name,version)]=None
        require(len(packages)==45,'fixed selected registry count differs')
        locked=tomllib.loads(lock_raw.decode())['package']
        real_directory(SOURCE_ROOT);real_directory(CACHE_ROOT)
        roots=sorted(SOURCE_ROOT.iterdir())
        require(0<len(roots)<=16 and all(stat.S_ISDIR(p.lstat().st_mode) for p in roots),'registry source root bound/aliases')
        result['registry_roots']=[{'path':str(p),'identity':identity(p.lstat())} for p in roots]
        for name,version in sorted(packages):
            require(time.monotonic()<DEADLINE,'bounded registry observation deadline exhausted')
            row={'name':name,'version':version};result['packages'].append(row)
            try:
                candidates=[p/(name+'-'+version) for p in roots if os.path.lexists(p/(name+'-'+version))]
                require(len(candidates)==1,'selected source cache directory absent or ambiguous')
                directory=candidates[0];real_directory(directory);row['source_directory']=str(directory)
                children=list(directory.iterdir());require(len(children)<=128,'selected package top-level listing exceeds bound')
                row['top_level']=[{'name':p.name,'mode':p.lstat().st_mode,'bytes':p.lstat().st_size} for p in sorted(children)]
                row['cargo_checksum_manifest']=observe_file(directory/'.cargo-checksum.json',4*1024*1024)
                row['cargo_ok']=observe_file(directory/'.cargo-ok',4096,True)
                row['cargo_manifest']=observe_file(directory/'Cargo.toml',1024*1024)
                matches=[p for p in locked if p['name']==name and p['version']==version and p.get('source')=='registry+https://github.com/rust-lang/crates.io-index']
                require(len(matches)==1,'selected package missing or ambiguous in exact lock')
                archive=CACHE_ROOT/directory.parent.name/(name+'-'+version+'.crate')
                row['expected_archive_path']=str(archive);row['expected_lock_checksum']=matches[0]['checksum']
                real_directory(archive.parent)
                row['comparison']=archive_source_comparison(archive,directory,name,version,matches[0]['checksum'])
            except Exception as error:row['error']=error_detail(error)
        result['collection_complete']=True
        result['all_45_archive_and_source_matches']=len(result['packages'])==45 and all('comparison' in r and
            r['comparison']['archive_matches_lock'] and r['comparison']['every_archive_file_matches_held_extracted_source'] and
            r['comparison']['extra_files_are_only_cargo_marker'] for r in result['packages'])
        result['state']='PASS' if result['all_45_archive_and_source_matches'] else 'FAIL'
    except Exception as error:result['state']='FAIL';result['error']=error_detail(error)
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
        try:
            result['authorities_unchanged_after']=bool(authorities) and all(hash_held(Path(p))==row for p,row in authorities.items())
            require(result['authorities_unchanged_after'],'dependency authorities changed')
        except Exception as error:result['after_error']=error_detail(error);result['state']='FAIL'
        try:
            require(resource_fd>=0 and resource_before is not None,'missing owned cgroup before observation')
            result['owned_resource_gate']=finish_resources(resource_fd,resource_before,result)
        except Exception as error:result['resource_error']=error_detail(error);result['state']='FAIL'
        finally:
            if resource_fd>=0:os.close(resource_fd)
    result['finished_utc']=utc();pin=write_new(ROOT/'result.json',result)
    print(json.dumps({'state':result['state'],'result':pin}),flush=True);return 0 if result['state']=='PASS' else 1

if __name__=='__main__':
    if sys.argv[1:]!=['--execute-once']:
        print(json.dumps({'mode':'PLAN','packages':45,'source_writes':0,'Cargo_execution':False,'Main_actions':0}))
    else:raise SystemExit(execute())
