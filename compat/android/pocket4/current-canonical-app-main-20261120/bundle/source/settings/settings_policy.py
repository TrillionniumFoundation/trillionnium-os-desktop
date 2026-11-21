"""Exact page routes, one journaled time-format round trip and read-only grants."""
import re


class Policy:
    native_timeout = 70

    def __init__(self, runtime):
        self.r = runtime
        self.s = runtime.session
        self.c = runtime.c
        self.remove_sent = False

    def admit(self, argv, timeout, mutation, private):
        c, r, s = self.c, self.r, self.s
        c.need(type(argv) is list and argv and all(type(x) is str and x and '\0' not in x for x in argv)
               and type(timeout) in (int, float) and 0 < timeout <= 70
               and type(mutation) is bool and private is False,
               'SETTINGS_EXACT_TYPED_COMMAND_REQUIRED')
        if argv == c.STACKS:
            c.need(mutation is False and (timeout == 20 or
                   r.phase == 'cleanup' and self.remove_sent and 0 < timeout <= 3),
                   'SETTINGS_TASK_READ_ONLY')
            return
        if argv == ['/system/bin/dumpsys', 'package', s.profile.PACKAGE]:
            c.need(timeout == 20 and mutation is False, 'SETTINGS_PACKAGE_READ_ONLY')
            return
        if argv in (s.profile.SETTINGS_READ, s.profile.ACCOUNT_READ,
                    s.profile.PERMISSION_CHECK, s.profile.PERMISSION_ERROR):
            c.need(timeout == 20 and mutation is False and r.phase in ('inspect', 'cleanup'),
                   'SETTINGS_BUSINESS_STATE_READ_ONLY')
            return
        if argv[:1] == ['/system/bin/settings']:
            pending = s.pending_setting
            c.need(r.phase in ('inspect', 'cleanup') and timeout == 20 and mutation is True
                   and pending is not None and not pending['sent']
                   and pending['scope'] == r.scope_ref and argv == pending['argv']
                   and s.pending_route is None and s.current_ui_context is None and s.pending_native is None
                   and s.cleanup_admission is None
                   and 1 <= s.setting_write_count <= 2
                   and (r.phase == 'inspect' or pending['restore'] is True),
                   'ONLY_CURRENT_ONCE_OWNED_TIME_FORMAT_WRITE_OR_RESTORE')
            intent = c.parse(c.read_ref(pending['intent']))
            state = s.roundtrip
            desired = state['original'] if pending['restore'] else state['test_value']
            c.need(intent['argv'] == argv == s.profile.setting_write_argv(desired)
                   and intent['original'] == state['original_ref']
                   and intent['lease'] == s.lease_ref and intent['desired'] == desired
                   and intent['restore'] is pending['restore'],
                   'SETTING_MUTATION_NOT_THE_IMMUTABLE_OWNED_INTENT')
            pending['sent'] = True
            return
        if argv[:2] == ['/system/bin/am', 'start-activity']:
            pending = s.pending_route
            c.need(r.phase == 'inspect' and pending is not None and not pending['sent']
                   and timeout == 35 and mutation is True
                   and argv == s.profile.route_argv(r.selected_task()['task'], pending['page'])
                   and pending['scope'] == r.scope_ref
                   and 1 <= s.page_route_count <= s.profile.LIMITS['maximum_page_routes'],
                   'ONE_FIXED_EXPORTED_SETTINGS_PAGE_ROUTE_REQUIRED')
            c.read_ref(pending['intent'])
            pending['sent'] = True
            return
        if argv[:4] == ['/system/bin/cmd', 'activity', 'stack', 'remove']:
            c.need(r.phase == 'cleanup' and timeout == 20 and mutation is True
                   and len(argv) == 5 and re.fullmatch('[1-9][0-9]*', argv[4])
                   and not self.remove_sent and s.pending_route is None
                   and s.cleanup_admission is not None,
                   'SETTINGS_ONLY_KNOWN_OWNED_TASK_REMOVAL')
            owned = r.selected_task()
            c.need(owned['task'] == int(argv[4]) and owned['cleanup_allowed'] is True
                   and owned['prelaunch_absent'] is True
                   and s.cleanup_admission == (r.scope_ref, owned['task']),
                   'SETTINGS_CURRENT_EXACT_OWNED_LEAF_REQUIRED')
            self.remove_sent = True
            return
        raise RuntimeError('COMMAND_OUTSIDE_EXACT_SETTINGS_BUSINESS_CONTRACT')

    def admit_ui(self, request, context):
        c, r, s = self.c, self.r, self.s
        c.need(r.phase == 'inspect' and request == {'op': 'observe', 'accessibility_mode': 'none'}
               and type(context) is dict and context == s.current_ui_context
               and context['scope'] == r.scope_ref and context['lease'] == s.lease_ref
               and s.pending_route is None and s.pending_setting is None
               and 1 <= s.observation_count <= s.profile.LIMITS['maximum_observations'],
               'SETTINGS_ONLY_CURRENT_READONLY_WINDOW_OBSERVATION')
        c.read_ref(context['owned_claim'])
        c.read_ref(context['lease'])
