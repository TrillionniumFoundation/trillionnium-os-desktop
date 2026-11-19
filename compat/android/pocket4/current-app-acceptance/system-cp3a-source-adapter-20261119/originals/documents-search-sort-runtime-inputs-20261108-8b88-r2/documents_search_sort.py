"""The two original Features10 omissions, under the unchanged case budget.

Sorting changes only the observed sort setting and restores its initial value.
Search uses native provider-root semantics and the existing GET_CONTENT round.
The original helper checks the exact owned URI before opening its contents.
No provider listing, arbitrary query, extra viewer or cleanup replay is added.
"""
import copy
import time
from urllib.parse import quote

DOCS = 'com.android.documentsui'
FILES = (DOCS, DOCS + '.files.FilesActivity')
PICKER = (DOCS, DOCS + '.picker.PickActivity')
NAME_ASC = 'File name (A to Z)'
NAME_DESC = 'File name (Z to A)'
SORT_CHOICES = frozenset((NAME_ASC, NAME_DESC, 'Type (A to Z)', 'Type (Z to A)',
    'Size (smallest first)', 'Size (largest first)', 'Modified (oldest first)', 'Modified (newest first)'))
SEARCH_EDITORS = frozenset((DOCS + ':id/search_src_text', DOCS + ':id/docked_search_text'))
QUERY_LABEL = 'search-exact-alpha-query'


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def box(node):
    value = node.get('bounds_array')
    need(type(value) is list and len(value) == 4 and all(type(x) is int for x in value)
         and value[0] < value[2] and value[1] < value[3], 'ACTUAL_NONEMPTY_NODE_RECTANGLE')
    return value


def contains(outer, inner):
    return outer[0] <= inner[0] < inner[2] <= outer[2] and outer[1] <= inner[1] < inner[3] <= outer[3]


def same_connection(node, anchor):
    return type(node.get('window_id')) is int and node['window_id'] >= 0 and node['window_id'] == anchor.get('window_id')


def one(obs, predicate, reason):
    found = [node for node in obs['nodes'] if predicate(node)]
    need(len(found) == 1, reason)
    return found[0]


def sort_items(obs):
    """Both pinned legacy and M3 layouts use this same list and item ID."""
    panel = one(obs, lambda n: n.get('package') == DOCS and n.get('resource-id') == DOCS + ':id/sorting_dialog_list'
        and n.get('class') == 'android.widget.ListView' and n.get('visible') is True
        and n.get('enabled') is True, 'ONE_ACTUAL_SORT_DIALOG_LIST')
    rectangle = box(panel)
    items = [n for n in obs['nodes'] if n.get('package') == DOCS and n.get('resource-id') == 'android:id/text1'
        and n.get('class') == 'android.widget.CheckedTextView' and n.get('visible') is True
        and n.get('enabled') is True and same_connection(n, panel) and contains(rectangle, box(n))]
    need(2 <= len(items) <= len(SORT_CHOICES) and all(n.get('text') in SORT_CHOICES
        and type(n.get('checked')) is bool and n.get('editable') is False for n in items)
        and len({n['text'] for n in items}) == len(items), 'ONLY_ORIGINAL_VISIBLE_SORT_CHOICES')
    checked = [n for n in items if n['checked']]
    need(len(checked) == 1, 'ONE_VISIBLE_CURRENT_SORT_CHOICE_REQUIRED')
    by_name = {n['text']: n for n in items}
    need(NAME_ASC in by_name and NAME_DESC in by_name, 'BOTH_NAME_DIRECTIONS_MUST_BE_VISIBLE')
    return by_name, checked[0]['text']


def visible_file_order(obs, rows, names):
    """Read positions of both unique generated file rows, never tree order."""
    need(len(rows) == 2 and len(names) == 2 and len(set(names)) == 2, 'TWO_DISTINCT_OWNED_FILE_ROWS')
    pairs = list(zip(names, rows))
    for name, row in pairs:
        label = one(obs, lambda n: n.get('package') == DOCS and n.get('text') == name
            and n.get('editable') is False and n.get('visible') is True, 'ONE_VISIBLE_OWNED_SORT_NAME')
        need(row.get('resource-id') == DOCS + ':id/item_root' and same_connection(row, label)
            and contains(box(row), box(label)), 'SORT_NAME_IN_ITS_ACTUAL_ROW')
    a, b = box(rows[0]), box(rows[1])
    need(same_connection(rows[0], rows[1]), 'SORT_ROWS_FROM_ONE_NATIVE_CONNECTION')
    if a[3] <= b[1] or b[3] <= a[1]:
        return [name for name, _ in sorted(pairs, key=lambda item: box(item[1])[1])]
    need(a[1] == b[1] and a[3] == b[3] and (a[2] <= b[0] or b[2] <= a[0]),
        'NONOVERLAPPING_SINGLE_VISIBLE_SORT_ROW_OR_COLUMN')
    return [name for name, _ in sorted(pairs, key=lambda item: box(item[1])[0])]


