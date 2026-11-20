"""Two exact generated image namespaces; no original media file bytes are read."""
import hashlib,io,json,os,re,stat
from PIL import Image

RUN='d24b61ed8f7c9a03';PACKAGE='org.droidloom.qa.galleryrotation.r12.n'+RUN
DB='/data/user/0/com.android.providers.media.module/databases/external.db'
FOLDERS={'control':'Pocket4_Rotate_Control_r12_'+RUN,'copy':'Pocket4_Rotate_Copy_r12_'+RUN}
NAMES={'control':'pocket4-control-'+RUN+'.png','copy':'pocket4-copy-'+RUN+'.jpg'}
MIMES={'control':'image/png','copy':'image/jpeg'}
PNG_SHA='c27368348393b4063097c6ab18993dfc91e5c71e7fd1ac6978c191e1740fc7db'
FIELDS='_id,_data,_display_name,relative_path,owner_package_name,media_type,mime_type,_size,width,height,is_pending,orientation,bucket_id,bucket_display_name,parent'
PROVIDER_APK='/apex/com.android.mediaprovider/priv-app/MediaProvider@CP3A.260905.010/MediaProvider.apk'
PROVIDER_BYTES=13826854
PROVIDER_SHA='aff897cc1f56583cd71c4cf48330eb4514fdefbd54f069e55223bd31e7af305b'

