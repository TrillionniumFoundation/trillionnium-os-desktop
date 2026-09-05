from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "tools/reject_symlink_path.sh"


def run_path_check(path: Path) -> subprocess.CompletedProcess[str]:
    """Run the shared guard against *path* without invoking a full QEMU gate."""

    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; reject_symlink_path "$2" test-path',
            "reject-symlink-path",
            str(HELPER),
            str(path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )


def run_regular_path_check(path: Path) -> subprocess.CompletedProcess[str]:
    """Run the regular-file guard without invoking a full QEMU gate."""

    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; require_regular_path "$2" test-file',
            "reject-symlink-path",
            str(HELPER),
            str(path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )


class D1ShellPathSafetyTests(unittest.TestCase):
    def test_regular_file_guard_rejects_links_and_special_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            regular = root / "regular.txt"
            regular.write_text("ok", encoding="utf-8")
            self.assertEqual(run_regular_path_check(regular).returncode, 0)
            self.assertEqual(run_regular_path_check(root / "new.txt").returncode, 0)

            fifo = root / "fifo"
            os.mkfifo(fifo)
            fifo_result = run_regular_path_check(fifo)
            self.assertNotEqual(fifo_result.returncode, 0)
            self.assertIn("not a regular file", fifo_result.stderr)

            directory_result = run_regular_path_check(root)
            self.assertNotEqual(directory_result.returncode, 0)
            alias = root / "alias"
            alias.symlink_to(regular)
            alias_result = run_regular_path_check(alias)
            self.assertNotEqual(alias_result.returncode, 0)
            self.assertIn("symlink component", alias_result.stderr)

    def test_guard_rejects_final_and_parent_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            (real / "input.bin").write_bytes(b"input")
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)

            parent_result = run_path_check(alias / "new" / "output.json")
            self.assertNotEqual(parent_result.returncode, 0)
            self.assertIn("symlink component", parent_result.stderr)

            final_alias = root / "final-alias"
            final_alias.symlink_to(real / "input.bin")
            final_result = run_path_check(final_alias)
            self.assertNotEqual(final_result.returncode, 0)
            self.assertIn("symlink component", final_result.stderr)

    def test_guard_allows_real_and_not_yet_created_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            self.assertEqual(run_path_check(real / "new" / "output.json").returncode, 0)
            self.assertEqual(run_path_check(real / "input.bin").returncode, 0)

    def test_qemu_and_builder_scripts_guard_raw_paths_before_resolution(self) -> None:
        scripts = {
            "tests/qemu/run-d1-pipeline.sh": [
                'reject_symlink_path "$workspace"',
                'reject_symlink_path "$output_dir"',
            ],
            "tests/qemu/run-d1-boot-test.sh": [
                'reject_symlink_path "$selection"',
                'reject_symlink_path "$artifacts"',
                'reject_symlink_path "$output_dir"',
            ],
            "tests/qemu/run-d2i-boot-test.sh": [
                'reject_symlink_path "$selection"',
                'reject_symlink_path "$artifacts"',
                'reject_symlink_path "$image"',
                'reject_symlink_path "$preparation"',
                'reject_symlink_path "$output_dir"',
            ],
            "tests/qemu/prepare-d2i-image.sh": [
                'reject_symlink_path "$base_image"',
                'reject_symlink_path "$runtime_binary"',
                'reject_symlink_path "$overlay"',
                'reject_symlink_path "$output_image"',
                'reject_symlink_path "$evidence"',
            ],
            "packaging/debian/image/build-d1-image.sh": [
                'check_raw_path "D1 selection" "$selection"',
                'check_raw_path "D1 output directory" "$output_dir"',
            ],
        }
        for relative, checks in scripts.items():
            with self.subTest(script=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("reject_symlink_path.sh", source)
                for check in checks:
                    self.assertIn(check, source)
                self.assertIn("readlink -f --", source)

        for relative in (
            "tests/qemu/run-d1-boot-test.sh",
            "tests/qemu/run-d2i-boot-test.sh",
        ):
            with self.subTest(regular_guard=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("require_regular_path", source)
                self.assertIn("run_image", source)

        d2i_workflow = (ROOT / ".github/workflows/d2i-integrated-image.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("tools/reject_symlink_path.sh", d2i_workflow)
        self.assertIn("tests/qemu/run-d1-boot-test.sh", d2i_workflow)

        prepare = (ROOT / "tests/qemu/prepare-d2i-image.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('safe_io="$script_dir/../../tools/qemu_safe_io.py"', prepare)
        self.assertIn('python3 "$safe_io" copy', prepare)
        self.assertIn('--source "$base_image"', prepare)
        self.assertIn('--destination "$output_image"', prepare)
        self.assertIn('from qemu_safe_io import write_text', prepare)
        self.assertNotIn('cp --reflink=auto --sparse=always "$base_image"', prepare)
        self.assertNotIn('pathlib.Path(sys.argv[1]).write_text', prepare)

    def test_generated_result_paths_are_not_interpolated_into_python(self) -> None:
        for relative in (
            "tests/qemu/run-d1-boot-test.sh",
            "tests/qemu/run-d2i-boot-test.sh",
        ):
            with self.subTest(script=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("python3 - <<'PY'", source)
                self.assertIn('pathlib.Path(os.environ["RESULT_PATH"])', source)
                self.assertNotIn('pathlib.Path("$output_dir/boot-result.json")', source)

    def test_d1_pipeline_evidence_copy_is_regular_file_only(self) -> None:
        """Evidence staging must never dereference untrusted tree entries."""

        pipeline = (ROOT / "tests/qemu/run-d1-pipeline.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("copy_regular_tree", pipeline)
        self.assertIn('require_regular_path "$source"', pipeline)
        self.assertIn('require_regular_path "$destination"', pipeline)
        self.assertIn('find -P "$source_root"', pipeline)
        self.assertIn('find -P "$qemu_result"', pipeline)
        self.assertIn('find -P "$evidence"', pipeline)
        self.assertNotIn(' -exec cp ', pipeline)
        self.assertNotIn('cp -a "$logs/."', pipeline)
        self.assertNotIn('cp -a "$build_root/."', pipeline)
        self.assertNotIn('cp -a "$resolution_logs/."', pipeline)

    def test_d1_pipeline_stage_and_result_writes_are_link_safe(self) -> None:
        """Generated logs/results must resist preseeded links and collisions."""

        pipeline = (ROOT / "tests/qemu/run-d1-pipeline.sh").read_text(
            encoding="utf-8"
        )
        # Build logs live below ``candidate`` for both invocations; evidence
        # must retain separate build-a/build-b buckets.
        self.assertIn('name=$(basename -- "$build_root_base")', pipeline)
        self.assertNotIn(
            'name=$(basename "$(dirname "$build_root")")', pipeline
        )

        # Stage logs are opened by a descriptor with kernel no-follow and
        # non-blocking flags instead of shell redirection through a pathname.
        self.assertIn('require_regular_path "$log_path" "D1 stage log"', pipeline)
        self.assertIn('O_NOFOLLOW', pipeline)
        self.assertIn('O_NONBLOCK', pipeline)
        self.assertIn('subprocess.run(command, stdout=descriptor', pipeline)
        self.assertNotIn('"$@" >"$logs/$name.log"', pipeline)

        # The result record is published via a same-directory atomic rename;
        # this prevents a preseeded destination link from being followed.
        self.assertIn('def atomic_write_text(path: pathlib.Path, text: str)', pipeline)
        self.assertIn('tempfile.mkstemp(', pipeline)
        self.assertIn('os.replace(temporary_path, path)', pipeline)

    def test_qemu_boot_outputs_use_descriptor_backed_io(self) -> None:
        """Boot gates must not redirect generated evidence through pathnames."""

        for relative in (
            "tests/qemu/run-d1-boot-test.sh",
            "tests/qemu/run-d2i-boot-test.sh",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(script=relative):
                self.assertIn('safe_io="$script_dir/../../tools/qemu_safe_io.py"', source)
                self.assertIn('python3 "$safe_io" copy', source)
                self.assertIn('python3 "$safe_io" truncate --path', source)
                self.assertIn('python3 "$safe_io" run --log', source)
                self.assertIn('python3 "$safe_io" write --path', source)
                self.assertIn("from qemu_safe_io import write_text", source)
                self.assertNotIn('cp --sparse=always', source)
                self.assertNotIn(': > "$serial_log"', source)
                self.assertNotIn(': > "$qemu_log"', source)
                self.assertNotIn('> "$qemu_log" 2>&1', source)
                self.assertNotIn('debugfs -R "dump -p $guest_path $host_path"', source)
                self.assertNotIn('pathlib.Path(os.environ["RESULT_PATH"]).write_text', source)
                self.assertIn('require_regular_path "$run_image"', source)

    def test_builder_restricts_recursive_cleanup_name(self) -> None:
        source = (ROOT / "packaging/debian/image/build-d1-image.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            '[[ "$build_name" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]',
            source,
        )
        self.assertIn('rm -rf "$build_dir"', source)

    def test_builder_binds_archive_keyring_to_prepared_trust_workspace(self) -> None:
        source = (ROOT / "packaging/debian/image/build-d1-image.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("host_keyring_raw=$(jq -er '.archive_keyring.path'", source)
        self.assertIn("expected_host_keyring", source)
        self.assertIn("debian-13-archive-keyring.gpg", source)
        self.assertIn("archive_keyring.sha256", source)
        self.assertIn("stat -c '%h'", source)
        self.assertIn("sha256sum -- \"$host_keyring\"", source)


if __name__ == "__main__":
    unittest.main()
