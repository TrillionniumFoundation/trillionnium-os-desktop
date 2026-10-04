"""Fixed supplier policy and sealed verifier inputs; diagnostic workflow custody.

No caller proof object is accepted. The official tool verifies signatures; this
module binds its actual output to the same retained archive, bundle and tool.
Python custody is not a hostile-code sandbox or a production trust capability.
"""
from __future__ import annotations

import base64
import argparse
import ctypes
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import selectors
import stat
import subprocess
import sys
import tempfile
import threading
import time

try:
    from . import mozjs_secondary_input as archive
    from . import build_mozjs_locked_native as original
    from .artifact_evidence import open_managed_file
    from .browser_codec_reference_security import load_json_strict
except ImportError:
    import mozjs_secondary_input as archive
    import build_mozjs_locked_native as original
    from artifact_evidence import open_managed_file
    from browser_codec_reference_security import load_json_strict

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "manifests/mozjs-authenticated-input.v2.json"
MAX_POLICY_BYTES = 16384
MAX_BUNDLE_BYTES = 65536
MAX_TOOL_BYTES = 67108864
MAX_OUTPUT_BYTES = 262144
MAX_CARGO_OUTPUT_BYTES = 16777216
VERIFY_TIMEOUT_SECONDS = 60
VERIFY_GRACE_SECONDS = 2
COMMIT = "95cacf65a191aaf82f47fad5eebdd5a9cf827aa7"
IDENTITY = "https://github.com/servo/mozjs/.github/workflows/publish.yml@refs/heads/main"
ISSUER = "https://token.actions.githubusercontent.com"
PREDICATE = "https://slsa.dev/provenance/v1"
TOKEN_SUBJECT = "repo:servo/mozjs:ref:refs/heads/main"
CERTIFICATE_FIELDS = {
    "certificateIssuer": "CN=sigstore-intermediate,O=sigstore.dev",
    "subjectAlternativeName": IDENTITY, "issuer": ISSUER,
    "githubWorkflowTrigger": "push", "githubWorkflowSHA": COMMIT,
    "githubWorkflowName": "Publish", "githubWorkflowRepository": "servo/mozjs",
    "githubWorkflowRef": "refs/heads/main", "buildSignerURI": IDENTITY,
    "buildSignerDigest": COMMIT, "runnerEnvironment": "github-hosted",
    "sourceRepositoryURI": "https://github.com/servo/mozjs",
    "sourceRepositoryDigest": COMMIT, "sourceRepositoryRef": "refs/heads/main",
    "sourceRepositoryIdentifier": "4239178", "sourceRepositoryOwnerURI": "https://github.com/servo",
    "sourceRepositoryOwnerIdentifier": "2566135", "buildConfigURI": IDENTITY,
    "buildConfigDigest": COMMIT, "buildTrigger": "push",
    "runInvocationURI": "https://github.com/servo/mozjs/actions/runs/32706570219/attempts/1",
    "sourceRepositoryVisibilityAtSigning": "public",
}
POLICY = {
    "schema": "trillionnium.mozjs-authenticated-input.v2",
    "status": "SOURCE_CANDIDATE_NOT_QUALIFIED",
    "archive": {"v1_manifest": archive.MANIFEST, "bytes": 19381534,
                "sha256": "c5f93d7f9f1b450e2a608b5e7378c95ec8fa9f3689bdfe1f6ad548e434c3107b",
                "name": "libmozjs-x86_64-unknown-linux-gnu.tar.gz", "asset_id": 527403045},
    "bundle": {"index": 1, "bytes": 14373,
               "sha256": "7077565ec6de92705ae4f742ed68f59cb88e5132a50153f578496cea023a2e88",
               "media_type": "application/vnd.dev.sigstore.bundle.v0.3+json",
               "delivery": "same bytes copied from held sealed FD to private readonly tmpfs; distinct consuming inode",
               "original_memfd_inode_consumption_proven": False},
    "tool": {"version": "2.102.0", "bytes": 42086560,
             "sha256": "7469124f706944133d6a169691dd1c6c3511b12e85878d255e044e2948df4c9b",
             "bootstrap": "official HTTPS API/checksums/tar member; tool attestation not independently verified",
             "tool_artifact_attestation_verified": False},
    "certificate": CERTIFICATE_FIELDS,
    "der": {"bytes": 1716, "sha256": "9638f394598817acc8b609393a55efae1a094d40f8074edf59dc842c40dc491c",
            "token_subject_oid": "1.3.6.1.4.1.57264.1.24", "token_subject": TOKEN_SUBJECT,
            "not_before": "2026-08-24T09:46:29+00:00", "not_after": "2026-08-24T09:56:29+00:00"},
    "time": {"verified_utc": "2026-08-24T09:46:29+00:00",
             "run_start": "2026-08-24T08:29:23+00:00", "run_end": "2026-08-24T10:22:14+00:00"},
    "limits": {"archive": archive.MAX_ARCHIVE_BYTES, "bundle": MAX_BUNDLE_BYTES,
               "tool": MAX_TOOL_BYTES, "policy": MAX_POLICY_BYTES, "each_output": MAX_OUTPUT_BYTES,
               "each_cargo_output": MAX_CARGO_OUTPUT_BYTES,
               "verifier_seconds": VERIFY_TIMEOUT_SECONDS, "verifier_grace_seconds": VERIFY_GRACE_SECONDS,
               "cache_entries": 128, "cache_files": 64, "cache_file_bytes": 1048576, "cache_total_bytes": 8388608},
    "build": {"profile": "checked-release", "toolchain": "1.97.1", "features": "bundled,js_jit",
              "locked": True, "default_features": False, "timeout_seconds": 10800, "grace_seconds": 5,
              "targets": original.TARGETS, "actual_archive_consumption_proven": False},
    "claims": {"caller_success_tokens_accepted": False, "default_ci_changed": False,
               "source_qualified": False, "native_six_pass": False, "installed_qualified": False,
               "human_approval": False, "production_ready": False},
}


