#!/usr/bin/env python3
"""Offline link-policy controls only; do not invoke main, HTTP, or Pocket4."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
source = (HERE / 'read_ihg_public_pages_once.py').read_bytes()
ns = {'__name__': 'page_probe_under_test'}
exec(compile(source, str(HERE / 'read_ihg_public_pages_once.py'), 'exec'), ns)
before = ns['census']()
variant = ns['VARIANT_URL']
current = variant + 'download/?key=synthetic_current_key'
cases = []


def rejected(name, call):
    try:
        call()
    except (RuntimeError, ValueError):
        cases.append({'name': name, 'passed': True})
        return
    raise AssertionError(name)


raw = ('<html><title>IHG 5.110.0</title><a href="' + current + '">Download APK</a></html>').encode()
assert ns['select_intermediate'](raw)['literal_intermediate_url'] == current
assert b'b0b3cbac8065608f28b9e64014b145770202a52a' not in source
cases.append({'name': 'fresh_literal_selected_no_historical_key_in_source', 'passed': True})
rejected('wrong_host_not_selected', lambda: ns['select_intermediate'](raw.replace(b'www.apkmirror.com', b'example.invalid')))
rejected('multiple_distinct_keys_rejected', lambda: ns['select_intermediate'](raw + raw.replace(b'synthetic_current_key', b'another_key')))
rejected('challenge_rejected', lambda: ns['select_intermediate'](raw.replace(b'IHG 5.110.0', b'Just a moment...')))
rejected('extra_query_not_accepted', lambda: ns['select_intermediate'](raw.replace(b'synthetic_current_key', b'synthetic_current_key&amp;unexpected=1')))
delivery = ns['select_unfetched_delivery'](b'<a href="https://files.example.invalid/file.apk">here</a>', current)
assert delivery['delivery_url_followed'] is False and delivery['needs_separate_bounded_acquisition_request'] is True
cases.append({'name': 'delivery_anchor_only_recorded_not_followed', 'passed': True})
rejected('insecure_final_literal_rejected', lambda: ns['select_unfetched_delivery'](b'<a href="http://files.example.invalid/file.apk">here</a>', current))
after = ns['census']()
assert before == after
print(json.dumps({'schema': 'pocket4-ihg-public-page-link-offline-controls-v1', 'ok': True,
                  'source': {'bytes': len(source), 'sha256': hashlib.sha256(source).hexdigest()},
                  'cases': cases, 'descriptor_identities_before': before, 'descriptor_identities_after': after,
                  'HTTP_requests': 0, 'remote_processes': 0, 'APK_downloads': 0,
                  'Main_actions': 0, 'production_candidate_qualified': False}, sort_keys=True))
