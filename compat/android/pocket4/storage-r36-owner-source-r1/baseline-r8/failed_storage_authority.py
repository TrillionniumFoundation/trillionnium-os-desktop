"""Pure typed input boundary for a future owner after the failed r6 epoch.

SOURCE_ONLY candidate. FROZEN_BINDING is the exact complete ten-document
failed-r6 family. The actual limited finalizer ROOT observation is a fact input,
never issuance of successor storage ownership, a manifest, or an executable request. This module has no CLI, IO, mutable setter, old
schema compatibility branch, mount operation, or lease renewal.
"""
import hashlib
import json
import math
import stat
from recovery_core import require, encoded
from f9_authority import full_ref

FROZEN_BINDING = {'expected_finalizer_native': {'H_job_id': None,
                               'InvocationID': '8e8c55476e304b4a92ce1b4b61997ae9',
                               'boot': '97d9600f-e081-465c-9e6e-62651e09806b',
                               'cgroup': '/sys/fs/cgroup/system.slice/p4-r6-failed-storage-finalize-e6ac-r1.service',
                               'execution_kind': 'native_systemd_system_unit',
                               'limits': {'cpu.max': '200000 100000',
                                          'cpuset.cpus.effective': '2-3',
                                          'memory.high': '402653184',
                                          'memory.max': '536870912',
                                          'memory.swap.max': '0',
                                          'pids.max': '64'},
                               'pid': 2872686,
                               'start_ticks': '67109973',
                               'state': {'ActiveState': 'active',
                                         'ControlGroup': '/system.slice/p4-r6-failed-storage-finalize-e6ac-r1.service',
                                         'Description': 'Pocket4 r6 failed-storage ordinary offline finalization e6ac r1',
                                         'ExecMainCode': '0',
                                         'ExecMainPID': '2872686',
                                         'ExecMainStartTimestampMonotonic': '671099730402',
                                         'ExecMainStatus': '0',
                                         'ExecStart': '{ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 -I -B '
                                                      '/home/alex/work/p4-r6-failed-storage-finalize-e6ac-r1.py '
                                                      '896d4ef1245424739ef3a834e5d92d4445a76ba83621b1740f29d1459498400a '
                                                      '3e417a93ae1040e7b01e51424f9a48b0142750e5edba5103d0067f0c256e0526 ; ignore_errors=no ; start_time=[Mon '
                                                      '2026-11-16 18:30:02 PST] ; stop_time=[n/a] ; pid=2872686 ; code=(null) ; status=0/0 }',
                                         'Group': '1000',
                                         'Id': 'p4-r6-failed-storage-finalize-e6ac-r1.service',
                                         'InvocationID': '8e8c55476e304b4a92ce1b4b61997ae9',
                                         'LoadState': 'loaded',
                                         'MainPID': '2872686',
                                         'Result': 'success',
                                         'SubState': 'running',
                                         'User': '1000'},
                               'unit': 'p4-r6-failed-storage-finalize-e6ac-r1.service'},
 'finalizer_source': {'bytes': 51638,
                      'identity': [66306, 31392799, 33152, 1000, 1000, 1, 51638, 1794881643365407979, 1794881643369495366],
                      'path': '/home/alex/work/p4-r6-failed-storage-finalize-e6ac-r1.py',
                      'sha256': '896d4ef1245424739ef3a834e5d92d4445a76ba83621b1740f29d1459498400a'},
 'original_source_pins': {'admit.py': {'bytes': 5797,
                                       'identity': [66306, 51249156, 33060, 0, 0, 1, 5797, 1794799632324164762, 1794799632324164762],
                                       'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/admit.py',
                                       'sha256': '06d984fd3ef57bfafe3d34296292f81d375bafd9872bf4868c518cb80e1acd40'},
                          'cd_authority.py': {'bytes': 19125,
                                              'identity': [66306, 51249157, 33060, 0, 0, 1, 19125, 1794799632329158373, 1794799632329158373],
                                              'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/cd_authority.py',
                                              'sha256': '913b16bedbbf549b41bbf0a9ec75ce29fb2b0447c57f195a09d72d2e7782aced'},
                          'cd_observed_root.py': {'bytes': 8267,
                                                  'identity': [66306, 51249158, 33060, 0, 0, 1, 8267, 1794799632332128266, 1794799632332128266],
                                                  'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/cd_observed_root.py',
                                                  'sha256': '98c1a0799e43d71a0ee52633b87a53ab7acd734acef46039bf007055129da05b'},
                          'cd_retired_epoch.py': {'bytes': 8603,
                                                  'identity': [66306, 51249159, 33060, 0, 0, 1, 8603, 1794799632335367139, 1794799632335367139],
                                                  'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/cd_retired_epoch.py',
                                                  'sha256': '8920c801a7e73f6099db82f648f27831ef40f508171ede4adc0019aedca4a250'},
                          'common.py': {'bytes': 22772,
                                        'identity': [66306, 51249160, 33060, 0, 0, 1, 22772, 1794799632340125975, 1794799632340125975],
                                        'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/common.py',
                                        'sha256': 'c86a19cc8881b12158628c70b912f9d48ac2a88eab1f2c908b207928bcf65988'},
                          'contract.json': {'bytes': 34881,
                                            'identity': [66306, 51249161, 33060, 0, 0, 1, 34881, 1794799632343152706, 1794799632343152706],
                                            'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/contract.json',
                                            'sha256': '82fb4673297eed094abae0a9d8093f0e03a86e9d9f622e60bbebaa94d7d3fdd7'},
                          'current_offline.py': {'bytes': 15027,
                                                 'identity': [66306, 51249162, 33060, 0, 0, 1, 15027, 1794799632346164679, 1794799632346164679],
                                                 'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/current_offline.py',
                                                 'sha256': '06453eed6553c352630691d1c9b78206b0a213c6d3706647e0a6310626710ec6'},
                          'current_offline_root.py': {'bytes': 9791,
                                                      'identity': [66306, 51249163, 33060, 0, 0, 1, 9791, 1794799632349144791, 1794799632349144791],
                                                      'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/current_offline_root.py',
                                                      'sha256': 'a29910861c6500c4cf26716f433f77295baedb1d964cf3e3d88b77c6a8eaf24e'},
                          'desktop_owner.py': {'bytes': 28898,
                                               'identity': [66306, 51249164, 33060, 0, 0, 1, 28898, 1794799632355144871, 1794799632355144871],
                                               'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/desktop_owner.py',
                                               'sha256': 'ac513857a5f6485753fd57f1104e3899121678cf1d1d7b47ce6f904e397bcfdc'},
                          'dispatch.py': {'bytes': 4105,
                                          'identity': [66306, 51249165, 33060, 0, 0, 1, 4105, 1794799632358156493, 1794799632358156493],
                                          'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/dispatch.py',
                                          'sha256': 'b885f02f3910fb599c8382ccbd901650bfb87bcbe3fac23c11670331bd2d4031'},
                          'dispatch_role.py': {'bytes': 5311,
                                               'identity': [66306, 51249166, 33060, 0, 0, 1, 5311, 1794799632361119343, 1794799632361119343],
                                               'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/dispatch_role.py',
                                               'sha256': 'fbd140d9652e5982b22056fd6751441c608f45542f1745d070d02761eacbacd8'},
                          'f9_authority.py': {'bytes': 15268,
                                              'identity': [66306, 51249167, 33060, 0, 0, 1, 15268, 1794799632364117830, 1794799632364117830],
                                              'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/f9_authority.py',
                                              'sha256': '4b6126fd125bd2a942320d1532bcb950439443439f28fb2c49be168cad59adac'},
                          'f9_contract.py': {'bytes': 10548,
                                             'identity': [66306, 51249168, 33060, 0, 0, 1, 10548, 1794799632367115636, 1794799632367115636],
                                             'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/f9_contract.py',
                                             'sha256': '7e86c8956d5e57b3e8b348635307d84c3928b5d36ed08ec6f1b83250515c3d40'},
                          'f9_inputs.py': {'bytes': 13440,
                                           'identity': [66306, 51249169, 33060, 0, 0, 1, 13440, 1794799632368621673, 1794799632368621673],
                                           'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/f9_inputs.py',
                                           'sha256': '6528caf63d01091b5f884e18b6ddfdc92f1c19e1e2c1d506568a92ed725a78e4'},
                          'f9_lease.py': {'bytes': 3838,
                                          'identity': [66306, 51249170, 33060, 0, 0, 1, 3838, 1794799632372477807, 1794799632372477807],
                                          'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/f9_lease.py',
                                          'sha256': '57d9248aab8865d21d0e103a6a4088b56e1d9e30526d1d674916cb983feb18e9'},
                          'f9_result.py': {'bytes': 5021,
                                           'identity': [66306, 51249171, 33060, 0, 0, 1, 5021, 1794799632376158808, 1794799632376158808],
                                           'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/f9_result.py',
                                           'sha256': '398d9f2a09d09473f633c92e7f6e6e885b131f97fa409e389982f2006c077dda'},
                          'namespace_entry.py': {'bytes': 12546,
                                                 'identity': [66306, 51249172, 33060, 0, 0, 1, 12546, 1794799632379142488, 1794799632379142488],
                                                 'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/namespace_entry.py',
                                                 'sha256': '3355bea57d37bd9ba9720befed0912877e217f23997cf81ab788d20fbe813597'},
                          'offline_paged_terminal.py': {'bytes': 14210,
                                                        'identity': [66306, 51249173, 33060, 0, 0, 1, 14210, 1794799632382146735, 1794799632382146735],
                                                        'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/offline_paged_terminal.py',
                                                        'sha256': '52a4acf7e8eb04e2fb30e66634376768209e1396881e5b179cdd6bd892a1b59c'},
                          'p4_finalize.py': {'bytes': 12502,
                                             'identity': [66306, 51249174, 33060, 0, 0, 1, 12502, 1794799632385138099, 1794799632385138099],
                                             'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/p4_finalize.py',
                                             'sha256': 'fe69a88f11eeda9f6e7fded3046cf70f92f967d5e6c2bd58db0e0edaecf0e424'},
                          'p4_server.py': {'bytes': 7386,
                                           'identity': [66306, 51249175, 33060, 0, 0, 1, 7386, 1794799632388137087, 1794799632388137087],
                                           'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/p4_server.py',
                                           'sha256': '00ba28362898b85ef450dc06280271e7a55babf5ba26b5d2f4e9fad28180e7c0'},
                          'paged_terminal.py': {'bytes': 9212,
                                                'identity': [66306, 51249176, 33060, 0, 0, 1, 9212, 1794799632390671524, 1794799632390671524],
                                                'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/paged_terminal.py',
                                                'sha256': 'e382b4e074a5dfcee4ef34b7e1b63f9a35739d4d1dbf89f6829a000a2130f12a'},
                          'prepare.py': {'bytes': 4444,
                                         'identity': [66306, 51249177, 33060, 0, 0, 1, 4444, 1794799632394167836, 1794799632394167836],
                                         'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/prepare.py',
                                         'sha256': '64685cccea0d060b5ddf1225c95f621823cec8a2e2dca3faa01c28742bb6be6d'},
                          'recovery_core.py': {'bytes': 14292,
                                               'identity': [66306, 51249178, 33060, 0, 0, 1, 14292, 1794799632397135675, 1794799632397135675],
                                               'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/recovery_core.py',
                                               'sha256': 'f5fec37975aad147110670e30867a9f7c040b5238f140dec016dc82426aaa411'},
                          'retire.py': {'bytes': 12357,
                                        'identity': [66306, 51249179, 33060, 0, 0, 1, 12357, 1794799632400142959, 1794799632400142959],
                                        'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/retire.py',
                                        'sha256': 'd88274dce0ca70095347f9dbd902383ebea8e05c2a2b5a46fed2b8811d46e59e'},
                          'rotation_support.py': {'bytes': 20773,
                                                  'identity': [66306, 51249180, 33060, 0, 0, 1, 20773, 1794799632404141943, 1794799632404141943],
                                                  'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/rotation_support.py',
                                                  'sha256': '9ab6a1ccbada7db43c35c48f55efd795af236bd600234ef1ade4705c70583a35'},
                          'seal_admission.py': {'bytes': 1861,
                                                'identity': [66306, 51249181, 33060, 0, 0, 1, 1861, 1794799632409150052, 1794799632409150052],
                                                'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/seal_admission.py',
                                                'sha256': '8a773e2f87bf6f271ccaf4958676cb0cda74278f3bdfce71ebd7b663325632a3'},
                          'storage_support.py': {'bytes': 18968,
                                                 'identity': [66306, 51249182, 33060, 0, 0, 1, 18968, 1794799632411108186, 1794799632411108186],
                                                 'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-storage-source-r6/storage_support.py',
                                                 'sha256': 'd87e5989a74929d1d927b9ded753afa55594a1eeef28e8ff4ae02faa8a52eedd'}},
 'original_tool_pins': {'blkid': {'bytes': 55800,
                                  'identity': [66306, 108028171, 33261, 0, 0, 1, 55800, 1787149416000000000, 1791083664418813240],
                                  'path': '/usr/sbin/blkid',
                                  'sha256': 'ca21432531372e34870eb11e78d700fe4cacbae47b2a35fa80fafc97b6946389'},
                        'debugfs': {'bytes': 231368,
                                    'identity': [66306, 108006000, 33261, 0, 0, 1, 231368, 1770985020000000000, 1791083649320555768],
                                    'path': '/usr/sbin/debugfs',
                                    'sha256': '864e1d7b445e7b5bfc831da78330dbcafc590fa82b89ea9de60b7527f989954f'},
                        'e2fsck': {'bytes': 377416,
                                   'identity': [66306, 108006003, 33261, 0, 0, 1, 377416, 1770985020000000000, 1791083649320555768],
                                   'path': '/usr/sbin/e2fsck',
                                   'sha256': '2e51f521c676729920eaba694933d9d4048645f1a5789556fd0027e62d11ecc8'},
                        'mkfs.ext4': {'bytes': 146136,
                                      'identity': [66306, 108017173, 33261, 0, 0, 1, 146136, 1770985020000000000, 1791083649321555785],
                                      'path': '/usr/sbin/mke2fs',
                                      'sha256': 'e42e49656dfc308efeed86f9bfad7746fc22ad1d4a3b0d508b5dba7a4b9a904f'},
                        'python3': {'bytes': 7477160,
                                    'identity': [66306, 108009763, 33261, 0, 0, 1, 7477160, 1787222518000000000, 1791083390422846841],
                                    'path': '/usr/bin/python3.14',
                                    'sha256': '52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41'},
                        'qemu-nbd': {'bytes': 2711952,
                                     'identity': [66306, 33992140, 33261, 1000, 1000, 1, 2711952, 1788340723000000000, 1794656378479123447],
                                     'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/tools/usr/bin/qemu-nbd',
                                     'sha256': 'd8f406908c6a47d135a4d50b85c9c0c677a4294aa472c21f3a6c1895ad36b140'},
                        'systemctl': {'bytes': 302112,
                                      'identity': [66306, 108017358, 33261, 0, 0, 1, 302112, 1789570531000000000, 1792945456488110570],
                                      'path': '/usr/bin/systemctl',
                                      'sha256': '639bce3ce5c06b605079ea56f74e3f08216ddffcfa76e11f62073aa775180082'},
                        'systemd-run': {'bytes': 97272,
                                        'identity': [66306, 108038720, 33261, 0, 0, 1, 97272, 1789570531000000000, 1792945456490110634],
                                        'path': '/usr/bin/systemd-run',
                                        'sha256': '6eaf6650fc3bc07ba2fb51242d9d286e56770a2abd7306678aa22050ddf9f935'}},
 'originals': {'desktop.result': {'bytes': 100782,
                                  'identity': [2067, 38148312, 33060, 0, 0, 1, 100782, 1794867103633386058, 1794867103633386058],
                                  'path': '/data/p4-production651-nbd-e6ac-r6/DESKTOP-RESULT.json',
                                  'sha256': '66635d410684790522e145f56f4c136962390629ecc047942fc3ebc8b3f78a9d'},
               'desktop.retirement': {'bytes': 275600,
                                      'identity': [2067, 53871089, 33060, 0, 0, 1, 275600, 1794879464846248331, 1794879464846248331],
                                      'path': '/data/p4-r6-failed-desktop-retirement-e6ac-r1/RESULT.json',
                                      'sha256': '43f1e74b7c580b437559e6a03382030d064da3cf428276a0ba429762f96bac1c'},
               'desktop.root': {'bytes': 6788,
                                'identity': [2067, 57426, 33152, 1000, 1000, 1, 6788, 1794880391279756808, 1794880391293941137],
                                'path': '/data/p4-r6-failed-desktop-retirement-ROOT-actual-acceptance-e6ac-r1.json',
                                'sha256': '773956998587f45d1deb7072b37d633ae2681a142cce2fe2aa2f54ba105c2c4b'},
               'offline.inputs': {'bytes': 35818,
                                  'identity': [66306, 31392808, 33152, 1000, 1000, 1, 35818, 1794882194317610279, 1794882194319772707],
                                  'path': '/home/alex/work/p4-r6-failed-storage-finalize-INPUTS-e6ac-r1.json',
                                  'sha256': '3e417a93ae1040e7b01e51424f9a48b0142750e5edba5103d0067f0c256e0526'},
               'offline.result': {'bytes': 68363,
                                  'identity': [66306, 35803688, 33060, 1000, 1000, 1, 68363, 1794883557384160807, 1794883557384160807],
                                  'path': '/home/alex/work/p4-r6-failed-storage-finalize-e6ac-r1/RESULT.json',
                                  'sha256': '3571d8771eddc39990093d471bdb889b5b238c7be626c7cff43eab71758e32bd'},
               'offline.root': {'bytes': 34031,
                                'identity': [66306, 31392852, 33152, 1000, 1000, 1, 34031, 1794885922230874909, 1794885922233148886],
                                'path': '/home/alex/work/p4-r6-failed-storage-finalize-ROOT-actual-acceptance-e6ac-r1.json',
                                'sha256': '896f745234dc857649f634e157b977f568f6ac52d22e3f4cb4bc6e8d3118b02c'},
               'server.ready': {'bytes': 3942,
                                'identity': [66306, 62550349, 33060, 1000, 1000, 1, 3942, 1794805700746066269, 1794805700746066269],
                                'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-r1/storage-r6/SERVER-READY.json',
                                'sha256': 'a80c6957fa064a0721df94a46ba1e31ff7c458b238f0c5f08566fea4a1fa2e78'},
               'server.result': {'bytes': 21402,
                                 'identity': [66306, 62550479, 33060, 1000, 1000, 1, 21402, 1794881888922913159, 1794881888922913159],
                                 'path': '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-r1/storage-r6/SERVER-RESULT.json',
                                 'sha256': '583d6eb75aff489640e5cf027ee3f9659caf883b15cb4f797834e0f7e620ec24'},
               'server.retirement': {'bytes': 140303,
                                     'identity': [66306, 35803644, 33060, 0, 0, 1, 140303, 1794881889186066208, 1794881889186066208],
                                     'path': '/home/alex/work/p4-r6-failed-server-retirement-e6ac-r1/RESULT.json',
                                     'sha256': 'a903841336098bdcebae0cd2eba6bbd604bf2c13742e009c95b2c6d4b70c0147'},
               'server.root': {'bytes': 6742,
                               'identity': [2067, 57476, 33152, 1000, 1000, 1, 6742, 1794882461477762069, 1794882461478271666],
                               'path': '/data/p4-r6-failed-server-retirement-ROOT-actual-acceptance-e6ac-r1.json',
                               'sha256': '6c6559621dd17253b19480a9ce65f441bf42d97a673be23fdf16cd798c469f1e'}},
 'schema': 'p4-r6-failed-storage-frozen-offline-binding-v1'}
