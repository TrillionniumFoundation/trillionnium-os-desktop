#!/usr/bin/python3 -I
"""One isolated SAF + Files flow. Default inert. Exact own package/folder cleanup only."""
from pathlib import Path
import argparse, hashlib, json, os, re, signal, stat, time, types
import xml.etree.ElementTree as ET

SOURCE=Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
SOURCE_SHA='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
ADAPTER=Path('/home/alex/work/pocket4-documents-flow-20261105-r12-tools-01/ui_adapter01.py')
ADAPTER_SHA='0dc186a9bc552b576a361b2c3e18128d31f2473ae9344ade1a1089f0f1d147d3'
ROOT=Path('/home/alex/work/pocket4-documents-flow-20261105-r12-01')
APK=Path('/home/alex/work/pocket4-documents-saf-build-20261105-r12-02/owned-saf.apk')
APK_SHA='3b2b8d01b551f68256a25c351b34f2a6c74f74cbfc9b44b226ea708dba9fffe6'
CERT_SHA='f772d334443bb5cd71abcc179d04e21ee3e70d424290df69828b94e42bc448f2'
BUILD=APK.parent/'build-result.json'
PM_HELP=Path('/home/alex/work/pocket4-documents-pm-help-20261105-r12-01/result.json')
PM_HELP_SHA='55aec5478f67047efdace8c4b3ac22b484ccbe9f4df1f1508c1cb0d594aa48ba'
BUILD_SHA='c3e63b03865200ce5b2f5c8f037c17b8e54a290f259312111cb481ae045482e8'
RUN='69814e80ea71f485'
PACKAGE='org.droidloom.qa.saf.r12.n'+RUN
FOLDER='Pocket4_SAF_r12_'+RUN
CREATED='created-'+RUN+'.txt';PROVIDER='provider-'+RUN+'.txt';FILES='files-ui-'+RUN+'.txt'
NAMES={CREATED,PROVIDER,FILES}
PAYLOAD_SHA='5e8ee8b6e154ade076e1f62e1ff0bc206ae69ba41982ac1c7a048c303f0503e7'
MAX_SECONDS=720;CLEANUP_RESERVE=120
DOCS='com.android.documentsui';AUTHORITY='com.android.externalstorage.documents'
CLIENT_ROUTE=(PACKAGE,PACKAGE+'.SafActivity');PICKER_ROUTE=(DOCS,DOCS+'.picker.PickActivity')
FILES_ROUTE=(DOCS,DOCS+'.files.FilesActivity');RESOLVER_ROUTE=('android','com.android.internal.app.ResolverActivity')


def need(value,reason):
    if not value:raise RuntimeError(reason)


def sha(data):return hashlib.sha256(data).hexdigest()


def load(path,pin,name):
    raw=path.read_bytes();need(sha(raw)==pin,'SOURCE_PIN_CHANGED:'+name)
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__);return module


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


