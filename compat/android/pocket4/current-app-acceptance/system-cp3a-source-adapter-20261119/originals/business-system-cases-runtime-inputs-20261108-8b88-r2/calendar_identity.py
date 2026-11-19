"""Independent new-Main component; no historical Session, Main or execute entry."""
from pathlib import Path
import argparse, hashlib, json, os, re, signal, stat, time, types
import xml.etree.ElementTree as ET

def need(value, reason):
    if not value:
        raise RuntimeError(reason)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def fp(info):
    return {k: getattr(info, k) for k in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode')}

def identity(session, package, expected_sha, expected_uid=None, expected_code=1):
    raw = session.android(['/system/bin/dumpsys', 'package', package]).decode()
    blocks = re.findall('^Packages:\\n(.*?)(?=^\\S|\\Z)', raw, re.M | re.S)
    need(len(blocks) == 1 and re.findall('^  Package \\[([^]]+)\\]', blocks[0], re.M) == [package], 'PACKAGE_SECTION_CHANGED')
    block = blocks[0]

    def one(pattern):
        values = re.findall(pattern, block, re.M)
        need(len(values) == 1, 'PACKAGE_FIELD_AMBIGUOUS:' + pattern)
        return values[0]
    uid = int(one('^    appId=(\\d+)$'))
    code = int(one('^    versionCode=(\\d+)\\b'))
    need((expected_uid is None or uid == expected_uid) and code == expected_code, 'PACKAGE_UID_OR_VERSION_CHANGED')
    state = one('^    User 0: (.*)$')
    need(all((re.search('\\b' + k + '=' + v + '\\b', state) for k, v in (('installed', 'true'), ('hidden', 'false'), ('suspended', 'false'), ('enabled', '[01]')))), 'PACKAGE_USER_STATE')
    paths = session.android(['/system/bin/pm', 'path', '--user', '0', package]).decode().splitlines()
    need(len(paths) == 1 and paths[0].startswith('package:/') and paths[0].endswith('.apk'), 'SINGLE_APK_PATH_REQUIRED')
    data, metadata = session.target.read_file(paths[0][8:], 16 * 1024 * 1024, single_link=True)
    need(sha(data) == expected_sha, 'INSTALLED_APK_HASH_CHANGED')
    directories = {}
    for label, path in [('ce', '/data/user/0/' + package), ('de', '/data/user_de/0/' + package)]:
        fd = session.target.open_root(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            directories[label] = fp(info)
        finally:
            os.close(fd)
        inode = int(re.search('\\b' + label + 'DataInode=(\\d+)\\b', state)[1])
        need(info.st_uid == info.st_gid == uid and info.st_ino == inode, 'PACKAGE_DATA_IDENTITY_CHANGED')
    session.guard()
    return {'package': package, 'uid': uid, 'version_code': code, 'apk_path': paths[0][8:], 'apk_sha256': sha(data), 'apk_bytes': len(data), 'directories': directories}
