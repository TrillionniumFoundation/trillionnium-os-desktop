# Final main synchronization

After the frozen review evidence was published at
`c3087947982e54500780d32a3f2e0bdd60547caf`, main advanced again to
`99924da27531876d7c383d490175d06d8f200856`. The merge completed locally without conflicts.
Only the four main-owned CI/status/A05 consumer files listed in `report.json`
were added by that merge. No kernel, OSTD or A05/A06-owned core source changed.

The added original `sh tests/kernel/control/run-host-smoke.sh` passed with the
host C compiler. It verifies HOS2 request/response byte validation and invalid
frames, plus the actual Linux `/dev/null` ioctl refusal. It does not execute an
Asterinas HOS2 driver. The fixed source gate still passes118 inputs and the
project root README remains0 bytes. Complete logs and source gate are retained.

No complete-kernel, OSDK or Linux guest result was rerun or upgraded for this
main-only merge. The immutable preceding review report retains all original
source bindings, full serial, build/boot hashes, 22/22 and later1/1 capture
results, as well as the Linux24/28 diagnostic failures and cancellation checks.
A00 retains the final main integration decision.
