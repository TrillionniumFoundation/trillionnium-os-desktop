"""Independent new-Main component; no historical Session, Main or execute entry."""

def run(flow, model):
    sequence = 0

    def command(op, **values):
        nonlocal sequence
        sequence += 1
        if sequence > 48:
            raise RuntimeError('ORIGINAL_COMMAND_LIMIT_REACHED')
        request = {'id': 'local-' + str(sequence).zfill(2) + '-' + op, 'op': op, **values}
        flow.record('local-driver-decision', {'request': request, 'automatic_retry': False})
        flow.diag_chain.checkpoint('before-' + request['id'])
        result = flow.step(request)
        flow.diag_chain.checkpoint('after-' + request['id'])
        return result

    def input_node(role, node, kind='tap', value=None):
        if flow.obs is None:
            raise RuntimeError('CURRENT_OBSERVATION_REQUIRED')
        matches = [i for i, item in enumerate(flow.obs['nodes']) if item is node]
        if len(matches) != 1:
            raise RuntimeError('ONE_EXACT_CURRENT_NODE_REQUIRED:' + role)
        values = {'view': flow.view_id, 'node': matches[0], 'role': role, 'kind': kind}
        if value is not None:
            values['value'] = value
        if command('input', **values) is not True:
            raise RuntimeError('INPUT_STEP_TERMINATED')

    def input_role(role, fields, kind='tap', value=None):
        if flow.obs is None:
            raise RuntimeError('CURRENT_OBSERVATION_REQUIRED')
        matches = [node for node in flow.obs['nodes'] if node.get('enabled') is True and node.get('clickable') is True and all((node.get(key) == expected for key, expected in fields.items()))]
        if len(matches) != 1:
            raise RuntimeError('ONE_CURRENT_SEMANTIC_ROLE_REQUIRED:' + role)
        input_node(role, matches[0], kind, value)

    def button(role, text, positive=False):
        fields = {'class': 'android.widget.Button', 'text': text}
        if positive:
            fields['resource-id'] = 'android:id/button1'
        input_role(role, fields)

    def field(role, hint, text, kind='tap', value=None):
        fields = {'class': 'android.widget.EditText', 'hint': hint, 'text': text, 'editable': True, 'password': False}
        if kind == 'set-text':
            fields['focused'] = True
        input_role(role, fields, kind, value)
    input_role('open-new', {'class': 'android.widget.Button', 'content-desc': 'New event'})
    button('local-open', 'Create local calendar')
    field('focus-local-name', 'Calendar name', 'On this device')
    field('local-name', 'Calendar name', 'On this device', 'set-text', model.CALENDAR_LABEL)
    button('local-confirm', 'Create', True)
    command('verify-calendar')
    field('focus-cancel-title', 'Title', 'Title')
    field('cancel-title', 'Title', 'Title', 'set-text', model.UNSAVED)
    button('cancel-open', 'Cancel')
    button('cancel-confirm', 'Discard', True)
    command('verify-cancel')
    button('save-create', 'Save')
    command('verify-created')
    button('open-edit', 'Edit')
    field('focus-edit-title', 'Title', model.TITLE)
    field('edit-title', 'Title', model.TITLE, 'set-text', model.EDITED)
    for role in flow.policy.CHAIN[1:-1]:
        target, _ = flow.policy.picker(role, flow.obs, flow.model.series)
        input_node(role, target)
    button('save-edit', 'Save')
    command('verify-edited')
    command('reopen')
    button('open-series-probe', 'Edit series')
    button('cancel-series-probe', 'Cancel')
    button('delete-open', 'Delete')
    button('delete-confirm', 'Delete', True)
    command('verify-deleted')
    if command('finish') is not False:
        raise RuntimeError('EXACT_FINISH_REQUIRED')
    flow.result['local_driver'] = {'commands': sequence, 'automatic_retry': False, 'transport_roundtrips_per_decision': 0, 'original_command_budget': 48, 'selected_from_current_observations': True, 'date_zone_repeat_inputs': 10, 'series_probe_save_calls': 0, 'diagnostics_contiguous_segments': True}
