"""Production651 vendor jobs2 observer; historical jobs6 remains provenance.

Current observation takes the approved plan, its exact12G/Go5G profile and the
owned normal driver's actual argv. There is no generic jobs parameter or fallback.
"""
import importlib.util,json,os
from pathlib import Path
_spec=importlib.util.spec_from_file_location('legacy_fixed_jobs6_production_observer',Path(__file__).with_name('production_user_observation_legacy_j6.py'))
legacy=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(legacy)
need=legacy.need;validate_variables=legacy.validate_variables;validate_ui_environment=legacy.validate_ui_environment
# Explicit compatibility entry points for immutable jobs6 history controls only.
expected_ui_argv=legacy.expected_ui_argv;expected_build_argv=legacy.expected_build_argv
ROOT=Path('/data/p4-production651-nbd-e6ac-r1/mount/source-production651');SOURCE=ROOT/'work/aosp-source'
OUT=Path('/data/p4-production651-nbd-e6ac-r1/mount/build-production651/out-production651-user-vendor-e6ac-r2')
UPDATE=ROOT/'tools-production-latest-r1/bin/droidloom-update'
NORMAL_ARGV=[str(UPDATE),'--source',str(ROOT/'tools-production-latest-r1/recipe'),'--jobs','2','vendor-image-build','--work',str(ROOT/'work'),'--out',str(OUT)]
PLAN_SHA='f6d0437be4ea9e2f2022de46006e370e92a6b39a5255917e7af27299f3af68b3'
UPDATE_REF={'path':str(UPDATE),'bytes':7578944,'sha256':'11ac8a474009aacc2c407c02b5b59a6344b2d6ca0bd0e4702634d01d3f83dac6'}

def current_expected_ui_argv(out):
    need(str(out)==str(OUT),'current jobs2 observer belongs to this exact output generation')
    return [str(OUT/'soong_ui'),'--make-mode','-j2','vendorimage','secilc']

def validate_current_binding(process, *, source, out, profile, normal_argv, normal_driver, normal_lifecycle, resource_plan):
    need(str(source)==str(SOURCE)and str(out)==str(OUT),'current production source/output generation differs')
    need(type(normal_argv)is list and normal_argv==NORMAL_ARGV,'current fixed normal jobs2 argv differs')
    need(type(profile)is dict,'current exact profile required')
    values={'build_memory_max_bytes':12884901888,'build_memory_high_bytes':10737418240,
            'memory_swap_max_bytes':0,'cpu_quota_percent':200,'normal_requested_jobs':2,
            'go_memory_limit_bytes':5368709120,'go_max_procs':2,'go_gc_percent':50,
            'fresh_memavailable_minimum_bytes':25769803776,'fresh_disk_minimum_bytes':266287972352}
    need(all(type(profile.get(k))is int and profile[k]==v for k,v in values.items())
         and type(profile.get('cpu_affinity'))is list and profile['cpu_affinity']==[8,9]
         and all(type(v)is int for v in profile['cpu_affinity']), 'current12G/Go5G2/jobs2 profile differs')
    need(type(resource_plan)is dict and resource_plan.get('bytes')==3481
         and type(resource_plan.get('bytes'))is int and resource_plan.get('sha256')==PLAN_SHA,
         'current independent approved resource-plan pin differs')
    need(type(normal_driver)is dict and type(normal_driver.get('pid'))is int and normal_driver['pid']>1
         and type(normal_driver.get('start_ticks'))is int and normal_driver['start_ticks']>0
         and normal_driver.get('argv')==NORMAL_ARGV and normal_driver.get('exe')==str(UPDATE)
         and type(normal_lifecycle)is dict and normal_lifecycle.get('pidfd_closed')is False,
         'actual current normal driver/PIDFD binding differs')
    need(type(process)is dict and process.get('cgroup')==normal_driver.get('cgroup')
         and normal_driver['cgroup']=='0::/system.slice/p4-production651-vendor-inner-desktop-e6ac-r3.service\n',
         'current Soong and owned normal driver must share the exact new cgroup')
    environment=process.get('environment');need(type(environment)is dict,'actual current Go environment required')
    need(all(environment.get(k)==v for k,v in {'GOMEMLIMIT':'5GiB','GOMAXPROCS':'2','GOGC':'50','GODEBUG':'gctrace=1'}.items()),
         'actual current Soong Go5GiB/2/GOGC50 environment differs')
    role=Path(process.get('exe','')).name
    need(role in('soong_ui','soong_build'),'only current owned dual Soong roles are observed')
    expected=current_expected_ui_argv(out)if role=='soong_ui'else expected_build_argv(source,out)
    need(process.get('argv')==expected and process.get('exe')==expected[0],
         'actual current Soong argv must be the exact fixed jobs2 invocation')
    return {'normal_argv':list(NORMAL_ARGV),'resource_profile':dict(profile),'resource_plan':dict(resource_plan),
            'normal_driver':dict(normal_driver),'normal_PIDFD_retained':True,'requested_jobs':2,
            'Go_memory_limit_bytes':5368709120,'Go_max_procs':2,'Go_GOGC':50,'process_role':role}


