#!/usr/bin/env python3
"""Run unmodified ELF workloads on either Linux or the candidate kernel guest.

Every scratch write is beneath an owned temporary directory. A JSON report is
created even on test failure; never interpret a missing case as a pass.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import select
import shutil
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading

HERE = Path(__file__).resolve().parent
C_CASES = ("smoke", "threads_futex", "ipc_epoll", "file_lock", "process", "errno",
           "scm_rights", "async_fd", "mmap_cow", "cloexec", "fd_limit",
           "uds_peercred", "robust_owner_death")


def workload_contract():
    """Load and validate the sibling machine-readable workload contract.

    ``run.py`` is imported by tests through a file loader, so a regular
    package import is not reliable.  Loading by path keeps standalone and
    test invocations on the same contract.
    """
    import importlib.util

    path = HERE / "catalog.py"
    spec = importlib.util.spec_from_file_location("a04_linux_workload_catalog", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load workload catalog")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        summary = module.validate_files(module.DEFAULT_CATALOG, module.DEFAULT_REFERENCE)
    except module.CatalogError as exc:
        raise RuntimeError(f"invalid workload catalog: {exc}") from exc
    # Reports may be published as evidence; avoid embedding local absolute
    # paths while retaining both input digests and coverage counts.
    return summary


def command(args, *, timeout=30, cwd=None, env=None):
    return subprocess.run([str(x) for x in args], timeout=timeout, cwd=cwd,
                          env=env, capture_output=True, text=True, check=False)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect_elf(path):
    h = command(["readelf", "-l", path])
    d = command(["readelf", "-d", path])
    if h.returncode or d.returncode:
        raise RuntimeError("readelf inspection failed")
    m = re.search(r"Requesting program interpreter:\s*([^]]+)", h.stdout)
    return {"sha256": digest(path), "size": Path(path).stat().st_size,
            "interpreter": m.group(1) if m else None,
            "needed": re.findall(r"Shared library: \[([^]]+)\]", d.stdout)}


def gcc_build(binary_dir):
    binaries = {}
    builds = (
        ("dynamic", "probe.c", []),
        ("static", "probe.c", ["-static"]),
        ("sqlite_dynamic", "sqlite_probe.c", ["-lsqlite3"]),
        ("sqlite_static", "sqlite_probe.c", ["-static", "-lsqlite3", "-lpthread", "-lm", "-ldl"]),
    )
    for label, source, flags in builds:
        output = binary_dir / (("probe_" + label) if label in ("dynamic", "static") else label)
        # Source basename stabilizes __FILE__ across checkout paths.
        cmd = ["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pthread"]
        cmd += (["-static"] if "-static" in flags else [])
        cmd += [source, "-o", str(output.resolve())]
        cmd += [x for x in flags if x != "-static"]
        result = command(cmd, timeout=90, cwd=HERE)
        if result.returncode:
            raise RuntimeError(f"compile {label} failed: {result.stderr}")
        binaries[label] = output
    return binaries


def parse_strict_case_json(stdout):
    """Decode one exact JSON object; never trust duplicate keys or NaN.

    Linux reference results must obey the same observable-output contract as
    the Asterinas guest and chroot replays. Otherwise a malformed original
    workload can be incorrectly promoted into the independent Linux baseline.
    """
    if not isinstance(stdout, str) or len(stdout.splitlines()) != 1:
        raise ValueError("expected exactly one JSON line")

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("nonfinite JSON constant: " + value)

    facts = json.loads(stdout, object_pairs_hook=unique_pairs,
                       parse_constant=invalid_constant)
    if not isinstance(facts, dict) or facts.get("ok") is not True:
        raise ValueError("missing true application success fact")
    return facts


def run_case(key, args, cwd, *, trace_dir=None, env=None):
    cmd = [str(x) for x in args]
    trace_prefix = None
    if trace_dir is not None:
        trace_prefix = trace_dir / key
        cmd = ["strace", "-ff", "-qq", "-yy", "-s", "256", "-o", str(trace_prefix), "--", *cmd]
    try:
        p = command(cmd, timeout=20, cwd=cwd, env=env)
        try:
            output = parse_strict_case_json(p.stdout)
            decode_error = None
        except (ValueError, json.JSONDecodeError) as exc:
            output = None
            decode_error = "invalid stdout: " + type(exc).__name__
        ok = p.returncode == 0 and not p.stderr and decode_error is None
        error = (None if ok else
                 "nonzero exit" if p.returncode != 0 else
                 "unexpected stderr" if p.stderr else decode_error)
        obj = {"status": "pass" if ok else "fail", "exit_code": p.returncode,
               "facts": output, "error": error}
    except subprocess.TimeoutExpired:
        obj = {"status": "fail", "exit_code": None, "facts": None, "error": "timeout"}
    if trace_prefix:
        traced = sorted(trace_dir.glob(trace_prefix.name + ".*"))
        obj["trace_files"] = [p.name for p in traced]
        obj["trace_sha256"] = {p.name: digest(p) for p in traced}
    return obj


def sqlite_worker(db, prefix):
    con = sqlite3.connect(db, timeout=10)
    con.execute("PRAGMA busy_timeout=10000")
    for index in range(20):
        con.execute("BEGIN IMMEDIATE")
        con.execute("INSERT INTO events(id, value) VALUES(?,?)", (f"{prefix}{index:02d}", index))
        con.commit()
    con.close()
    return 0


def sqlite_crash(db):
    con = sqlite3.connect(db, timeout=10)
    con.execute("INSERT INTO events(id, value) VALUES('crash_committed', 41)")
    con.commit()
    con.execute("BEGIN IMMEDIATE")
    con.execute("INSERT INTO events(id, value) VALUES('crash_uncommitted', 42)")
    os._exit(37)  # Synthetic abrupt worker death; never a real service or DB.


def sqlite_test(scratch):
    db = scratch / "wal.sqlite"
    con = sqlite3.connect(db)
    mode = con.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    con.execute("CREATE TABLE events(id TEXT PRIMARY KEY, value INTEGER NOT NULL)")
    con.commit()
    con.close()
    writers = [subprocess.Popen([sys.executable, str(HERE / "run.py"), "--sqlite-worker", str(db), s],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
               for s in ("A", "B")]
    writers_ok = True
    for p in writers:
        _, err = p.communicate(timeout=20)
        if p.returncode != 0:
            writers_ok = False
            raise RuntimeError(f"SQLite writer exited {p.returncode}: {err.decode(errors='replace')}")
    child = command([sys.executable, str(HERE / "run.py"), "--sqlite-crash", str(db)])
    con = sqlite3.connect(db)
    count = con.execute("SELECT count(*) FROM events").fetchone()[0]
    uncommitted = con.execute("SELECT count(*) FROM events WHERE id='crash_uncommitted'").fetchone()[0]
    committed = con.execute("SELECT count(*) FROM events WHERE id='crash_committed'").fetchone()[0]
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    checkpoint = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    con.close()
    reopened = sqlite3.connect(db)
    reopened_count = reopened.execute("SELECT count(*) FROM events").fetchone()[0]
    reopened.close()
    ok = (mode == "wal" and writers_ok and child.returncode == 37 and
          count == 41 and reopened_count == 41 and uncommitted == 0 and committed == 1 and
          integrity == "ok" and checkpoint[0] == 0)
    return {"ok": ok, "journal_mode": mode, "concurrent_commits": 40,
            "rows_after_reopen": reopened_count, "crash_exit_code": child.returncode,
            "uncommitted_visible": bool(uncommitted), "committed_visible": bool(committed),
            "integrity_check": integrity, "checkpoint_busy": checkpoint[0]}


def unix_path_test(scratch):
    path = scratch / "service.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)
    errors = []

    def client():
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
                c.connect(str(path))
                c.sendall(b"hello")
                if c.recv(5) != b"world":
                    errors.append("bad reply")
        except Exception as e:
            errors.append(str(e))

    t = threading.Thread(target=client)
    t.start()
    poll = select.epoll()
    try:
        poll.register(server.fileno(), select.EPOLLIN)
        ready = bool(poll.poll(5.0))
        if not ready:
            raise RuntimeError("AF_UNIX accept timeout")
        conn, _ = server.accept()
        with conn:
            got = conn.recv(5)
            conn.sendall(b"world")
        t.join(timeout=5)
    finally:
        poll.close()
        server.close()
        path.unlink(missing_ok=True)
    return {"ok": got == b"hello" and not t.is_alive() and not errors and not path.exists(),
            "named_af_unix": True, "epoll_accept": ready, "socket_path_released": not path.exists()}


def nss_tls_test(scratch):
    hosts = socket.getaddrinfo("localhost", None, type=socket.SOCK_STREAM)
    nss = bool(hosts)
    cert, key = scratch / "cert.pem", scratch / "key.pem"
    p = command(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-noenc", "-days", "1",
                 "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
                 "-keyout", key, "-out", cert], timeout=20)
    if p.returncode:
        raise RuntimeError("local TLS certificate generation failed: " + p.stderr[-200:])
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    server_ctx.load_cert_chain(cert, key)
    client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_ctx.check_hostname = True
    client_ctx.verify_mode = ssl.CERT_REQUIRED
    client_ctx.load_verify_locations(cafile=str(cert))
    client_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    errors = []

    def serve():
        try:
            conn, _ = server.accept()
            with server_ctx.wrap_socket(conn, server_side=True) as tls:
                if tls.recv(4) != b"ping":
                    errors.append("bad request")
                tls.sendall(b"pong")
        except Exception as e:
            errors.append(str(e))

    t = threading.Thread(target=serve)
    t.start()
    reply = None
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
            with client_ctx.wrap_socket(raw, server_hostname="localhost") as tls:
                tls.sendall(b"ping")
                reply = tls.recv(4)
    finally:
        t.join(timeout=5)
        server.close()
    paths = ssl.get_default_verify_paths()
    trust = any(p and Path(p).is_file() for p in (paths.cafile, paths.openssl_cafile))
    return {"ok": nss and reply == b"pong" and not errors and not t.is_alive() and trust,
            "nss_localhost": nss, "loopback_tls_verified": reply == b"pong" and not errors,
            "system_ca_bundle_present": trust}


def python_case(func, scratch):
    try:
        facts = func(scratch)
        return {"status": "pass" if facts["ok"] else "fail", "exit_code": 0 if facts["ok"] else 1,
                "facts": facts, "error": None}
    except Exception as e:
        return {"status": "fail", "exit_code": 1, "facts": None, "error": f"{type(e).__name__}: {e}"}


def run_rust(mode, binary_dir, scratch, env):
    if mode == "skip":
        return {"status": "not_run", "reason": "explicit --rust skip"}
    cargo = shutil.which("cargo")
    if not cargo:
        return {"status": "not_run" if mode == "auto" else "fail", "reason": "cargo unavailable"}
    manifest = HERE / "rust" / "Cargo.toml"
    lockfile = HERE / "rust" / "Cargo.lock"
    if not lockfile.exists():
        return {"status": "not_run" if mode == "auto" else "fail",
                "reason": "Tokio transitive Cargo.lock not frozen; generate and review on provisioned host"}
    build_command = [cargo, "build", "--offline", "--locked", "--release", "--manifest-path", manifest,
                     "--target-dir", binary_dir / "cargo-target"]
    build = command(build_command, timeout=120)
    build_record = {
        "command": [str(value) for value in build_command],
        "manifest_sha256": digest(manifest),
        "cargo_lock_sha256": digest(lockfile),
    }
    if build.returncode:
        return {"status": "not_run" if mode == "auto" else "fail",
                "reason": "offline dependency/build unavailable", "error": build.stderr[-1200:],
                "build": build_record}
    binary = binary_dir / "cargo-target" / "release" / "a04-tokio-workload"
    build_record["binary"] = inspect_elf(binary)
    result = run_case("rust_tokio", [binary, scratch], scratch, env=env)
    result["build"] = build_record
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, help="write JSON report, required for reproducible evidence")
    ap.add_argument("--binary-dir", type=Path, help="directory for generated or prebuilt probe_static/probe_dynamic")
    ap.add_argument("--no-build", action="store_true", help="use identical prebuilt ELF bytes")
    ap.add_argument("--rust", choices=("auto", "required", "skip"), default="auto")
    ap.add_argument("--trace", action="store_true", help="capture real strace -ff syscall logs")
    ap.add_argument("--trace-dir", type=Path, help="new PRIVATE persistent directory for trace.* files")
    ap.add_argument("--sqlite-worker", nargs=2, metavar=("DB", "TAG"))
    ap.add_argument("--sqlite-crash", metavar="DB")
    args = ap.parse_args()
    if args.sqlite_worker:
        return sqlite_worker(*args.sqlite_worker)
    if args.sqlite_crash:
        return sqlite_crash(args.sqlite_crash)
    if not args.output:
        ap.error("--output is required")
    if args.trace_dir and not args.trace:
        ap.error("--trace-dir requires --trace")
    if args.trace and shutil.which("strace") and args.trace_dir is None:
        ap.error("--trace requires --trace-dir to preserve private raw syscall evidence")
    if args.trace_dir is not None and args.trace_dir.exists():
        ap.error("--trace-dir already exists; refusing overwrite")
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix="a04-linux-") as td:
        scratch = Path(td)
        binary_dir = args.binary_dir or (scratch / "bins")
        binary_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update({"LC_ALL": "C", "TZ": "UTC"})
        report = {"schema": 1, "suite": "a04-linux-host-differential",
                  "platform": {"system": platform.system(), "machine": platform.machine(),
                               "release": platform.release(), "python": platform.python_version(),
                               "sqlite": sqlite3.sqlite_version,
                               "gcc": command(["gcc", "--version"]).stdout.splitlines()[0]},
                  "binaries": {}, "cases": {}, "trace": "not_requested"}
        try:
            report["workload_contract"] = workload_contract()
        except RuntimeError as exc:
            # Continue to emit a diagnostic report, but make this a hard
            # failure below instead of silently running an unreviewed matrix.
            report["workload_contract_error"] = str(exc)
        trace_dir = None
        if args.trace:
            if shutil.which("strace"):
                trace_dir = args.trace_dir.resolve()
                trace_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
                trace_dir.chmod(0o700)
                report["trace"] = "captured_private_persistent"
                report["raw_trace_is_private"] = True
            else:
                report["trace"] = "blocked_strace_unavailable"
        try:
            bins = {label: binary_dir / (("probe_" + label) if label in ("dynamic", "static") else label) for label in
                    ("dynamic", "static", "sqlite_dynamic", "sqlite_static")} if args.no_build else gcc_build(binary_dir)
            for label, binary in bins.items():
                report["binaries"][label] = inspect_elf(binary)
                for case in (("sqlite_wal_elf",) if label.startswith("sqlite_") else C_CASES):
                    case_dir = scratch / f"{label}-{case}"
                    case_dir.mkdir()
                    cmd = [binary.resolve(), case_dir] if label.startswith("sqlite_") else [binary.resolve(), case, case_dir]
                    report["cases"][f"{label}.{case}"] = run_case(
                        f"{label}.{case}", cmd, case_dir,
                        trace_dir=trace_dir, env=env)

        except (OSError, RuntimeError) as exc:
            report["build_error"] = str(exc)
        for case, func in (("sqlite_wal", sqlite_test), ("uds_path", unix_path_test), ("nss_tls", nss_tls_test)):
            case_dir = scratch / case
            case_dir.mkdir()
            report["cases"][case] = python_case(func, case_dir)
        rustdir = scratch / "rust"
        rustdir.mkdir()
        report["cases"]["rust_tokio"] = run_rust(args.rust, binary_dir, rustdir, env)
        report["counts"] = {key: sum(1 for x in report["cases"].values() if x["status"] == key)
                            for key in ("pass", "fail", "not_run")}
        report["overall"] = "failed" if (report["counts"]["fail"] or
                                         "build_error" in report or
                                         "workload_contract_error" in report) else (
            "partial" if report["counts"]["not_run"] else "passed")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"overall": report["overall"], "counts": report["counts"],
                          "trace": report["trace"], "output": str(args.output)}))
        return 1 if report["overall"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
