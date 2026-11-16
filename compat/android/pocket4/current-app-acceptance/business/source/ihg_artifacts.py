"""Pure extraction of original IHG artifact guard and read-only parsers.
No old Flow, Main, source contract or runtime entry is constructed.
"""
import hashlib
import os
from pathlib import Path
import re
import stat
import time
PACKAGE = 'com.ihg.apps.android'
UID = 10137
USER = 0
VERSION = 50023496
LIST = ['/system/bin/cmd','package','list','packages','-U','--show-versioncode','--user','0',PACKAGE]
PATHS = ['/system/bin/cmd','package','path','--user','0',PACKAGE]
RESOLVE = ['/system/bin/cmd','package','resolve-activity','--brief','--user','0','-a','android.intent.action.MAIN','-c','android.intent.category.LAUNCHER',PACKAGE]
FILE_LIMIT = 256*1024*1024
TOTAL_LIMIT = 512*1024*1024
HASH_SECONDS = 45
FILE_COUNT = 16

def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)

def identity(fd):
    s = os.fstat(fd)
    return {'device':s.st_dev,'inode':s.st_ino,'mode':s.st_mode,'uid':s.st_uid,'gid':s.st_gid,
            'nlink':s.st_nlink,'bytes':s.st_size,'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns}

class ArtifactSet:
    """The exact one installed commercial APK, read-only and held to exit."""
    def __init__(self, context, expected, reader):
        require(expected['target'] == {'package':PACKAGE,'uid':UID,'user':0,'version_code':VERSION},
                'ACTUAL_AMAZON_METADATA_REFERENCE_REQUIRED')
        self.context,self.expected,self.reader = context,expected,reader
        self.opened = []
        self.records = []
        self.closed = False

    def _metadata(self, raw):
        value = self.reader.metadata(raw)
        require(value == self.expected['target'],'ACTUAL_AMAZON_UID_OR_VERSION_CHANGED')
        return value

    def _paths(self, raw):
        values = self.reader.apk_paths(raw)
        require(values == sorted(row['path'] for row in self.expected['artifacts']) and len(values) == 1,
                'ACTUAL_ONE_IHG_APK_PATH_CHANGED')
        return values

    def _hash(self, fd, expected, deadline):
        first = identity(fd)
        require(first == expected['held_file'] and stat.S_ISREG(first['mode']) and first['nlink'] == 1 and
                first['uid'] == first['gid'] == 1000 and not first['mode']&0o022 and
                0 < first['bytes'] <= FILE_LIMIT,'ACTUAL_AMAZON_APK_IDENTITY_CHANGED')
        os.lseek(fd,0,os.SEEK_SET)
        digest = hashlib.sha256();count = 0
        while True:
            require(time.monotonic() < deadline,'AMAZON_APK_STREAM_HASH_DEADLINE')
            block = os.read(fd,min(65536,first['bytes']+1-count))
            if not block:
                break
            count += len(block)
            require(count <= first['bytes'],'AMAZON_APK_GREW')
            digest.update(block)
        require(count == first['bytes'] and identity(fd) == first and digest.hexdigest() == expected['sha256'],
                'ACTUAL_AMAZON_APK_CONTENT_CHANGED')
        return {'path':expected['path'],'sha256':digest.hexdigest(),'held_file':first}

    def before(self):
        self._metadata(self.context.android(LIST,15))
        self._paths(self.context.android(PATHS,15))
        require(sum(row['held_file']['bytes'] for row in self.expected['artifacts']) <= TOTAL_LIMIT,
                'ONE_APK_TOTAL_BOUND')
        deadline = min(self.context.deadline,time.monotonic()+HASH_SECONDS)
        for row in self.expected['artifacts']:
            fd = self.context.target.open_root(row['path'],os.O_RDONLY|os.O_NOFOLLOW)
            self.opened.append(fd)
            self.records.append(self._hash(fd,row,deadline))
        require(len(self.opened) == len(self.records) == 1,'EXACT_ONE_HELD_APK_REQUIRED')
        self.context.artifacts = self
        return {'metadata':self.expected['target'],'artifacts':self.records,
                'fresh_streaming_hashes':True,'signer_independently_verified':False}

    def verify_held(self):
        require(not self.closed and len(self.opened) == len(self.records) == 1,'OPEN_ONE_APK_SET_REQUIRED')
        for fd,row in zip(self.opened,self.records):
            require(identity(fd) == row['held_file'],'HELD_AMAZON_APK_CHANGED')

    def after(self):
        self._paths(self.context.android(PATHS,15))
        self._metadata(self.context.android(LIST,15))
        return self.revalidate_files()

    def revalidate_files(self):
        self.verify_held()
        deadline = min(self.context.deadline,time.monotonic()+HASH_SECONDS)
        after = []
        for fd,row in zip(self.opened,self.expected['artifacts']):
            after.append(self._hash(fd,row,deadline))
            named = self.context.target.open_root(row['path'],os.O_RDONLY|os.O_NOFOLLOW)
            try:
                require(identity(named) == row['held_file'],'AMAZON_APK_NAMED_PATH_CHANGED')
            finally:
                os.close(named)
        require(after == self.records,'AMAZON_APK_SET_CHANGED')
        return {'metadata':self.expected['target'],'artifacts':after,
                'fresh_streaming_hashes':True,'signer_independently_verified':False}

    def close(self):
        self.closed = True
        failures = []
        opened_count = len(self.opened)
        for fd in reversed(self.opened):
            try:
                os.close(fd)
            except BaseException as error:
                failures.append(repr(error))
        self.opened = []
        self.context.artifacts = None
        require(not failures,'AMAZON_ARTIFACT_FD_CLOSE_FAILED: '+repr(failures))
        return {'held_APK_FDs_closed':opened_count,'commercial_files_changed':False}

def need(value, message):
    if not value:
        raise RuntimeError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def metadata(raw):
    match=re.fullmatch(re.escape('package:'+PACKAGE)+r' versionCode:([0-9]+) uid:([0-9]+)\n',
                       raw.decode('utf-8','strict'))
    need(match is not None,'ONE_EXACT_TICKET12306_USER0_METADATA_ROW_REQUIRED')
    version,uid=map(int,match.groups())
    need(0<version<2**63 and 10000<=uid<100000,'TICKET12306_METADATA_RANGE')
    return {'package':PACKAGE,'user':USER,'uid':uid,'version_code':version}

def apk_paths(raw):
    text=raw.decode('utf-8','strict')
    need(text.endswith('\n') and len(raw)<=16384,'TICKET12306_PATH_OUTPUT_BOUND')
    lines=text.splitlines()
    need(1<=len(lines)<=FILE_COUNT and all(x.startswith('package:') for x in lines),
         'TICKET12306_APK_PATH_ROWS_REQUIRED')
    paths=[x[len('package:'):] for x in lines]
    need(len(set(paths))==len(paths),'DUPLICATE_APK_PATH')
    parents=set()
    for path in paths:
        need(isinstance(path,str) and '\x00' not in path and len(path.encode())<=4096,
             'TICKET12306_PATH_SHAPE')
        parts=Path(path).parts
        need(len(parts)==6 and parts[:3]==('/','data','app') and
             re.fullmatch(r'~~[A-Za-z0-9_=-]+',parts[3]) and
             re.fullmatch(re.escape(PACKAGE)+r'-[A-Za-z0-9_=-]+',parts[4]) and
             (parts[5]=='base.apk' or re.fullmatch(r'split_[A-Za-z0-9_.-]+\.apk',parts[5])),
             'ONLY_EXACT_TICKET12306_INSTALL_DIRECTORY_APKS_MAY_BE_READ')
        parents.add(str(Path(path).parent))
    need(len(parents)==1 and sum(Path(x).name=='base.apk' for x in paths)==1,
         'ONE_TICKET12306_BASE_AND_ONE_INSTALL_DIRECTORY_REQUIRED')
    return sorted(paths)

def component(raw):
    need(isinstance(raw,bytes) and 0<len(raw)<=4096,'RESOLVE_OUTPUT_BOUND')
    text=raw.decode('ascii','strict')
    need(text.endswith('\n') and '\x00' not in text and
         all(c=='\n' or 32<=ord(c)<127 for c in text),'RESOLVE_OUTPUT_TEXT_SHAPE')
    lines=text.splitlines()
    need(1<=len(lines)<=16,'RESOLVE_OUTPUT_LINE_BOUND')
    candidates=[line.strip() for line in lines if
        re.fullmatch(r'[A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+',line.strip())]
    need(len(candidates)==1,'ONE_CURRENT_LAUNCHER_COMPONENT_REQUIRED')
    value=candidates[0]
    need(re.fullmatch(re.escape(PACKAGE)+r'/(?:\.[A-Za-z_][A-Za-z0-9_.$]*|[A-Za-z_][A-Za-z0-9_.$]*)',value)
         is not None,'LAUNCHER_MUST_BELONG_TO_EXACT_TICKET12306_PACKAGE')
    return {'package':PACKAGE,'user':0,'component':value,
        'query_action':'android.intent.action.MAIN','query_category':'android.intent.category.LAUNCHER',
        'resolve_stdout_sha256':sha(raw),'fallback_used':False,
        'launch_performed':False,'later_launch_requires_new_current_binding':True}
