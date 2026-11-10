# Clock alarm candidate04 — actual ART delta

The candidate APK `433ff501b92a21bb9265c896add220b52bc16fc4124662eaf45310da99243a0d` passed the installed ART verifier in an isolated host-owned output directory. It has **not been installed**. The current Clock APK remains `e4ff4b46a651ff3ac77397705b7b749c7fbaaeb94fe1d00818debb31dea34172`.

The actual job `1a1ad596f63-fc05-5982` finished successfully from 2026-11-05 20:14:44.280741 UTC through 20:14:45.797997 UTC. The four changed classes have stored `Verified` / `NoneCompiled` statuses. The selected alarms namespace contains 67 parsed class headers, with no non-Verified status. `NoneCompiled` is expected for the requested verify filter. This is artifact verification; it is not an App launch or business result.

## Class-loader and dependency evidence

Context04 collected the real package declarations, two XML files and JAR hashes. The `dexoptanalyzer64` filename was absent, so it was not executed. The existing OAT header-only command returned 1. Both facts remain unchanged in the original result.

Context05 used the actually listed `dexoptanalyzer`. Its special flatten-success return code was 50, and its complete output ordered **sidecar before extensions** for file-descriptor input. The exact current OAT's stored classpath and compiler command record the hierarchy `PCL[]{PCL[extensions]#PCL[sidecar]}` with no after-app marker. The narrowly bounded OAT275 byte-table review explicitly records its 944 empty/empty pairs and does not infer their cause, OAT runtime acceptance, or a Java heap class-loader capture.

The verifier passed the 52 observed Boot Classpath files and the two shared libraries through read-only held file descriptors. Only its own OAT and VDEX outputs were writable. The full Boot Classpath/APEX/tool snapshots before and after are byte-identical, as are the current Clock package/JAR/XML/OAT snapshots. Peak memory was 183,762,944 bytes under a 2 GiB limit; memory max/oom/oom_kill counters were zero.

## Reproduce the local input checks

Run `python3 -I art04/validate_inputs04.py` from this package. The nine checks use already captured inputs and the production gate functions. They do not execute ART or Android. Root and independent peer reviews are included separately from the actual ART receipt.

All original result bytes and historical status values are retained. There is no install script in this delta. Installation, exact owned-alarm delivery and new-binary Timer regression remain separate requirements. Previous failed Alarm03 and the currently installed e4ff timer evidence are not rewritten or transferred to this candidate.
