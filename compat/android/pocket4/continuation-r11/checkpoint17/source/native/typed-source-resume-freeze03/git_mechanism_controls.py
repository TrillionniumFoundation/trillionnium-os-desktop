#!/usr/bin/env python3
"""Local Git mechanism checks only; does not compile or execute the Rust patch."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import tempfile


def main():
    results = []
    commands = []
    environment = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
                   'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
                   'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0',
                   'GIT_NO_LAZY_FETCH': '1'}

    def git(root, args, expect=0, local_fixture=False):
        argv = ['/usr/bin/timeout', '--signal=TERM', '--kill-after=2s', '5s',
                '/usr/bin/git', '--no-optional-locks', '-C', str(root),
                '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
                '-c', 'protocol.allow=never']
        if local_fixture:
            argv += ['-c', 'protocol.file.allow=always']
        argv += args
        completed = subprocess.run(argv, env=environment, capture_output=True, timeout=8)
        commands.append({'operation': args[0], 'returncode': completed.returncode,
                         'stdout_sha256': hashlib.sha256(completed.stdout).hexdigest(),
                         'stderr_sha256': hashlib.sha256(completed.stderr).hexdigest(),
                         'local_fixture_transport': local_fixture})
        if expect is not None:
            assert completed.returncode == expect, (args, completed.stderr.decode())
        return completed

    with tempfile.TemporaryDirectory(prefix='bounded-source-mechanism-') as temporary:
        root = Path(temporary)
        origin = root / 'origin'
        origin.mkdir()
        git(origin, ['init', '--quiet', '--initial-branch=main'])
        (origin / 'marker').write_bytes(b'locked bytes\n')
        git(origin, ['add', 'marker'])
        git(origin, ['-c', 'user.name=Source Control', '-c',
                     'user.email=source-control@droidloom.invalid', 'commit', '--quiet', '-m', 'fixture'])
        commit = git(origin, ['rev-parse', 'HEAD']).stdout.decode().strip()

        def cached(name):
            path = root / name
            path.mkdir()
            git(path, ['init', '--quiet', '--initial-branch=droidloom'])
            git(path, ['fetch', '--quiet', '--depth=1', 'file://' + str(origin), commit], local_fixture=True)
            git(path, ['remote', 'add', 'origin',
                       'https://android.googlesource.com/platform/owned-resume-control'])
            return path

        checkout = cached('partial')
        assert (checkout / '.git/HEAD').read_bytes() == b'ref: refs/heads/droidloom\n'
        assert not (checkout / '.git/index').exists()
        git(checkout, ['cat-file', '-e', commit + '^{commit}'])
        lock = checkout / '.git/index.lock'
        lock.write_bytes(b'original interrupted index')
        blocked = git(checkout, ['checkout', '--quiet', '--detach', commit], expect=None)
        assert blocked.returncode != 0 and lock.read_bytes() == b'original interrupted index'
        evidence = root / 'retained-index.lock'
        lock.rename(evidence)
        git(checkout, ['checkout', '--quiet', '--detach', commit])
        assert evidence.read_bytes() == b'original interrupted index'
        assert (checkout / 'marker').read_bytes() == b'locked bytes\n'
        assert git(checkout, ['status', '--porcelain=v1', '--untracked-files=all']).stdout == b''
        results.append({'case': 'cached_initial_checkout_succeeds_after_retaining_stale_lock', 'pass': True})

        (checkout / 'marker').write_bytes(b'preserve changed bytes\n')
        changed = git(checkout, ['status', '--porcelain=v1', '--untracked-files=all'])
        assert changed.stdout and (checkout / 'marker').read_bytes() == b'preserve changed bytes\n'
        results.append({'case': 'readonly_status_reports_dirty_completed_project_without_overwrite', 'pass': True})

        conflict = cached('conflict')
        (conflict / 'marker').write_bytes(b'preserve untracked conflict\n')
        stopped = git(conflict, ['checkout', '--quiet', '--detach', commit], expect=None)
        assert stopped.returncode != 0
        assert (conflict / 'marker').read_bytes() == b'preserve untracked conflict\n'
        assert (conflict / '.git/HEAD').read_bytes() == b'ref: refs/heads/droidloom\n'
        results.append({'case': 'plain_cached_checkout_refuses_untracked_conflict', 'pass': True})

        sparse = root / 'sparse'
        sparse.mkdir()
        git(sparse, ['init', '--quiet', '--initial-branch=droidloom'])
        git(sparse, ['sparse-checkout', 'init', '--cone'])
        git(sparse, ['sparse-checkout', 'set', '--cone', '--skip-checks', '--', 'Android.bp',
                     'clang-r584948b/lib/clang/22/include', 'clang-r584948b/lib/clang/22/lib/linux',
                     'soong', 'clang-r584948b'])
        selected = git(sparse, ['sparse-checkout', 'list']).stdout.decode().splitlines()
        assert selected == ['Android.bp', 'clang-r584948b', 'soong']
        assert not (sparse / '.git/index').exists()
        results.append({'case': 'actual_cone_normalization_matches_locked_parent_set_and_unborn_index_absence',
                        'pass': True, 'selected': selected})

        version = git(root, ['--version']).stdout.decode().strip()
    print(json.dumps({'schema': 1, 'state': 'LOCAL_GIT_MECHANISMS_PASS_RUST_UNCOMPILED',
                      'git_version': version, 'controls': results, 'commands': commands,
                      'fixture_only_file_transport': True, 'HTTPS_or_network_transport': False,
                      'Rust_compiled_or_executed': False, 'actual_owned_staging_read': False,
                      'Main_actions': 0, 'device_actions': 0}, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
