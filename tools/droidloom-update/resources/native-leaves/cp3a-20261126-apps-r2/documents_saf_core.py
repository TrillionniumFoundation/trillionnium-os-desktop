"""Original SAF11 business methods with explicit fresh names and artifacts.
Historical failures/fence are checked separately; their activation and nonce
are never imported or transferred. Import has no Main, APK or UI side effect.
"""
from pathlib import Path
import hashlib, json, os, re, signal, stat, time
import xml.etree.ElementTree as ET
DOCS = 'com.android.documentsui'
AUTHORITY = 'com.android.externalstorage.documents'
PICKER_ROUTE = (DOCS, DOCS + '.picker.PickActivity')
FILES_ROUTE = (DOCS, DOCS + '.files.FilesActivity')
RESOLVER_ROUTE = ('android', 'com.android.internal.app.ResolverActivity')

def need(value, reason):
    if not value:
        raise RuntimeError(reason)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def fp(info):
    return {k: getattr(info, k) for k in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode')}

def identity(session,package,expected_sha,expected_uid=None,expected_code=1):
    channel=session.baseline.live
    fixture=channel.fixture()
    if package==fixture.spec['package']:
        value=fixture.identity()
        need(value['apk_sha256']==expected_sha and value['version_code']==expected_code and
             (expected_uid is None or value['uid']==expected_uid),'ACTUAL_FIXED_HELPER_IDENTITY_DIFFERS')
        return value
    return channel.original_identity(package,expected_sha,expected_uid,expected_code)




class SAF11OwnedFolder:

    def __init__(self, session, record, *, scope):
        scope.require_kind('saf11')
        self.scope = scope
        self.s, self.record = (session, record)
        self.parent = self.fd = None
        self.created = False
        self.removed = False

    def setup(self):
        self.s.guard()
        self.parent = self.s.target.open_root('/storage/emulated/0', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.stat(self.scope.FOLDER, dir_fd=self.parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise RuntimeError('EXCLUSIVE_OWNED_FOLDER_ALREADY_EXISTS')
        self.record('fixture-directory-create-intent', {'path': '/storage/emulated/0/' + self.scope.FOLDER, 'scope': 'fixture setup only; no App create qualification', 'file_writes': 0, 'automatic_retry': False})
        os.mkdir(self.scope.FOLDER, 448, dir_fd=self.parent)
        self.created = True
        self.fd = os.open(self.scope.FOLDER, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.parent)
        self.birth = fp(os.fstat(self.fd))
        need(not os.listdir(self.fd), 'OWNED_DIRECTORY_NOT_EMPTY')
        self.record('fixture-directory-created', {'identity': self.birth, 'entries': [], 'created_by_app': False})
        self.s.guard()

    def check(self):
        need(self.created and self.fd is not None and (not self.removed), 'NO_OWNED_DIRECTORY')
        self.s.guard()
        info = os.stat(self.scope.FOLDER, dir_fd=self.parent, follow_symlinks=False)
        need(fp(info) == self.birth and fp(os.fstat(self.fd)) == self.birth, 'OWNED_DIRECTORY_REPLACED')
        fresh = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.fd)
        try:
            need(fp(os.fstat(fresh)) == self.birth, 'FRESH_ENUMERATION_DIRECTORY_CHANGED')
            names = os.listdir(fresh)
        finally:
            os.close(fresh)
        need(fp(os.stat(self.scope.FOLDER, dir_fd=self.parent, follow_symlinks=False)) == self.birth and fp(os.fstat(self.fd)) == self.birth, 'OWNED_DIRECTORY_CHANGED_AFTER_ENUMERATION')
        need(len(names) <= 1 and set(names) <= self.scope.NAMES, 'UNEXPECTED_OWNED_DIRECTORY_ENTRY_PRESERVED')
        return names

    def verify(self, name, label):
        need(name in self.scope.NAMES and self.check() == [name], 'EXACT_SINGLE_OWNED_FILENAME_REQUIRED:' + name)
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.fd)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and (before.st_size == 87), 'OWNED_DOCUMENT_TYPE_OR_SIZE_CHANGED')
            data = os.read(fd, 1025)
            after = os.fstat(fd)
            need(len(data) == 87 and sha(data) == self.scope.PAYLOAD_SHA and (fp(before) == fp(after)) and (before.st_mtime_ns == after.st_mtime_ns) and (before.st_ctime_ns == after.st_ctime_ns), 'OWNED_DOCUMENT_HASH_CHANGED')
        finally:
            os.close(fd)
        value = {'name': name, 'bytes': 87, 'sha256': sha(data), 'identity': fp(before), 'mtime_ns': before.st_mtime_ns, 'ctime_ns': before.st_ctime_ns}
        self.record(label, value)
        return value

    def absence(self, label):
        need(self.check() == [], 'OWNED_DOCUMENT_NOT_ABSENT')
        for name in self.scope.NAMES:
            try:
                os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise RuntimeError('DOCUMENT_STILL_PRESENT')
        self.record(label, {'exact_names': sorted(self.scope.NAMES), 'all_errno_ENOENT': True, 'directory_identity': self.birth})

    def cleanup(self, allow_file):
        if not self.created:
            return {'directory_created': False}
        names = self.check()
        fallback = False
        if names:
            need(allow_file, 'OWNED_DOCUMENT_WRITE_OUTCOME_PENDING_PRESERVE_FOR_RECONCILIATION')
            name = names[0]
            proof = self.verify(name, 'fallback-exact-fixture-readback')
            now = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            need(fp(now) == proof['identity'] and now.st_mtime_ns == proof['mtime_ns'] and (now.st_ctime_ns == proof['ctime_ns']), 'FIXTURE_CHANGED_BEFORE_CLEANUP')
            self.record('fallback-delete-intent', {'name': name, 'proof': proof, 'only_owned_fixture': True, 'provider_or_UI_delete_qualified': False, 'automatic_retry': False})
            os.unlink(name, dir_fd=self.fd)
            fallback = True
        self.absence('cleanup-fixture-absence')
        self.check()
        os.rmdir(self.scope.FOLDER, dir_fd=self.parent)
        try:
            os.stat(self.scope.FOLDER, dir_fd=self.parent, follow_symlinks=False)
        except FileNotFoundError:
            self.removed = True
        need(self.removed, 'OWNED_DIRECTORY_REMOVE_NOT_VERIFIED')
        return {'directory_removed_verified': True, 'fallback_file_unlink': fallback, 'file_contents_written_by_host': False}

    def close(self):
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
        errors = []
        try:
            for key in ('fd', 'parent'):
                fd = getattr(self, key)
                setattr(self, key, None)
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError as error:
                        errors.append(error)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
        if errors:
            raise errors[0]

