"""Derive only literal permission observations from two fixed private originals."""
from pathlib import Path
import hashlib
import json
import re

PRIVATE = Path('/workspace/scratch/265e5bca485a/p4_private_ui/beike-permission-pilot-r1')
HERE = Path(__file__).resolve().parent
PINS = {
    'android-02.stdout': (50525, '001c37aab9fe84def6d2e9d87c1e6a81d34baf74e62e2f50643c45c1077b5487'),
    'android-03.stdout': (1720, 'f839074801868c1196b0df62916df5c31b40ef894649c522495668cfcbeb3b6d'),
}


def exact(name):
    raw = (PRIVATE / name).read_bytes()
    size, digest = PINS[name]
    assert len(raw) == size and hashlib.sha256(raw).hexdigest() == digest
    return raw.decode('utf-8', 'strict').splitlines()


def section(lines, header, prefix):
    indices = [i for i, value in enumerate(lines) if value == header]
    assert len(indices) == 1, header
    rows = []
    for value in lines[indices[0] + 1:]:
        if not value.startswith(prefix):
            break
        rows.append(value[len(prefix):])
    assert rows and all(rows)
    return rows


def main():
    pm = exact('android-02.stdout')
    assert sum(value.startswith('  Package [com.lianjia.beike]') for value in pm) == 1
    user = [i for i, value in enumerate(pm) if value.startswith('    User 0: ceDataInode=')]
    runtime = [i for i, value in enumerate(pm) if value == '      runtime permissions:']
    assert len(user) == len(runtime) == 1 and user[0] < runtime[0]
    assert not any(re.match(r'    User [0-9]+:', value) for value in pm[user[0] + 1:runtime[0]])
    requested = section(pm, '    requested permissions:', '      ')
    install = []
    for value in section(pm, '    install permissions:', '      '):
        match = re.fullmatch(r'(.+): granted=(true|false)', value)
        assert match, value
        install.append({'permission': match[1], 'granted': match[2] == 'true'})
    grants = []
    for value in section(pm, '      runtime permissions:', '        '):
        match = re.fullmatch(r'(.+): granted=(true|false), flags=\[([^\]]*)\]', value)
        assert match, value
        grants.append({'permission': match[1], 'granted': match[2] == 'true', 'flags_raw': match[3]})
    assert len({row['permission'] for row in grants}) == len(grants)
    modes = []
    for value in exact('android-03.stdout'):
        match = re.fullmatch(r'(Uid mode: )?([A-Z][A-Z_0-9]*): (ignore|default|allow|deny|foreground)(?:;.*)?', value)
        assert match, value
        modes.append({'operation': match[2], 'reported_mode': match[3],
                      'explicit_uid_mode_prefix_on_this_line': bool(match[1]),
                      'raw_line_sha256': hashlib.sha256(value.encode()).hexdigest()})
    assert len({row['operation'] for row in modes}) == len(modes)
    worker = json.loads((HERE / 'actual/worker.stdout.original.json').read_bytes())
    assert worker['ok'] and worker['target_identity_from_pinned_scope'] == {
        'package': 'com.lianjia.beike', 'uid': 10143, 'version_code': 3067100}
    assert worker['current_scope_47_unchanged'] and worker['meituan_saved_location_unchanged']
    result = {
        'schema': 'pocket4-literal-beike-permission-service-observation-v1',
        'observation_job': '1a1b279845c-fc05-7e2e',
        'private_readback_job': '1a1b27e6086-fc05-7e44',
        'package': 'com.lianjia.beike', 'uid': 10143, 'version_code': 3067100,
        'runtime_permission_user': 0, 'AppOps_requested_user': 0,
        'private_inputs': [{'name': name, 'bytes': pin[0], 'sha256': pin[1], 'raw_content_published': False}
                          for name, pin in PINS.items()],
        'requested_permissions_verbatim_after_exact_six_space_format_prefix': requested,
        'noncanonical_leading_whitespace_names_preserved': [name for name in requested if name[:1].isspace()],
        'install_permission_observations': install,
        'user0_runtime_permission_observations': grants,
        'AppOps_reported_modes': modes,
        'counts': {'requested_names': len(requested), 'install_permission_rows': len(install),
                   'runtime_permission_rows': len(grants), 'runtime_granted_true': sum(row['granted'] for row in grants),
                   'runtime_granted_false': sum(not row['granted'] for row in grants), 'AppOps_rows': len(modes)},
        'permission_changes': 0, 'new_runtime_queries_in_this_derivation': 0,
        'full_raw_PM_or_AppOps_content_published': False, 'usage_timestamps_published': False,
        'role_status': 'UNKNOWN_NOT_QUERIED', 'production_ready': False,
        'limits': [
            'This is the recorded service state for the named observation, not a permanent grant guarantee.',
            'granted=false is not attributed to a user decision; the reported flags are retained literally.',
            'A reported AppOps mode is not itself a permission grant or successful core operation.',
            'The explicit Uid mode prefix is recorded per literal line; the scope of unprefixed lines is not inferred.',
            'INTERNET granted does not demonstrate a working network request; local-network grant does not prove connectivity.',
            'Only the exact presentation indentation is removed; permission name whitespace is not normalized.',
        ],
    }
    output = HERE / 'EFFECTIVE_PERMISSION_OBSERVATION.derived.json'
    raw = (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode()
    with output.open('xb') as stream:
        stream.write(raw)
    print(json.dumps({'output': output.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                      'counts': result['counts'], 'noncanonical_names': result['noncanonical_leading_whitespace_names_preserved']}))


if __name__ == '__main__':
    main()
