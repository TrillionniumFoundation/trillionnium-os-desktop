# Producer15 matching compile and ordinary requests

Create-only candidate/target from actual successful producer14 compilation.
The generator independently verifies producer14's matching 37 relay, 122
supervisor and 7 IPC result; this does not qualify producer15. All 32 inputs,
full source inventory, four binary targets and explicit two-library --lib
--no-run selection remain fixed. Only the four separately frozen source15
candidate files are overlaid. Original producer13/Owner14 failures remain.

Compile uses CPU1/1GiB/600s; ordinary uses CPU1/512MiB/180s and the same held
ELF/source/resource/child-cleanup gates. Ordinary execution stays non-root and
has no Cargo, namespace, Android, pressure or network effect. The complete
source inventory is checked before/after both stages; no old target is reused.

The ordinary template is not executable until the new actual successful
compile result is fully retrieved and its SHA is externally supplied. It
expects 39 relay tests, 128 supervisor tests, two exact public retirement
controls (1 passed/38 filtered each), seven IPC controls, the original worker
context test and actual entry ABI3. These counts are expectations only. Six
supervisor tests exercise actual owned-child wait facts and the production
audit method; two relay tests exercise held pidfd post-error evidence. These
ordinary children are not a full production Owner, broker or Android init.

No prior failure is replaced. No worker retirement, authority, LMKD admission,
namespace, capability, PSI, Stop authorization, network/resource/claim cleanup
predicate is relaxed by these controllers. The resource_guard.py bytes are
identical to14: usage is observed, but hard SwapMax0 and whole-invocation
resource qualification are not claimed. A candidate ordinary PASS would still
not prove first ACTIVE or identify Owner14's original SIGHUP/boot cause.

Main's observed pids.max change remains unresolved. This freeze contains no
Android Owner runtime plan or request and cannot admit through an old Main
fence. Root alone dispatches the reviewed matching requests; this generator
has not dispatched anything. No new Rust result is asserted.
