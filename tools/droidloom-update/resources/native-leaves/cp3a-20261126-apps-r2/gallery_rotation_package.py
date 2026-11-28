"""Source-owned current fixture lifecycle; no host app-data or guest APK staging."""
import hashlib
from pathlib import Path
RUN='d24b61ed8f7c9a03'
PACKAGE='org.droidloom.qa.galleryrotation.r12.nd24b61ed8f7c9a03'
APK_SHA='d53ba35fdb2252126fef94ce7da2d43bff78560cc90111206b0c2c9e766777d3'
APK=Path('/usr/libexec/droidloom/native-application-leaves/prebuilt-state-fixtures/20261128-r1/rotation/helper.apk')
CERT_SHA='f122e9201c86a547b8cbaa37cbe2cd7962bb96eabe3c07365204d392b580244f'
def need(ok,why):
    if not ok:raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()

def identity(session,package,expected_sha,expected_uid=None,expected_code=1):
    channel=session.baseline.live
    fixture=channel.fixture()
    if package==fixture.spec['package']:
        value=fixture.identity()
        need(value['apk_sha256']==expected_sha and value['version_code']==expected_code and
             (expected_uid is None or value['uid']==expected_uid),'ACTUAL_FIXED_HELPER_IDENTITY_DIFFERS')
        return value
    return channel.original_identity(package,expected_sha,expected_uid,expected_code)

class PackageFixture:
    def __init__(self,session,tx,ui,result):
        self.s,self.tx,self.ui,self.result=session,tx,ui,result
        self.fixed=session.baseline.live.fixture()
        self.staged=self.installed=None
        self.install_pending=self.uninstall_pending=False

    def install(self):
        need(self.installed is None and not self.install_pending and not self.uninstall_pending,
             'CREATE_ONLY_HELPER_INSTALLATION_MUST_NOT_REPEAT')
        self.s.guard()
        source=self.fixed.source()
        need(source['package']==PACKAGE and source['run_id']==RUN and
             source['apk']['sha256']==APK_SHA and source['certificate_sha256']==CERT_SHA,
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

    def grants_empty(self,label):
        raw=self.s.android(['/system/bin/dumpsys','activity','package',PACKAGE,'permissions']).decode()
        header='ACTIVITY MANAGER URI PERMISSIONS (dumpsys activity permissions)'
        lines=raw.splitlines();indices=[i for i,line in enumerate(lines) if line.strip()==header]
        need(len(indices)==1,'URI_GRANT_SECTION_NOT_UNIQUE')
        begin=indices[0];end=next((i for i in range(begin+1,len(lines))
            if lines[i].startswith('ACTIVITY MANAGER ')),len(lines))
        body=[line.strip() for line in lines[begin+1:end] if line.strip()]
        need(body==['(nothing)'],'OWNED_URI_GRANTS_NOT_EMPTY')
        self.ui.record(label,{'package_filter':PACKAGE,'raw_sha256':sha(raw.encode()),
            'exact_uri_grant_section':'\n'.join(lines[begin:end]),'empty':True})
        return True
