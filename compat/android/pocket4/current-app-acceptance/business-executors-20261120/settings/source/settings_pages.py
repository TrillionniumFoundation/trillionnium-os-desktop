"""Actual Settings page navigation through an admitted original Flow.

The caller must supply the new case's Main-bound Flow, current owned-task
claim, resource lease and immutable plan. No subprocess or shell is available
here. No result is credited until the recorder receipts, real window, PNG,
native controls and owned task all agree.
"""
import hashlib
import io
import re
from pathlib import Path


def need(value, code):
    if not value:
        raise RuntimeError(code)


def route_result(raw, page):
    need(type(raw) is bytes and len(raw) <= 65536, 'BOUNDED_ACTUAL_SETTINGS_ROUTE_RESULT')
    text = raw.decode('utf-8', 'strict')
    need(re.findall(r'^Status: (.+)$', text, re.M) == ['ok']
         and re.findall(r'^Activity: (.+)$', text, re.M) == [page['component']]
         and not re.search(r'(?im)^(?:Error|Exception|SecurityException):', text),
         'SETTINGS_ROUTE_DID_NOT_ACKNOWLEDGE_EXACT_COMPONENT')
    need(re.findall(r'^Complete$', text, re.M) == ['Complete'],
         'SETTINGS_ROUTE_WAIT_DID_NOT_COMPLETE')
    return {'component': page['component'], 'raw_sha256': hashlib.sha256(raw).hexdigest()}


def observation(value, png, *, profile, page, init_pid):
    """Check actual UI content while retaining only non-private summary facts."""
    need(type(value) is dict and value.get('ok') is True and value.get('outcome_unknown') is not True,
         'SETTINGS_OBSERVATION_UNKNOWN_OR_FAILED')
    native = value.get('native')
    need(type(native) is dict and native.get('ok') is True
         and native.get('accessibility_mode_restoration_verified') is True
         and native.get('outcome_unknown') is not True,
         'SETTINGS_NATIVE_READBACK_OR_RESTORATION_FAILED')
    meta = value.get('screenshot'); need(type(meta) is dict, 'ACTUAL_SETTINGS_SCREENSHOT_REQUIRED')
    window = meta.get('scope'); need(type(window) is dict, 'ACTUAL_SETTINGS_WINDOW_REQUIRED')
    activity = profile.HOME_ACTIVITY if page is None else page['activity']
    need(window.get('package') == profile.PACKAGE and window.get('activity') == activity
         and type(window.get('android_init_host_pid')) is int and window['android_init_host_pid'] == init_pid
         and type(window.get('display_id')) is int and window['display_id'] == 0
         and window.get('accessibility_mode') == 'none'
         and re.fullmatch('[0-9a-f]{1,32}', str(window.get('window_token', ''))),
         'SETTINGS_PAGE_WINDOW_OR_MAIN_CHANGED')
    need(type(png) is bytes and 0 < len(png) <= 32 * 1024 * 1024
         and png.startswith(b'\x89PNG\r\n\x1a\n'), 'BOUNDED_ACTUAL_SETTINGS_PNG_REQUIRED')
    from PIL import Image, ImageStat
    with Image.open(io.BytesIO(png)) as encoded:
        need(encoded.format == 'PNG' and 0 < encoded.width <= 8192 and 0 < encoded.height <= 8192
             and encoded.width * encoded.height <= 32_000_000, 'SETTINGS_IMAGE_DIMENSION_BOUND')
        encoded.load(); image = encoded.convert('RGB')
    try:
        need(image.width == meta.get('scope_width') and image.height == meta.get('scope_height'),
             'SETTINGS_SCOPED_IMAGE_SIZE_CHANGED')
        actual = hashlib.sha256(image.width.to_bytes(4, 'big') + image.height.to_bytes(4, 'big') + image.tobytes()).hexdigest()
        need(actual == meta.get('scope_sha256'), 'SETTINGS_SCOPED_PIXELS_CHANGED')
        stats = ImageStat.Stat(image)
        need(max(stats.stddev) >= 2, 'SETTINGS_PAGE_IS_UNUSABLE_FLAT_IMAGE')
    finally:
        image.close()
    nodes = native.get('nodes')
    need(type(nodes) is list and 1 <= len(nodes) <= 8192 and all(type(n) is dict for n in nodes),
         'BOUNDED_ACTUAL_SETTINGS_NATIVE_TREE_REQUIRED')
    visible = [n for n in nodes if n.get('package') == profile.PACKAGE
               and n.get('visible') is True and n.get('enabled') is True]
    titles = profile.HOME_TITLES if page is None else page['titles']
    heading = [n for n in visible if n.get('text') in titles and n.get('password') is False
               and n.get('editable') is False]
    controls = [n for n in visible if n.get('clickable') is True or n.get('scrollable') is True]
    # Content text is not copied into the public result. App names, network
    # names or other incidental Settings data stay in the private runtime
    # observation, whose exact pin is retained for review.
    labels = [n for n in visible if type(n.get('text')) is str and n['text'].strip()
              and n.get('password') is False]
    need(heading and len(controls) >= 2 and len(labels) >= 3,
         'SETTINGS_PAGE_TITLE_OR_USABLE_CONTROLS_MISSING')
    return {'page': 'home' if page is None else page['name'], 'package': profile.PACKAGE,
            'activity': activity, 'window_token': window['window_token'],
            'android_init_host_pid': init_pid, 'scoped_pixel_sha256': actual,
            'visible_control_count': len(controls), 'visible_label_count': len(labels),
            'expected_title_observed': True, 'source': 'actual-native-tree-and-scoped-PNG',
            'whole_app_business_accepted': False}


