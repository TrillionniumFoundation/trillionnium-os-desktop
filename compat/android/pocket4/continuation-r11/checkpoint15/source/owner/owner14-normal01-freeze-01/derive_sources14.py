"""Fresh Owner14 profile only; derive fixed runtime scripts without execution."""
from pathlib import Path
import ast
import difflib
import hashlib
import json

ROOT = Path(__file__).resolve().parent.parent
WORK = Path(__file__).resolve().parent
OLD = ROOT / 'owner13-normal-source-freeze-01'
OUT = ROOT / 'owner14-normal-source-freeze-01'
OLD_KIND = 'owned-real-producer13-normal01-terminal-drain01'
NEW_KIND = 'owned-real-producer14-normal01-fixture-repair01'
OLD_PREFIX = 'p4-owner13-normal-20261105-01'
NEW_PREFIX = 'p4-owner14-normal-20261105-01'
SCOPE = 'REAL_OWNER_ABI3_PINNED_CAUSE_TERMINAL_DRAIN_FIRST_ACTIVE_ORIGINAL_RETIREMENT'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return json.dumps(value, sort_keys=True, indent=2) + '\n'


def main():
    assert not OUT.exists()
    files = {}
    def put(name, data):
        data = data.encode() if isinstance(data, str) else data
        data.decode('utf-8')
        assert name not in files
        files[name] = data
    old_manifest = (OLD / 'manifest.json').read_bytes()
    assert sha(old_manifest) == 'f6e40d2b37bebe430eda08a0ad7aff95cd5917d4431e6c42a10c816d6c78dd41'
    for row in json.loads(old_manifest)['files']:
        raw = (OLD / row['path']).read_bytes()
        assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
    put('lineage/owner13-source-manifest.json', old_manifest)
    differences, review = [], []
    for name in ('actor.py', 'coordinator.py', 'prepare.py', 'owned.py', 'pinned_support.py', 'qualify.py'):
        old = (OLD / 'source' / name).read_text()
        new = old.replace(OLD_KIND, NEW_KIND).replace(OLD_PREFIX, NEW_PREFIX)
        new = new.replace('owner13-normal-preparation01', 'owner14-normal-preparation01')
        new = new.replace('owner13-real-normal01', 'owner14-real-normal01')
        new = new.replace('actual producer13 cell', 'actual producer14 cell')
        restored = new.replace(NEW_KIND, OLD_KIND).replace(NEW_PREFIX, OLD_PREFIX)
        restored = restored.replace('owner14-normal-preparation01', 'owner13-normal-preparation01')
        restored = restored.replace('owner14-real-normal01', 'owner13-real-normal01')
        restored = restored.replace('actual producer14 cell', 'actual producer13 cell')
        assert restored == old
        ast.parse(new)
        if name in ('owned.py', 'pinned_support.py', 'qualify.py'):
            assert new == old
        put('source/' + name, new)
        differences.append(''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
            fromfile='owner13/source/' + name, tofile='owner14/source/' + name)))
        review.append({'path': name, 'old_sha256': sha(old.encode()), 'new_sha256': sha(new.encode()),
            'new_bytes': len(new.encode()), 'reverse_fixed_literals_exact': True,
            'unchanged': new == old})
    put('source.diff', ''.join(differences))
    def guard(name, message):
        tree = ast.parse(files['source/' + name])
        matches = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and
            isinstance(n.func, ast.Attribute) and n.func.attr == 'need' and len(n.args) >= 2 and
            isinstance(n.args[1], ast.Constant) and n.args[1].value == message]
        assert len(matches) == 1
        return compile(ast.fix_missing_locations(ast.Expression(matches[0].args[0])), 'fixed-profile-guard', 'eval')
    profile = guard('prepare.py', 'wrong fixed profile')
    paths = guard('coordinator.py', 'this controller accepts only its fixed fresh unit/package/state')
    plan = {'attempt_nonce': '12' * 32, 'scope': SCOPE, 'kind': NEW_KIND,
        'unit': NEW_PREFIX + '.service', 'package': '/opt/' + NEW_PREFIX, 'state': '/opt/' + NEW_PREFIX + '-state'}
    cases = [('new_profile', profile, plan, True), ('new_paths', paths, plan, True),
        ('old_kind_rejected', profile, {**plan, 'kind': OLD_KIND}, False),
        ('short_nonce_rejected', profile, {**plan, 'attempt_nonce': '12' * 31}, False),
        ('old_scope_rejected', profile, {**plan, 'scope': 'REAL_OWNER_ABI3_RETAINED_CAUSE_FIRST_ACTIVE_ORIGINAL_RETIREMENT'}, False)]
    cases += [('old_' + key + '_rejected', paths, {**plan, key: value}, False) for key, value in [
        ('unit', OLD_PREFIX + '.service'), ('package', '/opt/' + OLD_PREFIX), ('state', '/opt/' + OLD_PREFIX + '-state')]]
    results = []
    for name, code, value, expected in cases:
        observed = eval(code, {'__builtins__': {}, 'len': len}, {'plan': value})
        assert observed is expected
        results.append({'case': name, 'accepted': observed})
    put('source-review.json', pretty({'schema': 1, 'scope': 'Fresh profile literals only',
        'sources': review, 'fixed_profile_controls': results,
        'actual_runtime_executed': False, 'plan_generated': False,
        'actual_build_or_ordinary_hashes_not_assumed': True,
        'previous_Owner11_runtime_still_failed': True, 'previous_producer13_ordinary_still_failed': True,
        'UID_61286_and_subordinate_20900000_live_absence_not_yet_checked': True,
        'unchanged_qualifier_or_identity_tests_not_repeated': True}))
    put('README.md', '''# Owner14 NORMAL01 source profile

This is a fresh source profile for a possible actual Producer14 run. It changes
only fixed profile/root labels and result labels from the unexecuted Owner13
source. qualify.py, owned.py and pinned_support.py are byte-identical. The actual
init identity, three-clock observation, ACTIVE, original Stop and full retirement
success gates remain unchanged; no kernel line is newly attributed to init.

Eight local checks evaluated the actual fixed profile/path guard expressions.
No runtime module, Android process, namespace or new Rust test was executed.
The producer13 ordinary run remains failed (35/37 relay tests), and the previous
Owner11 run remains failed before ACTIVE with incomplete original retirement.

No plan, random attempt nonce, prepare or runtime request is generated by this
source freeze. The later binder must require actual Producer14 compile/ordinary
success and actual artifact identities. Planned UID61286 and subordinate range
20900000+100000 require the original live absence guards. Unknown actual hashes
are never placeholders in an executable request. Root owns device dispatch.
''')
    put('derive_sources14.py', Path(__file__).read_bytes())
    rows = [{'path': name, 'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(files.items())]
    put('manifest.json', pretty({'schema': 1, 'kind': 'owner14_normal_source_freeze01', 'files': rows}))
    OUT.mkdir()
    for name, raw in files.items():
        p = OUT / name
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('xb') as stream:
            stream.write(raw)
    print(pretty({'root': str(OUT), 'files': len(files), 'manifest_sha256': sha(files['manifest.json']),
        'source_diff_bytes': len(files['source.diff']), 'source_diff_sha256': sha(files['source.diff']),
        'profile_controls_passed': len(results)}))


if __name__ == '__main__':
    main()
