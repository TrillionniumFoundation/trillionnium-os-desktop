# Controlled dumpability lifecycle and proc stat failures

Original v1 Linux failed because its fixture assumed reset0 while the actual
host reports fs.suid_dumpable2. The original failed source/logs remain intact;
no host setting was changed. V2 observes that host policy explicitly and passes
165 observations with actual UID60001, zero permitted/effective capabilities,
NoNewPrivs1 and all owned children reaped. The guest's existing fixed reset0
policy remains a separate explicit oracle. Stat v3 passes 54 Linux observations.

V2 covers fork, threads, CLONE_VM, ordinary exec, credential changes/no-ops,
capability drop, old descriptors and proc self permissions. Linux old maps,
memory and environment descriptors return0 after exec. Its old auxv retains
the original368 bytes; the test permits empty or exactly original bytes and
rejects a new image. The actual original6c26 guest retains its red observations.
Original0252 stat discloses20 sensitive address fields when dumpability is0,
plus its GET/SET1 stub failure. Both disposable guest runs exit probe42/raw33,
retain the original512MiB/120s limits and reap every owned child.

The strict lifecycle/stat checkers pass5 host tests and reject58 mutations.
Synthetic checker tests are not positive kernel qualification. These probes do
not qualify unsupported PTRACE_ATTACH/process_vm_readv or inspect unrelated
processes. Separate frozen P1 kernel qualification is required. Original raw
indexes and prior fourteen-member evidence are unchanged; large binaries and
private state are excluded. See [the complete manifest](publication.json).
