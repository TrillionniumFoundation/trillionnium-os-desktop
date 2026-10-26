#!/usr/bin/env python3
"""Real local Git, file and lease failures for original-entry provenance."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

import build_original_entry as build


class PackagingPermissionsTests(unittest.TestCase):
    """Actual small ELF/strip operations, never a Rust/Agentd qualification."""

    def setUp(self):
        self.cc, self.strip = shutil.which("cc"), shutil.which("strip")
        if not self.cc or not self.strip or not Path("/proc/self/status").is_file():
            self.skipTest("Linux C compiler and real strip are required")
        status = Path("/proc/self/status").read_text()
        effective = int(next(line.split()[1] for line in status.splitlines() if line.startswith("CapEff:")), 16)
        if effective & ((1 << 1) | (1 << 2)):
            self.skipTest("permission regression requires no DAC override/read-search capabilities")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        source = self.root / "probe.c"
        source.write_text("volatile int retained_value = 7;\nint main(void) { return retained_value; }\n")
        self.product = self.root / "original"
        subprocess.run([self.cc, "-g", "-no-pie", str(source), "-o", str(self.product)],
                       check=True, capture_output=True, timeout=30, env=build.BASE_ENV)
        self.frozen = self.root / "probe.unstripped"
        self.original = build.freeze(self.product, self.frozen)
        self.destination = self.root / "packaged"

    def test_readonly_copy_reproduces_failure_then_private_staging_strips_and_refreezes(self):
        old = self.root / "readonly"
        build.freeze(self.product, old)
        result = subprocess.run([self.strip, "--strip-debug", "--strip-unneeded", str(old)],
                                capture_output=True, text=True, timeout=30, env=build.BASE_ENV)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Permission denied", result.stderr)
        with build.packaging_copy(self.product, self.destination) as staged:
            self.assertEqual(staged.stat().st_mode & 0o7777, 0o700)
            subprocess.run([self.strip, "--strip-debug", "--strip-unneeded", str(staged)],
                           check=True, capture_output=True, timeout=30, env=build.BASE_ENV)
        self.assertEqual(self.destination.stat().st_mode & 0o7777, 0o555)
        self.assertLess(self.destination.stat().st_size, self.original["bytes"])
        self.assertEqual(build.digest(self.product), self.original["sha256"])
        self.assertEqual(build.digest(self.frozen), self.original["sha256"])
        self.assertEqual(self.frozen.stat().st_mode & 0o7777, 0o555)
        self.assertNotEqual(self.destination.stat().st_ino, self.product.stat().st_ino)

    def test_failed_real_strip_refreezes_only_its_staging_copy(self):
        invalid = self.root / "invalid-product"
        invalid.write_bytes(b"not an ELF")
        with self.assertRaises(subprocess.CalledProcessError):
            with build.packaging_copy(invalid, self.destination) as staged:
                subprocess.run([self.strip, "--strip-debug", "--strip-unneeded", str(staged)],
                               check=True, capture_output=True, timeout=30, env=build.BASE_ENV)
        self.assertEqual(self.destination.stat().st_mode & 0o7777, 0o555)
        self.assertEqual(invalid.read_bytes(), b"not an ELF")
        self.assertEqual(build.digest(self.frozen), self.original["sha256"])

    def test_existing_file_or_symlink_cannot_be_reused_as_writable_packaging_input(self):
        self.destination.write_bytes(b"retained old evidence")
        with self.assertRaisesRegex(ValueError, "must be new"):
            with build.packaging_copy(self.product, self.destination):
                self.fail("existing evidence became writable")
        self.assertEqual(self.destination.read_bytes(), b"retained old evidence")
        self.destination.unlink()
        self.destination.symlink_to(self.frozen)
        with self.assertRaisesRegex(ValueError, "must be new"):
            with build.packaging_copy(self.product, self.destination):
                self.fail("symlink became writable")
        self.assertEqual(build.digest(self.frozen), self.original["sha256"])
        self.assertEqual(self.frozen.stat().st_mode & 0o7777, 0o555)


class SourceAndEntryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir()
        self.entry = self.source / "codex-rs/hepta-agentd/src/bin/native.rs"
        self.entry.parent.mkdir(parents=True)
        self.entry.write_text("fn main() {}\n")
        self.manifest = self.source / "codex-rs/hepta-agentd/Cargo.toml"
        self.manifest.write_text('[package]\nname="codex-hepta-agentd"\nversion="0.1.0"\n')
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Native test", "-c", "user.email=native@example.invalid", "commit", "-qm", "source")
        self.head = self.git("rev-parse", "HEAD").strip()
        self.tree = self.git("rev-parse", "HEAD^{tree}").strip()
        self.metadata = {"workspace_members": ["original-package"], "packages": [{
            "id": "original-package", "name": build.PACKAGE, "manifest_path": str(self.manifest),
            "targets": [{"name": "native", "kind": ["bin"], "crate_types": ["bin"], "src_path": str(self.entry)}],
        }]}

    def git(self, *arguments):
        return subprocess.check_output(["/usr/bin/git", "-C", str(self.source), *arguments], text=True,
                                       stderr=subprocess.PIPE, env=build.BASE_ENV)

    def test_clean_actual_git_snapshot_matches_selected_original_entry(self):
        snapshot = build.source_snapshot(self.source, self.head, self.tree)
        target = build.select_original_target(self.metadata, self.source, "native", "bin")
        by_path = {item["path"]: item for item in snapshot["files"]}
        self.assertEqual(by_path[target["path"]]["sha256"], target["entry_sha256"])
        self.assertEqual(snapshot, build.source_snapshot(self.source, self.head, self.tree))

    def test_tracked_change_and_untracked_file_are_both_rejected(self):
        self.entry.write_text("fn main() { panic!(); }\n")
        with self.assertRaisesRegex(ValueError, "dirty"):
            build.source_snapshot(self.source, self.head, self.tree)
        self.git("checkout", "--", str(self.entry.relative_to(self.source)))
        (self.source / "replacement.rs").write_text("fn main() {}\n")
        with self.assertRaisesRegex(ValueError, "dirty"):
            build.source_snapshot(self.source, self.head, self.tree)

    def test_assume_unchanged_cannot_hide_mutated_source_bytes(self):
        self.git("update-index", "--assume-unchanged", str(self.entry.relative_to(self.source)))
        self.entry.write_text("fn main() { panic!(); }\n")
        self.assertEqual(self.git("status", "--porcelain=v1"), "")
        with self.assertRaisesRegex(ValueError, "bytes differ from Git"):
            build.source_snapshot(self.source, self.head, self.tree)

    def test_wrong_commit_and_wrong_tree_are_rejected(self):
        for head, tree in (("1" * 40, self.tree), (self.head, "2" * 40)):
            with self.subTest(head=head, tree=tree), self.assertRaises(ValueError):
                build.source_snapshot(self.source, head, tree)

    def test_external_fixture_package_and_source_are_rejected(self):
        variants = []
        external_manifest = json.loads(json.dumps(self.metadata))
        external_manifest["packages"][0]["manifest_path"] = str(self.root / "fixture/Cargo.toml")
        variants.append(external_manifest)
        external_source = json.loads(json.dumps(self.metadata))
        outside = self.root / "fixture.rs"
        outside.write_text("fn main() {}\n")
        external_source["packages"][0]["targets"][0]["src_path"] = str(outside)
        variants.append(external_source)
        for metadata in variants:
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                build.select_original_target(metadata, self.source, "native", "bin")

    def test_required_feature_or_untracked_target_name_is_not_silently_enabled(self):
        self.metadata["packages"][0]["targets"][0]["required-features"] = ["test-issuer"]
        with self.assertRaisesRegex(ValueError, "explicit features"):
            build.select_original_target(self.metadata, self.source, "native", "bin")
        with self.assertRaisesRegex(ValueError, "does not exist"):
            build.select_original_target(self.metadata, self.source, "replacement", "bin")

    def test_busy_cache_and_linked_lease_are_rejected_without_waiting(self):
        target = self.root / "target"
        target.mkdir()
        with build.target_lease(target):
            with self.assertRaisesRegex(ValueError, "already leased"):
                with build.target_lease(target):
                    self.fail("second lease acquired")
        lock = target / ".hepta-native-userspace.lock"
        (target / "alias").hardlink_to(lock)
        with self.assertRaisesRegex(ValueError, "unaliased"):
            with build.target_lease(target):
                self.fail("aliased lease acquired")

    def test_failed_original_command_keeps_exit_and_real_log(self):
        output = self.root / "evidence"
        output.mkdir()
        report = {"commands": [], "g2_complete": False}
        with self.assertRaisesRegex(ValueError, "original command failed"):
            build.run(["/bin/sh", "-c", "echo retained-failure; exit 7"], self.root,
                      build.BASE_ENV, output, "failed.log", report, 10)
        self.assertEqual(report["commands"][0]["exit_code"], 7)
        self.assertEqual((output / "failed.log").read_text(), "retained-failure\n")
        self.assertFalse(json.loads((output / "result.json").read_text())["g2_complete"])


class StaticPrivateArchiveTests(unittest.TestCase):
    """Actual ar/file mutations with explicitly synthetic pkg-config/LLD replies.

    These guards do not claim to compile Rust, OpenSSL or an original Agentd.
    The installed system pkg-config and original full build are a separate gate.
    """
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="hepta-static-private-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.libdir = self.root / "lib"
        self.pcdir = self.libdir / "pkgconfig"
        self.pcdir.mkdir(parents=True)
        self.bin = self.root / "tools"
        self.bin.mkdir()
        self.toolchain = self.root / "toolchain/bin"
        self.toolchain.mkdir(parents=True)
        linker = self.toolchain.parent / "lib/rustlib" / build.TARGET / "bin"
        (linker / "gcc-ld").mkdir(parents=True)
        (linker / "rust-lld").write_text("#!/bin/sh\nprintf 'LLD synthetic-test-fixture\\n'\n")
        (linker / "rust-lld").chmod(0o700)
        (linker / "gcc-ld/ld.lld").symlink_to("../rust-lld")
        source, obj = self.root / "member.c", self.root / "member.o"
        source.write_text("int native_private_fixture(void) { return 7; }\n")
        subprocess.run(["/usr/bin/cc", "-c", source, "-o", obj], check=True, capture_output=True, env=build.BASE_ENV)
        for name in (build.PRIVATE_ARCHIVE, "libcrypto.a", "libssl.a"):
            subprocess.run(["/usr/bin/ar", "rcs", self.libdir / name, obj], check=True, capture_output=True, env=build.BASE_ENV)
        for name in ("openssl", "libssl", "libcrypto"):
            (self.pcdir / (name + ".pc")).write_text("Version: 3.5.5\nLibs.private: -l:libjitterentropy.a -lz -lzstd -ldl -pthread\n")
        # The script reads mutable fixture .pc bytes, allowing actual token,
        # source and postcheck failures without touching system packages.
        self.pkg = self.bin / "pkg-config"
        self.pkg.write_text("#!/usr/bin/python3\nimport sys\nfrom pathlib import Path\n"
            + "lib=Path(" + repr(str(self.libdir)) + ")\n"
            + "a=sys.argv[1:]\n"
            + "if a==['--version']: print('synthetic-pkg-config-fixture'); raise SystemExit(0)\n"
            + "module=a[-1]\ntext=(lib/'pkgconfig'/(module+'.pc')).read_text()\n"
            + "if a[0]=='--variable=libdir': print(lib)\n"
            + "elif a[0]=='--variable=pcfiledir': print(lib/'pkgconfig')\n"
            + "elif a[0]=='--modversion': print(next(x.split(':',1)[1].strip() for x in text.splitlines() if x.startswith('Version:')))\n"
            + "elif a[:2]==['--static','--libs']:\n"
            + " print('-lcrypto '+next(x.split(':',1)[1].strip() for x in text.splitlines() if x.startswith('Libs.private:')))\n"
            + "else: raise SystemExit(2)\n")
        self.pkg.chmod(0o700)
        self.args = SimpleNamespace(static_private_archive=self.libdir / build.PRIVATE_ARCHIVE,
            expected_static_private_archive_sha256=build.digest(self.libdir / build.PRIVATE_ARCHIVE),
            toolchain_bin=self.toolchain)
        self.env = dict(build.BASE_ENV, PATH=str(self.bin) + ":" + build.BASE_ENV["PATH"])
        self.output = self.root / "evidence"
        self.output.mkdir()

    def snapshot(self):
        return build.static_private_snapshot(self.args, self.env)

    def test_exact_private_source_is_retained_and_only_the_final_command_changes(self):
        before = self.snapshot()
        frozen = build.freeze_private_archive(before, self.output)
        self.assertEqual(frozen["sha256"], self.args.expected_static_private_archive_sha256)
        self.assertNotEqual(frozen["path"], before["archive"]["path"])
        self.assertEqual(before["tools"]["ld.lld"]["resolved_path"], before["tools"]["rust-lld"]["resolved_path"])
        self.assertFalse(before["linker_execution_observed"])
        default = build.build_command("/selected/cargo", "bin", "hepta-agentd", 2)
        explicit = build.build_command("/selected/cargo", "bin", "hepta-agentd", 2, frozen)
        self.assertEqual(default, ["/selected/cargo", "build", "--manifest-path", "codex-rs/Cargo.toml", "--locked", "--offline",
            "--release", "--target", "x86_64-unknown-linux-gnu", "-p", "codex-hepta-agentd", "--bin", "hepta-agentd", "-j2"])
        self.assertEqual(explicit[:1] + ["build"] + explicit[2:-3], default)
        self.assertEqual(explicit[1], "rustc")
        self.assertEqual(explicit[-3:], ["--", "-C", "link-arg=" + frozen["path"]])
        self.assertNotIn("RUSTFLAGS", self.env)
        build.check_private_unchanged(before, self.snapshot(), frozen)
        second = self.root / "second-evidence"
        second.mkdir()
        other = build.freeze_private_archive(before, second)
        self.assertEqual(other["sha256"], frozen["sha256"])
        self.assertNotEqual(build.build_command("/selected/cargo", "bin", "hepta-agentd", 2, other), explicit)

    def test_missing_pair_wrong_hash_and_same_bytes_outside_original_libdir_fail(self):
        self.args.expected_static_private_archive_sha256 = None
        with self.assertRaisesRegex(ValueError, "together"):
            self.snapshot()
        self.args.expected_static_private_archive_sha256 = "0" * 64
        with self.assertRaisesRegex(ValueError, "explicit SHA256"):
            self.snapshot()
        original = self.libdir / build.PRIVATE_ARCHIVE
        outside = self.root / build.PRIVATE_ARCHIVE
        outside.write_bytes(original.read_bytes())
        self.args.static_private_archive = outside
        self.args.expected_static_private_archive_sha256 = build.digest(outside)
        with self.assertRaisesRegex(ValueError, "original OpenSSL pkg-config library directory"):
            self.snapshot()

    def test_missing_or_additional_colon_dependency_is_not_an_arbitrary_linker_escape(self):
        for field in ("-lz -lzstd -ldl -pthread", "-l:libjitterentropy.a -l:unreviewed.a"):
            (self.pcdir / "libcrypto.pc").write_text("Version: 3.5.5\nLibs.private: " + field + "\n")
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "actual static pkg-config output"):
                self.snapshot()

    def test_symlink_and_thin_archive_are_refused_before_linking(self):
        archive = self.args.static_private_archive
        data = archive.read_bytes()
        target = self.root / "alias.a"
        target.write_bytes(data)
        archive.unlink()
        archive.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "canonical unlinked"):
            self.snapshot()
        archive.unlink()
        archive.write_bytes(b"!<thin>\n")
        self.args.expected_static_private_archive_sha256 = build.digest(archive)
        with self.assertRaisesRegex(ValueError, "thin archives refused"):
            self.snapshot()

    def test_changed_pc_library_tool_and_frozen_copy_cannot_pass_postcheck(self):
        before = self.snapshot()
        frozen = build.freeze_private_archive(before, self.output)
        for path in (self.pcdir / "openssl.pc", self.libdir / "libcrypto.a", self.pkg):
            original = path.read_bytes()
            with path.open("ab") as stream:
                stream.write(b"\n# actual fixture input mutation\n")
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "closure changed"):
                build.check_private_unchanged(before, self.snapshot(), frozen)
            path.write_bytes(original)
            # Restoring bytes is deliberately not restoration of the observed
            # inode timestamp. Acquire a new before snapshot for each case.
            before = self.snapshot()
        copied = Path(frozen["path"])
        copied.chmod(0o600)
        copied.write_bytes(copied.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "frozen final-link archive"):
            build.check_private_unchanged(before, self.snapshot(), frozen)

    def test_original_archive_swap_before_freezing_is_rejected(self):
        before = self.snapshot()
        with self.args.static_private_archive.open("ab") as stream:
            stream.write(b"changed after initial verification")
        with self.assertRaisesRegex(ValueError, "changed before freezing"):
            build.freeze_private_archive(before, self.output)

    def test_no_explicit_archive_retains_the_default_profile(self):
        self.args.static_private_archive = None
        self.args.expected_static_private_archive_sha256 = None
        self.assertIsNone(self.snapshot())


if __name__ == "__main__":
    unittest.main()
