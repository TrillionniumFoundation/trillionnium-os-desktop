#!/usr/bin/env python3
"""Bind the actual private preparation through the unchanged template04 gate."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

BASE = Path('/workspace/scratch/94990735b266')
WORK = BASE / 'native-recovery-20261105-02'
HERE = Path(__file__).resolve().parent
OLD = WORK / 'engine-qualification07-android-bound01/binding.json'
TEMPLATE = WORK / 'engine-qualification-template-04/make_qualification.py'
PREPARED = BASE / 'root-recovery-20261104-02/evidence/candidate07-android-prepared-read01/prepared.json'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    old_raw = OLD.read_bytes()
    assert digest(old_raw) == 'c8d46b80137208b865441de84ff7e8d4d26ed7b9d7b5b9a2a479c7a4b24b4e4b'
    assert digest(TEMPLATE.read_bytes()) == 'c29fb03633ede92c845018ab93a20530320a5741e33afab1986b5bfa457c0efd'
    raw = PREPARED.read_bytes()
    assert len(raw) == 24635 and digest(raw) == '539041e99f862e728a88c75140f525e7771a584aabcdfe4eac30f75a59c41850'
    prepared = json.loads(raw)
    assert prepared['fresh_empty_data_images'] is True and prepared['services_started'] is False
    assert prepared['old_userdata_read'] is False and prepared['production_ready'] is False
    assert all(x['fresh_O_EXCL_created'] is True for x in prepared['data_images'])
    assert {x['name'] for x in prepared['data_images']} == {'data.img', 'metadata.img'}
    assert prepared['engine_sha256'] == '3aa9b479a9b66f56ae827477cf9f957fdeb6dcb21f1f8f981e34a1089f80048a'
    original = json.loads(old_raw)
    config = json.loads(old_raw)
    config['prepared'] = {
        'local_path': str(PREPARED),
        'path': prepared['evidence'] + '/prepared.json',
        'sha256': digest(raw),
    }
    assert all(config[key] == original[key] for key in original if key != 'prepared')
    binding = (json.dumps(config, indent=2, sort_keys=True) + '\n').encode()
    target = HERE / 'binding.json'
    with target.open('xb') as stream:
        stream.write(binding)
    subprocess.run([sys.executable, '-I', '-B', str(TEMPLATE), 'android-check',
                    '--binding', str(target), '--binding-sha256', digest(binding),
                    '--out', str(HERE / 'generated')], check=True)
    report = {
        'schema': 1, 'state': 'ACTUAL_PREPARED_BOUND_CHECK_AND_REVIEW_TEMPLATE_ONLY',
        'original_binding_sha256': digest(old_raw), 'binding_sha256': digest(binding),
        'changed_binding_keys': ['prepared'], 'prepared': config['prepared'],
        'template04_unchanged_sha256': digest(TEMPLATE.read_bytes()),
        'root_admission_fabricated': False, 'Hepta_calls': 0, 'Android_runtime_executed': False,
        'original_four_case_runner_changed': False, 'Main_actions': 0, 'production_ready': False,
        'next': 'Root runs the original input/runtime check, independently admits the exact review, then the unchanged android-runtime generator binds that review before the unique execution.',
    }
    encoded = (json.dumps(report, indent=2, sort_keys=True) + '\n').encode()
    with (HERE / 'BINDING_REVIEW.json').open('xb') as stream:
        stream.write(encoded)
    print(json.dumps({'binding_sha256': digest(binding), 'prepared_sha256': digest(raw), 'state': report['state']}))


if __name__ == '__main__':
    main()
