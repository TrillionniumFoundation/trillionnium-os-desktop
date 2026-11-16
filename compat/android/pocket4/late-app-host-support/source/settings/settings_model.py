"""Pure, bounded observations. Original source never establishes runtime success."""
import re

def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)

def expanded_component(value):
    package, activity = value.split('/', 1)
    return package + '/' + (package + activity if activity.startswith('.') else activity)

def exact_leaf(roots, task, component):
    row = roots.get(task)
    return bool(row and row['display'] == row['user'] == 0 and row['freeform']
        and len(row['children']) == 1 and row['children'][0]['id'] == task
        and row['children'][0]['user'] == 0
        and expanded_component(row['children'][0]['component']) == expanded_component(component))

def preserved_roots(before, after, owned):
    return {k: v for k, v in after.items() if k not in owned} == before

def focus_metadata(raw):
    focus_lines = [line.strip() for line in raw.splitlines() if 'mCurrentFocus=' in line]
    app_lines = [line.strip() for line in raw.splitlines() if 'mFocusedApp=' in line]
    focus = re.findall(r'mCurrentFocus=Window\{([0-9a-fA-F]+)\s+u(\d+)\s+([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)', raw)
    app = re.findall(r'mFocusedApp=ActivityRecord\{[^\n]*?\bu(\d+)\s+([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)\s+t(\d+)\b', raw)
    if len(set(focus_lines)) != 1 or len(set(app_lines)) != 1 or len(set(focus)) != 1 or len(set(app)) != 1:
        return {'verified': False, 'reason': 'FOCUS_OR_ACTIVITY_NOT_UNIQUE'}
    token, user, package, activity = focus[0]
    app_user, app_package, app_activity, task = app[0]
    return {'verified': user == app_user == '0' and package == app_package,
        'package': package, 'activity': activity, 'window_token': token.lower(),
        'focused_activity': app_activity, 'task': int(task), 'user': int(user)}

def page_content(nodes, route):
    visible = [n for n in nodes if n.get('package') == 'com.android.settings'
        and n.get('visible') is True and type(n.get('text')) is str and n['text'].strip()]
    labels = sorted({n['text'].strip() for n in visible})
    need(2 <= len(labels) <= 1024 and any(t in labels for t in route['titles']),
        'EXACT_SOURCE_PAGE_TITLE_AND_NONBLANK_ACTUAL_CONTENT_REQUIRED')
    return {'labels': labels, 'matching_original_titles': [t for t in route['titles'] if t in labels],
        'available': True, 'original_English_title_scope': True}

def rotation_widget(nodes):
    # This dedicated page has one original auto_rotate_main_switch or
    # auto_rotate_switch. The separate Face Detection toggle is never admitted.
    labels = [n for n in nodes if n.get('package') == 'com.android.settings'
        and n.get('visible') is True and n.get('text') == 'Use auto-rotate']
    switches = [n for n in nodes if n.get('package') == 'com.android.settings'
        and n.get('visible') is True and n.get('enabled') is True
        and n.get('checkable') is True and type(n.get('checked')) is bool
        and n.get('clickable') is True and type(n.get('bounds_array')) is list
        and len(n['bounds_array']) == 4 and type(n.get('resource-id')) is str and n['resource-id']]
    candidates = []
    for node in switches:
        if node.get('text') == 'Use auto-rotate' or node.get('content-desc') == 'Use auto-rotate':
            candidates.append(node); continue
        left, top, right, bottom = node['bounds_array']
        if any(type(n.get('bounds_array')) is list and len(n['bounds_array']) == 4
                and max(top, n['bounds_array'][1]) < min(bottom, n['bounds_array'][3])
                and n['bounds_array'][0] < right for n in labels):
            candidates.append(node)
    need(len(candidates) == 1, 'ONE_ACTUAL_ENABLED_CHECKABLE_AUTO_ROTATE_WIDGET_REQUIRED')
    node = candidates[0]
    selector = {'id': node['resource-id'], 'package': 'com.android.settings',
        'class': node['class'], 'enabled': True, 'clickable': True, 'checked': node['checked']}
    need(sum(all(n.get({'id': 'resource-id'}.get(k, k)) == v for k, v in selector.items())
        for n in nodes) == 1, 'AUTO_ROTATE_SELECTOR_MUST_BE_UNIQUE_IN_ACTUAL_TREE')
    return node, selector

def rotation_state(values, binder_raw, *, allow_transition=False):
    need(set(values) == {'accelerometer_rotation', 'user_rotation',
        'hide_rotation_lock_toggle_for_accessibility'}, 'EXACT_ROTATION_SETTING_READS')
    need(values['accelerometer_rotation'] in ('0', '1') and values['user_rotation'] in ('0', '1', '2', '3')
        and values['hide_rotation_lock_toggle_for_accessibility'] == '0',
        'EXPLICIT_SUPPORTED_ROTATION_PREIMAGE_NO_DEFAULT_WRITEBACK')
    binder = binder_raw.strip()
    need(binder == 'free' or re.fullmatch(r'lock [0-3]', binder), 'ORIGINAL_WM_BINDER_READ_FORMAT')
    enabled = values['accelerometer_rotation'] == '1'
    consistent = (binder == 'free') == enabled and (enabled or binder.startswith('lock ')
        and int(binder[-1]) == int(values['user_rotation']))
    need(allow_transition or consistent, 'SETTINGS_AND_WINDOW_MANAGER_ROTATION_DISAGREE')
    return {'settings': dict(values), 'binder': binder, 'auto_rotate': enabled,
        'consistency_verified': consistent}

def rotation_display(raw):
    # DisplayRotation.dump prints this exact pair. A single display rotation
    # block is required; multiple displays are not guessed or merged.
    blocks = list(re.finditer(r'^\s*DisplayRotation\s*$', raw, re.M))
    need(len(blocks) == 1, 'ONE_ACTUAL_DISPLAY_ROTATION_BLOCK_REQUIRED')
    text = raw[blocks[0].end():]
    rows = re.findall(r'^\s*mRotation=([0-3]) mDeferredRotationPauseCount=([0-9]+)\s*$', text, re.M)
    support = re.findall(r'^\s*mSupportAutoRotation=(true|false)\s*$', text, re.M)
    need(len(rows) == 1 and support == ['true'] and rows[0][1] == '0',
        'ACTUAL_SUPPORTED_UNPAUSED_DISPLAY_ROTATION_REQUIRED')
    return int(rows[0][0])

def same_rotation(first, second):
    return first == second

def permission_rows(raw):
    rows = sorted(line.strip() for line in raw.splitlines()
        if re.search(r'^\s+[A-Za-z][A-Za-z0-9_.]*: granted=(?:true|false)(?:,|$)', line))
    need(rows, 'ACTUAL_SETTINGS_PERMISSION_STATE_REQUIRED')
    return rows
