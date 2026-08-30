# Evidence and claim boundary

The machine source for current claims and non-claims is
`manifests/project-state.v1.json`.

| Evidence tier | It may prove | It does not prove |
| --- | --- | --- |
| source shape | files, schemas, graph, static policy | runtime enforcement |
| host unit/property | deterministic pure behavior | headed Servo, image, hardware |
| host integration/fixture | bounded local process/transport behavior | product activation or external authority |
| headed host | real frame/input/recovery on one host environment | Debian image or hardware |
| QEMU image | exact image and virtual-device behavior | headed integration unless repeated in that image |
| integrated QEMU image | headed Servo and services in one exact image | fixed hardware or release |
| fixed hardware | one selected hardware/BOM lane | other hardware or signed release |
| signed release | exact released artifacts, provenance, keys, update/rollback gates | future versions or other hardware |

Candidate head, tested merge, integrated main, and signed artifact identities
are distinct. A PR pass does not prove integrated main. A lower tier never
implies a higher tier. Missing or invalidated evidence remains an explicit
non-claim.
