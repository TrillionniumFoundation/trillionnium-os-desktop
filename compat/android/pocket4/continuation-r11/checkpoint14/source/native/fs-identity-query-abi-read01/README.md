# Fixed Bionic FS identity-query ABI source reader

Source-only handoff for Root; it has not been dispatched here. The four fixed paths come from the current Bionic module and Linux x86 UAPI layout; absence remains an error, with no alternate path search or source execution. The intended checks are public setfsuid/setfsgid aliases to compat *32, distinct old 16-bit syscall numbers, native numbers and the private library header integration point. No stock filter, namespace, capability, UID/GID or resource setting is changed.

The already reviewed seccomp4 reader helpers utc/digest/identity/observe are AST-identical. Each file is held and compared with its named identity before/after, fully hashed, and reported with exact bytes. This uses one bounded gzip envelope. CPU 25%, memory 128 MiB, nice 15, 30 seconds; no service, build or Android actions. An actual reader PASS would prove only current source bytes, not an installed Bionic/ART or kernel binding.
