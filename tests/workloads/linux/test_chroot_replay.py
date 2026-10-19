"""Chroot replay unit and real-host tests; NEVER infer Asterinas qualification."""
import importlib.util
import errno
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('a04_host_chroot', HERE/'chroot_replay.py')
chroot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chroot)


@unittest.skipUnless(os.geteuid() == 0, 'host CAP_SYS_CHROOT/root unavailable')
class ChrootReplay(unittest.TestCase):
    def run_or_skip_host_policy(self, archive, manifest, reference):
        try:
            return chroot.run(archive, manifest, reference)
        except OSError as exc:
            if exc.errno in (errno.EPERM, errno.EINVAL):
                self.skipTest(f"host uid 65534 mapping/chroot policy unavailable: {exc}")
            raise

    def make_input(self, base, *, noisy_stderr=False):
        stage = base/'staged'
        binary = stage/'usr/local/bin/a04/probe_static'
        binary.parent.mkdir(parents=True)
        source = base/'synthetic.c'
        body = ('#include <stdio.h>\nint main(void) { '
                + ('fputs("unexpected loader warning\\n", stderr); ' if noisy_stderr else '')
                + 'puts("{\\"ok\\":true,\\"token\\":\\"chroot_exec\\"}"); return 0; }\n')
        source.write_text(body)
        subprocess.run(['gcc','-O2','-static',str(source),'-o',str(binary)],
                       capture_output=True, check=True, timeout=30)
        binary.chmod(0o555)
        sha = chroot.capture.sha(binary)
        manifest = base/'manifest.json'
        manifest.write_text(json.dumps({'files': [{'path':'/usr/local/bin/a04/probe_static',
                        'sha256':sha, 'bytes':binary.stat().st_size, 'mode':'0555'}],
                        'elf':[{'name':'probe_static','sha256':sha,'path':'/usr/local/bin/a04/probe_static',
                                'interpreter': None, 'needed': []}]}))
        tar = base/'stage.tar'
        chroot.capture.create_tar(stage, tar)
        reference = {'binaries':{'static':{'sha256':sha,'interpreter':None,'needed':[]}},
                     'cases':{'static.errno':{'status':'pass','exit_code':0,
                                              'facts':{'ok':True,'token':'chroot_exec'}}}}
        return tar, manifest, reference

    def test_real_unprivileged_exec_in_pinned_rootfs(self):
        with tempfile.TemporaryDirectory() as td:
            archive, manifest, reference = self.make_input(Path(td))
            report = self.run_or_skip_host_policy(archive,manifest,reference)
            self.assertEqual(report['counts'],{'pass':1,'fail':0,'not_run':0})
            self.assertEqual(report['cases']['static.errno']['facts'],reference['cases']['static.errno']['facts'])
            self.assertEqual(report['platform']['execution'],'host_linux_chroot_uid65534')
            self.assertFalse(report['kernel_guest_verified'])
            self.assertFalse(report['real_hepta_w1_verified'])
            self.assertEqual(chroot.capture.sha(archive),report['rootfs_tar_sha256'])

    def test_real_correct_json_with_stderr_warning_must_fail(self):
        with tempfile.TemporaryDirectory() as td:
            archive, manifest, reference = self.make_input(Path(td), noisy_stderr=True)
            report = self.run_or_skip_host_policy(archive, manifest, reference)
            self.assertEqual(report['counts'], {'pass': 0, 'fail': 1, 'not_run': 0})
            self.assertEqual(report['cases']['static.errno']['error'], 'unexpected_stderr')

    def test_wrong_expected_facts_cannot_pass(self):
        with tempfile.TemporaryDirectory() as td:
            archive, manifest, reference = self.make_input(Path(td))
            reference['cases']['static.errno']['facts']['token'] = 'tampered'
            report = self.run_or_skip_host_policy(archive,manifest,reference)
            self.assertEqual(report['counts'],{'pass':0,'fail':1,'not_run':0})

    def test_self_consistent_manifest_cannot_launder_different_elf_bytes(self):
        # Rebuild with different optimization flags: exact same JSON behavior,
        # different executable SHA. files[] is updated while elf[] and the
        # fixed reference retain the original identity (a real old false pass).
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            archive, manifest, reference = self.make_input(base)
            staged = base / 'staged/usr/local/bin/a04/probe_static'
            subprocess.run(['gcc', '-O0', '-static', str(base/'synthetic.c'),
                            '-o', str(staged)], capture_output=True, check=True, timeout=30)
            staged.chmod(0o555)
            source = json.loads(manifest.read_text())
            source['files'][0]['sha256'] = chroot.capture.sha(staged)
            source['files'][0]['bytes'] = staged.stat().st_size
            self.assertNotEqual(source['files'][0]['sha256'],
                                reference['binaries']['static']['sha256'])
            manifest.write_text(json.dumps(source))
            chroot.capture.create_tar(base/'staged', archive)
            with self.assertRaisesRegex(ValueError, 'ELF bytes not identical'):
                chroot.run(archive, manifest, reference)

    def test_corrupted_archived_elf_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            archive, manifest, reference = self.make_input(base)
            raw=bytearray(archive.read_bytes())
            pattern=b'\x7fELF'
            assert pattern in raw
            off=raw.index(pattern)
            raw[off:off+4]=b'NOPE'
            archive.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'SHA-256'):
                chroot.run(archive,manifest,reference)


