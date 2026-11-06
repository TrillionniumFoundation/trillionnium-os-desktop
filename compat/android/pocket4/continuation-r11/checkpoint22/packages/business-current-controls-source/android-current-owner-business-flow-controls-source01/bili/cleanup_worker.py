def cleanup_worker(expected):
    """Own cleanup entry; original R6 cleanup and completion semantics remain."""
    verify_source(expected)
    require(os.getuid()==os.geteuid()==0 and HERE==SOURCE,'EXACT_ROOT_CLEANUP_REQUIRED')
    prior=load_prior()
    recorder=prior.recorder_module()
    manifest=prior.verify_source(INSTALL_MANIFEST_SHA)
    Flow=prior.current_flow_type(manifest,recorder)
    now=recorder.now
    write_new=recorder.write_new
    args=types.SimpleNamespace(operation='cleanup',adapter_manifest_sha256=R6_MANIFEST,
        flow_dir=FLOW,step='cleanup-01',
        epoch_module=prior.RECORDER_ROOT/'references/framework_epoch.py',
        task_source=prior.RECORDER_ROOT/'references/task_scope_baseline.py',
        request=None,unknown_step=None,observation_step=None,postcondition=None)
    os.umask(0o077)
    flow=Flow(args)
    mutation=True
    result = {'ok': False, 'automatic_retry': False, 'action_attempted': False, 'outcome_unknown': False,
              'business_success_verified': False}
    try:
        flow.begin(args, mutation)
        result.update(flow.cleanup())
        flow.guard(attempted=flow.action_attempted)
        result['ok'] = True
    except BaseException as exc:
        result.update(error_type=type(exc).__name__, error=str(exc), outcome_unknown=flow.action_attempted)
        if hasattr(exc, 'command_observation'):
            result['command_observation'] = exc.command_observation
        if hasattr(exc, 'details'):
            result['transport_failure'] = exc.details
    finally:
        try:
            flow.close()
        except BaseException as exc:
            result['ok'] = False
            result['outcome_unknown'] = flow.action_attempted
            if 'error' not in result:
                result.update(error_type=type(exc).__name__, error='HELD_BINDING_RELEASE_FAILED')
            result['release_error_type'] = type(exc).__name__
    result.update(action_attempted=flow.action_attempted, ended_utc=now(), epoch_sha256=flow.scope['epoch_sha256'])
    if flow.step is not None:
        write_new(flow.step / 'result.json', result)
    print(json.dumps(result, ensure_ascii=False))
    if not result['ok']:
        return 2
    return 0