def _pinned_current_binding(process, *, source, out, profile, normal_argv, normal_driver, normal_lifecycle, resource_plan, support, witness):
    s=support;need(profile==s.PROFILE,'actual current observer must use the loaded frozen profile')
    result=validate_current_binding(process,source=source,out=out,profile=profile,normal_argv=normal_argv,
        normal_driver=normal_driver,normal_lifecycle=normal_lifecycle,resource_plan=resource_plan)
    s.pinned(resource_plan);s.pinned(UPDATE_REF)
    now=s.process_identity(normal_driver['pid']);witness.validate_executed_command(normal_driver,now,NORMAL_ARGV,str(UPDATE))
    with witness.PinnedExecutable(UPDATE_REF)as held:held.verify_running(now['pid'])
    return result

def _observe_current(process, *, source, out, expected_cgroup, result_directory, support, witness, binding):
    """Take two execution boundaries around one full environment/input capture."""
    s = support
    need(type(process) is dict and type(process.get('pid')) is int and process['pid'] > 0,
         'actual positive owned process PID required')
    before = s.process_identity(process['pid'])
    need(witness.generation(before) == witness.generation(process)
         and before['cgroup'] == expected_cgroup, 'production observer left the owned generation')
    name = Path(before['exe']).name
    need(name in ('soong_ui', 'soong_build'), 'not a selected normal Soong process')
    expected = current_expected_ui_argv(out) if name == 'soong_ui' else expected_build_argv(source, out)
    need(before['argv'] == expected and before['exe'] == expected[0],
         'actual production Soong command differs from the fixed normal invocation')
    executable = s.file_ref(expected[0], 256 * 1024**2)
    records = {'schema': 'native-actual-production-user-input-observation-v1',
               'process_role': name, 'before': before, 'expected_argv': expected,
               'explicit_current_jobs2_binding': binding,
               'host_authority_inherited': False, 'artifact_qualified': False,
               'runtime_qualified': False}
    with witness.PinnedExecutable(executable, maximum=256 * 1024**2) as held:
        held.verify_running(before['pid'])
        witness.validate_executed_command(process, s.process_identity(before['pid']),
                                         expected, executable['path'])
        if name == 'soong_ui':
            raw = (Path('/proc') / str(before['pid']) / 'environ').read_bytes()
            need(len(raw) <= 2 * 1024**2, 'process environment exceeds observation bound')
            env = {}
            for item in raw.split(b'\0'):
                if not item:
                    continue
                key, sep, value = item.partition(b'=')
                need(sep == b'=' and key not in env, 'invalid or duplicate process environment key')
                env[key] = value
            selected = {k: env.get(k.encode(), b'').decode('utf-8') for k in
                        ('TARGET_BUILD_VARIANT', 'TARGET_RELEASE', 'TARGET_PRODUCT', 'ALLOW_MISSING_DEPENDENCIES', 'SELINUX_IGNORE_NEVERALLOWS')}
            records['actual_environment'] = validate_ui_environment(selected)
            need(selected['SELINUX_IGNORE_NEVERALLOWS'] == 'false', 'actual user UI must retain neverallow checks')
            records['actual_environment']['SELINUX_IGNORE_NEVERALLOWS'] = 'false'
        else:
            variable_path = Path(out) / 'soong/soong.droidloom_x86_64.variables'
            variable_ref = s.file_ref(variable_path, 2 * 1024**2)
            ref, raw = s.pinned(variable_ref, 2 * 1024**2, contents=True)
            records['actual_variables'] = validate_variables(raw)
            records['original_variables'] = ref
            records['snapshot_variables'] = s.create(Path(result_directory) /
                ('production-variables-%d-%d.json' % (before['pid'], before['start_ticks'])), raw)
            need(all(records['snapshot_variables'][k] == ref[k] for k in ('bytes', 'sha256')),
                 'complete actual Soong variable snapshot differs')
            s.pinned(ref)
        after = s.process_identity(before['pid'])
        witness.validate_executed_command(process, after, expected, executable['path'])
        held.verify_running(before['pid'])
        records['after'] = after
        records['executable_observation'] = held.record()
    return s.create(Path(result_directory) / ('production-%s-%d-%d.json' %
                    (name, before['pid'], before['start_ticks'])), records)


def observe(process, *, source, out, expected_cgroup, result_directory, support, witness,
            profile, normal_argv, normal_driver, normal_lifecycle, resource_plan):
    context=dict(source=source,out=out,profile=profile,normal_argv=normal_argv,normal_driver=normal_driver,
        normal_lifecycle=normal_lifecycle,resource_plan=resource_plan,support=support,witness=witness)
    before=_pinned_current_binding(process,**context)
    result=_observe_current(process,source=source,out=out,expected_cgroup=expected_cgroup,
        result_directory=result_directory,support=support,witness=witness,binding=before)
    after=_pinned_current_binding(process,**context)
    need(before==after,'actual current driver/profile/plan changed during production observation')
    return result
