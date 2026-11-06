import os, sys, json, stat, pathlib, hashlib, datetime
P = pathlib.Path
ROOT = P('/home/alex/work/pocket4-builder470-explicit-current-qualification-01-20261106')
SOURCE_BYTES = 72093
SOURCE_SHA = 'f8a4fed5618f05be2db375ddc63d3b2bff2e884d6ed0d9468e46bb138e86f03e'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def identity(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns]


def write_new(path, raw, mode):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                info.st_uid == info.st_gid == 1000, 'new stage file owner/type differs')
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:])
            require(count > 0, 'short stage write')
            offset += count
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        actual = os.pread(fd, len(raw) + 1, 0)
        after = os.fstat(fd)
        require(actual == raw and identity(before) == identity(after) == identity(path.lstat()) and
                before.st_nlink == 1 and before.st_uid == before.st_gid == 1000 and
                stat.S_IMODE(before.st_mode) == mode, 'stage readback differs')
        return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'identity': identity(before)}
    finally:
        os.close(fd)


def main(files):
    require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000,
            'original unprivileged operator required')
    os.umask(0o077)
    require(type(files) is dict and set(files) == {'qualify_current470.py'}, 'closed source packet differs')
    text = files['qualify_current470.py']
    require(type(text) is str, 'qualifier source must be UTF-8 text')
    raw = text.encode('utf-8', 'strict')
    require(len(raw) == SOURCE_BYTES and hashlib.sha256(raw).hexdigest() == SOURCE_SHA,
            'exact qualification source bytes differ')
    for path in [ROOT.parent, *ROOT.parent.parents]:
        require(stat.S_ISDIR(path.lstat().st_mode), 'stage parent is not a real directory')
    parent = ROOT.parent.lstat()
    require(parent.st_uid == parent.st_gid == 1000 and not parent.st_mode & 0o002,
            'owned work directory differs')
    require(not ROOT.exists() and not ROOT.is_symlink(),
            'new stage root already exists; reconcile the original job, do not restage')
    ROOT.mkdir(mode=0o700)
    source = write_new(ROOT / 'qualify_current470.py', raw, 0o400)
    receipt = {'schema': 'pocket4-current470-qualification-stage-v1', 'state': 'SOURCE_STAGED_ONLY',
        'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'qualifier_source': source,
        'root': str(ROOT), 'owner_uid': 1000, 'compiler_invoked': False,
        'Main_actions': 0, 'Android_actions': 0, 'runtime_authorization_enabled': False,
        'old_paths_written': False, 'existing_builder_source_changed': False,
        'production_ready': False, 'cleanup_eligible': False, 'automatic_retry': False}
    receipt_pin = write_new(ROOT / 'stage-receipt.json',
                            (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode(), 0o600)
    require(set(os.listdir(ROOT)) == {'qualify_current470.py', 'stage-receipt.json'},
            'unexpected staged files')
    print(json.dumps({'state': 'SOURCE_STAGED_ONLY', 'source': source, 'receipt': receipt_pin,
        'compiler_invoked': False, 'Main_actions': 0, 'production_ready': False}), flush=True)
