#!/usr/bin/env python3
"""Derive a public metadata-only receipt from exact private historical output."""
from pathlib import Path
import hashlib
import json

ROOT = Path('/workspace/scratch/265e5bca485a')
HERE = ROOT / 'pocket4_eight_apps/successor_qa/inspect_after_search_rejection_reader_r1'
PRIVATE = ROOT / 'p4_private_ui/beike-inspect-after-search-rejection-r1/stdout.private.original.json'


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    raw = PRIVATE.read_bytes()
    assert pin(raw) == {'bytes': 243223, 'sha256': '0b84a4a9df176ce1bc0ceffa1cb2600e6e96dc7bf1dc2426333cd577febb89f1'}
    terminal_raw = (HERE / 'actual-public/status-01.original.txt').read_bytes()
    terminal = json.loads(terminal_raw)
    data = json.loads(raw)
    assert terminal['job_id'] == '1a1b295db9e-fc05-7ec9'
    assert terminal['state'] == 'succeeded' and terminal['exit_code'] == 0
    assert all(terminal[k] is True for k in ('audit_recorded', 'output_complete', 'output_durable', 'terminal_publication_confirmed'))
    assert all(terminal[k] is False for k in ('timed_out', 'cancelled', 'automatic_retry'))
    assert terminal['log_bytes'] == {'stdout': {'seen': len(raw), 'stored': len(raw)}, 'stderr': {'seen': 0, 'stored': 0}}
    assert terminal['log_synced'] == {'stdout': True, 'stderr': True}
    assert terminal['log_truncated'] == {'stdout': False, 'stderr': False}
    assert terminal['log_errors'] == {'stdout': None, 'stderr': None}
    assert data['ok'] and data['complete_original_tree'] and data['all_file_bytes_and_stat_rechecked']
    assert data['process_fds_before'] == data['process_fds_after'] and data['whole_process_fd_identities_unchanged']
    assert data['current_action_authority'] is False and data['production_ready'] is False
    nodes = data['selected_visible_nonpassword_nodes']
    search = [n for n in nodes if n['resource_id'] == 'com.lianjia.beike:id/tv_nav_right_search_text'
              and n['class'] == 'android.widget.TextView' and n['text'] == '搜索'
              and n['enabled'] and n['visible'] and n['clickable'] and not n['password']
              and n['all_four_string_fields_untruncated']]
    result = {
        'schema': 'pocket4-historical-inspect-reader-public-derived-summary-v1',
        'kind': 'LOCAL_DERIVED_FROM_EXACT_ACTUAL_OUTPUT',
        'reader_job': terminal['job_id'], 'reader_terminal': pin(terminal_raw),
        'reader_stdout_private_original': pin(raw),
        'historical_job': data['historical_job'], 'flow': data['flow'], 'step': data['step'],
        'historical_task': data['historical_task'], 'nonce': data['nonce'], 'wire_sha256': data['wire_sha256'],
        'original_files_count': data['original_files_count'], 'original_files_bytes': data['original_files_bytes'],
        'all_original_node_count': data['all_original_node_count'],
        'visible_nonpassword_node_count': len(nodes),
        'omitted_invisible_or_password_nodes': data['omitted_invisible_or_password_nodes'],
        'all_original_bytes_and_stat_rechecked': True, 'original_command_lifetime_rechecked': True,
        'whole_process_fd_identities_unchanged': True,
        'home_search_selector_exact_match_count': len(search),
        'editable_visible_nonpassword_nodes': sum(n['editable'] for n in nodes),
        'private_UI_text_or_nodes_included': False,
        'new_live_observation': False, 'new_UI_action': False,
        'old_failed_case_or_UNKNOWN_modified': False, 'reconciliation_published': False,
        'current_action_authority': False, 'production_ready': False,
        'limitations': ['Historical inspection content only; this reader is not a fresh foreground check.',
                       'A visible home search control does not demonstrate search results, business success, or network health.'],
    }
    assert len(search) == 1
    out = json.dumps(result, ensure_ascii=False, indent=2).encode() + b'\n'
    (HERE / 'actual-public/ACTUAL_READER_SUMMARY.derived.json').write_bytes(out)
    print(json.dumps(pin(out)))


if __name__ == '__main__':
    main()
