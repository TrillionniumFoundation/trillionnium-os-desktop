#!/usr/bin/env python3
"""Only temporary-file and fake-boundary checks. Never invokes systemd or Main."""
import argparse
import copy
import hashlib
import importlib.util
import io
import json
import os
import stat
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('private_runner', HERE/'run_fixture.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

class Boundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def file(self, value):
        p = self.root/'input'
        p.write_text(value)
        return p
    def test_hash_pin_rejects_changed_bytes(self):
        p = self.file('{"schema":1}')
        with self.assertRaises(r.Stop):
            r.load_pinned(p, '0'*64)
    def test_file_bound_is_enforced(self):
        with self.assertRaises(r.Stop):
            r.read_regular(self.file('12345'), 4)
    def test_input_symlink_is_rejected(self):
        p = self.file('abc')
        link = self.root/'link'
        link.symlink_to(p)
        with self.assertRaises(OSError):
            r.read_regular(link)
    def test_input_hardlink_is_rejected(self):
        p = self.file('abc')
        os.link(p, self.root/'other')
        with self.assertRaises(r.Stop):
            r.read_regular(p)
    def test_output_claim_never_overwrites(self):
        p = self.root/'result'
        r.save(p, {'first': True})
        before = p.read_bytes()
        with self.assertRaises(FileExistsError):
            r.save(p, {'second': True})
        self.assertEqual(p.read_bytes(), before)
    def test_duplicate_counter_is_unknown(self):
        with self.assertRaises(r.Stop):
            r.values(self.file('max 0\nmax 1\n'))
    def test_negative_counter_is_unknown(self):
        with self.assertRaises(r.Stop):
            r.values(self.file('high -1\n'))
    def test_nonfinite_psi_is_unknown(self):
        p = self.file('some avg10=nan avg60=0 avg300=0 total=0\nfull avg10=0 avg60=0 avg300=0 total=0\n')
        with self.assertRaises(r.Stop):
            r.psi(p)
    def test_missing_psi_fields_are_unknown(self):
        p = self.file('some avg10=0 total=0\nfull avg10=0 avg60=0 avg300=0 total=0\n')
        with self.assertRaises(r.Stop):
            r.psi(p)
    def test_duplicate_psi_is_unknown(self):
        p = self.file(('some avg10=0 avg60=0 avg300=0 total=0\n')*2)
        with self.assertRaises(r.Stop):
            r.psi(p)
    def test_historical_counters_retained_and_deltas_stop(self):
        base = {'main_events':{'high':1703, 'max':0, 'oom':0, 'oom_kill':0, 'oom_group_kill':0},
                'main_pids_events':{'max':0}}
        r.guard_health(copy.deepcopy(base), base)
        for key in base['main_events']:
            current = copy.deepcopy(base)
            current['main_events'][key] += 1
            with self.assertRaises(r.Stop):
                r.guard_health(current, base)
        regressed = copy.deepcopy(base)
        regressed['main_events']['high'] = 0
        with self.assertRaises(r.Stop):
            r.guard_health(regressed, base)
        current = copy.deepcopy(base)
        current['main_pids_events']['max'] = 1
        with self.assertRaises(r.Stop):
            r.guard_health(current, base)
    def health_case(self):
        pin = {'limits':{'memory.max':str(6*r.GIB), 'pids.max':'12288'}}
        p = {'some':{'avg10':0.0,'avg60':0.0,'avg300':0.0,'total':0},
             'full':{'avg10':0.0,'avg60':0.0,'avg300':0.0,'total':0}}
        current = {'host_available':16*r.GIB,'host_swap_free':8*r.GIB,
            'main_current':2*r.GIB,'main_pids':1000,
            'main_events':{'high':123,'max':0,'oom':0,'oom_kill':0,'oom_group_kill':0},
            'main_pids_events':{'max':0}, 'main_psi':copy.deepcopy(p), 'host_psi':copy.deepcopy(p)}
        return pin, current

    def test_rejected_health_frame_is_durable_with_exact_trigger(self):
        pin, current = self.health_case()
        current['host_psi']['full']['avg10'] = 10.0
        path = self.root/'rejected-health.json'
        with patch.object(r, 'health', return_value=current):
            with self.assertRaises(r.Stop) as stopped:
                r.sample_health(pin, path)
        saved = json.loads(path.read_text())
        self.assertEqual(saved['host_psi']['full']['avg10'], 10.0)
        self.assertEqual(stopped.exception.evidence, str(path))
        self.assertEqual(stopped.exception.observation,
            {'scope':'host','metric':'memory.full.avg10_percent','value':10.0,
             'required_comparison':'<','limit':10})

    def test_persist_failure_prevents_policy_and_release_progress(self):
        pin, current = self.health_case()
        with patch.object(r, 'health', return_value=current), \
             patch.object(r, 'save', side_effect=OSError('storage unavailable')), \
             patch.object(r, 'guard_admission') as gate:
            with self.assertRaises(OSError):
                r.sample_health(pin, self.root/'health.json')
            gate.assert_not_called()

    def test_original_strict_psi_admission_threshold_is_unchanged(self):
        pin, current = self.health_case()
        current['host_psi']['full']['avg10'] = 9.99
        r.guard_admission(pin, current)
        current['main_psi']['full']['avg10'] = 10.0
        with self.assertRaises(r.Stop) as stopped:
            r.guard_admission(pin, current)
        self.assertEqual(stopped.exception.observation['scope'], 'main')
        self.assertEqual(stopped.exception.observation['limit'], 10)

    def test_changed_main_counter_frame_is_saved_before_stop(self):
        pin, current = self.health_case()
        before = copy.deepcopy(current)
        current['main_events']['high'] += 1
        path = self.root/'main-counter-delta.json'
        with patch.object(r, 'health', return_value=current):
            with self.assertRaises(r.Stop) as stopped:
                r.sample_health(pin, path, before)
        self.assertEqual(json.loads(path.read_text())['main_events']['high'], 124)
        self.assertEqual(stopped.exception.observation['metric'], 'memory.events.high')
        self.assertEqual(stopped.exception.evidence, str(path))

    def test_execute_requires_explicit_switch_before_any_host_read(self):
        args = argparse.Namespace(execute_approved=False)
        with patch.object(r.os, 'geteuid', return_value=0), patch.object(r, 'main_pin') as main:
            with self.assertRaises(r.Stop):
                r.run(args)
            main.assert_not_called()
    def test_post_registration_runtime_gate_precedes_pressure(self):
        source = (HERE/'fixture_init.cpp').read_text()
        startup = 'record_runtime(lmkd,"startup");'
        post = 'record_runtime(lmkd,"post-registration");'
        barrier = '"reject nonleader registration");'
        pressure = 'if(phase=="pressure")'
        def correctly_ordered(text):
            positions = [text.find(x) for x in (startup, barrier, post, pressure)]
            return all(p >= 0 for p in positions) and positions == sorted(set(positions))
        self.assertTrue(correctly_ordered(source))
        self.assertFalse(correctly_ordered(source.replace(post, '')))
        early = source.replace(post, '').replace(startup, startup+post)
        self.assertFalse(correctly_ordered(early))
        body = source.split('void record_runtime(', 1)[1].split('void run_phase(', 1)[0]
        self.assertIn('/evidence/lmkd-post-registration-', body)
        self.assertIn('/evidence/lmkd-', body)
        self.assertIn('link.find("cgroup.kill")==std::string::npos', body)
        self.assertIn('link.find("cgroup.procs")==std::string::npos', body)
    def test_execution_and_state_directory_policies(self):
        metadata = SimpleNamespace(st_mode=stat.S_IFDIR|0o755, st_uid=0, st_gid=0,
                                   st_dev=1, st_ino=2)
        state_flags = os.ST_NOSUID | os.ST_NODEV | os.ST_NOEXEC
        with patch.object(r.Path, 'lstat', return_value=metadata), \
             patch.object(r.os, 'statvfs', return_value=SimpleNamespace(f_flag=state_flags)):
            r.directory_policy('/run', False)
            with self.assertRaises(r.Stop):
                r.directory_policy('/run', True)
        with patch.object(r.Path, 'lstat', return_value=metadata), \
             patch.object(r.os, 'statvfs', return_value=SimpleNamespace(f_flag=0)):
            r.directory_policy('/opt', True)
            with self.assertRaises(r.Stop):
                r.directory_policy('/run', False)
            metadata.st_uid = 1000
            with self.assertRaises(r.Stop):
                r.directory_policy('/opt', True)

            metadata.st_uid = 0
            metadata.st_mode = stat.S_IFDIR|0o777
            with self.assertRaises(r.Stop):
                r.directory_policy('/opt', True)

    def framework_case(self):
        init = {'pid':100, 'ns':{'pid':17}}
        cg = '/system.slice/droidloomd.service'
        records = [
            {'role':'zygote64','pid':200,'ppid':100,'start_ticks':11,
             'argv0':'zygote64','exe':'/system/bin/app_process64','ns':{'pid':17},'cgroup':cg},
            {'role':'system_server','pid':201,'ppid':200,'start_ticks':12,
             'argv0':'system_server','exe':'/system/bin/app_process64','ns':{'pid':17},'cgroup':cg+'/system'},
            {'role':'surfaceflinger','pid':202,'ppid':100,'start_ticks':11,
             'argv0':'/system/bin/surfaceflinger','exe':'/system/bin/surfaceflinger',
             'ns':{'pid':17},'cgroup':cg+'/system'}]
        return records, init, cg

    def test_guest_framework_generations_are_part_of_stable_identity(self):
        records, init, cg = self.framework_case()
        before = r.verify_framework_records(copy.deepcopy(records), init, cg)
        records[1]['start_ticks'] += 1
        after = r.verify_framework_records(records, init, cg)
        self.assertNotEqual(before, after)
        self.assertEqual(after['system_server']['start_ticks'], 13)

    def test_missing_or_duplicate_framework_process_is_rejected(self):
        records, init, cg = self.framework_case()
        for invalid in [records[:2], [records[0], records[0], records[2]]]:
            with self.assertRaises(r.Stop):
                r.verify_framework_records(invalid, init, cg)

    def test_framework_process_cannot_escape_main_namespace_or_parent(self):
        records, init, cg = self.framework_case()
        for field, value in [('ppid',100), ('ns',{'pid':18}), ('cgroup','/system.slice/unrelated.service')]:
            invalid = copy.deepcopy(records)
            invalid[1][field] = value
            with self.assertRaises(r.Stop):
                r.verify_framework_records(invalid, init, cg)

    def domain_case(self):
        unit = self.root/'p4-lmkd-fixture-r8-test.service'
        unit.mkdir()
        (unit/'cgroup.procs').write_text('')
        (unit/'supervisor').mkdir()
        domain = unit/'domain'
        domain.mkdir()
        limits = {'memory.max':'536870912', 'memory.high':'max', 'memory.swap.max':'0',
                  'pids.max':'64', 'cpu.max':'100000 100000'}
        for key, value in limits.items():
            (domain/key).write_text(value+'\n')
        ds = domain.stat()
        outer = {'domain_relative':'/domain', 'domain_dev':ds.st_dev, 'domain_ino':ds.st_ino,
                 'bootstrap_cgroup':'/supervisor'}
        inner = {**outer, 'root_pressure_write_errno':1, 'memory_mount_path':'/sys/fs/cgroup',
                 'cgroup_dev':ds.st_dev, 'cgroup_ino':ds.st_ino}
        child = {'cgroup':'/system.slice/'+unit.name+'/domain'}
        bootstrap = {'cgroup':'/system.slice/'+unit.name+'/supervisor'}
        return unit, outer, inner, child, bootstrap

    def attest(self, case):
        original = Path.lstat
        def metadata(p):
            s = original(p)
            return SimpleNamespace(st_mode=s.st_mode, st_uid=0, st_gid=0,
                                   st_dev=s.st_dev, st_ino=s.st_ino)
        with patch.object(r.Path, 'lstat', autospec=True, side_effect=metadata):
            return r.verify_domain_attestation(*case)

    def test_owned_child_domain_is_bound_to_real_inode_and_limits(self):
        case = self.domain_case()
        result = self.attest(case)
        self.assertEqual(result['path'], str(case[0]/'domain'))
        self.assertEqual(result['identity'], [case[1]['domain_dev'], case[1]['domain_ino']])
        self.assertEqual(result['root_pressure_write_errno'], 1)

    def test_namespace_root_cannot_replace_memory_domain(self):
        case = self.domain_case()
        case[2]['domain_relative'] = '/'
        with self.assertRaises(r.Stop):
            self.attest(case)

    def test_unrelated_domain_inode_is_rejected(self):
        case = self.domain_case()
        case[2]['domain_ino'] += 1
        with self.assertRaises(r.Stop):
            self.attest(case)

    def test_namespace_root_bind_cannot_replace_fixed_memory_mount(self):
        case = self.domain_case()
        case[2]['cgroup_ino'] = case[0].stat().st_ino
        with self.assertRaises(r.Stop):
            self.attest(case)

    def test_alternate_lmkd_path_cannot_replace_fixed_contract(self):
        case = self.domain_case()
        case[2]['memory_mount_path'] = '/sys/fs/cgroup/domain'
        with self.assertRaises(r.Stop):
            self.attest(case)

    def test_workload_and_supervisor_membership_are_not_interchangeable(self):
        case = self.domain_case()
        original = case[3]['cgroup']
        case[3]['cgroup'] = case[4]['cgroup']
        with self.assertRaises(r.Stop):
            self.attest(case)
        case[3]['cgroup'] = original
        case[4]['cgroup'] = original
        with self.assertRaises(r.Stop):
            self.attest(case)

    def test_namespace_root_monitor_permission_must_still_be_denied(self):
        case = self.domain_case()
        case[2]['root_pressure_write_errno'] = 0
        with self.assertRaises(r.Stop):
            self.attest(case)

    def test_child_domain_limit_mismatch_and_populated_root_are_rejected(self):
        case = self.domain_case()
        (case[0]/'domain/memory.max').write_text('max\n')
        with self.assertRaises(r.Stop):
            self.attest(case)
        (case[0]/'domain/memory.max').write_text('536870912\n')
        (case[0]/'cgroup.procs').write_text('123\n')
        with self.assertRaises(r.Stop):
            self.attest(case)

if __name__ == '__main__':
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Boundaries)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    receipt = {'scope':'temporary files and fake guards only; no Main/unit/LMKD executed',
               'tests':result.testsRun, 'passed':result.wasSuccessful(),
               'failures':len(result.failures), 'errors':len(result.errors),
               'runner_sha256':hashlib.sha256((HERE/'run_fixture.py').read_bytes()).hexdigest(),
               'output':stream.getvalue()}
    print(json.dumps(receipt, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
