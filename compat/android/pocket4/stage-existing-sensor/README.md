# Preserve the already staged SensorService candidate

The canonical deployment already contains the independently ABI-qualified
SensorService candidate. The older composition source still expected its staged
file to be absent, appended a new payload and override, and appended its checksum
again. That source could not consume the actual current candidate.

This patch validates the current sealed baseline and retains the existing sensor
payload, install operation, override, checksum and Framework integration records.
The Native phase replaces the engine and bridge profile and adds the complete
ART APEX and pair record. The Audio phase then adds its eight new payloads.
It does not replace the sensor a second time.

| Candidate phase | Checksum rows | Payloads | Android overrides |
|---|---:|---:|---:|
| Current sealed baseline | 43 | 28 | 47 |
| Native pair composed | 45 | 30 | 49 |
| Audio composed | 53 | 38 | 50 |

The current baseline includes two Framework metadata files in addition to the
sensor payload. Both remain sealed. The final source preparation writes 27
candidate files because the existing sensor is preserved. Four runtime
directories remain unchanged. All original Framework proof checks and fresh
runtime requirements still apply.

`preserve-existing-sensor.patch` contains the narrow changes to `stage_model.py`,
`stage_integrate.py` and `stage_audio.py`. It composes with the separate exact
Native release policy and complete Audio APEX guard; it does not replace either
qualification policy. The source fragments here contain ten actual function
bodies extracted byte for byte from the complete prepared stage implementation.
They make the real baseline and composition code portable for focused controls.
Source fingerprints identify the complete implementation from which they came.

Run from any working directory:

```sh
python3 -I -B /path/to/stage-existing-sensor/tests/test_existing_sensor.py
```

Five controls exercise the actual functions: accepting the already present
sensor, rejecting its digest or metadata drift, retaining its payload and two
Framework metadata rows through Native and Audio composition, preserving exact
final counts and the write allowlist, and rejecting the obsolete 40/27/46
runner result. All fixture records and future artifacts are synthetic. The
tests model the existing pinned-reader interface; they do not assert real file
hashes or grant source, artifact, deployment or runtime qualification. No raw
device, account or host logs are shipped.

The complete private source bundle has passed a real read-only `inspect-inputs`
against the current 43/28/47 baseline. That check created no candidate payloads,
performed no service actions, and left `ready_for_apply` false. Actual Native
full outputs and the new desktop Audio generation remain pending; their real
receipt bytes must be bound before preparation and staging can succeed.
