"""Source fragments for the reviewed photo-to-video display adaptation.

The generator embeds these functions in the complete wrapper. This file is not
a runtime entry and performs no actions on import.
"""


def configure_video_preparation(path, expected):
    global PREPARATION_REF, VIDEO_CONTEXT
    require(PREPARATION_REF is None and re.fullmatch('[0-9a-f]{64}', expected or ''),
            'one externally reviewed video preparation required')
    fd, raw, observed = held_file(path, 131072, expected)
    try:
        packet = json.loads(raw)
    finally:
        os.close(fd)
    require(packet.get('schema') == 'pocket4-current-camera-video-preparation-v1'
            and packet.get('source_inventory_sha256') == VIDEO_INVENTORY_SHA256,
            'exact reviewed current video preparation required')
    refs = [row for row in packet['files'] if Path(row['path']).name == 'camera_entry.py']
    require(len(refs) == 1 and (refs[0]['bytes'], refs[0]['sha256']) == VIDEO_ENTRY_PIN,
            'exact current video entry required')
    fd, raw, _ = held_file(refs[0]['path'], 262144, refs[0]['sha256'])
    try:
        entry = types.ModuleType('outer_display_verified_video_entry')
        entry.__file__ = refs[0]['path']
        exec(compile(raw, entry.__file__, 'exec'), entry.__dict__)
    finally:
        os.close(fd)
    common, packet, preparation, planner = entry.bootstrap(argparse.Namespace(
        preparation=str(path), expect_preparation_sha256=expected))
    witness = common.EvidenceWitness([preparation])
    try:
        witness.verify()
    finally:
        witness.close()
    PREPARATION_REF = preparation
    VIDEO_CONTEXT = (common, packet, planner)
    SOURCES['camera'] = (Path(refs[0]['path']), refs[0]['sha256'], 262144)
    SOURCES['preparation'] = (Path(path), expected, 131072)
    for row in packet['files']:
        SOURCES['component_' + Path(row['path']).stem] = (Path(row['path']), row['sha256'], 262144)
    return packet


def supervisor_init(self, raw, output, sources=None):
    require(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0,
            'root camera video wrapper context required')
    require(VIDEO_CONTEXT is not None, 'reviewed current video preparation not configured')
    self.common, self.packet, self.planner = VIDEO_CONTEXT
    self.raw, self.out, self.spec = raw, output, self.common.parse(raw)
    require(len(raw) <= 131072 and type(self.spec) is dict
            and set(self.spec) == {'schema', 'plan', 'source_preparation', 'automatic_retry', 'whole_app_business_accepted'}
            and self.spec['schema'] == 'pocket4-camera-video-display-input-v1'
            and self.spec['source_preparation'] == PREPARATION_REF
            and self.spec['automatic_retry'] is False and self.spec['whole_app_business_accepted'] is False,
            'exact current video display request required')
    self.plan_ref = self.spec['plan']
    require(type(self.plan_ref) is dict and set(self.plan_ref) == {'path', 'bytes', 'sha256'}
            and type(self.plan_ref['bytes']) is int and 0 < self.plan_ref['bytes'] <= 131072
            and re.fullmatch('[0-9a-f]{64}', self.plan_ref['sha256']), 'exact reviewed video plan reference required')
    plan_path = Path(self.plan_ref['path'])
    self.case_root = plan_path.parent
    require(plan_path.is_absolute() and plan_path.resolve() == plan_path and plan_path.name == 'plan.json'
            and self.case_root.parent == QUALIFICATION
            and re.fullmatch('business-camera-video-plan-[0-9a-f]{32}', self.case_root.name),
            'only a newly factory-created video plan can enter the display lease')
    self.plan = self.common.parse(self.common.read_ref(self.plan_ref))
    require(self.plan.get('schema') == 'pocket4-current-camera-video-plan-v1'
            and self.plan.get('kind') == 'camera_video' and self.plan.get('case_root') == str(self.case_root)
            and self.plan.get('source_preparation') == PREPARATION_REF
            and self.plan.get('automatic_retry') is False and self.plan.get('whole_app_business_accepted') is False,
            'the request is not this frozen video plan')
    profiles = self.planner.named(self.common, self.packet, 'camera_profiles.py')
    require(self.plan['limits'] == profiles.LIMITS and profiles.LIMITS['business_seconds'] == 420
            and profiles.LIMITS['cleanup_seconds'] == 60 and profiles.LIMITS['supervisor_seconds'] == CAMERA_SECONDS,
            'exact existing video worker and acoustic owner budgets required')
    self.planner.source_packet(self.common, self.plan, self.packet)
    require(not any((self.case_root / name).exists() for name in
                    ('execute-once.json', 'result.json', 'evidence', 'acoustic-supervisor')),
            'video execution already begun; no implicit retry')
    self.spec['transaction_id'] = 'video-' + self.case_root.name.rsplit('-', 1)[1]
    self.sources = {**(SOURCES if sources is None else sources),
                    'plan': (plan_path, self.plan_ref['sha256'], 131072)}
    self.fds, self.logs, self.actors = [], [], {}
    self.channel = self.reaper = self.ready = self.release = self.last_heartbeat = None
    self.sequence = 0
    self.retiring = self.committed = False
    self.after_commit_signals = []
    self.error = self.inner_result = None
    self.record = {'schema': 'pocket4-camera-video-display-supervision-v1',
        'started_monotonic_ns': time.monotonic_ns(), 'errors': [], 'signals': [],
        'sources': {}, 'events': [], 'ready_revoked': False, 'automatic_retry': False,
        'Main_lifecycle_actions': 0, 'USB_actions': 0, 'global_power_setting_changes': 0,
        'public_lifecycle_changed': False,
        'principal_structure': 'root owns alex display holder and root acoustic supervisor siblings'}
    self.started = time.monotonic()
    self.operation_deadline = self.started + READY_SECONDS + CAMERA_SECONDS
    self.deadline = self.started + WRAPPER_SECONDS
    self.record['budgets'] = {'wrapper_seconds': WRAPPER_SECONDS, 'ready_seconds': READY_SECONDS,
        'video_worker_business_seconds': 420, 'video_worker_cleanup_seconds': 60,
        'acoustic_supervisor_with_retirement_seconds': CAMERA_SECONDS,
        'acoustic_cancellation_grace_seconds': CAMERA_GRACE_SECONDS,
        'operation_deadline': self.operation_deadline, 'absolute_deadline': self.deadline}


