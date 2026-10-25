# Datagram user-copy fixture initialization

The original full four-suite run of diagnostic source
`adbc15a9d1f8e7490240923b681ae694f815479b` did not pass. OSTD 229 and allocator
20 passed their strict raw-33 gates; core stopped with raw 65 at
`actual_user_copy_fault_refunds_unpublished_pages_and_preserves_receive`.
MLSDisk did not run. Both original-policy SCM_RIGHTS cycle reproducers had
executed successfully before that failure, demonstrating the leak and original
receive-based cleanup; their success is not a fixed-source qualification.

The failed core ELF is retained under
`/data/asterinas-audit-build.8tdrjboi/unix-rights-cycle-native-adbc-01/`, SHA-256
`a41c34e3ba44614c0bff7e4ae6bb1dd15c729afb5d3f7e8d57b4f5c667bb6dfe`.
The original serial SHA-256 is
`39bef3ae69880fe5b97d80c00c37dc60f16244c6111c3cb1a64cc37a78620b64`.
The complete source snapshots and failed result remain unchanged.

A private Unix-socket QEMU RSP diagnostic used that same retained ELF. It first
broke at the exact test entry, then at the first `core::panicking::panic_fmt`.
The first panic location was `datagram/message/tests.rs:140:71`, the
`vmar.vm_space().reader(BASE, PAGE_SIZE + 17).unwrap()` call. OSTD returned
AccessDenied because the VMAR page table had not been activated. This occurs
before `try_send` or a copy into a queued payload. The later error at
`thread/oops.rs:53` was a second panic trying to downcast the test panic payload.
The debugger trace is retained separately in `unix-datagram-copy-rsp-01` and is
not a passing test run.

The fixture now calls the original `crate::thread::init()` before spawning an
associated-VMAR thread, exactly as the pre-existing
`associated_vmar_is_reactivated_after_context_switch` test does. That initializer
installs the original post-schedule VMAR activation and real user-page-fault
hooks using their existing Once owners. It does not manually switch page tables,
replace the copy implementation, edit the panic policy, relax quota assertions,
or change test deadlines. All original actual EFAULT, partial-reader,
unpublished-page refund and queued-message preservation assertions remain.
The repaired source requires a new complete native run; this diagnosis alone
does not qualify it.
