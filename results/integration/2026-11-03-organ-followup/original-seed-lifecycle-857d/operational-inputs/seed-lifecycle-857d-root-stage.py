import hashlib, json, os, pathlib, stat, sys

expected = json.loads(sys.argv[1])
assert os.getuid()==0 and os.geteuid()==0
os.umask(0o077)
prefix = pathlib.Path('/opt/trill-seed-signal-20261103-857d')
config_path = pathlib.Path('/root/trill-organ-owner-20261103/seed-857d-v1.json')
deployment = pathlib.Path('/var/lib/trill/s1103as1')

def physical(path):
    assert path.is_absolute() and path.resolve()==path
    for part in [path,*path.parents]:
        m = part.lstat()
        assert stat.S_ISDIR(m.st_mode) and m.st_uid==0 and m.st_mode & 0o022==0

physical(prefix.parent)
physical(config_path.parent)
assert not os.path.lexists(prefix) and not os.path.lexists(config_path) and not os.path.lexists(deployment)
original = pathlib.Path('/root/trill-organ-owner-20261103/initialize.json')
physical(original.parent)
fd = os.open(original,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
with os.fdopen(fd,'rb') as f:
    m = os.fstat(f.fileno())
    assert stat.S_ISREG(m.st_mode) and m.st_uid==0 and m.st_nlink==1 and stat.S_IMODE(m.st_mode)==0o600
    raw = f.read(65537)
assert hashlib.sha256(raw).hexdigest()=='6a373c9e6bc949598aaa9a42d5eba46020113fa93ae10a3466f05ce68cfd52ec'
inputs = json.loads(raw)
prefix.mkdir(mode=0o755)
copied = {}
for key,name in [('appserver_binary','codex-app-server'),('seed_test_binary','hepta-desktop-root-seed-test')]:
    item = expected[key]
    source = pathlib.Path(item['path'])
    assert source.parent==pathlib.Path('/data/trill-organ-owner-20261103/appserver-signal-component-v1/bin')
    assert 0<item['size']<=2*1024**3 and len(item['sha256'])==64
    source_fd = os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
    destination = prefix/name
    h, length = hashlib.sha256(), 0
    with os.fdopen(source_fd,'rb') as src, destination.open('xb') as dst:
        before = os.fstat(src.fileno())
        assert stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size==item['size']
        assert src.read(4)==b'\x7fELF'
        src.seek(0)
        for block in iter(lambda:src.read(1024*1024),b''):
            length += len(block)
            assert length<=item['size']
            dst.write(block); h.update(block)
        after = os.fstat(src.fileno())
        assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
        assert length==item['size'] and h.hexdigest()==item['sha256']
        dst.flush(); os.fsync(dst.fileno()); os.fchmod(dst.fileno(),0o555)
    copied[key] = {'path':str(destination),'size':length,'sha256':h.hexdigest()}
inputs['prefix'] = str(deployment)
inputs['programs']['app_server'] = str(prefix/'codex-app-server')
data = (json.dumps(inputs,indent=2)+'\n').encode()
fd = os.open(config_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f: f.write(data);f.flush();os.fsync(f.fileno())
for path in (prefix,config_path.parent):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
print(json.dumps({'scope':'explicit original seed component only, mixed component sources',
    'config':str(config_path),'config_sha256':hashlib.sha256(data).hexdigest(),
    'prefix':str(deployment),'copied':copied,'production_qualified':False}))
