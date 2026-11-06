#!/usr/bin/env python3
"""Compare already collected Beike trees offline; never infer an unexported tree."""
import base64
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
PRIVATE = PROJECT.parent / 'p4_private_ui'
BUNDLE = PRIVATE / 'beike-search-click-failure-bundle-r1/bundle.private.original.json'
BUNDLE_PIN = (1102634, '85b3b9801685a427a484cc81b80de64e66df49ceb477efa99901ac2dfb01cee4')
HISTORIES = (
    ('after-search-rejection', 'beike-inspect-after-search-rejection-r1/stdout.private.original.json',
     243223, '0b84a4a9df176ce1bc0ceffa1cb2600e6e96dc7bf1dc2426333cd577febb89f1'),
    ('after-partial-commit', 'beike-inspect-after-partial-commit-reader-r1/stdout.original.json',
     243205, '6a1c770b862a47a5a64021392e58e9b36a9bc583a261a7412333bf9355513790'),
)
INSPECT_NONCE = '125381751c22b0a94c1954d0ceddca92'
ACTION_NONCE = '15dfd62fe344b6e95aed66cef092b3cb'
SEARCH = {'resource_id': 'com.lianjia.beike:id/tv_nav_right_search_text',
          'class': 'android.widget.TextView', 'text': '\u641c\u7d22'}


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def read_pinned(path, size, digest):
    raw = path.read_bytes()
    need(len(raw) == size and sha(raw) == digest, 'EXACT_COLLECTED_PRIVATE_BYTES')
    return json.loads(raw)


def nodes_by_path(nodes):
    out = {}
    for source in nodes:
        node = {key: value for key, value in source.items()
                if key not in ('all_four_string_fields_untruncated', 'usable_exact_selector_fields')}
        path = node['path']
        need(path not in out and node['package'] == 'com.lianjia.beike', 'UNIQUE_BEIKE_NODE_PATH')
        body = {key: value for key, value in node.items() if key != 'node_sha256'}
        need(sha(canonical(body)) == node['node_sha256'], 'ORIGINAL_NODE_HASH_RECOMPUTED')
        out[path] = node
    return out


def compare(left, right):
    private_differences, public_differences = [], []
    fields = Counter()
    for path in sorted(set(left) | set(right)):
        a, b = left.get(path), right.get(path)
        keys = sorted(set(a or {}) | set(b or {}))
        changed = [key for key in keys if (a or {}).get(key) != (b or {}).get(key)]
        if changed:
            fields.update(changed)
            private_differences.append({'node_path': path, 'before': a, 'after': b, 'changed_fields': changed})
            public_differences.append({'node_path': path, 'before_present': a is not None, 'after_present': b is not None,
                                       'changed_fields': changed,
                                       'before_node_sha256': None if a is None else a['node_sha256'],
                                       'after_node_sha256': None if b is None else b['node_sha256']})
    return ({'left_visible_nodes': len(left), 'right_visible_nodes': len(right),
             'visible_path_sets_equal': set(left) == set(right), 'changed_visible_nodes': len(public_differences),
             'changed_fields_count': dict(fields), 'differences_without_private_values': public_differences}, private_differences)


