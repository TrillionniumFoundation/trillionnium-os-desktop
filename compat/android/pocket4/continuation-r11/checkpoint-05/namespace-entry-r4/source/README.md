# Owned held namespace entry, revision 4

This is a repair of the existing owned-probe runner entry. It does not deploy a new Main runtime.

The Python caller holds the qualified process directory, pidfd, namespace descriptors and root descriptor. It checks process and object identities before and after every command. The entry helper receives descriptor numbers with pass_fds, checks each namespace type, restores FD_CLOEXEC, enters the held namespaces and root, forks into the held PID namespace, and executes the requested command. It never resolves a numeric target PID for namespace entry. APK verification walks beneath the held root with every symlink rejected.

The Rust helper protects the launcher-to-helper and helper-to-direct-child admission windows using parent-death signals and a pidfd. This does not provide automatic cleanup of an entire Android command tree: credential changes can clear the parent-death signal and descendants do not inherit it. Existing timeout, owned-package cleanup, systemd/cgroup teardown and external readback remain required.

The existing activation, framework epoch, package identity, APK, single-action lock and exact owned uninstall checks are retained. The new helper does not prove commercial app production readiness or arbitrary kernel PID reuse tests.

The helper is not setuid. It is an owned host executable invoked only by the authorized existing root control process. Main namespace entry is a separate read-only preflight gate and is not implied by host controls.
