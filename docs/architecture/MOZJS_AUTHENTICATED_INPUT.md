# Authenticated mozjs secondary input v2

This additive source candidate implements the fixed supplier verification
workflow in `contracts/mozjs-authenticated-input.v2.json` and
`manifests/mozjs-authenticated-input.v2.json`. It preserves all 635 original
source paths, including every v1 API, body, contract, test, finite false claim,
original native case, PIN, Cargo lock, CI command and budget. The new seven
paths require later explicit module/CI invalidation registration and independent
composition acceptance. That integration is incomplete in this narrow package.

The original v1 source profile remains a custody profile with
`attestation_verified=false`. Independent external evidence at
`work/mozjs-official-crypto-independent-facts/independent-crypto-policy-review.json`
SHA256 `d9405a237fe20e0228a78c18d8cd5e96dfdf75bce5d4fcbd9f4cd2fad65f1f5c`
records actual official verification of the exact supplier input. It belongs to
its own source/tool/archive tuple and is not qualification of this v2 source.

## Fixed byte selection and public API

`verify_inputs(archive_path, bundle_path, tool_path, evidence_parent)` invokes
the actual verifier and returns a diagnostic observation. Its result is never
an accepted argument to the build entry. The build entry's public signature is
`build_authenticated_native(upstream, original_lock, archive_path, bundle_path,
tool_path, target_parent, profile)`. It performs verification internally before
running the original Cargo command. Callers provide paths that select bytes;
they cannot provide verification flags, stdout, booleans, tokens, arbitrary
Cargo argv, trust roots or an expiration bypass.

The archive is the original 19381534-byte release asset 527403045, SHA256
`c5f93d7f9f1b450e2a608b5e7378c95ec8fa9f3689bdfe1f6ad548e434c3107b`.
Its original 32 MiB limit and `SealedArchiveLease` remain unchanged. The bundle
is the complete independently observed 14373-byte index 1 SLSA bundle, SHA256
`7077565ec6de92705ae4f742ed68f59cb88e5132a50153f578496cea023a2e88`,
within a new 64 KiB limit. Index 0 release provenance cannot satisfy this policy.
The gh 2.102.0 tool is the exact 42086560-byte Linux amd64 binary, SHA256
`7469124f706944133d6a169691dd1c6c3511b12e85878d255e044e2948df4c9b`,
within a separate 64 MiB limit. Its checksum bootstrap uses official HTTPS API,
checksums and the tar member; tool artifact attestation was not independently
verified. Matching an official API digest alone is not artifact attestation.

All three byte inputs are held in Linux memfds with write, grow, shrink and
seal seals. The tool is mode 0500; other snapshots are mode 0400. The child inherits only the explicit archive/bundle/tool FDs. The executable
passed to actual exec is an internally formed child self-FD path of the same
sealed tool object, bound by dev/inode/size/seals/full SHA to the parent lease. Hashing a mutable path and executing that path is not
this workflow. Complete proc-path SHA, size, object identity and seals are
read back before and after actual verification. Original path replacement
after admission cannot change the original held snapshots. Creator PID/thread,
reentry, closed descriptor and replaced object checks remain enforced.

## Actual verification and certificate policy

The official bundle loader requires a .json/.jsonl filename and has no stdin
or explicit-format input. A bare proc-FD path is refused. Binding the anonymous
memfd as a named file was also refused by the observed kernel; those actual
failures remain external immutable facts. The child instead creates a private
64 KiB tmpfs, copies complete bytes directly from the original held/sealed
bundle FD, checks size/SHA/object/seals before and after, and remounts the
whole tmpfs read-only. The internally owned directory FD survives exec and
provides the .json path within that same namespace. Actual writes must fail
with EROFS; file size/SHA/dev/inode and readonly mount are recorded. This named
consuming snapshot has the same bytes but a different inode/device. It does
not have the original four memfd seals, and original-bundle-FD consumption is
explicitly false. No mutable alias or fallback is accepted.

