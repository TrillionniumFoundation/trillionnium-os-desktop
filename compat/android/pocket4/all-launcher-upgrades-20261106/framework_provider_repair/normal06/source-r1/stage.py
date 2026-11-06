import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-systemui-provider-build-06-20261106')
EXPECTED = {'actual-builder469-qualification.json': {'bytes': 65386,
                                          'sha256': 'f31bb31d29967bacdb0842eea99dae65f8b67425f26f10063c3d84099367fd64'},
 'actual-builder469-result.json': {'bytes': 37384,
                                   'sha256': 'a14dde5d3a2e85fe44d90c651527c8c8402d341403ef84a7bc92b93252de72b9'},
 'actual-builder470-resource-admission.json': {'bytes': 2746,
                                               'sha256': '5b4b728f90ee088141d2cd9aaa7e242ef33e58b355c790422ed858930c926031'},
 'actual-builder470-result.json': {'bytes': 76136,
                                   'sha256': '6599026ebe5071ecdd5f0e2d962eb96cc791041be0dee9fd59a402735a6387d8'},
 'actual-current-baseline-guard.py': {'bytes': 3213,
                                      'sha256': 'd84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3'},
 'actual-current-guard-source-manifest.json': {'bytes': 749,
                                               'sha256': 'b97002660594ad0ef6e7b453927b8c5b19cba49a5873bc133199d790019b1f9f'},
 'actual-current-qualification.json': {'bytes': 1587,
                                       'sha256': '4bdfe7dd1e275bc4727f37c630dc2498b3dc31c528b03a4028e42c1cf8fc4fc6'},
 'actual-current-runtime-baseline.json': {'bytes': 44041,
                                          'sha256': '7c52723c372b9f486067456e720709ef401bcebe1a7aad158f6b8c099f67fcc8'},
 'actual-native-prebuilt-Android.bp': {'bytes': 1017,
                                       'sha256': 'd1eca99403572ee9d481e777febac8d4e062f44fd8844285ffc452b17beb531a'},
 'actual-provider-source-lock.json': {'bytes': 103409,
                                      'sha256': 'f5717d49fe0d4656b952bd397beab5d2fa70aa0992dd936ac31f81246c9e4772'},
 'actual-published-source-manifest.json': {'bytes': 109252,
                                           'sha256': '5ae96f8d2bc32986fdbf8fea12f54dbcb02b1ed1601894b2b23998f61aba0d7d'},
 'actual-work-preparation.json': {'bytes': 11091,
                                  'sha256': 'ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c'},
 'capture_lifecycle.py': {'bytes': 25240,
                          'sha256': '7fe6569f6665d6b710d2207c53e631261d6eb922d37e24ddfe5de15b841f0126'},
 'expected-builder469-manifest.json': {'bytes': 97964,
                                       'sha256': 'd9340351c9653b10dfd0882afbff5ff4fc11dafaa6083191ed2a8fdb5c8dd934'},
 'expected-builder470-manifest.json': {'bytes': 99075,
                                       'sha256': 'f4a0e6ff82f1ecf9bd786872d99cc0b1608e1d94d0adc37761e87aed449c81bd'},
 'fenced_build.py': {'bytes': 25683,
                     'sha256': '02bfa367fded725a8e62a017e5cec0de870f1f32f455727d2b0b3fc10954c17e'},
 'framework_build.py': {'bytes': 62413,
                        'sha256': '7bb695dd5e7ed4799a30931f1de09ddc1698b7ff140df9775be722a50a1378cb'},
 'frozen-work-inventory.py': {'bytes': 48443,
                              'sha256': '203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab'},
 'main_snapshot.py': {'bytes': 23238,
                      'sha256': '8872df36e07844fe490487db0c2eefe7db095c3b25bdf1e261ec602fa1f4c36e'},
 'parent-normal03-framework_build.py': {'bytes': 59292,
                                        'sha256': '03f0b4aecba20149ad7f1301ea823eb5e7e5ba1efa00d08c92c4fa7ecf482132'},
 'parent-normal05-framework_build.py': {'bytes': 60970,
                                        'sha256': 'f4ab5e09fc22b759811bfa9480c2de555dbc5096bc1258a984dbd33809db734b'},
 'prior-framework-inner-terminal.json': {'bytes': 3176,
                                         'sha256': '232a63a6a48c4248346921ee7f9cb86f13d17dcd3abcb32e6a52856cda0dbbde'},
 'prior-framework-outer-terminal.json': {'bytes': 24715,
                                         'sha256': '1353fe85e19ae79f4b615e7f38efcbb2f45f8a34529a3be6c59a6ed585e1a1f2'},
 'pure_controls.py': {'bytes': 14631,
                      'sha256': '30f48e0bbee38daf1db209fc0dcdee2c8036061d857070eeebb25bc524e4b79b'},
 'root_snapshot_supervisor.py': {'bytes': 12041,
                                 'sha256': 'a3a8f95260d71df60d5f2d51ed34b669fbe398b055dc0cb680002096caf53147'}}
