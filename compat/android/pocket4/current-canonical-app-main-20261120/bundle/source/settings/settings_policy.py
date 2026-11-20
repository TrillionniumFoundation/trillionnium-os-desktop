"""Only exact Settings page routes, read-only observation and owned removal."""
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
        if argv[:2] == ['/system/bin/am', 'start-activity']:
            pending = s.pending_route
            c.need(r.phase == 'inspect' and pending is not None and not pending['sent']
                   and timeout == 35 and mutation is True
                   and argv == s.profile.route_argv(r.selected_task()['task'], pending['page'])
                   and pending['scope'] == r.scope_ref and 1 <= s.page_route_count <= 5,
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
        raise RuntimeError('COMMAND_OUTSIDE_READONLY_SETTINGS_PAGES_CONTRACT')

    def admit_ui(self, request, context):
        c, r, s = self.c, self.r, self.s
        c.need(r.phase == 'inspect' and request == {'op': 'observe', 'accessibility_mode': 'none'}
               and type(context) is dict and context == s.current_ui_context
               and context['scope'] == r.scope_ref and context['lease'] == s.lease_ref
               and s.pending_route is None and 1 <= s.observation_count <= 7,
               'SETTINGS_ONLY_CURRENT_READONLY_WINDOW_OBSERVATION')
        c.read_ref(context['owned_claim'])
        c.read_ref(context['lease'])
