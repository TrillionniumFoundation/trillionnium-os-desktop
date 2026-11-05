"""Actual retained-record gates and owned temporary-file alias controls; no device read."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('metadata_candidate', HERE / 'read_metadata.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
EVIDENCE = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence')
FILES = {
    'prepared.json': EVIDENCE / 'owner14-normal01-prepared-read01/prepared.json',
    'runtime-result.json': EVIDENCE / 'owner14-normal01-runtime-read01/runtime-result.json',
}
tests = []


def passed(name):
    tests.append({'name': name, 'passed': True})


def rejected(name, call):
    try:
        call()
    except (OSError, RuntimeError, KeyError):
        passed(name)
    else:
        raise AssertionError('accepted negative: ' + name)


def main():
    raw = {name: path.read_bytes() for name, path in FILES.items()}
    for name, body in raw.items():
        assert (len(body), hashlib.sha256(body).hexdigest()) == m.RECORDS[name]
    p, r = (json.loads(raw[name]) for name in ('prepared.json', 'runtime-result.json'))
    bound = m.validate_records(p, r)
    assert bound['original_runtime_success'] is False and bound['original_cleanup_bound'] is True
    passed('actual failed runtime and exact cleanup bind without qualification')
    for label, mutate in [
        ('foreign nonce rejected', lambda a, b: b.update(attempt_nonce='0' * 64)),
        ('replacement fresh-image inode rejected', lambda a, b: a['data_images'][0]['identity'].update(inode=1)),
        ('incomplete outer cleanup rejected', lambda a, b: b['exact_unit_cleanup'].update(cgroup_absent=False)),
        ('foreign Invocation rejected', lambda a, b: b['first_unit'].update(InvocationID='0' * 32)),
        ('changed Main fence rejected', lambda a, b: b.update(main_after={'changed': True})),
        ('incomplete typed retirement rejected', lambda a, b: b['actor_result']['latest_status']['relay_lifecycle'].update(retirement_failure='forced incomplete')),
    ]:
        a, b = copy.deepcopy(p), copy.deepcopy(r)
        mutate(a, b)
        rejected(label, lambda: m.validate_records(a, b))
    # Only this newly created local directory is mutated; metadata main is not called.
    with tempfile.TemporaryDirectory(prefix='metadata-controls-', dir=HERE) as temp:
        root = Path(temp)
        parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            target = root / 'owned-data'
            target.write_bytes(b'owned metadata fixture')
            os.chmod(target, 0o600)
            os.symlink('owned-data', root / 'data.img')
            rejected('real symlink image rejected before content read',
                     lambda: m.regular('data.img', parent, [], m.IMAGE_BYTES))
            (root / 'data.img').unlink()
            os.link(target, root / 'data.img')
            rejected('real multiply linked image rejected',
                     lambda: m.regular('data.img', parent, [], m.IMAGE_BYTES))
            target.unlink()
            held = []
            fd, before = m.regular('data.img', parent, held, m.IMAGE_BYTES)
            try:
                assert os.pread(fd, before['bytes'], 0) == b'owned metadata fixture'
                m.recheck(held)
                (root / 'data.img').rename(root / 'old-data')
                (root / 'data.img').write_bytes(b'other inode')
                os.chmod(root / 'data.img', 0o600)
                rejected('real named-path replacement rejected while original FD held', lambda: m.recheck(held))
                assert os.pread(fd, before['bytes'], 0) == b'owned metadata fixture'
            finally:
                os.close(fd)
        finally:
            os.close(parent)
    result = {'schema': 1, 'scope': 'retained actual JSON bindings and local owned temporary filesystem only',
              'read_metadata_sha256': hashlib.sha256((HERE / 'read_metadata.py').read_bytes()).hexdigest(),
              'tests': tests, 'passed': len(tests), 'failed': 0,
              'device_runtime_executed': False, 'debugfs_executed': False,
              'image_read': False, 'metadata_main_executed': False, 'qualification': False}
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
