"""Admit r8 from actual r7 retirement and the separate r6 offline ancestor; no build or namespace acceptance."""
import datetime, hashlib, json, pathlib, sys, signal
signal.alarm(100)
C = pathlib.Path(__file__).parent
assert len(sys.argv) == 6
accepted, current_size, current_sha, generation, rotation_sha = sys.argv[1:]
raw = (C / 'SOURCE-MANIFEST.json').read_bytes(); assert hashlib.sha256(raw).hexdigest() == accepted
manifest = json.loads(raw)
for name in ('common.py', 'storage_support.py', 'rotation_support.py'):
    body = (C / name).read_bytes()
    assert len(body) == manifest['files'][name]['bytes'] and hashlib.sha256(body).hexdigest() == manifest['files'][name]['sha256']
    exec(compile(body, str(C / name), 'exec'))
contract = json.loads((C / 'contract.json').read_bytes())
schedule = rotation_schedule(contract)  # Null owner/ROOT slots fail before live admission observations.
need(str(C) == contract['p4_source'] and os.getresuid() == os.getresgid() == (0, 0, 0),
     'fixed root new-storage admission')
boot_is(contract['hosts']['pocket4']['boot']); _, sources = sealed_sources(C, accepted)
check_tools(contract, 'pocket4')
canonical, body = pin(contract['canonical']['path'], {'bytes': int(current_size), 'sha256': current_sha})
need(canonical['identity'][3:6] == [1000, 1000, 1] and stat.S_IMODE(canonical['identity'][2]) == 0o600,
     'original operator-owned CURRENT')
current = json.loads(body); owner = current['foreground_owner']
need(current['continuation_current']['generation'] == owner['generation'] == generation and
     encoded(owner) == encoded(dict(contract['owner_acquisition']['owner'], generation=generation)) and
     encoded(current['foreground_owner_acquisition_current']) == encoded(contract['owner_acquisition']['record']) and
     datetime.datetime.fromisoformat(owner['active_until_utc']) > datetime.datetime.now(datetime.timezone.utc),
     'actual unexpired foreground owner and generation')
need((datetime.datetime.fromisoformat(owner['active_until_utc']) - datetime.datetime.now(datetime.timezone.utc)).total_seconds() >= 21600,
     'minimum storage admission window only; the fresh full B role needs its separate complete budget')
owner_root, _ = pin(contract['owner_acquisition']['root_acceptance']['path'],
                    contract['owner_acquisition']['root_acceptance'], limit=2 * 1024**2)
binding = storage_binding(contract, accepted, rotation_sha)
need(current['source_storage_rotation_current'] == binding,
     'CURRENT explicitly adopts this exact reviewed transition and new finite lifetime')
rotation_ref, rows, image = rotation_inputs(contract, 'pocket4', rotation_sha)
qualified = failed_predecessors(rows, contract)
need(qualified['whole_image'] == {k: v for k, v in image.items() if k != 'uuid'} and
     image['uuid'] == contract['image_uuid'], 'same unmodified r6 image after actual r7 lifecycle bookends')
lock_ref, _ = pin(contract['allocation_lock_path'], qualified['allocation_lock'])
need(lock_ref['identity'][3:6] == [1000, 1000, 1] and stat.S_IMODE(lock_ref['identity'][2]) == 0o600,
     'original ordinary allocation lock, not a new bypass lock')
lock = os.open(contract['allocation_lock_path'], os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
image_fd = None
try:
    need(f9(os.fstat(lock)) == lock_ref['identity'], 'same original lock')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    need(not os.path.lexists(contract['p4_root']) and not (C / 'ADMISSION.json').exists(),
         'one unused storage generation')
    fresh_writer_observation = offline_image_observation(contract, {'allocated_image': image})
    need(fresh_writer_observation['image']['identity'] == image['identity'], 'fresh whole F9 still equals the offline image')
    image_fd, observed = physical_image(contract['image_path'], contract['image_bytes'], image['identity'])
    need(observed['allocated_bytes'] == image['allocated_bytes'],
         'same completely allocated original volume after complete offline readback')
    need(mem_available() >= contract['p4_fresh_memory_minimum'] and
         free_space(P(contract['p4_root']).parent) >= contract['p4_fresh_disk_minimum'],
         'original fresh P4 memory and disk gates remain unchanged')
    sources_unchanged(sources); pin(canonical['path'], canonical); pin(rotation_ref['path'], rotation_ref)
    pin(owner_root['path'], owner_root)
    need(f9(os.fstat(lock)) == lock_ref['identity'] == f9(P(contract['allocation_lock_path']).lstat()),
         'same held and named original allocation lock at final seal')
    need(datetime.datetime.fromisoformat(owner['active_until_utc']) > datetime.datetime.now(datetime.timezone.utc),
         'same unexpired owner at final seal')
    value = {'schema': 'p4-nbd-final-current-admission-v1', 'stage': 'production651_failed_epoch_storage_only',
             'source_manifest_sha256': accepted, 'nonce': contract['nonce'], 'canonical': canonical,
             'declared_generation': generation, 'foreground_owner': owner['name'],
             'lease_until_utc': owner['active_until_utc'], 'pocket4_boot': contract['hosts']['pocket4']['boot'],
             'allocation_source_manifest_sha256': contract['allocation_source_manifest_sha256'],
             'allocated_image': image, 'allocation_lock': lock_ref,
             'fresh_writer_observation': fresh_writer_observation, 'rotation_inputs': rotation_ref, 'rotation_binding': binding, 'schedule': schedule,
             'image_verification_scope': 'r7_known_failure_retirements_and_unchanged_r6_offline_ancestor',
             'failed_epoch_qualification': qualified, 'failed_epoch_offline_qualification_passed': True,
             'complete_old_storage_retirement': False, 'unknown_progress_reader_retired': False,
             'current_namespace_qualified': False, 'fresh_full_B_required_before_C_D': True,
             'original_desktop_functional_passed': False, 'whole_storage_lifecycle_passed': False,
             'original_B_passed': False, 'new_final_F9_passed': False, 'C_D_admitted': False, 'observed_F9_plan_accepted': False,
             'new_mount_complete_F9_required_before_C_D': True, 'new_mount_F9_qualified': False,
             'observed_ns': time.time_ns(), 'new_allocation_bytes': 0, 'formatting_performed': False,
             'old_owner_deadline_extended': False, 'permits_build_without_separate_role_admission': False,
             'permits_existing_device_use': False, 'root_may_renew_CURRENT_after_dispatch': False,
             'cleanup_depends_on_old_CURRENT': False, 'production_ready': False}
    validate_failed_storage_admission(value, contract)
    print(json.dumps(save(C / 'ADMISSION.json', value, 0o444), sort_keys=True))
finally:
    if image_fd is not None: os.close(image_fd)
    os.close(lock)
