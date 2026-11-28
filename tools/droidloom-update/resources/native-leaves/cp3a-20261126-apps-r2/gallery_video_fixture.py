"""Source-owned current fixture lifecycle; no host app-data or guest APK staging."""
import hashlib,os,signal
from pathlib import Path
RUN='c92c3d79180955ef'
PACKAGE='org.droidloom.qa.media.r12.nc92c3d79180955ef'
APK_SHA='f47d64fe943bb77fb8ad07288b4ae1c69e3db8cc8866b0e02230882134599820'
APK=Path('/usr/libexec/droidloom/native-application-leaves/prebuilt-state-fixtures/20261128-r1/video/helper.apk')
CERT_SHA='011632c9e2a1693585594df2bcc4b4fdb4cd074a05ccbdc5aa951aa1de9ad0b2'
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
