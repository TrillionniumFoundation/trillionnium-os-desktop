#!/usr/bin/env python3
"""Actual retained safe JSON predicates only; never read or export PNGs."""
import copy
import hashlib
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
RETAINED = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/bili-r5-player-geometry01-read01/originals')


def main():
    path = HERE / 'read_private_crops.py'
    module = types.ModuleType('private_crop_control'); module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    values = []
    for key, name in [('coordinator', 'coordinator.json'), ('stage', 'stage.json'),
                      ('navigation', 'navigation.json'), ('cleanup', 'cleanup.json')]:
        raw = (RETAINED / name).read_bytes()
        assert len(raw) == module.FILES[key][1] and hashlib.sha256(raw).hexdigest() == module.FILES[key][2]
        values.append(json.loads(raw))
    rows = []

    def run(name, change, accepted):
        v = copy.deepcopy(values); change(v); error = None
        try:
            module.validate_observations(*v)
        except RuntimeError as exc:
            error = str(exc)
        assert (error is None) == accepted, (name, error)
        rows.append({'case': name, 'accepted': error is None, 'expected_met': True, 'error': error})

    run('retained_failed_attempt_two_qualified_crops_only', lambda v: None, True)
    run('reject_attempt_rewritten_as_success', lambda v: v[2].update(ok=True), False)
    run('reject_Main_change', lambda v: v[0]['Main_after'].update(Main_epoch_sha256='0' * 64), False)
    run('reject_third_failed_crop_published', lambda v: v[2]['buffer_viewport_observation']['failed_capture'].update(private_crop_published=True), False)
    run('reject_first_crop_unqualified', lambda v: v[2]['buffer_viewport_observation']['viewport_samples'][0].update(scope_checked_before_and_after=False), False)
    run('reject_crop_path_substitution', lambda v: v[2]['buffer_viewport_observation']['viewport_samples'][0]['private_crop'].update(path='/not-an-input.png'), False)
    run('reject_changed_coordinates_during_second_capture', lambda v: v[2]['buffer_viewport_observation']['viewport_samples'][1]['after_observation']['proof'].update(crop=[0, 45, 1200, 720]), False)
    print(json.dumps({'schema': 1, 'state': 'PASS', 'controls': rows,
          'scope': 'actual validate_observations on retained safe JSON and explicit negative mutations',
          'original_attempt_remains_failed': True, 'PNG_or_commercial_tree_read': False,
          'private_copy_or_chown_or_namespace_or_Android_operations': 0}, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
