#!/usr/bin/python3 -I
"""Read only the two completed PM records from the owned Contacts capture."""
import base64, hashlib, json, os, re, stat
from pathlib import Path

ROOT = Path('/home/alex/work/pocket4-contacts-search-source-20261105-r12-01')
EXPECTED = (
    ['/system/bin/pm', 'path', '--user', '0', 'com.android.contacts'],
    ['/system/bin/pm', 'list', 'packages', '-U', '--user', '0', 'com.android.contacts'],
)

def read(path, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NOATIME)
    try:
        before = os.fstat(fd)
        assert stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= maximum
        data = b''
        while len(data) <= maximum:
            block = os.read(fd, min(65536, maximum + 1 - len(data)))
            if not block:
                break
            data += block
        after = os.fstat(fd)
        assert before == after and len(data) == before.st_size
        return data
    finally:
        os.close(fd)

def main():
    assert os.geteuid() == 0
    for directory in (ROOT, ROOT / 'commands'):
        info = directory.lstat()
        assert stat.S_ISDIR(info.st_mode) and info.st_uid == 0
    originals = read(ROOT / 'result.json', 4096)
    assert len(originals) == 925 and hashlib.sha256(originals).hexdigest() == '47b4b47db9213355d63a0e792b1b99fdb25702dd6dd802fad4b9a44b1af00e27'
    names = sorted(p.name[:-7] for p in (ROOT / 'commands').iterdir()
                   if re.fullmatch(r'[0-9]{3}-android\.stdout', p.name))
    assert len(names) == 2
    records = []
    for stem, expected in zip(names, EXPECTED):
        base = ROOT / 'commands' / stem
        intent_raw = read(str(base) + '.intent.json', 32768)
        result_raw = read(str(base) + '.result.json', 32768)
        intent, result = json.loads(intent_raw), json.loads(result_raw)
        index = intent['argv'].index('/system/bin/pm')
        assert intent['argv'][index:] == expected and result['argv'] == intent['argv']
        assert result['joined'] and result['rc'] == 0 and not result['timed_out'] and result['guard_after']
        out = read(str(base) + '.stdout', 4096)
        err = read(str(base) + '.stderr', 4096)
        records.append({'stem': stem, 'pm_argv': expected, 'joined': True, 'rc': 0,
                        'command_guard_after': True, 'stdout': out.decode(), 'stderr': err.decode(),
                        'stdout_sha256': hashlib.sha256(out).hexdigest(),
                        'intent_sha256': hashlib.sha256(intent_raw).hexdigest(),
                        'result_sha256': hashlib.sha256(result_raw).hexdigest()})
    print(json.dumps({'schema': 'contacts-search-owned-completed-PM-journal/v1',
                      'new_android_commands': 0, 'new_UI_actions': 0, 'records': records,
                      'original_result_base64': base64.b64encode(originals).decode(),
                      'original_result_sha256': hashlib.sha256(originals).hexdigest()}, sort_keys=True))

if __name__ == '__main__':
    main()
