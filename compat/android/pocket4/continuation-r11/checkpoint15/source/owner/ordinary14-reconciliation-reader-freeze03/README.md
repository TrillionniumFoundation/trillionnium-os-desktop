# Two fixed ACK-unknown request reconciliation

Revision 03 performs one UID 1000 read-only scan of the fixed worker jobs root.
Targets are original ordinary14 d383190c... and the original native snapshot
result reader 1abe8d99... . Each target has its own full execution tuple and
stdin byte-length/SHA. The original requests are not executed or resubmitted.

Shared argv is not request identity. Only full execution-field matches may open
fixed stdin.bin. A different length reads no stdin bytes; an incorrect hash
creates no output job record. Only exact per-target stdin plus held directory
proof produces a labelled matching record. Other jobs' argv, env, stdin, IDs
and file pins are never emitted. Original request.json has no idempotency key.

All prior bounds remain: 4096 names, 128 KiB/request, 32 MiB input total, eight
exact labelled records, 64 KiB JSON, checked ten-second monotonic deadline;
outer reader CPU1/128 MiB/nice10/30 seconds. Each target has its own outcome
and UNKNOWN execution state. NOT_FOUND_AT_OBSERVATION never authorizes replay.

Revision 01/02 were not submitted and remain unchanged. Thirty-four local
parser/matcher/owned-file controls passed; real jobs metadata, ordinary14,
Android and the snapshot reader were not executed by those tests.
