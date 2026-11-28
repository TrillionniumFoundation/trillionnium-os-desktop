"""Actual normal fixed fixture lifecycle for the original Documents feature business."""
import hashlib,re
DOCS='com.android.documentsui'
def identity(session,package,expected_sha,expected_uid=None,expected_code=1):
    channel=session.baseline.live
    fixture=channel.fixture()
    if package==fixture.spec['package']:
        value=fixture.identity()
        need(value['apk_sha256']==expected_sha and value['version_code']==expected_code and
             (expected_uid is None or value['uid']==expected_uid),'ACTUAL_FIXED_HELPER_IDENTITY_DIFFERS')
        return value
    return channel.original_identity(package,expected_sha,expected_uid,expected_code)

def need(ok,why):
    if not ok:raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()

class DocumentsPackageFixture:
    def __init__(self,session,tx,ui,result,*,scope,artifacts):
        scope.require_kind('features10');artifacts.validate_reference_shapes()
        self.scope,self.artifacts=scope,artifacts
        self.s,self.tx,self.ui,self.result=session,tx,ui,result
        self.fixed=session.baseline.live.fixture()
        self.staged=self.installed=None
        self.install_pending=self.uninstall_pending=False

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

    def pref_state(self):
        value,comparison=self.fixed.prefs()
        self.ui.record('actual-owned-helper-state',comparison)
        return value

    def uninstall(self,no_pending_effects):
        need(no_pending_effects is True,'UNKNOWN_EFFECT_PRESERVE_NEW_PACKAGE')
        need(not self.install_pending and not self.uninstall_pending,'PACKAGE_MUTATION_PENDING_NO_RETRY')
        if self.installed is None:
            return {'installed_by_this_session':False,'package_absent_verified':False,
                'data_directories_absent':False,'no_package_action_taken':True}
        need(not self.ui.owned and not self.ui.pending,'TASK_LIFECYCLE_UNCERTAIN_KEEP_PACKAGE')
        need(self.fixed.identity()==self.installed,'ACTUAL_HELPER_CHANGED_BEFORE_RETIREMENT')
        self.ui.record('fixed-owned-helper-retirement-intent',{'identity':self.installed,
            'retained_original_owner_required':True,'automatic_retry':False})
        self.uninstall_pending=True
        comparison=self.fixed.retire()
        self.uninstall_pending=False
        self.ui.record('actual-fixed-helper-retired',comparison)
        return {'package_uninstalled_verified':True,'package_absent_verified':True,
            'data_directories_absent':True,'installed_by_this_session':True,'actual_retirement':comparison}

    def cleanup_staged(self):
        need(self.staged is None,'UNEXPECTED_GUEST_STAGING_STATE')
        return {'guest_staging_used':False,'staged_apk_created':False,'staged_apk_removed':False}

    def packages(self, label):
        values = {DOCS: identity(self.s, DOCS, 'f7db1705178644333d5c9d291afd1170e71fcddfd1f73021381e1224be824899', 10022, 37), 'com.android.externalstorage': identity(self.s, 'com.android.externalstorage', '00cf8db78a3f8846e34fd3e6b7f1c811a9393b7c2e6227c083e27e5cdb0fa515', 10024, 37)}
        self.ui.record(label, values)
        return values

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
