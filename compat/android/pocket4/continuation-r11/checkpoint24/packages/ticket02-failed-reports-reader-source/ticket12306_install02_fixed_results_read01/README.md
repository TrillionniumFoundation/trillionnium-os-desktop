# Ticket12306 install02 fixed failed-report reader

SOURCE_ONLY; this agent has not dispatched or executed this reader. Root alone may submit exact-request.json.

Seed tree b03735ad15e00042506cf5485d55d67509369c42 is preserved as all five original leaves under references/. The authority consists only of the exact original stdout and terminal for actual job 1a1b32bc2a2-fc05-80e9. Both stdout summaries report ok=false and the terminal records failed/exit 1, stdout 1042 bytes, stderr 0, complete durable untruncated output and no retry, timeout or cancellation.

The only requested files are:

- /home/alex/work/pocket4-owned-ticket12306-qa-r1-install-state-02/result.json: 3498 bytes; SHA256 8953cdd7a45d0c12624e3654e31cadfcfad72c045aea325b4d94bd7785fb44f5.
- /home/alex/work/pocket4-owned-ticket12306-qa-r1-install-state-02/stage-result.json: 12969 bytes; SHA256 8761ae4760095dd408f32ebdfba40d9b31fff47cd2b199235d75bc595371d499.

Each file is fully read twice. The original read_exact_file, summary gate, all read loops, full SHA checks, no-follow traversal, held/named identity comparison, signal/alarm handling and FD finally are byte-identical. The original failed-terminal semantics and all resource/time/output bounds remain. There are seven exact source binding edits. The request differs only in stdin and a new Ticket02-specific key: sudo isolated/no-bytecode Python, 128 MiB, one CPU, nice 15, outer 30 seconds; the source keeps 10 seconds per file, 20 seconds for collection, and a 131072-byte output bound.

## Scope correction and outcome limits

The original seed scope.json incorrectly says scope_unknown_until_full_worker=false. That file remains byte-identical for provenance; it is not an authority and contributes no runtime gate or outcome. The correct derived statement is scope_unknown_until_full_worker=true: the worker original has not been read and installation remains UNKNOWN/unqualified. No worker path or pin is guessed. This request reads only the coordinator and stage reports; any later worker read must be separately bound to their actual originals.

The known primary summary is the coordinator install-state fence failure. The secondary summary is coordinator_final_Main/OWNER_SINGLE_DIRECT_CHILD_REQUIRED. Neither is rewritten, suppressed or used to infer whether installation occurred. The original installation is not replayed. The reader performs no Main/Android operation, namespace entry, explicit file write, child or directory scan; standard-library import I/O and ambient FD equality remain outside those source counters. Collection success is not installation or runtime acceptance: both qualification booleans remain false.

## Reproduction

Fetch all FROZEN_PINS.json leaves as exact UTF-8 plus the pins file. Evaluate reproduce.js as a function and pass the relative path-to-original-string map. It checks every body pin, regenerates source/request/edits/proof/source.diff, and verifies the complete inverse to the original Hilton source. It needs only V8 and no filesystem or Hepta. Do not print complete nonce-bearing authorities or requests in chat.
