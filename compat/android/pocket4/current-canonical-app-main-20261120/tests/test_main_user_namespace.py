"""Focused fact validators; fixture facts are never Android runtime evidence."""
import copy
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('new_main_user_namespace', ROOT/'source/main_user_namespace.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def fixture():
    user = {'link':'user:[4002]','device':4,'inode':4002}
    host = {'link':'user:[4001]','device':4,'inode':4001}
    identity = {'host_pid':123,'parent_host_pid':100,'start_ticks':456,
                'namespace_pids':[123,1], 'uids':[100000]*4,
                'namespaces':{'pid':'pid:[5001]','mnt':'mnt:[5002]'}}
    owned = {}
    for index, name in enumerate(m.NS_TYPES, 10):
        ino = {'pid':5001,'mnt':5002}.get(name, 5000+index)
        owned[name] = {'namespace':{'link':name+':['+str(ino)+']','device':4,'inode':ino},
                       'user_namespace':copy.deepcopy(user)}
    value = {'schema':m.SCHEMA,'boot_id':'12345678-1234-1234-1234-123456789abc',
             'init':{key:identity[key] for key in ('host_pid','parent_host_pid','start_ticks','namespace_pids')},
             'user_namespace':user,'parent_user_namespace':host,
             'uid_map':m.map_row(b'         0     100000     100000\n'),
             'gid_map':m.map_row(b'         0     100000     100000\n'),
             'root_uids':[100000]*4,'root_gids':[100000]*4,'owned_entry_namespaces':owned}
    return value, identity


class Tests(unittest.TestCase):
    def test_mapped_main_and_role_facts(self):
        value, identity=fixture()
        self.assertEqual(m.validate_observation(value,value['user_namespace'],identity,value['boot_id']),value)
        role={'user_namespace':value['user_namespace'],'uid_map':value['uid_map'],'gid_map':value['gid_map'],
              'uids':[101000]*4,'gids':[101000]*4}
        system={**identity,'host_pid':124,'uids':[101000]*4}
        self.assertEqual(m.validate_role(role,value,system,'system_server',value['parent_user_namespace']),role)
        self.assertEqual(m.mapped_id(value['uid_map'],10061),110061)

    def test_foreign_namespace_with_identical_maps_refused(self):
        value, identity=fixture(); wrong=copy.deepcopy(value)
        wrong['user_namespace']={'link':'user:[4003]','device':4,'inode':4003}
        with self.assertRaisesRegex(RuntimeError,'DIFFERS_FROM_NATIVE_OWNER'):
            m.validate_observation(wrong,value['user_namespace'],identity,value['boot_id'])
        role={'user_namespace':wrong['user_namespace'],'uid_map':value['uid_map'],'gid_map':value['gid_map'],
              'uids':[100000]*4,'gids':[100000]*4}
        with self.assertRaisesRegex(RuntimeError,'FOREIGN_USER_NAMESPACE'):
            m.validate_role(role,value,identity,'init',value['parent_user_namespace'])

    def test_selected_surfaceflinger_primary_graphics_group(self):
        # Selected rc c6f8279f... declares group graphics first. The exact
        # AOSP source header f67aad90... defines AID_GRAPHICS as 1003, and
        # ServiceParser::ParseGroup assigns args[1] to the primary GID.
        value,identity=fixture()
        surface={**identity,'uids':[101000]*4}
        role={'user_namespace':value['user_namespace'],'uid_map':value['uid_map'],
              'gid_map':value['gid_map'],'uids':[101000]*4,'gids':[101003]*4}
        old=m.ANDROID_IDS['surfaceflinger']
        try:
            m.ANDROID_IDS['surfaceflinger']=(1000,1000)
            with self.assertRaises(RuntimeError):
                m.validate_role(role,value,surface,'surfaceflinger',value['parent_user_namespace'])
        finally:m.ANDROID_IDS['surfaceflinger']=old
        m.validate_role(role,value,surface,'surfaceflinger',value['parent_user_namespace'])
        for bad in ({**role,'gids':[101000]*4},
                    {**role,'user_namespace':{'link':'user:[4999]','device':4,'inode':4999}}):
            with self.assertRaises(RuntimeError):
                m.validate_role(bad,value,surface,'surfaceflinger',value['parent_user_namespace'])

    def test_changed_map_or_root_gids_refused(self):
        value,identity=fixture()
        for key in ('uid_map','gid_map'):
            wrong=copy.deepcopy(value); wrong[key]=m.map_row(b'0 200000 100000\n')
            with self.assertRaisesRegex(RuntimeError,'ROOT_UID_GID'):
                m.validate_observation(wrong,value['user_namespace'],identity,value['boot_id'])
        role={'user_namespace':value['user_namespace'],'uid_map':m.map_row(b'0 200000 100000\n'),
              'gid_map':value['gid_map'],'uids':[100000]*4,'gids':[100000]*4}
        with self.assertRaisesRegex(RuntimeError,'ID_MAP_DIFFERS'):
            m.validate_role(role,value,identity,'init',value['parent_user_namespace'])

    def test_foreign_entry_owner_epoch_and_unknown_roles_refused(self):
        value,identity=fixture()
        wrong=copy.deepcopy(value)
        wrong['owned_entry_namespaces']['net']['user_namespace']=value['parent_user_namespace']
        with self.assertRaisesRegex(RuntimeError,'NOT_OWNED_BY_SAME'):
            m.validate_observation(wrong,value['user_namespace'],identity,value['boot_id'])
        wrong=copy.deepcopy(value); wrong['init']['start_ticks']+=1
        with self.assertRaisesRegex(RuntimeError,'INIT_EPOCH'):
            m.validate_observation(wrong,value['user_namespace'],identity,value['boot_id'])
        role={'user_namespace':value['parent_user_namespace'],'uid_map':'0 0 4294967295\n',
              'gid_map':'0 0 4294967295\n','uids':[0]*4,'gids':[0]*4}
        with self.assertRaisesRegex(RuntimeError,'EXPLICIT_CURRENT_HOST_ROLE'):
            m.validate_role(role,value,{**identity,'uids':[0]*4},'invented_launcher',value['parent_user_namespace'])

    def test_host_role_remains_in_actual_host_namespace(self):
        value,identity=fixture()
        role={'user_namespace':value['parent_user_namespace'],'uid_map':'0 0 4294967295\n',
              'gid_map':'0 0 4294967295\n','uids':[0]*4,'gids':[0]*4}
        host={**identity,'uids':[0]*4}
        m.validate_role(role,value,host,'daemon',value['parent_user_namespace'])
        role['user_namespace']=value['user_namespace']
        with self.assertRaisesRegex(RuntimeError,'HOST_ROLE_LEFT_HOST'):
            m.validate_role(role,value,host,'daemon',value['parent_user_namespace'])

    def test_actual_host_namespace_fd_and_original_counterexamples(self):
        fd=os.open('/proc/self/ns/user',os.O_RDONLY|os.O_CLOEXEC)
        try:
            actual=m.namespace_fact(fd)
            self.assertEqual(actual['link'],os.readlink('/proc/self/ns/user'))
        finally:os.close(fd)
        value,_=fixture()
        # Exact original predicates: all Android roles in host userns, init
        # host UID 0, and live host fstat UID equal raw image guest UID.
        self.assertFalse(value['user_namespace']['link']==value['parent_user_namespace']['link'])
        self.assertFalse(value['root_uids']==[0]*4)
        self.assertFalse(m.mapped_id(value['uid_map'],10061)==10061)


if __name__=='__main__':unittest.main(verbosity=2)
