"""Pure parser/resource-bound checks and the real flock fork lifecycle.

These tests never instantiate a production ReleaseLease or read host CURRENT.
"""
import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import select
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('native_leaf_release',ROOT/'source/native_leaf_release.py')
G = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(G)


def sample():
    def pin(path,size=1):
        return {'path':path,'bytes':size,'sha256':'a'*64}
    owner = {'name':'fixture-owner','generation':'fixture-generation','acquisition_id':'fixture-id',
             'active_until_utc':'2030-01-01T00:00:00+00:00','acquisition':'fixture','scope':'fixture'}
    return {'schema':G.MANIFEST_SCHEMA,'protocol':G.PROTOCOL,'binary':pin(str(G.CLI)),
        'selection':pin('/fixture/selection.json'),
        'catalog':pin(str(G.RELEASE_ROOT/'catalogs'/('a'*64+'.json'))),
        'foreground_owner':owner,'owner_expires_unix_seconds':1893456000,
        'before_current':{**pin(str(G.CURRENT)), 'f9':[1,2,33152,1000,1000,1,1,3,4]},
        'before_current_copy':pin(str(G.RELEASE_ROOT/'current-preimages'/('a'*64+'.json'))),
        'source_tree':'a'*40,'ci_commit':'b'*40,'ci_run_id':1,
        'runtime_qualified':False,'production_ready':False}


class TypedRelease(unittest.TestCase):
    def test_exact_manifest_and_utc_spellings(self):
        value=sample(); self.assertEqual(G.manifest(value),value)
        value['foreground_owner']['active_until_utc']='2030-01-01T00:00:00Z'
        G.manifest(value)

    def test_boolean_numbers_and_false_flags(self):
        for path,value in [(['ci_run_id'],True),(['owner_expires_unix_seconds'],True),
            (['binary','bytes'],True),(['before_current','f9',0],True),
            (['runtime_qualified'],0),(['production_ready'],0)]:
            changed=sample(); parent=changed
            for key in path[:-1]: parent=parent[key]
            parent[path[-1]]=value
            with self.subTest(path=path),self.assertRaises(RuntimeError): G.manifest(changed)

    def test_unknown_fields_and_non_utc_owner(self):
        for path,value in [(['extra'],'bad'),(['foreground_owner','extra'],'bad'),
            (['foreground_owner','active_until_utc'],'2030-01-01T01:00:00+01:00'),
            (['foreground_owner','name'],1),(['before_current','f9'],[1]*8)]:
            changed=sample(); parent=changed
            for key in path[:-1]: parent=parent[key]
            parent[path[-1]]=value
            with self.subTest(path=path),self.assertRaises(RuntimeError): G.manifest(changed)

    def test_duplicate_and_nonfinite_json(self):
        for raw in (b'{"x":1,"x":2}',b'{"a":{"x":1,"x":2}}',b'{"x":NaN}',b'{"x":Infinity}'):
            with self.subTest(raw=raw),self.assertRaises(RuntimeError): G.parse(raw)

    def test_original_resource_hard_bounds_and_refusals(self):
        original={'cpu.max':'200000 100000','memory.max':'2147483648','memory.swap.max':'0','pids.max':'64'}
        G.OwnedLeafResources._limits(original)
        for key,value in [('cpu.max','max 100000'),('cpu.max','200001 100000'),
                          ('cpu.max','0 100000'),('cpu.max','1 0'),
                          ('memory.max','max'),('memory.max','2147483649'),
                          ('memory.swap.max','1'),('pids.max','65')]:
            changed={**original,key:value}
            with self.subTest(key=key,value=value),self.assertRaises(RuntimeError):
                G.OwnedLeafResources._limits(changed)

    def test_real_nested_membership_has_no_parent_or_root_fallback(self):
        self.assertEqual(G.OwnedLeafResources._membership(b'0::/owned/child\n'),'/owned/child')
        for raw in (b'0::/\n',b'0::/owned/../other\n',b'0::/a//b\n',b'0::/a\n1:cpu:/b\n'):
            with self.subTest(raw=raw),self.assertRaises(RuntimeError):
                G.OwnedLeafResources._membership(raw)

    def test_calendar_keeps_half_cpu_and_512_mib_without_gallery_budget_fallback(self):
        spec=importlib.util.spec_from_file_location('native_calendar_release',ROOT/'source/native_calendar_release.py')
        calendar=importlib.util.module_from_spec(spec);spec.loader.exec_module(calendar)
        good={'cpu.max':'50000 100000','memory.max':'536870912','memory.swap.max':'0','pids.max':'64'}
        calendar.OwnedLeafResources._limits(good)
        for key,value in [('cpu.max','50001 100000'),('cpu.max','max 100000'),
                          ('memory.max','2147483648'),('memory.swap.max','1'),('pids.max','65')]:
            with self.subTest(key=key,value=value),self.assertRaises(RuntimeError):
                calendar.OwnedLeafResources._limits({**good,key:value})

    def test_forked_close_does_not_unlock_original_shared_ofd(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'lock'; path.write_bytes(b'')
            fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC); fcntl.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
            lease=object.__new__(G.ReleaseLease)
            lease.closed=False; lease.files=[]; lease.lock_fds=[fd]; lease.directories={}; lease.resource_scope=None
            child=os.fork()
            if child==0:
                try: lease.close()
                finally: os._exit(0)
            pidfd=os.pidfd_open(child,0)
            try:
                poll=select.poll(); poll.register(pidfd,select.POLLIN)
                self.assertTrue(poll.poll(5000),'forked descriptor cleanup must finish')
                self.assertEqual(os.waitpid(child,0),(child,0))
                probe=os.open(path,os.O_RDONLY|os.O_CLOEXEC)
                try:
                    with self.assertRaises(BlockingIOError): fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    lease.close()
                    fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB)
                finally: os.close(probe)
            finally:
                os.close(pidfd); lease.close()


if __name__=='__main__': unittest.main()
