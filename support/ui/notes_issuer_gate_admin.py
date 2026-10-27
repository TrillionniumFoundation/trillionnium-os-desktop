"""Run only the held actual Root CLI, once per step, within ONE gate budget."""
import hashlib
import os
from pathlib import Path
import selectors
import stat
import subprocess
import time

from notes_fault_contract import digest, exact_json, fields, require
from notes_issuer_gate_contract import octets
import notes_issuer_gate_receipts as receipts


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def private_parent(path):
    require(path.is_absolute() and path.resolve(strict=True) == path, "admin_canonical_parent")
    for node in (path, *path.parents):
        info = node.stat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
                "admin_root_ancestor_custody")
    require(stat.S_IMODE(path.stat().st_mode) == 0o700, "admin_private_parent")


class RootFile:
    def __init__(self, path, bound, *, private=False, expected_sha=None):
        self.path = Path(path)
        require(self.path.is_absolute() and self.path.resolve(strict=True) == self.path, "admin_file_path")
        self.fd = os.open(self.path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            self.info = os.fstat(self.fd)
            require(stat.S_ISREG(self.info.st_mode) and self.info.st_uid == 0
                    and self.info.st_nlink == 1 and 0 < self.info.st_size <= bound
                    and not self.info.st_mode & 0o022, "admin_file_custody")
            if private:
                require(stat.S_IMODE(self.info.st_mode) == 0o600, "admin_file_not_private")
                private_parent(self.path.parent)
            self.raw = os.pread(self.fd, self.info.st_size + 1, 0)
            require(len(self.raw) == self.info.st_size, "admin_file_size_changed")
            self.sha256 = digest(self.raw)
            if expected_sha is not None:
                require(self.sha256 == expected_sha and self.raw[:4] == b"\x7fELF"
                        and self.info.st_mode & 0o111, "admin_cli_elf_hash")
            self.verify()
        except BaseException:
            self.close()
            raise

    def verify(self):
        require(identity(os.fstat(self.fd)) == identity(self.info)
                and identity(self.path.stat()) == identity(self.info), "admin_file_replaced_or_changed")

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def write_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:])
            require(count > 0, "gate_artifact_write")
            offset += count
        os.fsync(fd)
    finally:
        os.close(fd)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


class OriginalRootAdmin:
    """A selector/observer, never a Root factory or replacement issuer."""
    def __init__(self, binding, root, output):
        self.root, self.output, self.steps = root, output, []
        self.cli = self.descriptor = None
        self.mutation_attempted = False
        try:
            self.cli = RootFile(binding["cli_executable"], 128*1024*1024, expected_sha=binding["cli_sha256"])
            self.descriptor = RootFile(binding["instance_file"], 16384, private=True)
            value = exact_json(self.descriptor.raw, 16384)
            fields(value, ("schema", "socket", "instance"))
            self.instance = value["instance"]
            fields(self.instance, ("boot_id", "root_pid", "process_start_ticks", "episode_nonce"))
            octets(self.instance["episode_nonce"], 32)
            require(value["schema"] == "trill.original-root-admin.v1"
                    and Path(value["socket"]) == self.descriptor.path.parent / "root-admin.sock"
                    and self.instance["root_pid"] == root.pid
                    and self.instance["process_start_ticks"] == root.identity["start_ticks"]
                    and self.instance["boot_id"] == binding["boot_id"], "original_admin_instance")
            self.verify()
        except BaseException:
            self.close()
            raise

    def verify(self):
        self.root.verify(tracer=os.getpid())
        require(identity(self.cli.info) == identity(self.root.executable)
                and self.cli.sha256 == self.root.sha256, "admin_cli_not_held_root_image")
        self.cli.verify(); self.descriptor.verify()

    def call(self, label, args, end, cancelled):
        self.verify()
        require(not cancelled() and time.monotonic() < end, "gate_admin_deadline")
        # Execute precisely the held ELF, rather than a PATH or a replacement path.
        process = subprocess.Popen([f"/proc/self/fd/{self.cli.fd}", "admin", "--instance-file",
                                    str(self.descriptor.path), *args], pass_fds=(self.cli.fd,),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env={"LANG":"C.UTF-8", "PATH":"/usr/bin:/bin"}, close_fds=True)
        selector = None
        raw, error = bytearray(), bytearray()
        try:
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ, raw)
            selector.register(process.stderr, selectors.EVENT_READ, error)
            while selector.get_map():
                require(not cancelled() and time.monotonic() < end, "gate_admin_deadline")
                for key, _ in selector.select(min(0.005, max(0, end-time.monotonic()))):
                    chunk = os.read(key.fileobj.fileno(), 4096)
                    if not chunk: selector.unregister(key.fileobj)
                    else:
                        key.data.extend(chunk)
                        require(len(raw) <= 65536 and len(error) <= 4096, "admin_cli_output_bound")
            code = process.wait(timeout=max(0.000001, end-time.monotonic()))
            require(time.monotonic() < end, "gate_admin_deadline")
        finally:
            try:
                if selector is not None: selector.close()
            finally:
                try:
                    if process.poll() is None: process.kill()  # Only this tool's own CLI child.
                    process.wait(timeout=1)
                finally:
                    process.stdout.close(); process.stderr.close()
                    self.steps.append({"step":label, "pid":process.pid, "exit":process.returncode,
                                       "stdout_sha256":digest(raw), "stderr_sha256":digest(error),
                                       "finished_monotonic":time.monotonic()})
                    write_new(self.output / (label+".json"), bytes(raw))
                    # No arbitrary error text, model content, argv or environment in receipts.
        self.verify()
        require(code == 0, "original_admin_cli_refused_or_unknown")
        return exact_json(bytes(raw), 65536)

    def revoke_held_original(self, capture, reason, end, cancelled):
        write_new(self.output / "original-signed-grant.json", capture["signed_raw"])
        artifact = str(self.output / "original-signed-grant.json")
        grant_id = capture["signed"]["grant"]["grant_id"]
        value = self.call("01-original-mirror", ["observe-grant", "--grant-id", grant_id], end, cancelled)
        receipts.mirror(value, capture, self.instance)
        before = self.call("02-original-state", ["observe-grant-state", "--signed-grant-file", artifact], end, cancelled)
        receipts.before_revoke(before, capture, self.instance)
        require(time.monotonic() < end and not cancelled(), "gate_admin_deadline")
        self.mutation_attempted = True  # No code path can retry this CAS.
        mutation = self.call("03-exact-revoke", ["revoke-grant", "--signed-grant-file", artifact,
            "--expected-effect-lease-revision", str(before["effect_lease"]["lease"]["revision"]),
            "--expected-issuer-head-revision", str(before["final_use_head"]["revision"]),
            "--reason-sha256", reason], end, cancelled)
        receipts.revoked(mutation, capture, self.instance, before, reason)
        after = self.call("04-original-recheck", ["observe-grant-state", "--signed-grant-file", artifact], end, cancelled)
        receipts.after_revoke(after, capture, self.instance, before, mutation)
        require(time.monotonic() < end and not cancelled(), "gate_admin_deadline")
        return {"original_instance":self.instance, "original_grant_id":grant_id,
                "final_use_head":mutation["final_use_head"], "synchronization":after["synchronization"],
                "effect_lease_receipt":mutation["effect_lease_receipt"], "steps":self.steps,
                "consumer_first_use_revoked_proven":False}

    def close(self):
        for file in (self.descriptor, self.cli):
            if file is not None: file.close()
