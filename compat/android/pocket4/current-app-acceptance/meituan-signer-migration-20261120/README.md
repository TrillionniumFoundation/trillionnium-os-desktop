# Meituan official signer and protected migration evidence

These two observations preserve a real unresolved migration constraint. They
do not authorize removal of the existing package, deletion of its data, a
signer substitution, or a claim that current app data has been migrated.

`SIGNING-LINEAGE-OBSERVATION.json` records the exact SDK 37 signature verifier
and lineage-tool results for the unmodified official Meituan 8.86.4 APK. The
APK has a verified v2 signature under its official certificate and no valid v3
or v3.1 signing lineage that could prove an upgrade from the installed signer.
The original APK identity remained unchanged throughout the inspection.

`PRIVATE-METADATA-SUMMARY.json` records only directory-entry counts obtained
read-only from the already verified complete R2 rollback copy. The CE and DE
areas contain existing regular files, so this is not an empty disposable test
installation. It contains no private file bodies, account classification,
private filenames or keystore contents. Original data/metadata and the verified
backup retained their exact original F9 identities.

The observations keep migration, data continuity and production acceptance
pending. They are included with the Gallery source repair so the remaining
app blocker remains explicit and its evidence is durable.
