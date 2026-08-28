# Session state machine

The executable reference is `crates/hepta-session-core`. Adapters supply events
and monotonic time; the core owns no Servo object, socket, thread, or OS clock.

## Control state

| State | Meaning | Agent mutation |
| --- | --- | --- |
| `Idle` | no input owner | may begin when phase is Ready |
| `AgentObserving` | one Agent observation is active | no second operation |
| `AgentMutating` | one Agent mutation is active | no second operation |
| `HumanActive` | human focus lease owns interaction | refused |
| `HumanImeComposing` | human IME composition owns text input | refused |

## Session phase

| Phase | Meaning | Compatible mutation |
| --- | --- | --- |
| `Ready` | normal operation | subject to control state |
| `NavigationPending` | top-level document transition | none |
| `ModalBlocked` | browser/system modal unresolved | none |
| `CapabilityPending` | typed capability unresolved | none |
| `Cancelling` | cancellation reconciliation | none |
| `Recovering` | browser/session recovery | none |
| `Closed` | terminal | none |

## Key transitions

| Event | Preconditions | Result/effect |
| --- | --- | --- |
| begin Agent mutation | Ready + Idle | `AgentMutating` |
| human focus gained | session not Closed | interrupt Agent work, grant bounded lease, `HumanActive` |
| IME started | matching human lease | `HumanImeComposing` |
| DOM committed | session live | increment `mutation_epoch` only |
| semantic snapshot published | session live | increment snapshot revision |
| navigation committed | NavigationPending | increment document/snapshot/mutation; return Ready/Idle |
| browser crashed | session live | increment every identity layer, clear lease, Recovering |
| tick at lease expiry | matching active lease elapsed | clear human control, emit expiry |
| close | any non-terminal state | Closed; clear lease/control |

D4 may relax read-only observation during human activity only through a new ADR
and consistency/privacy evidence. It may not weaken mutation exclusion.
