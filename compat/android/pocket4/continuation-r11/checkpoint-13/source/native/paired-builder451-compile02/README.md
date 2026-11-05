# Paired builder451 runner revision 02

The Rust451 source manifest, four source payloads, original seven projection tests and fifteen pairing tests are unchanged. Compile01's actual FAIL is preserved. Its test19 child returned zero but mkfs.erofs inserted output between libtest's test-name prefix and its final ok, so the old contiguous-name gate rejected it.

This fresh runner uses Rust1.93's supported, deprecated --logfile option. Official tag sources are retained as references; they are not a claim that source bytes are tied to the installed toolchain. The actual held test ELF must advertise --logfile in --help before any focused test executes. Each test gets a create-only 0600 file, held across execution, and exactly `ok <full exact test name>
` is required from that same inode. Ordinary stdout/stderr remain complete. Exact registration, --exact selection, running count, zero ignored/measured/failed, filtered count and successful summary still agree. Only the original nested fakeroot case permits its two stdout summaries; its outer independent result is exactly one record. Original timeout, process-exit and child-retirement gates remain unchanged.

Default PLAN and eight local parser controls ran; the positive parser fixture combines actual noisy stdout with a clearly synthetic logfile line. No Rust compile, installed libtest or image test was executed locally. Root alone dispatches the frozen fresh request. This does not qualify ART/APEX signatures, enabled metadata lifecycle or all apps.
