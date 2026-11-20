"""Preserve the actual Settings package, complete grants and directory owners.

Only package metadata and CE/DE directory metadata are read. No private data
file is opened. The shared system UID is not treated as a Settings-only crash
filter, so this partial case cannot satisfy the common stability gate.
"""
import os
import re
import stat


def parse(c, raw, profile):
    c.need(type(raw) is bytes and 0 < len(raw) <= 2*1024*1024,
           'BOUNDED_COMPLETE_SETTINGS_PACKAGE_DUMP')
    text=raw.decode('utf-8','strict')
    blocks=re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)',text,re.M|re.S)
    c.need(len(blocks)==1 and re.findall(r'^  Package \[([^]]+)\]',blocks[0],re.M)==[profile.PACKAGE],
           'ONE_ACTIVE_SETTINGS_PACKAGE_SECTION')
    block=blocks[0]
    def one(pattern):
        values=re.findall(pattern,block,re.M)
        c.need(len(values)==1,'SETTINGS_FIELD_NOT_UNIQUE:'+pattern)
        return values[0]
    uid=int(one(r'^    appId=(\d+)$'));code=int(one(r'^    versionCode=(\d+)\b'))
    c.need(uid==1000 and code==profile.TARGET['version_code'],'SETTINGS_SYSTEM_UID_OR_VERSION_CHANGED')
    rows=re.findall(r'^    User (\d+): (.*)$',block,re.M)
    c.need(len(rows)==1 and rows[0][0]=='0','SETTINGS_EXACT_USER_ZERO_REQUIRED')
    parts=rows[0][1].split()
    c.need(all(re.fullmatch(r'[A-Za-z][A-Za-z0-9]*=\S+',p) for p in parts)
           and len(parts)==len({p.split('=',1)[0] for p in parts}),'SETTINGS_USER_STATE_GRAMMAR')
    state=dict(p.split('=',1) for p in parts)
    c.need(state.get('installed')=='true' and state.get('hidden')=='false'
           and state.get('suspended')=='false' and state.get('enabled') in ('0','1'),
           'SETTINGS_INSTALLED_ENABLED_UNSUSPENDED_REQUIRED')
    permissions=[]
    for line in block.splitlines():
        if ': granted=' not in line:continue
        row=line.strip()
        c.need(re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]+: granted=(true|false)(?:, flags=\[[A-Z_ |]*\])?',row),
               'SETTINGS_UNPARSED_PERMISSION_ROW')
        permissions.append(row)
    c.need(1<=len(permissions)<=512 and len(permissions)==len(set(permissions)),
           'SETTINGS_COMPLETE_NONEMPTY_PERMISSION_SET_REQUIRED')
    lifecycle={k:state[k] for k in ('stopped','notLaunched') if k in state}
    c.need(all(v in ('true','false') for v in lifecycle.values()),'SETTINGS_LAUNCH_STATE_GRAMMAR')
    # Launch can legitimately clear these two flags. Keep the observations,
    # without changing them back or crediting the complete lifecycle gate.
    preserved={k:v for k,v in state.items() if k not in lifecycle}
    return {'package':profile.PACKAGE,'uid':uid,'version_code':code,
            'user0_state_preserved':preserved,'launch_state_observed':lifecycle,
            'all_permission_rows':sorted(permissions)}


def snapshot(flow, profile):
    c=flow.c;flow.guard()
    value=parse(c,flow.android(['/system/bin/dumpsys','package',profile.PACKAGE],20),profile)
    state=value['user0_state_preserved'];directories={}
    for key,guest in (('ce','/data/user/0/'+profile.PACKAGE),('de','/data/user_de/0/'+profile.PACKAGE)):
        fd=flow.view.target.open_root(guest,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            info,mapped=c.mapped_file_info(flow.view,fd,1000)
            c.need((info.st_uid,info.st_gid)==mapped and str(info.st_ino)==state.get(key+'DataInode'),
                   'SETTINGS_DIRECTORY_OWNER_OR_INODE_CHANGED')
            directories[key]={'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid,
                              'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode)}
        finally:os.close(fd)
    flow.artifacts.verify();flow.guard()
    value['directories']=directories
    value['identity_receipt']=flow.scope['actual_resolution_receipt']
    return value


def same(c, before, after):
    c.need({k:v for k,v in before.items() if k!='launch_state_observed'}==
           {k:v for k,v in after.items() if k!='launch_state_observed'},
           'SETTINGS_IDENTITY_GRANTS_OR_DIRECTORY_METADATA_CHANGED')
    c.need(all(value=='false' for value in after['launch_state_observed'].values()),
           'SETTINGS_LAUNCH_STATE_NOT_OBSERVED_AFTER_ACTUAL_LAUNCH')
    return True
