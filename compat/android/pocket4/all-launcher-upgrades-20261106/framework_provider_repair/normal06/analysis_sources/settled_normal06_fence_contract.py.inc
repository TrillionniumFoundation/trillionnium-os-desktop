def settled_normal06_fence_contract():
    # Build06 stopped before any snapshot/control fork or inner build. Its
    # failed authority remains a failure, with both outer root children reaped.
    authorities = [
        ('terminal.json', 'settled-normal06-fence-terminal.json', 8115,
         '867855adf975072432aada65f4decded4b88c725a6a5d2e9a17909ae1f94b841'),
        ('control-root-timeout.root-supervisor.stdout.json', 'settled-normal06-control-root-stdout.json', 904,
         'e78dc93dcb57b4bcd5390d5ff41f82dce63e25be88c311a564969a5396273b5a'),
        ('after.root-supervisor.stdout.json', 'settled-normal06-after-root-stdout.json', 896,
         '0df37043724399fd0b3b6597c4e77c6a72e14346271236b65d98a94d1554a58d'),
    ]
    documents, pins = [], []
    for remote_name, staged_name, size, digest_value in authorities:
        document, pin = json_pin(SETTLED_FENCE_ROOT / remote_name, digest_value, size)
        staged, staged_pin = json_pin(HERE / staged_name, digest_value, size)
        require(document == staged, 'settled normal06 original authority differs')
        documents.append(document)
        pins.extend([pin, staged_pin])
    terminal, control, after = documents
    require(terminal['state'] == 'FAILED' and terminal['inner_build_called'] is False and
            terminal['inner_returncode'] is None and terminal['main_fence_assessment'] is None and
            terminal['before_observed'] is False and terminal['after_observed'] is False and
            terminal['capture_lifecycle_controls'] is None and
            terminal['error'] == "RuntimeError('fixed child did not exit zero'); post-fence: RuntimeError('fixed child did not exit zero')" and
            terminal['Main_actions'] == terminal['Android_actions'] == 0 and
            terminal['installed'] is False and terminal['production_ready'] is False,
            'normal06 pre-builder failure was relabeled or not settled')
    receipts = terminal['capture_lifecycle_receipts']
    require(len(receipts) == 2 and [r['phase'] for r in receipts] == ['control-root-timeout', 'after'],
            'normal06 exact two failed outer captures differ')
    for index, (receipt, supervisor) in enumerate(zip(receipts, [control, after])):
        command = receipt['command']
        reaper = receipt['outer_subreaper']
        require(receipt['snapshot_sha256'] == '7908f4730c658e0d2f43ca66a810eb6d7033634560fcba2d7d928b380795136e' and
                receipt['root_source_sha256'] == 'a3a8f95260d71df60d5f2d51ed34b669fbe398b055dc0cb680002096caf53147' and
                receipt['lifecycle_sha256'] == '7fe6569f6665d6b710d2207c53e631261d6eb922d37e24ddfe5de15b841f0126' and
                receipt['qualified_success'] is False and receipt['secondary_errors'] == [] and
                receipt['outer_watchdog_installed_before_launch'] is True and
                receipt['outer_watchdog_disarmed_and_restored'] is True and
                receipt['within_absolute_outer_deadline'] is True and
                reaper['begin_passed'] is True and reaper['restored'] is True and reaper['final_children_empty'] is True and
                command['child_started'] is True and command['child_reaped'] is True and
                command['returncode'] == 1 and command['timed_out'] is False and command['kill_attempted'] is False and
                command['pidfd_closed'] is True and command['all_acquired_fds_closed'] is True and
                command['owned_tree_cleanup_complete'] is True and command['remaining_owned_children'] == [] and
                command['descendants'] == [] and command['secondary_errors'] == [] and
                command['retirement_within_deadline'] is True and command['qualified_success'] is False and
                all(command[k]['closed'] is True for k in ['input', 'stdout', 'stderr']) and
                command['stdout']['complete'] is True and command['stderr']['complete'] is True and
                command['stdout']['bytes'] == authorities[index + 1][2] and
                command['stdout']['sha256'] == authorities[index + 1][3] and command['stderr']['bytes'] == 0,
                'normal06 original root child/FD/watchdog retirement differs')
        require(supervisor['kind'] == 'fixed-root-main-snapshot-supervisor02' and
                supervisor['mode'] == ('control-timeout' if index == 0 else 'after') and
                supervisor['ok'] is False and supervisor['snapshot_qualified'] is False and
                supervisor['control_passed'] is False and supervisor['root_subreaper'] is None and
                supervisor['command'] is None and supervisor['child_stdout_utf8'] is None and
                supervisor['child_stderr_utf8'] is None and supervisor['secondary_errors'] == [] and
                supervisor['first_error'] == {'stage': 'root_supervisor', 'type': 'RuntimeError',
                    'errno': None, 'message': 'root child/lifecycle source pin differs'} and
                supervisor['root_uids'] == [0, 0, 0] and supervisor['dumpable'] == 0 and
                supervisor['Main_actions'] == supervisor['Android_actions'] == supervisor['service_actions'] == 0 and
                supervisor['watchdog_disarmed_after_retirement'] is True and
                supervisor['within_absolute_supervisor_deadline'] is True and
                supervisor['within_final_retirement_deadline'] is True,
                'normal06 failed before snapshot fork authority differs')
    return pins
