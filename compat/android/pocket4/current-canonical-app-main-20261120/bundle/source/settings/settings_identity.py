"""Preserve the actual Settings package, complete grants and directory owners.

Only package metadata and CE/DE directory metadata are read. No private data
file is opened. The shared system UID is not treated as a Settings-only crash
filter, so this partial case cannot satisfy the common stability gate.
"""
import os
import hashlib
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


def permission_state(c, snapshot, permission):
    rows = [row for row in snapshot['all_permission_rows'] if row.startswith(permission + ': ')]
    c.need(len(rows) == 1, 'ONE_EXPLICIT_SETTINGS_PERMISSION_STATE_REQUIRED')
    match = re.fullmatch(re.escape(permission) + r': granted=(true|false)(?:, flags=\[[A-Z_ |]*\])?', rows[0])
    c.need(match is not None, 'EXPLICIT_PERMISSION_GRANT_GRAMMAR')
    return match[1] == 'true'


def permission_result(c, raw):
    c.need(type(raw) is bytes and raw in (b'0\n', b'-1\n'),
           'ACTUAL_PACKAGE_PERMISSION_SERVICE_RESULT_REQUIRED')
    return raw == b'0\n'


def accounts(c, raw):
    """Compare account identities without copying names into public summaries.

    The actual private recorder retains the complete service reply. Logs and
    active-session ages are not account identities. Truncated, duplicate or
    ambiguous user/account sections fail closed rather than becoming zero.
    """
    c.need(type(raw) is bytes and 0 < len(raw) <= 2*1024*1024
           and raw.endswith(b'\n') and b'\0' not in raw and b'\r' not in raw,
           'BOUNDED_COMPLETE_ACCOUNT_SERVICE_DUMP')
    text = raw.decode('utf-8', 'strict')
    starts = list(re.finditer(r'^User UserInfo\{(\d+):[^\n]*\}:\s*$', text, re.M))
    c.need(starts and len(starts) <= 32 and len(starts) == len({m[1] for m in starts})
           and any(m[1] == '0' for m in starts), 'COMPLETE_UNIQUE_ACCOUNT_USERS_REQUIRED')
    output = []
    for index, match in enumerate(starts):
        section = text[match.end():starts[index+1].start() if index+1 < len(starts) else len(text)]
        headings = list(re.finditer(r'^\s*Accounts: (\d+)\s*$', section, re.M))
        c.need(len(headings) == 1, 'ONE_ACCOUNT_COUNT_FOR_EACH_ACTUAL_USER')
        head = headings[0]; count = int(head[1])
        c.need(0 <= count <= 1024, 'ACCOUNT_COUNT_BOUND')
        # AccountManagerService prints the complete account list immediately
        # after Accounts:, followed by a blank line and unrelated diagnostics.
        tail = section[head.end():].lstrip('\r\n')
        lines = tail.splitlines()
        account_rows = []
        for line in lines:
            if not line.strip(): break
            if not line.lstrip().startswith('Account {'): break
            c.need(re.fullmatch(r'\s*Account \{name=.+, type=[A-Za-z0-9_.-]+\}\s*', line)
                   is not None, 'UNPARSED_ACCOUNT_IDENTITY_ROW')
            account_rows.append(line.strip())
        c.need(len(account_rows) == count and len(account_rows) == len(set(account_rows)),
               'ACCOUNT_LIST_TRUNCATED_OR_DUPLICATED')
        output.append({'user': int(match[1]), 'count': count,
            'account_identity_sha256': sorted(hashlib.sha256(row.encode()).hexdigest() for row in account_rows)})
    return sorted(output, key=lambda row: row['user'])


def verify_permission_interfaces(flow, session, before, page_observations):
    """Read actual service state and an actual malformed-query error response."""
    c = flow.c; profile = session.profile
    c.need(len(page_observations) == 2
           and [r['summary']['page'] for r in page_observations] == ['special_access', 'accounts'],
           'ACTUAL_PERMISSION_AND_ACCOUNT_WINDOWS_REQUIRED')
    permission = profile.PERMISSION_CHECK[3]
    expected = permission_state(c, before, permission)
    actual = permission_result(c, flow.android(profile.PERMISSION_CHECK, 20))
    c.need(actual is expected, 'PERMISSION_SERVICE_AND_COMPLETE_PACKAGE_STATE_DISAGREE')
    error = flow.android(profile.PERMISSION_ERROR, 20)
    c.need(error == b'Error: check-permission missing permission argument\n',
           'ACTUAL_READONLY_PERMISSION_INPUT_ERROR_NOT_OBSERVED')
    # A denied grant is a legitimate state; never require or issue a grant.
    return {'permission': permission, 'user': 0, 'granted': actual,
        'service_matches_complete_package_dump': True, 'readonly_input_error_verified': True,
        'observed_pages': page_observations, 'permission_writes': 0, 'account_writes': 0,
        'account_identities': accounts(c, flow.android(profile.ACCOUNT_READ, 20)),
        'settings_permissions_gate_accepted': False,
        'remaining_permission_scope': 'actual-Settings-permission-denial-and-error-UX',
        'whole_app_business_accepted': False}