def editor(obs, expected, *, focused=False):
    return one(obs, lambda n: n.get('package') == DOCS and n.get('resource-id') in SEARCH_EDITORS
        and n.get('class') in ('android.widget.EditText', 'android.widget.AutoCompleteTextView')
        and n.get('editable') is True and n.get('password') is False and n.get('enabled') is True
        and n.get('visible') is True and n.get('text') == expected
        and (not focused or n.get('focused') is True), 'ONE_EXACT_NATIVE_SEARCH_EDITOR')


def root_option(obs, root_title):
    """Never open a location menu. The new picker starts at the owned root.

    The pinned legacy path searches stack.root directly. V2 defaults to
    ROOT_FOLDER, and its optional dropdown renders that actual root title.
    A visible V2 location is required to remain the exact primary title.
    """
    candidates = [n for n in obs['nodes'] if n.get('resource-id') == DOCS + ':id/search_location_trigger']
    need(len(candidates) <= 1, 'NO_DUPLICATE_SEARCH_ROOT_OPTION')
    if candidates:
        node = candidates[0]
        need(node.get('package') == DOCS and node.get('visible') is True and node.get('enabled') is True
            and node.get('editable') is False and node.get('text') == root_title,
            'ONLY_THIS_PRIMARY_ROOT_SEARCH_OPTION')
        return {'kind': 'visible_native_root_option', 'node': copy.deepcopy(node)}
    need(not any(n.get('resource-id') in (DOCS + ':id/search_options_row', DOCS + ':id/search_options_container')
        and n.get('visible') is True for n in obs['nodes']), 'VISIBLE_V2_OPTIONS_REQUIRE_VISIBLE_PRIMARY_ROOT')
    return {'kind': 'pinned_legacy_or_default_ROOT_FOLDER', 'native_location_option_visible': False,
            'scope_basis': 'fresh exact-INITIAL_URI picker; no location action; pinned current-root source branch'}


