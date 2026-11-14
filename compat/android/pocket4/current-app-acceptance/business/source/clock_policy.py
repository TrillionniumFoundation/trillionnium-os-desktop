"""Only the original Clock task reads, exact close, observe and semantic click."""

class Policy:
    native_timeout = 45

    def __init__(self, runtime):
        self.r = runtime; self.clicks = 0; self.removal = False

    def admit(self, argv, timeout, mutation, private):
        c, r = self.r.c, self.r
        c.need(type(timeout) in (int, float) and 0 < timeout <= 20 and
               type(mutation) is type(private) is bool and not private,
               'ORIGINAL_CLOCK_HELD_COMMAND_BOUND_REQUIRED')
        if argv == c.STACKS:
            c.need(not mutation, 'CLOCK_TASK_READ_ONLY')
            return
        selected = r.selected_task()
        c.need(r.phase == 'cleanup' and not self.removal and mutation and timeout == 20
            and argv == ['/system/bin/cmd', 'activity', 'stack', 'remove', str(selected['task'])]
            and selected['prelaunch_absent'] is True and selected['cleanup_allowed'] is True,
            'ONLY_ONE_EXACT_NEW_CLOCK_LEAF_REMOVAL')
        self.removal = True

    def admit_ui(self, request, context):
        r, c = self.r, self.r.c
        c.need(r.phase == 'inspect' and type(request) is dict and request.get('op') in ('observe', 'click')
            and request.get('accessibility_mode') == 'none', 'ORIGINAL_CLOCK_OBSERVE_OR_ACCESSIBILITY_CLICK_ONLY')
        if request['op'] == 'observe':
            c.need(set(request) == {'op', 'accessibility_mode'}, 'EXACT_CLOCK_OBSERVE_REQUEST')
        else:
            c.need(set(request) == {'op', 'selector', 'accessibility_mode', 'method'}
                and request['method'] == 'accessibility' and self.clicks < 20,
                'EXACT_ORIGINAL_CLOCK_SEMANTIC_CLICK_BUDGET')
            self.clicks += 1
        r.guard_module.validate_ui_context(r, request, context)