OLD_MANIFEST = 'b9c8805f82f628a8f67fcd17a73193b6141be7ee5a9c04b67ff270b9762b708d'
OLD_ADMISSION = '37d06a61be3bfc74595a57dfb59c9966da919903d0e5793f6b64666030ca57e0'
OLD_NONCE = '07fcf25dedaae64ee1f9fafb4d1ffc052f4f32175544b8d7be05b62abbfdba50'
FINALIZER_SOURCE_SHA = '896d4ef1245424739ef3a834e5d92d4445a76ba83621b1740f29d1459498400a'
FINALIZER_INPUT_SHA = '3e417a93ae1040e7b01e51424f9a48b0142750e5edba5103d0067f0c256e0526'
IMAGE_PATH = '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-r1/production651.raw'
IMAGE_BYTES = 429496729600
IMAGE_INODE = (66306, 48104071)
LOCK_PATH = '/home/alex/work/p4-remote-build-storage-e6ac-r1/production400-r1/owner.lock'
LOCK_IDENTITY = [66306, 48104069, 33152, 1000, 1000, 1, 0,
                 1794666463941136354, 1794666463941136354]
DOCUMENTS = frozenset(('desktop.result', 'desktop.retirement', 'desktop.root',
    'server.ready', 'server.result', 'server.retirement', 'server.root',
    'offline.inputs', 'offline.result', 'offline.root'))
