"""Original private staged-APK inode/FD cleanup, with explicit UNKNOWN retention."""
import os,stat,hashlib,re

def require(value,reason):
    if not value:raise RuntimeError(reason)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def error_record(phase,error):return {"phase":phase,"type":type(error).__name__,"message":str(error)}

class OwnedApk:
    """Only a fresh own directory/file below the held Main root; no recursion."""

    def __init__(self, target, artifact, guest_dir_name):
        require(type(guest_dir_name) is str and re.fullmatch('pocket4-final-ihg-qa-[0-9a-f]{32}', guest_dir_name), 'EXACT_NEW_STAGING_NAME_REQUIRED')
        require(type(artifact['bytes']) is int and 0 < artifact['bytes'] <= 2097152 and re.fullmatch('[0-9a-f]{64}', artifact['sha256']), 'ACTUAL_BOUNDED_APK_REFERENCE_REQUIRED')
        self.artifact, self.guest_dir_name = (artifact, guest_dir_name)
        self.guest_apk = '/data/local/tmp/' + guest_dir_name + '/owned-ihg-qa.apk'
        self.target = target
        self.parent = self.directory = self.file = -1
        self.directory_created = False
        self.file_created = False
        self.identity = self.directory_identity = None

    @staticmethod
    def identity_of(fd):
        s = os.fstat(fd)
        return {'device': s.st_dev, 'inode': s.st_ino, 'mode': s.st_mode, 'uid': s.st_uid, 'gid': s.st_gid, 'nlink': s.st_nlink, 'bytes': s.st_size}

    def stage(self, data):
        require(len(data) == self.artifact['bytes'] and digest(data) == self.artifact['sha256'], 'ACTUAL_APK_BYTES_REQUIRED')
        self.parent = self.target.open_root('/data/local/tmp', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        os.mkdir(self.guest_dir_name, 457, dir_fd=self.parent)
        self.directory_created = True
        self.directory = os.open(self.guest_dir_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.parent)
        self.directory_identity = self.identity_of(self.directory)
        require(self.directory_identity['uid'] == 0, 'OWNED_DIRECTORY_UID_CHANGED')
        os.fchmod(self.directory, 457)
        self.directory_identity = self.identity_of(self.directory)
        self.file = os.open('owned-ihg-qa.apk', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 384, dir_fd=self.directory)
        self.file_created = True
        count = 0
        while count < len(data):
            wrote = os.write(self.file, data[count:])
            require(wrote > 0, 'OWNED_APK_WRITE_STALLED')
            count += wrote
        os.fsync(self.file)
        os.fchmod(self.file, 292)
        self.identity = self.identity_of(self.file)
        require(self.identity['uid'] == 0 and self.identity['nlink'] == 1 and stat.S_ISREG(self.identity['mode']) and (self.identity['bytes'] == self.artifact['bytes']), 'OWNED_STAGED_APK_SHAPE_CHANGED')
        os.fsync(self.directory)
        os.fsync(self.parent)
        raw, meta = self.target.read_file(self.guest_apk, self.artifact['bytes'], single_link=True)
        require(digest(raw) == self.artifact['sha256'] and (meta['device'], meta['inode'], meta['bytes']) == (self.identity['device'], self.identity['inode'], self.artifact['bytes']), 'STAGED_PATH_NOT_OWNED_APK')
        return {'path': self.guest_apk, 'sha256': self.artifact['sha256'], 'file': self.identity, 'directory': self.directory_identity}

    def close(self, retire_files=True):
        errors = []
        try:
            if self.file_created and retire_files:
                require(self.directory >= 0 and self.file >= 0, 'OWNED_FILE_FDS_REQUIRED')
                expected = os.fstat(self.file)
                current = os.stat('owned-ihg-qa.apk', dir_fd=self.directory, follow_symlinks=False)
                require(stat.S_ISREG(current.st_mode) and current.st_nlink == 1 and ((current.st_dev, current.st_ino) == (expected.st_dev, expected.st_ino)), 'OWNED_APK_CLEANUP_IDENTITY_CHANGED')
                os.unlink('owned-ihg-qa.apk', dir_fd=self.directory)
                os.fsync(self.directory)
        except BaseException as error:
            errors.append(error_record('owned_staged_file_retire', error))
        try:
            if self.directory_created and retire_files:
                require(self.parent >= 0 and self.directory >= 0, 'OWNED_DIRECTORY_FDS_REQUIRED')
                expected = os.fstat(self.directory)
                current = os.stat(self.guest_dir_name, dir_fd=self.parent, follow_symlinks=False)
                require(stat.S_ISDIR(current.st_mode) and (current.st_dev, current.st_ino) == (expected.st_dev, expected.st_ino), 'OWNED_DIRECTORY_CLEANUP_IDENTITY_CHANGED')
                require(os.listdir(self.directory) == [], 'OWNED_DIRECTORY_NOT_EMPTY')
                os.rmdir(self.guest_dir_name, dir_fd=self.parent)
                os.fsync(self.parent)
        except BaseException as error:
            errors.append(error_record('owned_staged_directory_retire', error))
        for name in ('file', 'directory', 'parent'):
            fd = getattr(self, name)
            setattr(self, name, -1)
            if fd >= 0:
                try:
                    os.close(fd)
                except BaseException as error:
                    errors.append(error_record('owned_fd_close_' + name, error))
        if errors:
            error = RuntimeError('OWNED_STAGING_RETIREMENT_FAILED')
            error.details = errors
            raise error
        return {'staged_apk_created': self.file_created, 'staged_directory_created': self.directory_created, 'staged_apk_removed': self.file_created and retire_files, 'staged_directory_removed': self.directory_created and retire_files, 'authority_fds_closed': True, 'recursive_cleanup': False, 'staging_retained_for_UNKNOWN': not retire_files}
