"""Narrow original timeout/root variants of the frozen seven-FD transport.

All ownership, evidence, lease release, postguard, poison and retirement code
is the original BoundArun. Only its guest timeout construction differs for the
two original CameraSession contracts. Backend arun uses unmodified BoundArun.
"""
import ast
import copy
from pathlib import Path
import types


def bound_class(c, scope, support_ref, variant):
    c.need(variant in ('camera_android', 'calendar_root_sql'), 'EXACT_ORIGINAL_TRANSPORT_VARIANT')
    manifest = c.parse(c.read_ref(support_ref))
    ref = {'path': str(Path(support_ref['path']).parent / 'business_scope.py'),
           **manifest['files']['business_scope.py']}
    c.need(ref['sha256'] == c.SCOPE_SHA, 'UNMODIFIED_QUALIFIED_SEVEN_FD_SOURCE_REQUIRED')
    raw = c.read_ref(ref); tree = ast.parse(raw)
    classes = [x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'BoundArun']
    c.need(len(classes) == 1, 'ONE_ORIGINAL_BOUND_TRANSPORT')
    methods = [x for x in classes[0].body if isinstance(x, ast.FunctionDef) and x.name == '__call__']
    c.need(len(methods) == 1, 'ONE_ORIGINAL_TRANSPORT_ENTRY')
    original = methods[0]; method = copy.deepcopy(original); changes = []
    for node in ast.walk(method):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'inner':
            c.need(ast.dump(node.value) == ast.dump(ast.parse('max(1, timeout - 5)', mode='eval').body),
                   'ORIGINAL_GUEST_TIMEOUT_ASSIGNMENT_CHANGED')
            changes.append((node, copy.deepcopy(node.value)))
            node.value = ast.parse('timeout - 4' if variant == 'camera_android' else '10', mode='eval').body
        elif variant == 'calendar_root_sql' and isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) and node.target.id == 'command':
            value = node.value
            if isinstance(value, ast.List) and len(value.elts) >= 2 and all(isinstance(x, ast.Constant) for x in value.elts[:2]) and [x.value for x in value.elts[:2]] == ['/system/xbin/su', '2000']:
                changes.append((node, copy.deepcopy(node.value)))
                node.value.elts = node.value.elts[2:]
    c.need(len(changes) == (1 if variant == 'camera_android' else 2), 'ONLY_DECLARED_ORIGINAL_TRANSPORT_DIFFERENCES')
    candidate = copy.deepcopy(method)
    for node, value in changes:
        node.value = value
    c.need(ast.dump(method) == ast.dump(original), 'ALL_OTHER_BOUND_TRANSPORT_CODE_MUST_BE_IDENTICAL')
    environment = dict(scope.BoundArun.__call__.__globals__)
    candidate = ast.fix_missing_locations(ast.Module(body=[candidate], type_ignores=[]))
    exec(compile(candidate, __file__ + ':' + variant, 'exec'), environment)
    return type('Original_' + variant, (scope.BoundArun,), {'__call__': environment['__call__']})


class ImageRecorder:
    """Only actual screencap gets the separately qualified 32 MiB pipe."""
    def __init__(self, flow, real):
        self.flow, self.real = flow, real
        self.last_completed = None

    def __getattr__(self, name):
        return getattr(self.real, name)

    def command(self, *args, **kwargs):
        result = self.real.command(*args, **kwargs)
        if kwargs.get('check') is False:
            self.last_completed = result
        return result

    def runner(self, argv, **options):
        f = self.flow; b = f.bound; c = f.c
        import subprocess
        c.need(set(options) == {'stdout', 'stderr', 'timeout', 'env', 'pass_fds', 'close_fds'}
            and options['stdout'] == options['stderr'] == subprocess.PIPE and options['close_fds'] is True
            and len(options['pass_fds']) == 7 and not self.real.closed and not b.poisoned,
            'EXACT_HELD_ORIGINAL_API_RUNNER_OPTIONS')
        image = f._image_transport
        c.need(not image or (options['timeout'] == 20 and tuple(argv[-2:]) == ('/system/bin/screencap', '-p')
            and f._android_mutation is False and f._private_backend_transport is True),
            'ONLY_EXACT_HELD_SCREENSHOT_HAS_IMAGE_BUDGET')
        self.real.command_index += 1; name = 'command-%03d' % self.real.command_index
        try:
            result = b.commands.run_recorded(name, list(argv), options['timeout'], self.real.step, b.guard,
                protected_pids=b.baseline.protected_pids, mutation=f._android_mutation, pass_fds=options['pass_fds'],
                host_env=options['env'], check=False, deferred_post_guard=True,
                private_output=f._private_backend_transport,
                output_bound=33554432 if image else 16777216, image_channel=image)
            f.action_attempted |= bool(result.command_observation['action_attempted'])
            self.last_completed = result
            return result
        except BaseException as error:
            observed = getattr(error, 'command_observation', {})
            f.action_attempted |= bool(observed.get('action_attempted', False))
            self.real._hold(error)
            raise