class OwnedFolder:
    def __init__(self,session,record):
        self.s,self.record=session,record;self.parent=self.fd=None;self.created=False;self.removed=False

    def setup(self):
        self.s.guard();self.parent=self.s.target.open_root('/storage/emulated/0',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.stat(FOLDER,dir_fd=self.parent,follow_symlinks=False)
        except FileNotFoundError:pass
        else:raise RuntimeError('EXCLUSIVE_OWNED_FOLDER_ALREADY_EXISTS')
        self.record('fixture-directory-create-intent',{'path':'/storage/emulated/0/'+FOLDER,
            'scope':'fixture setup only; no App create qualification','file_writes':0,'automatic_retry':False})
        os.mkdir(FOLDER,0o700,dir_fd=self.parent);self.created=True
        self.fd=os.open(FOLDER,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.parent)
        self.birth=fp(os.fstat(self.fd));need(not os.listdir(self.fd),'OWNED_DIRECTORY_NOT_EMPTY')
        self.record('fixture-directory-created',{'identity':self.birth,'entries':[],'created_by_app':False})
        self.s.guard()

    def check(self):
        need(self.created and self.fd is not None and not self.removed,'NO_OWNED_DIRECTORY')
        self.s.guard();info=os.stat(FOLDER,dir_fd=self.parent,follow_symlinks=False)
        need(fp(info)==self.birth and fp(os.fstat(self.fd))==self.birth,'OWNED_DIRECTORY_REPLACED')
        names=os.listdir(self.fd);need(len(names)<=1 and set(names)<=NAMES,'UNEXPECTED_OWNED_DIRECTORY_ENTRY_PRESERVED')
        return names

    def verify(self,name,label):
        need(name in NAMES and self.check()==[name],'EXACT_SINGLE_OWNED_FILENAME_REQUIRED:'+name)
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.fd)
        try:
            before=os.fstat(fd);need(stat.S_ISREG(before.st_mode) and before.st_nlink==1
                and before.st_size==87,'OWNED_DOCUMENT_TYPE_OR_SIZE_CHANGED')
            data=os.read(fd,1025);after=os.fstat(fd)
            need(len(data)==87 and sha(data)==PAYLOAD_SHA and fp(before)==fp(after)
                and before.st_mtime_ns==after.st_mtime_ns and before.st_ctime_ns==after.st_ctime_ns,'OWNED_DOCUMENT_HASH_CHANGED')
        finally:os.close(fd)
        value={'name':name,'bytes':87,'sha256':sha(data),'identity':fp(before),
            'mtime_ns':before.st_mtime_ns,'ctime_ns':before.st_ctime_ns}
        self.record(label,value);return value

    def absence(self,label):
        need(self.check()==[],'OWNED_DOCUMENT_NOT_ABSENT')
        for name in NAMES:
            try:os.stat(name,dir_fd=self.fd,follow_symlinks=False)
            except FileNotFoundError:continue
            raise RuntimeError('DOCUMENT_STILL_PRESENT')
        self.record(label,{'exact_names':sorted(NAMES),'all_errno_ENOENT':True,'directory_identity':self.birth})

    def cleanup(self,allow_file):
        if not self.created:return {'directory_created':False}
        names=self.check();fallback=False
        if names:
            need(allow_file,'OWNED_DOCUMENT_WRITE_OUTCOME_PENDING_PRESERVE_FOR_RECONCILIATION')
            name=names[0];proof=self.verify(name,'fallback-exact-fixture-readback')
            now=os.stat(name,dir_fd=self.fd,follow_symlinks=False)
            need(fp(now)==proof['identity'] and now.st_mtime_ns==proof['mtime_ns']
                and now.st_ctime_ns==proof['ctime_ns'],'FIXTURE_CHANGED_BEFORE_CLEANUP')
            self.record('fallback-delete-intent',{'name':name,'proof':proof,'only_owned_fixture':True,
                'provider_or_UI_delete_qualified':False,'automatic_retry':False})
            os.unlink(name,dir_fd=self.fd);fallback=True
        self.absence('cleanup-fixture-absence');self.check()
        os.rmdir(FOLDER,dir_fd=self.parent)
        try:os.stat(FOLDER,dir_fd=self.parent,follow_symlinks=False)
        except FileNotFoundError:self.removed=True
        need(self.removed,'OWNED_DIRECTORY_REMOVE_NOT_VERIFIED')
        return {'directory_removed_verified':True,'fallback_file_unlink':fallback,'file_contents_written_by_host':False}

    def close(self):
        for fd in (self.fd,self.parent):
            if fd is not None:os.close(fd)


