# Candidate06 complete engine qualification binder

This is an offline request generator. It does not contact Pocket4, upload inputs,
execute an engine or test, start a service, or operate Main. The default command
prints a plan. Generated requests require separate root review and dispatch.

## Exact build prerequisite

The binder accepts the five actual receipts from only
`full-build-combined06-go5-streaming-01`: preparation, inner terminal, Main fence
terminal, native-engine inputs, and native-engine source/artifact receipt. Each
local receipt must be paired with its exact remote path and SHA-256. It checks
the completed artifact gate, resource/cleanup outcome, candidate06's entire
925-file map, its three-file ancestry from candidate05, the actual NOFILE host
and Android proofs, six signal source hashes, and the compiled450 versus Go5
runtime450 distinction. An admission failure or an incomplete build is refused.

Revision 02 requires the successful Main terminal from `build-fences-02`. It additionally binds the actual `build-fences-02/readmission.json` and the exact retained failure at `build-fences-01/terminal.json` (SHA-256 `8b74d6b0351db5823c4e183c222783b94ada34369f1eede78289ac3b6d20146a`). The latter remains a resource-admission failure, never a successful-build prerequisite. The historical memory sample explains the separate request and cannot replace the unchanged live 13 GiB / 2 GiB admission.

No future build success or artifact hash is supplied in the template.

## Sequential qualification

1. `host`: produce fresh input data and check/run requests for the unchanged
   frozen `host_suite.py`. The original contract has 3,793 registrations, 3,791
   executions, 3,788 completed tests, two disabled tests, and three exact skips.
   The wrapper checks all names and output, the actual binary plus three mapped
   libraries, all three corpora, the prior exact R16 baseline, CPU 6, resources,
   and Main before/after. No filter reduction, sharding, retry, or tiny-suite
   substitution is introduced.
2. `android-prepare`: require the new complete host receipt and generate a fresh
   private preparation request using the unchanged frozen R5 sources. The
   operator supplies a new nonce, host UID, and subordinate-ID range; the
   existing live R5 admission checks still determine whether these are unused.
3. `android-check`: require the new actual prepared receipt. Generate the
   unchanged R5 read-only check and an independent root-review template whose
   `admitted` field is false.
4. `android-runtime`: additionally require the exact independently admitted
   root review. Bind the existing once-only controller to the new inputs,
   prepared receipt, host result, paths, nonce, and review. It runs the same four
   original ARM64 cases: r2 SVC, r2 handled SMC, r2 default SMC, and r3 saved-mask
   editing. Its existing held-namespace entry, Main checks, bounded execution,
   exact package removal, and whole owned hierarchy cleanup are preserved.

The generator changes data bindings and owned names only. It does not rewrite
`host_suite.py`, `prepare.py`, `prepare_runtime.py`, or R5 `run.py`. The original
`signal-mask-r1` arm and `a04` claim-kind text inside those frozen implementations
are historical schema labels, not claims that this is the old run.

## Usage

Copy `binding.template.json` to a new local file and fill only actual values.
Compute the complete binding file's SHA-256. For each phase, use a new local
output directory:

```text
python3 -B make_qualification.py host --binding /absolute/actual-binding.json --binding-sha256 ACTUAL_SHA --out /absolute/new-host-requests
```

Use the subsequent phase names above as the corresponding actual receipts
become available. `remote-inputs.json` identifies the exact new JSON input and
hash that root must stage before dispatch; this generator performs no staging.
All source, reference, and output pins are recorded separately from execution.

## Scope

Candidate06 retains metadata generation flag 0. These gates qualify the new
compiled engine's full existing host suite and the four specific signal
contracts. They do not enable the metadata path, provide ART/factory lifecycle
qualification, deploy Main, or prove any commercial app production ready. The
separately completed NOFILE 26-case Android controls remain separately scoped.

The local validation checks syntax, exact reference bytes, default PLAN, the
original runtime argv shape, and refusal of an incomplete binding. It executes
no target engine, test suite, Android process, or remote controller.
