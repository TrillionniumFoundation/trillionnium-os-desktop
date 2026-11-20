"""Independent new-Main component; no historical Session, Main or execute entry."""
from datetime import date
PACKAGE = 'com.android.calendar'
EDITORS = {PACKAGE + '.event.EditEventActivity', PACKAGE + '.EditEventActivity'}
MOUSE_ROLES = {'start-date-step', 'end-date-step', 'timezone-option', 'repeat-open', 'repeat-option'}
DATE_CONFIRM_ROLES = {'start-date-confirm', 'end-date-confirm'}
NEW_ROLES = {'start-date-open', 'start-date-step', 'start-date-confirm', 'end-date-open', 'end-date-step', 'end-date-confirm', 'timezone-open', 'timezone-option', 'repeat-open', 'repeat-option'}
CHAIN = ('edit-title', 'start-date-open', 'start-date-step', 'start-date-confirm', 'end-date-open', 'end-date-step', 'end-date-confirm', 'timezone-open', 'timezone-option', 'repeat-open', 'repeat-option', 'save-edit')
MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')

def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)

def one(nodes, predicate, reason):
    values = [n for n in nodes if n.get('package') == PACKAGE and n.get('visible') is True and predicate(n)]
    need(len(values) == 1, reason)
    return values[0]

def inside(outer, inner):
    return isinstance(outer, list) and isinstance(inner, list) and (len(outer) == len(inner) == 4) and all((type(v) is int for v in outer + inner)) and (outer[0] <= inner[0] < inner[2] <= outer[2]) and (outer[1] <= inner[1] < inner[3] <= outer[3])

def number_date(nodes, plan, changed):
    """Match the three actual17 NumberPickers without guessing a day cell."""
    original = date.fromisoformat(plan['original_date'])
    target = date.fromisoformat(plan['target_date'])
    need(original.year == target.year and original.month == target.month and (abs((target - original).days) == 1), 'ONE_SAME_MONTH_DAY_CHANGE_REQUIRED')
    expected = target if changed else original
    container = one(nodes, lambda n: n.get('class') == 'android.widget.DatePicker' and n.get('resource-id') == 'android:id/datePicker' and (n.get('enabled') is True), 'ACTUAL_DATE_PICKER_REQUIRED')
    pickers = [n for n in nodes if n.get('package') == PACKAGE and n.get('visible') is True and (n.get('class') == 'android.widget.NumberPicker') and (n.get('enabled') is True) and (n.get('scrollable') is True) and inside(container.get('bounds_array'), n.get('bounds_array'))]
    need(len(pickers) == 3, 'EXACT_THREE_NUMBER_PICKERS_REQUIRED')
    inputs = []
    for number in pickers:
        values = [n for n in nodes if n.get('package') == PACKAGE and n.get('visible') is True and (n.get('class') == 'android.widget.EditText') and (n.get('enabled') is True) and (n.get('resource-id') == 'android:id/numberpicker_input') and (n.get('editable') is True) and (n.get('password') is False) and inside(number.get('bounds_array'), n.get('bounds_array'))]
        need(len(values) == 1, 'ONE_INPUT_IN_EACH_NUMBER_PICKER_REQUIRED')
        need(values[0].get('value') == values[0].get('text'), 'NUMBER_PICKER_VALUE_TEXT_DIFFER')
        inputs.append(values[0])
    texts = (MONTHS[expected.month - 1], str(expected.day).zfill(2), str(expected.year))
    need(sorted((n['text'] for n in inputs)) == sorted(texts), 'EXACT_MONTH_DAY_YEAR_NOT_OBSERVED')
    context = [container, *pickers, *inputs]
    need(all((n.get('window_id') == container['window_id'] for n in context)), 'DATE_PICKER_CROSS_WINDOW')
    day_input = next((n for n in inputs if n['text'] == texts[1]))
    day_picker = next((n for n in pickers if inside(n['bounds_array'], day_input['bounds_array'])))
    return (day_picker, day_input, context)

def selected_repeat(nodes, text):
    child = one(nodes, lambda n: n.get('class') == 'android.widget.CheckedTextView' and n.get('resource-id') == 'android:id/text1' and (n.get('text') == text) and (n.get('enabled') is True), 'EXACT_REPEAT_LABEL_REQUIRED')
    spinner = one(nodes, lambda n: n.get('class') == 'android.widget.Spinner' and n.get('enabled') is True and (n.get('clickable') is True) and inside(n.get('bounds_array'), child.get('bounds_array')), 'EXACT_REPEAT_SPINNER_REQUIRED')
    caption = one(nodes, lambda n: n.get('class') == 'android.widget.TextView' and n.get('text') == 'Repeats', 'REPEAT_CAPTION_REQUIRED')
    need(child['window_id'] == spinner['window_id'] == caption['window_id'], 'REPEAT_CROSS_WINDOW')
    return (child, [spinner, caption])

