def hold_exact(name, pin, expected, held, deadline):
    path = pin['resolved_path']
    need(Path(path).is_absolute() and Path(path).resolve(strict=True).as_posix() == path,
         'EXACT_NONALIAS_INPUT_PATH:' + name)
    need(Path(pin['declared_path']).resolve(strict=True).as_posix() == path,
         'DECLARED_INPUT_ALIAS_CHANGED:' + name)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(fd); observed = ident(fd)
        need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and
             observed == {k: str(expected[k]) for k in FIELDS} and s.st_size == pin['bytes'],
             'EXACT_PREVIOUSLY_OBSERVED_FILE_IDENTITY_REQUIRED:' + name)
        need(digest_fd(fd, pin['bytes'], deadline) == pin['sha256'] and ident(fd) == observed,
             'FULL_PINNED_FILE_BYTES_CHANGED:' + name)
    except BaseException:
        os.close(fd); raise
    held.append({'name': name, 'fd': fd, 'path': path, 'declared_path': pin['declared_path'],
                 'bytes': pin['bytes'], 'sha256': pin['sha256'], 'identity': observed})
    return fd


def recheck_exact(held, deadline):
    for row in held:
        need(ident(row['fd']) == row['identity'] and
             digest_fd(row['fd'], row['bytes'], deadline) == row['sha256'],
             'HELD_INPUT_CHANGED:' + row['name'])
        fresh = os.open(row['path'], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            need(ident(fresh) == row['identity'] and
                 Path(row['path']).resolve(strict=True).as_posix() == row['path'] and
                 Path(row['declared_path']).resolve(strict=True).as_posix() == row['path'],
                 'INPUT_PATH_REPLACED:' + row['name'])
        finally:
            os.close(fresh)


def main():
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000 and
         sys.argv[1:] == ['--observe-signature-as-existing-owner-once'],
         'EXACT_UNPRIVILEGED_EXISTING_TOOL_OWNER_ENTRY')
    need(ROOT.parent.resolve() == ROOT.parent, 'FIXED_PRIVATE_PARENT')
    os.umask(0o077); before = census(); ROOT.mkdir(mode=0o700)
    held, deadline = [], time.monotonic() + 170
    result = {'schema': 'pocket4-szzc-operator-signature-observation-v1', 'ok': False, 'errors': [],
        'actual_uid': os.getuid(), 'actual_euid': os.geteuid(), 'root_execution': False,
        'Android_commands': 0, 'Main_actions': 0, 'installs': 0, 'UI_actions': 0,
        'permission_changes': 0, 'automatic_retry': False, 'production_ready': False,
        's37_failed_root_owner_assumption_preserved': True,
        'root_private_dependency_files_opened': False, 'old_files_modified_or_deleted': False,
        'current_manifest_verified': False, 'candidate_manifest_verified': False,
        'newer_version_claimed': False, 'commands': [],
        'tool_identity_basis': TOOL_EVIDENCE, 'runner_source_basis': RUNNER_EVIDENCE,
        'installed_signature_reference_kind': 'saved PackageManager certificate digest; not current APK cryptographic verification',
        'installed_signer_reference': SAVED_PM_SIGNER}
    try:
        need(len(TOOL_BINDINGS) == 12 and set(TOOL_BINDINGS) == EXPECTED_TOOL_NAMES,
             'EXACT_PRIOR_TWELVE_TOOL_INPUTS')
        for name, row in TOOL_BINDINGS.items():
            hold_exact(name, row['pin'], row['observed']['file'], held, deadline)
        af = hold_exact('complete_s36_APK', APK_PIN, APK_IDENTITY, held, deadline)
        result['candidate'] = {k: v for k, v in held[-1].items() if k != 'fd'}
        recheck_exact(held, deadline)
        argv = [TOOL_BINDINGS['java']['pin']['resolved_path'], '-Xmx256m', '-jar',
                TOOL_BINDINGS['apksigner_jar']['pin']['resolved_path'], 'verify', '--verbose',
                '--print-certs', '/proc/self/fd/' + str(af)]
        command = {'name': 'apksigner-verify', 'purpose': 'cryptographic signature observation only',
                   'execution_uid': 1000}
        result['commands'].append(command)
        outputs = run_tool(argv, (af,), command, deadline)
        for stream, raw in outputs.items():
            command[stream] = save('apksigner.' + stream, raw)
            if len(raw) <= 32768:
                command[stream + '_original_utf8'] = raw.decode('utf-8', 'strict')
        need(command.get('returncode') == 0 and command.get('joined') is True and
             command.get('pipes_closed') is True and command.get('output_capture_complete') is True and
             command.get('timed_out') is False and command.get('own_group_kill_requested') is False and
             not command.get('error') and not command.get('retirement_error') and
             not command.get('output_truncated'), 'COMPLETE_NORMAL_SIGNATURE_VERIFIER_EXIT_REQUIRED')
        certs = re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([0-9a-f]{64})$',
                           outputs['stdout'].decode('utf-8', 'strict'), re.M)
        need(certs and len(certs) == len(set(certs)), 'EXACT_UNIQUE_SIGNER_DIGESTS')
        recheck_exact(held, deadline)
        result.update(ok=True, signature_verified=True, signer_certificate_sha256=certs,
            signer_matches_saved_PM_reference=certs == [SAVED_PM_SIGNER],
            all_held_files_full_identity_and_hash_unchanged=True,
            held_input_bindings=[{k: v for k, v in row.items() if k != 'fd'} for row in held],
            update_eligibility='NOT_ASSESSED_PENDING_MANIFEST_CURRENT_SCOPE_AND_VERSION')
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
    finally:
        close_errors = []
        for row in reversed(held):
            try:
                os.close(row['fd'])
            except OSError as error:
                close_errors.append({'name': row['name'], 'errno': error.errno})
        result['held_files'] = {'acquired': len(held), 'closed': len(held) - len(close_errors), 'errors': close_errors}
        if close_errors:
            result['ok'] = False
    result['original_descriptor_identities_restored'] = census() == before
    result['ok'] = result['ok'] and result['original_descriptor_identities_restored']
    result['status'] = 'SIGNATURE_OBSERVED_NOT_INSTALLED' if result['ok'] else 'SIGNATURE_OBSERVATION_FAILED'
    raw = (json.dumps(result, sort_keys=True) + '\n').encode()
    save('result.json', raw); print(raw.decode(), end='', flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
