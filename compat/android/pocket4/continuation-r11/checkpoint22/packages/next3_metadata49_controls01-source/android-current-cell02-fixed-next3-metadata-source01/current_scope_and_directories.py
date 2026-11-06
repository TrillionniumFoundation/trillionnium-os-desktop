
def current_baseline_scope(reference, baseline):
    need(type(baseline) is dict and baseline.get('schema')=='pocket4-main-current-baseline-v2' and
         baseline.get('kind')=='current-cell-generation' and baseline.get('deployment_performed') is False and
         'main_deployed' not in baseline and baseline.get('framework_exit_cause_resolved') is False and
         baseline.get('whole_app_production_ready') is False and
         baseline['framework_epoch']['sha256']==reference.EPOCH==CURRENT_EPOCH and
         reference.BASELINE_SHA==BASELINE_SHA and reference.QUALIFICATION_SHA==QUALIFICATION_SHA,
         'EXACT_CURRENT_CELL02_BASELINE_REQUIRED')
    # This observation does not add PACKAGE to the immutable four-target baseline.
    return {'schema':'pocket4-fixed-new-target-metadata-scope-v1',
        'current_baseline_schema':baseline['schema'],'epoch_sha256':CURRENT_EPOCH,
        'current_baseline_sha256':BASELINE_SHA,'current_baseline_qualification_sha256':QUALIFICATION_SHA,
        'package':PACKAGE,'user':USER,'UID_version_APKs_and_data_directories_pending':True,
        'baseline_packages_modified':False,'Bili_scope_reused':False,'business_action_authority':False}


def discover_main(app, baseline, epoch, guard):
    discovery=load(SOURCE_PATH.parent/'current_discovery.py',DISCOVERY_SHA,
                   'fixed_target_current_discovery',DISCOVERY_BYTES)
    need(discovery.BASELINE_SHA==BASELINE_SHA and discovery.QUALIFICATION_SHA==QUALIFICATION_SHA and
         discovery.MAIN_EPOCH==CURRENT_EPOCH,'EXACT_CURRENT_DISCOVERY_AUTHORITY')
    return discovery.discover_current(app,baseline,epoch,guard)


def directory_identity(fd):
    value=os.fstat(fd)
    need(stat.S_ISDIR(value.st_mode),'FIXED_TARGET_DATA_DIRECTORY_REQUIRED')
    return {'device':value.st_dev,'inode':value.st_ino,'mode':value.st_mode,
            'uid':value.st_uid,'gid':value.st_gid}


class DataDirectories:
    """Hold only the two exact directory inodes; never enumerate or read contents."""
    def __init__(self,target,uid,binding,deadline):
        need(type(uid) is int and 10000<=uid<100000,'CURRENT_TARGET_UID_REQUIRED')
        self.target=target;self.uid=uid;self.binding=binding;self.deadline=deadline
        self.rows=[];self.closed=False
        try:
            for kind in ('user','user_de'):
                need(time.monotonic()<deadline,'TARGET_DIRECTORY_OBSERVATION_DEADLINE')
                path='/data/'+kind+'/0/'+PACKAGE
                fd=target.open_root(path,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
                self.rows.append({'path':path,'fd':fd})
                row=directory_identity(fd)
                need(row['device']>=0 and row['inode']>0 and row['uid']==uid,
                     'CURRENT_TARGET_DATA_DIRECTORY_OWNER_REQUIRED')
                self.rows[-1]['identity']=row
            self.verify()
        except BaseException as primary:
            try:self.close()
            except BaseException as secondary:primary.add_note('target directory close: '+repr(secondary))
            raise

    def verify(self):
        need(not self.closed and len(self.rows)==2,'TWO_OPEN_FIXED_TARGET_DIRECTORIES_REQUIRED')
        need(time.monotonic()<self.deadline,'TARGET_DIRECTORY_OBSERVATION_DEADLINE')
        self.target.verify()
        raw,_=self.target.read_file('/data/system/packages.list',1024*1024,
                                    deadline=min(self.deadline,time.monotonic()+5))
        self.binding.package_uids(raw,{PACKAGE:self.uid})
        del raw
        for row in self.rows:
            need(directory_identity(row['fd'])==row['identity'],
                 'HELD_TARGET_DATA_DIRECTORY_IDENTITY_CHANGED')
            fd=self.target.open_root(row['path'],os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
            primary=None
            try:
                need(directory_identity(fd)==row['identity'],'NAMED_TARGET_DATA_DIRECTORY_CHANGED')
            except BaseException as error:
                primary=error;raise
            finally:
                try:os.close(fd)
                except BaseException as cleanup:
                    if primary is None:raise
                    primary.add_note('named directory close: '+repr(cleanup))
        self.target.verify()

    def record(self):
        self.verify()
        return [{'path':row['path'],**row['identity']} for row in self.rows]

    def close(self):
        if self.closed:return {'held_data_directory_FDs_closed':0,'contents_read':False}
        self.closed=True;errors=[];count=len(self.rows)
        for row in reversed(self.rows):
            try:os.close(row['fd'])
            except BaseException as error:errors.append(type(error).__name__)
        self.rows=[]
        need(not errors,'TARGET_DIRECTORY_FD_CLOSE_FAILED:'+repr(errors))
        return {'held_data_directory_FDs_closed':count,'contents_read':False}
