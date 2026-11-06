import hashlib,json,os,stat
from pathlib import Path,PurePosixPath
ROOT = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-systemui-provider-build-08-20261106')
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
 'actual-current470-qualification-result.json': {'bytes': 121931,
                                                 'sha256': '3673f75b77a2133b5fbeecd26b13441d6c4625312c304f7dab8604e2efbfbd69'},
 'actual-current470-qualification-stdout.original.jsonl': {'bytes': 4024,
                                                           'sha256': '2854236b0227f6f89e9c6875708fa4863ead70306d02ee4b510d3fe7ddb790ac'},
 'actual-current470-qualification-terminal.original.json': {'bytes': 731,
                                                            'sha256': '7042c5d094d24aae3eea354d03d9c3d6b94cb647fa0ca23a872814c3753e8e6a'},
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
 'fenced_build.py': {'bytes': 26050,
                     'sha256': '7987820a8760c6ea4ffb7ca8fea186a7e5c5dfa9c64a12137a54a719c524db1f'},
 'framework_build.py': {'bytes': 97024,
                        'sha256': '09c4eebe8615076ca886363d450d103ec3145e532f86a186db2ebbeae5856f5a'},
 'frozen-work-inventory.py': {'bytes': 48443,
                              'sha256': '203dd7f4efdac01891a4c31fd79f2eb3204e3c8c2be5702988f0875307cce9ab'},
 'main_snapshot.py': {'bytes': 24579,
                      'sha256': '7908f4730c658e0d2f43ca66a810eb6d7033634560fcba2d7d928b380795136e'},
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
                                 'sha256': 'ced37d036b93ab8f85803c42ca6a2d0fb18939c78a5d62ef9a2fd0a215176f7b'},
 'settled-build07-diagnosis-stdout.original.jsonl': {'bytes': 4320,
                                                     'sha256': '2a8c2c6c141a76bbc604c039d4dfcc22ab2daac80b6d51286b06718f19e6207b'},
 'settled-build07-diagnosis-terminal.original.json': {'bytes': 728,
                                                      'sha256': '5adba93adeff2d4d540ac0f7ccb41a4d349b66bf2f9bb4769003365a36570d6f'},
 'settled-build07-durable-terminal.original.json': {'bytes': 726,
                                                    'sha256': '629a7963a7c7f2401c4d0f8a554352c262342d0bca246be39d644bcaa1118d82'},
 'settled-build07-fence-terminal.original.json': {'bytes': 24701,
                                                  'sha256': '22c315979504854e249d059762a2ef008fc278c93b26c4a2bd65e0ba0a68bc34'},
 'settled-normal06-after-root-stdout.json': {'bytes': 896,
                                             'sha256': '0df37043724399fd0b3b6597c4e77c6a72e14346271236b65d98a94d1554a58d'},
 'settled-normal06-control-root-stdout.json': {'bytes': 904,
                                               'sha256': 'e78dc93dcb57b4bcd5390d5ff41f82dce63e25be88c311a564969a5396273b5a'},
 'settled-normal06-fence-terminal.json': {'bytes': 8115,
                                          'sha256': '867855adf975072432aada65f4decded4b88c725a6a5d2e9a17909ae1f94b841'}}
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
