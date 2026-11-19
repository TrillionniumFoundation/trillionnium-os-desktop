"""Finite phase identity, reserves and original full-role retirement."""


def duration_us(value):
    units = {'us': 1, 'ms': 1000, 's': 1000000, 'min': 60000000, 'h': 3600000000, 'd': 86400000000}
    parts = re.findall(r'(\d+)(us|ms|min|s|h|d)', value)
    need(parts and ''.join(n + u for n, u in parts) == value.replace(' ', ''), 'finite native duration')
    return sum(int(n) * units[u] for n, u in parts)


def verify_storage_unit(commands, contract, role, invocation):
    names = 'Id,InvocationID,RuntimeMaxUSec,TimeoutStopUSec,Restart,KillMode,RemainAfterExit,SendSIGKILL'
    row = commands.run('storage-lifetime-properties', ['/usr/bin/systemctl', 'show', contract[role + '_unit'],
        '--property=' + names, '--no-pager'])
    values = dict(line.split('=', 1) for line in output(row).splitlines() if '=' in line)
    need(values['Id'] == contract[role + '_unit'] and values['InvocationID'] == invocation,
         'actual original storage invocation')
    runtime = contract.get(role + '_runtime_max_seconds', contract['storage_runtime_max_seconds'])
    need(duration_us(values['RuntimeMaxUSec']) == runtime * 1000000 and
         duration_us(values['TimeoutStopUSec']) == contract['storage_stop_seconds'] * 1000000,
         'actual separately admitted finite storage lifetime and bounded stop')
    need(values['Restart'] == 'no' and values['KillMode'] == 'control-group' and
         values['RemainAfterExit'] == values['SendSIGKILL'] == 'yes', 'finite original storage lifetime')
    return values


