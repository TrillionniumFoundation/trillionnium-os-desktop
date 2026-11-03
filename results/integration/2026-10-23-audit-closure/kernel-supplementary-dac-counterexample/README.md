# Supplementary-group DAC compatibility failure

The same static public-fixture probe passes all6 Linux checks. Root creates a
0640 file and0710 directory owned by Root with group60002. An owned child runs
as UID/GID60001, actual supplementary group60002, zero capabilities and NNP1.
It must be allowed to read the file and search the directory while being denied
write. A separate owned child with no supplementary groups is refused all3.
Both children are reaped and the fixture is removed.

On original0252 Asterinas, legitimate supplementary-group read and search return
EACCES. The write and nonmember refusals remain correct. Probe42/rawQEMU33 in
0.816s confirms a compatibility failure at the original512MiB/120s limits.
It is not a privilege-bypass finding. The actual group identity is recorded,
so correctly setting groups alone cannot fix it. The next independent kernel
phase must use supplementary membership in the original DAC group decision,
then pass this exact Linux-backed oracle and its ordinary regressions.

Original C/helper, build output, Linux/native serial and executable/kernel hashes
are retained. No unrelated process, production file, binary or private state is
published. See [the complete manifest](publication.json).
