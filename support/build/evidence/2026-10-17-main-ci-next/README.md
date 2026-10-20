# Exact CI readback and main integration, 2026-10-17

The previously pending CI observation is superseded for exact A01 commit `cdf308e751e561328c556ca2ece86056d15809a0`: three exact-head check runs and both requested workflows completed successfully. The host job ran 27 + 27 + 30 + 30 + 28 + 28 = **170 host test executions**, checking out synthetic merge `ae353aa12559fa486b73637b0c2f10d024ef366f` against old main `40ca002fac0726b366726d3353916637b29adeae`. These are host fixtures. CodeQL checked out cdf itself. Original API reads span 03:58:16–04:01:06 UTC.

Main `b75f8e4ca6f55495a10d1652107c26010cdede7d` was then integrated through formal two-parent commit `09aea79c71dc9f48ba519757078dd8a20f5c8fb3`, tree `23eba5d298ff7db98f0ba6cd8b1c363094639cd4`. Ordered parents are cdf, then b75. The only imported path is `.github/workflows/g0-contracts.yml` (+13 lines), exactly main's blob. GitHub creation used that single tree entry and a non-force update with the expected old branch SHA. All 9,128 recursive Git entries, including modes, types and object IDs, matched the local staged tree. The root README remains empty and the kernel tree remains `6b3cab110aa6d30d5b89f99c4389c9c3e01022da`. The offline verifier also reconstructs every captured Git tree object hash.

For the merge, source verification (118 files), the A05 host smoke and staged whitespace check returned 0. The newly conditional C guest compilation was skipped because `tests/kernel/control/queryabi_guest.c` is absent from this exact tree. There was no guest compile or guest execution in this phase.

A separate fresh readback at 04:09:41–04:11:09 UTC found **09aea's two exact workflows/checks still queued, conclusion null**: host run 39001122216 and CodeQL run 39001120343. Its predecessor's green checks do not establish this merge's CI result. PR #22 was API-mergeable/unstable against b75, while actual main had advanced to `47288c4465720d125658b392efc655b333c90868` (three A02 paths, no kernel/build changes). That old-base PR response does not prove mergeability against the newer main. These are fixed historical observations, not a claim about a later HEAD.

Both retained legacy-status wrappers expose an empty `statuses` list. The original audit report describes aggregate status as pending, but its retained wrapper omits that aggregate field. This phase preserves that report and explicitly limits direct verification to the exposed empty context list; CI success or failure comes from the exact workflow/check records.

All original readbacks, logs, the historical report and publication receipts are retained byte for byte in the split deterministic gzip archive. `source-index.json` binds every regular member; no extraction is needed. Parts are at most 2 MiB. This phase does not change A04/A05/A06 implementations and does not establish any new kernel, W1, KVM, AF_UNIX, cross-host or G1/G2 result.

```bash
python3 -I verify.py
python3 -I -O verify.py
sha256sum -c SHA256SUMS
```