FINAL_ROOT_CHECKS = frozenset((
    "all12_finalizer_commands_exit0_complete24streams",
    "all73_independent_fresh_refs_ROOT_joined",
    "allocation_lock_same_inode_read_only_closed",
    "finalizer_native_success_before_release_saved_whole",
    "independent23checks_alltrue_whole_readback",
    "independent_original_native_release_native_stop_after_H_exact_join",
    "no_selected_delivery_or_export_credited",
    "old15_and_release9_all_known_PID_paths_absent_in_ROOT_sample",
    "one_exact_stop_no_reset_target_signal_image_lock_action",
    "read_only_e2fsck_f_n_all5phases_exit0",
    "release_all6_commands_18bodies_verified",
    "release_original_START_H_exit0_complete",
    "release_original_terminal_whole_and_5_original_bodies_verified",
    "release_source_grant_and_request_exact",
    "source_report_FD_counts_restored",
    "whole400GiB_SHA_and_full9_bookends",
))
FINAL_ROOT_INDEPENDENT_CHECKS = frozenset((
    "24_command_body_occurrences_all_whole_SHA",
    "FD3_to3_all_closed",
    "H_result_native_tokens_join",
    "RESULT_direct_fresh9_equal_original_H",
    "START_H_same_host_sid_boot_PID_created_no_retry",
    "actual_request_whole_frozen",
    "exact_one_stop_no_reset_no_direct_target_signal",
    "fresh_complete_covered_tail_old15_new9_absent",
    "independent_H_complete_exit0_whole",
    "limited_scope_no_new_storage_C_D_or_unknown_claim",
    "native_H_RESULT_exact_and_bookends",
    "old15_source_absences_exact_frozen",
    "original_successful_exited_native_full_state_before_stop",
    "passed_errors_empty_original_budget",
    "six_cmd_records_streams_H_birth_reap_equal",
    "source_observed_exact_cgroup_ENOENT_before_after",
    "target_gone_after_exact_stop",
    "ten_fixed_refs_fresh_whole_SHA_all9",
    "three_original_docs_exact_whole_bytes",
    "three_tools_whole_pins_fixed",
    "two_fixed_cgroups_fresh_actual_ENOENT",
    "two_units_fresh_system_user_notfound",
    "whole_old_stdout6994_stderr0_finalevent_exact",
))
FINAL_ROOT_KEYS = frozenset((
    "ROOT_known_exit",
    "accepted",
    "actual_after",
    "allocation_lock",
    "checks",
    "command_stream_validation",
    "credit",
    "e2fsck",
    "exact_stop",
    "finalizer_independent",
    "finalizer_result",
    "finalizer_result_whole",
    "finalizer_stderr",
    "finalizer_stdout",
    "host",
    "independent_checks",
    "observation_limit",
    "original_failed_storage_preserved",
    "original_native",
    "release_H",
    "release_body_validation",
    "release_independent",
    "release_native",
    "release_original_dispatch",
    "release_original_terminal",
    "release_result",
    "release_source_admission",
    "saved_successful_original_terminal",
    "schema",
    "scope",
    "whole_image",
    "whole_image_bytes_read",
))