class ExactObservation(unittest.TestCase):
    def setUp(self):
        self.expected = {'status': 'pass', 'exit_code': 0,
                         'facts': {'ok': True, 'value': 'expected'}}

    def test_duplicate_json_keys_and_nonfinite_fail_closed(self):
        for output in ('{"ok":false,"ok":true,"value":"expected"}\n',
                       '{"ok":true,"value":"expected","extra":NaN}\n'):
            with self.subTest(output=output):
                result = {'exit_code': 0, 'stdout': output, 'stderr': '',
                          'timed_out': False, 'cleanup_incomplete': False}
                _, passed, error = chroot.exact_observation(result, self.expected)
                self.assertFalse(passed)
                self.assertEqual(error, 'invalid_or_ambiguous_json')

    def test_extra_stdout_or_failed_cleanup_never_passes(self):
        valid = json.dumps(self.expected['facts']) + '\n'
        for change, error in (({'stdout': valid + 'WARNING\n'}, 'unexpected_stdout'),
                              ({'cleanup_incomplete': True}, 'incomplete_descendant_cleanup')):
            with self.subTest(change=change):
                result = {'exit_code': 0, 'stdout': valid, 'stderr': '',
                          'timed_out': False, 'cleanup_incomplete': False}
                result.update(change)
                _, passed, actual_error = chroot.exact_observation(result, self.expected)
                self.assertFalse(passed)
                self.assertEqual(actual_error, error)


class DescendantCleanup(unittest.TestCase):
    def test_timeout_kills_forked_pipe_holders_without_hanging(self):
        # Real host process group test. No chroot and no production side effects.
        # A descendant inherits PIPE fds so killing only the parent would hang.
        code = ("import subprocess,sys,time;"
                "subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']);"
                "print('spawned',flush=True);time.sleep(30)")
        start = time.monotonic()
        result = chroot.bounded_run([sys.executable, '-c', code], env=os.environ.copy(),
                                    timeout=1, preexec_fn=None)
        self.assertTrue(result['timed_out'])
        self.assertNotEqual(result['exit_code'], 0)
        self.assertLess(time.monotonic() - start, 5.0)
        self.assertFalse(result['cleanup_incomplete'])

    def test_detached_child_pipe_cannot_hang_host_executor(self):
        # A grandchild deliberately escapes killpg via setsid while holding
        # stdout open. It is tracked by PID and explicitly killed in finally.
        with tempfile.TemporaryDirectory() as td:
            pidfile = Path(td) / 'detached.pid'
            child = ('import os,sys,time;os.setsid();'
                     'open(sys.argv[1],"w").write(str(os.getpid()));time.sleep(30)')
            parent = ('import subprocess,sys,time;'
                      'subprocess.Popen([sys.executable,"-c",sys.argv[2],sys.argv[1]]);'
                      'time.sleep(30)')
            start = time.monotonic()
            try:
                result = chroot.bounded_run([sys.executable, '-c', parent,
                                             str(pidfile), child], env=os.environ.copy(),
                                            timeout=3, preexec_fn=None)
                self.assertTrue(result['timed_out'])
                self.assertTrue(result['cleanup_incomplete'])
                self.assertLess(time.monotonic() - start, 9.5)
            finally:
                if pidfile.exists():
                    try:
                        os.kill(int(pidfile.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass


if __name__ == '__main__':
    unittest.main()
