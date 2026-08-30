# Session state machine

The executable reference is `crates/hepta-session-core`. Adapters supply events
and monotonic time; the core owns no Servo object, socket, thread, or OS clock.

## Control state

| State | Meaning | Agent mutation |
| --- | --- | --- |
| `Idle` | no input owner | may begin when phase is Ready |
| `AgentObserving` | one Agent observation is active | no second operation |
| `AgentMutating` | one Agent mutation is active | no second operation |
| `AgentNavigating` | one top-level Agent navigation is pending | no human lease or Agent operation |
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
| begin Agent observation (including `page_wait`) | Ready + Idle | `AgentObserving` |
| begin Agent navigation | Ready + Idle | `AgentNavigating` + `NavigationPending` |
| human focus gained | session Ready and no pending Agent navigation (not Closed/Cancelling) | interrupt Agent work, grant bounded lease, `HumanActive` |
| IME started | matching human lease | `HumanImeComposing` |
| DOM committed | session live | increment `mutation_epoch` only |
| semantic snapshot published | session live | increment snapshot revision |
| navigation committed | NavigationPending | increment document/snapshot/mutation; return Ready/Idle |
| browser crashed | session live | increment every identity layer, clear lease, Recovering |
| cancel requested | session live and not Recovering | revoke any human lease, enter `Cancelling`; no new human lease/input |
| cancel completed | `Cancelling` | return `Ready`/`Idle`; defensively keep the human lease empty |
| tick at lease expiry | matching active lease elapsed | clear human control, emit expiry |
| close | any non-terminal state | Closed; clear lease/control |

Cancellation is an ownership boundary: `CancelRequested` immediately revokes
any human lease (and returns human control to `Idle`) before entering
`Cancelling`. Human focus, input, release, and IME events are refused with a
typed phase conflict for the whole cancellation window. `CancelCompleted`
returns the machine to `Ready`/`Idle` and clears the lease defensively, so an
old lease identifier cannot resume input after reconciliation.

D4 may relax read-only observation during human activity only through a new ADR
and consistency/privacy evidence. It may not weaken mutation exclusion.
