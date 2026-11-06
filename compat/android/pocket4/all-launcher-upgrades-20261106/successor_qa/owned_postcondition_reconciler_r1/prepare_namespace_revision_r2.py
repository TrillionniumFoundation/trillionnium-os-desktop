#!/usr/bin/env python3
"""Create an independent minimal revision from the frozen failed r1 source."""
import difflib
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE / 'host-stage-candidate-r1'
NEW = HERE / 'candidate-r2'
CORE_PIN = (23654, '4653c827e236680a227e50d739eaa45b4432126d5326c5bc38d184a58a31f3dc')
PRODUCER_PIN = (41581, 'b9944bfd05f3ed216e9a55c9933a51c00380f8b9b02f16d449104a5496a8484e')

ADDITION = '''# Only these records come from namespace FDs in the pinned R5 producer.
# R5 checks NS_GET_NSTYPE, proc namespace inode links and held process identity.
# fd_record also retains nsfs mtime as an observation, not namespace identity.
HELD_R5_SHA = '72cf33399ca3c280fc0c9288669f7d6c13d387e41b5fb930cf477f2b940f16b4'
NAMESPACE_NAMES = ('mnt', 'pid', 'uts', 'ipc', 'net', 'cgroup')
NAMESPACE_FD_KEYS = {'device', 'inode', 'mode', 'uid', 'gid', 'bytes', 'mtime_ns', 'nlink'}


def held_binding_identity(binding):
    """Copy one binding; project mtime only at eight proven namespace-FD sites.

    Original dictionaries and bytes are never changed. All namespace identity
    and metadata other than mtime, and every other binding field, stay exact.
    Type admission was performed by the frozen R5 NS_GET_NSTYPE checks; this
    function verifies their recorded inode links and closed fd_record shape.
    It does not itself acquire or qualify any live namespace.
    """
    need(type(binding) is dict and
         binding.get('schema') == 'pocket4-successor-held-binding-r5-v1' and
         binding.get('held_runtime_r5_sha256') == HELD_R5_SHA,
         'PINNED_R5_NAMESPACE_RECORD_PROVENANCE')
    target, classpath = binding.get('target'), binding.get('classpath')
    need(type(target) is dict and type(classpath) is dict and
         type(target.get('namespaces')) is dict and
         set(target['namespaces']) == set(NAMESPACE_NAMES) and
         type(target.get('init')) is dict and type(target['init'].get('ns')) is dict and
         set(target['init']['ns']) == set(NAMESPACE_NAMES) and
         type(classpath.get('zygote')) is dict and
         type(classpath['zygote'].get('namespaces')) is dict and
         classpath.get('schema') == 2 and classpath.get('main_classpath_read') is True,
         'CLOSED_R5_NAMESPACE_RECORD_LOCATIONS')
    need(classpath['zygote']['namespaces'].get('pid') == target['init']['ns']['pid'],
         'R5_ZYGOTE_INIT_PID_NAMESPACE_IDENTITY')
    projected = copy.deepcopy(binding)
    observations = {}

    def namespace_row(row, name, link, path):
        need(type(row) is dict and set(row) == NAMESPACE_FD_KEYS and
             all(type(value) is int and value >= 0 for value in row.values()) and
             row['inode'] > 0 and row['nlink'] > 0 and stat.S_ISREG(row['mode']),
             'CLOSED_NAMESPACE_FD_METADATA:' + path)
        match = re.fullmatch(re.escape(name) + r':\\[(\\d+)\\]', link) if type(link) is str else None
        need(match is not None and row['inode'] == int(match[1]),
             'NAMESPACE_FD_MATCHES_RECORDED_PROCESS_LINK:' + path)
        observations[path + '/mtime_ns'] = row.pop('mtime_ns')

    for name in NAMESPACE_NAMES:
        namespace_row(projected['target']['namespaces'][name], name, target['init']['ns'][name],
                      '/target/namespaces/' + name)
    namespace_row(projected['classpath'].get('command_mount_namespace'), 'mnt', target['init']['ns']['mnt'],
                  '/classpath/command_mount_namespace')
    namespace_row(projected['classpath'].get('zygote_mount_namespace'), 'mnt',
                  classpath['zygote']['namespaces'].get('mnt'), '/classpath/zygote_mount_namespace')
    need(projected['classpath']['command_mount_namespace'] == projected['target']['namespaces']['mnt'],
         'R5_COMMAND_MOUNT_RECORD_IS_THE_SAME_HELD_INIT_NAMESPACE')
    return projected, observations


def compare_held_bindings(left, right):
    """Exact cross-observation identity under the frozen namespace contract."""
    left_identity, left_times = held_binding_identity(left)
    right_identity, right_times = held_binding_identity(right)
    need(left_identity == right_identity, 'EXACT_R5_IDENTITY_EXCEPT_NAMESPACE_OBSERVATION_MTIME')
    observations = [{'path': path, 'left_mtime_ns': left_times[path], 'right_mtime_ns': right_times[path]}
                    for path in sorted(left_times)]
    return {'schema': 'pocket4-r5-namespace-identity-comparison-v1',
            'held_runtime_r5_sha256': HELD_R5_SHA,
            'canonical_identity_projection_sha256': sha(json.dumps(left_identity, ensure_ascii=True,
                sort_keys=True, separators=(',', ':'), allow_nan=False).encode()),
            'namespace_mtime_observations': observations,
            'namespace_mtime_differences': [row for row in observations if row['left_mtime_ns'] != row['right_mtime_ns']],
            'all_other_binding_fields_exactly_equal': True,
            'namespace_device_inode_mode_uid_gid_size_nlink_exactly_equal': True,
            'original_binding_objects_rewritten': False,
            'live_namespace_qualification_performed_by_comparison': False}


'''