def validate_failed_storage_admission(value, contract):
    rotation_schedule(contract)
    need(type(value) is dict and value['schema'] == 'p4-nbd-final-current-admission-v1' and
         value['stage'] == 'production651_failed_epoch_storage_only' and
         value['nonce'] == contract['nonce'] and value['allocation_source_manifest_sha256'] ==
         contract['allocation_source_manifest_sha256'], 'r8 storage binds its exact source and original allocation')
    qualified = value['failed_epoch_qualification']
    true_flags = ('controller_original_state_restored', 'server_lifecycle_clean',
        'known_predecessor_lifecycles_retired', 'ordinary_public_originals_actually_read',
        'offline_readonly_qualification_passed', 'known_finalizer_lifecycles_retired',
        'fresh_allocation_lock_EXNB_required', 'fresh_full_image_F9_and_no_writer_census_required',
        'fresh_current_owner_and_reserve_checks_required', 'new_mount_and_full_B_second_F9_required')
    false_flags = ('whole_image_hash_recomputed_for_r7', 'offline_fsck_repeated_for_r7',
        'complete_old_storage_retirement', 'unknown_progress_reader_retired', 'current_namespace_qualified',
        'new_storage_admitted', 'C_D_admitted', 'Android_passed', 'production_ready',
        'old_READY_reusable', 'old_plan_or_SQLite_resume_accepted')
    need(type(qualified) is dict and set(qualified) == set(true_flags + false_flags) | {
         'schema', 'offline_ancestor', 'immediate_predecessor', 'predecessor_refs',
         'whole_image', 'allocation_lock', 'controller_failure'} and
         qualified['schema'] == 'p4-r7-failed-successor-with-r6-offline-ancestor-qualified-v1' and
         encoded(qualified['immediate_predecessor']) == encoded(contract['immediate_predecessor']),
         'exact typed immediate predecessor separated from the complete offline ancestor')
    ancestor = qualified['offline_ancestor']
    need(type(ancestor) is dict and ancestor['schema'] == 'p4-failed-epoch-offline-qualified-input-v1' and
         encoded(ancestor['original_failed_epoch']) == encoded(contract['offline_ancestor']) and
         all(ancestor[key] is True for key in true_flags[4:]) and
         all(ancestor[key] is False for key in false_flags[2:]) and
         all(qualified[key] is True for key in true_flags) and
         all(qualified[key] is False for key in false_flags),
         'original r6 scope and all fresh guards survive without a rehash, relabel or new permission')
    labels = {'r7.controller.result', 'r7.controller.retirement', 'r7.controller.root',
              'r7.server.result', 'r7.server.retirement', 'r7.server.root', 'r7.public.root'}
    need(type(qualified['predecessor_refs']) is dict and set(qualified['predecessor_refs']) == labels and
         type(ancestor['phase_refs']) is dict and set(ancestor['phase_refs']) == set(contract['transition_originals']) - labels,
         'seven exact predecessor originals and ten exact offline ancestor originals')
    for refs in (qualified['predecessor_refs'], ancestor['phase_refs']):
        for label, ref in refs.items():
            need(encoded(full_ref(ref)) == encoded(full_ref(contract['transition_originals'][label]['original'])),
                 'full native-int original reference, never a copied or partial identity')
    need(encoded(qualified['whole_image']) == encoded(ancestor['whole_image']) == encoded(contract['offline_image']) and
         encoded(full_ref(qualified['allocation_lock'])) == encoded(full_ref(ancestor['allocation_lock'])) and
         qualified['allocation_lock']['path'] == contract['allocation_lock_path'] and
         qualified['controller_failure'] == ["RuntimeError('fresh preserved-volume server export bound to complete offline verification')"],
         'same original image/lock and the actual unmodified controller failure')
    image = qualified['whole_image']
    full_ref({key: image[key] for key in ('path', 'bytes', 'sha256', 'identity')})
    need(encoded(value['allocated_image']) == encoded(dict(image, uuid=contract['image_uuid'])) and
         encoded(full_ref(value['allocation_lock'])) == encoded(qualified['allocation_lock']),
         'same qualified image and original lock, retaining all nine actual fields')
    need(value['image_verification_scope'] == 'r7_known_failure_retirements_and_unchanged_r6_offline_ancestor' and
         value['failed_epoch_offline_qualification_passed'] is True and
         value['fresh_full_B_required_before_C_D'] is True and
         value['new_mount_complete_F9_required_before_C_D'] is True,
         'historical image qualification still needs a new full B and second F9')
    need(encoded(value['schedule']) == encoded(rotation_schedule(contract)) and
         encoded(value['rotation_binding']) == encoded(storage_binding(contract,
             value['source_manifest_sha256'], full_ref(value['rotation_inputs'])['sha256'])),
         'same exact new source, actual rotation reference, independent owner and finite schedule')
    need(all(value.get(key) is False for key in (
         'permits_build_without_separate_role_admission', 'permits_existing_device_use',
         'observed_F9_plan_accepted', 'new_mount_F9_qualified', 'C_D_admitted',
         'original_B_passed', 'new_final_F9_passed', 'original_desktop_functional_passed',
         'whole_storage_lifecycle_passed', 'root_may_renew_CURRENT_after_dispatch', 'production_ready',
         'old_owner_deadline_extended', 'current_namespace_qualified', 'complete_old_storage_retirement',
         'unknown_progress_reader_retired', 'cleanup_depends_on_old_CURRENT', 'formatting_performed')),
         'new storage preserves every explicit non-permission and all historical failures')
    owner = contract['owner_acquisition']['owner']
    need(type(value['new_allocation_bytes']) is int and value['new_allocation_bytes'] == 0 and
         value['foreground_owner'] == owner['name'] and value['lease_until_utc'] == owner['active_until_utc'],
         'no allocation or deadline renewal; only the exact independently acquired owner')


def storage_admission(directory, accepted, admission_sha, contract):
    ref, value = load_admission(directory, accepted, admission_sha, contract)
    validate_failed_storage_admission(value, contract)
    return ref, value


def allocation_input(commands, contract, admission):
    result_ref, body = pin(contract['allocation_result_path'], admission['allocation_result'])
    result = json.loads(body)
    retired_ref, body = pin(contract['allocation_retirement_path'], admission['allocation_retirement'])
    retired = json.loads(body)
    need(result['passed'] is True and result['source_manifest_sha256'] == contract['allocation_source_manifest_sha256'] and
         retired['source_manifest_sha256'] == contract['allocation_source_manifest_sha256'] and
         retired['retirement_passed'] is True and retired['allocation_functional_passed'] is True and
         retired['actual_terminal']['Result'] == 'success', 'actual complete allocation and independent native success')
    need(retired['allocation_result'] == result_ref and retired['original_full_readback_retained'] == result['formatted_image'],
         'independent retirement binds the original complete readback')
    need(result['formatted_image'] == admission['allocated_image'] and
         result['formatted_image']['path'] == contract['image_path'] and
         result['formatted_image']['bytes'] == contract['image_bytes'] and
         result['formatted_image']['uuid'] == contract['image_uuid'], 'exact physically allocated selected image')
    state = show(commands, contract['allocation_unit'])
    need(state['MainPID'] == '0' and state['ActiveState'] == 'inactive' and
         not (P('/sys/fs/cgroup/system.slice') / contract['allocation_unit']).exists(), 'allocator remains retired')
    return result_ref, retired_ref


