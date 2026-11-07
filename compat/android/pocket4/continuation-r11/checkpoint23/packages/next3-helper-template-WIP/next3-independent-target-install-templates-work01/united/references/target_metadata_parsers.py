"""Fixed target metadata parsers only; original parser bodies preserved."""
import re
from pathlib import Path
PACKAGE = "com.united.mobile.android"
USER = 0
FILE_COUNT = 16

def need(value, message):
    if not value:
        raise RuntimeError(message)

def metadata(raw):
    match=re.fullmatch(re.escape('package:'+PACKAGE)+r' versionCode:([0-9]+) uid:([0-9]+)\n',
                       raw.decode('utf-8','strict'))
    need(match is not None,'ONE_EXACT_TICKET12306_USER0_METADATA_ROW_REQUIRED')
    version,uid=map(int,match.groups())
    need(0<version<2**63 and 10000<=uid<100000,'TICKET12306_METADATA_RANGE')
    return {'package':PACKAGE,'user':USER,'uid':uid,'version_code':version}

def apk_paths(raw):
    text=raw.decode('utf-8','strict')
    need(text.endswith('\n') and len(raw)<=16384,'TICKET12306_PATH_OUTPUT_BOUND')
    lines=text.splitlines()
    need(1<=len(lines)<=FILE_COUNT and all(x.startswith('package:') for x in lines),
         'TICKET12306_APK_PATH_ROWS_REQUIRED')
    paths=[x[len('package:'):] for x in lines]
    need(len(set(paths))==len(paths),'DUPLICATE_APK_PATH')
    parents=set()
    for path in paths:
        need(isinstance(path,str) and '\x00' not in path and len(path.encode())<=4096,
             'TICKET12306_PATH_SHAPE')
        parts=Path(path).parts
        need(len(parts)==6 and parts[:3]==('/','data','app') and
             re.fullmatch(r'~~[A-Za-z0-9_=-]+',parts[3]) and
             re.fullmatch(re.escape(PACKAGE)+r'-[A-Za-z0-9_=-]+',parts[4]) and
             (parts[5]=='base.apk' or re.fullmatch(r'split_[A-Za-z0-9_.-]+\.apk',parts[5])),
             'ONLY_EXACT_TICKET12306_INSTALL_DIRECTORY_APKS_MAY_BE_READ')
        parents.add(str(Path(path).parent))
    need(len(parents)==1 and sum(Path(x).name=='base.apk' for x in paths)==1,
         'ONE_TICKET12306_BASE_AND_ONE_INSTALL_DIRECTORY_REQUIRED')
    return sorted(paths)

if __name__ == "__main__":
    raise SystemExit("PARSER_ONLY_NO_DEVICE_OR_FILESYSTEM_ENTRY")