def main(packet):
    if os.getuid()!=1000 or os.geteuid()!=1000:raise RuntimeError('operator UID1000 required')
    if set(packet)!=set(EXPECTED):raise RuntimeError('staged source member set differs')
    for name,text in packet.items():
        path=PurePosixPath(name)
        if not name or path.is_absolute() or '..' in path.parts or str(path)!=name:raise RuntimeError('noncanonical staged source path')
        raw=text.encode('utf-8')
        if len(raw)!=EXPECTED[name]['bytes'] or hashlib.sha256(raw).hexdigest()!=EXPECTED[name]['sha256']:
            raise RuntimeError('staged source pin mismatch: '+name)
    for name,text in packet.items():
        if name.endswith('.py'):
            compile(text,'<staged-'+name+'>','exec')
    binding_scope={'__name__':'normal06_binding_only','__file__':'<normal06-binding-only>'}
    exec(compile(packet['main_snapshot.py'],'main_snapshot.py','exec'),binding_scope,binding_scope)
    binding_scope['qualify_scope_reference'](binding_scope['APP_SCOPE_PIN'],binding_scope['APP_SCOPE_PACKAGES'])
    controls_scope={'__name__':'frozen_host_build_pure_controls','__file__':'<frozen-pure-controls>'}
    exec(compile(packet['pure_controls.py'],'pure_controls.py','exec'),controls_scope,controls_scope)
    controls=controls_scope['run'](packet)
    if controls['state']!='PASS' or controls['passed']!=59:
        raise RuntimeError('new host-only pure controls incomplete')
    for parent in [ROOT.parent,*ROOT.parent.parents]:
        if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('owned root parent aliases non-directory')
    parent=ROOT.parent.lstat()
    if [parent.st_dev,parent.st_ino,parent.st_mode,parent.st_uid,parent.st_gid]!=[66306,34351895,16832,1000,1000]:
        raise RuntimeError('fixed strict owned parent identity differs')
    os.umask(0o077)
    ROOT.mkdir(mode=0o700)
    source=ROOT/'control-source';source.mkdir(mode=0o700)
    for name,text in packet.items():
        path=source/name
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        for parent in [path.parent,*path.parent.parents]:
            if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('staged parent is not a real directory')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,'wb') as stream:
            stream.write(text.encode('utf-8'));stream.flush();os.fsync(stream.fileno())
    raw=(json.dumps({'schema':1,'files':EXPECTED,'pure_controls':controls,'capture_lifecycle_controls_expected':4,'capture_lifecycle_controls_executed':False,'Main_actions':0,'Android_actions':0,'old_QA_epoch_invalid':True,'new_QA_epoch_qualified':False,'only_owned_root_written':True},indent=2)+'\n').encode()
    fd=os.open(ROOT/'stage-receipt.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    scope={'__name__':'frozen_framework_main_fence','__file__':str(source/'fenced_build.py')}
    exec(compile(packet['fenced_build.py'],str(source/'fenced_build.py'),'exec'),scope,scope)
    raise SystemExit(scope['run']({'controller_source':packet['framework_build.py'],
        'snapshot_source':packet['main_snapshot.py'],
        'snapshot_sha256':EXPECTED['main_snapshot.py']['sha256'],
        'lifecycle_source':packet['capture_lifecycle.py'],
        'root_supervisor_source':packet['root_snapshot_supervisor.py']}))
