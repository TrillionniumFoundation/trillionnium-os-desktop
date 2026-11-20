"""Run the original upstream validators and their new narrow successors.

All process/data rows in this file are explicit fixtures. No Android process,
image, user directory or private data body is opened by these controls.
"""
import copy
import importlib.util
import os
from pathlib import Path
import stat
import types
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
m=load(ROOT/'source/main_user_namespace.py','owner_module')
f=load(ROOT/'tests/test_main_user_namespace.py','facts_fixture')
old_data=load(ROOT/'inputs/original-support/business_data.py','old_data')
new_data=load(ROOT/'source/business_data.py','new_data');new_data._userns_module=m
old_base=load(ROOT/'inputs/original-support/business_baseline.py','old_base')
new_base=load(ROOT/'source/business_baseline.py','new_base')
policy=load(ROOT/'inputs/main/baseline_policy.py','actual_original_policy')
old_epoch=load(ROOT/'inputs/main/framework_epoch.py','actual_original_epoch')


def row(pid,parent,uid,argv,exe,ns_pid,ns_mnt):
    return {'host_pid':pid,'parent_host_pid':parent,'start_ticks':pid+333,
            'namespace_pids':[pid] if ns_pid==6001 else [pid,pid-122],
            'uids':[uid]*4,'cmdline':argv,'executable':exe,
            'namespaces':{'pid':'pid:['+str(ns_pid)+']','mnt':'mnt:['+str(ns_mnt)+']'},
            'cgroup':['0::/system.slice/droidloomd.service']}


def baseline(legacy):
    mapping,init=f.fixture()
    rows={
        'daemon':row(100,1,0,['/usr/bin/droidloomd'],'/usr/bin/droidloomd',6001,6002),
        'presenter':row(101,1,1000,['/usr/bin/droidloom-wayland'],'/usr/bin/droidloom-wayland',6001,6002),
        'init':row(123,112 if legacy else 100,100000,['/init'],'/system/bin/init',5001,5002),
        'zygote64':row(124,123,100000,['zygote64'],'/system/bin/app_process64',5001,5003),
        'system_server':row(125,124,101000,['system_server'],'/system/bin/app_process64',5001,5003),
        'surfaceflinger':row(126,123,101000,['/system/bin/surfaceflinger'],'/system/bin/surfaceflinger',5001,5002)}
    if legacy:
        rows['launcher']=row(110,100,0,['python3'],'/usr/bin/python3',6001,6002)
        rows['owner_intermediary']=row(112,110,0,['unshare'],'/usr/bin/unshare',6001,6002)
    mapping['init']={key:rows['init'][key] for key in ('host_pid','parent_host_pid','start_ticks','namespace_pids')}
    value={'roles':rows,'roots':{},'namespaces':{},'executables':{k:{} for k in rows},
           'child_tables':{},'host_user_namespace':mapping['parent_user_namespace']['link'],
           'limits':dict(old_base.LIMITS)}
    facts={}
    for role,identity in rows.items():
        android=role in m.ANDROID_IDS
        value['roots'][role]={'device':8,'inode':2 if android else 3}
        namespaces={}
        for index,name in enumerate(old_base.NS):
            if name=='user':item=copy.deepcopy(mapping['user_namespace'] if android else mapping['parent_user_namespace'])
            else:
                link=identity['namespaces'].get(name,name+':['+str(7000+index)+']')
                item={'link':link,'device':4,'inode':int(link.split('[')[1][:-1])}
            namespaces[name]=item
        value['namespaces'][role]=namespaces
        facts[role]={'user_namespace':namespaces['user'],
                     'uid_map':mapping['uid_map'] if android else '0 0 4294967295\n',
                     'gid_map':mapping['gid_map'] if android else '0 0 4294967295\n',
                     'uids':identity['uids'],'gids':[101003]*4 if role=='surfaceflinger' else identity['uids']}
    edges=(('daemon','launcher'),('launcher','owner_intermediary'),('owner_intermediary','init')) if legacy else (('daemon','init'),)
    for parent,child in edges:
        pid=rows[parent]['host_pid'];children=[rows[child]['host_pid']]
        if not legacy:children.append(170)
        value['child_tables'][parent]={'thread_ids':[pid],'per_thread':{str(pid):children},'child_host_pids':children}
    if not legacy:value.update(main_user_namespace=mapping,role_user_namespaces=facts)
    return value,rows,mapping


