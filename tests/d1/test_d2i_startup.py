"""Actual shell/e2fsprogs host regressions; they do not qualify a QEMU guest."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / 'packaging/debian/image/d2i-overlay'
LIBEXEC = OVERLAY / 'usr/local/libexec'


class StartupShellTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.bin = self.work / 'bin'
        self.bin.mkdir()

    def command(self, name: str, body: str) -> Path:
        path = self.bin / name
        path.write_text('#!/bin/bash\n' + body)
        path.chmod(0o700)
        return path

    def probe(self, body: str) -> subprocess.CompletedProcess[str]:
        client = self.command('wayland-info', body)
        source = (LIBEXEC / 'trillionnium-d2i-wait-wayland').read_text()
        source = source.replace('/usr/bin/wayland-info', str(client))
        source = source.replace('/run/hepta-desktop', str(self.work))
        # Shorten only the isolated host fixture, never the tracked service.
        source = source.replace('deadline=$((SECONDS + 20))', 'deadline=$((SECONDS + 1))')
        script = self.work / 'probe.sh'
        script.write_text(source)
        return subprocess.run(['bash', str(script)], capture_output=True, text=True, timeout=5)

    def test_protocol_round_trip_succeeds_with_all_required_globals(self) -> None:
        result = self.probe("printf \"interface: 'wl_compositor'\\ninterface: 'wl_shm'\\ninterface: 'xdg_wm_base'\\n\"\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PROTOCOL_READY', result.stdout)
        self.assertFalse(list(self.work.glob('d2i-wayland-info.*')))

    def test_socket_path_and_partial_globals_do_not_establish_readiness(self) -> None:
        (self.work / 'wayland-0').touch()
        result = self.probe("printf \"interface: 'wl_compositor'\\ninterface: 'wl_shm'\\n\"\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('PROTOCOL_READY', result.stdout)
        self.assertIn('PROTOCOL_FAIL', result.stderr)

    def test_nonzero_client_exit_cannot_supply_ready_text(self) -> None:
        result = self.probe("printf \"interface: 'wl_compositor'\\ninterface: 'wl_shm'\\ninterface: 'xdg_wm_base'\\n\"\nexit 1\n")
        self.assertNotEqual(result.returncode, 0)

    def test_hung_protocol_client_is_terminated_and_cleans_report(self) -> None:
        started = time.monotonic()
        result = self.probe('exec sleep 20\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertLess(time.monotonic() - started, 4)
        self.assertFalse(list(self.work.glob('d2i-wayland-info.*')))

    def test_oversized_protocol_output_is_bounded_and_refused(self) -> None:
        result = self.probe("head -c 1000000 /dev/zero | tr '\\0' x\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertLessEqual(len(result.stderr.encode()), 65600)

    def capture(self, reason: str = 'unit_failure', mutate=None) -> tuple[subprocess.CompletedProcess[str], Path]:
        parent = self.work / 'var'
        library = parent / 'lib'
        output = library / 'trillionnium-d2i-diagnostics'
        library.mkdir(parents=True)
        parent.chmod(0o700)
        library.chmod(0o700)
        output.mkdir(mode=0o700)
        calls = self.work / 'calls.txt'
        self.command('journalctl', "printf 'runtime exit status=73 D2I_EXPLICIT_STARTUP_NEGATIVE_EXIT_73\\n'; head -c 200000 /dev/zero | tr '\\0' x\n")
        self.command('systemctl', f'''if [[ $1 == show ]]; then
printf 'ActiveState=failed\\nResult=exit-code\\nExecMainStatus=73\\n'
else printf '%s\\n' "$*" >> '{calls}'; fi
''')
        self.command('runuser', f"printf 'renderer_read:%s\\n' \"$*\" >> '{calls}'; printf 'bounded weston failure\\n'\n")
        self.command('sync', f"printf 'sync\\n' >> '{calls}'\n")
        source = (LIBEXEC / 'trillionnium-d2i-capture-failure').read_text()
        source = source.replace('/var/lib/trillionnium-d2i-diagnostics', str(output))
        source = source.replace('for parent in /var /var/lib;', f'for parent in {parent} {library};')
        # Test the same private custody checks under this host fixture's UID.
        source = source.replace('$(stat -c %u "$parent") == 0', f'$(stat -c %u "$parent") == {os.getuid()}')
        source = source.replace('== 0:700', f'== {os.getuid()}:700')
        source = source.replace('== 0:600:1', f'== {os.getuid()}:600:1')
        script = self.work / 'capture.sh'
        script.write_text(source)
        if mutate:
            mutate(parent, output)
        result = subprocess.run(['bash', str(script), reason], capture_output=True, text=True, timeout=10,
                                env={**os.environ, 'PATH': str(self.bin) + ':' + os.environ['PATH']})
        return result, output

    def test_actual_capture_keeps_files_private_and_bounds_each_text(self) -> None:
        result, output = self.capture()
        self.assertEqual(result.returncode, 0, result.stderr)
        limits = {'runtime-journal.txt': 131072, 'acceptance-journal.txt': 65536,
                  'weston.log': 65536, 'unit-state.txt': 16384, 'failure.json': 4096}
        for name, limit in limits.items():
            path = output / name
            self.assertTrue(0 < path.stat().st_size <= limit, name)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        fact = json.loads((output / 'failure.json').read_text())
        self.assertEqual(fact['status'], 'FAIL')
        self.assertFalse(fact['release_ready'])
        calls = (self.work / 'calls.txt').read_text()
        self.assertIn('renderer_read:-u hepta-desktop --', calls)
        self.assertLess(calls.index('sync\n'), calls.index('poweroff --no-block'))

    def test_capture_refuses_symlink_directory_without_touching_target(self) -> None:
        outside = self.work / 'outside'
        outside.mkdir()
        def mutate(parent, output):
            output.rmdir()
            output.symlink_to(outside, target_is_directory=True)
        result, _ = self.capture(mutate=mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])

    def test_capture_refuses_group_writable_parent(self) -> None:
        result, output = self.capture(mutate=lambda parent, output: parent.chmod(0o770))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(output.iterdir()), [])

    def test_capture_refuses_nonprivate_leaf_directory(self) -> None:
        result, output = self.capture(mutate=lambda parent, output: output.chmod(0o755))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(output.iterdir()), [])

    def test_capture_refuses_symlink_parent_even_to_same_private_directory(self) -> None:
        saved = self.work / 'saved-var'
        def mutate(parent, output):
            parent.rename(saved)
            parent.symlink_to(saved, target_is_directory=True)
        result, _ = self.capture(mutate=mutate)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list((saved / 'lib/trillionnium-d2i-diagnostics').iterdir()), [])

    def test_full_boot_preflight_refuses_stale_facts_without_launching_qemu(self) -> None:
        output = self.work / 'output'
        output.mkdir()
        stale = output / 'startup-failure.json'
        stale.write_text('old facts remain unchanged')
        launched = self.work / 'qemu-launched'
        self.command('qemu-system-x86_64', f"touch '{launched}'\n")
        self.command('jq', 'exit 1\n')
        selection, image, preparation = (self.work / name for name in ('selection.json', 'image.ext4', 'preparation.json'))
        for path in (selection, image, preparation):
            path.touch()
        result = subprocess.run(['bash', str(ROOT / 'tests/qemu/run-d2i-boot-test.base.sh'),
                                 '--selection', str(selection), '--image', str(image),
                                 '--preparation', str(preparation), '--artifacts', str(self.work),
                                 '--output-dir', str(output), '--startup-failure-negative'],
                                capture_output=True, text=True, timeout=5,
                                env={**os.environ, 'PATH': str(self.bin) + ':' + os.environ['PATH']})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('fresh empty output directory', result.stderr)
        self.assertEqual(stale.read_text(), 'old facts remain unchanged')
        self.assertFalse(launched.exists())

    def test_capture_refuses_hardlinked_destination(self) -> None:
        foreign = self.work / 'foreign'
        foreign.write_text('unchanged private bytes')
        foreign.chmod(0o600)
        result, _ = self.capture(mutate=lambda parent, output: os.link(foreign, output / 'runtime-journal.txt'))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(foreign.read_text(), 'unchanged private bytes')

    def test_capture_reason_cannot_inject_json_fields(self) -> None:
        result, output = self.capture('bad","status":"PASS')
        self.assertEqual(result.returncode, 0, result.stderr)
        fact = json.loads((output / 'failure.json').read_text())
        self.assertEqual(fact['reason'], 'invalid_failure_reason')
        self.assertEqual(fact['status'], 'FAIL')


class StartupImageTests(unittest.TestCase):
    def test_actual_ext4_injection_includes_readiness_failure_and_compositor_dropin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            content = work / 'root'
            for name in ('usr/libexec', 'usr/local/libexec', 'usr/lib/trillionnium-d1',
                         'etc/systemd/system/trillionnium-d1-wayland.service.d'):
                (content / name).mkdir(parents=True, exist_ok=True)
            base = work / 'base.ext4'
            subprocess.run(['mke2fs', '-q', '-t', 'ext4', '-F', '-d', str(content), str(base), '32768'],
                           check=True, capture_output=True, timeout=30)
            outputs = []
            for index in (0, 1):
                image, evidence = work / f'image-{index}.ext4', work / f'evidence-{index}.json'
                subprocess.run(['bash', str(ROOT / 'tests/qemu/prepare-d2i-image.sh'),
                                '--base-image', str(base), '--runtime-binary', '/usr/bin/true',
                                '--overlay', str(OVERLAY), '--source-epoch', '1787875200',
                                '--servo-revision', '670ae8a70801b162e186f81cbb5bdd2d59c39108',
                                '--output-image', str(image), '--evidence', str(evidence)],
                               check=True, capture_output=True, text=True, timeout=45)
                fact = json.loads(evidence.read_text())
                self.assertFalse(fact['release_ready'])
                self.assertEqual(len(fact['injected_paths']), 10)
                for relative in ('etc/systemd/system/trillionnium-d1-wayland.service.d/20-d2i-failure.conf',
                                 'usr/local/libexec/trillionnium-d2i-wait-wayland',
                                 'usr/local/libexec/trillionnium-d2i-capture-failure'):
                    extracted = work / f'dump-{index}-{Path(relative).name}'
                    subprocess.run(['debugfs', '-R', f'dump /{relative} {extracted}', str(image)],
                                   check=True, capture_output=True, timeout=10)
                    self.assertEqual(extracted.read_bytes(), (OVERLAY / relative).read_bytes())
                outputs.append(hashlib.sha256(image.read_bytes()).hexdigest())
            self.assertEqual(outputs[0], outputs[1])

    def test_default_graph_has_no_negative_override_and_dedicated_failure_edges(self) -> None:
        runtime = (OVERLAY / 'etc/systemd/system/trillionnium-d2i-runtime.service').read_text()
        acceptance = (OVERLAY / 'etc/systemd/system/trillionnium-d2i-acceptance.service').read_text()
        compositor = (OVERLAY / 'etc/systemd/system/trillionnium-d1-wayland.service.d/20-d2i-failure.conf').read_text()
        failure = (OVERLAY / 'etc/systemd/system/trillionnium-d2i-failure.service').read_text()
        self.assertIn('OnFailure=trillionnium-d2i-failure.service', compositor)
        self.assertIn('OnFailure=trillionnium-d2i-failure.service', runtime)
        self.assertIn('22s /bin/bash /usr/local/libexec/trillionnium-d2i-wait-wayland', runtime)
        self.assertIn('Wants=trillionnium-d2i-runtime.service', acceptance)
        self.assertNotIn('Requires=trillionnium-d2i-runtime.service', acceptance)
        self.assertIn('StateDirectory=trillionnium-d2i-acceptance', acceptance)
        self.assertIn('StateDirectory=trillionnium-d2i-diagnostics', failure)
        self.assertIn('ExecStopPost=/usr/bin/systemctl poweroff --no-block', failure)
        self.assertNotIn('NEGATIVE_EXIT_73', runtime)
        workflow = (ROOT / '.github/workflows/d2i-integrated-image.yml').read_text()
        self.assertLess(workflow.index('boot-startup-negative'), workflow.index('boot-image'))
        self.assertIn('d2i-startup-negative-${{ github.sha }}', workflow)
        self.assertNotIn('paths:', workflow)


class StartupNegativeVerifierTests(unittest.TestCase):
    """Run the tracked verifier on declared host text fixtures, without QEMU."""
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        boot = (ROOT / 'tests/qemu/run-d2i-boot-test.base.sh').read_text()
        start = boot.index("root = Path(sys.argv[1])", boot.index('if [[ $startup_failure_negative == true ]]; then', boot.index('qemu_status=$?')))
        imports = 'import hashlib\nimport json\nimport os\nfrom pathlib import Path\nimport re\nimport sys\n'
        self.code = imports + boot[start:].split('\nPY\n', 1)[0]
        self.environment = {**os.environ, 'TESTED_SHA': '1' * 40, 'TESTED_TREE_SHA': '2' * 40,
                            'CANDIDATE_HEAD_SHA': '3' * 40, 'GITHUB_RUN_ID': '1',
                            'GITHUB_RUN_ATTEMPT': '1', 'EVIDENCE_ROLE': 'pr_synthetic_merge'}
        (self.work / 'serial.log').write_text('HOST_TEXT_FIXTURE_ONLY\nTRILLIONNIUM_D2I_ACCEPTANCE_FAIL:unit_failure\nreboot: Power down\n')
        failure = {'schema': 'trillionnium.desktop.d2i-startup-failure.v1', 'status': 'FAIL',
                   'reason': 'unit_failure', 'qualification_only': True, 'release_ready': False}
        (self.work / 'startup-failure.json').write_text(json.dumps(failure))
        (self.work / 'startup-runtime-journal.txt').write_text('HOST_TEXT_FIXTURE_ONLY D2I_EXPLICIT_STARTUP_NEGATIVE_EXIT_73\n')
        (self.work / 'startup-acceptance-journal.txt').write_text('HOST_TEXT_FIXTURE_ONLY\n')
        (self.work / 'startup-weston.log').write_text('HOST_TEXT_FIXTURE_ONLY\n')
        (self.work / 'startup-unit-state.txt').write_text('[trillionnium-d2i-runtime.service]\nResult=exit-code\nExecMainStatus=73\n')
        (self.work / 'trillionnium-d2i-startup-negative.ext4').write_bytes(b'HOST_FILE_FIXTURE_NOT_AN_IMAGE')
        (self.work / 'qemu-command.txt').write_text('HOST_TEXT_FIXTURE_ONLY -nic none\n')

    def run_verifier(self, negative_digest: str = 'b' * 64) -> subprocess.CompletedProcess[str]:
        return subprocess.run(['python3', '-c', self.code, str(self.work), 'a' * 64, negative_digest, '0', '30'],
                              capture_output=True, text=True, timeout=5, env=self.environment)

    def refused(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.work / 'startup-negative-result.json').exists())

    def test_host_fixture_cannot_promote_normal_runtime_or_release(self) -> None:
        result = self.run_verifier()
        self.assertEqual(result.returncode, 0, result.stderr)
        fact = json.loads((self.work / 'startup-negative-result.json').read_text())
        self.assertTrue(fact['negative_only'])
        for name in ('normal_runtime_qualified', 'release_ready', 'promotion_authoritative'):
            self.assertIs(fact[name], False)

    def test_serial_pass_marker_refuses_negative_packet(self) -> None:
        with (self.work / 'serial.log').open('a') as stream:
            stream.write('TRILLIONNIUM_D2I_ACCEPTANCE_PASS\n')
        self.refused(self.run_verifier())

    def test_absent_original_failure_cause_refuses_packet(self) -> None:
        (self.work / 'startup-runtime-journal.txt').write_text('different failure')
        self.refused(self.run_verifier())

    def test_status_73_from_another_unit_cannot_replace_runtime_cause(self) -> None:
        (self.work / 'startup-unit-state.txt').write_text('[trillionnium-d2i-runtime.service]\nExecMainStatus=0\n[other.service]\nExecMainStatus=73\n')
        self.refused(self.run_verifier())

    def test_missing_and_oversized_records_refuse_packet(self) -> None:
        (self.work / 'startup-runtime-journal.txt').write_text('x' * 131073)
        self.refused(self.run_verifier())
        (self.work / 'startup-weston.log').unlink()
        self.refused(self.run_verifier())

    def test_normal_image_digest_cannot_be_used_as_negative_identity(self) -> None:
        self.refused(self.run_verifier('a' * 64))

    def test_extra_production_claim_or_nonboolean_false_refuses_packet(self) -> None:
        path = self.work / 'startup-failure.json'
        fact = json.loads(path.read_text())
        fact['production_ready'] = True
        path.write_text(json.dumps(fact))
        self.refused(self.run_verifier())
        del fact['production_ready']
        fact['release_ready'] = 0
        path.write_text(json.dumps(fact))
        self.refused(self.run_verifier())

    def test_invalid_source_or_run_identity_refuses_packet(self) -> None:
        self.environment['GITHUB_RUN_ID'] = '0'
        self.refused(self.run_verifier())


if __name__ == '__main__':
    unittest.main()