class Flow:
    def __init__(self,session,tx,adapter):
        self.s,self.tx=session,tx;self.ui=adapter.Adapter(session,tx,ROOT)
        self.folder=OwnedFolder(session,self.ui.record);self.staged=None;self.installed=None
        self.install_pending=self.uninstall_pending=False;self.status=None
        self.result={'state':'NOT_STARTED','business_flow_completed':False,'whole_app_production_ready':False,
            'package':PACKAGE,'run':RUN,'gates':{},'temporary_package_excluded_from_launcher_denominator':True,
            'automatic_retry':False,'user_file_contents_read':False}

    def install(self):
        proof=json.loads(self.tx.read_regular(PM_HELP,PM_HELP_SHA,16384))
        need(proof['state']=='ACTUAL_NO_REPLACE_FLAG_VERIFIED' and proof['no_replace_flag']=='-R'
            and proof['guard_before']==proof['guard_after']==self.s.guard()
            and proof['ui_actions']==proof['package_mutations']==0
            and [line.strip() for line in proof['actual_flag_lines']]==
                ['-R: disallow replacement of existing application'],'ACTUAL_CREATE_ONLY_FLAG_PROOF_CHANGED')
        self.ui.record('actual-pm-no-replace-proof',proof)
        absent(self.s)
        build_raw=BUILD.read_bytes();need(sha(build_raw)==BUILD_SHA,'BUILD_RECEIPT_CHANGED')
        build=json.loads(build_raw)
        need(build['state']=='BUILT_SIGNED_VERIFIED_UNINSTALLED' and build['apk']['sha256']==APK_SHA
            and build['signer_certificate_sha256']==CERT_SHA and build['permissions']==[] and build['launcher'] is False,
            'APK_PROVENANCE_NOT_VERIFIED')
        data=self.tx.read_regular(APK,APK_SHA,1048576);need(len(data)==16588,'APK_SIZE_CHANGED')
        parent=self.s.target.open_root('/data/local/tmp',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        name='pocket4-owned-saf-'+RUN;guest='/data/local/tmp/'+name+'/owned-saf.apk'
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
        fd=os.open('owned-saf.apk',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o644,dir_fd=directory)
        with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno());os.fchmod(out.fileno(),0o644)
        self.staged['file_identity']=fp(os.stat('owned-saf.apk',dir_fd=directory,follow_symlinks=False))
        staged,_=self.s.target.read_file(guest,1048576,single_link=True);need(sha(staged)==APK_SHA,'STAGED_APK_CHANGED')
        absent(self.s);self.s.guard()
        argv=['/system/bin/pm','install','-R','-t','--user','0',guest]
        self.ui.record('create-only-install-intent',{'argv':argv,'replace_flag':False,'disallow_replacement_flag':'-R','pm_help_proof_sha256':PM_HELP_SHA,'apk_sha256':APK_SHA,
            'signer_sha256':CERT_SHA,'preinstall_absent_all_users':True,'automatic_retry':False})
        self.install_pending=True
        raw=self.s.android(argv,60).decode();need(raw.strip()=='Success','INSTALL_RESPONSE_NOT_SUCCESS')
        self.installed=identity(self.s,PACKAGE,APK_SHA)
        need(10000<=self.installed['uid']<20000,'NEW_APPLICATION_UID_OUT_OF_RANGE')
        self.install_pending=False;self.ui.record('new-package-installed',self.installed)
        self.result['installed_identity']=self.installed

    def packages(self,label):
        values={DOCS:identity(self.s,DOCS,'757feffc32440dd371eaab4fb91f45273a621ee45b848e2dc734b386ac6e2086',10022,37),
            'com.android.externalstorage':identity(self.s,'com.android.externalstorage',
                '50d1e6f2be950e049cdc898dd812c8e609f421cc167013d4ee2c795dcdc0e5ea',10024,37)}
        self.ui.record(label,values);return values

    def pref_state(self):
        path='/data/user/0/'+PACKAGE+'/shared_prefs/owned-saf-'+RUN+'.xml'
        try:raw,_=self.s.target.read_file(path,16384,single_link=True)
        except FileNotFoundError:return None
        root=ET.fromstring(raw);need(root.tag=='map','OWNED_PREFS_SCHEMA')
        result={}
        for item in root:
            name=item.get('name');need(name and name not in result,'DUPLICATE_OWNED_PREF_KEY')
            if item.tag=='string':result[name]=item.text or ''
            elif item.tag in ('int','long'):result[name]=int(item.get('value'))
            else:raise RuntimeError('UNKNOWN_OWNED_PREF_TYPE')
        need(result.get('run')==RUN,'OWNED_PREF_RUN_CHANGED')
        self.ui.record('owned-client-phase-readonly',{'phase':result.get('phase'),'pending':result.get('pending',''),
            'sha256':sha(raw),'content_writes':result.get('content_writes',0),'uri':result.get('uri','')})
        return result

    def status_ui(self,phase):
        obs=self.ui.observe('client-'+phase,[CLIENT_ROUTE])
        node=self.ui.one(obs,lambda n:n.get('resource-id')==PACKAGE+':id/status','ONE_CLIENT_STATUS_REQUIRED')
        value=json.loads(node.get('text',''))
        need(value.get('run')==RUN and value.get('phase')==phase and value.get('pending')==''
            and value.get('error')=='','EXPECTED_CLIENT_BUSINESS_PHASE_MISSING:'+phase)
        if phase!='NEW':need(value.get('sha256')==PAYLOAD_SHA and value.get('bytes')==87,'APP_READBACK_HASH_MISSING')
        self.status=value;self.result['gates'][phase]={'passed':True,'client_status':value}
        return obs

    def client_button(self,obs,suffix,label,transition=None):
        node=self.ui.one(obs,lambda n:n.get('resource-id')==PACKAGE+':id/'+suffix
            and n.get('enabled') is True and n.get('clickable') is True,'ONE_CLIENT_BUTTON_REQUIRED')
        self.ui.input(obs,label,node,transition=transition)

    def own_location(self,obs):
        need(any(n.get('text')==FOLDER or n.get('content-desc')==FOLDER for n in obs['nodes']),
            'ACTUAL_PICKER_OR_FILES_OWNED_FOLDER_NOT_VISIBLE')
        self.folder.check()

    def control(self,obs,text):
        return self.ui.one(obs,lambda n:n.get('enabled') is True and n.get('editable') is False
            and n.get('class') in ('android.widget.TextView','android.widget.Button',
                'android.widget.ImageButton','android.widget.CheckedTextView')
            and (str(n.get('text','')).strip().casefold()==text.casefold()
                or str(n.get('content-desc','')).strip().casefold()==text.casefold()),'ONE_VISIBLE_CONTROL_REQUIRED:'+text)

    def row(self,obs,name,longpress=False):
        label=self.ui.one(obs,lambda n:n.get('text')==name and n.get('editable') is False,'ONE_EXACT_OWNED_FILENAME_REQUIRED')
        box=label.get('bounds_array');need(isinstance(box,list) and len(box)==4,'FILENAME_BOUNDS')
        def contains(outer,inner):return (isinstance(outer,list) and len(outer)==4 and all(type(v) is int for v in outer)
            and outer[0]<=inner[0]<inner[2]<=outer[2] and outer[1]<=inner[1]<inner[3]<=outer[3])
        candidates=[n for n in obs['nodes'] if n.get('enabled') is True and n.get('window_id')==label.get('window_id')
            and contains(n.get('bounds_array'),box) and (32 in n.get('supported_actions',[]) if longpress else
                (n.get('clickable') is True and 16 in n.get('supported_actions',[])))]
        need(candidates,'OBSERVED_FILE_ROW_CAPABILITY_MISSING')
        smallest=[n for n in candidates if not any(x is not n and x['bounds_array']!=n['bounds_array']
            and contains(n['bounds_array'],x['bounds_array']) for x in candidates)]
        need(len(smallest)==1,'INNermost_FILE_ROW_NOT_UNIQUE')
        return smallest[0]

    def grants(self,label,expect_empty=False):
        raw=self.s.android(['/system/bin/dumpsys','activity','package',PACKAGE,'permissions']).decode()
        lines=[line.strip() for line in raw.splitlines() if line.strip()]
        need(lines and lines[0]=='ACTIVITY MANAGER URI PERMISSIONS (dumpsys activity permissions)',
            'URI_GRANT_DUMP_GRAMMAR_UNRECOGNIZED')
        empty=lines==['ACTIVITY MANAGER URI PERMISSIONS (dumpsys activity permissions)','(nothing)']
        if expect_empty:need(empty,'OWNED_URI_GRANTS_NOT_EMPTY')
        self.ui.record(label,{'raw':raw,'package_filter':PACKAGE,'empty':empty});return empty

    def business(self):
        before=self.packages('target-identities-before');self.install();self.folder.setup()
        self.grants('new-package-grants-empty',True)
        self.ui.launch();obs=self.status_ui('NEW')
        self.client_button(obs,'create_document','create-picker')
        obs=self.ui.observe('create-picker',[PICKER_ROUTE]);self.own_location(obs)
        self.ui.one(obs,lambda n:n.get('editable') is True and n.get('text')==CREATED,'EXACT_CREATE_FILENAME_REQUIRED')
        need(self.folder.check()==[],'OWNED_FOLDER_NOT_EMPTY_BEFORE_PICKER_SAVE')
        self.ui.input(obs,'picker-save',self.control(obs,'Save'))
        obs=self.status_ui('CREATE_WRITE_READ_OK');self.folder.verify(CREATED,'created-file-readback')
        self.grants('created-document-persisted-grants')
        self.client_button(obs,'provider_rename','provider-rename')
        obs=self.status_ui('PROVIDER_RENAME_OK');self.folder.verify(PROVIDER,'provider-rename-readback')
        self.client_button(obs,'open_files','open-files',FILES_ROUTE)
        obs=self.ui.observe('files-owned-folder',[FILES_ROUTE],admit=True);self.own_location(obs)
        row=self.row(obs,PROVIDER,True);self.ui.input(obs,'select-owned-file',row,kind='long-press')
        obs=self.ui.observe('files-selected',[FILES_ROUTE])
        self.ui.one(obs,lambda n:n.get('text')==PROVIDER,'SELECTED_OWNED_FILENAME_MISSING')
        direct=[n for n in obs['nodes'] if n.get('enabled') is True and n.get('clickable') is True
            and (n.get('text')=='Rename' or n.get('content-desc')=='Rename')]
        if not direct:
            self.ui.input(obs,'files-more',self.control(obs,'More options'),popup=True)
            obs=self.ui.observe('files-owned-menu',[FILES_ROUTE])
        self.ui.input(obs,'files-rename-menu',self.control(obs,'Rename'))
        obs=self.ui.observe('files-rename-dialog',[FILES_ROUTE])
        field=self.ui.one(obs,lambda n:n.get('editable') is True and n.get('text')==PROVIDER,'EXACT_RENAME_INPUT_REQUIRED')
        self.ui.input(obs,'files-rename-text',field,'set-text',FILES)
        obs=self.ui.observe('files-rename-text-readback',[FILES_ROUTE])
        self.ui.one(obs,lambda n:n.get('editable') is True and n.get('text')==FILES,'UI_RENAME_TEXT_READBACK')
        positive=self.ui.one(obs,lambda n:n.get('enabled') is True and n.get('class')=='android.widget.Button'
            and n.get('resource-id')=='android:id/button1' and str(n.get('text','')).casefold() in ('ok','rename'),
            'ONE_ACTUAL_RENAME_DIALOG_POSITIVE_BUTTON_REQUIRED')
        self.ui.input(obs,'files-rename-confirm',positive)
        obs=self.ui.observe('files-renamed',[FILES_ROUTE]);self.own_location(obs)
        self.folder.verify(FILES,'actual-files-ui-rename-readback')
        self.result['gates']['FILES_UI_RENAME']={'passed':True,'old_name_absent':True,'new_name':FILES,'sha256':PAYLOAD_SHA}
        self.ui.input(obs,'files-open-owned-file',self.row(obs,FILES),transition=RESOLVER_ROUTE)
        obs=self.ui.observe('files-open-result',[CLIENT_ROUTE,RESOLVER_ROUTE],admit=True)
        if obs['focus']['package']=='android':
            self.ui.input(obs,'resolver-owned-client',self.control(obs,'Pocket4 Owned SAF 69814e80'))
            obs=self.ui.observe('resolver-owned-client-selected',[RESOLVER_ROUTE])
            self.ui.input(obs,'resolver-just-once',self.control(obs,'Just once'))
        obs=self.status_ui('FILES_VIEW_OK')
        self.client_button(obs,'open_document','open-picker')
        obs=self.ui.observe('open-picker',[PICKER_ROUTE]);self.own_location(obs)
        self.ui.input(obs,'picker-select-owned-document',self.row(obs,FILES))
        self.status_ui('OPEN_OK');self.ui.close_all();self.ui.launch()
        obs=self.status_ui('REOPEN_OK');self.folder.verify(FILES,'reopen-file-persistence')
        self.client_button(obs,'provider_delete','provider-delete')
        self.status_ui('DELETE_PROVIDER_ACK');self.folder.absence('provider-delete-true-absence')
        self.grants('provider-delete-grants-empty',True)
        self.result['gates']['PROVIDER_DELETE_AND_ABSENCE']={'passed':True,'all_exact_paths_errno_ENOENT':True,'grants_empty':True}
        self.ui.close_all();need(self.packages('target-identities-after')==before,'TARGET_PACKAGE_IDENTITIES_CHANGED')
        need(identity(self.s,PACKAGE,APK_SHA)==self.installed,'TEMPORARY_APP_IDENTITY_CHANGED')
        need(self.ui.launches==2 and not self.ui.pending,'CLIENT_LIFECYCLE_OR_PENDING_EFFECTS_INCOMPLETE')
        self.result.update(state='SCOPED_SAF_AND_FILES_BUSINESS_COMPLETED',business_flow_completed=True)

    def cleanup(self):
        cleanup={'errors':[],'package_uninstalled_verified':False,'package_absent_verified':False,
            'file_cleanup':None,'staged_apk_removed':False}
        if self.result.get('staging_setup_incomplete'):
            cleanup['errors'].append('staged directory setup incomplete; preserve for read-only reconciliation')
        try:self.ui.close_all()
        except BaseException as exc:cleanup['errors'].append('owned_tasks:'+type(exc).__name__+':'+str(exc))
        try:
            if self.installed is not None and not self.install_pending and not self.uninstall_pending:
                need(not self.ui.pending,'UI_OUTCOME_PENDING_PRESERVE_OWNED_FIXTURE_AND_PACKAGE')
                phase=self.pref_state()
                allow_file=phase is None or phase.get('pending','') in ('','FILES_REQUESTED')
                need(allow_file,'CLIENT_PROVIDER_EFFECT_PENDING_PRESERVE_FOR_RECONCILIATION')
                if self.folder.created:cleanup['file_cleanup']=self.folder.cleanup(allow_file)
                need(not self.ui.owned and not any(k.startswith(('launch-','close-')) for k in self.ui.pending),
                    'OWNED_TASK_LIFECYCLE_UNCERTAIN_KEEP_PACKAGE')
                need(identity(self.s,PACKAGE,APK_SHA)==self.installed,'TEMPORARY_PACKAGE_CHANGED_BEFORE_UNINSTALL')
                self.ui.record('exact-new-package-uninstall-intent',{'package':PACKAGE,'identity':self.installed,
                    'preinstall_absent_all_users':True,'automatic_retry':False})
                self.uninstall_pending=True
                raw=self.s.android(['/system/bin/pm','uninstall',PACKAGE],60).decode()
                need(raw.strip()=='Success','UNINSTALL_RESPONSE_UNKNOWN')
                absent(self.s);self.uninstall_pending=False
                cleanup['package_uninstalled_verified']=cleanup['package_absent_verified']=True
            elif self.install_pending:raise RuntimeError('INSTALL_UNKNOWN_PRESERVE_FOR_READ_ONLY_RECONCILIATION')
            else:
                absent(self.s);cleanup['package_absent_verified']=True
        except BaseException as exc:cleanup['errors'].append('fixture_or_package:'+type(exc).__name__+':'+str(exc))
        try:
            if self.staged is not None:
                stage=self.staged
                if self.install_pending:
                    cleanup['staged_apk_retained_for_unknown_install']=stage['guest']
                    self.ui.record('unknown-install-input-preserved',{'guest_path':stage['guest'],
                        'expected_sha256':APK_SHA,'reconciliation_required':True,'automatic_retry':False})
                else:
                    need(fp(os.stat(stage['name'],dir_fd=stage['parent'],follow_symlinks=False))==stage['birth']
                        and fp(os.fstat(stage['directory']))==stage['birth'],'STAGE_DIRECTORY_CHANGED')
                    info=os.stat('owned-saf.apk',dir_fd=stage['directory'],follow_symlinks=False)
                    need(fp(info)==stage['file_identity'] and os.listdir(stage['directory'])==['owned-saf.apk'],
                        'STAGED_APK_SCOPE_CHANGED')
                    data,_=self.s.target.read_file(stage['guest'],1048576,single_link=True);need(sha(data)==APK_SHA,'STAGED_APK_CHANGED')
                    os.unlink('owned-saf.apk',dir_fd=stage['directory']);os.rmdir(stage['name'],dir_fd=stage['parent'])
                    cleanup['staged_apk_removed']=True
        except BaseException as exc:cleanup['errors'].append('stage:'+type(exc).__name__+':'+str(exc))
        finally:
            if self.staged is not None:
                os.close(self.staged['directory']);os.close(self.staged['parent'])
            self.folder.close()
        return cleanup