def recorded_ui_result(flow, value, step):
    c = flow.c
    result_ref = c.regular(step / 'command-001.result.json', contents=False)
    actual = c.parse(c.read_ref(result_ref)); logical = c.parse(c.regular(step / 'command-001.logical.json')[0])
    need(actual['host_retirement_proved'] is True and actual['evidence_complete'] is True
         and actual['returncode'] == 0 and actual['timed_out'] is False and actual['errors'] == []
         and actual.get('first_error') is None and logical['scope_sha256'] == flow.scope_ref['sha256']
         and logical['automatic_retry'] is False
         and actual['argv'] == flow.modules['business_ui_entry.py'].entry_argv(
             flow.scope_ref, 'client', step.name, 'command-001', logical['argv'][1:])
         and c.parse(c.read_ref(actual['stdout'])) == value,
         'SETTINGS_UI_MUST_HAVE_COMPLETE_ACTUAL_RECORDER_CHAIN')
    c.read_ref(actual['stderr'])
    return result_ref


def observe(flow, session, page):
    session.require_owned_task(flow)
    context = session.ui_context(flow, page)
    value, step = flow.ui({'op': 'observe', 'accessibility_mode': 'none'}, case_context=context)
    receipt = recorded_ui_result(flow, value, step)
    png_ref = flow.c.regular(step / 'observation.png', 32 * 1024 * 1024, contents=False)
    png = flow.c.read_ref(png_ref, 32 * 1024 * 1024)
    session.require_owned_task(flow); flow.guard()
    # The actual read-only transport and restoration are known to have ended.
    # A later content assertion can fail without pretending the page passed;
    # its already-known task may still use the bounded normal close path.
    session.observation_finished()
    summary = observation(value, png, profile=session.profile, page=page,
                          init_pid=flow.view.target.expected['pid'])
    return {'summary': summary, 'recorder_result': receipt,
            'observation': flow.c.regular(step / 'observed-result.json', contents=False), 'PNG': png_ref}


def execute_pages(flow, session):
    """Navigate each fixed read-only page exactly once, then observe it."""
    need(flow.phase == 'inspect' and session.page_route_count == 0,
         'NEW_SETTINGS_INSPECTION_PHASE_REQUIRED')
    rows = []
    for page in session.profile.PAGES:
        with flow.c.locked('/run/lock/android-digitalis-actions.lock'):
            session.require_owned_task(flow)
            argv = session.profile.route_argv(flow.selected_task()['task'], page)
            intent = session.begin_route(flow, page, argv)
            # begin_route persists a once-only intent. A timeout, failed post-guard
            # or changed task poisons that intent; no automatic route replay follows.
            raw = flow.android(argv, 35, mutation=True)
            ack = route_result(raw, page)
            session.end_route(flow, page, intent, raw, ack)
        rows.append(observe(flow, session, page))
    need(len(rows) == len(session.profile.PAGES) == 5,
         'ALL_FIVE_ORIGINAL_SETTINGS_PAGE_CLASSES_REQUIRED')
    return rows
