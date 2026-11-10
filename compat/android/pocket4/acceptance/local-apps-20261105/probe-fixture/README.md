# Pocket4 local two-editor fixture

The exact installed APK and all five disassembled classes were reviewed. The
actual Probe03 flow completed two independent launch/normal-close rounds, with
14 inputs total: empty confirmation, first-field Unicode entry, distinct second
field entry, exact first-field confirmation, first-field clear and empty result,
then second-field clear. The two fields remained independent. Fresh launch
resets the view by design. No account, network or external business operation is
declared by this small fixture.

The actual result retains matching APK/UID/version/user/epoch and permission
metadata before and after. Exact-UID diagnostics show no fresh crash or ANR;
two new normal-close exit records exist. Tasks915/916 each closed normally and
no input remains pending.

Probe01 failed before launch because its package parser expected the old UID
field name. Probe02 opened and normally closed task914 with zero inputs because
the Android17 native tree presents an empty TextView's hint as its text. Probe03
recognizes only the two exact observed hints and proves the underlying first
editor is empty using the App's real getText()/confirmation path. It does not
rewrite native nodes. Both original failures remain separate from this pass.

This is scoped functional evidence. Ambiguous-selector rejection, complete
signing/engine/resource identity and whole-release coverage remain unqualified.
The private frozen Contacts adapter and original diagnostic module are pinned
by the executed source and result, but are not copied here. Images, account
baselines and raw process/window journals are excluded. These sources describe
completed fixed-Main trials and are not instructions to replay them.
