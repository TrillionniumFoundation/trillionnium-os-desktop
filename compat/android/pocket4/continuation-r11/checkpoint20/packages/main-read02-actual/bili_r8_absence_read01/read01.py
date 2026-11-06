#!/usr/bin/env python3
"""Two fixed host path absence observations after R8 pre-Main failure; no device I/O."""
import json
import os
import stat
import time

PARENT_PARTS=('home','alex','work')
NAMES=('pocket4-bilibili-r8-pause-resume-01','pocket4-bilibili-owned-qa-r8-flow-d53dc79edc9083c8ebcbadf65b289823')
FAILED_JOB='1a1af2e2032-fc05-667e'
REQUEST_SHA256='ed6a2dc08fc96107b3124e073c79937f8da65a219456b3a4f2f36f2693a06128'
STAGE_SHA256='ceabf424cd88a5812c6c36e7032a426ff5b87d3229c738694d39383e72fc8451'

def need(value,reason):
    if not value:raise RuntimeError(reason)

def identity(info):
    return {key:getattr(info,'st_'+key) for key in ('dev','ino','mode','uid','gid')}

def main():
    result={'schema':1,'kind':'bili-r8-pre-main-fixed-path-absence-read01','ok':False,
        'failed_job':FAILED_JOB,'failed_request_sha256':REQUEST_SHA256,
        'failed_stage_sha256':STAGE_SHA256,'path_observations':[],
        'error':None,'secondary_errors':[],'opened_readonly_directory_fds':0,
        'directory_close_attempts':0,'Android_commands':0,'process_or_service_actions':0,
        'file_reads':0,'file_writes':0,'permission_changes':0,'Main_identity_qualified':False,
        'UI_or_install_admission':False,'atomic_absence_snapshot_claimed':False,
        'raw_UI_or_private_contents_read':False,'old_nonce_reused_for_action':False,
        'whole_app_production_ready':False}
    fds=[];links=[];began=time.monotonic()
    def remember(phase,error):
        row={'phase':phase,'type':type(error).__name__}
        code=str(error)
        if code in ('ROOT_REQUIRED','FIXED_PARENT_DIRECTORY_REQUIRED','READ_DEADLINE',
                    'PARENT_IDENTITY_CHANGED','FAILED_STAGE_PATH_UNEXPECTEDLY_EXISTS'):
            row['code']=code
        else:row['code']='FIXED_HOST_STAT_OR_CLOSE_FAILED'
        if result['error'] is None:result['error']=row
        else:result['secondary_errors'].append(row)
    try:
        need(os.getuid()==os.geteuid()==0,'ROOT_REQUIRED')
        current=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        fds.append(current)
        for name in PARENT_PARTS:
            need(time.monotonic()-began<3,'READ_DEADLINE')
            parent=current
            current=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
            fds.append(current)
            info=os.fstat(current);need(stat.S_ISDIR(info.st_mode),'FIXED_PARENT_DIRECTORY_REQUIRED')
            links.append((parent,name,current,identity(info)))
        result['parent_identity']=identity(os.fstat(current))
        for name in NAMES:
            need(time.monotonic()-began<3,'READ_DEADLINE')
            row={'path':'/home/alex/work/'+name,'observation':'lstat_no_follow','exists':None}
            try:
                info=os.stat(name,dir_fd=current,follow_symlinks=False)
            except FileNotFoundError:
                row['exists']=False
            else:
                row['exists']=True;row['identity']=identity(info)
            result['path_observations'].append(row)
        for parent,name,fd,expected in links:
            need(identity(os.fstat(fd))==expected and
                 identity(os.stat(name,dir_fd=parent,follow_symlinks=False))==expected,
                 'PARENT_IDENTITY_CHANGED')
        need(time.monotonic()-began<3,'READ_DEADLINE')
        need(len(result['path_observations'])==2 and
             all(row['exists'] is False for row in result['path_observations']),
             'FAILED_STAGE_PATH_UNEXPECTEDLY_EXISTS')
    except BaseException as error:
        remember('fixed_host_path_observation',error)
    finally:
        result['opened_readonly_directory_fds']=len(fds)
        for fd in reversed(fds):
            result['directory_close_attempts']+=1
            try:os.close(fd)
            except BaseException as error:remember('directory_close',error)
    result['elapsed_seconds']=time.monotonic()-began
    result['ok']=result['error'] is None and result['secondary_errors']==[]
    result['every_acquired_directory_close_attempted']=(result['directory_close_attempts']==len(fds))
    output=json.dumps(result,sort_keys=True,separators=(',',':'))+'\n'
    need(len(output.encode('utf-8'))<=8192,'OUTPUT_BOUND')
    print(output,end='',flush=True)
    return 0 if result['ok'] else 1
