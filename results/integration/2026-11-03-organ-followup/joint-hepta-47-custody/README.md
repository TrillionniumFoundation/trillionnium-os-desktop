# Original custody test: observe physical release inside the original deadline

The original four-package execution at Hepta 26a remains failed. Its Agentd
custody test failed twice at the final physical-lock acquisition assertion.
The one-file successor `47b3335357c5607e2f09791fcb028ee1207a9cd7`, tree
`eab8c04e0bd441ee990356f3bf98c6f4d1e59eda`, changes only that test's completion
observation. The same one-second deadline now waits for both Weak retirement
and the same contender's actual lock availability. Production custody, the
original inode, held-lock refusal and fencing assertions remain unchanged.

Original job `1a1a3ce2d75-96a-7769` actually completed successfully on Rust
1.96, exit 0, complete output, with no outer timeout or cancellation. The
original formatter, scoped Agentd fix and one exact custody case each passed
on the clean source. The selected test passed on its first attempt; 554 other
library cases were skipped. No full Agentd suite was repeated.

[The complete pipeline](custody47-raw/pipelines/47b33353-custody-v1/result.json)
is 2,148 bytes, SHA256
`67199fd3d335184f15addf3b11f2e3b384d9911eb075f6f8f800182d876b3559`.
All three command results and their complete stdout/stderr are retained,
including empty logs. [The original index](source-index.json) binds 16 files,
206,421 bytes. [Independent review](independent-review.json) rehashed all
sixteen, matched ten complete files to the original RPC text and hashes,
checked each command's log receipts, and checked the authoritative process
status and complete 6,484-byte job stdout through original byte cursors.

The earlier [26a full Agentd result](../joint-hepta-26a-tests/README.md) stays
546 passed / 1 failed / 60 skipped. The later canonical source and its
documentation-only successor retain these actual execution identities.
This selected test grants no installed Root, user admission, Notes/Calculator
effect or restart qualification.
