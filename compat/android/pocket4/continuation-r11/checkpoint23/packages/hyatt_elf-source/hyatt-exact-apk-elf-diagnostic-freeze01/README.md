# Hyatt exact APK native-member diagnostic01

SOURCE_ONLY / UNRUN. Root is the only dispatcher. This childless reader has no App nonce, APK mutation, package mutation, process execution, namespace entry or file write.

## Evidence binding

The current metadata report is exactly 13,115 bytes / SHA256 4e087d0a84cb0a640206d25cb3c958181b6aba11e7869f60eadff96caad7a0ce. Current UID is 10138 and version is 26090096. The three current APK filenames, complete byte counts and SHA256 values exactly equal the historical Hyatt set: base.apk 138,951,987 bytes, arm64 split 1,192,682 bytes and xxhdpi split 654,090 bytes, total 140,798,759 bytes. Current paths and current held identities are separate from the old epoch.

The historical failure remains JNI_OnLoad returning -500 in libdexprotector.so. Its internal cause is UNKNOWN. This reader neither accepts that JNI return nor modifies the library. No current App process maps or ELF BuildId have yet been observed.

## Fixed read and output boundary

The unchanged R6 SourceContract/current8 guard is checked before and after. The existing root action lock is opened read-only and acquired once with EX|NB. The original fixed current init pidfd, six namespace descriptors and root are held; every explicitly acquired FD is journaled before qualification. The three exact APK paths are traversed from that held root with no-follow components.

Every APK must retain all nine exact metadata fields from the complete bound report. All three complete SHA256 values must pass before ZIP parsing and again afterward. All original APK shape predicates remain unchanged. Total APK reads are capped at 384 MiB; one pread is at most 1 MiB. Each central directory is capped at 8 MiB and 65,534 entries. No filesystem directory is listed.

Only lib/arm64-v8a/libdexprotector.so is eligible, across exactly these three APKs. This member path is a fixed diagnostic target, not a previous observation. Missing or duplicate members fail without fallback. Stored and raw-DEFLATE contents are bounded to 32 MiB compressed and 64 MiB uncompressed, with exact CRC, complete stream and local/central metadata checks. No member is extracted to disk.

Output is capped at 128 KiB and contains complete member hashes, ELF class/machine, BuildId if present, the exact JNI_OnLoad dynamic symbol and numeric visibility, and at most a 16 KiB linear instruction-window hash with 128 public opcode metadata rows. Only fixed JNI constants and -500 are named. Arbitrary symbol names, string tables, code bytes and APK/ELF bytes are not exported. A static constant or RET does not establish an executed return path.

The observation window is 120 seconds from main entry, final qualification is 150 seconds, the one-shot alarm is 165 seconds and the outer request is 180 seconds. The request has 256 MiB memory, one CPU and nice 15. No observed throughput or runtime memory peak is claimed. First errors and all recorded close/final-guard errors are retained; none can produce collection_complete=true. Cleanup covers explicitly acquired journal FDs and propagated original R6 errors, without an ambient process-wide FD equality claim.

## Validation and reproduction

Fifteen in-memory controls call the production ZIP/ELF functions. They cover SysV/GNU hash positive cases, fixed-immediate metadata, truncated headers, wrong machine, or invalid mapping/stride/size, stored/deflated members, duplicate target, CRC, expansion and truncated/trailing streams. They run before private Main source loading in the request. Python compilation and these controls have NOT been executed during preparation.

V8 reproduction is available in reproduce.js. Supply all files as an object keyed by relative path. It reconstructs the complete request and diff, verifies historical/current inputs, and checks sixteen lifecycle helpers plus the nested original Main/source guard byte-for-byte against the previously frozen fstat source. Root dispatch remains separate. The original fstat source's successful execution does not qualify the new ZIP/ELF parser or reader.

## Static peer review

The Android collaborator independently read the exact ZIP/ELF core (20,456 bytes) and all 15 pure parser controls (4 positive, 11 negative: 5 ELF and 6 ZIP). No concrete first-run fixture failure or incorrect qualification was found within that source scope. This did not execute Python or inspect the full Main/FD finally or actual APKs. Numeric dynamic-symbol visibility does not prove loader export or successful lookup. The production source and request are unchanged by this documentation clarification.