def physical_image(path, size, expected_identity=None):
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == before.st_gid == 1000 and
             before.st_size == size and before.st_blocks * 512 >= size and f9(before) == f9(P(path).lstat()),
             'exact original ordinary single-link physically allocated regular image')
        if expected_identity is not None: need(f9(before) == expected_identity, 'allocated image full F9')
        return fd, {'path': str(path), 'identity': f9(before), 'allocated_bytes': before.st_blocks * 512}
    except BaseException:
        os.close(fd); raise


def root_record(path):
    ref, raw = pin(path)
    need(ref['identity'][3:6] == [0, 0, 1] and stat.S_IMODE(ref['identity'][2]) == 0o444,
         'immutable root-authored operation intent')
    return ref, json.loads(raw)


def role_description(contract, role):
    return 'Pocket4 Production651 owned mounted role ' + role + ' ' + contract['nonce']


def validate_role_intent(contract, accepted, admission_sha, role, intent):
    need(role in contract['role_units'] and intent['schema'] == 'p4-production651-storage-role-intent-v1' and
         intent['role'] == role and intent['unit'] == contract['role_units'][role] and
         intent['nonce'] == contract['nonce'] and intent['source_manifest_sha256'] == accepted and
         intent['admission_sha256'] == admission_sha and intent['boot'] == contract['hosts']['desktop']['boot'],
         'exact fixed role and storage generation')
    expected = ['/usr/bin/python3', '-I', '-B', contract['desktop_source'] + '/namespace_entry.py',
                accepted, admission_sha, role, intent['role_manifest_sha256']]
    need(intent['argv'] == expected and intent['description'] == role_description(contract, role),
         'fixed root namespace-entry argv; no arbitrary command surface')


def retire_registered_roles(commands, directory, contract, accepted, admission_sha):
    """Retire only this owner's fixed original roles before any unmount."""
    actors = []; results = []
    try:
        for role, unit in contract['role_units'].items():
            state = show(commands, unit)
            if state.get('LoadState') == 'not-found':
                need(not (P('/sys/fs/cgroup/system.slice') / unit).exists(), 'absent original role cgroup')
                results.append({'role': role, 'unit': unit, 'actual_absent': True}); continue
            intent_ref, intent = root_record(directory / 'actor-intents' / (role + '.json'))
            validate_role_intent(contract, accepted, admission_sha, role, intent)
            argv = re.findall(r'argv\[\]=(.*?) ;', state['ExecStart'])
            need(state['Description'] == intent['description'] and state['User'] == state['Group'] == '0' and
                 len(argv) == 1 and shlex.split(argv[0]) == intent['argv'] and
                 int(state['ExecMainStartTimestampMonotonic']) * 1000 >= intent['created_monotonic_ns'] and
                 re.fullmatch('[a-f0-9]{32}', state['InvocationID']), 'actual original role unit and entry source')
            actor = {'role': role, 'unit': unit, 'intent': intent_ref, 'state': state, 'held': None}
            actors.append(actor)
            if int(state['MainPID']):
                try:
                    actor['held'] = HeldProcess(int(state['MainPID']))
                    current = proc_ref(actor['held'].pid)
                    again = show(commands, unit)
                    need(current['cmdline'] == [a.encode() for a in intent['argv']] and
                         current['cgroup'].strip() == '0::' + state['ControlGroup'] and
                         again['InvocationID'] == state['InvocationID'],
                         'held original mounted-role generation before stop')
                    if again['MainPID'] != state['MainPID']:
                        need(again['MainPID'] == '0' and not actor['held'].live(),
                             'same original role finished while checking its generation')
                        actor['terminal_during_open'] = True
                except OSError as error:
                    need(error.errno in (errno.ENOENT, errno.ESRCH), 'original role open error')
                    again = show(commands, unit)
                    need(again['MainPID'] == '0' and
                         (again['InvocationID'] == state['InvocationID'] or again.get('LoadState') == 'not-found') and
                         not P('/proc/' + state['MainPID']).exists(),
                         'terminal-first race proves original numeric PID absent without signaling a replacement')
                    actor['terminal_during_open'] = True
        # Signal all admitted original roles before waiting; independent timeouts
        # cannot multiply the owner's one bounded cleanup interval.
        for actor in actors:
            if actor['held'] is not None: actor['held'].signal(signal.SIGTERM)
        deadline = time.monotonic() + 1000
        for actor in actors:
            state = show(commands, actor['unit'])
            while state['MainPID'] != '0':
                need(time.monotonic() < deadline and state['InvocationID'] == actor['state']['InvocationID'],
                     'bounded same-role retirement before storage detach')
                time.sleep(0.5); state = show(commands, actor['unit'])
            released = state.get('LoadState') == 'not-found'
            if released:
                need(not (P('/sys/fs/cgroup/system.slice') / actor['unit']).exists(),
                     'concurrently released original role has no remaining cgroup')
            else:
                need(state['InvocationID'] == actor['state']['InvocationID'] and state['ExecMainCode'] in ('1', '2', '3'),
                     'actual mounted-role terminal retained before stop')
            retirement = actor['held'].retired(5) if actor['held'] is not None else {'terminal_at_first_observation': True}
            terminal = {'role': actor['role'], 'intent': actor['intent'], 'terminal': state,
                        'terminal_during_open': actor.get('terminal_during_open', False),
                        'manager_terminal_already_released': released, 'role_functional_success_not_inferred': True,
                        **retirement}
            save(commands.directory / ('role-' + actor['role'] + '-terminal.json'), terminal)
            stop_error = None
            if not released:
                try: commands.run('release-original-mounted-role', ['/usr/bin/systemctl', 'stop', actor['unit']], 45)
                except BaseException as error: stop_error = str(error)
            after = show(commands, actor['unit'])
            if after.get('ActiveState') == 'failed':
                need(after['InvocationID'] == state['InvocationID'], 'only original failed role reset')
                commands.run('release-original-role-failure', ['/usr/bin/systemctl', 'reset-failed', actor['unit']], 15)
                after = show(commands, actor['unit'])
            need(after['MainPID'] == '0' and after['ActiveState'] == 'inactive' and
                 not (P('/sys/fs/cgroup/system.slice') / actor['unit']).exists(), 'original mounted-role cgroup absent')
            results.append({**terminal, 'after': after, 'stop_ack_error': stop_error})
        return results
    finally:
        for actor in actors:
            if actor['held'] is not None: actor['held'].close()


