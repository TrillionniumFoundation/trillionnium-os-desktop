"""Fixed create-only helper package lifecycle. No UI or provider operations here."""
from pathlib import Path
import hashlib,json,os,re,stat
RUN='c92c3d79180955ef'
PACKAGE='org.droidloom.qa.media.r12.n'+RUN
APK=Path('/home/alex/work/pocket4-gallery-video-fixture-build-20261105-r12-01/owned-media.apk')
APK_SHA='7fc4dadcc33c94cd41d0425473622df38138d60801c2e5585c4d28cf7db68933'
CERT_SHA='b152def48096bab1000175a762244910f2c4aa9b5b6b080813515a1a38a0b403'
BUILD=APK.parent/'build-result.json'
BUILD_SHA='632e5c0aa13a758f7245939b227577c1b8416a3c950e55eddbc5e0bb61d735b9'
PM_HELP=Path('/home/alex/work/pocket4-documents-pm-help-20261105-r12-01/result.json')
PM_HELP_SHA='55aec5478f67047efdace8c4b3ac22b484ccbe9f4df1f1508c1cb0d594aa48ba'

def need(ok,why):
    if not ok:raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def fp(info):return {k:getattr(info,k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode')}


def absent(session):
    listed=session.android(['/system/bin/pm','list','packages','-u','-U',PACKAGE]).decode()
    dump=session.android(['/system/bin/dumpsys','package',PACKAGE]).decode()
    need(not listed.strip() and dump.strip()=='Unable to find package: '+PACKAGE,'NEW_PACKAGE_NOT_ABSENT')


def identity(session,package,expected_sha,expected_uid=None,expected_code=1):
    raw=session.android(['/system/bin/dumpsys','package',package]).decode()
    blocks=re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)',raw,re.M|re.S)
    need(len(blocks)==1 and re.findall(r'^  Package \[([^]]+)\]',blocks[0],re.M)==[package],'PACKAGE_SECTION_CHANGED')
    block=blocks[0]
    def one(pattern):
        values=re.findall(pattern,block,re.M);need(len(values)==1,'PACKAGE_FIELD_AMBIGUOUS:'+pattern);return values[0]
    uid=int(one(r'^    appId=(\d+)$'));code=int(one(r'^    versionCode=(\d+)\b'))
    need((expected_uid is None or uid==expected_uid) and code==expected_code,'PACKAGE_UID_OR_VERSION_CHANGED')
    state=one(r'^    User 0: (.*)$')
    need(all(re.search(r'\b'+k+'='+v+r'\b',state) for k,v in
        (('installed','true'),('hidden','false'),('suspended','false'),('enabled','[01]'))),'PACKAGE_USER_STATE')
    paths=session.android(['/system/bin/pm','path','--user','0',package]).decode().splitlines()
    need(len(paths)==1 and paths[0].startswith('package:/') and paths[0].endswith('.apk'),'SINGLE_APK_PATH_REQUIRED')
    data,metadata=session.target.read_file(paths[0][8:],16*1024*1024,single_link=True)
    need(sha(data)==expected_sha,'INSTALLED_APK_HASH_CHANGED')
    directories={}
    for label,path in [('ce','/data/user/0/'+package),('de','/data/user_de/0/'+package)]:
        fd=session.target.open_root(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:info=os.fstat(fd);directories[label]=fp(info)
        finally:os.close(fd)
        inode=int(re.search(r'\b'+label+r'DataInode=(\d+)\b',state)[1])
        need(info.st_uid==info.st_gid==uid and info.st_ino==inode,'PACKAGE_DATA_IDENTITY_CHANGED')
    session.guard()
    return {'package':package,'uid':uid,'version_code':code,'apk_path':paths[0][8:],
        'apk_sha256':sha(data),'apk_bytes':len(data),'directories':directories}


class PackageFixture:
    def __init__(self,session,tx,ui,result):
        self.s,self.tx,self.ui,self.result=session,tx,ui,result
        self.staged=self.installed=None;self.install_pending=self.uninstall_pending=False

    def data_absent(self):
        for prefix in ('/data/user/0/','/data/user_de/0/'):
            try:fd=self.s.target.open_root(prefix+PACKAGE,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            except FileNotFoundError:continue
            else:os.close(fd);raise RuntimeError('PREEXISTING_HELPER_DATA_DIRECTORY_PRESERVED')

    def install(self):
        proof=json.loads(self.tx.read_regular(PM_HELP,PM_HELP_SHA,16384))
        need(proof['state']=='ACTUAL_NO_REPLACE_FLAG_VERIFIED' and proof['no_replace_flag']=='-R'
            and proof['guard_before']==proof['guard_after']==self.s.guard()
            and proof['ui_actions']==proof['package_mutations']==0
            and [line.strip() for line in proof['actual_flag_lines']]==
                ['-R: disallow replacement of existing application'],'ACTUAL_CREATE_ONLY_FLAG_PROOF_CHANGED')
        self.ui.record('actual-pm-no-replace-proof',proof)
        absent(self.s);self.data_absent()
        build_raw=BUILD.read_bytes();need(sha(build_raw)==BUILD_SHA,'BUILD_RECEIPT_CHANGED')
        build=json.loads(build_raw)
        need(build['state']=='BUILT_SIGNED_VERIFIED_UNINSTALLED' and build['apk']['sha256']==APK_SHA
            and build['signer_certificate_sha256']==CERT_SHA and build['permissions']==[] and build['launcher'] is False,
            'APK_PROVENANCE_NOT_VERIFIED')
        data=self.tx.read_regular(APK,APK_SHA,1048576);need(len(data)==139532,'APK_SIZE_CHANGED')
        parent=self.s.target.open_root('/data/local/tmp',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        name='pocket4-owned-galleryvideo-'+RUN;guest='/data/local/tmp/'+name+'/owned-media.apk'
        directory=None;created=False
        try:
            os.mkdir(name,0o755,dir_fd=parent);created=True
            directory=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
            os.fchmod(directory,0o755)  # Explicit traversal despite the operator's 077 umask.
            self.staged={'parent':parent,'directory':directory,'name':name,'birth':fp(os.fstat(directory)),
                'guest':guest,'file_identity':None}
        except BaseException:
            if directory is not None:os.close(directory)
            os.close(parent)
            if created:self.result['staging_setup_incomplete']={'path':'/data/local/tmp/'+name,
                'reconciliation_required':True,'directory_identity_not_yet_verified':True}
            raise
        fd=os.open('owned-media.apk',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o644,dir_fd=directory)
        with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno());os.fchmod(out.fileno(),0o644)
        self.staged['file_identity']=fp(os.stat('owned-media.apk',dir_fd=directory,follow_symlinks=False))
        staged,_=self.s.target.read_file(guest,1048576,single_link=True);need(sha(staged)==APK_SHA,'STAGED_APK_CHANGED')
        absent(self.s);self.data_absent();self.s.guard()
        argv=['/system/bin/pm','install','-R','-t','--user','0',guest]
        self.ui.record('create-only-install-intent',{'argv':argv,'replace_flag':False,'disallow_replacement_flag':'-R','pm_help_proof_sha256':PM_HELP_SHA,'apk_sha256':APK_SHA,
            'signer_sha256':CERT_SHA,'preinstall_absent_all_users':True,'automatic_retry':False})
        self.install_pending=True
        raw=self.s.android(argv,60).decode();need(raw.strip()=='Success','INSTALL_RESPONSE_NOT_SUCCESS')
        self.installed=identity(self.s,PACKAGE,APK_SHA)
        need(10000<=self.installed['uid']<20000,'NEW_APPLICATION_UID_OUT_OF_RANGE')
        self.install_pending=False;self.ui.record('new-package-installed',self.installed)
        self.result['installed_identity']=self.installed




    def uninstall(self,no_pending_effects):
        need(no_pending_effects is True,'UNKNOWN_EFFECT_PRESERVE_NEW_PACKAGE')
        need(not self.install_pending and not self.uninstall_pending,'PACKAGE_MUTATION_PENDING_NO_RETRY')
        if self.installed is None:
            absent(self.s);self.data_absent();return {'package_absent_verified':True,'data_directories_absent':True,
                'installed_by_this_session':False}
        need(not self.ui.owned and not self.ui.pending,'TASK_LIFECYCLE_UNCERTAIN_KEEP_PACKAGE')
        need(identity(self.s,PACKAGE,APK_SHA)==self.installed,'TEMPORARY_PACKAGE_CHANGED_BEFORE_UNINSTALL')
        self.ui.record('exact-new-package-uninstall-intent',{'package':PACKAGE,'identity':self.installed,
            'preinstall_absent_all_users':True,'automatic_retry':False})
        self.uninstall_pending=True
        raw=self.s.android(['/system/bin/pm','uninstall',PACKAGE],60).decode()
        need(raw.strip()=='Success','UNINSTALL_RESPONSE_UNKNOWN')
        absent(self.s);self.data_absent();self.uninstall_pending=False
        return {'package_uninstalled_verified':True,'package_absent_verified':True,'data_directories_absent':True,
            'installed_by_this_session':True}

    def cleanup_staged(self):
        if self.staged is None:return {'staged_apk_created':False}
        stage=self.staged
        try:
            if self.install_pending:
                self.ui.record('unknown-install-input-preserved',{'guest_path':stage['guest'],
                    'expected_sha256':APK_SHA,'reconciliation_required':True,'automatic_retry':False})
                return {'staged_apk_retained_for_unknown_install':stage['guest'],'staged_apk_removed':False}
            need(fp(os.stat(stage['name'],dir_fd=stage['parent'],follow_symlinks=False))==stage['birth']
                and fp(os.fstat(stage['directory']))==stage['birth'],'STAGE_DIRECTORY_CHANGED')
            info=os.stat('owned-media.apk',dir_fd=stage['directory'],follow_symlinks=False)
            fresh=os.open('.',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=stage['directory'])
            try:names=os.listdir(fresh)
            finally:os.close(fresh)
            need(fp(info)==stage['file_identity'] and names==['owned-media.apk'],'STAGED_APK_SCOPE_CHANGED')
            data,_=self.s.target.read_file(stage['guest'],1048576,single_link=True)
            need(sha(data)==APK_SHA,'STAGED_APK_CHANGED')
            os.unlink('owned-media.apk',dir_fd=stage['directory']);os.rmdir(stage['name'],dir_fd=stage['parent'])
            try:os.stat(stage['name'],dir_fd=stage['parent'],follow_symlinks=False)
            except FileNotFoundError:return {'staged_apk_removed':True}
            raise RuntimeError('STAGED_DIRECTORY_NOT_ABSENT')
        finally:
            os.close(stage['directory']);os.close(stage['parent']);self.staged=None