class SAF11Flow:

    def __init__(self, session, tx, adapter, *, scope, artifacts, history):
        self.artifacts = artifacts
        self.fixed = session.baseline.live.fixture()
        self.history = history
        scope.require_kind('saf11')
        self.scope = scope
        self.s, self.tx = (session, tx)
        self.ui = adapter.Adapter(session, tx, self.scope.ROOT)
        self.folder = SAF11OwnedFolder(session, self.ui.record, scope=scope)
        self.staged = None
        self.installed = None
        self.install_pending = self.uninstall_pending = False
        self.status = None
        self.result = {'state': 'NOT_STARTED', 'business_flow_completed': False, 'whole_app_production_ready': False, 'package': self.scope.PACKAGE, 'run': self.scope.RUN, 'gates': {}, 'temporary_package_excluded_from_launcher_denominator': True, 'automatic_retry': False, 'user_file_contents_read': False}

    def install(self):
        need(self.installed is None and not self.install_pending and not self.uninstall_pending,
             'CREATE_ONLY_HELPER_INSTALLATION_MUST_NOT_REPEAT')
        self.s.guard()
        source=self.fixed.source()
        need(source['package']==self.scope.PACKAGE and source['run_id']==self.scope.RUN and
             source['apk']['sha256']==self.artifacts.APK_SHA and source['certificate_sha256']==self.artifacts.CERT_SHA,
             'FIXED_CURRENT_HELPER_GENERATION_DIFFERS')
        self.ui.record('fixed-create-only-install-intent',{'source':source,
            'normal_packageinstaller_session':True,'guest_staging_used':False,'automatic_retry':False})
        self.install_pending=True
        comparison=self.fixed.begin()
        self.installed=self.fixed.identity(refresh=False)
        self.install_pending=False
        self.ui.record('actual-fixed-helper-installed',comparison)
        self.result['installed_identity']=self.installed
        self.result['normal_fixture_installation']=comparison
        self.s.guard()



    def packages(self, label):
        values = {DOCS: identity(self.s, DOCS, 'f7db1705178644333d5c9d291afd1170e71fcddfd1f73021381e1224be824899', 10022, 37), 'com.android.externalstorage': identity(self.s, 'com.android.externalstorage', '00cf8db78a3f8846e34fd3e6b7f1c811a9393b7c2e6227c083e27e5cdb0fa515', 10024, 37)}
        self.ui.record(label, values)
        return values

    def pref_state(self):
        value,comparison=self.fixed.prefs()
        self.ui.record('actual-owned-helper-state',comparison)
        return value



    def status_ui(self, phase):
        obs = self.ui.observe('client-' + phase, [self.scope.CLIENT_ROUTE])
        node = self.ui.one(obs, lambda n: n.get('resource-id') == self.scope.PACKAGE + ':id/status', 'ONE_CLIENT_STATUS_REQUIRED')
        value = json.loads(node.get('text', ''))
        need(value.get('run') == self.scope.RUN and value.get('phase') == phase and (value.get('pending') == '') and (value.get('error') == ''), 'EXPECTED_CLIENT_BUSINESS_PHASE_MISSING:' + phase)
        if phase != 'NEW':
            need(value.get('sha256') == self.scope.PAYLOAD_SHA and value.get('bytes') == 87, 'APP_READBACK_HASH_MISSING')
        self.status = value
        self.result['gates'][phase] = {'passed': True, 'client_status': value}
        return obs

    def client_button(self, obs, suffix, label, transition=None):
        node = self.ui.one(obs, lambda n: n.get('resource-id') == self.scope.PACKAGE + ':id/' + suffix and n.get('enabled') is True and (n.get('clickable') is True), 'ONE_CLIENT_BUTTON_REQUIRED')
        self.ui.input(obs, label, node, transition=transition)

    def own_location(self, obs):
        need(any((n.get('text') == self.scope.FOLDER or n.get('content-desc') == self.scope.FOLDER for n in obs['nodes'])), 'ACTUAL_PICKER_OR_FILES_OWNED_FOLDER_NOT_VISIBLE')
        self.folder.check()

    def control(self, obs, text):
        return self.ui.one(obs, lambda n: n.get('enabled') is True and n.get('editable') is False and (n.get('class') in ('android.widget.TextView', 'android.widget.Button', 'android.widget.ImageButton', 'android.widget.CheckedTextView')) and (str(n.get('text', '')).strip().casefold() == text.casefold() or str(n.get('content-desc', '')).strip().casefold() == text.casefold()), 'ONE_VISIBLE_CONTROL_REQUIRED:' + text)

    def files_more(self, obs, selected=False):
        need((obs['focus']['package'], obs['focus']['activity']) == FILES_ROUTE, 'FILES_MENU_ROUTE_REQUIRED')

        def inside(outer, inner):
            return isinstance(outer, list) and isinstance(inner, list) and (len(outer) == len(inner) == 4) and all((type(v) is int for v in outer + inner)) and (outer[0] <= inner[0] < inner[2] <= outer[2]) and (outer[1] <= inner[1] < inner[3] <= outer[3])
        bar_id = DOCS + (':id/action_mode_bar' if selected else ':id/toolbar')
        bar = self.ui.one(obs, lambda n: n.get('package') == DOCS and n.get('resource-id') == bar_id and (n.get('class') == 'android.view.ViewGroup') and (n.get('enabled') is True) and (n.get('visible') is True), 'ONE_ACTUAL_FILES_TOOLBAR_REQUIRED')
        if selected:
            row = self.row(obs, self.scope.PROVIDER)
            need(row.get('selected') is True and row.get('resource-id') == DOCS + ':id/item_root', 'OWNED_FILE_CARD_NOT_SELECTED')
            self.ui.one(obs, lambda n: n.get('resource-id') == DOCS + ':id/action_bar_title' and n.get('class') == 'android.widget.TextView' and (n.get('text') == '1 selected') and (n.get('enabled') is True) and (n.get('window_id') == bar.get('window_id')) and inside(bar.get('bounds_array'), n.get('bounds_array')), 'ONE_SELECTED_FILE_TITLE_IN_ACTION_MODE_BAR_REQUIRED')
        else:
            need(not any((n.get('resource-id') == DOCS + ':id/action_mode_bar' for n in obs['nodes'])), 'NORMAL_TOOLBAR_WITH_ACTIVE_SELECTION_MODE')
        return self.ui.one(obs, lambda n: n.get('package') == DOCS and n.get('enabled') is True and (n.get('class') == 'android.widget.ImageView') and (n.get('content-desc') == 'More options') and (n.get('clickable') is True) and (n.get('editable') is False) and (n.get('window_id') == bar.get('window_id')) and inside(bar.get('bounds_array'), n.get('bounds_array')) and (16 in n.get('supported_actions', [])), 'ONE_ACTUAL_FILES_OVERFLOW_IN_TOOLBAR_REQUIRED')

    def select_single_owned_file(self, obs):
        self.own_location(obs)
        self.folder.verify(self.scope.PROVIDER, 'sole-file-before-menu-selection')
        row = self.row(obs, self.scope.PROVIDER)
        roots = [n for n in obs['nodes'] if n.get('resource-id') == DOCS + ':id/item_root']
        need(roots == [row], 'ONLY_ONE_OBSERVED_OWNED_FILE_CARD_REQUIRED')
        self.ui.input(obs, 'files-selection-menu', self.files_more(obs), popup=True)
        menu = self.ui.observe('files-selection-menu', [FILES_ROUTE])
        self.folder.verify(self.scope.PROVIDER, 'sole-file-before-select-all')
        self.ui.input(menu, 'select-only-owned-file', self.control(menu, 'Select all'))
        selected = self.ui.observe('files-selected', [FILES_ROUTE])
        self.own_location(selected)
        self.folder.verify(self.scope.PROVIDER, 'sole-file-after-menu-selection')
        self.row(selected, self.scope.PROVIDER)
        count = self.ui.one(selected, lambda n: n.get('enabled') is True and n.get('class') == 'android.widget.TextView' and re.fullmatch('1(?:\\s+item)?\\s+selected', str(n.get('text', '')).strip(), re.I), 'EXACTLY_ONE_FILE_SELECTION_COUNT_REQUIRED')
        self.ui.record('selection-mode-verified', {'count': 1, 'filename': self.scope.PROVIDER, 'count_node': count, 'sole_owned_file_hash_verified': True, 'selection_via_observed_menu': True, 'long_press_used': False})
        return selected

    def confirm_owned_rename(self, obs):

        def controls(observation):
            field = self.ui.one(observation, lambda n: n.get('editable') is True and n.get('text') == self.scope.FILES, 'EXACT_RENAME_TEXT_REQUIRED_BEFORE_CONFIRM')
            button = self.ui.one(observation, lambda n: n.get('enabled') is True and n.get('clickable') is True and (n.get('class') == 'android.widget.Button') and (n.get('resource-id') == 'android:id/button1') and (str(n.get('text', '')).casefold() in ('ok', 'rename')) and (16 in n.get('supported_actions', [])), 'ONE_ACTUAL_RENAME_DIALOG_POSITIVE_BUTTON_REQUIRED')
            return (field, button)

        def stable(node):
            return {k: v for k, v in node.items() if k != 'window_id'}
        field, button = controls(obs)
        original_focus = obs['focus']
        original_context = obs['screenshot']['context_token']
        for decision in range(3):
            self.folder.verify(self.scope.PROVIDER, 'uncommitted-rename-before-decision-' + str(decision + 1))
            try:
                self.ui.input(obs, 'files-rename-confirm-' + str(decision + 1), button)
                return
            except self.s.helper.ControlError as exc:
                details = exc.details
                if str(exc) != 'STALE_FRAME' or details.get('action_taken') is not False or details.get('outcome_unknown') is True or self.ui.pending or (decision == 2):
                    raise
                self.ui.record('rename-confirm-no-effect-redecision', {'previous_decision': decision + 1, 'action_taken': False, 'unknown_input_replayed': False, 'maximum_decisions': 3})
                fresh = self.ui.observe('rename-confirm-fresh-' + str(decision + 2), [FILES_ROUTE])
                need(fresh['focus'] == original_focus and fresh['screenshot']['context_token'] == original_context, 'RENAME_CONFIRM_FOCUS_OR_CONTEXT_CHANGED')
                new_field, new_button = controls(fresh)
                need(stable(new_field) == stable(field) and stable(new_button) == stable(button), 'RENAME_CONFIRM_FORM_CHANGED')
                self.result.setdefault('confirmed_no_effect_fresh_decisions', []).append(decision + 2)
                obs, field, button = (fresh, new_field, new_button)

    def row(self, obs, name, longpress=False):
        label = self.ui.one(obs, lambda n: n.get('text') == name and n.get('editable') is False, 'ONE_EXACT_OWNED_FILENAME_REQUIRED')
        box = label.get('bounds_array')
        need(isinstance(box, list) and len(box) == 4, 'FILENAME_BOUNDS')

        def contains(outer, inner):
            return isinstance(outer, list) and len(outer) == 4 and all((type(v) is int for v in outer)) and (outer[0] <= inner[0] < inner[2] <= outer[2]) and (outer[1] <= inner[1] < inner[3] <= outer[3])
        candidates = [n for n in obs['nodes'] if n.get('enabled') is True and n.get('window_id') == label.get('window_id') and contains(n.get('bounds_array'), box) and (32 in n.get('supported_actions', []) if longpress else n.get('clickable') is True and 16 in n.get('supported_actions', []))]
        need(candidates, 'OBSERVED_FILE_ROW_CAPABILITY_MISSING')
        smallest = [n for n in candidates if not any((x is not n and x['bounds_array'] != n['bounds_array'] and contains(n['bounds_array'], x['bounds_array']) for x in candidates))]
        need(len(smallest) == 1, 'INNermost_FILE_ROW_NOT_UNIQUE')
        return smallest[0]

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

    def business(self):
        self.result['historical_prerequisites'] = self.history.verify(self.s, self.ui.record)
        before = self.packages('target-identities-before')
        self.install()
        self.folder.setup()
        self.grants('new-package-grants-empty', True)
        self.ui.launch()
        obs = self.status_ui('NEW')
        self.client_button(obs, 'create_document', 'create-picker')
        obs = self.ui.observe('create-picker', [PICKER_ROUTE])
        self.s.view.commands.native_channel_module().ComparisonChannel().observe_running_engine()
        self.own_location(obs)
        self.ui.one(obs, lambda n: n.get('editable') is True and n.get('text') == self.scope.CREATED, 'EXACT_CREATE_FILENAME_REQUIRED')
        need(self.folder.check() == [], 'OWNED_FOLDER_NOT_EMPTY_BEFORE_PICKER_SAVE')
        self.ui.input(obs, 'picker-save', self.control(obs, 'Save'))
        obs = self.status_ui('CREATE_WRITE_READ_OK')
        self.folder.verify(self.scope.CREATED, 'created-file-readback')
        self.grants('created-document-persisted-grants')
        self.client_button(obs, 'provider_rename', 'provider-rename')
        obs = self.status_ui('PROVIDER_RENAME_OK')
        self.folder.verify(self.scope.PROVIDER, 'provider-rename-readback')
        self.client_button(obs, 'open_files', 'open-files', FILES_ROUTE)
        obs = self.ui.observe('files-owned-folder', [FILES_ROUTE], admit=True)
        self.s.view.commands.native_channel_module().ComparisonChannel().observe_running_engine()
        self.own_location(obs)
        obs = self.select_single_owned_file(obs)
        self.ui.one(obs, lambda n: n.get('text') == self.scope.PROVIDER, 'SELECTED_OWNED_FILENAME_MISSING')
        direct = [n for n in obs['nodes'] if n.get('enabled') is True and n.get('clickable') is True and (n.get('text') == 'Rename' or n.get('content-desc') == 'Rename')]
        if not direct:
            self.ui.input(obs, 'files-more', self.files_more(obs, selected=True), popup=True)
            obs = self.ui.observe('files-owned-menu', [FILES_ROUTE])
        self.ui.input(obs, 'files-rename-menu', self.control(obs, 'Rename'))
        obs = self.ui.observe('files-rename-dialog', [FILES_ROUTE])
        field = self.ui.one(obs, lambda n: n.get('editable') is True and n.get('text') == self.scope.PROVIDER, 'EXACT_RENAME_INPUT_REQUIRED')
        self.ui.input(obs, 'files-rename-text', field, 'set-text', self.scope.FILES)
        obs = self.ui.observe('files-rename-text-readback', [FILES_ROUTE])
        self.ui.one(obs, lambda n: n.get('editable') is True and n.get('text') == self.scope.FILES, 'UI_RENAME_TEXT_READBACK')
        self.confirm_owned_rename(obs)
        obs = self.ui.observe('files-renamed', [FILES_ROUTE])
        self.own_location(obs)
        self.folder.verify(self.scope.FILES, 'actual-files-ui-rename-readback')
        self.result['gates']['FILES_UI_RENAME'] = {'passed': True, 'old_name_absent': True, 'new_name': self.scope.FILES, 'sha256': self.scope.PAYLOAD_SHA}
        self.ui.input(obs, 'files-open-owned-file', self.row(obs, self.scope.FILES), transition=RESOLVER_ROUTE)
        obs = self.ui.observe('files-open-result', [self.scope.CLIENT_ROUTE, RESOLVER_ROUTE], admit=True)
        if obs['focus']['package'] == 'android':
            self.ui.input(obs, 'resolver-owned-client', self.control(obs, self.scope.APP_LABEL))
            obs = self.ui.observe('resolver-owned-client-selected', [RESOLVER_ROUTE])
            self.ui.input(obs, 'resolver-just-once', self.control(obs, 'Just once'))
        obs = self.status_ui('FILES_VIEW_OK')
        self.client_button(obs, 'open_document', 'open-picker')
        obs = self.ui.observe('open-picker', [PICKER_ROUTE])
        self.s.view.commands.native_channel_module().ComparisonChannel().observe_running_engine()
        self.own_location(obs)
        self.ui.input(obs, 'picker-select-owned-document', self.row(obs, self.scope.FILES))
        self.status_ui('OPEN_OK')
        self.ui.close_all()
        self.ui.launch()
        obs = self.status_ui('REOPEN_OK')
        self.folder.verify(self.scope.FILES, 'reopen-file-persistence')
        self.client_button(obs, 'provider_delete', 'provider-delete')
        self.status_ui('DELETE_PROVIDER_ACK')
        self.folder.absence('provider-delete-true-absence')
        self.grants('provider-delete-grants-empty', True)
        self.result['gates']['PROVIDER_DELETE_AND_ABSENCE'] = {'passed': True, 'all_exact_paths_errno_ENOENT': True, 'grants_empty': True}
        self.ui.close_all()
        need(self.packages('target-identities-after') == before, 'TARGET_PACKAGE_IDENTITIES_CHANGED')
        need(identity(self.s, self.scope.PACKAGE, self.artifacts.APK_SHA) == self.installed, 'TEMPORARY_APP_IDENTITY_CHANGED')
        need(self.ui.launches == 2 and (not self.ui.pending), 'CLIENT_LIFECYCLE_OR_PENDING_EFFECTS_INCOMPLETE')
        self.result.update(state='SCOPED_SAF_AND_FILES_BUSINESS_COMPLETED', business_flow_completed=True)

    def cleanup(self):
        cleanup={'errors':[],'package_uninstalled_verified':False,'package_absent_verified':False,
            'file_cleanup':None,'guest_staging_used':False,'staged_apk_created':False,'staged_apk_removed':False}
        try:self.ui.close_all()
        except BaseException as exc:cleanup['errors'].append('owned_tasks:'+type(exc).__name__+':'+str(exc))
        try:
            if self.installed is not None and not self.install_pending and not self.uninstall_pending:
                need(not self.ui.pending,'UI_OUTCOME_PENDING_PRESERVE_OWNED_FIXTURE_AND_PACKAGE')
                phase=self.pref_state()
                allow_file=phase is None or phase.get('pending','') in ('','FILES_REQUESTED')
                need(allow_file,'CLIENT_PROVIDER_EFFECT_PENDING_PRESERVE_FOR_RECONCILIATION')
                if self.folder.created:cleanup['file_cleanup']=self.folder.cleanup(allow_file)
                need(not self.ui.owned and not self.ui.pending,'OWNED_TASK_LIFECYCLE_UNCERTAIN_KEEP_PACKAGE')
                need(self.fixed.identity()==self.installed,'TEMPORARY_PACKAGE_CHANGED_BEFORE_RETIREMENT')
                self.uninstall_pending=True
                comparison=self.fixed.retire()
                self.ui.record('actual-fixed-helper-retired',comparison)
                self.uninstall_pending=False
                cleanup.update(package_uninstalled_verified=True,package_absent_verified=True,
                    data_directories_absent=True,actual_retirement=comparison)
            elif self.install_pending:
                raise RuntimeError('INSTALL_UNKNOWN_PRESERVE_FOR_READ_ONLY_RECONCILIATION')
            else:cleanup['no_package_action_taken']=True
        except BaseException as exc:cleanup['errors'].append('fixture_or_package:'+type(exc).__name__+':'+str(exc))
        finally:self.release_local_handles()
        return cleanup


    def release_local_handles(self):
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
        errors = []
        try:
            if self.staged is not None:
                for key in ('directory', 'parent'):
                    fd = self.staged.get(key)
                    self.staged[key] = None
                    if fd is not None:
                        try:
                            os.close(fd)
                        except OSError as error:
                            errors.append(error)
            try:
                self.folder.close()
            except OSError as error:
                errors.append(error)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
        if errors:
            raise errors[0]
