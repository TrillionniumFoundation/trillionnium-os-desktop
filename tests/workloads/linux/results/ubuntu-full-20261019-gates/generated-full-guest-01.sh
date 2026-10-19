#!/bin/sh
set -eu
umask 077
full_failed=0
/bin/busybox mkdir -p /tmp/a04
export PATH=/usr/local/bin/a04:/usr/bin:/bin
export LC_ALL=C
export TZ=UTC
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
export PYTHONSAFEPATH=1
export OPENSSL_CONF=/etc/ssl/openssl.cnf
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
export SSL_CERT_DIR=/etc/ssl/certs
unset LD_PRELOAD LD_LIBRARY_PATH PYTHONPATH PYTHONHOME PYTHONSTARTUP
/bin/busybox mkdir -p /tmp/a04/dynamic.async_fd
export HOME=/tmp/a04/dynamic.async_fd
echo A04_FULL_BEGIN=dynamic.async_fd
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_dynamic async_fd /tmp/a04/dynamic.async_fd >/tmp/a04/dynamic.async_fd/stdout.log 2>/tmp/a04/dynamic.async_fd/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/dynamic.async_fd/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=dynamic.async_fd:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.async_fd/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.async_fd/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/dynamic.async_fd/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=dynamic.async_fd:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.async_fd/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.async_fd/stderr.log)
stderr_sha=$1
echo A04_FULL_END=dynamic.async_fd:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/dynamic.cloexec
export HOME=/tmp/a04/dynamic.cloexec
echo A04_FULL_BEGIN=dynamic.cloexec
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_dynamic cloexec /tmp/a04/dynamic.cloexec >/tmp/a04/dynamic.cloexec/stdout.log 2>/tmp/a04/dynamic.cloexec/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/dynamic.cloexec/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=dynamic.cloexec:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.cloexec/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.cloexec/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/dynamic.cloexec/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=dynamic.cloexec:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.cloexec/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.cloexec/stderr.log)
stderr_sha=$1
echo A04_FULL_END=dynamic.cloexec:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/dynamic.errno
export HOME=/tmp/a04/dynamic.errno
echo A04_FULL_BEGIN=dynamic.errno
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_dynamic errno /tmp/a04/dynamic.errno >/tmp/a04/dynamic.errno/stdout.log 2>/tmp/a04/dynamic.errno/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/dynamic.errno/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=dynamic.errno:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.errno/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.errno/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/dynamic.errno/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=dynamic.errno:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.errno/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.errno/stderr.log)
stderr_sha=$1
echo A04_FULL_END=dynamic.errno:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/dynamic.fd_limit
export HOME=/tmp/a04/dynamic.fd_limit
echo A04_FULL_BEGIN=dynamic.fd_limit
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_dynamic fd_limit /tmp/a04/dynamic.fd_limit >/tmp/a04/dynamic.fd_limit/stdout.log 2>/tmp/a04/dynamic.fd_limit/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/dynamic.fd_limit/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=dynamic.fd_limit:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.fd_limit/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.fd_limit/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/dynamic.fd_limit/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=dynamic.fd_limit:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.fd_limit/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.fd_limit/stderr.log)
stderr_sha=$1
echo A04_FULL_END=dynamic.fd_limit:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/dynamic.file_lock
export HOME=/tmp/a04/dynamic.file_lock
echo A04_FULL_BEGIN=dynamic.file_lock
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_dynamic file_lock /tmp/a04/dynamic.file_lock >/tmp/a04/dynamic.file_lock/stdout.log 2>/tmp/a04/dynamic.file_lock/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/dynamic.file_lock/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=dynamic.file_lock:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.file_lock/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.file_lock/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/dynamic.file_lock/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=dynamic.file_lock:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.file_lock/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.file_lock/stderr.log)
stderr_sha=$1
echo A04_FULL_END=dynamic.file_lock:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/dynamic.ipc_epoll
export HOME=/tmp/a04/dynamic.ipc_epoll
echo A04_FULL_BEGIN=dynamic.ipc_epoll
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_dynamic ipc_epoll /tmp/a04/dynamic.ipc_epoll >/tmp/a04/dynamic.ipc_epoll/stdout.log 2>/tmp/a04/dynamic.ipc_epoll/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/dynamic.ipc_epoll/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=dynamic.ipc_epoll:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.ipc_epoll/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.ipc_epoll/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/dynamic.ipc_epoll/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=dynamic.ipc_epoll:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.ipc_epoll/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.ipc_epoll/stderr.log)
stderr_sha=$1
echo A04_FULL_END=dynamic.ipc_epoll:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/dynamic.mmap_cow
export HOME=/tmp/a04/dynamic.mmap_cow
echo A04_FULL_BEGIN=dynamic.mmap_cow
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_dynamic mmap_cow /tmp/a04/dynamic.mmap_cow >/tmp/a04/dynamic.mmap_cow/stdout.log 2>/tmp/a04/dynamic.mmap_cow/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/dynamic.mmap_cow/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=dynamic.mmap_cow:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.mmap_cow/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.mmap_cow/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/dynamic.mmap_cow/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=dynamic.mmap_cow:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.mmap_cow/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.mmap_cow/stderr.log)
stderr_sha=$1
echo A04_FULL_END=dynamic.mmap_cow:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/dynamic.process
export HOME=/tmp/a04/dynamic.process
echo A04_FULL_BEGIN=dynamic.process
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_dynamic process /tmp/a04/dynamic.process >/tmp/a04/dynamic.process/stdout.log 2>/tmp/a04/dynamic.process/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/dynamic.process/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=dynamic.process:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.process/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.process/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/dynamic.process/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=dynamic.process:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.process/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.process/stderr.log)
stderr_sha=$1
echo A04_FULL_END=dynamic.process:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/dynamic.robust_owner_death
export HOME=/tmp/a04/dynamic.robust_owner_death
echo A04_FULL_BEGIN=dynamic.robust_owner_death
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_dynamic robust_owner_death /tmp/a04/dynamic.robust_owner_death >/tmp/a04/dynamic.robust_owner_death/stdout.log 2>/tmp/a04/dynamic.robust_owner_death/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/dynamic.robust_owner_death/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=dynamic.robust_owner_death:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.robust_owner_death/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.robust_owner_death/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/dynamic.robust_owner_death/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=dynamic.robust_owner_death:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.robust_owner_death/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.robust_owner_death/stderr.log)
stderr_sha=$1
echo A04_FULL_END=dynamic.robust_owner_death:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/dynamic.scm_rights
export HOME=/tmp/a04/dynamic.scm_rights
echo A04_FULL_BEGIN=dynamic.scm_rights
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_dynamic scm_rights /tmp/a04/dynamic.scm_rights >/tmp/a04/dynamic.scm_rights/stdout.log 2>/tmp/a04/dynamic.scm_rights/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/dynamic.scm_rights/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=dynamic.scm_rights:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.scm_rights/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.scm_rights/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/dynamic.scm_rights/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=dynamic.scm_rights:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.scm_rights/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.scm_rights/stderr.log)
stderr_sha=$1
echo A04_FULL_END=dynamic.scm_rights:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/dynamic.smoke
export HOME=/tmp/a04/dynamic.smoke
echo A04_FULL_BEGIN=dynamic.smoke
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_dynamic smoke /tmp/a04/dynamic.smoke >/tmp/a04/dynamic.smoke/stdout.log 2>/tmp/a04/dynamic.smoke/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/dynamic.smoke/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=dynamic.smoke:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.smoke/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.smoke/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/dynamic.smoke/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=dynamic.smoke:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.smoke/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.smoke/stderr.log)
stderr_sha=$1
echo A04_FULL_END=dynamic.smoke:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/dynamic.threads_futex
export HOME=/tmp/a04/dynamic.threads_futex
echo A04_FULL_BEGIN=dynamic.threads_futex
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_dynamic threads_futex /tmp/a04/dynamic.threads_futex >/tmp/a04/dynamic.threads_futex/stdout.log 2>/tmp/a04/dynamic.threads_futex/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/dynamic.threads_futex/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=dynamic.threads_futex:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.threads_futex/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.threads_futex/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/dynamic.threads_futex/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=dynamic.threads_futex:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.threads_futex/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.threads_futex/stderr.log)
stderr_sha=$1
echo A04_FULL_END=dynamic.threads_futex:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/dynamic.uds_peercred
export HOME=/tmp/a04/dynamic.uds_peercred
echo A04_FULL_BEGIN=dynamic.uds_peercred
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_dynamic uds_peercred /tmp/a04/dynamic.uds_peercred >/tmp/a04/dynamic.uds_peercred/stdout.log 2>/tmp/a04/dynamic.uds_peercred/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/dynamic.uds_peercred/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=dynamic.uds_peercred:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.uds_peercred/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.uds_peercred/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/dynamic.uds_peercred/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=dynamic.uds_peercred:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/dynamic.uds_peercred/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/dynamic.uds_peercred/stderr.log)
stderr_sha=$1
echo A04_FULL_END=dynamic.uds_peercred:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/nss_tls
export HOME=/tmp/a04/nss_tls
echo A04_FULL_BEGIN=nss_tls
if /bin/busybox timeout -s KILL 45 /usr/bin/python3.12 -I -B -S /usr/local/lib/a04/full_python_case.py nss_tls /tmp/a04/nss_tls >/tmp/a04/nss_tls/stdout.log 2>/tmp/a04/nss_tls/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/nss_tls/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=nss_tls:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/nss_tls/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/nss_tls/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/nss_tls/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=nss_tls:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/nss_tls/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/nss_tls/stderr.log)
stderr_sha=$1
echo A04_FULL_END=nss_tls:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/rust_tokio
export HOME=/tmp/a04/rust_tokio
echo A04_FULL_BEGIN=rust_tokio
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/a04-tokio-workload /tmp/a04/rust_tokio >/tmp/a04/rust_tokio/stdout.log 2>/tmp/a04/rust_tokio/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/rust_tokio/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=rust_tokio:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/rust_tokio/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/rust_tokio/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/rust_tokio/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=rust_tokio:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/rust_tokio/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/rust_tokio/stderr.log)
stderr_sha=$1
echo A04_FULL_END=rust_tokio:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/sqlite_dynamic.sqlite_wal_elf
export HOME=/tmp/a04/sqlite_dynamic.sqlite_wal_elf
echo A04_FULL_BEGIN=sqlite_dynamic.sqlite_wal_elf
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/sqlite_dynamic /tmp/a04/sqlite_dynamic.sqlite_wal_elf >/tmp/a04/sqlite_dynamic.sqlite_wal_elf/stdout.log 2>/tmp/a04/sqlite_dynamic.sqlite_wal_elf/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/sqlite_dynamic.sqlite_wal_elf/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=sqlite_dynamic.sqlite_wal_elf:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/sqlite_dynamic.sqlite_wal_elf/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/sqlite_dynamic.sqlite_wal_elf/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/sqlite_dynamic.sqlite_wal_elf/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=sqlite_dynamic.sqlite_wal_elf:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/sqlite_dynamic.sqlite_wal_elf/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/sqlite_dynamic.sqlite_wal_elf/stderr.log)
stderr_sha=$1
echo A04_FULL_END=sqlite_dynamic.sqlite_wal_elf:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/sqlite_static.sqlite_wal_elf
export HOME=/tmp/a04/sqlite_static.sqlite_wal_elf
echo A04_FULL_BEGIN=sqlite_static.sqlite_wal_elf
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/sqlite_static /tmp/a04/sqlite_static.sqlite_wal_elf >/tmp/a04/sqlite_static.sqlite_wal_elf/stdout.log 2>/tmp/a04/sqlite_static.sqlite_wal_elf/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/sqlite_static.sqlite_wal_elf/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=sqlite_static.sqlite_wal_elf:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/sqlite_static.sqlite_wal_elf/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/sqlite_static.sqlite_wal_elf/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/sqlite_static.sqlite_wal_elf/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=sqlite_static.sqlite_wal_elf:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/sqlite_static.sqlite_wal_elf/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/sqlite_static.sqlite_wal_elf/stderr.log)
stderr_sha=$1
echo A04_FULL_END=sqlite_static.sqlite_wal_elf:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/sqlite_wal
export HOME=/tmp/a04/sqlite_wal
echo A04_FULL_BEGIN=sqlite_wal
if /bin/busybox timeout -s KILL 45 /usr/bin/python3.12 -I -B -S /usr/local/lib/a04/full_python_case.py sqlite_wal /tmp/a04/sqlite_wal >/tmp/a04/sqlite_wal/stdout.log 2>/tmp/a04/sqlite_wal/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/sqlite_wal/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=sqlite_wal:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/sqlite_wal/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/sqlite_wal/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/sqlite_wal/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=sqlite_wal:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/sqlite_wal/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/sqlite_wal/stderr.log)
stderr_sha=$1
echo A04_FULL_END=sqlite_wal:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/static.async_fd
export HOME=/tmp/a04/static.async_fd
echo A04_FULL_BEGIN=static.async_fd
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_static async_fd /tmp/a04/static.async_fd >/tmp/a04/static.async_fd/stdout.log 2>/tmp/a04/static.async_fd/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/static.async_fd/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=static.async_fd:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/static.async_fd/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.async_fd/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/static.async_fd/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=static.async_fd:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/static.async_fd/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.async_fd/stderr.log)
stderr_sha=$1
echo A04_FULL_END=static.async_fd:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/static.cloexec
export HOME=/tmp/a04/static.cloexec
echo A04_FULL_BEGIN=static.cloexec
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_static cloexec /tmp/a04/static.cloexec >/tmp/a04/static.cloexec/stdout.log 2>/tmp/a04/static.cloexec/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/static.cloexec/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=static.cloexec:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/static.cloexec/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.cloexec/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/static.cloexec/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=static.cloexec:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/static.cloexec/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.cloexec/stderr.log)
stderr_sha=$1
echo A04_FULL_END=static.cloexec:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/static.errno
export HOME=/tmp/a04/static.errno
echo A04_FULL_BEGIN=static.errno
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_static errno /tmp/a04/static.errno >/tmp/a04/static.errno/stdout.log 2>/tmp/a04/static.errno/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/static.errno/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=static.errno:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/static.errno/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.errno/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/static.errno/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=static.errno:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/static.errno/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.errno/stderr.log)
stderr_sha=$1
echo A04_FULL_END=static.errno:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/static.fd_limit
export HOME=/tmp/a04/static.fd_limit
echo A04_FULL_BEGIN=static.fd_limit
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_static fd_limit /tmp/a04/static.fd_limit >/tmp/a04/static.fd_limit/stdout.log 2>/tmp/a04/static.fd_limit/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/static.fd_limit/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=static.fd_limit:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/static.fd_limit/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.fd_limit/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/static.fd_limit/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=static.fd_limit:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/static.fd_limit/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.fd_limit/stderr.log)
stderr_sha=$1
echo A04_FULL_END=static.fd_limit:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/static.file_lock
export HOME=/tmp/a04/static.file_lock
echo A04_FULL_BEGIN=static.file_lock
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_static file_lock /tmp/a04/static.file_lock >/tmp/a04/static.file_lock/stdout.log 2>/tmp/a04/static.file_lock/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/static.file_lock/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=static.file_lock:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/static.file_lock/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.file_lock/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/static.file_lock/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=static.file_lock:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/static.file_lock/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.file_lock/stderr.log)
stderr_sha=$1
echo A04_FULL_END=static.file_lock:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/static.ipc_epoll
export HOME=/tmp/a04/static.ipc_epoll
echo A04_FULL_BEGIN=static.ipc_epoll
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_static ipc_epoll /tmp/a04/static.ipc_epoll >/tmp/a04/static.ipc_epoll/stdout.log 2>/tmp/a04/static.ipc_epoll/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/static.ipc_epoll/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=static.ipc_epoll:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/static.ipc_epoll/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.ipc_epoll/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/static.ipc_epoll/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=static.ipc_epoll:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/static.ipc_epoll/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.ipc_epoll/stderr.log)
stderr_sha=$1
echo A04_FULL_END=static.ipc_epoll:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/static.mmap_cow
export HOME=/tmp/a04/static.mmap_cow
echo A04_FULL_BEGIN=static.mmap_cow
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_static mmap_cow /tmp/a04/static.mmap_cow >/tmp/a04/static.mmap_cow/stdout.log 2>/tmp/a04/static.mmap_cow/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/static.mmap_cow/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=static.mmap_cow:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/static.mmap_cow/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.mmap_cow/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/static.mmap_cow/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=static.mmap_cow:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/static.mmap_cow/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.mmap_cow/stderr.log)
stderr_sha=$1
echo A04_FULL_END=static.mmap_cow:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/static.process
export HOME=/tmp/a04/static.process
echo A04_FULL_BEGIN=static.process
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_static process /tmp/a04/static.process >/tmp/a04/static.process/stdout.log 2>/tmp/a04/static.process/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/static.process/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=static.process:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/static.process/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.process/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/static.process/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=static.process:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/static.process/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.process/stderr.log)
stderr_sha=$1
echo A04_FULL_END=static.process:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/static.robust_owner_death
export HOME=/tmp/a04/static.robust_owner_death
echo A04_FULL_BEGIN=static.robust_owner_death
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_static robust_owner_death /tmp/a04/static.robust_owner_death >/tmp/a04/static.robust_owner_death/stdout.log 2>/tmp/a04/static.robust_owner_death/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/static.robust_owner_death/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=static.robust_owner_death:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/static.robust_owner_death/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.robust_owner_death/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/static.robust_owner_death/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=static.robust_owner_death:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/static.robust_owner_death/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.robust_owner_death/stderr.log)
stderr_sha=$1
echo A04_FULL_END=static.robust_owner_death:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/static.scm_rights
export HOME=/tmp/a04/static.scm_rights
echo A04_FULL_BEGIN=static.scm_rights
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_static scm_rights /tmp/a04/static.scm_rights >/tmp/a04/static.scm_rights/stdout.log 2>/tmp/a04/static.scm_rights/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/static.scm_rights/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=static.scm_rights:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/static.scm_rights/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.scm_rights/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/static.scm_rights/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=static.scm_rights:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/static.scm_rights/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.scm_rights/stderr.log)
stderr_sha=$1
echo A04_FULL_END=static.scm_rights:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/static.smoke
export HOME=/tmp/a04/static.smoke
echo A04_FULL_BEGIN=static.smoke
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_static smoke /tmp/a04/static.smoke >/tmp/a04/static.smoke/stdout.log 2>/tmp/a04/static.smoke/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/static.smoke/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=static.smoke:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/static.smoke/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.smoke/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/static.smoke/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=static.smoke:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/static.smoke/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.smoke/stderr.log)
stderr_sha=$1
echo A04_FULL_END=static.smoke:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/static.threads_futex
export HOME=/tmp/a04/static.threads_futex
echo A04_FULL_BEGIN=static.threads_futex
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_static threads_futex /tmp/a04/static.threads_futex >/tmp/a04/static.threads_futex/stdout.log 2>/tmp/a04/static.threads_futex/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/static.threads_futex/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=static.threads_futex:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/static.threads_futex/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.threads_futex/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/static.threads_futex/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=static.threads_futex:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/static.threads_futex/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.threads_futex/stderr.log)
stderr_sha=$1
echo A04_FULL_END=static.threads_futex:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/static.uds_peercred
export HOME=/tmp/a04/static.uds_peercred
echo A04_FULL_BEGIN=static.uds_peercred
if /bin/busybox timeout -s KILL 45 /usr/local/bin/a04/probe_static uds_peercred /tmp/a04/static.uds_peercred >/tmp/a04/static.uds_peercred/stdout.log 2>/tmp/a04/static.uds_peercred/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/static.uds_peercred/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=static.uds_peercred:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/static.uds_peercred/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.uds_peercred/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/static.uds_peercred/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=static.uds_peercred:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/static.uds_peercred/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/static.uds_peercred/stderr.log)
stderr_sha=$1
echo A04_FULL_END=static.uds_peercred:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
/bin/busybox mkdir -p /tmp/a04/uds_path
export HOME=/tmp/a04/uds_path
echo A04_FULL_BEGIN=uds_path
if /bin/busybox timeout -s KILL 45 /usr/bin/python3.12 -I -B -S /usr/local/lib/a04/full_python_case.py uds_path /tmp/a04/uds_path >/tmp/a04/uds_path/stdout.log 2>/tmp/a04/uds_path/stderr.log; then
    case_exit=0
else
    case_exit=$?
    full_failed=$((full_failed + 1))
fi
/bin/busybox base64 /tmp/a04/uds_path/stdout.log | while IFS= read -r chunk; do
    echo A04_FULL_STDOUT=uds_path:$chunk
done
stdout_bytes=$(/bin/busybox wc -c </tmp/a04/uds_path/stdout.log)
set -- $(/bin/busybox sha256sum /tmp/a04/uds_path/stdout.log)
stdout_sha=$1
/bin/busybox base64 /tmp/a04/uds_path/stderr.log | while IFS= read -r chunk; do
    echo A04_FULL_STDERR=uds_path:$chunk
done
stderr_bytes=$(/bin/busybox wc -c </tmp/a04/uds_path/stderr.log)
set -- $(/bin/busybox sha256sum /tmp/a04/uds_path/stderr.log)
stderr_sha=$1
echo A04_FULL_END=uds_path:$case_exit:$stdout_bytes:$stdout_sha:$stderr_bytes:$stderr_sha
echo A04_FULL_COMPLETE=32:$full_failed
test "$full_failed" -eq 0