OBSERVED_FINAL_ROOT_BYTES = 34031
OBSERVED_FINAL_ROOT_SHA = '896f745234dc857649f634e157b977f568f6ac52d22e3f4cb4bc6e8d3118b02c'
# Original native-int refs from the accepted ORIGINAL-TERMINAL body, not ROOT's
# string-ns observation representation and not a successor production binding.
OBSERVED_TERMINAL_ORIGINALS = {
  "inputs": {
    "bytes": 35818,
    "identity": [
      66306,
      31392808,
      33152,
      1000,
      1000,
      1,
      35818,
      1794882194317610279,
      1794882194319772707
    ],
    "path": "/home/alex/work/p4-r6-failed-storage-finalize-INPUTS-e6ac-r1.json",
    "sha256": "3e417a93ae1040e7b01e51424f9a48b0142750e5edba5103d0067f0c256e0526"
  },
  "result": {
    "bytes": 68363,
    "identity": [
      66306,
      35803688,
      33060,
      1000,
      1000,
      1,
      68363,
      1794883557384160807,
      1794883557384160807
    ],
    "path": "/home/alex/work/p4-r6-failed-storage-finalize-e6ac-r1/RESULT.json",
    "sha256": "3571d8771eddc39990093d471bdb889b5b238c7be626c7cff43eab71758e32bd"
  },
  "source": {
    "bytes": 51638,
    "identity": [
      66306,
      31392799,
      33152,
      1000,
      1000,
      1,
      51638,
      1794881643365407979,
      1794881643369495366
    ],
    "path": "/home/alex/work/p4-r6-failed-storage-finalize-e6ac-r1.py",
    "sha256": "896d4ef1245424739ef3a834e5d92d4445a76ba83621b1740f29d1459498400a"
  }
}