class _FixedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print("MOZJS_AUTHENTICATED_INPUT_REFUSED", file=sys.stderr)
        raise SystemExit(2)


def check_manifest(value: object) -> None:
    if json.dumps(value, sort_keys=True, allow_nan=False) != json.dumps(POLICY, sort_keys=True):
        raise ValueError("authenticated input policy differs")


def _read_regular(path: Path, maximum: int) -> bytes:
    with open_managed_file(path.absolute()) as reader:
        before = reader.stat()
        if before.st_size > maximum: raise ValueError("bounded input exceeded")
        raw = reader.read(maximum + 1)
        after = reader.stat()
        if len(raw) != before.st_size or archive._identity(before) != archive._identity(after):
            raise ValueError("bounded input changed")
        if archive._identity(before) != archive._identity(path.absolute().lstat()):
            raise ValueError("bounded input name changed")
        return raw


def load_manifest() -> dict:
    value = load_json_strict(_read_regular(ROOT / MANIFEST, MAX_POLICY_BYTES))
    check_manifest(value)
    archive.load_manifest()
    return value


def _seal_input(path: Path, size: int, digest: str, maximum: int, executable: bool = False) -> archive.SealedArchiveLease:
    """Private host primitive; the public entry obtains all expectations from policy."""
    if type(size) is not int or not 0 < size <= maximum or type(digest) is not str or len(digest) != 64:
        raise ValueError("sealed input bounds differ")
    if type(executable) is not bool: raise ValueError("sealed input mode differs")
    value = archive.SealedArchiveLease()
    try:
        value._owner.fd = os.memfd_create("mozjs-authenticated-input", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        value._original = os.fstat(value._owner.fd)
        value._expected_size, value._expected_sha256 = size, digest
        actual = hashlib.sha256(); total = 0
        with open_managed_file(path.absolute()) as reader:
            before = reader.stat()
            if before.st_size != size: raise ValueError("sealed input size differs")
            while total < size:
                raw = reader.read_some(min(archive.CHUNK_BYTES, size - total))
                if not raw: raise ValueError("sealed input short read")
                total += len(raw); actual.update(raw); offset = 0
                while offset < len(raw):
                    written = os.write(value._owner.fd, raw[offset:])
                    if written <= 0: raise ValueError("sealed input short write")
                    offset += written
            if reader.read_some(1): raise ValueError("sealed input grew")
            after = reader.stat()
            if archive._identity(before) != archive._identity(after) or archive._identity(before) != archive._identity(path.absolute().lstat()):
                raise ValueError("sealed input source changed")
        if total != size or actual.hexdigest() != digest: raise ValueError("sealed input digest differs")
        os.fchmod(value._owner.fd, 0o500 if executable else 0o400)
        fcntl.fcntl(value._owner.fd, fcntl.F_ADD_SEALS, archive.SEALS)
        value._original = os.fstat(value._owner.fd)
        value.readback()
        return value
    except BaseException:
        value._release()
        raise


class _InputSet:
    def __init__(self) -> None:
        self._pid = os.getpid(); self._thread = threading.current_thread()
        self._active = False; self._leases: dict[str, archive.SealedArchiveLease] = {}

    def _creator(self) -> None:
        if os.getpid() != self._pid or threading.current_thread() is not self._thread or self._active:
            raise ValueError("authenticated input creator or lifetime differs")

    def readback(self) -> dict:
        self._creator(); self._active = True
        try:
            if set(self._leases) != {"archive", "bundle", "tool"}: raise ValueError("authenticated inputs incomplete")
            return {name: lease.readback() for name, lease in self._leases.items()}
        finally: self._active = False

    def paths(self) -> dict[str, str]:
        self._creator(); self._active = True
        try:
            if set(self._leases) != {"archive", "bundle", "tool"}: raise ValueError("authenticated inputs incomplete")
            return {name: lease.stable_path() for name, lease in self._leases.items()}
        finally: self._active = False

    def close(self) -> None:
        self._creator(); self._active = True
        try:
            for lease in self._leases.values(): lease.close()
        finally: self._active = False


def _admit_inputs(archive_path: Path, bundle_path: Path, tool_path: Path) -> _InputSet:
    policy = load_manifest(); held = _InputSet()
    try:
        held._leases["archive"] = archive.lease_archive(archive_path)
        for name, path, limit in [("bundle", bundle_path, MAX_BUNDLE_BYTES), ("tool", tool_path, MAX_TOOL_BYTES)]:
            spec = policy[name]
            held._leases[name] = _seal_input(path, spec["bytes"], spec["sha256"], limit, name == "tool")
        held.readback()
        return held
    except BaseException:
        held.close()
        raise


def _argv(paths: dict[str, str]) -> list[str]:
    return [paths["tool"], "attestation", "verify", paths["archive"], "--hostname", "github.com",
            "--repo", "servo/mozjs", "--bundle", paths["bundle"], "--cert-identity", IDENTITY,
            "--cert-oidc-issuer", ISSUER, "--signer-digest", COMMIT, "--source-digest", COMMIT,
            "--source-ref", "refs/heads/main", "--predicate-type", PREDICATE,
            "--deny-self-hosted-runners", "--format", "json"]


def _new_directory(parent: Path, prefix: str) -> Path:
    parent = parent.absolute()
    for path in [parent, *parent.parents]:
        if path.is_symlink(): raise ValueError("private parent has a symlink component")
    if not parent.is_dir(): raise ValueError("private parent is absent")
    path = Path(tempfile.mkdtemp(prefix=prefix, dir=parent)); path.chmod(0o700)
    if list(path.iterdir()): raise ValueError("private directory was not initially empty")
    return path


def _verifier_environment(evidence: Path) -> dict[str, str]:
    # The verifier accepts no inherited auth, config, trust-root or debugging
    # selectors. Its default authenticated TUF roots are fetched normally.
    home = evidence / "home"; cache = evidence / "default-tuf-cache"; config = evidence / "gh-config"
    for path in [home, cache, config]: path.mkdir(mode=0o700)
    return {"PATH": "/usr/bin:/bin", "HOME": str(home), "XDG_CACHE_HOME": str(cache),
            "GH_CONFIG_DIR": str(config), "GH_PROMPT_DISABLED": "1", "LANG": "C.UTF-8"}


class _VerifierProcess(original._BuildProcess):
    def start(self, argv: list[str], cwd: Path, environment: dict[str, str]) -> None:
        subprocess.Popen.__init__(self.process, argv, executable=argv[0], cwd=cwd, env=environment,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  start_new_session=True, close_fds=True,
                                  pass_fds=getattr(self, "_inherited", ()))
        self.started = True


def _run_verifier(held: _InputSet, argv: list[str], evidence: Path, environment: dict[str, str],
                  timeout: float = VERIFY_TIMEOUT_SECONDS, grace: float = VERIFY_GRACE_SECONDS,
                  *, tool_execution: bool = False, output_limit: int = MAX_OUTPUT_BYTES,
                  inherit_fds: tuple[int, ...] = (), cwd: Path | None = None) -> tuple[int, bytes, bytes]:
    """Private process primitive, also exercised with ordinary host subprocesses."""
    if not 0 < grace < timeout / 2: raise ValueError("verifier process bounds differ")
    if type(output_limit) is not int or not 0 < output_limit <= MAX_CARGO_OUTPUT_BYTES:
        raise ValueError("process output bounds differ")
    execution_cwd = evidence if cwd is None else cwd
    if not isinstance(execution_cwd, Path) or not execution_cwd.is_absolute():
        raise ValueError("process working directory differs")
    held.readback(); owner = _VerifierProcess(held); deadline = time.monotonic() + timeout
    owner._inherited = inherit_fds
    outputs = {"stdout": bytearray(), "stderr": bytearray()}; result = None
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tool_observation = {"requested": tool_execution, "proc_exe_identity_and_bytes_observed": False}
    try:
        held._active = True; owner.start(argv, execution_cwd, environment)
        if tool_execution:
            # Popen exec-error handshake has completed. Observe the actual
            # executable object too, when the child is still live. A vanished
            # proc entry is explicit unknown and cannot qualify successful use.
            lease = held._leases["tool"]; borrowed = archive._SourceDescriptor()
            try:
                while time.monotonic() < deadline - 2 * grace:
                    try: borrowed.fd = os.open(f"/proc/{owner.process.pid}/exe", os.O_RDONLY | os.O_CLOEXEC)
                    except (FileNotFoundError, PermissionError): pass
                    if borrowed.fd is not None:
                        current = os.fstat(borrowed.fd)
                        if archive._sealed_identity(current) == archive._sealed_identity(lease._original): break
                        borrowed.close()
                    if owner.process.poll() is not None: break
                    time.sleep(.01)
                if borrowed.fd is not None:
                    before = os.fstat(borrowed.fd)
                    digest = hashlib.sha256(); offset = 0
                    while offset < lease._expected_size:
                        raw = os.pread(borrowed.fd, min(archive.CHUNK_BYTES, lease._expected_size - offset), offset)
                        if not raw: raise ValueError("actual tool executable short read")
                        digest.update(raw); offset += len(raw)
                    if os.pread(borrowed.fd, 1, offset) or digest.hexdigest() != lease._expected_sha256:
                        raise ValueError("actual tool executable bytes differ")
                    if archive._sealed_identity(os.fstat(borrowed.fd)) != archive._sealed_identity(before):
                        raise ValueError("actual tool executable changed")
                    tool_observation.update(proc_exe_identity_and_bytes_observed=True,
                                            bytes=offset, sha256=digest.hexdigest(),
                                            device=before.st_dev, inode=before.st_ino)
                    status_owner = archive._SourceDescriptor()
                    try:
                        status_owner.fd = os.open(f"/proc/{owner.process.pid}/status", os.O_RDONLY | os.O_CLOEXEC)
                        status_raw = os.read(status_owner.fd, 32769)
                        if len(status_raw) > 32768: raise ValueError("actual tool status bound exceeded")
                        status = dict(line.split(":", 1) for line in status_raw.decode("ascii", "strict").splitlines() if ":" in line)
                        capability_fields = {name: int(status[name].strip(), 16) for name in ("CapEff", "CapPrm", "CapInh", "CapAmb", "CapBnd")}
                        if any(capability_fields.values()) or status["NoNewPrivs"].strip() != "1":
                            raise ValueError("actual tool namespace privilege retirement differs")
                        (evidence / "actual-gh-status.raw").write_bytes(status_raw)
                        tool_observation.update(actual_capabilities=capability_fields, actual_no_new_privileges=True,
                                                status_sha256=hashlib.sha256(status_raw).hexdigest(),
                                                actual_namespace={name: os.stat(f"/proc/{owner.process.pid}/ns/{name}").st_ino for name in ("user", "mnt")})
                    finally: status_owner.close()
            finally: borrowed.close()
        with selectors.DefaultSelector() as selected:
            for name in outputs:
                stream = getattr(owner.process, name)
                os.set_blocking(stream.fileno(), False)
                selected.register(stream, selectors.EVENT_READ, name)
            drain_deadline = None
            while selected.get_map():
                remaining = deadline - 2 * grace - time.monotonic()
                if remaining <= 0: raise subprocess.TimeoutExpired(argv, timeout)
                if owner.process.poll() is not None:
                    if drain_deadline is None: drain_deadline = time.monotonic() + .2
                    if time.monotonic() >= drain_deadline: break
                for key, _ in selected.select(min(remaining, 0.1)):
                    raw = os.read(key.fileobj.fileno(), 65536)
                    if not raw: selected.unregister(key.fileobj)
                    else:
                        outputs[key.data].extend(raw)
                        if len(outputs[key.data]) > output_limit: raise ValueError("process output bound exceeded")
            result = owner.process.wait(timeout=max(0.001, deadline - 2 * grace - time.monotonic()))
    finally:
        try:
            owner.stop(min(deadline, time.monotonic() + 2 * grace), grace)
        finally:
            if owner.stopped:
                held._active = False
            else:
                original._PENDING_SHUTDOWNS.append(owner)
            for name in outputs:
                stream = getattr(owner.process, name, None)
                if stream is not None: stream.close()
            for name, raw in outputs.items():
                # Retain bounded raw diagnostic bytes privately; CLI failures
                # print only fixed categories, never these payloads.
                (evidence / (name + ".raw")).write_bytes(bytes(raw[:output_limit]))
            observation = {"schema": "trillionnium.bounded-input-process-observation.v2",
                           "started_utc": started, "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                           "argv": argv, "pid": getattr(owner.process, "pid", None),
                           "working_directory": str(execution_cwd),
                           "actual_returncode": result, "leader_returncode_observed": getattr(owner.process, "returncode", None),
                           "ordinary_group_ended": owner.stopped, "input_custody_retained_on_unresolved": not owner.stopped,
                           "tool_execution": tool_observation, "timeout_seconds": timeout,
                           "termination_grace_seconds": grace, "each_output_limit_bytes": output_limit}
            (evidence / "actual-process.json").write_text(json.dumps(observation, indent=2) + "\n")
    return result, bytes(outputs["stdout"]), bytes(outputs["stderr"])


def _der_items(raw: bytes) -> list[tuple[int, bytes]]:
    """Finite canonical DER TLVs, used only for the fixed authenticated cert."""
    result = []; position = 0
    if len(raw) > 4096: raise ValueError("certificate DER bound exceeded")
    while position < len(raw):
        if len(result) >= 64 or position + 2 > len(raw): raise ValueError("certificate DER structure differs")
        tag, length = raw[position], raw[position + 1]; position += 2
        if tag & 31 == 31: raise ValueError("certificate DER tag differs")
        if length & 128:
            width = length & 127
            if not 1 <= width <= 2 or position + width > len(raw) or raw[position] == 0:
                raise ValueError("certificate DER length differs")
            length = int.from_bytes(raw[position:position + width], "big"); position += width
            if length < 128: raise ValueError("certificate DER noncanonical length")
        if position + length > len(raw): raise ValueError("certificate DER truncated")
        result.append((tag, raw[position:position + length])); position += length
    return result


def _der_certificate(der: bytes) -> tuple[str, datetime.datetime, datetime.datetime]:
    if len(der) != POLICY["der"]["bytes"] or hashlib.sha256(der).hexdigest() != POLICY["der"]["sha256"]:
        raise ValueError("authenticated certificate DER differs")
    top = _der_items(der)
    if len(top) != 1 or top[0][0] != 48: raise ValueError("certificate sequence differs")
    certificate = _der_items(top[0][1])
    if len(certificate) != 3 or certificate[0][0] != 48: raise ValueError("certificate body differs")
    tbs = _der_items(certificate[0][1])
    if len(tbs) != 8 or tbs[0][0] != 160 or tbs[4][0] != 48 or tbs[7][0] != 163:
        raise ValueError("certificate fields differ")
    validity = _der_items(tbs[4][1])
    if len(validity) != 2 or any(tag != 23 for tag, _ in validity): raise ValueError("certificate validity differs")
    times = []
    for _, raw in validity:
        text = raw.decode("ascii", "strict")
        if len(text) != 13 or not text.endswith("Z") or not text[:-1].isdigit(): raise ValueError("certificate time differs")
        times.append(datetime.datetime.strptime(text, "%y%m%d%H%M%SZ").replace(tzinfo=datetime.timezone.utc))
    wrapper = _der_items(tbs[7][1])
    if len(wrapper) != 1 or wrapper[0][0] != 48: raise ValueError("certificate extensions differ")
    token_oid = bytes.fromhex("2b0601040183bf300118"); tokens = []
    for tag, raw in _der_items(wrapper[0][1]):
        if tag != 48: raise ValueError("certificate extension differs")
        fields = _der_items(raw)
        if len(fields) not in (2, 3) or fields[0][0] != 6 or fields[-1][0] != 4:
            raise ValueError("certificate extension fields differ")
        if fields[0][1] == token_oid:
            if len(fields) != 2: raise ValueError("token subject critical policy differs")
            value = _der_items(fields[-1][1])
            if len(value) != 1 or value[0][0] != 12: raise ValueError("token subject encoding differs")
            tokens.append(value[0][1].decode("utf-8", "strict"))
    if tokens != [TOKEN_SUBJECT]: raise ValueError("authenticated token subject differs")
    return tokens[0], times[0], times[1]


def _bounded_json(raw: bytes, maximum: int) -> object:
    if type(raw) is not bytes or len(raw) > maximum: raise ValueError("JSON byte bound exceeded")
    value = load_json_strict(raw)
    pending = [(value, 0)]; count = 0
    while pending:
        current, depth = pending.pop(); count += 1
        if depth > 20 or count > 4096: raise ValueError("JSON structure bound exceeded")
        if type(current) is dict: pending.extend((child, depth + 1) for child in current.values())
        elif type(current) is list: pending.extend((child, depth + 1) for child in current)
    return value


def _fd_fact(fd: int, size: int, digest: str) -> dict:
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or before.st_size != size or fcntl.fcntl(fd, fcntl.F_GET_SEALS) != archive.SEALS:
        raise ValueError("inherited sealed input differs")
    actual = hashlib.sha256(); position = 0
    while position < size:
        raw = os.pread(fd, min(archive.CHUNK_BYTES, size - position), position)
        if not raw: raise ValueError("inherited sealed input short read")
        actual.update(raw); position += len(raw)
    if os.pread(fd, 1, size) or actual.hexdigest() != digest or archive._sealed_identity(before) != archive._sealed_identity(os.fstat(fd)):
        raise ValueError("inherited sealed input readback differs")
    return {"device": before.st_dev, "inode": before.st_ino, "mode": stat.S_IMODE(before.st_mode),
            "uid": before.st_uid, "gid": before.st_gid, "bytes": position, "sha256": actual.hexdigest(), "four_seals": archive.SEALS}


def _namespace_snapshot(source_fd: int, evidence: Path, size: int, digest: str) -> tuple[int, dict]:
    """Private Linux host primitive; public worker uses only fixed bundle policy.

    The named consuming snapshot is a different inode. Original memfd bind is
    unavailable here; there is no mutable alias or automatic fallback.
    """
    if type(size) is not int or not 0 < size <= MAX_BUNDLE_BYTES: raise ValueError("namespace bundle bound differs")
    original_fact = _fd_fact(source_fd, size, digest)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.unshare.argtypes = [ctypes.c_int]; libc.unshare.restype = ctypes.c_int
    libc.mount.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulong, ctypes.c_void_p]
    libc.mount.restype = ctypes.c_int
    def checked(result):
        if result != 0: raise OSError(ctypes.get_errno(), "private namespace operation refused")
    uid, gid = os.getuid(), os.getgid()
    previous_ns = {name: os.stat("/proc/self/ns/" + name).st_ino for name in ("user", "mnt")}
    checked(libc.unshare(0x10000000 | 0x00020000))
    Path("/proc/self/setgroups").write_text("deny")
    Path("/proc/self/uid_map").write_text(f"0 {uid} 1\n")
    Path("/proc/self/gid_map").write_text(f"0 {gid} 1\n")
    checked(libc.mount(None, b"/", None, 16384 | 262144, None))
    parent = archive._SourceDescriptor(); destination = archive._SourceDescriptor(); writer = archive._SourceDescriptor()
    try:
        parent.fd = os.open(evidence, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        os.mkdir("bundle-view", mode=0o700, dir_fd=parent.fd)
        mountpoint = f"/proc/self/fd/{parent.fd}/bundle-view"
        checked(libc.mount(b"tmpfs", mountpoint.encode(), b"tmpfs", 2 | 4 | 8, b"size=65536,mode=0700"))
        destination.fd = os.open(mountpoint, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        writer.fd = os.open("bundle.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                            0o600, dir_fd=destination.fd)
        actual = hashlib.sha256(); position = 0
        while position < size:
            raw = os.pread(source_fd, min(archive.CHUNK_BYTES, size - position), position)
            if not raw: raise ValueError("namespace bundle short read")
            actual.update(raw); position += len(raw); written = 0
            while written < len(raw):
                count = os.write(writer.fd, raw[written:])
                if count <= 0: raise ValueError("namespace bundle short write")
                written += count
        if os.pread(source_fd, 1, size) or actual.hexdigest() != digest: raise ValueError("namespace bundle copy differs")
        os.fchmod(writer.fd, 0o400); os.fsync(writer.fd); writer.close()
        checked(libc.mount(None, mountpoint.encode(), None, 32 | 1 | 2 | 4 | 8, None))
        reader = archive._SourceDescriptor()
        try:
            reader.fd = os.open("bundle.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=destination.fd)
            snapshot = os.fstat(reader.fd); raw = os.pread(reader.fd, size + 1, 0)
            if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest: raise ValueError("readonly snapshot bytes differ")
            if (snapshot.st_dev, snapshot.st_ino) == (original_fact["device"], original_fact["inode"]):
                raise ValueError("readonly snapshot object domain differs")
            attempted = archive._SourceDescriptor(); refused = None
            try:
                try: attempted.fd = os.open("bundle.json", os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=destination.fd)
                except OSError as error: refused = error.errno
            finally: attempted.close()
            if refused != 30 or not os.fstatvfs(reader.fd).f_flag & os.ST_RDONLY:
                raise ValueError("readonly snapshot write policy differs")
        finally: reader.close()
        after = _fd_fact(source_fd, size, digest)
        if any(after[key] != original_fact[key] for key in ("device", "inode", "mode", "bytes", "sha256", "four_seals")):
            raise ValueError("original bundle changed through namespace mapping")
        fact = {"original_sealed_bundle_before_mapping": original_fact, "original_sealed_bundle_after_mapping": after,
                "snapshot": {"device": snapshot.st_dev, "inode": snapshot.st_ino, "bytes": size, "sha256": digest,
                             "mode": stat.S_IMODE(snapshot.st_mode), "readonly_mount": True, "write_errno": refused,
                             "same_original_memfd_inode": False, "four_seals_on_consuming_inode_claimed": False},
                "host_uid": uid, "host_gid": gid, "namespace_uid": os.getuid(), "namespace_gid": os.getgid(),
                "uid_map": Path("/proc/self/uid_map").read_text(), "gid_map": Path("/proc/self/gid_map").read_text(),
                "namespace_before": previous_ns, "namespace_after": {name: os.stat("/proc/self/ns/" + name).st_ino for name in ("user", "mnt")},
                "mount_propagation_private": True}
        os.set_inheritable(destination.fd, True)
        descriptor, destination.fd = destination.fd, None
        return descriptor, fact
    finally:
        writer.close(); destination.close(); parent.close()


def _drop_namespace_privilege() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    raw = Path("/proc/sys/kernel/cap_last_cap").read_bytes()
    if len(raw) > 8 or not raw.strip().isdigit(): raise ValueError("kernel capability inventory differs")
    last = int(raw)
    if not 0 <= last <= 63: raise ValueError("kernel capability bound differs")
    for capability in range(last + 1):
        if libc.prctl(24, capability, 0, 0, 0) != 0: raise OSError(ctypes.get_errno(), "namespace bounding drop refused")
    if any(libc.prctl(23, capability, 0, 0, 0) != 0 for capability in range(last + 1)):
        raise ValueError("namespace bounding set remains active")
    if libc.prctl(28, 207, 0, 0, 0) != 0: raise OSError(ctypes.get_errno(), "namespace securebits refused")
    class Header(ctypes.Structure): _fields_ = [("version", ctypes.c_uint), ("pid", ctypes.c_int)]
    class Data(ctypes.Structure): _fields_ = [("effective", ctypes.c_uint), ("permitted", ctypes.c_uint), ("inheritable", ctypes.c_uint)]
    header = Header(0x20080522, 0); data = (Data * 2)()
    if libc.capset(ctypes.byref(header), ctypes.byref(data)) != 0: raise OSError(ctypes.get_errno(), "namespace capability drop refused")
    if libc.prctl(38, 1, 0, 0, 0) != 0: raise OSError(ctypes.get_errno(), "namespace no-new-privileges refused")
    if libc.prctl(4, 1, 0, 0, 0) != 0: raise OSError(ctypes.get_errno(), "namespace supervisor readback refused")


def _readonly_worker(archive_fd: int, bundle_fd: int, tool_fd: int, evidence: Path) -> None:
    policy = load_manifest(); descriptors = {"archive": archive_fd, "bundle": bundle_fd, "tool": tool_fd}
    if len(set(descriptors.values())) != 3 or any(type(fd) is not int or fd < 3 for fd in descriptors.values()):
        raise ValueError("private worker descriptor inventory differs")
    before = {name: _fd_fact(fd, policy[name]["bytes"], policy[name]["sha256"]) for name, fd in descriptors.items()}
    directory = archive._SourceDescriptor()
    try:
        directory.fd, namespace = _namespace_snapshot(bundle_fd, evidence, policy["bundle"]["bytes"], policy["bundle"]["sha256"])
        after = {name: _fd_fact(fd, policy[name]["bytes"], policy[name]["sha256"]) for name, fd in descriptors.items()}
        if any(before[name][key] != after[name][key] for name in before for key in ("device", "inode", "mode", "bytes", "sha256", "four_seals")):
            raise ValueError("private worker inherited inputs changed")
        _drop_namespace_privilege()
        status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
        if any(int(status[name].strip(), 16) for name in ("CapEff", "CapPrm", "CapInh", "CapAmb", "CapBnd")) or status["NoNewPrivs"].strip() != "1":
            raise ValueError("private worker privilege retirement differs")
        paths = {"archive": f"/proc/self/fd/{archive_fd}", "bundle": f"/proc/self/fd/{directory.fd}/bundle.json", "tool": f"/proc/self/fd/{tool_fd}"}
        namespace.update(inherited_inputs_before=before, inherited_inputs_after_mapping=after,
                         retained_directory_fd=directory.fd, child_pid=os.getpid(), cap_effective=0,
                         no_new_privileges=True, actual_fixed_gh_argv=_argv(paths),
                         original_bundle_memfd_inode_consumption_proven=False)
        (evidence / "readonly-namespace.json").write_text(json.dumps(namespace, indent=2) + "\n")
        # Only these three reviewed inputs plus this namespace-owned directory
        # survive exec. The snapshot filename cannot be replaced on readonly fs.
        for fd in descriptors.values(): os.set_inheritable(fd, True)
        os.execve(paths["tool"], _argv(paths), dict(os.environ))
    finally: directory.close()


def _parse_verified(stdout: bytes, bundle_raw: bytes) -> dict:
    """Parser policy only; a caller invocation is never cryptographic authority."""
    output = _bounded_json(stdout, MAX_OUTPUT_BYTES); bundle = _bounded_json(bundle_raw, MAX_BUNDLE_BYTES)
    if type(output) is not list or len(output) != 1 or type(output[0]) is not dict or set(output[0]) != {"attestation", "verificationResult"}:
        raise ValueError("single verified attestation differs")
    item = output[0]; attestation = item["attestation"]; verified = item["verificationResult"]
    if type(attestation) is not dict or set(attestation) != {"bundle", "bundle_url", "initiator"} or attestation["bundle"] != bundle:
        raise ValueError("verified bundle binding differs")
    if any(type(attestation[name]) is not str or len(attestation[name]) > 4096 for name in ("bundle_url", "initiator")):
        raise ValueError("verified attestation diagnostic fields differ")
    if type(bundle) is not dict or bundle.get("mediaType") != POLICY["bundle"]["media_type"]:
        raise ValueError("verified bundle media type differs")
    if type(verified) is not dict or set(verified) != {"mediaType", "signature", "verifiedTimestamps", "verifiedIdentity", "statement"}:
        raise ValueError("verified result fields differ")
    if verified["mediaType"] != "application/vnd.dev.sigstore.verificationresult+json;version=0.1":
        raise ValueError("verified result media type differs")
    signature = verified["signature"]
    if type(signature) is not dict or set(signature) != {"certificate"} or signature["certificate"] != CERTIFICATE_FIELDS:
        raise ValueError("authenticated certificate policy differs")
    expected_display = {"subjectAlternativeName": {"subjectAlternativeName": IDENTITY},
                        "issuer": {"issuer": "", "regexp": ".*"}, "runnerEnvironment": "github-hosted"}
    if verified["verifiedIdentity"] != expected_display: raise ValueError("verified identity display differs")
    payload = base64.b64decode(bundle["dsseEnvelope"]["payload"], validate=True)
    statement = _bounded_json(payload, MAX_BUNDLE_BYTES)
    if statement != verified["statement"] or type(statement) is not dict or set(statement) != {"_type", "subject", "predicateType", "predicate"}:
        raise ValueError("verified signed statement binding differs")
    if statement["_type"] != "https://in-toto.io/Statement/v1" or statement["predicateType"] != PREDICATE:
        raise ValueError("verified statement policy differs")
    subjects = statement["subject"]
    if type(subjects) is not list or not 0 < len(subjects) <= 64: raise ValueError("verified subject inventory differs")
    matches = []
    for subject in subjects:
        if type(subject) is not dict or set(subject) != {"name", "digest"} or type(subject["name"]) is not str or type(subject["digest"]) is not dict:
            raise ValueError("verified subject fields differ")
        if subject["name"] == POLICY["archive"]["name"]: matches.append(subject)
    if matches != [{"name": POLICY["archive"]["name"], "digest": {"sha256": POLICY["archive"]["sha256"]}}]:
        raise ValueError("single verified archive subject differs")
    der = base64.b64decode(bundle["verificationMaterial"]["certificate"]["rawBytes"], validate=True)
    token, before, after = _der_certificate(der)
    timestamps = verified["verifiedTimestamps"]
    if type(timestamps) is not list or len(timestamps) != 1 or type(timestamps[0]) is not dict or set(timestamps[0]) != {"type", "uri", "timestamp"}:
        raise ValueError("authenticated timestamp inventory differs")
    timestamp = timestamps[0]
    if timestamp["type"] != "Tlog" or timestamp["uri"] != "https://rekor.sigstore.dev" or type(timestamp["timestamp"]) is not str:
        raise ValueError("authenticated timestamp authority differs")
    signing = datetime.datetime.fromisoformat(timestamp["timestamp"])
    if signing.utcoffset() is None: raise ValueError("authenticated timestamp lacks timezone")
    signing = signing.astimezone(datetime.timezone.utc)
    fixed = {name: datetime.datetime.fromisoformat(value) for name, value in POLICY["time"].items()}
    if signing != fixed["verified_utc"] or before.isoformat() != POLICY["der"]["not_before"] or after.isoformat() != POLICY["der"]["not_after"]:
        raise ValueError("authenticated historical time differs")
    if not before <= signing <= after or not fixed["run_start"] <= signing <= fixed["run_end"]:
        raise ValueError("authenticated historical time outside bounds")
    return {"archive_subject": matches[0], "authenticated_certificate_fields": signature["certificate"],
            "authenticated_token_subject": token, "verified_signing_time_utc": signing.isoformat(),
            "display_issuer_is_wildcard": True, "current_expiry_bypass": False}


def _cache_readback(cache: Path) -> list[dict]:
    records = []; entries = 0; total = 0; pending = [cache]
    while pending:
        directory = pending.pop()
        if directory.is_symlink(): raise ValueError("default cache symlink refused")
        with os.scandir(directory) as visible:
            for entry in visible:
                entries += 1
                if entries > POLICY["limits"]["cache_entries"]: raise ValueError("default cache entry bound exceeded")
                path = Path(entry.path)
                if entry.is_symlink(): raise ValueError("default cache symlink refused")
                if entry.is_dir(follow_symlinks=False): pending.append(path); continue
                if len(records) >= POLICY["limits"]["cache_files"]: raise ValueError("default cache file bound exceeded")
                raw = _read_regular(path, POLICY["limits"]["cache_file_bytes"]); total += len(raw)
                if total > POLICY["limits"]["cache_total_bytes"]: raise ValueError("default cache total bound exceeded")
                records.append({"path": str(path.relative_to(cache)), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    return sorted(records, key=lambda item: item["path"])


def _authenticate(held: _InputSet, evidence: Path) -> dict:
    before = held.readback(); paths = held.paths(); environment = _verifier_environment(evidence)
    fds = tuple(held._leases[name]._descriptor() for name in ("archive", "bundle", "tool"))
    argv = [sys.executable, str(Path(__file__)), "--private-readonly-verifier-worker", *(str(fd) for fd in fds), str(evidence)]
    rc, stdout, stderr = _run_verifier(held, argv, evidence, environment, tool_execution=True, inherit_fds=fds)
    if rc != 0: raise ValueError("official verification refused")
    process_raw = _read_regular(evidence / "actual-process.json", MAX_POLICY_BYTES)
    process = _bounded_json(process_raw, MAX_POLICY_BYTES)
    if process["tool_execution"]["proc_exe_identity_and_bytes_observed"] is not True:
        raise ValueError("actual tool executable observation unavailable")
    namespace_raw = _read_regular(evidence / "readonly-namespace.json", MAX_POLICY_BYTES)
    namespace = _bounded_json(namespace_raw, MAX_POLICY_BYTES)
    if namespace["child_pid"] != process["pid"] or process["tool_execution"]["actual_namespace"] != namespace["namespace_after"]:
        raise ValueError("actual readonly namespace process binding differs")
    for name, lease in held._leases.items():
        actual = namespace["inherited_inputs_before"][name]; expected = lease._original
        if (actual["device"], actual["inode"], actual["mode"], actual["bytes"], actual["sha256"], actual["four_seals"]) != (expected.st_dev, expected.st_ino, stat.S_IMODE(expected.st_mode), before[name]["bytes"], before[name]["sha256"], archive.SEALS):
            raise ValueError("actual inherited object binding differs")
    snapshot = namespace["snapshot"]
    if snapshot["readonly_mount"] is not True or snapshot["write_errno"] != 30 or snapshot["same_original_memfd_inode"] is not False or snapshot["bytes"] != before["bundle"]["bytes"] or snapshot["sha256"] != before["bundle"]["sha256"]:
        raise ValueError("actual readonly bundle delivery binding differs")
    after = held.readback()
    if before != after: raise ValueError("authenticated inputs changed")
    # Read the actual sealed bytes through the held object; proc paths are
    # intentional symlinks and must never be re-admitted as ordinary inputs.
    held._creator(); held._active = True
    lease = held._leases["bundle"]; lease._creator(); lease._active = True
    try:
        bundle_raw = os.pread(lease._descriptor(), lease._expected_size + 1, 0)
    finally:
        lease._active = False; held._active = False
    if len(bundle_raw) != before["bundle"]["bytes"] or hashlib.sha256(bundle_raw).hexdigest() != before["bundle"]["sha256"]:
        raise ValueError("sealed bundle readback differs")
    policy = _parse_verified(stdout, bundle_raw)
    cache = _cache_readback(evidence / "default-tuf-cache")
    after = held.readback()
    if before != after: raise ValueError("authenticated final input readback differs")
    return {"schema": "trillionnium.mozjs-authenticated-observation.v2", "actual_verifier_returncode": rc,
            "actual_supplier_signature_verified": True, "inputs": after, "policy": policy,
            "evidence_directory": str(evidence), "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "actual_process_sha256": hashlib.sha256(process_raw).hexdigest(),
            "readonly_namespace_sha256": hashlib.sha256(namespace_raw).hexdigest(), "readonly_snapshot": snapshot,
            "original_bundle_memfd_inode_consumption_proven": False,
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(), "default_tuf_cache": cache,
            "tool_artifact_attestation_verified": False, "actual_cargo_archive_consumption_proven": False,
            "native_cases_executed": False, "installed_qualified": False, "production_ready": False}


def verify_inputs(archive_path: Path, bundle_path: Path, tool_path: Path, evidence_parent: Path) -> dict:
    """Actual bounded verifier observation, never an input token for a build."""
    held = _admit_inputs(archive_path, bundle_path, tool_path)
    try:
        evidence = _new_directory(evidence_parent, "mozjs-authenticated-evidence-")
        return _authenticate(held, evidence)
    finally:
        if not held._active: held.close()


if __name__ == "__main__":
    try:
        if len(sys.argv) != 6 or sys.argv[1] != "--private-readonly-verifier-worker":
            raise ValueError("private worker invocation refused")
        _readonly_worker(*(int(value) for value in sys.argv[2:5]), Path(sys.argv[5]))
    except (Exception, KeyboardInterrupt):
        print("MOZJS_AUTHENTICATED_INPUT_REFUSED", file=sys.stderr)
        raise SystemExit(1)