def data_fixture(mapped):
    package='explicit.fixture.package';guest=10061;device=os.makedev(7,42)
    image_meta={'st_dev':8,'st_ino':100,'st_mode':stat.S_IFREG|0o600,'st_uid':0,'st_gid':0,
                'st_nlink':1,'st_size':1024*1024}
    pre={'images_before':{'data.img':{'filesystem_uuid':'12345678-1234-1234-1234-123456789abc','file':image_meta}},
         'packages':{package:guest},'targets':{package:{'image_paths':{}}}}
    dirs={};mounts=[]
    for index,kind in enumerate(('user','user_de'),1):
        rel=kind+'/0/'+package;image=('/data/' if kind=='user' else '/user_de/0/')+package
        pre['targets'][package]['image_paths'][image]={'exists':True,'stat':{'type':'directory','inode':1000+index,'uid':guest,'gid':guest}}
        dirs[rel]={'android_path':'/data/'+rel,'image_path':image,'device':device,
                   'inode':1000+index,'uid':guest+(100000 if mapped else 0),'gid':guest+(100000 if mapped else 0),'mode_observed':0o700}
        mounts.append({'mount_id':index,'parent_mount_id':0,'major_minor':'7:42',
                       'root':'/data' if kind=='user' else '/user_de/0','mountpoint':'/data/'+kind+'/0',
                       'mount_options':'rw','optional_fields':[],'filesystem':'ext4','source':'/dev/loop42','super_options':'rw'})
    proof={'schema':'pocket4-live-data-continuity-v1','preimage':old_data.PREIMAGE,
           'filesystem_uuid':pre['images_before']['data.img']['filesystem_uuid'],
           'backing_image_identity':image_meta,'backing_image_path':str(old_data.DATA_IMAGE),
           'live_device':{'device':device,'major_minor':'7:42','loop_name':'loop42','backing_file':str(old_data.DATA_IMAGE),'offset':0,'sizelimit':0},
           'package_uids':{package:guest},'directories':dirs,'selected_mount_rows':mounts,
           'namespace_entry':False,'Android_commands':0,'app_data_writes':0,'business_accepted':False}
    return pre,proof


class Tests(unittest.TestCase):
    def test_original_epoch_rejects_actual_shifted_uid_shape(self):
        _,rows,_=baseline(False)
        with mock.patch.object(old_epoch,'process_identity',return_value=rows['init']):
            with self.assertRaisesRegex(old_epoch.EpochError,'ANDROID_INIT_UNVERIFIED'):
                old_epoch.capture_android(123)

    def test_original_baseline_and_native_topology_counterexamples(self):
        value,rows,_=baseline(True)
        with self.assertRaisesRegex(RuntimeError,'ACTUAL_USER_AND_FINAL_PID_MNT_NAMESPACES'):
            old_base.validate_observation(value,rows,policy)
        actual,rows,_=baseline(False)
        with self.assertRaisesRegex(RuntimeError,'OWNER_SINGLE_DIRECT_CHILD'):
            policy.validate_child_table(actual['child_tables']['daemon'],100,123)
        new_base.validate_broker_child_table(actual['child_tables']['daemon'],100,123)

    def test_new_baseline_mapping_and_foreign_namespace_refusal(self):
        value,rows,mapping=baseline(False)
        with mock.patch.object(new_base,'data_module',return_value=types.SimpleNamespace(userns_module=lambda:m)):
            new_base.validate_observation(value,rows,policy,mapping)
            bad=copy.deepcopy(value)
            bad['role_user_namespaces']['zygote64']['user_namespace']={'link':'user:[4999]','device':4,'inode':4999}
            bad['namespaces']['zygote64']['user']=bad['role_user_namespaces']['zygote64']['user_namespace']
            with self.assertRaisesRegex(RuntimeError,'FOREIGN_USER_NAMESPACE'):
                new_base.validate_observation(bad,rows,policy,mapping)
            bad=copy.deepcopy(value);bad['role_user_namespaces']['system_server']['gid_map']=m.map_row(b'0 200000 100000\n')
            with self.assertRaisesRegex(RuntimeError,'ID_MAP_DIFFERS'):
                new_base.validate_observation(bad,rows,policy,mapping)

    def test_actual_old_data_validator_rejects_shifted_owner(self):
        pre,old=data_fixture(False)
        old_data.validate_live(pre,old)
        pre,shifted=data_fixture(True)
        with self.assertRaisesRegex(RuntimeError,'DATA_DIRECTORY_IDENTITY_REPLACED'):
            old_data.validate_live(pre,shifted)

    def test_new_data_keeps_inode_raw_guest_facts_and_mapped_host_owner(self):
        pre,proof=data_fixture(True);mapping,_=f.fixture()
        proof.update(schema='pocket4-live-data-continuity-v2',main_user_namespace=mapping)
        before=copy.deepcopy(pre)
        new_data.validate_live(pre,proof,mapping)
        self.assertEqual(pre,before)
        for key in ('uid','gid','inode'):
            bad=copy.deepcopy(proof);next(iter(bad['directories'].values()))[key]+=1
            with self.assertRaises(RuntimeError):new_data.validate_live(pre,bad,mapping)
        bad=copy.deepcopy(proof);bad['main_user_namespace']['user_namespace']['inode']+=1
        with self.assertRaisesRegex(RuntimeError,'ORIGINAL_MAIN_MAPPING_DIFFER'):
            new_data.validate_live(pre,bad,mapping)


if __name__=='__main__':unittest.main(verbosity=2)
