#!/usr/bin/env python3
"""Small local controls; no claim to have read the private target inspection."""
import copy
import hashlib
import json
import os
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent


def main():
    module = runpy.run_path(str(HERE / 'read_completed_inspect878.py'), run_name='local_reader_definitions_only')
    before = module['census']()
    project = module['project_nodes']
    node = {'path': '0', 'node_sha256': '0' * 64, 'package': 'com.lianjia.beike',
            'visible': True, 'password': False, 'resource_id': 'fixture:id/field',
            'class': 'android.widget.EditText', 'text': '北京', 'content_desc': '',
            'resource_id_truncated': False, 'class_truncated': False,
            'text_truncated': False, 'content_desc_truncated': False,
            'editable': True, 'supports_set_text': True}
    selected, omitted = project({'nodes': [node]})
    assert selected[0]['text'] == '北京' and selected[0]['all_four_string_fields_untruncated'] is True and omitted == 0
    privacy = [{**node, 'password': True, 'text': 'must-never-appear'},
               {**node, 'visible': False, 'text': 'must-never-appear'}]
    selected, omitted = project({'nodes': privacy})
    assert selected == [] and omitted == 2
    truncated = {**node, 'text_truncated': True}
    selected, omitted = project({'nodes': [truncated]})
    assert selected[0]['text'] == '北京' and selected[0]['text_truncated'] is True
    assert selected[0]['all_four_string_fields_untruncated'] is False and 'text' not in selected[0]['usable_exact_selector_fields']
    malformed = copy.deepcopy(node)
    del malformed['text_truncated']
    try:
        project({'nodes': [malformed]})
    except RuntimeError as error:
        assert str(error) == 'ORIGINAL_STRING_AND_TRUNCATION_FLAG_REQUIRED'
    else:
        raise AssertionError('missing truncation evidence was accepted')
    packet = json.loads((HERE / 'process-request.review-only.json').read_bytes())
    assert packet['args'] == ['-n', '/usr/bin/python3', '-I', '-B', '-c', (HERE / 'read_completed_inspect878.py').read_text()]
    assert packet['timeout_seconds'] == 120 and packet['memory_max_bytes'] == 268435456
    assert len(module['ALLOWED_PATHS']) == 21
    assert all('/steps/' not in path or '/steps/inspect-new-session-01/' in path for path in module['ALLOWED_PATHS'])
    after = module['census']()
    assert before == after
    print(json.dumps({'schema': 'pocket4-inspect878-reader-local-boundaries-v1', 'ok': True,
        'actual_uid': os.getuid(), 'actual_euid': os.geteuid(), 'cases': [
            'public Chinese text preserved without extra truncation',
            'password and invisible nodes omitted',
            'original truncated value cannot be an exact text selector',
            'missing original truncation evidence rejected',
            'one exact finite historical step and source packet'],
        'case_count': 5, 'whole_process_fd_identities_unchanged': True,
        'process_fds_before': before, 'process_fds_after': after,
        'synthetic_nodes_are_control_fixtures_only': True, 'actual_private_tree_read': False,
        'Main_commands': 0, 'remote_submitted': False}, sort_keys=True))


if __name__ == '__main__':
    main()
