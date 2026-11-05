#!/usr/bin/env python3
"""Create a fixed-path readonly follow-up; never execute a remote request."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

WORK = Path(__file__).resolve().parent
OLD = WORK / 'native-generation-image-tools-read01'
NEW = WORK / 'native-generation-image-tools-read02'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def replace(text, before, after):
    assert text.count(before) == 1, before[:100]
    return text.replace(before, after)


def put(name, raw):
    path = NEW / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        assert stream.write(raw) == len(raw)


def main():
    prior = OLD / 'collect.py'
    original = prior.read_bytes()
    assert sha(original) == 'efb089d91d1c761a9666b1f64751a46474fb8e5668a81f44d053bb551ea6ed23'
    actual = (WORK.parent / 'root-recovery-20261104-02/evidence/native-generation-image-tools-read01/result.json').read_bytes()
    assert sha(actual) == '85ba1d47a80f57de6ba5af983cf90d89171f7139de66a5a7136daabfbbca5a7d'
    old_result = json.loads(actual)
    assert old_result['state'] == 'FAIL' and list(old_result['tools']) == ['zip', 'unzip']
    assert old_result['backend_observations'] == []
    text = original.decode()
    text = replace(text, 'pocket4-native-generation-image-tools-readonly-01-20261105',
                   'pocket4-native-generation-image-tools-readonly-02-20261105')
    text = replace(text,
        "TOOLS = ('zip', 'unzip', 'debugfs', 'mke2fs', 'fsck.erofs', 'mkfs.erofs',\n         'fakeroot', 'chown', 'setfattr')",
        """TOOLS = {
    'zip': ('/usr/bin/zip',),
    'unzip': ('/usr/bin/unzip',),
    'debugfs': ('/usr/bin/debugfs', '/usr/sbin/debugfs'),
    'mke2fs': ('/usr/bin/mke2fs', '/usr/sbin/mke2fs'),
    'fsck.erofs': ('/usr/bin/fsck.erofs', '/usr/sbin/fsck.erofs'),
    'mkfs.erofs': ('/usr/bin/mkfs.erofs', '/usr/sbin/mkfs.erofs'),
    'fakeroot': ('/usr/bin/fakeroot',),
    'chown': ('/usr/bin/chown',),
    'setfattr': ('/usr/bin/setfattr',),
}
CONTROLLED_PATH = '/usr/bin:/usr/sbin:/bin:/sbin'
PRIOR_PATH = Path('/home/alex/work/pocket4-native-generation-image-tools-readonly-01-20261105/result.json')
PRIOR_SHA = '85ba1d47a80f57de6ba5af983cf90d89171f7139de66a5a7136daabfbbca5a7d'""")
    text = replace(text, "(Path('/usr/bin'), Path('/usr/lib')))",
                   "(Path('/usr/bin'), Path('/usr/sbin'), Path('/usr/lib')))")
    anchor = '\ndef execute():\n'
    helper = '''
def prior_failure():
    fd = os.open(PRIOR_PATH, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 1000 and
                not (before.st_mode & 0o022) and before.st_size <= 16384,
                'prior owned observation type/owner/bound differs')
        raw = os.read(fd, 16385)
        require(len(raw) == before.st_size and len(raw) <= 16384 and sha(raw) == PRIOR_SHA and
                identity(before) == identity(os.fstat(fd)) == identity(PRIOR_PATH.lstat()),
                'prior failure receipt changed')
        observed = json.loads(raw)
        require(observed['state'] == 'FAIL' and list(observed['tools']) == ['zip', 'unzip'] and
                observed['backend_observations'] == [] and observed['commands_executed'] == 0 and
                observed['error'] == "RuntimeError('required fixed test tool absent from controlled PATH: debugfs')",
                'prior observation is not the recorded PATH failure')
        return {'path': str(PRIOR_PATH), 'bytes': len(raw), 'sha256': sha(raw),
                'held_before': identity(before), 'held_after': identity(os.fstat(fd)),
                'named_after': identity(PRIOR_PATH.lstat()), 'state': observed['state']}
    finally:
        os.close(fd)

'''
    text = replace(text, anchor, helper + anchor)
    text = replace(text, "'tools': {}, 'backend_observations': [],",
                   "'tools': {}, 'tool_candidate_observations': {}, 'missing_required_tools': [],\n              'backend_observations': [], 'controlled_selection_PATH': CONTROLLED_PATH,")
    text = replace(text, "report['owned_resources_before'] = resource_before\n",
                   "report['owned_resources_before'] = resource_before\n        report['prior_failed_observation'] = prior_failure()\n")
    start = text.index('        for name in TOOLS:\n')
    end = text.index("        report['observations_unchanged_after'] = True\n", start)
    text = text[:start] + '''        for name, paths in TOOLS.items():
            rows = [observe(path) for path in paths]
            report['tool_candidate_observations'][name] = rows
            available = [row for row in rows if row.get('absent') is not True]
            if not available:
                report['missing_required_tools'].append(name)
                continue
            selected = available[0]
            require(selected['held_before'][2] & 0o111,
                    'selected fixed system input is not executable: ' + name)
            require(shutil.which(name, path=CONTROLLED_PATH) == selected['requested_path'],
                    'controlled selection differs from the fixed observed path: ' + name)
            report['tools'][name] = selected
        for name in BACKENDS:
            report['backend_observations'].append(observe(name))
        # Missing fixed tools do not suppress the remaining readonly evidence.
        # They still make the completed observation ineligible for execution.
        for name, rows in report['tool_candidate_observations'].items():
            for row in rows:
                require(observe(row['requested_path']) == row,
                        'fixed tool candidate changed after read: ' + name)
        for name, row in report['tools'].items():
            require(shutil.which(name, path=CONTROLLED_PATH) == row['requested_path'],
                    'controlled tool selection changed after read: ' + name)
        for row in report['backend_observations']:
            require(observe(row['requested_path']) == row, 'fixed backend observation changed after read')
        require(prior_failure() == report['prior_failed_observation'], 'prior receipt changed during observation')
        require(not report['missing_required_tools'], 'one or more required fixed tools remain absent')
''' + text[end:]
    text = replace(text, "'fixed_tool_names': TOOLS,", "'fixed_tool_candidates': TOOLS,")
    ast.parse(text)
    request = json.loads((OLD / 'exact-request.json').read_bytes())
    request['stdin'] = text
    request['idempotency_key'] = 'pocket4-native-generation-image-tools-readonly-02-20261105'
    request['args'][2] = request['args'][2].replace(sha(original), sha(text.encode()))
    assert request['args'][2].count(sha(text.encode())) == 1
    NEW.mkdir(mode=0o700)
    put('collect.py', text.encode())
    put('exact-request.json', (json.dumps(request, indent=2) + '\n').encode())
    put('read01-to-read02.patch', ''.join(difflib.unified_diff(original.decode().splitlines(True),
        text.splitlines(True), fromfile='readonly01/collect.py', tofile='readonly02/collect.py')).encode())
    put('references/readonly01-collect.py', original)
    put('references/readonly01-actual-failure.json', actual)
    put('derive.py', Path(__file__).read_bytes())
    files = {str(p.relative_to(NEW)): {'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
             for p in sorted(NEW.rglob('*')) if p.is_file()}
    put('SOURCE_PINS.json', (json.dumps({'schema': 1, 'files': files,
        'fixed_tool_candidate_paths': 13, 'backend_paths_unchanged': 10,
        'resource_helpers_unchanged': True, 'commands_executed': 0,
        'tools_known_present_before_this_request': ['zip', 'unzip'],
        'actual_execution': False, 'prior_FAIL_preserved': True}, indent=2) + '\n').encode())
    print(json.dumps({'request': str(NEW / 'exact-request.json'),
        'request_sha256': sha((NEW / 'exact-request.json').read_bytes()),
        'controller_sha256': sha(text.encode()), 'fixed_candidate_paths': 13,
        'actual_execution': False}))


if __name__ == '__main__':
    main()
