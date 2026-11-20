"""Independent original package lifecycle. Explicit refs are data, not authority.

No CLI, original session loading, installer call, or IO occurs on import.
The future trusted plan must first validate actual build/Main/source evidence.
"""
from pathlib import Path
import hashlib, json, os, re, signal, stat
import xml.etree.ElementTree as ET
DOCS = "com.android.documentsui"

def need(ok, why):
    if not ok:
        raise RuntimeError(why)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def fp(info):
    return {k: getattr(info, k) for k in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode')}

def absent(session, package):
    listed = session.android(['/system/bin/pm', 'list', 'packages', '-u', '-U', package]).decode()
    dump = session.android(['/system/bin/dumpsys', 'package', package]).decode()
    need(not listed.strip() and dump.strip() == 'Unable to find package: ' + package, 'NEW_PACKAGE_NOT_ABSENT')

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

def close_stage_handles(owner, stage):
    previous=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGALRM})
    errors=[]
    try:
        for name in ('directory','parent'):
            fd=stage[name];stage[name]=None
            if fd is not None:
                try:os.close(fd)
                except BaseException as error:errors.append(error)
        owner.staged=None
    finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)
    if errors:raise errors[0]

class DocumentsPackageFixture:

    def __init__(self, session, tx, ui, result, *, scope, artifacts):
        scope.require_kind('features10')
        artifacts.validate_reference_shapes()
        self.scope, self.artifacts = (scope, artifacts)
        self.s, self.tx, self.ui, self.result = (session, tx, ui, result)
        self.staged = self.installed = None
        self.install_pending = self.uninstall_pending = False

    def data_absent(self):
        for prefix in ('/data/user/0/', '/data/user_de/0/'):
            try:
                fd = self.s.target.open_root(prefix + self.scope.PACKAGE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            except FileNotFoundError:
                continue
            else:
                os.close(fd)
                raise RuntimeError('PREEXISTING_HELPER_DATA_DIRECTORY_PRESERVED')

    def install(self):
        proof = json.loads(self.tx.read_regular(self.artifacts.PM_HELP, self.artifacts.PM_HELP_SHA, 16384))
        need(proof['state'] == 'ACTUAL_NO_REPLACE_FLAG_VERIFIED' and proof['no_replace_flag'] == '-R' and (proof['guard_before'] == proof['guard_after'] == self.s.guard()) and (proof['ui_actions'] == proof['package_mutations'] == 0) and ([line.strip() for line in proof['actual_flag_lines']] == ['-R: disallow replacement of existing application']), 'ACTUAL_CREATE_ONLY_FLAG_PROOF_CHANGED')
        self.ui.record('actual-pm-no-replace-proof', proof)
        absent(self.s, self.scope.PACKAGE)
        self.data_absent()
        build_raw = self.tx.read_regular(self.artifacts.BUILD, self.artifacts.BUILD_SHA, 1048576)
        need(sha(build_raw) == self.artifacts.BUILD_SHA, 'BUILD_RECEIPT_CHANGED')
        build = json.loads(build_raw)
        need(build['state'] == 'BUILT_SIGNED_VERIFIED_UNINSTALLED' and build['apk']['sha256'] == self.artifacts.APK_SHA and (build['signer_certificate_sha256'] == self.artifacts.CERT_SHA) and (build['permissions'] == []) and (build['launcher'] is False), 'APK_PROVENANCE_NOT_VERIFIED')
        data = self.tx.read_regular(self.artifacts.APK, self.artifacts.APK_SHA, 1048576)
        need(len(data) == self.artifacts.APK_BYTES, 'APK_SIZE_CHANGED')
        parent = self.s.target.open_root('/data/local/tmp', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        name = 'pocket4-owned-docfeatures-' + self.scope.RUN
        guest = '/data/local/tmp/' + name + '/owned-features.apk'
        directory = None
        created = False
        try:
            os.mkdir(name, 493, dir_fd=parent)
            created = True
            directory = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            os.fchmod(directory, 493)
            self.staged = {'parent': parent, 'directory': directory, 'name': name, 'birth': fp(os.fstat(directory)), 'guest': guest, 'file_identity': None}
        except BaseException as primary:
            if created:
                self.result['staging_setup_incomplete'] = {'path': '/data/local/tmp/' + name, 'reconciliation_required': True, 'directory_identity_not_yet_verified': True}
            try:
                close_stage_handles(self, {'directory': directory, 'parent': parent})
            except BaseException as secondary:
                primary.add_note('LOCAL_STAGE_FD_CLOSE:' + type(secondary).__name__)
            raise
        fd = os.open('owned-features.apk', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 420, dir_fd=directory)
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
            os.fchmod(out.fileno(), 420)
        self.staged['file_identity'] = fp(os.stat('owned-features.apk', dir_fd=directory, follow_symlinks=False))
        staged, _ = self.s.target.read_file(guest, 1048576, single_link=True)
        need(sha(staged) == self.artifacts.APK_SHA, 'STAGED_APK_CHANGED')
        absent(self.s, self.scope.PACKAGE)
        self.data_absent()
        self.s.guard()
        argv = ['/system/bin/pm', 'install', '-R', '-t', '--user', '0', guest]
        self.ui.record('create-only-install-intent', {'argv': argv, 'replace_flag': False, 'disallow_replacement_flag': '-R', 'pm_help_proof_sha256': self.artifacts.PM_HELP_SHA, 'apk_sha256': self.artifacts.APK_SHA, 'signer_sha256': self.artifacts.CERT_SHA, 'preinstall_absent_all_users': True, 'automatic_retry': False})
        self.install_pending = True
        raw = self.s.android(argv, 60).decode()
        need(raw.strip() == 'Success', 'INSTALL_RESPONSE_NOT_SUCCESS')
        self.installed = identity(self.s, self.scope.PACKAGE, self.artifacts.APK_SHA)
        need(10000 <= self.installed['uid'] < 20000, 'NEW_APPLICATION_UID_OUT_OF_RANGE')
        self.install_pending = False
        self.ui.record('new-package-installed', self.installed)
        self.result['installed_identity'] = self.installed

    def packages(self, label):
        values = {DOCS: identity(self.s, DOCS, 'f7db1705178644333d5c9d291afd1170e71fcddfd1f73021381e1224be824899', 10022, 37), 'com.android.externalstorage': identity(self.s, 'com.android.externalstorage', '00cf8db78a3f8846e34fd3e6b7f1c811a9393b7c2e6227c083e27e5cdb0fa515', 10024, 37)}
        self.ui.record(label, values)
        return values

    def pref_state(self):
        path = '/data/user/0/' + self.scope.PACKAGE + '/shared_prefs/owned-features-' + self.scope.RUN + '.xml'
        try:
            raw, _ = self.s.target.read_file(path, 16384, single_link=True)
        except FileNotFoundError:
            return None
        root = ET.fromstring(raw)
        need(root.tag == 'map', 'OWNED_PREFS_SCHEMA')
        result = {}
        for item in root:
            name = item.get('name')
            need(name and name not in result, 'DUPLICATE_OWNED_PREF_KEY')
            if item.tag == 'string':
                result[name] = item.text or ''
            elif item.tag in ('int', 'long'):
                result[name] = int(item.get('value'))
            else:
                raise RuntimeError('UNKNOWN_OWNED_PREF_TYPE')
        need(result.get('run') == self.scope.RUN, 'OWNED_PREF_RUN_CHANGED')
        self.ui.record('owned-client-phase-readonly', {'phase': result.get('phase'), 'pending': result.get('pending', ''), 'sha256': sha(raw), 'step_pending': result.get('step_pending', ''), 'content_writes': result.get('content_writes', 0)})
        return result

    def grants(self, label, expect_empty=False):
        raw = self.s.android(['/system/bin/dumpsys', 'activity', 'package', self.scope.PACKAGE, 'permissions']).decode()
        header = 'ACTIVITY MANAGER URI PERMISSIONS (dumpsys activity permissions)'
        lines = raw.splitlines()
        indices = [i for i, line in enumerate(lines) if line.strip() == header]
        need(len(indices) == 1, 'URI_GRANT_SECTION_NOT_UNIQUE')
        begin = indices[0]
        end = next((i for i in range(begin + 1, len(lines)) if lines[i].startswith('ACTIVITY MANAGER ')), len(lines))
        section = '\n'.join(lines[begin:end])
        body = [line.strip() for line in lines[begin + 1:end] if line.strip()]
        empty = body == ['(nothing)']
        if expect_empty:
            need(empty, 'OWNED_URI_GRANTS_NOT_EMPTY')
        self.ui.record(label, {'raw_sha256': sha(raw.encode()), 'raw_output_bytes': len(raw.encode()), 'exact_uri_grant_section': section, 'package_filter': self.scope.PACKAGE, 'empty': empty})
        return empty

    def uninstall(self, no_pending_effects):
        need(no_pending_effects is True, 'UNKNOWN_EFFECT_PRESERVE_NEW_PACKAGE')
        need(not self.install_pending and (not self.uninstall_pending), 'PACKAGE_MUTATION_PENDING_NO_RETRY')
        if self.installed is None:
            absent(self.s, self.scope.PACKAGE)
            self.data_absent()
            return {'package_absent_verified': True, 'data_directories_absent': True, 'installed_by_this_session': False}
        need(not self.ui.owned and (not self.ui.pending), 'TASK_LIFECYCLE_UNCERTAIN_KEEP_PACKAGE')
        need(identity(self.s, self.scope.PACKAGE, self.artifacts.APK_SHA) == self.installed, 'TEMPORARY_PACKAGE_CHANGED_BEFORE_UNINSTALL')
        self.ui.record('exact-new-package-uninstall-intent', {'package': self.scope.PACKAGE, 'identity': self.installed, 'preinstall_absent_all_users': True, 'automatic_retry': False})
        self.uninstall_pending = True
        raw = self.s.android(['/system/bin/pm', 'uninstall', self.scope.PACKAGE], 60).decode()
        need(raw.strip() == 'Success', 'UNINSTALL_RESPONSE_UNKNOWN')
        absent(self.s, self.scope.PACKAGE)
        self.data_absent()
        self.uninstall_pending = False
        return {'package_uninstalled_verified': True, 'package_absent_verified': True, 'data_directories_absent': True, 'installed_by_this_session': True}

    def cleanup_staged(self):
        if self.staged is None:
            return {'staged_apk_created': False}
        stage = self.staged
        try:
            if self.install_pending:
                self.ui.record('unknown-install-input-preserved', {'guest_path': stage['guest'], 'expected_sha256': self.artifacts.APK_SHA, 'reconciliation_required': True, 'automatic_retry': False})
                return {'staged_apk_retained_for_unknown_install': stage['guest'], 'staged_apk_removed': False}
            need(fp(os.stat(stage['name'], dir_fd=stage['parent'], follow_symlinks=False)) == stage['birth'] and fp(os.fstat(stage['directory'])) == stage['birth'], 'STAGE_DIRECTORY_CHANGED')
            info = os.stat('owned-features.apk', dir_fd=stage['directory'], follow_symlinks=False)
            fresh = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=stage['directory'])
            try:
                names = os.listdir(fresh)
            finally:
                os.close(fresh)
            need(fp(info) == stage['file_identity'] and names == ['owned-features.apk'], 'STAGED_APK_SCOPE_CHANGED')
            data, _ = self.s.target.read_file(stage['guest'], 1048576, single_link=True)
            need(sha(data) == self.artifacts.APK_SHA, 'STAGED_APK_CHANGED')
            os.unlink('owned-features.apk', dir_fd=stage['directory'])
            os.rmdir(stage['name'], dir_fd=stage['parent'])
            try:
                os.stat(stage['name'], dir_fd=stage['parent'], follow_symlinks=False)
            except FileNotFoundError:
                return {'staged_apk_removed': True}
            raise RuntimeError('STAGED_DIRECTORY_NOT_ABSENT')
        finally:
            close_stage_handles(self, stage)

    def release_local_handles(self):
        # No file/package/UI mutation: preserve UNKNOWN inputs and their paths.
        if self.staged is not None:
            close_stage_handles(self, self.staged)
