"""Independent new-Main component; no historical Session, Main or execute entry."""
from pathlib import Path
import hashlib, json, os, re, types, urllib.parse

def shared_shell_permission_rows(raw):
    sections = re.findall('^Shared users:\\n(.*?)(?=^\\S|\\Z)', raw, re.M | re.S)
    assert len(sections) == 1, 'SHARED_USER_SECTION_NOT_UNIQUE'
    users = re.findall('^  SharedUser \\[([^]]+)\\][^\\n]*\\n(.*?)(?=^  SharedUser |\\Z)', sections[0], re.M | re.S)
    matches = [body for name, body in users if name == 'android.uid.shell']
    assert len(matches) == 1, 'SHELL_SHARED_USER_NOT_UNIQUE'
    shared = matches[0]
    assert re.findall('^    appId=(\\d+)\\s*$', shared, re.M) == ['2000'], 'SHELL_SHARED_UID_CHANGED'
    assert re.search('^      PackageSetting\\{[^}]* com\\.android\\.shell/2000\\}\\s*$', shared, re.M), 'SHELL_SHARED_PACKAGE_MISSING'
    user_blocks = re.findall('^    User (\\d+):[^\\n]*\\n(.*?)(?=^    User |\\Z)', shared, re.M | re.S)
    target = [body for user, body in user_blocks if user == '0']
    assert len(target) == 1, 'SHELL_USER_ZERO_NOT_UNIQUE'
    runtime = re.findall('^      runtime permissions:\\n(.*?)(?=^      \\S|\\Z)', target[0], re.M | re.S)
    assert len(runtime) == 1, 'SHELL_RUNTIME_PERMISSION_SECTION_NOT_UNIQUE'
    return sorted((line.strip() for line in runtime[0].splitlines() if re.search('android\\.permission\\.[A-Z_]+: granted=', line)))