def same(left, right, message):
    require(encoded(left) == encoded(right), message)


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, 'exact finite integer, never bool/float/string')
    return value


def whole_document(row, expected):
    require(type(row) is dict and set(row) == {'original', 'raw'},
            'one original full reference and its complete original bytes')
    ref = full_ref(row['original'])
    same(ref, full_ref(expected), 'exact frozen original full reference')
    raw = row['raw']
    require(type(raw) is bytes and len(raw) == ref['bytes'] <= 4 * 1024**2 and
            hashlib.sha256(raw).hexdigest() == ref['sha256'],
            'complete original bytes, not a native/copy metadata substitution')
    value = json.loads(raw)
    require(type(value) is dict, 'one original JSON object')
    return ref, value


def exact_checks(checks, expected_names):
    require(type(checks) is dict and set(checks) == set(expected_names) and
            all(value is True for value in checks.values()),
            'closed exact set of independent true checks')


def old_cohort(value):
    require(value['source_manifest_sha256'] == OLD_MANIFEST and
            value['admission_sha256'] == OLD_ADMISSION and value['nonce'] == OLD_NONCE,
            'exact original failed r6 cohort, never relabelled as the next epoch')


def zero_exit(command):
    require(type(command) is dict and type(command['exit_code']) is int and
            command['exit_code'] == 0 and command['PIDFD_HUP'] is True and
            command['original_procdir_absent'] is True and command['timed_out'] is False,
            'actual successful command and owned-child retirement')
    integer(command['pid'], 1)
    for name in ('stdout', 'stderr'):
        full_ref(command[name])


def observed_ref_join(observed, original, message):
    """Compare this ROOT receipt's string-ns view; never return a runtime ref."""
    original = full_ref(original)
    require(type(observed) is dict and set(observed) == set(original),
            message + ': exact observation ref shape')
    same({key: observed[key] for key in ('path', 'bytes', 'sha256')},
         {key: original[key] for key in ('path', 'bytes', 'sha256')}, message)
    observed_f9 = observed['identity']
    original_f9 = original['identity']
    require(type(observed_f9) is list and len(observed_f9) == 9 and
            all(type(value) is int for value in observed_f9[:7]),
            message + ': first seven observation fields stay native ints')
    same(observed_f9[:7], original_f9[:7], message)
    for index in (7, 8):
        integer(original_f9[index])
        text = observed_f9[index]
        require(type(text) is str and 1 <= len(text) <= 20 and
                text.isascii() and text.isdecimal() and
                text == str(original_f9[index]),
                message + ': canonical observed ns equals original native int')