def recover_normal_projection(commands, directory, mount, contract, accepted, admission_sha):
    work = mount / 'source-production651/work'
    journal = work / 'source-projection.json'
    if not os.path.lexists(journal):
        return {'projection_journal_absent': True, 'normal_recovery_commands': 0}
    admissions = []
    for role in ('vendor_inner', 'wm_inner'):
        path = directory / 'actor-intents' / (role + '.json')
        if path.exists():
            reference, intent = root_record(path)
            validate_role_intent(contract, accepted, admission_sha, role, intent)
            admissions.append((reference, intent))
    need(admissions, 'a remaining journal must belong to an actually admitted full producer')
    role_ref, role_manifest = root_record(P(contract['full_source_dir']) / 'ROLE-SOURCE-MANIFEST.json')
    need(all(role_ref['sha256'] == intent['role_manifest_sha256'] for _, intent in admissions) and
         role_manifest['storage_source_manifest_sha256'] == accepted and
         role_manifest['storage_admission_sha256'] == admission_sha,
         'same root-reviewed full role source for normal recovery')
    recipe = mount / contract['full_tools_relative'] / 'recipe'
    updater = mount / contract['full_tools_relative'] / 'bin/droidloom-update'
    need(role_manifest['normal_updater']['path'] == str(updater) and
         role_manifest['source_work_path'] == str(work) and role_manifest['source_recipe_path'] == str(recipe),
         'recovery cannot select another worktree or updater')
    tool_ref, _ = pin(updater, role_manifest['normal_updater'])
    need(tool_ref['identity'][3:6] == [1000, 1000, 1] and stat.S_IMODE(tool_ref['identity'][2]) == 0o755,
         'exact ordinary qualified updater ELF')
    before = pin(journal, limit=128 * 1024**2)[0]
    original_cwd = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.chdir(recipe)
        row = commands.run('normal-owned-source-projection-recovery',
            [str(updater), 'recover-source', '--work', str(work)], 300, uid=1000)
    finally:
        os.fchdir(original_cwd); os.close(original_cwd)
    need(not os.path.lexists(journal), 'normal original protocol removed its recovered source journal')
    pin(updater, tool_ref)
    return {'projection_journal_before': before, 'normal_updater': tool_ref, 'command': row,
            'projection_journal_absent': True, 'normal_recovery_commands': 1,
            'full_build_success_not_inferred': True}


