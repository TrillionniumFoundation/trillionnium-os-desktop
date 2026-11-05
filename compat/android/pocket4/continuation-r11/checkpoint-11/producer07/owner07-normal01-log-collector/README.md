# Read original NORMAL01 evidence only

This fixed root reader opens only the seven named JSON receipts and eight logs
under `/opt/p4-owner07-normal-20261105-01-state`. It validates the external actual
prepared/runtime SHA values, original InvocationID and actor PID, retained exact
cleanup evidence and held state inode before collecting the allowlist. Every
member is bounded, regular, single-linked and root-owned, with full SHA and
pre/post stamp checks. No children, writes, signals, namespace, service command,
Main access, process census or journal lookup occurs. Exit zero means collection
only. It cannot promote the original failed NORMAL result or retry any work.
