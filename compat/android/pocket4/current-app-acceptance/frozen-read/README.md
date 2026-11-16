# Bound frozen application inputs on the complete current source

The native application reader verifies input identity and content before accepting
evidence. Its existing correction opens without following a final-component link
or blocking on a replaced special file, and verifies the opened descriptor as a
bounded regular file before reading. Original metadata, size and byte-identity
checks remain required.

This revision binds that unchanged correction and its four ordinary native tests
to the complete current source carried by public wrapper commit
16b2d43552add67b0d9a0d4e8d7337e0fdee1972.

| Identity | Fixed value |
| --- | --- |
| Public wrapper tree | 550b1989b75444932c9df76ce8cb5eda89128312 |
| Original producer parent commit | 61a38baa745483fbfb757466a1cf352febc20552 |
| Original producer parent tree | db6249e80209abeda8000eeced6d045a1d57e0a2 |
| Complete current producer tree | cbe7986c27605ea7d3167f1171a09f625dc22192 |
| Complete producer files before and after the reader patch | 2,231 |
| Producer tree after the three-file reader patch | a197f2a490bf47c611a38b4db5152e913652e417 |
| External public capsule inventory SHA256 | 469c02ab24549f7c0bdd010bbac8bf544ca7f23732ebe63fed12460865ddad0c |

The current source is a verified original capsule plus its complete 27-path
overlay. It has no new producer commit; the evidence records source_commit as
null and identifies the original parent separately. The workflow checks out the
public wrapper at its exact commit. It does not require the parent producer
commit to be available as a GitHub checkout.

## Source composition

The maintained public source verifier is pinned by complete size and SHA256.
Its source-data validation checks the external inventory, complete original
archive, original commit body, all 2,222 parent files, and every overlay before
row, replacement body and mode. It reconstructs the exact 2,231-file current
tree in a new private source directory.

The existing application helper calls only that verifier's input validation,
source replay and full-source snapshot functions. The current source's
preparation script, ordinary-suite controller and runtime entry points are not
invoked by this workflow.

The patch still changes exactly three native files:

- The reader and four ordinary tests in the application release module.
- The application's explicit dependency on the existing workspace libc.
- The corresponding single dependency edge in the current workspace lockfile.

The current 51,900-byte lockfile already contains the upstream source changes.
Those changes remain byte-for-byte present. Adding the application dependency
produces a 51,909-byte lockfile; no resolved version, registry source or package
checksum changes. The two application source inputs remain identical to the
original inputs of the existing reader patch.

The packet manifest binds all three before and after files, both complete native
trees, the complete source-row digests, this packet and its workflow. Every
other native source file and mode must remain unchanged.

## Fresh focused CI

The workflow uses Rust 1.93.0 and Cargo --locked to compile the actual application
crate and execute exactly the fourteen named release::tests:: cases. Ten are
the original release tests and four exercise ordinary regular content, empty
input, directory rejection and a static size bound. Each calls the real native
reader. No duplicated implementation, test injection or old race executor is
used.

The same actual crate then receives a locked, offline all-targets check. Source
and lockfile identities are checked again afterward, including the complete
2,231-file physical source snapshot. Test compilation and all-targets checking
do not execute the other application tests, ignored cases, documentation tests
or runtime entry points. This is not a repeat of any earlier 967-, 1,257- or
1,272-case qualification.

Source verification and Cargo commands use at most two logical CPUs while
leaving at least two others outside their affinity. Compilation uses a fresh
Cargo home and target directory, with inherited compiler overrides cleared.
The source replay, Cargo home and target directory are removed afterward and
their absence is checked. CI artifacts preserve source bookends and the actual
test and check logs.

The ordinary entry is host-regression/apply_native_patch.py with the reviewed
public capsule directory, exact wrapper and external inventory pins, a new
native source destination and a new evidence output. After the Cargo commands,
the same entry uses --verify-applied and the original --prior-report. The
workflow records the complete invocation and named-test gate.

Previous successful jobs remain evidence for their own source generations.
This packet grants no Android startup, application business-route, deployment
or production-readiness acceptance.