def launch_camera(self):
    require(time.monotonic() <= self.started + READY_SECONDS, 'video started after its full budget reserve')
    require(not self.retiring and not self.record['signals'], 'no video child after cancellation')
    require(not any((self.case_root / name).exists() for name in
                    ('execute-once.json', 'result.json', 'evidence', 'acoustic-supervisor')),
            'video plan has already begun; never repeat or adopt a prior result')
    self.planner.source_packet(self.common, self.plan, self.packet)
    request = self.common.write_new(self.out / 'camera-execution-request.json', {'base_plan': self.plan_ref}, 0o400)
    self.record['video_execution_request'] = request
    script = self.source_fds['camera']
    argv = ['/usr/bin/python3', '-I', '-B', '/proc/self/fd/%d' % script,
        '--preparation', PREPARATION_REF['path'], '--expect-preparation-sha256', PREPARATION_REF['sha256'],
        'execute', '--request', request['path'], '--expect-request-sha256', request['sha256']]
    item = self.actor('camera', argv, (script,))
    pid = item['process'].pid
    raw = Path('/proc/%d/stat' % pid).read_text()
    fields = raw[raw.rfind(')') + 2:].split()
    require(int(raw.split(' ', 1)[0]) == pid and int(fields[1]) == os.getpid(),
            'acoustic supervisor is not this exact direct child')
    self.record['camera_operator'] = {'pid': pid, 'parent': int(fields[1]), 'start_ticks': int(fields[19])}
    self.record['camera_argv'] = argv
    return item


