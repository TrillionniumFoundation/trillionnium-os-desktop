#!/usr/bin/env python3
"""Local source/admission boundary controls; no Pocket4 builds or locks."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import unittest

HERE = Path(__file__).parent.parent
FIXTURES = HERE / 'tests/fixtures'
BASELINE = json.loads((FIXTURES / 'reviewed-source-baselines.json').read_text())
OLD_ID = 'native597-20261108-r1'
NEW_ID = 'native597-8gib-hostreserve5-20261108-r1'


def source(name):
    return (HERE / 'source' / name).read_text()


def namespace(text):
    out = {'__name__': 'isolated_native_profile_control'}
    exec(compile(text, '<isolated-source-control>', 'exec'), out)
    return out


def canonical_ast(value):
    """Keep semantic fields, independent of ast.dump's versioned formatting.

    CPython 3.12 adds empty type_params to functions/classes; 3.13 adds
    default_value=None to type parameters. Their absence has the same meaning
    on earlier interpreters. No other empty or optional fields are discarded.
    """
    if isinstance(value, ast.AST):
        kind = type(value).__name__
        fields = {}
        for key, item in ast.iter_fields(value):
            if (kind in ('FunctionDef', 'AsyncFunctionDef', 'ClassDef')
                    and key == 'type_params' and type(item) is list and not item):
                continue
            if (kind in ('TypeVar', 'ParamSpec', 'TypeVarTuple')
                    and key == 'default_value' and item is None):
                continue
            fields[key] = canonical_ast(item)
        return {'node': kind, 'fields': fields}
    if type(value) is list:
        return [canonical_ast(item) for item in value]
    if value is None or type(value) in (str, int, float, bool):
        # Tag scalar types so bool/int and other equal JSON values cannot alias.
        return {'scalar': type(value).__name__, 'value': value}
    if type(value) is bytes:
        return {'scalar': 'bytes', 'hex': value.hex()}
    if type(value) is complex:
        return {'scalar': 'complex', 'real': value.real, 'imag': value.imag}
    if value is Ellipsis:
        return {'scalar': 'ellipsis'}
    raise TypeError('unsupported AST field type: ' + type(value).__name__)


def functions(text):
    return {node.name: hashlib.sha256(json.dumps(canonical_ast(node),
                sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                allow_nan=False).encode()).hexdigest() for node in ast.parse(text).body
            if isinstance(node, ast.FunctionDef)}


def preflight_predicate(message):
    text = source('preflight_native597_8gib_hostreserve5.template-r2.py')
    calls = [node for node in ast.walk(ast.parse(text))
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == 'need' and len(node.args) == 2
             and isinstance(node.args[1], ast.Constant) and node.args[1].value == message]
    if len(calls) != 1:
        raise AssertionError('one real preflight predicate required: ' + message)
    return compile(ast.Expression(calls[0].args[0]), '<actual-preflight-predicate>', 'eval')


def preflight_resource(events=None, swap='0'):
    values = {key: '0' for key in ('max', 'oom', 'oom_kill', 'oom_group_kill')}
    if events:
        values.update(events)
    return eval(preflight_predicate('preflight resource fault'), {'events': values,
        'report': {'preflight_resources_after': {'memory.swap.current': swap}}})


class Profile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before_hashes = BASELINE['r11_function_sha256']
        cls.after = source('framework_build_native597_8gib_hostreserve5.template-r1.py')
        cls.new = namespace(cls.after)

    def memory(self, available=13 * 1024**3, **changes):
        owned = {'memory.max': str(8 * 1024**3), 'cpu.max': '200000 100000',
                 'memory.swap.max': '0', 'memory.swap.current': '0'}
        owned.update(changes)
        return self.new['memory_admission']({'MemAvailable': available, 'SwapFree': 1 << 50}, owned)

    def test_ast_empty_version_fields_are_equivalent(self):
        node = ast.parse('def example():\n    return 1\n').body[0]
        expected = canonical_ast(node)
        node._fields = tuple(key for key in node._fields if key != 'type_params')
        self.assertEqual(canonical_ast(node), expected)
        node._fields += ('type_params',)
        node.type_params = []
        self.assertEqual(canonical_ast(node), expected)
        node.type_params = [ast.Name(id='T', ctx=ast.Load())]
        self.assertNotEqual(canonical_ast(node), expected)

    def test_ast_optional_type_default_is_preserved_when_present(self):
        # This also exercises the future field on interpreters without TypeVar.
        type_var = type('TypeVar', (ast.AST,), {'_fields': ('name', 'bound')})
        node = type_var(name='T', bound=None)
        expected = canonical_ast(node)
        node._fields += ('default_value',)
        node.default_value = None
        self.assertEqual(canonical_ast(node), expected)
        node.default_value = ast.Name(id='int', ctx=ast.Load())
        self.assertNotEqual(canonical_ast(node), expected)

    def test_ast_keeps_other_empty_fields_and_scalar_types(self):
        node = ast.parse('def example():\n    return 1\n').body[0]
        expected = canonical_ast(node)
        node._fields = tuple(key for key in node._fields if key != 'decorator_list')
        self.assertNotEqual(canonical_ast(node), expected)
        self.assertNotEqual(functions('def f(): return 1'), functions('def f(): return True'))
        self.assertNotEqual(functions('def f(): return 1'), functions('def f(): return 2'))

    def test_preflight_exact_2gib_cap_only(self):
        class Cgroup:
            def __init__(self, value): self.value = value
            def __truediv__(self, name):
                self.name = name
                return self
            def read_text(self):
                self.assert_name()
                return self.value
            def assert_name(self):
                if self.name != 'memory.max': raise AssertionError(self.name)
        expression = preflight_predicate('wrong preflight hard memory')
        for value, accepted in ((str(2 * 1024**3), True), (str(1024**3), False), ('max', False)):
            with self.subTest(value=value):
                self.assertIs(eval(expression, {'cg': Cgroup(value)}), accepted)

    def test_preflight_clean_events_and_zero_swap_accepted(self):
        self.assertIs(preflight_resource(), True)

    def test_preflight_actual_prior_limit_pressure_rejected(self):
        failure = BASELINE['preflight_1gib_compact_regression']
        self.assertEqual(failure['memory_max_bytes'], 1024**3)
        self.assertEqual(failure['memory_events']['max'], 4727)
        self.assertIs(preflight_resource({key: str(value)
            for key, value in failure['memory_events'].items()}), False)

    def test_preflight_each_owned_oom_event_rejected(self):
        for name in ('oom', 'oom_kill', 'oom_group_kill'):
            with self.subTest(name=name):
                self.assertIs(preflight_resource({name: '1'}), False)

    def test_preflight_nonzero_swap_rejected(self):
        self.assertIs(preflight_resource(swap='1'), False)

    def test_preflight_both_fresh_13gib_boundaries_kept(self):
        for key, label in (
            ('available_memory_before_bytes', 'fresh 8GiB plus 5GiB host-reserve admission not yet available'),
            ('available_memory_after_bytes', '8GiB plus 5GiB host-reserve floor no longer met')):
            expression = preflight_predicate(label)
            with self.subTest(phase=key):
                self.assertIs(eval(expression, {'report': {key: 13 * 1024**3}}), True)
                self.assertIs(eval(expression, {'report': {key: 13 * 1024**3 - 1}}), False)

    def test_exact_floor_accepted(self):
        self.memory()

    def test_one_byte_below_floor_rejected(self):
        with self.assertRaises(RuntimeError):
            self.memory(13 * 1024**3 - 1)

    def test_more_memory_accepted(self):
        self.memory(14 * 1024**3)

    def test_original_10gib_request_not_admitted_as_8gib(self):
        with self.assertRaises(RuntimeError):
            self.memory(**{'memory.max': str(10 * 1024**3)})

    def test_lower_or_unlimited_cap_rejected(self):
        for value in (str(7 * 1024**3), 'max'):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                self.memory(**{'memory.max': value})

    def test_swap_limit_and_usage_rejected(self):
        for key in ('memory.swap.max', 'memory.swap.current'):
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                self.memory(**{key: '1'})

    def test_cpu_change_rejected(self):
        with self.assertRaises(RuntimeError):
            self.memory(**{'cpu.max': '300000 100000'})

    def test_global_swap_never_satisfies_floor(self):
        with self.assertRaises(RuntimeError):
            self.memory(8 * 1024**3)

    def test_changed_reserve_rejected(self):
        isolated = namespace(self.after)
        isolated['MIN_AVAILABLE'] = 12 * 1024**3
        with self.assertRaises(RuntimeError):
            isolated['memory_admission']({'MemAvailable': 20 * 1024**3},
                {'memory.max': str(8 * 1024**3), 'cpu.max': '200000 100000',
                 'memory.swap.max': '0', 'memory.swap.current': '0'})

    def test_exact_execution_function_delta(self):
        before, after = self.before_hashes, functions(self.after)
        self.assertEqual(set(before), set(after))
        self.assertEqual({k for k in before if before[k] != after[k]},
            {'memory_admission', 'record_resource_admission', 'builder_recovery_contract',
             'prior_failure_contract', 'plan'})

    def test_history_uses_original_floor_and_literals(self):
        self.assertEqual(self.new['MIN_AVAILABLE'], 13 * 1024**3)
        self.assertEqual(self.new['HISTORICAL_MIN_AVAILABLE'], 15 * 1024**3)
        # Restoring the historical variable name yields exactly the original
        # AST; old resource receipts and rejection strings are unchanged.
        for name in ('builder_recovery_contract', 'prior_failure_contract'):
            restored = self.after.replace('HISTORICAL_MIN_AVAILABLE', 'MIN_AVAILABLE')
            self.assertEqual(functions(restored)[name], self.before_hashes[name])
        self.assertEqual(15 * 1024**3 - 14854873088, 1251254272)
        self.assertLess(13 * 1024**3, 14854873088)

    def test_historical_rejection_predicate_executes_with_13gib_active(self):
        function = next(node for node in ast.parse(self.after).body
                        if isinstance(node, ast.FunctionDef) and node.name == 'prior_failure_contract')
        check = next(node for node in ast.walk(function) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name) and node.func.id == 'require'
                     and len(node.args) == 2 and isinstance(node.args[1], ast.Constant)
                     and node.args[1].value == 'prior Normal09 failed RAM threshold was changed')
        expression = compile(ast.Expression(check.args[0]), '<historical-threshold>', 'eval')
        values = dict(self.new, resource_memory={'MemAvailable': 14854873088})
        self.assertIs(eval(expression, values), True)
        values['HISTORICAL_MIN_AVAILABLE'] = 13 * 1024**3
        self.assertIs(eval(expression, values), False)

    def test_source_and_build_lifecycle_unchanged(self):
        for name in ('build', 'cleanup_children', 'owned_resource_gate', 'source_resume_predecessor',
                     'historical_active_materialization', 'builder_contract', 'completion_gate',
                     'observe_active_inputs', 'verify_prepared', 'verify_inputs_after'):
            self.assertEqual(self.before_hashes[name], functions(self.after)[name], name)

    def test_exact_new_plan_keeps_original_source_and_targets(self):
        old, new = BASELINE['r11_plan'], self.new['plan']()
        expected = copy.deepcopy(old)
        expected.update(resource_profile_id=NEW_ID, memory_max_bytes=8 * 1024**3,
                        fresh_MemAvailable_min_bytes=13 * 1024**3)
        def paths(value):
            if type(value) is str:
                return value.replace(OLD_ID, NEW_ID)
            if type(value) is list:
                return [paths(item) for item in value]
            if type(value) is dict:
                return {key: paths(item) for key, item in value.items()}
            return value
        self.assertEqual(new, paths(expected))
        self.assertEqual(new['admission_difference_bytes'], 5 * 1024**3)
        self.assertEqual(new['builder_sha256'], '75bf728444a101d39428a8c90a876e53d3325c1e45441c132b2552deb74660f0')
        self.assertEqual(new['targets'], ['libberberis_arm64', 'com.android.art'])
        self.assertEqual(new['dependency_mode'], 'Strict')

    def test_launcher_parent_leases_only_relocated(self):
        new = source('launch_build_native597_8gib_hostreserve5.parent-lease-r1.template.py')
        self.assertEqual(hashlib.sha256(new.replace(NEW_ID, OLD_ID).encode()).hexdigest(), BASELINE['r11_launcher_sha256'])

    def test_binder_exact_original_packet_function_guard(self):
        binder = namespace(source('bind_packet_native597_8gib_hostreserve5.bound-r1.py'))
        original = (FIXTURES / 'original_build_function.py').read_text()
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), BASELINE['original_build_function_sha256'])
        before, after = BASELINE['original_packet_function_sha256'], functions(self.after)
        self.assertEqual(sorted(k for k in before if after.get(k) != before[k]), binder['EXPECTED_CHANGED_FUNCTIONS'])
        self.assertEqual(sorted(set(after) - set(before)), binder['EXPECTED_ADDED_FUNCTIONS'])
        binder['check_only_build_timeout_changed'](original, self.after)
        self.assertEqual(binder['TEMPLATE_SHA'], hashlib.sha256(self.after.encode()).hexdigest())
        self.assertEqual(binder['LAUNCHER_TEMPLATE_SHA'], hashlib.sha256(
            source('launch_build_native597_8gib_hostreserve5.parent-lease-r1.template.py').encode()).hexdigest())

    def test_new_profile_preserves_separate_historical_budget(self):
        self.assertEqual(BASELINE['r11_plan']['memory_max_bytes'], 10 * 1024**3)
        self.assertEqual(BASELINE['r11_plan']['fresh_MemAvailable_min_bytes'], 15 * 1024**3)
        self.assertEqual(self.new['MEMORY_MAX'], 8 * 1024**3)
        self.assertEqual(self.new['MIN_AVAILABLE'], 13 * 1024**3)
        self.assertNotEqual(BASELINE['r11_plan']['out'], self.new['plan']()['out'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