The child maps the current host UID/GID into private user/mount namespaces and
sets private mount propagation. It drops the full kernel capability bounding
set, locks NOROOT/NO_SETUID_FIXUP/NO_AMBIENT securebits, empties capability sets
and enables no-new-privileges before exec. Actual gh CapEff/CapPrm/CapInh/CapAmb/
CapBnd must all read back zero; unavailable readback refuses success. Namespace
UID zero is not host-root authority. The parent remains the original lease
creator and retains all original snapshots through the complete group.

The official command uses a fixed GitHub hostname, `servo/mozjs` repository,
exact certificate SAN, exact OIDC issuer, signer/source digests, main ref,
SLSA predicate type and denial of self-hosted runners. It uses the tool's
default authenticated TUF roots in a new private cache. It has no custom-root,
off, expiry or network-error bypass. Inherited tokens, config/debug selectors,
and trust-root environment selectors are absent from the verifier environment.
Private namespace/status diagnostics use a separate bounded channel, leaving
official verified stdout unchanged. Raw default-cache bytes remain private diagnostic evidence; callers cannot
replace the verification root policy through those records.

Actual verifier exit 0 is necessary. Its independent 60-second total lifecycle
contains a 2-second termination grace. Each stdout/stderr stream has a 256 KiB
bound; JSON also rejects duplicate keys, nonfinite numbers and excessive
structure. A single result must contain the same held bundle and the same
decoded DSSE statement, with exactly one matching archive subject/digest.
The certificate's exact 22 fields bind issuer, SAN, source/owner identifiers,
source/signer/config digests, ref, run/attempt, event, public visibility and
GitHub-hosted runner. Predicate metadata is not certificate identity authority.

The same verified bundle's exact signed certificate DER is also checked. A
bounded canonical DER parser reads OID 1.3.6.1.4.1.57264.1.24 `TokenSubject` as
`repo:servo/mozjs:ref:refs/heads/main`. The authenticated Rekor signing time
2026-08-24T09:46:29Z must equal the fixed historical observation, lie within
the certificate 09:46:29–09:56:29Z interval, and within the fixed official run
08:29:23–10:22:14Z interval. This uses verified historical time, never a
current-time expiry bypass. The `verifiedIdentity` display's empty wildcard
issuer is recorded separately; exact issuer policy uses the authenticated
`signature.certificate.issuer` field, not that display.

The private parser does not verify a signature by itself. Synthetic parser
fixtures and changed certificate fields only test parsing/policy rejection.
Actual official-tool bad DSSE, changed signed subject and index 0 executions
must remain separately identified actual nonzero observations. No test creates
a fake signed wrong-authority certificate or a transferable proof token.

## Build custody and diagnostic boundary

The explicit native-owner/approved-startup profiles retain the original Rust
1.97.1, checked-release, locked, no-default-features, bundled/js_jit,
`--no-run` command, 10800-second Cargo limit and 5-second termination grace.
The original prepared-source helper runs unchanged in a bounded private Python
child so native Git failure payload cannot reach the public CLI. Its original
30-second Git operation budgets remain unchanged. Interpreter/PATH, inherited
Git configuration and local prepared-source trust remain ordinary execution
inputs; they are not authenticated by the gh binary's bootstrap receipt.

The build refuses inherited MOZJS/cache/profile/target/wrapper/rustflags
overrides before input admission. It creates an exclusive initially empty
target outside upstream for every invocation. The same three held snapshots
remain retained during verification, the original Cargo leader wait and
ordinary process-group shutdown. A nonzero Cargo exit remains failure.
Cancellation/timeout terminates and waits for the group before release. If
bounded shutdown cannot prove the group absent, the original lifecycle owner
retains the aggregate custody and the workflow refuses success. This does not
cover supervisor SIGKILL, arbitrary Python/native opcode interruption, escaped
process groups or hostile in-process modification. Python custody is not a
hostile-code sandbox or language-unforgeable capability.

