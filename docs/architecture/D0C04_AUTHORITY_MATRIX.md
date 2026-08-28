# D0C-04 authority matrix

| Capability | D0C-04 state | Owner of later decision |
| --- | --- | --- |
| Decode canonical Browser API request | implemented in source | AgentPort mechanism |
| Authenticate an already-connected peer | implemented in source | transport mechanism |
| Invoke one typed handler | implemented in source | AgentPort mechanism |
| Bind and hash the response | implemented in source | AgentPort mechanism |
| Bind a socket path | closed | D0C-05/systemd custody |
| Accept a product connection | closed | D0C-05 plus explicit enable policy |
| Map TaskFlow principal to service identity | closed | later identity checkpoint |
| Dispatch BrowserActor | closed | D3 PageOwner runtime |
| Start or control Servo | closed | D0A/D2 browser runtime |
| Grant a system capability | closed | D6 capability service |
| Authorize an external effect | closed | later policy/effect gate |
| Automatically retry an indeterminate effect | forbidden | semantic Agent/reconciliation |

The current D0 handler returns truthful unavailability or policy refusal; it
never fabricates browser execution.
