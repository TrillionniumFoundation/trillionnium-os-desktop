# Audio compiler evidence guards

These helpers validate the original Ninja graph, a source-to-linked-object path,
the exact compiler command, its retained response bytes, and a successful Ninja
log entry. An order-only dependency, a declared command that was not observed
in the successful log, or file presence alone cannot qualify a compiled bridge.

The Audio bridge is unconditional source. Its compilation does not require the
unrelated Native bridge feature macro. Passing `None` for that macro preserves
all source, output, architecture, command-chain and response-file checks. Actual
valid header dependencies additionally bind the exact compiled object generation.

Run `python3 -m unittest -v test_ninja_audio_proof.py` for 12 portable controls.
They reject wrong or multiple translation units, wrong outputs or architectures,
non-compiling modes, shell masking, substituted objects, nested response files,
stale dependency records, order-only linkage, and changed logged response bytes.

The command-hash implementation must also be tested against the actual pinned
Ninja binary. The production workflow ran two tiny independent fixtures, with
and without a retained response file, and verified exact command hashes and
nanosecond output mtimes against the real Ninja log. Four changed-command or
changed-response cases were rejected. These controls start no Soong build and
confer no Audio artifact, signature or runtime qualification.

A release consumer must join these guards with the actual successful full build,
owned process retirement, restored source, original effective translation-unit
bytes, exact linked payload ELF, whole-APEX signature and content validation,
and fresh runtime tests. This package contains no host or job identities, private
source allowlists, signing material or raw build logs.