def save_new(path, value):
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + '\n').encode('ascii')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    need(path.read_bytes() == raw, 'LOCAL_DERIVED_OUTPUT_READBACK')
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def main():
    bundle = read_pinned(BUNDLE, *BUNDLE_PIN)
    need(bundle['actual_job'] == '1a1b30305de-fc05-8072' and bundle['step'] == 'search-click-after-partial-commit-01' and
         bundle['approved_for_Git'] is False and len(bundle['files']) == 101, 'ONE_ORIGINAL_FAILED_CASE_BUNDLE')
    records = {}
    for key, row in bundle['files'].items():
        body = base64.b64decode(row['base64'], validate=True)
        need(len(body) == row['bytes'] and sha(body) == row['sha256'], 'ALL_ORIGINAL_RECORD_BYTES')
        records[key] = body
    def fixed_record(basename):
        matches = [(key, value) for key, value in records.items() if key.rsplit('/', 1)[-1] == basename]
        need(len(matches) == 1, 'ONE_EXACT_ASSESSMENT_RECORD')
        return json.loads(matches[0][1]), {'record': matches[0][0], 'bytes': len(matches[0][1]), 'sha256': sha(matches[0][1])}
    assessment, assessment_pin = fixed_record(INSPECT_NONCE + '.assessment.json')
    failure, failure_pin = fixed_record(ACTION_NONCE + '.failed-assessment.json')
    helper = assessment['helper']
    need(sha(canonical(helper)) == assessment['wire_sha256'] == '3d5cf94834c0a7234b9b0e364ebc35abd1329defada5ee26acc42a867672854e',
         'ACTUAL_PRE_ACTION_INSPECTION_WIRE')
    inspection = helper['inspection']
    need(inspection['complete'] is True and len(inspection['nodes']) == 245 and
         sha(canonical(inspection['nodes'])) == inspection['tree_sha256'] and
         sha(canonical(inspection['window'])) == inspection['window_sha256'], 'ACTUAL_COMPLETE_TREE_AND_STABLE_WINDOW_HASHES')
    all_nodes = nodes_by_path(inspection['nodes'])
    current = {path: node for path, node in all_nodes.items() if node['visible'] is True and node['password'] is False}
    search_nodes = [node for node in current.values() if all(node.get(key) == value for key, value in SEARCH.items())]
    need(len(search_nodes) == 1, 'ONE_OBSERVED_SEARCH_NODE')
    rejection = failure['helper_rejection']
    need(failure['qualified_success'] is False and rejection['error'] == 'INSPECTED_TREE_OR_WINDOW_CHANGED' and
         rejection['action_attempted'] is False and rejection['outcome_unknown'] is False, 'ORIGINAL_HELPER_REJECTION')
    public_pairs, private_pairs, history_pins = [], [], []
    for label, relative, size, digest in HISTORIES:
        history = read_pinned(PRIVATE / relative, size, digest)
        need(history['ok'] is True and history['all_original_node_count'] == 245, 'HISTORICAL_READER_SUCCESS')
        old = nodes_by_path(history['selected_visible_nonpassword_nodes'])
        public, private = compare(old, current)
        public.update(history=label, historical_tree_sha256=history['inspection_tree_sha256'],
                      current_tree_sha256=inspection['tree_sha256'], tree_hash_equal=history['inspection_tree_sha256'] == inspection['tree_sha256'],
                      stable_window_hash_equal=history['inspection_window_sha256'] == inspection['window_sha256'],
                      exact_search_node_equal=old.get(search_nodes[0]['path']) == search_nodes[0],
                      omitted_historical_nodes_reconstructed=False)
        public_pairs.append(public)
        private_pairs.append({'history': label, 'differences': private})
        history_pins.append({'label': label, 'path': str(PRIVATE / relative), 'bytes': size, 'sha256': digest})
    private_output = PRIVATE / 'beike-search-click-tree-comparison-r1'
    private_output.mkdir(mode=0o700)
    private_pin = save_new(private_output / 'node-differences.private.derived.json', private_pairs)
    result = {'schema': 'pocket4-beike-current-preinspection-to-history-field-comparison-v1',
              'bundle': {'path': str(BUNDLE), 'bytes': BUNDLE_PIN[0], 'sha256': BUNDLE_PIN[1]},
              'current_inspection_assessment': assessment_pin, 'failed_assessment': failure_pin,
              'current_inspection_nonce': INSPECT_NONCE, 'current_tree_sha256': inspection['tree_sha256'],
              'current_window_sha256': inspection['window_sha256'], 'current_node_count': len(all_nodes),
              'current_visible_nodes': len(current), 'current_connection_scoped_window_id': inspection['connection_scoped_window_id'],
              'history_inputs': history_pins, 'comparisons': public_pairs, 'private_differences': private_pin,
              'helper_reported_action_attempted': False, 'helper_reported_outcome_unknown': False,
              'original_outer_UNKNOWN_reclassified': False, 'rejected_current_tree_exported': False,
              'rejected_current_tree_or_window_specific_difference': 'UNKNOWN',
              'cross_connection_hash_includes_connection_id': False, 'specific_failed_action_root_cause_proven': False,
              'Main_commands': 0, 'UI_actions': 0, 'guard_changes': 0, 'production_ready': False}
    pin = save_new(HERE / 'CURRENT_PREINSPECTION_COMPARISON.derived.json', result)
    print(json.dumps({'analysis': pin, 'comparisons': public_pairs, 'specific_failed_action_root_cause_proven': False}, sort_keys=True))


if __name__ == '__main__':
    main()
