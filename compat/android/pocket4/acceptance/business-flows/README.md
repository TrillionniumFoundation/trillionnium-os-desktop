# Current-epoch business acceptance

Status: **NO-GO**. These records describe actual bounded App flows after the presenter/R16 Main activation, not whole-App readiness.

| App | Verified portion | Observed blocker or untested portion |
| --- | --- | --- |
| [Bilibili](../../evidence/business-bilibili-20261104.json) | Public search for 微积分; matching video opened; three private screenshots independently inspected show progression from title card to instructor/desktop and then textbook content; actual R16 mapped; normal close preserves the preexisting Home. | Audio was not listened to. Pause/seek, in-app return, reopen and cold-start qualification remain open. The first read-only startup dump failed and remains recorded. |
| [Marriott](../../evidence/business-marriott-20261104.json) | Exact fresh crash attribution from the parent capture. | Single launch failed with SIG11 at 09:35:50 UTC. No completed-task receipt or business success; the original outcome-unknown launch is retained. |
| [Beike](../../evidence/business-beike-20261104.json) | Beijing home, exact 望京 readback, matching region/community suggestions, actual R16 mapping, normal close. | Region selection triggered the App's login route. LoginActivity was cleared by another App-originated login intent; OneLoginRouterActivity remained visibly blank. Results/details/return are unqualified, with no authentication attempt or bypass. |
| [Meituan Takeout](../../evidence/business-meituan-20261104.json) | Single native launch, actual R16 mapping and normal owned-task close. | Startup repeatedly calls System.exit(0); matching fresh main-process EXIT_SELF/0 records were captured. The task remained on SplashAdActivity and merchant query/menu were never reached. No click or text input occurred. |

## Evidence discipline

Each flow pins the explicit activation receipt, recorder source, helper sources, configuration and init/zygote/system_server/SurfaceFlinger generation. A changed epoch stops the flow. Every mutation has a unique saved intent; uncertain actions are not replayed. Cleanup removes only a newly owned leaf established by the successful launch receipt and preserves other tasks.

Bilibili's archive review rehashed 40 stdout/stderr pairs and inspected all three private resized images. Media-session position was zero and is not used to prove progress; the actual visible content progression is the evidence. Beike's screenshot confirms a real white surface, while retained lifecycle logs refine the component to the login router. Its post-close diagnostics are explicitly labeled as such, not presented as a live pre-close process snapshot.

A controller response timeout during Beike close was reconciled using the identical durable operation key and returned the original job as reused. The original close had already succeeded; it was not repeated. The UI helper did not report an unknown mutation in that flow.

Meituan's read-only observation failed with `WINDOW_CHANGED` and produced no image; that failure is retained. Later exit-info and App logs establish repeated self-exit, while the precise caller/trigger remains unknown. Its initial generic WebView and later empty node tree are not presented as visually verified blank merchant pages. Original resource limits stayed fixed and OOM counters remained zero; the increase in memory.high events does not establish causality.

Only deidentified summaries and original artifact hashes are distributed here. Private images, raw UI, account data and commercial crash logs remain excluded. Historical results remain in [readiness-status.json](../../readiness-status.json); an old-epoch success does not carry into this epoch.
