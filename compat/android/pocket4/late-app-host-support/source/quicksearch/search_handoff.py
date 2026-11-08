"""Actual QSB result-to-browser ownership, separate from native-launch claims."""
import copy
import re
import unicodedata
from urllib.parse import parse_qs, urlsplit

def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)

def normalized(text):
    need(type(text) is str and 0 < len(text.encode('utf-8')) <= 4096, 'BOUNDED_REAL_QUERY_OR_RESULT')
    return unicodedata.normalize('NFKC', text).casefold()

def matching_labels(nodes, package, query):
    prefix = normalized(query)
    rows = [n for n in nodes if n.get('package') == package and n.get('resource-id') == package + ':id/text1'
        and n.get('visible') is True and n.get('enabled') is True and n.get('password') is False
        and n.get('class') == 'android.widget.TextView' and type(n.get('text')) is str and n['text']]
    return [copy.deepcopy(n) for n in rows if normalized(n['text']).startswith(prefix)]

def contains(outer, inner):
    return (type(outer) is list and type(inner) is list and len(outer) == len(inner) == 4
        and all(type(x) is int for x in outer + inner)
        and outer[0] <= inner[0] < inner[2] <= outer[2]
        and outer[1] <= inner[1] < inner[3] <= outer[3])

def stable_node(node):
    # UiAutomation connection window IDs may change between observations.
    # The real WindowManager token is checked separately at every input.
    return {k: v for k, v in node.items() if k != 'window_id'}

def stable_binding(binding):
    return {k: stable_node(v) if k in ('label', 'row', 'list') else v for k, v in binding.items()}