def read_pin(filename, pin):
    raw = (OLD / filename).read_bytes()
    assert (len(raw), hashlib.sha256(raw).hexdigest()) == pin
    return raw.decode('utf-8')


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    NEW.mkdir(mode=0o700)
    old_core = read_pin('owned_postcondition_core.py', CORE_PIN)
    old_producer = read_pin('publish_owned_reconciliation.py', PRODUCER_PIN)
    core = replace_once(old_core, 'import datetime\n', 'import copy\nimport datetime\n')
    core = replace_once(core, 'def timestamp(value):\n', ADDITION + 'def timestamp(value):\n')
    core = replace_once(core,
        "need(binding == expected_binding and binding.get('schema') == 'pocket4-successor-held-binding-r5-v1' and",
        "need(binding.get('schema') == 'pocket4-successor-held-binding-r5-v1' and")
    core = replace_once(core, "         'EXACT_HELD_R5_RUNTIME_APP_CLASSPATH_BINDING')\n",
        "         'EXACT_HELD_R5_RUNTIME_APP_CLASSPATH_BINDING')\n"
        "    binding_comparison = compare_held_bindings(binding, expected_binding)\n")
    core = replace_once(core,
        "            'binding': binding, 'installed': installed, 'owned_task': launch}",
        "            'binding': binding, 'binding_comparison': binding_comparison,\n"
        "            'installed': installed, 'owned_task': launch}")
    core = replace_once(core,
        "    need(action['installed'] == observed['installed'] and action['owned_task'] == observed['owned_task'] and\n"
        "         action['binding'] == observed['binding'], 'NO_HELPER_TASK_OR_HELD_RUNTIME_CHANGE_BETWEEN_STEPS')",
        "    need(action['installed'] == observed['installed'] and action['owned_task'] == observed['owned_task'],\n"
        "         'NO_HELPER_OR_TASK_CHANGE_BETWEEN_STEPS')\n"
        "    binding_comparison = compare_held_bindings(action['binding'], observed['binding'])\n"
        "    binding_comparison['raw_held_binding_file_sha256'] = {\n"
        "        'left': action['files_sha256']['held-main-binding.json'],\n"
        "        'right': observed['files_sha256']['held-main-binding.json']}")
    core = replace_once(core,
        "            'raw_protocol_recomputed': True, 'complete_sequences_verified': True,",
        "            'held_binding_comparison': binding_comparison,\n"
        "            'raw_protocol_recomputed': True, 'complete_sequences_verified': True,")
    core_raw = core.encode()
    producer = replace_once(old_producer, 'CORE_BYTES = 23654\n', 'CORE_BYTES = ' + str(len(core_raw)) + '\n')
    producer = replace_once(producer, "CORE_SHA = '" + CORE_PIN[1] + "'\n",
        "CORE_SHA = '" + hashlib.sha256(core_raw).hexdigest() + "'\n")
    producer = replace_once(producer,
        "            'actual_execution_evidence': archive['execution'], 'matched': archive['offline']['matched'],",
        "            'actual_execution_evidence': archive['execution'], 'matched': archive['offline']['matched'],\n"
        "            'held_binding_comparison': archive['offline']['held_binding_comparison'],")
    producer = replace_once(producer,
        "                 'current_held_R5_runtime_app_task_helper_rechecked': True,",
        "                 'current_held_R5_runtime_app_task_helper_rechecked': True,\n"
        "                 'original_to_current_binding_comparisons': {\n"
        "                     'action': action['binding_comparison'], 'observation': observed['binding_comparison']},")
    for name, text in (('owned_postcondition_core.py', core), ('publish_owned_reconciliation.py', producer)):
        compile(text, name, 'exec')
        with (NEW / name).open('xb') as stream:
            stream.write(text.encode())
    diff = ''.join(difflib.unified_diff(old_core.splitlines(True), core.splitlines(True),
        fromfile='host-stage-candidate-r1/owned_postcondition_core.py', tofile='candidate-r2/owned_postcondition_core.py'))
    diff += ''.join(difflib.unified_diff(old_producer.splitlines(True), producer.splitlines(True),
        fromfile='host-stage-candidate-r1/publish_owned_reconciliation.py', tofile='candidate-r2/publish_owned_reconciliation.py'))
    with (NEW / 'SOURCE_DIFF.patch').open('xb') as stream:
        stream.write(diff.encode())
    print('Created candidate-r2; did not run a verifier, contact Main, or change frozen r1.')


if __name__ == '__main__':
    main()