def expired(signum,frame):raise TimeoutError('DOCUMENTS_SESSION_DEADLINE_NO_REPLAY')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    if not args.execute:
        print(json.dumps({'state':'PLAN_ONLY','package':PACKAGE,'apk_sha256':APK_SHA,'max_seconds':MAX_SECONDS,
            'max_ui_actions':36,'permissions':[],'launcher':False,'ui_actions':0,'installs':0}));return 0
    tx=load(SOURCE,SOURCE_SHA,'saf_frozen_session');adapter=load(ADAPTER,ADAPTER_SHA,'saf_ui_adapter')
    result={'state':'NOT_STARTED','business_flow_completed':False,'whole_app_production_ready':False}
    with tx.ui_lock():
        ROOT.mkdir(mode=0o700);started=time.monotonic();old=signal.signal(signal.SIGALRM,expired)
        signal.setitimer(signal.ITIMER_REAL,MAX_SECONDS-CLEANUP_RESERVE)
        try:
            with tx.CameraSession(ROOT/'commands') as session:
                flow=Flow(session,tx,adapter)
                try:flow.business()
                except BaseException as exc:flow.result.update(state='DOCUMENTS_FLOW_STOPPED',business_flow_completed=False,
                    error=type(exc).__name__+': '+str(exc))
                finally:
                    signal.setitimer(signal.ITIMER_REAL,max(.001,min(CLEANUP_RESERVE,MAX_SECONDS-(time.monotonic()-started))))
                    cleanup=flow.cleanup();flow.result['cleanup']=cleanup
                    if cleanup['errors'] or not cleanup['package_absent_verified']:
                        flow.result.update(state='OWNED_CLEANUP_UNVERIFIED',business_flow_completed=False)
                    flow.result.update(ui_actions=flow.ui.actions,native_launch_calls=flow.ui.launches,
                        owned_remove_calls=flow.ui.removals,owned_task_ids_closed=flow.ui.closed,
                        source_bound_adopted_tasks=flow.ui.adopted,pending_effects=flow.ui.pending,
                        install_pending=flow.install_pending,uninstall_pending=flow.uninstall_pending,
                        outcome_unknown=bool(flow.ui.pending or flow.install_pending or flow.uninstall_pending),
                        elapsed_seconds=time.monotonic()-started,framework_epoch_sha256=session.epoch_sha256,
                        final_guard=session.guard())
                    result=flow.result;session.caller_status('documents-final-caller')
        except BaseException as exc:result.update(state='DOCUMENTS_FLOW_STOPPED',business_flow_completed=False,
            outer_error=type(exc).__name__+': '+str(exc))
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
            tx.write_new(ROOT/'result.json',result)
    print(json.dumps(result,indent=2,sort_keys=True));return 0 if result.get('business_flow_completed') is True else 1


if __name__=='__main__':raise SystemExit(main())