def validate_video_terminals(plan_ref, plan, preparation, direct_operator, ready_device,
                             parent, parent_ref, supervisor, worker, worker_ref, claim):
    """Strict consumer of unchanged actual producer schemas; no I/O or authority."""
    require(parent.get('schema') == 'pocket4-current-camera-acoustic-parent-v1'
            and parent.get('plan') == plan_ref and parent.get('preparation') == preparation
            and parent.get('case_root') == plan['case_root'] and parent.get('limits') == plan['limits']
            and parent.get('nonce') == plan['audio_nonce'] and parent.get('automatic_retry') is False,
            'actual acoustic parent has another plan/preparation/nonce')
    owner = parent.get('parent', {})
    require(all(owner.get(k) == v for k, v in direct_operator.items()) and owner.get('uids') == [0, 0, 0, 0],
            'acoustic receipt is not from the exact owned root child')
    require(supervisor.get('schema') == 'pocket4-current-camera-acoustic-supervisor-result-v1'
            and supervisor.get('plan') == plan_ref and supervisor.get('preparation') == preparation
            and supervisor.get('kind') == 'camera_video' and supervisor.get('nonce') == plan['audio_nonce']
            and supervisor.get('limits') == plan['limits'] and supervisor.get('inner_result') == worker_ref
            and supervisor.get('state') == 'CURRENT_CAMERA_VIDEO_SCOPE_VERIFIED_CLEAN'
            and supervisor.get('case_business_success_verified') is True
            and supervisor.get('worker_result_verified') is True and supervisor.get('outcome_unknown') is False
            and supervisor.get('whole_app_business_accepted') is False
            and supervisor.get('automatic_retry') is False and supervisor.get('automatic_rollback') is False
            and supervisor.get('error') is None and supervisor.get('errors') == []
            and supervisor.get('received_signals') == [] and supervisor.get('Main_signals') == 0
            and supervisor.get('Android_UI_actions_by_supervisor') == 0,
            'acoustic supervisor did not return its exact successful terminal')
    commit = supervisor.get('cancellation_commit', {})
    require(commit.get('pending_at_commit') == [] and commit.get('decision_after_all_context_close') is True,
            'acoustic owner cancellation commit incomplete')
    reaper = supervisor.get('subreaper', {})
    require(all(reaper.get(k) is True for k in ('begin_passed', 'restored', 'final_children_empty'))
            and supervisor.get('adopted_retirement', {}).get('owned_tree_cleanup_complete') is True
            and supervisor['adopted_retirement'].get('descendants') == []
            and all(supervisor.get(k) is True for k in
                    ('control_fd_closed', 'selector_closed', 'audio_artifact_descriptors_closed', 'held_Main_closed')),
            'acoustic owner retained a child, descriptor or Main context')
    actors = supervisor.get('actors', {})
    require(set(actors) == {'business', 'emit', 'listen'} and
            len({row.get('pid') for row in actors.values()}) == 3 and
            all(type(row.get('pid')) is int and row['pid'] > 1 for row in actors.values()),
            'three distinct actual video principals required')
    for role, actor in actors.items():
        require(actor.get('uid') == (0 if role == 'business' else 1000)
                and all(actor.get(k) is True for k in ('child_started', 'child_reaped', 'pidfd_closed'))
                and actor.get('pipe_eof') == {'stdout': True, 'stderr': True}
                and actor.get('returncode') == 0,
                'video principal retirement or complete output missing:' + role)
    business = supervisor.get('business_process', {})
    require(business.get('pid') == actors['business']['pid'] and business.get('parent') == direct_operator['pid']
            and business.get('uids') == [0, 0, 0, 0] and type(business.get('start_ticks')) is int
            and business['start_ticks'] > 0 and claim.get('plan') == plan_ref
            and claim.get('operator') == business and claim.get('automatic_retry') is False,
            'execute-once claim must name the actual acoustic-owned business worker')
    require(worker.get('schema') == 'pocket4-current-camera-video-case-result-v1'
            and worker.get('plan') == plan_ref and worker.get('source_preparation') == preparation
            and worker.get('kind') == 'camera_video'
            and worker.get('state') == 'CURRENT_CAMERA_VIDEO_SCOPE_VERIFIED_CLEAN'
            and worker.get('case_business_success_verified') is True and worker.get('outcome_unknown') is False
            and worker.get('secondary_errors') == [] and worker.get('error') is None
            and all(worker.get(k) is False for k in ('runtime_qualified', 'whole_app_business_accepted',
                                                   'camera_recovery_qualified', 'automatic_retry')),
            'actual worker did not return its narrow current video successful contract')
    require(all(worker.get(k) is True for k in ('owned_task_cleanup_verified', 'current_Main_APIs_closed',
            'whole_case_OFD_closed', 'evidence_witness_closed', 'acoustic_channel_closed',
            'owned_decoder_descriptor_closed', 'final_source_and_identity_chain_unchanged'))
            and all(k in worker and worker[k] is None for k in ('acoustic_pending', 'pending_business_action',
            'pending_owned_task_remove', 'owned_task_remaining', 'recording_pending')),
            'video worker has incomplete contexts or an unresolved action')
    commit = worker.get('cancellation_commit', {})
    require(commit.get('received_signals') == commit.get('pending_at_commit') == []
            and commit.get('decision_after_all_context_close') is True, 'video worker cancelled before commit')
    launches = worker.get('native_launches')
    require(type(launches) is list and len(launches) == len(set(launches)) == 3
            and launches == worker.get('exact_normal_closes') == worker.get('native_tasks') == worker.get('normal_closes'),
            'three actual distinct launches and exact normal closes required')
    recording = worker.get('recording', {})
    require(recording.get('state') == 'CAMERA_VIDEO_RECORD_AUDIO_PLAYBACK_VERIFIED'
            and recording.get('camera_video_verified') is True and recording.get('outcome_unknown') is False
            and recording.get('pending') is None and recording.get('nonce') == plan['audio_nonce']
            and recording.get('epoch_sha256') == plan['framework_epoch_sha256']
            and recording.get('original_mode') == recording.get('final_mode')
            and all(recording.get(k) is True for k in ('owned_task_closed', 'preserved_state', 'host_retired')),
            'recording/playback/state restoration terminal incomplete')
    acoustic = supervisor.get('acoustic_results', {})
    require(set(acoustic) == {'emit', 'listen'} and worker.get('acoustic_results') == acoustic,
            'actual worker and supervisor disagree on acoustic evidence')
    for role, row in acoustic.items():
        require(row.get('role') == role and row.get('parent') == parent_ref and row.get('exit_code') == 0
                and row.get('leader_reaped') is True and row.get('pipe_eof') == {'stdout': True, 'stderr': True}
                and row.get('automatic_retry') is False and all(row.get(k, {}).get('nonce') == plan['audio_nonce']
                                                             for k in ('ready', 'started', 'closed')),
                'actual finite acoustic receipt mismatch:' + role)
    require(worker.get('physical_device') == ready_device and ready_device is not None,
            'video and display lease bind different physical devices')
    return True