def consume_actual_finalizer_root(raw, offline_ref, offline, source_ref, inputs_ref):
    """Validate one actual limited receipt; no new storage permission is issued."""
    require(type(raw) is bytes and len(raw) == OBSERVED_FINAL_ROOT_BYTES and
            hashlib.sha256(raw).hexdigest() == OBSERVED_FINAL_ROOT_SHA,
            'the complete actual ROOT receipt bytes, never a constructed substitute')
    root = json.loads(raw)
    require(type(root) is dict and set(root) == FINAL_ROOT_KEYS and
            root['schema'] == 'p4-r6-failed-storage-finalize-ROOT-actual-acceptance-v1' and
            root['host'] == 'pocket4' and root['accepted'] is True and
            root['original_failed_storage_preserved'] is True,
            'actual limited offline validation and exact terminal release')
    exact_checks(root['checks'], FINAL_ROOT_CHECKS)
    exact_checks(root['independent_checks'], FINAL_ROOT_INDEPENDENT_CHECKS)
    same(root['credit'], {
        'Android_starts': 0, 'CURRENT_written': False, 'C_D_admitted': False,
        'arbitrary_desktop_namespace_FD_lifetimes_proved': False,
        'complete_storage_retirement': False,
        'known_finalizer_terminal_released': True,
        'known_release_actor_and_children_retired': True,
        'new_storage_admitted': False, 'owner_deadline_extended': False,
        'production_ready': False, 'runtime_qualified': False,
        'unknown_progress_reader_retirement': False,
        'whole_image_read_only_finalization_accepted': True},
        'only observed offline/known-exit credit; no complete retirement or future grant')
    require(root['scope'] ==
            'Successful ordinary offline whole-image validation and release of the exact completed finalizer; known-subject exit only.' and
            root['observation_limit'] ==
            'Known PID absence is a bounded non-atomic observation. Successful finalization does not make old failed storage or old classification current.',
            'the original bounded observation scope is not promoted')

    for name, ref in (('result', offline_ref), ('source', source_ref), ('inputs', inputs_ref)):
        same(full_ref(ref), OBSERVED_TERMINAL_ORIGINALS[name],
             'original native-int terminal body ref ' + name)
    require(source_ref['sha256'] == FINALIZER_SOURCE_SHA and
            inputs_ref['sha256'] == FINALIZER_INPUT_SHA,
            'unchanged actual finalizer source and input hashes')
    result_locator = root['finalizer_result']
    require(type(result_locator) is dict and set(result_locator) ==
            {'host', 'path', 'bytes', 'sha256', 'version', 'pages', 'whole_verified'} and
            result_locator['host'] == 'pocket4' and result_locator['whole_verified'] is True and
            type(result_locator['pages']) is int and result_locator['pages'] == 2,
            'actual ROOT result locator, never a full nine-field ref')
    same({key: result_locator[key] for key in ('path', 'bytes', 'sha256')},
         {key: offline_ref[key] for key in ('path', 'bytes', 'sha256')},
         'ROOT locator binds the original whole typed result')
    require(result_locator['version'] ==
            ':'.join(str(offline_ref['identity'][index]) for index in (0, 1, 6, 7, 8)),
            'version compares only its five actual fields; it does not supply full F9')
    same(root['finalizer_result_whole'], result_locator, 'same two-page original whole RESULT')
    same(root['original_native'], offline['native'], 'same finalizer native and complete original state')

    for field in ('allocation_lock', 'e2fsck'):
        original = offline[field]
        observed = root[field]
        ref_keys = ('original',) if field == 'allocation_lock' else ('stdout', 'stderr')
        same({key: value for key, value in observed.items() if key not in ref_keys},
             {key: value for key, value in original.items() if key not in ref_keys},
             'same original finalizer ' + field)
        for key in ref_keys:
            observed_ref_join(observed[key], original[key], field + '.' + key)
    image = offline['whole_image']
    require(type(image) is dict and set(image) ==
            {'path', 'bytes', 'sha256', 'identity', 'allocated_bytes'},
            'original typed whole image shape')
    observed_ref_join({key: root['whole_image'][key] for key in ('path', 'bytes', 'sha256', 'identity')},
                      {key: image[key] for key in ('path', 'bytes', 'sha256', 'identity')},
                      'ROOT observation of original whole image')
    same(root['whole_image']['allocated_bytes'], image['allocated_bytes'],
         'same original whole-image allocation')
    require(integer(root['whole_image_bytes_read']) ==
            integer(offline['whole_image_bytes_read']) == IMAGE_BYTES,
            'the original complete 400GiB read')

    terminal = root['saved_successful_original_terminal']
    require(terminal['Id'] == offline['native']['unit'] and
            terminal['InvocationID'] == offline['native']['InvocationID'] and
            terminal['MainPID'] == '0' and
            terminal['ExecMainPID'] == str(offline['native']['pid']) and
            terminal['ExecMainCode'] == '1' and terminal['ExecMainStatus'] == '0' and
            terminal['LoadState'] == 'loaded' and terminal['ActiveState'] == 'active' and
            terminal['SubState'] == 'exited' and terminal['Result'] == 'success',
            'same successfully exited finalizer before its one exact stop')
    stop = root['exact_stop']
    require(type(stop['exit_code']) is int and stop['exit_code'] == 0 and
            stop['PIDFD_HUP'] is True and stop['original_procdir_absent'] is True and
            stop['timed_out'] is False and stop['argv'] ==
            ['/usr/bin/systemctl', 'stop', offline['native']['unit']],
            'only the actually recorded terminal release, not a live kill or reset')
    after = root['actual_after']
    require(after['Id'] == terminal['Id'] and after['LoadState'] == 'not-found' and
            after['ActiveState'] == 'inactive' and after['SubState'] == 'dead' and
            after['MainPID'] == '0' and after['InvocationID'] == '' and after['ControlGroup'] == '',
            'the exact released unit after the recorded stop')
    require(root['release_H']['complete'] is True and
            type(root['release_H']['exit_code']) is int and root['release_H']['exit_code'] == 0,
            'complete actual release H, not a launch acknowledgement')
    known = root['ROOT_known_exit']
    require(known['all_known_absent'] is True and known['snapshot_atomic'] is False and
            type(known['known_PIDs']) is list and
            all(type(pid) is int and pid > 0 for pid in known['known_PIDs']) and
            len(known['known_PIDs']) == len(set(known['known_PIDs'])) == 24 and
            {offline['native']['pid'], root['release_native']['pid'], stop['pid']} |
            {command['pid'] for command in offline['commands']} <= set(known['known_PIDs']),
            'bounded original known-subject observation, with no unknown-reader assertion')
    # Every remaining observed locator/native/stream field is kept byte-for-byte
    # by the actual ROOT pin above. No observation ref is returned or made typed.
    return None