The CLI emits fixed `MOZJS_AUTHENTICATED_INPUT_REFUSED` for failure. Private
bounded `stdout.raw`/`stderr.raw` and fresh default-root cache bytes preserve
actual verifier diagnostics. It does not interpolate error, environment,
credential or raw verifier payload into a user failure message.
Cargo stdout/stderr are also retained privately with independent 16 MiB bounds
per stream; reaching the bound refuses the new profile. The original Cargo
argv, 10800/5 time budgets and lifecycle owner remain unchanged. When a leader
exits, the bounded capture drains buffered output briefly and then stops its
ordinary group within the original two-grace shutdown window; a descendant
holding a pipe cannot extend that shutdown to the complete build deadline.

Example explicit verification, which executes the sealed official tool:

```sh
python3 tools/verify_mozjs_authenticated_input.py --archive /absolute/archive \
  --bundle /absolute/index-1-slsa.bundle.json --tool /absolute/gh-2.102.0 \
  --evidence-parent /absolute/private-evidence-parent
```

The source-only checker, without these optional selectors, executes no tool,
Cargo or native case. The explicit build entry is
`tools/build_mozjs_authenticated_native.py`, with the source-defined profile
and the seven required byte/source/target selectors.

## Remaining qualification

Current source and host tests do not prove actual Cargo archive consumption.
Upstream can prefer a cached OUT_DIR archive; a fresh target and MOZJS_ARCHIVE
assignment do not by themselves prove all descendant reads, copy, extraction
or linkage. The next actual run must bind full exact-PIN source, the held
archive path/object, child PID/group, complete OUT_DIR archive SHA, linker
outputs and exact final ELF. It must then run the unchanged original six
native cases on that final source tuple. No earlier source, Cargo, native,
hosted CI, installed service, human, hardware/HSM or production result is
transferred to this candidate. The upstream helper's ignored nonzero status
remains a static observation until a separate actual failed-helper build
execution demonstrates it. Production-ready remains false.

## Execution directory and diagnostic directory

The private bounded process helper keeps its execution cwd separate from the
private evidence directory. Official verification and the prepared-source
helper retain their fixed private evidence cwd. After unchanged
`verify_prepared` succeeds on the selected absolute upstream pathname, the
final Cargo call executes in that same upstream pathname. Cargo stdout, stderr
and lifecycle metadata remain in the separate evidence/cargo directory. The
public APIs accept no caller-selected cwd or arbitrary command. The original
v1 APIs and bodies and Cargo argv/time limits remain unchanged.

An independent short ordinary-child observation on the prior frozen v2 object
found that its Cargo call would use evidence/cargo as cwd despite having no
manifest-path selector. That retained observation is a process-helper/source
finding; it did not execute Cargo or prove archive consumption. New tests use
explicit private fixture substitutions for preparation, cryptography and the
compile selector, then execute real short host subprocesses through the full
build call chain. Their actual cwd and relative source marker reads establish
call routing only, not supplier verification, Cargo consumption or linkage.
Prepared checkout/PATH/config trust and concurrent external checkout mutation
remain unqualified execution inputs. Any final qualified build requires its
own whole source, input and output readbacks.

## Canonical build directory selectors

A separate adversarial review of the cwd successor found that lexical
`Path.absolute()` containment accepted a target parent spelled with `..`
which resolved inside the upstream checkout. The new selector guard requires
both upstream and target parent to be existing canonical absolute directories,
with neither parent aliases nor symlink aliases, before input admission or any
evidence/target allocation. Canonical same-source and descendant target parents
remain refused. A canonical external sibling still runs the unchanged complete
host call-chain case, whose short real child proves cwd/held bytes/group
cleanup only. External `..` spellings are also explicitly refused; callers
must supply the canonical directory spelling.

The five added host tests use real temporary directories and symlink aliases
and assert refusal before admission/allocation, with no directory changes.
The original 33 v2 and 24 v1 tests, fixed Cargo argv and budgets remain intact.
This selector guard does not establish custody against a concurrent path
rename, verify a Cargo run, or qualify installed/native/production execution.