def validate_camera_result(self):
    def read_document(path, bound=2 * 1024 * 1024):
        fd, raw, observed = held_file(path, bound)
        self.fds.append(fd)
        ref = {key: observed[key] for key in ('path', 'bytes', 'sha256')}
        return self.common.parse(raw), ref
    root = self.case_root
    worker, worker_ref = read_document(root / 'result.json')
    supervisor, supervisor_ref = read_document(root / 'acoustic-supervisor/result.json')
    parent, parent_ref = read_document(root / 'acoustic-supervisor/parent.json', 131072)
    claim, claim_ref = read_document(root / 'execute-once.json', 131072)
    validate_video_terminals(self.plan_ref, self.plan, PREPARATION_REF, self.record['camera_operator'],
                             self.ready['physical_device'], parent, parent_ref,
                             supervisor, worker, worker_ref, claim)
    runtime = self.planner.named(self.common, self.packet, 'app_runtime.py')
    require(parent['boot_id'] == runtime.boot(), 'acoustic receipt boot differs')
    for name in ('full_decode', 'current_audio', 'current_playback'):
        self.common.read_ref(worker[name])
    self.planner.source_packet(self.common, self.plan, self.packet)
    self.record.update(camera_result=worker_ref, acoustic_supervisor_result=supervisor_ref,
                       acoustic_parent=parent_ref, execute_once_claim=claim_ref)
    self.inner_result = worker
    return worker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation', required=True, type=Path)
    parser.add_argument('--expect-preparation-sha256', required=True)
    parser.add_argument('mode', choices=('inspect-source', 'execute'), nargs='?', default='inspect-source')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--expect-input-sha256')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    packet = configure_video_preparation(args.preparation, args.expect_preparation_sha256)
    if args.mode == 'inspect-source':
        require(args.input is None and args.output is None and args.expect_input_sha256 is None,
                'video wrapper inspection has no live input')
        refs = []
        for role, (path, digest, bound) in SOURCES.items():
            fd, _, ref = held_file(path, bound, digest)
            try:
                refs.append({'role': role, **ref})
            finally:
                os.close(fd)
        print(json.dumps({'schema': 'pocket4-camera-video-display-source-inspection-v1',
            'sources': refs, 'video_source_files': len(packet['files']), 'wrapper_seconds': WRAPPER_SECONDS,
            'acoustic_supervisor_seconds': CAMERA_SECONDS, 'cleanup_grace_seconds': CAMERA_GRACE_SECONDS,
            'Main_actions': 0, 'DBus_actions': 0, 'Android_UI_actions': 0,
            'runtime_qualified': False, 'whole_app_business_accepted': False}, sort_keys=True))
        return 0
    require(args.input is not None and args.output is not None
            and re.fullmatch('[0-9a-f]{64}', args.expect_input_sha256 or ''),
            'explicit reviewed video wrapper input and pin required')
    output = args.output.absolute()
    require(output == output.resolve() and output.parent == QUALIFICATION
            and re.fullmatch('camera-video-display-[0-9a-f]{32}', output.name),
            'fresh private video display output required')
    fd, raw, reference = held_file(args.input, 131072, args.expect_input_sha256)
    try:
        runner = Supervisor(raw, output)
        output.mkdir(mode=0o700)
        with (output / 'input.json').open('xb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        runner.record['reviewed_input'] = reference
        code = runner.run()
        print(json.dumps({'result': str(output / 'result.json'), 'success': code == 0,
                          'camera_video_and_display_verified': code == 0,
                          'whole_app_business_accepted': False, 'outcome_unknown': code == 4, 'exit_code': code}), flush=True)
        return code
    finally:
        os.close(fd)
