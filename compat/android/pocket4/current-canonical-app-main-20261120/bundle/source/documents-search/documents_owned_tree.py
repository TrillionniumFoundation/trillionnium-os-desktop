"""Independent extracted core; no Main/session/import-time execution.

Explicit FeaturesNames only supplies names/payloads, never runtime authority.
Caller must supply separately qualified fresh session, helpers and typed policy.
"""
import hashlib, os, signal, stat

def need(ok, why):
    if not ok:
        raise RuntimeError(why)

def birth(st):
    return {k: getattr(st, k) for k in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode')}

def close_handles(owner, names):
    """Close every owned local FD before a pending phase alarm is delivered."""
    previous=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGALRM})
    errors=[]
    try:
        for name in names:
            fd=getattr(owner,name)
            if fd is not None:
                setattr(owner,name,None)
                try:os.close(fd)
                except BaseException as error:errors.append(error)
    finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)
    if errors:raise errors[0]

class DocumentsOwnedTree:

    def __init__(self, session, record, *, scope):
        scope.require_kind('features10')
        self.scope = scope
        self.s, self.record = (session, record)
        self.parent = self.fd = None
        self.created = self.removed = False
        self.ledger = {}
        self.expected = set()

    def setup(self):
        self.s.guard()
        self.parent = self.s.target.open_root('/storage/emulated/0', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.stat(self.scope.FOLDER, dir_fd=self.parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise RuntimeError('EXCLUSIVE_GENERATED_ROOT_ALREADY_EXISTS')
        self.record('owned-root-create-intent', {'name': self.scope.FOLDER, 'file_contents_written': 0, 'fixture_setup_only': True})
        os.mkdir(self.scope.FOLDER, 448, dir_fd=self.parent)
        self.created = True
        self.fd = os.open(self.scope.FOLDER, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.parent)
        self.birth = birth(os.fstat(self.fd))
        need(self.fresh_names(self.fd) == [], 'NEW_ROOT_NOT_EMPTY')
        self.record('owned-root-created', {'birth': self.birth, 'entries': [], 'App_creation_credit': False})
        self.s.guard()

    def guard(self):
        need(self.created and (not self.removed) and (self.fd is not None), 'NO_HELD_OWNED_ROOT')
        self.s.guard()
        need(birth(os.fstat(self.fd)) == self.birth and birth(os.stat(self.scope.FOLDER, dir_fd=self.parent, follow_symlinks=False)) == self.birth, 'OWNED_ROOT_REPLACED')

    @staticmethod
    def fresh_names(fd):
        before = birth(os.fstat(fd))
        fresh = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
        try:
            need(birth(os.fstat(fresh)) == before, 'FRESH_DIRECTORY_CHANGED')
            names = os.listdir(fresh)
        finally:
            os.close(fresh)
        need(birth(os.fstat(fd)) == before, 'HELD_DIRECTORY_CHANGED')
        return sorted(names)

    def file(self, parent, name, relative):
        need(relative in self.scope.ALLOWED_FILES and name in self.scope.PAYLOAD, 'ONLY_FIXED_GENERATED_FILE_ALLOWED')
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        try:
            before = os.fstat(fd)
            size, sha = self.scope.PAYLOAD[name]
            need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and (before.st_size == size), 'FIXTURE_FILE_TYPE_SIZE_OR_LINKS')
            raw = os.read(fd, 1025)
            after = os.fstat(fd)
            need(len(raw) == size and hashlib.sha256(raw).hexdigest() == sha and (birth(before) == birth(after)) and (before.st_mtime_ns == after.st_mtime_ns) and (before.st_ctime_ns == after.st_ctime_ns), 'FIXTURE_FILE_CHANGED_OR_HASH_MISMATCH')
            return {'kind': 'file', 'birth': birth(before), 'bytes': size, 'sha256': sha, 'mtime_ns': str(before.st_mtime_ns), 'ctime_ns': str(before.st_ctime_ns)}
        finally:
            os.close(fd)

    def scan(self):
        self.guard()
        names = self.fresh_names(self.fd)
        need(set(names) <= self.scope.ALLOWED_DIRS | set(self.scope.PAYLOAD), 'UNEXPECTED_ROOT_ENTRY_PRESERVED')
        observed = {}
        for name in names:
            if name in self.scope.PAYLOAD:
                observed[name] = self.file(self.fd, name, name)
                continue
            sub = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.fd)
            try:
                ident = birth(os.fstat(sub))
                need(stat.S_ISDIR(ident['st_mode']), 'OWNED_SUBDIRECTORY_TYPE')
                children = self.fresh_names(sub)
                need(set(children) <= set(self.scope.PAYLOAD), 'UNEXPECTED_CHILD_ENTRY_PRESERVED')
                observed[name] = {'kind': 'directory', 'birth': ident}
                for child in children:
                    observed[name + '/' + child] = self.file(sub, child, name + '/' + child)
                need(self.fresh_names(sub) == children, 'CHILD_ENTRIES_CHANGED_DURING_READ')
                need(birth(os.stat(name, dir_fd=self.fd, follow_symlinks=False)) == ident, 'OWNED_SUBDIRECTORY_REPLACED')
            finally:
                os.close(sub)
        need(self.fresh_names(self.fd) == names, 'ROOT_ENTRIES_CHANGED_DURING_READ')
        self.guard()
        return observed

    def expect(self, expected, label, admit_changes=False):
        expected = set(expected)
        need(expected <= self.scope.ALLOWED_DIRS | self.scope.ALLOWED_FILES, 'EXPECTED_LAYOUT_OUTSIDE_SCOPE')
        need(all(('/' not in n or n.split('/')[0] in expected for n in expected)), 'EXPECTED_LAYOUT_MISSING_PARENT')
        actual = self.scan()
        need(set(actual) == expected, 'EXACT_GENERATED_LAYOUT_REQUIRED:' + label)
        for name in set(actual) & set(self.ledger):
            need(actual[name] == self.ledger[name], 'UNCHANGED_OWNED_ENTRY_IDENTITY_CHANGED:' + name)
        need(admit_changes or expected == self.expected, 'LAYOUT_CHANGE_REQUIRES_RECORDED_APP_OPERATION')
        self.ledger = actual
        self.expected = expected
        self.record(label, {'entries': actual, 'root_birth': self.birth, 'content_bytes_read_from_own_fixture_only': True})
        return actual

    def remove_known(self, no_pending_effects):
        need(no_pending_effects is True, 'PENDING_WORK_PRESERVE_ENTIRE_FIXTURE')
        if not self.created:
            return {'created': False, 'removed': False}
        self.expect(self.expected, 'cleanup-exact-layout', False)
        for relative in sorted((n for n, v in self.ledger.items() if v['kind'] == 'file'), key=lambda n: (n.count('/'), n), reverse=True):
            parts = relative.split('/')
            parent = self.fd
            sub = None
            try:
                if len(parts) == 2:
                    sub = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.fd)
                    parent = sub
                    need(birth(os.fstat(sub)) == self.ledger[parts[0]]['birth'], 'CLEANUP_SUBDIRECTORY_CHANGED')
                proof = self.file(parent, parts[-1], relative)
                need(proof == self.ledger[relative], 'FILE_CHANGED_BEFORE_EXACT_UNLINK')
                self.record('cleanup-exact-file-intent', {'relative': relative, 'proof': proof, 'business_delete_credit': False})
                os.unlink(parts[-1], dir_fd=parent)
                try:
                    os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise RuntimeError('EXACT_FILE_UNLINK_NOT_ABSENT')
            finally:
                if sub is not None:
                    os.close(sub)
        removed_files = sum((v['kind'] == 'file' for v in self.ledger.values()))
        for name in sorted((n for n, v in self.ledger.items() if v['kind'] == 'directory')):
            sub = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.fd)
            try:
                need(birth(os.fstat(sub)) == self.ledger[name]['birth'] and self.fresh_names(sub) == [], 'EMPTY_OWNED_SUBDIRECTORY_REQUIRED')
            finally:
                os.close(sub)
            need(birth(os.stat(name, dir_fd=self.fd, follow_symlinks=False)) == self.ledger[name]['birth'], 'SUBDIRECTORY_CHANGED_BEFORE_REMOVE')
            os.rmdir(name, dir_fd=self.fd)
        self.guard()
        need(self.fresh_names(self.fd) == [], 'OWNED_ROOT_NOT_EMPTY_AT_FINAL_REMOVE')
        os.rmdir(self.scope.FOLDER, dir_fd=self.parent)
        try:
            os.stat(self.scope.FOLDER, dir_fd=self.parent, follow_symlinks=False)
        except FileNotFoundError:
            self.removed = True
        need(self.removed, 'OWNED_ROOT_REMOVAL_NOT_VERIFIED')
        return {'created': True, 'removed': True, 'fallback_files_unlinked': removed_files, 'provider_or_UI_delete_credit': False, 'file_contents_written_by_host': False}

    def close(self):
        close_handles(self, ('fd', 'parent'))