def capture_selected_delivery(directory, mount, contract, accepted, admission_sha):
    path = mount / 'delivery/SELECTED-OUTPUTS.json'
    if not path.exists(): return {'present': False, 'build_success_not_inferred': True}
    source_ref, raw = pin(path, limit=8 * 1024**2); value = json.loads(raw)
    need(value['schema'] == 'p4-production651-selected-output-delivery-v1' and value['nonce'] == contract['nonce'] and
         value['storage_source_manifest_sha256'] == accepted and value['storage_admission_sha256'] == admission_sha,
         'selected output metadata belongs to this original volume generation')
    need(0 < len(value['files']) <= 20000 and sum(row['bytes'] for row in value['files']) <= 16 * GIB,
         'fixed bounded selected-output export budget')
    names = set()
    for row in value['files']:
        relative = row['image_path']; p = pathlib.PurePosixPath(relative)
        need(not p.is_absolute() and '..' not in p.parts and relative not in names and
             re.fullmatch('[A-Za-z0-9._/+@-]+', relative) is not None and
             (relative.startswith('build-production651/') or relative.startswith('delivery/host-deps/')),
             'selected output is confined to original build or private dependency copy')
        names.add(relative); target = mount / relative
        need(target.resolve() == target, 'selected regular output has no path symlink')
        st = target.lstat()
        need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == st.st_gid == 1000 and
             st.st_dev == os.makedev(43, 0) and f9(st) == row['identity'] and st.st_size == row['bytes'],
             'stable original whole-hashed selected output metadata after all writers retired')
    pin(path, source_ref)
    copied = save(directory / 'SELECTED-OUTPUTS.json', raw, 0o444)
    return {'present': True, 'original_manifest': source_ref, 'copied_manifest': copied,
            'files': len(names), 'bytes': sum(row['bytes'] for row in value['files']),
            'actual_output_hashes_supplied_by_original_full_producer': True,
            'whole_output_hashes_recomputed_by_this_capture': False, 'build_success_not_inferred': True}


def offline_image_observation(contract, admission):
    need(os.getresuid() == (0, 0, 0), 'root independent offline writer observation')
    image = P(contract['image_path'])
    fd = os.open(image, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        value = os.fstat(fd)
        need(stat.S_ISREG(value.st_mode) and value.st_nlink == 1 and value.st_uid == value.st_gid == 1000 and
             value.st_size == contract['image_bytes'] and value.st_blocks * 512 >= value.st_size and
             f9(value) == f9(image.lstat()) and f9(value)[:2] == admission['allocated_image']['identity'][:2],
             'same original fully allocated regular image after storage retirement')
        metadata = {'path': str(image), 'identity': f9(value), 'allocated_bytes': value.st_blocks * 512}
    finally: os.close(fd)
    matches = []; unavailable = []; processes = descriptors = 0; deadline = time.monotonic() + 60
    for process in P('/proc').iterdir():
        if not process.name.isdecimal(): continue
        need(time.monotonic() < deadline, 'bounded independent image-writer observation')
        try:
            entries = list((process / 'fd').iterdir()); processes += 1
        except OSError as error:
            if error.errno in (errno.ENOENT, errno.ESRCH): continue
            unavailable.append({'pid': int(process.name), 'errno': error.errno}); continue
        for entry in entries:
            need(time.monotonic() < deadline, 'bounded independent image descriptor observation')
            try:
                state = entry.stat(); descriptors += 1
                if (state.st_dev, state.st_ino) != tuple(metadata['identity'][:2]): continue
                info = (process / 'fdinfo' / entry.name).read_text()
                flags = int(next(line.split()[1] for line in info.splitlines() if line.startswith('flags:')), 8)
                if flags & os.O_ACCMODE != os.O_RDONLY:
                    matches.append({'pid': int(process.name), 'fd': entry.name, 'start_ticks': birth(int(process.name)),
                                    'access_mode': flags & os.O_ACCMODE})
            except OSError as error:
                if error.errno not in (errno.ENOENT, errno.ESRCH):
                    unavailable.append({'pid': int(process.name), 'fd': entry.name, 'errno': error.errno})
    need(not unavailable and not matches, 'no unobserved process descriptors or remaining original-image writer')
    need(f9(image.lstat()) == metadata['identity'], 'same image throughout independent writer observation')
    return {'image': metadata, 'processes_observed': processes, 'descriptors_observed': descriptors,
            'image_writers': matches, 'unavailable': unavailable, 'whole_image_hash_not_computed_here': True}