class SearchSort:
    def __init__(self, flow):
        self.f = flow
        self.sort_started = self.sort_completed = False
        self.initial_sort = None
        self.sort_setting_may_differ = False
        self.query_attempted = self.query_dispatch_open = self.query_acknowledged = False
        self.result_selected = self.search_completed = False
        self.search_focus = self.search_node = self.query_receipt = self.search_observation = None
        self.sort_proof = []
        self.root_metadata = None

    def record(self, label, value):
        self.f.ui.record(label, value)

    def namespace(self, label):
        f = self.f
        expected = {f.scope.SOURCE, f.scope.COPIES, f.scope.ALPHA, f.scope.BETA}
        need(f.tree.expected == expected and f.operation_pending is None, 'EXACT_FOUR_POST_MOVE_OWNED_ENTRIES')
        return f.tree.expect(expected, label)

    def checked_dialog(self, obs, label):
        f = self.f
        need((obs['focus']['package'], obs['focus']['activity']) == FILES and not obs['focus'].get('popup')
            and not f.ui.pending and not f.helper_pending, 'SORT_ONLY_IN_OWNED_FILES_MAIN_WINDOW')
        f.rows(obs, {f.scope.SOURCE, f.scope.COPIES, f.scope.ALPHA, f.scope.BETA})
        self.namespace(label + '-before')
        f.ui.input(obs, label + '-overflow', f.more(obs), popup=True)
        menu = f.ui.observe(label + '-menu', [FILES])
        need(menu['focus'].get('popup') is True, 'SORT_MENU_REQUIRES_SOURCE_BOUND_POPUP')
        item = f.control(menu, 'Sort by...')
        need(item.get('package') == DOCS and item.get('visible') is True, 'ACTUAL_DOCUMENTS_SORT_MENU_ITEM')
        f.ui.input(menu, label + '-open', item)
        dialog = f.ui.observe(label + '-dialog', [FILES])
        need(not dialog['focus'].get('popup'), 'ACTUAL_OWNED_SORT_DIALOG_WINDOW')
        items, selected = sort_items(dialog)
        self.record(label + '-current-selection', {'selected': selected, 'visible_options': copy.deepcopy(items),
            'focus': dialog['focus'], 'frame_sha256': dialog['screenshot']['frame_sha256']})
        return dialog, items, selected

    def choose_sort(self, dialog, items, choice, label):
        need(choice in items, 'ONLY_CURRENT_VISIBLE_SORT_OPTION')
        self.sort_setting_may_differ = True
        self.f.ui.input(dialog, label + '-select', items[choice])
        out = self.f.ui.observe(label + '-after', [FILES])
        need(not out['focus'].get('popup'), 'SORT_DIALOG_CLOSED_TO_OWNED_FILES')
        self.namespace(label + '-namespace')
        return self.f.completed_operation_observation(out, '',
            {self.f.scope.SOURCE, self.f.scope.COPIES, self.f.scope.ALPHA, self.f.scope.BETA}, label)

    def visible_order(self, obs, expected, label):
        f = self.f
        f.rows(obs, {f.scope.SOURCE, f.scope.COPIES, f.scope.ALPHA, f.scope.BETA})
        actual = visible_file_order(obs, [f.row(obs, f.scope.ALPHA), f.row(obs, f.scope.BETA)],
                                    [f.scope.ALPHA, f.scope.BETA])
        need(actual == expected, 'NATIVE_VISIBLE_SORT_ORDER_NOT_VERIFIED')
        proof = {'visible_order': actual, 'focus': obs['focus'], 'frame_sha256': obs['screenshot']['frame_sha256'],
                 'file_rows': [copy.deepcopy(f.row(obs, name)) for name in actual],
                 'owned_bytes_and_births': self.namespace(label + '-known-bytes'), 'input_ACK_alone_used': False}
        self.sort_proof.append(proof)
        self.record(label + '-visible-order', proof)

    def sort(self, obs):
        f = self.f
        need(not self.sort_started and not self.query_attempted, 'SORT_SEQUENCE_ONCE_BEFORE_SEARCH')
        self.sort_started = True
        obs = f.root_directory(obs, 'sort-owned-root')
        dialog, items, self.initial_sort = self.checked_dialog(obs, 'sort-initial')
        obs = self.choose_sort(dialog, items, NAME_ASC, 'sort-ascending')
        self.visible_order(obs, [f.scope.ALPHA, f.scope.BETA], 'sort-ascending')
        dialog, items, selected = self.checked_dialog(obs, 'sort-ascending-readback')
        need(selected == NAME_ASC, 'NATIVE_ASCENDING_SELECTION_READBACK')
        obs = self.choose_sort(dialog, items, NAME_DESC, 'sort-descending')
        self.visible_order(obs, [f.scope.BETA, f.scope.ALPHA], 'sort-descending')
        dialog, items, selected = self.checked_dialog(obs, 'sort-descending-readback')
        need(selected == NAME_DESC, 'NATIVE_DESCENDING_SELECTION_READBACK')
        obs = self.choose_sort(dialog, items, self.initial_sort, 'sort-restore-original')
        dialog, items, selected = self.checked_dialog(obs, 'sort-original-readback')
        need(selected == self.initial_sort, 'NATIVE_ORIGINAL_SORT_RESTORED')
        # The original source dismisses the sheet after choosing even the same
        # current value. This known action is never retried following UNKNOWN.
        obs = self.choose_sort(dialog, items, self.initial_sort, 'sort-close-verified-original')
        self.sort_setting_may_differ = False
        self.sort_completed = True
        f.gate('FILES_VISIBLE_SORT', {'directions': self.sort_proof, 'original_choice': self.initial_sort,
            'restored_choice': selected, 'restoration_actual_checked_readback': True,
            'scope': 'two generated text files in the same owned root; native visible geometry',
            'maximum_UI_actions_unchanged': 80, 'automatic_retry': False})
        return obs

    def admit_query(self, request):
        """Called by the source-pinned session at the actual dispatch boundary."""
        f = self.f
        need(self.query_dispatch_open and self.query_attempted and not self.query_acknowledged
            and self.search_node is not None and f.ui.pending == {QUERY_LABEL: {'input_acknowledged': False, 'kind': 'set-text'}}
            and f.s.last_focus == self.search_focus and (self.search_focus['package'], self.search_focus['activity']) == PICKER,
            'ONE_FRESH_OWNED_SEARCH_TEXT_DISPATCH')
        node = self.search_node
        expected = {'package': DOCS, 'class': node['class'], 'editable': True, 'enabled': True,
                    'focused': True, 'id': node['resource-id'], 'text': ''}
        need(request == {'op': 'set-text', 'package': DOCS, 'display': 0, 'accessibility_mode': 'none',
            'window_token': self.search_focus['window_token'], 'selector': expected, 'value': f.scope.ALPHA},
            'ONLY_CURRENT_FULL_RANDOM_ALPHA_QUERY')

    def query(self, obs):
        f = self.f
        need(self.sort_completed and not self.query_attempted and not f.ui.pending
            and f.helper_pending == {'client_action': 'get-owned-alpha', 'previous_phase': 'DENIED_OBSERVED'}
            and (obs['focus']['package'], obs['focus']['activity']) == PICKER and not obs['focus'].get('popup'),
            'SEARCH_ONLY_ONCE_IN_ORIGINAL_GET_CONTENT_ROUND')
        f.location(obs)
        self.namespace('search-owned-before')
        private = f.pkg.pref_state()
        need(private is not None and private.get('run') == f.scope.RUN
            and private.get('phase') == private.get('pending') == 'GET_ACCEPT_PENDING'
            and private.get('pending_request') == 54 and private.get('step_pending', '') == ''
            and private.get('error', '') == '' and private.get('get_content_results', 0) == 0,
            'EXACT_ORIGINAL_HELPER_AWAITS_ONE_GET_RESULT')
        self.root_metadata = f.primary_root_metadata('search-same-primary')
        root_option(obs, self.root_metadata['title'])
        editors = [n for n in obs['nodes'] if n.get('resource-id') in SEARCH_EDITORS]
        if editors:
            current = editor(obs, '')
            if current.get('focused') is not True:
                f.ui.input(obs, 'search-focus-empty-editor', current)
                obs = f.ui.observe('search-empty-focused-editor', [PICKER])
        else:
            trigger = one(obs, lambda n: n.get('package') == DOCS and n.get('resource-id') in
                (DOCS + ':id/option_menu_search', DOCS + ':id/search_button') and n.get('enabled') is True
                and n.get('visible') is True and n.get('clickable') is True and n.get('editable') is False
                and n.get('content-desc', n.get('text')) in ('Search', 'Search files'), 'ONE_ACTUAL_NATIVE_SEARCH_TRIGGER')
            f.ui.input(obs, 'search-expand-empty-query', trigger)
            obs = f.ui.observe('search-expanded-empty-query', [PICKER])
        self.search_node = copy.deepcopy(editor(obs, '', focused=True))
        self.search_focus = copy.deepcopy(obs['focus'])
        root_option(obs, self.root_metadata['title'])
        self.query_attempted = self.query_dispatch_open = True
        try:
            reply = f.ui.input(obs, QUERY_LABEL, self.search_node, kind='set-text', value=f.scope.ALPHA)
        finally:
            self.query_dispatch_open = False
        need(reply.get('ok') is True and reply.get('performed') == 'set-text' and reply.get('readback_verified') is True
            and reply.get('outcome_unknown') is not True, 'SEARCH_TEXT_REQUIRES_ACTUAL_NATIVE_ACK')
        self.query_receipt = copy.deepcopy(f.s.completed_inputs.get(QUERY_LABEL))
        need(self.query_receipt is not None and self.query_receipt['phase'] == f.s.phase_ref,
            'SEARCH_QUERY_FROM_CURRENT_PHASE_NATIVE_ACK_RECEIPT')
        self.query_acknowledged = True
        self.record('search-query-acknowledged', {'text': f.scope.ALPHA, 'input': self.query_receipt,
            'provider_root': self.root_metadata, 'actual_query_scope': 'provider root primary, not a subdirectory filter',
            'source_scope_claim': 'search initiated from the exact owned folder; only the exact owned result is accepted',
            'other_provider_or_account_selection': False, 'automatic_retry': False})
        return self.results()

    def results(self):
        f = self.f
        need(self.query_acknowledged and not self.result_selected, 'NO_RESULT_SELECTION_WITHOUT_QUERY_ACK')
        previous = None
        end = min(time.monotonic() + 20, f.s.deadline)
        for index in range(4):
            need(time.monotonic() < end, 'EXACT_SEARCH_RESULT_DID_NOT_SETTLE')
            obs = f.ui.observe('search-owned-result-' + str(index + 1), [PICKER])
            need(obs['focus'] == self.search_focus and not f.ui.pending, 'SEARCH_RESULT_WINDOW_OR_ACK_CHANGED')
            entry = editor(obs, f.scope.ALPHA)
            root = root_option(obs, self.root_metadata['title'])
            rows = [n for n in obs['nodes'] if n.get('resource-id') == DOCS + ':id/item_root']
            if not rows:
                self.record('search-result-not-yet-visible', {'index': index + 1, 'input_replayed': False})
                previous = None
                continue
            need(len(rows) == 1, 'ONLY_ONE_SEARCH_RESULT_MAY_BE_INSPECTED_OR_SELECTED')
            row = f.row(obs, f.scope.ALPHA)
            need(row == rows[0] and same_connection(row, entry), 'SOLE_EXACT_OWNED_SEARCH_NAME')
            self.namespace('search-result-known-bytes-' + str(index + 1))
            value = {'row': {k: v for k, v in row.items() if k != 'window_id'},
                     'query_editor': {k: v for k, v in entry.items() if k != 'window_id'},
                     'focus': obs['focus'], 'scope': {k: v for k, v in obs['screenshot']['scope'].items() if k != 'window_id'}}
            self.record('search-result-source-readback', {'index': index + 1, 'native_row': row,
                'query_editor': entry, 'root': root, 'focus': obs['focus'],
                'frame_sha256': obs['screenshot']['frame_sha256'], 'URI_or_contents_read_by_controller': False})
            if previous == value:
                self.search_observation = {'row': copy.deepcopy(row), 'query_editor': copy.deepcopy(entry),
                    'focus': copy.deepcopy(obs['focus']), 'root': root,
                    'frame_sha256': obs['screenshot']['frame_sha256'], 'two_native_observations_equal': True}
                return obs
            previous = value
        raise RuntimeError('EXACT_SEARCH_RESULT_DID_NOT_SETTLE')

    def select(self, obs):
        f = self.f
        need(self.query_acknowledged and not self.result_selected and self.search_observation is not None
            and not f.ui.pending and obs is f.ui.last and obs['focus'] == self.search_focus,
            'ONCE_CURRENT_SEARCH_RESULT_SELECTION')
        editor(obs, f.scope.ALPHA)
        root_option(obs, self.root_metadata['title'])
        rows = [n for n in obs['nodes'] if n.get('resource-id') == DOCS + ':id/item_root']
        row = f.row(obs, f.scope.ALPHA)
        need(rows == [row], 'NO_OTHER_NATIVE_SEARCH_ROWS')
        self.namespace('search-before-exact-result-selection')
        self.result_selected = True
        return f.ui.input(obs, 'select-get-content-alpha', row)

    def complete(self):
        f = self.f
        need(self.result_selected and not self.search_completed and not f.ui.pending and not f.helper_pending
            and f.last_status.get('phase') == 'GET_CONTENT_OK' and f.last_status.get('run') == f.scope.RUN
            and f.last_status.get('get_content_results') == 1 and f.last_status.get('content_readbacks') == 5
            and f.last_status.get('last_read_bytes') == 59 and f.last_status.get('last_read_sha256') == f.scope.ALPHA_SHA
            and f.last_status.get('persisted_grant_count') == 0
            and f.result['gates'].get('GET_CONTENT_EXACT_FILE_READ', {}).get('passed') is True,
            'ORIGINAL_EXACT_GET_CONTENT_PREDICATES_REQUIRED_FOR_SEARCH_CREDIT')
        identity = 'primary:' + f.scope.FOLDER + '/' + f.scope.ALPHA
        proof = {'query': f.scope.ALPHA, 'query_ACK': self.query_receipt,
            'visible_unique_result': self.search_observation, 'authority': 'com.android.externalstorage.documents',
            'provider_root_id': 'primary', 'provider_query_scope': 'root primary; no subdirectory isolation claimed',
            'owned_parent_document_id': 'primary:' + f.scope.FOLDER, 'owned_document_id': identity,
            'expected_returned_URI': 'content://com.android.externalstorage.documents/document/' + quote(identity, safe=''),
            'URI_evidence': 'unchanged helper onActivityResult requires value.equals(plain(ALPHA)) before metadata/openInputStream',
            'raw_returned_URI_serialized_by_original_helper': False,
            'original_helper_phase_and_counters': copy.deepcopy(f.last_status),
            'owned_name': f.scope.ALPHA, 'bytes': 59, 'sha256': f.scope.ALPHA_SHA,
            'same_original_GET_CONTENT_readback_reused': True,
            'additional_viewers_or_content_opens': 0, 'other_document_or_account_access': False,
            'unmatched_URI_opens_before_original_helper_rejection': 0,
            'physical_owned_identity': self.namespace('search-final-owned-identity')}
        self.search_completed = True
        f.gate('FILES_OWNED_SEARCH', proof)
        f.result['deferred_supported_features'] = []

    def state(self):
        return {'sort_started': self.sort_started, 'sort_completed': self.sort_completed,
            'original_sort': self.initial_sort, 'sort_setting_may_differ': self.sort_setting_may_differ,
            'query_attempted': self.query_attempted, 'query_acknowledged': self.query_acknowledged,
            'result_selected': self.result_selected, 'search_completed': self.search_completed,
            'automatic_retry': False, 'cleanup_replays_search_or_sort': False}