def need(value,why):
    if not value:raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def birth(s):return {k:getattr(s,k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode')}
def q(value):
    need(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_./-]+',value),'FIXED_SQL_LITERAL_REQUIRED')
    return "'"+value+"'"
def folder(role):return '/storage/emulated/0/DCIM/'+FOLDERS[role]
def relative(role):return 'DCIM/'+FOLDERS[role]+'/'
def exact_row_predicate(row):
    need(set(row)==set(FIELDS.split(',')),'FULL_DIRECTORY_TUPLE_REQUIRED')
    parts=[]
    for key in FIELDS.split(','):
        value=row[key]
        if value is None:parts.append(key+' IS NULL')
        elif type(value) is int:parts.append(key+'='+str(value))
        else:parts.append(key+'='+q(value))
    return ' AND '.join(parts)

class OwnedMedia:
    def __init__(self,session,record):
        self.s,self.record=session,record;self.parent=None;self.parent_birth=None;self.held={};self.folder_birth={}
        self.before=None;self.media=None;self.baseline=None;self.rotated=None;self.directory_rows={}
        self.directory_pending=None;self.directory_delete_calls=0
        self.backing_parent=None;self.backing_parent_birth=None
        self.backing_held={};self.backing_folder_birth={};self.directory_rmdir_calls=0

    def query(self,label,sql):
        need(sql.startswith('SELECT ') and not re.search(r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH)\b',sql,re.I),
            'READ_ONLY_SQL_REQUIRED')
        command=['/system/bin/env','-i']+[k+'='+self.s.environment[k] for k in sorted(self.s.environment)]
        command+=['/system/bin/timeout','-k','2','10','/system/bin/sqlite3','-readonly','-json',DB,
            'PRAGMA query_only=ON;BEGIN;'+sql+';ROLLBACK;']
        result=self.s.root_query(label,command,14)
        need(result['rc']==0 and result['joined'] and not result['timed_out'],'GLOBAL_MEDIA_READ_FAILED')
        need(len(result['stdout'])<=262144,'GLOBAL_MEDIA_METADATA_BOUND')
        rows=json.loads(result['stdout']) if result['stdout'].strip() else []
        need(isinstance(rows,list),'GLOBAL_MEDIA_ROW_LIST_REQUIRED')
        self.record(label,{'rows':rows,'read_only':True});return rows

    def namespace(self,label):
        clauses=['owner_package_name='+q(PACKAGE)]
        for role in FOLDERS:
            clauses+=['relative_path='+q(relative(role)),
                '_data IN ('+q(folder(role))+','+q(folder(role)+'/'+NAMES[role])+')',
                '_display_name IN ('+q(FOLDERS[role])+','+q(NAMES[role])+')']
        return self.query(label,'SELECT '+FIELDS+' FROM files WHERE '+' OR '.join(clauses)+' ORDER BY _id')

    def original(self,label):
        rows=self.query(label,'SELECT _id,media_type,mime_type,_size,width,height,is_pending,orientation,date_modified '
            'FROM files WHERE media_type IN (1,3) AND (owner_package_name IS NULL OR owner_package_name!='+
            q(PACKAGE)+') ORDER BY _id')
        return {'rows':len(rows),'sha256':sha(json.dumps(rows,sort_keys=True,separators=(',',':')).encode())}

    def setup(self):
        self.s.guard();self.before=self.original('original-media-before')
        need(self.namespace('new-media-namespace-before')==[],'GLOBAL_OWNED_MEDIA_NAMESPACE_PRESENT')
        self.parent=self.s.target.open_root('/storage/emulated/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        self.parent_birth=birth(os.fstat(self.parent))
        self.backing_parent=self.s.target.open_root('/data/media/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        self.backing_parent_birth=birth(os.fstat(self.backing_parent))
        for role,name in FOLDERS.items():
            for parent in (self.parent,self.backing_parent):
                try:os.stat(name,dir_fd=parent,follow_symlinks=False)
                except FileNotFoundError:continue
                raise RuntimeError('PREEXISTING_MEDIA_DIRECTORY_PRESERVED:'+role)
        self.record('two-exclusive-media-directories-absent',{'roles':FOLDERS,'App_creation_credit':False})

    def guard_parent(self):
        self.s.guard()
        need(self.parent is not None and self.parent_birth is not None,'ORIGINAL_DCIM_PARENT_NOT_BOUND')
        fresh=self.s.target.open_root('/storage/emulated/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            need(birth(os.fstat(fresh))==birth(os.fstat(self.parent))==self.parent_birth,
                'DCIM_PARENT_OR_STORAGE_MOUNT_CHANGED')
        finally:os.close(fresh)
        need(self.backing_parent is not None and self.backing_parent_birth is not None,
            'ORIGINAL_BACKING_PARENT_NOT_BOUND')
        fresh=self.s.target.open_root('/data/media/0/DCIM',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            need(birth(os.fstat(fresh))==birth(os.fstat(self.backing_parent))==self.backing_parent_birth,
                'BACKING_PARENT_OR_STORAGE_MOUNT_CHANGED')
        finally:os.close(fresh)

    def names(self,role):
        self.guard_parent()
        if role not in self.held:
            fd=os.open(FOLDERS[role],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.parent)
            self.held[role]=fd;self.folder_birth[role]=birth(os.fstat(fd))
        fd=self.held[role];expected=self.folder_birth[role]
        need(birth(os.fstat(fd))==birth(os.stat(FOLDERS[role],dir_fd=self.parent,follow_symlinks=False))==expected,
            'OWNED_MEDIA_DIRECTORY_REPLACED')
        fresh=os.open('.',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
        try:
            need(birth(os.fstat(fresh))==expected,'FRESH_DIRECTORY_DESCRIPTION_CHANGED');names=sorted(os.listdir(fresh))
        finally:os.close(fresh)
        need(set(names)<={NAMES[role]},'UNOWNED_FILE_IN_MEDIA_DIRECTORY')
        if role not in self.backing_held:
            back=os.open(FOLDERS[role],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                dir_fd=self.backing_parent)
            self.backing_held[role]=back;self.backing_folder_birth[role]=birth(os.fstat(back))
        back=self.backing_held[role];expected_back=self.backing_folder_birth[role]
        need(birth(os.fstat(back))==birth(os.stat(FOLDERS[role],dir_fd=self.backing_parent,
            follow_symlinks=False))==expected_back,'OWNED_BACKING_DIRECTORY_REPLACED')
        fresh=os.open('.',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=back)
        try:
            need(birth(os.fstat(fresh))==expected_back,'FRESH_BACKING_DESCRIPTION_CHANGED')
            need(sorted(os.listdir(fresh))==names,'OWNED_DIRECTORY_VIEWS_DISAGREE')
        finally:os.close(fresh)
        return names

    def removed_directory(self,role):
        self.guard_parent()
        need(role in self.held and role in self.backing_held,'ORIGINAL_DIRECTORY_FDS_NOT_BOUND')
        # Deleted FUSE descriptors can return ENOENT on fstat. The independently
        # held backing inode remains the unlink proof; both named views must be absent.
        back=os.fstat(self.backing_held[role])
        need(birth(back)==self.backing_folder_birth[role] and back.st_nlink==0,
            'ORIGINAL_BACKING_DIRECTORY_NOT_UNLINKED')
        for parent in (self.parent,self.backing_parent):
            try:os.stat(FOLDERS[role],dir_fd=parent,follow_symlinks=False)
            except FileNotFoundError:continue
            raise RuntimeError('OWNED_DIRECTORY_PATH_REAPPEARED')
        return {'role':role,'fuse_birth':self.folder_birth[role],
            'backing_birth':self.backing_folder_birth[role],'backing_nlink':0,
            'both_named_views_absent':True}

    def empty_after_delete(self,role):
        self.guard_parent()
        try:current=os.stat(FOLDERS[role],dir_fd=self.parent,follow_symlinks=False)
        except FileNotFoundError:
            self.record('provider-already-removed-owned-directory',self.removed_directory(role))
            return True
        need(birth(current)==self.folder_birth.get(role),'OWNED_DIRECTORY_CHANGED_AFTER_IMAGE_DELETE')
        need(self.names(role)==[],'OWNED_IMAGE_PHYSICAL_FILE_NOT_ABSENT')
        return False

    def file(self,role):
        need(self.names(role)==[NAMES[role]],'ONE_OWNED_IMAGE_FILE_REQUIRED')
        fd=os.open(NAMES[role],os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.held[role])
        try:
            before=os.fstat(fd);need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and
                0<before.st_size<=2*1024*1024,'OWNED_IMAGE_FILE_BOUND')
            chunks=[];left=before.st_size
            while left:
                raw=os.read(fd,min(left,65536));need(raw,'SHORT_OWNED_IMAGE_READ');chunks.append(raw);left-=len(raw)
            raw=b''.join(chunks);after=os.fstat(fd)
            need(birth(before)==birth(after) and before.st_size==after.st_size and before.st_nlink==after.st_nlink
                and before.st_mtime_ns==after.st_mtime_ns and before.st_ctime_ns==after.st_ctime_ns,
                'OWNED_IMAGE_CHANGED_DURING_READ')
            back=os.open(NAMES[role],os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=self.backing_held[role])
            try:
                bb=os.fstat(back)
                need(stat.S_ISREG(bb.st_mode) and bb.st_nlink==1 and bb.st_size==len(raw),
                    'OWNED_BACKING_IMAGE_BOUND')
                parts=[];left=bb.st_size
                while left:
                    chunk=os.read(back,min(left,65536));need(chunk,'SHORT_BACKING_IMAGE_READ')
                    parts.append(chunk);left-=len(chunk)
                ba=os.fstat(back)
                need(birth(bb)==birth(ba) and bb.st_size==ba.st_size and bb.st_nlink==ba.st_nlink
                    and bb.st_mtime_ns==ba.st_mtime_ns and bb.st_ctime_ns==ba.st_ctime_ns
                    and b''.join(parts)==raw,'FUSE_AND_BACKING_IMAGE_BYTES_DISAGREE')
            finally:os.close(back)
            with Image.open(io.BytesIO(raw)) as image:
                need(image.format==('PNG' if role=='control' else 'JPEG') and image.size==(640,480),
                    'RAW_IMAGE_ENCODING_OR_DIMENSIONS_CHANGED')
                exif=int(image.getexif().get(274,0));pixels=sha(image.convert('RGB').tobytes())
            return {'bytes':len(raw),'sha256':sha(raw),'birth':birth(before),'nlink':before.st_nlink,
                'backing_birth':birth(bb),'backing_bytes_identical':True,
                'mtime_ns':str(before.st_mtime_ns),'ctime_ns':str(before.st_ctime_ns),
                'raw_RGB_sha256':pixels,'exif_orientation':exif}
        finally:os.close(fd)

    def verify(self,label,rotated,admit_rotation=False):
        need(self.media is not None,'SEEDED_MEDIA_RECEIPT_REQUIRED');self.s.guard()
        rows=self.namespace(label+'-namespace');proof={};expected_ids=set();used=set()
        for role in ('control','copy'):
            seed=self.media[role];match=re.fullmatch(r'content://media/external_primary/images/media/([1-9][0-9]*)',seed['uri'])
            need(match,'EXACT_OWNED_IMAGE_URI_REQUIRED');identity=int(match[1]);expected_ids.add(identity)
            images=[r for r in rows if r['_id']==identity];need(len(images)==1,'ONE_GLOBAL_OWNED_IMAGE_ROW')
            row=images[0];used.add(identity);file=self.file(role)
            need(row['_data']==folder(role)+'/'+NAMES[role] and row['_display_name']==NAMES[role]
                and row['relative_path']==relative(role) and row['owner_package_name']==PACKAGE
                and row['media_type']==1 and row['mime_type']==MIMES[role] and row['is_pending']==0
                and row['_size']==file['bytes'] and row['width']==640 and row['height']==480
                and row['bucket_display_name']==FOLDERS[role]
                and row['bucket_id']==seed['metadata']['bucket_id'],'EXACT_OWNED_IMAGE_METADATA_REQUIRED')
            bucket=int(row['bucket_id']);need(-(2**31)<=bucket<2**31,'INTEGER_BUCKET_REQUIRED')
            members=self.query(label+'-'+role+'-sole-bucket','SELECT _id FROM files WHERE media_type=1 AND bucket_id='+str(bucket)+' ORDER BY _id')
            need(members==[{'_id':identity}],'GLOBAL_BUCKET_HAS_OTHER_IMAGE')
            directories=[r for r in rows if r['_data']==folder(role)]
            need(len(directories)<=1,'OWNED_DIRECTORY_INDEX_AMBIGUOUS')
            if directories:
                directory=directories[0];used.add(directory['_id'])
                need(directory['_id']>0 and directory['_display_name']==FOLDERS[role]
                    and directory['relative_path']=='DCIM/' and directory['media_type']==0
                    and directory['is_pending']==0 and directory['owner_package_name'] is None,
                    'EXACT_OWNER_NULL_DIRECTORY_ROW_REQUIRED')
                if role in self.directory_rows:need(directory==self.directory_rows[role],'OWNED_DIRECTORY_INDEX_CHANGED')
                else:self.directory_rows[role]=directory
            proof[role]={'file':file,'metadata':row,'folder_birth':self.folder_birth[role]}
            if role=='control':
                need(file['sha256']==PNG_SHA and file['bytes']==2416,'ORIGINAL_PNG_CONTROL_BYTES_CHANGED')
                if self.baseline:need(proof[role]==self.baseline[role],'IMMUTABLE_PNG_CONTROL_CHANGED')
            elif rotated:
                need(self.baseline is not None and file['exif_orientation']==6 and row['orientation']==90
                    and file['raw_RGB_sha256']==self.baseline[role]['file']['raw_RGB_sha256'],
                    'JPEG_EXIF_INDEX_AND_RAW_PIXELS_MUST_AGREE')
                if self.rotated:need(proof[role]==self.rotated[role],'ROTATED_COPY_CHANGED_AFTER_CONFIRMATION')
                else:need(admit_rotation is True,'ROTATION_ADMISSION_REQUIRES_SINGLE_RECORDED_UI_EFFECT')
            else:
                need(file['sha256']==seed['sha256'] and file['bytes']==seed['bytes']
                    and file['exif_orientation']==seed['exif_orientation'] and row['orientation'] in (None,0),
                    'ORIGINAL_JPEG_CHANGED_WITHOUT_ROTATION')
                if self.baseline:need(proof[role]==self.baseline[role],'ORIGINAL_COPY_IDENTITY_CHANGED')
        need(len(rows)==len(used) and len(expected_ids)==2,'EXTRA_OWNED_NAMESPACE_ROW')
        need(proof['copy']['metadata']['bucket_id']!=proof['control']['metadata']['bucket_id'],'OWNED_BUCKET_COLLISION')
        need(self.original(label+'-original-media')==self.before,'PREEXISTING_MEDIA_METADATA_CHANGED')
        self.s.guard();self.record(label,{'media':proof,'source_or_UI_effect_not_inferred_from_ACK':True})
        if self.baseline is None:self.baseline=proof
        if rotated and self.rotated is None:self.rotated=proof
        return proof

    def provider_pin(self,label):
        raw,_=self.s.target.read_file(PROVIDER_APK,16777216,single_link=True)
        need(len(raw)==PROVIDER_BYTES and sha(raw)==PROVIDER_SHA,'REVIEWED_MEDIAPROVIDER_CHANGED')
        proof={'bytes':len(raw),'sha256':sha(raw)};self.record(label,proof);return proof

    def no_child_index(self,role,row):
        need(self.query('directory-'+role+'-children','SELECT _id FROM files WHERE parent='+str(row['_id'])+
            ' OR _data GLOB ('+q(folder(role))+"||'/*') ORDER BY _id")==[],
            'OWNED_DIRECTORY_HAS_CHILD_INDEX')

    def cleanup_directories(self):
        need(self.directory_pending is None and self.media is not None,'DIRECTORY_EFFECT_PENDING_NO_REPLAY')
        provider=self.provider_pin('reviewed-provider-before-directory-cleanup')
        for role in ('copy','control'):
            self.empty_after_delete(role)
        rows=self.namespace('after-owned-image-delete')
        need(all(r in self.directory_rows.values() for r in rows),'UNEXPECTED_ROW_AFTER_IMAGE_DELETE')
        for role in ('copy','control'):
            row=self.directory_rows.get(role)
            if row in rows:self.no_child_index(role,row)
            removed=self.empty_after_delete(role)
            if not removed:
                need(self.namespace('before-'+role+'-rmdir')==rows,'DIRECTORY_TUPLE_CHANGED_BEFORE_RMDIR')
                need(self.names(role)==[],'OWNED_DIRECTORY_NOT_EMPTY')
                self.guard_parent();self.directory_pending='rmdir-'+role
                self.record('exact-owned-empty-rmdir-intent',{'role':role,
                    'birth':self.folder_birth[role],'backing_birth':self.backing_folder_birth[role],
                    'automatic_retry':False})
                self.directory_rmdir_calls+=1
                os.rmdir(FOLDERS[role],dir_fd=self.parent)
                self.record('exact-owned-empty-rmdir-readback',self.removed_directory(role))
                self.directory_pending=None
            after=self.namespace('directory-'+role+'-after-rmdir')
            need(after in (rows,[entry for entry in rows if entry!=row]),'NAMESPACE_CHANGED_AFTER_RMDIR')
            rows=after
            if row in rows:
                identity=row['_id'];predicate=exact_row_predicate(row)
                query=['/system/bin/content','query','--user','0','--uri',
                    'content://media/external_primary/file/'+str(identity),'--projection','_id','--where',predicate]
                raw=self.s.android(query,25).decode();self.record('exact-empty-directory-query',{'row':row,'stdout':raw})
                need(re.fullmatch(r'Row: 0 _id='+str(identity)+r'\s*',raw),'EXACT_DIRECTORY_PROVIDER_QUERY_REQUIRED')
                self.removed_directory(role)
                need(self.namespace('immediate-directory-'+role+'-tuple')==rows,'DIRECTORY_INDEX_TUPLE_CHANGED')
                self.no_child_index(role,row)
                self.s.guard()
                argv=['/system/bin/content','delete','--user','0','--uri','content://media/external_primary/file/'+str(identity),'--where',predicate]
                self.directory_pending='delete-'+role;self.record('exact-empty-directory-delete-intent',
                    {'argv':argv,'row':row,'birth':self.folder_birth[role],
                    'backing_birth':self.backing_folder_birth[role],'physical_directory_already_absent':True,
                    'automatic_retry':False,'App_UI_delete_credit':False,'cross_row_SQL_atomicity_claimed':False})
                self.directory_delete_calls+=1;raw=self.s.android(argv,25).decode()
                self.record('exact-empty-directory-delete-response',{'stdout':raw})
                need(raw.strip()=='' or re.fullmatch(r'Deleted 1 rows\.?',raw.strip()),'DIRECTORY_PROVIDER_RESPONSE_UNKNOWN')
                fresh=self.namespace('directory-'+role+'-after-delete')
                need(all(r['_id']!=identity for r in fresh) and fresh==[r for r in rows if r['_id']!=identity],
                    'EXACT_DIRECTORY_INDEX_ABSENCE_NOT_VERIFIED');rows=fresh;self.directory_pending=None
            self.removed_directory(role)
        need(self.namespace('final-owned-namespace')==[] and self.original('final-original-media')==self.before,
            'FINAL_NAMESPACE_OR_ORIGINAL_MEDIA_CHANGED')
        need(self.provider_pin('reviewed-provider-after-directory-cleanup')==provider,'PROVIDER_CHANGED_DURING_CLEANUP')
        return {'owned_image_rows_absent':True,'physical_owned_image_files_absent':True,
            'physical_and_indexed_owned_directories_absent':True,'original_media_preserved':True,
            'directory_provider_delete_calls':self.directory_delete_calls,
            'directory_rmdir_calls':self.directory_rmdir_calls,'UI_delete_credit':False,
            'cross_row_SQL_atomicity_claimed':False,'backing_unlink_and_both_path_views_verified':True}

    def close(self):
        for fd in self.held.values():os.close(fd)
        self.held={}
        if self.parent is not None:os.close(self.parent);self.parent=None
        for fd in self.backing_held.values():os.close(fd)
        self.backing_held={}
        if self.backing_parent is not None:os.close(self.backing_parent);self.backing_parent=None