def picker(role, obs, plan):
    need(role in NEW_ROLES and obs['focus']['package'] == PACKAGE and (obs['focus']['activity'] in EDITORS), 'OWNED_EDITOR_PICKER_ROLE_REQUIRED')
    nodes = obs['nodes']

    def button(text):
        return one(nodes, lambda n: n.get('class') == 'android.widget.Button' and n.get('text') == text and (n.get('enabled') is True) and (n.get('clickable') is True), 'ONE_EXACT_DATE_ZONE_BUTTON_REQUIRED')
    if role in ('start-date-open', 'end-date-open'):
        return (button(('Starts: ' if role.startswith('start') else 'Ends: ') + plan['original_date_text']), [])
    if role == 'timezone-open':
        return (button('Time zone: ' + plan['original_timezone']), [])
    if role == 'repeat-open':
        need(not obs['focus'].get('popup'), 'REPEAT_SOURCE_MUST_BE_OWNED_EDITOR')
        return selected_repeat(nodes, 'Does not repeat')
    if role in ('start-date-step', 'end-date-step', 'start-date-confirm', 'end-date-confirm'):
        need(not obs['focus'].get('popup'), 'DATE_DIALOG_MUST_BELONG_TO_EDITOR')
        original = date.fromisoformat(plan['original_date'])
        target = date.fromisoformat(plan['target_date'])
        day_picker, day_input, context = number_date(nodes, plan, role.endswith('confirm'))
        if role.endswith('step'):
            day = one(nodes, lambda n: n.get('class') == 'android.widget.Button' and n.get('text') == str(target.day).zfill(2) and (n.get('resource-id') == '') and (n.get('enabled') is True) and (n.get('clickable') is True) and (n.get('editable') is False) and (n.get('password') is False) and (16 in n.get('supported_actions', [])) and inside(day_picker.get('bounds_array'), n.get('bounds_array')), 'ONE_EXACT_ADJACENT_DAY_BUTTON_REQUIRED')
            need(day['window_id'] == day_input['window_id'], 'DAY_BUTTON_CROSS_WINDOW')
            need(target > original and day['bounds_array'][1] >= day_input['bounds_array'][3] or (target < original and day['bounds_array'][3] <= day_input['bounds_array'][1]), 'DAY_BUTTON_NOT_ON_OBSERVED_INCREMENT_OR_DECREMENT_SIDE')
            return (day, context)
        positive = button('OK')
        need(positive.get('resource-id') == 'android:id/button1', 'PICKER_POSITIVE_REQUIRED')
        need(positive['window_id'] == day_input['window_id'], 'DATE_CONFIRM_CROSS_WINDOW')
        return (positive, context)
    if role == 'timezone-option':
        title = one(nodes, lambda n: n.get('resource-id') == 'android:id/alertTitle' and n.get('text') == 'Time zone', 'EXACT_TIMEZONE_DIALOG_REQUIRED')
        target = one(nodes, lambda n: n.get('class') == 'android.widget.CheckedTextView' and n.get('resource-id') == 'android:id/text1' and (n.get('text') == plan['timezone']) and (n.get('enabled') is True) and (n.get('clickable') is True) and (n.get('checked') is False), 'EXACT_VISIBLE_NEW_TIMEZONE_REQUIRED')
        listing = one(nodes, lambda n: n.get('class') == 'android.widget.ListView' and n.get('resource-id') == 'android:id/select_dialog_listview' and inside(n.get('bounds_array'), target.get('bounds_array')), 'TIMEZONE_LIST_REQUIRED')
        return (target, [title, listing])
    need(role == 'repeat-option' and obs['focus'].get('popup') is True, 'ACKNOWLEDGED_REPEAT_POPUP_REQUIRED')
    target = one(nodes, lambda n: n.get('class') == 'android.widget.CheckedTextView' and n.get('resource-id') == 'android:id/text1' and (n.get('text') == 'Daily') and (n.get('enabled') is True) and (n.get('clickable') is True) and (n.get('checked') is False), 'ONE_DAILY_REPEAT_OPTION_REQUIRED')
    listing = one(nodes, lambda n: n.get('class') == 'android.widget.ListView' and inside(n.get('bounds_array'), target.get('bounds_array')), 'REPEAT_POPUP_LIST_REQUIRED')
    return (target, [listing])

def form_proof(obs, plan, title, keep_original=False):
    need(obs['focus']['package'] == PACKAGE and obs['focus']['activity'] in EDITORS and (not obs['focus'].get('popup')), 'OWNED_SERIES_FORM_REQUIRED')
    nodes = obs['nodes']
    one(nodes, lambda n: n.get('class') == 'android.widget.EditText' and n.get('hint') == 'Title' and (n.get('text') == title), 'SERIES_TITLE_NOT_VISIBLE')
    for label in ('Starts: ' + plan['target_date_text'], 'Ends: ' + plan['target_date_text'], 'Start time: 12:00 PM', 'End time: 12:45 PM', 'Time zone: ' + plan['timezone']):
        one(nodes, lambda n: n.get('class') == 'android.widget.Button' and n.get('text') == label, 'SERIES_FORM_DATE_TIME_OR_TIMEZONE_NOT_VISIBLE')
    repeat = 'Existing repeat pattern (unchanged)' if keep_original else 'Daily'
    selected_repeat(nodes, repeat)
    return {'target_date': plan['target_date'], 'timezone': plan['timezone'], 'start_wall_time': '12:00', 'end_wall_time': '12:45', 'repeat': repeat, 'title': title, 'series_form_not_selected_occurrence': keep_original}