def row_binding(nodes, label, package, query):
    matches = matching_labels(nodes, package, query)
    same = [n for n in matches if n == label]
    need(len(same) == 1 and sum(n['text'] == label['text'] for n in matches) == 1,
        'ONE_KNOWN_VISIBLE_UNICODE_MATCHING_RESULT')
    bounds = label.get('bounds_array')
    rows = [n for n in nodes if n.get('package') == package and n.get('visible') is True
        and n.get('enabled') is True and n.get('clickable') is True
        and n.get('window_id') == label.get('window_id') and contains(n.get('bounds_array'), bounds)
        and n.get('resource-id') != package + ':id/icon2']
    need(len(rows) == 1, 'ONE_OBSERVED_RESULT_CLICK_CONTAINER')
    lists = [n for n in nodes if n.get('resource-id') == package + ':id/suggestions'
        and n.get('package') == package and n.get('visible') is True
        and n.get('window_id') == label.get('window_id') and contains(n.get('bounds_array'), rows[0]['bounds_array'])]
    need(len(lists) == 1, 'RESULT_INSIDE_ORIGINAL_SUGGESTIONS_LIST')
    point = [(bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2]
    refiners = [n for n in nodes if n.get('resource-id') == package + ':id/icon2'
        and n.get('package') == package and n.get('visible') is True
        and n.get('window_id') == label.get('window_id')]
    need(all(not (n['bounds_array'][0] <= point[0] < n['bounds_array'][2]
        and n['bounds_array'][1] <= point[1] < n['bounds_array'][3]) for n in refiners),
        'RESULT_TOUCH_MUST_NOT_HIT_REFINE_CONTROL')
    return {'query': query, 'result_text': label['text'], 'label': copy.deepcopy(label),
        'row': copy.deepcopy(rows[0]), 'list': copy.deepcopy(lists[0]), 'coords': point,
        'method': 'single fresh snapshot-bound touch on the actual result label'}

def expanded_component(component):
    package, activity = component.split('/', 1)
    return package + '/' + (package + activity if activity.startswith('.') else activity)

def exact_leaf(roots, task, component, *, native=False):
    row = roots.get(task)
    return bool(row and row['display'] == row['user'] == 0 and (not native or row['freeform'])
        and len(row['children']) == 1 and row['children'][0]['id'] == task
        and row['children'][0]['user'] == 0
        and expanded_component(row['children'][0]['component']) == expanded_component(component))

def preserved_roots(before, after, owned):
    return {k: v for k, v in after.items() if k not in owned} == before

def adopt(before_roots, before_tasks, after_roots, after_tasks, primary, target, browser, response, focus):
    need(response.get('ok') is True and response.get('performed') == 'snapshot-tap'
        and response.get('input_command_completed') is True,
        'ACTUAL_ONCE_RESULT_INPUT_COMMAND_MUST_HAVE_COMPLETED')
    need(response.get('outcome_unknown') is not True or response.get('post_action_observation_available') is False,
        'ONLY_RECORDED_POST_CAPTURE_UNCERTAINTY_CAN_BE_OBSERVED_WITHOUT_REPLAY')
    need(not any(c['component'].split('/')[0] == browser['package'] for r in before_roots.values() for c in r['children']),
        'PREEXISTING_BROWSER_TASK_CANNOT_BECOME_OWNED')
    added = set(after_tasks) - set(before_tasks)
    need(len(added) == 1 and set(after_tasks) == set(before_tasks) | added, 'EXACTLY_ONE_NEW_HANDOFF_TASK')
    task = next(iter(added))
    need(task not in before_roots and exact_leaf(after_roots, task, browser['component'])
        and exact_leaf(before_roots, primary, target['component'], native=True)
        and after_roots.get(primary) == before_roots[primary]
        and preserved_roots(before_roots, after_roots, {task}), 'ONLY_NEW_EXCLUSIVE_BROWSER_LEAF')
    need(focus.get('verified') is True and focus.get('task') == task and focus.get('user') == 0
        and expanded_component(focus['package'] + '/' + focus['activity']) == expanded_component(browser['component'])
        and expanded_component(focus['package'] + '/' + focus['focused_activity']) == expanded_component(browser['component']),
        'ACTUAL_FOCUSED_NEW_BROWSER_TASK')
    return {'task': task, 'primary_task': primary, 'package': browser['package'], 'uid': browser['uid'],
        'component': browser['component'], 'preexisting_task_ids': sorted(before_tasks),
        'actual_new_exclusive_leaf': True, 'native_launch_receipt': None,
        'ownership_basis': 'source-bound once result input plus exact before/after task delta and actual focus',
        'original_postcapture_unknown_retained': response.get('outcome_unknown') is True,
        'input_replayed': False, 'business_success_verified': False}

def search_url(uri, expected_query):
    need(type(uri) is str and 0 < len(uri.encode('utf-8')) <= 8192 and not any(x in uri for x in ('\r', '\n', '\x00')),
        'BOUNDED_ACTUAL_SEARCH_URL')
    value = urlsplit(uri); host = value.hostname
    # Original GoogleSearch domain helper may use regional google domains.
    need(value.scheme in ('http', 'https') and not value.username and not value.password
        and value.port in (None, 80, 443) and type(host) is str
        and re.fullmatch(r'(?:www\.)?google\.(?:com|[a-z]{2,3}|co\.[a-z]{2}|com\.[a-z]{2})', host)
        and value.path == '/search', 'ACTUAL_ORIGINAL_GOOGLE_SEARCH_DESTINATION')
    params = parse_qs(value.query, keep_blank_values=True, strict_parsing=True)
    need(params.get('q') == [expected_query], 'ACTUAL_OPENED_QUERY_MUST_MATCH_KNOWN_RESULT')
    return {'url': uri, 'query': expected_query, 'scheme': value.scheme, 'host': host,
        'original_query_utf8_roundtrip_verified': True}

def rendered_result(nodes, package, query):
    views = [n for n in nodes if n.get('package') == package and n.get('class') == 'android.webkit.WebView'
        and n.get('visible') is True and n.get('enabled') is True]
    need(views, 'ACTUAL_RESULT_WEBVIEW_DOCUMENT_NOT_YET_VISIBLE')
    content = [n for n in nodes if n.get('package') == package and n.get('visible') is True
        and n.get('resource-id') != package + ':id/url_field'
        and any(contains(v.get('bounds_array'), n.get('bounds_array')) for v in views)]
    texts = [text for n in content for text in (n.get('text'), n.get('content-desc')) if type(text) is str and text]
    need(texts and any(normalized(query) in normalized(text) for text in texts),
        'ACTUAL_QUERY_RELATED_DOCUMENT_CONTENT_NOT_YET_VISIBLE')
    error_words = ('net::err_', 'webpage not available', 'this site can’t be reached', 'this site cannot be reached')
    need(not any(any(error in text.casefold() for error in error_words) for text in texts),
        'BROWSER_ERROR_PAGE_IS_NOT_OPENED_RESULT_CONTENT')
    return {'query': query, 'webview_nodes': copy.deepcopy(views), 'visible_document_text': texts,
        'address_bar_alone_not_sufficient': True, 'actual_document_content_observed': True}

def branch_lines(raw, since, until, kind, *, before):
    need(kind in ('search_offline', 'search_error') and 0 <= since <= until and until - since <= 90,
        'BOUNDED_ACTUAL_QUERY_BRANCH_WINDOW')
    need(type(before) is str, 'ACTUAL_PRE_QUERY_LOG_PREIMAGE_REQUIRED')
    observed = []; timed = []; old_lines = set(before.splitlines())
    for line in raw.splitlines():
        m = re.fullmatch(r'\s*(\d+\.\d+)\s+(\d+)\s+(\d+)\s+([VDIWEAF])\s+GoogleSearch\s*:\s?(.*)', line)
        if m is None:
            continue
        when = float(m[1]); timed.append(when)
        if since <= when <= until and line not in old_lines:
            observed.append({'timestamp': m[1], 'pid': int(m[2]), 'tid': int(m[3]),
                'priority': m[4], 'message': m[5]})
    need(len(timed) < 512 or min(timed) <= since, 'FRESH_GOOGLESEARCH_BRANCH_LOG_TRUNCATED')
    if kind == 'search_offline':
        hits = [x for x in observed if x['priority'] == 'I' and x['message'] == 'Not connected to network.']
    else:
        hits = [x for x in observed if x['priority'] == 'W' and x['message'] == 'Error']
        exceptions = [x for x in observed if x['priority'] == 'W' and re.search(
            r'(?:java\.(?:io|net)\.[A-Za-z]+Exception|org\.json\.JSONException)', x['message'])]
        need(exceptions and any(x['pid'] == y['pid'] for x in hits for y in exceptions),
            'ACTUAL_ORIGINAL_IO_OR_JSON_FAILURE_REQUIRED')
    need(hits and len({x['pid'] for x in hits}) == 1, 'FRESH_ACTUAL_QUICKSEARCH_BRANCH_NOT_OBSERVED')
    return {'branch': kind.removeprefix('search_'), 'actual_app_log_rows': hits,
        'bounded_uid_filtered_read': True, 'environment_changed_by_runner': False,
        'current_query_request_correlation_verified': False,
        'scope': 'actual UID branch occurrence during the owned UI interval; no request identity is present in the original log',
        'source_only_facts_do_not_count_as_runtime_branch': True}
