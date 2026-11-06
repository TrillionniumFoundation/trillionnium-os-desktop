#!/usr/bin/env python3
"""One ordinary OS resolver observation; no HTTP, download, child or Android.

The only application-level DNS invocation is socket.getaddrinfo. The configured
system resolver may perform its normal NSS lookups, IPv4/IPv6 queries or retries;
this script does not change that configuration or promise one wire packet.
"""
import fcntl
import json
import os
import signal
import socket
import sys
import time

HOSTNAME = 's.shouji.qihucdn.com'
PORT = 443
DNS_DEADLINE_SECONDS = 20
ENTRY = '--resolve-zbj-official-host-once'


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def census():
    result={}
    for name in os.listdir('/proc/self/fd'):
        try:
            fd=int(name);s=os.fstat(fd)
            result[name]=[os.readlink('/proc/self/fd/'+name),s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,
                          fcntl.fcntl(fd,fcntl.F_GETFD),fcntl.fcntl(fd,fcntl.F_GETFL)]
        except OSError as e:
            if e.errno not in (2,9):raise
    return result


def emit(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True), flush=True)


def main():
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000,
         'EXACT_UNPRIVILEGED_OPERATOR_REQUIRED')
    need(sys.argv[1:] == [ENTRY], 'EXACT_SINGLE_OBSERVATION_ENTRY_REQUIRED')
    before = census()
    started = time.monotonic()
    result = {
        'schema': 'pocket4-zbj-system-resolver-observation-v1',
        'ok': False, 'status': 'NOT_OBSERVED', 'errors': [],
        'hostname': HOSTNAME, 'service_port': PORT,
        'family': int(socket.AF_UNSPEC), 'socket_type': int(socket.SOCK_STREAM),
        'protocol': int(socket.IPPROTO_TCP), 'flags': 0,
        'application_getaddrinfo_calls': 0, 'application_retries': 0,
        'normal_resolver_internal_query_count': None,
        'normal_resolver_configuration_changed': False,
        'resolution_completed': False, 'address_records': [],
        'actual_uid': os.getuid(), 'actual_euid': os.geteuid(),
        'actual_gid': os.getgid(), 'actual_egid': os.getegid(),
        'python_executable_observed': sys.executable,
        'python_version_observed': sys.version,
        'python_full_file_identity_verified_by_this_probe': False,
        'explicit_subprocesses': 0, 'HTTP_requests': 0, 'APK_downloads': 0,
        'TLS_handshakes_requested': 0, 'proxy_configuration_changes': 0,
        'TLS_configuration_changes': 0, 'IP_override_or_custom_resolver': False,
        'files_written_by_probe': 0, 'Android_commands': 0, 'Main_actions': 0,
        'Main_lock_or_fds': 0, 'installs': 0, 'permission_changes': 0,
        'production_ready': False, 'authorizes_download_or_install': False,
        'before_descriptor_identities': before,
    }
    try:
        # SIG_DFL terminates this owned probe even if libc resolution remains
        # blocked in C. Such an exit has no success result and must not pass.
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.setitimer(signal.ITIMER_REAL, DNS_DEADLINE_SECONDS, 0)
        result['application_getaddrinfo_calls'] = 1
        emit({'event': 'DNS_RESOLUTION_STARTED', 'hostname': HOSTNAME,
              'port': PORT, 'application_call_count': 1, 'automatic_retries': 0,
              'own_process_default_SIGALRM_deadline_seconds': DNS_DEADLINE_SECONDS})
        answers = socket.getaddrinfo(HOSTNAME, PORT, socket.AF_UNSPEC,
                                     socket.SOCK_STREAM, socket.IPPROTO_TCP, 0)
        signal.setitimer(signal.ITIMER_REAL, 0, 0)
        result['resolution_completed'] = True
        need(0 < len(answers) <= 256, 'BOUNDED_NONEMPTY_RESOLVER_ANSWER_REQUIRED')
        for family, socktype, protocol, canonical, address in answers:
            need(family in (socket.AF_INET, socket.AF_INET6) and
                 socktype == socket.SOCK_STREAM and protocol == socket.IPPROTO_TCP,
                 'EXPECTED_TCP_IP_RESOLVER_RECORD_REQUIRED')
            need(isinstance(canonical, str) and len(canonical) <= 255 and
                 isinstance(address, tuple) and len(address) in (2, 4) and
                 isinstance(address[0], str) and len(address[0]) <= 255 and
                 address[1] == PORT, 'BOUNDED_RESOLVER_RECORD_SHAPE_REQUIRED')
            result['address_records'].append({
                'family': int(family), 'socket_type': int(socktype),
                'protocol': int(protocol), 'canonical_name': canonical,
                'socket_address': list(address),
            })
        result['ok'] = True
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__,
                                 'errno': getattr(error, 'errno', None),
                                 'reason': str(error)[:1024]})
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0, 0)
    result['elapsed_seconds'] = time.monotonic() - started
    after = census()
    result['after_descriptor_identities'] = after
    result['original_descriptor_identities_restored'] = after == before
    result['ok'] = (result['ok'] and result['original_descriptor_identities_restored']
                    and result['application_getaddrinfo_calls'] == 1
                    and result['elapsed_seconds'] < DNS_DEADLINE_SECONDS
                    and not result['errors'])
    result['status'] = ('OS_DNS_RESOLVED_ONLY_NOT_HTTP_OR_DOWNLOAD_VERIFIED'
                        if result['ok'] else 'DNS_OBSERVATION_FAILED')
    emit(result)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
