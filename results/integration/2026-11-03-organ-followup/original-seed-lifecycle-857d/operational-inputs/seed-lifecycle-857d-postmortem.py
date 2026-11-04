import base64, hashlib, json, os, pathlib, stat

root = pathlib.Path('/var/lib/trill/s1103as1')
assert os.getuid()==0 and os.geteuid()==0
result = {'scope':'read-only new seed-test prefix after the exact test returned',
          'prefix':str(root),'observer_mount_namespace':os.readlink('/proc/self/ns/mnt'),
          'authority_state_exists':os.path.lexists(root/'a/state'), 'entries':[], 'files':[]}
retained = 0
admin_names = {'seed.stdout','seed.stderr','original-inputs.json','original-thread-seed.json','seed-lifecycle-observation.json'}
if root.exists():
    assert root.resolve()==root
    for directory, directories, files in os.walk(root,followlinks=False):
        directories[:] = sorted(d for d in directories if not (pathlib.Path(directory)/d).is_symlink())
        for name in sorted(files):
            path = pathlib.Path(directory)/name
            m = path.lstat()
            assert len(result['entries'])<2048
            relative = path.relative_to(root).as_posix()
            item = {'path':relative,'size':m.st_size,'mode':stat.S_IMODE(m.st_mode),'uid':m.st_uid,'gid':m.st_gid,
                    'device':m.st_dev,'inode':m.st_ino,'regular':stat.S_ISREG(m.st_mode),'symlink':stat.S_ISLNK(m.st_mode)}
            result['entries'].append(item)
            wanted = (path.parent==root/'admin' and name in admin_names) or path.suffix=='.log'
            if not wanted or not item['regular'] or m.st_nlink!=1 or m.st_size>262144 or retained+m.st_size>1048576:
                continue
            fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as stream:
                before=os.fstat(stream.fileno());data=stream.read(262145);after=os.fstat(stream.fileno())
            assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
            assert len(data)==m.st_size
            retained += len(data)
            result['files'].append({'path':relative,'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                                    'base64':base64.b64encode(data).decode()})
result['retained_bytes'] = retained
print(json.dumps(result))