def qualified_failed_storage(documents):
    frozen = FROZEN_BINDING
    require(type(frozen) is dict and set(frozen) ==
            {'schema', 'originals', 'original_source_pins', 'original_tool_pins',
             'finalizer_source', 'expected_finalizer_native'},
            'future actual offline and independent exit binding is not issued')
    require(frozen['schema'] == 'p4-r6-failed-storage-frozen-offline-binding-v1' and
            type(frozen['originals']) is dict and set(frozen['originals']) == DOCUMENTS and
            type(documents) is dict and set(documents) == DOCUMENTS,
            'only the complete closed failed-epoch proof family')
    refs = {}; values = {}
    for name in sorted(DOCUMENTS):
        refs[name], values[name] = whole_document(documents[name], frozen['originals'][name])
    require(sum(ref['bytes'] for ref in refs.values()) <= 16 * 1024**2,
            'original finite complete-proof total, excluding image/journal payload')

    desktop = values['desktop.result']
    retired_desktop = values['desktop.retirement']
    desktop_root = values['desktop.root']
    server_ready = values['server.ready']
    original_server = values['server.result']
    retired_server = values['server.retirement']
    server_root = values['server.root']
    inputs = values['offline.inputs']
    offline = values['offline.result']
    for value in (desktop, retired_desktop, desktop_root, server_ready,
                  original_server, retired_server, server_root, offline):
        old_cohort(value)

    require(desktop['schema'] == 'p4-production651-nbd-desktop-result-v1' and
            desktop['passed'] is False and
            desktop['original_module_device_mount_state_restored'] is True and
            desktop['selected_delivery']['present'] is False and
            desktop['errors'] == [
                "RuntimeError('actual host 12 GiB RAM, local evidence and original 32 GiB shared volume reserves')"],
            'the complete original desktop reserve failure remains failed')
    require(integer(desktop['minimum_local_free']) == 8568438784 < 8589934592,
            'original recorded reserve minimum, not a current free-space observation')
    require(retired_desktop['schema'] ==
            'p4-r6-failed-desktop-terminal-retirement-v1' and
            retired_desktop['retirement_passed'] is True and
            retired_desktop['functional_result_passed'] is False and
            retired_desktop['original_failure_preserved'] is True and
            retired_desktop['zero_NBD_transport_independently_observed'] is True and
            retired_desktop['complete_storage_retirement'] is False and
            retired_desktop['arbitrary_namespace_FD_retirement_claimed'] is False and
            retired_desktop['unresolved_historical_progress_reader_retirement_claimed'] is False,
            'only the actual limited desktop terminal/device release')
    same(retired_desktop['result'], refs['desktop.result'], 'same original failed desktop report')
    require(desktop_root['schema'] ==
            'p4-r6-failed-desktop-terminal-retirement-ROOT-actual-acceptance-v1' and
            desktop_root['decision'] ==
            'ACCEPT_EXACT_LIMITED_DESKTOP_TERMINAL_RELEASE_AND_ZERO_NBD_OBSERVATION',
            'new limited desktop ROOT schema, not the old complete retirement')
    same(desktop_root['original_result'], refs['desktop.retirement'],
         'desktop ROOT original complete limited report')
    require(desktop_root['scope']['new_desktop_limited_retirement_verified'] is True and
            desktop_root['scope']['all_43_known_new_subjects_retired'] is True and
            all(desktop_root['scope'][key] is False for key in
                ('complete_storage_retirement', 'all_namespace_FD_lifetimes_proved',
                 'unknown_progress_reader_proved_retired', 'server_retired',
                 'new_storage_admission', 'Android_success', 'C_D_success')),
            'historical desktop scope is preserved without adding later server success')

    require(server_ready['schema'] == 'p4-production651-nbd-server-ready-v1' and
            original_server['schema'] == 'p4-production651-nbd-server-result-v1' and
            original_server['server_lifecycle_clean'] is True and original_server['errors'] == [] and
            original_server['stop_requested'] is True,
            'actual original server clean stop, never a still-live READY for reuse')
    same(original_server['ready'], refs['server.ready'], 'original exact server READY')
    same(original_server['native'], server_ready['native'], 'same original server native')
    zero_exit(original_server['server_retirement'])
    require(retired_server['schema'] == 'p4-r6-failed-server-terminal-retirement-v1' and
            retired_server['retirement_passed'] is True and
            retired_server['cgroup_absent'] is True and
            retired_server['original_server_lifecycle_clean'] is True and
            retired_server['original_storage_failure_preserved'] is True and
            retired_server['complete_storage_retirement'] is False and
            retired_server['offline_image_full_SHA_completed'] is False and
            retired_server['unknown_progress_reader_retirement_claimed'] is False,
            'actual first stage retirement without claiming the later offline hash')
    same(retired_server['original_server_result'], refs['server.result'], 'same original server terminal result')
    same(retired_server['original_server_ready'], refs['server.ready'], 'same historical READY')
    same(retired_server['desktop_peer']['retirement_original'], refs['desktop.retirement'],
         'the P4 first stage consumes the exact limited desktop report')
    require(server_root['schema'] == 'p4-r6-failed-server-retirement-ROOT-actual-acceptance-v1' and
            server_root['decision'] ==
            'ACCEPT_EXACT_ORIGINAL_SERVER_QEMU_RETIREMENT_AND_OFFLINE_WRITER_OBSERVATION' and
            server_root['scope']['server_and_qemu_retirement_verified'] is True and
            server_root['scope']['all15_new_known_and2_old_known_subjects_absent'] is True,
            'actual independent ROOT acceptance of the original server and qemu exit')
    same(server_root['original_result'], refs['server.retirement'], 'server ROOT exact original first-stage report')
    same(server_root['original_server_result'], refs['server.result'], 'server ROOT exact old server result')
    require(all(server_root['scope'][key] is False for key in
                ('complete_storage_retirement', 'all_namespace_FD_lifetimes_proved',
                 'unknown_progress_reader_proved_retired', 'new_storage_admitted',
                 'C_D_or_Android', 'whole_image_SHA_completed', 'e2fsck_completed')),
            'first-stage facts are not retroactively promoted by the finalizer')

    require(refs['offline.inputs']['sha256'] == FINALIZER_INPUT_SHA and
            inputs['schema'] == 'p4-r6-failed-storage-finalize-inputs-v1',
            'actual original finalizer INPUTS')
    same(full_ref(inputs['server_retirement']), refs['server.retirement'],
         'typed actual original finalizer server report')
    require(offline['schema'] == 'p4-r6-failed-storage-offline-filesystem-result-v1' and
            offline['passed'] is True and offline['errors'] == [] and offline['signals'] == [] and
            offline['passed_scope'] == 'offline_filesystem_and_selected_persisted_bytes_only' and
            offline['source_tool_inputs_and_image_bookends_equal'] is True and
            offline['original_selected_delivery_present'] is False and
            offline['exported_files'] == [] and offline['full_build_success_not_inferred'] is True and
            type(offline['elapsed_seconds']) in (int, float) and
            math.isfinite(offline['elapsed_seconds']) and 0 <= offline['elapsed_seconds'] < 13200,
            'complete actually successful finite read-only finalizer, never the launch acknowledgement')
    require(all(offline[key] is False for key in
                ('complete_storage_retirement', 'old_full_retirement_schema_used',
                 'old_private_dispatch_diagnostics_read', 'old_private_DISPATCH_HOST_read',
                 'unknown_progress_reader_retirement_claimed',
                 'arbitrary_desktop_namespace_FD_lifetimes_proved', 'new_storage_admitted',
                 'CURRENT_written_or_owner_deadline_changed',
                 'allocation_lock_replaced_or_truncated', 'C_D_admitted', 'production_ready')) and
            type(offline['Android_starts']) is int and offline['Android_starts'] == 0,
            'original unknowns/failures and future authority remain explicitly separate')
    same(offline['desktop_retirement'], refs['desktop.retirement'], 'same actual desktop input')
    same(offline['server_retirement'], refs['server.retirement'], 'same actual P4 server input')
    same(offline['original_server_result'], refs['server.result'], 'same clean original server body')
    same(offline['fd_before'], offline['fd_after'], 'all ordinary finalizer descriptors released')
    same(offline['native'], frozen['expected_finalizer_native'], 'same independently captured finalizer invocation')
    for key in ('unit', 'InvocationID', 'pid', 'start_ticks', 'cgroup', 'boot', 'limits'):
        same(offline['native_after'][key], offline['native'][key], 'same finalizer native bookend ' + key)
    same(offline['source_refs'], frozen['original_source_pins'], 'all original storage source full references')
    same(offline['tool_refs'], frozen['original_tool_pins'], 'all original tool full references')
    require(len(offline['source_refs']) == 27 and len(offline['tool_refs']) == 8,
            'exact original source/tool inventory')
    lock = offline['allocation_lock']
    full_ref(lock['original'])
    same(lock['original']['identity'], LOCK_IDENTITY, 'unchanged original allocation lock full F9')
    require(lock['original']['path'] == LOCK_PATH and
            all(lock[key] is True for key in ('held_exclusive_nonblocking',
                'read_only_descriptor', 'same_original_inode', 'closed_after_checks')) and
            lock['replaced'] is lock['truncated'] is False,
            'held original lock stayed unchanged and was released after all checks')
    image = offline['whole_image']
    require(type(image) is dict and set(image) == {'path', 'bytes', 'sha256', 'identity', 'allocated_bytes'},
            'exact complete newly measured offline image object')
    image_ref = full_ref({key: image[key] for key in ('path', 'bytes', 'sha256', 'identity')})
    require(image_ref['path'] == IMAGE_PATH and image_ref['bytes'] == IMAGE_BYTES and
            tuple(image_ref['identity'][:2]) == IMAGE_INODE and
            image_ref['identity'][3:6] == [1000, 1000, 1] and
            integer(image['allocated_bytes']) >= IMAGE_BYTES and
            integer(offline['whole_image_bytes_read']) == IMAGE_BYTES,
            'one exact original fully allocated 400GiB inode with a new whole hash')
    same({key: image[key] for key in ('path', 'identity', 'allocated_bytes')},
         retired_server['offline_original_image']['image'],
         'the finalizer hashed the same image F9 the retired server left')
    zero_exit(offline['e2fsck'])
    require(offline['e2fsck']['argv'] == ['/usr/sbin/e2fsck', '-f', '-n', IMAGE_PATH],
            'exact original read-only fsck, without repair or reformat')
    require(type(offline['commands']) is list and 1 <= len(offline['commands']) <= 128,
            'finite actual command inventory')
    for command in offline['commands']:
        zero_exit(command)

    consume_actual_finalizer_root(documents['offline.root']['raw'],
        refs['offline.result'], offline, full_ref(frozen['finalizer_source']), refs['offline.inputs'])
    return {'schema': 'p4-failed-epoch-offline-qualified-input-v1',
        'phase_refs': refs, 'whole_image': image, 'allocation_lock': lock['original'],
        'original_failed_epoch': {'source_manifest_sha256': OLD_MANIFEST,
            'admission_sha256': OLD_ADMISSION, 'nonce': OLD_NONCE},
        'offline_readonly_qualification_passed': True, 'known_finalizer_lifecycles_retired': True,
        'complete_old_storage_retirement': False, 'unknown_progress_reader_retired': False,
        'fresh_full_image_F9_and_no_writer_census_required': True,
        'fresh_allocation_lock_EXNB_required': True, 'fresh_current_owner_and_reserve_checks_required': True,
        'new_mount_and_full_B_second_F9_required': True,
        'old_READY_reusable': False, 'old_plan_or_SQLite_resume_accepted': False,
        'new_storage_admitted': False, 'current_namespace_qualified': False,
        'C_D_admitted': False, 'Android_passed': False, 'production_ready': False}
