# Commoncap capability ceiling and consent

Frozen4aabde6a completed the original full pipeline in581.185s: core363
with all124 required cases, OSTD230 with original3 TCG VMX soft skips,
allocator20 and MLSDisk15. The same fresh ordinary ELF passed boot18,
SGID30, ownership12, proc12, memfd4, signal22, lifecycle164, stat54,
TRACEME15, supplementary DAC6 and the original commoncap16 probe.
All guest/probe exits were expected33/0, without timeout; original tracked
source blobs remained identical. Original512MiB and deadlines are unchanged.

The Linux-referenced controlled child first retains permitted CAP_CHOWN
with effective capabilities empty: all eight sensitive reads must fail.
After dropping its permitted set, the same eight operations must succeed.
Original690 wrongly allowed the first eight operations; those raw failures,
the exact source and unchanged probe binary identity remain in this archive.
The fix checks the caller's effective set for FSCREDS and permitted set for
REALCREDS against the target's permitted set, within the original credential
transaction. TRACEME uses the separate original consent contract and a
coherent parent capability snapshot. Three new original-owner tests ran.

This closes the selected commoncap access and consent defect. It does not
establish full Linux capability, namespace, ptrace or SCM parity, general
memory recovery, actual GPU/ARM/mobile kernel support or the final persistent
Root/Host/Session CPU G2. See [the byte manifest](publication.json),
[source-bound receipt](../commoncap-4aab.json), and
[module contract](../../../../docs/agents/COMMONCAP_ALIEN_ACCESS.md).
