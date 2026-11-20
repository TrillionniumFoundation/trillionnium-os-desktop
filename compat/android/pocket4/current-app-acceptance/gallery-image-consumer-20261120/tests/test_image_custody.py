"""Offline controls using the exact 2360 Rust unit-model wire shape.

These values create no Ready owner, descriptor, actual read receipt, image
custody, data continuity or business acceptance. Real capture is a separate
interface with the original recorder, covered by its exact argument contract.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('custody', ROOT/'src/gallery_image_custody.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


def model():
    def file(device, inode, mode, uid, size):
        return dict(device=device, inode=inode, mode=mode, uid=uid, gid=uid, links=1,
                    bytes=size, modified=[1, 0], changed=[2, 0])
    def read(argv, stdout, ordinal):
        query = 1000 + 2*ordinal
        return {'argv': argv, 'stdout': stdout, 'receipt': {
            'worker_pid': query+1, 'worker_waitid_code': 1, 'worker_waitid_status': 0,
            'query_pid': query, 'query_waitid_code': 1, 'query_waitid_status': 0,
            'output_bytes': len(stdout.encode()), 'output_sha256': c.sha(stdout.encode()),
            'elapsed_millis': 1, 'cgroup_removed': True,
            'exec': {'query_start_ticks': 500+ordinal, 'original_parent_pid': 99, 'tracer_tid': 99,
                'waitid_code': 4, 'waitid_status': 1029, 'event_previous_tid': query,
                'executable': {'dev': 1, 'ino': 55, 'mode': 33261, 'uid': 100000, 'gid': 100000,
                    'nlink': 1, 'bytes': 128, 'mtime': 1, 'mtime_nsec': 0, 'ctime': 2, 'ctime_nsec': 0},
                'executable_mount_id': 50, 'executable_sha256': 'b'*64,
                'executable_selinux': 'u:object_r:droidloom_query_exec:s0',
                'process_selinux': 'u:r:droidloom_query:s0',
                'process_apparmor': 'droidloom-production-android//&droidloom-production-broker (enforce)',
                'uid': 102000, 'gid': 102000, 'no_new_privileges': True, 'seccomp_filter_mode': 2}}}
    cohort_sha = 'a'*64
    def image(role, device, inode, size, digest):
        return dict(role=role, path='/var/lib/droidloom/cohorts/'+cohort_sha+'/images/'+role+'.img',
            file=file(1, inode, 0o100644, 0, size), sha256=digest,
            loop_node=file(2, inode+50, 0o060660, 0, 0), loop_device=device, loop_number=inode,
            loop_source_device=1, loop_source_inode=inode, loop_offset=0, loop_size_limit=0,
            loop_flags=5, mount_id=inode, mount_root=file(device, 2, 0o040755, 100000, 4096),
            mount_flags=7, filesystem='ext4')
    user = dict(name='user', device=4, inode=10)
    namespaces = [dict(name=name, device=4, inode=11+i)
                  for i, name in enumerate(('mount', 'pid', 'ipc', 'uts', 'net', 'cgroup'))]+[user]
    cohort = dict(manifest_path='/etc/droidloom/cohorts/'+cohort_sha+'.json',
        manifest=file(1, 5, 0o100644, 0, 500), manifest_sha256=cohort_sha, host_uid=1000,
        user_namespace=user, uid_range=[100000, 65536], gid_range=[100000, 65536],
        system=image('system', 259, 20, c.SYSTEM_BYTES, c.SYSTEM_SHA256),
        vendor=image('vendor', 260, 21, 4096, 'e'*64))
    path = c.APK_PATHS[1]
    app = dict(package=c.PACKAGE, user=0, uid=10064, version_code=40030,
        epoch=dict(boot_id='00000000-0000-0000-0000-000000000001', cell_host_pid=321,
                   framework_host_pid=322, framework_start_ticks=101),
        apks=[dict(name='base.apk', path=path, bytes=c.APK_BYTES, sha256=c.APK_SHA256)])
    package = ['/system/bin/cmd', 'package', 'list', 'packages', '--user', '0', '-U', '--show-versioncode', c.PACKAGE]
    paths = ['/system/bin/cmd', 'package', 'path', '--user', '0', c.PACKAGE]
    st = ['/system/bin/toybox', 'stat', '-c', '%d:%i:%s:%y:%z', path]
    checksum = ['/system/bin/toybox', 'sha256sum', path]
    p = 'package:'+c.PACKAGE+' uid:10064 versionCode:40030\n'
    a = 'package:'+path+'\n'
    s = '259:123:'+str(c.APK_BYTES)+':2026-11-20 00:00:00.0 +0000:2026-11-20 00:00:00.0 +0000\n'
    h = c.APK_SHA256+'  '+path+'\n'
    original = dict(path=c.APK_SOURCE, file=file(259, 123, 0o100644, 100000, c.APK_BYTES),
                    sha256=c.APK_SHA256, mount_id=20)
    custody = dict(schema='droidloom-image-application-custody-v1', application=copy.deepcopy(app),
        owner=dict(host_uid=1000, cell_host_pid=321, cell_start_ticks=100,
                   selection_binding_sha256='c'*64, base_cohort_sha256=cohort_sha,
                   runtime_manifest_sha256='d'*64, namespaces=namespaces),
        cohort=cohort, after_cohort=copy.deepcopy(cohort), original_apk=original,
        after_original_apk=copy.deepcopy(original),
        reads=[read(argv, stdout, ordinal) for ordinal, (argv, stdout) in enumerate(
            ((package,p),(paths,a),(st,s),(checksum,h),(st,s),(package,p),(paths,a)))],
        elapsed_millis=100, data_continuity_qualified=False, runtime_qualified=False,
        business_qualified=False, production_ready=False)
    # A real serialized wire value has no shared mutable object aliases.
    return json.loads(json.dumps(dict(operation='inspect_installed_application', observation=app, image_custody=custody,
                data_continuity_qualified=False, production_ready=False, runtime_qualified=False, app_launches=0)))


def set_path(value, path, replacement):
    cursor = value
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = replacement


class WireControls(unittest.TestCase):
    def test_exact_rust_wire_model_is_coherent_and_unqualified(self):
        value = model()
        result = c.validate_response(c.decode(c.canonical(value)), value['observation']['epoch'])
        self.assertEqual(result, value)
        self.assertIs(result['production_ready'], False)
        self.assertIs(result['image_custody']['data_continuity_qualified'], False)

    def test_uid_is_observed_instead_of_historic_constant(self):
        value = model(); value['observation']['uid'] = value['image_custody']['application']['uid'] = 10112
        for ordinal in (0, 5):
            read = value['image_custody']['reads'][ordinal]
            read['stdout'] = read['stdout'].replace('uid:10064', 'uid:10112')
            read['receipt']['output_sha256'] = c.sha(read['stdout'].encode())
        c.validate_response(value, value['observation']['epoch'])

    def test_adversarial_custody_changes_are_rejected(self):
        changes = [
            (('production_ready',), True), (('runtime_qualified',), 0),
            (('app_launches',), False), (('image_custody',), None),
            (('observation', 'uid'), True), (('observation', 'apks', 0, 'sha256'), 'f'*64),
            (('observation', 'apks', 0, 'path'), '/data/app/old/base.apk'),
            (('image_custody','data_continuity_qualified'), True),
            (('image_custody','business_qualified'), True), (('image_custody','elapsed_millis'), 300000),
            (('image_custody','owner','cell_host_pid'), 999),
            (('image_custody','owner','runtime_manifest_sha256'), ''),
            (('image_custody','owner','namespaces'), []),
            (('image_custody','after_cohort','vendor','sha256'), 'f'*64),
            (('image_custody','after_original_apk','file','inode'), 999),
            (('image_custody','reads'), []),
            (('image_custody','reads',3,'receipt','query_waitid_status'), 1),
            (('image_custody','reads',3,'receipt','worker_waitid_code'), True),
            (('image_custody','reads',3,'receipt','cgroup_removed'), False),
            (('image_custody','reads',3,'receipt','output_bytes'), 1),
            (('image_custody','reads',3,'receipt','exec','event_previous_tid'), 1),
            (('image_custody','reads',3,'receipt','exec','uid'), 0),
            (('image_custody','reads',3,'receipt','exec','no_new_privileges'), 1),
            (('image_custody','reads',3,'receipt','exec','process_selinux'), 'u:r:su:s0'),
            (('image_custody','reads',0,'argv'), ['/system/bin/id']),
        ]
        for path, replacement in changes:
            with self.subTest(path=path):
                value = model(); set_path(value, path, replacement)
                with self.assertRaises((RuntimeError, TypeError, KeyError)):
                    c.validate_response(value, model()['observation']['epoch'])

    def test_coherent_wrong_image_or_mount_cannot_pass_bookends(self):
        changes = [(('system','sha256'),'f'*64), (('system','loop_flags'),1),
                   (('system','loop_source_inode'),999), (('system','mount_flags'),6),
                   (('system','file','bytes'), c.SYSTEM_BYTES-512),
                   (('vendor','file','inode'),20), (('user_namespace','inode'),999)]
        for path, replacement in changes:
            with self.subTest(path=path):
                value = model()
                for key in ('cohort', 'after_cohort'):
                    set_path(value['image_custody'][key], path, replacement)
                with self.assertRaises(RuntimeError):
                    c.validate_response(value, value['observation']['epoch'])

    def test_original_member_inode_is_independently_reproduced_by_pm(self):
        value=model()
        for key in ('original_apk','after_original_apk'):
            value['image_custody'][key]['file']['inode']=999
        with self.assertRaisesRegex(RuntimeError,'PM_APK_IS_NOT_ORIGINAL_MOUNT_INODE'):
            c.validate_response(value,value['observation']['epoch'])

    def test_saved_model_does_not_construct_capture(self):
        value=model()
        with self.assertRaisesRegex(RuntimeError,'SERIALIZED_RECEIPTS'):
            c.CapturedImage(object(),value,{}, {})

    def test_extra_authority_duplicate_keys_and_nonfinite_values_rejected(self):
        value=model(); value['image_custody']['reuse_pid_as_authority']=321
        with self.assertRaises(RuntimeError): c.validate_response(value,value['observation']['epoch'])
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}'):
            with self.assertRaises(RuntimeError): c.decode(raw)

    def test_epoch_is_exact(self):
        value=model(); epoch=copy.deepcopy(value['observation']['epoch']); epoch['framework_start_ticks']+=1
        with self.assertRaisesRegex(RuntimeError,'CURRENT_EPOCH_DIFFER'):
            c.validate_response(value,epoch)


if __name__=='__main__':
    unittest.main()
